"""Agregação de observações Airflow; não aceita envelopes como autoridade.

O reconciliador deve ler DagRun e TaskInstances da mesma corrida/geração.
Este módulo puro não consulta publicação atual nem ativa o produtor.
"""
from __future__ import annotations


def aggregate_result(dag_state, tasks, *, expected_tasks, warning_tasks=()):
    """Resultado terminal somente com inventário completo e sem estados abertos.

    ``warning_tasks`` contém ids comprovados pelo registro de execução dos jobs,
    nunca falhas de comunicação. Clear reabre a corrida: estados não terminais
    invalidam o resultado anterior, inclusive se o DagRun ainda diz success.
    Ausência, duplicatas e estados desconhecidos falham fechado.
    """
    expected = tuple(expected_tasks)
    observed = tuple(tasks)
    warnings = tuple(warning_tasks)
    if (not expected or any(not isinstance(x, str) or not x for x in expected)
            or len(set(expected)) != len(expected)):
        return None
    if any(not isinstance(row, (tuple, list)) or len(row) != 2 for row in observed):
        return None
    ids = [row[0] for row in observed]
    if (any(not isinstance(x, str) for x in ids)
            or len(set(ids)) != len(ids) or set(ids) != set(expected)):
        return None
    if any(not isinstance(x, str) or x not in expected for x in warnings):
        return None
    states = [row[1] for row in observed]
    terminal = ('success', 'failed', 'upstream_failed', 'skipped', 'removed')
    if any(state not in terminal for state in states):
        return None
    if dag_state == 'failed':
        return 'failure'
    if dag_state != 'success':
        return None
    # Uma folha all_done pode ter sucesso apesar de falha em tarefa anterior.
    if any(state in ('failed', 'upstream_failed') for state in states):
        return 'failure'
    successful = {task_id for task_id, state in observed if state == 'success'}
    if not successful or any(task_id not in successful for task_id in warnings):
        return None
    return 'warning' if warnings else 'success'
