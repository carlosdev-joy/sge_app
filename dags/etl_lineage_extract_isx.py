"""
etl_lineage_extract_isx.py — lineage ISX em lote (spec docs/spec-lineage-isx.md, F3).
=====================================================================================

A DAG ORQUESTRA e a API EXTRAI: aqui só se lê a lista de jobs mapeados em pipelines
(SQL Server, placeholders `%s`) e se chama `POST /lineage/isx/extrair` por job. Uma
credencial de DataStage, uma fila SSH, um só código de gravação (o da API). A DAG
nunca grava no banco.

Conf (dag_run.conf):
  pipeline_name  : str   — opcional; vazio = todos os pipelines com project_name
  jobs           : [str] — opcional; restringe aos jobs listados (dentro do filtro acima)
  force          : bool  — reextrai mesmo quando o `lastModified` da API não mudou
  incluir_copias : bool  — inclui jobs `CopyOf*` (excluídos por padrão)
  incluir_inativos: bool — inclui pipelines com `active = 0` (excluídos por padrão)

Só jobs com `job_type = 'datastage'` entram: os outros nós de um pipeline (http,
decisão, aguarde, shell…) não existem no DataStage e só gastariam a busca na API REST.

Configuração do Airflow (spec §8.16 — pelo AMBIENTE do worker, não pelo banco):
  AIRFLOW_CONN_ORQUESTRA_API=http://<usuario>:<senha>@orquestra-api:8000/http
      usuário de serviço do Orquestra com `acao_editar` (a API valida no Airflow e
      aplica o RBAC). Com o host na Connection, a URL da API vem dela.
  Variable ORQUESTRA_API_URL — só quando a Connection não tem host (padrão
      http://orquestra-api:8000, o mesmo da factory).

Retorno via XCom (task extrair_em_lote):
  {"total": N, "extraidos": n1, "cache": n2, "erros": [{pipeline_name, job_name, status,
   detail}], "duracao_s": s}
Erro individual não aborta o lote (fica em `erros`, e a run termina VERDE mesmo com
erros — a tela lê `erros[]`); a task só falha quando NENHUM job respondeu (API fora do
ar / credencial recusada / ISX não configurado) — aí é configuração, não lineage.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor

import pendulum
from airflow import DAG
from airflow.hooks.base import BaseHook
from airflow.models import Variable
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

DAG_ID = "etl_lineage_extract_isx"
LOCAL_TZ = "America/Sao_Paulo"
MSSQL_CONN_ID = "sql14_dmdb41"
API_CONN_ID = "orquestra_api"
API_URL_VAR = "ORQUESTRA_API_URL"
API_URL_PADRAO = "http://orquestra-api:8000"
ORIGEM = f"dag:{DAG_ID}"
MAX_WORKERS = 4          # a API tem 2 threads por worker (2 workers): 4 extrações simultâneas
TIMEOUT_JOB_S = 90       # a API responde 504 aos 60 s; margem para a fila do executor dela

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}


# ── funções puras (testáveis sem Airflow) ────────────────────────────────────

def filtrar_jobs(linhas, *, jobs=None, incluir_copias=False) -> list[dict]:
    """(pipeline_name, job_name, project_name) → dicts; aplica o filtro de jobs e a
    exclusão de cópias (`CopyOf*`). Mantém a ordem de execução do pipeline."""
    alvo = {str(j).strip().casefold() for j in (jobs or []) if str(j).strip()}
    saida = []
    for pipeline, job, projeto in linhas:
        job = str(job or "").strip()
        if not job:
            continue
        if not incluir_copias and job.lower().startswith("copyof"):
            continue
        if alvo and job.casefold() not in alvo:
            continue
        saida.append({"pipeline_name": str(pipeline or "").strip(), "job_name": job,
                      "ds_project": str(projeto or "").strip()})
    return saida


def classificar(status: int | None, corpo) -> tuple[str, str]:
    """('extraido' | 'cache' | 'erro', detalhe curto) a partir da resposta da API."""
    if status == 200 and isinstance(corpo, dict):
        return ("cache" if corpo.get("cache_hit") else "extraido"), ""
    if status is None:
        return "erro", str(corpo or "sem resposta")[:300]
    detail = corpo.get("detail") if isinstance(corpo, dict) else corpo
    return "erro", f"HTTP {status}: {str(detail or '')[:300]}"


def resumir(resultados: list[dict], duracao_s: float) -> dict:
    erros = [{"pipeline_name": r["pipeline_name"], "job_name": r["job_name"],
              "status": r.get("status"), "detail": r.get("detail", "")}
             for r in resultados if r["classe"] == "erro"]
    return {
        "total": len(resultados),
        "extraidos": sum(1 for r in resultados if r["classe"] == "extraido"),
        "cache": sum(1 for r in resultados if r["classe"] == "cache"),
        "erros": erros,
        "duracao_s": round(duracao_s, 1),
    }


# ── acesso externo (substituível nos testes) ─────────────────────────────────

def _sessao():
    import requests  # noqa: PLC0415 — existe no worker pela imagem base
    s = requests.Session()
    s.trust_env = False   # alvo interno (orquestra-api): nunca pelo proxy corporativo, o Basic iria junto
    return s


def _credencial_api() -> tuple[str, str, str]:
    """(url base, login, senha) da Connection `orquestra_api`. Com host na Connection
    (o caso do ambiente: AIRFLOW_CONN_ORQUESTRA_API), a URL vem dela — um Op do Airflow
    que edite a Variable não redireciona a credencial. Sem host, Variable, senão o padrão."""
    conn = BaseHook.get_connection(API_CONN_ID)
    login = (conn.login or "").strip()
    senha = conn.password or ""
    if not login or not senha:
        raise ValueError(f"Connection '{API_CONN_ID}' sem login/senha — cadastre o usuário de serviço do Orquestra.")
    host = (conn.host or "").strip()
    if host:
        esquema = "https" if str(conn.schema or "").lower() == "https" else "http"
        url = f"{esquema}://{host}:{conn.port or 8000}"
    else:
        url = (Variable.get(API_URL_VAR, default_var="") or "").strip().rstrip("/") or API_URL_PADRAO
    return url, login, senha


# ── tasks ────────────────────────────────────────────────────────────────────

def listar_jobs(**context) -> list[dict]:
    conf = (context.get("dag_run").conf if context.get("dag_run") else None) or {}
    pipeline = (conf.get("pipeline_name") or "").strip()
    jobs = conf.get("jobs") or []
    incluir_copias = bool(conf.get("incluir_copias"))
    incluir_inativos = bool(conf.get("incluir_inativos"))

    sql = (
        "SELECT j.pipeline_name, j.job_name, p.project_name "
        "FROM dbo.etl_pipeline_job j "
        "JOIN dbo.etl_pipeline p ON p.pipeline_name = j.pipeline_name "
        "WHERE LTRIM(RTRIM(ISNULL(p.project_name, ''))) <> '' "
        "AND LOWER(ISNULL(j.job_type, 'datastage')) = 'datastage' "
    )
    params: list = []
    if not incluir_inativos:
        sql += "AND ISNULL(p.active, 1) = 1 "
    if pipeline:
        sql += "AND j.pipeline_name = %s "
        params.append(pipeline)
    sql += "ORDER BY j.pipeline_name, j.execution_order, j.job_name"

    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    linhas = hook.get_records(sql, parameters=params) or []
    lista = filtrar_jobs(linhas, jobs=jobs, incluir_copias=incluir_copias)
    if pipeline and not lista:
        raise ValueError(
            f"Pipeline {pipeline!r}: nenhum job para extrair — confira se existe, se tem "
            "project_name e se os jobs do filtro estão mapeados nele.")
    print(f"[ISX] {len(lista)} job(s) DataStage a extrair" + (f" do pipeline {pipeline}" if pipeline else " (todos os pipelines)")
          + (f", filtro de {len(jobs)} job(s)" if jobs else "") + (", com cópias" if incluir_copias else "")
          + (", com pipelines inativos" if incluir_inativos else ""))
    return lista


def _extrair_um(sessao, url: str, auth, job: dict, forcar: bool) -> dict:
    corpo = {"pipeline_name": job["pipeline_name"], "job_name": job["job_name"],
             "force": forcar, "origem": ORIGEM}
    t0 = time.time()
    try:
        r = sessao.post(f"{url}/lineage/isx/extrair", json=corpo, auth=auth, timeout=TIMEOUT_JOB_S)
        try:
            dados = r.json()
        except ValueError:
            dados = r.text[:300]
        classe, detalhe = classificar(r.status_code, dados)
        status = r.status_code
    except Exception as e:  # noqa: BLE001 — timeout, conexão recusada…: vira erro do job
        classe, detalhe, status = "erro", f"{type(e).__name__}: {str(e)[:200]}", None
    return {**job, "classe": classe, "status": status, "detail": detalhe, "duracao_ms": int((time.time() - t0) * 1000)}


def extrair_em_lote(**context) -> dict:
    conf = (context.get("dag_run").conf if context.get("dag_run") else None) or {}
    forcar = bool(conf.get("force"))
    ti = context["ti"]
    lista = ti.xcom_pull(task_ids="listar_jobs") or []
    if not lista:
        print("[ISX] nada a fazer.")
        return resumir([], 0.0)

    url, login, senha = _credencial_api()
    auth = (login, senha)
    t0 = time.time()
    resultados: list[dict] = []
    with _sessao() as sessao, ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="isx-lote") as pool:
        for r in pool.map(lambda j: _extrair_um(sessao, url, auth, j, forcar), lista):
            resultados.append(r)
            rotulo = {"extraido": "extraído", "cache": "cache ok", "erro": "ERRO"}[r["classe"]]
            print(f"[ISX] {r['pipeline_name']}/{r['job_name']}: {rotulo} em {r['duracao_ms']} ms"
                  + (f" — {r['detail']}" if r["detail"] else ""))

    resumo = resumir(resultados, time.time() - t0)
    print(f"[ISX] resumo: {json.dumps({k: v for k, v in resumo.items() if k != 'erros'}, ensure_ascii=False)}"
          f" — {len(resumo['erros'])} erro(s)")
    if resumo["total"] and resumo["extraidos"] + resumo["cache"] == 0 \
            and all(e["status"] in (None, 401, 403, 503) for e in resumo["erros"]):
        raise RuntimeError(
            "Nenhum job respondeu: API fora do ar, credencial de serviço recusada ou lineage ISX "
            f"não configurado — {resumo['erros'][0]['detail']}")
    return resumo


with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Lineage ISX em lote: chama POST /lineage/isx/extrair por job dos pipelines",
    start_date=pendulum.datetime(2026, 1, 1, tz=LOCAL_TZ),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["orquestra", "lineage", "isx"],
    access_control={"Op": {"can_read", "can_edit"}},
) as dag:
    t_listar = PythonOperator(task_id="listar_jobs", python_callable=listar_jobs, do_xcom_push=True)
    t_extrair = PythonOperator(task_id="extrair_em_lote", python_callable=extrair_em_lote, do_xcom_push=True)
    t_listar >> t_extrair
