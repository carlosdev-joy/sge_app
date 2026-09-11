"""Catálogo de modelos de e-mail — `api/services/email_modelos.py` e a semente
da migration 112 (spec docs/spec-email-modelos-e-navegacao.md, F2).

O vínculo é VIVO: o nó guarda só o `modelo_id` e o corpo é lido no envio. Por
isso o que se prende aqui tem peso de produção — um erro no catálogo chega em
todos os fluxos que usam o modelo, de uma vez:

  1. **`validar`** usa a MESMA régua do nó para o corpo e mede nome/descrição
     em UTF-16 (o que a coluna NVARCHAR conta).
  2. **`pipelines_que_usam`** é a trava da exclusão: casa no DELIMITADOR, e a
     falha de leitura PROPAGA — devolver vazio diria "não está em uso" e
     deixaria apagar um modelo que N fluxos usam.
  3. **um padrão só**: criar/atualizar como padrão zera o anterior.
  4. **semente da 112** guardada pelo catálogo VAZIO, não pelo nome: renomeado,
     o nome não casaria e a semente voltaria criando um segundo padrão.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from services import email_modelos as M  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
MIGRACAO = RAIZ / "sql" / "migrations" / "112_email_modelos.sql"

LINHA = (1, "Aviso de fim de carga", "Use no fim da carga", "[Orquestra] {pipeline}",
         "<html>corpo</html>", 1, 1, 1, "ADM1", "2026-09-11 10:00:00", None)


class _Cur:
    """Cursor de mentira: registra o SQL e devolve linhas combinadas."""

    def __init__(self, linhas=(LINHA,), tabela=True, usos=()):
        self.linhas, self.tabela, self.usos = list(linhas), tabela, list(usos)
        self.execs: list[tuple[str, tuple]] = []
        self._rows: list = []

    def execute(self, sql, params=None):
        params = tuple(params or ())
        self.execs.append((sql, params))
        s = " ".join(sql.lower().split())
        if "information_schema.tables" in s:
            self._rows = [(1 if self.tabela else 0,)]
        elif "from dbo.etl_pipeline_job" in s:
            # o LIKE de verdade: a trava só vale se casar como o banco casaria
            self._rows = [(nome,) for nome, json_ in self.usos
                          if any(_like(json_, p) for p in params)]
        elif s.startswith("select id, nome"):
            linhas = self.linhas
            if "where ativo = 1" in s:
                linhas = [l for l in linhas if l[6]]
            if "where id = ?" in s:
                linhas = [l for l in linhas if l[0] == params[0]]
            self._rows = linhas
        elif "output inserted.id" in s:
            self._rows = [(42,)]
        else:
            self._rows = []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def sqls(self, trecho: str) -> list[tuple[str, tuple]]:
        return [e for e in self.execs if trecho.lower() in " ".join(e[0].lower().split())]


def _like(valor: str, padrao: str) -> bool:
    """LIKE do SQL Server com `%` (o único curinga que os padrões usam)."""
    return re.fullmatch(".*".join(re.escape(p) for p in padrao.split("%")), valor,
                        re.S) is not None


# ═══════════ tabela e listagem ═══════════════════════════════════════════════

def test_tabela_existe():
    assert M.tabela_existe(_Cur()) is True
    assert M.tabela_existe(_Cur(tabela=False)) is False


def test_listar_sem_corpo_troca_o_html_pelo_tamanho():
    """A lista do Admin não pode trafegar o HTML inteiro de cada modelo."""
    m = M.listar(_Cur(), com_corpo=False)[0]
    assert m["corpo_tamanho"] == len("<html>corpo</html>") and "corpo" not in m
    assert M.listar(_Cur())[0]["corpo"] == "<html>corpo</html>"


def test_listar_apenas_ativos_e_o_default_de_trazer_todos():
    inativo = (2, "Velho", None, None, "x", 1, 0, 0, "ADM1", "2026-09-11 10:00:00", None)
    cur = _Cur(linhas=(LINHA, inativo))
    assert [m["id"] for m in M.listar(cur)] == [1, 2]
    assert [m["id"] for m in M.listar(cur, apenas_ativos=True)] == [1]


def test_linha_devolve_booleanos_de_verdade():
    """`CAST(... AS INT)` volta 0/1: sem a conversão o front receberia número
    onde espera true/false, e `m.padrao` nunca reprovaria."""
    m = M.obter(_Cur(), 1)
    assert m["html"] is True and m["ativo"] is True and m["padrao"] is True
    assert M.obter(_Cur(), 99) is None


# ═══════════ validação ═══════════════════════════════════════════════════════

BOM = {"nome": "Institucional", "descricao": "Use sempre", "assunto": "[Orquestra] {pipeline}",
       "corpo": "O fluxo {pipeline} terminou em {data}.", "html": True,
       "ativo": True, "padrao": False}


def test_validar_aceita_e_normaliza():
    valores, erros = M.validar({**BOM, "nome": "  Institucional  "})
    assert erros == []
    assert valores["nome"] == "Institucional" and valores["padrao"] is False
    assert valores["html"] is True and valores["ativo"] is True
    # ausentes viram os defaults úteis: HTML ligado e ativo
    valores, erros = M.validar({"nome": "X", "corpo": "texto"})
    assert erros == [] and valores["html"] is True and valores["ativo"] is True
    assert valores["descricao"] is None and valores["assunto"] is None


def test_validar_exige_nome_e_corpo():
    assert any("informe o nome" in e for e in M.validar({**BOM, "nome": "  "})[1])
    assert M.validar({**BOM, "corpo": "   "})[1]
    assert M.validar("texto")[1] == ["corpo inválido"]


def test_nome_e_descricao_medidos_em_utf16():
    """NVARCHAR conta UTF-16: 100 emoji são 200 unidades e estourariam a coluna
    de 120 num `len()` ingênuo — 500 opaco no INSERT em vez de 422."""
    assert M.validar({**BOM, "nome": "😀" * 61})[1]          # 122 unidades
    assert M.validar({**BOM, "nome": "😀" * 60})[1] == []    # 120, no limite
    assert M.validar({**BOM, "descricao": "😀" * 201})[1]
    assert any("mais de 120" in e for e in M.validar({**BOM, "nome": "a" * 121})[1])


def test_nome_com_quebra_de_linha_e_recusado():
    assert any("quebra de linha" in e for e in M.validar({**BOM, "nome": "Aviso\nBcc: x@y"})[1])


def test_assunto_sugerido_e_opcional_mas_passa_pela_regua():
    assert M.validar({**BOM, "assunto": ""})[1] == []
    assert any("assunto sugerido" in e for e in M.validar({**BOM, "assunto": "Fim\nBcc: x@y"})[1])


def test_marcadores_booleanos_recusam_texto():
    for campo in ("html", "ativo", "padrao"):
        assert M.validar({**BOM, campo: "sim"})[1], campo


def test_corpo_passa_pela_mesma_regua_do_no():
    """Um corpo que o ENVIO recusaria não pode entrar no catálogo e quebrar N
    fluxos de uma vez."""
    from services import email_mime as em
    gigante = "x" * (em.LIMITE_CORPO + 1)
    assert M.validar({**BOM, "corpo": gigante})[1] == [em.validar_corpo(gigante)[1]]


# ═══════════ um padrão só ════════════════════════════════════════════════════

def test_criar_como_padrao_zera_o_anterior():
    cur = _Cur()
    assert M.criar(cur, {**BOM, "padrao": True, "descricao": None, "assunto": None}, "ADM1") == 42
    assert cur.sqls("set padrao = 0"), "o padrão anterior continuou marcado"
    cur = _Cur()
    M.criar(cur, {**BOM, "padrao": False, "descricao": None, "assunto": None}, "ADM1")
    assert not cur.sqls("set padrao = 0")


def test_atualizar_como_padrao_poupa_o_proprio_id():
    """Zerar sem exceção apagaria o padrão que acabou de ser marcado."""
    cur = _Cur()
    M.atualizar(cur, 7, {**BOM, "padrao": True, "descricao": None, "assunto": None})
    zerar = cur.sqls("set padrao = 0")[0]
    assert "id <> ?" in zerar[0] and zerar[1] == (7,)


def test_criado_por_cabe_na_coluna():
    cur = _Cur()
    M.criar(cur, {**BOM, "descricao": None, "assunto": None}, "M" * 300)
    assert len(cur.execs[-1][1][-1]) == 100


# ═══════════ a trava da exclusão ═════════════════════════════════════════════

USOS = [
    ("FLUXO_QUE_USA_O_4", '{"modelo_id": 4, "assunto": "x"}'),
    ("FLUXO_QUE_USA_O_4_SEM_ESPACO", '{"modelo_id":4}'),
    ("FLUXO_QUE_USA_O_40", '{"modelo_id": 40, "assunto": "x"}'),
    ("FLUXO_QUE_USA_O_14", '{"assunto": "x", "modelo_id": 14}'),
]


def test_pipelines_que_usam_casa_no_delimitador_e_nao_no_numero():
    """Sem terminar em `,` ou `}`, `"modelo_id": 4` casaria com o 40 e com o
    14 — e o admin veria a exclusão do 4 recusada nomeando fluxos alheios."""
    achados = M.pipelines_que_usam(_Cur(usos=USOS), 4)
    assert achados == ["FLUXO_QUE_USA_O_4", "FLUXO_QUE_USA_O_4_SEM_ESPACO"]
    assert M.pipelines_que_usam(_Cur(usos=USOS), 40) == ["FLUXO_QUE_USA_O_40"]
    assert M.pipelines_que_usam(_Cur(usos=USOS), 14) == ["FLUXO_QUE_USA_O_14"]
    assert M.pipelines_que_usam(_Cur(usos=USOS), 7) == []


def test_pipelines_que_usam_so_olha_no_de_email():
    cur = _Cur(usos=USOS)
    M.pipelines_que_usam(cur, 4)
    sql = " ".join(cur.execs[-1][0].lower().split())
    assert "job_type = 'email'" in sql and "notify_json is not null" in sql


def test_falha_de_leitura_propaga():
    """Engolir a exceção e devolver [] diria 'não está em uso' — e deixaria
    apagar um modelo que N fluxos usam, que é o defeito que a trava existe
    para evitar."""
    class _Fora(_Cur):
        def execute(self, sql, params=None):
            raise RuntimeError("Login timeout expired")

    with pytest.raises(RuntimeError):
        M.pipelines_que_usam(_Fora(), 4)


def test_excluir_e_por_id():
    cur = _Cur()
    M.excluir(cur, 3)
    assert cur.execs[-1][1] == (3,) and "delete from dbo.etl_email_modelo" in cur.execs[-1][0].lower()


# ═══════════ semente da migration 112 ════════════════════════════════════════

def test_semente_guardada_pelo_catalogo_vazio():
    """Guarda por NOME re-inseria a semente se o admin renomeasse o modelo — e
    como ela entra com `padrao = 1`, o catálogo ficaria com DOIS padrões."""
    sql = MIGRACAO.read_text(encoding="utf-8")
    guarda = re.search(r"IF NOT EXISTS \(SELECT 1 FROM dbo\.etl_email_modelo([^)]*)\)", sql)
    assert guarda, "a semente precisa de uma guarda de idempotência"
    assert "where" not in guarda.group(1).lower(), (
        "a guarda não pode ser por nome: renomeado, o modelo voltaria duplicado")


def test_semente_entra_como_padrao_unico_e_ativa():
    sql = MIGRACAO.read_text(encoding="utf-8")
    assert sql.lower().count("insert into dbo.etl_email_modelo") == 1
    assert "ux_etl_email_modelo_nome" in sql          # nome único: a lista de escolha não repete
    assert "email_exigir_modelo" in sql               # o interruptor nasce desligado
