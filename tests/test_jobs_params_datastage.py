"""
Parâmetros de etapa DataStage na API (F1 da spec docs/spec-parametros-job-datastage.md).

O que estes testes prendem:

  1. **Validação por tipo DataStage** (services/job_params.normalizar_lista):
     nome com um ponto (Parameter Set), tipos do DataStage, origem × tipo,
     campos de cálculo só com origem de data, valor fixo por tipo, duplicata
     por CAIXA EXATA (o DataStage distingue `pData` de `pdata`).
  2. **Encrypted nunca em claro** (routers/jobs._preparar_params_ds e
     _serializar_param): o banco recebe token Fernet, o GET devolve `***` +
     tem_valor, e `***` no payload preserva o token gravado — sem token gravado
     é erro, não silêncio.
  3. **A prévia** (POST /pipelines/jobs/params/preview): o caso mensal da spec
     e a borda 31/03, com descrição; item inválido vai para `erros` sem
     derrubar os válidos.

Helpers puros importados via fixture (padrão de test_jobs_python_node.py);
endpoint via TestClient com auth em dependency_overrides (padrão de
test_admin_dags_inventario.py). Nada toca banco.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")

from services import job_params as jp  # noqa: E402


@pytest.fixture(scope="module")
def J():
    import routers.jobs as _j
    return _j


@pytest.fixture
def chave_fernet(monkeypatch):
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("ORQUESTRA_CONN_KEY", key)
    return key


def _item(**kw):
    base = {"param_name": "pData", "param_type": "String", "param_source": "fixo",
            "param_value": "x"}
    base.update(kw)
    return base


# ═══════════ 1. validação ═══════════════════════════════════════════════════

def test_fixo_string_valido():
    validos, erros = jp.normalizar_lista([_item()])
    assert erros == []
    assert validos[0] == {
        "param_name": "pData", "param_type": "String", "param_source": "fixo",
        "param_value": "x", "param_offset_meses": None, "param_ancora": None,
        "param_offset_dias": None, "param_formato": None,
    }


@pytest.mark.parametrize("nome", ["PSet.pData", "p_1", "_x", "a.b"])
def test_nome_com_um_ponto_e_parameter_set(nome):
    validos, erros = jp.normalizar_lista([_item(param_name=nome)])
    assert erros == [] and validos[0]["param_name"] == nome


@pytest.mark.parametrize("nome", ["1abc", "a b", "a.b.c", "a-b", "p;rm", "", "@p"])
def test_nome_invalido(nome):
    _, erros = jp.normalizar_lista([_item(param_name=nome, param_value="v")])
    assert erros and "inválido" in erros[0]


def test_tipo_invalido_lista_os_aceitos():
    _, erros = jp.normalizar_lista([_item(param_type="VARCHAR")])
    assert erros and "Encrypted" in erros[0] and "String" in erros[0]


def test_origem_invalida():
    _, erros = jp.normalizar_lista([_item(param_source="hoje")])
    assert erros and "origem 'hoje' inválida" in erros[0]


def test_origem_e_obrigatoria_sem_default():
    """A tela de antes da F3 reenvia só nome/tipo/valor: sem origem NÃO vira
    'fixo' em silêncio (rebaixaria um parâmetro de data) — é 422 explícito."""
    item = {"param_name": "pData", "param_type": "String", "param_value": ""}
    _, erros = jp.normalizar_lista([item])
    assert erros == ["parâmetro #1 'pData': origem obrigatória — use uma de "
                     + ", ".join(jp.DS_PARAM_SOURCES)]
    _, erros = jp.normalizar_lista([_item(param_source="")])
    assert erros and "origem obrigatória" in erros[0]


def test_nome_e_formato_respeitam_a_largura_da_sp():
    """VARCHAR(128)/VARCHAR(40) na SP truncam em silêncio — a API recusa antes."""
    _, erros = jp.normalizar_lista([_item(param_name="p" * 129)])
    assert erros and "máximo 128" in erros[0]
    validos, erros = jp.normalizar_lista([_item(param_name="p" * 128)])
    assert erros == [] and len(validos[0]["param_name"]) == 128
    _, erros = jp.normalizar_lista([_item(param_source="data_referencia",
                                          param_formato="%Y" + "-" * 39)])
    assert erros and "máximo 40" in erros[0]
    _, erros = jp.normalizar_lista([_item(param_source="data_referencia",
                                          param_formato="%Y" + "-" * 38)])
    assert erros == []


def test_duplicata_por_caixa_exata():
    # pData e pdata NÃO são duplicata (DataStage é case-sensitive)...
    validos, erros = jp.normalizar_lista([_item(param_name="pData"), _item(param_name="pdata")])
    assert erros == [] and len(validos) == 2
    # ...mas pData duas vezes é.
    _, erros = jp.normalizar_lista([_item(param_name="pData"), _item(param_name="pData")])
    assert erros == ["parâmetro #2 'pData': duplicado"]


def test_linha_vazia_e_ignorada():
    validos, erros = jp.normalizar_lista([{"param_name": "", "param_value": ""}, _item()])
    assert erros == [] and len(validos) == 1


def test_lista_nao_lista():
    assert jp.normalizar_lista("x") == ([], ["params deve ser uma lista"])
    assert jp.normalizar_lista(None) == ([], [])


@pytest.mark.parametrize("tipo, valor, ok", [
    ("Integer", "42", True), ("Integer", "-7", True), ("Integer", "4.2", False), ("Integer", "abc", False),
    ("Float", "3.14", True), ("Float", "-1", True), ("Float", "1,5", False),
    ("Date", "2026-09-09", True), ("Date", "09/09/2026", False),
    ("Time", "23:59:00", True), ("Time", "23:59", False),
    ("Timestamp", "2026-09-09 10:00:00", True), ("Timestamp", "2026-09-09T10:00:00", False),
    ("Pathname", "/dados/entrada", True), ("Pathname", "~/dados", False),
    ("Pathname", "/com espaco", False), ("Pathname", "relativo/x", False),
    ("List", "A", True), ("String", "", True), ("Integer", "", False),
])
def test_valor_fixo_por_tipo(tipo, valor, ok):
    _, erros = jp.normalizar_lista([_item(param_type=tipo, param_value=valor)])
    assert (erros == []) is ok, erros


def test_valor_fixo_sem_quebra_de_linha():
    _, erros = jp.normalizar_lista([_item(param_value="a\nb")])
    assert erros and "quebra de linha" in erros[0]


def test_origem_de_data_normaliza_calculo():
    validos, erros = jp.normalizar_lista([_item(
        param_type="Date", param_source="data_referencia", param_value="ignorado",
        param_offset_meses="-1", param_ancora="fim_mes", param_offset_dias="",
        param_formato="%Y%m%d")])
    assert erros == []
    v = validos[0]
    assert v["param_value"] is None            # nasce em runtime
    assert v["param_offset_meses"] == -1 and v["param_ancora"] == "fim_mes"
    assert v["param_offset_dias"] is None and v["param_formato"] == "%Y%m%d"


@pytest.mark.parametrize("tipo", ["Integer", "Float", "Time", "Pathname", "List", "Encrypted"])
def test_origem_de_data_so_com_tipo_de_data_ou_string(tipo):
    _, erros = jp.normalizar_lista([_item(param_type=tipo, param_source="data_logica")])
    assert erros and "origem de data só com tipo" in erros[0]


def test_ancora_sem_origem_de_data_e_erro():
    _, erros = jp.normalizar_lista([_item(param_ancora="fim_mes")])
    assert erros and "só vale com origem de data" in erros[0]


def test_meses_e_dias_fora_da_faixa_ou_nao_inteiros():
    _, e1 = jp.normalizar_lista([_item(param_source="data_referencia", param_offset_meses="121")])
    _, e2 = jp.normalizar_lista([_item(param_source="data_referencia", param_offset_dias="x")])
    assert e1 and "fora da faixa" in e1[0]
    assert e2 and "inteiro" in e2[0]


@pytest.mark.parametrize("formato", ["%Y-%m-%d", "%Y%m%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%y.%m"])
def test_formato_permitido(formato):
    _, erros = jp.normalizar_lista([_item(param_source="data_referencia", param_formato=formato)])
    assert erros == []


@pytest.mark.parametrize("formato", ["%", "%Y%", "%s", "%A", "abc", "%Y %B", "%Y;rm"])
def test_formato_fora_da_allowlist(formato):
    _, erros = jp.normalizar_lista([_item(param_source="data_referencia", param_formato=formato)])
    assert erros and "formato" in erros[0]


def test_run_id_so_string_e_sem_valor():
    validos, erros = jp.normalizar_lista([_item(param_source="run_id", param_value="lixo")])
    assert erros == [] and validos[0]["param_value"] is None
    _, erros = jp.normalizar_lista([_item(param_type="Date", param_source="run_id")])
    assert erros and "run_id só com tipo String" in erros[0]


# ═══════════ 2. Encrypted nunca em claro ════════════════════════════════════

def test_encrypted_cifra_e_nao_guarda_em_claro(J, chave_fernet):
    from services.conn_crypto import decrypt_password
    linhas, erros = J._preparar_params_ds(
        [_item(param_name="pSenha", param_type="Encrypted", param_value="segredo!")], {})
    assert erros == [] and len(linhas) == 1
    token = linhas[0]["param_value"]
    assert token != "segredo!" and "segredo" not in token
    assert decrypt_password(token) == "segredo!"
    assert linhas[0]["param_order"] == 0


def test_encrypted_mascara_preserva_token_gravado(J, chave_fernet):
    linhas, erros = J._preparar_params_ds(
        [_item(param_name="pSenha", param_type="Encrypted", param_value="***")],
        {"pSenha": "token-gravado"})
    assert erros == [] and linhas[0]["param_value"] == "token-gravado"


def test_encrypted_mascara_sem_token_gravado_e_erro(J, chave_fernet):
    linhas, erros = J._preparar_params_ds(
        [_item(param_name="pSenha", param_type="Encrypted", param_value="***")], {})
    assert linhas == [] and erros and "Encrypted sem valor gravado" in erros[0]


def test_encrypted_sem_chave_configurada_e_500_claro(J, monkeypatch):
    from fastapi import HTTPException
    monkeypatch.delenv("ORQUESTRA_CONN_KEY", raising=False)
    with pytest.raises(HTTPException) as exc:
        J._preparar_params_ds(
            [_item(param_name="pSenha", param_type="Encrypted", param_value="s")], {})
    assert exc.value.status_code == 500 and "ORQUESTRA_CONN_KEY" in str(exc.value.detail)


def test_ordem_segue_a_lista(J, chave_fernet):
    linhas, erros = J._preparar_params_ds(
        [_item(param_name="b"), {"param_name": "", "param_value": ""}, _item(param_name="a")], {})
    assert erros == [] and [(p["param_name"], p["param_order"]) for p in linhas] == [("b", 0), ("a", 1)]


def test_serializar_mascara_encrypted_e_degrada_sem_107(J):
    # Linha COM as colunas da 107 (9 posições)
    r = ("pSenha", "Encrypted", "token", 0, "fixo", None, None, None, None)
    out = J._serializar_param(r, True)
    assert out["param_value"] == "***" and out["tem_valor"] is True
    # Encrypted sem valor → vazio, tem_valor False
    out = J._serializar_param(("pSenha", "Encrypted", None, 0, "fixo", None, None, None, None), True)
    assert out["param_value"] == "" and out["tem_valor"] is False
    # Origem de data com cálculo
    out = J._serializar_param(("pFim", "Date", None, 1, "data_referencia", -1, "fim_mes", None, "%Y%m%d"), True)
    assert out == {"param_name": "pFim", "param_type": "Date", "param_value": None, "param_order": 1,
                   "param_source": "data_referencia", "param_offset_meses": -1, "param_ancora": "fim_mes",
                   "param_offset_dias": None, "param_formato": "%Y%m%d"}
    # SEM a 107 (4 posições): storedproc continua como antes + campos degradados
    out = J._serializar_param(("@p", "VARCHAR", "v", 0), False)
    assert out["param_value"] == "v" and out["param_source"] == "fixo" and out["param_ancora"] is None
    assert "tem_valor" not in out


# ═══════════ 3. a prévia ════════════════════════════════════════════════════

@pytest.fixture
def cliente():
    from fastapi.testclient import TestClient
    from api.main import app
    from deps import get_current_user
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "U1", "perfil": "desenvolvedor", "permissoes": ["tela_jobs"]}
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)


def test_preview_caso_mensal_da_spec(cliente):
    r = cliente.post("/pipelines/jobs/params/preview", json={
        "referencia": "2026-09-09",
        "itens": [
            {"param_name": "pDataIni", "param_type": "Date", "param_source": "data_referencia",
             "param_offset_meses": -1, "param_ancora": "inicio_mes"},
            {"param_name": "pDataFim", "param_type": "Date", "param_source": "data_referencia",
             "param_offset_meses": -1, "param_ancora": "fim_mes"},
            {"param_name": "pAmb", "param_type": "String", "param_source": "fixo", "param_value": "PRD"},
            {"param_name": "pSenha", "param_type": "Encrypted", "param_source": "fixo", "param_value": "s"},
            {"param_name": "pRun", "param_type": "String", "param_source": "run_id"},
        ]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["referencia"] == "2026-09-09" and d["erros"] == []
    por_nome = {i["param_name"]: i for i in d["itens"]}
    assert por_nome["pDataIni"]["valor"] == "2026-08-01"
    assert por_nome["pDataIni"]["descricao"] == "referência 2026-09-09 → -1 mês → início do mês → 2026-08-01"
    assert por_nome["pDataFim"]["valor"] == "2026-08-31"
    assert por_nome["pAmb"] == {"param_name": "pAmb", "valor": "PRD", "descricao": "fixo"}
    assert por_nome["pSenha"]["valor"] == "***" and "s" != por_nome["pSenha"]["valor"]
    assert por_nome["pRun"]["valor"] == "<run_id do Airflow>"


def test_preview_borda_31_de_marco(cliente):
    r = cliente.post("/pipelines/jobs/params/preview", json={
        "referencia": "2026-03-31",
        "itens": [{"param_name": "p", "param_type": "String", "param_source": "data_referencia",
                   "param_offset_meses": -1}]})
    assert r.json()["itens"][0]["valor"] == "2026-02-28"
    r = cliente.post("/pipelines/jobs/params/preview", json={
        "referencia": "2024-03-15",
        "itens": [{"param_name": "p", "param_type": "String", "param_source": "data_referencia",
                   "param_offset_meses": -1, "param_ancora": "fim_mes"}]})
    assert r.json()["itens"][0]["valor"] == "2024-02-29"


def test_preview_item_invalido_nao_derruba_os_validos(cliente):
    r = cliente.post("/pipelines/jobs/params/preview", json={
        "referencia": "2026-09-09",
        "itens": [{"param_name": "ok", "param_type": "String", "param_source": "fixo", "param_value": "1"},
                  {"param_name": "ruim", "param_type": "Integer", "param_source": "fixo", "param_value": "x"}]})
    assert r.status_code == 200
    d = r.json()
    assert [i["param_name"] for i in d["itens"]] == ["ok"]
    assert d["erros"] and "'ruim'" in d["erros"][0]


def test_preview_borda_do_calendario_vira_erro_do_item_nao_500(cliente):
    r = cliente.post("/pipelines/jobs/params/preview", json={
        "referencia": "9999-12-31",
        "itens": [{"param_name": "pFora", "param_type": "String", "param_source": "data_referencia",
                   "param_offset_meses": 1},
                  {"param_name": "pOk", "param_type": "String", "param_source": "data_referencia",
                   "param_ancora": "inicio_ano"}]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert [i["param_name"] for i in d["itens"]] == ["pOk"]
    assert d["itens"][0]["valor"] == "9999-01-01"
    assert d["erros"] and "'pFora'" in d["erros"][0] and "fora do calendário" in d["erros"][0]


def test_resolver_preview_devolve_tupla_e_isola_o_item_ruim():
    from datetime import date
    validos, _ = jp.normalizar_lista([
        _item(param_name="a", param_source="data_referencia", param_offset_dias=3660),
        _item(param_name="b"),
    ])
    valores, erros = jp.resolver_preview(date(9999, 12, 1), validos)
    assert [v["param_name"] for v in valores] == ["b"] and len(erros) == 1


def test_preview_referencia_invalida_e_422(cliente):
    r = cliente.post("/pipelines/jobs/params/preview", json={"referencia": "31/03/2026", "itens": []})
    assert r.status_code == 422


def test_preview_sem_referencia_usa_hoje(cliente):
    import datetime as _dt
    r = cliente.post("/pipelines/jobs/params/preview", json={"itens": []})
    assert r.status_code == 200 and r.json()["referencia"] == _dt.date.today().isoformat()
