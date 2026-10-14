"""Propriedade do alerta principal por corrida, nunca por publicação atual.

A reserva API grava ciclo e snapshot na mesma transação antes de disparar
Airflow. Runs antigos não são matriculados no polling. O legado só emite
quando a ausência de matrícula é confirmada; erro de leitura fecha o envio,
sem falhar processamento ou retarget para uma corrida recente.
"""
import hashlib
import json


def principal_owner(hook, pipeline, run):
    if (not isinstance(pipeline, str) or not pipeline or len(pipeline) > 200
            or not isinstance(run, str) or not run or len(run) > 300):
        return 'unavailable'
    try:
        schema = hook.get_first(
            "SELECT OBJECT_ID('dbo.etl_alert_cycle','U'),"
            "OBJECT_ID('dbo.etl_alert_run_snapshot','U')")
        if not schema or len(schema) != 2:
            return 'unavailable'
        if not all(schema):
            return 'unavailable'
        row = hook.get_first(
            'SELECT s.snapshot_json,s.snapshot_hash FROM dbo.etl_alert_cycle c '
            'LEFT JOIN dbo.etl_alert_run_snapshot s ON s.run_key=c.run_key '
            'WHERE c.pipeline_name=%s COLLATE Latin1_General_100_BIN2 '
            'AND c.run_id=%s COLLATE Latin1_General_100_BIN2',
            parameters=(pipeline, run))
        if row is None:
            return 'legacy'
        encoded, digest = row
        if not isinstance(encoded, str) or hashlib.sha256(encoded.encode()).hexdigest() != digest:
            return 'unavailable'
        snapshot = json.loads(encoded)
        if (not isinstance(snapshot, dict) or not snapshot.get('policyRevision')
                or not isinstance(snapshot.get('policy'), dict)):
            return 'unavailable'
        # Matrícula dry-run observa sem retirar comunicações reais legadas.
        # Modo é imutável por corrida; expirar autorização não devolve ownership
        # ao legado (poderia duplicar envio que já foi aceito).
        mode = snapshot.get('deliveryMode')
        if mode is None:
            return 'legacy'
        return 'outbox' if mode == 'operational-test' else 'unavailable'
    except Exception:
        # Não copiar erro driver, JSON, destinatários ou credenciais para logs.
        return 'unavailable'
