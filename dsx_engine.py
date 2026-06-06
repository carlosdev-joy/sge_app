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
"""

from __future__ import annotations

import os
import re
from typing import Optional

# ── Variável de ambiente para localização dos arquivos .dsx ──────
_DEFAULT_DSX_DIR = os.environ.get("DSX_BASE_DIR", "/opt/airflow/dsx")

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

    # Alias mantido para retrocompatibilidade com código existente
    def buscar_linhagem(self, nome_projeto: str, nome_job: str) -> dict:
        result = self.extrair(nome_projeto, nome_job)
        if "erro" in result:
            return result
        # Converter para formato legado se necessário
        dados_legado = []
        for d in result["dados"]:
            dados_legado.append({
                "Projeto":          d["project_name"],
                "Job":              d["job_name"],
                "Direção":          d["direction"].capitalize(),
                "Tipo de Objeto":   d["stage_type_raw"],
                "Nome do Objeto":   d["object_name"],
                "Tabela / Arquivo": d.get("sql_expression", "") or d.get("file_path", "") or "",
            })
        return {"sucesso": True, "dados": dados_legado}

    # ── Extração do bloco do job ────────────────────────────────
    def _extract_job_block(self, content: str, job_name: str) -> Optional[str]:
        """
        Extrai o bloco BEGIN DSJOB ... (next BEGIN DSJOB) para o job dado.
        Usa str.find para evitar regex sobre o arquivo completo.
        """
        marker = f'BEGIN DSJOB\n   Identifier "{job_name}"'
        start = content.find(marker)
        if start < 0:
            # Tenta com \r\n (Windows line endings)
            marker = f'BEGIN DSJOB\r\n   Identifier "{job_name}"'
            start = content.find(marker)
        if start < 0:
            return None
        # Encontrar o próximo job para delimitar
        next_job = content.find("BEGIN DSJOB", start + len(marker))
        end = next_job if next_job > 0 else len(content)
        return content[start:end]

    # ── Parsing dos stages ──────────────────────────────────────
    def _parse_stages(self, job_block: str, project_name: str,
                      job_name: str, dsx_file: str) -> list[dict]:
        """
        Itera os DSRECORD do job e extrai lineage de cada stage.
        """
        records = self._split_records(job_block)
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # Índice de paths de DataSet por Identifier (vêm de pin records filhos)
        dataset_paths = self._index_dataset_paths(records)

        results = []
        for rec in records:
            stage = self._process_record(
                rec, project_name, job_name, dsx_file, now, dataset_paths
            )
            if stage:
                results.append(stage)

        return results

    def _index_dataset_paths(self, records: list[str]) -> dict[str, str]:
        """
        Mapeia Identifier → path do DataSet para pin records (CCustomInput/CCustomOutput).
        Ex: {"V0S4P3": "#SSD_DIROT.ParmDirDst#/DS_COBERTURA"}
        """
        paths: dict[str, str] = {}
        for rec in records:
            if 'CCustomInput' not in rec and 'CCustomOutput' not in rec:
                continue
            ident_m = re.search(r'^\s+Identifier\s+"([^"]+)"', rec, re.MULTILINE)
            path_m  = re.search(r'Name "dataset"\s*\n\s*Value "([^"]+)"', rec, re.IGNORECASE)
            if ident_m and path_m:
                paths[ident_m.group(1)] = path_m.group(1).strip()
            # SequentialFile usa "file"
            elif ident_m:
                fpath_m = re.search(r'Name "file"\s*\n\s*Value "([^"]+)"', rec, re.IGNORECASE)
                if fpath_m:
                    paths[ident_m.group(1)] = fpath_m.group(1).strip()
        return paths

    # ── Split de DSRECORD (linha a linha — sem regex enorme) ────
    def _split_records(self, block: str) -> list[str]:
        """Extrai blocos BEGIN DSRECORD ... END DSRECORD sem regex DOTALL."""
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
                        dataset_paths: dict | None = None) -> Optional[dict]:
        """Extrai metadados de lineage de um DSRECORD individual."""
        # Só processa stages reais (CCustomStage / CStage)
        if 'OLEType "CCustomStage"' not in rec and 'OLEType "CStage"' not in rec:
            return None

        # Nome e tipo
        name_m      = re.search(r'^\s+Name\s+"([^"]+)"', rec, re.MULTILINE)
        stagetype_m = re.search(r'StageType\s+"([^"]+)"', rec)
        if not name_m or not stagetype_m:
            return None

        stage_name = name_m.group(1)
        stage_type = stagetype_m.group(1)

        # Ignorar containers / subrecords sem tipo real
        if stage_name in ("ROOT", "Job"):
            return None

        # Direção
        direction = self._infer_direction(rec, stage_type)

        # Extrair XMLProperties blob (delimitado por =+=+=+=)
        xml_blob = self._extract_xml_blob(rec)

        # Campos enriquecidos
        sql_expression: Optional[str] = None
        file_path:      Optional[str] = None
        database_name:  Optional[str] = None
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
            object_type = "Banco de Dados (ODBC)"

        if is_file:
            # Tentar primeiro o subrecord direto no stage
            file_path = self._extract_dataset_path(rec)
            # Se não achou, procurar nos pin records filhos via Identifier
            if not file_path and dataset_paths:
                # Pegar Identifiers de InputPins e OutputPins do stage
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
            object_type = "Arquivo DataSet (.ds/.dx)" if "DataSet" in stage_type else "Arquivo Sequencial"

        return {
            "project_name":     project_name,
            "job_name":         job_name,
            "direction":        direction,
            "stage_name":       stage_name,
            "stage_type_raw":   stage_type,
            "object_name":      stage_name,
            "object_type":      object_type,
            "database_name":    database_name,
            "sql_expression":   sql_expression,
            "file_path":        file_path,
            "dsx_source_file":  dsx_file,
            "extracted_at":     now,
            "extraction_method": "dsx_auto",
        }

    # ── Direção do stage ────────────────────────────────────────
    def _infer_direction(self, rec: str, stage_type: str) -> str:
        """Determina origem / destino / transformacao."""
        if stage_type in _TRANSFORM_TYPES:
            return "transformacao"

        # Context é o mais confiável: DataStage grava "source" ou "target"
        ctx_m = re.search(r'Name "Context"\s*\n\s*Value "([^"]+)"', rec)
        if ctx_m:
            ctx = ctx_m.group(1).strip().lower()
            if ctx == "source":
                return "origem"
            if ctx in ("target", "write"):
                return "destino"

        # Fallback topológico: InputPins / OutputPins
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
        """
        Extrai o XML do subrecord XMLProperties.
        DataStage usa dois formatos:
          1. Multi-linha:  Value =+=+=+=\\n<xml>\\n=+=+=+=   (queries longas)
          2. Linha única:  Value "<xml>"                      (queries curtas)
        """
        SENTINEL = "=+=+=+="
        # ── Formato 1: multi-linha ───────────────────────────────
        start = rec.find(SENTINEL)
        if start >= 0:
            start += len(SENTINEL)
            end = rec.find(SENTINEL, start)
            if end >= 0:
                return rec[start:end].strip()

        # ── Formato 2: linha única entre aspas ─────────────────────
        # Captura: Name "XMLProperties"\n   Value "..."
        m = re.search(
            r'Name\s+"XMLProperties"\s*\n\s*Value\s+"((?:[^"\\]|\\.)*)"',
            rec, re.DOTALL
        )
        if m:
            # Desescapar aspas internas (\" → ")
            raw = m.group(1).replace('\\"', '"')
            return raw.strip()

        return None

    # ── Extração de tabelas DB e database name ───────────────────
    def _extract_db_info(self, xml: str) -> tuple[list[str], Optional[str]]:
        """
        Extrai nomes de tabelas (FROM/JOIN) e hint do banco.
        Retorna (tabelas, database_name).
        """
        tables: list[str] = []

        # ── TableName explícito (INSERT/UPDATE destinos) ─────────
        tn_m = re.search(r'<TableName[^>]*><!\[CDATA\[(.*?)\]\]>', xml, re.DOTALL)
        if tn_m:
            tn = tn_m.group(1).strip()
            if tn:
                tables.append(tn)

        # ── SQL via SelectStatement / WriteStatement ─────────────
        for tag in ("SelectStatement", "WriteStatement", "InsertStatement"):
            sql_m = re.search(
                rf'<{tag}[^>]*><!\[CDATA\[(.*?)\]\]>',
                xml, re.DOTALL
            )
            if sql_m:
                sql_raw = sql_m.group(1)
                # Decodificar escapes DataStage \(XX) → char
                sql = _RE_DSX_ESCAPE.sub(
                    lambda m: chr(int(m.group(1), 16)), sql_raw
                )
                tables.extend(self._extract_tables_from_sql(sql))
                break   # considera apenas o primeiro statement

        # Deduplicar preservando ordem
        tables = list(dict.fromkeys(t for t in tables if t))

        # ── Database hint ────────────────────────────────────────
        database_name = None
        ds_m = re.search(r'<DataSource[^>]*><!\[CDATA\[(.*?)\]\]>', xml, re.DOTALL)
        if ds_m:
            ds_raw = ds_m.group(1).strip()
            # Extrair nome real se não for parâmetro
            if not ds_raw.startswith("#"):
                database_name = ds_raw
            else:
                # Tentar extrair hint do nome do parâmetro
                # Ex: #SSD_DIROT.ParmDbNameDMDB42# → DMDB42
                hint = _RE_DB_HINT.search(ds_raw)
                if hint:
                    database_name = hint.group(1)

        return tables, database_name

    # ── Extração de tabelas do SQL ───────────────────────────────
    def _extract_tables_from_sql(self, sql: str) -> list[str]:
        """
        Extrai apenas nomes de tabelas referenciadas em FROM e JOIN.
        Exclui CTEs, subqueries e aliases.
        Robusto para queries grandes sem risco de backtracking.
        """
        # Coletar nomes de CTEs para excluir
        cte_names: set[str] = set()
        for m in _RE_CTE.finditer(sql):
            name = m.group(1) or m.group(2)
            if name:
                cte_names.add(name.lower())

        tables: list[str] = []
        for m in _RE_FROM_JOIN.finditer(sql):
            raw = m.group(1).strip()
            # Remover brackets SQL: [dbo].[table] → dbo.table
            clean = re.sub(r'\[([^\]]+)\]', r'\1', raw).strip("\"' ")
            # Ignorar se é alias de CTE
            base = clean.split(".")[-1].lower()
            if base in cte_names:
                continue
            # Ignorar subqueries abertas
            if clean.startswith("("):
                continue
            # Ignorar strings vazias ou números
            if clean and not clean.isdigit():
                tables.append(clean)

        return list(dict.fromkeys(tables))

    # ── Extração de path para DataSet ───────────────────────────
    def _extract_dataset_path(self, rec: str) -> Optional[str]:
        """
        Procura o path do DataSet no subrecord simples:
          Name "dataset"
          Value "/caminho/do/arquivo"
        """
        m = re.search(r'Name "dataset"\s*\n\s*Value "([^"]+)"', rec, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        # Variante SequentialFile
        m = re.search(r'Name "file"\s*\n\s*Value "([^"]+)"', rec, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        return None

    def _extract_file_path_from_xml(self, xml: str) -> Optional[str]:
        """Fallback: procura caminho de arquivo dentro do blob XML."""
        for tag in ("FilePattern", "DatasetName", "Filename", "FileName"):
            m = re.search(rf'<{tag}[^>]*><!\[CDATA\[(.*?)\]\]>', xml, re.DOTALL)
            if m:
                val = m.group(1).strip()
                if val:
                    return val
        return None


# ── CLI (mantém compatibilidade com lineage.py original) ─────────
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
            fmt = f"{'DIREÇÃO':<14} | {'TIPO':<25} | {'OBJETO':<35} | {'TABELAS / PATH'}"
            print(fmt)
            print("-" * 120)
            for d in dados:
                detail = d.get("sql_expression", "") or d.get("file_path", "") or ""
                detail = detail.replace("\n", ", ")[:80]
                print(f"{d['direction']:<14} | {d['stage_type_raw']:<25} | {d['object_name']:<35} | {detail}")