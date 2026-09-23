"""api/services/rerun_params.py — parâmetros DataStage na REEXECUÇÃO (F5 da spec
docs/spec-parametros-job-datastage.md).

Dois lados do mesmo gesto:

  parametros_da_previa   o que o modal mostra ANTES de reexecutar: por etapa
                         DataStage do conjunto limpo, os itens efetivos
                         (defaults do pipeline < etapa) com o valor que iria ao
                         DataStage na referência da corrida — calculado pelo
                         MESMO módulo da tela (services/job_params). Encrypted
                         sai `***` e não é editável.
  validar_overrides      o que o operador pediu para trocar: job DataStage do
                         pipeline, parâmetro existente por nome EXATO, nunca
                         Encrypted, valor validado pelo tipo da linha.
  gravar_overrides /     a tabela da migration 109, ANTES do clear (e o desfazer
  apagar_overrides       se o clear falhar).

Tudo com cursor pyodbc (`?`). Degrada sem as migrations: sem a 107 não há
parâmetro de etapa; sem a 108 não há default; sem a 109 a sobreposição é
recusada com mensagem clara (nunca gravada em silêncio em lugar nenhum).
"""
from __future__ import annotations

from datetime import date

from services import job_params as jp

COLS = ("param_name", "param_type", "param_value", "param_source",
        "param_offset_meses", "param_ancora", "param_offset_dias", "param_formato")
_SQL_ETAPA = (
    "SELECT job_name, param_name, param_type, param_value, param_source, param_offset_meses, "
    "param_ancora, param_offset_dias, param_formato FROM dbo.etl_pipeline_job_param "
    "WHERE pipeline_name=? ORDER BY job_name, param_order")
_SQL_PIPELINE = (
    "SELECT param_name, param_type, param_value, param_source, param_offset_meses, "
    "param_ancora, param_offset_dias, param_formato FROM dbo.etl_pipeline_param "
    "WHERE pipeline_name=? ORDER BY param_order")
ERRO_SEM_109 = ("sobreposição de parâmetros na reexecução exige a migration 109 "
                "(dbo.etl_job_param_override) — aplique-a e tente de novo")


def _tem_tabela(cur, nome: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME=?", (nome,))
    return bool(cur.fetchone()[0])


def _tem_coluna(cur, tabela: str, coluna: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME=? AND COLUMN_NAME=?", (tabela, coluna))
    return bool(cur.fetchone()[0])


def _jobs_datastage(cur, pipeline: str) -> dict[str, str]:
    """casefold(job_name) → job_name oficial, só das etapas datastage."""
    cur.execute(
        "SELECT job_name, ISNULL(job_type, 'datastage') FROM dbo.etl_pipeline_job "
        "WHERE pipeline_name=?", (pipeline,))
    return {r[0].casefold(): r[0] for r in cur.fetchall()
            if (r[1] or "datastage").lower().strip() == "datastage"}


def _params_por_job(cur, pipeline: str) -> dict[str, list[dict]]:
    """job_name → linhas de etl_pipeline_job_param (só com a 107 — sem ela não
    existe parâmetro de etapa datastage)."""
    if not _tem_coluna(cur, "etl_pipeline_job_param", "param_source"):
        return {}
    cur.execute(_SQL_ETAPA, (pipeline,))
    saida: dict[str, list[dict]] = {}
    for r in cur.fetchall():
        saida.setdefault(r[0], []).append(dict(zip(COLS, r[1:])))
    return saida


def _defaults_pipeline(cur, pipeline: str) -> list[dict]:
    if not _tem_tabela(cur, "etl_pipeline_param"):
        return []
    cur.execute(_SQL_PIPELINE, (pipeline,))
    return [dict(zip(COLS, r)) for r in cur.fetchall()]


def itens_efetivos(defaults: list[dict], etapa: list[dict]) -> list[dict]:
    """Passos 1–2 do §4 sem o `-lparams` (a API não fala com o DataStage): o
    default do pipeline entra marcado `condicional` — só vale se o job
    declarar o nome — e a etapa sobrepõe por nome exato."""
    por_nome: dict[str, dict] = {}
    for p in defaults:
        por_nome[p["param_name"]] = dict(p, fonte="pipeline", condicional=True)
    for p in etapa:
        por_nome[p["param_name"]] = dict(p, fonte="etapa", condicional=False)
    return list(por_nome.values())


def parametros_da_previa(cur, pipeline: str, etapas: list[str], data_ref) -> list[dict]:
    """[{job_name, itens: [{param_name, param_type, param_source, fonte,
    condicional, valor_efetivo, descricao, editavel}]}] — só etapas DataStage
    do conjunto limpo que têm algum item."""
    ds = _jobs_datastage(cur, pipeline)
    alvo = [ds[e.casefold()] for e in etapas if e.casefold() in ds]
    if not alvo:
        return []
    por_job = _params_por_job(cur, pipeline)
    defaults = _defaults_pipeline(cur, pipeline)
    referencia = jp.parse_data(data_ref) if data_ref is not None else None
    saida = []
    for job in alvo:
        itens = itens_efetivos(defaults, por_job.get(job, []))
        if not itens:
            continue
        if referencia is not None:
            valores, erros = jp.resolver_preview(referencia, itens)
            por_nome = {v["param_name"]: v for v in valores}
        else:
            por_nome, erros = {}, []
        lista = []
        for it in itens:
            v = por_nome.get(it["param_name"])
            encrypted = it["param_type"] == "Encrypted"
            if v is None and it["param_source"] in jp.DS_SOURCES_DATA:
                valor, desc = None, ("referência da corrida desconhecida — calculado no disparo"
                                     if referencia is None else "data fora do calendário")
            elif v is None:
                valor, desc = (jp.ENCRYPTED_MASCARA if encrypted else (it.get("param_value") or "")), "fixo"
            else:
                valor, desc = v["valor"], v["descricao"]
            lista.append({
                "param_name": it["param_name"], "param_type": it["param_type"],
                "param_source": it["param_source"], "fonte": it["fonte"],
                "condicional": bool(it.get("condicional")),
                "valor_efetivo": valor, "descricao": desc,
                "editavel": not encrypted,
            })
        saida.append({"job_name": job, "itens": lista})
    return saida


def validar_overrides(cur, pipeline: str, raw) -> tuple[list[dict], list[str]]:
    """[{job_name, param_name, param_value}] → (linhas prontas, erros).

    Regras: lista; job DataStage do pipeline; parâmetro existente por nome
    EXATO (etapa ou default do pipeline); nunca Encrypted; valor validado como
    fixo pelo tipo da linha (services/job_params); sem duplicata (job, nome).
    A sobreposição é sempre um valor FIXO para aquela corrida."""
    if not isinstance(raw, list):
        return [], ["parametros deve ser uma lista"]
    if not raw:
        return [], []
    if not _tem_tabela(cur, "etl_job_param_override"):
        return [], [ERRO_SEM_109]
    ds = _jobs_datastage(cur, pipeline)
    por_job = _params_por_job(cur, pipeline)
    defaults = _defaults_pipeline(cur, pipeline)
    linhas: list[dict] = []
    erros: list[str] = []
    vistos: set[tuple[str, str]] = set()
    for i, o in enumerate(raw):
        if not isinstance(o, dict):
            erros.append(f"item #{i + 1}: inválido"); continue
        job_raw = str(o.get("job_name") or "").strip()
        nome = str(o.get("param_name") or "").strip()
        job = ds.get(job_raw.casefold())
        if not job:
            erros.append(f"item #{i + 1}: '{job_raw}' não é uma etapa DataStage deste pipeline"); continue
        efetivos = {it["param_name"]: it for it in itens_efetivos(defaults, por_job.get(job, []))}
        alvo = efetivos.get(nome)
        if alvo is None:
            erros.append(f"{job}: o parâmetro '{nome}' não existe na etapa nem nos defaults do pipeline "
                         "(o nome é sensível a maiúsculas)"); continue
        if alvo["param_type"] == "Encrypted":
            erros.append(f"{job}: '{nome}' é Encrypted — não pode ser sobreposto na reexecução"); continue
        if (job, nome) in vistos:
            erros.append(f"{job}: '{nome}' repetido"); continue
        # Linha com origem de DATA: o valor efetivo que a prévia mostra já está
        # no formato do job (ex.: 20260901 com %Y%m%d) e é isso que o operador
        # digita — validar como Date ISO recusaria o valor certo. O formato é do
        # job; aqui vale texto (sem quebra de linha). Origem fixa: régua do tipo.
        tipo_validacao = ("String" if alvo["param_source"] in jp.DS_SOURCES_DATA
                          else alvo["param_type"])
        norm, errs = jp.normalizar_item({
            "param_name": nome, "param_type": tipo_validacao, "param_source": "fixo",
            "param_value": o.get("param_value"),
        })
        if errs:
            erros.extend(f"{job}: {e}" for e in errs); continue
        vistos.add((job, nome))
        linhas.append({"job_name": job, "param_name": nome, "param_value": norm["param_value"]})
    return linhas, erros


def gravar_overrides(cur, pipeline: str, dag_run_id: str, linhas: list[dict], usuario: str | None) -> None:
    """Replace das sobreposições desta corrida (um rerun anterior do mesmo
    run pode ter deixado linhas — o gesto novo é o que vale)."""
    apagar_overrides(cur, pipeline, dag_run_id)
    for p in linhas:
        cur.execute(
            "INSERT INTO dbo.etl_job_param_override "
            "(pipeline_name, job_name, dag_run_id, param_name, param_value, criado_por) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (pipeline, p["job_name"], dag_run_id, p["param_name"], p["param_value"], usuario))


def sobreposicoes_anteriores(cur, pipeline: str, dag_run_id: str) -> list[str]:
    """`job.param` das sobreposições que um rerun ANTERIOR desta corrida deixou
    — a prévia avisa que elas serão descartadas pelo gesto novo (o operador
    digita de novo se quiser mantê-las). Nunca os valores."""
    if not dag_run_id or not _tem_tabela(cur, "etl_job_param_override"):
        return []
    cur.execute(
        "SELECT job_name, param_name FROM dbo.etl_job_param_override "
        "WHERE pipeline_name=? AND dag_run_id=? ORDER BY job_name, param_name",
        (pipeline, dag_run_id))
    return [f"{r[0]}.{r[1]}" for r in cur.fetchall()]


def apagar_overrides(cur, pipeline: str, dag_run_id: str) -> None:
    cur.execute(
        "DELETE FROM dbo.etl_job_param_override WHERE pipeline_name=? AND dag_run_id=?",
        (pipeline, dag_run_id))
