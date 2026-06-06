from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

DAG_ID        = "etl_pipeline_register"
MSSQL_CONN_ID = "SQL14_DMDB41"

# Campos rastreados pelo audit trail (nome_conf -> coluna_db)
AUDIT_FIELDS = {
    "active":           "active",
    "scheduled_time":   "scheduled_time",
    "schedule_type":    "schedule_type",
    "schedule_hour":    "schedule_hour",
    "schedule_minute":  "schedule_minute",
    "schedule_dow":     "schedule_dow",
    "schedule_dom":     "schedule_dom",
    "envia_msg_inicio": "envia_msg_inicio",
    "envia_msg_fim":    "envia_msg_fim",
    "envia_msg_erro":   "envia_msg_erro",
    "project_name":     "project_name",
    "domain":           "domain",
    "tags":             "tags",
    "depends_on":       "depends_on",
    "criticidade":         "criticidade",
    "sla_minutos":         "sla_minutos",
    "ambiente":            "ambiente",
    "max_active_runs":     "max_active_runs",
    "retries_count":       "retries_count",
    "retry_delay_seconds": "retry_delay_seconds",
    "pool_name":           "pool_name",
    "descricao":           "descricao",
}


def _build_cron(schedule_type: str | None, hour, minute, dow, dom) -> str:
    """Converte schedule_type + parâmetros para cron expression."""
    st = (schedule_type or "daily").strip().lower()
    h = int(hour or 0)
    m = int(minute or 0)
    if st == "hourly":
        return f"{m} * * * *"
    if st == "daily":
        return f"{m} {h} * * *"
    if st == "weekly":
        d = int(dow if dow is not None else 1)
        return f"{m} {h} * * {d}"
    if st == "monthly":
        day = int(dom if dom is not None else 1)
        return f"{m} {h} {day} * *"
    return f"{m} {h} * * *"


def _get_valid_projects(hook) -> set:
    try:
        rows = hook.get_records("SELECT project_name FROM dbo.etl_project WHERE ativo=1")
        if rows:
            return {r[0] for r in rows}
    except Exception:
        pass
    return {"BI_CVP", "BI_VIDA", "BI_PRESTAMISTA", "BI_PREVIDENCIA"}


def _check_circular_dependency(hook, pipeline_name: str, depends_on_list: list[str]) -> None:
    for depends_on in depends_on_list:
        if not depends_on:
            continue
        visited: set[str] = set()
        current: str | None = depends_on
        hops = 0
        while current and hops < 50:
            if current == pipeline_name:
                raise ValueError(
                    f"Dependência circular detectada: '{pipeline_name}' → '{depends_on}' "
                    f"cria um ciclo no grafo de dependências."
                )
            if current in visited:
                break
            visited.add(current)
            row = hook.get_first(
                "SELECT depends_on FROM dbo.etl_pipeline WHERE pipeline_name = %s",
                parameters=(current,),
            )
            # depends_on may now be comma-separated; check each
            raw = (str(row[0]).strip() if row and row[0] else None)
            current = raw.split(",")[0].strip() if raw else None
            hops += 1
        print(f"[S4] Ciclo OK: '{pipeline_name}' → '{depends_on}' ({hops} salto(s))")


def _read_current_record(hook, pipeline_name: str) -> dict | None:
    """Lê o registro atual do pipeline para comparação no audit trail."""
    conn   = hook.get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            active, scheduled_time, schedule_type, schedule_hour, schedule_minute,
            schedule_dow, schedule_dom, envia_msg_inicio, envia_msg_fim, envia_msg_erro,
            project_name, domain, tags, depends_on,
            criticidade, sla_minutos, ambiente, max_active_runs, retries_count,
            retry_delay_seconds, pool_name, descricao
        FROM dbo.etl_pipeline
        WHERE pipeline_name = %s
        """,
        (pipeline_name,),
    )
    row = cursor.fetchone()
    if row is None:
        cursor.close()
        conn.close()
        return None
    cols = [d[0] for d in cursor.description]
    cursor.close()
    conn.close()
    return dict(zip(cols, row))


def _write_audit(hook, pipeline_name: str, changed_by: str, old: dict, new_vals: dict):
    """Registra em dbo.etl_pipeline_audit os campos que mudaram."""
    entries = []
    for conf_key, db_col in AUDIT_FIELDS.items():
        old_val = str(old.get(db_col, "") or "")
        new_val = str(new_vals.get(conf_key, "") or "")
        if old_val != new_val:
            entries.append((pipeline_name, changed_by, db_col, old_val, new_val))

    if not entries:
        print(f"[AUDIT] pipeline='{pipeline_name}' — nenhuma alteração detectada.")
        return

    sql = """
        INSERT INTO dbo.etl_pipeline_audit
            (pipeline_name, changed_by, field_name, old_value, new_value, changed_at)
        VALUES (%s, %s, %s, %s, %s, GETDATE())
    """
    for entry in entries:
        hook.run(sql, parameters=entry)
    print(f"[AUDIT] pipeline='{pipeline_name}' | {len(entries)} campo(s) auditado(s) por '{changed_by}'")


def registrar_pipeline(**context):
    """
    Parâmetros esperados via conf:

      pipeline_name    : str  — obrigatório
      scheduled_time   : str  — obrigatório (legado) ex: "08:00:00"
      schedule_type    : str  — hourly | daily | weekly | monthly (opcional)
      schedule_hour    : int  — 0-23 (opcional)
      schedule_minute  : int  — 0-59 (opcional)
      schedule_dow     : int  — 0=Dom..6=Sab (opcional, weekly)
      schedule_dom     : int  — 1-31 (opcional, monthly)
      active           : int  — 0 | 1  (default 1)
      envia_msg_inicio : int  — 0 | 1  (default 1)
      envia_msg_fim    : int  — 0 | 1  (default 1)
      envia_msg_erro   : int  — 0 | 1  (default 1)
      dag_criada       : int  — 0 | 1  (default 0 — gerenciado pela factory)
      project_name     : str  — BI_CVP | BI_VIDA | BI_PRESTAMISTA | BI_PREVIDENCIA
      domain           : str  — ex: Clientes, Cobrança (default 'Geral')
      tags             : str  — separadas por vírgula (default '')
      depends_on       : str  — pipeline_name(s) separados por vírgula (S4, opcional)
      changed_by       : str  — usuário que realizou a alteração (S1 audit trail)
      criticidade      : str  — Alta | Media | Baixa (default 'Media')
      sla_minutos      : int  — SLA em minutos (opcional)
      ambiente         : str  — PROD | HML | DEV (default 'PROD')
      max_active_runs  : int  — máximo de runs simultâneos (default 1)
      retries_count    : int  — número de tentativas (default 1)
      retry_delay_seconds : int — delay entre tentativas em segundos (default 300)
      pool_name        : str  — pool do Airflow (opcional)
      descricao        : str  — descrição do pipeline (opcional)
    """
    conf = context["dag_run"].conf or {}

    pipeline = conf.get("pipeline_name")
    horario  = conf.get("scheduled_time")
    if not pipeline or not horario:
        raise ValueError("conf.pipeline_name e conf.scheduled_time são obrigatórios")

    project = conf.get("project_name", "BI_CVP")

    active           = int(conf.get("active",           1))
    envia_msg_inicio = int(conf.get("envia_msg_inicio", 1))
    envia_msg_fim    = int(conf.get("envia_msg_fim",    1))
    envia_msg_erro   = int(conf.get("envia_msg_erro",   1))
    dag_criada       = int(conf.get("dag_criada",       0))
    domain           = conf.get("domain", "Geral")
    tags             = conf.get("tags", "")
    depends_on_raw   = (conf.get("depends_on") or "").strip()
    depends_on_list  = [d.strip() for d in depends_on_raw.split(",") if d.strip()] if depends_on_raw else []
    depends_on       = ",".join(depends_on_list) or None
    changed_by       = (conf.get("changed_by") or "system").strip()
    dag_start_date   = (conf.get("dag_start_date") or "").strip() or None

    schedule_type   = (conf.get("schedule_type") or None)
    schedule_hour   = conf.get("schedule_hour")
    schedule_minute = conf.get("schedule_minute")
    schedule_dow    = conf.get("schedule_dow")
    schedule_dom    = conf.get("schedule_dom")

    descricao            = (conf.get("descricao") or "").strip() or None
    criticidade          = (conf.get("criticidade") or "Media").strip()
    sla_minutos_raw      = conf.get("sla_minutos")
    sla_minutos          = int(sla_minutos_raw) if sla_minutos_raw is not None and str(sla_minutos_raw).strip() else None
    ambiente             = (conf.get("ambiente") or "PROD").strip()
    max_active_runs_raw  = conf.get("max_active_runs")
    max_active_runs      = int(max_active_runs_raw) if max_active_runs_raw is not None else 1
    retries_count_raw    = conf.get("retries_count")
    retries_count        = int(retries_count_raw) if retries_count_raw is not None else 1
    retry_delay_raw      = conf.get("retry_delay_seconds")
    retry_delay_seconds  = int(retry_delay_raw) if retry_delay_raw is not None else 300
    pool_name            = (conf.get("pool_name") or "").strip() or None

    cron = _build_cron(schedule_type, schedule_hour, schedule_minute, schedule_dow, schedule_dom)

    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)

    valid_projects = _get_valid_projects(hook)
    if project not in valid_projects:
        raise ValueError(f"project_name inválido: '{project}'. Valores aceitos: {valid_projects}")

    # ── S4: Validação de dependência circular ANTES de qualquer escrita ───
    for dep in depends_on_list:
        if dep == pipeline:
            raise ValueError(f"Pipeline não pode depender de si mesmo: depends_on='{dep}'")
    _check_circular_dependency(hook, pipeline, depends_on_list)

    # ── S1: Audit Trail — lê o estado atual ANTES do upsert ──────────────
    old_record = _read_current_record(hook, pipeline)
    is_new     = old_record is None
    if is_new:
        print(f"[AUDIT] pipeline='{pipeline}' — novo registro, criação será auditada.")

    # ── Upsert principal ──────────────────────────────────────────────────
    sql_upsert = """
    EXEC dbo.sp_etl_pipeline_upsert
        @pipeline_name    = %s,
        @scheduled_time   = %s,
        @schedule_type    = %s,
        @schedule_hour    = %s,
        @schedule_minute  = %s,
        @schedule_dow     = %s,
        @schedule_dom     = %s,
        @active           = %s,
        @envia_msg_inicio = %s,
        @envia_msg_fim    = %s,
        @envia_msg_erro   = %s,
        @dag_criada       = %s,
        @project_name     = %s,
        @domain           = %s,
        @tags             = %s
    """
    hook.run(sql_upsert, parameters=(
        pipeline, horario,
        schedule_type, schedule_hour, schedule_minute, schedule_dow, schedule_dom,
        active,
        envia_msg_inicio, envia_msg_fim, envia_msg_erro,
        dag_criada, project, domain, tags,
    ))

    # ── S4: Persiste depends_on + dag_start_date (colunas de migration) ──
    hook.run(
        "UPDATE dbo.etl_pipeline SET depends_on = %s, dag_start_date = %s, "
        "updated_at = GETDATE() WHERE pipeline_name = %s",
        parameters=(depends_on, dag_start_date, pipeline),
    )

    # ── Persiste campos avançados ─────────────────────────────────────────
    hook.run(
        "UPDATE dbo.etl_pipeline SET "
        "descricao=%s, criticidade=%s, sla_minutos=%s, ambiente=%s, "
        "max_active_runs=%s, retries_count=%s, retry_delay_seconds=%s, pool_name=%s, "
        "updated_at=GETDATE() WHERE pipeline_name=%s",
        parameters=(descricao, criticidade, sla_minutos, ambiente,
                    max_active_runs, retries_count, retry_delay_seconds, pool_name, pipeline),
    )

    # ── S1: Audit Trail — registra campos alterados APÓS o upsert ─────────
    new_vals = {
        "active":           active,
        "scheduled_time":   horario,
        "schedule_type":    schedule_type,
        "schedule_hour":    schedule_hour,
        "schedule_minute":  schedule_minute,
        "schedule_dow":     schedule_dow,
        "schedule_dom":     schedule_dom,
        "envia_msg_inicio": envia_msg_inicio,
        "envia_msg_fim":    envia_msg_fim,
        "envia_msg_erro":   envia_msg_erro,
        "project_name":     project,
        "domain":           domain,
        "tags":             tags,
        "depends_on":       depends_on,
        "criticidade":         criticidade,
        "sla_minutos":         sla_minutos,
        "ambiente":            ambiente,
        "max_active_runs":     max_active_runs,
        "retries_count":       retries_count,
        "retry_delay_seconds": retry_delay_seconds,
        "pool_name":           pool_name,
        "descricao":           descricao,
    }
    if is_new:
        # Novo pipeline: audita todos os campos como criação
        for field, val in new_vals.items():
            hook.run(
                "INSERT INTO dbo.etl_pipeline_audit "
                "(pipeline_name, changed_by, field_name, old_value, new_value, changed_at) "
                "VALUES (%s, %s, %s, %s, %s, GETDATE())",
                parameters=(pipeline, changed_by, field, None, str(val) if val is not None else ""),
            )
        print(f"[AUDIT] pipeline='{pipeline}' — criação registrada com {len(new_vals)} campo(s).")
    else:
        _write_audit(hook, pipeline, changed_by, old_record, new_vals)

    print(
        f"[OK] pipeline='{pipeline}' | horario={horario} | cron='{cron}' | project={project} | "
        f"domain={domain} | tags={tags} | depends_on={depends_on} | active={active} | "
        f"msg_inicio={envia_msg_inicio} | msg_fim={envia_msg_fim} | "
        f"msg_erro={envia_msg_erro} | dag_criada={dag_criada} | changed_by={changed_by} | "
        f"criticidade={criticidade} | sla_minutos={sla_minutos} | ambiente={ambiente} | "
        f"max_active_runs={max_active_runs} | retries_count={retries_count} | "
        f"retry_delay_seconds={retry_delay_seconds} | pool_name={pool_name}"
    )


with DAG(
    dag_id=DAG_ID,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    schedule_interval=None,
    tags=["etl", "pipeline", "cadastro"],
    access_control={"Op": {"can_read", "can_edit"}},
) as dag:
    task = PythonOperator(
        task_id="registrar_pipeline",
        python_callable=registrar_pipeline,
    )
