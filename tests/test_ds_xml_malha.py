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


def test_to_rows_estrutura(tmp_path):
    p = _parsed(tmp_path)
    rows = M.to_rows(p)
    assert rows["project"] == "TESTPROJ"
    names = {n["name"] for n in rows["nodes"]}
    assert names == set(p["jobs"])
    # node executor marcado corretamente
    kinds = {n["name"]: n["kind"] for n in rows["nodes"]}
    assert kinds["ExecWrapper"] == "executor" and kinds["MasterSeq"] == "sequence" and kinds["JobA"] == "job"
    # aresta com real_target resolvido (RealBizJob) existe
    assert any(e["parent"] == "MasterSeq" and e["real_target"] == "RealBizJob" for e in rows["edges"])


def test_roundtrip_rows_preserva_malha(tmp_path):
    """to_rows → from_rows deve reproduzir a mesma árvore/lista monitorável (sem reparsear)."""
    p = _parsed(tmp_path)
    rows = M.to_rows(p)
    p2 = M.from_rows(rows["nodes"], rows["edges"], project=rows["project"])

    def flat(node):
        return (node["name"], node["kind"], tuple(flat(c) for c in node.get("children", [])))

    assert flat(M.build_tree(p, "MasterSeq")) == flat(M.build_tree(p2, "MasterSeq"))
    assert set(M.monitorable_jobs(p, "MasterSeq")) == set(M.monitorable_jobs(p2, "MasterSeq"))


def test_scan_targets_inclui_sequences(tmp_path):
    p = _parsed(tmp_path)
    targets = set(M.scan_targets(p))
    # varredura cobre jobs E sequences (sequences têm status próprio, ex.: warning)
    assert {"MasterSeq", "SubSeq", "JobA", "JobB", "RealBizJob"} <= targets
    assert "ExecWrapper" not in targets   # executor resolvido, não entra
    # difere do monitorável (que é só folha): MasterSeq/SubSeq não são folha
    assert "MasterSeq" in targets and "MasterSeq" not in set(M.monitorable_jobs(p))


def test_to_rows_dedup_nomes_case_insensitive(tmp_path):
    """Nós que diferem só por caixa contam como 1 (igual ao índice único do SQL)."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<DSExport>
   <Header ToolInstanceID="P" ServerVersion="11.7"/>
   <Job Identifier="jobOrigemFTP"><Record Identifier="ROOT" Type="JobDefn"><Property Name="Name">jobOrigemFTP</Property></Record></Job>
   <Job Identifier="JobOrigemFTP"><Record Identifier="ROOT" Type="JobDefn"><Property Name="Name">JobOrigemFTP</Property></Record></Job>
</DSExport>"""
    f = tmp_path / "dup.xml"
    f.write_text(xml, encoding="utf-8")
    rows = M.to_rows(M.parse_file(str(f)))
    norms = [n["name"].strip().lower() for n in rows["nodes"]]
    assert norms.count("joborigemftp") == 1   # deduplicado


def test_arquivo_inexistente_ou_invalido(tmp_path):
    bad = tmp_path / "x.xml"
    bad.write_text("<NotDSExport/>", encoding="utf-8")
    assert M.parse_file(str(bad)).get("erro")
