#!/usr/bin/env python3
"""Smoke HTTP de Nginx em rede Docker isolada, sem credenciais ou serviços DEV.

Usa imagens locais nginx:1.27 e python:3.12-alpine; não baixa imagens.
Não valida SQL/autenticação .NET: esses gates têm bancadas próprias.
"""
import json
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]


def docker(*args):
    result = subprocess.run(['docker', *args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


CLIENT = None


def request(url, method='GET', redirect=True):
    # Cliente dentro da própria rede internal: nenhum bind de porta no host.
    code = """import json,sys,urllib.request,urllib.error
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args): return None
opener=urllib.request.build_opener() if sys.argv[3]=='True' else urllib.request.build_opener(NoRedirect)
req=urllib.request.Request(sys.argv[1],method=sys.argv[2],headers={'Authorization':'Bearer synthetic-smoke','X-Correlation-ID':'untrusted'})
try: response=opener.open(req,timeout=15)
except urllib.error.HTTPError as error: response=error
with response: print(json.dumps([response.status,dict(response.headers),response.read().decode()]))
"""
    return json.loads(docker('exec', CLIENT, 'python', '-c', code, url, method, str(redirect)))


def main():
    global CLIENT
    suffix = uuid.uuid4().hex[:10]
    network = 'workspace-smoke-' + suffix
    legacy, workspace, proxy = [network + '-' + name for name in ('legacy', 'workspace', 'proxy')]
    created = []
    docker('image', 'inspect', 'nginx:1.27', 'python:3.12-alpine')
    try:
        docker('network', 'create', '--internal', network)
        with tempfile.TemporaryDirectory(prefix='workspace-proxy-') as folder:
            server = Path(folder) / 'server.py'
            server.write_text('''from http.server import BaseHTTPRequestHandler, HTTPServer
import json
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  status = 503 if self.path.startswith('/workspace/health/ready') else 200
  self.send_response(status); self.send_header('Content-Type','application/json'); self.end_headers()
  self.wfile.write(json.dumps({'path':self.path,'auth':self.headers.get('Authorization'),'correlation':self.headers.get('X-Correlation-ID'),'detail':'Dependência do workspace indisponível' if status == 503 else 'ok'}).encode())
 do_POST = do_GET
 def log_message(self,*args): pass
HTTPServer(('0.0.0.0',8080),Handler).serve_forever()
''')
            docker('run', '-d', '--pull=never', '--name', legacy, '--network', network,
                   '--network-alias', 'orquestra-api', '--network-alias', 'airflow-webserver',
                   '-v', str(server) + ':/server.py:ro', 'python:3.12-alpine', 'python', '/server.py')
            created.append(legacy)
            CLIENT = legacy
            # Adaptar apenas portas legadas para a bancada; produção/config DEV intactas.
            config = Path(folder) / 'nginx.conf'
            config.write_text((ROOT / 'config/nginx.workspace.dev.conf').read_text().replace('orquestra-api:8000', 'orquestra-api:8080'))
            docker('run', '-d', '--pull=never', '--name', proxy, '--network', network,
                   '--network-alias', 'proxy', '-v', str(config) + ':/etc/nginx/nginx.conf:ro', 'nginx:1.27')
            created.append(proxy)
            base = 'http://proxy'
            for _ in range(30):
                try:
                    assert request(base + '/orquestra/health')[0] == 200
                    break
                except (OSError, AssertionError, RuntimeError):
                    time.sleep(.2)
            else:
                raise AssertionError('Proxy não iniciou com workspace ausente')
            absent = request(base + '/orquestra/workspace/capabilities')
            assert absent[0] == 503, absent
            status, headers, _ = request(base + '/orquestra/workspace?x=1', redirect=False)
            assert status == 308 and headers['Location'] == '/orquestra/workspace/?x=1'
            docker('run', '-d', '--pull=never', '--name', workspace, '--network', network,
                   '--network-alias', 'workspace-api', '-v', str(server) + ':/server.py:ro',
                   'python:3.12-alpine', 'python', '/server.py')
            created.append(workspace)
            for _ in range(40):
                status, _, body = request(base + '/orquestra/workspace/capabilities?x=a%20b')
                if status == 200:
                    break
                time.sleep(.25)
            assert status == 200, 'DNS não recuperou upstream criado depois do proxy'
            data = json.loads(body)
            assert data['path'] == '/workspace/capabilities?x=a%20b'
            assert data['auth'] == 'Bearer synthetic-smoke'
            assert data['correlation'] != 'untrusted' and len(data['correlation']) == 32
            assert request(base + '/orquestra/workspace/health/ready')[0] == 503
            for route in ('/orquestra/health', '/orquestra/me', '/orquestra/pipelines', '/orquestra/workspaceXYZ', '/api/v1/dags', '/'):
                assert request(base + route)[0] == 200, route
            docker('stop', workspace)
            for method in ('GET', 'POST'):
                status, headers, body = request(base + '/orquestra/workspace/capabilities', method)
                assert status == 503 and json.loads(body)['code'] == 'workspace_unavailable'
                assert headers['Cache-Control'] == 'no-store'
            assert request(base + '/orquestra/health')[0] == 200
            print('PASS: upstream ausente, recuperação DNS, path/query/barra, headers, 503 SQL simulado, legado/UI/Airflow e upstream parado GET/POST')
    finally:
        for name in reversed(created):
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
        subprocess.run(['docker', 'network', 'rm', network], capture_output=True)


if __name__ == '__main__':
    main()
