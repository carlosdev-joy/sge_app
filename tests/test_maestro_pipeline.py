"""Maestro no NÍVEL DO PIPELINE e as perguntas conceituais (complemento da
spec docs/spec-maestro-parametros.md, "F5", 2026-09-10).

O que se prende:

  1. **O prompt ensina a herança** — o que o usuário pergunta: default do
     pipeline vale para toda etapa DataStage cujo job declara o nome, sem
     configurar nada nas etapas; a etapa sobrepõe; o valor é recalculado a cada
     disparo pela data de referência da corrida (exemplo mensal do dia 05);
     status `explicacao` para quem só quer entender.
  2. **Nível pipeline no prompt**: lista o que CADA etapa declara (ISX) e diz
     que a proposta vira default; no nível etapa nada mudou.
  3. **`parametros_declarados_pipeline`** percorre as etapas DataStage do
     pipeline (teto), degrada sem pipeline/etapas.
  4. **`avaliar` no pipeline** avisa QUAIS etapas herdam cada nome e quais
     ignoram; sem ISX em etapa nenhuma, avisa para conferir no Designer.
  5. **Rota**: `contexto.nivel` (padrão etapa; inválido → 422); no pipeline o
     `job_name` é ignorado, os declarados vêm por etapa e os defaults do banco
     não entram (o editor É a lista); a resposta ecoa `nivel`.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from services import caixa_ia, maestro  # noqa: E402

REF = date(2026, 3, 15)
DECL_PIPE = {"nivel": "pipeline", "jobs": [
    {"job_name": "JobA", "disponivel": True, "extracted_at": "2026-09-10 10:00",
     "itens": [{"name": "dat_inicio", "type": "date"}, {"name": "dat_fim", "type": "date"}]},
    {"job_name": "JobB", "disponivel": True, "extracted_at": None, "itens": [{"name": "dat_inicio", "type": "date"}]},
    {"job_name": "JobC", "disponivel": False, "extracted_at": None, "itens": []},
]}


def _proposta(*nomes):
    return {"status": "atendido", "cenario": "mensal_anterior", "params": [
        {"param_name": n, "param_type": "Date", "param_source": "data_referencia",
         "param_offset_meses": -1, "param_ancora": "inicio_mes" if i == 0 else "fim_mes"}
        for i, n in enumerate(nomes)]}


# ═══════════ 1. o prompt ensina a herança ════════════════════════════════════

def test_prompt_explica_heranca_referencia_e_exemplo_mensal():
    sp = maestro.system_prompt([], {"nivel": "etapa"})
    assert "HERDAM sem configurar nada nelas" in sp
    assert "A ETAPA sobrepõe o default pelo mesmo nome" in sp
    assert "DATA DE REFERÊNCIA da corrida" in sp and "não o relógio" in sp
    assert "só a origem data_execucao usa o relógio do worker" in sp
    assert "05/10/2026" in sp and "2026-09-01 e 2026-09-30" in sp and "05/11/2026" in sp
    assert "Reexecutar uma corrida antiga usa a referência DAQUELA corrida" in sp
    assert "NÃO exige republicar a DAG" in sp
    assert "Simular com a referência" in sp and "[DS] parâmetros:" in sp
    assert "dat_inicio ≠ Dat_Inicio" in sp
    assert '{"status": "explicacao"' in sp and "status explicacao, sem proposta" in sp


# ═══════════ 2. nível no prompt ══════════════════════════════════════════════

def test_prompt_no_nivel_pipeline_lista_o_que_cada_etapa_declara():
    sp = maestro.system_prompt([], {"nivel": "pipeline", "pipeline_name": "PIPE_VIDA", "declarados": DECL_PIPE,
                                    "editor": [], "referencia": "2026-03-15"})
    assert "## Onde o usuário está: cadastro do PIPELINE (defaults)" in sp
    assert "vira DEFAULT DO PIPELINE" in sp
    assert "- Etapa JobA declara: dat_inicio, dat_fim." in sp
    assert "- Etapa JobB declara: dat_inicio." in sp
    assert "- Etapa JobC: sem lineage ISX" in sp
    assert "diga QUAIS etapas o declaram" in sp
    assert "O editor do pipeline está vazio." in sp
    assert "cadastro da ETAPA" not in sp


def test_prompt_no_nivel_pipeline_sem_etapas_e_no_nivel_etapa_como_antes():
    sp = maestro.system_prompt([], {"nivel": "pipeline", "pipeline_name": None, "declarados": {"nivel": "pipeline", "jobs": []}})
    assert "ainda não tem etapas DataStage cadastradas" in sp
    sp = maestro.system_prompt([], {"pipeline_name": "P", "job_name": "J",
                                    "declarados": {"disponivel": True, "itens": [{"name": "pX", "type": "date"}]},
                                    "defaults": [{"param_name": "dat_inicio", "param_type": "Date", "param_source": "data_referencia"}]})
    assert "## Onde o usuário está: cadastro da ETAPA" in sp and "pX (date)" in sp
    assert "Defaults do pipeline (a etapa herda; cadastre na etapa só para sobrepor)" in sp
    assert "O editor desta etapa está vazio." in sp


# ═══════════ 3. declarados por etapa ═════════════════════════════════════════

class _Cur:
    def __init__(self, jobs=None):
        self.jobs = jobs or []
        self._rows = []

    def execute(self, sql, params=None):
        if "etl_pipeline_job" in sql:
            self._rows = [(j, "datastage") for j in self.jobs] + [("Shell1", "shell")]
        else:
            self._rows = []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


def test_parametros_declarados_pipeline_percorre_as_etapas_datastage(monkeypatch):
    from services import lineage_isx
    cabs = {"JobA": {"parameters_json": json.dumps([{"name": "dat_inicio", "type": "Date"}]), "status": "ok",
                     "extracted_at": "2026-09-10 10:00:00"},
            "JobB": None}
    monkeypatch.setattr(lineage_isx, "cabecalho", lambda cur, p, j: cabs.get(j))
    d = maestro.parametros_declarados_pipeline(_Cur(["JobB", "JobA"]), "PIPE_VIDA")
    assert d["nivel"] == "pipeline"
    assert [(j["job_name"], j["disponivel"]) for j in d["jobs"]] == [("JobA", True), ("JobB", False)]   # ordenado, sem a shell
    assert d["jobs"][0]["itens"] == [{"name": "dat_inicio", "type": "date"}]
    assert maestro.parametros_declarados_pipeline(_Cur(), None) == {"nivel": "pipeline", "jobs": [], "truncados": 0}
    muitos = [f"Job{i:02d}" for i in range(50)]
    monkeypatch.setattr(lineage_isx, "cabecalho", lambda cur, p, j: None)
    d = maestro.parametros_declarados_pipeline(_Cur(muitos), "P")
    assert len(d["jobs"]) == maestro.MAX_JOBS_PIPELINE and d["truncados"] == 20   # o teto é dito, não silencioso
    assert d["jobs"][0]["job_name"] == "Job00" and d["jobs"][-1]["job_name"] == "Job29"


def test_teto_de_etapas_aparece_no_prompt_e_nos_avisos():
    decl = {"nivel": "pipeline", "truncados": 3, "jobs": [
        {"job_name": "JobA", "disponivel": True, "extracted_at": None, "itens": [{"name": "dat_inicio", "type": "date"}]}]}
    sp = maestro.system_prompt([], {"nivel": "pipeline", "pipeline_name": "P", "declarados": decl})
    assert "E mais 3 etapa(s) DataStage não conferida(s) (teto de 30)" in sp
    r = maestro.avaliar(_proposta("pX"), REF, decl)
    assert "nenhuma etapa com lineage ISX declara 'pX' — confira o nome no Designer; o default seria ignorado por todas as conferidas" in r["avisos"]
    assert r["avisos"][-1] == "e mais 3 etapa(s) DataStage não conferida(s) (teto de 30)"


def test_avaliar_no_pipeline_avisa_tipo_divergente_e_cadastro_novo():
    p = _proposta("dat_inicio")
    p["params"][0]["param_type"] = "String"
    r = maestro.avaliar(p, REF, DECL_PIPE)
    assert "JobA declara 'dat_inicio' como Date; a proposta usa String" in r["avisos"]
    assert "JobB declara 'dat_inicio' como Date; a proposta usa String" in r["avisos"]
    r = maestro.avaliar(_proposta("dat_inicio"), REF, {"nivel": "pipeline", "jobs": [], "truncados": 0})
    assert r["status"] == "atendido" and any("ainda não tem etapas DataStage" in a for a in r["avisos"])


# ═══════════ 4. avaliar no pipeline ══════════════════════════════════════════

def test_avaliar_no_pipeline_diz_quem_herda_e_quem_ignora():
    r = maestro.avaliar(_proposta("dat_inicio", "dat_fim"), REF, DECL_PIPE, {"mensal_anterior"})
    assert r["status"] == "atendido" and [p["valor"] for p in r["previa"]] == ["2026-02-01", "2026-02-28"]
    assert r["avisos"] == [
        "'dat_inicio' vai para: JobA, JobB",
        "'dat_fim' vai para: JobA; ignorado por (não declara): JobB",
        "sem lineage ISX (não dá para saber se herdam): JobC",
    ]


def test_avaliar_no_pipeline_nome_que_ninguem_declara_e_sem_isx_nenhum():
    r = maestro.avaliar(_proposta("Dat_Inicio"), REF, DECL_PIPE)
    assert any("nenhuma etapa com lineage ISX declara 'Dat_Inicio'" in a for a in r["avisos"])
    sem_isx = {"nivel": "pipeline", "jobs": [{"job_name": "JobC", "disponivel": False, "itens": []}]}
    r = maestro.avaliar(_proposta("dat_inicio"), REF, sem_isx)
    assert r["status"] == "atendido" and r["avisos"] == [
        "nenhuma etapa deste pipeline tem lineage ISX: confira os nomes no Designer — só as etapas cujo job declarar o nome vão herdar"]
    r = maestro.avaliar(_proposta("dat_inicio"), REF, {"nivel": "pipeline", "jobs": []})
    assert r["status"] == "atendido" and len(r["avisos"]) == 1 and "ainda não tem etapas" in r["avisos"][0]


def test_avaliar_explicacao_sem_proposta():
    r = maestro.avaliar({"status": "explicacao", "params": [{"x": 1}]}, REF, DECL_PIPE)
    assert r == {"status": "explicacao", "cenario": None, "motivo": None, "params": None, "previa": None, "avisos": []}


# ═══════════ 5. rota ═════════════════════════════════════════════════════════

class _CurRota:
    def __init__(self):
        self._rows = []
        self.inseridos = []

    def execute(self, sql, params=None):
        s = sql.lower()
        params = tuple(params or ())
        if "etl_app_config" in s:
            self._rows = [("1",)] if params == (maestro.K_ENABLED,) else []
        elif "etl_maestro_cenario" in s:
            self._rows = [("mensal_anterior", "Mensal", "d", '{"params":[{"param_name":"<D>","param_type":"Date","param_source":"data_referencia"}],"exemplos":["x"]}')]
        elif "etl_pipeline_job" in s and "etl_pipeline_job_param" not in s:
            self._rows = [("JobA", "datastage"), ("JobB", "datastage")]
        elif "insert into dbo.etl_maestro_conversa" in s:
            self.inseridos.append(params); self._rows = []
        elif "information_schema.tables" in s:
            self._rows = [(1,)]
        elif "etl_pipeline_param" in s:
            self._rows = [("dat_x", "Date", None, "data_referencia", None, None, None, None)]
        else:
            self._rows = []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def close(self):
        pass


class _Conn:
    def __init__(self, cur):
        self._cur = cur

    def cursor(self):
        return self._cur

    def commit(self):
        pass

    def close(self):
        pass


@pytest.fixture
def ambiente(monkeypatch):
    from fastapi.testclient import TestClient
    from api.main import app
    from deps import get_current_user
    from services import lineage_isx
    app.dependency_overrides[get_current_user] = lambda: {"matricula": "U1", "perfil": "dev", "permissoes": ["tela_jobs"]}
    cur = _CurRota()
    chamadas = []

    async def _fake(cfg, system, mensagens):
        chamadas.append(system)
        return ("Entendi.\n```json\n" + json.dumps(_proposta("dat_inicio")) + "\n```", "m")
    monkeypatch.setattr(caixa_ia, "load_config", lambda c=None: {"provider": "anthropic", "api_key_enc": "x", "model": ""})
    monkeypatch.setattr(caixa_ia, "chat_conversa", _fake)
    monkeypatch.setattr(lineage_isx, "cabecalho", lambda c, p, j: {
        "parameters_json": json.dumps([{"name": "dat_inicio", "type": "Date"}]), "status": "ok", "extracted_at": None} if j == "JobA" else None)
    with patch("routers.maestro.get_db_conn", return_value=_Conn(cur)):
        yield TestClient(app), cur, chamadas
    app.dependency_overrides.pop(get_current_user, None)


def _corpo(**ctx):
    return {"conversa_id": "conv-0001", "mensagens": [{"role": "user", "content": "mensal"}],
            "contexto": {"pipeline_name": "PIPE_VIDA", "job_name": "JobA", "referencia": "2026-03-15", **ctx}}


def test_rota_nivel_pipeline(ambiente):
    cliente, cur, chamadas = ambiente
    d = cliente.post("/maestro/conversar", json=_corpo(nivel="pipeline")).json()
    assert d["status"] == "atendido" and d["nivel"] == "pipeline"
    assert d["avisos"] == ["'dat_inicio' vai para: JobA", "sem lineage ISX (não dá para saber se herdam): JobB"]
    assert "cadastro do PIPELINE" in chamadas[0] and "- Etapa JobA declara: dat_inicio." in chamadas[0]
    assert "Defaults do pipeline (a etapa herda" not in chamadas[0]      # o editor É a lista de defaults
    assert cur.inseridos[0][3] is None                                    # job_name não vai no registro


def test_rota_nivel_padrao_etapa_e_invalido(ambiente):
    cliente, cur, chamadas = ambiente
    d = cliente.post("/maestro/conversar", json=_corpo()).json()
    assert d["nivel"] == "etapa" and "cadastro da ETAPA" in chamadas[0] and cur.inseridos[0][3] == "JobA"
    r = cliente.post("/maestro/conversar", json=_corpo(nivel="malha"))
    assert r.status_code == 422 and any("contexto.nivel" in e for e in r.json()["detail"]["errors"])
