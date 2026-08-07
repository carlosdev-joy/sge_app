"""
Testes da F8 — diagrama de montagem da Malha (api/routers/malhas.py).

Cobrem o contrato da F8: GET /malhas/{name} ganha "arestas"; POST/DELETE
/dependencias gravam a dependência REAL em etl_pipeline_dependencia (067) com
as validações da F1 (existência + ciclo BFS) e espelho CSV em
etl_pipeline.depends_on; PUT /malhas/{name}/layout persiste as posições.

Padrão ESTATAL de test_malhas.py: o FakeDb da F7 é ESTENDIDO (subclasse) com
etl_pipeline_dependencia e a coluna depends_on — os fluxos compostos
(dependência → arestas nas malhas → layout) exercitam o SQL real do router.
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
from tests.test_malhas import FakeCur as FakeCurF7, FakeDb as FakeDbF7


# ── dublê estatal estendido (F7 + tabela 067 + CSV depends_on) ───────────────

class FakeDb(FakeDbF7):
    """FakeDb da F7 + etl_pipeline_dependencia (067) e o CSV depends_on.

    com_067=False simula o deploy parcial SEM a migration 067 (a 070 pode
    existir): leitura degrada para "arestas": [] e escrita de dependência dá
    503 — qualquer query que toque a tabela nesse estado LEVANTA no dublê."""

    def __init__(self, pipelines=None, com_tabelas=True, com_067=True, com_073=False):
        # pipelines: {grafia_oficial: {..., "depends_on": "A,B" | None,
        #                              "dag_criada": 0|1, "dag_config_pendente": 0|1}}
        super().__init__(pipelines=pipelines, com_tabelas=com_tabelas)
        self.com_067 = com_067
        # F5: coluna dag_config_pendente (migration 073). Default False = o
        # banco de HOJE — os testes da flag ligam explicitamente.
        self.com_073 = com_073
        self.dependencias: list[dict] = []  # {"pipeline", "depende_de"} (tipo PIPELINE)

    def cursor(self):
        return FakeCur(self)


class FakeCur(FakeCurF7):
    def execute(self, sql, params=()):  # noqa: C901 — dispatcher de dublê
        db = self.db
        s = " ".join(str(sql).split())
        self._rows = []
        self.rowcount = -1

        # ── migration 067 ───────────────────────────────────────────────────
        if "OBJECT_ID('dbo.etl_pipeline_dependencia'" in s:
            self._rows = [(1,)] if db.com_067 else [(None,)]
            return
        if not db.com_067 and "etl_pipeline_dependencia" in s:
            raise RuntimeError("Invalid object name 'dbo.etl_pipeline_dependencia'")

        # ── etl_pipeline_dependencia ────────────────────────────────────────
        if s.startswith("SELECT pipeline_name, COUNT(*) FROM dbo.etl_pipeline_dependencia"):
            # F1 da spec-malha-data-unica: quantos predecessores cada membro
            # tem — o insumo do aviso "tem dependência mas ainda dispara por
            # agenda" no detalhe da malha.
            contagem: dict = {}
            for d in db.dependencias:
                contagem[d["pipeline"]] = contagem.get(d["pipeline"], 0) + 1
            self._rows = sorted(contagem.items())
            return
        if s.startswith("SELECT pipeline_name, depende_de FROM dbo.etl_pipeline_dependencia"):
            self._rows = sorted((d["pipeline"], d["depende_de"])
                                for d in db.dependencias)
            return
        if s.startswith("SELECT depende_de FROM dbo.etl_pipeline_dependencia"):
            # _dependencias_de da F1 (BFS do ciclo) — match CI como a colação
            self._rows = [(d["depende_de"],) for d in db.dependencias
                          if d["pipeline"].casefold() == (params[0] or "").casefold()]
            return
        if s.startswith("SELECT 1 FROM dbo.etl_pipeline_dependencia"):
            self._rows = [(1,)] if any(
                d["pipeline"].casefold() == (params[0] or "").casefold()
                and d["depende_de"].casefold() == (params[1] or "").casefold()
                for d in db.dependencias) else []
            return
        if s.startswith("INSERT INTO dbo.etl_pipeline_dependencia"):
            db.dependencias.append({"pipeline": params[0], "depende_de": params[1]})
            return
        if s.startswith("DELETE FROM dbo.etl_pipeline_dependencia"):
            antes = len(db.dependencias)
            db.dependencias = [
                d for d in db.dependencias
                if not (d["pipeline"].casefold() == (params[0] or "").casefold()
                        and d["depende_de"].casefold() == (params[1] or "").casefold())]
            self.rowcount = antes - len(db.dependencias)
            return

        # ── etl_pipeline: existência (_validar_existencia) e CSV espelho ────
        if s.startswith("SELECT 1 FROM dbo.etl_pipeline WHERE"):
            self._rows = [(1,)] if db._pipeline_key(params[0]) else []
            return
        if s.startswith("SELECT depends_on FROM dbo.etl_pipeline WHERE"):
            k = db._pipeline_key(params[0])
            self._rows = [(db.pipelines[k].get("depends_on"),)] if k else []
            return
        if s.startswith("UPDATE dbo.etl_pipeline SET depends_on"):
            k = db._pipeline_key(params[1])
            db.pipelines[k]["depends_on"] = params[0]
            self.rowcount = 1 if k else 0
            return

        # ── dag_config_pendente_em (migration 073 reescrita, F5) ────────────
        # Carimbo no banco real (achado 2 — TOCTOU); o dublê guarda o 0/1
        # equivalente em "dag_config_pendente" (o router só ESCREVE a coluna e
        # devolve o booleano — os testes leem este dict).
        if s.startswith("UPDATE dbo.etl_pipeline SET dag_config_pendente_em"):
            if not getattr(db, "com_073", False):
                raise RuntimeError("Invalid column name 'dag_config_pendente_em'")
            k = db._pipeline_key(params[0])
            n = 0
            if k is not None:
                if "dag_criada = 1" in s:
                    if int(db.pipelines[k].get("dag_criada") or 0) == 1:
                        db.pipelines[k]["dag_config_pendente"] = 1
                        n = 1
                else:
                    db.pipelines[k]["dag_config_pendente"] = 0
                    n = 1
            self.rowcount = n
            return

        # ── layout (etl_malha_pipeline) ─────────────────────────────────────
        if s.startswith("UPDATE dbo.etl_malha_pipeline SET layout_x"):
            x, y, malha, pipe = params
            n = 0
            for m in db.membros:
                if (m["malha"].casefold() == (malha or "").casefold()
                        and m["pipeline"].casefold() == (pipe or "").casefold()):
                    m["layout_x"], m["layout_y"] = x, y
                    n += 1
            self.rowcount = n
            return

        super().execute(sql, params)


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_editor(app):
    """Usuário com acao_editar (quem monta malhas e cadastra dependências)."""
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


def _pipes():
    return {
        "PIPE_A": {"active": 1, "criticidade": "Alta",  "schedule_type": "daily",
                   "depends_on": None},
        "PIPE_B": {"active": 1, "criticidade": "Media", "schedule_type": "daily",
                   "depends_on": None},
        "PIPE_C": {"active": 1, "criticidade": "Baixa", "schedule_type": "on_demand",
                   "depends_on": None},
    }


def _delete(client, json):
    # httpx não aceita json= em client.delete — o contrato da F8 manda body.
    return client.request("DELETE", "/dependencias", json=json)


# ── registro das rotas e auth ────────────────────────────────────────────────

def test_rotas_f8_registradas(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json().get("paths", {})
    for p in ("/dependencias", "/malhas/{malha_name}/layout"):
        assert p in paths, f"rota {p} não registrada em api/main.py"


def test_escrita_exige_acao_editar_403(client, auth_consulta):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        r_post = client.post("/dependencias",
                             json={"pipeline_name": "PIPE_A", "depende_de": "PIPE_B"})
        r_del = _delete(client, {"pipeline_name": "PIPE_A", "depende_de": "PIPE_B"})
        r_layout = client.put("/malhas/M1/layout", json={"posicoes": []})
    assert r_post.status_code == 403
    assert r_del.status_code == 403
    assert r_layout.status_code == 403
    assert db.dependencias == [] and db.commits == 0


# ── POST /dependencias ───────────────────────────────────────────────────────

def test_criar_dependencia_grava_tabela_e_espelho_csv(client, auth_editor):
    """Grafia divergente é canonizada pela registrada (PR #236) e o CSV
    depends_on do DEPENDENTE ganha o nome na MESMA transação."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        r = client.post("/dependencias",
                        json={"pipeline_name": "pipe_a", "depende_de": "pipe_b"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "ja_existia": False, "dag_config_pendente": False}
    assert db.dependencias == [{"pipeline": "PIPE_A", "depende_de": "PIPE_B"}]
    assert db.pipelines["PIPE_A"]["depends_on"] == "PIPE_B"
    assert db.pipelines["PIPE_B"]["depends_on"] is None   # espelho é só do dependente
    assert db.commits == 1


def test_espelho_csv_acrescenta_sem_duplicar_e_com_trim(client, auth_editor):
    """CSV legado com espaços e nome órfão: o espelho normaliza por trim, não
    duplica (comparação CI) e PRESERVA o que já estava lá."""
    pipes = _pipes()
    pipes["PIPE_A"]["depends_on"] = " PIPE_ORFAO ,  pipe_b "
    db = FakeDb(pipelines=pipes)
    with _patch_db(db):
        r1 = client.post("/dependencias",
                         json={"pipeline_name": "PIPE_A", "depende_de": "PIPE_B"})
        r2 = client.post("/dependencias",
                         json={"pipeline_name": "PIPE_A", "depende_de": "PIPE_C"})
    assert r1.status_code == 200 and r2.status_code == 200
    # PIPE_B já estava no CSV (caixa divergente): não duplica nem regrava
    assert db.pipelines["PIPE_A"]["depends_on"] == "PIPE_ORFAO,pipe_b,PIPE_C"


def test_criar_dependencia_ja_existente_e_idempotente(client, auth_editor):
    """Aresta re-salva devolve ja_existia=True sem regravar nada — é o aceite
    'salvar sem mudanças é no-op' visto do servidor (nem commit acontece)."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        r1 = client.post("/dependencias",
                         json={"pipeline_name": "PIPE_A", "depende_de": "PIPE_B"})
        r2 = client.post("/dependencias",
                         json={"pipeline_name": "pipe_a", "depende_de": "PIPE_B"})
    assert r1.json() == {"ok": True, "ja_existia": False, "dag_config_pendente": False}
    assert r2.status_code == 200
    assert r2.json() == {"ok": True, "ja_existia": True, "dag_config_pendente": False}
    assert len(db.dependencias) == 1
    assert db.pipelines["PIPE_A"]["depends_on"] == "PIPE_B"
    assert db.commits == 1                     # o re-salvar não commitou nada


def test_ciclo_direto_422_com_a_mensagem_do_servidor(client, auth_editor):
    """A→B gravada; B→O fecharia ciclo. O 422 traz a MENSAGEM EXATA do
    _check_circular da F1 — o MalhaEditor espelha este texto no cliente
    (aceite da F8: cliente e servidor com a mesma mensagem)."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        assert client.post("/dependencias",
                           json={"pipeline_name": "PIPE_A",
                                 "depende_de": "PIPE_B"}).status_code == 200
        r = client.post("/dependencias",
                        json={"pipeline_name": "PIPE_B", "depende_de": "PIPE_A"})
    assert r.status_code == 422
    assert r.json()["detail"] == (
        "Dependência circular: 'PIPE_B' → 'PIPE_A' fecha um ciclo "
        "(o caminho volta para 'PIPE_B')")
    assert db.dependencias == [{"pipeline": "PIPE_A", "depende_de": "PIPE_B"}]
    assert db.pipelines["PIPE_B"]["depends_on"] is None   # espelho intocado


def test_ciclo_transitivo_422(client, auth_editor):
    """A→B→C; C→O fecha o ciclo pela transitividade — o BFS da F1 olha o
    grafo INTEIRO, não só a primeira aresta."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        client.post("/dependencias", json={"pipeline_name": "PIPE_A", "depende_de": "PIPE_B"})
        client.post("/dependencias", json={"pipeline_name": "PIPE_B", "depende_de": "PIPE_C"})
        r = client.post("/dependencias",
                        json={"pipeline_name": "PIPE_C", "depende_de": "PIPE_A"})
    assert r.status_code == 422
    assert "Dependência circular" in r.json()["detail"]
    assert len(db.dependencias) == 2


def test_self_dependencia_422(client, auth_editor):
    """Mesmo texto do cadastro da F1; a canonização pega inclusive a caixa
    divergente ('pipe_a' depende de 'PIPE_A' é self)."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        r = client.post("/dependencias",
                        json={"pipeline_name": "pipe_a", "depende_de": "PIPE_A"})
    assert r.status_code == 422
    assert r.json()["detail"] == "Pipeline não pode depender de si mesmo"
    assert db.dependencias == []


def test_pipeline_inexistente_422(client, auth_editor):
    """422 com o nome digitado, nos dois lados — a mensagem do lado
    'depende de' é a MESMA do cadastro da F1."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        r_dep = client.post("/dependencias",
                            json={"pipeline_name": "PIPE_FANTASMA",
                                  "depende_de": "PIPE_A"})
        r_pred = client.post("/dependencias",
                             json={"pipeline_name": "PIPE_A",
                                   "depende_de": "PIPE_FANTASMA"})
    assert r_dep.status_code == 422
    assert r_dep.json()["detail"] == "Pipeline inexistente: 'PIPE_FANTASMA'"
    assert r_pred.status_code == 422
    assert r_pred.json()["detail"] == \
        "Pipeline inexistente em 'depende de': 'PIPE_FANTASMA'"
    assert db.dependencias == []


def test_body_incompleto_422(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        r = client.post("/dependencias", json={"pipeline_name": "PIPE_A"})
    assert r.status_code == 422
    assert "obrigatórios" in r.json()["detail"]


# ── DELETE /dependencias ─────────────────────────────────────────────────────

def test_delete_remove_tabela_e_espelho_csv(client, auth_editor):
    """Excluir a aresta apaga a dependência REAL (tabela 067) e tira o nome do
    CSV do dependente — preservando as demais entradas do CSV."""
    pipes = _pipes()
    pipes["PIPE_A"]["depends_on"] = "PIPE_ORFAO"
    db = FakeDb(pipelines=pipes)
    with _patch_db(db):
        client.post("/dependencias", json={"pipeline_name": "PIPE_A", "depende_de": "PIPE_B"})
        r = _delete(client, {"pipeline_name": "pipe_a", "depende_de": "pipe_b"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "dag_config_pendente": False}
    assert db.dependencias == []
    assert db.pipelines["PIPE_A"]["depends_on"] == "PIPE_ORFAO"


def test_delete_ultima_dependencia_zera_o_csv(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        client.post("/dependencias", json={"pipeline_name": "PIPE_A", "depende_de": "PIPE_B"})
        _delete(client, {"pipeline_name": "PIPE_A", "depende_de": "PIPE_B"})
    assert db.pipelines["PIPE_A"]["depends_on"] is None


def test_delete_inexistente_404(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        r = _delete(client, {"pipeline_name": "PIPE_A", "depende_de": "PIPE_B"})
    assert r.status_code == 404
    assert "Dependência não encontrada" in r.json()["detail"]
    assert db.commits == 0


# ── GET /malhas/{name} — arestas ─────────────────────────────────────────────

def _monta_malha(client, nome, membros):
    assert client.post("/malhas", json={"malha_name": nome}).status_code == 200
    for p in membros:
        assert client.post(f"/malhas/{nome}/pipelines",
                           json={"pipeline_name": p}).status_code == 200


def test_arestas_so_com_as_duas_pontas_na_malha(client, auth_editor):
    """A dependência A→B é GLOBAL; a malha só a mostra como aresta se AMBOS
    forem membros — malha com uma ponta só não mostra nada."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "COMPLETA", ["PIPE_A", "PIPE_B"])
        _monta_malha(client, "SO_UMA_PONTA", ["PIPE_A", "PIPE_C"])
        client.post("/dependencias", json={"pipeline_name": "PIPE_A", "depende_de": "PIPE_B"})
        r_completa = client.get("/malhas/COMPLETA")
        r_ponta = client.get("/malhas/SO_UMA_PONTA")
    assert r_completa.status_code == 200
    assert r_completa.json()["arestas"] == [
        {"pipeline_name": "PIPE_A", "depende_de": "PIPE_B"}]
    assert r_ponta.json()["arestas"] == []


def test_mesma_dependencia_aparece_em_toda_malha_com_as_duas_pontas(client, auth_editor):
    """Aceite da F8: a aresta não tem escopo por malha — duas malhas contendo
    os dois pipelines mostram a MESMA dependência."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B"])
        _monta_malha(client, "M2", ["PIPE_A", "PIPE_B", "PIPE_C"])
        client.post("/dependencias", json={"pipeline_name": "PIPE_A", "depende_de": "PIPE_B"})
        a1 = client.get("/malhas/M1").json()["arestas"]
        a2 = client.get("/malhas/M2").json()["arestas"]
    assert a1 == a2 == [{"pipeline_name": "PIPE_A", "depende_de": "PIPE_B"}]


def test_malha_sem_dependencias_tem_arestas_vazia(client, auth_editor):
    """A chave "arestas" faz parte do contrato mesmo sem dependências."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        r = client.get("/malhas/M1")
    assert r.status_code == 200
    assert r.json()["arestas"] == []
    assert "migration_067_pendente" not in r.json()


# ── PUT /malhas/{name}/layout ────────────────────────────────────────────────

def test_layout_atualiza_membros_e_ignora_nao_membros(client, auth_editor):
    """Posição de não-membro é ignorada e contada fora de 'atualizados' — o
    front pode mandar um nó recém-removido sem quebrar o salvar."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B"])
        r = client.put("/malhas/m1/layout", json={"posicoes": [
            {"pipeline_name": "pipe_a", "layout_x": 120, "layout_y": 40.5},
            {"pipeline_name": "PIPE_C", "layout_x": 0, "layout_y": 0},   # não-membro
        ]})
        detalhe = client.get("/malhas/M1").json()
    assert r.status_code == 200
    assert r.json() == {"ok": True, "atualizados": 1, "ignorados": 1}
    membros = {m["pipeline_name"]: m for m in detalhe["membros"]}
    assert membros["PIPE_A"]["layout_x"] == 120.0
    assert membros["PIPE_A"]["layout_y"] == 40.5
    assert membros["PIPE_B"]["layout_x"] is None       # não veio no body: intocado


def test_layout_sem_posicoes_e_noop(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        r = client.put("/malhas/M1/layout", json={"posicoes": []})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "atualizados": 0, "ignorados": 0}


def test_layout_malha_inexistente_404(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        r = client.put("/malhas/NAO_EXISTE/layout", json={"posicoes": []})
    assert r.status_code == 404


def test_layout_posicao_invalida_422(client, auth_editor):
    """posicoes fora de forma (não-lista, sem nome, coordenada não-numérica ou
    booleana) → 422 sem gravar nada."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        commits_antes = db.commits
        r_nao_lista = client.put("/malhas/M1/layout", json={"posicoes": "x"})
        r_sem_nome = client.put("/malhas/M1/layout", json={"posicoes": [
            {"layout_x": 1, "layout_y": 2}]})
        r_texto = client.put("/malhas/M1/layout", json={"posicoes": [
            {"pipeline_name": "PIPE_A", "layout_x": "abc", "layout_y": 2}]})
        r_bool = client.put("/malhas/M1/layout", json={"posicoes": [
            {"pipeline_name": "PIPE_A", "layout_x": True, "layout_y": 2}]})
    for r in (r_nao_lista, r_sem_nome, r_texto, r_bool):
        assert r.status_code == 422
    assert db.commits == commits_antes
    assert db.membros[0]["layout_x"] is None


# ── degradação em deploy parcial ─────────────────────────────────────────────

def test_sem_067_malha_abre_com_arestas_vazias(client, auth_editor):
    """Migration 070 aplicada, 067 pendente: a malha ainda ABRE (membros ok),
    com "arestas": [] e o sinal migration_067_pendente para o front avisar."""
    db = FakeDb(pipelines=_pipes(), com_067=False)
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B"])
        r = client.get("/malhas/M1")
    assert r.status_code == 200
    body = r.json()
    assert body["qtd_pipelines"] == 2
    assert body["arestas"] == []
    assert body["migration_067_pendente"] is True


def test_sem_067_escrita_de_dependencia_da_503(client, auth_editor):
    db = FakeDb(pipelines=_pipes(), com_067=False)
    with _patch_db(db):
        r_post = client.post("/dependencias",
                             json={"pipeline_name": "PIPE_A", "depende_de": "PIPE_B"})
        r_del = _delete(client, {"pipeline_name": "PIPE_A", "depende_de": "PIPE_B"})
    for r in (r_post, r_del):
        assert r.status_code == 503
        assert "migration 067" in r.json()["detail"]
    assert db.dependencias == [] and db.commits == 0


def test_sem_070_layout_da_503(client, auth_editor):
    """Sem as tabelas da 070 o layout não tem onde ser salvo: 503 claro."""
    db = FakeDb(pipelines=_pipes(), com_tabelas=False)
    with _patch_db(db):
        r = client.put("/malhas/M1/layout", json={"posicoes": []})
    assert r.status_code == 503
    assert "migration 070" in r.json()["detail"]


# ── grafia divergente na 067 aparece CANONIZADA no GET (revisão da F8) ──────

def test_aresta_com_grafia_divergente_e_canonizada_no_get(client, auth_editor):
    """Linha legada gravada como 'pipe_b' (register antigo / seed da 067): sem
    canonizar pela grafia dos MEMBROS, o React Flow descarta a aresta em
    silêncio — a dependência real sumia do desenho."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "LEGADA", ["PIPE_A", "PIPE_B"])
        db.dependencias.append({"pipeline": "pipe_a", "depende_de": " pipe_b"})
        r = client.get("/malhas/LEGADA")
    assert r.status_code == 200
    assert r.json()["arestas"] == [
        {"pipeline_name": "PIPE_A", "depende_de": "PIPE_B"}]
