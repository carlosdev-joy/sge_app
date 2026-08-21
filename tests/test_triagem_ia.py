"""Triagem de chamados (dags/utils/triagem_ia.py) — F4.

O que estes testes prendem, e por que cada um existe:

  1. **Todo chamado sai com veredito.** Gateway fora do ar, JSON quebrado,
     veredito inventado pelo modelo — tudo cai na heurística. Uma fila
     parcialmente triada é pior que uma fila triada por regra simples: o
     operador não sabe quais cards ele pode confiar.

  2. **A origem nunca mente.** Heurística apresentada como análise de IA é
     veredito em que ninguém pensou. Cada caminho de falha é medido pelo
     `origem` que devolve.

  3. **O erro fica registrado.** "A IA está fora há três dias" e "a IA
     concorda com a heurística" produzem o mesmo veredito — só o campo de
     erro separa os dois.

  4. **O hash cobre o texto que foi analisado.** Sem isso, ou a fila inteira é
     re-triada a cada 15 min (custo), ou um chamado cuja descrição mudou fica
     com o veredito velho (silencioso, e pior).

Nada aqui toca rede: o cliente HTTP é substituído.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "dags"))

from utils import triagem_ia  # noqa: E402
from utils.triagem_ia import (  # noqa: E402
    ORIGEM_HEURISTICA, ORIGEM_IA, VEREDITO_OK, VEREDITO_RETORNAR,
    config_da_triagem, extrair_json, laudo_da_ia, params_gravar, pendentes,
    suficiencia_heuristica, texto_para_hash, triagem_heuristica, triar,
)

CHAMADO = {
    "sys_id": "abc", "numero": "RITM0001",
    "titulo": "Inclusão de coluna na DM_123",
    "descricao": "Favor incluir a coluna NUM_APOLICE na tabela DM_123_VIDA, "
                 "com origem na TB_APOLICE e carga diária.",
    "work_notes": "dia a dia - melhoria",
    "catalogo": "Ajuste em tabela",
}

CONF_LIGADA = {"habilitada": True, "provider": "caixa_gateway",
               "modelo": "claude-sonnet-4-6", "base_url": "http://gw/api",
               "api_key_enc": "x", "usa_proxy": False, "lote": 20}


def _resposta_ia(monkeypatch, texto, erro=""):
    monkeypatch.setattr(triagem_ia, "chamar_gateway",
                        lambda *_a, **_k: (texto, erro))


# ═══════════ 1. o caminho feliz ═════════════════════════════════════════════

def test_ia_produz_laudo_com_origem_ia(monkeypatch):
    _resposta_ia(monkeypatch, """{
        "resumo": "Tipo: coluna | Objeto: DM_123_VIDA | Pedido: incluir",
        "entendimento": "Incluir coluna com origem definida.",
        "lacunas": [],
        "veredito": "PODE INICIAR",
        "justificativa": "fonte e critério claros",
        "perguntas": ""
    }""")
    laudo = triar(CHAMADO, CONF_LIGADA, "chave")
    assert laudo["veredito"] == VEREDITO_OK
    assert laudo["origem"] == ORIGEM_IA
    assert laudo["suficiencia"] == "suficiente"
    assert laudo["modelo"] == "claude-sonnet-4-6"
    assert laudo["erro"] == ""


def test_json_dentro_de_cerca_markdown_e_aproveitado(monkeypatch):
    """Modelo instruído a responder só JSON às vezes cerca com ```json.
    Recusar isso mandaria para a heurística um laudo que estava lá, correto."""
    _resposta_ia(monkeypatch,
                 '```json\n{"veredito": "PODE INICIAR", "resumo": "ok"}\n```')
    laudo = triar(CHAMADO, CONF_LIGADA, "chave")
    assert laudo["origem"] == ORIGEM_IA
    assert laudo["veredito"] == VEREDITO_OK


def test_lacunas_viram_linhas(monkeypatch):
    _resposta_ia(monkeypatch, """{
        "veredito": "RETORNAR AO SOLICITANTE",
        "lacunas": ["falta a fonte", "falta critério de aceite"],
        "perguntas": "1. Qual a origem?\\n2. Como validar?"
    }""")
    laudo = triar(CHAMADO, CONF_LIGADA, "chave")
    assert laudo["lacunas"] == "falta a fonte\nfalta critério de aceite"
    assert laudo["suficiencia"] == "parcial"
    assert "Qual a origem?" in laudo["perguntas"]


def test_pergunta_em_veredito_aprovado_e_descartada(monkeypatch):
    """Pergunta colada num chamado que já pode andar é ruído no ServiceNow."""
    _resposta_ia(monkeypatch,
                 '{"veredito": "PODE INICIAR", "perguntas": "1. algo?"}')
    assert triar(CHAMADO, CONF_LIGADA, "chave")["perguntas"] == ""


# ═══════════ 2. toda falha cai na heurística, com a origem correta ══════════

def test_gateway_fora_do_ar_cai_na_heuristica(monkeypatch):
    _resposta_ia(monkeypatch, "", erro="ConnectError: sem rota")
    laudo = triar(CHAMADO, CONF_LIGADA, "chave")
    assert laudo["origem"] == ORIGEM_HEURISTICA
    assert laudo["veredito"] in (VEREDITO_OK, VEREDITO_RETORNAR)
    assert "ConnectError" in laudo["erro"], (
        "o motivo precisa ficar gravado: gateway morto e gateway concordando "
        "com a heurística produzem o mesmo veredito")


def test_resposta_sem_json_cai_na_heuristica(monkeypatch):
    _resposta_ia(monkeypatch, "Claro! Aqui está a análise do chamado...")
    laudo = triar(CHAMADO, CONF_LIGADA, "chave")
    assert laudo["origem"] == ORIGEM_HEURISTICA
    assert "JSON" in laudo["erro"]


def test_veredito_inventado_pelo_modelo_e_recusado(monkeypatch):
    """Um "TALVEZ" viraria categoria nova na tela, sem cor nem significado."""
    _resposta_ia(monkeypatch, '{"veredito": "TALVEZ", "resumo": "x"}')
    laudo = triar(CHAMADO, CONF_LIGADA, "chave")
    assert laudo["origem"] == ORIGEM_HEURISTICA
    assert "TALVEZ" in laudo["erro"]


def test_triagem_desligada_ainda_da_veredito():
    conf = dict(CONF_LIGADA, habilitada=False)
    laudo = triar(CHAMADO, conf, "chave")
    assert laudo["origem"] == ORIGEM_HEURISTICA
    assert laudo["veredito"] in (VEREDITO_OK, VEREDITO_RETORNAR)
    assert "desligada" in laudo["erro"]


def test_sem_chave_nao_chama_gateway(monkeypatch):
    def _explode(*_a, **_k):
        raise AssertionError("não deveria chamar o gateway sem chave")
    monkeypatch.setattr(triagem_ia, "chamar_gateway", _explode)
    laudo = triar(CHAMADO, CONF_LIGADA, "")
    assert laudo["origem"] == ORIGEM_HEURISTICA


# ═══════════ 3. a heurística em si ══════════════════════════════════════════

def test_query_sql_e_contexto_suficiente():
    nivel, _ = suficiencia_heuristica("SELECT * FROM DMDB41..TB_X WHERE ano=2026")
    assert nivel == "suficiente"


def test_descricao_que_delega_para_anexo_e_insuficiente():
    nivel, motivo = suficiencia_heuristica(
        "Boa tarde, conforme falamos segue em anexo a imagem com o que precisamos.")
    assert nivel == "insuficiente"
    assert "anexo" in motivo.lower()


def test_descricao_vazia_e_insuficiente():
    assert suficiencia_heuristica("")[0] == "insuficiente"
    assert suficiencia_heuristica(None)[0] == "insuficiente"


def test_heuristica_nao_inventa_perguntas():
    """Ela mediu sinais do texto, não leu o pedido: pergunta genérica colada
    no chamado gera ruído para o solicitante."""
    laudo = triagem_heuristica("t", "Boa tarde, segue anexo com o print.")
    assert laudo["perguntas"] == ""
    assert laudo["veredito"] == VEREDITO_RETORNAR


def test_na_duvida_a_heuristica_manda_retornar():
    """Falso 'pode iniciar' faz alguém começar um trabalho que trava na
    metade; falso 'retornar' custa uma leitura humana."""
    laudo = triagem_heuristica("t", "Precisamos de um relatório para a diretoria "
                                    "com os números do mês fechado por produto.")
    assert laudo["veredito"] == VEREDITO_RETORNAR


# ═══════════ 4. o hash e a fila do lote ═════════════════════════════════════

def test_hash_muda_quando_o_texto_muda():
    a = texto_para_hash("desc", "notas", "titulo")
    assert a == texto_para_hash("desc", "notas", "titulo")
    assert a != texto_para_hash("desc MUDOU", "notas", "titulo")
    assert a != texto_para_hash("desc", "notas MUDARAM", "titulo")


def test_hash_nao_confunde_concatenacao():
    """Sem separador, ('ab','c') e ('a','bc') teriam o mesmo hash — e um
    chamado editado passaria por já triado."""
    assert texto_para_hash("ab", "c", "") != texto_para_hash("a", "bc", "")


def _linha(sys_id, texto, hash_gravado):
    return (sys_id, "RITM1", "titulo", texto, "notas", "cat", hash_gravado)


def test_pendentes_pega_quem_nunca_foi_triado():
    fila = pendentes([_linha("a", "desc", None)], 20)
    assert [c["sys_id"] for c in fila] == ["a"]
    assert fila[0]["hash"] == texto_para_hash("desc", "notas", "titulo")


def test_pendentes_ignora_quem_ja_foi_triado_com_o_mesmo_texto():
    h = texto_para_hash("desc", "notas", "titulo")
    assert pendentes([_linha("a", "desc", h)], 20) == []


def test_pendentes_pega_quem_mudou_de_texto():
    """O defeito silencioso: descrição nova com veredito velho."""
    h_velho = texto_para_hash("desc antiga", "notas", "titulo")
    fila = pendentes([_linha("a", "desc nova", h_velho)], 20)
    assert len(fila) == 1


def test_pendentes_respeita_o_teto_do_lote():
    linhas = [_linha(str(i), "desc", None) for i in range(50)]
    assert len(pendentes(linhas, 5)) == 5


def test_params_gravar_na_ordem_do_sql():
    """Deslocamento aqui grava o veredito na coluna do resumo, em silêncio."""
    laudo = triagem_heuristica("titulo", "desc")
    p = params_gravar(laudo, "hash123", "sys-1")
    assert p[0] == laudo["veredito"]
    assert p[-2] == "hash123"
    assert p[-1] == "sys-1"
    assert len(p) == triagem_ia.sql_gravar().count("%s")


# ═══════════ 5. config ══════════════════════════════════════════════════════

def test_config_desligada_por_padrao():
    assert config_da_triagem({})["habilitada"] is False


def test_config_le_o_interruptor_proprio():
    """A triagem NÃO pode depender de caixa_ia_enabled: aquele governa os
    assistentes do Caixa Seguro, e desligar o Diego não pode desligar isto."""
    cfg = {"chamados_triagem_habilitada": "1", "caixa_ia_enabled": "0"}
    assert config_da_triagem(cfg)["habilitada"] is True


def test_lote_invalido_cai_no_padrao():
    assert config_da_triagem({"chamados_triagem_lote": "abc"})["lote"] == \
        triagem_ia.LOTE_PADRAO


def test_lote_tem_teto():
    """Lote sem teto estoura o dagrun_timeout de 10 min do sync."""
    assert config_da_triagem({"chamados_triagem_lote": "99999"})["lote"] == 200


def test_extrair_json_recusa_lista_e_escalar():
    assert extrair_json("[1,2,3]") is None
    assert extrair_json("") is None
    assert extrair_json("texto sem json") is None


def test_laudo_da_ia_recusa_veredito_fora_da_lista():
    assert laudo_da_ia({"veredito": "quem sabe"}, "m") is None
    assert laudo_da_ia({}, "m") is None
