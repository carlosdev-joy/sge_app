"""
Conferência do nome do job contra o DataStage no CADASTRO da etapa
(GET /datastage/jobs) — incidente 2026-08-01.

O nome errado (caixa divergente) só se manifestava quando o pipeline rodava em
produção. Aqui o Orquestra pergunta ao DataStage quais jobs existem no projeto
(`dsjob -ljobs`) para a tela conferir a grafia e sugerir a certa.

REGRA INEGOCIÁVEL testada aqui: **indisponibilidade do DataStage NÃO bloqueia o
cadastro**. Toda falha de conexão/config vira 200 com ``disponivel=false`` e um
motivo em texto — nunca 5xx, nunca erro. Só entrada inválida (projeto fora da
allowlist anti-injeção) é 422.

⚠️ O ambiente de dev NÃO tem servidor DataStage: o caminho feliz é provado com
DUBLÊ do ``run_dsjob``; o caminho de indisponibilidade é o que roda de verdade
no dev (e também está coberto aqui).
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from deps import PERM_EDITAR, get_current_user

# Saída real de `dsjob -ljobs`: um nome por linha + rodapé "Status code = 0".
LJOBS_OK = """SSDVidaCobranca01BaixaProcessamentoCobranca
SeqSsdVida7Peps
BiCvp_Extract_01
Status code = 0
"""


@pytest.fixture(autouse=True)
def limpa_cache():
    import routers.datastage as ds
    ds._LJOBS_CACHE.clear()
    yield
    ds._LJOBS_CACHE.clear()


@pytest.fixture
def auth_editar():
    _app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor", "permissoes": [PERM_EDITAR],
    }
    yield
    _app.dependency_overrides.pop(get_current_user, None)


# ─────────────────────────── parser puro (-ljobs) ───────────────────────────

def test_parse_ljobs_preserva_ordem_e_caixa():
    from services.ssh_datastage import parse_ljobs
    jobs = parse_ljobs(LJOBS_OK)
    assert jobs == ["SSDVidaCobranca01BaixaProcessamentoCobranca",
                    "SeqSsdVida7Peps", "BiCvp_Extract_01"]
    # A CAIXA é o dado que importa — nada de normalizar.
    assert jobs[0].startswith("SSD")


def test_parse_ljobs_descarta_rodape_vazio_e_lixo():
    from services.ssh_datastage import parse_ljobs
    saida = ("<none>\nStatus code = 0\n\n"
             "ERROR: Failed to open project (DSOpenProject)\nJobOk\nJobOk\n")
    # '<none>', rodapé, linha de erro (tem espaço/parênteses) e duplicata saem.
    assert parse_ljobs(saida) == ["JobOk"]
    assert parse_ljobs("") == []
    assert parse_ljobs(None) == []


# ───────────────────────── endpoint: caminho feliz ──────────────────────────

def test_lista_jobs_do_projeto(client, auth_editar):
    with patch("routers.datastage.ssh_configured", return_value=True), \
         patch("routers.datastage.run_dsjob",
               return_value={"exit_code": 0, "stdout": LJOBS_OK, "stderr": ""}):
        r = client.get("/datastage/jobs?project=BI_VIDA")
    assert r.status_code == 200
    body = r.json()
    assert body["disponivel"] is True
    assert body["total"] == 3
    assert "SSDVidaCobranca01BaixaProcessamentoCobranca" in body["jobs"]
    assert body["cached"] is False


def test_segunda_chamada_vem_do_cache(client, auth_editar):
    """A consulta é uma sessão SSH: sem cache, o autocompletar do cadastro
    abriria uma conexão por tecla digitada."""
    alvo = MagicMock(return_value={"exit_code": 0, "stdout": LJOBS_OK, "stderr": ""})
    with patch("routers.datastage.ssh_configured", return_value=True), \
         patch("routers.datastage.run_dsjob", alvo):
        r1 = client.get("/datastage/jobs?project=BI_VIDA")
        r2 = client.get("/datastage/jobs?project=BI_VIDA")
        r3 = client.get("/datastage/jobs?project=bi_vida")   # caixa não cria entrada nova
    assert r1.json()["cached"] is False
    assert r2.json()["cached"] is True
    assert r3.json()["cached"] is True
    assert alvo.call_count == 1

    with patch("routers.datastage.ssh_configured", return_value=True), \
         patch("routers.datastage.run_dsjob", alvo):
        r4 = client.get("/datastage/jobs?project=BI_VIDA&refresh=true")
    assert r4.json()["cached"] is False
    assert alvo.call_count == 2


# ──────────────── endpoint: degradação (NUNCA bloqueia o cadastro) ──────────

def test_ssh_nao_configurado_avisa_sem_erro(client, auth_editar):
    with patch("routers.datastage.ssh_configured", return_value=False):
        r = client.get("/datastage/jobs?project=BI_VIDA")
    assert r.status_code == 200
    body = r.json()
    assert body["disponivel"] is False
    assert body["jobs"] == []
    assert "não configurado" in body["motivo"]


def test_falha_de_conexao_avisa_sem_erro(client, auth_editar):
    with patch("routers.datastage.ssh_configured", return_value=True), \
         patch("routers.datastage.run_dsjob",
               side_effect=OSError("Connection timed out")):
        r = client.get("/datastage/jobs?project=BI_VIDA")
    assert r.status_code == 200
    body = r.json()
    assert body["disponivel"] is False
    assert "Connection timed out" in body["motivo"]


def test_dsjob_recusado_avisa_sem_erro(client, auth_editar):
    with patch("routers.datastage.ssh_configured", return_value=True), \
         patch("routers.datastage.run_dsjob",
               return_value={"exit_code": 255, "stdout": "",
                             "stderr": "ERROR: Failed to open project"}):
        r = client.get("/datastage/jobs?project=NAO_EXISTE")
    assert r.status_code == 200
    body = r.json()
    assert body["disponivel"] is False
    assert "Failed to open project" in body["motivo"]


def test_indisponibilidade_tem_cache_curto(client, auth_editar):
    """Servidor fora não pode ser martelado a cada tecla, mas também não pode
    ficar 5 min 'fora' depois de voltar — TTL curto (1/5)."""
    import routers.datastage as ds
    with patch("routers.datastage.ssh_configured", return_value=False):
        client.get("/datastage/jobs?project=BI_VIDA")
    expira, payload = ds._LJOBS_CACHE["BI_VIDA"]
    assert payload["disponivel"] is False
    import time as _t
    assert 0 < expira - _t.time() <= max(15, ds._LJOBS_TTL // 5) + 1


# ───────────────────────── endpoint: entrada inválida ───────────────────────

def test_projeto_invalido_e_422(client, auth_editar):
    # Allowlist anti-injeção (mesma do console): sem espaços nem símbolos.
    r = client.get("/datastage/jobs?project=BI VIDA; rm -rf /")
    assert r.status_code == 422
    r2 = client.get("/datastage/jobs?project=")
    assert r2.status_code == 422


def test_exige_permissao_de_edicao(client):
    _app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "LEITOR", "perfil": "consulta", "permissoes": [],
    }
    try:
        r = client.get("/datastage/jobs?project=BI_VIDA")
        assert r.status_code == 403
    finally:
        _app.dependency_overrides.pop(get_current_user, None)
