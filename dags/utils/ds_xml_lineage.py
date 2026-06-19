"""ds_xml_lineage.py — Extrai LINEAGE do export XML <DSExport> do DataStage.

APARTADO e SOMENTE-LEITURA: lê o XML (mesmo arquivo da Malha DS) e devolve, por
job, origens/destinos/transformações com tabela, SQL, database, colunas e lineage
de coluna. NÃO grava no banco — serve para PREVIEW/validação e, depois, para uma
carga opcional (sp_etl_job_lineage_upsert, extraction_method='xml_export').

Mapeamento confirmado em export real (BI_VIDA, DS 11.7):
  Record Type="ODBCStage"       → stage + DSN (conexão, geralmente parametrizada)
  Record Type="ODBCOutput"      → ORIGEM  (SqlPrimary = SELECT; Columns; Partner→stage)
  Record Type="ODBCInput"       → DESTINO (TableName + SqlInsert/Update/Delete)
  Record Type="TransformerStage"→ TRANSFORMAÇÃO (StageVars/derivações = Expression)
  Collection Name="Columns"     → colunas (Name, SqlType, Precision, Scale, Nullable)
  coluna.SourceColumn/ParsedDerivation → lineage de coluna (db.schema.tabela.coluna)
  coluna.TableDef = ODBC\<DSN>\<db>.<schema>.<tabela>
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

# Tabela física a partir do SQL (a que realmente roda; TableDef guarda a modelada).
_RE_FROM   = re.compile(r"\bFROM\s+([A-Za-z0-9_\.\[\]\"#]+)", re.I)
_RE_JOIN   = re.compile(r"\bJOIN\s+([A-Za-z0-9_\.\[\]\"#]+)", re.I)
_RE_INTO   = re.compile(r"\bINTO\s+([A-Za-z0-9_\.\[\]\"#]+)", re.I)
_RE_UPDATE = re.compile(r"\bUPDATE\s+([A-Za-z0-9_\.\[\]\"#]+)", re.I)
_RE_DELETE = re.compile(r"\bDELETE\s+FROM\s+([A-Za-z0-9_\.\[\]\"#]+)", re.I)

# SqlType ODBC → rótulo legível (subset comum)
_SQLTYPE = {
    "1": "CHAR", "12": "VARCHAR", "-9": "NVARCHAR", "-1": "TEXT",
    "4": "INTEGER", "5": "SMALLINT", "-5": "BIGINT", "-6": "TINYINT",
    "2": "NUMERIC", "3": "DECIMAL", "6": "FLOAT", "7": "REAL", "8": "DOUBLE",
    "91": "DATE", "92": "TIME", "93": "TIMESTAMP", "-7": "BIT",
}


def _props(rec) -> dict:
    return {p.get("Name"): (p.text or "").strip() for p in rec.findall("Property")}


def _columns(rec) -> list[dict]:
    cols: list[dict] = []
    for col in rec.findall("Collection"):
        if col.get("Name") != "Columns":
            continue
        for sr in col.findall("SubRecord"):
            p = _props(sr)
            cols.append({
                "name":          p.get("Name"),
                "type":          _SQLTYPE.get(p.get("SqlType"), p.get("SqlType")),
                "precision":     p.get("Precision"),
                "scale":         p.get("Scale"),
                "nullable":      p.get("Nullable") != "0",
                "key":           p.get("KeyPosition") not in (None, "0"),
                "source_column": p.get("SourceColumn") or p.get("ParsedDerivation") or None,
                "table_def":     p.get("TableDef") or None,
            })
    return cols


def _parse_tabledef(td: str | None):
    """ODBC\\STG_DES\\TDDB00.dbo.TB_CARGA → (dsn='STG_DES', fqtn='TDDB00.dbo.TB_CARGA')."""
    if not td:
        return (None, None)
    parts = td.split("\\")
    return (parts[1] if len(parts) > 2 else None, parts[-1])


def _tables(sql: str | None, write: bool) -> list[str]:
    """Tabelas físicas referenciadas no SQL (FROM/JOIN para leitura; INTO/UPDATE/DELETE
    para escrita). Remove aspas/colchetes e duplicatas, preservando ordem."""
    if not sql:
        return []
    found: list[str] = []
    pats = (_RE_INTO, _RE_UPDATE, _RE_DELETE) if write else (_RE_FROM, _RE_JOIN)
    for pat in pats:
        for m in pat.findall(sql):
            t = m.strip().strip('"[]')
            if t and not t.startswith("#") and t.lower() not in (x.lower() for x in found):
                found.append(t)
    return found


def _stage_index(records) -> dict:
    """Identifier do stage → {name, dsn, type}. Os links (Input/Output) apontam para
    o stage via Partner='<stageId>|<pin>'."""
    idx: dict = {}
    for r in records:
        t = r.get("Type") or ""
        if t.endswith("Stage"):
            p = _props(r)
            idx[r.get("Identifier")] = {
                "name": p.get("Name"),
                "dsn":  p.get("DSN") or p.get("Database") or None,
                "type": p.get("StageType") or t,
            }
    return idx


def _stage_for(rec, stages: dict) -> dict:
    """Stage dono do link = prefixo do Identifier do próprio record (sem o pin 'P<n>').
    Ex.: link 'V0S21P1' pertence ao stage 'V0S21'. (O Partner é a OUTRA ponta.)"""
    return stages.get(re.sub(r"P\d+$", "", rec.get("Identifier") or ""), {})


def extract_job_lineage(job) -> dict:
    """Lineage de UM <Job> do export. Devolve {origens, destinos, transformacoes}."""
    records = job.findall("Record")
    stages  = _stage_index(records)
    origens, destinos, transf = [], [], []

    for r in records:
        t = r.get("Type") or ""
        p = _props(r)
        stage = _stage_for(r, stages)

        if t in ("ODBCOutput", "OracleOutput", "DRSOutput"):  # leitura (origem)
            sql  = p.get("SqlPrimary") or p.get("SqlSelect") or p.get("SelectStatement")
            cols = _columns(r)
            dsn_c, fqtn = _parse_tabledef(next((c["table_def"] for c in cols if c["table_def"]), None))
            tabelas = _tables(sql, write=False) or ([fqtn] if fqtn else []) or ([p.get("TableNames")] if p.get("TableNames") else [])
            origens.append({
                "object_type": "Tabela",
                "object_name": tabelas[0] if tabelas else (p.get("TableNames") or None),
                "tables_all":  tabelas,
                "stage_name":  stage.get("name") or p.get("Name"),
                "stage_type_raw": stage.get("type"),
                "database_name":  dsn_c or stage.get("dsn"),
                "sql_expression": sql,
                "columns":     cols,
                "col_lineage": [{"col": c["name"], "from": c["source_column"]}
                                for c in cols if c.get("source_column")],
            })
        elif t in ("ODBCInput", "OracleInput", "DRSInput"):   # escrita (destino)
            sql  = p.get("SqlInsert") or p.get("SqlUpdate") or p.get("SqlDelete")
            cols = _columns(r)
            tabelas = ([p.get("TableName")] if p.get("TableName") else []) or _tables(sql, write=True)
            destinos.append({
                "object_type": "Tabela",
                "object_name": tabelas[0] if tabelas else None,
                "tables_all":  tabelas,
                "stage_name":  stage.get("name") or p.get("Name"),
                "stage_type_raw": stage.get("type"),
                "database_name":  stage.get("dsn"),
                "sql_expression": sql,
                "columns":     cols,
                "actions":     {k: p.get(k) for k in ("SqlInsert", "SqlUpdate", "SqlDelete") if p.get(k)},
            })
        elif t in ("HashedOutput",):                          # arquivo hash (origem)
            origens.append({"object_type": "Arquivo", "object_name": p.get("FileName") or stage.get("name"),
                            "stage_name": stage.get("name") or p.get("Name"), "stage_type_raw": stage.get("type"),
                            "file_path": p.get("FileName"), "columns": _columns(r)})
        elif t in ("HashedInput",):                           # arquivo hash (destino)
            destinos.append({"object_type": "Arquivo", "object_name": p.get("FileName") or stage.get("name"),
                            "stage_name": stage.get("name") or p.get("Name"), "stage_type_raw": stage.get("type"),
                            "file_path": p.get("FileName"), "columns": _columns(r)})
        elif t == "TransformerStage":                         # transformação
            derivs = []
            for col in r.findall("Collection"):
                if col.get("Name") in ("StageVars", "OutputColumn", "TrxOutput"):
                    for sr in col.findall("SubRecord"):
                        sp = _props(sr)
                        if sp.get("Expression") or sp.get("Derivation"):
                            derivs.append({"target": sp.get("Name"),
                                           "expr": sp.get("Expression") or sp.get("Derivation")})
            if derivs:
                transf.append({"object_type": "Transformacao", "object_name": p.get("Name"),
                               "stage_name": p.get("Name"), "stage_type_raw": p.get("StageType"),
                               "derivations": derivs})

    return {"origens": _dedup(origens), "destinos": _dedup(destinos), "transformacoes": transf}


def _dedup(items: list[dict]) -> list[dict]:
    """Une por object_name (mantém o primeiro, mais rico)."""
    seen: dict = {}
    out: list[dict] = []
    for it in items:
        key = (it.get("object_type"), (it.get("object_name") or "").lower())
        if key in seen:
            continue
        seen[key] = True
        out.append(it)
    return out


def extract_lineage(path: str) -> dict:
    """Lineage de TODOS os jobs do export. {job_name: {origens, destinos, transformacoes}}."""
    root = ET.parse(path).getroot()
    out: dict = {}
    for job in root.findall("Job"):
        jid = job.get("Identifier")
        lin = extract_job_lineage(job)
        if lin["origens"] or lin["destinos"] or lin["transformacoes"]:
            out[jid] = lin
    return out
