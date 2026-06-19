"""
Testes do extrator de lineage do XML (<DSExport>) — ds_xml_lineage.

Fixture sintético no formato real (ODBCStage + ODBCOutput/ODBCInput + Transformer
+ Columns). Cobre: origem (SELECT→tabela do FROM), lineage de coluna
(SourceColumn), destino (TableName + SqlInsert) e transformação (Expression).
SOMENTE LEITURA — não toca banco nem Airflow.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DAGS = ROOT / "dags"
if str(DAGS) not in sys.path:
    sys.path.insert(0, str(DAGS))

from utils import ds_xml_lineage as L  # noqa: E402

FIXTURE = r"""<?xml version="1.0" encoding="UTF-8"?>
<DSExport>
   <Header ToolInstanceID="TESTPROJ" ServerVersion="11.7"/>
   <Job Identifier="JobX">
      <Record Identifier="ROOT" Type="JobDefn"><Property Name="Name">JobX</Property></Record>
      <Record Identifier="V0S1" Type="ODBCStage">
         <Property Name="Name">SRC</Property>
         <Property Name="DSN">STG_DES</Property>
         <Property Name="OutputPins">V0S1P1</Property>
      </Record>
      <Record Identifier="V0S1P1" Type="ODBCOutput">
         <Property Name="Name">Link_Read</Property>
         <Property Name="Partner">V0S1|V0S1P1</Property>
         <Property Name="SqlPrimary">SELECT NUM_CARGA FROM GE_002_CARGA WHERE X=1;</Property>
         <Collection Name="Columns" Type="OutputColumn">
            <SubRecord>
               <Property Name="Name">NUM_CARGA</Property>
               <Property Name="SqlType">4</Property>
               <Property Name="Precision">10</Property>
               <Property Name="Nullable">0</Property>
               <Property Name="KeyPosition">1</Property>
               <Property Name="SourceColumn">TDDB00.dbo.TB_CARGA.NUM_CARGA</Property>
               <Property Name="TableDef">ODBC\STG_DES\TDDB00.dbo.TB_CARGA</Property>
            </SubRecord>
         </Collection>
      </Record>
      <Record Identifier="V0S2" Type="ODBCStage">
         <Property Name="Name">TGT</Property>
         <Property Name="DSN">STG_GRA</Property>
         <Property Name="InputPins">V0S2P1</Property>
      </Record>
      <Record Identifier="V0S2P1" Type="ODBCInput">
         <Property Name="Name">Link_Write</Property>
         <Property Name="Partner">V0S2|V0S2P1</Property>
         <Property Name="TableName">GE_004_EXEC_PROCESSO</Property>
         <Property Name="SqlInsert">INSERT INTO GE_004_EXEC_PROCESSO(NUM_CARGA) VALUES (?);</Property>
      </Record>
      <Record Identifier="V0S3" Type="TransformerStage">
         <Property Name="Name">TRF</Property>
         <Property Name="StageType">CTransformerStage</Property>
         <Collection Name="StageVars" Type="StageVar">
            <SubRecord><Property Name="Name">v1</Property><Property Name="Expression">a + 1</Property></SubRecord>
         </Collection>
      </Record>
   </Job>
</DSExport>
"""


def _extract(tmp_path):
    f = tmp_path / "sample.xml"
    f.write_text(FIXTURE, encoding="utf-8")
    return L.extract_lineage(str(f))


def test_origem_tabela_e_database(tmp_path):
    data = _extract(tmp_path)
    assert "JobX" in data
    org = data["JobX"]["origens"]
    assert len(org) == 1
    assert org[0]["object_name"] == "GE_002_CARGA"      # tabela física do FROM
    assert org[0]["database_name"] == "STG_DES"
    assert org[0]["sql_expression"].startswith("SELECT NUM_CARGA")


def test_lineage_de_coluna(tmp_path):
    org = _extract(tmp_path)["JobX"]["origens"][0]
    assert org["col_lineage"] == [{"col": "NUM_CARGA", "from": "TDDB00.dbo.TB_CARGA.NUM_CARGA"}]
    col = org["columns"][0]
    assert col["name"] == "NUM_CARGA" and col["type"] == "INTEGER" and col["key"] is True


def test_destino_tabela_e_sql(tmp_path):
    dest = _extract(tmp_path)["JobX"]["destinos"]
    assert len(dest) == 1
    assert dest[0]["object_name"] == "GE_004_EXEC_PROCESSO"
    assert dest[0]["database_name"] == "STG_GRA"
    assert "SqlInsert" in dest[0]["actions"]


def test_transformacao(tmp_path):
    trf = _extract(tmp_path)["JobX"]["transformacoes"]
    assert len(trf) == 1
    assert trf[0]["object_name"] == "TRF"
    assert {"target": "v1", "expr": "a + 1"} in trf[0]["derivations"]
