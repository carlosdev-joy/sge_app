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

  GET  /factory/runs                      — execuções da etl_dag_factory
  GET  /factory/runs/{dag_run_id}/log     — log estruturado de execução da factory

  GET  /airflow/connections/ssh           — lista conexões SSH no Airflow
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import (
    auth, infra, pipelines, jobs, execucoes, dashboard,
    lineage, catalogo, sync, admin, agenda, sequence,
    datastage, factory, airflow
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("orquestra-api")

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
MSSQL_CONN_STR = os.getenv("MSSQL_CONN_STR", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not MSSQL_CONN_STR:
        log.warning("MSSQL_CONN_STR não definida — endpoints de banco vão falhar")
    if CORS_ORIGINS == ["*"]:
        log.warning("CORS_ORIGINS='*' — recomendado restringir à origem do nginx via env CORS_ORIGINS")
    log.info("ORQUESTRA API v0.3.0 iniciando")
    yield
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
    datastage, factory, airflow,
]:
    app.include_router(_router_module.router)
