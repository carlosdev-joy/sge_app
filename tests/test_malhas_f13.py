"""
Testes da F13 — Início: agendamento da malha (grupo 6 do §13 do desenho
docs/malha-componentes-desenho.md, §4/Decisões 8-11 + a pendência declarada
pela revisão da F12: o 422 de raiz-com-dependência do §2.2).

Cobrem: validação do agendamento pelas MESMAS funções do register (domínio,
dias_horarios_mes, horários específicos; hora_virada inválida → NULL com
aviso, D35); cópia campo a campo às raízes INCLUSIVE hora_virada e o
scheduled_time DERIVADO (o gerador lê scheduled_time — sem alinhar, o aceite
'crons idênticos' seria impossível); assinatura agenda_no + carimbo (só com
dag_criada=1); conflito de assinatura entre malhas (Decisão 11 — 422
nomeando a dona nas DUAS portas: agendamento e aresta); desligar raiz →
on_demand + carimbo, NUNCA os valores antigos de volta (Decisão 10, teste de
ausência); excluir o Início desliga todas as raízes assinadas e PRESERVA o
agendamento_json da malha (Decisão 8 — o nó é o plugue); raiz com dependência
na 067 → 422 no gesto da aresta (§2.2) e badge de contradição quando a
dependência chega DEPOIS por outra porta (aviso, nunca bloqueio); dry_run sem
gravação; rollback total; degradação sem as colunas da 075.

Dublês: o FakeDb da F11 é ESTENDIDO (subclasse) com etl_malha.agendamento_json,
etl_pipeline.agenda_no (+ colunas de agenda no dict de pipeline) e a FK
FK_pipe_agenda_no simulada como o banco a garante (DELETE de nó com
assinatura de agenda pendurada FALHA — prova que o endpoint desliga ANTES,
na ordem do §1.4).
"""
from __future__ import annotations

import copy
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
from tests.test_malhas_f10 import _aresta, _cria_no, _monta_malha
from tests.test_malhas_f11 import FakeCur as FakeCurF11, FakeDb as FakeDbF11


# ── dublê: F11 + agendamento_json / agenda_no (colunas da 075, F13) ──────────

class FakeDb(FakeDbF11):
    """FakeDb da F11 + as colunas de agendamento da 075: etl_malha.
    agendamento_json (dict da malha) e etl_pipeline.agenda_no + colunas de
    agenda no dict de cada pipeline.

    com_agenda=False simula a 075 aplicada PELA METADE (tabelas sim, colunas
    de agenda não): o guard _colunas_agenda degrada e o Início volta a ser
    só desenho (F12). falhar_copia injeta erro no UPDATE da cópia para
    provar o rollback TOTAL da transação do gesto."""

    def __init__(self, pipelines=None, com_tabelas=True, com_067=True,
                 com_073=True, com_075=True, com_agenda=None):
        super().__init__(pipelines=pipelines, com_tabelas=com_tabelas,
                         com_067=com_067, com_073=com_073, com_075=com_075)
        self.com_agenda = com_075 if com_agenda is None else com_agenda
        self.falhar_copia = False

    def cursor(self):
        self._snapshot = copy.deepcopy(self._estado())
        return FakeCur(self)


class FakeCur(FakeCurF11):
    def execute(self, sql, params=()):  # noqa: C901 — dispatcher de dublê
        db = self.db
        s = " ".join(str(sql).split())
        params = tuple(params)

        # guard das colunas de agendamento (F13) — ANTES do COL_LENGTH
        # genérico de etl_malha (074) do dublê da F7
        if "COL_LENGTH('dbo.etl_malha', 'agendamento_json')" in s:
            self._rows = [(4, 4)] if db.com_agenda else [(None, None)]
            self.rowcount = -1
            return
        if s.startswith("SELECT agendamento_json FROM dbo.etl_malha WHERE"):
            if not db.com_agenda:
                raise RuntimeError("Invalid column name 'agendamento_json'")
            k = db._malha_key(params[0])
            self._rows = [(db.malhas[k].get("agendamento_json"),)] if k else []
            self.rowcount = -1
            return
        if s.startswith("UPDATE dbo.etl_malha SET agendamento_json"):
            if not db.com_agenda:
                raise RuntimeError("Invalid column name 'agendamento_json'")
            k = db._malha_key(params[1])
            if k:
                db.malhas[k]["agendamento_json"] = params[0]
            self.rowcount = 1 if k else 0
            return
        if s.startswith("SELECT p.schedule_type, CAST(p.schedule_hour AS INT)"):
            # _agenda_da_raiz: fotografia + assinatura + dag_criada
            k = db._pipeline_key(params[0])
            if k is None:
                self._rows = []
                return
            p = db.pipelines[k]
            ono = p.get("agenda_no")
            n = db.nos.get(ono) if ono is not None else None
            self._rows = [(
                p.get("schedule_type"), p.get("schedule_hour"),
                p.get("schedule_minute"), p.get("schedule_dow"),
                p.get("schedule_dom"), p.get("horarios_especificos"),
                p.get("dias_semana"), p.get("dias_horarios_mes"),
                p.get("somente_dias_uteis"), p.get("calendario_nome"),
                (str(p.get("hora_virada"))[:5] if p.get("hora_virada") else None),
                ono, (n or {}).get("malha"), int(p.get("dag_criada") or 0))]
            self.rowcount = -1
            return
        # (SELECT TOP 1 1 da raiz-com-dependência: herdado do dublê da F10 —
        # o gesto vale desde a F10 e o handler mora lá, uma fonte só.)
        if s.startswith("SELECT pipeline_name FROM dbo.etl_pipeline WHERE agenda_no"):
            self._rows = sorted((k,) for k, p in db.pipelines.items()
                                if p.get("agenda_no") == params[0])
            self.rowcount = -1
            return
        if s.startswith("UPDATE dbo.etl_pipeline SET scheduled_time"):
            # a CÓPIA do §4.2 (13 campos + pipeline no WHERE)
            if db.falhar_copia:
                raise RuntimeError("deadlock simulado na cópia da agenda (teste)")
            k = db._pipeline_key(params[13])
            if k:
                p = db.pipelines[k]
                (p["scheduled_time"], p["schedule_type"], p["schedule_hour"],
                 p["schedule_minute"], p["schedule_dow"], p["schedule_dom"],
                 p["horarios_especificos"], p["dias_semana"],
                 p["dias_horarios_mes"], p["somente_dias_uteis"],
                 p["calendario_nome"], p["hora_virada"],
                 p["agenda_no"]) = params[:13]
            self.rowcount = 1 if k else 0
            return
        if s.startswith("UPDATE dbo.etl_pipeline SET schedule_type = 'on_demand'"):
            # Decisão 10: desligar a raiz
            k = db._pipeline_key(params[0])
            if k:
                db.pipelines[k]["schedule_type"] = "on_demand"
                db.pipelines[k]["agenda_no"] = None
            self.rowcount = 1 if k else 0
            return
        if "FROM dbo.etl_malha_pipeline mp JOIN dbo.etl_pipeline p" in s \
                and "p.agenda_no" in s:
            # membros do detalhe COM a coluna aditiva agenda_no (F13)
            k = db._malha_key(params[0])
            out = []
            for m in db.membros:
                if k and m["malha"].casefold() == k.casefold():
                    pk = db._pipeline_key(m["pipeline"])
                    if pk is None:
                        continue
                    p = db.pipelines[pk]
                    out.append((pk, p.get("active", 1),
                                p.get("criticidade") or "Media",
                                p.get("schedule_type"),
                                m["layout_x"], m["layout_y"],
                                p.get("agenda_no")))
            self._rows = sorted(out)
            self.rowcount = -1
            return
        if s.startswith("DELETE FROM dbo.etl_malha_no WHERE id"):
            # FK_pipe_agenda_no (NO ACTION, §1.4): nó com assinatura de
            # AGENDA pendurada não pode ser excluído — como o banco garante.
            nid = params[0]
            if any(p.get("agenda_no") == nid for p in db.pipelines.values()):
                raise RuntimeError(
                    'The DELETE statement conflicted with the REFERENCE '
                    'constraint "FK_pipe_agenda_no"')
        super().execute(sql, params)


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_editor(app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor",
        "permissoes": [PERM_EDITAR, "tela_malha", "tela_pipelines"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_consulta(app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "USER1", "perfil": "consulta", "permissoes": ["tela_malha"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _patch_db(db):
    return patch("routers.malhas.get_db_conn", return_value=db)


def _pipes():
    """Raízes A/B (DAG publicada) e C (não publicada) com agendamento diário
    próprio; PIPE_DEP/PIPE_PRED para o cenário de dependência."""
    base = {"active": 1, "criticidade": "Media", "depends_on": None,
            "scheduled_time": "07:30:00", "schedule_type": "daily",
            "schedule_hour": 7, "schedule_minute": 30, "schedule_dow": 1,
            "schedule_dom": 1, "horarios_especificos": None,
            "dias_semana": None, "dias_horarios_mes": None,
            "somente_dias_uteis": 0, "calendario_nome": None,
            "hora_virada": None, "agenda_no": None}
    return {
        "RAIZ_A": {**base, "dag_criada": 1},
        "RAIZ_B": {**base, "dag_criada": 1},
        "RAIZ_C": {**base, "dag_criada": 0},
        "PIPE_DEP": {**base, "dag_criada": 1},
        "PIPE_PRED": {**base, "dag_criada": 0},
    }


def _ag_weekly(**kw):
    """O agendamento do cenário E6: semanal dom (D05: dow 0 = domingo) 20:00,
    virada 20:00."""
    ag = {"schedule_type": "weekly", "schedule_hour": 20, "schedule_minute": 0,
          "schedule_dow": 0, "hora_virada": "20:00"}
    ag.update(kw)
    return ag


def _salvar(client, malha, agendamento, dry_run=False):
    body = {"agendamento": agendamento}
    if dry_run:
        body["dry_run"] = True
    return client.post(f"/malhas/{malha}/agendamento", json=body)


def _monta_inicio(client, malha, raizes):
    """Malha + membros + Início ligado às raízes. Devolve o id do Início."""
    _monta_malha(client, malha, raizes)
    ini = _cria_no(client, malha, "inicio")
    for p in raizes:
        r = _aresta(client, malha, {"no": ini}, {"pipeline": p})
        assert r.status_code == 200, r.text
    return ini


# ── registro da rota e permissão ─────────────────────────────────────────────

def test_rota_f13_registrada(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert "/malhas/{malha_name}/agendamento" in r.json().get("paths", {})


def test_agendamento_exige_acao_editar_403(client, auth_consulta):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        r = _salvar(client, "M1", _ag_weekly())
    assert r.status_code == 403
    assert db.commits == 0


# ── o aceite central (§10-F13): cópia às raízes ──────────────────────────────

def test_salvar_agendamento_copia_para_3_raizes(client, auth_editor):
    """3 raízes ligadas ao Início → colunas IDÊNTICAS nas três (hora_virada
    inclusive — Decisão 9), scheduled_time DERIVADO (o gerador lê dele),
    assinatura agenda_no, carimbo SÓ para quem tem dag_criada=1, JSON salvo
    na malha e o gesto inteiro numa transação."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        ini = _monta_inicio(client, "M1", ["RAIZ_A", "RAIZ_B", "RAIZ_C"])
        db.pipelines["RAIZ_A"]["dag_config_pendente"] = 0
        commits = db.commits
        r = _salvar(client, "M1", _ag_weekly())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["efeito"]["agendamentos"] == [
        {"pipeline": "RAIZ_A", "de": "diário 07:30",
         "para": "semanal (dom) 20:00 · virada 20:00"},
        {"pipeline": "RAIZ_B", "de": "diário 07:30",
         "para": "semanal (dom) 20:00 · virada 20:00"},
        {"pipeline": "RAIZ_C", "de": "diário 07:30",
         "para": "semanal (dom) 20:00 · virada 20:00"}]
    assert body["efeito"]["republicar"] == ["RAIZ_A", "RAIZ_B"]
    assert body["cron"] == "0 20 * * 0"          # a MESMA função do register
    for nome in ("RAIZ_A", "RAIZ_B", "RAIZ_C"):
        p = db.pipelines[nome]
        assert p["schedule_type"] == "weekly"
        assert p["schedule_hour"] == 20 and p["schedule_minute"] == 0
        assert p["schedule_dow"] == 0
        assert p["scheduled_time"] == "20:00:00"     # derivado, alinhado
        assert p["hora_virada"] == "20:00:00"        # Decisão 9
        assert p["agenda_no"] == ini                 # assinatura
    # carimbo: A e B têm DAG publicada; C não
    assert db.pipelines["RAIZ_A"]["dag_config_pendente"] == 1
    assert db.pipelines["RAIZ_B"]["dag_config_pendente"] == 1
    assert db.pipelines["RAIZ_C"].get("dag_config_pendente") != 1
    # JSON na malha (fonte de compilação — o motor nunca lê daqui)
    assert '"schedule_type": "weekly"' in db.malhas["M1"]["agendamento_json"]
    assert db.commits == commits + 1                 # UMA transação


def test_dry_run_devolve_o_efeito_sem_gravar(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_inicio(client, "M1", ["RAIZ_A"])
        antes = copy.deepcopy(db._estado())
        commits = db.commits
        r = _salvar(client, "M1", _ag_weekly(), dry_run=True)
    assert r.status_code == 200
    body = r.json()
    assert set(body["efeito"].keys()) == {
        "dependencias_criar", "dependencias_remover",
        "dependencias_transferir", "ja_existentes_manuais",
        "agendamentos", "republicar"}
    assert body["efeito"]["agendamentos"] == [
        {"pipeline": "RAIZ_A", "de": "diário 07:30",
         "para": "semanal (dom) 20:00 · virada 20:00"}]
    assert body["erros"] == []
    assert db._estado() == antes
    assert db.commits == commits


def test_salvar_de_novo_o_mesmo_agendamento_e_no_op_nas_raizes(client, auth_editor):
    """Raiz já compilada campo a campo não entra no efeito nem ganha carimbo
    de novo — o re-salvar é honesto sobre não ter nada a fazer."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_inicio(client, "M1", ["RAIZ_A"])
        assert _salvar(client, "M1", _ag_weekly()).status_code == 200
        db.pipelines["RAIZ_A"]["dag_config_pendente"] = 0
        r = _salvar(client, "M1", _ag_weekly())
    assert r.status_code == 200
    assert r.json()["efeito"]["agendamentos"] == []
    assert r.json()["efeito"]["republicar"] == []
    assert db.pipelines["RAIZ_A"]["dag_config_pendente"] == 0


def test_agendamento_sem_inicio_salva_com_aviso(client, auth_editor):
    """Decisão 8: o agendamento é da MALHA — sem nó Início ele fica guardado
    (o nó é o plugue) e o aviso forte diz que nada foi alcançado."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["RAIZ_A"])
        r = _salvar(client, "M1", _ag_weekly())
    assert r.status_code == 200
    assert r.json()["efeito"]["agendamentos"] == []
    assert any("não tem nó Início" in a["mensagem"] for a in r.json()["avisos"])
    assert db.malhas["M1"].get("agendamento_json")
    assert db.pipelines["RAIZ_A"]["agenda_no"] is None


# ── validação pelas MESMAS funções do register (§13 grupo 6) ─────────────────

def test_validacao_do_agendamento(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_inicio(client, "M1", ["RAIZ_A"])
        casos = [
            (None, "agendamento deve ser um objeto"),
            ({}, "agendamento deve ser um objeto"),
            ({"schedule_type": "weekly", "intruso": 1},
             "Campos fora do schema"),
            ({"schedule_hour": 6}, "schedule_type é obrigatório"),
            ({"schedule_type": "on_demand"}, "não aceita 'on_demand'"),
            ({"schedule_type": "monthly_days_times"},
             "dias_horarios_mes é obrigatório para schedule_type "
             "'monthly_days_times'"),                # mensagem literal do register
            ({"schedule_type": "monthly_days_times",
              "dias_horarios_mes": "não é json"},
             "dias_horarios_mes deve ser um JSON válido"),
            ({"schedule_type": "custom"},
             "horarios_especificos é obrigatório"),
            ({"schedule_type": "custom", "horarios_especificos": "25:00"},
             "Horário fora do intervalo: '25:00'"),  # _parse_horarios_especificos
            ({"schedule_type": "daily", "schedule_hour": 99},
             "schedule_hour fora do intervalo"),
            ({"schedule_type": "daily", "dias_semana": "7"},
             "dias_semana inválido"),
        ]
        for ag, trecho in casos:
            r = _salvar(client, "M1", ag)
            assert r.status_code == 422, (ag, r.text)
            assert trecho in r.json()["detail"], (ag, r.json()["detail"])
        assert db.pipelines["RAIZ_A"]["agenda_no"] is None
        # hora_virada inválida NÃO recusa: vira NULL com aviso (D35)
        r = _salvar(client, "M1", _ag_weekly(hora_virada="meia-noite"))
    assert r.status_code == 200
    assert any("hora_virada" in a["mensagem"] and "inválido" in a["mensagem"]
               for a in r.json()["avisos"])
    assert db.pipelines["RAIZ_A"]["hora_virada"] is None
    assert db.pipelines["RAIZ_A"]["schedule_type"] == "weekly"


def test_biweekly_dom_limitado_a_13(client, auth_editor):
    """Defeito GRAVE da revisão adversarial da F13: quinzenal com dom 14–28
    passava na validação e compilava schedule_dom=20 → o cron do factory sai
    '0 6 20,35 * *' (dia 35 não existe) → Broken DAG após republicar e a raiz
    PARA de agendar; 14–16 gera cron válido mas quinzena falsa (a 2ª cai em
    29–31 e pula meses). O wizard sempre bloqueou (1–13) — o agendamento da
    malha bloqueia com a MESMA mensagem; dom=13 segue válido (13 e 28)."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_inicio(client, "M1", ["RAIZ_A"])
        r_ruim = _salvar(client, "M1", {
            "schedule_type": "biweekly", "schedule_hour": 6,
            "schedule_minute": 0, "schedule_dom": 20})
        assert r_ruim.status_code == 422, r_ruim.text
        assert "Dia da 1ª quinzena inválido (1–13)" in r_ruim.json()["detail"]
        assert db.pipelines["RAIZ_A"]["agenda_no"] is None   # nada compilado
        r_ok = _salvar(client, "M1", {
            "schedule_type": "biweekly", "schedule_hour": 6,
            "schedule_minute": 0, "schedule_dom": 13})
    assert r_ok.status_code == 200, r_ok.text
    assert r_ok.json()["cron"] == "0 6 13,28 * *"            # dentro de 1–31
    assert db.pipelines["RAIZ_A"]["schedule_dom"] == 13


def test_custom_deriva_hora_do_primeiro_horario(client, auth_editor):
    """'custom': hora/minuto e scheduled_time seguem o PRIMEIRO horário — a
    mesma derivação do wizard (buildSchedulePayload)."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_inicio(client, "M1", ["RAIZ_A"])
        r = _salvar(client, "M1", {
            "schedule_type": "custom",
            "horarios_especificos": "14:30, 9:0",
            "dias_semana": "5,1"})
    assert r.status_code == 200
    p = db.pipelines["RAIZ_A"]
    assert p["horarios_especificos"] == "09:00,14:30"   # normalizado/ordenado
    assert p["dias_semana"] == "1,5"
    assert p["schedule_hour"] == 9 and p["schedule_minute"] == 0
    assert p["scheduled_time"] == "09:00:00"


# ── conflito de assinatura (Decisão 11) ──────────────────────────────────────

def test_agendamento_com_raiz_de_outra_malha_422_nomeando(client, auth_editor):
    """E8 pela porta do AGENDAMENTO: M2 também ligou o Início na mesma raiz
    (antes de qualquer assinatura); M1 assina primeiro — o agendamento de M2
    devolve o conflito em `erros` no dry_run (HTTP 200) e 422 no write,
    nomeando a malha e o nó donos. Nada de last-write-wins."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        ini1 = _monta_inicio(client, "M1", ["RAIZ_A"])
        _monta_inicio(client, "M2", ["RAIZ_A"])
        assert _salvar(client, "M1", _ag_weekly()).status_code == 200
        assert db.pipelines["RAIZ_A"]["agenda_no"] == ini1
        r_dry = _salvar(client, "M2", _ag_weekly(schedule_dow=3), dry_run=True)
        assert r_dry.status_code == 200
        assert len(r_dry.json()["erros"]) == 1
        assert f"Início #{ini1}" in r_dry.json()["erros"][0]
        assert "'M1'" in r_dry.json()["erros"][0]
        antes = copy.deepcopy(db._estado())
        r = _salvar(client, "M2", _ag_weekly(schedule_dow=3))
    assert r.status_code == 422
    assert f"Início #{ini1}" in r.json()["detail"]
    assert "'M1'" in r.json()["detail"]
    assert db._estado() == antes                 # nem o JSON de M2 foi salvo


def test_aresta_inicio_para_raiz_de_outra_malha_422_nomeando(client, auth_editor):
    """E8 pela porta da ARESTA: ligar o Início de M2 numa raiz JÁ assinada
    por M1 → 422 nomeando a dona; o fio nem nasce."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        ini1 = _monta_inicio(client, "M1", ["RAIZ_A"])
        assert _salvar(client, "M1", _ag_weekly()).status_code == 200
        _monta_malha(client, "M2", ["RAIZ_A"])
        ini2 = _cria_no(client, "M2", "inicio")
        arestas_antes = len(db.arestas_no)
        r = _aresta(client, "M2", {"no": ini2}, {"pipeline": "RAIZ_A"})
    assert r.status_code == 422
    assert f"Início #{ini1}" in r.json()["detail"]
    assert "'M1'" in r.json()["detail"]
    assert len(db.arestas_no) == arestas_antes


# ── raiz com dependência (§2.2 — a pendência da revisão da F12) ──────────────

def test_aresta_inicio_para_pipeline_com_dependencia_422(client, auth_editor):
    """A célula do §2.2: Início → pipeline que TEM dependência na 067 → 422
    ('raiz não pode ter dependência — o schedule=None do motor venceria o
    cron'); nada é gravado, nem o fio."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        assert client.post("/dependencias", json={
            "pipeline_name": "PIPE_DEP",
            "depende_de": "PIPE_PRED"}).status_code == 200
        _monta_malha(client, "M1", ["PIPE_DEP"])
        ini = _cria_no(client, "M1", "inicio")
        antes = copy.deepcopy(db._estado())
        r = _aresta(client, "M1", {"no": ini}, {"pipeline": "PIPE_DEP"})
    assert r.status_code == 422
    assert "raiz não pode ter dependência" in r.json()["detail"]
    assert "schedule=None do motor venceria o cron" in r.json()["detail"]
    assert db._estado() == antes


def test_dependencia_que_chega_depois_vira_aviso_nunca_bloqueio(client, auth_editor):
    """§2.2 última linha: raiz ASSINADA que ganha dependência por OUTRA porta
    (F8) depois — a porta NÃO é bloqueada; o GET marca agenda_contradicao no
    membro e o aviso forte aparece no Início (badge de contradição)."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        ini = _monta_inicio(client, "M1", ["RAIZ_A"])
        assert _salvar(client, "M1", _ag_weekly()).status_code == 200
        # a porta F8 continua aberta (aviso, não bloqueio)
        assert client.post("/dependencias", json={
            "pipeline_name": "RAIZ_A",
            "depende_de": "PIPE_PRED"}).status_code == 200
        detalhe = client.get("/malhas/M1").json()
        # re-salvar a aresta existente não vira 422 — no-op com o aviso
        r_re = _aresta(client, "M1", {"no": ini}, {"pipeline": "RAIZ_A"})
    membro = next(m for m in detalhe["membros"]
                  if m["pipeline_name"] == "RAIZ_A")
    assert membro["agenda_no"] == ini
    assert membro["agenda_contradicao"] is True
    assert any(a["no"] == ini and a["nivel"] == "forte"
               and "agendamento da malha está inerte" in a["mensagem"]
               for a in detalhe["avisos"])
    assert r_re.status_code == 200
    assert r_re.json()["ja_existia"] is True
    assert any("agendamento da malha está inerte" in a["mensagem"]
               for a in r_re.json()["avisos"])


# ── o gesto da aresta Início → raiz ──────────────────────────────────────────

def test_aresta_inicio_sem_agendamento_liga_so_o_fio(client, auth_editor):
    """§4.2: sem agendamento na malha, ligar o Início cria só o fio, com o
    aviso 'configure o agendamento' — zero cópia, zero assinatura."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_malha(client, "M1", ["RAIZ_A"])
        ini = _cria_no(client, "M1", "inicio")
        r = _aresta(client, "M1", {"no": ini}, {"pipeline": "RAIZ_A"})
    assert r.status_code == 200
    assert r.json()["efeito"]["agendamentos"] == []
    assert any("configure o agendamento no Início" in a["mensagem"]
               for a in r.json()["avisos"])
    assert db.pipelines["RAIZ_A"]["agenda_no"] is None
    assert db.pipelines["RAIZ_A"]["schedule_type"] == "daily"


def test_aresta_inicio_com_agendamento_compila_na_hora(client, auth_editor):
    """Raiz ligada DEPOIS do agendamento salvo: o gesto da aresta mostra o
    diff de/para e a cópia + assinatura + carimbo saem na MESMA transação
    da aresta (substituição de agendamento próprio é consentida no diff)."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_inicio(client, "M1", ["RAIZ_A"])
        assert _salvar(client, "M1", _ag_weekly()).status_code == 200
        # RAIZ_B entra na malha e é ligada depois
        assert client.post("/malhas/M1/pipelines",
                           json={"pipeline_name": "RAIZ_B"}).status_code == 200
        db.pipelines["RAIZ_B"]["dag_config_pendente"] = 0
        ini = next(nid for nid, n in db.nos.items() if n["tipo"] == "inicio")
        commits = db.commits
        r_dry = client.post("/malhas/M1/arestas", json={
            "origem": {"no": ini}, "destino": {"pipeline": "RAIZ_B"},
            "dry_run": True})
        assert r_dry.status_code == 200
        assert r_dry.json()["efeito"]["agendamentos"] == [
            {"pipeline": "RAIZ_B", "de": "diário 07:30",
             "para": "semanal (dom) 20:00 · virada 20:00"}]
        assert r_dry.json()["efeito"]["republicar"] == ["RAIZ_B"]
        assert db.commits == commits                 # dry_run não gravou
        r = _aresta(client, "M1", {"no": ini}, {"pipeline": "RAIZ_B"})
    assert r.status_code == 200
    assert r.json()["efeito"]["agendamentos"] == [
        {"pipeline": "RAIZ_B", "de": "diário 07:30",
         "para": "semanal (dom) 20:00 · virada 20:00"}]
    p = db.pipelines["RAIZ_B"]
    assert p["schedule_type"] == "weekly" and p["agenda_no"] == ini
    assert p["hora_virada"] == "20:00:00"
    assert p["dag_config_pendente"] == 1
    assert db.commits == commits + 1                 # aresta + cópia juntas


# ── desligar (Decisão 10) ────────────────────────────────────────────────────

def test_desligar_raiz_vira_on_demand_nunca_cron_velho(client, auth_editor):
    """E7/anti-D40: excluir a aresta Início → raiz desliga a raiz para
    'on_demand' + carimbo — o agendamento ANTIGO (diário 07:30) NUNCA volta
    (teste de ausência); o dry_run diz o efeito antes."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        ini = _monta_inicio(client, "M1", ["RAIZ_A", "RAIZ_B"])
        assert _salvar(client, "M1", _ag_weekly()).status_code == 200
        db.pipelines["RAIZ_A"]["dag_config_pendente"] = 0
        aid = next(a["id"] for a in db.arestas_no
                   if a["origem_no"] == ini
                   and a["destino_pipeline"] == "RAIZ_A")
        r_dry = client.delete(f"/malhas/M1/arestas/{aid}?dry_run=true")
        assert r_dry.status_code == 200
        assert r_dry.json()["efeito"]["agendamentos"] == [
            {"pipeline": "RAIZ_A",
             "de": "semanal (dom) 20:00 · virada 20:00",
             "para": "sob demanda"}]
        assert db.pipelines["RAIZ_A"]["agenda_no"] == ini   # dry_run não gravou
        r = client.delete(f"/malhas/M1/arestas/{aid}")
    assert r.status_code == 200
    p = db.pipelines["RAIZ_A"]
    assert p["schedule_type"] == "on_demand"     # nunca 'daily' de volta
    assert p["agenda_no"] is None
    assert p["dag_config_pendente"] == 1
    # a outra raiz segue intacta, assinada e agendada
    assert db.pipelines["RAIZ_B"]["schedule_type"] == "weekly"
    assert db.pipelines["RAIZ_B"]["agenda_no"] == ini


def test_excluir_inicio_desliga_todas_e_preserva_o_json(client, auth_editor):
    """Excluir o Início: TODAS as raízes assinadas viram on_demand na mesma
    transação (a FK agenda_no não deixa outra ordem) e o agendamento_json da
    MALHA fica — o nó é o plugue (Decisão 8); recriar não perde a config."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        ini = _monta_inicio(client, "M1", ["RAIZ_A", "RAIZ_B"])
        assert _salvar(client, "M1", _ag_weekly()).status_code == 200
        r_dry = client.delete(f"/malhas/M1/nos/{ini}?dry_run=true")
        assert r_dry.status_code == 200
        assert [i["pipeline"] for i in r_dry.json()["efeito"]["agendamentos"]] \
            == ["RAIZ_A", "RAIZ_B"]
        assert all(i["para"] == "sob demanda"
                   for i in r_dry.json()["efeito"]["agendamentos"])
        commits = db.commits
        r = client.delete(f"/malhas/M1/nos/{ini}")
    assert r.status_code == 200
    assert ini not in db.nos
    for nome in ("RAIZ_A", "RAIZ_B"):
        assert db.pipelines[nome]["schedule_type"] == "on_demand"
        assert db.pipelines[nome]["agenda_no"] is None
    assert db.malhas["M1"].get("agendamento_json")       # Decisão 8: fica
    assert db.commits == commits + 1


def test_delete_inicio_por_sql_direto_com_assinatura_estoura_a_fk(client, auth_editor):
    """§1.4 no MODELO (simulado como o banco garante): DELETE do nó Início
    por SQL direto com agenda_no pendurado falha ALTO — desligar as raízes
    antes é a única ordem possível."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        ini = _monta_inicio(client, "M1", ["RAIZ_A"])
        assert _salvar(client, "M1", _ag_weekly()).status_code == 200
    cur = db.cursor()
    cur.execute("DELETE FROM dbo.etl_malha_aresta "
                "WHERE origem_no = ? OR destino_no = ?", (ini, ini))
    with pytest.raises(RuntimeError, match="FK_pipe_agenda_no"):
        cur.execute("DELETE FROM dbo.etl_malha_no WHERE id = ?", (ini,))
    assert ini in db.nos


# ── GET do detalhe ───────────────────────────────────────────────────────────

def test_get_detalhe_traz_agendamento_resumo_e_agenda_no(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        ini = _monta_inicio(client, "M1", ["RAIZ_A"])
        assert _salvar(client, "M1", _ag_weekly()).status_code == 200
        body = client.get("/malhas/M1").json()
    assert body["agendamento"]["schedule_type"] == "weekly"
    assert body["agendamento"]["hora_virada"] == "20:00:00"
    assert body["agendamento_resumo"] == "semanal (dom) 20:00 · virada 20:00"
    membro = next(m for m in body["membros"] if m["pipeline_name"] == "RAIZ_A")
    assert membro["agenda_no"] == ini
    assert "agenda_contradicao" not in membro


def test_get_avisa_inicio_ligado_sem_agendamento(client, auth_editor):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        ini = _monta_inicio(client, "M1", ["RAIZ_A"])
        body = client.get("/malhas/M1").json()
    assert body["agendamento"] is None
    assert body["agendamento_resumo"] is None
    assert any(a["no"] == ini and a["nivel"] == "forte"
               and "ainda não tem agendamento" in a["mensagem"]
               for a in body["avisos"])


# ── degradação e rollback ────────────────────────────────────────────────────

def test_sem_colunas_de_agenda_503_e_gestos_como_na_f12(client, auth_editor):
    """075 aplicada pela metade (tabelas sim, colunas de agenda não): o POST
    do agendamento dá 503 instrutivo; a aresta Início→raiz volta a ser só
    desenho (F12) e o GET não tem a chave `agendamento`."""
    db = FakeDb(pipelines=_pipes(), com_agenda=False)
    with _patch_db(db):
        _monta_malha(client, "M1", ["RAIZ_A"])
        ini = _cria_no(client, "M1", "inicio")
        r_ag = _salvar(client, "M1", _ag_weekly())
        assert r_ag.status_code == 503
        assert "migration 075" in r_ag.json()["detail"]
        r_ar = _aresta(client, "M1", {"no": ini}, {"pipeline": "RAIZ_A"})
        assert r_ar.status_code == 200
        assert r_ar.json()["efeito"]["agendamentos"] == []
        body = client.get("/malhas/M1").json()
    assert "agendamento" not in body
    assert all("agenda_no" not in m for m in body["membros"])
    assert db.pipelines["RAIZ_A"]["agenda_no"] is None


def test_falha_no_meio_da_copia_rollback_total(client, auth_editor):
    """Grupo 4 do §13 aplicado à F13: a cópia falhando no meio desfaz TUDO —
    nem JSON na malha, nem raiz pela metade, nem commit."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta_inicio(client, "M1", ["RAIZ_A", "RAIZ_B"])
        antes = copy.deepcopy(db._estado())
        commits = db.commits
        db.falhar_copia = True
        r = _salvar(client, "M1", _ag_weekly())
        db.falhar_copia = False
    assert r.status_code == 500
    assert db._estado() == antes
    assert db.commits == commits
