"""
POST /execucoes/rerun × sobreposição de parâmetros (F5 da spec
docs/spec-parametros-job-datastage.md) — a ROTA, não o serviço.

O que se prende (o buraco que a revisão adversarial apontou):
  1. `parametros` sem a corrida identificada → 422 `corrida_nao_identificada`,
     nada gravado, nada limpo no Airflow;
  2. com a corrida → valida e GRAVA ANTES do clear; a resposta traz
     `parametros_sobrepostos` e a auditoria (INSERT em etl_pipeline_audit) leva
     os nomes;
  3. clear recusado (DAG pausada → 409) → a sobreposição gravada é DESFEITA;
  4. validação com erro → 422 com `detail.errors`, nada gravado, nada limpo;
  5. rerun SEM parâmetros numa corrida conhecida → a sobreposição de um rerun
     anterior é apagada ANTES do clear (o gesto novo é o que vale).

Reusa o banco e o Airflow de mentira de tests/test_rerun_etapa_f4.py; o
serviço rerun_params é trocado por dublês que registram a ORDEM dos eventos
junto com o POST do clear.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from tests.test_rerun_etapa_f4 import _ClientFake, _DbRerun, _corrida, _RUN_A  # noqa: E402
from deps import PERM_EXECUTAR, get_current_user  # noqa: E402


@pytest.fixture
def cliente(client, app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor",
        "permissoes": [PERM_EXECUTAR, "tela_malha"],
    }
    yield client
    app.dependency_overrides.pop(get_current_user, None)


class _AirflowRegistrando(_ClientFake):
    """O clear entra na MESMA linha do tempo dos dublês do serviço."""

    def __init__(self, eventos, **kw):
        super().__init__(**kw)
        self.eventos = eventos

    async def post(self, url, json=None):
        self.eventos.append(("clear", url))
        return await super().post(url, json=json)


@pytest.fixture
def servico(monkeypatch):
    """Dublês de rerun_params que registram a ordem; `erros` força o 422."""
    import routers.execucoes as E
    eventos: list = []
    estado = {"erros": []}

    def validar(cur, pipeline, raw):
        eventos.append(("validar", pipeline, [r["param_name"] for r in raw]))
        if estado["erros"]:
            return [], list(estado["erros"])
        return [{"job_name": "etapa_x", "param_name": r["param_name"], "param_value": r["param_value"]}
                for r in raw], []

    def gravar(cur, pipeline, dag_run_id, linhas, usuario):
        eventos.append(("gravar", pipeline, dag_run_id, [p["param_name"] for p in linhas], usuario))

    def apagar(cur, pipeline, dag_run_id):
        eventos.append(("apagar", pipeline, dag_run_id))

    monkeypatch.setattr(E.rerun_params, "validar_overrides", validar)
    monkeypatch.setattr(E.rerun_params, "gravar_overrides", gravar)
    monkeypatch.setattr(E.rerun_params, "apagar_overrides", apagar)
    return eventos, estado


def _post(cliente, db, body, af):
    with patch("routers.execucoes.get_db_conn", return_value=db), \
         patch("routers.execucoes.get_airflow_client", return_value=af):
        return cliente.post("/execucoes/rerun", json=body)


def _corpo(**extra):
    return {"pipeline_name": "DEV_F10_A", "task_id": "etapa_x", "data_referencia": "2026-08-03", **extra}


def test_parametros_sem_corrida_identificada_e_422_sem_tocar_em_nada(cliente, servico):
    eventos, _ = servico
    db = _DbRerun(corridas=[_corrida(_RUN_A)])
    af = _AirflowRegistrando(eventos)
    # só execution_id (caminho histórico): o run_id nasceria dentro do clear
    r = _post(cliente, db, {"pipeline_name": "DEV_F10_A", "task_id": "etapa_x",
                            "execution_id": "20260803T120000",
                            "parametros": [{"job_name": "etapa_x", "param_name": "pData", "param_value": "20260901"}]}, af)
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["erro"] == "corrida_nao_identificada"
    assert eventos == [] and af.posts == []


def test_grava_antes_do_clear_e_responde_e_audita_os_nomes(cliente, servico):
    eventos, _ = servico
    db = _DbRerun(corridas=[_corrida(_RUN_A)])
    af = _AirflowRegistrando(eventos)
    r = _post(cliente, db, _corpo(parametros=[
        {"job_name": "etapa_x", "param_name": "pData", "param_value": "20260901"}]), af)
    assert r.status_code == 200, r.text
    tipos = [e[0] for e in eventos]
    assert tipos == ["validar", "gravar", "clear"], eventos          # gravado ANTES do clear
    assert eventos[1][2] == _RUN_A and eventos[1][3] == ["pData"] and eventos[1][4] == "DEV1"
    assert r.json()["parametros_sobrepostos"] == ["etapa_x.pData"]
    auditorias = [p for s, p in db.escritas if s.startswith("INSERT INTO dbo.etl_pipeline_audit")]
    assert auditorias, "auditoria do rerun não gravada"
    depois = json.loads(auditorias[-1][4])
    assert depois["parametros_sobrepostos"] == ["etapa_x.pData"]
    assert "20260901" not in auditorias[-1][4]                       # nomes, nunca valores


def test_clear_recusado_desfaz_a_sobreposicao(cliente, servico):
    eventos, _ = servico
    db = _DbRerun(corridas=[_corrida(_RUN_A)])
    af = _AirflowRegistrando(eventos, is_paused=True)               # 409: DAG pausada
    r = _post(cliente, db, _corpo(parametros=[
        {"job_name": "etapa_x", "param_name": "pData", "param_value": "20260901"}]), af)
    assert r.status_code == 409, r.text
    assert [e[0] for e in eventos] == ["validar", "gravar", "apagar"]
    assert eventos[2][2] == _RUN_A
    assert af.posts == []


def test_validacao_com_erro_e_422_estruturado_sem_gravar_nem_limpar(cliente, servico):
    eventos, estado = servico
    estado["erros"] = ["etapa_x: 'pSenha' é Encrypted — não pode ser sobreposto na reexecução"]
    db = _DbRerun(corridas=[_corrida(_RUN_A)])
    af = _AirflowRegistrando(eventos)
    r = _post(cliente, db, _corpo(parametros=[
        {"job_name": "etapa_x", "param_name": "pSenha", "param_value": "x"}]), af)
    assert r.status_code == 422, r.text
    det = r.json()["detail"]
    assert det["errors"] == estado["erros"] and "Encrypted" in det["mensagem"]
    assert [e[0] for e in eventos] == ["validar"] and af.posts == []


def test_rerun_sem_parametros_apaga_a_sobreposicao_anterior_antes_do_clear(cliente, servico):
    """O gesto novo é o que vale: um rerun 'limpo' não pode reaplicar o valor
    de um rerun anterior da mesma corrida (achado 1 da revisão da F5)."""
    eventos, _ = servico
    db = _DbRerun(corridas=[_corrida(_RUN_A)])
    af = _AirflowRegistrando(eventos)
    r = _post(cliente, db, _corpo(), af)
    assert r.status_code == 200, r.text
    assert [e[0] for e in eventos] == ["apagar", "clear"]
    assert eventos[0][2] == _RUN_A
    assert r.json()["parametros_sobrepostos"] == []
