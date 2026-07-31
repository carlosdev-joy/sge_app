"""
Correção C da revisão adversarial: contrato de leitura/escrita da API.

Dois defeitos, ambos com perda silenciosa de configuração já gravada:

  1. hora_virada / nao_iniciar_antes / hora_limite_dependencia eram gravados e
     NUNCA lidos de volta — o formulário carregava vazio e todo save os zerava.
     Zerar a virada parte em dois dias a corrida que atravessa a meia-noite, que
     é justamente o que a feature existe para evitar.
  2. o replace-all de dependências fazia DELETE + INSERT sem deduplicar e
     engolindo exceção: um `depends_on` legado com nome repetido deixava o
     pipeline sem dependência na tabela — e a tabela é a fonte da geração.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def pipes():
    for m in ["pyodbc", "fastapi", "fastapi.responses", "pydantic", "httpx"]:
        sys.modules.setdefault(m, MagicMock())
    sys.path.insert(0, str(_ROOT / "api"))
    spec = importlib.util.spec_from_file_location(
        "pipelines_contrato_test", _ROOT / "api/routers/pipelines.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ───────────────────────────── Deduplicação ────────────────────────────────

def test_dedup_remove_repetidos_preservando_ordem(pipes):
    assert pipes.deduplicar(["A", "B", "A", "C"]) == ["A", "B", "C"]


def test_dedup_ignora_caixa(pipes):
    """A collation do SQL Server é case-insensitive: 'A,a' viola o índice único."""
    assert pipes.deduplicar(["PIPE_A", "pipe_a"]) == ["PIPE_A"]


def test_dedup_limpa_espacos_e_vazios(pipes):
    assert pipes.deduplicar([" A ", "", "  ", "B"]) == ["A", "B"]


def test_dedup_aceita_gerador(pipes):
    """O handler passa um generator expression."""
    assert pipes.deduplicar(d for d in "A,A,B".split(",")) == ["A", "B"]


# ─────────────── Gravação: degrada sem migration, propaga o resto ──────────

def test_sem_a_migration_degrada_sem_apagar_nada(pipes):
    """O DELETE é a primeira instrução: falha antes de tocar em qualquer linha."""
    cur = MagicMock()
    cur.execute.side_effect = RuntimeError("Invalid object name")
    assert pipes._gravar_dependencias(cur, "C", ["A"], None) is False


def test_falha_depois_do_delete_propaga(pipes):
    """Engolir aqui commitava o DELETE com os INSERTs pela metade.

    O pipeline ficava sem dependência na tabela — que é a fonte da geração — e
    voltava a rodar por cron, sozinho, com a tela mostrando 200.
    """
    cur = MagicMock()
    chamadas = {"n": 0}

    def execute(sql, params=None):
        chamadas["n"] += 1
        if "INSERT" in sql and chamadas["n"] > 2:
            raise RuntimeError("violação de constraint")

    cur.execute.side_effect = execute
    with pytest.raises(RuntimeError):
        pipes._gravar_dependencias(cur, "C", ["A", "B"], None)


def test_grava_a_lista_deduplicada(pipes):
    cur = MagicMock()
    assert pipes._gravar_dependencias(cur, "C", ["A", "a", "B"], "u1") is True
    inserts = [c for c in cur.execute.call_args_list
               if "INSERT INTO dbo.etl_pipeline_dependencia" in str(c.args[0])]
    assert len(inserts) == 2


# ───────────────── Leitura: os três campos voltam do GET ───────────────────

def test_select_devolve_os_campos_da_janela(pipes):
    """Sem isso o form carrega vazio e o save zera o banco."""
    fonte = (_ROOT / "api/routers/pipelines.py").read_text(encoding="utf-8")
    assert "janela_cols" in fonte
    assert "CONVERT(VARCHAR(5), hora_virada, 108) AS hora_virada" in fonte
    # E o mapeamento posicional precisa das três chaves, na mesma ordem.
    assert '"hora_virada", "nao_iniciar_antes", "hora_limite_dependencia",' in fonte


def test_select_degrada_sem_a_migration_067(pipes):
    fonte = (_ROOT / "api/routers/pipelines.py").read_text(encoding="utf-8")
    assert "NULL AS hora_virada, NULL AS nao_iniciar_antes" in fonte
    assert "COLUMN_NAME='hora_virada'" in fonte


# ─────────────── Escrita: campo ausente no body não é tocado ───────────────

def test_update_da_janela_so_toca_o_que_veio_no_body(pipes):
    """O diálogo de inativar monta um body próprio, sem esses campos.

    Com UPDATE incondicional, inativar um pipeline apagava a janela dele — e
    reativar não restaurava.
    """
    fonte = (_ROOT / "api/routers/pipelines.py").read_text(encoding="utf-8")
    assert "if c in body]" in fonte
    assert "if _janela:" in fonte
    # A cláusula é montada a partir da lista filtrada, não fixa.
    assert '", ".join(f"{c}=?" for c, _ in _janela)' in fonte


def test_rollback_explicito_nos_tres_caminhos_de_erro(pipes):
    fonte = (_ROOT / "api/routers/pipelines.py").read_text(encoding="utf-8")
    trecho = fonte[fonte.index("def register_pipeline"):]
    assert trecho.count("_rollback_silencioso(locals().get(\"conn\"))") == 3


def test_rollback_nao_mascara_o_erro_original(pipes):
    """Falha no rollback não pode virar a exceção que o usuário vê."""
    conn = MagicMock()
    conn.rollback.side_effect = RuntimeError("conexão já morta")
    pipes._rollback_silencioso(conn)   # não levanta
    pipes._rollback_silencioso(None)   # tolera ausência
