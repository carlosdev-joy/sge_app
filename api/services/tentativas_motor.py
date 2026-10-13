"""Tentativas do motor (Airflow) de UMA tarefa numa corrida exata.

Contexto (correção 2.21.2): a tentativa gravada em ``etl_job_execution`` é o
ciclo OPERACIONAL do Orquestra — quem a incrementa é o ``log_start`` da etapa,
que fica fora do retry automático da tarefa. Uma tarefa com ``retries=1`` que
falha duas vezes deixa ``attempt=1`` no SQL e ``try_number=2`` no Airflow. O
número SQL nunca serve de ``try_number`` do motor; este módulo monta a lista
1..n a partir do que o próprio Airflow comprova.

Semântica do Airflow 2.10+ (a imagem do projeto é 2.11.2):
- ``try_number`` da instância é a tentativa CORRENTE e é incrementado quando a
  instância é agendada (não ao terminar); ``queued``/``scheduled`` com
  ``try_number=N`` é a tentativa N ainda sem início. ``0`` = nunca agendada.
- ``GET …/taskInstances/{task}/tries`` devolve o histórico
  (``TaskInstanceHistory``, uma linha por tentativa superada) mais a instância
  corrente — exceto quando ela está ``up_for_retry``, já arquivada.
- Tarefa mapeada tem uma instância por ``map_index``; esta tela não escolhe
  índice e não mistura índices.

Nada aqui fabrica estado ou horário: tentativa sem linha do motor é contada
como lacuna (``complete=False``), nunca preenchida.
"""
from __future__ import annotations

# Estados de instância do Airflow que esta tela conhece; o resto vai cru.
ESTADOS = frozenset({
    "success", "failed", "up_for_retry", "running", "queued", "scheduled",
    "up_for_reschedule", "deferred", "skipped", "upstream_failed", "removed",
    "restarting", "shutdown",
})
# Tentativa sem início pode ter log mesmo assim quando o motor a encerrou
# (ex.: falha de worker); só estas situações justificam oferecer o log.
_COM_LOG_SEM_INICIO = frozenset({"failed", "up_for_retry", "success", "running", "restarting"})
MAX_TENTATIVAS = 10_000
_CAMPO_DATA = 40
_CAMPO_TEXTO = 255


def _texto(valor, limite=_CAMPO_TEXTO):
    return valor[:limite] if isinstance(valor, str) and valor else None


def _numero(valor):
    return valor if type(valor) is int and 1 <= valor <= MAX_TENTATIVAS else None


def _duracao(valor):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return float(valor) if 0 <= valor < 10 ** 9 else None


def _linha(row, origem):
    """Só os campos de identidade e tempo: nada de conf, rendered_fields,
    executor_config, pid ou fila vai para a tela."""
    estado = row.get("state")
    estado = estado.strip().lower()[:40] if isinstance(estado, str) and estado.strip() else None
    inicio = _texto(row.get("start_date"), _CAMPO_DATA)
    return {
        "try_number": _numero(row.get("try_number")),
        "state": estado,
        "start_date": inicio,
        "end_date": _texto(row.get("end_date"), _CAMPO_DATA),
        "duration": _duracao(row.get("duration")),
        "hostname": _texto(row.get("hostname")),
        "started": inicio is not None,
        "has_log": inicio is not None or estado in _COM_LOG_SEM_INICIO,
        "origin": origem,
    }


def _mesma_tarefa(row, dag_id, run_id, task_id):
    return (isinstance(row, dict) and row.get("dag_id") == dag_id
            and row.get("dag_run_id") == run_id and row.get("task_id") == task_id)


def montar(atual, historico, *, dag_id: str, run_id: str, task_id: str) -> dict:
    """Junta a instância corrente e o histórico do motor numa lista 1..n.

    ``atual``: corpo de ``GET …/taskInstances/{task}`` (dict) ou ``None`` quando
    o motor não tem a instância (404). ``historico``: ``task_instances`` de
    ``…/tries`` ou ``None`` quando o endpoint não existe/recusou. Linha de outra
    DAG, corrida, tarefa ou índice é descartada e contada em ``ignored``.
    """
    base = {"dag_id": dag_id, "run_id": run_id, "task_id": task_id, "source": "airflow",
            "try_number": None, "max_tries": None, "state": None, "attempts": [],
            "complete": False, "history": historico is not None, "ignored": 0}
    if atual is None:
        return {**base, "available": False, "reason": "instancia_ausente"}
    if not _mesma_tarefa(atual, dag_id, run_id, task_id):
        return {**base, "available": False, "reason": "instancia_divergente"}
    if atual.get("map_index", -1) != -1:
        return {**base, "available": False, "reason": "tarefa_mapeada"}
    corrente = _linha(atual, "instancia")
    corrente_n = atual.get("try_number")
    corrente_n = corrente_n if type(corrente_n) is int and 0 <= corrente_n <= MAX_TENTATIVAS else None
    max_tries = atual.get("max_tries")
    base = {**base, "try_number": corrente_n, "state": corrente["state"],
            "max_tries": max_tries if type(max_tries) is int and 0 <= max_tries <= MAX_TENTATIVAS else None}
    if corrente_n is None:
        return {**base, "available": False, "reason": "contador_invalido"}
    por_numero: dict[int, dict] = {}
    ignoradas = 0
    for row in historico or []:
        if not _mesma_tarefa(row, dag_id, run_id, task_id) or row.get("map_index", -1) != -1:
            ignoradas += 1
            continue
        linha = _linha(row, "historico")
        n = linha["try_number"]
        # Tentativa acima da corrente não existe para o motor; repetida fica a primeira.
        if n is None or n > corrente_n or n in por_numero:
            ignoradas += 1
            continue
        por_numero[n] = linha
    # A instância corrente é a autoridade da tentativa dela (ex.: up_for_retry
    # aparece no histórico como falha; a corrente diz que haverá nova tentativa).
    if corrente_n >= 1:
        por_numero[corrente_n] = {**corrente, "try_number": corrente_n}
    tentativas = sorted(por_numero.values(), key=lambda linha: linha["try_number"], reverse=True)
    for linha in tentativas:
        linha["current"] = linha["try_number"] == corrente_n
    return {**base, "available": True, "reason": None if corrente_n else "sem_tentativas",
            "attempts": tentativas, "ignored": ignoradas,
            "complete": set(por_numero) == set(range(1, corrente_n + 1))}
