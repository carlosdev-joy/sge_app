"""Maestro — o serviço (F1 da spec docs/spec-maestro-parametros.md).

O que estes testes prendem, e por quê:

  1. **Anti-drift do prompt.** O system prompt é GERADO do vocabulário de
     services/job_params: todo tipo, origem, âncora e limite aparece nele, e uma
     âncora acrescentada ao vocabulário (monkeypatch) aparece sozinha. Um prompt
     digitado à mão prometeria o que o operador não tem — ou esconderia o que
     ele passou a ter.
  2. **A semente do catálogo passa na régua.** As receitas da migration 110
     (lidas do próprio .sql) validam com a MESMA régua do salvar. Cenário que a
     régua recusaria não pode estar no catálogo.
  3. **A régua manda, não o modelo.** `atendido` com âncora inventada vira
     `nao_atendido` com o erro; params vazios idem; JSON ausente é `pergunta`.
  4. **Segredo nunca.** Valor Encrypted some do contexto, da proposta e do
     registro.
  5. **Contrato da proposta.** Encrypted sai vazio + tem_valor False; prévia do
     caso mensal com borda de fevereiro; avisos por nome não declarado, tipo
     divergente e ausência de ISX; motivo cortado em UTF-16.

Nada toca banco: cursores de mentira registram os executes.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from services import job_params as jp  # noqa: E402
from services import maestro  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
MIGRATION_110 = RAIZ / "sql" / "migrations" / "110_maestro.sql"

REF = date(2026, 3, 15)


def _catalogo():
    return [{"codigo": "mensal_anterior", "titulo": "Carga mensal do mês anterior",
             "descricao": "Primeiro e último dia do mês anterior.",
             "receita": {"params": [
                 {"param_name": "<DATA_INICIAL>", "param_type": "Date", "param_source": "data_referencia",
                  "param_offset_meses": -1, "param_ancora": "inicio_mes", "param_offset_dias": 0,
                  "param_formato": "%Y-%m-%d"}],
                 "exemplos": ["carga mensal do mês anterior"]}},
            {"codigo": "rastreio_run_id", "titulo": "Run id", "descricao": "run_id.",
             "receita": {"params": [{"param_name": "<RUN_ID>", "param_type": "String",
                                     "param_source": "run_id"}], "exemplos": []}}]


def _ctx(**extra):
    base = {"pipeline_name": "PIPE_VIDA", "job_name": "JobRaiz",
            "declarados": {"disponivel": True, "status": "ok", "extracted_at": "2026-09-10 10:00",
                           "itens": [{"name": "pDataIni", "type": "date"}, {"name": "pDataFim", "type": "date"},
                                     {"name": "pSenha", "type": "encrypted"}]},
            "defaults": [], "editor": [], "referencia": "2026-03-15"}
    base.update(extra)
    return base


def _proposta_mensal(**extra):
    p = {"status": "atendido", "cenario": "mensal_anterior", "motivo": None, "params": [
        {"param_name": "pDataIni", "param_type": "Date", "param_source": "data_referencia",
         "param_value": None, "param_offset_meses": -1, "param_ancora": "inicio_mes",
         "param_offset_dias": 0, "param_formato": "%Y-%m-%d"},
        {"param_name": "pDataFim", "param_type": "Date", "param_source": "data_referencia",
         "param_value": None, "param_offset_meses": -1, "param_ancora": "fim_mes",
         "param_offset_dias": 0, "param_formato": "%Y-%m-%d"}]}
    p.update(extra)
    return p


# ═══════════ 1. anti-drift do prompt ═════════════════════════════════════════

def test_prompt_lista_todo_o_vocabulario_do_job_params():
    sp = maestro.system_prompt(_catalogo(), _ctx())
    for t in jp.DS_PARAM_TYPES:
        assert t in sp
    for o in jp.DS_PARAM_SOURCES:
        assert o in sp
    for a in jp.DS_PARAM_ANCORAS:
        assert a in sp and jp.ROTULO_ANCORA[a] in sp
    assert f"±{jp.LIMITE_MESES}" in sp and f"±{jp.LIMITE_DIAS}" in sp
    assert str(jp.LIMITE_NOME) in sp and str(jp.LIMITE_FORMATO) in sp
    assert jp.FORMATO_PADRAO in sp
    assert "meses → âncora → dias → formato" in sp


def test_prompt_e_gerado_e_nao_digitado(monkeypatch):
    """Uma âncora nova no vocabulário aparece no prompt sem ninguém lembrar."""
    monkeypatch.setattr(jp, "DS_PARAM_ANCORAS", jp.DS_PARAM_ANCORAS + ("fim_decada",))
    monkeypatch.setattr(jp, "ROTULO_ANCORA", dict(jp.ROTULO_ANCORA, fim_decada="fim da década"))
    sp = maestro.system_prompt(_catalogo(), _ctx())
    assert "fim_decada (fim da década)" in sp


def test_prompt_traz_catalogo_declarados_defaults_e_editor():
    ctx = _ctx(defaults=[{"param_name": "pAmbiente", "param_type": "String", "param_source": "fixo",
                          "param_value": "PRD"}],
               editor=[{"param_name": "pJaExiste", "param_type": "Integer", "param_source": "fixo",
                        "param_value": "1"}])
    sp = maestro.system_prompt(_catalogo(), ctx)
    assert "[mensal_anterior] Carga mensal do mês anterior" in sp
    assert '"param_name":"<DATA_INICIAL>"' in sp            # a receita vai compacta
    assert "pDataIni (date)" in sp and "pSenha (encrypted)" in sp
    assert "extração de 2026-09-10 10:00" in sp
    assert '"pAmbiente"' in sp and '"pJaExiste"' in sp
    assert "2026-03-15" in sp
    assert "```json" in sp and '"status": "nao_atendido"' in sp


def test_prompt_sem_isx_pede_os_nomes_e_com_isx_vazio_avisa():
    sp = maestro.system_prompt([], _ctx(declarados={"disponivel": False, "itens": []}))
    assert "Sem lineage ISX extraído" in sp and "catálogo vazio" in sp
    sp = maestro.system_prompt([], _ctx(declarados={"disponivel": True, "itens": []}))
    assert "NÃO declara parâmetro nenhum" in sp


def test_prompt_proibe_pedir_valor_encrypted_e_calcular_datas():
    sp = maestro.system_prompt(_catalogo(), _ctx())
    assert "NUNCA peça, repita nem proponha o VALOR de um Encrypted" in sp
    assert "Não calcule datas" in sp
    assert "procurar o administrador" in sp


# ═══════════ 2. semente da migration 110 ═════════════════════════════════════

def _receitas_da_semente() -> dict[str, dict]:
    sql = MIGRATION_110.read_text(encoding="utf-8")
    blocos = re.findall(r"WHERE codigo = '(\w+)'\)\s*BEGIN\s*INSERT INTO dbo\.etl_maestro_cenario.*?N'(\{.*?\})',\s*'migration_110'",
                        sql, re.S)
    return {codigo: json.loads(receita) for codigo, receita in blocos}


def test_semente_tem_os_cenarios_da_spec_e_codigos_unicos():
    receitas = _receitas_da_semente()
    assert set(receitas) >= {"mensal_anterior", "mes_corrente", "diario_referencia", "diario_d1",
                             "semanal_anterior", "trimestre_anterior", "ano_anterior",
                             "competencia_aaaamm", "rastreio_run_id", "caminho_fixo"}
    sql = MIGRATION_110.read_text(encoding="utf-8")
    codigos = re.findall(r"WHERE codigo = '(\w+)'", sql)
    assert len(codigos) == len(set(codigos))


@pytest.mark.parametrize("codigo", sorted(_receitas_da_semente()))
def test_cada_receita_da_semente_passa_na_regua(codigo):
    receita = _receitas_da_semente()[codigo]
    validos, erros = maestro.validar_receita(receita)
    assert erros == [], erros
    assert validos and receita.get("exemplos"), "toda receita tem params válidos e exemplos"
    # E a prévia resolve para uma referência real (borda de fevereiro).
    previa, erros_previa = jp.resolver_preview(REF, validos)
    assert erros_previa == [] and len(previa) == len(validos)


def test_semente_mensal_anterior_da_o_caso_da_spec():
    validos, _ = maestro.validar_receita(_receitas_da_semente()["mensal_anterior"])
    previa, _ = jp.resolver_preview(REF, validos)
    assert [p["valor"] for p in previa] == ["2026-02-01", "2026-02-28"]


def test_semente_semanal_anterior_ancora_e_depois_desloca():
    validos, _ = maestro.validar_receita(_receitas_da_semente()["semanal_anterior"])
    previa, _ = jp.resolver_preview(date(2026, 9, 10), validos)   # quinta
    assert [p["valor"] for p in previa] == ["2026-08-31", "2026-09-06"]


def test_migration_110_nao_usa_aspas_simples_dentro_do_json():
    """Uma aspa simples dentro do N'…' quebraria o lote inteiro no SQL Server."""
    for receita in re.findall(r"N'(\{.*?\})'", MIGRATION_110.read_text(encoding="utf-8"), re.S):
        assert "'" not in receita


# ═══════════ 3. receita e proposta ═══════════════════════════════════════════

def test_validar_receita_troca_marcadores_e_aceita_encrypted_sem_valor():
    validos, erros = maestro.validar_receita({"params": [
        {"param_name": "<SENHA>", "param_type": "Encrypted", "param_source": "fixo"}]})
    assert erros == [] and validos[0]["param_name"] == "p_1"


@pytest.mark.parametrize("receita", [None, {}, {"params": []}, {"params": "x"}])
def test_validar_receita_recusa_forma_errada(receita):
    _, erros = maestro.validar_receita(receita)
    assert erros


def test_validar_receita_recusa_ancora_inventada():
    _, erros = maestro.validar_receita({"params": [
        {"param_name": "<D>", "param_type": "Date", "param_source": "data_referencia",
         "param_ancora": "ultimo_dia_util"}]})
    assert erros and "âncora 'ultimo_dia_util' inválida" in erros[0]


def test_extrair_proposta_pega_o_ultimo_bloco_e_limpa_o_texto():
    texto = ("Entendi: mês anterior.\n\n```json\n{\"status\": \"pergunta\"}\n```\n"
             "Na verdade:\n```json\n" + json.dumps(_proposta_mensal()) + "\n```\n")
    limpo, proposta = maestro.extrair_proposta(texto)
    assert proposta["status"] == "atendido" and len(proposta["params"]) == 2
    assert "```" not in limpo.split("Na verdade")[1] and limpo.startswith("Entendi")


def test_extrair_proposta_nao_atravessa_uma_fence_aberta_antes():
    """Fence anterior com `{` sem `}` (um exemplo cortado) não pode engolir o
    bloco final: o nao_atendido viraria `pergunta` e o pedido sumiria."""
    texto = ("Exemplo:\n```json\n{\"status\": \"atendido\", \"params\": [\n```\n"
             "Agora a proposta real:\n```json\n"
             "{\"status\": \"nao_atendido\", \"cenario\": null, \"motivo\": \"dia útil\", \"params\": []}\n```")
    limpo, proposta = maestro.extrair_proposta(texto)
    assert proposta == {"status": "nao_atendido", "cenario": None, "motivo": "dia útil", "params": []}
    assert limpo.endswith("Agora a proposta real:")


@pytest.mark.parametrize("texto", ["``` json\n{\"status\": \"pergunta\"}\n```",
                                   "```JSON {\"status\": \"pergunta\"} ```",
                                   "```\n{\"status\": \"pergunta\"}\n```"])
def test_extrair_proposta_tolera_variacoes_da_fence(texto):
    assert maestro.extrair_proposta(texto)[1] == {"status": "pergunta"}


@pytest.mark.parametrize("texto", ["Só conversa, sem bloco.", "```json\n{isso não é json}\n```",
                                   "```json\n{\"sem\": \"status\"}\n```", "", None])
def test_extrair_proposta_sem_bloco_valido_e_none(texto):
    limpo, proposta = maestro.extrair_proposta(texto)
    assert proposta is None and limpo == (texto or "").strip()


def test_avaliar_caso_mensal_atendido_com_previa_de_fevereiro():
    r = maestro.avaliar(_proposta_mensal(), REF, _ctx()["declarados"], {"mensal_anterior"})
    assert r["status"] == "atendido" and r["cenario"] == "mensal_anterior" and r["motivo"] is None
    assert [p["valor"] for p in r["previa"]] == ["2026-02-01", "2026-02-28"]
    assert "-1 mês → início do mês → 2026-02-01" in r["previa"][0]["descricao"]
    assert r["params"][0]["param_source"] == "data_referencia" and r["params"][0]["param_value"] is None
    assert r["avisos"] == []


def test_avaliar_regua_derruba_ancora_inventada_mesmo_com_status_atendido():
    p = _proposta_mensal()
    p["params"][1]["param_ancora"] = "ultimo_dia_util"
    r = maestro.avaliar(p, REF, _ctx()["declarados"])
    assert r["status"] == "nao_atendido" and r["params"] is None and r["previa"] is None
    assert "não passou na régua" in r["motivo"] and "ultimo_dia_util" in r["motivo"]


def test_avaliar_atendido_sem_params_e_nao_atendido():
    r = maestro.avaliar({"status": "atendido", "params": []}, REF, None)
    assert r["status"] == "nao_atendido" and "sem parâmetros" in r["motivo"]


def test_avaliar_sem_proposta_ou_status_estranho_e_pergunta():
    assert maestro.avaliar(None, REF, None)["status"] == "pergunta"
    assert maestro.avaliar({"status": "talvez"}, REF, None)["status"] == "pergunta"
    assert maestro.avaliar({"status": "pergunta", "params": [{"x": 1}]}, REF, None)["params"] is None


def test_avaliar_nao_atendido_passa_o_motivo_cortado_em_utf16():
    motivo = "🙂" * 400   # 800 unidades UTF-16 > 600
    r = maestro.avaliar({"status": "nao_atendido", "motivo": motivo}, REF, None)
    assert r["status"] == "nao_atendido"
    assert len(r["motivo"].encode("utf-16-le")) // 2 <= maestro.LIMITE_MOTIVO
    assert not r["motivo"].endswith("\ud83d")   # nunca meio emoji


def test_avaliar_nao_atendido_sem_motivo_ganha_um():
    r = maestro.avaliar({"status": "nao_atendido"}, REF, None)
    assert r["motivo"]


def test_avaliar_encrypted_sai_vazio_com_tem_valor_false_e_previa_mascarada():
    p = {"status": "atendido", "params": [
        {"param_name": "pSenha", "param_type": "Encrypted", "param_source": "fixo", "param_value": "segredo!"}]}
    r = maestro.avaliar(p, REF, _ctx()["declarados"])
    assert r["status"] == "atendido"
    assert r["params"][0]["param_value"] == "" and r["params"][0]["tem_valor"] is False
    assert r["previa"][0]["valor"] == jp.ENCRYPTED_MASCARA
    assert "segredo" not in json.dumps(r, ensure_ascii=False)


def test_avaliar_avisa_nome_nao_declarado_e_tipo_divergente():
    p = _proposta_mensal()
    p["params"][0]["param_name"] = "pInexistente"
    p["params"][1]["param_type"] = "String"
    r = maestro.avaliar(p, REF, _ctx()["declarados"])
    assert r["status"] == "atendido"
    assert any("não declara 'pInexistente'" in a and "2026-09-10 10:00" in a for a in r["avisos"])
    assert any("declara 'pDataFim' como Date; a proposta usa String" in a for a in r["avisos"])


def test_avaliar_sem_isx_avisa_para_conferir_no_designer():
    r = maestro.avaliar(_proposta_mensal(), REF, {"disponivel": False, "itens": []})
    assert r["status"] == "atendido" and any("sem lineage ISX" in a for a in r["avisos"])


def test_avaliar_cenario_fora_do_catalogo_vira_none():
    r = maestro.avaliar(_proposta_mensal(cenario="inventado"), REF, None, {"mensal_anterior"})
    assert r["cenario"] is None
    r = maestro.avaliar(_proposta_mensal(cenario="x" * 80), REF, None, None)
    assert len(r["cenario"]) == maestro.LIMITE_CENARIO


def test_avaliar_previa_com_borda_de_calendario_vira_nao_atendido():
    p = {"status": "atendido", "params": [
        {"param_name": "pD", "param_type": "Date", "param_source": "data_referencia",
         "param_offset_meses": 12}]}
    r = maestro.avaliar(p, date(9999, 6, 1), None)
    assert r["status"] == "nao_atendido" and "prévia falhou" in r["motivo"]


# ═══════════ 4. contexto sem segredo ═════════════════════════════════════════

def test_sanear_editor_remove_valor_encrypted_e_limita():
    linhas = [{"param_name": "pSenha", "param_type": "Encrypted", "param_source": "fixo",
               "param_value": "segredo!", "id": "p_0", "tem_valor": True},
              {"param_name": "pTxt", "param_type": "String", "param_source": "fixo",
               "param_value": "v" * 500},
              {"param_name": "", "param_type": "String"}, "lixo", None]
    saida = maestro.sanear_editor(linhas)
    assert saida == [{"param_name": "pSenha", "param_type": "Encrypted", "param_source": "fixo"},
                     {"param_name": "pTxt", "param_type": "String", "param_source": "fixo",
                      "param_value": "v" * maestro.MAX_VALOR_EDITOR}]
    assert "segredo" not in json.dumps(saida)
    muitas = [{"param_name": f"p{i}", "param_type": "String"} for i in range(80)]
    assert len(maestro.sanear_editor(muitas)) == maestro.MAX_PARAMS_EDITOR


# ═══════════ 5. banco por dublê ══════════════════════════════════════════════

class _Cur:
    def __init__(self, rows=None, erro=None):
        self.rows, self.erro = rows or [], erro
        self.execs: list[tuple[str, tuple]] = []

    def execute(self, sql, params=None):
        self.execs.append((sql, tuple(params or ())))
        if self.erro:
            raise self.erro

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


def test_enabled_le_a_chave_e_degrada():
    assert maestro.enabled(_Cur([("1",)])) is True
    assert maestro.enabled(_Cur([("0",)])) is False
    assert maestro.enabled(_Cur([])) is False
    assert maestro.enabled(_Cur(erro=Exception("Invalid object name 'dbo.etl_app_config'"))) is False


def test_carregar_catalogo_pula_json_invalido_e_exige_a_110():
    cur = _Cur([("a", "A", "d", '{"params":[]}'), ("b", "B", "d", "{nao json"), ("c", "C", "d", "[]")])
    cat = maestro.carregar_catalogo(cur)
    assert [c["codigo"] for c in cat] == ["a"] and "ativo = 1" in cur.execs[0][0]
    with pytest.raises(maestro.MaestroIndisponivel) as e:
        maestro.carregar_catalogo(_Cur(erro=Exception("Invalid object name 'dbo.etl_maestro_cenario'")))
    assert "migration 110" in str(e.value)
    with pytest.raises(Exception, match="timeout"):
        maestro.carregar_catalogo(_Cur(erro=Exception("Login timeout expired")))


def test_parametros_declarados_le_o_isx(monkeypatch):
    from datetime import datetime
    from services import lineage_isx
    cab = {"parameters_json": json.dumps([{"name": "pDataIni", "type": "Date"}, {"name": "", "type": "x"},
                                          {"name": "PSet", "type": "ParameterSet"}]),
           "status": "ok", "extracted_at": datetime(2026, 9, 10, 10, 0, 5)}
    monkeypatch.setattr(lineage_isx, "cabecalho", lambda cur, p, j: cab if (p, j) == ("P", "J") else None)
    d = maestro.parametros_declarados(_Cur(), "P", "J")
    assert d == {"disponivel": True, "status": "ok", "extracted_at": "2026-09-10 10:00",
                 "itens": [{"name": "pDataIni", "type": "date"}, {"name": "PSet", "type": "parameterset"}]}
    assert maestro.parametros_declarados(_Cur(), "P", "Outro")["disponivel"] is False
    assert maestro.parametros_declarados(_Cur(), None, "J")["disponivel"] is False
    # Extração que FALHOU: o cabeçalho existe, mas não vale como "declara".
    monkeypatch.setattr(lineage_isx, "cabecalho", lambda cur, p, j: dict(cab, status="erro"))
    assert maestro.parametros_declarados(_Cur(), "P", "J")["disponivel"] is False
    # Tabela ausente (106 pendente): degrada.
    def _explode(cur, p, j):
        raise Exception("Invalid object name 'dbo.etl_ds_job_isx'")
    monkeypatch.setattr(lineage_isx, "cabecalho", _explode)
    assert maestro.parametros_declarados(_Cur(), "P", "J")["disponivel"] is False


def test_defaults_pipeline_sem_valor_encrypted(monkeypatch):
    monkeypatch.setattr(maestro, "_defaults_pipeline_108", lambda cur, p: [
        {"param_name": "pSenha", "param_type": "Encrypted", "param_value": "tok", "param_source": "fixo",
         "param_offset_meses": None, "param_ancora": None, "param_offset_dias": None, "param_formato": None}])
    d = maestro.defaults_pipeline(_Cur(), "P")
    assert d == [{"param_name": "pSenha", "param_type": "Encrypted", "param_source": "fixo"}]
    assert maestro.defaults_pipeline(_Cur(), None) == []


def test_registrar_grava_sem_segredo_e_corta_o_motivo():
    cur = _Cur()
    maestro.registrar(cur, conversa_id="c" * 50, matricula="U1", pipeline="P", job="J", mensagem="m",
                      resposta="r", status="atendido", cenario="mensal_anterior",
                      params=[{"param_name": "pSenha", "param_type": "Encrypted", "param_source": "fixo",
                               "param_value": "vazou?"}],
                      motivo="x" * 700, modelo="m" * 150, duracao_ms=12)
    sql, params = cur.execs[0]
    assert "INSERT INTO dbo.etl_maestro_conversa" in sql
    assert len(params[0]) == 36 and params[1] == "U1" and params[6] == "atendido"
    assert "vazou" not in params[8] and '"param_value": ""' in params[8]
    assert len(params[9]) == 600 and len(params[10]) == 100
    with pytest.raises(maestro.MaestroIndisponivel):
        maestro.registrar(_Cur(erro=Exception("Invalid object name 'dbo.etl_maestro_conversa'")),
                          conversa_id="c", matricula="U1", pipeline=None, job=None, mensagem="m",
                          resposta=None, status="erro", cenario=None, params=None, motivo=None,
                          modelo=None, duracao_ms=None)


def test_historico_escolhe_as_conversas_e_traz_todas_as_rodadas():
    """O SQL escolhe as `limite` conversas mais recentes (TOP parametrizado)
    e devolve as linhas em ordem: conversa mais recente primeiro, rodadas
    crescentes — o Python só agrupa, sem cortar nada."""
    rows = [("c2", "P", "J", "m3", "r3", "atendido", "2026-09-10 10:05:00"),
            ("c1", "P", "J", "m1", "r1", "pergunta", "2026-09-10 10:00:00"),
            ("c1", "P", "J", "m2", "r2", "pergunta", "2026-09-10 10:01:00")]
    cur = _Cur(rows)
    h = maestro.historico(cur, "U1", limite=2)
    sql, params = cur.execs[0]
    assert "TOP (?)" in sql and "GROUP BY conversa_id" in sql and "status <> 'erro'" in sql
    assert params == (2, "U1", "U1")
    assert [c["conversa_id"] for c in h] == ["c2", "c1"]
    assert h[1]["iniciado_em"] == "2026-09-10 10:00:00"
    assert [r["mensagem"] for r in h[1]["rodadas"]] == ["m1", "m2"]
    assert h[0]["rodadas"] == [{"mensagem": "m3", "resposta": "r3", "status": "atendido"}]


def test_sugestoes_usa_o_primeiro_exemplo_ou_o_titulo():
    assert maestro.sugestoes(_catalogo()) == ["carga mensal do mês anterior", "Run id"]
    assert maestro.sugestoes(_catalogo() * 5, maximo=3) == ["carga mensal do mês anterior", "Run id"]
