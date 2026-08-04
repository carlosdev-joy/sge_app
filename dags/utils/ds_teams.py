"""
dags/utils/ds_teams.py — card do Teams para os alertas da supervisão.

Segue o mesmo Adaptive Card que o orquestra_sla_monitor já usa no canal, para
os avisos do Orquestra terem a mesma cara.

Separação proposital: `montar_card` é PURA (dict entra, dict sai) e por isso
testável sem rede; `enviar_card` é a única parte que fala com o mundo.

Duas regras que valem conhecer antes de mexer:

  • **`notificado_em` só é marcado depois de o webhook responder 2xx.** Marcar
    antes trocaria "avisei" por "tentei avisar" — e um alerta perdido em silêncio
    é o pior resultado possível numa feature cujo propósito é avisar.
  • **A URL do webhook nunca entra em log nem em mensagem de erro.** Ela é
    credencial: quem tem a URL posta no canal. Os erros citam o canal pelo nome.
"""
from __future__ import annotations

# Rótulo, ícone e cor do Adaptive Card por tipo de evento.
#
# SITUACAO_INICIAL é deliberadamente verde e sem tom de urgência: ele não é um
# problema, é a confirmação de que o monitoramento começou. Vermelho ali
# ensinaria a operação a ignorar a cor.
ESTILO: dict[str, dict[str, str]] = {
    "ABORTOU":          {"rotulo": "Job abortou",          "icone": "🚨", "cor": "Attention"},
    "NAO_EXECUTOU":     {"rotulo": "Job não executou",     "icone": "🚨", "cor": "Attention"},
    "ATRASO":           {"rotulo": "Job atrasado",         "icone": "⏰", "cor": "Warning"},
    "ESTRUTURA":        {"rotulo": "Falha na verificação", "icone": "⚠️", "cor": "Warning"},
    "SITUACAO_INICIAL": {"rotulo": "Monitoramento iniciado", "icone": "✅", "cor": "Good"},
    # F4 — eventos de dependência entre pipelines (guardiã). Warning para o
    # que pede atenção do dia; Attention para o que já é fato consumado
    # (predecessor falhou / a corrida morreu sem liberar).
    "JANELA_ESTOUROU":    {"rotulo": "Janela de dependência estourou", "icone": "⏰", "cor": "Warning"},
    "DATA_DIVERGENTE":    {"rotulo": "Datas de referência divergentes", "icone": "⚠️", "cor": "Warning"},
    "PREDECESSOR_FALHOU": {"rotulo": "Predecessor falhou",             "icone": "🚨", "cor": "Attention"},
    "NAO_LIBEROU":        {"rotulo": "Dependência não liberou",        "icone": "🚨", "cor": "Attention"},
    # F5 — corrida que COMEÇOU e cujo DagRun morreu sem fechar nada (a classe
    # "órfão em RUNNING"). Attention: enquanto a linha estiver EXECUTANDO,
    # TODOS os dependentes do dia ficam parados atrás dela.
    "EXECUCAO_ORFA":      {"rotulo": "Execução órfã",                  "icone": "🚨", "cor": "Attention"},
    # F14 — observadores de malha (Notificação/Fim pela guardiã). Os quatro da
    # F4 são de PROBLEMA; estes são os primeiros de CONCLUSÃO — tom positivo,
    # como o SITUACAO_INICIAL: vermelho aqui ensinaria a ignorar a cor. O card
    # do Fim é opt-in por config (Decisão 14) — quem chega ao canal foi pedido.
    "MALHA_NOTIFICACAO":  {"rotulo": "Notificação da malha",           "icone": "📣", "cor": "Good"},
    "MALHA_CONCLUIDA":    {"rotulo": "Malha concluída",                "icone": "✅", "cor": "Good"},
}

_PADRAO = {"rotulo": "Alerta", "icone": "🔔", "cor": "Warning"}


def _fato(titulo: str, valor) -> dict:
    return {"title": titulo, "value": str(valor) if valor not in (None, "") else "—"}


def montar_card(evento: dict) -> dict:
    """Payload do Adaptive Card a partir de uma linha de evento + dados do job.

    Espera as chaves: tipo, mensagem, data_ref, project, job_name, descricao,
    janela_inicio, janela_fim. Tudo opcional exceto tipo — evento incompleto
    ainda gera card, com travessão no lugar do que faltar.
    """
    tipo = evento.get("tipo") or ""
    estilo = ESTILO.get(tipo, _PADRAO)
    rotulo = f"{estilo['icone']} {estilo['rotulo']}"
    alvo = f"{evento.get('project') or '?'}.{evento.get('job_name') or '?'}"

    corpo: list[dict] = [
        {"type": "TextBlock", "text": rotulo, "size": "Large", "weight": "Bolder",
         "wrap": True, "color": estilo["cor"]},
        {"type": "TextBlock", "text": alvo, "wrap": True, "spacing": "None",
         "isSubtle": True},
    ]

    # A mensagem já vem renderizada da coleta (variáveis substituídas lá, onde o
    # contexto do dia existe). Aqui é só exibir.
    mensagem = (evento.get("mensagem") or evento.get("detalhe") or "").strip()
    if mensagem:
        corpo.append({"type": "TextBlock", "text": mensagem, "wrap": True,
                      "spacing": "Medium"})

    janela = "—"
    ini, fim = evento.get("janela_inicio"), evento.get("janela_fim")
    if ini and fim:
        janela = f"{str(ini)[:5]}–{str(fim)[:5]}"

    corpo.append({
        "type": "FactSet", "spacing": "Medium",
        "facts": [
            _fato("Projeto", evento.get("project")),
            _fato("Job", evento.get("job_name")),
            _fato("Descrição", evento.get("descricao")),
            _fato("Dia", evento.get("data_ref")),
            _fato("Janela esperada", janela),
        ],
    })

    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": corpo,
            },
        }],
    }


def montar_card_dependencia(evento: dict) -> dict:
    """Card dos eventos de DEPENDÊNCIA entre pipelines (F4 — guardiã).

    PURA como `montar_card`: dict entra, dict sai — testável sem rede.
    Espera as chaves: tipo, pipeline, data_ref, detalhe, detectado_em —
    tudo opcional exceto tipo (evento incompleto ainda gera card, com
    travessão no lugar do que faltar). O corpo é o `detalhe` do evento: a
    mensagem é renderizada na DETECÇÃO, com o contexto em mãos (padrão da
    supervisão). O transporte é o MESMO `enviar_card` — herda os dois
    contratos já pagos: notificado_em só após 2xx e URL fora do log.
    """
    tipo = evento.get("tipo") or ""
    estilo = ESTILO.get(tipo, _PADRAO)

    corpo: list[dict] = [
        {"type": "TextBlock", "text": f"{estilo['icone']} {estilo['rotulo']}",
         "size": "Large", "weight": "Bolder", "wrap": True, "color": estilo["cor"]},
        {"type": "TextBlock", "text": str(evento.get("pipeline") or "?"),
         "wrap": True, "spacing": "None", "isSubtle": True},
    ]

    detalhe = (str(evento.get("detalhe") or "")).strip()
    if detalhe:
        corpo.append({"type": "TextBlock", "text": detalhe, "wrap": True,
                      "spacing": "Medium"})

    corpo.append({
        "type": "FactSet", "spacing": "Medium",
        "facts": [
            _fato("Pipeline", evento.get("pipeline")),
            _fato("Data de referência", evento.get("data_ref")),
            _fato("Detectado em", evento.get("detectado_em")),
        ],
    })

    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": corpo,
            },
        }],
    }


def enviar_card(webhook_url: str, card: dict, timeout: int = 15) -> tuple[bool, str]:
    """POST no webhook. Devolve (enviou, motivo).

    `enviou` só é True em 2xx — é o que autoriza marcar notificado_em. O motivo
    NUNCA inclui a URL: ela é credencial, e log é lido por muita gente.
    """
    if not (webhook_url or "").strip():
        return False, "canal sem webhook configurado"

    import requests  # import tardio: só a DAG precisa, e mantém o módulo testável

    try:
        resp = requests.post(webhook_url, json=card, timeout=timeout)
    except Exception as e:
        return False, f"falha de rede ao chamar o webhook: {type(e).__name__}"

    if 200 <= resp.status_code < 300:
        return True, f"HTTP {resp.status_code}"
    return False, f"webhook respondeu HTTP {resp.status_code}"
