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

import hashlib
import os
import re
import sys
from datetime import datetime, timedelta

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook
from airflow.providers.ssh.hooks.ssh import SSHHook

DAG_ID        = "etl_ds_malha_status"
AUTO_DAG_ID   = "etl_ds_malha_status_auto"
SSH_CONN_ID   = "ssh_lnxprd021"
MSSQL_CONN_ID = "SQL14_DMDB41"
DSHOME        = "/opt/IBM/InformationServer/Server/DSEngine"
LOCAL_TZ      = "America/Sao_Paulo"
TEAMS_WEBHOOK_VAR = "TEAMS_WEBHOOK_URL_CVP"   # mesmo canal do orquestra_sla_monitor

# Intervalo da varredura automática (minutos) — Variable DS_MALHA_SCAN_MINUTES
try:
    from airflow.models import Variable
    _SCAN_MIN = int(Variable.get("DS_MALHA_SCAN_MINUTES", default_var=10))
except Exception:
    _SCAN_MIN = 10

# Códigos de status do dsjob -jobinfo ("Job Status : ... (n)")
_STATUS = {
    0: "RUNNING", 1: "OK", 2: "WARNING", 3: "ABORTED",
    11: "VAL_OK", 12: "VAL_WARN", 13: "VAL_FAILED",
    21: "RESET", 23: "STOPPED", 25: "NOT_RUN",
}
# Nomes de job seguros (evita injeção no shell remoto)
_JOB_RE = re.compile(r"^[A-Za-z0-9_.]+$")

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}


def _malha_exec_id(project: str, job: str, wave) -> str:
    """ID sintético estável (cabe em VARCHAR(50/100)) p/ dedup e chave do ack/resolve."""
    h = hashlib.md5(f"{project}|{job}|{wave}".encode("utf-8")).hexdigest()[:16]
    return f"malha:{h}"


def _parse_ds_time(s: str | None):
    """Converte 'Job Start Time' do dsjob (ex.: 'Thu Jun 18 02:00:01 2026') em datetime."""
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), "%a %b %d %H:%M:%S %Y")
    except Exception:
        return None


def _teams_alert_aborts(project: str, aborts: list[dict]) -> None:
    """Posta UM card no Teams listando os jobs ABORTED novos do projeto (anti-spam)."""
    try:
        from airflow.models import Variable  # noqa: PLC0415
        webhook = Variable.get(TEAMS_WEBHOOK_VAR)
    except Exception:
        print(f"[ALERT] Variable '{TEAMS_WEBHOOK_VAR}' ausente — alerta Teams ignorado.")
        return
    import requests  # noqa: PLC0415
    facts = []
    for a in aborts[:15]:
        val = a["job"]
        if a.get("elapsed"):
            val += f" · {a['elapsed']}s"
        if a.get("wave") is not None:
            val += f" · wave {a['wave']}"
        facts.append({"title": "Job", "value": val})
    if len(aborts) > 15:
        facts.append({"title": "…", "value": f"+{len(aborts) - 15} job(s)"})
    body = [
        {"type": "TextBlock", "text": f"🚨 Falha(s) na malha — {project}", "size": "Large",
         "weight": "Bolder", "wrap": True, "color": "Attention"},
        {"type": "TextBlock",
         "text": f"{len(aborts)} job(s) ABORTED detectado(s) na varredura — fora do tratamento da sequence.",
         "wrap": True, "isSubtle": True, "spacing": "None"},
        {"type": "FactSet", "spacing": "Medium", "facts": facts},
        {"type": "TextBlock", "text": "Registrado na Gestão de Falhas (Orquestra) para assunção/resolução.",
         "wrap": True, "isSubtle": True, "size": "Small"},
    ]
    payload = {"type": "message", "attachments": [{
        "contentType": "application/vnd.microsoft.card.adaptive",
        "content": {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard", "version": "1.4", "body": body}}]}
    try:
        resp = requests.post(webhook, json=payload, timeout=15)
        print(f"[ALERT] {project}: Teams status={resp.status_code}")
    except Exception as e:
        print(f"[ALERT] {project}: Teams falhou: {e}")


def _register_aborts(hook: MsSqlHook, project: str, fields_by_job: dict) -> list[dict]:
    """Registra jobs ABORTED em etl_ds_malha_falha (dedup por project+job+wave) e
    devolve a lista dos NOVOS (para alertar uma única vez por run)."""
    new: list[dict] = []
    for job, fld in fields_by_job.items():
        if fld.get("code") != 3:   # 3 = ABORTED
            continue
        wave    = fld.get("wave")
        started = _parse_ds_time(fld.get("start"))
        elapsed = fld.get("elapsed")
        exec_id = _malha_exec_id(project, job, wave)
        exists = hook.get_first(
            "SELECT 1 FROM dbo.etl_ds_malha_falha "
            "WHERE project=%s AND job_name=%s AND ISNULL(wave_number,-1)=ISNULL(%s,-1)",
            parameters=[project, job, wave])
        if exists:
            continue
        hook.run(
            "INSERT INTO dbo.etl_ds_malha_falha "
            "(execution_id, project, pipeline, job_name, wave_number, status_code, "
            " status_label, info, started_at, elapsed_seconds) "
            "VALUES (%s, %s, %s, %s, %s, 3, 'ABORTED', %s, %s, %s)",
            parameters=[exec_id, project, project, job, wave, fld.get("info"), started, elapsed])
        new.append({"job": job, "wave": wave, "elapsed": elapsed, "exec_id": exec_id})
    return new


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


def scan_project(project: str) -> dict:
    """Varre o status (dsjob -jobinfo) de todos os nós da malha do projeto e grava snapshot."""
    jobs = _scan_names(project)
    if not jobs:
        print(f"[STATUS] {project}: nenhum nó (job/sequence) na malha.")
        return {"project": project, "scanned": 0, "aborted": []}

    # Um único round-trip SSH: loop remoto chamando dsjob -jobinfo por job/sequence
    joblist = " ".join(f"'{j}'" for j in jobs)
    remote = (
        f"source {DSHOME}/dsenv >/dev/null 2>&1; "
        f"for j in {joblist}; do echo \"===JOB===$j\"; "
        f"{DSHOME}/bin/dsjob -jobinfo {project} \"$j\" 2>&1 | "
        f"grep -iE 'Job Status|Status code|Job Start Time|Job Wave Number|Elapsed|Last Run|not found|Failed'; done"
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

    # Parse: blocos ===JOB===<nome> + linhas status/wave/start/elapsed do dsjob -jobinfo
    fields_by_job: dict[str, dict] = {}
    cur = None
    for line in out.splitlines():
        if line.startswith("===JOB==="):
            cur = line[len("===JOB==="):].strip()
            fields_by_job[cur] = {"code": None, "label": "NOT_RUN", "info": None,
                                  "wave": None, "start": None, "elapsed": None}
        elif cur:
            low = line.lower()
            m = re.search(r"\((\d+)\)", line)
            if m and "status" in low and "interim" not in low:
                code = int(m.group(1))
                fields_by_job[cur]["code"]  = code
                fields_by_job[cur]["label"] = _STATUS.get(code, str(code))
                fields_by_job[cur]["info"]  = line.strip()[:480]
            elif "wave number" in low:
                wm = re.search(r"(\d+)", line.split(":", 1)[-1])
                if wm:
                    fields_by_job[cur]["wave"] = int(wm.group(1))
            elif "start time" in low:
                fields_by_job[cur]["start"] = line.split(":", 1)[-1].strip()[:60]
            elif "elapsed" in low:
                em = re.search(r"(\d+)", line)
                if em:
                    fields_by_job[cur]["elapsed"] = int(em.group(1))
            elif fields_by_job[cur]["info"] is None:
                # guarda a 1ª linha não-status (erro/diagnóstico) como info
                fields_by_job[cur]["info"] = line.strip()[:480]

    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    hook.run("DELETE FROM dbo.etl_ds_malha_status WHERE project = %s", parameters=[project])
    for job, fld in fields_by_job.items():
        hook.run(
            "INSERT INTO dbo.etl_ds_malha_status (project, job_name, status_code, status_label, info, scanned_at) "
            "VALUES (%s, %s, %s, %s, %s, GETDATE())",
            parameters=[project, job, fld["code"], fld["label"], fld["info"]])

    # Registra ABORTED na Gestão de Falhas (dedup por run) e alerta no Teams 1x.
    new_aborts = _register_aborts(hook, project, fields_by_job)
    if new_aborts:
        _teams_alert_aborts(project, new_aborts)
        for a in new_aborts:
            hook.run("UPDATE dbo.etl_ds_malha_falha SET alerted_at=GETDATE() WHERE execution_id=%s",
                     parameters=[a["exec_id"]])

    aborted = [j for j, f in fields_by_job.items() if f["code"] == 3]
    warn    = [j for j, f in fields_by_job.items() if f["code"] == 2]
    print(f"[STATUS] {project}: {len(fields_by_job)} varrido(s). "
          f"ABORTED: {aborted or '—'} (novos: {len(new_aborts)}) | WARNING: {warn or '—'}")
    return {"project": project, "scanned": len(fields_by_job),
            "aborted": aborted, "warning": warn, "novas_falhas": len(new_aborts)}


def _scan(**context):
    """Task sob demanda: varre um projeto (conf={'project': ...})."""
    project = ((context["dag_run"].conf or {}).get("project") or "").strip()
    if not project:
        raise ValueError("project é obrigatório.")
    return scan_project(project)


def _scan_all(**context):
    """Task periódica: varre TODOS os projetos com malha importada."""
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    projects = [r[0] for r in (hook.get_records("SELECT project FROM dbo.etl_ds_malha") or [])]
    print(f"[STATUS-AUTO] varrendo {len(projects)} projeto(s): {projects or '—'}")
    out = {}
    for p in projects:
        try:
            out[p] = scan_project(p)
        except Exception as e:  # um projeto com problema não derruba os demais
            print(f"[STATUS-AUTO] erro em {p}: {e}")
            out[p] = {"erro": str(e)}
    return out


# DAG sob demanda (disparada pela API POST /malha-ds/{project}/scan)
with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Varre status (dsjob -jobinfo) dos nós da malha de um projeto",
    start_date=pendulum.datetime(2026, 1, 1, tz=LOCAL_TZ),
    schedule=None,
    catchup=False,
    tags=["malha-ds", "datastage", "status", "monitor"],
    access_control={"Op": {"can_read", "can_edit"}},
) as dag:
    PythonOperator(task_id="scan", python_callable=_scan, do_xcom_push=True)


# DAG periódica (varre todos os projetos importados a cada _SCAN_MIN minutos).
# Comece PAUSADA; despause no Airflow quando quiser ligar o monitoramento contínuo.
with DAG(
    dag_id=AUTO_DAG_ID,
    default_args=default_args,
    description="Varredura periódica de status da malha (todos os projetos importados)",
    start_date=pendulum.datetime(2026, 1, 1, tz=LOCAL_TZ),
    schedule=timedelta(minutes=_SCAN_MIN),
    catchup=False,
    max_active_runs=1,
    tags=["malha-ds", "datastage", "status", "monitor", "auto"],
    access_control={"Op": {"can_read", "can_edit"}},
) as dag_auto:
    PythonOperator(task_id="scan_all", python_callable=_scan_all, do_xcom_push=True)
