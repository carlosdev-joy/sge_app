"""
Envio dos alertas da supervisão ao Teams (dags/utils/ds_teams.py + a etapa de
notificação da DAG).

O que estes testes protegem:

  • **`notificado_em` só depois do 2xx.** Marcar antes trocaria "avisei" por
    "tentei avisar", e o alerta sumiria em silêncio — falha total do propósito
    da feature.
  • **A URL do webhook nunca vaza** para log ou mensagem de erro: ela é
    credencial, quem tem a URL posta no canal.
  • **O card de início do monitoramento é visualmente distinto** dos alertas.
    Se ele saísse vermelho, a operação aprenderia a ignorar a cor.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_ROOT = Path(__file__).parent.parent
_DAGS = _ROOT / "dags"
if str(_DAGS) not in sys.path:
    sys.path.insert(0, str(_DAGS))

from utils.ds_teams import (  # noqa: E402
    ACAO_MALHA, ESTILO, enviar_card, montar_card, montar_card_dependencia,
    montar_card_malha, url_da_corrida,
)

WEBHOOK = "https://outlook.office.com/webhook/SEGREDO-abc123"


def _evento(**kw) -> dict:
    base = {
        "id": 1, "tipo": "ABORTOU", "data_ref": "2026-07-27",
        "detalhe": "detalhe técnico",
        "mensagem": "🚨 SeqSsdVida7Peps abortou em 2026-07-27. Início 02:10, parada 02:15.",
        "project": "BI_CVP", "job_name": "SeqSsdVida7Peps",
        "descricao": "Carga diária de vida",
        "janela_inicio": "02:00:00", "janela_fim": "03:00:00",
    }
    base.update(kw)
    return base


def _texto_do_card(card: dict) -> str:
    """Concatena todo texto visível do card, para asserções de conteúdo."""
    corpo = card["attachments"][0]["content"]["body"]
    partes = []
    for bloco in corpo:
        if bloco.get("type") == "TextBlock":
            partes.append(bloco.get("text", ""))
        if bloco.get("type") == "FactSet":
            for f in bloco["facts"]:
                partes.append(f"{f['title']}: {f['value']}")
    return "\n".join(partes)


# ── Estrutura do Adaptive Card ──────────────────────────────────────────────

def test_card_tem_o_envelope_esperado_pelo_teams():
    card = montar_card(_evento())
    anexo = card["attachments"][0]
    assert card["type"] == "message"
    assert anexo["contentType"] == "application/vnd.microsoft.card.adaptive"
    assert anexo["content"]["type"] == "AdaptiveCard"
    assert anexo["content"]["version"] == "1.4"


def test_card_traz_projeto_job_dia_e_janela():
    texto = _texto_do_card(montar_card(_evento()))
    assert "BI_CVP" in texto
    assert "SeqSsdVida7Peps" in texto
    assert "2026-07-27" in texto
    assert "02:00–03:00" in texto            # janela formatada, sem segundos


def test_card_usa_a_mensagem_ja_renderizada():
    texto = _texto_do_card(montar_card(_evento()))
    assert "abortou em 2026-07-27. Início 02:10, parada 02:15." in texto


def test_sem_mensagem_cai_no_detalhe_tecnico():
    texto = _texto_do_card(montar_card(_evento(mensagem=None)))
    assert "detalhe técnico" in texto


def test_evento_incompleto_ainda_gera_card():
    # Card torto é melhor que alerta não enviado.
    card = montar_card({"tipo": "ATRASO"})
    texto = _texto_do_card(card)
    assert "—" in texto                      # campos ausentes viram travessão
    assert card["attachments"][0]["content"]["body"]


# ── Cor e rótulo por tipo ───────────────────────────────────────────────────

@pytest.mark.parametrize("tipo,cor", [
    ("ABORTOU", "Attention"),
    ("NAO_EXECUTOU", "Attention"),
    ("ATRASO", "Warning"),
    ("ESTRUTURA", "Warning"),
    ("SITUACAO_INICIAL", "Good"),
])
def test_cor_do_card_por_tipo(tipo, cor):
    card = montar_card(_evento(tipo=tipo))
    assert card["attachments"][0]["content"]["body"][0]["color"] == cor


def test_inicio_do_monitoramento_nao_parece_alerta():
    inicial = montar_card(_evento(tipo="SITUACAO_INICIAL"))
    alerta = montar_card(_evento(tipo="ABORTOU"))
    cor_inicial = inicial["attachments"][0]["content"]["body"][0]["color"]
    cor_alerta = alerta["attachments"][0]["content"]["body"][0]["color"]
    assert cor_inicial != cor_alerta
    assert cor_inicial == "Good"
    assert "Monitoramento iniciado" in _texto_do_card(inicial)


def test_tipo_desconhecido_nao_quebra_o_card():
    card = montar_card(_evento(tipo="INVENTADO"))
    assert card["attachments"][0]["content"]["body"][0]["color"] == "Warning"


def test_todo_tipo_conhecido_tem_estilo():
    for tipo in ("ABORTOU", "NAO_EXECUTOU", "ATRASO", "ESTRUTURA", "SITUACAO_INICIAL"):
        assert {"rotulo", "icone", "cor"} <= set(ESTILO[tipo])


# ── Envio ───────────────────────────────────────────────────────────────────

class RespostaFalsa:
    def __init__(self, status_code):
        self.status_code = status_code


def _mock_requests(monkeypatch, resposta=None, erro=None):
    modulo = MagicMock()
    if erro is not None:
        modulo.post.side_effect = erro
    else:
        modulo.post.return_value = resposta
    monkeypatch.setitem(sys.modules, "requests", modulo)
    return modulo


def test_webhook_vazio_nao_tenta_enviar(monkeypatch):
    mod = _mock_requests(monkeypatch, RespostaFalsa(200))
    ok, motivo = enviar_card("   ", {"a": 1})
    assert ok is False
    assert "sem webhook" in motivo
    mod.post.assert_not_called()


@pytest.mark.parametrize("status", [200, 201, 202, 204])
def test_2xx_autoriza_marcar_como_notificado(monkeypatch, status):
    _mock_requests(monkeypatch, RespostaFalsa(status))
    ok, motivo = enviar_card(WEBHOOK, {"a": 1})
    assert ok is True
    assert str(status) in motivo


@pytest.mark.parametrize("status", [400, 401, 404, 429, 500, 503])
def test_erro_http_nao_autoriza_marcar(monkeypatch, status):
    _mock_requests(monkeypatch, RespostaFalsa(status))
    ok, motivo = enviar_card(WEBHOOK, {"a": 1})
    assert ok is False
    assert str(status) in motivo


def test_falha_de_rede_nao_propaga_excecao(monkeypatch):
    _mock_requests(monkeypatch, erro=TimeoutError("timeout"))
    ok, motivo = enviar_card(WEBHOOK, {"a": 1})
    assert ok is False
    assert "TimeoutError" in motivo


@pytest.mark.parametrize("cenario", ["http", "rede", "vazio"])
def test_url_do_webhook_nunca_aparece_no_motivo(monkeypatch, cenario):
    if cenario == "http":
        _mock_requests(monkeypatch, RespostaFalsa(500))
        _ok, motivo = enviar_card(WEBHOOK, {})
    elif cenario == "rede":
        _mock_requests(monkeypatch, erro=ValueError(f"falhou ao chamar {WEBHOOK}"))
        _ok, motivo = enviar_card(WEBHOOK, {})
    else:
        _ok, motivo = enviar_card("", {})
    assert "SEGREDO" not in motivo
    assert "outlook.office.com" not in motivo


def test_card_e_enviado_como_json(monkeypatch):
    mod = _mock_requests(monkeypatch, RespostaFalsa(200))
    card = montar_card(_evento())
    enviar_card(WEBHOOK, card)
    _args, kwargs = mod.post.call_args
    assert kwargs["json"] == card
    assert kwargs["timeout"] == 15


# ── Card de dependência entre pipelines (F4 — guardiã) ──────────────────────

def _evento_dep(**kw) -> dict:
    base = {"id": 9, "tipo": "JANELA_ESTOUROU", "pipeline": "PIPE_C",
            "data_ref": "2026-08-01", "detalhe": "aguardando: PIPE_A",
            "detectado_em": "2026-08-01 08:05:00"}
    base.update(kw)
    return base


@pytest.mark.parametrize("tipo,cor", [
    ("JANELA_ESTOUROU", "Warning"),
    ("DATA_DIVERGENTE", "Warning"),
    ("PREDECESSOR_FALHOU", "Attention"),
    ("NAO_LIBEROU", "Attention"),
])
def test_card_de_dependencia_por_tipo(tipo, cor):
    """Os 4 tipos da guardiã têm estilo próprio no ESTILO (F4 §8)."""
    card = montar_card_dependencia(_evento_dep(tipo=tipo))
    assert card["attachments"][0]["content"]["body"][0]["color"] == cor
    assert {"rotulo", "icone", "cor"} <= set(ESTILO[tipo])


def test_card_de_dependencia_traz_pipeline_data_e_detalhe():
    texto = _texto_do_card(montar_card_dependencia(_evento_dep()))
    assert "PIPE_C" in texto
    assert "2026-08-01" in texto
    assert "aguardando: PIPE_A" in texto        # o detalhe É o corpo
    assert "Detectado em: 2026-08-01 08:05:00" in texto


def test_card_de_dependencia_incompleto_ainda_sai():
    # Card torto é melhor que alerta não enviado (mesma regra do canal).
    card = montar_card_dependencia({"tipo": "NAO_LIBEROU"})
    assert "—" in _texto_do_card(card)
    assert card["attachments"][0]["content"]["body"]


def test_card_de_dependencia_no_mesmo_envelope_do_canal():
    card = montar_card_dependencia(_evento_dep())
    anexo = card["attachments"][0]
    assert card["type"] == "message"
    assert anexo["contentType"] == "application/vnd.microsoft.card.adaptive"
    assert anexo["content"]["version"] == "1.4"


@pytest.mark.parametrize("tipo,rotulo", [
    ("MALHA_NOTIFICACAO", "Notificação da malha"),
    ("MALHA_CONCLUIDA", "Malha concluída"),
])
def test_card_dos_observadores_de_malha_tem_tom_positivo(tipo, rotulo):
    """F14 (Decisão 14): os 2 tipos novos são de CONCLUSÃO — cor Good, como o
    SITUACAO_INICIAL; vermelho aqui ensinaria a operação a ignorar a cor. O
    envelope é o MESMO montar_card_dependencia (pipeline = marcador #no:{id})."""
    card = montar_card_dependencia(
        _evento_dep(tipo=tipo, pipeline="#no:9", malha="Carga_Vida"))
    corpo = card["attachments"][0]["content"]["body"]
    assert corpo[0]["color"] == "Good"
    assert rotulo in corpo[0]["text"]
    assert {"rotulo", "icone", "cor"} <= set(ESTILO[tipo])
    # F11 (pendência 11 do §18): o sujeito é a MALHA, nunca o marcador.
    assert "Carga_Vida" in _texto_do_card(card)


# ── Card da CORRIDA de malha (F2 — spec §6.5/§9.14) ─────────────────────────
#
# O que esta seção protege, e o defeito que cada teste evita:
#
#   • **Os sete tipos têm estilo próprio.** Sem isso o celular recebe às 3h um
#     "🔔 Alerta" âmbar genérico — cor de "atenção" para o evento mais grave do
#     produto, e sem dizer qual malha quebrou (Decisão 47).
#   • **O card nomeia a MALHA, nunca o marcador.** `#corrida:12` é chave
#     interna; publicá-la troca o nome que a pessoa conhece por um id que não
#     significa nada, e faz o id posar de identidade pública (Decisão 74).
#   • **Tipo desconhecido não estoura.** É a degradação que mantém a guardiã
#     viva quando uma fase futura acrescentar um tipo novo antes de o card
#     saber dele: sai neutro, sem próximo passo inventado, e o alerta chega.

_TIPOS_DA_CORRIDA = [
    # (tipo, ícone, cor) — a tabela do §9.14, transcrita. É de propósito que
    # este parâmetro repita a constante em vez de importá-la: um teste que lê o
    # próprio mapa que testa concorda com qualquer troca de cor feita sem
    # querer, inclusive a que pinta MALHA_FALHOU de verde.
    ("MALHA_FALHOU",       "🚨", "Attention"),
    ("MALHA_EXPIRADA",     "🚨", "Attention"),
    ("MALHA_ABORTADA",     "🚨", "Attention"),
    ("MALHA_ATRASADA",     "⏰", "Warning"),
    ("MALHA_CANCELADA",    "⚠️", "Warning"),
    ("MALHA_REPROCESSO",   "⚠️", "Warning"),
    ("MALHA_SEM_TRABALHO", "💤", "Good"),
]


def _evento_corrida(**kw) -> dict:
    """Como o evento chega da fila: pipeline_name é o marcador '#corrida:{id}'
    (Decisão 49), e a data é o ODATE em ISO, como o `eventos_nao_notificados`
    devolve. Sem '#' no detalhe, para as asserções de vazamento valerem."""
    base = {"id": 4321, "tipo": "MALHA_FALHOU", "pipeline": "#corrida:98765",
            "malha": "Carga_Vida", "data_ref": "2026-08-04",
            "detalhe": ("Malha Carga_Vida, corrida de 04/08: 2 pendentes — "
                        "CARGA_A (falhou 01:12), CARGA_B (esperando outro "
                        "pipeline)"),
            "detectado_em": "2026-08-04 01:12:30"}
    base.update(kw)
    return base


@pytest.mark.parametrize("tipo,icone,cor", _TIPOS_DA_CORRIDA)
def test_os_sete_tipos_da_corrida_tem_estilo_proprio(tipo, icone, cor):
    corpo = montar_card_malha(_evento_corrida(tipo=tipo))["attachments"][0]["content"]["body"]
    assert {"rotulo", "icone", "cor"} <= set(ESTILO[tipo])
    assert ESTILO[tipo]["cor"] == cor
    assert ESTILO[tipo]["icone"] == icone
    assert corpo[0]["color"] == cor
    assert ESTILO[tipo]["rotulo"] != "Alerta"        # não caiu no _PADRAO
    assert icone in corpo[0]["text"]


def test_a_particao_de_cor_e_a_do_painel():
    """Decisão 59 — "isso me chama às 3h?". Attention SÓ para o que acabou mal;
    prazo, gesto humano e reprocesso são âmbar; "não havia trabalho" não é
    alarme nenhum. Um tipo a mais em Attention treina o plantão a ignorar
    vermelho, que é o custo que nenhuma cor paga de volta."""
    attention = {t for t, _i, _c in _TIPOS_DA_CORRIDA if ESTILO[t]["cor"] == "Attention"}
    assert attention == {"MALHA_FALHOU", "MALHA_EXPIRADA", "MALHA_ABORTADA"}
    assert ESTILO["MALHA_SEM_TRABALHO"]["cor"] == ESTILO["MALHA_CONCLUIDA"]["cor"] == "Good"


def test_os_tres_vermelhos_se_distinguem_sem_a_cor():
    """Cor nunca é o único canal (regra da casa, SupervisaoCard.tsx:64-65). Os
    três Attention compartilham o 🚨 de propósito — a família é a mesma —, então
    quem separa "falhou", "encerrada sem terminar" e "não chegou a começar" é o
    RÓTULO, e ele tem de ser distinto e legível."""
    rotulos = [ESTILO[t]["rotulo"] for t in
               ("MALHA_FALHOU", "MALHA_EXPIRADA", "MALHA_ABORTADA")]
    assert len(set(rotulos)) == 3


@pytest.mark.parametrize("tipo,_icone,_cor", _TIPOS_DA_CORRIDA)
def test_nenhum_nome_de_maquina_chega_ao_celular(tipo, _icone, _cor):
    """Decisão 74 — uma palavra por conceito, em português, e nenhum nome de
    máquina na interface. "a malha expirou por quiescência" não é frase que
    alguém leve para uma reunião, e o card é a superfície mais lida de todas."""
    texto = (ESTILO[tipo]["rotulo"] + " " + ACAO_MALHA[tipo]).lower()
    for jargao in ("malha_", "expirada", "abortada", "quiesc", "odate", "teto",
                   "guardiã", "órfã", "#"):
        assert jargao not in texto


def test_card_da_corrida_nomeia_a_malha_e_esconde_o_marcador():
    texto = _texto_do_card(montar_card_malha(_evento_corrida()))
    assert "Carga_Vida" in texto
    assert "Malha: Carga_Vida" in texto
    assert "#corrida:" not in texto and "98765" not in texto
    assert "#" not in texto                          # nenhuma numeração interna


def test_o_id_do_evento_tambem_fica_fora_do_card():
    """O card não é a tela de suporte: id de evento e id de corrida vivem no
    painel. Publicá-los ensina o plantão a citar número que ninguém procura."""
    texto = _texto_do_card(montar_card_malha(
        _evento_corrida(malha_execucao_id=98765, id=4321)))
    assert "4321" not in texto and "98765" not in texto


def test_a_corrida_se_chama_pela_data():
    texto = _texto_do_card(montar_card_malha(_evento_corrida()))
    assert "corrida de 04/08" in texto
    assert "2026-08-04" in texto        # o ODATE por extenso segue nos fatos


def test_a_segunda_corrida_do_dia_se_anuncia():
    """Decisão 74 — a ordinal só a partir da 2ª: "1ª corrida de 04/08" sugere
    que existe uma segunda, e numa malha diária isso é ruído todo dia."""
    assert "2ª corrida de 04/08" in _texto_do_card(
        montar_card_malha(_evento_corrida(sequencia=2)))
    assert "1ª corrida" not in _texto_do_card(
        montar_card_malha(_evento_corrida(sequencia=1)))


@pytest.mark.parametrize("tipo,_icone,_cor", _TIPOS_DA_CORRIDA)
def test_card_da_corrida_diz_o_que_fazer(tipo, _icone, _cor):
    """Na maioria das noites o card é a ÚNICA superfície que a pessoa vê: sem o
    próximo passo, "Malha falhou" obriga a abrir o notebook só para descobrir
    se há algo a fazer agora. Sem URL: o botão para a tela é da F11."""
    texto = _texto_do_card(montar_card_malha(_evento_corrida(tipo=tipo)))
    assert "O que fazer:" in texto
    assert "http" not in texto.lower()


def test_o_detalhe_e_o_corpo_do_card():
    """Padrão da casa: a mensagem é renderizada na DETECÇÃO, com o contexto do
    dia em mãos (Decisão 48 — o detalhe nomeia malha, corrida e os pendentes
    com a classe). O card só exibe."""
    texto = _texto_do_card(montar_card_malha(_evento_corrida()))
    assert "CARGA_A (falhou 01:12)" in texto
    assert "CARGA_B (esperando outro pipeline)" in texto
    assert "Detectado em: 2026-08-04 01:12:30" in texto


def test_card_da_corrida_no_mesmo_envelope_do_canal():
    card = montar_card_malha(_evento_corrida())
    anexo = card["attachments"][0]
    assert card["type"] == "message"
    assert anexo["contentType"] == "application/vnd.microsoft.card.adaptive"
    assert anexo["content"]["type"] == "AdaptiveCard"
    assert anexo["content"]["version"] == "1.4"


# ── Roteamento: a guardiã manda tudo por montar_card_dependencia ────────────

def test_evento_da_corrida_vira_card_de_malha_pelo_marcador():
    """`_notificar` monta UM card por evento da fila, sempre pela mesma função.
    Se o roteamento não morasse aqui, o evento mais grave do produto sairia com
    subtítulo `#corrida:98765` — a chave técnica no lugar do nome da malha."""
    texto = _texto_do_card(montar_card_dependencia(_evento_corrida()))
    assert "Carga_Vida · corrida de 04/08" in texto
    assert "#corrida:" not in texto


def test_evento_da_corrida_sem_marcador_ainda_vira_card_de_malha():
    """Segundo ramo do roteamento: os sete tipos são exclusivos da corrida, e o
    card certo não pode depender de a guardiã ter gravado o marcador."""
    texto = _texto_do_card(montar_card_dependencia(
        _evento_corrida(tipo="MALHA_EXPIRADA", pipeline=None)))
    assert "Malha encerrada sem terminar" in texto
    assert "Carga_Vida" in texto


@pytest.mark.parametrize("tipo", ["MALHA_NOTIFICACAO", "MALHA_CONCLUIDA"])
def test_roteamento_nao_sequestra_os_eventos_de_no(tipo):
    """Regressão da F14: Fim e Notificação são componentes do DESENHO, não a
    corrida — chegam com '#no:{id}' e seguem no card de nó. MALHA_CONCLUIDA é o
    caso que prova que o roteamento é pelo MARCADOR: o mesmo tipo sai do nó Fim
    e do fechamento da corrida, e cada um tem o seu card.

    O que MUDOU na F11 (pendência 11 do §18) é o SUJEITO, não a rota: o card
    continua sendo o de nó e continua trazendo a data, mas quem aparece é a
    malha — o marcador é chave interna e não vai ao celular (Decisão 74)."""
    card = montar_card_dependencia(
        _evento_dep(tipo=tipo, pipeline="#no:9", malha="Carga_Vida"))
    texto = _texto_do_card(card)
    assert "Data de referência: 2026-08-01" in texto
    # O card de NÓ não é o card da corrida: o de nó não fala em "corrida de
    # 01/08" (o componente do desenho não tem ordinal de ciclo).
    assert "corrida de" not in texto


# ── Pendência 11 do §18 — `#no:38` não vai ao celular ───────────────────────
#
# O defeito, medido na `main`: o card de MALHA_CONCLUIDA do nó Fim saía com
# subtítulo `#no:38` e fato `Pipeline: #no:38`. O roteamento (mantê-lo no card
# de nó) é deliberado — Fim e Notificação são componentes do DESENHO, não a
# corrida —, e o que estava errado era publicar a chave técnica no lugar do
# nome que a pessoa de plantão conhece.

@pytest.mark.parametrize("tipo", ["MALHA_NOTIFICACAO", "MALHA_CONCLUIDA"])
def test_card_do_no_NAO_publica_o_marcador_interno(tipo):
    card = montar_card_dependencia(
        _evento_dep(tipo=tipo, pipeline="#no:38", malha="Carga_Vida"))
    texto = _texto_do_card(card)
    assert "#no:" not in texto and "#" not in texto
    assert "Malha: Carga_Vida" in texto
    # E o subtítulo é a malha, não o "?" mudo nem o marcador.
    assert card["attachments"][0]["content"]["body"][1]["text"] == "Carga_Vida"


def test_card_do_no_sem_malha_DIZ_que_nao_sabe_em_vez_de_publicar_a_chave():
    """A malha pode faltar (fila de uma versão anterior, nó apagado entre a
    detecção e o envio). Preferir "não identificada" a `#no:38` não é preciosismo:
    o marcador PARECE informação — quem lê às 3h tenta procurar por ele."""
    texto = _texto_do_card(montar_card_dependencia(
        _evento_dep(tipo="MALHA_CONCLUIDA", pipeline="#no:38")))
    assert "#no:" not in texto
    assert "malha não identificada" in texto


def test_evento_de_dependencia_COMUM_continua_nomeando_o_pipeline():
    """A contrapartida da correção acima: o card de dependência entre
    pipelines não perde o sujeito. `PIPE_C` não é nome de máquina — é o nome
    do pipeline, e é por ele que se procura no painel."""
    texto = _texto_do_card(montar_card_dependencia(_evento_dep()))
    assert "Pipeline: PIPE_C" in texto
    assert "Malha:" not in texto


def test_conclusao_do_fechamento_da_corrida_vai_pelo_card_da_malha():
    texto = _texto_do_card(montar_card_dependencia(
        _evento_corrida(tipo="MALHA_CONCLUIDA", detalhe="Malha Carga_Vida "
                        "concluída em 2026-08-04 com 40 pipelines")))
    assert "Malha concluída" in texto
    assert "Carga_Vida · corrida de 04/08" in texto
    assert "#corrida:" not in texto


# ── Degradação ─────────────────────────────────────────────────────────────

def test_tipo_desconhecido_da_familia_cai_no_neutro_sem_estourar():
    """A degradação que mantém a guardiã viva: a fase que acrescentar um tipo
    novo emite ANTES de o card conhecê-lo (deploy de `dags/` é um só, mas a
    ordem entre quem emite e quem estiliza não é garantida). O card sai neutro,
    o alerta chega, e ninguém perde a noite por um KeyError na notificação."""
    for montar in (montar_card_malha, montar_card_dependencia):
        card = montar(_evento_corrida(tipo="MALHA_INVENTADA_NA_F13"))
        corpo = card["attachments"][0]["content"]["body"]
        assert corpo[0]["color"] == "Warning"            # o _PADRAO
        assert "Alerta" in corpo[0]["text"]
        texto = _texto_do_card(card)
        assert "Carga_Vida" in texto                     # ainda diz qual malha
        assert "O que fazer:" not in texto               # e não inventa ação
        assert "#" not in texto


def test_malha_nomeada_no_campo_do_pipeline_ainda_aparece():
    """A fila entrega uma chave só (`pipeline`), e quem grava o evento pode
    pôr ali o nome da malha em vez do marcador. O card usa o que houver — só
    nunca um marcador, que é chave interna."""
    texto = _texto_do_card(montar_card_malha(
        _evento_corrida(malha=None, pipeline="Carga_Vida")))
    assert "Malha: Carga_Vida" in texto
    assert "malha não identificada" not in texto


def test_evento_da_corrida_incompleto_ainda_sai():
    """Card torto é melhor que alerta não enviado (mesma regra do canal). Sem
    malha e sem data, o card DIZ que não sabe — um "?" calado deixaria o alerta
    mais grave do produto sem sujeito, e o leitor sem saber se o problema é a
    malha ou o aviso."""
    card = montar_card_malha({"tipo": "MALHA_FALHOU"})
    texto = _texto_do_card(card)
    assert "malha não identificada" in texto
    assert "—" in texto
    assert card["attachments"][0]["content"]["body"]


@pytest.mark.parametrize("data_ref", [None, "", "ontem", "2026-08", 20260804])
def test_data_em_formato_estranho_nao_derruba_o_card(data_ref):
    """A data vem do banco como VARCHAR(10), mas o card também é montado em
    teste, em reenvio e por quem passar um date — nenhum desses caminhos pode
    derrubar a notificação por causa de uma formatação."""
    texto = _texto_do_card(montar_card_malha(_evento_corrida(data_ref=data_ref)))
    assert "Carga_Vida" in texto


def test_sequencia_nao_numerica_nao_derruba_o_card():
    texto = _texto_do_card(montar_card_malha(_evento_corrida(sequencia="duas")))
    assert "corrida de 04/08" in texto


def test_sem_trabalho_nao_parece_alerta():
    """Sábado de malha só-dias-úteis é o oposto de incidente (Decisão 26). Se
    ele saísse com a cara de alarme, na primeira semana o plantão aprenderia a
    ignorar a família inteira — e aí o alarme real deixa de servir."""
    dormindo = montar_card_malha(_evento_corrida(tipo="MALHA_SEM_TRABALHO"))
    alarme = montar_card_malha(_evento_corrida(tipo="MALHA_FALHOU"))
    cor = dormindo["attachments"][0]["content"]["body"][0]["color"]
    assert cor == "Good" != alarme["attachments"][0]["content"]["body"][0]["color"]
    assert "sem trabalho" in _texto_do_card(dormindo).lower()


# ── F11 (Decisão 69) — o BOTÃO que leva o card à corrida ────────────────────
#
# A pergunta que esta fase responde: uma tela ótima que ninguém alcança às 3h
# vale menos que uma tela boa com caminho até ela. O card chega no celular e o
# caminho até a corrida era destravar o telefone, abrir o notebook, VPN,
# `/malha`, achar a malha na lista, trocar o modo e escolher a data.
#
# O que estes testes protegem, e o defeito de cada um:
#   • **sem `app_base_url` o card sai EXATAMENTE como hoje.** Degradação por
#     ausência — uma URL adivinhada manda o plantão para um host que não
#     responde, às 3h, e queima a confiança no botão inteiro;
#   • **o id da corrida viaja na URL e nunca no texto** (Decisão 74);
#   • **marcador nunca vira parâmetro:** `?malha=%23corrida%3A12` abriria a
#     tela numa malha que não existe, com a chave técnica na barra de endereço.

BASE = "https://orquestra.exemplo.com"


def _acoes_do_card(card: dict):
    return card["attachments"][0]["content"].get("actions")


def _url_do_card(card: dict):
    acoes = _acoes_do_card(card)
    return acoes[0]["url"] if acoes else None


def test_card_da_corrida_leva_botao_para_a_corrida_certa():
    card = montar_card_malha(_evento_corrida(corrida_id=98765), BASE)
    acoes = _acoes_do_card(card)
    assert len(acoes) == 1
    assert acoes[0]["type"] == "Action.OpenUrl"
    assert acoes[0]["title"]                      # botão sem rótulo não existe
    assert acoes[0]["url"] == (
        "https://orquestra.exemplo.com/malha?malha=Carga_Vida"
        "&modo=execucao&corrida=98765")


@pytest.mark.parametrize("base", [None, "", "   ", "orquestra.exemplo.com",
                                  "ftp://orquestra", "/malha"])
def test_sem_endereco_utilizavel_o_card_sai_EXATAMENTE_como_hoje(base):
    """O aceite literal da fase. Esquema ausente entra na mesma vala do vazio:
    `orquestra.exemplo.com` sem `https://` vira link relativo dentro do Teams e
    abre um erro — e um botão que erra é pior que nenhum botão."""
    com = montar_card_malha(_evento_corrida(corrida_id=1), base)
    sem = montar_card_malha(_evento_corrida(corrida_id=1))
    assert "actions" not in com["attachments"][0]["content"]
    assert com == sem                              # byte a byte


@pytest.mark.parametrize("base", [
    "https://orquestra.exemplo.com/?x=1",     # query colada na base
    "https://orquestra.exemplo.com#topo",     # fragmento colado na base
    "https:// orquestra.exemplo.com",         # espaço no meio (copiar/colar)
    "https://orquestra.exemplo.com\tX",       # tabulação vinda da planilha
])
def test_base_que_nao_e_SO_endereco_sai_sem_botao_em_vez_de_link_colado(base):
    """A degradação desta fase é por AUSÊNCIA, e a checagem de esquema sozinha
    não a garante.

    ⚠️ Medido: `https://host/?x=1` passa por "começa com https://" e sai
    concatenado — `https://host/?x=1/malha?malha=…`. Um link quebrado é URL
    inventada com outro nome: o plantão clica às 3h e cai num 404, que é
    exatamente o que queima a confiança no botão inteiro. Sem base utilizável,
    o card sai como o de antes da fase."""
    card = montar_card_malha(_evento_corrida(corrida_id=12), base)
    assert "actions" not in card["attachments"][0]["content"]
    assert card == montar_card_malha(_evento_corrida(corrida_id=12))


@pytest.mark.parametrize("base", ["HTTPS://orquestra.exemplo.com",
                                  "Https://orquestra.exemplo.com"])
def test_esquema_em_CAIXA_ALTA_continua_sendo_um_endereco(base):
    """O outro lado da mesma checagem: `HTTPS://` é endereço válido em todo
    navegador, e recusá-lo apagaria o botão da fase inteira por uma diferença
    que ninguém enxerga — com o sintoma mais caro possível, que é o silêncio
    (a degradação por ausência esconderia um erro de digitação da config)."""
    url = _url_do_card(montar_card_malha(_evento_corrida(corrida_id=12), base))
    assert url == f"{base}/malha?malha=Carga_Vida&modo=execucao&corrida=12"


def test_botao_sem_o_id_da_corrida_ainda_leva_a_lente_de_execucao():
    """Evento sem corrida (o dos componentes do desenho): o link ainda é melhor
    que a lista — abre a malha na lente de execução. Inventar um id abriria a
    tela na corrida de outra pessoa."""
    url = _url_do_card(montar_card_malha(_evento_corrida(corrida_id=None), BASE))
    assert url == ("https://orquestra.exemplo.com/malha?malha=Carga_Vida"
                   "&modo=execucao")
    assert "corrida=" not in url


@pytest.mark.parametrize("cid", ["12", 12])
def test_id_de_corrida_em_texto_ainda_vira_lente(cid):
    """A fila devolve o que o driver der (int ou str) — o botão não pode
    depender disso."""
    assert _url_do_card(
        montar_card_malha(_evento_corrida(corrida_id=cid), BASE)).endswith(
            "&corrida=12")


@pytest.mark.parametrize("cid", ["duas", None, 0, -3, ""])
def test_id_de_corrida_estranho_nao_vira_parametro_nem_derruba_o_card(cid):
    url = _url_do_card(montar_card_malha(_evento_corrida(corrida_id=cid), BASE))
    assert url and "corrida=" not in url


def test_a_url_nao_leva_marcador_interno():
    """`malha` vindo como marcador é o caso do evento gravado sem a resolução
    da fila. Ele não pode virar `?malha=%23corrida%3A12`: é chave interna na
    barra de endereço, e o parâmetro não casaria com malha nenhuma."""
    card = montar_card_malha(
        _evento_corrida(malha=None, pipeline="#corrida:12"), BASE)
    assert "actions" not in card["attachments"][0]["content"]


@pytest.mark.parametrize("marcador", ["#corrida:12", "#no:38"])
def test_a_guarda_do_MARCADOR_e_perguntada_a_url_da_corrida(marcador):
    """A mesma regra, perguntada a QUEM a aplica — e a diferença não é estilo.

    ⚠️ Achado por MUTAÇÃO: apagando a guarda `nome.startswith('#')` de
    `url_da_corrida`, o teste acima continuava VERDE. Ele entra por
    `montar_card_malha`, que já limpa o marcador antes (o `provavel` do §F2), e
    por isso o `malha` que chega à URL nunca é um marcador **por aquele
    caminho** — a asserção passava por um motivo que não é o que ela afirma.

    O outro caminho não limpa nada: `montar_card_dependencia` entrega o
    `evento['malha']` cru ao botão do evento de nó. A guarda é a única coisa
    entre um `malha` estranho e `?malha=%23no%3A38` na barra de endereço do
    celular."""
    assert url_da_corrida(BASE, marcador, 12) is None
    assert url_da_corrida(BASE, marcador) is None


def test_o_card_do_NO_com_malha_estranha_nao_publica_a_chave_na_url():
    """O caminho que a guarda de fato protege, ponta a ponta: o card do nó usa
    `evento['malha']` sem limpeza nenhuma. Fila de uma versão anterior, ou um
    evento gravado antes da resolução da pendência 11, e o marcador chegaria
    inteiro à URL."""
    card = montar_card_dependencia(
        _evento_dep(tipo="MALHA_CONCLUIDA", pipeline="#no:38",
                    malha="#no:38"), BASE)
    assert "actions" not in card["attachments"][0]["content"]
    assert "#no:" not in _texto_do_card(card)


def test_nome_de_malha_com_espaco_e_acento_vai_percentcodificado():
    url = _url_do_card(montar_card_malha(
        _evento_corrida(malha="Carga Vida & Previdência"), BASE))
    assert "malha=Carga%20Vida%20%26%20Previd%C3%AAncia" in url
    assert " " not in url


def test_barra_final_da_config_nao_duplica_na_url():
    url = _url_do_card(montar_card_malha(
        _evento_corrida(), "https://orquestra.exemplo.com/"))
    assert url.startswith("https://orquestra.exemplo.com/malha?")


def test_o_id_da_corrida_continua_FORA_do_texto_do_card():
    """Decisão 74 — o `#` não vai à interface nem ao celular. A URL é endereço,
    não texto lido: o id pode estar nela e não pode estar no card."""
    texto = _texto_do_card(montar_card_malha(
        _evento_corrida(corrida_id=98765), BASE))
    assert "98765" not in texto and "#" not in texto
    assert "corrida de 04/08" in texto


def test_o_roteamento_repassa_o_endereco_para_o_card_da_corrida():
    """A guardiã chama UMA função (`montar_card_dependencia`); se a base
    parasse no roteador, o botão existiria em teste e não em produção."""
    url = _url_do_card(montar_card_dependencia(
        _evento_corrida(corrida_id=7), BASE))
    assert url.endswith("&corrida=7")


def test_card_do_NO_tambem_leva_botao_para_a_malha():
    """`MALHA_CONCLUIDA` do nó Fim é o card que a §18/11 conserta — e ele é
    tão `MALHA_*` quanto os outros: com a malha resolvida pela fila, ganha o
    botão. Sem corrida no evento, o link é o da lente de execução."""
    url = _url_do_card(montar_card_dependencia(
        _evento_dep(tipo="MALHA_CONCLUIDA", pipeline="#no:38",
                    malha="Carga_Vida"), BASE))
    assert url == ("https://orquestra.exemplo.com/malha?malha=Carga_Vida"
                   "&modo=execucao")


def test_card_de_dependencia_COMUM_nao_ganha_botao():
    """Evento de dependência entre pipelines não tem malha para abrir —
    mandá-lo para a LISTA seria o botão que esta fase existe para consertar."""
    card = montar_card_dependencia(_evento_dep(), BASE)
    assert "actions" not in card["attachments"][0]["content"]


def test_card_do_no_sem_malha_nao_ganha_botao():
    card = montar_card_dependencia(
        _evento_dep(tipo="MALHA_CONCLUIDA", pipeline="#no:38"), BASE)
    assert "actions" not in card["attachments"][0]["content"]


def test_actions_nunca_sai_como_lista_vazia():
    """`"actions": []` faz alguns clientes do Teams desenharem a faixa de ações
    vazia — uma tira cinza embaixo do card que não faz nada."""
    for card in (montar_card_malha(_evento_corrida()),
                 montar_card_dependencia(_evento_dep()),
                 montar_card(_evento())):
        assert card["attachments"][0]["content"].get("actions") != []


# ── "EXATAMENTE como hoje" — o card de antes da F11, congelado ──────────────
#
# Por que um card inteiro escrito à mão, e não `card_com == card_sem`:
# aquela comparação prova que os dois CAMINHOS desta versão coincidem, o que é
# necessário e insuficiente. Se a F11 tivesse acrescentado uma linha de texto
# ("acompanhe pelo Orquestra"), os dois lados a teriam e a igualdade
# continuaria verdadeira — com o card do celular mudado para todo mundo que
# ainda não configurou o endereço.
#
# Este é o card que a `main` produzia, capturado dela byte a byte antes da
# fase. É a régua externa: ele não muda quando o código muda.
_CARD_DE_ANTES = {
    "type": "message",
    "attachments": [{
        "contentType": "application/vnd.microsoft.card.adaptive",
        "content": {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "body": [
                {"type": "TextBlock", "text": "🚨 Malha falhou",
                 "size": "Large", "weight": "Bolder", "wrap": True,
                 "color": "Attention"},
                {"type": "TextBlock", "text": "Carga_Vida · corrida de 04/08",
                 "wrap": True, "spacing": "None", "isSubtle": True},
                {"type": "TextBlock",
                 "text": ("Malha Carga_Vida, corrida de 04/08: 2 pendentes — "
                          "CARGA_A (falhou 01:12), CARGA_B (esperando outro "
                          "pipeline)"),
                 "wrap": True, "spacing": "Medium"},
                {"type": "TextBlock",
                 "text": ("O que fazer: Reprocesse a partir do pipeline que "
                          "falhou. Os outros podem seguir rodando — a corrida "
                          "só fecha quando nada mais estiver em execução."),
                 "wrap": True, "spacing": "Medium", "isSubtle": True},
                {"type": "FactSet", "spacing": "Medium", "facts": [
                    {"title": "Malha", "value": "Carga_Vida"},
                    {"title": "Data de referência", "value": "2026-08-04"},
                    {"title": "Detectado em", "value": "2026-08-04 01:12:30"},
                ]},
            ],
        },
    }],
}


def test_sem_a_config_o_card_e_o_MESMO_de_antes_da_fase():
    """O aceite literal, contra a régua de fora: sem `app_base_url` o card do
    celular é o de antes da F11, campo a campo.

    A degradação por ausência é o contrato desta fase — e ela não vale só para
    o botão: vale para o card inteiro. Quem não configurar o endereço não pode
    receber um card diferente do que recebia ontem."""
    assert montar_card_malha(_evento_corrida()) == _CARD_DE_ANTES


def test_com_a_config_o_UNICO_acrescimo_e_o_botao():
    """A contrapartida: o botão é ADITIVO. Nenhum texto novo, nenhum bloco
    movido, nenhuma cor trocada — só a chave `actions`.

    É o que permite ligar a config em produção sem revalidar o card com quem
    está de plantão: o que ele já sabia ler continua onde estava."""
    card = montar_card_malha(_evento_corrida(corrida_id=7), BASE)
    conteudo = card["attachments"][0]["content"]
    antes = _CARD_DE_ANTES["attachments"][0]["content"]
    assert set(conteudo) - set(antes) == {"actions"}
    assert conteudo["body"] == antes["body"]
