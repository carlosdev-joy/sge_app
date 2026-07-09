"""
ORQUESTRA API — v0.3.0

Endpoints:
  POST /auth/login                        — login (valida no Airflow, emite token de sessão)
  POST /auth/logout                       — logout (revoga token)
  GET  /me                                — dados do usuário autenticado
  GET  /auth/airflow-header               — header Basic da service account

  GET  /health                            — health check
  GET  /config                            — parâmetros de configuração da app
  GET  /versao                            — histórico de versões
  POST /versao/register                   — CRUD de versões
  GET  /audit                             — histórico de alterações de pipeline
  GET  /performance                       — snapshots de performance

  GET  /pipelines                         — lista pipelines (paginado, filtros)
  POST /pipelines/register                — cria/atualiza pipeline
  GET  /malha                             — todos pipelines + jobs para visualização de malha

  GET  /jobs                              — lista jobs de pipeline
  POST /pipelines/jobs/register           — registra/atualiza jobs e lineage
  POST /pipelines/jobs/reorder            — reordena jobs

  GET  /execucoes                         — execuções paginadas (agregado ou detalhe)
  POST /execucoes/rerun                   — reexecuta a partir de uma task
  POST /execucoes/ack                     — acknowledge de falha
  GET  /execucoes/duracao-media           — duração média P50 por job_name

  GET  /dashboard                         — KPIs + status + falhas + running
  GET  /dashboard/gantt                   — linha do tempo das execuções do dia

  GET  /lineage                           — lineage de um pipeline
  PUT  /lineage/job                       — substitui lineage de um job
  POST /lineage/extract-dsx               — extrai lineage de arquivo .dsx
  POST /lineage/normalize                 — normaliza lineage legado
  GET  /lineage/dsx-files                 — lista arquivos .dsx disponíveis
  GET  /lineage/dsx-folders               — lista pastas (Category) de um .dsx
  GET  /lineage/field-impact              — impacto por campo (varredura de .dsx)

  GET    /change-plans                    — lista planos de ajuste de campos
  POST   /change-plans                    — cria plano (com itens opcionais)
  GET    /change-plans/{id}               — plano + itens
  POST   /change-plans/{id}/items         — adiciona itens ao plano
  PATCH  /change-plans/{id}/items/{iid}   — atualiza item (status/alvo/obs)
  DELETE /change-plans/{id}/items/{iid}   — remove item
  POST   /change-plans/{id}/finalize      — finaliza (ou reabre) o plano
  DELETE /change-plans/{id}               — remove plano

  POST /catalogo                          — catálogo de dados (multi-modo)

  GET  /sync/pipeline-status/dry-run      — simula sincronização sem alterar banco
  POST /sync/pipeline-status              — sincroniza status com Airflow

  POST /admin                             — operações administrativas
  POST /admin/freeze                      — congela/descongela ambiente
  POST /admin/test-webhook                — testa envio ao Teams

  GET  /agenda/calendarios                — lista calendários
  GET  /agenda/calendarios/{nome}         — datas de um calendário
  POST /agenda/calendarios                — adiciona datas a calendário
  DELETE /agenda/calendarios/{nome}       — remove datas ou calendário
  GET  /agenda/blackouts                  — lista blackouts
  POST /agenda/blackouts                  — cria janela de blackout
  POST /agenda/blackouts/{id}/encerrar    — encerra blackout

  POST /sequence/parse                    — parse de sequence .dsx
  POST /sequence/approve                  — aprova importação de sequence

  POST /datastage/monitor                 — dispara DAG de monitoramento DataStage
  GET  /datastage/log                     — consulta logs DataStage
  GET  /datastage/status                  — status atual de job DataStage

  GET    /malha-ds/xml-files               — lista exports .xml disponíveis (lineage via XML/DSX)
  GET    /malha-ds/{project}/lineage-preview — preview do lineage do XML × atual (read-only)

  GET  /factory/runs                      — execuções da etl_dag_factory
  GET  /factory/runs/{dag_run_id}/log     — log estruturado de execução da factory

  GET  /airflow/connections/ssh           — lista conexões SSH no Airflow

  GET  /copias/conexoes                   — connections MSSQL do Airflow (Cópia de Dados)
  GET  /copias/introspect/databases       — bancos de uma connection (direto/cache/airflow)
  GET  /copias/introspect/tables          — tabelas + nº de linhas de um banco
  GET  /copias/introspect/columns         — colunas de uma tabela + partição sugerida
  POST /copias/preview                    — amostra (TOP 50) do SELECT transformado
  GET  /copias                            — lista cópias salvas (com última execução)
  POST /copias                            — cria/atualiza cópia (compila transformações)
  GET  /copias/{id}                       — detalhe completo da cópia
  DELETE /copias/{id}                     — soft delete da cópia
  POST /copias/{id}/executar              — dispara a DAG etl_copy_exec
  GET  /copias/{id}/execucoes             — histórico de execuções da cópia
  GET  /copias/exec/{exec_id}             — progresso de uma execução (polling)
  POST /copias/exec/{exec_id}/cancelar    — pede cancelamento da execução

  GET    /inventario/endpoints              — inventário de consumidores (endpoints + objetos)
  POST   /inventario/endpoints              — cria/atualiza endpoint do inventário
  DELETE /inventario/endpoints/{id}         — soft delete do endpoint
  POST   /inventario/endpoints/{id}/objetos — adiciona objeto consumido (view/proc/tabela)
  PATCH  /inventario/objetos/{id}           — atualiza status de validação/observação
  DELETE /inventario/objetos/{id}           — remove objeto do inventário

  GET  /powerbi/status                              — diagnóstico de configuração/token/admin API
  GET  /powerbi/overview                            — workspaces + datasets + status refresh + datasource type
  GET  /powerbi/workspaces                          — workspaces visíveis ao service principal
  GET  /powerbi/workspaces/{gid}/datasets           — datasets de um workspace
  GET  /powerbi/workspaces/{gid}/reports            — reports de um workspace
  GET  /powerbi/workspaces/{gid}/datasets/{did}                   — detalhe do dataset
  GET  /powerbi/workspaces/{gid}/datasets/{did}/refreshes         — histórico de refresh
  GET  /powerbi/workspaces/{gid}/datasets/{did}/refresh-schedule  — agendamento de refresh
  GET  /powerbi/workspaces/{gid}/datasets/{did}/datasources       — conexões (tipo/servidor)
  GET  /powerbi/workspaces/{gid}/datasets/{did}/parameters        — parâmetros do dataset
  GET  /powerbi/workspaces/{gid}/datasets/{did}/users             — usuários com acesso
  GET  /powerbi/gateways                            — gateways acessíveis
  GET  /powerbi/gateways/{id}/datasources           — datasources de um gateway
  GET  /powerbi/capacities                          — capacities acessíveis
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.dag_reconcile import reconcile_loop
from services.monitor_capture import capture_loop as monitor_capture_loop

from routers import (
    auth, infra, pipelines, jobs, execucoes, dashboard,
    lineage, catalogo, sync, admin, agenda, sequence,
    datastage, factory, airflow, change_plans, powerbi, lineage_xml,
    notificacoes, comunicados, backlog, monitor, mensagens, copias,
    inventario, finalizacao, caixa_chat,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("orquestra-api")

# Fail-closed: sem CORS_ORIGINS, NENHUMA origem cross-site é liberada (o app é
# same-origin pelo nginx, então funciona normal). Nunca usar "*" com credenciais.
_cors_env = os.getenv("CORS_ORIGINS", "").strip()
CORS_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()]
MSSQL_CONN_STR = os.getenv("MSSQL_CONN_STR", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not MSSQL_CONN_STR:
        log.warning("MSSQL_CONN_STR não definida — endpoints de banco vão falhar")
    if not CORS_ORIGINS:
        log.warning("CORS_ORIGINS vazio — cross-origin bloqueado (ok p/ same-origin via nginx). "
                    "Defina CORS_ORIGINS se precisar de origem cross-site.")
    if "*" in CORS_ORIGINS:
        log.warning("CORS_ORIGINS contém '*' — inseguro com credenciais; restrinja às origens do app.")
    log.info("ORQUESTRA API v0.3.0 iniciando")
    # Reconciliador do Gerar-DAG: conclui despause/notificação a partir da fila
    # persistida (etl_dag_pendente), retomando itens deixados por um restart.
    reconcile_task = asyncio.create_task(reconcile_loop())
    # Observabilidade de tabelas: captura snapshots periódicos (frescor/volume).
    monitor_task = asyncio.create_task(monitor_capture_loop())
    yield
    for _t in (reconcile_task, monitor_task):
        _t.cancel()
        try:
            await _t
        except asyncio.CancelledError:
            pass
    log.info("ORQUESTRA API encerrando.")


app = FastAPI(
    title="ORQUESTRA API",
    version="0.3.0",
    description="API de integração ORQUESTRA — sincronização de pipelines com Airflow",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Registra todos os routers
for _router_module in [
    auth, infra, pipelines, jobs, execucoes, dashboard,
    lineage, catalogo, sync, admin, agenda, sequence,
    datastage, factory, airflow, change_plans, powerbi, lineage_xml,
    notificacoes, comunicados, backlog, monitor, mensagens, copias,
    inventario, finalizacao, caixa_chat,
]:
    app.include_router(_router_module.router)
