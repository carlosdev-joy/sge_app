"""api/services/agentes_ferramentas.py — as ferramentas novas da F2b
(spec docs/spec-agentes-datastage.md): `isx_info_do_job`, `mensagem_erro_lineage`,
`nome_dsx_valido`, `projeto_tem_dsx`, `ferramenta_dsx_consulta`.

O que estes testes prendem, e por que cada um existe:

  1. **`isx_info_do_job` nunca levanta** — devolve `None` para job fora de
     pipeline, pipeline sem projeto, ou nó que não é DataStage (a mesma
     régua de `routers.lineage_isx._info_do_job`, sem HTTPException).

  2. **`nome_dsx_valido`/`projeto_tem_dsx`** — path traversal recusado
     (critério 7 da F2b); só reconhece projeto que tem `.dsx` de verdade.

  3. **`ferramenta_dsx_consulta` nunca toca SSH/dsjob** — só o `DSXEngine`
     sobre arquivo local; toda resposta traz `dsx_arquivo`/`dsx_data`
     (critério 8); operação fora da allowlist é recusada sem rodar nada.

Nada aqui toca banco, SSH nem rede de verdade: tudo dublê/arquivo temporário.
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from services import agentes_ferramentas as af  # noqa: E402


# ═══════════ 0. executor compartilhado — nenhum pool novo ══════════════════

def test_isx_executor_e_o_mesmo_objeto_do_router_lineage_isx():
    """Critério 3 da F2b: 'o executor é o mesmo... nenhum pool novo' — não
    basta ter o mesmo teto (2 workers): tem que ser o MESMO objeto Python,
    senão 3 pedidos simultâneos rodariam 2+2 (dois pools) em vez de 2+1
    (fila compartilhada)."""
    from routers import lineage_isx as rt
    assert af.ISX_EXECUTOR is rt._EXECUTOR_ISX  # noqa: SLF001
    assert af.isx_no_executor is rt._no_executor  # noqa: SLF001
    assert af.ISX_TETO_EXTRAIR_S == rt._TETO_EXTRAIR_S == 60  # noqa: SLF001


# ═══════════ 1. isx_info_do_job ══════════════════════════════════════════════

class _CurJobPipeline:
    """Responde `job_do_pipeline` — mesmo shape de `etl_pipeline_job`×`etl_pipeline`."""

    def __init__(self, row=None):
        self._row = row

    def execute(self, sql, params=None):
        pass

    def fetchone(self):
        return self._row


def test_isx_info_do_job_mapeado_e_datastage_devolve_info():
    cur = _CurJobPipeline(row=("BI_CVP", "datastage", "PIPE_VIDA", "JobX"))
    info = af.isx_info_do_job(cur, "PIPE_VIDA", "JobX")
    assert info == {"ds_project": "BI_CVP", "job_type": "datastage",
                    "pipeline_name": "PIPE_VIDA", "job_name": "JobX"}


def test_isx_info_do_job_nao_mapeado_e_none():
    cur = _CurJobPipeline(row=None)
    assert af.isx_info_do_job(cur, "PIPE_X", "JobY") is None


def test_isx_info_do_job_sem_projeto_e_none():
    cur = _CurJobPipeline(row=("", "datastage", "PIPE_VIDA", "JobX"))
    assert af.isx_info_do_job(cur, "PIPE_VIDA", "JobX") is None


def test_isx_info_do_job_nao_datastage_e_none():
    cur = _CurJobPipeline(row=("BI_CVP", "sql", "PIPE_VIDA", "JobX"))
    assert af.isx_info_do_job(cur, "PIPE_VIDA", "JobX") is None


# Achado real da revisão adversarial da F2b: `redigir()` (que mascara até o
# fim da LINHA) aplicado ao JSON compacto (`json.dumps` sem `indent`, uma
# única linha lógica) do `isx_extrair`/`dsx_consulta` apagava a resposta
# INTEIRA sempre que qualquer parte dela tivesse uma keyword sensível — o
# lineage útil (stages, SQL, tabelas) sumia atrás da máscara, não só o
# segredo. `redigir_estrutura()` aplica `redigir()` por STRING FOLHA, nunca
# ao JSON inteiro, isolando o dano a cada campo.
def test_redigir_estrutura_preserva_o_dado_util_ao_redor_do_campo_sensivel():
    payload = {
        "gravado": False, "job_name": "JobX", "ds_project": "BI_CVP",
        "parameters": [
            {"name": "DB_PASSWORD", "type": "Encrypted", "default": "***", "description": "senha de conexao"},
            {"name": "OUTRO_PARAM", "type": "string", "default": "valor_normal", "description": ""},
        ],
        "flow": {"stages": [{"stage_name": "OracleConnector_1", "database_name": "PRODDB",
                             "sql_expression": "SELECT * FROM CLIENTES"}]},
        "last_modified": "2026-09-01T10:00:00",
    }
    import json
    texto = json.dumps(af.redigir_estrutura(payload), ensure_ascii=False, default=str)
    # o dado de LINEAGE (o que a ferramenta existe para trazer) sobrevive
    assert "SELECT * FROM CLIENTES" in texto
    assert "OracleConnector_1" in texto
    assert "PRODDB" in texto
    assert "OUTRO_PARAM" in texto and "valor_normal" in texto  # campo NÃO sensível intocado


def test_redigir_estrutura_ainda_mascara_segredo_em_texto_livre():
    payload = {"job_description": "Uses FTP account ftpuser, password: Summer2026!",
              "outro_campo": "sem nada de sensivel aqui"}
    import json
    texto = json.dumps(af.redigir_estrutura(payload), ensure_ascii=False, default=str)
    assert "Summer2026!" not in texto
    assert "sem nada de sensivel aqui" in texto  # campo IRMÃO não é afetado


def test_redigir_estrutura_recursiva_em_listas_aninhadas():
    payload = {"stages": [{"a": "ok1"}, {"b": "token: abc123XYZ", "c": "ok2"}]}
    import json
    texto = json.dumps(af.redigir_estrutura(payload), ensure_ascii=False, default=str)
    assert "abc123XYZ" not in texto
    assert "ok1" in texto and "ok2" in texto


# ═══════════ 2. mensagem_erro_lineage ════════════════════════════════════════

class _ISXErrorFake(Exception):
    def __init__(self, status, detail, interno=None):
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.interno = interno


def test_mensagem_erro_lineage_isx_error():
    e = _ISXErrorFake(404, "Job X não encontrado.", interno="detalhe sensível interno")
    msg = af.mensagem_erro_lineage(e)
    assert msg == "Job X não encontrado."
    assert "detalhe sensível interno" not in msg


def test_mensagem_erro_lineage_http_exception():
    from fastapi import HTTPException
    e = HTTPException(status_code=503, detail="Lineage ISX não configurado.")
    assert af.mensagem_erro_lineage(e) == "Lineage ISX não configurado."


def test_mensagem_erro_lineage_generica_nao_vaza_traceback():
    msg = af.mensagem_erro_lineage(RuntimeError("boom interno"))
    assert "boom interno" not in msg
    assert "RuntimeError" in msg


# ═══════════ 3. nome_dsx_valido / projeto_tem_dsx ════════════════════════════

@pytest.mark.parametrize("bruto", ["../etc/passwd", "a/b", "a\\b", "..", "foo..bar", "", "   "])
def test_nome_dsx_valido_recusa_path_traversal(bruto):
    assert af.nome_dsx_valido(bruto) is None


@pytest.mark.parametrize("bruto,esperado", [
    ("BI_CVP", "BI_CVP"), ("BI_CVP.dsx", "BI_CVP"), ("  BI_CVP  ", "BI_CVP"),
])
def test_nome_dsx_valido_aceita_nome_normal(bruto, esperado):
    assert af.nome_dsx_valido(bruto) == esperado


def test_projeto_tem_dsx_usa_a_lista_local(monkeypatch):
    monkeypatch.setattr(af, "_projetos_com_dsx", lambda: ["BI_CVP", "BI_VIDA"])
    assert af.projeto_tem_dsx("BI_CVP") is True
    assert af.projeto_tem_dsx("bi_cvp") is True  # ignora caixa, mesma régua de resolver_projeto
    assert af.projeto_tem_dsx("OUTRO") is False


# ═══════════ 4. ferramenta_dsx_consulta ══════════════════════════════════════

class _DSXEngineFake:
    """Dublê do DSXEngine — nunca toca disco/SSH de verdade."""

    def __init__(self, diretorio_base="/tmp/dsx-fake"):
        self.diretorio_base = diretorio_base
        self.chamadas: list[tuple] = []

    def listar_jobs(self, projeto):
        self.chamadas.append(("listar_jobs", projeto))
        return {"sucesso": True, "project_name": projeto, "jobs": ["JobA", "JobB"]}

    def listar_pastas(self, projeto):
        self.chamadas.append(("listar_pastas", projeto))
        return {"sucesso": True, "project_name": projeto, "pastas": [{"category": "Jobs", "total_jobs": 2}]}

    def buscar_campo(self, projeto, termo, **kw):
        self.chamadas.append(("buscar_campo", projeto, termo, kw))
        return {"sucesso": True, "termo": termo, "jobs": []}

    def extrair(self, projeto, job_name):
        self.chamadas.append(("extrair", projeto, job_name))
        return {"sucesso": True, "project_name": projeto, "job_name": job_name, "dados": []}


@pytest.fixture
def _motor_fake(monkeypatch):
    instancia = _DSXEngineFake()
    monkeypatch.setattr(af, "_dsx_engine_cls", lambda: (lambda: instancia))
    return instancia


@pytest.mark.asyncio
async def test_dsx_consulta_listar_jobs_delega_ao_engine(_motor_fake):
    r = await af.ferramenta_dsx_consulta("BI_CVP", "listar_jobs", {})
    assert _motor_fake.chamadas == [("listar_jobs", "BI_CVP")]
    assert r["jobs"] == ["JobA", "JobB"]


@pytest.mark.asyncio
async def test_dsx_consulta_buscar_campo_repassa_args(_motor_fake):
    await af.ferramenta_dsx_consulta("BI_CVP", "buscar_campo",
                                     {"termo": "CNPJ", "exato": True, "pasta": "Jobs"})
    nome, projeto, termo, kw = _motor_fake.chamadas[0]
    assert (nome, projeto, termo) == ("buscar_campo", "BI_CVP", "CNPJ")
    assert kw["exato"] is True and kw["pasta"] == "Jobs"


@pytest.mark.asyncio
async def test_dsx_consulta_extrair_um_job(_motor_fake):
    r = await af.ferramenta_dsx_consulta("BI_CVP", "extrair", {"job_name": "JobX"})
    assert _motor_fake.chamadas == [("extrair", "BI_CVP", "JobX")]
    assert r["job_name"] == "JobX"


@pytest.mark.asyncio
async def test_dsx_consulta_operacao_fora_da_allowlist_nao_chama_o_engine(_motor_fake):
    with pytest.raises(ValueError):
        await af.ferramenta_dsx_consulta("BI_CVP", "exportar", {})
    assert _motor_fake.chamadas == []  # nunca chegou a instanciar/chamar nada


@pytest.mark.asyncio
async def test_dsx_consulta_nunca_toca_ssh_nem_dsjob(monkeypatch, _motor_fake):
    """Critério 7 da F2b: `dsx_consulta` não abre SSH nem chama `dsjob`."""
    def _explode(*a, **k):
        raise AssertionError("dsx_consulta não deveria tocar SSH/dsjob")
    monkeypatch.setattr(af, "run_dsjob", _explode)
    monkeypatch.setattr(af, "ssh_configured", _explode)
    await af.ferramenta_dsx_consulta("BI_CVP", "listar_jobs", {})
    # se chegou aqui sem AssertionError, run_dsjob/ssh_configured nunca foram chamados


@pytest.mark.asyncio
async def test_dsx_consulta_traz_nome_e_data_do_arquivo(monkeypatch, _motor_fake):
    """Critério 8 da F2b: toda resposta de `dsx_consulta` traz o nome e a
    data do arquivo (é um retrato, não o estado agora)."""
    with tempfile.TemporaryDirectory() as tmp:
        caminho = os.path.join(tmp, "BI_CVP.dsx")
        with open(caminho, "w") as f:
            f.write("conteudo")
        _motor_fake.diretorio_base = tmp
        r = await af.ferramenta_dsx_consulta("BI_CVP", "listar_jobs", {})
    assert r["dsx_arquivo"] == "BI_CVP.dsx"
    assert r["dsx_data"] is not None  # a data de modificação do arquivo real


@pytest.mark.asyncio
async def test_dsx_consulta_arquivo_ausente_nao_levanta(_motor_fake):
    """`_dsx_data_arquivo` nunca levanta — arquivo apagado entre a listagem
    e a consulta (ou caminho nunca existiu) devolve `dsx_data: None`."""
    r = await af.ferramenta_dsx_consulta("BI_CVP", "listar_jobs", {})
    assert r["dsx_data"] is None


@pytest.mark.asyncio
async def test_dsx_consulta_estoura_o_teto_e_erro_nomeado(monkeypatch, _motor_fake):
    """Critério 10 da F2b: um `.dsx` grande não pode travar a rodada — o
    parse roda num executor com prazo (`asyncio.wait_for` dentro da própria
    `ferramenta_dsx_consulta`, sem precisar de proteção extra do chamador)."""
    import time as _t

    def _lento(projeto):
        _t.sleep(0.5)
        return {"sucesso": True, "jobs": []}
    monkeypatch.setattr(_motor_fake, "listar_jobs", _lento)
    monkeypatch.setattr(af, "DSX_TETO_S", 0.05)
    with pytest.raises((asyncio.TimeoutError, TimeoutError)):
        await af.ferramenta_dsx_consulta("BI_CVP", "listar_jobs", {})
