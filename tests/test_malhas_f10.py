"""
Testes da F10 — nós especiais da malha: modelo e API do desenho
(api/routers/malhas.py + migration 075 + services/malha_nos).

Cobrem os grupos 2 e 3 do §13 do desenho (docs/malha-componentes-desenho.md):
modelo (índices filtrados de Início/Fim, CHECKs da aresta, FK NO ACTION de nó
— simulados no dublê como o banco os garante; a prova viva é o smoke §14),
gramática da tabela §2.1 célula a célula, unicidade, DELETE de nó com/sem
arestas, avisos §2.2, GET estendido (nos com upstream do SERVIDOR, arestas_no,
compilada_por), layout com "no:{id}" e degradação sem a 075.

Fronteira F10→F11 FECHADA: com o compilador (F11), gesto que envolve Aguarde
TEM efeito na 067 — o antigo aceite "zero efeito" virou o teste de ida e volta
limpa (compila ↔ descompila) e o ciclo passou a ser o PÓS-expansão com a
mensagem canônica da F1 (Decisão 15). Os testes do COMPILADOR em si (diff,
dry_run, transferência, proteções) vivem em test_malhas_f11.py.

Padrão ESTATAL de test_malhas_f8.py: o FakeDb da F8 é ESTENDIDO (subclasse)
com etl_malha_no/etl_malha_aresta (075), a coluna origem_no da 067 e os SQLs
do compilador da F11 (INSERT assinado, DELETE por assinatura, transferência).
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
from tests.test_malhas_f8 import FakeCur as FakeCurF8, FakeDb as FakeDbF8


# ── dublê estatal estendido (F8 + tabelas 075 + origem_no na 067) ────────────

class FakeDb(FakeDbF8):
    """FakeDb da F8 + etl_malha_no/etl_malha_aresta (075) e a coluna origem_no
    da 067.

    com_075=False simula o deploy parcial SEM a migration 075: GET degrada com
    migration_075_pendente (nos/arestas_no vazios) e escrita de nó/aresta dá
    503 — qualquer query que toque as tabelas nesse estado LEVANTA no dublê.

    O dublê também simula o que o MODELO da 075 garante (grupo 2 do §13):
    índices filtrados ux_malha_no_inicio/fim, CHECKs XOR/tem_no da aresta e a
    FK NO ACTION de nó — INSERT/DELETE por fora da API estouram como no banco
    (a prova VIVA é o smoke §14 no dev)."""

    def __init__(self, pipelines=None, com_tabelas=True, com_067=True,
                 com_073=False, com_075=True):
        super().__init__(pipelines=pipelines, com_tabelas=com_tabelas,
                         com_067=com_067, com_073=com_073)
        self.com_075 = com_075
        # id -> {"malha","tipo","config_json","layout_x","layout_y","criado_por"}
        self.nos: dict[int, dict] = {}
        # {"id","malha","origem_no","origem_pipeline","destino_no","destino_pipeline"}
        self.arestas_no: list[dict] = []
        self._prox_no = 1
        self._prox_aresta = 1

    def cursor(self):
        return FakeCur(self)


class FakeCur(FakeCurF8):
    def execute(self, sql, params=()):  # noqa: C901 — dispatcher de dublê
        db = self.db
        s = " ".join(str(sql).split())
        self._rows = []
        self.rowcount = -1

        # ── migration 075 (guards ANTES do raise de tabela ausente) ─────────
        if "OBJECT_ID('dbo.etl_malha_no'" in s:
            self._rows = [(1, 1)] if db.com_075 else [(None, None)]
            return
        if "COL_LENGTH('dbo.etl_pipeline_dependencia'" in s:
            self._rows = [(4,)] if db.com_075 else [(None,)]
            return
        if not db.com_075 and ("etl_malha_no" in s or "etl_malha_aresta" in s):
            raise RuntimeError("Invalid object name 'dbo.etl_malha_no'")

        # ── etl_malha_no ────────────────────────────────────────────────────
        if s.startswith("SELECT id, tipo, config_json, layout_x, layout_y "
                        "FROM dbo.etl_malha_no"):
            k = (params[0] or "").casefold()
            self._rows = sorted(
                (nid, n["tipo"], n["config_json"], n["layout_x"], n["layout_y"])
                for nid, n in db.nos.items() if n["malha"].casefold() == k)
            return
        if s.startswith("SELECT 1 FROM dbo.etl_malha_no WHERE malha_name"):
            k = (params[0] or "").casefold()
            self._rows = [(1,)] if any(
                n["malha"].casefold() == k and n["tipo"] == params[1]
                for n in db.nos.values()) else []
            return
        if s.startswith("SELECT id, tipo FROM dbo.etl_malha_no WHERE id"):
            nid, malha = params
            n = db.nos.get(nid)
            self._rows = ([(nid, n["tipo"])]
                          if n and n["malha"].casefold() == (malha or "").casefold()
                          else [])
            return
        if s.startswith("INSERT INTO dbo.etl_malha_no"):
            malha, tipo, config_json, x, y, criado_por = params
            # índice filtrado ux_malha_no_inicio/fim: garantido no MODELO
            if tipo in ("inicio", "fim") and any(
                    n["malha"].casefold() == (malha or "").casefold()
                    and n["tipo"] == tipo for n in db.nos.values()):
                raise RuntimeError(
                    "Cannot insert duplicate key row in object 'dbo.etl_malha_no' "
                    f"with unique index 'ux_malha_no_{tipo}'")
            nid = db._prox_no
            db._prox_no += 1
            db.nos[nid] = {"malha": malha, "tipo": tipo,
                           "config_json": config_json, "layout_x": x,
                           "layout_y": y, "criado_por": criado_por}
            self._rows = [(nid,)]      # OUTPUT INSERTED.id
            return
        if s.startswith("UPDATE dbo.etl_malha_no SET config_json"):
            config_json, nid, malha = params
            n = db.nos.get(nid)
            if n and n["malha"].casefold() == (malha or "").casefold():
                n["config_json"] = config_json
                self.rowcount = 1
            else:
                self.rowcount = 0
            return
        if s.startswith("UPDATE dbo.etl_malha_no SET layout_x"):
            x, y, nid, malha = params
            n = db.nos.get(nid)
            if n and n["malha"].casefold() == (malha or "").casefold():
                n["layout_x"], n["layout_y"] = x, y
                self.rowcount = 1
            else:
                self.rowcount = 0
            return
        if s.startswith("DELETE FROM dbo.etl_malha_no WHERE id"):
            nid = params[0]
            # FK NO ACTION (FK_malha_ar_ono/dno): DELETE com arestas penduradas
            # FALHA — a API tem de remover as arestas ANTES, na mesma transação.
            if any(a["origem_no"] == nid or a["destino_no"] == nid
                   for a in db.arestas_no):
                raise RuntimeError(
                    'The DELETE statement conflicted with the REFERENCE '
                    'constraint "FK_malha_ar_ono"')
            self.rowcount = 1 if db.nos.pop(nid, None) is not None else 0
            return

        # ── etl_malha_aresta ────────────────────────────────────────────────
        if s.startswith("SELECT id, origem_no, origem_pipeline, destino_no, "
                        "destino_pipeline FROM dbo.etl_malha_aresta"):
            k = (params[0] or "").casefold()
            self._rows = sorted(
                (a["id"], a["origem_no"], a["origem_pipeline"],
                 a["destino_no"], a["destino_pipeline"])
                for a in db.arestas_no if a["malha"].casefold() == k)
            return
        if s.startswith("INSERT INTO dbo.etl_malha_aresta"):
            malha, ono, opipe, dno, dpipe = params
            # CHECKs do modelo (§1.1): XOR nas pontas + tem_no
            if (ono is None) == (opipe is None):
                raise RuntimeError(
                    "The INSERT statement conflicted with the CHECK constraint "
                    '"CK_malha_ar_origem"')
            if (dno is None) == (dpipe is None):
                raise RuntimeError(
                    "The INSERT statement conflicted with the CHECK constraint "
                    '"CK_malha_ar_destino"')
            if ono is None and dno is None:
                raise RuntimeError(
                    "The INSERT statement conflicted with the CHECK constraint "
                    '"CK_malha_ar_tem_no"')
            for ref in (ono, dno):
                if ref is not None and ref not in db.nos:
                    raise RuntimeError(
                        "The INSERT statement conflicted with the FOREIGN KEY "
                        'constraint "FK_malha_ar_ono"')
            def _cf(v):
                return v.casefold() if isinstance(v, str) else v
            if any(_cf(a["malha"]) == _cf(malha)
                   and a["origem_no"] == ono and _cf(a["origem_pipeline"]) == _cf(opipe)
                   and a["destino_no"] == dno and _cf(a["destino_pipeline"]) == _cf(dpipe)
                   for a in db.arestas_no):
                raise RuntimeError(
                    "Cannot insert duplicate key row in object "
                    "'dbo.etl_malha_aresta' with unique index 'ux_malha_aresta'")
            aid = db._prox_aresta
            db._prox_aresta += 1
            db.arestas_no.append({"id": aid, "malha": malha, "origem_no": ono,
                                  "origem_pipeline": opipe, "destino_no": dno,
                                  "destino_pipeline": dpipe})
            self._rows = [(aid,)]      # OUTPUT INSERTED.id
            return
        if s.startswith("DELETE FROM dbo.etl_malha_aresta WHERE origem_no"):
            nid = params[0]
            antes = len(db.arestas_no)
            db.arestas_no = [a for a in db.arestas_no
                             if a["origem_no"] != nid and a["destino_no"] != nid]
            self.rowcount = antes - len(db.arestas_no)
            return
        if s.startswith("DELETE FROM dbo.etl_malha_aresta WHERE id"):
            aid, malha = params
            antes = len(db.arestas_no)
            db.arestas_no = [
                a for a in db.arestas_no
                if not (a["id"] == aid
                        and a["malha"].casefold() == (malha or "").casefold())]
            self.rowcount = antes - len(db.arestas_no)
            return

        # ── F13: raiz-com-dependência (§2.2) ────────────────────────────────
        # O gesto Início → pipeline pergunta se o destino TEM dependência na
        # 067 (aresta nova → 422). Dublê no estado, com a mesma fidelidade da
        # tabela ausente (com_067=False levanta como o banco levantaria).
        if s.startswith("SELECT TOP 1 1 FROM dbo.etl_pipeline_dependencia"):
            if not db.com_067:
                raise RuntimeError(
                    "Invalid object name 'dbo.etl_pipeline_dependencia'")
            cf = (params[0] or "").casefold()
            self._rows = [(1,)] if any(
                d["pipeline"].casefold() == cf for d in db.dependencias) else []
            return

        # ── 067 com a assinatura (JOIN do GET quando a 075 existe) ──────────
        if s.startswith("SELECT d.pipeline_name, d.depende_de, d.origem_no"):
            out = []
            for d in db.dependencias:
                ono = d.get("origem_no")
                n = db.nos.get(ono) if ono is not None else None
                out.append((d["pipeline"], d["depende_de"], ono,
                            n["malha"] if n else None))
            self._rows = sorted(out)
            return

        # ── compilador (F11) — SQLs novos dos gestos com efeito ─────────────
        if s.startswith("SELECT id, malha_name, tipo FROM dbo.etl_malha_no"):
            # mapa GLOBAL de nós (_nos_globais): proveniência + transferência
            self._rows = sorted((nid, n["malha"], n["tipo"])
                                for nid, n in db.nos.items())
            return
        if s.startswith("SELECT pipeline_name, depende_de, origem_no "
                        "FROM dbo.etl_pipeline_dependencia"):
            self._rows = sorted(
                (d["pipeline"], d["depende_de"], d.get("origem_no"))
                for d in db.dependencias)
            return
        if s.startswith("SELECT d.origem_no, n.malha_name "
                        "FROM dbo.etl_pipeline_dependencia d"):
            # assinatura de UMA linha (services.dependencias.assinatura)
            dep_cf = (params[0] or "").casefold()
            pred_cf = (params[1] or "").casefold()
            self._rows = []
            for d in db.dependencias:
                if (d["pipeline"].casefold() == dep_cf
                        and d["depende_de"].casefold() == pred_cf):
                    ono = d.get("origem_no")
                    n = db.nos.get(ono) if ono is not None else None
                    self._rows = [(ono, n["malha"] if n else None)]
                    break
            return
        if s.startswith("INSERT INTO dbo.etl_pipeline_dependencia") and "origem_no" in s:
            # INSERT ASSINADO do compilador; ux_dep: uma linha por par
            def _cf(v):
                return (v or "").casefold()
            if any(_cf(d["pipeline"]) == _cf(params[0])
                   and _cf(d["depende_de"]) == _cf(params[1])
                   for d in db.dependencias):
                raise RuntimeError(
                    "Cannot insert duplicate key row in object "
                    "'dbo.etl_pipeline_dependencia' with unique index 'ux_dep'")
            db.dependencias.append({"pipeline": params[0], "depende_de": params[1],
                                    "criado_por": params[2], "origem_no": params[3]})
            return
        if s.startswith("DELETE FROM dbo.etl_pipeline_dependencia") and "origem_no = ?" in s:
            # DELETE pela ASSINATURA (linha manual coincidente nunca é atingida)
            antes = len(db.dependencias)
            db.dependencias = [
                d for d in db.dependencias
                if not (d["pipeline"].casefold() == (params[0] or "").casefold()
                        and d["depende_de"].casefold() == (params[1] or "").casefold()
                        and d.get("origem_no") == params[2])]
            self.rowcount = antes - len(db.dependencias)
            return
        if s.startswith("UPDATE dbo.etl_pipeline_dependencia SET origem_no"):
            # transferência de assinatura (§7.3)
            n = 0
            for d in db.dependencias:
                if (d["pipeline"].casefold() == (params[1] or "").casefold()
                        and d["depende_de"].casefold() == (params[2] or "").casefold()):
                    d["origem_no"] = params[0]
                    n += 1
            self.rowcount = n
            return
        if s.startswith("SELECT CAST(dag_criada AS INT) FROM dbo.etl_pipeline"):
            k = db._pipeline_key(params[0])
            self._rows = [(int(db.pipelines[k].get("dag_criada") or 0),)] if k else []
            return
        if s.startswith("SELECT 1 FROM dbo.etl_malha_aresta WHERE malha_name"):
            # membro ligado a componente (recusa do remove_membro, §7.3)
            malha_cf = (params[0] or "").casefold()
            nome_cf = (params[1] or "").casefold()

            def _cfp(v):
                return v.casefold() if isinstance(v, str) else None
            self._rows = [(1,)] if any(
                a["malha"].casefold() == malha_cf
                and nome_cf in (_cfp(a["origem_pipeline"]), _cfp(a["destino_pipeline"]))
                for a in db.arestas_no) else []
            return

        super().execute(sql, params)


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_editor(app):
    """Usuário com acao_editar (quem desenha os componentes)."""
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
        "PIPE_A": {"active": 1, "criticidade": "Alta", "schedule_type": "daily",
                   "depends_on": None},
        "PIPE_B": {"active": 1, "criticidade": "Media", "schedule_type": "daily",
                   "depends_on": None},
        "PIPE_C": {"active": 1, "criticidade": "Baixa", "schedule_type": "on_demand",
                   "depends_on": None},
        "PIPE_D": {"active": 1, "criticidade": "Baixa", "schedule_type": "daily",
                   "depends_on": None},
    }


def _monta_malha(client, nome, membros):
    assert client.post("/malhas", json={"malha_name": nome}).status_code == 200
    for p in membros:
        assert client.post(f"/malhas/{nome}/pipelines",
                           json={"pipeline_name": p}).status_code == 200


def _cria_no(client, malha, tipo, **kw):
    r = client.post(f"/malhas/{malha}/nos", json={"tipo": tipo, **kw})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _aresta(client, malha, origem, destino):
    return client.post(f"/malhas/{malha}/arestas",
                       json={"origem": origem, "destino": destino})


def _avisos_do_no(payload, no_id):
    return [a for a in payload["avisos"] if a["no"] == no_id]


# ── registro das rotas e auth ────────────────────────────────────────────────

def test_rotas_f10_registradas(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json().get("paths", {})
    for p in ("/malhas/{malha_name}/nos",
              "/malhas/{malha_name}/nos/{no_id}",
              "/malhas/{malha_name}/arestas",
              "/malhas/{malha_name}/arestas/{aresta_id}"):
        assert p in paths, f"rota {p} não registrada em api/main.py"


def test_escrita_exige_acao_editar_403(client, auth_consulta):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        r_no = client.post("/malhas/M1/nos", json={"tipo": "aguarde"})
        r_patch = client.patch("/malhas/M1/nos/1", json={"config": {}})
        r_del_no = client.delete("/malhas/M1/nos/1")
        r_ar = _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": 1})
        r_del_ar = client.delete("/malhas/M1/arestas/1")
    for r in (r_no, r_patch, r_del_no, r_ar, r_del_ar):
        assert r.status_code == 403
    assert db.nos == {} and db.arestas_no == [] and db.commits == 0


# ── criação de nós ───────────────────────────────────────────────────────────

def test_criar_no_de_cada_tipo_grava_criado_por_e_devolve_avisos(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        ids = [_cria_no(client, "M1", t)
               for t in ("inicio", "aguarde", "notificacao", "fim")]
        r = client.post("/malhas/M1/nos", json={"tipo": "aguarde"})
    assert ids == [1, 2, 3, 4]
    assert r.status_code == 200 and isinstance(r.json()["avisos"], list)
    assert db.nos[1]["tipo"] == "inicio"
    assert db.nos[1]["criado_por"] == "DEV1"
    assert db.nos[5]["tipo"] == "aguarde"     # N aguardes são permitidos


def test_tipo_invalido_422(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        r = client.post("/malhas/M1/nos", json={"tipo": "sensor"})
    assert r.status_code == 422
    assert "inicio, aguarde, notificacao, fim" in r.json()["detail"]
    assert db.nos == {}


def test_config_nao_objeto_422_e_objeto_gravado_como_json(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        r_ruim = client.post("/malhas/M1/nos",
                             json={"tipo": "notificacao", "config": "titulo"})
        r_ok = client.post("/malhas/M1/nos",
                           json={"tipo": "notificacao",
                                 "config": {"titulo": "Ondas 1-2 concluídas"}})
        detalhe = client.get("/malhas/M1").json()
    assert r_ruim.status_code == 422
    assert "objeto JSON" in r_ruim.json()["detail"]
    assert r_ok.status_code == 200
    assert db.nos[1]["config_json"] == '{"titulo": "Ondas 1-2 concluídas"}'
    # o GET devolve o config como OBJETO (parse no servidor)
    assert detalhe["nos"][0]["config"] == {"titulo": "Ondas 1-2 concluídas"}


def test_layout_invalido_422(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        r = client.post("/malhas/M1/nos",
                        json={"tipo": "aguarde", "layout_x": True, "layout_y": 1})
    assert r.status_code == 422
    assert db.nos == {}


def test_segundo_inicio_422_e_o_indice_filtrado_segura_insert_direto(client, auth_editor):
    """2º Início: 422 com mensagem na API; e um INSERT por SQL direto estoura
    no índice filtrado ux_malha_no_inicio — garantia no MODELO, não só na API
    (grupo 2 do §13; a prova viva no banco real é o smoke §14)."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        _cria_no(client, "M1", "inicio")
        r = client.post("/malhas/M1/nos", json={"tipo": "inicio"})
    assert r.status_code == 422
    assert "já tem um nó Início" in r.json()["detail"]
    assert len(db.nos) == 1
    cur = db.cursor()
    with pytest.raises(RuntimeError, match="ux_malha_no_inicio"):
        cur.execute(
            "INSERT INTO dbo.etl_malha_no "
            "(malha_name, tipo, config_json, layout_x, layout_y, criado_por) "
            "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?, ?)",
            ("M1", "inicio", None, None, None, None))


def test_segundo_fim_422(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        _cria_no(client, "M1", "fim")
        r = client.post("/malhas/M1/nos", json={"tipo": "fim"})
    assert r.status_code == 422
    assert "já tem um nó Fim" in r.json()["detail"]


def test_inicio_em_duas_malhas_e_independente(client, auth_editor):
    """Aceite da F10: duas malhas com os MESMOS pipelines criam nós
    independentes — a unicidade de Início/Fim é POR MALHA (índice filtrado em
    malha_name), e o GET de cada uma só mostra os seus."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B"])
        _monta_malha(client, "M2", ["PIPE_A", "PIPE_B"])
        no_m1 = _cria_no(client, "M1", "inicio")
        no_m2 = _cria_no(client, "M2", "inicio")
        d1 = client.get("/malhas/M1").json()
        d2 = client.get("/malhas/M2").json()
    assert no_m1 != no_m2
    assert [n["id"] for n in d1["nos"]] == [no_m1]
    assert [n["id"] for n in d2["nos"]] == [no_m2]


def test_no_em_malha_inexistente_404(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        r = client.post("/malhas/NAO_EXISTE/nos", json={"tipo": "aguarde"})
    assert r.status_code == 404


# ── PATCH de nó ──────────────────────────────────────────────────────────────

def test_patch_config_layout_e_limpeza(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        nid = _cria_no(client, "M1", "notificacao",
                       config={"titulo": "velho"}, layout_x=1, layout_y=2)
        r1 = client.patch(f"/malhas/M1/nos/{nid}",
                          json={"config": {"titulo": "novo"},
                                "layout_x": 30, "layout_y": 40.5})
        r2 = client.patch(f"/malhas/M1/nos/{nid}", json={"config": None})
    assert r1.status_code == 200 and r2.status_code == 200
    assert db.nos[nid]["layout_x"] == 30.0 and db.nos[nid]["layout_y"] == 40.5
    assert db.nos[nid]["config_json"] is None      # config: None LIMPA


def test_patch_no_inexistente_ou_de_outra_malha_404(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        _monta_malha(client, "M2", ["PIPE_B"])
        nid = _cria_no(client, "M2", "aguarde")
        r_fantasma = client.patch("/malhas/M1/nos/999", json={"config": {}})
        r_outra = client.patch(f"/malhas/M1/nos/{nid}", json={"config": {}})
    assert r_fantasma.status_code == 404
    assert r_outra.status_code == 404      # nó existe, mas em OUTRA malha


def test_patch_sem_nada_para_atualizar_422(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        nid = _cria_no(client, "M1", "aguarde")
        r = client.patch(f"/malhas/M1/nos/{nid}", json={})
    assert r.status_code == 422


# ── gramática §2.1 — células permitidas ──────────────────────────────────────

def test_todas_as_celulas_permitidas_da_tabela(client, auth_editor):
    """As 8 combinações permitidas do §2.1, num desenho acíclico único:
    inicio→pipeline · pipeline→aguarde · aguarde→pipeline · aguarde→aguarde ·
    pipeline→notificacao · aguarde→notificacao · pipeline→fim · aguarde→fim."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B", "PIPE_C", "PIPE_D"])
        ini = _cria_no(client, "M1", "inicio")
        w1 = _cria_no(client, "M1", "aguarde")
        w2 = _cria_no(client, "M1", "aguarde")
        not_ = _cria_no(client, "M1", "notificacao")
        fim = _cria_no(client, "M1", "fim")
        pares = [
            ({"no": ini}, {"pipeline": "PIPE_A"}),      # inicio → pipeline
            ({"pipeline": "PIPE_A"}, {"no": w1}),       # pipeline → aguarde
            ({"no": w1}, {"pipeline": "PIPE_B"}),       # aguarde → pipeline
            ({"no": w1}, {"no": w2}),                   # aguarde → aguarde
            ({"pipeline": "PIPE_B"}, {"no": not_}),     # pipeline → notificacao
            ({"no": w2}, {"no": not_}),                 # aguarde → notificacao
            ({"pipeline": "PIPE_C"}, {"no": fim}),      # pipeline → fim
            ({"no": w2}, {"no": fim}),                  # aguarde → fim
        ]
        for origem, destino in pares:
            r = _aresta(client, "M1", origem, destino)
            assert r.status_code == 200, (origem, destino, r.text)
            assert r.json()["ja_existia"] is False
    assert len(db.arestas_no) == 8


def test_celulas_proibidas_da_tabela_422(client, auth_editor):
    """Cada célula proibida do §2.1 → 422 com a mensagem da célula, e NADA é
    gravado (nem desenho, nem 067)."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B"])
        ini = _cria_no(client, "M1", "inicio")
        w1 = _cria_no(client, "M1", "aguarde")
        not_ = _cria_no(client, "M1", "notificacao")
        fim = _cria_no(client, "M1", "fim")
        casos = [
            # inicio → nó: Início só liga em pipeline
            ({"no": ini}, {"no": w1}, "Início só liga em pipeline"),
            ({"no": ini}, {"no": not_}, "Início só liga em pipeline"),
            ({"no": ini}, {"no": fim}, "Início só liga em pipeline"),
            # qualquer → inicio: nada entra no Início
            ({"pipeline": "PIPE_A"}, {"no": ini}, "nada liga NO Início"),
            ({"no": w1}, {"no": ini}, "nada liga NO Início"),
            # notificacao/fim → qualquer: observadores terminais
            ({"no": not_}, {"pipeline": "PIPE_A"}, "observadores terminais"),
            ({"no": not_}, {"no": w1}, "observadores terminais"),
            ({"no": not_}, {"no": fim}, "observadores terminais"),
            ({"no": fim}, {"pipeline": "PIPE_A"}, "observadores terminais"),
            ({"no": fim}, {"no": w1}, "observadores terminais"),
            ({"no": fim}, {"no": not_}, "observadores terminais"),
        ]
        for origem, destino, trecho in casos:
            r = _aresta(client, "M1", origem, destino)
            assert r.status_code == 422, (origem, destino, r.text)
            assert trecho in r.json()["detail"], (origem, destino)
    assert db.arestas_no == []
    assert db.dependencias == []


def test_pipeline_para_pipeline_recusado_com_a_instrucao_da_porta_f8(client, auth_editor):
    """pipeline→pipeline não entra no desenho de nós (Decisão 2 — o CHECK
    CK_malha_ar_tem_no torna impossível no modelo): o 422 instrui a porta
    certa, a aresta direta do F8."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B"])
        r = _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"pipeline": "PIPE_B"})
    assert r.status_code == 422
    assert "aresta direta" in r.json()["detail"]
    assert db.arestas_no == [] and db.dependencias == []


# ── validações das pontas ────────────────────────────────────────────────────

def test_aresta_com_pipeline_nao_membro_422(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        w1 = _cria_no(client, "M1", "aguarde")
        r = _aresta(client, "M1", {"pipeline": "PIPE_B"}, {"no": w1})
        r_fantasma = _aresta(client, "M1", {"pipeline": "NAO_EXISTE"}, {"no": w1})
    assert r.status_code == 422
    assert "não é membro da malha" in r.json()["detail"]
    assert r_fantasma.status_code == 422
    assert "Pipeline inexistente" in r_fantasma.json()["detail"]


def test_aresta_com_no_de_outra_malha_ou_inexistente_422(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        _monta_malha(client, "M2", ["PIPE_A"])
        no_m2 = _cria_no(client, "M2", "aguarde")
        r_outra = _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": no_m2})
        r_fantasma = _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": 999})
    for r in (r_outra, r_fantasma):
        assert r.status_code == 422
        assert "não existe na malha" in r.json()["detail"]


def test_aresta_com_ponta_ambigua_422(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        w1 = _cria_no(client, "M1", "aguarde")
        r_vazia = _aresta(client, "M1", {}, {"no": w1})
        r_dupla = _aresta(client, "M1",
                          {"no": w1, "pipeline": "PIPE_A"}, {"no": w1})
        r_sem_destino = client.post("/malhas/M1/arestas",
                                    json={"origem": {"no": w1}})
    for r in (r_vazia, r_dupla, r_sem_destino):
        assert r.status_code == 422
        assert "exatamente uma das chaves" in r.json()["detail"]


def test_aresta_duplicada_e_idempotente(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        w1 = _cria_no(client, "M1", "aguarde")
        r1 = _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w1})
        commits = db.commits
        r2 = _aresta(client, "M1", {"pipeline": "pipe_a"}, {"no": w1})
    assert r1.json()["ja_existia"] is False
    assert r2.status_code == 200
    assert r2.json()["ja_existia"] is True
    assert r2.json()["id"] == r1.json()["id"]
    assert len(db.arestas_no) == 1
    assert db.commits == commits           # re-salvar não commitou nada


def test_grafia_do_pipeline_e_canonizada_na_aresta(client, auth_editor):
    """Regra da PR #236: a ponta-pipeline grava a grafia REGISTRADA — o
    upstream do GET conta a mesma história que os nós do diagrama."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        w1 = _cria_no(client, "M1", "aguarde")
        r = _aresta(client, "M1", {"pipeline": " pipe_a "}, {"no": w1})
    assert r.status_code == 200
    assert db.arestas_no[0]["origem_pipeline"] == "PIPE_A"


# ── ciclo estrutural do desenho (F10) ────────────────────────────────────────

def test_ciclo_atraves_de_nos_422(client, auth_editor):
    """A→W1→B, B→W2: fechar W2→A cicla ATRAVÉS dos nós — no F11 o ciclo passa
    a ser validado sobre o conjunto PÓS-expansão (Decisão 15): o gesto criaria
    (A depende de B) contra a linha compilada (B depende de A), e o 422 traz a
    MENSAGEM CANÔNICA do BFS da F1 (a fronteira F10/F11 registrada no
    _criaria_ciclo_desenho foi fechada — o texto topológico fica de retaguarda
    para o ciclo só-de-nós, ver o teste seguinte)."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B"])
        w1 = _cria_no(client, "M1", "aguarde")
        w2 = _cria_no(client, "M1", "aguarde")
        assert _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w1}).status_code == 200
        assert _aresta(client, "M1", {"no": w1}, {"pipeline": "PIPE_B"}).status_code == 200
        assert _aresta(client, "M1", {"pipeline": "PIPE_B"}, {"no": w2}).status_code == 200
        r = _aresta(client, "M1", {"no": w2}, {"pipeline": "PIPE_A"})
    assert r.status_code == 422
    assert r.json()["detail"] == (
        "Dependência circular: 'PIPE_A' → 'PIPE_B' fecha um ciclo "
        "(o caminho volta para 'PIPE_A')")
    assert len(db.arestas_no) == 3


def test_ciclo_aguarde_aguarde_e_self_loop_422(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        w1 = _cria_no(client, "M1", "aguarde")
        w2 = _cria_no(client, "M1", "aguarde")
        assert _aresta(client, "M1", {"no": w1}, {"no": w2}).status_code == 200
        r_volta = _aresta(client, "M1", {"no": w2}, {"no": w1})
        r_self = _aresta(client, "M1", {"no": w1}, {"no": w1})
    assert r_volta.status_code == 422
    assert "Ciclo no desenho" in r_volta.json()["detail"]
    assert r_self.status_code == 422
    assert "Ciclo no desenho" in r_self.json()["detail"]
    assert len(db.arestas_no) == 1


# ── DELETE de aresta e de nó ─────────────────────────────────────────────────

def test_delete_aresta_e_404_de_inexistente(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        w1 = _cria_no(client, "M1", "aguarde")
        aid = _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w1}).json()["id"]
        ok = client.delete(f"/malhas/M1/arestas/{aid}")
        de_novo = client.delete(f"/malhas/M1/arestas/{aid}")
    assert ok.status_code == 200 and isinstance(ok.json()["avisos"], list)
    assert db.arestas_no == []
    assert de_novo.status_code == 404


def test_delete_no_sem_arestas(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        nid = _cria_no(client, "M1", "aguarde")
        r = client.delete(f"/malhas/M1/nos/{nid}")
    assert r.status_code == 200
    assert r.json()["arestas_removidas"] == 0
    assert db.nos == {}


def test_delete_no_remove_as_arestas_na_mesma_transacao(client, auth_editor):
    """Aceite da F10: com arestas, a API remove NA ORDEM (arestas → nó) numa
    transação só — a FK NO ACTION da 075 não deixa outra ordem."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B"])
        w1 = _cria_no(client, "M1", "aguarde")
        _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w1})
        _aresta(client, "M1", {"no": w1}, {"pipeline": "PIPE_B"})
        commits = db.commits
        r = client.delete(f"/malhas/M1/nos/{w1}")
    assert r.status_code == 200
    assert r.json()["arestas_removidas"] == 2
    assert db.nos == {} and db.arestas_no == []
    assert db.commits == commits + 1       # UMA transação para o gesto inteiro


def test_delete_no_por_sql_direto_com_arestas_estoura_a_fk(client, auth_editor):
    """Grupo 2 do §13: a FK NO ACTION (FK_malha_ar_ono/dno) bloqueia DELETE de
    nó com arestas penduradas por FORA da API — falha alto, nunca leva o
    desenho junto em silêncio (a prova viva no banco real é o smoke §14)."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        w1 = _cria_no(client, "M1", "aguarde")
        _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w1})
    cur = db.cursor()
    with pytest.raises(RuntimeError, match="FK_malha_ar"):
        cur.execute("DELETE FROM dbo.etl_malha_no WHERE id = ?", (w1,))
    assert w1 in db.nos                    # nada foi removido


def test_delete_no_inexistente_404(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        r = client.delete("/malhas/M1/nos/999")
    assert r.status_code == 404


# ── efeito no motor: ida e volta limpa (fronteira F10→F11 fechada) ───────────

def test_desenho_compila_e_descompila_ida_e_volta(client, auth_editor):
    """Na F10 este teste guardava 'zero linha na 067 nasce desta fase'; a F11
    é exatamente a fase em que o desenho GANHA efeito. O que permanece
    invariante é a IDA E VOLTA LIMPA: desenhar A,B→W1→C compila as linhas
    assinadas (com espelho CSV), e excluir o nó descompila TUDO — a 067 e o
    CSV voltam byte a byte ao estado anterior (nada órfão, nada adotado)."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B", "PIPE_C"])
        w1 = _cria_no(client, "M1", "aguarde")
        _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w1})
        _aresta(client, "M1", {"pipeline": "PIPE_B"}, {"no": w1})
        r = _aresta(client, "M1", {"no": w1}, {"pipeline": "PIPE_C"})
        # a IDA: a última aresta fecha a junção e compila 2 linhas ASSINADAS
        assert r.json()["efeito"]["dependencias_criar"] == [
            {"dependente": "PIPE_C", "predecessor": "PIPE_A"},
            {"dependente": "PIPE_C", "predecessor": "PIPE_B"}]
        assert sorted((d["pipeline"], d["depende_de"], d["origem_no"])
                      for d in db.dependencias) == [
            ("PIPE_C", "PIPE_A", w1), ("PIPE_C", "PIPE_B", w1)]
        assert db.pipelines["PIPE_C"]["depends_on"] == "PIPE_A,PIPE_B"
        # a VOLTA: excluir o nó descompila tudo na mesma transação
        r_del = client.delete(f"/malhas/M1/nos/{w1}")
        assert r_del.json()["efeito"]["dependencias_remover"] == [
            {"dependente": "PIPE_C", "predecessor": "PIPE_A"},
            {"dependente": "PIPE_C", "predecessor": "PIPE_B"}]
    assert db.dependencias == []
    assert all(p["depends_on"] is None for p in db.pipelines.values())


# ── GET do detalhe estendido ─────────────────────────────────────────────────

def test_get_traz_nos_com_upstream_do_servidor_e_arestas_no(client, auth_editor):
    """O upstream vem do SERVIDOR (port da expansão, com paridade testada) —
    o front nunca expande. arestas_no espelha a tabela, ordenada por id."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B", "PIPE_C"])
        w1 = _cria_no(client, "M1", "aguarde")
        _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w1})
        _aresta(client, "M1", {"pipeline": "PIPE_B"}, {"no": w1})
        _aresta(client, "M1", {"no": w1}, {"pipeline": "PIPE_C"})
        body = client.get("/malhas/M1").json()
    assert body["nos"] == [{
        "id": w1, "tipo": "aguarde", "config": None,
        "layout_x": None, "layout_y": None,
        "upstream": ["PIPE_A", "PIPE_B"],
    }]
    assert body["arestas_no"] == [
        {"id": 1, "origem_no": None, "origem_pipeline": "PIPE_A",
         "destino_no": w1, "destino_pipeline": None},
        {"id": 2, "origem_no": None, "origem_pipeline": "PIPE_B",
         "destino_no": w1, "destino_pipeline": None},
        {"id": 3, "origem_no": w1, "origem_pipeline": None,
         "destino_no": None, "destino_pipeline": "PIPE_C"},
    ]
    assert "migration_075_pendente" not in body


def test_get_upstream_transitivo_atraves_de_aguardes(client, auth_editor):
    """aguarde→aguarde: o upstream de W2 atravessa W1 até os pipelines — a
    mesma matemática do canônico (a paridade é testada à parte)."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B", "PIPE_C"])
        w1 = _cria_no(client, "M1", "aguarde")
        w2 = _cria_no(client, "M1", "aguarde")
        _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w1})
        _aresta(client, "M1", {"no": w1}, {"no": w2})
        _aresta(client, "M1", {"pipeline": "PIPE_B"}, {"no": w2})
        _aresta(client, "M1", {"no": w2}, {"pipeline": "PIPE_C"})
        body = client.get("/malhas/M1").json()
    upstream = {n["id"]: n["upstream"] for n in body["nos"]}
    assert upstream[w1] == ["PIPE_A"]
    assert upstream[w2] == ["PIPE_A", "PIPE_B"]


# ── avisos §2.2 — no gesto e no GET ──────────────────────────────────────────

def test_avisos_no_gesto_e_no_get(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B"])
        ini = _cria_no(client, "M1", "inicio")
        w1 = _cria_no(client, "M1", "aguarde")
        not_ = _cria_no(client, "M1", "notificacao")
        r_fim = client.post("/malhas/M1/nos", json={"tipo": "fim"})
        fim = r_fim.json()["id"]

        # nós recém-criados, sem arestas: avisos estruturais no retorno do gesto
        avisos = r_fim.json()["avisos"]
        por_no = {a["no"]: a for a in avisos}
        assert "Início sem saída" in por_no[ini]["mensagem"]
        assert por_no[ini]["nivel"] == "forte"
        assert "marco visual" in por_no[w1]["mensagem"]       # aguarde sem saída
        assert por_no[w1]["nivel"] == "leve"
        assert "guardiã não avalia" in por_no[not_]["mensagem"]
        assert por_no[not_]["nivel"] == "forte"
        assert "guardiã não avalia" in por_no[fim]["mensagem"]

        # aguarde com saída e SEM entrada: aviso FORTE no gesto que o criou
        r = _aresta(client, "M1", {"no": w1}, {"pipeline": "PIPE_B"})
        forte = [a for a in r.json()["avisos"] if a["no"] == w1]
        assert any("sem entradas" in a["mensagem"] and a["nivel"] == "forte"
                   for a in forte)

        # 1 entrada: vira o aviso LEVE de junção de uma perna
        r = _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": w1})
        leves = [a for a in r.json()["avisos"] if a["no"] == w1]
        assert any("única entrada" in a["mensagem"] and a["nivel"] == "leve"
                   for a in leves)
        assert not any("sem entradas" in a["mensagem"] for a in leves)

        # o GET repete os avisos correntes (banner persistente do editor, F12)
        body = client.get("/malhas/M1").json()
        assert any(a["no"] == w1 and "única entrada" in a["mensagem"]
                   for a in body["avisos"])
        # Início ligado deixa de avisar
        _aresta(client, "M1", {"no": ini}, {"pipeline": "PIPE_A"})
        body = client.get("/malhas/M1").json()
        assert not any(a["no"] == ini for a in body["avisos"])


# ── linha assinada da 067 no GET (§7.4 — contrato de leitura) ────────────────

def test_linha_assinada_por_outra_malha_vira_aresta_com_compilada_por(client, auth_editor):
    """Renderização do §7.4: linha da 067 assinada por nó de OUTRA malha vira
    aresta direta anotada compilada_por (cadeado no editor, F12); assinada por
    nó DESTA malha NÃO vira aresta direta (ela é o desenho do nó). Na F10 nada
    assina — o contrato de leitura nasce pronto para a F11 (linhas semeadas
    direto no dublê, como o compilador fará)."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B"])
        _monta_malha(client, "M2", ["PIPE_A", "PIPE_B"])
        w_m2 = _cria_no(client, "M2", "aguarde")
        # linha da 067 assinada pelo Aguarde de M2 (semeada como a F11 gravará)
        db.dependencias.append({"pipeline": "PIPE_B", "depende_de": "PIPE_A",
                                "origem_no": w_m2})
        d1 = client.get("/malhas/M1").json()
        d2 = client.get("/malhas/M2").json()
    assert d1["arestas"] == [{
        "pipeline_name": "PIPE_B", "depende_de": "PIPE_A",
        "compilada_por": {"malha": "M2", "no": w_m2}}]
    assert d2["arestas"] == []             # desenho do nó de M2, não aresta direta


def test_linha_manual_da_067_segue_sem_anotacao(client, auth_editor):
    """Linha manual (origem_no NULL — todas as de hoje) aparece como sempre:
    sem compilada_por, byte a byte o contrato da F8."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B"])
        db.dependencias.append({"pipeline": "PIPE_B", "depende_de": "PIPE_A"})
        body = client.get("/malhas/M1").json()
    assert body["arestas"] == [{"pipeline_name": "PIPE_B", "depende_de": "PIPE_A"}]


# ── PUT layout com nós ───────────────────────────────────────────────────────

def test_layout_aceita_entradas_no_e_pipeline_mistas(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        nid = _cria_no(client, "M1", "aguarde")
        r = client.put("/malhas/M1/layout", json={"posicoes": [
            {"pipeline_name": "PIPE_A", "layout_x": 10, "layout_y": 20},
            {"pipeline_name": f"no:{nid}", "layout_x": 100, "layout_y": 200.5},
            {"pipeline_name": "no:999", "layout_x": 0, "layout_y": 0},  # não existe
        ]})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "atualizados": 2, "ignorados": 1}
    assert db.nos[nid]["layout_x"] == 100.0
    assert db.nos[nid]["layout_y"] == 200.5


def test_layout_no_com_id_invalido_422(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        r = client.put("/malhas/M1/layout", json={"posicoes": [
            {"pipeline_name": "no:abc", "layout_x": 1, "layout_y": 2}]})
    assert r.status_code == 422
    assert "no:{id}" in r.json()["detail"]


# ── degradação sem a migration 075 ───────────────────────────────────────────

def test_sem_075_get_degrada_com_flag_e_a_malha_abre(client, auth_editor):
    """Deploy parcial (070/067 ok, 075 pendente): a malha ABRE inteira —
    membros e arestas do F8 intactos — com nos/arestas_no vazios e a flag
    migration_075_pendente para o front avisar (princípio 6 do desenho)."""
    db = FakeDb(pipelines=_pipes(), com_075=False)
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B"])
        db.dependencias.append({"pipeline": "PIPE_B", "depende_de": "PIPE_A"})
        r = client.get("/malhas/M1")
    assert r.status_code == 200
    body = r.json()
    assert body["qtd_pipelines"] == 2
    assert body["arestas"] == [{"pipeline_name": "PIPE_B", "depende_de": "PIPE_A"}]
    assert body["nos"] == [] and body["arestas_no"] == [] and body["avisos"] == []
    assert body["migration_075_pendente"] is True


def test_sem_075_escrita_de_no_e_aresta_da_503(client, auth_editor):
    db = FakeDb(pipelines=_pipes(), com_075=False)
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        commits = db.commits
        r_no = client.post("/malhas/M1/nos", json={"tipo": "aguarde"})
        r_patch = client.patch("/malhas/M1/nos/1", json={"config": {}})
        r_del_no = client.delete("/malhas/M1/nos/1")
        r_ar = _aresta(client, "M1", {"pipeline": "PIPE_A"}, {"no": 1})
        r_del_ar = client.delete("/malhas/M1/arestas/1")
    for r in (r_no, r_patch, r_del_no, r_ar, r_del_ar):
        assert r.status_code == 503
        assert "migration 075" in r.json()["detail"]
    assert db.nos == {} and db.arestas_no == [] and db.commits == commits


def test_sem_075_layout_de_pipeline_segue_e_de_no_da_503(client, auth_editor):
    db = FakeDb(pipelines=_pipes(), com_075=False)
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        r_pipe = client.put("/malhas/M1/layout", json={"posicoes": [
            {"pipeline_name": "PIPE_A", "layout_x": 1, "layout_y": 2}]})
        r_no = client.put("/malhas/M1/layout", json={"posicoes": [
            {"pipeline_name": "no:1", "layout_x": 1, "layout_y": 2}]})
    assert r_pipe.status_code == 200
    assert r_no.status_code == 503
    assert "migration 075" in r_no.json()["detail"]


# ── CHECKs do modelo (grupo 2 do §13 — simulados como o banco garante) ───────

def test_modelo_recusa_aresta_malformada_por_sql_direto(client, auth_editor):
    """Os CHECKs da 075 seguram o que a API nunca deixaria passar: ponta dupla
    (XOR), ponta vazia (XOR) e pipeline→pipeline (CK_malha_ar_tem_no — a
    Decisão 2 declarada no modelo)."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B"])
        w1 = _cria_no(client, "M1", "aguarde")
    cur = db.cursor()
    sql = ("INSERT INTO dbo.etl_malha_aresta "
           "(malha_name, origem_no, origem_pipeline, destino_no, destino_pipeline) "
           "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?)")
    with pytest.raises(RuntimeError, match="CK_malha_ar_origem"):
        cur.execute(sql, ("M1", w1, "PIPE_A", None, "PIPE_B"))   # ponta dupla
    with pytest.raises(RuntimeError, match="CK_malha_ar_destino"):
        cur.execute(sql, ("M1", w1, None, None, None))           # ponta vazia
    with pytest.raises(RuntimeError, match="CK_malha_ar_tem_no"):
        cur.execute(sql, ("M1", None, "PIPE_A", None, "PIPE_B"))  # pipe→pipe
    assert db.arestas_no == []
