"""
api/services/ds_seq_flow.py — Extrai o DAG de dependências (fluxo) de uma Sequence
do DataStage a partir do export XML <DSExport> (mesmo arquivo usado pela malha).

As dependências reais entre atividades estão nos registros JSActivityOutput de
cada Job: SourceID (stage de origem) → Partner ("stageDestino|pin"), com
ConditionType/TriggerExpression (o gatilho OK/condicional/etc.). Os nós são as
atividades (JSJobActivity, JSSequencer, JSMailActivity, …).

É uma leitura LOCAL do arquivo (sem SSH). O endpoint cacheia o resultado no banco
(etl_ds_seq_flow) para não reparsear toda vez — atualiza sob demanda.
"""
from __future__ import annotations

import html
import os
import re
import xml.etree.ElementTree as ET

XML_BASE_DIR = os.environ.get("XML_BASE_DIR") or os.environ.get("DSX_BASE_DIR", "/opt/airflow/dsx")

# Registros que são LIGAÇÕES/condições (não são nós/atividades).
_LINK_TYPES = {"JSActivityInput", "JSActivityOutput", "JSCondition"}

# Rótulo amigável por tipo de atividade da sequence.
_TYPE_LABEL = {
    "JSJobActivity":         "Job",
    "JSSequencer":           "Sequencer",
    "JSRoutineActivity":     "Rotina",
    "JSUserVarsActivity":    "Variáveis",
    "JSMailActivity":        "E-mail",
    "JSExecCmdActivity":     "Comando",
    "JSExceptionHandler":    "Exceção",
    "JSTerminatorActivity":  "Terminator",
    "JSWaitForFileActivity": "Aguarda arquivo",
    "JSNestedCondition":     "Condição",
    "JSStartLoopActivity":   "Início loop",
    "JSEndLoopActivity":     "Fim loop",
    "JSEndActivity":         "Fim",
}


def _props(rec) -> dict:
    return {p.get("Name"): (p.text or "").strip() for p in rec.findall("Property")}


def _load_root(path: str):
    """Lê o XML, com fallback latin-1 (DataStage declara UTF-8 mas usa CP1252)."""
    try:
        return ET.parse(path).getroot()
    except ET.ParseError:
        with open(path, "rb") as fh:
            raw = fh.read()
        text = re.sub(r"^\s*<\?xml[^>]*\?>", "", raw.decode("latin-1"), count=1)
        return ET.fromstring(text)


def _cond_label(ctype: str | None, expr: str | None) -> str:
    e = (expr or "").strip()
    if e and e != "N/A":
        return "condicional"
    return {"0": "ok", "1": "falhou", "2": "avisos", "3": "custom",
            "4": "retorno", "5": "incondicional"}.get(str(ctype or ""), "ok")


def xml_path_for(project: str) -> str:
    return os.path.join(XML_BASE_DIR, f"{project}.xml")


def parse_seq_flow(project: str, job: str) -> dict:
    """
    Extrai {nodes, edges} da sequence `job` no export `<project>.xml`.

    nodes: [{id, name, type, jobname?}]
    edges: [{source, target, label, cond, expr?}]   (source/target = id do nó)
    """
    path = xml_path_for(project)
    if not os.path.isfile(path):
        return {"erro": f"Export '{project}.xml' não encontrado em {XML_BASE_DIR}."}

    try:
        root = _load_root(path)
    except Exception as e:  # noqa: BLE001
        return {"erro": f"Falha ao ler o XML: {e}"}

    if root.tag != "DSExport":
        return {"erro": f"Raiz inesperada '{root.tag}' (esperado DSExport)."}

    jobel = None
    for j in root.findall("Job"):
        if html.unescape(j.get("Identifier") or "") == job:
            jobel = j
            break
    if jobel is None:
        return {"erro": f"Job '{job}' não encontrado no export de '{project}'."}

    stages: dict[str, dict] = {}
    edges: list[dict] = []
    for r in jobel.findall("Record"):
        t = r.get("Type")
        p = _props(r)
        if t == "JSActivityOutput":
            partner = p.get("Partner", "")
            tgt = partner.split("|")[0] if partner else ""
            edges.append({
                "source": p.get("SourceID"),
                "target": tgt,
                "label": p.get("Name") or "",
                "cond": _cond_label(p.get("ConditionType"), p.get("TriggerExpression")),
                "expr": (p.get("TriggerExpression") or "").strip()
                        if (p.get("TriggerExpression") or "").strip() not in ("", "N/A") else None,
            })
        elif (t and t.startswith("JS") and t not in _LINK_TYPES) or ("OutputPins" in p or "InputPins" in p):
            stages[r.get("Identifier")] = {
                "name": p.get("Name") or (r.get("Identifier") or "?"),
                "type": _TYPE_LABEL.get(t, (t or "").replace("JS", "").replace("Activity", "") or "Stage"),
                "jobname": p.get("Jobname") or None,
            }

    # placeholders para ids referenciados por arestas mas não capturados como stage
    for e in edges:
        for k in (e["source"], e["target"]):
            if k and k not in stages:
                stages[k] = {"name": k, "type": "?", "jobname": None}

    nodes = [{"id": sid, "name": s["name"], "type": s["type"], "jobname": s.get("jobname")}
             for sid, s in stages.items()]
    edges = [e for e in edges if e["source"] and e["target"]]
    return {"sucesso": True, "project": project, "job": job,
            "nodes": nodes, "edges": edges, "source_file": f"{project}.xml"}
