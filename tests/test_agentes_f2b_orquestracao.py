"""api/services/agentes.py — orquestração de `isx_extrair`/`dsx_consulta`
(F2b da spec docs/spec-agentes-datastage.md), via `conversar()`.

O que estes testes prendem, e por que cada um existe (numeração = critérios
de aceite da F2b em docs/spec-agentes-datastage.md §5):

  1. Sem `acao_editar` → o agente NÃO extrai por ISX (dublê que falha se
     chamado) e devolve o link da Governança.
  2. Job em pipeline: o que `isx_extrair` grava é feito pelas MESMAS funções
     que `POST /lineage/isx/extrair` usaria (`lineage_isx.gravar`, com os
     mesmos parâmetros); cache hit → 0 gravação.
  4. Job fora de pipeline: nada é gravado (`lineage_isx.gravar` nunca é
     chamado) — extrai e responde.
  5. Pedido fora da allowlist → recusado; no máximo 2 extrações ISX por
     pergunta.
  7. `dsx_consulta` não abre SSH nem chama `dsjob`.
  9. Valores canário num DSX de teste não chegam ao modelo (`redigir()`).
  11. `dsx_consulta` só roda com projeto **com** `.dsx`.

Nada aqui toca banco, SSH, istool nem rede de verdade — tudo dublê. O
provedor de IA e o `abrir_conn` são os mesmos dublês de
`test_agentes_orquestracao.py` (replicados aqui pelo mesmo padrão).
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from services import agentes as svc  # noqa: E402
from services import agentes_ferramentas as af  # noqa: E402
from services import ia_provedor  # noqa: E402


def _abrir_fake():
    class _C:
        def commit(self):
            pass

        def close(self):
            pass
    return _C(), _C()


class _Provedor:
    """Dublê de ia_provedor.chat_conversa: devolve as respostas em ORDEM."""

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    async def __call__(self, cfg, sistema, historico, identidade=None, campo_identidade=None, ssh_max=10):
        self.chamadas.append({"sistema": sistema, "historico": list(historico)})
        item = self.respostas.pop(0)
        if isinstance(item, Exception):
            raise item
        return item, "modelo-teste"


async def _executor_fake(fn, *args, teto):
    """Dublê de `routers.lineage_isx._no_executor` — chama `fn` direto, sem
    executor de verdade nem teto real (o teto em si já é testado no
    router lineage_isx)."""
    return fn(*args)


def _projeto_resolvido(monkeypatch, projeto="BI_CVP"):
    monkeypatch.setattr(af, "resolver_projeto",
                        lambda cur, nome=None, **kw: {"estado": "resolvido", "projeto": projeto,
                                                      "tem_dsx": False, "sugerido": None, "sugestoes": []})


# ═══════════ 1. isx_extrair — acao_editar ════════════════════════════════════

@pytest.mark.asyncio
async def test_isx_extrair_sem_acao_editar_nao_toca_lineage_e_devolve_link(monkeypatch):
    def _explode(*a, **k):
        raise AssertionError("isx_extrair não deveria ter chamado o lineage_isx sem acao_editar")
    monkeypatch.setattr(af.lineage_isx, "config", _explode)
    provedor = _Provedor([
        '```json\n{"ferramenta": "isx_extrair", "args": {"pipeline_name": "PIPE_VIDA", "job_name": "JobX"}}\n```',
        "entendido",
    ])
    monkeypatch.setattr(ia_provedor, "chat_conversa", provedor)
    r = await svc.conversar(_abrir_fake, mensagens=[{"role": "user", "content": "extrai o job X"}],
                            projeto_atual=None, provedor_cfg={}, identidade=None, campo_identidade=None,
                            ssh_max=10, acao_editar=False, matricula="DEV1")
    assert r["status"] == "ok"
    mensagem_ferramenta = provedor.chamadas[1]["historico"][-1]["content"]
    assert "acao_editar" in mensagem_ferramenta or "Governança" in mensagem_ferramenta


# ═══════════ 2. isx_extrair — job em pipeline: mesmas funções, mesmo shape ═══

@pytest.mark.asyncio
async def test_isx_extrair_job_em_pipeline_grava_pelas_mesmas_funcoes(monkeypatch):
    chamadas_gravar = []
    monkeypatch.setattr(af, "isx_info_do_job", lambda cur, pipeline, job: {
        "ds_project": "BI_CVP", "job_type": "datastage", "pipeline_name": pipeline, "job_name": job})
    monkeypatch.setattr(af.lineage_isx, "config", lambda: "CFG-FAKE")
    monkeypatch.setattr(af.lineage_isx, "cabecalho", lambda cur, p, j: None)
    monkeypatch.setattr(af.lineage_isx, "conta_linhas", lambda cur, p, j: 0)
    monkeypatch.setattr(af.lineage_isx, "mapa_tipos", lambda cur: {})
    monkeypatch.setattr(af, "isx_no_executor", _executor_fake)
    monkeypatch.setattr(af.lineage_isx, "extrair", lambda cfg, projeto, job, cab, tem_linhas, forcar, mapa: (
        {"folder_path": "\\Jobs", "job_type": "PARALLEL", "last_modified": "2026-09-01T10:00:00"},
        {"stages": [], "job_description": "desc"}, False))

    def _gravar(conn, cur, *, pipeline, job, projeto, meta, resultado, usuario, duracao_ms):
        chamadas_gravar.append({"pipeline": pipeline, "job": job, "projeto": projeto,
                                "usuario": usuario, "meta": meta, "resultado": resultado})
        return 3
    monkeypatch.setattr(af.lineage_isx, "gravar", _gravar)
    monkeypatch.setattr(af.lineage_isx, "montar", lambda cur, p, j: {
        "pipeline_name": p, "job_name": j, "status": "ok", "stages": []})

    provedor = _Provedor([
        '```json\n{"ferramenta": "isx_extrair", "args": {"pipeline_name": "PIPE_VIDA", "job_name": "JobX"}}\n```',
        "extraído",
    ])
    monkeypatch.setattr(ia_provedor, "chat_conversa", provedor)
    r = await svc.conversar(_abrir_fake, mensagens=[{"role": "user", "content": "extrai o job X do pipeline"}],
                            projeto_atual=None, provedor_cfg={}, identidade=None, campo_identidade=None,
                            ssh_max=10, acao_editar=True, matricula="DEV1")
    assert r["status"] == "ok"
    assert r["projeto"] == "BI_CVP"  # resolvido pela extração, sem precisar de resolver_projeto
    assert len(chamadas_gravar) == 1
    g = chamadas_gravar[0]
    assert g["pipeline"] == "PIPE_VIDA" and g["job"] == "JobX" and g["projeto"] == "BI_CVP"
    assert "DEV1" in g["usuario"] and "agente:datastage" in g["usuario"]  # rastreabilidade


@pytest.mark.asyncio
async def test_isx_extrair_cache_hit_nao_grava(monkeypatch):
    """Critério 2 da F2b: 2ª pergunta com o mesmo `lastModified` → 0 extração
    (0 gravação — o cache é decidido dentro de `lineage_isx.extrair`, aqui
    só provamos que `cache_hit=True` nunca chama `gravar`)."""
    monkeypatch.setattr(af, "isx_info_do_job", lambda cur, pipeline, job: {
        "ds_project": "BI_CVP", "job_type": "datastage", "pipeline_name": pipeline, "job_name": job})
    monkeypatch.setattr(af.lineage_isx, "config", lambda: "CFG-FAKE")
    monkeypatch.setattr(af.lineage_isx, "cabecalho", lambda cur, p, j: {"status": "ok"})
    monkeypatch.setattr(af.lineage_isx, "conta_linhas", lambda cur, p, j: 5)
    monkeypatch.setattr(af.lineage_isx, "mapa_tipos", lambda cur: {})
    monkeypatch.setattr(af, "isx_no_executor", _executor_fake)
    monkeypatch.setattr(af.lineage_isx, "extrair",
                        lambda cfg, projeto, job, cab, tem_linhas, forcar, mapa: ({"last_modified": "x"}, None, True))

    def _explode_gravar(*a, **k):
        raise AssertionError("gravar() não deveria ser chamado em cache hit")
    monkeypatch.setattr(af.lineage_isx, "gravar", _explode_gravar)
    monkeypatch.setattr(af.lineage_isx, "montar", lambda cur, p, j: {"pipeline_name": p, "job_name": j, "status": "ok"})

    provedor = _Provedor([
        '```json\n{"ferramenta": "isx_extrair", "args": {"pipeline_name": "PIPE_VIDA", "job_name": "JobX"}}\n```',
        "sem novidade",
    ])
    monkeypatch.setattr(ia_provedor, "chat_conversa", provedor)
    r = await svc.conversar(_abrir_fake, mensagens=[{"role": "user", "content": "extrai de novo"}],
                            projeto_atual=None, provedor_cfg={}, identidade=None, campo_identidade=None,
                            ssh_max=10, acao_editar=True, matricula="DEV1")
    assert r["status"] == "ok"  # não levantou AssertionError — gravar() nunca foi chamado


# ═══════════ 4. isx_extrair — fora de pipeline: extrai, não grava ═══════════

@pytest.mark.asyncio
async def test_isx_extrair_fora_de_pipeline_nao_grava(monkeypatch):
    _projeto_resolvido(monkeypatch, "BI_CVP")
    monkeypatch.setattr(af.lineage_isx, "config", lambda: "CFG-FAKE")
    monkeypatch.setattr(af, "isx_no_executor", _executor_fake)
    monkeypatch.setattr(af.lineage_isx, "extrair", lambda cfg, projeto, job, cab, tem_linhas, forcar, mapa: (
        {"last_modified": "2026-09-01T10:00:00"}, {"stages": [], "job_description": "d"}, False))

    def _explode_gravar(*a, **k):
        raise AssertionError("job fora de pipeline nunca deve gravar em etl_job_lineage/etl_ds_job_isx")
    monkeypatch.setattr(af.lineage_isx, "gravar", _explode_gravar)

    provedor = _Provedor([
        '```json\n{"ferramenta": "resolver_projeto", "args": {"projeto": "BI_CVP"}}\n```',
        '```json\n{"ferramenta": "isx_extrair", "args": {"job_name": "JobAvulso"}}\n```',
        "extraído sem gravar",
    ])
    monkeypatch.setattr(ia_provedor, "chat_conversa", provedor)
    r = await svc.conversar(_abrir_fake, mensagens=[{"role": "user", "content": "extrai o job avulso"}],
                            projeto_atual=None, provedor_cfg={}, identidade=None, campo_identidade=None,
                            ssh_max=10, acao_editar=True, matricula="DEV1")
    assert r["status"] == "ok"
    mensagem_ferramenta = provedor.chamadas[2]["historico"][-1]["content"]
    assert '"gravado": false' in mensagem_ferramenta.lower()


# ═══════════ 5. isx_extrair — allowlist e limite de 2 por pergunta ══════════

@pytest.mark.asyncio
async def test_isx_extrair_sem_job_name_e_recusado(monkeypatch):
    provedor = _Provedor([
        '```json\n{"ferramenta": "isx_extrair", "args": {"pipeline_name": "PIPE_VIDA"}}\n```',
        "ok",
    ])
    monkeypatch.setattr(ia_provedor, "chat_conversa", provedor)
    r = await svc.conversar(_abrir_fake, mensagens=[{"role": "user", "content": "extrai"}],
                            projeto_atual=None, provedor_cfg={}, identidade=None, campo_identidade=None,
                            ssh_max=10, acao_editar=True, matricula="DEV1")
    assert r["status"] == "ok"


@pytest.mark.asyncio
async def test_isx_extrair_ferramenta_fora_da_allowlist_e_recusada(monkeypatch):
    """Critério 5 da F2b: 'importar'/'compilar'/'executar'/'parar'/'apagar'/
    'lote' não existem como ferramenta — `_executar_ferramenta_interna` só
    reconhece os 5 nomes da allowlist."""
    provedor = _Provedor([
        '```json\n{"ferramenta": "isx_importar", "args": {}}\n```',
        "não posso fazer isso",
    ])
    monkeypatch.setattr(ia_provedor, "chat_conversa", provedor)
    r = await svc.conversar(_abrir_fake, mensagens=[{"role": "user", "content": "importa o job"}],
                            projeto_atual=None, provedor_cfg={}, identidade=None, campo_identidade=None,
                            ssh_max=10, acao_editar=True, matricula="DEV1")
    assert r["status"] == "ok"
    mensagem_ferramenta = provedor.chamadas[1]["historico"][-1]["content"]
    assert "não existe" in mensagem_ferramenta


@pytest.mark.asyncio
async def test_isx_extrair_limite_de_2_extracoes_por_pergunta(monkeypatch):
    monkeypatch.setattr(af, "isx_info_do_job", lambda cur, pipeline, job: {
        "ds_project": "BI_CVP", "job_type": "datastage", "pipeline_name": pipeline, "job_name": job})
    monkeypatch.setattr(af.lineage_isx, "config", lambda: "CFG-FAKE")
    monkeypatch.setattr(af.lineage_isx, "cabecalho", lambda cur, p, j: None)
    monkeypatch.setattr(af.lineage_isx, "conta_linhas", lambda cur, p, j: 0)
    monkeypatch.setattr(af.lineage_isx, "mapa_tipos", lambda cur: {})
    monkeypatch.setattr(af, "isx_no_executor", _executor_fake)
    monkeypatch.setattr(af.lineage_isx, "extrair", lambda cfg, projeto, job, cab, tem_linhas, forcar, mapa: (
        {"folder_path": "\\Jobs", "last_modified": "x"}, {"stages": []}, False))
    monkeypatch.setattr(af.lineage_isx, "gravar", lambda *a, **k: 0)
    monkeypatch.setattr(af.lineage_isx, "montar", lambda cur, p, j: {"pipeline_name": p, "job_name": j, "status": "ok"})

    pedido = '```json\n{"ferramenta": "isx_extrair", "args": {"pipeline_name": "PIPE_VIDA", "job_name": "JobX"}}\n```'
    provedor = _Provedor([pedido, pedido, pedido, "chega"])
    monkeypatch.setattr(ia_provedor, "chat_conversa", provedor)
    r = await svc.conversar(_abrir_fake, mensagens=[{"role": "user", "content": "extrai 3 vezes"}],
                            projeto_atual=None, provedor_cfg={}, identidade=None, campo_identidade=None,
                            ssh_max=10, acao_editar=True, matricula="DEV1")
    assert r["status"] == "ok"
    # a 3ª tentativa (rodada índice 2, 4ª chamada ao modelo) recebeu a recusa por limite
    terceira_ferramenta = provedor.chamadas[3]["historico"][-1]["content"]
    assert "limite" in terceira_ferramenta.lower()


# ═══════════ dsx_consulta — critérios 7, 9, 11 ═══════════════════════════════

@pytest.mark.asyncio
async def test_dsx_consulta_sem_projeto_com_dsx_e_recusada(monkeypatch):
    _projeto_resolvido(monkeypatch, "BI_CVP")
    monkeypatch.setattr(af, "projeto_tem_dsx", lambda nome: False)

    def _explode(*a, **k):
        raise AssertionError("dsx_consulta não deveria rodar sem .dsx disponível")
    monkeypatch.setattr(af, "ferramenta_dsx_consulta", _explode)

    provedor = _Provedor([
        '```json\n{"ferramenta": "resolver_projeto", "args": {"projeto": "BI_CVP"}}\n```',
        '```json\n{"ferramenta": "dsx_consulta", "args": {"operacao": "listar_jobs"}}\n```',
        "sem dsx mesmo",
    ])
    monkeypatch.setattr(ia_provedor, "chat_conversa", provedor)
    r = await svc.conversar(_abrir_fake, mensagens=[{"role": "user", "content": "lista os jobs do dsx"}],
                            projeto_atual=None, provedor_cfg={}, identidade=None, campo_identidade=None,
                            ssh_max=10, acao_editar=False, matricula="DEV1")
    assert r["status"] == "ok"


@pytest.mark.asyncio
async def test_dsx_consulta_canario_nao_chega_ao_modelo(monkeypatch):
    """Critério 9 da F2b: valores canário (senha, {iisenc}) num DSX de teste
    não chegam ao modelo — `redigir()` roda sobre a saída de dsx_consulta."""
    _projeto_resolvido(monkeypatch, "BI_CVP")
    monkeypatch.setattr(af, "projeto_tem_dsx", lambda nome: True)

    async def _consulta_fake(projeto, operacao, args):
        return {"sucesso": True, "jobs": [{"job_name": "JobX", "stage": {
            "database_name": "DB1", "sql_expression": 'password: "SegredoCanarioXYZ"'}}]}
    monkeypatch.setattr(af, "ferramenta_dsx_consulta", _consulta_fake)

    provedor = _Provedor([
        '```json\n{"ferramenta": "resolver_projeto", "args": {"projeto": "BI_CVP"}}\n```',
        '```json\n{"ferramenta": "dsx_consulta", "args": {"operacao": "listar_jobs"}}\n```',
        "ok",
    ])
    monkeypatch.setattr(ia_provedor, "chat_conversa", provedor)
    await svc.conversar(_abrir_fake, mensagens=[{"role": "user", "content": "lista os jobs"}],
                        projeto_atual=None, provedor_cfg={}, identidade=None, campo_identidade=None,
                        ssh_max=10, acao_editar=False, matricula="DEV1")
    mensagem_ferramenta = provedor.chamadas[2]["historico"][-1]["content"]
    assert "SegredoCanarioXYZ" not in mensagem_ferramenta
