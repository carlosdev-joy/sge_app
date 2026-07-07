"""
Testes da validação/normalização do nó Python v2 no backend
(_validate_python_node/_normalize_python_node em api/routers/jobs.py).

Funções puras (não tocam banco) — importadas via fixture, como nos vizinhos.
"""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def J():
    import routers.jobs as _j
    return _j


# ── Legado / discriminação de modo ───────────────────────────────────────────

def test_none_e_legado_ok(J):
    assert J._validate_python_node(None, None) == []


def test_nao_dict_invalido(J):
    assert J._validate_python_node("x", "ssh_a")


def test_modo_invalido(J):
    errs = J._validate_python_node({"modo": "modulo"}, "ssh_a")
    assert any("modo do nó Python inválido" in e for e in errs)


# ── Modo arquivo ─────────────────────────────────────────────────────────────

def test_arquivo_valido(J):
    cfg = {"modo": "arquivo", "script_path": "/opt/scripts/carga.py"}
    assert J._validate_python_node(cfg, "ssh_a") == []


def test_arquivo_exige_ssh(J):
    cfg = {"modo": "arquivo", "script_path": "/opt/scripts/carga.py"}
    errs = J._validate_python_node(cfg, None)
    assert any("Servidor SSH é obrigatório" in e for e in errs)


@pytest.mark.parametrize("ruim", [
    "", "relativo.py", "/sem/extensao", "/com espaco/x.py", "/aspas'x.py",
])
def test_arquivo_caminho_invalido(J, ruim):
    errs = J._validate_python_node({"modo": "arquivo", "script_path": ruim}, "ssh_a")
    assert any("caminho do script inválido" in e for e in errs)


# ── Modo código ──────────────────────────────────────────────────────────────

def test_codigo_valido(J):
    cfg = {"modo": "codigo", "destino_dir": "/opt/scripts", "arquivo": "gerado.py",
           "codigo": "print(1)"}
    assert J._validate_python_node(cfg, "ssh_a") == []


def test_codigo_campos_invalidos(J):
    errs = J._validate_python_node(
        {"modo": "codigo", "destino_dir": "relativo", "arquivo": "sem_py.txt",
         "codigo": "  "}, "ssh_a")
    assert any("diretório de destino inválido" in e for e in errs)
    assert any("nome do arquivo inválido" in e for e in errs)
    assert any("código Python vazio" in e for e in errs)


def test_interpretador_invalido(J):
    errs = J._validate_python_node(
        {"modo": "arquivo", "script_path": "/opt/x.py",
         "interpretador": "python3; rm -rf /"}, "ssh_a")
    assert any("interpretador inválido" in e for e in errs)


# ── Normalização ─────────────────────────────────────────────────────────────

def test_normalize_arquivo_so_chaves_do_modo(J):
    out = J._normalize_python_node({
        "modo": " ARQUIVO ", "script_path": " /opt/x.py ",
        "destino_dir": "/lixo", "arquivo": "lixo.py", "codigo": "lixo",
    })
    assert out == {"modo": "arquivo", "script_path": "/opt/x.py"}


def test_normalize_codigo_preserva_codigo_e_normaliza_dir(J):
    out = J._normalize_python_node({
        "modo": "codigo", "destino_dir": "/opt/scripts/", "arquivo": " g.py ",
        "codigo": "print(1)\n", "interpretador": " python3.11 ",
    })
    assert out == {"modo": "codigo", "destino_dir": "/opt/scripts",
                   "arquivo": "g.py", "codigo": "print(1)\n",
                   "interpretador": "python3.11"}
