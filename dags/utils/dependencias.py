"""
dags/utils/dependencias.py — quando um pipeline dependente pode rodar.

O MODELO (condições IN/OUT do Control-M, traduzidas):
    um pipeline só é liberado quando TODOS os seus predecessores concluíram com
    sucesso NA MESMA data de referência. É o `AND` das condições IN, e o "na
    mesma data" é o que o ODATE resolve — sem ele, o sucesso de ontem liberaria
    a corrida de hoje.

O QUE ISTO SUBSTITUI: o `ExternalTaskSensor`, que exigia que pai e filho
tivessem o MESMO horário de agendamento (mesmo `logical_date`) e desistia após
1h. Aqui não há espera nem polling no caminho principal: quem conclui avalia
quem depende dele e dispara na hora.

DIVISÃO PROPOSITAL: as regras são funções PURAS (recebem dados, devolvem
decisão) e as consultas ficam separadas. É o que permite testar a liberação em
todos os casos sem banco — inclusive os que só apareceriam em produção, como um
predecessor concluído em OUTRA data de referência.
"""
from __future__ import annotations

from datetime import time

# Estados de etl_pipeline_execucao que contam como "concluiu bem".
SUCESSO = "SUCESSO"

# Só o sucesso libera. FALHA, EXECUTANDO e AGUARDANDO_DEPENDENCIA seguram; e
# PULADO também segura de propósito — se o predecessor não rodou hoje (blackout,
# dia não útil), o dependente não tem insumo, e disparar mesmo assim é o defeito
# 5 do QA (o modo Dataset fazia o oposto: sumia em silêncio).
ESTADOS_QUE_LIBERAM = frozenset({SUCESSO})


def avaliar_liberacao(status_por_predecessor: dict) -> tuple:
    """Todos os predecessores concluíram com sucesso na data de referência?

    `status_por_predecessor` mapeia nome → status da execução mais recente
    NAQUELA data (None = não há execução nenhuma nessa data).

    Devolve (liberado, pendentes) — a lista de pendentes é o que a mensagem de
    alerta mostra, então ela sai ordenada e não vazia quando bloqueia.

        >>> avaliar_liberacao({"A": "SUCESSO", "B": "SUCESSO"})
        (True, [])
        >>> avaliar_liberacao({"A": "SUCESSO", "B": None})
        (False, ['B'])
        >>> avaliar_liberacao({"A": "SUCESSO", "B": "FALHA"})
        (False, ['B'])

    Sem predecessores devolve (False, []): quem não tem dependência não passa
    por aqui, e responder True abriria caminho para disparar um pipeline por
    engano se a lista chegar vazia por erro de consulta.
    """
    if not status_por_predecessor:
        return False, []
    pendentes = sorted(
        nome for nome, status in status_por_predecessor.items()
        if status not in ESTADOS_QUE_LIBERAM)
    return (not pendentes), pendentes


def dentro_da_janela(nao_iniciar_antes, agora) -> bool:
    """Já passou do horário mínimo de início?

    É o FROM TIME do Control-M: o pipeline pode estar liberado às 07:10 e mesmo
    assim não dever começar antes das 08:00. Sem valor configurado, não há
    janela e o disparo é imediato.
    """
    if nao_iniciar_antes is None:
        return True
    limite = nao_iniciar_antes
    if not isinstance(limite, time):
        limite = _parse_hora(str(limite))
        if limite is None:
            return True          # valor inválido não pode travar o disparo
    atual = agora if isinstance(agora, time) else agora.time()
    return atual >= limite


def _parse_hora(texto: str):
    from datetime import datetime
    for formato in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(texto.strip(), formato).time()
        except ValueError:
            continue
    return None


# ── Regras da guardiã (F4) — puras ─────────────────────────────────────────

# Estados em que a corrida ainda não saiu do lugar: é sobre eles que a janela
# estoura. EXECUTANDO e SUCESSO já saíram; FALHA é problema do pipeline, não da
# dependência, e tem alerta próprio.
ESTADOS_PARADOS = frozenset({"AGUARDANDO_DEPENDENCIA", None})


def passou_do_limite(hora_limite, agora) -> bool:
    """Já passou do horário até o qual a liberação fazia sentido?

    Sem limite configurado, nunca estoura — o deadline é opt-in por decisão do
    usuário (spec §8), porque só quem conhece a janela de negócio sabe informá-lo.
    """
    if hora_limite is None:
        return False
    limite = hora_limite
    if not isinstance(limite, time):
        limite = _parse_hora(str(limite))
        if limite is None:
            return False
    atual = agora if isinstance(agora, time) else agora.time()
    return atual >= limite


def precisa_alertar_janela(hora_limite, agora, status_atual) -> bool:
    """Estourou a janela com a corrida ainda parada?

    Note que status None (corrida nem ordenada) TAMBÉM alerta: é o caso em que
    nenhum predecessor rodou o dia inteiro — exatamente o silêncio que o defeito
    5 do QA produzia.
    """
    return passou_do_limite(hora_limite, agora) and status_atual in ESTADOS_PARADOS


def detectar_divergencia(status_na_data: dict, datas_por_predecessor: dict) -> list:
    """Predecessores que concluíram, mas em OUTRA data de referência.

    É o alerta que o usuário pediu: em vez de o dependente simplesmente nunca
    liberar, dizer que o insumo existe — só que carimbado com outro dia.

    Devolve [(predecessor, data_encontrada)], ordenado, só para quem está
    pendente na data corrente.
    """
    divergentes = []
    for nome, status in sorted(status_na_data.items()):
        if status in ESTADOS_QUE_LIBERAM:
            continue
        outra = datas_por_predecessor.get(nome)
        if outra:
            divergentes.append((nome, outra))
    return divergentes


def status_dos_predecessores(hook, pipeline_name: str, data_referencia) -> dict:
    """nome do predecessor → status que vale para a liberação, naquela data.

    **Um SUCESSO na data vale, mesmo que não seja a execução mais recente.**
    É a semântica da condição OUT do Control-M: uma vez que o job terminou bem e
    produziu o insumo, a condição existe — execuções posteriores não a desfazem.

    A versão anterior olhava só a execução mais recente, e isso quebrava de um
    jeito difícil de enxergar: um pipeline com horários 08:30 e 09:00 recebe
    disparos de cron às 08:00 e 09:30 que o próprio check_agenda descarta como
    PULADO. Esse PULADO era o "mais recente" e escondia o SUCESSO das 09:00 —
    o dependente ficava esperando para sempre um predecessor que rodou duas
    vezes com sucesso.

    Sem SUCESSO na data, devolve o status mais recente (ou None se não houve
    execução nenhuma): é o que a mensagem de pendência mostra ao operador, e
    "falhou" precisa ser distinguível de "nem rodou".
    """
    linhas = hook.get_records(
        "SELECT d.depende_de, "
        "       CASE WHEN EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao s "
        "                          WHERE s.pipeline_name = d.depende_de "
        "                            AND s.data_referencia = %s AND s.status = 'SUCESSO') "
        "            THEN 'SUCESSO' "
        "            ELSE (SELECT TOP 1 e.status FROM dbo.etl_pipeline_execucao e "
        "                   WHERE e.pipeline_name = d.depende_de AND e.data_referencia = %s "
        "                   ORDER BY COALESCE(e.inicio, e.criado_em) DESC, e.id DESC) END "
        "FROM dbo.etl_pipeline_dependencia d "
        "WHERE d.pipeline_name = %s AND d.tipo = 'PIPELINE'",
        parameters=(data_referencia, data_referencia, pipeline_name))
    return {str(r[0]): (str(r[1]) if r[1] is not None else None) for r in (linhas or [])}


def dependentes_de(hook, pipeline_name: str) -> list:
    """Quem depende deste pipeline — a pergunta que o disparo faz ao concluir."""
    linhas = hook.get_records(
        "SELECT DISTINCT pipeline_name FROM dbo.etl_pipeline_dependencia "
        "WHERE depende_de = %s AND tipo = 'PIPELINE'",
        parameters=(pipeline_name,))
    return [str(r[0]) for r in (linhas or [])]


def config_do_dependente(hook, pipeline_name: str) -> dict:
    """Dados do dependente que decidem SE e QUANDO disparar."""
    linhas = hook.get_records(
        "SELECT active, CONVERT(VARCHAR(8), nao_iniciar_antes, 108) "
        "FROM dbo.etl_pipeline WHERE pipeline_name = %s",
        parameters=(pipeline_name,))
    if not linhas:
        return {"ativo": False, "nao_iniciar_antes": None}
    linha = linhas[0]
    return {"ativo": bool(linha[0]), "nao_iniciar_antes": linha[1]}
