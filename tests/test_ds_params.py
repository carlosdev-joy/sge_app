"""
Runtime dos parâmetros DataStage (dags/utils/ds_params.py) — F2 da spec
docs/spec-parametros-job-datastage.md. Funções puras: nada de Airflow, nada de
banco (carregar_etapa recebe um dublê de hook).

O que se prende aqui:
  · parse_lparams lê o que o job declara (simples e PSet.Param), ignora "Status code";
  · mesclar segue o §4: pipeline só declarado (resto ignorado e listado), etapa
    não declarada = ParamError com a lista do job, override = fixo/rerun;
  · resolver: fixo, run_id, origem de data com cálculo, Encrypted decifrado e
    MARCADO; origem de data sem base = ParamError; borda de calendário = ParamError;
  · o rastro (linha de log, JSON, args exibidos) NUNCA carrega o valor Encrypted;
  · montar_args quota só quando precisa (shlex) e preserva valor com espaço/aspa;
  · carregar_etapa: sem a 107 devolve vazio com aviso; outro erro propaga.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "dags"))
from utils import ds_params as dp  # noqa: E402

REF = date(2026, 9, 9)


def _linha(nome, tipo="String", origem="fixo", valor=None, meses=None, ancora=None,
           dias=None, formato=None):
    return {"param_name": nome, "param_type": tipo, "param_value": valor,
            "param_source": origem, "param_offset_meses": meses, "param_ancora": ancora,
            "param_offset_dias": dias, "param_formato": formato}


# ── parse_lparams ────────────────────────────────────────────────────────────

def test_parse_lparams_simples_e_parameter_set():
    saida = "pDataIni\npDataFim\nPSet\nPSet.pAmb\n\nStatus code = 0\n"
    assert dp.parse_lparams(saida) == {"pDataIni", "pDataFim", "PSet", "PSet.pAmb"}


def test_parse_lparams_vazio():
    assert dp.parse_lparams("") == set()
    assert dp.parse_lparams("Status code = 0") == set()


# ── mesclar ──────────────────────────────────────────────────────────────────

def test_mesclar_etapa_declarada():
    itens, ignorados = dp.mesclar([_linha("pA", valor="1")], {"pA", "pB"})
    assert ignorados == []
    assert [(i["param_name"], i["fonte"]) for i in itens] == [("pA", "etapa")]


def test_mesclar_etapa_nao_declarada_e_erro_com_a_lista_do_job():
    with pytest.raises(dp.ParamError) as e:
        dp.mesclar([_linha("pdata", valor="1")], {"pData", "pOutro"})
    msg = str(e.value)
    assert "NÃO declara" in msg and "pdata" in msg
    assert "pData, pOutro" in msg           # o que o job declara, ordenado
    assert "maiúsculas de minúsculas" in msg


def test_mesclar_pipeline_so_o_declarado_e_etapa_sobrepoe():
    pipe = [_linha("pAmb", valor="PRD"), _linha("pFora", valor="x")]
    etapa = [_linha("pAmb", valor="HML")]
    itens, ignorados = dp.mesclar(etapa, {"pAmb"}, pipeline=pipe)
    assert ignorados == ["pFora"]
    assert len(itens) == 1
    assert itens[0]["param_value"] == "HML" and itens[0]["fonte"] == "etapa"


def test_mesclar_pipeline_sem_etapa_mantem_fonte_pipeline():
    itens, _ = dp.mesclar([], {"pAmb"}, pipeline=[_linha("pAmb", valor="PRD")])
    assert itens[0]["fonte"] == "pipeline" and itens[0]["param_value"] == "PRD"


def test_mesclar_override_vira_fixo_rerun():
    etapa = [_linha("pData", tipo="Date", origem="data_referencia", meses=-1, ancora="fim_mes")]
    itens, _ = dp.mesclar(etapa, {"pData"}, overrides=[{"param_name": "pData", "param_value": "2026-09-01"}])
    it = itens[0]
    assert it["fonte"] == "rerun" and it["param_source"] == "fixo"
    assert it["param_value"] == "2026-09-01" and it["param_ancora"] is None
    assert it["param_type"] == "Date"        # o tipo da linha original sobrevive


def test_mesclar_override_de_nome_nao_declarado_e_erro():
    with pytest.raises(dp.ParamError) as e:
        dp.mesclar([], {"pA"}, overrides=[{"param_name": "pZ", "param_value": "1"}])
    assert "sobreposição do rerun cita 'pZ'" in str(e.value)


def test_mesclar_override_de_nome_declarado_mas_nao_cadastrado_entra_como_string():
    itens, _ = dp.mesclar([], {"pA"}, overrides=[{"param_name": "pA", "param_value": "1"}])
    assert itens[0]["param_type"] == "String" and itens[0]["fonte"] == "rerun"


# ── resolver ─────────────────────────────────────────────────────────────────

def test_resolver_caso_mensal_da_spec():
    itens = [
        _linha("pDataIni", "Date", "data_referencia", meses=-1, ancora="inicio_mes"),
        _linha("pDataFim", "Date", "data_referencia", meses=-1, ancora="fim_mes"),
        _linha("pD1", "String", "data_logica", dias=-1, formato="%Y%m%d"),
        _linha("pAmb", valor="PRD"),
        _linha("pRun", origem="run_id"),
    ]
    for it in itens:
        it["fonte"] = "etapa"
    out = dp.resolver(itens, {"data_referencia": REF, "data_logica": date(2026, 9, 8)},
                      "manual__2026-09-09T06:00:00+00:00")
    por = {p["name"]: p for p in out}
    assert por["pDataIni"]["valor"] == "2026-08-01"
    assert por["pDataIni"]["descricao"] == "referência 2026-09-09 → -1 mês → início do mês → 2026-08-01"
    assert por["pDataFim"]["valor"] == "2026-08-31"
    assert por["pD1"]["valor"] == "20260907"
    assert por["pD1"]["descricao"] == "data lógica 2026-09-08 → -1 dia → 20260907"
    assert por["pAmb"] == {"name": "pAmb", "valor": "PRD", "fonte": "etapa", "descricao": "fixo", "mascarado": False}
    assert por["pRun"]["valor"] == "manual__2026-09-09T06:00:00+00:00"
    assert all(p["mascarado"] is False for p in out)


def test_resolver_origem_de_data_sem_base_e_erro():
    with pytest.raises(dp.ParamError) as e:
        dp.resolver([_linha("p", origem="data_referencia")], {}, "r")
    assert "origem data_referencia indisponível" in str(e.value)


def test_resolver_borda_de_calendario_e_erro_nao_500():
    with pytest.raises(dp.ParamError) as e:
        dp.resolver([_linha("p", origem="data_referencia", meses=1)], {"data_referencia": date(9999, 12, 31)}, "r")
    assert "fora do calendário" in str(e.value)


def test_resolver_encrypted_decifra_e_marca(monkeypatch):
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    monkeypatch.setenv("ORQUESTRA_CONN_KEY", key.decode())
    token = Fernet(key).encrypt(b"segredo!").decode()
    out = dp.resolver([_linha("pSenha", "Encrypted", valor=token)], {}, "r")
    assert out[0]["valor"] == "segredo!" and out[0]["mascarado"] is True
    assert out[0]["descricao"] == "fixo (Encrypted)"


def test_resolver_encrypted_sem_chave_no_worker_e_erro_claro(monkeypatch):
    monkeypatch.delenv("ORQUESTRA_CONN_KEY", raising=False)
    with pytest.raises(dp.ParamError) as e:
        dp.resolver([_linha("pSenha", "Encrypted", valor="token")], {}, "r")
    assert "ORQUESTRA_CONN_KEY não configurada no worker" in str(e.value)


def test_resolver_encrypted_com_chave_errada_e_erro_claro(monkeypatch):
    from cryptography.fernet import Fernet
    token = Fernet(Fernet.generate_key()).encrypt(b"x").decode()
    monkeypatch.setenv("ORQUESTRA_CONN_KEY", Fernet.generate_key().decode())
    with pytest.raises(dp.ParamError) as e:
        dp.resolver([_linha("pSenha", "Encrypted", valor=token)], {}, "r")
    assert "ilegível" in str(e.value) and "x" != str(e.value)


def test_resolver_encrypted_sem_valor_gravado_e_erro():
    with pytest.raises(dp.ParamError) as e:
        dp.resolver([_linha("pSenha", "Encrypted", valor="")], {}, "r")
    assert "Encrypted sem valor gravado" in str(e.value)


def test_resolver_fixo_none_vira_vazio():
    out = dp.resolver([_linha("p", valor=None)], {}, "r")
    assert out[0]["valor"] == ""


# ── rastro: nada de Encrypted em claro ───────────────────────────────────────

def _lista_com_segredo():
    return [{"name": "pData", "valor": "2026-08-31", "fonte": "etapa",
             "descricao": "referência 2026-09-09 → -1 mês → fim do mês → 2026-08-31", "mascarado": False},
            {"name": "pSenha", "valor": "segredo!", "fonte": "etapa", "descricao": "fixo (Encrypted)",
             "mascarado": True}]


def test_montar_args_real_e_exibido():
    lista = _lista_com_segredo()
    # `!` não é seguro para o shell → o par inteiro ganha aspas (shlex)
    assert dp.montar_args(lista) == ["-param", "pData=2026-08-31", "-param", "'pSenha=segredo!'"]
    # `*` também não é seguro → a versão exibida sai quotada, mas sem o segredo
    assert dp.montar_args(lista, exibir=True) == ["-param", "pData=2026-08-31", "-param", "'pSenha=***'"]


@pytest.mark.parametrize("valor, esperado", [
    ("2026-08-31", "p=2026-08-31"),                 # sem aspas quando não precisa
    ("com espaco", "'p=com espaco'"),
    ("a'b", "'p=a'\"'\"'b'"),                       # aspa simples embutida (shlex)
    ("$HOME;rm -rf /", "'p=$HOME;rm -rf /'"),       # metacaracteres neutralizados
    ("", "p="),
])
def test_montar_args_quota_pelo_shlex(valor, esperado):
    assert dp.montar_args([{"name": "p", "valor": valor}]) == ["-param", esperado]


def test_linha_de_log_mascara_e_lista_ignorados():
    linha = dp.linha_de_log(_lista_com_segredo(), ["pFora"])
    assert "pData=2026-08-31 (etapa · referência 2026-09-09 → -1 mês → fim do mês → 2026-08-31)" in linha
    assert "pSenha=*** (etapa · fixo (Encrypted))" in linha
    assert "ignorados do pipeline (o job não declara): pFora" in linha
    assert "segredo" not in linha


def test_linha_de_log_vazia():
    assert dp.linha_de_log([]) == "nenhum"


def test_para_json_mascara_o_encrypted():
    doc = json.loads(dp.para_json(_lista_com_segredo()))
    assert doc[1] == {"name": "pSenha", "valor": "***", "fonte": "etapa",
                      "descricao": "fixo (Encrypted)", "mascarado": True}
    assert doc[0]["valor"] == "2026-08-31" and doc[0]["mascarado"] is False
    assert "segredo" not in dp.para_json(_lista_com_segredo())


# ── carregar_etapa (dublê de hook) ───────────────────────────────────────────

class _Hook:
    def __init__(self, rows=None, erro=None):
        self.rows, self.erro, self.chamadas = rows, erro, []

    def get_records(self, sql, parameters=None):
        self.chamadas.append((sql, parameters))
        if self.erro:
            raise self.erro
        return self.rows


def test_carregar_etapa_le_com_placeholder_pymssql():
    h = _Hook(rows=[("pA", "String", "1", "fixo", None, None, None, None)])
    out = dp.carregar_etapa(h, "PIPE", "JOB")
    assert out == [_linha("pA", valor="1")]
    sql, params = h.chamadas[0]
    assert "%s" in sql and "?" not in sql and params == ("PIPE", "JOB")
    assert "ORDER BY param_order" in sql


def test_carregar_etapa_sem_migration_107_devolve_vazio_com_aviso(caplog):
    h = _Hook(erro=Exception("(207, b\"Invalid column name 'param_source'\")"))
    with caplog.at_level(logging.WARNING):
        assert dp.carregar_etapa(h, "P", "J", log=logging.getLogger("t")) == []
    assert "migration 107" in caplog.text


def test_carregar_etapa_outro_erro_propaga():
    h = _Hook(erro=OSError("banco fora"))
    with pytest.raises(OSError):
        dp.carregar_etapa(h, "P", "J")


# ── carregar_pipeline (F4) ───────────────────────────────────────────────────

def test_carregar_pipeline_le_a_tabela_108_com_placeholder_pymssql():
    h = _Hook(rows=[("pAmb", "String", "PRD", "fixo", None, None, None, None)])
    out = dp.carregar_pipeline(h, "PIPE")
    assert out == [_linha("pAmb", valor="PRD")]
    sql, params = h.chamadas[0]
    assert "dbo.etl_pipeline_param " in sql and "etl_pipeline_job_param" not in sql
    assert "%s" in sql and "?" not in sql and params == ("PIPE",)


def test_carregar_pipeline_sem_migration_108_devolve_vazio():
    h = _Hook(erro=Exception("(208, b\"Invalid object name 'dbo.etl_pipeline_param'\")"))
    assert dp.carregar_pipeline(h, "P", log=logging.getLogger("t")) == []


def test_carregar_pipeline_outro_erro_propaga():
    with pytest.raises(OSError):
        dp.carregar_pipeline(_Hook(erro=OSError("banco fora")), "P")
