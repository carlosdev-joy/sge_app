from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook
from datetime import datetime

DAG_ID        = "etl_pipeline_audit_query"
MSSQL_CONN_ID = "SQL14_DMDB41"
MAX_LIMIT     = 200


def consultar_audit(**context):
    """
    Consulta o histórico de alterações de um pipeline (tabela dbo.etl_pipeline_audit).

    Parâmetros via conf:
      pipeline_name : str — obrigatório
      limit         : int — máximo de registros (default 50, máx 200)
      offset        : int — paginação (default 0)
    """
    conf          = context["dag_run"].conf or {}
    pipeline_name = (conf.get("pipeline_name") or "").strip()
    if not pipeline_name:
        raise ValueError("conf.pipeline_name é obrigatório")

    limit  = min(MAX_LIMIT, max(1, int(conf.get("limit",  50))))
    offset = max(0, int(conf.get("offset", 0)))

    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    conn   = hook.get_conn()
    cursor = conn.cursor()

    # Total
    cursor.execute(
        "SELECT COUNT(*) FROM dbo.etl_pipeline_audit WHERE pipeline_name = %s",
        (pipeline_name,),
    )
    total = cursor.fetchone()[0] or 0

    # Dados paginados
    cursor.execute(
        """
        SELECT
            changed_at,
            changed_by,
            field_name,
            old_value,
            new_value
        FROM dbo.etl_pipeline_audit
        WHERE pipeline_name = %s
        ORDER BY changed_at DESC
        OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
        """,
        (pipeline_name, offset, limit),
    )
    cols = [d[0] for d in cursor.description]
    rows = []
    for row in cursor.fetchall():
        r = dict(zip(cols, row))
        # Serializa datetime para string ISO
        if r.get("changed_at") and hasattr(r["changed_at"], "isoformat"):
            r["changed_at"] = r["changed_at"].isoformat()
        rows.append(r)

    cursor.close()
    conn.close()

    pages = max(1, -(-total // limit))  # ceil division
    result = {
        "total":  total,
        "offset": offset,
        "limit":  limit,
        "pages":  pages,
        "filters": {"pipeline_name": pipeline_name},
        "data":   rows,
    }
    print(f"[AUDIT] pipeline='{pipeline_name}' total={total} retornando={len(rows)}")
    return result


with DAG(
    dag_id=DAG_ID,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    schedule_interval=None,
    tags=["etl", "pipeline", "audit"],
    access_control={"Op": {"can_read", "can_edit"}},
) as dag:
    PythonOperator(
        task_id="consultar_audit",
        python_callable=consultar_audit,
        do_xcom_push=True,
    )
