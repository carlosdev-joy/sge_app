"""
dags/utils/ds_teams.py — card do Teams para os alertas da supervisão.

Segue o mesmo Adaptive Card que o orquestra_sla_monitor já usa no canal, para
os avisos do Orquestra terem a mesma cara.

Separação proposital: os montadores são PUROS (dict entra, dict sai) e por isso
testáveis sem rede; `enviar_card` é a única parte que fala com o mundo. São três,
um por família de evento — supervisão do DataStage (`montar_card`), dependência
entre pipelines (`montar_card_dependencia`) e corrida de malha
(`montar_card_malha`) —, todos no MESMO envelope de Adaptive Card.

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
    # F2 — o ciclo de vida da CORRIDA de malha (spec §6.5 e §9.14, Decisão 47).
    # Sem estes sete, o que chega no celular às 3h é o _PADRAO: um card amarelo
    # "🔔 Alerta" com subtítulo `#corrida:12` — cor de "atenção" para o evento
    # mais grave do produto, e nenhuma pista de QUAL malha quebrou.
    #
    # A partição de cor é a MESMA do painel (Decisão 59, "isso me chama às 3h?"):
    # Attention só para o que acabou mal, Warning para prazo/atípico/gesto
    # humano, Good para "não havia trabalho". Os três Attention dividem o mesmo
    # 🚨 de propósito — quem separa é o RÓTULO, porque cor nunca é o único canal
    # e o ícone aqui é a família, não o desfecho.
    #
    # Os rótulos saem do vocabulário da Decisão 74: nome de máquina não vai à
    # tela nem ao celular ("encerrada sem terminar", nunca "EXPIRADA").
    "MALHA_FALHOU":       {"rotulo": "Malha falhou",                   "icone": "🚨", "cor": "Attention"},
    "MALHA_EXPIRADA":     {"rotulo": "Malha encerrada sem terminar",   "icone": "🚨", "cor": "Attention"},
    "MALHA_ABORTADA":     {"rotulo": "Malha não chegou a começar",     "icone": "🚨", "cor": "Attention"},
    "MALHA_ATRASADA":     {"rotulo": "Malha fora do prazo",            "icone": "⏰", "cor": "Warning"},
    "MALHA_CANCELADA":    {"rotulo": "Malha encerrada pelo operador",  "icone": "⚠️", "cor": "Warning"},
    "MALHA_REPROCESSO":   {"rotulo": "Reprocesso na malha",            "icone": "⚠️", "cor": "Warning"},
    # Não vira card (§9.14) — o evento nasce carimbado de notificado. O estilo
    # existe para o dia em que ele chegar por outra porta (reenvio, fila da
    # F11): sábado de malha só-dias-úteis é o oposto de incidente, e cair no
    # _PADRAO faria um "🔔 Alerta" âmbar por uma noite que funcionou.
    "MALHA_SEM_TRABALHO": {"rotulo": "Malha sem trabalho hoje",        "icone": "💤", "cor": "Good"},
}

_PADRAO = {"rotulo": "Alerta", "icone": "🔔", "cor": "Warning"}

# Marcadores que a guardiã grava em `pipeline_name` quando o evento não é de um
# pipeline: '#no:{id}' para os componentes do desenho (F14 §5) e '#corrida:{id}'
# para a corrida (Decisão 49). São chave INTERNA — nenhum dos dois chega ao card.
_MARCA_CORRIDA = "#corrida:"
_MARCA_NO = "#no:"

# Tipos que só a corrida emite. MALHA_CONCLUIDA fica FORA de propósito: ele sai
# tanto do nó Fim (marcador '#no:') quanto do fechador da corrida ('#corrida:'),
# e para ele quem decide o card é o marcador, não o tipo.
_TIPOS_CORRIDA = frozenset({
    "MALHA_FALHOU", "MALHA_EXPIRADA", "MALHA_ABORTADA", "MALHA_ATRASADA",
    "MALHA_CANCELADA", "MALHA_REPROCESSO", "MALHA_SEM_TRABALHO",
})

# O próximo passo, por tipo. O `detalhe` do evento diz o que aconteceu e nomeia
# os pendentes (Decisão 48); esta linha diz o que FAZER — porque na maioria das
# noites o card é a única superfície que a pessoa de plantão vê, e "Malha
# falhou" sem próximo passo obriga a abrir o notebook só para descobrir se há
# algo a fazer agora.
#
# Divergência declarada da spec: o §9.14 não prevê este bloco — prevê o BOTÃO
# para a tela da corrida, que é entregável da F11 (Decisão 69). Esta é a versão
# em texto, que vale antes e depois dele; nenhuma URL é inventada aqui.
ACAO_MALHA: dict[str, str] = {
    "MALHA_FALHOU": (
        "Reprocesse a partir do pipeline que falhou. Os outros podem seguir "
        "rodando — a corrida só fecha quando nada mais estiver em execução."),
    "MALHA_EXPIRADA": (
        "A corrida bateu o limite de segurança e foi encerrada sem terminar. "
        "Confira o que ficou para trás antes de disparar a malha de novo."),
    "MALHA_ABORTADA": (
        "Nenhum pipeline da malha chegou a iniciar. Confira se o Airflow está "
        "no ar e dispare a malha de novo."),
    # Teto com membro vivo é alarme, não desfecho (Decisão 25): dizer o que
    # NÃO adianta tentar vale tanto quanto dizer o que fazer — quem tenta
    # disparar de novo aqui recebe recusa e perde minutos de plantão.
    "MALHA_ATRASADA": (
        "Ainda há pipeline rodando, então nada foi encerrado e a malha segue "
        "bloqueada para um novo disparo. Se travou, encerre a corrida pela "
        "tela da malha."),
    "MALHA_CANCELADA": (
        "Encerramento pedido por uma pessoa, com o motivo acima. A malha volta "
        "a aceitar disparo."),
    "MALHA_REPROCESSO": (
        "Um pipeline desta corrida foi reprocessado sem reabri-la, porque já "
        "existe outra corrida em andamento. Confira se o resultado do dia "
        "mudou."),
    "MALHA_SEM_TRABALHO": (
        "Nenhum pipeline da malha roda nesta data (regra de dia). Não há nada "
        "a fazer."),
    "MALHA_CONCLUIDA": "Nada a fazer — a malha terminou o ciclo.",
}


def _fato(titulo: str, valor) -> dict:
    return {"title": titulo, "value": str(valor) if valor not in (None, "") else "—"}


def _dia_curto(valor) -> str:
    """'2026-08-04' → '04/08'. Formato desconhecido volta como veio, e ausente
    volta vazio — card torto é melhor que alerta não enviado."""
    texto = str(valor or "").strip()[:10]
    if len(texto) == 10 and texto[4] == "-" and texto[7] == "-":
        return f"{texto[8:10]}/{texto[5:7]}"
    return texto


def _corrida_publica(evento: dict) -> str:
    """Como a corrida se chama para quem lê o card: pela DATA, nunca pelo id.

    Decisão 74 — `#12` numa malha diária lê-se como "12ª tentativa hoje", e o
    id é numeração interna (IDENTITY global) que não significa nada para quem
    está de plantão. A ordinal só aparece da 2ª corrida do mesmo dia em diante,
    porque "1ª corrida de 04/08" sugere que houve uma segunda.
    """
    dia = _dia_curto(evento.get("data_ref"))
    if not dia:
        return ""
    try:
        sequencia = int(evento.get("sequencia") or 1)
    except (TypeError, ValueError):
        sequencia = 1                      # rótulo humano nunca derruba o card
    return f"corrida de {dia}" if sequencia <= 1 else f"{sequencia}ª corrida de {dia}"


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
    pipeline = str(evento.get("pipeline") or "")

    # A guardiã manda TODO evento da fila por aqui (`_notificar`, um card por
    # evento), então é aqui — e não no chamador — que a família do evento tem
    # de ser reconhecida: assim a guardiã continua sem saber o que é um card.
    # Roteia por MARCADOR primeiro (é a chave que a corrida grava, Decisão 49)
    # e por TIPO depois, para o evento que chegar sem marcador. Os '#no:' ficam
    # neste card: Fim e Notificação são componentes do desenho, não a corrida.
    if pipeline.startswith(_MARCA_CORRIDA) or (
            tipo in _TIPOS_CORRIDA and not pipeline.startswith(_MARCA_NO)):
        return montar_card_malha(evento)

    estilo = ESTILO.get(tipo, _PADRAO)

    corpo: list[dict] = [
        {"type": "TextBlock", "text": f"{estilo['icone']} {estilo['rotulo']}",
         "size": "Large", "weight": "Bolder", "wrap": True, "color": estilo["cor"]},
        {"type": "TextBlock", "text": pipeline or "?",
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


def montar_card_malha(evento: dict) -> dict:
    """Card dos eventos da CORRIDA de malha (F2 — spec §6.5/§9.14).

    PURA como as outras duas: dict entra, dict sai. Espera as chaves tipo,
    malha, data_ref, detalhe, detectado_em e — quando houver — sequencia; tudo
    opcional exceto tipo. Mesmo envelope, mesmo esqueleto (título · sujeito ·
    corpo · fatos) das outras famílias: quem está de plantão já lê esse card.

    O que muda, e por quê: o sujeito é a MALHA, não o `pipeline_name` — que
    para estes eventos é o marcador interno '#corrida:{id}' (Decisão 49).
    Publicar o marcador mandaria a chave técnica ao celular no lugar do nome
    que a pessoa conhece, e ainda faria o id de corrida (IDENTITY global) posar
    de identidade pública, que a Decisão 74 proíbe: a corrida se chama pela
    data. O id não aparece em lugar nenhum deste card — quem precisa dele tem
    o painel.
    """
    tipo = evento.get("tipo") or ""
    estilo = ESTILO.get(tipo, _PADRAO)
    malha = str(evento.get("malha") or "").strip()
    if not malha:
        # Quem grava o evento pode nomear a malha em `pipeline` em vez de
        # `malha` (a fila entrega uma chave só). Aproveita-se o que houver,
        # menos marcador: '#' é o prefixo de chave interna da casa, e é
        # justamente ele que não pode chegar ao celular.
        provavel = str(evento.get("pipeline") or "").strip()
        malha = "" if provavel.startswith("#") else provavel
    corrida = _corrida_publica(evento)

    # "Carga_Vida · corrida de 04/08". Faltando os dois, diz que falta — um "?"
    # calado neste card deixaria o alerta mais grave do produto sem sujeito, e
    # o leitor sem saber se o problema é a malha ou o aviso.
    sujeito = " · ".join(p for p in (malha, corrida) if p) or "malha não identificada"

    corpo: list[dict] = [
        {"type": "TextBlock", "text": f"{estilo['icone']} {estilo['rotulo']}",
         "size": "Large", "weight": "Bolder", "wrap": True, "color": estilo["cor"]},
        {"type": "TextBlock", "text": sujeito, "wrap": True, "spacing": "None",
         "isSubtle": True},
    ]

    # O detalhe é o corpo (padrão da casa: a mensagem é renderizada na DETECÇÃO,
    # onde o contexto do dia existe — aqui é só exibir).
    detalhe = (str(evento.get("detalhe") or "")).strip()
    if detalhe:
        corpo.append({"type": "TextBlock", "text": detalhe, "wrap": True,
                      "spacing": "Medium"})

    # Tipo sem ação mapeada não ganha linha vazia nem texto genérico: uma fase
    # futura que acrescente um tipo cai no estilo neutro e sai SEM próximo
    # passo, que é honesto — inventar ação para evento desconhecido é pior que
    # omitir.
    acao = ACAO_MALHA.get(tipo)
    if acao:
        corpo.append({"type": "TextBlock", "text": f"O que fazer: {acao}",
                      "wrap": True, "spacing": "Medium", "isSubtle": True})

    corpo.append({
        "type": "FactSet", "spacing": "Medium",
        "facts": [
            _fato("Malha", malha),
            # A data de referência sai por extenso além do subtítulo curto: é
            # com ela que se reprocessa, e 04/08 sozinho não diz o ano.
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
