"""
dsx_engine.py  —  ORQUESTRA / BI CVP
=====================================
Engine robusto de extração de lineage a partir de arquivos DataStage .dsx.

Princípios de design:
  • Parsing linha a linha: nenhuma regex sobre o arquivo completo
  • Blob XMLProperties extraído por delimitador =+=+=+=  (não por regex .*?)
  • SQL nunca armazenado: apenas nomes de tabelas (FROM / JOIN)
  • CTEs excluídas dos resultados
  • Escapes DataStage \\(XX) decodificados antes da extração
  • Direção determinada por Context (source/target) ou topologia de links
  • Thread-safe: sem estado compartilhado entre chamadas
  • Colunas extraídas dos OutputPin DSSUBRECORD (o que realmente flui para a próxima etapa)
"""

from __future__ import annotations

import os
import re
import threading
from typing import Optional

# ── Variável de ambiente para localização dos arquivos .dsx ──────
_DEFAULT_DSX_DIR = os.environ.get("DSX_BASE_DIR", "/opt/airflow/dsx")

try:
    from airflow.models import Variable
    _DEFAULT_DSX_DIR = Variable.get("DSX_BASE_DIR", default_var=_DEFAULT_DSX_DIR)
except Exception:
    pass

# ── Cache de parsing por arquivo (chave = path, invalida por mtime) ──
# Usado pela busca de impacto por campo: evita reparsear o mesmo .dsx a cada
# consulta. Protegido por lock — seguro sob a API multithread.
_PARSE_LOCK = threading.Lock()
_PARSE_CACHE: dict[str, tuple[float, dict[str, list[dict]]]] = {}

# ── De-para: StageType bruto → categoria de direção ──────────────
_TRANSFORM_TYPES: frozenset[str] = frozenset({
    "PxSort", "PxSortWithGroupBy", "PxRemDup", "PxFunnel",
    "PxLookup", "PxAggregator", "PxJoin", "PxMerge", "PxFilter",
    "PxModify", "CTransformerStage", "PxSwitch", "PxPivot",
    "PxSurrogateKeyGen", "PxChangeCapture", "PxChangeApply",
    "PxDifference", "PxChecksum", "PxColumnExport", "PxColumnImport",
    "PxNormalize", "PxDenormalize", "PxMakeSubrec", "PxSplitSubrec",
    "PxRowMerge", "PxEncode", "PxDecode", "PxSharedContainer",
    "LocalContainerStage", "PxPeek", "RowGenerator", "ColumnGenerator",
    "PxHead", "PxTail", "PxSample",
    "CJobActivity", "CNotificationActivity", "CExceptionHandler",
})

_DB_TYPES: frozenset[str] = frozenset({
    "ODBCConnectorPX", "OracleConnector", "DB2Connector",
    "SQLServerConnector", "TeradataConnector", "JDBCConnector",
    "DRSStage", "StoredProcedureStage", "MS_OLEDB",
})

_FILE_TYPES: frozenset[str] = frozenset({
    "PxDataSet", "DataSetStage",
    "PxSequentialFile", "SequentialFile", "FileConnector",
    "FileSetStage", "PxFileSet",
})

# Nomes de subrecords que NÃO são colunas
_COL_SKIP: frozenset[str] = frozenset({
    "", "input", "output", "Input", "Output", "lookup\\type",
    "dataset", "datasetmode", "VariantName", "VariantLibrary",
    "VariantVersion", "ConnectorName", "Engine", "Context",
    "ConnectionString", "Username", "Password", "XMLProperties",
    "RejectFromLink", "RejectThreshold", "RejectNumber",
    "RejectUsesPercentage", "SupportedVariants",
})

# ── De-para: SqlType (código ODBC do DataStage) → nome legível ────
_SQL_TYPE_MAP: dict[int, str] = {
    1: "CHAR", 12: "VARCHAR", -1: "LONGVARCHAR",
    -8: "NCHAR", -9: "NVARCHAR", -10: "LONGNVARCHAR",
    2: "NUMERIC", 3: "DECIMAL",
    4: "INTEGER", 5: "SMALLINT", -5: "BIGINT", -6: "TINYINT",
    6: "FLOAT", 7: "REAL", 8: "DOUBLE", -7: "BIT",
    9: "DATE", 10: "TIME", 11: "TIMESTAMP",
    91: "DATE", 92: "TIME", 93: "TIMESTAMP",
    -2: "BINARY", -3: "VARBINARY", -4: "LONGVARBINARY",
}

# Categorias de tipo (nomes em maiúsculas) para filtros de datatype
_TEXT_TYPE_NAMES: frozenset[str] = frozenset({
    "CHAR", "VARCHAR", "LONGVARCHAR", "NCHAR", "NVARCHAR",
    "LONGNVARCHAR", "WCHAR", "WVARCHAR", "TEXT", "STRING",
})
_NUMERIC_TYPE_NAMES: frozenset[str] = frozenset({
    "INTEGER", "BIGINT", "SMALLINT", "TINYINT", "DECIMAL",
    "NUMERIC", "FLOAT", "REAL", "DOUBLE", "BIT",
})

# Padrões de pasta/categoria de backup a ignorar na varredura
# (substring, case-insensitive). Ex.: "\\Jobs\\Projetos\\Coberturas\\bckp"
_BACKUP_PATTERNS: tuple[str, ...] = ("backup", "bckp", "bkp", "bkup")

# Jobs "cópia" (duplicatas geradas no DataStage, ex.: CopyOfX) — em geral não
# usados no dia a dia. Detectado no nome do job ou na pasta (substring, lower).
_COPY_PATTERNS: tuple[str, ...] = ("copyof", "copy of", "copy_of", "copy-of", "cópia", "copia")

# ── Regex compiladas (seguras — aplicadas em blocos pequenos) ────
_RE_DSX_ESCAPE  = re.compile(r'\\\(([0-9A-Fa-f]{2})\)')
_RE_CDATA       = re.compile(r'<!\[CDATA\[(.*?)\]\]>', re.DOTALL)
_RE_CDATA_TAG   = re.compile(r'<([A-Za-z][A-Za-z0-9_]*)[^>]*><!\[CDATA\[(.*?)\]\]>', re.DOTALL)
_RE_CTE         = re.compile(r'\bWITH\s+([a-zA-Z0-9_#]+)\s+AS\s*\(|,\s*([a-zA-Z0-9_#]+)\s+AS\s*\(', re.IGNORECASE)
_RE_FROM_JOIN   = re.compile(r'\b(?:FROM|JOIN)\s+([a-zA-Z0-9_.#\[\]"]+)', re.IGNORECASE)
_RE_DB_HINT     = re.compile(r'ParmDb(?:Name)?([A-Z0-9]{4,})')
_RE_SIMPLE_NAME = re.compile(r'^\s+(Name|Value)\s+"([^"]*)"', re.MULTILINE)


# ════════════════════════════════════════════════════════════════
class DSXEngine:
    """Extrai lineage de jobs DataStage a partir de arquivos .dsx."""

    def __init__(self, diretorio_base: str = _DEFAULT_DSX_DIR):
        self.diretorio_base = diretorio_base

    # ── API pública ─────────────────────────────────────────────
    def extrair(self, project_name: str, job_name: str) -> dict:
        """
        Retorna dict com chave 'sucesso' e 'dados' (lista de stages)
        ou 'erro' com mensagem de falha.
        """
        dsx_file = f"{project_name}.dsx"
        path = os.path.join(self.diretorio_base, dsx_file)

        if not os.path.exists(path):
            return {"erro": f"Arquivo '{dsx_file}' não encontrado em '{self.diretorio_base}'."}

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
        except OSError as exc:
            return {"erro": f"Erro ao ler '{dsx_file}': {exc}"}

        job_block = self._extract_job_block(content, job_name)
        if job_block is None:
            return {"erro": f"Job '{job_name}' não encontrado em '{dsx_file}'."}

        stages = self._parse_stages(job_block, project_name, job_name, dsx_file)
        return {"sucesso": True, "project_name": project_name,
                "job_name": job_name, "dsx_file": dsx_file, "dados": stages}

    # Alias mantido para retrocompatibilidade
    def buscar_linhagem(self, nome_projeto: str, nome_job: str) -> dict:
        return self.extrair(nome_projeto, nome_job)

    # ── Listagem de arquivos .dsx disponíveis ───────────────────
    def listar_dsx(self) -> list[str]:
        """Nomes de projeto (arquivo .dsx sem extensão) disponíveis no diretório base."""
        try:
            nomes = [f[:-4] for f in os.listdir(self.diretorio_base)
                     if f.lower().endswith(".dsx")]
        except OSError:
            return []
        return sorted(nomes, key=str.lower)

    # ── Listagem de jobs de um .dsx ─────────────────────────────
    def listar_jobs(self, project_name: str) -> dict:
        """Lista todos os jobs (DSJOB) declarados no arquivo .dsx do projeto."""
        jobs_stages = self._load_jobs_cached(project_name)
        if isinstance(jobs_stages, dict) and jobs_stages.get("erro"):
            return jobs_stages
        return {
            "sucesso": True,
            "project_name": project_name,
            "dsx_file": f"{project_name}.dsx",
            "jobs": sorted(jobs_stages.keys(), key=str.lower),
        }

    # ── Busca de impacto por campo (varredura do .dsx) ──────────
    def buscar_campo(self, project_name: str, termo: str,
                     exato: bool = False, tipos=None,
                     excluir: bool = False, incluir_bkp: bool = False,
                     incluir_copy: bool = False) -> dict:
        """
        Varre TODOS os jobs do .dsx do projeto e retorna onde o campo aparece,
        com o datatype de cada coluna que casou.

        Busca tipo LIKE (substring, case-insensitive) por padrão — útil quando
        não há padrão de nomenclatura (ex.: 'CNPJ' casa NUM_CNPJ, CPF_CNPJ…).
        Com exato=True, casa apenas igualdade exata (case-insensitive).

        Filtro de datatype (opcional):
          tipos   — iterável de nomes de tipo (ex.: ['VARCHAR','CHAR'])
          excluir — False: só colunas cujo tipo ESTÁ em `tipos`
                    True:  só colunas cujo tipo NÃO está em `tipos`
          (ex.: tipos=['VARCHAR','CHAR'], excluir=True → todo CNPJ que NÃO é texto)

        incluir_bkp — False (padrão): ignora jobs em pastas de backup
                      (categoria com bkp/bckp/backup); True: inclui esses jobs.
        incluir_copy — False (padrão): ignora jobs cópia (ex.: CopyOf...);
                       True: inclui esses jobs.
        """
        termo_norm = (termo or "").strip().lower()
        if not termo_norm:
            return {"erro": "O termo de busca (campo) é obrigatório."}

        jobs_data = self._load_jobs_cached(project_name)
        if isinstance(jobs_data, dict) and jobs_data.get("erro"):
            return jobs_data

        tipos_set = {str(t).strip().upper() for t in (tipos or []) if str(t).strip()}

        def _match_nome(name: str) -> bool:
            c = (name or "").lower()
            return c == termo_norm if exato else termo_norm in c

        def _match_tipo(col: dict) -> bool:
            if not tipos_set:
                return True
            tname = (col.get("type_name") or "").upper()
            if not tname:               # tipo desconhecido → não confirma o filtro
                return False
            return (tname not in tipos_set) if excluir else (tname in tipos_set)

        jobs_out: list[dict] = []
        total_ocorrencias = 0
        jobs_considerados = 0
        jobs_bkp_ignorados = 0
        jobs_copy_ignorados = 0
        for job_name in sorted(jobs_data, key=str.lower):
            category = jobs_data[job_name].get("category") or ""
            if not incluir_bkp and self._is_backup_category(category):
                jobs_bkp_ignorados += 1
                continue
            if not incluir_copy and self._is_copy_job(job_name, category):
                jobs_copy_ignorados += 1
                continue
            jobs_considerados += 1

            ocorrencias = []
            for stage in jobs_data[job_name].get("stages") or []:
                cols_detail = stage.get("columns_detail") or []
                matched = [c for c in cols_detail
                           if _match_nome(c.get("name")) and _match_tipo(c)]
                if not matched:
                    continue
                detalhe = (stage.get("sql_expression") or stage.get("file_path") or "")
                if detalhe:
                    detalhe = detalhe.replace("\n", ", ")
                ocorrencias.append({
                    "stage_name":      stage.get("stage_name"),
                    "direction":       stage.get("direction"),
                    "object_name":     stage.get("object_name"),
                    "object_type":     stage.get("object_type"),
                    "stage_type_raw":  stage.get("stage_type_raw"),
                    "database_name":   stage.get("database_name"),
                    "detalhe":         detalhe,
                    "matched_columns": matched,
                    "total_columns":   len(cols_detail),
                })
            if ocorrencias:
                total_ocorrencias += sum(len(o["matched_columns"]) for o in ocorrencias)
                jobs_out.append({"job_name": job_name, "category": category,
                                 "ocorrencias": ocorrencias})

        return {
            "sucesso":                True,
            "project_name":           project_name,
            "dsx_file":               f"{project_name}.dsx",
            "termo":                  termo,
            "exato":                  exato,
            "filtro_tipos":           sorted(tipos_set),
            "filtro_excluir":         excluir,
            "incluir_bkp":            incluir_bkp,
            "incluir_copy":           incluir_copy,
            "jobs_bkp_ignorados":     jobs_bkp_ignorados,
            "jobs_copy_ignorados":    jobs_copy_ignorados,
            "total_jobs_dsx":         jobs_considerados,
            "total_jobs_impactados":  len(jobs_out),
            "total_ocorrencias":      total_ocorrencias,
            "jobs":                   jobs_out,
        }

    # ── Iteração dos blocos de job (BEGIN DSJOB … próximo) ───────
    def _iter_job_blocks(self, content: str):
        """Gera (job_name, job_block) para cada BEGIN DSJOB no conteúdo."""
        marker = "BEGIN DSJOB"
        idx = content.find(marker)
        while idx >= 0:
            nxt = content.find(marker, idx + len(marker))
            end = nxt if nxt > 0 else len(content)
            block = content[idx:end]
            m = re.search(r'Identifier\s+"([^"]+)"', block)
            if m:
                yield m.group(1), block
            idx = nxt

    def _job_category(self, block: str) -> str:
        """Pasta/categoria do job no DataStage (ex.: \\Jobs\\Projetos\\Coberturas)."""
        m = re.search(r'^\s*Category\s+"([^"]*)"', block, re.MULTILINE)
        return m.group(1) if m else ""

    @staticmethod
    def _is_backup_category(category: str) -> bool:
        """True se a categoria do job aparenta ser pasta de backup (bkp/bckp/backup)."""
        low = (category or "").lower()
        return any(p in low for p in _BACKUP_PATTERNS)

    @staticmethod
    def _is_copy_job(job_name: str, category: str = "") -> bool:
        """True se o job aparenta ser uma cópia (ex.: CopyOf...) — nome ou pasta."""
        name = (job_name or "").lower()
        cat = (category or "").lower()
        return any(p in name or p in cat for p in _COPY_PATTERNS)

    # ── Parsing de todos os jobs com cache por mtime ────────────
    def _load_jobs_cached(self, project_name: str):
        """Lê e parseia todos os jobs do .dsx; cache invalidado pelo mtime.

        Retorna dict {job_name: {"category": str, "stages": [...]}}.
        """
        dsx_file = f"{project_name}.dsx"
        path = os.path.join(self.diretorio_base, dsx_file)
        if not os.path.exists(path):
            return {"erro": f"Arquivo '{dsx_file}' não encontrado em '{self.diretorio_base}'."}
        try:
            mtime = os.path.getmtime(path)
        except OSError as exc:
            return {"erro": f"Erro ao acessar '{dsx_file}': {exc}"}

        with _PARSE_LOCK:
            cached = _PARSE_CACHE.get(path)
            if cached and cached[0] == mtime:
                return cached[1]

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
        except OSError as exc:
            return {"erro": f"Erro ao ler '{dsx_file}': {exc}"}

        jobs_data: dict[str, dict] = {}
        for job_name, block in self._iter_job_blocks(content):
            jobs_data[job_name] = {
                "category": self._job_category(block),
                "stages":   self._parse_stages(block, project_name, job_name, dsx_file),
            }

        with _PARSE_LOCK:
            _PARSE_CACHE[path] = (mtime, jobs_data)
        return jobs_data

    # ── Extração do bloco do job ────────────────────────────────
    def _extract_job_block(self, content: str, job_name: str) -> Optional[str]:
        marker = f'BEGIN DSJOB\n   Identifier "{job_name}"'
        start = content.find(marker)
        if start < 0:
            marker = f'BEGIN DSJOB\r\n   Identifier "{job_name}"'
            start = content.find(marker)
        if start < 0:
            return None
        next_job = content.find("BEGIN DSJOB", start + len(marker))
        end = next_job if next_job > 0 else len(content)
        return content[start:end]

    # ── Parsing dos stages ──────────────────────────────────────
    def _parse_stages(self, job_block: str, project_name: str,
                      job_name: str, dsx_file: str) -> list[dict]:
        records = self._split_records(job_block)
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # Índice identifier → record (para lookup de pins)
        records_by_id: dict[str, str] = {}
        for rec in records:
            id_m = re.search(r'^\s+Identifier\s+"([^"]+)"', rec, re.MULTILINE)
            if id_m:
                records_by_id[id_m.group(1)] = rec

        dataset_paths = self._index_dataset_paths(records)

        results = []
        for rec in records:
            stage = self._process_record(
                rec, project_name, job_name, dsx_file, now,
                dataset_paths, records_by_id
            )
            if stage:
                results.append(stage)

        return results

    def _index_dataset_paths(self, records: list[str]) -> dict[str, str]:
        paths: dict[str, str] = {}
        for rec in records:
            if 'CCustomInput' not in rec and 'CCustomOutput' not in rec:
                continue
            ident_m = re.search(r'^\s+Identifier\s+"([^"]+)"', rec, re.MULTILINE)
            path_m  = re.search(r'Name "dataset"\s*\n\s*Value "([^"]+)"', rec, re.IGNORECASE)
            if ident_m and path_m:
                paths[ident_m.group(1)] = path_m.group(1).strip()
            elif ident_m:
                fpath_m = re.search(r'Name "file"\s*\n\s*Value "([^"]+)"', rec, re.IGNORECASE)
                if fpath_m:
                    paths[ident_m.group(1)] = fpath_m.group(1).strip()
        return paths

    # ── Split de DSRECORD (linha a linha) ───────────────────────
    def _split_records(self, block: str) -> list[str]:
        records = []
        depth = 0
        buf: list[str] = []
        in_record = False

        for line in block.splitlines(keepends=True):
            stripped = line.strip()
            if stripped == "BEGIN DSRECORD":
                depth += 1
                if depth == 1:
                    in_record = True
                    buf = [line]
                else:
                    buf.append(line)
            elif stripped == "END DSRECORD":
                buf.append(line)
                depth -= 1
                if depth == 0 and in_record:
                    records.append("".join(buf))
                    buf = []
                    in_record = False
            elif in_record:
                buf.append(line)

        return records

    # ── Processamento de um DSRECORD ────────────────────────────
    def _process_record(self, rec: str, project_name: str, job_name: str,
                        dsx_file: str, now: str,
                        dataset_paths: dict | None = None,
                        records_by_id: dict | None = None) -> Optional[dict]:
        if 'OLEType "CCustomStage"' not in rec and 'OLEType "CStage"' not in rec:
            return None

        name_m      = re.search(r'^\s+Name\s+"([^"]+)"', rec, re.MULTILINE)
        stagetype_m = re.search(r'StageType\s+"([^"]+)"', rec)
        if not name_m or not stagetype_m:
            return None

        stage_name = name_m.group(1)
        stage_type = stagetype_m.group(1)

        if stage_name in ("ROOT", "Job"):
            return None

        direction = self._infer_direction(rec, stage_type)
        xml_blob  = self._extract_xml_blob(rec)

        # Coletar pins para extração de colunas (OutputPins primeiro, InputPins como fallback)
        output_pin_content = self._collect_pin_content(rec, records_by_id, "OutputPins")
        input_pin_content  = self._collect_pin_content(rec, records_by_id, "InputPins")

        sql_expression: Optional[str] = None
        file_path:      Optional[str] = None
        database_name:  Optional[str] = None
        columns:        list[str]     = []
        object_type = stage_type

        is_db = (
            stage_type in _DB_TYPES
            or any(t in stage_type for t in ("ODBC", "Oracle", "DB2", "SQL", "Connector"))
        )
        is_file = (
            stage_type in _FILE_TYPES
            or any(t in stage_type for t in ("DataSet", "Sequential", "FileSet"))
        )

        if is_db and xml_blob:
            tables, db_hint = self._extract_db_info(xml_blob)
            if tables:
                sql_expression = "\n".join(tables)
            if db_hint:
                database_name = db_hint
            object_type = "ODBC"

        if is_file:
            file_path = self._extract_dataset_path(rec)
            if not file_path and dataset_paths:
                for pin_field in ("InputPins", "OutputPins"):
                    pins_m = re.search(rf'^\s+{pin_field}\s+"([^"]+)"', rec, re.MULTILINE)
                    if pins_m:
                        for pin_id in pins_m.group(1).split("|"):
                            pin_id = pin_id.strip()
                            if pin_id in dataset_paths:
                                file_path = dataset_paths[pin_id]
                                break
                    if file_path:
                        break
            if not file_path and xml_blob:
                file_path = self._extract_file_path_from_xml(xml_blob)
            # Gravar somente o nome do arquivo (sem diretório/parâmetros)
            if file_path:
                file_path = file_path.replace("\\", "/").split("/")[-1] or file_path
            object_type = "Arquivo"

        # Colunas (com datatype): OutputPins primeiro, InputPins como fallback
        columns_detail = (self._extract_columns_detail_from_pin(output_pin_content) or
                          self._extract_columns_detail_from_pin(input_pin_content))
        columns = [c["name"] for c in columns_detail]

        return {
            "project_name":      project_name,
            "job_name":          job_name,
            "direction":         direction,
            "stage_name":        stage_name,
            "stage_type_raw":    stage_type,
            "object_name":       stage_name,
            "object_type":       object_type,
            "database_name":     database_name,
            "sql_expression":    sql_expression,
            "file_path":         file_path,
            "dsx_source_file":   dsx_file,
            "extracted_at":      now,
            "extraction_method": "dsx_auto",
            "columns":           columns,
            "columns_detail":    columns_detail,
        }

    # ── Colunas dos OutputPins ───────────────────────────────────
    def _collect_pin_content(self, rec: str, records_by_id: dict | None,
                             pin_field: str) -> str:
        """Retorna o conteúdo concatenado dos pin records referenciados."""
        if not records_by_id:
            return ""
        content = ""
        pins_m = re.search(rf'^\s+{pin_field}\s+"([^"]+)"', rec, re.MULTILINE)
        if pins_m:
            for pin_id in pins_m.group(1).split("|"):
                pin_id = pin_id.strip()
                if pin_id in records_by_id:
                    content += records_by_id[pin_id]
        return content

    def _extract_columns_from_pin(self, pin_content: str) -> list[str]:
        """Nomes de coluna (retrocompat) — derivados de _extract_columns_detail_from_pin."""
        return [c["name"] for c in self._extract_columns_detail_from_pin(pin_content)]

    def _mk_col(self, name: str, sql_type, precision, scale, nullable) -> dict:
        """Monta o dict de uma coluna com tipo legível.

        sql_type pode ser int (código ODBC) ou str (texto vindo de XML).
        """
        if isinstance(sql_type, int):
            type_name = _SQL_TYPE_MAP.get(sql_type, f"SQL({sql_type})")
            code = sql_type
        elif isinstance(sql_type, str) and sql_type.strip():
            type_name = sql_type.strip().upper()
            code = None
        else:
            type_name = None
            code = None
        return {
            "name":      name,
            "sql_type":  code,
            "type_name": type_name,
            "precision": precision,
            "scale":     scale,
            "nullable":  nullable,
        }

    def _extract_columns_detail_from_pin(self, pin_content: str) -> list[dict]:
        """
        Extrai colunas (nome + datatype) do conteúdo de pin records.
        Suporta:
          1. DSSUBRECORD com Name + SqlType/Precision/Scale/Nullable (ODBCConnectorPX)
          2. <Column name="..."> XML (tipo opcional via atributo)
        """
        if not pin_content:
            return []

        # 1. XML <Column name="..." ...>
        detail: list[dict] = []
        for tag in re.findall(r"<Column\b[^>]*>", pin_content, re.IGNORECASE):
            nm = re.search(r'\bname="([^"]+)"', tag, re.IGNORECASE)
            if not nm:
                continue
            tp = re.search(r'\b(?:sqlType|type|datatype)="([^"]+)"', tag, re.IGNORECASE)
            detail.append(self._mk_col(nm.group(1), tp.group(1) if tp else None,
                                       None, None, None))
        if detail:
            return detail

        # 2. DSSUBRECORD com Name + SqlType/Precision/Scale/Nullable
        sub_blocks = re.split(r"BEGIN DSSUBRECORD|END DSSUBRECORD", pin_content)
        for block in sub_blocks:
            if "SqlType" not in block and "Precision" not in block:
                continue
            nm = re.search(r'^\s*Name\s+"([^"]+)"', block, re.MULTILINE)
            if not nm or nm.group(1) in _COL_SKIP:
                continue
            st = re.search(r'^\s*SqlType\s+"(-?\d+)"', block, re.MULTILINE)
            pr = re.search(r'^\s*Precision\s+"(-?\d+)"', block, re.MULTILINE)
            sc = re.search(r'^\s*Scale\s+"(-?\d+)"', block, re.MULTILINE)
            nl = re.search(r'^\s*Nullable\s+"(-?\d+)"', block, re.MULTILINE)
            detail.append(self._mk_col(
                nm.group(1),
                int(st.group(1)) if st else None,
                int(pr.group(1)) if pr else None,
                int(sc.group(1)) if sc else None,
                (nl.group(1) == "1") if nl else None,
            ))

        return detail

    # ── Direção do stage ────────────────────────────────────────
    def _infer_direction(self, rec: str, stage_type: str) -> str:
        if stage_type in _TRANSFORM_TYPES:
            return "transformacao"

        ctx_m = re.search(r'Name "Context"\s*\n\s*Value "([^"]+)"', rec)
        if ctx_m:
            ctx = ctx_m.group(1).strip().lower()
            if ctx == "source":
                return "origem"
            if ctx in ("target", "write"):
                return "destino"

        has_in  = bool(re.search(r'^\s+InputPins\s+"', rec, re.MULTILINE))
        has_out = bool(re.search(r'^\s+OutputPins\s+"', rec, re.MULTILINE))
        if has_out and not has_in:
            return "origem"
        if has_in and not has_out:
            return "destino"
        if has_in and has_out:
            return "transformacao"

        return "transformacao"

    # ── Extração do blob XMLProperties ──────────────────────────
    def _extract_xml_blob(self, rec: str) -> Optional[str]:
        SENTINEL = "=+=+=+="
        start = rec.find(SENTINEL)
        if start >= 0:
            start += len(SENTINEL)
            end = rec.find(SENTINEL, start)
            if end >= 0:
                return rec[start:end].strip()

        m = re.search(
            r'Name\s+"XMLProperties"\s*\n\s*Value\s+"((?:[^"\\]|\\.)*)"',
            rec, re.DOTALL
        )
        if m:
            raw = m.group(1).replace('\\"', '"')
            return raw.strip()

        return None

    # ── Extração de tabelas DB e database name ───────────────────
    def _extract_db_info(self, xml: str) -> tuple[list[str], Optional[str]]:
        tables: list[str] = []

        tn_m = re.search(r'<TableName[^>]*><!\[CDATA\[(.*?)\]\]>', xml, re.DOTALL)
        if tn_m:
            tn = tn_m.group(1).strip()
            if tn:
                tables.append(tn)

        for tag in ("SelectStatement", "WriteStatement", "InsertStatement"):
            sql_m = re.search(
                rf'<{tag}[^>]*>.*?<!\[CDATA\[(.*?)\]\]>',
                xml, re.DOTALL
            )
            if sql_m:
                sql_raw = sql_m.group(1)
                sql = _RE_DSX_ESCAPE.sub(
                    lambda m: chr(int(m.group(1), 16)), sql_raw
                )
                tables.extend(self._extract_tables_from_sql(sql))
                break

        tables = list(dict.fromkeys(t for t in tables if t))

        database_name = None
        ds_m = re.search(r'<DataSource[^>]*>.*?<!\[CDATA\[(.*?)\]\]>', xml, re.DOTALL)
        if ds_m:
            ds_raw = ds_m.group(1).strip()
            if not ds_raw.startswith("#"):
                database_name = ds_raw
            else:
                hint = _RE_DB_HINT.search(ds_raw)
                if hint:
                    database_name = hint.group(1)

        return tables, database_name

    # ── Extração de tabelas do SQL ───────────────────────────────
    def _extract_tables_from_sql(self, sql: str) -> list[str]:
        cte_names: set[str] = set()
        for m in _RE_CTE.finditer(sql):
            name = m.group(1) or m.group(2)
            if name:
                cte_names.add(name.lower())

        tables: list[str] = []
        for m in _RE_FROM_JOIN.finditer(sql):
            raw = m.group(1).strip()
            clean = re.sub(r'\[([^\]]+)\]', r'\1', raw).strip("\"' ")
            base = clean.split(".")[-1].lower()
            if base in cte_names:
                continue
            if clean.startswith("("):
                continue
            if clean and not clean.isdigit():
                tables.append(clean)

        return list(dict.fromkeys(tables))

    # ── Extração de path para DataSet ───────────────────────────
    def _extract_dataset_path(self, rec: str) -> Optional[str]:
        m = re.search(r'Name "dataset"\s*\n\s*Value "([^"]+)"', rec, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        m = re.search(r'Name "file"\s*\n\s*Value "([^"]+)"', rec, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        return None

    def _extract_file_path_from_xml(self, xml: str) -> Optional[str]:
        for tag in ("FilePattern", "DatasetName", "Filename", "FileName"):
            m = re.search(rf'<{tag}[^>]*><!\[CDATA\[(.*?)\]\]>', xml, re.DOTALL)
            if m:
                val = m.group(1).strip()
                if val:
                    return val
        return None


# ── CLI ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    import argparse

    parser = argparse.ArgumentParser(description="Extrator de Lineage DataStage (.dsx)")
    parser.add_argument("-d", "--diretorio", required=True)
    parser.add_argument("-p", "--projeto",   required=True)
    parser.add_argument("-j", "--job",       required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    engine    = DSXEngine(diretorio_base=args.diretorio)
    resultado = engine.extrair(project_name=args.projeto, job_name=args.job)

    if args.json:
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
    else:
        if resultado.get("erro"):
            print(f"\n[X] ERRO: {resultado['erro']}\n")
        else:
            dados = resultado["dados"]
            print(f"\n--- {len(dados)} pontos de contato: {args.job} ---\n")
            fmt = f"{'DIREÇÃO':<14} | {'TIPO':<25} | {'OBJETO':<35} | {'TABELAS/ARQUIVO':<40} | COLUNAS"
            print(fmt)
            print("-" * 140)
            for d in dados:
                detail = (d.get("sql_expression") or d.get("file_path") or "").replace("\n", ", ")[:40]
                cols   = ", ".join(d.get("columns") or [])[:40]
                print(f"{d['direction']:<14} | {d['stage_type_raw']:<25} | {d['object_name']:<35} | {detail:<40} | {cols}")
