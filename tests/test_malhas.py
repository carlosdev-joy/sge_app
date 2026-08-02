"""
Testes da entidade Malha — F7 da spec de dependências (api/routers/malhas.py).

Padrão de test_finalizacao.py: TestClient do conftest, get_db_conn mockado em
routers.malhas e autenticação sobrescrita via dependency_overrides — nenhum
teste toca rede ou banco.

O dublê aqui é ESTATAL (FakeDb): etl_malha/etl_malha_pipeline em dicts com a
semântica case-insensitive da colação do SQL Server. Assim os fluxos compostos
(criar → renomear → detalhar) exercitam o SQL real do router de ponta a ponta,
em vez de listas de fetchone decoradas por teste.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

# Replica o mock de pyodbc do conftest (garante o import de api.main mesmo se
# este arquivo for coletado antes do conftest configurar o ambiente).
if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from deps import PERM_EDITAR, get_current_user


# ── dublê estatal do banco ───────────────────────────────────────────────────

_AGORA = datetime(2026, 8, 2, 10, 0, 0)


class FakeDb:
    """etl_malha + etl_malha_pipeline em memória, com chaves case-insensitive
    (a colação do SQL Server é CI — 'Fechamento' e 'FECHAMENTO' colidem)."""

    def __init__(self, pipelines=None, com_tabelas=True):
        # pipelines: {grafia_oficial: {"active": 1, "criticidade": "Alta",
        #                              "schedule_type": "daily"}}
        self.pipelines = pipelines or {}
        self.com_tabelas = com_tabelas
        self.malhas: dict[str, dict] = {}   # grafia_oficial -> linha
        self.membros: list[dict] = []       # {"malha", "pipeline", "layout_x", "layout_y"}
        self.commits = 0

    # chave CI
    def _malha_key(self, nome):
        for k in self.malhas:
            if k.casefold() == (nome or "").casefold():
                return k
        return None

    def _pipeline_key(self, nome):
        for k in self.pipelines:
            if k.casefold() == (nome or "").casefold():
                return k
        return None

    def cursor(self):
        return FakeCur(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


class FakeCur:
    def __init__(self, db: FakeDb):
        self.db = db
        self._rows: list[tuple] = []
        self.rowcount = -1
        self.description = []

    def close(self):
        pass

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def execute(self, sql, params=()):  # noqa: C901 — dispatcher de dublê
        db = self.db
        s = " ".join(str(sql).split())
        self._rows = []
        self.rowcount = -1

        if "OBJECT_ID('dbo.etl_malha'" in s:
            self._rows = [(1, 1)] if db.com_tabelas else [(None, None)]
            return
        # A checagem única do router precisa impedir QUALQUER toque nas
        # tabelas quando elas não existem — chegar aqui é bug de degradação.
        if not db.com_tabelas and "etl_malha" in s:
            raise RuntimeError("Invalid object name 'dbo.etl_malha'")

        # ── SELECTs em etl_malha ────────────────────────────────────────────
        if s.startswith("SELECT malha_name FROM dbo.etl_malha WHERE"):
            k = db._malha_key(params[0])
            self._rows = [(k,)] if k else []
            return
        if s.startswith("SELECT malha_name, descricao"):
            def linha(k):
                m = db.malhas[k]
                return (k, m["descricao"], m["ativo"], m["criado_em"],
                        m["criado_por"], m["atualizado_em"])
            if "WHERE malha_name = ?" in s:
                k = db._malha_key(params[0])
                self._rows = [linha(k)] if k else []
            else:  # listagem ORDER BY malha_name
                self._rows = [linha(k) for k in sorted(db.malhas)]
            return

        # ── membros (JOIN com etl_pipeline) ─────────────────────────────────
        if "FROM dbo.etl_malha_pipeline mp JOIN dbo.etl_pipeline p" in s:
            if "WHERE mp.malha_name = ?" in s:   # detalhe
                k = db._malha_key(params[0])
                out = []
                for m in db.membros:
                    if k and m["malha"].casefold() == k.casefold():
                        pk = db._pipeline_key(m["pipeline"])
                        if pk is None:
                            continue  # pipeline excluído: o JOIN o faz sumir
                        p = db.pipelines[pk]
                        out.append((pk, p.get("active", 1),
                                    p.get("criticidade") or "Media",
                                    p.get("schedule_type"),
                                    m["layout_x"], m["layout_y"]))
                self._rows = sorted(out)
            else:                                 # agregados da listagem
                out = []
                for m in db.membros:
                    pk = db._pipeline_key(m["pipeline"])
                    if pk is None:
                        continue
                    p = db.pipelines[pk]
                    out.append((db._malha_key(m["malha"]), p.get("active", 1),
                                p.get("criticidade") or "Media"))
                self._rows = out
            return

        # ── SELECTs auxiliares ──────────────────────────────────────────────
        if s.startswith("SELECT pipeline_name FROM dbo.etl_pipeline WHERE"):
            k = db._pipeline_key(params[0])
            self._rows = [(k,)] if k else []
            return
        if s.startswith("SELECT 1 FROM dbo.etl_malha_pipeline"):
            self._rows = [(1,)] if any(
                m["malha"].casefold() == params[0].casefold()
                and m["pipeline"].casefold() == params[1].casefold()
                for m in db.membros) else []
            return

        # ── escrita em etl_malha ────────────────────────────────────────────
        if s.startswith("INSERT INTO dbo.etl_malha (") and " SELECT ?" in s:
            novo, atual = params
            k = db._malha_key(atual)
            if db._malha_key(novo):
                raise RuntimeError("Violation of PRIMARY KEY constraint 'PK_etl_malha'")
            velho = db.malhas[k]
            db.malhas[novo] = {**velho, "atualizado_em": _AGORA}
            return
        if s.startswith("INSERT INTO dbo.etl_malha ("):
            nome, descricao, criado_por = params
            if db._malha_key(nome):
                raise RuntimeError("Violation of PRIMARY KEY constraint 'PK_etl_malha'")
            db.malhas[nome] = {"descricao": descricao, "ativo": 1,
                               "criado_em": _AGORA, "criado_por": criado_por,
                               "atualizado_em": None}
            return
        if s.startswith("UPDATE dbo.etl_malha SET malha_name"):
            novo, atual = params
            k = db._malha_key(atual)
            db.malhas[novo] = {**db.malhas.pop(k), "atualizado_em": _AGORA}
            return
        if s.startswith("UPDATE dbo.etl_malha SET descricao"):
            k = db._malha_key(params[1])
            db.malhas[k].update(descricao=params[0], atualizado_em=_AGORA)
            return
        if s.startswith("UPDATE dbo.etl_malha SET ativo"):
            k = db._malha_key(params[1])
            db.malhas[k].update(ativo=params[0], atualizado_em=_AGORA)
            return
        if s.startswith("DELETE FROM dbo.etl_malha WHERE"):
            k = db._malha_key(params[0])
            if k:
                db.malhas.pop(k)
                db.membros = [m for m in db.membros            # ON DELETE CASCADE
                              if m["malha"].casefold() != k.casefold()]
            return

        # ── escrita em etl_malha_pipeline ───────────────────────────────────
        if s.startswith("INSERT INTO dbo.etl_malha_pipeline"):
            db.membros.append({"malha": params[0], "pipeline": params[1],
                               "layout_x": None, "layout_y": None})
            return
        if s.startswith("UPDATE dbo.etl_malha_pipeline SET malha_name"):
            novo, atual = params
            for m in db.membros:
                if m["malha"].casefold() == atual.casefold():
                    m["malha"] = novo
            return
        if s.startswith("DELETE FROM dbo.etl_malha_pipeline"):
            antes = len(db.membros)
            db.membros = [m for m in db.membros
                          if not (m["malha"].casefold() == params[0].casefold()
                                  and m["pipeline"].casefold() == params[1].casefold())]
            self.rowcount = antes - len(db.membros)
            return

        raise AssertionError(f"SQL não previsto pelo dublê: {s[:120]}")


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_editor(app):
    """Usuário com acao_editar (quem constrói malhas)."""
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor",
        "permissoes": [PERM_EDITAR, "tela_malha"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_consulta(app):
    """Usuário autenticado SEM acao_editar (só leitura)."""
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "USER1", "perfil": "consulta", "permissoes": ["tela_malha"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _patch_db(db):
    return patch("routers.malhas.get_db_conn", return_value=db)


_PIPES = {
    "PIPE_VENDAS":  {"active": 1, "criticidade": "Alta",    "schedule_type": "daily"},
    "PIPE_ESTOQUE": {"active": 0, "criticidade": "Baixa",   "schedule_type": "on_demand"},
    "PIPE_FISCAL":  {"active": 1, "criticidade": "Critica", "schedule_type": "daily"},
    "PIPE_SEM_CRIT": {"active": 1, "criticidade": None,     "schedule_type": "weekly"},
}


# ── registro do router e auth ────────────────────────────────────────────────

def test_router_malhas_registrado(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json().get("paths", {})
    for p in ("/malhas", "/malhas/{malha_name}",
              "/malhas/{malha_name}/pipelines",
              "/malhas/{malha_name}/pipelines/{pipeline_name}"):
        assert p in paths, f"rota {p} não registrada em api/main.py"


def test_sem_auth_401(client):
    assert client.get("/malhas").status_code == 401
    assert client.post("/malhas", json={"malha_name": "X"}).status_code == 401


def test_escrita_exige_acao_editar_403(client, auth_consulta):
    """Perfil de consulta vê a lista, mas não cria/edita malha."""
    db = FakeDb()
    with _patch_db(db):
        assert client.get("/malhas").status_code == 200
        assert client.post("/malhas", json={"malha_name": "X"}).status_code == 403
        assert client.patch("/malhas/X", json={"ativo": 0}).status_code == 403
    assert db.malhas == {}


# ── criação ──────────────────────────────────────────────────────────────────

def test_criar_malha_grava_criado_por(client, auth_editor):
    db = FakeDb()
    with _patch_db(db):
        r = client.post("/malhas", json={"malha_name": "Fechamento Diario",
                                         "descricao": "  ondas do fechamento  "})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "malha_name": "Fechamento Diario"}
    assert db.malhas["Fechamento Diario"]["criado_por"] == "DEV1"
    assert db.malhas["Fechamento Diario"]["descricao"] == "ondas do fechamento"
    assert db.commits == 1


def test_criar_nome_vazio_422(client, auth_editor):
    db = FakeDb()
    with _patch_db(db):
        r = client.post("/malhas", json={"malha_name": "   "})
    assert r.status_code == 422
    assert "malha_name" in r.json()["detail"]


def test_criar_duplicada_case_insensitive_422(client, auth_editor):
    """A colação do banco é CI: 'FECHAMENTO' duplicaria 'Fechamento' — o 422
    precisa vir da pré-validação, com a grafia registrada, não do PK."""
    db = FakeDb()
    with _patch_db(db):
        assert client.post("/malhas", json={"malha_name": "Fechamento"}).status_code == 200
        r = client.post("/malhas", json={"malha_name": "FECHAMENTO"})
    assert r.status_code == 422
    assert "'Fechamento'" in r.json()["detail"]
    assert list(db.malhas) == ["Fechamento"]


# ── membros ──────────────────────────────────────────────────────────────────

def test_membro_pipeline_inexistente_422(client, auth_editor):
    """422 com o NOME antes de a FK estourar — o erro útil diz qual foi o typo."""
    db = FakeDb(pipelines=_PIPES)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        r = client.post("/malhas/M1/pipelines", json={"pipeline_name": "PIPE_FANTASMA"})
    assert r.status_code == 422
    assert "PIPE_FANTASMA" in r.json()["detail"]
    assert db.membros == []


def test_membro_grafia_divergente_e_canonizado(client, auth_editor):
    """Mesma regra da PR #236: grava-se a grafia REGISTRADA em etl_pipeline,
    nunca a digitada — dicts Python são case-sensitive e o membro 'sumiria'."""
    db = FakeDb(pipelines=_PIPES)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        r = client.post("/malhas/m1/pipelines", json={"pipeline_name": "pipe_vendas"})
    assert r.status_code == 200
    assert r.json()["pipeline_name"] == "PIPE_VENDAS"
    assert db.membros == [{"malha": "M1", "pipeline": "PIPE_VENDAS",
                           "layout_x": None, "layout_y": None}]


def test_adicionar_membro_e_idempotente(client, auth_editor):
    db = FakeDb(pipelines=_PIPES)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        r1 = client.post("/malhas/M1/pipelines", json={"pipeline_name": "PIPE_VENDAS"})
        r2 = client.post("/malhas/M1/pipelines", json={"pipeline_name": "Pipe_Vendas"})
    assert r1.status_code == 200 and r1.json()["ja_membro"] is False
    assert r2.status_code == 200 and r2.json()["ja_membro"] is True
    assert len(db.membros) == 1


def test_adicionar_membro_em_malha_inexistente_404(client, auth_editor):
    db = FakeDb(pipelines=_PIPES)
    with _patch_db(db):
        r = client.post("/malhas/NAO_EXISTE/pipelines",
                        json={"pipeline_name": "PIPE_VENDAS"})
    assert r.status_code == 404


def test_remover_membro_e_404_de_nao_membro(client, auth_editor):
    db = FakeDb(pipelines=_PIPES)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        client.post("/malhas/M1/pipelines", json={"pipeline_name": "PIPE_VENDAS"})
        ok = client.delete("/malhas/M1/pipelines/pipe_vendas")
        de_novo = client.delete("/malhas/M1/pipelines/PIPE_VENDAS")
    assert ok.status_code == 200
    assert db.membros == []
    assert de_novo.status_code == 404
    assert "não é membro" in de_novo.json()["detail"]


# ── rename ───────────────────────────────────────────────────────────────────

def test_rename_atualiza_a_tabela_filha(client, auth_editor):
    """A FK da 070 é cascade de DELETE, não de UPDATE: renomear tem de migrar
    os membros na MESMA transação — senão a malha nova nasce vazia."""
    db = FakeDb(pipelines=_PIPES)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        client.post("/malhas/M1/pipelines", json={"pipeline_name": "PIPE_VENDAS"})
        client.post("/malhas/M1/pipelines", json={"pipeline_name": "PIPE_FISCAL"})
        r = client.patch("/malhas/M1", json={"novo_nome": "MALHA_FECHAMENTO"})
        detalhe = client.get("/malhas/MALHA_FECHAMENTO")
        antiga = client.get("/malhas/M1")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "malha_name": "MALHA_FECHAMENTO", "renomeada": True}
    assert detalhe.status_code == 200
    assert [m["pipeline_name"] for m in detalhe.json()["membros"]] == \
        ["PIPE_FISCAL", "PIPE_VENDAS"]
    assert antiga.status_code == 404
    # criado_em/criado_por sobrevivem ao rename (a linha é migrada, não recriada)
    assert db.malhas["MALHA_FECHAMENTO"]["criado_por"] == "DEV1"


def test_rename_para_nome_de_outra_malha_422(client, auth_editor):
    db = FakeDb()
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        client.post("/malhas", json={"malha_name": "M2"})
        r = client.patch("/malhas/M1", json={"novo_nome": "m2"})
    assert r.status_code == 422
    assert "'M2'" in r.json()["detail"]
    assert set(db.malhas) == {"M1", "M2"}


def test_rename_so_de_caixa_nao_estoura_o_pk(client, auth_editor):
    """'m1' → 'M1' é o MESMO valor para a colação CI: o caminho
    insert/migra/apaga colidiria no PK; aqui tem de ser UPDATE direto."""
    db = FakeDb(pipelines=_PIPES)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "malha_diaria"})
        client.post("/malhas/malha_diaria/pipelines",
                    json={"pipeline_name": "PIPE_VENDAS"})
        r = client.patch("/malhas/malha_diaria", json={"novo_nome": "MALHA_DIARIA"})
    assert r.status_code == 200
    assert list(db.malhas) == ["MALHA_DIARIA"]
    assert db.membros[0]["malha"] == "MALHA_DIARIA"


def test_patch_malha_inexistente_404(client, auth_editor):
    db = FakeDb()
    with _patch_db(db):
        r = client.patch("/malhas/NAO_EXISTE", json={"descricao": "x"})
    assert r.status_code == 404


def test_patch_descricao_e_ativo(client, auth_editor):
    db = FakeDb()
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1", "descricao": "antiga"})
        r = client.patch("/malhas/M1", json={"descricao": "nova", "ativo": 0})
    assert r.status_code == 200
    assert db.malhas["M1"]["descricao"] == "nova"
    assert db.malhas["M1"]["ativo"] == 0


# ── listagem e agregados ─────────────────────────────────────────────────────

def test_lista_agrega_qtds_e_criticidade_mais_alta(client, auth_editor):
    """Critica > Alta > Media > Baixa; qtd_ativos conta só active=1; malha sem
    membros não inventa criticidade."""
    db = FakeDb(pipelines=_PIPES)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "CHEIA"})
        for p in ("PIPE_VENDAS", "PIPE_ESTOQUE", "PIPE_FISCAL"):
            client.post("/malhas/CHEIA/pipelines", json={"pipeline_name": p})
        client.post("/malhas", json={"malha_name": "VAZIA"})
        r = client.get("/malhas")
    assert r.status_code == 200
    cheia, vazia = r.json()["malhas"]        # ordenadas por nome
    assert cheia["malha_name"] == "CHEIA"
    assert cheia["qtd_pipelines"] == 3
    assert cheia["qtd_ativos"] == 2
    assert cheia["criticidade"] == "Critica"
    assert vazia == {**vazia, "malha_name": "VAZIA", "qtd_pipelines": 0,
                     "qtd_ativos": 0, "criticidade": None}


def test_criticidade_nula_conta_como_media(client, auth_editor):
    """ISNULL(criticidade,'Media') do banco + fallback do agregador: pipeline
    sem criticidade não derruba nem rebaixa a conta."""
    db = FakeDb(pipelines=_PIPES)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        client.post("/malhas/M1/pipelines", json={"pipeline_name": "PIPE_SEM_CRIT"})
        client.post("/malhas/M1/pipelines", json={"pipeline_name": "PIPE_ESTOQUE"})
        r = client.get("/malhas")
    assert r.json()["malhas"][0]["criticidade"] == "Media"


def test_detalhe_traz_membros_com_layout(client, auth_editor):
    db = FakeDb(pipelines=_PIPES)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        client.post("/malhas/M1/pipelines", json={"pipeline_name": "PIPE_VENDAS"})
        r = client.get("/malhas/m1")     # grafia divergente resolve pela CI
    assert r.status_code == 200
    body = r.json()
    assert body["malha_name"] == "M1"
    assert body["qtd_pipelines"] == 1 and body["qtd_ativos"] == 1
    assert body["membros"] == [{
        "pipeline_name": "PIPE_VENDAS", "active": 1, "criticidade": "Alta",
        "schedule_type": "daily", "layout_x": None, "layout_y": None,
    }]


def test_detalhe_malha_inexistente_404(client, auth_editor):
    db = FakeDb()
    with _patch_db(db):
        r = client.get("/malhas/NAO_EXISTE")
    assert r.status_code == 404


# ── degradação sem a migration 070 ───────────────────────────────────────────

def test_sem_tabelas_lista_degrada_para_vazio(client, auth_editor):
    """Deploy parcial (API nova, migration 070 pendente): a tela lista vazio,
    sem stack trace — o dublê LEVANTA se qualquer query tocar as tabelas."""
    db = FakeDb(com_tabelas=False)
    with _patch_db(db):
        r = client.get("/malhas")
    assert r.status_code == 200
    assert r.json() == {"malhas": [], "migration_pendente": True}


def test_sem_tabelas_escrita_da_erro_claro(client, auth_editor):
    """Escrita sem as tabelas: 503 com instrução em pt-BR, nunca 500 cru."""
    db = FakeDb(com_tabelas=False)
    with _patch_db(db):
        r_post = client.post("/malhas", json={"malha_name": "M1"})
        r_membro = client.post("/malhas/M1/pipelines",
                               json={"pipeline_name": "PIPE_VENDAS"})
        r_patch = client.patch("/malhas/M1", json={"ativo": 0})
        r_del = client.delete("/malhas/M1/pipelines/PIPE_VENDAS")
        r_detalhe = client.get("/malhas/M1")
    for r in (r_post, r_membro, r_patch, r_del, r_detalhe):
        assert r.status_code == 503
        assert "migration 070" in r.json()["detail"]
    assert db.commits == 0


# ── nome com '/' fica inendereçável no path (achado da revisão adversarial) ──

def test_nome_com_barra_recusado_na_criacao(client, auth_editor):
    db = FakeDb()
    with _patch_db(db):
        r = client.post("/malhas", json={"malha_name": "Fechamento/Diario"})
    assert r.status_code == 422
    assert "/" in r.json()["detail"]
    assert list(db.malhas) == []


def test_nome_com_barra_recusado_no_rename(client, auth_editor):
    db = FakeDb()
    with _patch_db(db):
        assert client.post("/malhas", json={"malha_name": "MALHA_OK"}).status_code == 200
        r = client.patch("/malhas/MALHA_OK", json={"novo_nome": "a/b"})
    assert r.status_code == 422
    assert "/" in r.json()["detail"]
    assert list(db.malhas) == ["MALHA_OK"]
