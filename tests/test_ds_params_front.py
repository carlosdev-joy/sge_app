"""
Parâmetros DataStage no front (F3 da spec docs/spec-parametros-job-datastage.md):
lib/dsParams.ts e o JobTypeFields em modo datastage, pela bancada
tests/js/ds_params_harness.cjs (sucrase + React mínimo da casa).

O que se prende:
  1. draft ↔ API: origem SEMPRE presente (a API a exige), cálculo só com origem
     de data (o CHECK da 107 recusa o resto), Encrypted vazio + token gravado
     vira `***` (manter), run_id/data sem valor, linha vazia some, o segredo
     NUNCA vai para a prévia; storedproc byte a byte como antes;
  2. réguas que espelham api/services/job_params.py (nome, largura, origem,
     tipo × origem, faixas, formato, valor fixo por tipo, Encrypted, duplicata
     por CAIXA EXATA) — e as regex são literais `/…/`, não string com `\\d`;
  3. a tela: a seção só existe para datastage, "Simular com" só com parâmetro,
     o bloco de cálculo só aparece em origem de data, Encrypted é `password`
     com "mantido", a prévia do servidor aparece por nome, os erros da prévia
     aparecem, e o storedproc não ganhou nada.

Sem Node ou sem `node_modules` a suíte SALTA em vez de falhar.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "ds_params_harness.cjs"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"


def _node() -> str | None:
    caminho = shutil.which("node")
    if not caminho or not SUCRASE.is_dir():
        return None
    try:
        v = subprocess.run([caminho, "-v"], capture_output=True, text=True, timeout=30).stdout.strip()
        return caminho if int(v.lstrip("v").split(".")[0]) >= 18 else None
    except Exception:      # noqa: BLE001 — sonda de ambiente degrada em salto
        return None


@pytest.fixture(scope="module")
def cen() -> dict:
    node = _node()
    if node is None:
        pytest.skip("front não instalado nesta máquina")
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True, cwd=str(RAIZ), timeout=180)
    assert r.returncode == 0, f"bancada do front falhou:\n{r.stderr}"
    return json.loads(r.stdout)


# ═══════════ 1. draft ↔ API ═════════════════════════════════════════════════

def test_to_api_origem_sempre_e_calculo_so_com_data(cen):
    por = {p["param_name"]: p for p in cen["toApi"]}
    assert set(por) == {"pDataIni", "pAmb", "pSenhaMantida", "pSenhaNova", "pRun", "pSemOrigem"}
    assert por["pDataIni"] == {"param_name": "pDataIni", "param_type": "Date", "param_source": "data_referencia",
                               "param_value": None, "param_offset_meses": -1, "param_ancora": "inicio_mes",
                               "param_offset_dias": None, "param_formato": None}
    # cálculo digitado numa origem fixa NÃO vai (o CHECK da 107 recusaria)
    assert por["pAmb"]["param_value"] == "PRD"
    assert (por["pAmb"]["param_offset_meses"], por["pAmb"]["param_ancora"],
            por["pAmb"]["param_offset_dias"], por["pAmb"]["param_formato"]) == (None, None, None, None)
    assert por["pSemOrigem"]["param_source"] == "fixo"


def test_to_api_encrypted_e_run_id(cen):
    por = {p["param_name"]: p for p in cen["toApi"]}
    assert por["pSenhaMantida"]["param_value"] == "***"      # vazio + token gravado = manter
    assert por["pSenhaNova"]["param_value"] == "segredo!"    # digitado = trocar
    assert por["pRun"]["param_value"] is None and por["pRun"]["param_source"] == "run_id"


def test_previa_nunca_recebe_o_segredo(cen):
    por = {p["param_name"]: p for p in cen["previewItens"]}
    # o que vai é um MARCADOR (o sentinela `***` do "manter" também é truthy → 'x')
    assert por["pSenhaNova"]["param_value"] == "x"
    assert por["pSenhaMantida"]["param_value"] == "x"
    assert "segredo" not in json.dumps(cen["previewItens"])


def test_despacho_por_tipo(cen):
    assert cen["despacho"]["storedproc"] == [{"param_name": "@p", "param_type": "INT", "param_value": "1"}]
    assert cen["despacho"]["shell"] == []


def test_from_api_hidrata_draft_e_mascara_encrypted(cen):
    por = {p["param_name"]: p for p in cen["fromApi"]}
    d = por["pDataFim"]
    assert (d["param_source"], d["param_offset_meses"], d["param_ancora"], d["param_offset_dias"], d["param_formato"]) \
        == ("data_referencia", "-1", "fim_mes", "", "%Y%m%d")
    assert d["param_value"] == ""
    s = por["pSenha"]
    assert s["param_value"] == "" and s["tem_valor"] is True
    sp = por["@p"]
    assert sp["param_value"] == "v" and sp["param_source"] == "fixo" and "tem_valor" not in sp


# ═══════════ 2. réguas ══════════════════════════════════════════════════════

def test_regras(cen):
    r = cen["regras"]
    assert r["valido"] == [] and r["pset"] == [] and r["encryptedMantido"] == [] and r["stringVazia"] == []
    assert r["linhaVazia"] == []
    assert any("nome inválido" in e for e in r["nomeRuim"])
    assert any("máximo 128" in e for e in r["nomeLongo"])
    assert any("origem" in e for e in r["semOrigem"])
    assert any("origem de data só com tipo" in e for e in r["dataComInteger"])
    assert any("fora da faixa" in e for e in r["mesesFora"])
    assert any("inteiro" in e for e in r["diasNaoInteiro"])
    assert any("formato inválido" in e for e in r["formatoRuim"])
    assert any("máximo 40" in e for e in r["formatoLongo"])
    assert any("run_id só com tipo String" in e for e in r["runIdDate"])
    assert any("não é um Integer válido" in e for e in r["integerRuim"])
    assert any("não é um Pathname válido" in e for e in r["pathRelativo"])
    assert any("não é um Date válido" in e for e in r["dateRuim"])
    assert any("Encrypted" in e for e in r["encryptedVazio"])
    # pA × pa NÃO é duplicata; pA × pA é
    assert r["duplicadoCaixaExata"] == ['Parâmetro "pA": duplicado']


def test_regex_sao_literais(cen):
    """`/\\d/` numa string nunca casa e passa tsc+lint+build (gotcha do repo):
    as regex expostas têm de ser objetos RegExp de verdade."""
    nome, formato = cen["regras"]["regexLiteral"]
    assert nome.startswith("/^[A-Za-z_]") and nome.endswith("$/")
    assert formato.startswith("/^(?:%[YmdyHMS]") and formato.endswith("$/")


def test_jobtypefields_valida_datastage_e_nao_muda_storedproc(cen):
    assert any("não é um Integer válido" in e for e in cen["erroPorTipo"]["datastage"])
    assert cen["erroPorTipo"]["storedprocIntocado"] == []


# ═══════════ 3. a tela ══════════════════════════════════════════════════════

def test_secao_so_para_datastage_e_simular_so_com_parametro(cen):
    t = cen["tela"]
    assert t["secaoSemParams"] == 1 and t["referenciaSemParams"] == 0
    assert t["referenciaComParams"] == 1
    assert t["storedprocSemSecaoDs"] == 0 and t["storedprocSemEditorDs"] == 0


def test_lista_esvaziada_nao_mostra_previa_nem_erro_velho(cen):
    """A query desabilitada ainda devolve a última resposta (placeholderData):
    com a lista vazia nada dela pode aparecer (achado da revisão da F3)."""
    assert cen["tela"]["esvaziadaErros"] == 0 and cen["tela"]["esvaziadaPrevias"] == 0


def test_linhas_por_origem(cen):
    t = cen["tela"]
    assert t["linhas"] == ["pDataFim", "pSenha", "pRun", "pAmb"]
    assert t["origens"] == ["data_referencia", "fixo", "run_id", "fixo"]
    assert t["calculos"] == 1                       # só a origem de data tem o bloco meses/âncora/dias/formato
    assert t["encrypted"] == [["mantido", "password", "mantido — digite para trocar"]]


# ═══════════ 4. F4: defaults do pipeline ════════════════════════════════════

def test_defaults_do_pipeline_aparecem_na_etapa_com_sobreposicao(cen):
    d = cen["defaults"]
    assert d["linha"] == 1
    assert d["itens"] == [["pAmb", "1"], ["pSenha", "0"], ["pDataFim", "0"]]
    assert "sobreposto pela etapa" in d["texto"]
    assert "Encrypted" in d["texto"] and "Data de referência" in d["texto"]
    assert "***" not in d["texto"] and "PRD" not in d["texto"]      # nunca o valor, só nome/origem
    # sem o pipeline (prop ausente) a query fica desabilitada; sem defaults a linha some
    assert d["semPipeline"] == 0 and d["semDefaults"] == 0


def test_secao_do_wizard_reusa_o_editor_datastage(cen):
    s = cen["secaoPipeline"]
    assert s["vaziaEditor"] == 1 and s["vaziaReferencia"] == 0    # editor sempre; "Simular com" só com item
    assert s["contagem"] == [2]
    assert s["linhas"] == ["pAmb", "pDataFim"] and s["calculos"] == 1
    assert s["previas"][0] == "PRD"
    assert "declarar o nome" in s["texto"] or "Parâmetros DataStage do pipeline" in s["texto"]


# ═══════════ 5. F5: a seção do modal de rerun ══════════════════════════════

def test_rerun_envia_so_o_que_difere_e_nunca_encrypted(cen):
    r = cen["rerun"]
    assert r["enviar"] == [{"job_name": "SeqCarga", "param_name": "pDataFim", "param_value": "2026-09-01"}]
    assert r["enviarVazio"] == []
    assert r["sobrepostos"] == [1]


def test_rerun_tela_mostra_efetivo_input_por_item_e_encrypted_bloqueado(cen):
    r = cen["rerun"]
    assert r["etapas"] == ["SeqCarga"]
    assert r["efetivos"] == ["2026-08-31", "PRD", "***"]
    assert r["inputs"] == [["pDataFim", "2026-09-01", "1"], ["pAmb", "PRD", "0"]]   # igual ao efetivo = não mudou
    assert r["naoEditaveis"] == ["pSenha"]
    assert r["aviso"] == 1 and "só nesta reexecução" in r["texto"]
    assert "se o job declarar" in r["texto"] and "default do pipeline" in r["texto"]
    assert r["vazio"] == "" and r["indisponiveis"] == ["indisponiveis"]


def test_previa_do_servidor_aparece_por_nome(cen):
    t = cen["tela"]
    assert t["previas"] == [
        ["2026-08-31", "referência 2026-09-09 → -1 mês → fim do mês → 2026-08-31"],
        ["", ""], ["", ""],
        ["PRD", "fixo"],
    ]
    assert t["errosPrevia"] == 1
    assert "algo" in t["texto"]
