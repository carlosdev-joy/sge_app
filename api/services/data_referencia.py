"""
api/services/data_referencia.py — a que dia de processamento uma execução
pertence (ODATE), visto da API.

PORT PURO de dags/utils/data_referencia.py — **o canônico é o de dags/**: quem
mudar a regra muda lá primeiro e espelha aqui. A cópia existe porque api/ e
dags/ são árvores de deploy separadas (o container da API não embarca dags/), e
um import cruzado quebraria no primeiro deploy parcial. Os DOIS módulos têm
teste de paridade em tests/test_malhas_f9.py — divergir a semântica faz a suíte
falhar antes de chegar em produção.

Usado pela visão de execução da Malha (F9): quando o operador abre a malha sem
pedir uma data, o servidor calcula o ODATE corrente com a hora de virada GLOBAL
de etl_app_config['dependencia_hora_virada'] — a leitura do config fica no
endpoint (api/routers/malhas.py); este módulo segue PURO: sem banco, sem
FastAPI, testável sozinho.
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

    Regra (a MESMA de dags/utils/data_referencia.py — ver teste de paridade):
      • virada 00:00 (padrão) → a data do calendário, sem deslocamento;
      • hora >= virada        → o dia SEGUINTE (já se está processando o próximo
                                dia de negócio);
      • hora <  virada        → a data do calendário.

    O caso que motivou a spec: com virada 20:00, tanto 31/07 23:30 quanto
    01/08 00:40 caem em 01/08 — as duas pontas da meia-noite são a MESMA
    corrida de negócio.
    """
    v = parse_virada(virada)
    if v == VIRADA_PADRAO:
        return momento.date()
    if momento.time() >= v:
        return momento.date() + timedelta(days=1)
    return momento.date()
