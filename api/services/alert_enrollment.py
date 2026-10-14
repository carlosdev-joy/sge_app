"""Matrícula interna atômica; não ativa coorte, backfill ou transporte.

O chamador deve fornecer a versão reservada ORIGINAL e inventário produzido
pelo compilador dessa versão, antes do primeiro POST de execução. A mesma
transação deve cercar reserva/cutover; esta função nunca faz commit.
"""
import hashlib
import json
from uuid import UUID

from services.alert_cycle import locked_cycle, conflict, unavailable
from services.pipeline_alerts import captured_policy


def snapshot(version_id, definition, *, expected_tasks, processing_tasks, warning_sources=None, delivery_mode=None):
    """Documento canônico independente de mutações posteriores no draft."""
    try:
        version = str(UUID(str(version_id)))
    except (ValueError, TypeError, AttributeError):
        raise conflict('alert_enrollment_version') from None
    captured = captured_policy(definition, version)
    if captured['mode'] == 'legacy':
        return None
    expected, processing = expected_tasks, processing_tasks
    if (not isinstance(expected, (list, tuple)) or not expected
            or not isinstance(processing, (list, tuple)) or not processing):
        raise conflict('alert_enrollment_inventory')
    for tasks in (expected, processing):
        if (any(not isinstance(x, str) or not x or len(x) > 250
                or any(ord(c) < 32 or ord(c) == 127 for c in x) for x in tasks)
                or len(set(tasks)) != len(tasks)):
            raise conflict('alert_enrollment_inventory')
    if not set(processing).issubset(expected):
        raise conflict('alert_enrollment_inventory')
    document = {'versionId': version, 'policyRevision': captured['policyRevision'],
                'policy': captured['policy'], 'expectedTasks': sorted(expected),
                'processingTasks': sorted(processing)}
    if delivery_mode is not None:
        if delivery_mode != 'operational-test':
            raise conflict('alert_enrollment_delivery_mode')
        document['deliveryMode'] = delivery_mode
    if warning_sources is not None:
        if (not isinstance(warning_sources, dict)
                or any(task not in processing or helper not in expected or helper in processing
                       or not isinstance(helper, str) for task, helper in warning_sources.items())
                or len(set(warning_sources.values())) != len(warning_sources)):
            raise conflict('alert_enrollment_inventory')
        document['warningSources'] = warning_sources
    try:
        encoded = json.dumps(document, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':'))
        digest = hashlib.sha256(encoded.encode()).hexdigest()
    except (ValueError, UnicodeError, TypeError):
        raise conflict('alert_enrollment_inventory') from None
    return encoded, digest


def enroll_reserved(cur, pipeline, run, version_id, definition, *,
                    expected_tasks, processing_tasks, warning_sources=None, delivery_mode=None):
    """Primitive transacional: novo ou replay idêntico, nunca retarget.

    Não é endpoint nem prova de origem: o produtor ainda precisa ligar a
    reserva original ao compilador. Não chamar em polling ou para runs antigos.
    Retorna False para política legada; não cria ciclo nesses runs.
    """
    original = snapshot(version_id, definition, expected_tasks=expected_tasks,
                        processing_tasks=processing_tasks, warning_sources=warning_sources, delivery_mode=delivery_mode)
    cycle = locked_cycle(cur, pipeline, run)
    if original is None:
        if cycle is not None:
            raise conflict('alert_enrollment_original_conflict')
        return False
    encoded, digest = original
    schema = cur.execute("SELECT OBJECT_ID('dbo.etl_alert_run_snapshot','U')").fetchone()
    if not schema or not schema[0]:
        raise unavailable()
    # locked_cycle retém applock inclusive quando o ciclo ainda não existe.
    from services.alert_cycle import run_key
    key = run_key(pipeline, run)
    stored = cur.execute(
        "SELECT snapshot_json,snapshot_hash FROM dbo.etl_alert_run_snapshot "
        "WITH (UPDLOCK) WHERE run_key=?", (key,)).fetchone()
    if cycle is not None:
        if not stored or stored[0] != encoded or stored[1] != digest:
            raise conflict('alert_enrollment_original_conflict')
        return True
    if stored:
        raise conflict('alert_enrollment_original_conflict')
    cur.execute("INSERT dbo.etl_alert_cycle (run_key,pipeline_name,run_id) VALUES (?,?,?)",
                (key, pipeline, run))
    cur.execute("INSERT dbo.etl_alert_run_snapshot (run_key,snapshot_json,snapshot_hash) "
                "VALUES (?,?,?)", (key, encoded, digest))
    return True


def compiled_inventory(source, markers):
    """Lê o artefato da factory sem importar/executar código Airflow.

    Aceita só o formato estático emitido hoje. Novas construções dinâmicas
    exigem contrato novo, em vez de inventário incompleto silencioso.
    """
    import ast
    try:
        tree = ast.parse(source)
        captured = [node.value for node in tree.body if isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'WORKSPACE_MARKERS'
                            for t in node.targets)]
        if len(captured) != 1 or ast.literal_eval(captured[0]) != markers:
            raise ValueError()
        dags = [node for node in tree.body if isinstance(node, ast.With)
                and len(node.items) == 1
                and isinstance(node.items[0].context_expr, ast.Call)
                and isinstance(node.items[0].context_expr.func, ast.Name)
                and node.items[0].context_expr.func.id == 'DAG']
        if len(dags) != 1:
            raise ValueError()
        expected, processing = [], []
        for statement in dags[0].body:
            if isinstance(statement, ast.FunctionDef):
                # Helpers locais emitidos pela factory não criam operadores.
                if any(isinstance(n, ast.keyword) and n.arg == 'task_id'
                       for n in ast.walk(statement)):
                    raise ValueError()
                continue
            if (isinstance(statement, ast.Assign)
                    and isinstance(statement.value, (ast.List, ast.Tuple))
                    and all(isinstance(n, ast.Name) for n in statement.value.elts)):
                continue
            if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.BinOp):
                # Arestas estáticas da factory, sem criação de tasks em expressões.
                if any(isinstance(n, ast.Call) for n in ast.walk(statement)):
                    raise ValueError()
                continue
            if not isinstance(statement, ast.Assign) or not isinstance(statement.value, ast.Call):
                raise ValueError()
            call = statement.value
            if not isinstance(call.func, ast.Name) or any(k.arg is None for k in call.keywords):
                raise ValueError()
            kwargs = {k.arg: k.value for k in call.keywords}
            task = ast.literal_eval(kwargs['task_id'])
            if not isinstance(task, str) or not task or task in expected:
                raise ValueError()
            expected.append(task)
            fn = kwargs.get('python_callable')
            communication = (isinstance(fn, ast.Name) and
                fn.id in {'teams_start', 'teams_end', 'teams_error', '_flow_close'})
            # EmailOperator e _notify_* são tarefas customizadas do pipeline.
            # O próprio operador preserva Teams tolerante por padrão; se a
            # task falha, o alerta principal deve refletir essa falha.
            # Auxiliares de agenda/telemetria têm trigger rules próprias e
            # dependências das comunicações; nunca são resultado da carga.
            auxiliary = isinstance(fn, ast.Name) and fn.id in {
                'check_agenda', '_registrar_sucesso', '_registrar_falha',
                'log_start', 'log_end'}
            if not communication and not auxiliary:
                processing.append(task)
        if not expected or not processing:
            raise ValueError()
        return expected, processing
    except (ValueError, TypeError, KeyError, SyntaxError, RecursionError):
        raise conflict('alert_enrollment_artifact') from None


def validate_reprocess_snapshot(cur, pipeline, run, version_id, definition):
    """Confere a coorte original sob lock, sem rematricular ou fazer commit.

    Preparação para o rerun: não autoriza POST nem substitui begin_clear.
    O chamador deve reservar o Clear antes de modificar parâmetros do run.
    """
    cycle = locked_cycle(cur, pipeline, run)
    if cycle is None:
        raise conflict('alert_enrollment_legacy_replay')
    key, _, pending = cycle
    if pending is not None:
        raise conflict('alert_clear_pending')
    row = cur.execute(
        "SELECT snapshot_json,snapshot_hash FROM dbo.etl_alert_run_snapshot "
        "WITH (UPDLOCK) WHERE run_key=?", (key,)).fetchone()
    if not row:
        raise conflict('alert_enrollment_original_conflict')
    try:
        document = json.loads(row[0])
        original = snapshot(version_id, definition,
                            expected_tasks=document['expectedTasks'],
                            processing_tasks=document['processingTasks'],
                            warning_sources=document.get('warningSources'), delivery_mode=document.get('deliveryMode'))
    except (ValueError, TypeError, KeyError):
        raise conflict('alert_enrollment_original_conflict') from None
    if original is None or original != (row[0], row[1]):
        raise conflict('alert_enrollment_original_conflict')
    return document


def enroll_command(cur, pipeline, run, token, *, existing=False):
    """Reserva e snapshot compartilham a transação externa de reserve_run.

    Origem é o comando já reservado, nunca a publicação atual ou pedido HTTP.
    Reprocessamento matriculado espera integração Clear e falha fechado.
    """
    import os
    from pathlib import Path
    row = cur.execute(
        "SELECT c.version_id,c.content_hash,c.active_hash,c.tipo,v.definition_json "
        "FROM dbo.etl_workspace_comando c WITH(UPDLOCK,HOLDLOCK) "
        "JOIN dbo.etl_workspace_versao v ON v.version_id=c.version_id "
        "WHERE c.pipeline_name=? AND c.run_id=? AND c.command_token=?",
        (pipeline, run, token)).fetchone()
    if not row:
        raise conflict('alert_enrollment_command')
    definition = json.loads(row[4])
    if captured_policy(definition, str(row[0]))['mode'] == 'legacy':
        # Ausência de política nunca permite retarget de corrida matriculada.
        return enroll_reserved(cur, pipeline, run, row[0], definition,
                               expected_tasks=[], processing_tasks=[])
    # Replay não é disparo original. Comandos anteriores à coorte podem já
    # ter emitido pelo legado; matriculá-los agora duplicaria o cutover.
    if existing and locked_cycle(cur, pipeline, run) is None:
        raise conflict('alert_enrollment_legacy_replay')
    if existing:
        # Replay usa somente definição/mode da corrida original; autorização
        # de teste e artefato atuais não podem mudar um comando idempotente.
        return validate_reprocess_snapshot(cur, pipeline, run, row[0], definition)
    if row[3] == 'reprocess':
        # Procedure172 já exige versão/hash originais da execução. Confere o
        # snapshot sob o mesmo lock, sem matrícula nem artefato atual.
        return validate_reprocess_snapshot(cur, pipeline, run, row[0], definition)
    if row[3] != 'execute':
        raise conflict('alert_enrollment_command')
    try:
        metadata = definition['metadata']['legacyPipeline']
        root = Path(os.getenv('WORKSPACE_DAG_ROOT', os.getenv('DAGS_FOLDER', '/opt/airflow/dags'))).resolve() / 'generated'
        parts = [metadata['project_name'], metadata['domain'], pipeline]
        if any(not isinstance(x, str) or x in {'.', '..'} or not x
               or '/' in x or chr(92) in x for x in parts):
            raise ValueError()
        path = (root / parts[0] / parts[1] / (parts[2] + '.py')).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError()
        source = path.read_text()
    except (KeyError, TypeError, ValueError, OSError, UnicodeError):
        raise conflict('alert_enrollment_artifact') from None
    expected, processing = compiled_inventory(source, {
        'workspace_version_id': str(row[0]).lower(),
        'workspace_content_hash': row[1], 'workspace_projection_hash': row[2]})
    from services import alert_runtime
    mode = {'delivery_mode': 'operational-test'} if alert_runtime.authorization() is not None else {}
    return enroll_reserved(cur, pipeline, run, row[0], definition,
                           expected_tasks=expected, processing_tasks=processing,
                           warning_sources=compiled_warning_sources(source, expected, processing), **mode)


def compiled_warning_sources(source, expected, processing):
    """Vínculo estático original log_end -> operador DS, nunca nome presumido.

    Só tasks realmente emparelhadas ao log_end da factory podem fornecer
    códigos DataStage; tasks SQL/customizadas não inventam Warning.
    """
    import ast
    try:
        tree = ast.parse(source)
        result = {}
        datastage = set()
        helpers = []
        for node in tree.body:
            if not isinstance(node, ast.With):
                continue
            for statement in node.body:
                if not isinstance(statement, ast.Assign) or not isinstance(statement.value, ast.Call):
                    continue
                call = statement.value
                kwargs = {k.arg: k.value for k in call.keywords}
                if isinstance(call.func, ast.Name) and call.func.id == 'DataStageOperator':
                    datastage.add(ast.literal_eval(kwargs['task_id']))
                fn = kwargs.get('python_callable')
                if not isinstance(fn, ast.Name) or fn.id != 'log_end':
                    continue
                helper = ast.literal_eval(kwargs['task_id'])
                task = ast.literal_eval(kwargs['op_kwargs'])['upstream_task_id']
                helpers.append((task, helper))
        for task, helper in helpers:
            if task not in datastage:
                continue
            if (task not in processing or helper not in expected or helper in processing
                    or task in result or helper in result.values()):
                raise ValueError()
            result[task] = helper
        if set(result) != datastage:
            raise ValueError()
        return result
    except (ValueError, KeyError, TypeError, SyntaxError, RecursionError):
        raise conflict('alert_enrollment_artifact') from None
