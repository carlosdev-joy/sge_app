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

    def _extract_tables_from_component(self, record_content):
        tables = []
        table_name_match = re.search(r"<TableName[^>]*><!\[CDATA\[(.*?)\]\]></TableName>", record_content)
        if table_name_match and table_name_match.group(1).strip():
            tables.append(table_name_match.group(1).strip())

        select_match = re.search(
            r"<SelectStatement[^>]*><!\[CDATA\[(.*?)\]\]></SelectStatement>", record_content, re.DOTALL
        )
        if select_match:
            sql_text = select_match.group(1)

            cte_pattern = re.compile(r"\b(?:WITH|,)\s+([a-zA-Z0-9_]+)\s+AS\s*\(", re.IGNORECASE)
            cte_blacklist = {cte.strip().lower() for cte in cte_pattern.findall(sql_text)}

            pattern = re.compile(r"\b(?:FROM|JOIN)\s+([a-zA-Z0-9_.\[\]]+)", re.IGNORECASE)
            for t in pattern.findall(sql_text):
                t_clean = t.strip()
                t_compare = t_clean.split(".")[-1].replace("[", "").replace("]", "").lower()

                if t_clean and (t_compare not in cte_blacklist):
                    tables.append(t_clean)

        return list(dict.fromkeys(tables))

    def _extract_select_statement(self, record_content: str) -> str:
        select_match = re.search(
            r"<SelectStatement[^>]*><!\[CDATA\[(.*?)\]\]></SelectStatement>", record_content, re.DOTALL
        )
        if select_match:
            return select_match.group(1).strip()
        return ""

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

                tables_or_files = []
                sql_expression = ""
                file_path = ""

                if any(db_type in raw_type for db_type in ["ODBC", "Oracle", "DB2", "SQL"]):
                    tables_or_files = self._extract_tables_from_component(record)
                    sql_expression = self._extract_select_statement(record)
                elif any(file_type in raw_type for file_type in ["DataSet", "SequentialFile"]):
                    file_name = self._extract_file_name(record)
                    if file_name:
                        tables_or_files = [file_name]
                    file_path = self._extract_file_path(record)

                # Fase 2: retornar TODOS os stages (inclui transformações)
                # - Para estágios com múltiplas tabelas (FROM/JOIN), gera 1 registro por tabela.
                # - Para transformações (sem tabela/arquivo), gera 1 registro com object_name=stage.
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
                            "sql_expression": sql_expression or None,
                            "file_path": file_path or None,
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
                                "sql_expression": sql_expression or None,
                                "file_path": file_path or None,
                            }
                        )

        return {"sucesso": True, "dados": self.extracted_lineage}

