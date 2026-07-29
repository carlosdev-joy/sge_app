"""
dags/utils/ds_logsum.py — parser da saída do `dsjob -logsum`.

Porte fiel do parser que o Console DataStage usa hoje no front
(ui-react/src/pages/DsConsole.tsx, função parseLogsum): agrupa o log em RUNS da
sequence, cada um com início, fim, resultado e os jobs filhos disparados.

Por que portar em vez de reaproveitar o que já existe em Python: o
etl_ds_monitor_centralizado só olha o run ATUAL (_current_run_lines) e conta os
filhos — ele nunca separou o log em vários runs. A supervisão precisa da série
de runs dos últimos dias para dizer se o job rodou em cada dia.

Módulo PURO: sem SSH, sem banco, sem Airflow — é o que o torna testável com
saídas reais capturadas do console (tests/test_ds_logsum_parser.py).

Formato de entrada (cada evento são 2+ linhas):

    12345 STARTED  Mon Jul 27 02:10:15 2026
    Starting Job SeqSsdVida7Peps.
    12346 INFO     Mon Jul 27 02:10:16 2026
    SeqSsdVida7Peps..JobControl (@Coord): -> (SsdVidaCarga): Job run requested

FUSO: o DataStage não carimba timezone — "Mon Jul 27 02:10:15 2026" é a hora
LOCAL do servidor Unix. O datetime devolvido é naive e representa essa hora
local, exatamente como o front já interpreta hoje. Quem compara com a janela
cadastrada (regras da supervisão) assume que servidor e aplicação vivem no mesmo
fuso — premissa registrada como risco na spec.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

# Cabeçalho do evento: "  12345 STARTED  Mon Jul 27 02:10:15 2026"
_HEADER_RE = re.compile(
    r"^\s*(\d+)\s+[A-Z]+\s+(\w{3}\s+\w{3}\s+\d{1,2}\s+[\d:]+\s+\d{4})\s*$")

# "Mon Jul 27 02:10:15 2026" → partes
_TIME_RE = re.compile(
    r"\w{3}\s+(\w{3})\s+(\d{1,2})\s+(\d{2}):(\d{2}):(\d{2})\s+(\d{4})")

_MESES = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

_INICIO_RE   = re.compile(r"^Starting Job\s")
_FIM_RE      = re.compile(r"^Finished Job\s")
_ABORT_RE    = re.compile(
    r"sequence abort requested|aborted due to|fatal error from @", re.IGNORECASE)
_FILHO_FIM_RE = re.compile(
    r"Job\s+(\S+)\s+has finished, status = (\d+)\s*\(([^)]*)\)")
_FILHO_REQ_RE = re.compile(
    r"->\s*\(([A-Za-z0-9_.]+)\):\s*Job (?:run|reset) requested", re.IGNORECASE)
_ESPERA_START_RE = re.compile(
    r"Waiting for job\s+([A-Za-z0-9_.]+)\s+to start", re.IGNORECASE)
_ESPERA_FIM_RE = re.compile(r"Waiting for job\s+(.+?)\s+to finish", re.IGNORECASE)
_NOME_SEGURO_RE = re.compile(r"^[A-Za-z0-9_.]+$")
_SOB_CONTROLE_RE = re.compile(r"Job under control finished")

# Resultados possíveis de um run — espelham o Badge do console.
OK          = "ok"
ABORTADO    = "aborted"
EXECUTANDO  = "running"
INDEFINIDO  = "indefinido"


@dataclass
class DsRun:
    """Um run da sequence extraído do logsum."""
    inicio: datetime | None
    fim: datetime | None = None
    resultado: str = EXECUTANDO
    jobs_filhos: int = 0
    primeiro_evento: int | None = None
    ultimo_evento: int | None = None
    # Texto cru do log, útil no detalhe do alerta.
    inicio_texto: str = ""
    fim_texto: str = ""
    filhos_abortados: list[str] = field(default_factory=list)
    # nome do job filho → código de status do DataStage
    #   1 = concluído, 2 = com avisos, 3 = ABORTADO, 96 = crash,
    #   97 = parado, 13 = validação falhou, -1 = disparado sem status no log.
    # É esta lista que permite descobrir o "sucesso falso": a sequence termina
    # OK enquanto um filho abortou, e o DataStage não propaga isso para cima.
    filhos: dict[str, int] = field(default_factory=dict)

    @property
    def duracao_seg(self) -> int | None:
        if not (self.inicio and self.fim):
            return None
        return max(0, int((self.fim - self.inicio).total_seconds()))


def parse_ds_time(texto: str | None) -> datetime | None:
    """"Mon Jul 27 02:10:15 2026" → datetime naive (hora local do servidor).

    Devolve None em texto ausente, mês desconhecido ou data impossível
    (31 de fevereiro num log corrompido não pode derrubar a coleta inteira)."""
    if not texto:
        return None
    m = _TIME_RE.search(texto)
    if not m:
        return None
    mes = _MESES.get(m.group(1))
    if mes is None:
        return None
    try:
        return datetime(int(m.group(6)), mes, int(m.group(2)),
                        int(m.group(3)), int(m.group(4)), int(m.group(5)))
    except ValueError:
        return None


def parse_logsum(stdout: str) -> list[DsRun]:
    """Segmenta a saída do `dsjob -logsum` em runs, do mais antigo ao mais novo.

    Best-effort, igual ao front: log truncado (o `-max` corta o começo) produz um
    run sem 'Starting Job' — esse trecho inicial é descartado, porque não dá para
    afirmar quando aquele run começou. Vale a mesma leitura do console: o que
    aparece é o que o log reteve."""
    runs: list[DsRun] = []
    atual: DsRun | None = None
    filhos: dict[str, int] | None = None   # nome → código de status (-1 = sem status)
    hora_texto = ""
    hora: datetime | None = None
    evento_id = 0

    def registrar_filho(nome: str) -> None:
        if filhos is not None and nome not in filhos:
            filhos[nome] = -1

    def fechar() -> None:
        nonlocal atual, filhos
        if atual is not None and filhos is not None:
            atual.jobs_filhos = len(filhos)
            atual.filhos = dict(filhos)
            atual.filhos_abortados = [n for n, code in filhos.items() if code == 3]
            runs.append(atual)
        atual = None
        filhos = None

    for linha in (stdout or "").split("\n"):
        cabecalho = _HEADER_RE.match(linha)
        if cabecalho:
            evento_id = int(cabecalho.group(1))
            hora_texto = cabecalho.group(2)
            hora = parse_ds_time(hora_texto)
            continue

        msg = linha.strip()
        if not msg:
            continue

        if _INICIO_RE.match(msg):
            fechar()
            atual = DsRun(inicio=hora, inicio_texto=hora_texto,
                          primeiro_evento=evento_id, ultimo_evento=evento_id)
            filhos = {}
            continue

        if atual is None or filhos is None:
            continue

        atual.ultimo_evento = evento_id

        if _FIM_RE.match(msg):
            atual.resultado = OK
            atual.fim = hora
            atual.fim_texto = hora_texto
            continue

        if _ABORT_RE.search(msg):
            atual.resultado = ABORTADO
            atual.fim = hora
            atual.fim_texto = hora_texto
            continue

        fim_filho = _FILHO_FIM_RE.search(msg)
        if fim_filho:
            filhos[fim_filho.group(1)] = int(fim_filho.group(2))
            continue

        req = _FILHO_REQ_RE.search(msg)
        if req:
            registrar_filho(req.group(1))
            continue

        espera_start = _ESPERA_START_RE.search(msg)
        if espera_start:
            registrar_filho(espera_start.group(1))
            continue

        espera_fim = _ESPERA_FIM_RE.search(msg)
        if espera_fim:
            # "Waiting for job A+B+C to finish" — pode vir truncada; só aceita
            # os pedaços que ainda parecem nome de job.
            for pedaco in espera_fim.group(1).split("+"):
                nome = pedaco.strip()
                if _NOME_SEGURO_RE.match(nome):
                    registrar_filho(nome)
            continue

        if _SOB_CONTROLE_RE.search(msg):
            if atual.fim is None:
                atual.fim = hora
                atual.fim_texto = hora_texto
            fechar()

    fechar()
    return runs


def runs_desde(runs: list[DsRun], limite: datetime) -> list[DsRun]:
    """Só os runs iniciados a partir de `limite` (a janela de 7 dias da coleta).

    Run sem início legível é descartado: sem hora não dá para atribuí-lo a um
    dia, e contá-lo como 'rodou hoje' esconderia uma falha real."""
    return [r for r in runs if r.inicio is not None and r.inicio >= limite]
