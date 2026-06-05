"""
dsx_engine.py
=============
Motor de extração de lineage a partir de arquivos DataStage (.dsx).

Baseado em: linhage_busca.py (ORQUESTRA)

Adaptação [AIRFLOW]:
- Permite configurar o diretório base dos .dsx via Airflow Variable: DSX_BASE_DIR
  (default: /opt/airflow/dsx)
"""

from __future__ import annotations

import os
import re


# [AIRFLOW] — diretório base configurável
try:
    from airflow.models import Variable

    _DEFAULT_DSX_DIR = Variable.get("DSX_BASE_DIR", default_var="/opt/airflow/dsx")
except Exception:
    _DEFAULT_DSX_DIR = "/opt/airflow/dsx"


class DSXEngine:
    def __init__(self, diretorio_base: str):
        """Inicializa o motor apontando para a pasta onde ficam os arquivos .dsx"""
        self.diretorio_base = diretorio_base
        self.extracted_lineage = []

        self.type_mapping = {
            "ODBCConnectorPX": "Banco de Dados (ODBC)",
            "PxDataSet": "Arquivo DataSet (.ds/.dx)",
            "PxSequentialFile": "Arquivo Sequencial",
            "TransformerStage": "TransformerStage",
        }

    def _get_functional_name(self, stage_type):
        return self.type_mapping.get(stage_type, stage_type)

    def _extract_file_name(self, record_content):
        ds_match = re.search(r'Name "dataset"\s*Value "(.*?)"', record_content)
        if ds_match:
            return ds_match.group(1).strip()

        seq_match = re.search(r'Name "file"\s*Value "(.*?)"', record_content)
        if seq_match:
            return seq_match.group(1).strip()

        return ""

    def _extract_file_path(self, record_content: str) -> str:
        """
        Tenta capturar o path completo do arquivo (principalmente DataSet/SequentialFile).
        Em DSX, é comum aparecer em variáveis/props como:
          Name "resources.filename" Value "/caminho/arquivo.ds"
          Name "filename" Value "/caminho/arquivo.txt"
        """
        for key in ["resources.filename", "filename", "FileName", "fileName"]:
            m = re.search(rf'Name "{re.escape(key)}"\s*Value "(.*?)"', record_content, re.IGNORECASE)
            if m and m.group(1).strip():
                return m.group(1).strip()
        # fallback: alguns dumps aparecem como XMLish
        m2 = re.search(r"(resources\.filename|filename)[^\"=]*=\"([^\"]+)\"", record_content, re.IGNORECASE)
        if m2 and m2.group(2).strip():
            return m2.group(2).strip()
        return ""

    def _infer_direction_key(self, has_inputs: bool, has_outputs: bool) -> str:
        # padroniza para keys consumidas pelo ORQUESTRA
        if has_outputs and not has_inputs:
            return "origem"
        if has_inputs and not has_outputs:
            return "destino"
        if has_inputs and has_outputs:
            return "transformacao"
        return "transformacao"

    def _extract_tables_from_sql(self, record_content: str) -> list[str]:
        """
        Extrai tabelas usadas em stages ODBC:
        - <TableName><![CDATA[...]]></TableName>
        - <SelectStatement><![CDATA[ ... ]]></SelectStatement> com parsing FROM/JOIN
          e exclusão de CTEs.
        Retorna lista sem duplicatas (preservando ordem).
        """
        tables: list[str] = []

        # 1) TableName explícito (estágio com tabela configurada)
        table_name_match = re.search(
            r"<TableName[^>]*><!\[CDATA\[(.*?)\]\]></TableName>",
            record_content,
        )
        if table_name_match and table_name_match.group(1).strip():
            tables.append(table_name_match.group(1).strip())

        # 2) SelectStatement — FROM/JOIN com exclusão de CTEs
        select_match = re.search(
            r"<SelectStatement[^>]*><!\[CDATA\[(.*?)\]\]></SelectStatement>",
            record_content,
            re.DOTALL,
        )
        if select_match:
            sql_text = select_match.group(1)

            cte_pattern = re.compile(r"\b(?:WITH|,)\s+([a-zA-Z0-9_]+)\s+AS\s*\(", re.IGNORECASE)
            cte_blacklist = {cte.strip().lower() for cte in cte_pattern.findall(sql_text)}

            pattern = re.compile(r"\b(?:FROM|JOIN)\s+([a-zA-Z0-9_.\[\]]+)", re.IGNORECASE)
            for t_raw in pattern.findall(sql_text):
                t_clean = t_raw.strip()
                t_compare = t_clean.split(".")[-1].replace("[", "").replace("]", "").lower()
                if t_clean and t_compare not in cte_blacklist:
                    tables.append(t_clean)

        return list(dict.fromkeys(tables))

    def _extract_select_statement(self, record_content: str) -> str:
        select_match = re.search(
            r"<SelectStatement[^>]*><!\[CDATA\[(.*?)\]\]></SelectStatement>", record_content, re.DOTALL
        )
        if select_match:
            return select_match.group(1).strip()
        return ""

    def _extract_columns_from_select(self, sql_text: str) -> list[str]:
        """Parse SELECT clause and return column names/aliases."""
        m = re.search(r"\bSELECT\s+(.*?)\bFROM\b", sql_text, re.IGNORECASE | re.DOTALL)
        if not m:
            return []
        select_part = m.group(1).strip()
        if select_part in ("*", "1"):
            return []

        # Split by top-level commas (respects parentheses)
        tokens: list[str] = []
        depth, buf = 0, []
        for ch in select_part:
            if ch == "(":
                depth += 1; buf.append(ch)
            elif ch == ")":
                depth -= 1; buf.append(ch)
            elif ch == "," and depth == 0:
                tokens.append("".join(buf).strip()); buf = []
            else:
                buf.append(ch)
        if buf:
            tokens.append("".join(buf).strip())

        result: list[str] = []
        for tok in tokens:
            tok = tok.strip()
            as_m = re.search(r"\bAS\s+([a-zA-Z0-9_\[\]]+)\s*$", tok, re.IGNORECASE)
            if as_m:
                result.append(as_m.group(1).strip("[]"))
            else:
                id_m = re.search(r"([a-zA-Z0-9_\[\]]+)\s*$", tok)
                if id_m:
                    name = id_m.group(1).strip("[]")
                    if name and name.upper() not in ("FROM", "WHERE", "GROUP", "ORDER", "SELECT"):
                        result.append(name)
        return result

    def _extract_schema_columns(self, record_content: str) -> list[str]:
        """Extract column names from XML schema/column definitions embedded in a stage record."""
        # <Column name="..." or <Column Name="..."
        cols = re.findall(r"<Column[^>]+\bname=\"([^\"]+)\"", record_content, re.IGNORECASE)
        if cols:
            return cols
        # <SqlColumnDef name="..."
        cols = re.findall(r"<SqlColumnDef[^>]+\bname=\"([^\"]+)\"", record_content, re.IGNORECASE)
        if cols:
            return cols
        # DSX flat format: Name "COL" / SqlType "N" pairs (innermost DSRECORDs with SqlType)
        inner_records = re.findall(r"BEGIN DSRECORD(.*?)END DSRECORD", record_content, re.DOTALL)
        col_names: list[str] = []
        for inner in inner_records:
            if "SqlType" in inner or "DataType" in inner:
                nm = re.search(r'Name\s+"([^"]+)"', inner)
                if nm and nm.group(1) not in ("", "input", "output", "Input", "Output"):
                    col_names.append(nm.group(1))
        return col_names

    def buscar_linhagem(self, nome_projeto, nome_job):
        self.extracted_lineage = []

        # Monta o caminho dinâmico: diretorio_base/nome_projeto.dsx
        nome_arquivo = f"{nome_projeto}.dsx"
        file_path = os.path.join(self.diretorio_base, nome_arquivo)

        if not os.path.exists(file_path):
            return {"erro": f"Arquivo '{nome_arquivo}' não encontrado no diretório '{self.diretorio_base}'."}

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Isola o bloco do Job
        regex_job = r'BEGIN DSJOB\s+Identifier "' + re.escape(nome_job) + r'".*?END DSJOB'
        job_match = re.search(regex_job, content, re.DOTALL)

        if not job_match:
            return {"erro": f"O Job '{nome_job}' não foi encontrado dentro de '{nome_arquivo}'."}

        job_block = job_match.group(0)
        record_pattern = re.compile(r"BEGIN DSRECORD.*?END DSRECORD", re.DOTALL)
        records = record_pattern.findall(job_block)

        for record in records:
            if 'OLEType "CCustomStage"' in record or 'OLEType "CStage"' in record:
                name_match = re.search(r'Name "(.*?)"', record)
                obj_name = name_match.group(1) if name_match else "Sem Nome"

                type_match = re.search(r'StageType "(.*?)"', record)
                raw_type = type_match.group(1) if type_match else "Unknown"
                functional_type = self._get_functional_name(raw_type)

                has_inputs = "InputPins" in record
                has_outputs = "OutputPins" in record

                direction_key = self._infer_direction_key(has_inputs, has_outputs)

                tables_or_files: list[str] = []
                sql_expression: str | None = None
                file_path: str | None = None
                columns: list[str] = []

                if any(db_type in raw_type for db_type in ["ODBC", "Oracle", "DB2", "SQL"]):
                    tables_or_files = self._extract_tables_from_sql(record)
                    sql_expression = "\n".join(tables_or_files) if tables_or_files else None
                    # Extract columns: try SELECT clause first, fallback to schema definitions
                    sql_text = self._extract_select_statement(record)
                    if sql_text:
                        columns = self._extract_columns_from_select(sql_text)
                    if not columns:
                        columns = self._extract_schema_columns(record)
                elif any(file_type in raw_type for file_type in ["DataSet", "SequentialFile"]):
                    file_path = self._extract_file_name(record) or None
                    if file_path:
                        tables_or_files = [file_path]
                    columns = self._extract_schema_columns(record)
                else:
                    columns = self._extract_schema_columns(record)

                # Para estágios com múltiplas tabelas (FROM/JOIN), gera 1 registro por tabela.
                # Para transformações (sem tabela/arquivo), gera 1 registro com object_name=stage.
                if not tables_or_files:
                    self.extracted_lineage.append(
                        {
                            "project_name": nome_projeto,
                            "job_name": nome_job,
                            "direction": direction_key,
                            "stage_name": obj_name,
                            "stage_type_raw": functional_type,
                            "object_name": obj_name,
                            "object_type": "Transformação" if direction_key == "transformacao" else "",
                            "database_name": None,
                            "sql_expression": sql_expression,
                            "file_path": file_path,
                            "columns": columns,
                        }
                    )
                else:
                    for item in tables_or_files:
                        self.extracted_lineage.append(
                            {
                                "project_name": nome_projeto,
                                "job_name": nome_job,
                                "direction": direction_key,
                                "stage_name": obj_name,
                                "stage_type_raw": functional_type,
                                "object_name": item,
                                "object_type": "Tabela" if any(db_type in raw_type for db_type in ["ODBC", "Oracle", "DB2", "SQL"]) else "Arquivo",
                                "database_name": None,
                                "sql_expression": sql_expression,
                                "file_path": file_path,
                                "columns": columns,
                            }
                        )

        return {"sucesso": True, "dados": self.extracted_lineage}

    # Alias usado em etl_sequence_import_parse
    def extrair(self, nome_projeto: str, nome_job: str) -> dict:
        return self.buscar_linhagem(nome_projeto, nome_job)

