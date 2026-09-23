"""services/agentes_conhecimento.py — fatos e propostas (F5 da spec
docs/spec-agentes-datastage.md).

Os critérios de aceite da F5, e onde cada um é provado aqui:

  1. Fato só é gravado com origem de ferramenta → `gravar_fatos` recusa
     `interpretacao_aprovada` e origem desconhecida.
  2. Sem decisão, 0 linhas `interpretacao_aprovada` → proposta criada e não
     decidida não deixa fato nenhum.
  3. Aprovar 2× gera 1 fato; outro usuário decidindo → não encontrada;
     recusar não grava nada.
  4. Proposta com valor Encrypted ou padrão de segredo → recusada pela régua.
  5. A aprovação guarda `decidida_por`/`decidida_em` e sobrevive à purga da
     conversa → sem FK na 117, e a decisão não lê a conversa.
  6/7. ISX fora de pipeline e DSX viram fato com a origem certa (a fiação
     está em test_agentes_f5_orquestracao.py; aqui, o que é derivado).

Banco é o dublê em memória de `tests/_banco_agentes_f5.py`.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from services import agentes_conhecimento as ac  # noqa: E402
from tests._banco_agentes_f5 import BancoF5  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]


def _gravar(banco, fatos, *, origem="dsjob_lstages", job="JobX", lm=None, matricula="DEV1"):
    return ac.gravar_fatos(banco, banco.cursor(), ds_project="BI_CVP", job_name=job, pipeline_name=None,
                           origem=origem, fatos=fatos, evidencia="dsjob lstages", ds_last_modified=lm,
                           matricula=matricula)


# ═══════════ 1. fato só de ferramenta (critério 1) ═════════════════════════

@pytest.mark.parametrize("origem", ["interpretacao_aprovada", "modelo", "", "manual"])
def test_gravar_fatos_recusa_origem_que_nao_e_de_ferramenta(origem):
    banco = BancoF5()
    with pytest.raises(ValueError):
        _gravar(banco, [{"tipo": "stage", "chave": "S1", "valor": None}], origem=origem)
    assert banco.fatos == []


def test_origens_de_ferramenta_nao_incluem_a_interpretacao():
    assert ac.ORIGEM_INTERPRETACAO not in ac.ORIGENS_FERRAMENTA


# ═══════════ 2. retrato: insere, confirma, obsoleta ════════════════════════

def test_retrato_novo_insere_cada_chave_com_quem_leu():
    banco = BancoF5()
    r = _gravar(banco, [{"tipo": "stage", "chave": "S1", "valor": None},
                        {"tipo": "stage", "chave": "S2", "valor": None}])
    assert r == {"novos": 2, "confirmados": 0, "obsoletos": 0}
    assert {f["chave"] for f in banco.vigentes()} == {"S1", "S2"}
    assert all(f["lido_por"] == "DEV1" and f["origem"] == "dsjob_lstages" for f in banco.fatos)


def test_retrato_igual_so_confirma_sem_duplicar():
    banco = BancoF5()
    _gravar(banco, [{"tipo": "stage", "chave": "S1", "valor": {"a": 1}}])
    r = _gravar(banco, [{"tipo": "stage", "chave": "S1", "valor": {"a": 1}}], matricula="DEV2")
    assert r == {"novos": 0, "confirmados": 1, "obsoletos": 0}
    assert len(banco.fatos) == 1 and banco.fatos[0]["lido_por"] == "DEV2"


def test_valor_que_mudou_obsoleta_o_antigo_e_insere_o_novo():
    banco = BancoF5()
    _gravar(banco, [{"tipo": "stage", "chave": "S1", "valor": {"tipo_stage": "Oracle"}}])
    r = _gravar(banco, [{"tipo": "stage", "chave": "S1", "valor": {"tipo_stage": "DB2"}}])
    assert r == {"novos": 1, "confirmados": 0, "obsoletos": 1}
    assert len(banco.fatos) == 2  # o antigo fica (auditoria)
    [vigente] = banco.vigentes()
    assert json.loads(vigente["valor_json"]) == {"tipo_stage": "DB2"}


def test_chave_que_sumiu_do_retrato_fica_obsoleta():
    banco = BancoF5()
    _gravar(banco, [{"tipo": "stage", "chave": "S1", "valor": None},
                    {"tipo": "stage", "chave": "S2", "valor": None}])
    _gravar(banco, [{"tipo": "stage", "chave": "S1", "valor": None}])
    assert [f["chave"] for f in banco.vigentes()] == ["S1"]


def test_retrato_vazio_nao_obsoleta_nada():
    """Um parse que não achou nada é mais provável formato inesperado (D-07)
    do que um job sem stages — não pode apagar o que já se sabia."""
    banco = BancoF5()
    _gravar(banco, [{"tipo": "stage", "chave": "S1", "valor": None}])
    r = _gravar(banco, [])
    assert r == {"novos": 0, "confirmados": 0, "obsoletos": 0}
    assert len(banco.vigentes()) == 1


def test_retrato_de_uma_origem_nao_mexe_em_outra():
    banco = BancoF5()
    _gravar(banco, [{"tipo": "stage", "chave": "S1", "valor": None}], origem="dsx")
    _gravar(banco, [{"tipo": "stage", "chave": "S9", "valor": None}], origem="dsjob_lstages")
    assert {(f["origem"], f["chave"]) for f in banco.vigentes()} == {("dsx", "S1"), ("dsjob_lstages", "S9")}


def test_retrato_nao_obsoleta_interpretacao_aprovada():
    banco = BancoF5()
    pid = banco.nova_proposta(tipo="stage", chave="S1")
    ac.decidir_proposta(banco, banco.cursor(), proposta_id=pid, matricula="DEV1", decisao="aprovar",
                        retencao_dias=30)
    _gravar(banco, [{"tipo": "stage", "chave": "S2", "valor": None}])
    assert any(f["origem"] == ac.ORIGEM_INTERPRETACAO for f in banco.vigentes())


def test_chave_e_cortada_na_largura_utf16_da_coluna():
    banco = BancoF5()
    _gravar(banco, [{"tipo": "stage", "chave": "😀" * 200, "valor": None}])
    chave = banco.fatos[0]["chave"]
    assert len(chave.encode("utf-16-le")) // 2 <= 300


def test_falha_no_meio_desfaz_o_retrato_inteiro():
    banco = BancoF5()
    _gravar(banco, [{"tipo": "stage", "chave": "S1", "valor": None}])

    class _Explode(type(banco.cursor())):
        def execute(self, sql, params=None):
            if sql.lower().startswith("insert"):
                raise RuntimeError("deadlock simulado")
            return super().execute(sql, params)
    with pytest.raises(RuntimeError):
        ac.gravar_fatos(banco, _Explode(banco), ds_project="BI_CVP", job_name="JobX", pipeline_name=None,
                        origem="dsjob_lstages", fatos=[{"tipo": "stage", "chave": "S2", "valor": None}],
                        evidencia="x", ds_last_modified=None, matricula="DEV1")
    # o S1 não foi obsoletado pela metade: rollback
    assert [f["chave"] for f in banco.vigentes()] == ["S1"]


# ═══════════ 3. derivar fatos da saída das ferramentas ═════════════════════

def test_lstages_so_aceita_linhas_com_cara_de_nome():
    saida = "LerClientes\nTransformar_1\n\nStatus code = 0\nGravar.Saida\nLerClientes\n"
    origem, fatos = ac.fatos_do_dsjob("lstages", saida)
    assert origem == "dsjob_lstages"
    assert [f["chave"] for f in fatos] == ["LerClientes", "Transformar_1", "Gravar.Saida"]
    assert all(f["tipo"] == "stage" for f in fatos)


def test_lparams_vira_parametro_so_com_o_nome():
    origem, fatos = ac.fatos_do_dsjob("lparams", "DT_CORTE\nDB_PASSWORD\n")
    assert origem == "dsjob_lparams"
    assert [(f["tipo"], f["chave"], f["valor"]) for f in fatos] == [
        ("parametro", "DT_CORTE", None), ("parametro", "DB_PASSWORD", None)]


@pytest.mark.parametrize("comando", ["ljobs", "jobinfo"])
def test_ljobs_e_jobinfo_nao_viram_fato(comando):
    assert ac.fatos_do_dsjob(comando, "qualquer coisa") is None


def test_report_vira_uma_descricao():
    origem, fatos = ac.fatos_do_dsjob("report", "Job JobX\nStages: 3")
    assert origem == "dsjob_report" and len(fatos) == 1 and fatos[0]["tipo"] == "descricao"


def test_isx_nunca_guarda_o_valor_padrao_do_parametro():
    resultado = {
        "stages": [{"stage_name": "Ler", "direction": "origem", "stage_type_raw": "OracleConnector",
                    "sql_tag": "TableName", "sql_expression": "SCH.TB_CLIENTE", "output_columns": [
                        {"name": "ID"}, {"name": "NOME"}]}],
        "parameters": [{"name": "DB_PASSWORD", "type": "Encrypted", "default": "{iisenc}CANARIO==",
                        "description": "senha do banco"},
                       {"name": "DT_CORTE", "type": "String", "default": "2026-01-01"}],
        "job_description": "Carga de clientes",
    }
    fatos = ac.fatos_do_isx(resultado)
    serializado = json.dumps(fatos, ensure_ascii=False)
    assert "CANARIO" not in serializado and "2026-01-01" not in serializado
    chaves = {(f["tipo"], f["chave"]) for f in fatos}
    assert ("stage", "Ler") in chaves and ("tabela", "origem:SCH.TB_CLIENTE") in chaves
    assert ("parametro", "DB_PASSWORD") in chaves and ("descricao", "job") in chaves
    stage = next(f for f in fatos if f["tipo"] == "stage")
    assert stage["valor"]["colunas"] == ["ID", "NOME"]


def test_dsx_so_vira_fato_quando_a_extracao_deu_certo():
    assert ac.fatos_do_dsx({"erro": "Job não encontrado"}) == []
    fatos = ac.fatos_do_dsx({"sucesso": True, "dados": [
        {"stage_name": "Gravar", "direction": "destino", "object_name": "TB_SAIDA", "columns": ["A"]}]})
    assert {(f["tipo"], f["chave"]) for f in fatos} == {("stage", "Gravar"), ("tabela", "destino:TB_SAIDA")}


def test_segredo_no_valor_do_fato_e_redigido_antes_de_gravar():
    banco = BancoF5()
    _gravar(banco, [{"tipo": "stage", "chave": "S1", "valor": {"sql": "CONNECT user/x password=CANARIO9"}}],
            origem="dsx")
    assert "CANARIO9" not in banco.fatos[0]["valor_json"]


# ═══════════ 4. ler_fatos (base primeiro) ═════════════════════════════════

def test_ler_fatos_marca_dsjob_vencido_pela_validade():
    banco = BancoF5()
    _gravar(banco, [{"tipo": "stage", "chave": "S1", "valor": None}])
    _gravar(banco, [{"tipo": "stage", "chave": "D1", "valor": None}], origem="dsx", lm="2026-01-01 10:00:00")
    import datetime as dt
    for f in banco.fatos:
        f["lido_em"] -= dt.timedelta(days=10)
    fatos = ac.ler_fatos(banco.cursor(), "BI_CVP", "JobX", validade_dias=7)
    por_chave = {f["chave"]: f for f in fatos}
    assert por_chave["S1"]["vencido"] is True and por_chave["S1"]["lido_ha_dias"] == 10
    # ISX/DSX não vencem por prazo: carregam a data do arquivo/job
    assert "vencido" not in por_chave["D1"]
    assert por_chave["D1"]["data_do_job_ou_arquivo"] == "2026-01-01 10:00:00"


def test_ler_fatos_nao_devolve_obsoleto():
    banco = BancoF5()
    _gravar(banco, [{"tipo": "stage", "chave": "S1", "valor": None}])
    _gravar(banco, [{"tipo": "stage", "chave": "S2", "valor": None}])
    assert [f["chave"] for f in ac.ler_fatos(banco.cursor(), "BI_CVP", "JobX", 7)] == ["S2"]


# ═══════════ 5. propostas: extrair e régua (critério 4) ═══════════════════

SAIDA = 'stage LerClientes lê a tabela SCH.TB_CLIENTE e grava em TB_SAIDA'
LEITURA = {"job": "JobX", "texto": SAIDA}


def _prop(**over):
    base = {"job_name": "JobX", "tipo": "lineage", "chave": "fluxo principal",
            "valor": "Carrega clientes de SCH.TB_CLIENTE para TB_SAIDA", "motivo": "leitura do job",
            "evidencia": "lê a tabela SCH.TB_CLIENTE"}
    base.update(over)
    return base


def test_extrair_propostas_tira_o_bloco_do_texto():
    texto = ('O job carrega clientes.\n```json\n{"propostas": [' + json.dumps(_prop()) + ']}\n```')
    limpo, brutas = ac.extrair_propostas(texto)
    assert limpo == "O job carrega clientes." and len(brutas) == 1


def test_extrair_proposta_unica_tambem_vale():
    _, brutas = ac.extrair_propostas('```json\n{"proposta": ' + json.dumps(_prop()) + '}\n```')
    assert len(brutas) == 1


def test_bloco_sem_proposta_fica_no_texto():
    texto = 'Exemplo:\n```json\n{"x": 1}\n```'
    limpo, brutas = ac.extrair_propostas(texto)
    assert brutas == [] and '"x": 1' in limpo


def test_proposta_valida_passa():
    p, motivo = ac.validar_proposta(_prop(), projeto="BI_CVP", saidas=[LEITURA])
    assert motivo is None and p["ds_project"] == "BI_CVP" and p["tipo"] == "lineage"


def test_evidencia_com_espacos_diferentes_ainda_confere():
    p, _ = ac.validar_proposta(_prop(evidencia="lê  a tabela\nSCH.TB_CLIENTE"), projeto="BI_CVP", saidas=[LEITURA])
    assert p is not None


def test_evidencia_que_nao_esta_na_saida_das_ferramentas_e_recusada():
    """Risco 1 (falso verde): uma interpretação sem lastro no que foi lido
    nem chega ao cartão."""
    p, motivo = ac.validar_proposta(_prop(evidencia="o job é crítico para o fechamento"),
                                    projeto="BI_CVP", saidas=[LEITURA])
    assert p is None and "evidência" in motivo


def test_sem_ferramenta_na_pergunta_nao_ha_proposta():
    p, _ = ac.validar_proposta(_prop(), projeto="BI_CVP", saidas=[])
    assert p is None


def test_sem_projeto_resolvido_e_recusada():
    p, motivo = ac.validar_proposta(_prop(), projeto=None, saidas=[LEITURA])
    assert p is None and "projeto" in motivo


@pytest.mark.parametrize("over", [
    {"valor": "o parâmetro vale {iisenc}AbCdEf=="},
    {"valor": "password=Segredo123"},
    {"valor": {"DB_PASSWORD": "Segredo123"}},
    {"chave": "Encrypted: X"},
    {"motivo": "achei o token: abc123"},
    {"valor": "senha ••••"},
])
def test_proposta_com_cara_de_segredo_e_recusada(over):
    p, motivo = ac.validar_proposta(_prop(**over), projeto="BI_CVP", saidas=[LEITURA])
    assert p is None and motivo == "parece conter segredo"


@pytest.mark.parametrize("over,trecho", [
    ({"tipo": "opiniao"}, "tipo"),
    ({"job_name": ""}, "job_name"),
    ({"job_name": "J" * 201}, "job_name"),
    ({"chave": "C" * 301}, "chave"),
    ({"chave": "😀" * 151}, "chave"),  # 302 unidades UTF-16
    ({"valor": ""}, "valor"),
    ({"valor": "V" * 5000}, "valor"),
    ({"motivo": "M" * 601}, "motivo"),
    ({"evidencia": "curta"}, "evidência"),
])
def test_regua_de_tipo_e_tamanhos(over, trecho):
    p, motivo = ac.validar_proposta(_prop(**over), projeto="BI_CVP", saidas=[LEITURA])
    assert p is None and trecho in motivo


def test_no_maximo_3_propostas_e_o_excedente_e_informado():
    validas, recusadas = ac.filtrar_propostas([_prop(chave=f"c{i}") for i in range(5)],
                                              projeto="BI_CVP", saidas=[LEITURA])
    assert len(validas) == 3 and len(recusadas) == 2 and all("limite" in r for r in recusadas)


def test_proposta_nao_dict_e_recusada_sem_levantar():
    validas, recusadas = ac.filtrar_propostas(["texto", 3, None], projeto="BI_CVP", saidas=[LEITURA])
    assert validas == [] and len(recusadas) == 3


# ═══════════ 6. decidir (critérios 2, 3 e 5) ══════════════════════════════

def _decidir(banco, pid, decisao, matricula="DEV1"):
    return ac.decidir_proposta(banco, banco.cursor(), proposta_id=pid, matricula=matricula,
                               decisao=decisao, retencao_dias=30)


def _interpretacoes(banco):
    return [f for f in banco.fatos if f["origem"] == ac.ORIGEM_INTERPRETACAO]


def test_sem_decisao_nenhum_fato_de_interpretacao():
    banco = BancoF5()
    ac.inserir_propostas(banco.cursor(), conversa_id="conv-00000001", agente="datastage", matricula="DEV1",
                         propostas=[ac.validar_proposta(_prop(), projeto="BI_CVP", saidas=[LEITURA])[0]])
    banco.commit()
    assert len(banco.propostas) == 1 and _interpretacoes(banco) == []


def test_aprovar_grava_um_fato_com_quem_e_quando():
    banco = BancoF5()
    pid = banco.nova_proposta()
    r = _decidir(banco, pid, "aprovar")
    assert r["estado"] == "aprovada" and r["decidida_por"] == "DEV1" and r["decidida_em"]
    [fato] = _interpretacoes(banco)
    assert fato["aprovado_por"] == "DEV1" and fato["aprovado_em"] is not None
    assert r["fato_id"] == fato["id"] and banco.propostas[pid]["fato_id"] == fato["id"]
    assert fato["evidencia"] == "stage LerClientes"


def test_aprovar_duas_vezes_gera_um_fato_so():
    banco = BancoF5()
    pid = banco.nova_proposta()
    _decidir(banco, pid, "aprovar")
    r = _decidir(banco, pid, "aprovar")
    assert r.get("ja_decidida") is True
    assert len(_interpretacoes(banco)) == 1


def test_recusar_nao_grava_nada():
    banco = BancoF5()
    pid = banco.nova_proposta()
    r = _decidir(banco, pid, "recusar")
    assert r["estado"] == "recusada" and r["decidida_por"] == "DEV1"
    assert banco.fatos == []


def test_outro_usuario_nao_decide_e_nao_descobre_que_existe():
    banco = BancoF5()
    pid = banco.nova_proposta(matricula="DEV1")
    with pytest.raises(ac.PropostaNaoEncontrada):
        _decidir(banco, pid, "aprovar", matricula="DEV2")
    with pytest.raises(ac.PropostaNaoEncontrada):
        _decidir(banco, 999, "aprovar")
    assert banco.fatos == [] and banco.propostas[pid]["estado"] == "pendente"


def test_decisao_oposta_depois_de_decidida_e_recusada():
    banco = BancoF5()
    pid = banco.nova_proposta()
    _decidir(banco, pid, "recusar")
    with pytest.raises(ac.PropostaJaDecidida) as e:
        _decidir(banco, pid, "aprovar")
    assert e.value.proposta["estado"] == "recusada"
    assert banco.fatos == []


def test_proposta_pendente_mais_velha_que_a_retencao_expira():
    banco = BancoF5()
    pid = banco.nova_proposta(idade_dias=31)
    with pytest.raises(ac.PropostaExpirada):
        _decidir(banco, pid, "aprovar")
    assert banco.propostas[pid]["estado"] == "expirada" and banco.fatos == []


def test_nova_aprovacao_substitui_a_interpretacao_anterior_da_mesma_chave():
    banco = BancoF5()
    p1 = banco.nova_proposta(valor_json='"versão 1"')
    p2 = banco.nova_proposta(valor_json='"versão 2"')
    _decidir(banco, p1, "aprovar")
    _decidir(banco, p2, "aprovar")
    vig = [f for f in banco.vigentes() if f["origem"] == ac.ORIGEM_INTERPRETACAO]
    assert [f["valor_json"] for f in vig] == ['"versão 2"']


def test_decisao_invalida_levanta_antes_do_banco():
    banco = BancoF5()
    with pytest.raises(ValueError):
        _decidir(banco, 1, "talvez")
    assert banco.execs == []


def test_decidir_nao_depende_da_conversa_existir():
    """Critério 5: a purga apaga a conversa; a proposta e a decisão ficam.
    `decidir_proposta` não lê `etl_agente_conversa` em momento nenhum."""
    banco = BancoF5()
    pid = banco.nova_proposta(conversa_id="conversa-ja-purgada")
    _decidir(banco, pid, "aprovar")
    assert not any("etl_agente_conversa" in sql.lower() for sql, _ in banco.execs)


def test_117_nao_tem_fk_de_fato_nem_proposta_para_a_conversa():
    sql = (RAIZ / "sql" / "migrations" / "117_agentes.sql").read_text(encoding="utf-8")
    for tabela in ("etl_agente_fato", "etl_agente_proposta"):
        bloco = re.search(rf"CREATE TABLE dbo\.{tabela} \((.*?)\);", sql, re.S).group(1)
        assert "REFERENCES" not in bloco.upper(), tabela


def test_purga_de_conversas_nao_toca_fato_nem_proposta():
    dag = (RAIZ / "dags" / "etl_log_cleanup.py").read_text(encoding="utf-8")
    trecho = dag[dag.index("def limpar_conversas_agentes"):]
    trecho = trecho[:trecho.index("\ndef ", 1)] if "\ndef " in trecho[1:] else trecho
    assert "etl_agente_fato" not in trecho and "etl_agente_proposta" not in trecho


# ═══════════ 7. achados das revisões (adversarial + segurança) ════════════

def test_evidencia_de_outro_job_nao_serve():
    """Segurança: o job da proposta tem de ter sido LIDO nesta pergunta — a
    evidência de outro job não ancora a interpretação."""
    p, motivo = ac.validar_proposta(_prop(job_name="JobY"), projeto="BI_CVP", saidas=[LEITURA])
    assert p is None and "não foi lido" in motivo


def test_saida_sem_job_nao_serve_de_evidencia():
    p, _ = ac.validar_proposta(_prop(), projeto="BI_CVP", saidas=[{"job": None, "texto": SAIDA}, SAIDA])
    assert p is None


def test_evidencia_copiada_de_saida_json_com_quebra_de_linha_confere():
    """Adversarial #3: a saída do ISX/DSX vai ao modelo como json.dumps (\\n
    literal); a cópia fiel, depois do json.loads da proposta, tem quebra real."""
    import json as _j
    saida = _j.dumps({"sql": "SELECT a, b\nFROM dw.cliente WHERE x = \"1\""}, ensure_ascii=False)
    prop = _j.loads(_j.dumps(_prop(evidencia="SELECT a, b\nFROM dw.cliente WHERE x = \"1\"")))
    p, motivo = ac.validar_proposta(prop, projeto="BI_CVP", saidas=[{"job": "JobX", "texto": saida}])
    assert p is not None, motivo


def test_evidencia_com_valor_cifrado_e_recusada():
    saida = "CONN_STR {iisenc}AbCdEf0123==\nLerClientes"
    p, motivo = ac.validar_proposta(_prop(evidencia="CONN_STR {iisenc}AbCdEf0123=="), projeto="BI_CVP",
                                    saidas=[{"job": "JobX", "texto": saida}])
    assert p is None and motivo == "parece conter segredo"


def test_cifrado_sem_palavra_chave_nao_chega_ao_fato_nem_a_evidencia():
    """Adversarial #1 (alto): `{iisenc}` numa linha sem "password" passava por
    `redigir()` e ficava permanente no fato do -report e na evidência."""
    banco = BancoF5()
    saida = "Job JobX\nCONN_STR {iisenc}CANARIO0123==\nStages: 3"
    origem, fatos = ac.fatos_do_dsjob("report", saida)
    ac.gravar_fatos(banco, banco.cursor(), ds_project="BI_CVP", job_name="JobX", pipeline_name=None,
                    origem=origem, fatos=fatos, evidencia=ac.evidencia_de("dsjob", {"comando": "report"}, saida),
                    ds_last_modified=None, matricula="DEV1")
    [f] = banco.fatos
    assert "CANARIO" not in f["valor_json"] and "CANARIO" not in f["evidencia"]
    assert "{iisenc}••••" in f["valor_json"]


def test_retrato_parcial_nao_obsoleta_o_que_nao_apareceu():
    """Adversarial #2: leitura cortada não é retrato completo."""
    banco = BancoF5()
    _gravar(banco, [{"tipo": "stage", "chave": "S1", "valor": None},
                    {"tipo": "stage", "chave": "S2", "valor": None}])
    r = ac.gravar_fatos(banco, banco.cursor(), ds_project="BI_CVP", job_name="JobX", pipeline_name=None,
                        origem="dsjob_lstages", fatos=[{"tipo": "stage", "chave": "S1", "valor": None}],
                        evidencia="e", ds_last_modified=None, matricula="DEV1", parcial=True)
    assert r["obsoletos"] == 0 and {f["chave"] for f in banco.vigentes()} == {"S1", "S2"}


def test_base_entrega_interpretacao_por_ultimo_sem_a_matricula():
    """Segurança: interpretação aprovada é opinião de um usuário — vem depois
    do que foi lido, rotulada, e sem a matrícula de quem aprovou."""
    banco = BancoF5()
    pid = banco.nova_proposta(tipo="stage", chave="AAA")
    _decidir(banco, pid, "aprovar")
    _gravar(banco, [{"tipo": "stage", "chave": "ZZZ", "valor": None}])
    fatos = ac.ler_fatos(banco.cursor(), "BI_CVP", "JobX", 7)
    assert [f["origem"] for f in fatos] == ["dsjob_lstages", ac.ORIGEM_INTERPRETACAO]
    assert "aprovado_por" not in fatos[1] and "não foi lida por ferramenta" in fatos[1]["nota"]
    assert "DEV1" not in json.dumps(fatos, ensure_ascii=False)


def test_aprovar_trava_a_chave_da_interpretacao():
    """Adversarial (não verificável estaticamente): duas propostas diferentes
    da mesma chave aprovadas juntas — o applock por chave serializa."""
    banco = BancoF5()
    pid = banco.nova_proposta()
    _decidir(banco, pid, "aprovar")
    travas = [p for sql, p in banco.execs if "sp_getapplock" in sql]
    assert travas and travas[-1][0] == "agente_interp:BI_CVP:JobX:descricao:job"


def test_mascara_do_cifrado_em_json_nao_engole_a_linha_seguinte():
    """2ª rodada adversarial: em JSON a quebra é `\\n` literal."""
    texto = json.dumps({"texto": "CONN_STR {iisenc}AbC==\nDT_CORTE 2026-01-01"})
    saida = ac.sem_cifrado(texto)
    assert "AbC" not in saida and "DT_CORTE" in saida
