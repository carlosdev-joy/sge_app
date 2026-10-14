"""Leitura conservadora do Airflow para o produtor interno de alertas.

Inventário é o da definição ORIGINAL compilada, fornecido pelo reconciliador.
Nenhuma publicação atual, envelope HTTP ou status da UI constitui autoridade.
Leituras duplas detectam mudanças durante consulta; o produtor ainda precisa
reter o fence de geração ao gravar evento e tratar Clear fora da API.
"""
from copy import deepcopy
import ast
import json
from datetime import datetime
from urllib.parse import quote

from services.alert_result import aggregate_result


def _instant(value):
    if not isinstance(value, str):
        raise ValueError()
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError()
    return parsed


def attempt_warning(value, row, pipeline, run):
    """None = sem prova; False = SUCCESS comprovado; True = WARNING.

    XCom não possui chave por tentativa. Por isso run/task/try/map e ambos
    os instantes devem conferir com a TaskInstance estável da autoridade.
    """
    try:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                value = ast.literal_eval(value)
        if not isinstance(value, dict) or not isinstance(row, dict):
            return None
        if (row.get('state') != 'success' or row.get('dag_id') != pipeline
                or row.get('dag_run_id') != run
                or value.get('pipeline') != pipeline or value.get('run') != run
                or value.get('task') != row.get('task_id')):
            return None
        for proof_key, row_key in (('tryNumber', 'try_number'), ('mapIndex', 'map_index')):
            if (type(value.get(proof_key)) is not int or type(row.get(row_key)) is not int
                    or value[proof_key] != row[row_key]):
                return None
        if value['tryNumber'] < 1 or value['mapIndex'] != -1:
            return None
        start, end = _instant(row.get('start_date')), _instant(row.get('end_date'))
        if (end < start or _instant(value.get('startDate')) != start
                or _instant(value.get('endDate')) != end
                or type(value.get('statusCode')) is not int
                or value['statusCode'] not in (1, 2)):
            return None
        return value['statusCode'] == 2
    except (ValueError, TypeError, SyntaxError, OverflowError, RecursionError):
        return None


async def terminal_observation(client, pipeline, run, *, expected_tasks, processing_tasks,
                               warning_sources=None):
    """Retorna observação estável ou None; não persiste nem envia.

    Exige inventário completo (inclusive comunicação) terminal, mas agrega
    processamento e tarefas customizadas obrigatórias. Transporte lateral
    do alerta principal permanece fora desse resultado, evitando recursão. Mapeamento dinâmico ainda falha fechado.
    Warning será acrescentado exclusivamente com telemetria da tentativa exata.
    """
    expected, processing = tuple(expected_tasks), tuple(processing_tasks)
    if (not expected or not processing
            or any(not isinstance(x, str) or not x for x in expected + processing)
            or len(set(expected)) != len(expected)
            or len(set(processing)) != len(processing)
            or not set(processing).issubset(expected)
            or not isinstance(pipeline, str) or not pipeline
            or not isinstance(run, str) or not run):
        return None
    base = '/api/v1/dags/' + quote(pipeline, safe='') + '/dagRuns/' + quote(run, safe='')
    # Mapa do artefato ORIGINAL: task DataStage -> task log_end correspondente.
    # None conserva observação preliminar, que nunca autoriza publicação.
    if warning_sources is not None and (
            not isinstance(warning_sources, dict)
            or any(task not in processing or helper not in expected or helper in processing
                   or not isinstance(helper, str) for task, helper in warning_sources.items())
            or len(set(warning_sources.values())) != len(warning_sources)):
        return None

    async def get(path, **kwargs):
        response = await client.get(path, **kwargs)
        if not response.is_success:
            return None
        value = response.json()
        return value if isinstance(value, dict) else None

    async def instances():
        # Amostra paginada limitada pelo inventário original.
        # Total inconsistente e duplicatas são recusados, sem truncamento.
        rows = []
        total = None
        while total is None or len(rows) < total:
            page = await get(base + '/taskInstances', params={'limit': 100, 'offset': len(rows)})
            if page is None:
                return None
            size, entries = page.get('total_entries'), page.get('task_instances')
            if (type(size) is not int or size != len(expected)
                    or not isinstance(entries, list) or not entries
                    or len(rows) + len(entries) > size):
                return None
            total = size
            rows.extend(entries)
        ids = []
        for row in rows:
            if (not isinstance(row, dict) or row.get('dag_id') != pipeline
                    or row.get('dag_run_id') != run or type(row.get('map_index')) is not int
                    or row['map_index'] != -1
                    or not isinstance(row.get('task_id'), str)
                    or row.get('state') not in ('success', 'failed', 'upstream_failed', 'skipped', 'removed')):
                return None
            ids.append(row['task_id'])
        if len(set(ids)) != len(ids) or set(ids) != set(expected):
            return None
        return sorted(rows, key=lambda row: row['task_id'])

    try:
        before = await get(base)
        if (before is None or before.get('dag_id') != pipeline or before.get('dag_run_id') != run
                or before.get('state') not in ('success', 'failed') or not before.get('end_date')):
            return None
        first = await instances()
        if first is None:
            return None
        warnings = []
        if warning_sources is not None:
            indexed = {row['task_id']: row for row in first}
            for task, helper in warning_sources.items():
                if indexed[task]['state'] != 'success':
                    continue
                if indexed[helper]['state'] != 'success':
                    return None
                proof = await get(base + '/taskInstances/' + quote(helper, safe='')
                                  + '/xcomEntries/eoc_result_attempt')
                if (proof is None or proof.get('dag_id') != pipeline
                        or proof.get('dag_run_id') != run or proof.get('task_id') != helper
                        or proof.get('key') != 'eoc_result_attempt'):
                    return None
                warning = attempt_warning(proof.get('value'), indexed[task], pipeline, run)
                if warning is None:
                    return None
                if warning:
                    warnings.append(task)
        second = await instances()
        after = await get(base)
        if first != second or before != after:
            return None
        tasks = [(row['task_id'], row['state']) for row in first if row['task_id'] in processing]
        # Sem grafo causal original, upstream_failed/skipped/removed não
        # comprovam execução de processamento. Uma comunicação falhada pode
        # ter impedido essas tarefas; não publicar failure nem success nesse
        # caso. O produtor permanece inconclusivo até obter prova causal.
        communication_failed = any(
            row['task_id'] not in processing
            and row['state'] in ('failed', 'upstream_failed') for row in first)
        if communication_failed and not any(state == 'failed' for _, state in tasks) and any(
                state in ('upstream_failed', 'skipped', 'removed') for _, state in tasks):
            return None
        # Falha exclusiva da comunicação não contamina o resultado de
        # processamento. Estado failed sem tarefa falhada é inconclusivo.
        if before['state'] == 'failed' and not any(
                row['state'] in ('failed', 'upstream_failed') for row in first):
            return None
        result = aggregate_result('success', tasks, expected_tasks=processing,
                                  warning_tasks=warnings)
        if result is None:
            return None
        return {'pipeline': pipeline, 'run': run, 'dagState': before['state'],
                'sourceAt': before['end_date'], 'tasks': deepcopy(tasks),
                'taskInstances': deepcopy(first), 'processingResult': result,
                'warningEvidenceRequired': warning_sources is None}
    except Exception:
        # Falha fechado, sem texto privado do transporte em logs/erros.
        return None
