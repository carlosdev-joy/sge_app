"""Admin › E-mail no front (F1 da spec docs/spec-notificacao-email.md):
lib/emailAdmin.ts pela bancada tests/js/ds_params_harness.cjs (seção 9).

O que se prende: listas ↔ texto (uma por linha ou vírgula, sem repetição), o
corpo do POST normalizado (remetente aparado, limite numérico, listas), e a
régua local que espelha `validar_config` da API — ligar sem remetente,
remetente inválido, limite 1–25 inteiro, raízes absolutas sem `..`/espaço,
domínios — mais as mensagens de erro e a detecção da migration 111.

Sem Node ou sem `node_modules` a suíte SALTA em vez de falhar.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "ds_params_harness.cjs"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"


def _node() -> str | None:
    caminho = shutil.which("node")
    if not caminho or not SUCRASE.is_dir():
        return None
    try:
        v = subprocess.run([caminho, "-v"], capture_output=True, text=True, timeout=30).stdout.strip()
        return caminho if int(v.lstrip("v").split(".")[0]) >= 18 else None
    except Exception:      # noqa: BLE001
        return None


@pytest.fixture(scope="module")
def e() -> dict:
    node = _node()
    if node is None:
        pytest.skip("front não instalado nesta máquina")
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True, cwd=str(RAIZ), timeout=180)
    assert r.returncode == 0, f"bancada do front falhou:\n{r.stderr}"
    return json.loads(r.stdout)["emailAdmin"]


def test_form_e_corpo(e):
    assert e["form"] == {"enabled": True, "remetente": "orquestra@cvp.com.br", "limite_mb": "5",
                         "raizesTexto": "/dados/saida\n/opt/IBM/dados", "dominiosTexto": "cvp.com.br",
                         "exigirModelo": False}
    assert e["corpo"] == {"enabled": True, "remetente": "Orq@CVP.com.br", "limite_mb": 10,
                          "raizes": ["/a", "/b"], "dominios": [], "exigir_modelo": False}
    assert e["listas"] == [["a@x.com", "b@y.org", "c@z.io"], "/a\n/b", []]


def test_regua_local(e):
    r = e["erros"]
    assert r["valido"] == []
    assert r["ligadoSemRemetente"] == ["Informe o remetente antes de ligar o canal"]
    assert r["desligadoSemRemetente"] == []
    assert r["remetenteRuim"] == ["Remetente inválido (um endereço de e-mail)"]
    assert r["limite"] == [1, 1, 1, 0]
    assert len(r["raizes"]) == 3 and all("Raiz inválida" in x for x in r["raizes"])   # "/ok/" é válida
    assert r["raizBarra"] == ['Raiz inválida: "/" abriria o servidor inteiro — use uma pasta']
    assert len(r["raizPonto"]) == 1 and "Raiz inválida" in r["raizPonto"][0]
    assert r["dominios"] == ["Domínio inválido: ruim"]
    # espelha o teto VARCHAR(1000) de validar_config: a tela avisa antes do 422
    assert len(r["longa"]) == 1 and "lista longa demais" in r["longa"][0]


def test_mensagens_e_etapas(e):
    assert e["mensagens"] == ["a · b", "E-mail indisponível: migration 111 pendente", "padrão"]
    assert e["pendente111"] == [True, False]
    assert e["etapas"] == ["ok", "sendmail", "config", "ssh"]
