"""API REST do DataStage de AMOSTRA (spec docs/spec-lineage-isx.md, F1) — só DEV.

Serve, por HTTP simples, os JSONs de `rotas.json` nos mesmos caminhos da API real
(`/ibm/iis/ds/api/engines`, `.../folders/<engine>%5C<projeto>%5CJobs/contents`,
`.../jobdesigns/<...>`). Exige Basic auth (qualquer usuário/senha não vazios) para
a API do Orquestra exercitar o cabeçalho. Sem dependência fora da biblioteca
padrão: roda em `python:3.12-alpine` sem pip.
"""
from __future__ import annotations

import base64
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AQUI = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(AQUI, "rotas.json"), encoding="utf-8") as f:
    ROTAS: dict[str, dict] = json.load(f)
PORTA = int(os.environ.get("DS_API_AMOSTRA_PORTA", "9443"))


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, corpo: dict) -> None:
        dados = json.dumps(corpo).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self) -> None:  # noqa: N802
        auth = self.headers.get("Authorization") or ""
        if not auth.startswith("Basic "):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="amostra"')
            self.end_headers()
            return
        try:
            usuario, _, senha = base64.b64decode(auth[6:]).decode("utf-8").partition(":")
        except Exception:  # noqa: BLE001
            usuario, senha = "", ""
        if not usuario or not senha:
            self._json(401, {"erro": "credencial vazia"})
            return
        caminho = self.path.split("?", 1)[0].rstrip("/")
        corpo = ROTAS.get(caminho)
        if corpo is None:
            self._json(404, {"erro": "rota desconhecida", "path": caminho})
            return
        self._json(int(corpo.get("_status", 200)), {k: v for k, v in corpo.items() if not k.startswith("_")})

    def log_message(self, fmt, *args):  # noqa: D102
        print("[ds-api-amostra]", fmt % args, flush=True)


if __name__ == "__main__":
    print(f"[ds-api-amostra] {len(ROTAS)} rotas na porta {PORTA}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORTA), Handler).serve_forever()
