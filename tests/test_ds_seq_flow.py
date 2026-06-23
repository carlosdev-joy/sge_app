"""
Parser do fluxo (DAG) da Sequence — services/ds_seq_flow.parse_seq_flow.

Valida a extração das atividades (nós) e dos triggers (arestas via JSActivityOutput:
SourceID -> Partner) a partir do export XML, espelhando a estrutura real.
"""
from __future__ import annotations

import services.ds_seq_flow as sf

FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<DSExport>
  <Header ToolInstanceID="TESTPROJ" ServerName="srv" ServerVersion="11.7"/>
  <Job Identifier="SeqMain">
    <Record Identifier="V0S0" Type="JSJobActivity">
      <Property Name="Name">AtivJobA</Property><Property Name="Jobname">JobA</Property>
      <Property Name="OutputPins">V0S0P1</Property>
    </Record>
    <Record Identifier="V0S1" Type="JSJobActivity">
      <Property Name="Name">AtivJobB</Property><Property Name="Jobname">JobB</Property>
      <Property Name="InputPins">V0S1P2</Property><Property Name="OutputPins">V0S1P3</Property>
    </Record>
    <Record Identifier="V0S2" Type="JSSequencer">
      <Property Name="Name">WaitAll</Property><Property Name="InputPins">V0S2P4</Property>
    </Record>
    <Record Identifier="V0S0P1" Type="JSActivityOutput">
      <Property Name="Name">Ini_B</Property><Property Name="Partner">V0S1|V0S1P2</Property>
      <Property Name="ConditionType">0</Property><Property Name="TriggerExpression">N/A</Property>
      <Property Name="SourceID">V0S0</Property>
    </Record>
    <Record Identifier="V0S1P3" Type="JSActivityOutput">
      <Property Name="Name">Fim_B</Property><Property Name="Partner">V0S2|V0S2P4</Property>
      <Property Name="ConditionType">6</Property>
      <Property Name="TriggerExpression">JobB.$ReturnValue = 1</Property>
      <Property Name="SourceID">V0S1</Property>
    </Record>
    <Record Identifier="V0S1P9" Type="JSActivityInput">
      <Property Name="Partner">V0S0|V0S0P1</Property>
    </Record>
  </Job>
</DSExport>
"""


def _setup(tmp_path, monkeypatch):
    (tmp_path / "TESTPROJ.xml").write_text(FIXTURE, encoding="utf-8")
    monkeypatch.setattr(sf, "XML_BASE_DIR", str(tmp_path))


def test_nodes_e_jobs(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = sf.parse_seq_flow("TESTPROJ", "SeqMain")
    assert r["sucesso"]
    by_id = {n["id"]: n for n in r["nodes"]}
    assert by_id["V0S0"]["name"] == "AtivJobA" and by_id["V0S0"]["type"] == "Job" and by_id["V0S0"]["jobname"] == "JobA"
    assert by_id["V0S2"]["type"] == "Sequencer"


def test_edges_triggers(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = sf.parse_seq_flow("TESTPROJ", "SeqMain")
    edges = {(e["source"], e["target"]): e for e in r["edges"]}
    # AtivJobA --Ini_B (ok)--> AtivJobB
    assert ("V0S0", "V0S1") in edges
    assert edges[("V0S0", "V0S1")]["label"] == "Ini_B"
    assert edges[("V0S0", "V0S1")]["cond"] == "ok"
    assert edges[("V0S0", "V0S1")]["expr"] is None
    # AtivJobB --Fim_B (condicional, com expressão)--> WaitAll
    assert ("V0S1", "V0S2") in edges
    assert edges[("V0S1", "V0S2")]["cond"] == "condicional"
    assert "ReturnValue" in (edges[("V0S1", "V0S2")]["expr"] or "")


def test_job_inexistente(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert "erro" in sf.parse_seq_flow("TESTPROJ", "NaoExiste")


def test_xml_inexistente(tmp_path, monkeypatch):
    monkeypatch.setattr(sf, "XML_BASE_DIR", str(tmp_path))
    assert "erro" in sf.parse_seq_flow("SEMXML", "X")
