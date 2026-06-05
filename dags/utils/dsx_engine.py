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

    def _extract_database_name(self, record_content: str) -> str | None:
        """
        Extrai o nome do banco/DSN ao qual o stage ODBC está conectado.
        Tenta diversas formas em que o DataStage grava essa informação no DSX.
        """
        # 1. CDATA tags mais comuns (ODBC Connector PX / Server ODBC)
        for tag in ["DataSourceName", "DatabaseName", "Database", "DSN", "DataSource"]:
            m = re.search(
                rf"<{tag}[^>]*><!\[CDATA\[(.*?)\]\]></{tag}>",
                record_content, re.IGNORECASE | re.DOTALL
            )
            if m and m.group(1).strip():
                return m.group(1).strip()

        # 2. Atributo XML: <DataSourceName value="..." /> ou name="..." value="..."
        m = re.search(
            r'<(?:DataSourceName|DatabaseName|DSN)[^>]+value="([^"]+)"',
            record_content, re.IGNORECASE
        )
        if m and m.group(1).strip():
            return m.group(1).strip()

        # 3. Propriedade flat-DSX:  Name "DataSourceName"  Value "MY_DSN"
        for key in ["DataSourceName", "DatabaseName", "DataSource", "DSN", "Database"]:
            m = re.search(
                rf'Name\s+"{re.escape(key)}"\s+Value\s+"([^"]+)"',
                record_content, re.IGNORECASE
            )
            if m and m.group(1).strip():
                return m.group(1).strip()

        # 4. String de conexão ODBC: DSN=NOME; ou DATABASE=NOME;
        m = re.search(r'\bDSN=([^;"\s]+)', record_content, re.IGNORECASE)
        if m and m.group(1).strip():
            return m.group(1).strip()
        m = re.search(r'\bDATABASE=([^;"\s]+)', record_content, re.IGNORECASE)
        if m and m.group(1).strip():
            return m.group(1).strip()

        return None

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
        """Parse SELECT clause and return column names/aliases (sem distinção de tabela)."""
        m = re.search(r"\bSELECT\s+(.*?)\bFROM\b", sql_text, re.IGNORECASE | re.DOTALL)
        if not m:
            return []
        select_part = m.group(1).strip()
        if select_part in ("*", "1"):
            return []
        return [col for _, col in self._tokenize_select(select_part)]

    def _tokenize_select(self, select_part: str) -> list[tuple[str | None, str]]:
        """
        Divide o SELECT em tokens e retorna lista de (alias_tabela, nome_coluna).
        alias_tabela é None quando a coluna não tem prefixo de tabela.
        """
        # Split por vírgulas de nível 0 (respeita parênteses)
        raw_tokens: list[str] = []
        depth, buf = 0, []
        for ch in select_part:
            if ch == "(":
                depth += 1; buf.append(ch)
            elif ch == ")":
                depth -= 1; buf.append(ch)
            elif ch == "," and depth == 0:
                raw_tokens.append("".join(buf).strip()); buf = []
            else:
                buf.append(ch)
        if buf:
            raw_tokens.append("".join(buf).strip())

        result: list[tuple[str | None, str]] = []
        skip = {"FROM", "WHERE", "GROUP", "ORDER", "SELECT", "HAVING", "UNION"}
        for tok in raw_tokens:
            tok = tok.strip()
            # Alias explícito: ... AS nome
            as_m = re.search(r"\bAS\s+([a-zA-Z0-9_\[\]]+)\s*$", tok, re.IGNORECASE)
            col_name = as_m.group(1).strip("[]") if as_m else None

            # Prefixo de tabela: alias.coluna
            prefix_m = re.match(r"([a-zA-Z0-9_]+)\.([a-zA-Z0-9_\[\]]+)", tok)
            tbl_alias = prefix_m.group(1).lower() if prefix_m else None

            if col_name is None:
                if prefix_m:
                    col_name = prefix_m.group(2).strip("[]")
                else:
                    id_m = re.search(r"([a-zA-Z0-9_\[\]]+)\s*$", tok)
                    if id_m:
                        col_name = id_m.group(1).strip("[]")

            if col_name and col_name.upper() not in skip:
                result.append((tbl_alias, col_name))
        return result

    def _extract_columns_per_table(self, sql_text: str) -> dict[str, list[str]]:
        """
        Retorna dict  table_name_lower → [colunas daquela tabela].
        Usa os aliases do FROM/JOIN para atribuir cada coluna à tabela correta.
        Colunas sem prefixo de alias são associadas a todas as tabelas (fallback).
        """
        # 1. Monta alias → table_name (lower, sem schema)
        alias_map: dict[str, str] = {}
        for m in re.finditer(
            r"\b(?:FROM|JOIN)\s+([a-zA-Z0-9_.\[\]]+)(?:\s+AS)?\s+([a-zA-Z0-9_]+)",
            sql_text, re.IGNORECASE
        ):
            table_full = m.group(1).strip()
            alias = m.group(2).strip().lower()
            skip_kw = {"ON", "WHERE", "INNER", "LEFT", "RIGHT", "OUTER", "FULL", "CROSS",
                       "WITH", "SET", "AND", "OR"}
            if alias.upper() in skip_kw:
                continue
            table_simple = table_full.split(".")[-1].strip("[]").lower()
            alias_map[alias] = table_simple
            alias_map[table_simple] = table_simple  # sem alias também funciona

        if not alias_map:
            return {}

        # 2. Parse SELECT
        m_sel = re.search(r"\bSELECT\s+(.*?)\bFROM\b", sql_text, re.IGNORECASE | re.DOTALL)
        if not m_sel:
            return {}
        select_part = m_sel.group(1).strip()
        if select_part in ("*", "1"):
            return {}

        tokens = self._tokenize_select(select_part)
        unaliased: list[str] = []   # colunas sem prefixo de tabela
        per_table: dict[str, list[str]] = {}

        for tbl_alias, col_name in tokens:
            if tbl_alias and tbl_alias in alias_map:
                tbl = alias_map[tbl_alias]
                per_table.setdefault(tbl, []).append(col_name)
            else:
                unaliased.append(col_name)

        # Colunas sem alias → distribui para todas as tabelas
        if unaliased:
            for tbl in set(alias_map.values()):
                per_table.setdefault(tbl, []).extend(unaliased)

        return per_table

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

                per_table_cols: dict[str, list[str]] = {}
                db_name: str | None = None

                if any(db_type in raw_type for db_type in ["ODBC", "Oracle", "DB2", "SQL"]):
                    tables_or_files = self._extract_tables_from_sql(record)
                    sql_expression = "\n".join(tables_or_files) if tables_or_files else None
                    db_name = self._extract_database_name(record)
                    # Colunas = schema de OUTPUT do stage (o que realmente flui para a próxima etapa)
                    output_cols = self._extract_schema_columns(record)
                    for tbl in tables_or_files:
                        tbl_key = tbl.split(".")[-1].strip("[]").lower()
                        per_table_cols[tbl_key] = output_cols
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
                            "database_name": db_name,
                            "sql_expression": sql_expression,
                            "file_path": file_path,
                            "columns": columns,
                        }
                    )
                else:
                    for item in tables_or_files:
                        tbl_key = item.split(".")[-1].strip("[]").lower()
                        item_cols = per_table_cols.get(tbl_key, columns)
                        self.extracted_lineage.append(
                            {
                                "project_name": nome_projeto,
                                "job_name": nome_job,
                                "direction": direction_key,
                                "stage_name": obj_name,
                                "stage_type_raw": functional_type,
                                "object_name": item,
                                "object_type": "Tabela" if any(db_type in raw_type for db_type in ["ODBC", "Oracle", "DB2", "SQL"]) else "Arquivo",
                                "database_name": db_name,
                                "sql_expression": sql_expression,
                                "file_path": file_path,
                                "columns": item_cols,
                            }
                        )

        return {"sucesso": True, "dados": self.extracted_lineage}

    # Alias usado em etl_sequence_import_parse
    def extrair(self, nome_projeto: str, nome_job: str) -> dict:
        return self.buscar_linhagem(nome_projeto, nome_job)

