"""
ORQUESTRA — Importação de Sequence (v1.0)

DAG: etl_sequence_import_parse
Objetivo: receber um arquivo .dsx (salvo em DSX_IMPORT_DIR), identificar a SEQUENCE,
extrair a ordem de execução dos jobs e pré-extrair lineage via DSXEngine.

Entrada (dag_run.conf):
  dsx_filename: str (obrigatório)  # nome do arquivo em DSX_IMPORT_DIR
  project_name: str (opcional)     # BI_CVP etc (fallback)
  domain: str (opcional)
  imported_by: str (opcional)

Saída (XCom return_value):
  {
    import_id, dsx_filename, project_name,
    seq_name_raw, seq_name,
    pipeline_name_suggest,
    jobs: [
      { import_job_id, execution_order, job_name_ds, job_name_orq, ignored, lineage_count }
    ]
  }
"""

from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

from dags.utils.dsx_engine import DSXEngine


MSSQL_CONN_ID = os.environ.get("MSSQL_CONN_ID", "SQL14_DMDB41")
DSX_IMPORT_DIR = os.environ.get("DSX_IMPORT_DIR", "/opt/airflow/dsx/imports")

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}


def _decode_dsx_text(s: str) -> str:
    """
    Decodifica escapes do DataStage no formato: \\(E7) = ç (CP1252).
    """
    def repl(m):
        b = int(m.group(1), 16)
        return bytes([b]).decode("cp1252", errors="ignore")

    return re.sub(r"\\\(([0-9A-Fa-f]{2})\)", repl, s or "")


def _suggest_pipeline_name(seq_name: str) -> str:
    """
    Sugere pipeline_name no padrão ORQUESTRA (A-Z 0-9 _).
    """
    if not seq_name:
        return ""
    base = unicodedata.normalize("NFKD", seq_name)
    base = "".join(ch for ch in base if not unicodedata.combining(ch))
    base = base.replace(" ", "_").replace("-", "_")
    base = re.sub(r"[^A-Za-z0-9_]+", "_", base)
    base = re.sub(r"_+", "_", base).strip("_")
    return base.upper()


def _parse_sequence_from_dsx(content: str) -> dict:
    """
    Retorna:
      { tool_instance_id, seq_identifier_raw, seq_name, ordered_job_names }
    """
    tool_instance_id = None
    m = re.search(r'ToolInstanceID\s+"(.*?)"', content)
    if m:
        tool_instance_id = m.group(1).strip()

    # seleciona DSJOB JobType "2" (Sequence)
    seq_block = None
    seq_identifier_raw = None
    for mjob in re.finditer(r'BEGIN DSJOB\s+Identifier\s+"(.*?)".*?END DSJOB', content, re.DOTALL):
        block = mjob.group(0)
        if 'JobType "2"' in block:
            seq_block = block
            seq_identifier_raw = mjob.group(1)
            break

    if not seq_block:
        raise RuntimeError("Nenhuma DSJOB com JobType \"2\" (Sequence) encontrada no arquivo DSX.")

    seq_name = _decode_dsx_text(seq_identifier_raw or "")

    # StageList/StageNames para mapear V0S* -> nome do job
    stage_list = None
    stage_names = None
    msl = re.search(r'StageList\s+"(.*?)"', seq_block)
    msn = re.search(r'StageNames\s+"(.*?)"', seq_block)
    if msl and msn:
        stage_list = msl.group(1)
        stage_names = msn.group(1)

    stage_map: dict[str, str] = {}
    if stage_list and stage_names:
        ids = stage_list.split("|")
        names_raw = stage_names.split("|")
        for sid, nm in zip(ids, names_raw):
            nm2 = _decode_dsx_text(nm).strip()
            if sid.startswith("V0S") and nm2:
                stage_map[sid] = nm2

    # Ordena via JobControlCode (GoTo L$V0S0$START ...)
    order_ids: list[str] = []
    for gid in re.findall(r"GoTo\s+L\$(V0S[0-9A-Za-z]+)\$START", seq_block):
        if gid not in order_ids:
            order_ids.append(gid)

    ordered_job_names: list[str] = []
    if order_ids:
        for sid in order_ids:
            if sid in stage_map:
                ordered_job_names.append(stage_map[sid])
    else:
        ordered_job_names = list(stage_map.values())

    # remove duplicatas mantendo ordem
    dedup: list[str] = []
    for j in ordered_job_names:
        if j not in dedup:
            dedup.append(j)

    return {
        "tool_instance_id": tool_instance_id,
        "seq_identifier_raw": seq_identifier_raw,
        "seq_name": seq_name,
        "ordered_job_names": dedup,
    }


def parse_sequence(**context):
    conf = context["dag_run"].conf or {}
    dsx_filename = conf.get("dsx_filename")
    if not dsx_filename:
        raise ValueError("conf.dsx_filename é obrigatório")

    fp = os.path.join(DSX_IMPORT_DIR, dsx_filename)
    if not os.path.exists(fp):
        raise FileNotFoundError(f"Arquivo DSX não encontrado: {fp}")

    with open(fp, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    parsed = _parse_sequence_from_dsx(content)
    project_name = (conf.get("project_name") or parsed.get("tool_instance_id") or "").strip()
    if not project_name:
        raise ValueError("project_name não informado e não foi possível inferir do ToolInstanceID do DSX")

    domain = (conf.get("domain") or "").strip() or None
    imported_by = (conf.get("imported_by") or "").strip() or None

    seq_identifier_raw = parsed["seq_identifier_raw"] or ""
    seq_name = parsed["seq_name"] or ""
    pipeline_name_suggest = _suggest_pipeline_name(seq_name)

    jobs = parsed["ordered_job_names"]
    if not jobs:
        raise RuntimeError("Nenhum job foi identificado na Sequence (JobControlCode/StageNames).")

    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)

    # 1) insert header
    insert_import_sql = """
    INSERT INTO dbo.etl_seq_import
      (dsx_filename, seq_name_raw, seq_name, project_name, domain, pipeline_name_suggest, imported_by)
    VALUES
      (%s, %s, %s, %s, %s, %s, %s);
    SELECT SCOPE_IDENTITY();
    """
    import_id = int(hook.get_first(insert_import_sql, parameters=(
        dsx_filename,
        seq_identifier_raw,
        seq_name,
        project_name,
        domain,
        pipeline_name_suggest,
        imported_by,
    ))[0])

    # 2) insert jobs + lineage
    engine = DSXEngine(diretorio_base=DSX_IMPORT_DIR)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    jobs_out = []
    for i, job_name in enumerate(jobs, start=1):
        insert_job_sql = """
        INSERT INTO dbo.etl_seq_import_job
          (import_id, execution_order, job_name_ds, job_name_orq, ignored)
        VALUES
          (%s, %s, %s, %s, 0);
        SELECT SCOPE_IDENTITY();
        """
        import_job_id = int(hook.get_first(insert_job_sql, parameters=(import_id, i, job_name, job_name))[0])

        res = engine.buscar_linhagem(project_name, job_name, dsx_file=dsx_filename)
        dados = res.get("dados") if isinstance(res, dict) else None
        if not dados:
            # marca como sem lineage (não falha o parse)
            hook.run(
                "UPDATE dbo.etl_seq_import_job SET lineage_extracted=1, lineage_count=0 WHERE id=%s",
                parameters=(import_job_id,),
            )
            jobs_out.append({
                "import_job_id": import_job_id,
                "execution_order": i,
                "job_name_ds": job_name,
                "job_name_orq": job_name,
                "ignored": 0,
                "lineage_count": 0,
            })
            continue

        lineage_rows = []
        for item in dados:
            direction = (item.get("direction") or "").strip().lower() or "transformacao"
            obj_type = (item.get("object_type") or "").strip()
            if not obj_type:
                obj_type = "Transformação" if direction == "transformacao" else "Tabela"

            lineage_rows.append((
                import_id,
                import_job_id,
                direction,
                obj_type,
                (item.get("object_name") or item.get("stage_name") or "").strip() or "(sem nome)",
                item.get("stage_name"),
                item.get("stage_type_raw"),
                item.get("database_name"),
                item.get("sql_expression"),
                item.get("file_path"),
                dsx_filename,
                now,
                "dsx_auto",
            ))

        insert_lin_sql = """
        INSERT INTO dbo.etl_seq_import_lineage
          (import_id, import_job_id, direction, object_type, object_name,
           stage_name, stage_type_raw, database_name, sql_expression, file_path,
           dsx_source_file, extracted_at, extraction_method)
        VALUES
          (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """
        hook.run(insert_lin_sql, parameters=lineage_rows, autocommit=True)

        hook.run(
            "UPDATE dbo.etl_seq_import_job SET lineage_extracted=1, lineage_count=%s WHERE id=%s",
            parameters=(len(lineage_rows), import_job_id),
        )

        jobs_out.append({
            "import_job_id": import_job_id,
            "execution_order": i,
            "job_name_ds": job_name,
            "job_name_orq": job_name,
            "ignored": 0,
            "lineage_count": len(lineage_rows),
        })

    return {
        "import_id": import_id,
        "dsx_filename": dsx_filename,
        "project_name": project_name,
        "seq_name_raw": seq_identifier_raw,
        "seq_name": seq_name,
        "pipeline_name_suggest": pipeline_name_suggest,
        "jobs": jobs_out,
    }


with DAG(
    dag_id="etl_sequence_import_parse",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule_interval=None,
    catchup=False,
    tags=["ORQUESTRA", "SEQUENCE", "IMPORT"],
) as dag:
    t_parse = PythonOperator(
        task_id="parse_sequence",
        python_callable=parse_sequence,
        provide_context=True,
    )

