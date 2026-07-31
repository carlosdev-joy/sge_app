"""
dags/utils/data_referencia.py — a que dia de processamento uma execução pertence.

O PROBLEMA (caso real levantado pelo usuário em 2026-07-31): um pipeline começa
31/07 às 23:30 e o seguinte começa 01/08 às 00:40. Pelo relógio são dias
diferentes; pelo negócio são a MESMA corrida. Sem um nome para isso, não há como
dizer se duas execuções "combinam" — e a dependência entre elas vira adivinhação.

A SOLUÇÃO é o `ODATE` do Control-M, aqui chamado de **data de referência**: um
carimbo de dia de processamento que NÃO é a data do relógio. Ele nasce de duas
regras, nesta ordem de precedência:

  1. **Herança** — quem é disparado por dependência NÃO recalcula nada: recebe a
     data de referência do predecessor. É o que mantém a corrida inteira coerente
     quando ela atravessa a meia-noite, e é como o Control-M carimba condições
     com o ODATE de quem as gerou. (A herança acontece em quem chama, via
     `conf['data_referencia']` — este módulo só cobre o cálculo.)

  2. **Virada do dia** — para quem roda por agenda, a data sai do relógio
     deslocado pela hora de virada configurada.

Módulo PURO: sem banco, sem Airflow. Testável sozinho.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

# Preserva o comportamento anterior à migration 067: sem virada configurada, a
# data de referência é simplesmente a data do calendário.
VIRADA_PADRAO = time(0, 0)


def parse_virada(valor) -> time:
    """Aceita 'HH:MM', 'HH:MM:SS', time ou None → time.

    Entrada inválida devolve a virada padrão em vez de estourar: um valor
    estranho em etl_app_config não pode derrubar o cálculo de TODOS os
    pipelines — o pior caso aceitável é manter o comportamento de hoje.
    """
    if valor is None or valor == "":
        return VIRADA_PADRAO
    if isinstance(valor, time):
        return valor
    if isinstance(valor, datetime):
        return valor.time()
    texto = str(valor).strip()
    for formato in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(texto, formato).time()
        except ValueError:
            continue
    return VIRADA_PADRAO


def calcular(momento: datetime, virada=None) -> date:
    """Data de referência de uma execução iniciada em `momento`.

    Regra:
      • virada 00:00 (padrão) → a data do calendário, sem deslocamento;
      • hora >= virada        → o dia SEGUINTE (já se está processando o próximo
                                dia de negócio);
      • hora <  virada        → a data do calendário.

    Exemplos (o caso que motivou a spec):

        >>> calcular(datetime(2026, 7, 31, 23, 30))                 # virada 00:00
        datetime.date(2026, 7, 31)
        >>> calcular(datetime(2026, 7, 31, 23, 30), time(20, 0))    # virada 20:00
        datetime.date(2026, 8, 1)
        >>> calcular(datetime(2026, 8, 1, 0, 40), time(20, 0))
        datetime.date(2026, 8, 1)

    Repare no último: com virada 20:00, tanto 31/07 23:30 quanto 01/08 00:40 caem
    em 01/08 — que é exatamente o "mesma corrida" que o usuário descreveu.
    """
    v = parse_virada(virada)
    if v == VIRADA_PADRAO:
        return momento.date()
    if momento.time() >= v:
        return momento.date() + timedelta(days=1)
    return momento.date()


def mesma_corrida(data_a, data_b) -> bool:
    """As duas execuções pertencem ao mesmo dia de processamento?

    É a pergunta que libera (ou não) um pipeline dependente. Existe como função
    nomeada porque a comparação aparece em vários pontos e um `==` solto no meio
    da regra não diz o que significa.
    """
    return data_a is not None and data_b is not None and data_a == data_b
