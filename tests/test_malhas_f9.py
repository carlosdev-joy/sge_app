"""
Testes da F9 — visão de execução da Malha (api/routers/malhas.py).

Cobrem o contrato da F9: GET /malhas/{name}/execucao devolve, por data de
referência, a execução MAIS RECENTE de cada pipeline MEMBRO (etl_pipeline_execucao,
regra do §6 risco 6 da spec) e os eventos da guardiã (etl_dependencia_evento);
sem a data na query, o servidor calcula o ODATE corrente com a virada GLOBAL de
etl_app_config — e o helper portado (api/services/data_referencia.py) tem teste
de PARIDADE com o canônico de dags/utils/data_referencia.py.

Padrão ESTATAL de test_malhas_f8.py: o FakeDb da F8 é ESTENDIDO (subclasse) com
etl_pipeline_execucao, etl_dependencia_evento e a config da virada — os fluxos
compostos (montar malha → semear execuções → abrir a visão) exercitam o SQL
real do router.

Produção PRÉ-retomada (F2–F4): as tabelas da 067 existem mas NADA as alimenta —
o "vazio honesto" (arrays vazios, sem flag) é contrato testado aqui.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from datetime import date, datetime, time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Replica o mock de pyodbc do conftest (garante o import de api.main mesmo se
# este arquivo for coletado antes do conftest configurar o ambiente).
if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from deps import PERM_EDITAR, get_current_user
from services import data_referencia as dref_api
from tests.test_malhas_f8 import FakeCur as FakeCurF8, FakeDb as FakeDbF8


# ── dublê estatal estendido (F8 + execução/eventos da 067 + config) ──────────

class FakeDb(FakeDbF8):
    """FakeDb da F8 + etl_pipeline_execucao, etl_dependencia_evento e a config
    dependencia_hora_virada.

    com_067=False agora cobre TODAS as tabelas da migration 067 (elas nascem
    juntas): a visão de execução degrada para arrays vazios + flag — qualquer
    query que toque as tabelas nesse estado LEVANTA no dublê."""

    def __init__(self, pipelines=None, com_tabelas=True, com_067=True, config=None):
        super().__init__(pipelines=pipelines, com_tabelas=com_tabelas, com_067=com_067)
        # {"pipeline", "data_referencia" (date), "execution_id", "status",
        #  "inicio" (datetime|None), "fim", "disparado_por", "motivo"}
        self.execucoes: list[dict] = []
        # {"pipeline", "data_referencia" (date), "tipo", "detalhe",
        #  "detectado_em" (datetime)}
        self.eventos: list[dict] = []
        self.config = {"dependencia_hora_virada": "00:00"} if config is None else config

    def cursor(self):
        return FakeCur(self)


class FakeCur(FakeCurF8):
    def execute(self, sql, params=()):  # noqa: C901 — dispatcher de dublê
        db = self.db
        s = " ".join(str(sql).split())
        self._rows = []
        self.rowcount = -1

        # ── checagem das tabelas de execução da 067 ─────────────────────────
        if "OBJECT_ID('dbo.etl_pipeline_execucao'" in s:
            self._rows = [(1, 1)] if db.com_067 else [(None, None)]
            return
        if not db.com_067 and ("etl_pipeline_execucao" in s
                               or "etl_dependencia_evento" in s):
            raise RuntimeError("Invalid object name (migration 067 ausente)")

        # ── membros da malha (query enxuta da F9, só o nome) ────────────────
        if s.startswith("SELECT p.pipeline_name FROM dbo.etl_malha_pipeline mp"):
            k = db._malha_key(params[0])
            out = []
            for m in db.membros:
                if k and m["malha"].casefold() == k.casefold():
                    pk = db._pipeline_key(m["pipeline"])
                    if pk is not None:      # pipeline excluído: o JOIN o faz sumir
                        out.append((pk,))
            self._rows = sorted(out)
            return

        # ── etl_pipeline_execucao por data ──────────────────────────────────
        if s.startswith("SELECT pipeline_name, status, inicio"):
            self._rows = [
                (e["pipeline"], e["status"], e["inicio"], e["fim"],
                 e["disparado_por"], e["motivo"], e["execution_id"])
                for e in db.execucoes if e["data_referencia"] == params[0]]
            return

        # ── etl_dependencia_evento por data ─────────────────────────────────
        if s.startswith("SELECT pipeline_name, tipo, detectado_em"):
            # F10: a 5ª coluna é `notificado_em` (a fila de aviso do Teams).
            # O dublê a devolve SEMPRE que o SELECT a pede — um dublê que
            # entrega menos colunas que o banco faria o painel parecer quebrado
            # aqui e funcionar em produção, que é o pior dos dois mundos.
            notif = "notificado_em" in s
            self._rows = [
                (e["pipeline"], e["tipo"], e["detectado_em"], e["detalhe"])
                + ((e.get("notificado_em"),) if notif else ())
                for e in db.eventos if e["data_referencia"] == params[0]]
            return

        # ── etl_app_config (virada global) ──────────────────────────────────
        if s.startswith("SELECT config_value FROM dbo.etl_app_config"):
            self._rows = ([(db.config[params[0]],)]
                          if params[0] in db.config else [])
            return

        super().execute(sql, params)


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_editor(app):
    """Usuário com acao_editar (monta a malha de teste pela própria API)."""
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor",
        "permissoes": [PERM_EDITAR, "tela_malha"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_consulta(app):
    """Usuário autenticado SEM acao_editar — a visão de execução é LEITURA."""
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


def _monta_malha(client, nome, membros):
    assert client.post("/malhas", json={"malha_name": nome}).status_code == 200
    for p in membros:
        assert client.post(f"/malhas/{nome}/pipelines",
                           json={"pipeline_name": p}).status_code == 200


_D = date(2026, 8, 1)


def _exec(pipeline, data_ref=_D, execution_id="run_1", status="SUCESSO",
          inicio=None, fim=None, disparado_por="agenda", motivo=None):
    return {"pipeline": pipeline, "data_referencia": data_ref,
            "execution_id": execution_id, "status": status,
            "inicio": inicio, "fim": fim,
            "disparado_por": disparado_por, "motivo": motivo}


# ── registro da rota e auth ──────────────────────────────────────────────────

def test_rota_f9_registrada(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert "/malhas/{malha_name}/execucao" in r.json().get("paths", {})


def test_sem_auth_401(client):
    assert client.get("/malhas/M1/execucao").status_code == 401


def test_leitura_nao_exige_acao_editar(client, auth_consulta):
    """Visão de execução é leitura (get_current_user, como o GET detalhe):
    perfil de consulta abre a malha sem 403."""
    db = FakeDb(pipelines=_pipes())
    db.malhas["M1"] = {"descricao": None, "ativo": 1, "criado_em": None,
                       "criado_por": None, "atualizado_em": None}
    db.membros.append({"malha": "M1", "pipeline": "PIPE_A",
                       "layout_x": None, "layout_y": None})
    with _patch_db(db):
        r = client.get("/malhas/M1/execucao?data_referencia=2026-08-01")
    assert r.status_code == 200
    assert r.json()["data_referencia"] == "2026-08-01"


# ── status por data de referência ────────────────────────────────────────────

def test_status_vem_da_data_pedida_sem_vazar_outra_data(client, auth_editor):
    """Aceite da F9: o status na malha bate com etl_pipeline_execucao DA DATA —
    linhas de outra data não vazam para o colorido dos nós."""
    db = FakeDb(pipelines=_pipes())
    db.execucoes = [
        _exec("PIPE_A", data_ref=_D, status="SUCESSO",
              inicio=datetime(2026, 8, 1, 6, 0), fim=datetime(2026, 8, 1, 6, 20),
              disparado_por="agenda"),
        _exec("PIPE_A", data_ref=date(2026, 7, 31), status="FALHA",
              inicio=datetime(2026, 7, 31, 6, 0), motivo="erro de ontem"),
    ]
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B"])
        r = client.get("/malhas/M1/execucao?data_referencia=2026-08-01")
    assert r.status_code == 200
    body = r.json()
    assert body["data_referencia"] == "2026-08-01"
    # Contrato LITERAL da execução: status CRU da tabela + campos completos.
    assert body["execucoes"] == [{
        "pipeline_name": "PIPE_A", "status": "SUCESSO",
        "inicio": "2026-08-01 06:00:00", "fim": "2026-08-01 06:20:00",
        "disparado_por": "agenda", "motivo": None,
    }]
    assert body["eventos"] == []


def test_mais_recente_da_data_vence(client, auth_editor):
    """Regra do §6 risco 6: pipeline que roda N vezes no dia responde pela
    execução MAIS RECENTE — maior inicio; linha ainda sem inicio (AGUARDANDO)
    perde de qualquer linha iniciada."""
    db = FakeDb(pipelines=_pipes())
    db.execucoes = [
        _exec("PIPE_A", execution_id="run_06h", status="FALHA",
              inicio=datetime(2026, 8, 1, 6, 0)),
        _exec("PIPE_A", execution_id="run_12h", status="SUCESSO",
              inicio=datetime(2026, 8, 1, 12, 0)),
        _exec("PIPE_A", execution_id="run_agendada", status="AGUARDANDO_DEPENDENCIA",
              inicio=None),
    ]
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        r = client.get("/malhas/M1/execucao?data_referencia=2026-08-01")
    assert [e["status"] for e in r.json()["execucoes"]] == ["SUCESSO"]
    assert r.json()["execucoes"][0]["inicio"] == "2026-08-01 12:00:00"


def test_empate_de_inicio_desempata_por_execution_id(client, auth_editor):
    inicio = datetime(2026, 8, 1, 6, 0)
    db = FakeDb(pipelines=_pipes())
    db.execucoes = [
        _exec("PIPE_A", execution_id="run_1", status="FALHA", inicio=inicio),
        _exec("PIPE_A", execution_id="run_2", status="EXECUTANDO", inicio=inicio),
    ]
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        r = client.get("/malhas/M1/execucao?data_referencia=2026-08-01")
    assert [e["status"] for e in r.json()["execucoes"]] == ["EXECUTANDO"]


def test_so_membros_aparecem_em_cada_malha(client, auth_editor):
    """Aceite da F9: pipeline fora da malha não aparece nela — a MESMA data
    mostra conjuntos diferentes em malhas diferentes."""
    db = FakeDb(pipelines=_pipes())
    db.execucoes = [
        _exec("PIPE_A", status="SUCESSO", inicio=datetime(2026, 8, 1, 6, 0)),
        _exec("PIPE_B", status="FALHA", inicio=datetime(2026, 8, 1, 7, 0)),
        _exec("PIPE_C", status="EXECUTANDO", inicio=datetime(2026, 8, 1, 8, 0)),
    ]
    with _patch_db(db):
        _monta_malha(client, "M_AB", ["PIPE_A", "PIPE_B"])
        _monta_malha(client, "M_A", ["PIPE_A"])
        r_ab = client.get("/malhas/M_AB/execucao?data_referencia=2026-08-01")
        r_a = client.get("/malhas/M_A/execucao?data_referencia=2026-08-01")
    assert [e["pipeline_name"] for e in r_ab.json()["execucoes"]] == \
        ["PIPE_A", "PIPE_B"]
    assert [e["pipeline_name"] for e in r_a.json()["execucoes"]] == ["PIPE_A"]


def test_grafia_divergente_na_067_e_canonizada(client, auth_editor):
    """Linha de execução gravada como 'pipe_a' (colação CI do banco aceita):
    sem canonizar pela grafia dos MEMBROS, o nó do React Flow não casaria com o
    status e ficaria sem cor em silêncio — mesma regra das arestas da F8."""
    db = FakeDb(pipelines=_pipes())
    db.execucoes = [_exec(" pipe_a ", status="SUCESSO",
                          inicio=datetime(2026, 8, 1, 6, 0))]
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        r = client.get("/malhas/M1/execucao?data_referencia=2026-08-01")
    assert r.json()["execucoes"][0]["pipeline_name"] == "PIPE_A"


# ── eventos da guardiã ───────────────────────────────────────────────────────

def test_eventos_filtrados_por_membro_e_ordenados_desc(client, auth_editor):
    """Eventos: só de MEMBROS, da data pedida, do mais novo para o mais antigo;
    detectado_em/detalhe da tabela viram criado_em/mensagem no contrato."""
    db = FakeDb(pipelines=_pipes())
    db.eventos = [
        {"pipeline": "PIPE_A", "data_referencia": _D, "tipo": "JANELA_ESTOUROU",
         "detalhe": "limite 08:00 estourado",
         "detectado_em": datetime(2026, 8, 1, 8, 5)},
        {"pipeline": "PIPE_A", "data_referencia": _D, "tipo": "DATA_DIVERGENTE",
         "detalhe": "predecessor em 31/07, dependente em 01/08",
         "detectado_em": datetime(2026, 8, 1, 9, 10)},
        {"pipeline": "PIPE_C", "data_referencia": _D, "tipo": "JANELA_ESTOUROU",
         "detalhe": "não-membro: não aparece",
         "detectado_em": datetime(2026, 8, 1, 8, 0)},
        {"pipeline": "PIPE_A", "data_referencia": date(2026, 7, 31),
         "tipo": "JANELA_ESTOUROU", "detalhe": "outra data: não aparece",
         "detectado_em": datetime(2026, 7, 31, 8, 5)},
    ]
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B"])
        r = client.get("/malhas/M1/execucao?data_referencia=2026-08-01")
    # F10: `notificado_em` entra como campo ADITIVO — chave presente com
    # `null` significa "está na fila e ninguém foi avisado", e é ela que
    # alimenta o banner da Decisão 66. A chave só some quando o BANCO não tem
    # a coluna, que é outra coisa ("não perguntei") e tem teste próprio.
    assert r.json()["eventos"] == [
        {"pipeline_name": "PIPE_A", "tipo": "DATA_DIVERGENTE",
         "criado_em": "2026-08-01 09:10:00",
         "mensagem": "predecessor em 31/07, dependente em 01/08",
         "notificado_em": None},
        {"pipeline_name": "PIPE_A", "tipo": "JANELA_ESTOUROU",
         "criado_em": "2026-08-01 08:05:00",
         "mensagem": "limite 08:00 estourado",
         "notificado_em": None},
    ]


# ── ODATE corrente (sem data na query) ───────────────────────────────────────

def test_sem_data_usa_odate_corrente_com_virada_global(client, auth_editor):
    """23:30 de 31/07 com virada global 20:00 → ODATE 01/08 (o caso que motivou
    a spec): a resposta declara a data usada e busca as execuções NELA."""
    db = FakeDb(pipelines=_pipes(),
                config={"dependencia_hora_virada": "20:00"})
    db.execucoes = [_exec("PIPE_A", data_ref=date(2026, 8, 1), status="EXECUTANDO",
                          inicio=datetime(2026, 7, 31, 23, 40))]
    with _patch_db(db), patch("routers.malhas._agora",
                              return_value=datetime(2026, 7, 31, 23, 30)):
        _monta_malha(client, "M1", ["PIPE_A"])
        r = client.get("/malhas/M1/execucao")
    body = r.json()
    assert body["data_referencia"] == "2026-08-01"
    assert [e["status"] for e in body["execucoes"]] == ["EXECUTANDO"]


def test_virada_padrao_e_config_ausente_usam_a_data_do_calendario(client, auth_editor):
    """00:00 (default da 067) e config ausente caem na data do calendário —
    config quebrado/ausente nunca impede a malha de abrir."""
    for config in ({"dependencia_hora_virada": "00:00"}, {},
                   {"dependencia_hora_virada": "meia-noite"}):
        db = FakeDb(pipelines=_pipes(), config=config)
        with _patch_db(db), patch("routers.malhas._agora",
                                  return_value=datetime(2026, 7, 31, 23, 30)):
            _monta_malha(client, "M1", ["PIPE_A"])
            r = client.get("/malhas/M1/execucao")
        assert r.status_code == 200
        assert r.json()["data_referencia"] == "2026-07-31", f"config={config}"


# ── validação e degradação ───────────────────────────────────────────────────

def test_data_malformada_422(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        for ruim in ("01/08/2026", "2026-13-01", "hoje"):
            r = client.get(f"/malhas/M1/execucao?data_referencia={ruim}")
            assert r.status_code == 422, ruim
            assert "YYYY-MM-DD" in r.json()["detail"]


def test_malha_inexistente_404(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        r = client.get("/malhas/NAO_EXISTE/execucao?data_referencia=2026-08-01")
    assert r.status_code == 404
    assert "NAO_EXISTE" in r.json()["detail"]


def test_sem_067_degrada_com_flag_e_a_malha_abre(client, auth_editor):
    """Deploy parcial (070 aplicada, 067 pendente): 200 com arrays vazios +
    migration_067_pendente — a malha continua abrindo, sem status."""
    db = FakeDb(pipelines=_pipes(), com_067=False)
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A"])
        r = client.get("/malhas/M1/execucao?data_referencia=2026-08-01")
    assert r.status_code == 200
    body = r.json()
    assert body["execucoes"] == [] and body["eventos"] == []
    assert body["migration_067_pendente"] is True


def test_vazio_honesto_sem_execucoes_na_data(client, auth_editor):
    """Produção PRÉ-retomada (F2–F4): a 067 existe mas nada a alimenta — a
    resposta é arrays vazios SEM flag de migration (o registro chega com a
    retomada; a tela conta essa verdade, nunca quebra nem promete)."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["PIPE_A", "PIPE_B"])
        r = client.get("/malhas/M1/execucao?data_referencia=2026-08-01")
    assert r.status_code == 200
    body = r.json()
    assert body["execucoes"] == [] and body["eventos"] == []
    assert "migration_067_pendente" not in body


# ── paridade do port de data_referencia (api/services ↔ dags/utils) ─────────

_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def dref_dags():
    """Canônico de dags/, carregado por caminho como em test_dependencias_f1."""
    spec = importlib.util.spec_from_file_location(
        "data_referencia_dags_f9", _ROOT / "dags/utils/data_referencia.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_paridade_calcular_com_o_canonico_de_dags(dref_dags):
    """REUSA os valores de test_dependencias_f1: virada 20:00 junta 31/07 23:30
    e 01/08 00:40 no ODATE 01/08; 00:00 preserva a data do calendário; na
    virada exata já é o dia seguinte. Os DOIS módulos têm de concordar."""
    casos = [
        (datetime(2026, 7, 31, 23, 30), None, date(2026, 7, 31)),
        (datetime(2026, 8, 1, 0, 40), None, date(2026, 8, 1)),
        (datetime(2026, 7, 31, 23, 30), time(20, 0), date(2026, 8, 1)),
        (datetime(2026, 8, 1, 0, 40), time(20, 0), date(2026, 8, 1)),
        (datetime(2026, 8, 1, 19, 59), time(20, 0), date(2026, 8, 1)),
        (datetime(2026, 8, 1, 20, 0), time(20, 0), date(2026, 8, 2)),
    ]
    for momento, virada, esperado in casos:
        assert dref_api.calcular(momento, virada) == esperado, (momento, virada)
        assert dref_dags.calcular(momento, virada) == \
            dref_api.calcular(momento, virada), (momento, virada)


def test_paridade_parse_virada_tolerante(dref_dags):
    """Valor estranho em etl_app_config não derruba o cálculo — em NENHUMA das
    duas árvores de deploy."""
    for valor in ("meia-noite", None, "", "20:00", "20:00:00", "lixo", time(7, 30)):
        assert dref_api.parse_virada(valor) == dref_dags.parse_virada(valor), valor
    assert dref_api.parse_virada("meia-noite") == dref_api.VIRADA_PADRAO
    assert dref_api.parse_virada("20:00:00") == time(20, 0)
    assert dref_api.calcular(datetime(2026, 7, 31, 23, 30), "lixo") == date(2026, 7, 31)
    assert dref_api.VIRADA_PADRAO == dref_dags.VIRADA_PADRAO
