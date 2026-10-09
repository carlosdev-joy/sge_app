import asyncio
import shutil
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from routers import execucoes


def test_workspace_model_preserves_all_types_unknown_fields_and_transport():
    root=Path(__file__).resolve().parents[1]
    if not shutil.which("node") or not (root/"ui-react/node_modules/sucrase").is_dir():
        pytest.skip("Node/sucrase indisponível")
    result=subprocess.run(["node",str(root/"tests/js/workspace_f3_harness.cjs")],cwd=root,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr


@pytest.mark.parametrize("missing",["tela_pipelines","tela_jobs","tela_logs"])
def test_execution_query_alias_checks_permissions_before_legacy_read(monkeypatch,missing):
    read=AsyncMock();monkeypatch.setattr(execucoes,"get_pipeline_execucao",read)
    with pytest.raises(HTTPException) as e:
        asyncio.run(execucoes.get_workspace_pipeline_execution("a/b",_auth={"permissoes":[p for p in ("tela_pipelines","tela_jobs","tela_logs") if p!=missing]}))
    assert e.value.status_code==403
    read.assert_not_called()


def test_execution_query_alias_preserves_slashes_percent_unicode_and_date(monkeypatch):
    read=AsyncMock(return_value={"etapas":[]});monkeypatch.setattr(execucoes,"get_pipeline_execucao",read)
    actor={"permissoes":["tela_pipelines","tela_jobs","tela_logs"]}
    assert asyncio.run(execucoes.get_workspace_pipeline_execution("ação/A %25",data_referencia="2026-10-09",_auth=actor))=={"etapas":[]}
    read.assert_awaited_once_with("ação/A %25",data_referencia="2026-10-09",_auth=actor)
