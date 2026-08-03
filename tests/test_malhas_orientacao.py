"""
Testes da orientação do diagrama de montagem da Malha (migration 074).

Cobrem o contrato novo em api/routers/malhas.py: PATCH /malhas/{name} aceita
`orientacao` ('horizontal' | 'vertical'; outro valor → 422 pt-BR); GET detalhe
e GET lista devolvem `orientacao` (aditivo — card e front antigos ignoram);
sem a coluna (deploy parcial da 074) a leitura degrada para 'horizontal' e o
PATCH responde migration_074_pendente=True em vez de 503 — o precedente do
arquivo para COLUNA opcional é o degrade suave (073/_ligar_dag_config_pendente);
o 503 fica para TABELAS ausentes (070/067).

Padrão ESTATAL de test_malhas.py: o FakeDb da F7 já carrega com_074 (default
False = banco sem a 074; os testes daqui ligam explicitamente) — os fluxos
compostos (criar → trocar orientação → renomear → detalhar) exercitam o SQL
real do router.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Replica o mock de pyodbc do conftest (garante o import de api.main mesmo se
# este arquivo for coletado antes do conftest configurar o ambiente).
if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from deps import PERM_EDITAR, get_current_user
from tests.test_malhas import _PIPES, FakeDb


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_editor(app):
    """Usuário com acao_editar (quem monta malhas)."""
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor",
        "permissoes": [PERM_EDITAR, "tela_malha"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _patch_db(db):
    return patch("routers.malhas.get_db_conn", return_value=db)


# ── PATCH orientacao (com a 074) ─────────────────────────────────────────────

def test_patch_orientacao_valida_grava_e_devolve(client, auth_editor):
    db = FakeDb(com_074=True)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        r = client.patch("/malhas/M1", json={"orientacao": "vertical"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "malha_name": "M1", "renomeada": False,
                        "orientacao": "vertical"}
    assert db.malhas["M1"]["orientacao"] == "vertical"


def test_get_detalhe_round_trip_da_orientacao(client, auth_editor):
    """Malha nova nasce 'horizontal' (DEFAULT da 074); o PATCH vira 'vertical'
    e o GET devolve o que foi gravado — é o round-trip que o MalhaEditor usa."""
    db = FakeDb(pipelines=_PIPES, com_074=True)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        antes = client.get("/malhas/M1").json()["orientacao"]
        client.patch("/malhas/M1", json={"orientacao": "vertical"})
        depois = client.get("/malhas/M1").json()["orientacao"]
        de_volta = client.patch("/malhas/M1", json={"orientacao": "horizontal"})
        final = client.get("/malhas/M1").json()["orientacao"]
    assert antes == "horizontal"
    assert depois == "vertical"
    assert de_volta.status_code == 200
    assert final == "horizontal"


def test_patch_orientacao_tolera_caixa_e_grava_canonico(client, auth_editor):
    """'Vertical' vale na entrada (mesmo espírito da colação CI), mas o
    gravado — e o devolvido — é o canônico minúsculo."""
    db = FakeDb(com_074=True)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        r = client.patch("/malhas/M1", json={"orientacao": "  Vertical "})
    assert r.status_code == 200
    assert r.json()["orientacao"] == "vertical"
    assert db.malhas["M1"]["orientacao"] == "vertical"


def test_patch_orientacao_invalida_422_sem_gravar(client, auth_editor):
    db = FakeDb(com_074=True)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        commits_antes = db.commits
        r_texto = client.patch("/malhas/M1", json={"orientacao": "diagonal"})
        r_vazia = client.patch("/malhas/M1", json={"orientacao": ""})
        r_numero = client.patch("/malhas/M1", json={"orientacao": 1})
    for r in (r_texto, r_vazia, r_numero):
        assert r.status_code == 422
        assert r.json()["detail"] == "orientacao deve ser 'horizontal' ou 'vertical'"
    assert db.malhas["M1"]["orientacao"] == "horizontal"
    assert db.commits == commits_antes


def test_patch_orientacao_invalida_aborta_o_rename_junto(client, auth_editor):
    """A validação vem ANTES de qualquer escrita: um body com rename + valor
    inválido não pode deixar o rename pela metade."""
    db = FakeDb(com_074=True)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        r = client.patch("/malhas/M1", json={"novo_nome": "M2",
                                             "orientacao": "diagonal"})
    assert r.status_code == 422
    assert list(db.malhas) == ["M1"]


def test_patch_combinado_com_descricao_e_ativo(client, auth_editor):
    db = FakeDb(com_074=True)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        r = client.patch("/malhas/M1", json={"descricao": "nova",
                                             "ativo": 0,
                                             "orientacao": "vertical"})
    assert r.status_code == 200
    assert r.json()["orientacao"] == "vertical"
    assert db.malhas["M1"]["descricao"] == "nova"
    assert db.malhas["M1"]["ativo"] == 0
    assert db.malhas["M1"]["orientacao"] == "vertical"


def test_patch_sem_orientacao_nao_ganha_as_chaves_novas(client, auth_editor):
    """Aditivo de verdade: quem não mexeu na orientação recebe a resposta de
    sempre, byte a byte (front antigo não vê chave nova)."""
    db = FakeDb(com_074=True)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        r = client.patch("/malhas/M1", json={"ativo": 0})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "malha_name": "M1", "renomeada": False}


def test_rename_preserva_a_orientacao(client, auth_editor):
    """O rename copia a linha-mãe por lista explícita de colunas — com a 074 a
    orientação tem de viajar junto, senão a malha renomeada cai no DEFAULT."""
    db = FakeDb(pipelines=_PIPES, com_074=True)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        client.patch("/malhas/M1", json={"orientacao": "vertical"})
        r = client.patch("/malhas/M1", json={"novo_nome": "M2"})
        detalhe = client.get("/malhas/M2")
    assert r.status_code == 200
    assert detalhe.json()["orientacao"] == "vertical"


# ── GET lista (aditivo) ──────────────────────────────────────────────────────

def test_lista_inclui_orientacao(client, auth_editor):
    db = FakeDb(com_074=True)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "HORIZ"})
        client.post("/malhas", json={"malha_name": "VERT"})
        client.patch("/malhas/VERT", json={"orientacao": "vertical"})
        r = client.get("/malhas")
    assert r.status_code == 200
    horiz, vert = r.json()["malhas"]         # ordenadas por nome
    assert horiz["malha_name"] == "HORIZ" and horiz["orientacao"] == "horizontal"
    assert vert["malha_name"] == "VERT" and vert["orientacao"] == "vertical"


def test_valor_estranho_no_banco_normaliza_para_horizontal(client, auth_editor):
    """A coluna não tem CHECK (padrão da casa): um valor fora do domínio,
    gravado por fora da API, vira 'horizontal' na leitura — nunca quebra a
    tela nem vaza jargão inesperado para o front."""
    db = FakeDb(com_074=True)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        db.malhas["M1"]["orientacao"] = "Diagonal"
        estranho = client.get("/malhas/M1").json()["orientacao"]
        db.malhas["M1"]["orientacao"] = "VERTICAL"   # caixa divergente vale
        caixa = client.get("/malhas/M1").json()["orientacao"]
    assert estranho == "horizontal"
    assert caixa == "vertical"


# ── degradação sem a coluna (deploy parcial da 074) ──────────────────────────

def test_sem_074_get_degrada_para_horizontal(client, auth_editor):
    """Sem a coluna, detalhe e lista devolvem 'horizontal' — o SQL executado é
    o de sempre (o dublê LEVANTA se algo tocar a coluna inexistente)."""
    db = FakeDb(pipelines=_PIPES, com_074=False)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        detalhe = client.get("/malhas/M1")
        lista = client.get("/malhas")
    assert detalhe.status_code == 200
    assert detalhe.json()["orientacao"] == "horizontal"
    assert lista.json()["malhas"][0]["orientacao"] == "horizontal"


def test_sem_074_patch_avisa_sem_503(client, auth_editor):
    """Escrita sem a coluna NÃO é 503 (precedente das colunas opcionais — 073):
    200 com migration_074_pendente=True e log; nada é gravado e o resto do
    PATCH (descricao etc.) segue funcionando."""
    db = FakeDb(com_074=False)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        r = client.patch("/malhas/M1", json={"orientacao": "vertical",
                                             "descricao": "segue valendo"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "malha_name": "M1", "renomeada": False,
                        "orientacao": "vertical", "migration_074_pendente": True}
    assert db.malhas["M1"]["orientacao"] == "horizontal"   # intocada
    assert db.malhas["M1"]["descricao"] == "segue valendo"


def test_sem_074_orientacao_invalida_ainda_e_422(client, auth_editor):
    """A validação do domínio não depende da coluna existir: valor inválido é
    422 mesmo no deploy parcial — o contrato do front é um só."""
    db = FakeDb(com_074=False)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        r = client.patch("/malhas/M1", json={"orientacao": "diagonal"})
    assert r.status_code == 422
    assert r.json()["detail"] == "orientacao deve ser 'horizontal' ou 'vertical'"
