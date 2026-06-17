"""api/routers/powerbi.py — Sustentação de relatórios Power BI (ORQUESTRA).

Todos os endpoints usam o service principal configurado em Admin > Configurações
(ver api/services/powerbi_client.py). Endpoints somente leitura (GET), pensados
para a tela de sustentação: visão geral de workspaces/datasets, saúde de refresh,
datasources (tipo de conexão) e gateways.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from deps import get_current_user
from services.powerbi_client import get_pbi_config, is_configured, pbi_get

log = logging.getLogger("orquestra-api")

router = APIRouter(prefix="/powerbi", tags=["powerbi"])

OVERVIEW_DATASET_LIMIT = 200
OVERVIEW_CONCURRENCY = 6


# ── Status / diagnóstico ─────────────────────────────────────────────────────

@router.get("/status")
async def powerbi_status(_user: dict = Depends(get_current_user)):
    """Diagnóstico rápido: configurado? token ok? alcança a API?"""
    cfg = get_pbi_config()
    result = {
        "configurado": is_configured(),
        "config": {
            "powerbi_tenant_id":     "✓ preenchido" if cfg["powerbi_tenant_id"] else "✗ ausente",
            "powerbi_client_id":     "✓ preenchido" if cfg["powerbi_client_id"] else "✗ ausente",
            "powerbi_client_secret": "✓ preenchido" if cfg["powerbi_client_secret"] else "✗ ausente",
            "powerbi_scope":         cfg["powerbi_scope"] or "(default)",
            "powerbi_token_url":     cfg["powerbi_token_url"] or "(derivado do tenant_id)",
        },
        "token_ok": False,
        "workspaces_acessiveis": None,
        "admin_api_liberada": None,
        "erro": None,
    }
    if not result["configurado"]:
        result["erro"] = ("Power BI não configurado. Preencha powerbi_tenant_id, powerbi_client_id e "
                           "powerbi_client_secret em Admin > Configurações.")
        return result

    try:
        groups = await pbi_get("groups", params={"$top": 1})
        result["token_ok"] = True
        result["workspaces_acessiveis"] = len((await pbi_get("groups", params={"$top": 100})).get("value", []))
    except HTTPException as e:
        result["erro"] = e.detail
        return result

    try:
        await pbi_get("admin/groups", params={"$top": 1})
        result["admin_api_liberada"] = True
    except HTTPException:
        result["admin_api_liberada"] = False

    return result


# ── Workspaces / Datasets / Reports (escopo do service principal) ───────────

@router.get("/workspaces")
async def list_workspaces(_user: dict = Depends(get_current_user)):
    data = await pbi_get("groups", params={"$top": 200})
    return {"total": len(data.get("value", [])), "data": data.get("value", [])}


@router.get("/workspaces/{group_id}/datasets")
async def list_workspace_datasets(group_id: str, _user: dict = Depends(get_current_user)):
    data = await pbi_get(f"groups/{group_id}/datasets")
    return {"total": len(data.get("value", [])), "data": data.get("value", [])}


@router.get("/workspaces/{group_id}/reports")
async def list_workspace_reports(group_id: str, _user: dict = Depends(get_current_user)):
    data = await pbi_get(f"groups/{group_id}/reports")
    return {"total": len(data.get("value", [])), "data": data.get("value", [])}


# ── Detalhe de dataset (sustentação) ─────────────────────────────────────────

@router.get("/workspaces/{group_id}/datasets/{dataset_id}")
async def get_dataset_detail(group_id: str, dataset_id: str, _user: dict = Depends(get_current_user)):
    return await pbi_get(f"groups/{group_id}/datasets/{dataset_id}")


@router.get("/workspaces/{group_id}/datasets/{dataset_id}/refreshes")
async def get_dataset_refreshes(
    group_id: str, dataset_id: str,
    top: int = Query(10, ge=1, le=100),
    _user: dict = Depends(get_current_user),
):
    data = await pbi_get(f"groups/{group_id}/datasets/{dataset_id}/refreshes", params={"$top": top})
    return {"total": len(data.get("value", [])), "data": data.get("value", [])}


@router.get("/workspaces/{group_id}/datasets/{dataset_id}/refresh-schedule")
async def get_dataset_refresh_schedule(group_id: str, dataset_id: str, _user: dict = Depends(get_current_user)):
    return await pbi_get(f"groups/{group_id}/datasets/{dataset_id}/refreshSchedule")


@router.get("/workspaces/{group_id}/datasets/{dataset_id}/datasources")
async def get_dataset_datasources(group_id: str, dataset_id: str, _user: dict = Depends(get_current_user)):
    data = await pbi_get(f"groups/{group_id}/datasets/{dataset_id}/datasources")
    return {"total": len(data.get("value", [])), "data": data.get("value", [])}


@router.get("/workspaces/{group_id}/datasets/{dataset_id}/parameters")
async def get_dataset_parameters(group_id: str, dataset_id: str, _user: dict = Depends(get_current_user)):
    data = await pbi_get(f"groups/{group_id}/datasets/{dataset_id}/parameters")
    return {"total": len(data.get("value", [])), "data": data.get("value", [])}


@router.get("/workspaces/{group_id}/datasets/{dataset_id}/users")
async def get_dataset_users(group_id: str, dataset_id: str, _user: dict = Depends(get_current_user)):
    data = await pbi_get(f"groups/{group_id}/datasets/{dataset_id}/users")
    return {"total": len(data.get("value", [])), "data": data.get("value", [])}


# ── Gateways / Capacities ─────────────────────────────────────────────────────

@router.get("/gateways")
async def list_gateways(_user: dict = Depends(get_current_user)):
    data = await pbi_get("gateways")
    return {"total": len(data.get("value", [])), "data": data.get("value", [])}


@router.get("/gateways/{gateway_id}/datasources")
async def get_gateway_datasources(gateway_id: str, _user: dict = Depends(get_current_user)):
    data = await pbi_get(f"gateways/{gateway_id}/datasources")
    return {"total": len(data.get("value", [])), "data": data.get("value", [])}


@router.get("/capacities")
async def list_capacities(_user: dict = Depends(get_current_user)):
    data = await pbi_get("capacities")
    return {"total": len(data.get("value", [])), "data": data.get("value", [])}


# ── Overview agregado (visão principal da tela de sustentação) ──────────────

async def _fetch_datasets_for_workspace(client: httpx.AsyncClient, ws: dict, sem: asyncio.Semaphore) -> list[dict]:
    async with sem:
        try:
            data = await pbi_get(f"groups/{ws['id']}/datasets", client=client)
        except HTTPException as e:
            log.info("overview: falha ao listar datasets do workspace %s: %s", ws.get("name"), e.detail)
            return []
    out = []
    for ds in data.get("value", []):
        ds["_workspace_id"] = ws["id"]
        ds["_workspace_name"] = ws.get("name")
        out.append(ds)
    return out


async def _enrich_dataset(client: httpx.AsyncClient, ds: dict, sem: asyncio.Semaphore) -> dict:
    ws_id, ds_id = ds["_workspace_id"], ds["id"]
    enriched = {
        "dataset_id": ds_id,
        "dataset_name": ds.get("name"),
        "workspace_id": ws_id,
        "workspace_name": ds.get("_workspace_name"),
        "configured_by": ds.get("configuredBy"),
        "is_refreshable": ds.get("isRefreshable"),
        "last_refresh_status": None,
        "last_refresh_start": None,
        "last_refresh_end": None,
        "last_refresh_error": None,
        "datasource_types": [],
        "erro": None,
    }

    async with sem:
        # datasources → tipo de conexão (SQL, SharePoint, Web, etc.)
        try:
            ds_sources = await pbi_get(f"groups/{ws_id}/datasets/{ds_id}/datasources", client=client)
            enriched["datasource_types"] = sorted({
                d.get("datasourceType") for d in ds_sources.get("value", []) if d.get("datasourceType")
            })
        except HTTPException as e:
            enriched["erro"] = e.detail

        # última atualização (status de refresh)
        if ds.get("isRefreshable"):
            try:
                refreshes = await pbi_get(
                    f"groups/{ws_id}/datasets/{ds_id}/refreshes", params={"$top": 1}, client=client
                )
                items = refreshes.get("value", [])
                if items:
                    last = items[0]
                    enriched["last_refresh_status"] = last.get("status")
                    enriched["last_refresh_start"] = last.get("startTime")
                    enriched["last_refresh_end"] = last.get("endTime")
                    err = last.get("serviceExceptionJson")
                    enriched["last_refresh_error"] = err[:500] if err else None
            except HTTPException as e:
                enriched["erro"] = (enriched["erro"] + " | " if enriched["erro"] else "") + e.detail

    return enriched


@router.get("/overview")
async def powerbi_overview(_user: dict = Depends(get_current_user)):
    """Agrega workspaces + datasets + status de última atualização + tipo de fonte.

    Único endpoint que a tela principal de sustentação precisa chamar — evita
    N chamadas do browser direto à API do Power BI e mantém o token no backend.
    """
    workspaces_resp = await pbi_get("groups", params={"$top": 200})
    workspaces = workspaces_resp.get("value", [])

    sem_list = asyncio.Semaphore(OVERVIEW_CONCURRENCY)
    async with httpx.AsyncClient() as client:
        per_ws = await asyncio.gather(*[
            _fetch_datasets_for_workspace(client, ws, sem_list) for ws in workspaces
        ])
        all_datasets = [ds for sub in per_ws for ds in sub][:OVERVIEW_DATASET_LIMIT]

        sem_ds = asyncio.Semaphore(OVERVIEW_CONCURRENCY)
        enriched = await asyncio.gather(*[
            _enrich_dataset(client, ds, sem_ds) for ds in all_datasets
        ])

    falhas = sum(1 for d in enriched if (d["last_refresh_status"] or "").lower() == "failed")
    sem_status = sum(1 for d in enriched if d["is_refreshable"] and not d["last_refresh_status"])

    return {
        "workspaces": {"total": len(workspaces), "data": workspaces},
        "datasets": {
            "total": len(enriched),
            "truncado": len(all_datasets) >= OVERVIEW_DATASET_LIMIT,
            "data": enriched,
        },
        "resumo": {
            "total_workspaces": len(workspaces),
            "total_datasets": len(enriched),
            "datasets_com_falha": falhas,
            "datasets_sem_status": sem_status,
        },
    }
