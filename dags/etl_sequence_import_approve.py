"""
etl_sequence_import_approve.py
==============================
DAG de aprovação da importação de sequence DataStage.

Recebe o import_id de uma importação com status 'pendente_aprovacao',
atualiza o nome do pipeline e o schedule, e chama a stored procedure
sp_etl_seq_import_approve que move os dados do staging para as
tabelas principais (etl_pipeline, etl_pipeline_job, etl_job_lineage)
em uma única transação.

Após a aprovação, dispara a DAG etl_dag_factory para gerar o DAG
Airflow do pipeline automaticamente.

Entrada via conf:
  import_id              : int   — ID retornado pelo parse
  reviewed_by            : str   — matrícula/usuário que aprovou
  pipeline_name_override : str   (opcional) — nome final do pipeline
  schedule_type          : str   (opcional) — hourly|daily|weekly|monthly
  schedule_hour          : int   (opcional)
  schedule_minute        : int   (opcional)
  schedule_dow           : int   (opcional) — 0=Dom ... 6=Sab
  schedule_dom           : int   (opcional) — 1-31
"""

from __future__ import annotations

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

DAG_ID        = "etl_sequence_import_approve"
MSSQL_CONN_ID = "SQL14_DMDB41"
LOCAL_TZ      = "America/Sao_Paulo"

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}


def _build_cron(schedule_type: str, hour: int, minute: int,
                dow: int | None, dom: int | None) -> str | None:
    """Converte schedule_type + parâmetros para cron expression."""
    h = max(0, min(23, int(hour   or 0)))
    m = max(0, min(59, int(minute or 0)))

    if schedule_type == "hourly":
        return f"{m} * * * *"
    elif schedule_type == "daily":
        return f"{m} {h} * * *"
    elif schedule_type == "weekly":
        d = max(0, min(6, int(dow or 1)))
        return f"{m} {h} * * {d}"
    elif schedule_type == "monthly":
        day = max(1, min(31, int(dom or 1)))
        return f"{m} {h} {day} * *"
    return None


def approve_sequence(**context):
    conf         = context["dag_run"].conf or {}
    import_id    = int(conf.get("import_id", 0))
    reviewed_by  = (conf.get("reviewed_by") or "system").strip()

    if not import_id:
        raise ValueError("Parâmetro 'import_id' é obrigatório.")

    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)

    # 1. Verificar se a importação existe e está pendente
    row = hook.get_first("""
        SELECT id, seq_name, project_name, status
        FROM dbo.etl_seq_import
        WHERE id = %s
    """, parameters=[import_id])

    if not row:
        raise ValueError(f"Importação id={import_id} não encontrada.")
    if row[3] != "pendente_aprovacao":
        raise ValueError(
            f"Importação id={import_id} está com status '{row[3]}' "
            f"e não pode ser aprovada."
        )

    seq_name     = row[1]
    project_name = row[2]
    print(f"[SEQ_APPROVE] Aprovando: {seq_name} (id={import_id})")

    # 2. Atualizar pipeline_name_override e schedule se fornecidos
    pipeline_override = (conf.get("pipeline_name_override") or "").strip() or None
    schedule_type     = (conf.get("schedule_type") or "").strip() or None

    if pipeline_override or schedule_type:
        cron = None
        if schedule_type:
            cron = _build_cron(
                schedule_type,
                conf.get("schedule_hour",   6),
                conf.get("schedule_minute", 0),
                conf.get("schedule_dow"),
                conf.get("schedule_dom"),
            )

        update_parts = []
        update_params = []

        if pipeline_override:
            update_parts.append("pipeline_name_override = %s")
            update_params.append(pipeline_override)
        if schedule_type:
            update_parts.append("schedule_type = %s")
            update_params.append(schedule_type)
            if cron:
                update_parts.append("schedule_cron = %s")
                update_params.append(cron)
                update_parts.append("schedule_hour   = %s")
                update_params.append(int(conf.get("schedule_hour", 6)))
                update_parts.append("schedule_minute = %s")
                update_params.append(int(conf.get("schedule_minute", 0)))
            if conf.get("schedule_dow") is not None:
                update_parts.append("schedule_dow = %s")
                update_params.append(int(conf.get("schedule_dow")))
            if conf.get("schedule_dom") is not None:
                update_parts.append("schedule_dom = %s")
                update_params.append(int(conf.get("schedule_dom")))

        if update_parts:
            update_params.append(import_id)
            hook.run(
                f"UPDATE dbo.etl_seq_import SET {', '.join(update_parts)} WHERE id = %s",
                parameters=update_params
            )
            print(f"[SEQ_APPROVE] Metadados atualizados: {', '.join(update_parts)}")

    # 3. Executar a stored procedure de aprovação (transação no banco)
    hook.run(
        "EXEC dbo.sp_etl_seq_import_approve %s, %s",
        parameters=[import_id, reviewed_by]
    )
    print(f"[SEQ_APPROVE] sp_etl_seq_import_approve executada com sucesso")

    # 4. Recuperar o pipeline_name final para disparar a factory
    pipeline_name_row = hook.get_first("""
        SELECT COALESCE(pipeline_name_override, seq_name)
        FROM dbo.etl_seq_import
        WHERE id = %s
    """, parameters=[import_id])
    pipeline_name = pipeline_name_row[0] if pipeline_name_row else None

    # 5. Disparar etl_dag_factory para gerar o DAG Airflow automaticamente
    if pipeline_name:
        try:
            from airflow.api.client.local_client import Client  # noqa: PLC0415
            client = Client(None, None)
            client.trigger_dag(
                dag_id="etl_dag_factory",
                run_id=f"import_{import_id}",
                conf={"pipeline_name": pipeline_name},
            )
            print(f"[SEQ_APPROVE] etl_dag_factory disparada para '{pipeline_name}'")
        except Exception as exc:
            # Não falhar se a factory não estiver disponível — o usuário pode disparar manualmente
            print(f"[SEQ_APPROVE] Aviso: não foi possível disparar etl_dag_factory: {exc}")

    result = {
        "import_id":     import_id,
        "pipeline_name": pipeline_name,
        "project_name":  project_name,
        "status":        "aprovado",
        "reviewed_by":   reviewed_by,
    }
    print(f"[SEQ_APPROVE] Pipeline '{pipeline_name}' importado com sucesso!")
    return result


# ── DAG definition ────────────────────────────────────────────────
with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Aprova importação de sequence: move staging → tabelas principais",
    start_date=pendulum.datetime(2024, 1, 1, tz=LOCAL_TZ),
    schedule=None,
    catchup=False,
    tags=["etl", "import", "sequence", "approve"],
    access_control={"Op": {"can_read", "can_edit"}},
) as dag:

    PythonOperator(
        task_id="approve_sequence",
        python_callable=approve_sequence,
        do_xcom_push=True,
    )
