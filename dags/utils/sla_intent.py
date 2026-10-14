"""Intenção SLA atômica; legado nunca volta à fila e incerto não é reenviado.

O hook deve fazer commit de cada run antes de qualquer chamada de provider.
Payload é o cartão e a referência estável da Variable, sem credenciais.
"""
import json
from uuid import uuid4


def enqueue(hook, execution, pipeline, kind, sla, elapsed, card):
    if kind not in ('RISK', 'BREACH', 'PREDICT'):
        raise ValueError('sla_event_invalid')
    payload = json.dumps(dict(schemaVersion=1, source='etl_job_execution',
                              event=kind, destinationRef='TEAMS_WEBHOOK_URL_CVP',
                              card=card), ensure_ascii=False)
    # HOLDLOCK protege também a ausência; unique index legado é a última cerca.
    hook.run('''INSERT dbo.etl_sla_alert
        (execution_id,pipeline,alert_type,sla_minutos,elapsed_min,intent_json,delivery_state)
        SELECT %s,%s,%s,%s,%s,%s,'Pending'
        WHERE NOT EXISTS (SELECT 1 FROM dbo.etl_sla_alert WITH (UPDLOCK,HOLDLOCK)
            WHERE execution_id=%s AND pipeline=%s AND alert_type=%s)''',
        parameters=(execution, pipeline, kind, sla, elapsed, payload,
                    execution, pipeline, kind))


def drain(hook, sender, limit=50):
    # Depois de crash/timeout pode ter havido aceitação. Nunca retry automático.
    hook.run("""SET XACT_ABORT ON; BEGIN TRANSACTION;
        DECLARE @expired TABLE(id INT,token UNIQUEIDENTIFIER);
        UPDATE dbo.etl_sla_alert SET delivery_state='Unknown',
        claim_token=NULL,lease_until=NULL
        OUTPUT INSERTED.id,DELETED.claim_token INTO @expired
        WHERE delivery_state='Sending' AND lease_until<=SYSUTCDATETIME();
        UPDATE a SET outcome='Unknown',finished_at=SYSUTCDATETIME()
        FROM dbo.etl_sla_attempt a JOIN @expired e ON e.id=a.alert_id AND e.token=a.claim_token
        WHERE a.outcome IS NULL; COMMIT TRANSACTION;""")
    accepted = 0
    for _ in range(limit):
        token = str(uuid4())
        # Commit antes de rede: get_first não garante commit em todos os hooks.
        hook.run('''SET XACT_ABORT ON; BEGIN TRANSACTION;
            DECLARE @claimed TABLE(id INT,sequence INT,token UNIQUEIDENTIFIER);
            ;WITH candidate AS (
            SELECT TOP (1) * FROM dbo.etl_sla_alert WITH (UPDLOCK,READPAST,ROWLOCK)
            WHERE delivery_state='Pending' ORDER BY id)
            UPDATE candidate SET delivery_state='Sending',claim_token=%s,
                lease_until=DATEADD(SECOND,60,SYSUTCDATETIME()),attempt_count=attempt_count+1
            OUTPUT INSERTED.id,INSERTED.attempt_count,INSERTED.claim_token INTO @claimed;
            INSERT dbo.etl_sla_attempt(alert_id,sequence,claim_token)
            SELECT id,sequence,token FROM @claimed; COMMIT TRANSACTION;''', parameters=(token,))
        row = hook.get_first('''SELECT id,intent_json FROM dbo.etl_sla_alert
            WHERE claim_token=%s AND delivery_state='Sending'
            AND lease_until>SYSUTCDATETIME()''', parameters=(token,))
        if not row:
            break
        state = 'Unknown'
        try:
            document = json.loads(row[1])
            if (document['schemaVersion'] != 1
                    or document['destinationRef'] != 'TEAMS_WEBHOOK_URL_CVP'):
                state = 'Failed'
            else:
                def fence():
                    return bool(hook.get_first("""SELECT id FROM dbo.etl_sla_alert
                        WHERE id=%s AND claim_token=%s AND delivery_state='Sending'
                        AND lease_until>SYSUTCDATETIME()""",
                        parameters=(row[0], token)))
                state = sender(**document['card'], fence=fence)
                if state not in ('Accepted', 'Failed', 'Unknown'):
                    state = 'Unknown'
        except Exception:
            pass  # sem mensagens de exceção com possíveis URLs/credenciais
        hook.run('''SET XACT_ABORT ON; BEGIN TRANSACTION;
            DECLARE @state VARCHAR(16)=%s;
            DECLARE @finished TABLE(id INT,token UNIQUEIDENTIFIER);
            UPDATE dbo.etl_sla_alert WITH (UPDLOCK) SET delivery_state=@state,
            claim_token=NULL,lease_until=NULL
            OUTPUT INSERTED.id,DELETED.claim_token INTO @finished
            WHERE id=%s AND claim_token=%s AND delivery_state='Sending'
            AND lease_until>SYSUTCDATETIME();
            UPDATE a SET outcome=@state,finished_at=SYSUTCDATETIME()
            FROM dbo.etl_sla_attempt a JOIN @finished f
            ON f.id=a.alert_id AND f.token=a.claim_token
            WHERE a.outcome IS NULL; COMMIT TRANSACTION;''',
            parameters=(state, row[0], token))
        accepted += state == 'Accepted'
    return accepted
