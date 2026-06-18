"""
etl_ds_malha_status.py — Varredura de status (dsjob -jobinfo) dos jobs da malha.

APARTADO: monitoramento puro, não dispara jobs nem gera DAG. A partir da malha
persistida (etl_ds_malha*), lê a lista de jobs monitoráveis, roda
`dsjob -jobinfo` para cada um via SSH (num único round-trip) e grava um snapshot
em etl_ds_malha_status. Detecta ABORTED mesmo com a SEQ ainda rodando, pegando
falhas que a SEQ não trata.

Disparado via ORQUESTRA (POST /malha-ds/{project}/scan) ou trigger manual:
  { "project": "BI_VIDA" }
"""
from __future__ import annotations

import os
import re
import sys

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook
from airflow.providers.ssh.hooks.ssh import SSHHook

DAG_ID        = "etl_ds_malha_status"
SSH_CONN_ID   = "ssh_lnxprd021"
MSSQL_CONN_ID = "SQL14_DMDB41"
DSHOME        = "/opt/IBM/InformationServer/Server/DSEngine"
LOCAL_TZ      = "America/Sao_Paulo"

# Códigos de status do dsjob -jobinfo ("Job Status : ... (n)")
_STATUS = {
    0: "RUNNING", 1: "OK", 2: "WARNING", 3: "ABORTED",
    11: "VAL_OK", 12: "VAL_WARN", 13: "VAL_FAILED",
    21: "RESET", 23: "STOPPED", 25: "NOT_RUN",
}
# Nomes de job seguros (evita injeção no shell remoto)
_JOB_RE = re.compile(r"^[A-Za-z0-9_.]+$")

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}


def _scan_names(project: str) -> list[str]:
    """Lê os nós da malha a varrer (jobs E sequences) da malha persistida — sem
    reparsear XML. Inclui sequences porque elas também têm status (ex.: 2/warning)."""
    dags_folder = os.path.dirname(os.path.abspath(__file__))
    if dags_folder not in sys.path:
        sys.path.insert(0, dags_folder)
    from utils import ds_xml_malha as M  # noqa: PLC0415

    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    nrows = hook.get_records(
        "SELECT name, kind, is_sequence, is_executor FROM dbo.etl_ds_malha_node WHERE project = %s",
        parameters=[project]) or []
    erows = hook.get_records(
        "SELECT parent, seq_order, activity, jobname, real_target, kind "
        "FROM dbo.etl_ds_malha_edge WHERE project = %s ORDER BY parent, seq_order",
        parameters=[project]) or []
    nodes = [{"name": r[0], "kind": r[1], "is_sequence": bool(r[2]),
              "is_executor": bool(r[3]), "stage_types": []} for r in nrows]
    edges = [{"parent": r[0], "seq_order": r[1], "activity": r[2],
              "jobname": r[3], "real_target": r[4], "kind": r[5]} for r in erows]
    parsed = M.from_rows(nodes, edges, project=project)
    return [j for j in M.scan_targets(parsed) if _JOB_RE.match(j or "")]


def _scan(**context):
    conf = context["dag_run"].conf or {}
    project = (conf.get("project") or "").strip()
    if not project:
        raise ValueError("project é obrigatório.")

    jobs = _scan_names(project)
    if not jobs:
        print(f"[STATUS] {project}: nenhum nó (job/sequence) na malha.")
        return {"project": project, "scanned": 0, "aborted": []}

    # Um único round-trip SSH: loop remoto chamando dsjob -jobinfo por job/sequence
    joblist = " ".join(f"'{j}'" for j in jobs)
    remote = (
        f"source {DSHOME}/dsenv >/dev/null 2>&1; "
        f"for j in {joblist}; do echo \"===JOB===$j\"; "
        f"{DSHOME}/bin/dsjob -jobinfo {project} \"$j\" 2>&1 | grep -iE 'Job Status|Status code|not found|Failed'; done"
    )
    client = SSHHook(ssh_conn_id=SSH_CONN_ID).get_conn()
    try:
        _, stdout, stderr = client.exec_command(remote, timeout=300)
        out = stdout.read().decode("utf-8", "ignore")
        err = stderr.read().decode("utf-8", "ignore")
    finally:
        client.close()

    print(f"[STATUS] {project}: varrendo {len(jobs)} nó(s).")
    print("----- saída dsjob (bruta, para diagnóstico) -----")
    print(out)
    if err.strip():
        print("----- stderr -----"); print(err)

    # Parse: blocos ===JOB===<nome> seguidos da linha "Job Status : ... (n)"
    results: dict[str, tuple] = {}
    cur = None
    for line in out.splitlines():
        if line.startswith("===JOB==="):
            cur = line[len("===JOB==="):].strip()
            results[cur] = (None, "NOT_RUN", None)
        elif cur:
            m = re.search(r"\((\d+)\)", line)
            if m and ("status" in line.lower()):
                code = int(m.group(1))
                results[cur] = (code, _STATUS.get(code, str(code)), line.strip()[:480])
            elif results.get(cur, (None,))[0] is None:
                # guarda a 1ª linha não-status (erro/diagnóstico) como info
                results[cur] = (None, "NOT_RUN", line.strip()[:480])

    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    hook.run("DELETE FROM dbo.etl_ds_malha_status WHERE project = %s", parameters=[project])
    for job, (code, label, info) in results.items():
        hook.run(
            "INSERT INTO dbo.etl_ds_malha_status (project, job_name, status_code, status_label, info, scanned_at) "
            "VALUES (%s, %s, %s, %s, %s, GETDATE())",
            parameters=[project, job, code, label, info])

    aborted = [j for j, (c, _l, _i) in results.items() if c == 3]
    warn    = [j for j, (c, _l, _i) in results.items() if c == 2]
    print(f"[STATUS] {project}: {len(results)} varrido(s). ABORTED: {aborted or '—'} | WARNING: {warn or '—'}")
    return {"project": project, "scanned": len(results), "aborted": aborted, "warning": warn}


with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Varre status (dsjob -jobinfo) dos jobs da malha e grava snapshot",
    start_date=pendulum.datetime(2026, 1, 1, tz=LOCAL_TZ),
    schedule=None,
    catchup=False,
    tags=["malha-ds", "datastage", "status", "monitor"],
    access_control={"Op": {"can_read", "can_edit"}},
) as dag:
    PythonOperator(task_id="scan", python_callable=_scan, do_xcom_push=True)
