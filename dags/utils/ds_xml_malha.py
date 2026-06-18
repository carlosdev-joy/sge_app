"""
ds_xml_malha.py — Malha de orquestração a partir do export XML <DSExport> do DataStage.

APARTADO de propósito: NÃO faz parte da geração de DAG (etl_dag_factory) nem do
dsx_engine (lineage de coluna). É um módulo de leitura puro, sem efeitos colaterais,
para alimentar o "cockpit de transição" (malha + varredura de status por job).

Entrega:
  • parse_file(path)        → estrutura de jobs/sequences do projeto
  • build_tree(parsed,root) → árvore de chamadas (resolvendo executor genérico)
  • monitorable_jobs(...)   → lista plana de jobs reais para dsjob -jobinfo

Resolução de executor genérico: quando uma JSJobActivity chama um executor
(ex.: SeqExecJob) passando o job real em ParmNomeJob, a malha mostra o job real
— não o wrapper. (Validado em exports BI_CVP/BI_VIDA 11.7.)
"""
from __future__ import annotations

import re
import html
import xml.etree.ElementTree as ET

# Parâmetro que carrega o nome do job real nos executores genéricos
EXECUTOR_JOB_PARAM = "ParmNomeJob"

# Tipos de atividade de sequence relevantes para a malha
_ACT_JOB     = "JSJobActivity"
_ACT_ROUTINE = "JSRoutineActivity"
_ACT_CMD     = ("JSExecCommandActivity", "JSExecCmdActivity")
_SEQ_MARKERS = (_ACT_JOB, "JSSequencer", "JSStartLoopActivity")


def _props(rec) -> dict:
    return {p.get("Name"): (p.text or "") for p in rec.findall("Property")}


def _subrec_value(rec, name: str) -> str | None:
    """Procura, dentro do record, um SubRecord cujo Name==name e devolve Value/Default."""
    for sr in rec.iter("SubRecord"):
        p = _props(sr)
        if p.get("Name") == name:
            return (p.get("Value") or p.get("Default") or "").strip() or None
    return None


def _record_text(rec) -> str:
    return " ".join((e.text or "") for e in rec.iter())


def _looks_like_job(v: str | None) -> bool:
    """Nome plausível de job: começa com letra, ≥3 chars, não é #ref nem número."""
    return bool(v) and not v.startswith("#") and bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{2,}", v))


def _real_target(rec, jobname: str) -> str:
    """Job real de uma JSJobActivity: o valor de ParmNomeJob (se válido) ou o Jobname."""
    val = _subrec_value(rec, EXECUTOR_JOB_PARAM)
    if not _looks_like_job(val):
        # fallback: valor entre aspas após ParmNomeJob (estrito, evita casar números soltos)
        m = re.search(r"ParmNomeJob['\"]?\s*[=:]?\s*['\"]([A-Za-z][A-Za-z0-9_]{2,})['\"]",
                      _record_text(rec))
        val = m.group(1) if m else None
    return val if _looks_like_job(val) else jobname


def parse_file(path: str) -> dict:
    """Lê um <DSExport> e devolve a estrutura de jobs/sequences do projeto."""
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        # Fallback p/ exports com bytes não-UTF8 (DataStage declara UTF-8 mas usa
        # CP1252). latin-1 mapeia todos os 256 bytes (nunca falha); identificadores
        # de job/tabela são ASCII, então a estrutura é preservada.
        with open(path, "rb") as fh:
            raw = fh.read()
        text = re.sub(r"^\s*<\?xml[^>]*\?>", "", raw.decode("latin-1"), count=1)
        root = ET.fromstring(text)
    if root.tag != "DSExport":
        return {"erro": f"Raiz inesperada '{root.tag}' (esperado DSExport)."}

    hdr = root.find("Header")
    project = hdr.get("ToolInstanceID") if hdr is not None else None
    server  = hdr.get("ServerName") if hdr is not None else None
    version = hdr.get("ServerVersion") if hdr is not None else None

    jobs: dict[str, dict] = {}
    for j in root.findall("Job"):
        name = html.unescape(j.get("Identifier") or "")
        recs = j.findall("Record")
        calls: list[dict] = []
        for r in recs:
            t = r.get("Type")
            if t == _ACT_JOB:
                p = _props(r)
                jobname = p.get("Jobname", "?")
                calls.append({
                    "activity":    p.get("Name", "?"),
                    "jobname":     jobname,
                    "real_target": _real_target(r, jobname),
                    "kind":        "JOB",
                })
            elif t == _ACT_ROUTINE:
                calls.append({"activity": _props(r).get("Name", "?"),
                              "real_target": _props(r).get("Name", "?"), "kind": "ROTINA"})
            elif t in _ACT_CMD:
                calls.append({"activity": _props(r).get("Name", "?"),
                              "real_target": "(shell)", "kind": "CMD"})
        is_seq = any(r.get("Type") in _SEQ_MARKERS for r in recs)
        stage_types = {_props(r).get("StageType") for r in recs if _props(r).get("StageType")}
        params = []
        for r in recs:
            for col in r.findall("Collection"):
                if col.get("Name") == "Parameters":
                    for sr in col.findall("SubRecord"):
                        pn = _props(sr).get("Name")
                        if pn:
                            params.append(pn)
        jobs[name] = {
            "is_sequence": is_seq,
            "is_executor": EXECUTOR_JOB_PARAM in params,   # executor genérico (roda job via parâmetro)
            "stage_types": sorted(t for t in stage_types if t),
            "params":      params,
            "calls":       calls,
        }

    return {"sucesso": True, "project": project, "server": server,
            "version": version, "jobs": jobs}


def _is_seq(parsed: dict, name: str) -> bool:
    j = parsed["jobs"].get(name)
    return bool(j and j["is_sequence"])


def root_sequences(parsed: dict) -> list[str]:
    """Sequences-raiz: que ninguém chama e NÃO são executores genéricos."""
    jobs = parsed["jobs"]
    called = {c["real_target"] for j in jobs.values() for c in j["calls"] if c["kind"] == "JOB"}
    return sorted(n for n, j in jobs.items()
                  if j["is_sequence"] and not j["is_executor"] and n not in called)


def _best_root(parsed: dict) -> str | None:
    """Raiz padrão: a sequence-raiz com mais chamadas de job (o orquestrador 'de cima')."""
    roots = root_sequences(parsed)
    if not roots:
        roots = [n for n, j in parsed["jobs"].items()
                 if j["is_sequence"] and not j["is_executor"]] or list(parsed["jobs"])
    if not roots:
        return None
    return max(roots, key=lambda n: sum(
        1 for c in parsed["jobs"].get(n, {}).get("calls", []) if c["kind"] == "JOB"))


def build_tree(parsed: dict, root: str | None = None, _seen=None) -> dict:
    """Árvore de chamadas a partir de `root` (ou da raiz detectada).

    Resolve executor genérico (ParmNomeJob), marca aninhamento e conta invocações;
    rotinas/comandos entram resumidos. Protegido contra ciclo.
    """
    if root is None:
        root = _best_root(parsed)
    if root is None:
        return {}

    _seen = _seen or set()
    node = {
        "name":     root,
        "kind":     "SEQ" if _is_seq(parsed, root) else ("JOB" if root in parsed["jobs"] else "EXTERNO"),
        "children": [],
        "routines": 0,
        "commands": 0,
    }
    here = parsed["jobs"].get(root)
    if not here or root in _seen:
        node["ref"] = root in _seen  # já expandido em outro ramo (evita loop)
        return node
    _seen = _seen | {root}

    # contagem de invocações de cada alvo dentro deste nó
    from collections import Counter
    inv = Counter(c["real_target"] for c in here["calls"] if c["kind"] == "JOB")
    vistos: set[str] = set()
    for c in here["calls"]:
        if c["kind"] == "ROTINA":
            node["routines"] += 1
        elif c["kind"] == "CMD":
            node["commands"] += 1
        elif c["kind"] == "JOB":
            tgt = c["real_target"]
            if tgt in vistos:
                continue
            vistos.add(tgt)
            child = build_tree(parsed, tgt, _seen)
            child["invocations"] = inv[tgt]
            node["children"].append(child)
    return node


def monitorable_jobs(parsed: dict, root: str | None = None) -> list[str]:
    """Lista plana e única dos jobs reais (não-sequence, não-rotina) sob a malha.

    São esses que o cockpit varre com `dsjob -jobinfo`. Inclui também os nomes
    resolvidos de executor (o job de negócio, não o wrapper).
    """
    out: list[str] = []
    seen: set[str] = set()

    def walk(name: str, guard: set[str]):
        if name in guard:
            return
        guard = guard | {name}
        j = parsed["jobs"].get(name)
        if j is None:
            # alvo não presente neste arquivo (job de outro projeto/export) — ainda é monitorável
            if name not in seen and name != "(shell)":
                seen.add(name); out.append(name)
            return
        if not j["is_sequence"]:
            if name not in seen:
                seen.add(name); out.append(name)
            return
        for c in j["calls"]:
            if c["kind"] == "JOB":
                walk(c["real_target"], guard)

    if root is None:
        root = _best_root(parsed)
    if root:
        walk(root, set())
    return out


# ── Persistência: malha ⇆ linhas de banco ───────────────────────────
def scan_targets(parsed: dict) -> list[str]:
    """Todos os nós da malha que são jobs/sequences do DataStage (para varredura
    de status): raízes + todos os real_target das chamadas de job. Inclui as
    próprias sequences (que também têm status). Executores genéricos ficam de
    fora (já resolvidos para o job real)."""
    names: set[str] = set(root_sequences(parsed))
    for j in parsed.get("jobs", {}).values():
        for c in j["calls"]:
            if c["kind"] == "JOB" and c.get("real_target"):
                names.add(c["real_target"])
    return sorted(names)


def to_rows(parsed: dict) -> dict:
    """Achata a malha em linhas para gravar no banco (sem dependência de DB).

    Retorna {project, server, version, nodes:[...], edges:[...], roots:[...]}.
    nodes = jobs/sequences; edges = chamadas (parent → real_target) em ordem.
    """
    nodes = []
    for name, j in parsed.get("jobs", {}).items():
        nodes.append({
            "name":        name,
            "kind":        "executor" if j["is_executor"] else
                           ("sequence" if j["is_sequence"] else "job"),
            "is_sequence": bool(j["is_sequence"]),
            "is_executor": bool(j["is_executor"]),
            "stage_types": list(j.get("stage_types") or []),
        })
    edges = []
    for parent, j in parsed.get("jobs", {}).items():
        for i, c in enumerate(j["calls"], start=1):
            edges.append({
                "parent":      parent,
                "seq_order":   i,
                "activity":    c.get("activity"),
                "jobname":     c.get("jobname"),
                "real_target": c.get("real_target"),
                "kind":        c["kind"],
            })
    return {
        "project": parsed.get("project"), "server": parsed.get("server"),
        "version": parsed.get("version"), "nodes": nodes, "edges": edges,
        "roots": root_sequences(parsed),
    }


def from_rows(nodes: list[dict], edges: list[dict], project: str | None = None) -> dict:
    """Reconstrói a estrutura `parsed` a partir das linhas do banco.

    Permite reusar build_tree/monitorable_jobs lendo do banco (sem reparsear XML).
    """
    jobs: dict[str, dict] = {}
    for n in nodes:
        jobs[n["name"]] = {
            "is_sequence": bool(n.get("is_sequence")),
            "is_executor": bool(n.get("is_executor")),
            "stage_types": list(n.get("stage_types") or []),
            "params":      [],
            "calls":       [],
        }
    for e in sorted(edges, key=lambda x: (x.get("parent") or "", x.get("seq_order") or 0)):
        parent = e.get("parent")
        if parent not in jobs:
            continue
        jobs[parent]["calls"].append({
            "activity":    e.get("activity"),
            "jobname":     e.get("jobname"),
            "real_target": e.get("real_target"),
            "kind":        e.get("kind"),
        })
    return {"sucesso": True, "project": project, "jobs": jobs}

