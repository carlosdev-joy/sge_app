"""Maestro no front (F2 da spec docs/spec-maestro-parametros.md): lib/maestro.ts,
MaestroPainel, MaestroChat e o botão no JobTypeFields, pela bancada
tests/js/ds_params_harness.cjs (seção 7; sucrase + React mínimo da casa).

O que se prende:
  1. o contexto que sai do browser NUNCA leva valor Encrypted (primeira
     barreira, antes do servidor) e só leva as colunas do contrato;
  2. o histórico enviado exclui boas-vindas e bolhas de erro e corta em 12;
  3. a proposta da API vira linhas do editor (Encrypted vazio + tem_valor
     false) e a mescla substitui pelo nome exato no lugar, acrescenta o resto
     e não toca o que o Maestro não citou;
  4. o painel: proposta com prévia por nome e sem prévia do Encrypted, avisos,
     "Aplicar no editor" que vira "Aplicado", cartão do não atendido com a
     orientação, sugestões só na abertura, estado pensando, histórico,
     `data-modal-exempt` (o trap de foco do Modal solta só para isso);
  5. o botão só em datastage com o backend dizendo enabled — e o "Importar do
     DataStage" continua lá; clicar abre o painel.

Sem Node ou sem `node_modules` a suíte SALTA em vez de falhar.
"""
from __future__ import annotations

import json
import re
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
def m() -> dict:
    node = _node()
    if node is None:
        pytest.skip("front não instalado nesta máquina")
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True, cwd=str(RAIZ), timeout=180)
    assert r.returncode == 0, f"bancada do front falhou:\n{r.stderr}"
    return json.loads(r.stdout)["maestro"]


# ═══════════ 1–2. o que sai do browser ═══════════════════════════════════════

def test_contexto_nunca_leva_valor_encrypted_e_so_as_colunas_do_contrato(m):
    c = m["contexto"]
    assert c["pipeline_name"] == "PIPE_VIDA" and c["job_name"] == "SeqCarga" and c["referencia"] == "2026-03-15"
    por = {p["param_name"]: p for p in c["params"]}
    assert set(por) == {"pSenha", "pAmb", "pDataFim"}           # linha vazia some
    assert por["pSenha"] == {"param_name": "pSenha", "param_type": "Encrypted", "param_source": "fixo"}
    assert "id" not in por["pAmb"] and "tem_valor" not in por["pSenha"]
    assert por["pDataFim"] == {"param_name": "pDataFim", "param_type": "Date", "param_source": "data_referencia",
                               "param_offset_meses": "-1", "param_ancora": "fim_mes"}
    assert "segredo" not in json.dumps(c)
    assert "pipeline_name" not in m["contextoSemJob"] and "job_name" not in m["contextoSemJob"]


def test_historico_exclui_boas_vindas_e_erros_e_corta_em_12(m):
    assert m["historico"] == [
        {"role": "user", "content": "mensal do mês anterior"},
        {"role": "assistant", "content": "Entendi. **pDataIni** e **pDataFim**."},
        {"role": "user", "content": "e o último dia útil?"},
        {"role": "assistant", "content": "Isso eu não atendo."},
    ]
    assert len(m["historicoCorte"]) == 12 and m["historicoCorte"][-1] == "m29"


# ═══════════ 3. proposta → editor ═══════════════════════════════════════════

def test_proposta_vira_draft_com_encrypted_vazio(m):
    assert [n[1:] for n in m["novos"]] == [
        ["pDataIni", "Date", "data_referencia", "", "-1", "inicio_mes", "%Y-%m-%d", None],
        ["pDataFim", "Date", "data_referencia", "", "-1", "fim_mes", "%Y-%m-%d", None],
        ["pSenha", "Encrypted", "fixo", "", "", "", "", False],
    ]
    assert all(re.fullmatch(r"m_\d+_p\w+", n[0]) for n in m["novos"])
    # aplicar duas vezes a mesma proposta nunca repete id (key duplicada no editor)
    assert len(set(m["idsDuasVezes"])) == len(m["idsDuasVezes"]) == 6


def test_aplicar_substitui_no_lugar_acrescenta_o_resto_e_preserva_o_que_nao_foi_citado(m):
    a = m["aplicado"]
    # pSenha (a) e pDataFim (c) substituídas NO LUGAR, com o id original; pAmb intocada; pDataIni no fim.
    # pSenha: a proposta Encrypted vem sem valor → o que o usuário tinha digitado ('segredo!') e o
    # tem_valor SOBREVIVEM (achado 1 da revisão adversarial: senão o salvar travava).
    assert a["ordem"][:4] == [["a", "pSenha", "segredo!", True], ["b", "pAmb", "PRD", None],
                              ["c", "pDataFim", "", None], ["d", "  ", "x", None]]
    assert a["ordem"][4][1:] == ["pDataIni", "", None]
    assert a["substituidos"] == ["pSenha", "pDataFim"] and a["adicionados"] == ["pDataIni"]


def test_aplicar_encrypted_sobre_token_gravado_mantem_o_manter(m):
    g = {p[1]: p for p in m["aplicadoGravado"]}
    assert g["pSenha"] == ["g", "pSenha", "Encrypted", "", True]      # `***` no salvar = manter o token
    assert set(g) == {"pSenha", "pDataIni", "pDataFim"}
    assert m["resumo"] == "1 parâmetro(s) adicionado(s) · 2 substituído(s): pSenha, pDataFim — confira os valores e salve a etapa"
    assert m["resumoVazio"].startswith("nada mudou")


def test_descricao_da_linha_e_mensagens_de_erro(m):
    assert m["descricoes"] == [
        "Date · Data de referência · −1 mês · início do mês · %Y-%m-%d",
        "Date · Data de referência · −1 mês · fim do mês · %Y-%m-%d",
        "Encrypted · Valor fixo · digite o valor no editor",
        "String · Run id da corrida",
        "String · Valor fixo · valor: PRD",
    ]
    e = m["erros"]
    assert "Limite" in e[0] and "Créditos" in e[1] and e[2] == "Não consegui enviar: a; b"
    assert e[3] == "Maestro desligado — contate o administrador." and "perfil" in e[4] and e[5] == "msg"
    a, b = m["idConversa"]
    assert a != b and all(8 <= len(x) <= 36 for x in (a, b))


# ═══════════ 4. o painel ════════════════════════════════════════════════════

def test_painel_mostra_proposta_previa_avisos_e_nao_atendido(m):
    p = m["painel"]
    assert p["msgs"] == ["assistant", "user", "assistant", "assistant", "user", "assistant"]
    assert p["propostas"] == 1 and p["params"] == ["pDataIni", "pDataFim", "pSenha"]
    assert p["previas"] == ["2026-02-01", "2026-02-28"]          # Encrypted sem prévia (seria `***`)
    # o rótulo usa a referência que a API CALCULOU (2026-03-15), não a atual do editor (2026-06-10)
    assert p["referenciasDaPrevia"] == ["2026-03-15", "2026-03-15"]
    assert p["avisos"] == 1 and p["aplicar"] == 1 and p["naoAtendido"] == 1
    assert "Procure o administrador" in p["texto"] and "dia útil exige calendário" in p["texto"]
    assert "digite o valor no editor" in p["texto"] and "***" not in p["texto"]
    assert "erro do provedor" in p["texto"]
    assert p["sugestoesComConversa"] == 0 and p["modalExempt"] == 1


def test_painel_aplicado_sugestoes_pensando_e_historico(m):
    p = m["painel"]
    assert p["aplicadaBotao"] == 0 and p["aplicadaMarca"] == 1
    assert p["sugestoesSoBoasVindas"] == 2
    assert p["estadoOuvindo"] == ["ouvindo"] and p["estadoPensando"] == ["pensando"] and p["digitando"] == 1
    # "Nova conversa" e "Histórico" esperam o Maestro terminar (resposta em voo na conversa errada)
    assert p["botoesDesabilitadosPensando"] == [True, True] and p["botoesHabilitadosOuvindo"] == [False, False]
    assert "pensando" in p["avatarPensando"]
    assert p["historicoConversas"] == ["c1"] and p["historicoSemEntrada"] == 0


# ═══════════ 5. o botão e a abertura ════════════════════════════════════════

def test_botao_so_em_datastage_com_o_backend_ligado(m):
    b = m["botao"]
    assert b["comMaestro"] == 1 and b["importarContinua"] == 1
    assert b["desligado"] == 0 and b["storedproc"] == 0
    assert b["semJob"] == 1          # nó novo no Fluxo: o Maestro ainda ajuda (pede os nomes)


def test_clicar_abre_o_painel_com_as_boas_vindas(m):
    assert m["abrir"] == {"antes": 0, "depois": 1, "boasVindas": 1}
