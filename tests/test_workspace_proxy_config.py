"""Contrato de isolamento do overlay DEV; comportamento HTTP coberto pela bancada."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_producao_nao_habilita_workspace():
    assert 'workspace-api' not in (ROOT / 'config/nginx.conf').read_text()
    assert 'workspace-api' not in (ROOT / 'docker-compose.yaml').read_text()


def test_proxy_workspace_resolve_runtime_e_falha_fechada():
    config = (ROOT / 'config/nginx.workspace.dev.conf').read_text()
    assert 'resolver 127.0.0.11 valid=5s ipv6=off;' in config
    assert 'proxy_pass $workspace_backend;' in config
    assert 'location ^~ /orquestra/workspace/ {' in config
    assert 'location = /orquestra/workspace {' in config
    assert 'return 308 /orquestra/workspace/$is_args$args;' in config
    assert 'error_page 502 504 =503 @workspace_unavailable;' in config
    assert 'proxy_set_header Authorization $http_authorization;' in config
    assert 'proxy_set_header X-Correlation-ID $request_id;' in config
    block = config.split('location ^~ /orquestra/workspace/ {')[1].split('\n        }')[0]
    assert 'orquestra-api' not in block
    assert '$http_authorization' not in re.sub(r'proxy_set_header Authorization.*;', '', block)


def test_overlay_sem_porta_publica_e_credencial_obrigatoria():
    config = (ROOT / 'docker-compose.workspace.dev.yaml').read_text()
    assert 'ports:' not in config
    assert 'WORKSPACE_SQL_PASSWORD:?' in config
    assert 'WORKSPACE_SQL_USER:?' in config
    assert 'WORKSPACE_ENABLED:-false' in config
    assert 'no-new-privileges:true' in config


def test_imagens_dotnet_fixadas_por_digest():
    config = (ROOT / 'backend-dotnet/Dockerfile').read_text()
    assert len(re.findall(r'^FROM mcr.microsoft.com/dotnet/(?:sdk|aspnet)@sha256:[0-9a-f]{64}', config, re.M)) == 2
    assert '--locked-mode' in config
    assert 'USER $APP_UID' in config
