"""
Testes do parser de malha (ds_xml_malha) — formato <DSExport> do DataStage.

Usa um fixture sintético (não depende de export real nem de Airflow/banco).
Cobre: classificação sequence/executor, resolução de executor genérico
(ParmNomeJob), raiz correta, árvore e lista monitorável.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DAGS = ROOT / "dags"
if str(DAGS) not in sys.path:
    sys.path.insert(0, str(DAGS))

from utils import ds_xml_malha as M  # noqa: E402

# Fixture: MasterSeq chama JobA (direto), ExecWrapper (executor, via ParmNomeJob=RealBizJob)
# e SubSeq (que chama JobB). ExecWrapper declara ParmNomeJob como parâmetro → é executor.
FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<DSExport>
   <Header ToolInstanceID="TESTPROJ" ServerName="srv01" ServerVersion="11.7"/>
   <Job Identifier="MasterSeq">
      <Record Identifier="ROOT" Type="JobDefn"><Property Name="Name">MasterSeq</Property></Record>
      <Record Identifier="a1" Type="JSJobActivity">
         <Property Name="Name">a1</Property><Property Name="Jobname">JobA</Property>
      </Record>
      <Record Identifier="a2" Type="JSJobActivity">
         <Property Name="Name">a2</Property><Property Name="Jobname">ExecWrapper</Property>
         <Collection Name="Arguments" Type="Argument">
            <SubRecord><Property Name="Name">ParmNomeJob</Property><Property Name="Value">RealBizJob</Property></SubRecord>
         </Collection>
      </Record>
      <Record Identifier="a3" Type="JSJobActivity">
         <Property Name="Name">a3</Property><Property Name="Jobname">SubSeq</Property>
      </Record>
   </Job>
   <Job Identifier="ExecWrapper">
      <Record Identifier="ROOT" Type="JobDefn"><Property Name="Name">ExecWrapper</Property>
         <Collection Name="Parameters" Type="Parameters">
            <SubRecord><Property Name="Name">ParmNomeJob</Property><Property Name="ParamType">0</Property></SubRecord>
         </Collection>
      </Record>
      <Record Identifier="w1" Type="JSJobActivity">
         <Property Name="Name">w1</Property><Property Name="Jobname">InnerJob</Property>
      </Record>
   </Job>
   <Job Identifier="SubSeq">
      <Record Identifier="ROOT" Type="JobDefn"><Property Name="Name">SubSeq</Property></Record>
      <Record Identifier="s1" Type="JSJobActivity">
         <Property Name="Name">s1</Property><Property Name="Jobname">JobB</Property>
      </Record>
   </Job>
   <Job Identifier="JobA"><Record Identifier="ROOT" Type="JobDefn"><Property Name="Name">JobA</Property></Record></Job>
   <Job Identifier="JobB"><Record Identifier="ROOT" Type="JobDefn"><Property Name="Name">JobB</Property></Record></Job>
   <Job Identifier="RealBizJob"><Record Identifier="ROOT" Type="JobDefn"><Property Name="Name">RealBizJob</Property></Record></Job>
</DSExport>
"""


def _parsed(tmp_path):
    f = tmp_path / "sample.xml"
    f.write_text(FIXTURE, encoding="utf-8")
    return M.parse_file(str(f))


def test_parse_basico(tmp_path):
    p = _parsed(tmp_path)
    assert p["sucesso"] and p["project"] == "TESTPROJ" and p["version"] == "11.7"
    assert set(p["jobs"]) == {"MasterSeq", "ExecWrapper", "SubSeq", "JobA", "JobB", "RealBizJob"}


def test_classificacao_executor_e_sequence(tmp_path):
    p = _parsed(tmp_path)
    assert p["jobs"]["MasterSeq"]["is_sequence"] and not p["jobs"]["MasterSeq"]["is_executor"]
    assert p["jobs"]["ExecWrapper"]["is_executor"]          # declara ParmNomeJob
    assert not p["jobs"]["JobA"]["is_sequence"]


def test_raiz_exclui_executor(tmp_path):
    p = _parsed(tmp_path)
    # ExecWrapper é executor → fora; SubSeq é chamado → não é raiz
    assert M.root_sequences(p) == ["MasterSeq"]
    assert M._best_root(p) == "MasterSeq"


def test_resolucao_executor_na_arvore(tmp_path):
    p = _parsed(tmp_path)
    tree = M.build_tree(p)
    nomes = [c["name"] for c in tree["children"]]
    assert "RealBizJob" in nomes      # resolveu ParmNomeJob (não o wrapper)
    assert "ExecWrapper" not in nomes
    assert "SubSeq" in nomes


def test_monitoraveis_sao_jobs_reais(tmp_path):
    p = _parsed(tmp_path)
    mon = set(M.monitorable_jobs(p))
    assert mon == {"JobA", "RealBizJob", "JobB"}   # folhas; sem sequences/executor


def test_arquivo_inexistente_ou_invalido(tmp_path):
    bad = tmp_path / "x.xml"
    bad.write_text("<NotDSExport/>", encoding="utf-8")
    assert M.parse_file(str(bad)).get("erro")
