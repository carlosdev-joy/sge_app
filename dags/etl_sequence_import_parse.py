"""
etl_sequence_import_parse.py
============================
DAG de importação de sequences DataStage para o ORQUESTRA.

Lê o arquivo .dsx do projeto (já presente em DSX_BASE_DIR),
identifica a sequence pelo nome, extrai os jobs em ordem e
o lineage de cada job, e grava tudo nas tabelas de staging
com status 'pendente_aprovacao'.

Entrada via conf:
  project_name  : str   — ex: 'BI_CVP'  → lê DSX_BASE_DIR/BI_CVP.dsx
  seq_name      : str   — nome da sequence (pode conter acentos)
  imported_by   : str   — matrícula/usuário que disparou a importação
  domain        : str   (opcional) — domínio do pipeline no ORQUESTRA

Saída via XCom (key='return_value'):
{
  "import_id"               : int,
  "seq_name"                : str,   # decodificado
  "project_name"            : str,
  "pipeline_name_suggestion": str,   # nome sanitizado para o ORQUESTRA
  "jobs_count"              : int,
  "jobs"                    : [
    {
      "execution_order"  : int,
      "job_name_ds"      : str,   # nome original DataStage
      "job_name_orq"     : str,   # sugestão para ORQUESTRA
      "lineage_extracted": bool,
      "lineage_count"    : int,
      "lineage"          : [...]  # lista de objetos
    }
  ]
}
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

DAG_ID       = "etl_sequence_import_parse"
MSSQL_CONN_ID = "SQL14_DMDB41"
LOCAL_TZ     = "America/Sao_Paulo"

# Diretório dos arquivos .dsx (mesmo usado pelo engine de jobs)
DSX_BASE_DIR = os.environ.get("DSX_BASE_DIR", "/opt/airflow/dsx")

default_args = {"owner": "airflow", "depends_on_past": False, "retries": 0}


# ── Importar DSXEngine (já presente no servidor) ─────────────────
def _load_engine():
    """
    Importa DSXEngine de forma segura.
    Tenta múltiplos caminhos para cobrir qualquer estrutura de deploy.
    """
    dags_dir = os.path.dirname(os.path.abspath(__file__))
    parent   = os.path.dirname(dags_dir)
    for candidate in [dags_dir, parent, os.path.join(parent, 'Orquestrador')]:
        if candidate not in sys.path:
            sys.path.insert(0, candidate)

    # Caminho 1 — estrutura padrão do projeto (utils/dsx_engine.py)
    try:
        from utils.dsx_engine import DSXEngine  # noqa: PLC0415
        return DSXEngine
    except ImportError:
        pass
    # Caminho 2 — dsx_engine.py na mesma pasta da DAG
    try:
        from dsx_engine import DSXEngine  # noqa: PLC0415
        return DSXEngine
    except ImportError:
        pass
    raise ImportError(
        "Não foi possível importar DSXEngine. "
        "Verifique se dsx_engine.py está em utils/ ou na mesma pasta da DAG."
    )


# ── Decodificação de nomes DSX ───────────────────────────────────
def _decode_dsx(text: str) -> str:
    """
    Converte escapes DSX como \\(E7) → ç, \\(E3) → ã, etc.
    Ex: 'Seq_Flexibiliza\\(E7)\\(E3)o_Cobran\\(E7)a'
        → 'Seq_Flexibilização_Cobrança'
    """
    return re.sub(
        r'\\\(([0-9A-Fa-f]{2})\)',
        lambda m: chr(int(m.group(1), 16)),
        text
    )


def _encode_dsx_pattern(name: str) -> str:
    """
    Constrói um padrão de busca que casa com a versão raw do DSX.
    Aceita tanto o nome decodificado quanto o raw.
    """
    # Escapar o nome decodificado para uso em regex
    # Substituir cada char especial pela sequência raw OU pelo char
    chars_map = {
        'ç': r'(?:ç|\\\\?\(E7\))',
        'ã': r'(?:ã|\\\\?\(E3\))',
        'â': r'(?:â|\\\\?\(E2\))',
        'é': r'(?:é|\\\\?\(E9\))',
        'á': r'(?:á|\\\\?\(E1\))',
        'õ': r'(?:õ|\\\\?\(F5\))',
        'í': r'(?:í|\\\\?\(ED\))',
        'ú': r'(?:ú|\\\\?\(FA\))',
        'à': r'(?:à|\\\\?\(E0\))',
        'ê': r'(?:ê|\\\\?\(EA\))',
        'ô': r'(?:ô|\\\\?\(F4\))',
        'ó': r'(?:ó|\\\\?\(F3\))',
    }
    pattern = re.escape(name)
    for char, replacement in chars_map.items():
        pattern = pattern.replace(re.escape(char), replacement)
    return pattern


def _sanitize_name(name: str) -> str:
    """Gera nome sanitizado para uso no ORQUESTRA (sem acentos, sem espaços)."""
    replacements = {
        'ç': 'c', 'Ç': 'C',
        'ã': 'a', 'â': 'a', 'á': 'a', 'à': 'a', 'Ã': 'A', 'Â': 'A', 'Á': 'A',
        'é': 'e', 'ê': 'e', 'è': 'e', 'É': 'E', 'Ê': 'E',
        'í': 'i', 'ì': 'i', 'Í': 'I',
        'ó': 'o', 'ô': 'o', 'õ': 'o', 'ò': 'o', 'Ó': 'O', 'Ô': 'O', 'Õ': 'O',
        'ú': 'u', 'ù': 'u', 'Ú': 'U',
    }
    result = name
    for char, replacement in replacements.items():
        result = result.replace(char, replacement)
    # Substituir chars não alfanuméricos por underscore e limpar duplos
    result = re.sub(r'[^a-zA-Z0-9_]', '_', result)
    result = re.sub(r'_+', '_', result).strip('_').lower()
    return result


# ── Extração da sequence ─────────────────────────────────────────
def _find_sequence_block(content: str, seq_name: str) -> tuple[str | None, str | None]:
    """
    Localiza o bloco BEGIN DSJOB ... da sequence no conteúdo do DSX.
    Aceita nome decodificado OU raw com escapes.
    Retorna (bloco, nome_raw) ou (None, None).
    """
    # Tentar pelo nome exato primeiro
    raw_candidates = [
        seq_name,                                  # como foi passado
        _decode_dsx(seq_name),                     # decodificado (se veio raw)
    ]

    for candidate in raw_candidates:
        # Busca case-insensitive, aceita espaços/underscores variados
        pattern = _encode_dsx_pattern(candidate)
        match = re.search(
            r'(BEGIN DSJOB\s+Identifier\s+"' + pattern + r'".*?)(?=BEGIN DSJOB|\Z)',
            content, re.DOTALL | re.IGNORECASE
        )
        if match:
            # Extrair o nome raw do identificador
            id_m = re.search(r'Identifier\s+"([^"]+)"', match.group(1))
            raw_name = id_m.group(1) if id_m else candidate
            return match.group(1), raw_name

    return None, None


def _extract_sequence_info(seq_block: str) -> dict | None:
    """
    Extrai informações da sequence a partir do bloco BEGIN DSJOB.
    Retorna dict com seq_name_raw, seq_name, jobs_in_order.
    """
    # Verificar JobType=2 (sequence)
    jtype = re.search(r'JobType\s+"?(\d+)"?', seq_block)
    if not jtype or jtype.group(1) != '2':
        return None

    # Nome raw da sequence
    name_m = re.search(r'^\s+Name\s+"([^"]+)"', seq_block, re.MULTILINE)
    seq_name_raw = name_m.group(1) if name_m else ""
    seq_name = _decode_dsx(seq_name_raw)

    # Ordem de execução: extraída do JobControlCode (GoTo chain)
    jcc_m = re.search(
        r'JobControlCode\s*=\+=\+=\+=\s*(.*?)\s*=\+=\+=\+=',
        seq_block, re.DOTALL
    )
    jobs_in_order: list[str] = []

    if jcc_m:
        jcc = jcc_m.group(1)
        # 3 formatos possíveis no JobControlCode do DSX:
        #   1. DSAttachJob(\"nome\", ...) — escapes com backslash (mais comum)
        #   2. DSAttachJob("nome", ...)    — sem escape (algumas versões do DataStage)
        #   3. DSAttachJob('nome', ...)    — aspas simples (raro)
        seen: set[str] = set()
        for pattern in [
            r'DSAttachJob\(\\"([^\\"]+)\\"',   # formato \"-escaped
            r'DSAttachJob\(\"([^\"]+)\"',          # formato "-escaped simples
            r'DSAttachJob\("([^"]+)"',                # formato sem escape
        ]:
            for job in re.findall(pattern, jcc):
                if job and job not in seen:
                    seen.add(job)
                    jobs_in_order.append(job)
            if jobs_in_order:
                break  # parar no primeiro padrão que funcionar

    # Fallback 1: CJobActivity — busca simplificada por Name nas activities
    if not jobs_in_order:
        for m in re.finditer(
            r'BEGIN DSRECORD.*?OLEType\s+"CJobActivity".*?END DSRECORD',
            seq_block, re.DOTALL
        ):
            name_m = re.search(r'Name\s+"([^"]+)"', m.group(0))
            if name_m:
                name = name_m.group(1)
                if name and name not in ("Job", "ROOT") and name not in jobs_in_order:
                    jobs_in_order.append(name)

    # Fallback 2: tokens * IdVxSy <= job_name nos comentários do JobControlCode
    if not jobs_in_order and jcc_m:
        jcc = jcc_m.group(1)
        # Linha: * IdV0S0%%Name%%2 <= BiCvp_BaseCobranca_00_ext_Parcelas_Pagas.$JobName
        for m in re.finditer(r'\*\s+IdV\w+%%Name%%\d+\s+<=\s+([^.]+)\.\$JobName', jcc):
            job = m.group(1).strip()
            if job and job not in jobs_in_order:
                jobs_in_order.append(job)
    return {
        "seq_name_raw": seq_name_raw,
        "seq_name":     seq_name,
        "jobs_in_order": jobs_in_order,
    }


# ── Task principal ────────────────────────────────────────────────
def parse_sequence(**context):
    conf         = context["dag_run"].conf or {}
    project_name = (conf.get("project_name") or "").strip()
    seq_name     = (conf.get("seq_name")     or "").strip()
    imported_by  = (conf.get("imported_by")  or "system").strip()
    domain       = (conf.get("domain")       or "").strip() or None

    if not project_name:
        raise ValueError("Parâmetro 'project_name' é obrigatório.")
    if not seq_name:
        raise ValueError("Parâmetro 'seq_name' é obrigatório.")

    # 1. Localizar e ler o DSX
    dsx_filename = f"{project_name}.dsx"
    dsx_path     = os.path.join(DSX_BASE_DIR, dsx_filename)

    if not os.path.exists(dsx_path):
        raise FileNotFoundError(
            f"Arquivo '{dsx_filename}' não encontrado em '{DSX_BASE_DIR}'. "
            f"Verifique se o arquivo .dsx do projeto {project_name} está presente no servidor."
        )

    print(f"[SEQ_PARSE] Lendo {dsx_path} ...")
    with open(dsx_path, "r", encoding="utf-8", errors="ignore") as fh:
        content = fh.read()
    print(f"[SEQ_PARSE] Arquivo lido: {len(content):,} chars")

    # 2. Localizar a sequence no arquivo
    seq_block, seq_name_raw = _find_sequence_block(content, seq_name)
    if seq_block is None:
        raise ValueError(
            f"Sequence '{seq_name}' não encontrada em '{dsx_filename}'. "
            f"Verifique o nome exato (acentuação incluída)."
        )

    seq_info = _extract_sequence_info(seq_block)
    if seq_info is None:
        raise ValueError(
            f"O bloco encontrado para '{seq_name}' não é uma sequence (JobType != 2)."
        )

    seq_decoded = seq_info["seq_name"]
    jobs_in_order = seq_info["jobs_in_order"]
    print(f"[SEQ_PARSE] Sequence: '{seq_decoded}' | Jobs: {len(jobs_in_order)}")

    # 3. Gravar cabeçalho no staging
    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
    pipeline_suggestion = _sanitize_name(seq_decoded)

    hook.run("""
        INSERT INTO dbo.etl_seq_import
            (dsx_filename, seq_name_raw, seq_name, project_name, domain,
             pipeline_name_override, status, imported_by, imported_at)
        VALUES (%s, %s, %s, %s, %s, %s, 'pendente_aprovacao', %s, GETDATE())
    """, parameters=[
        dsx_filename, seq_decoded, seq_decoded, project_name, domain,
        pipeline_suggestion, imported_by
    ])

    import_id = hook.get_first("SELECT MAX(id) FROM dbo.etl_seq_import")[0]
    print(f"[SEQ_PARSE] import_id={import_id}")

    # 4. Para cada job: gravar no staging + extrair lineage
    DSXEngineClass = _load_engine()
    engine = DSXEngineClass(DSX_BASE_DIR)

    jobs_preview = []
    for order, job_name in enumerate(jobs_in_order):
        # job_name_orq = nome original do DSX (mantém CamelCase)
        # Garante que o botão "Lineage" encontre o job no arquivo .dsx
        # sem precisar de fallback. O usuário pode renomear na etapa de revisão.
        job_name_orq = job_name

        hook.run("""
            INSERT INTO dbo.etl_seq_import_job
                (import_id, execution_order, job_name_ds, job_name_orq, job_type, status)
            VALUES (%s, %s, %s, %s, 'datastage', 'pendente')
        """, parameters=[import_id, order, job_name, job_name_orq])

        job_id = hook.get_first("""
            SELECT MAX(id) FROM dbo.etl_seq_import_job
            WHERE import_id=%s AND execution_order=%s
        """, parameters=[import_id, order])[0]

        # Extrair lineage (reutiliza o engine existente)
        lineage_result = engine.extrair(project_name, job_name)
        lineage_data   = []
        lineage_ok     = False

        if lineage_result.get("sucesso"):
            lineage_ok   = True
            lineage_data = lineage_result.get("dados", [])

            for item in lineage_data:
                cols = item.get("columns") or []
                cols_json = json.dumps(cols, ensure_ascii=False) if cols else None
                hook.run("""
                    INSERT INTO dbo.etl_seq_import_lineage
                        (import_job_id, direction, object_name, object_type,
                         stage_type_raw, sql_expression, file_path, database_name,
                         dsx_source_file, extraction_method, columns_json, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'dsx_auto', %s, 'pendente')
                """, parameters=[
                    job_id,
                    item.get("direction"),
                    item.get("object_name"),
                    item.get("object_type"),
                    item.get("stage_type_raw"),
                    item.get("sql_expression"),
                    item.get("file_path"),
                    item.get("database_name"),
                    item.get("dsx_source_file"),
                    cols_json,
                ])

            hook.run("""
                UPDATE dbo.etl_seq_import_job
                SET lineage_extracted=1, lineage_count=%s
                WHERE id=%s
            """, parameters=[len(lineage_data), job_id])
        else:
            print(f"[SEQ_PARSE] Lineage não extraída para {job_name}: "
                  f"{lineage_result.get('erro', 'desconhecido')}")

        jobs_preview.append({
            "import_job_id":    job_id,
            "execution_order":  order,
            "job_name_ds":      job_name,
            "job_name_orq":     job_name,   # nome original do DSX
            "lineage_extracted": lineage_ok,
            "lineage_count":    len(lineage_data),
            "lineage":          lineage_data,
        })

        print(f"[SEQ_PARSE] Job {order+1}/{len(jobs_in_order)}: "
              f"{job_name} | lineage={len(lineage_data)} objetos")

    result = {
        "import_id":                import_id,
        "seq_name":                 seq_decoded,
        "seq_name_raw":             seq_decoded,
        "project_name":             project_name,
        "pipeline_name_suggestion": pipeline_suggestion,
        "jobs_count":               len(jobs_in_order),
        "jobs":                     jobs_preview,
    }

    print(f"[SEQ_PARSE] Concluído: import_id={import_id} | {len(jobs_in_order)} jobs")
    return result


# ── DAG definition ───────────────────────────────────────────────
with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Importa sequence DataStage: extrai jobs, ordem e lineage para aprovação",
    start_date=pendulum.datetime(2024, 1, 1, tz=LOCAL_TZ),
    schedule=None,
    catchup=False,
    tags=["etl", "import", "sequence", "lineage"],
    access_control={"Op": {"can_read", "can_edit"}},
) as dag:

    PythonOperator(
        task_id="parse_sequence",
        python_callable=parse_sequence,
        do_xcom_push=True,
    )
