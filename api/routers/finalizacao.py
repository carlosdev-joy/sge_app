"""api/routers/finalizacao.py — GET /finalizacao/executando, POST /finalizacao/finalizar.

Finalização manual de execuções penduradas em RUNNING. Diferente do
/execucoes/reconciliar (espelho puro, só fecha o que o DataStage já reporta
terminal), aqui o operador FORÇA o encerramento nos logs do Orquestra quando o
processo já terminou no DataStage mas o registro ficou órfão (worker morreu
antes do log_end e o etl_ds_job_log também ficou RUNNING — nada mais fecha).

Uma finalização toca três lugares, na mesma transação:
  1. dbo.etl_job_execution  — status final + end_time (some do Executando/Gantt/KPIs/SLA);
  2. dbo.etl_ds_job_log     — status/status_code terminal (monitor central para de pollar);
  3. dbo.etl_pipeline_performance_snapshot — DELETE (some da tela Performance na hora).
Auditoria em dbo.etl_pipeline_audit (quem, quando, motivo) + notificação best-effort.

NÃO toca no DataStage nem no Airflow — é só o registro no Orquestra.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException

from db import get_db_conn
from deps import PERM_EXECUTAR, get_current_user, require_perm
from services import execucao_identidade as ident_svc
from services import malha_corrida as mc
from services.notify import add_notificacao

log = logging.getLogger("orquestra-api")

router = APIRouter()

# status final permitido → (status, status_code) equivalentes no etl_ds_job_log
_STATUS_DS = {
    "SUCCESS": ("SUCCESS", 1),
    "WARNING": ("WARNING", 2),
    "FAILED":  ("ABORTED", 3),
}

# ...e o equivalente na 067, que é a linha que o CICLO da malha lê (F8).
# WARNING vira SUCESSO porque é assim que o resto do produto o trata: o
# DataStage devolve "terminou com avisos", e `liberado()`/`pipelines_todos_sucesso`
# já contam WARNING como conclusão. Inventar um terceiro estado aqui faria a
# corrida ficar esperando para sempre por um pipeline que o operador declarou
# terminado.
_STATUS_067 = {"SUCCESS": "SUCESSO", "WARNING": "SUCESSO", "FAILED": "FALHA"}


def _fmt_dt(v):
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)


def _iso(v) -> str:
    return v.strftime("%Y-%m-%d") if hasattr(v, "strftime") else str(v)


def _fechar_linha_do_ciclo(cur, pipeline: str, alvos: list, status_final: str,
                           quem: str, motivo) -> dict:
    """F8 (Decisão 22) — a finalização manual passa a alcançar a linha da 067, e
    reavalia o ciclo da malha **no mesmo gesto**.

    Por que isto faltava: a linha órfã mais comum do sistema é `EXECUTANDO` na
    067 com o DagRun já morto, e é ela que a Decisão 22 tira de `vivos` para a
    corrida poder fechar nomeando o problema. A Finalização Manual é a
    ferramenta do operador para esse caso — mas ela mexia em três tabelas e
    **nenhuma delas era a 067**. O gesto "encerrei essa órfã" era literalmente
    invisível para o ciclo: o membro continuava vivo no denominador, e a corrida
    esperava por ele até o teto (24h por padrão).

    O que este passo faz e o que NÃO faz:

      • fecha a linha da 067 **só quando ela está `EXECUTANDO`** — nunca
        reescreve terminal, nunca ressuscita, e o `rowcount` é o árbitro;
      • carimba o `motivo` com a autoria, porque um SUCESSO declarado à mão tem
        consequência a jusante (o dependente parte) e precisa ser rastreável;
      • **não fecha a corrida.** Fechar é da guardiã, sempre (Decisão 19): os
        sete desfechos dependem de quiescência, carência e teto, e uma segunda
        implementação deles aqui seria a próxima divergência. O que o gesto
        entrega na hora é tirar o membro de `vivos` — que é o que travava — e
        DIZER como o ciclo ficou.

    A ponte ts_nodash ↔ run_id é a `resolve_por_ts_nodash` que já existe: a 067
    guarda o `run_id` do Airflow e o log de jobs guarda o `ts_nodash`, e casar
    os dois "por parecido" foi um defeito que este repo já pagou.

    ⚠️ **Medido no dev (2026-08-06):** essa ponte só fecha sozinha para run_id
    da forma do Airflow (`scheduled__<ISO>`). Os run_ids que o próprio Orquestra
    gera — `manual_orq_…` e o `guardia__…` do push, que é como a MAIORIA dos
    membros de malha parte — devolvem `None` de propósito (o timestamp deles é
    relógio local, e traduzi-lo daria um ts_nodash deslocado do fuso). Sem um
    segundo caminho, a Decisão 22 valeria só para o membro agendado, que é
    justamente o que menos precisa dela.

    O segundo caminho é o `candidatos` que a própria resolução já devolve — as
    linhas do pipeline na janela de ±1 dia do ts. Dele sai a linha a fechar
    **só quando há exatamente UMA em execução**. Duas é ambiguidade, e
    ambiguidade aqui se DECLARA, nunca se escolhe: fechar a errada carimbaria
    SUCESSO num pipeline que ainda está rodando, e o dependente partiria com o
    dado da véspera.

    Nunca levanta: a finalização é a ferramenta de emergência do plantão, e ela
    não pode falhar porque a malha não pôde ser consultada.
    """
    saida = {"linhas_ciclo_fechadas": 0, "corridas": [], "avisos": []}
    novo_status = _STATUS_067.get(status_final)
    if novo_status is None:
        return saida
    if not ident_svc.tem_tabela_067(cur):
        return saida
    texto = f"finalizacao manual por {quem}" + (f": {motivo}" if motivo else "")
    datas: set = set()
    for ts in alvos:
        try:
            ident = ident_svc.resolve_por_ts_nodash(cur, pipeline, str(ts))
            run_id = ident.get("run_id")
            if not run_id:
                vivas = [c for c in (ident.get("candidatos") or [])
                         if str(c.get("status") or "") == "EXECUTANDO"
                         and c.get("substituida_em") is None
                         and c.get("run_id")]
                if len(vivas) > 1:
                    saida["avisos"].append(
                        f"há {len(vivas)} execuções em andamento deste pipeline "
                        "na janela desta data e não dá para saber qual é esta — "
                        "nenhuma foi encerrada para o ciclo da malha; encerre a "
                        "ciclo pela tela de Malha se ela estiver travada")
                    continue
                if not vivas:
                    # A 067 pode simplesmente não ter linha em execução (pipeline
                    # pré-retomada, disparo fora do Orquestra, ou a linha já
                    # fechada). Não é erro: é o caso sem ciclo a reavaliar.
                    continue
                run_id = vivas[0]["run_id"]
            # A chave é (pipeline, execution_id): o run_id é único no Airflow, e
            # com ele a data não precisa entrar no WHERE — o que importa é não
            # depender dela quando ela veio do caminho dos candidatos. O
            # `status = 'EXECUTANDO'` é a guarda que impede reescrever terminal.
            cur.execute(
                "UPDATE dbo.etl_pipeline_execucao "
                "SET status = ?, fim = GETDATE(), "
                "    motivo = LEFT(ISNULL(motivo + ' | ', '') + ?, 500), "
                "    atualizado_em = GETDATE() "
                "OUTPUT inserted.data_referencia "
                "WHERE pipeline_name = ? AND execution_id = ? "
                "AND status = 'EXECUTANDO'",
                (novo_status, texto[:400], pipeline, run_id))
            fechadas = [r[0] for r in cur.fetchall()]
            saida["linhas_ciclo_fechadas"] += len(fechadas)
            datas.update(fechadas)
        except Exception as e:  # noqa: BLE001
            log.warning("[FINALIZACAO] linha do ciclo de '%s' (ts=%s) não "
                        "fechada: %s", pipeline, ts, e)
            saida["avisos"].append(
                "a linha de execução usada pelo ciclo da malha não pôde ser "
                f"encerrada ({e}) — a malha pode continuar esperando por este "
                "pipeline")
    if not datas:
        return saida
    # A reavaliação: com o membro fora de `vivos`, o que sobrou no ciclo?
    try:
        if not mc.tabela_085_presente(cur):
            return saida
        for c in (mc.corrida_aberta_do_pipeline(cur, pipeline).get("corridas")
                  or []):
            if c["data_referencia"] not in datas:
                continue
            est = mc.estado(cur, c)
            saida["corridas"].append({
                "malha": c["malha_name"],
                "data_referencia": _iso(c["data_referencia"]),
                "em_execucao": len(est["vivos"]),
                "pendentes": [p["pipeline"] for p in est["pendentes"]],
                "concluidos": len(est["ok"]),
            })
    except Exception as e:  # noqa: BLE001 — leitura degrada larga
        log.warning("[FINALIZACAO] ciclo de '%s' não reavaliado: %s",
                    pipeline, e)
    return saida


@router.get("/finalizacao/executando", tags=["finalizacao"])
def list_executando(q: str = "", _auth: dict = Depends(get_current_user)):
    """Execuções em RUNNING agregadas por (execution_id, pipeline), com o rastro que
    a finalização vai limpar: jobs RUNNING, estruturas abertas no etl_ds_job_log e
    snapshots de performance. Filtro opcional `q` por nome de pipeline (LIKE)."""
    q = (q or "").strip()
    data: list[dict] = []
    try:
        conn = get_db_conn(); cur = conn.cursor()
        params: list = []
        where = "WHERE status = 'RUNNING' AND end_time IS NULL"
        if q:
            where += " AND pipeline LIKE ?"
            params.append(f"%{q}%")
        cur.execute(f"""
            SELECT execution_id, pipeline, MAX(project) AS project,
                   COUNT(*) AS jobs_running, MIN(start_time) AS inicio,
                   DATEDIFF(SECOND, MIN(start_time), GETDATE()) AS elapsed_seconds
            FROM dbo.etl_job_execution
            {where}
            GROUP BY execution_id, pipeline
            ORDER BY MIN(start_time) ASC
        """, params)
        data = [
            {
                "execution_id": r[0], "pipeline": r[1], "project": r[2],
                "jobs_running": int(r[3] or 0), "inicio": _fmt_dt(r[4]),
                "elapsed_seconds": int(r[5] or 0),
                "estruturas_abertas": 0, "snapshots": 0,
            }
            for r in cur.fetchall()
        ]

        # Estruturas ainda abertas no log do DataStage (inclui órfãs sem par no
        # etl_job_execution — também precisam de finalização)
        try:
            params_ds: list = []
            where_ds = "WHERE status IN ('RUNNING', 'QUEUED')"
            if q:
                where_ds += " AND pipeline_name LIKE ?"
                params_ds.append(f"%{q}%")
            cur.execute(f"""
                SELECT execution_id, pipeline_name, MAX(project), COUNT(*)
                FROM dbo.etl_ds_job_log
                {where_ds}
                GROUP BY execution_id, pipeline_name
            """, params_ds)
            idx = {(d["execution_id"], d["pipeline"]): d for d in data}
            for r in cur.fetchall():
                d = idx.get((r[0], r[1]))
                if d is None:
                    d = {
                        "execution_id": r[0], "pipeline": r[1], "project": r[2],
                        "jobs_running": 0, "inicio": None, "elapsed_seconds": 0,
                        "estruturas_abertas": 0, "snapshots": 0,
                    }
                    data.append(d); idx[(r[0], r[1])] = d
                d["estruturas_abertas"] = int(r[3] or 0)
        except Exception as e:
            log.warning("finalizacao: etl_ds_job_log indisponível: %s", e)

        # Snapshots de performance pendurados na tela Performance
        try:
            cur.execute("""
                SELECT execution_id, pipeline, COUNT(*)
                FROM dbo.etl_pipeline_performance_snapshot
                GROUP BY execution_id, pipeline
            """)
            idx = {(d["execution_id"], d["pipeline"]): d for d in data}
            for r in cur.fetchall():
                d = idx.get((r[0], r[1]))
                if d is not None:
                    d["snapshots"] = int(r[2] or 0)
        except Exception as e:
            log.warning("finalizacao: snapshots indisponíveis: %s", e)

        cur.close(); conn.close()
    except Exception as e:
        log.warning("finalizacao: listagem degradou para vazio: %s", e)
        return {"data": []}
    return {"data": data}


@router.post("/finalizacao/finalizar", tags=["finalizacao"])
def finalizar_execucao(body: dict = Body(default={}),
                       user: dict = Depends(require_perm(PERM_EXECUTAR))):
    """Força o encerramento de execuções RUNNING de um pipeline nos logs do Orquestra.

    Body: pipeline (obrigatório), status_final ('SUCCESS'|'WARNING'|'FAILED',
          obrigatório), execution_id (opcional — sem ele fecha TODAS as execuções
          RUNNING do pipeline), motivo (opcional, vai para a auditoria).
    """
    pipeline     = (body.get("pipeline") or "").strip()
    execution_id = (body.get("execution_id") or "").strip()
    status_final = (body.get("status_final") or "").strip().upper()
    motivo       = (body.get("motivo") or "").strip() or None

    if not pipeline:
        raise HTTPException(status_code=422, detail="pipeline é obrigatório")
    if status_final not in _STATUS_DS:
        raise HTTPException(status_code=422,
                            detail="status_final deve ser SUCCESS, WARNING ou FAILED")
    ds_status, ds_code = _STATUS_DS[status_final]

    try:
        conn = get_db_conn(); cur = conn.cursor()

        # Alvos: execuções RUNNING no log principal + estruturas abertas no log DS
        # (união — cobre a órfã que só existe em um dos dois)
        extra_exec = " AND execution_id = ?" if execution_id else ""
        args = [pipeline] + ([execution_id] if execution_id else [])
        cur.execute(f"""
            SELECT execution_id FROM dbo.etl_job_execution
            WHERE pipeline = ? AND status = 'RUNNING' AND end_time IS NULL{extra_exec}
            UNION
            SELECT execution_id FROM dbo.etl_ds_job_log
            WHERE pipeline_name = ? AND status IN ('RUNNING', 'QUEUED'){extra_exec}
        """, args + args)
        alvos = [r[0] for r in cur.fetchall()]
        if not alvos:
            cur.close(); conn.close()
            raise HTTPException(status_code=404,
                detail="Nenhuma execução em andamento encontrada para este pipeline")

        # 1) Tira do Executando (Logs, card do Dashboard, Gantt, SLA/perf monitors)
        cur.execute(f"""
            UPDATE dbo.etl_job_execution
               SET status = ?, end_time = GETDATE(),
                   duration_seconds = DATEDIFF(SECOND, start_time, GETDATE()),
                   updated_at = GETDATE()
             WHERE pipeline = ? AND status = 'RUNNING' AND end_time IS NULL{extra_exec}
        """, [status_final] + args)
        jobs_fechados = max(0, cur.rowcount or 0)

        # 2) Fecha a estrutura no log do DataStage (monitor central para de pollar)
        cur.execute(f"""
            UPDATE dbo.etl_ds_job_log
               SET status = ?, status_code = ?,
                   ds_end_time = COALESCE(ds_end_time, GETDATE()),
                   updated_at = GETDATE()
             WHERE pipeline_name = ? AND status IN ('RUNNING', 'QUEUED'){extra_exec}
        """, [ds_status, ds_code] + args)
        estruturas_fechadas = max(0, cur.rowcount or 0)

        # 3) Limpa a tela Performance imediatamente (novos snapshots não voltam:
        #    o monitor de performance só insere para status='RUNNING')
        cur.execute(f"""
            DELETE FROM dbo.etl_pipeline_performance_snapshot
             WHERE pipeline = ?{extra_exec}
        """, args)
        snapshots_removidos = max(0, cur.rowcount or 0)

        # Auditoria: uma linha por execução finalizada
        matricula = str(user.get("matricula") or "?")
        for eid in alvos:
            novo = f"{status_final} (finalização manual, execução {eid})"
            if motivo:
                novo += f" — motivo: {motivo}"
            cur.execute(
                "INSERT INTO dbo.etl_pipeline_audit "
                "(pipeline_name, changed_by, field_name, old_value, new_value, changed_at) "
                "VALUES (?, ?, 'finalizacao_manual', 'RUNNING', ?, GETDATE())",
                (pipeline, matricula, novo),
            )

        # F8: a MESMA transação alcança a linha que o ciclo da malha lê, e
        # devolve como o ciclo ficou. Fora da transação, uma falha de rede
        # deixaria o log fechado e a malha ainda esperando — que é exatamente o
        # estado que o operador veio desfazer.
        ciclo = _fechar_linha_do_ciclo(cur, pipeline, alvos, status_final,
                                       matricula, motivo)

        conn.commit()
        cur.close(); conn.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    add_notificacao(
        user.get("matricula"),
        f"Pipeline {pipeline} finalizado manualmente",
        f"{len(alvos)} execução(ões) marcadas como {status_final}; "
        f"{jobs_fechados} job(s) e {estruturas_fechadas} estrutura(s) fechados, "
        f"{snapshots_removidos} snapshot(s) de performance removidos.",
        tipo="warning", link="/finalizacao",
    )
    log.info("Finalização manual: %s por %s → %s (execs=%s jobs=%s estruturas=%s snaps=%s)",
             pipeline, user.get("matricula"), status_final,
             alvos, jobs_fechados, estruturas_fechadas, snapshots_removidos)

    resp = {
        "ok": True, "pipeline": pipeline, "status_final": status_final,
        "execucoes_finalizadas": alvos, "jobs_fechados": jobs_fechados,
        "estruturas_fechadas": estruturas_fechadas,
        "snapshots_removidos": snapshots_removidos,
    }
    # ADITIVAS (F8) e só quando houve o quê dizer: front antigo ignora as
    # chaves, e pipeline fora de malha responde byte a byte como antes.
    if ciclo["linhas_ciclo_fechadas"]:
        resp["linhas_ciclo_fechadas"] = ciclo["linhas_ciclo_fechadas"]
    if ciclo["corridas"]:
        resp["corridas"] = ciclo["corridas"]
    if ciclo["avisos"]:
        resp["avisos"] = ciclo["avisos"]
    return resp
