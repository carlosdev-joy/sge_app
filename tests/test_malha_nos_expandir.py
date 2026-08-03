"""
Testes da expansão dos nós de malha (F10 — desenho §3.2) e da PARIDADE entre o
canônico (dags/utils/malha_nos.py) e o port da API (api/services/malha_nos.py).

Grupo 1 do §13 do desenho: N×M simples; aguarde→aguarde transitivo; aguarde
sem entrada = conjunto vazio; nó isolado; e a paridade port × canônico — a
MESMA matriz de cenários roda nos DOIS módulos e o resultado tem de ser
IDÊNTICO (precedente de test_malhas_f9/test_dependencias_f5_paridade).

Módulos PUROS: nenhum teste toca banco, FastAPI ou Airflow.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Replica o mock de pyodbc do conftest (garante o import de api.main mesmo se
# este arquivo for coletado antes do conftest configurar o ambiente).
if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from services import malha_nos as exp_api

_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def exp_dags():
    """Canônico de dags/, carregado por caminho como em test_malhas_f9."""
    spec = importlib.util.spec_from_file_location(
        "malha_nos_dags_f10", _ROOT / "dags/utils/malha_nos.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── cenários compartilhados (a matriz da paridade) ───────────────────────────

def _ar(**kw):
    """Aresta no formato da etl_malha_aresta (chave ausente = None, como o
    contrato do expandir declara)."""
    return kw


CENARIOS = {
    # 2×2 simples: A,B → W1 → C,D (a explosão N×M do §3.1)
    "nxm": (
        [{"id": 1, "tipo": "aguarde"}],
        [_ar(origem_pipeline="A", destino_no=1),
         _ar(origem_pipeline="B", destino_no=1),
         _ar(origem_no=1, destino_pipeline="C"),
         _ar(origem_no=1, destino_pipeline="D")],
    ),
    # Encadeado: A→W1→B, W1→W2, C→W2, W2→D (upstream transitivo do §2.1)
    "encadeado": (
        [{"id": 1, "tipo": "aguarde"}, {"id": 2, "tipo": "aguarde"}],
        [_ar(origem_pipeline="A", destino_no=1),
         _ar(origem_no=1, destino_pipeline="B"),
         _ar(origem_no=1, destino_no=2),
         _ar(origem_pipeline="C", destino_no=2),
         _ar(origem_no=2, destino_pipeline="D")],
    ),
    # Aguarde com saídas e SEM entrada: zero dependência (o efeito zero é dito
    # no aviso do §2.2 — aqui só a matemática)
    "sem_entrada": (
        [{"id": 7, "tipo": "aguarde"}],
        [_ar(origem_no=7, destino_pipeline="X")],
    ),
    # Nó fora do grafo: sets vazios
    "isolado": (
        [{"id": 3, "tipo": "aguarde"}, {"id": 4, "tipo": "notificacao"}],
        [],
    ),
    # Observadores e Início NÃO compilam dependência (só o Aguarde)
    "observadores": (
        [{"id": 1, "tipo": "inicio"}, {"id": 2, "tipo": "notificacao"},
         {"id": 3, "tipo": "fim"}],
        [_ar(origem_no=1, destino_pipeline="A"),
         _ar(origem_pipeline="A", destino_no=2),
         _ar(origem_pipeline="A", destino_no=3),
         _ar(origem_pipeline="B", destino_no=3)],
    ),
    # Ciclo entre nós (entrada malformada — a API recusa no gesto): o BFS não
    # pode pendurar
    "ciclo_malformado": (
        [{"id": 1, "tipo": "aguarde"}, {"id": 2, "tipo": "aguarde"}],
        [_ar(origem_pipeline="A", destino_no=1),
         _ar(origem_no=1, destino_no=2),
         _ar(origem_no=2, destino_no=1),
         _ar(origem_no=2, destino_pipeline="B")],
    ),
}


# ── semântica do canônico (grupo 1 do §13) ───────────────────────────────────

def test_nxm_simples(exp_dags):
    """2 entradas × 2 saídas = 4 dependências reais em 4 arestas desenhadas —
    cada uma assinada com o id do nó (proveniência, Decisão 1)."""
    nos, arestas = CENARIOS["nxm"]
    r = exp_dags.expandir(nos, arestas)
    assert r["nos"][1]["upstream"] == {"A", "B"}
    assert r["nos"][1]["saidas_pipeline"] == {"C", "D"}
    assert r["dependencias"] == {
        ("C", "A", 1), ("C", "B", 1), ("D", "A", 1), ("D", "B", 1)}


def test_aguarde_encadeado_e_transitivo(exp_dags):
    """W1→W2: o upstream de W2 atravessa W1 até os PIPELINES (A) e soma a
    entrada direta (C) — barreiras encadeadas, mesmo espírito do Aguarde das
    Etapas (§5.5). B (saída de W1) NÃO entra: upstream anda para TRÁS."""
    nos, arestas = CENARIOS["encadeado"]
    r = exp_dags.expandir(nos, arestas)
    assert r["nos"][1]["upstream"] == {"A"}
    assert r["nos"][2]["upstream"] == {"A", "C"}
    assert r["dependencias"] == {
        ("B", "A", 1), ("D", "A", 2), ("D", "C", 2)}


def test_aguarde_sem_entrada_nao_compila_nada(exp_dags):
    nos, arestas = CENARIOS["sem_entrada"]
    r = exp_dags.expandir(nos, arestas)
    assert r["nos"][7]["upstream"] == set()
    assert r["nos"][7]["saidas_pipeline"] == {"X"}
    assert r["dependencias"] == set()


def test_no_isolado_tem_sets_vazios(exp_dags):
    nos, arestas = CENARIOS["isolado"]
    r = exp_dags.expandir(nos, arestas)
    assert r["nos"][3] == {"upstream": set(), "saidas_pipeline": set()}
    assert r["nos"][4] == {"upstream": set(), "saidas_pipeline": set()}
    assert r["dependencias"] == set()


def test_so_aguarde_compila_dependencia(exp_dags):
    """Início planta agendamento (F13) e Notificação/Fim observam (F14):
    upstream calculado para todos, dependência compilada para NENHUM deles."""
    nos, arestas = CENARIOS["observadores"]
    r = exp_dags.expandir(nos, arestas)
    assert r["nos"][2]["upstream"] == {"A"}
    assert r["nos"][3]["upstream"] == {"A", "B"}
    assert r["dependencias"] == set()


def test_ciclo_entre_nos_nao_pendura(exp_dags):
    """Desenho malformado com ciclo nó→nó (a API recusa no gesto — §3.3): o
    BFS com visitados global termina e devolve o upstream alcançável."""
    nos, arestas = CENARIOS["ciclo_malformado"]
    r = exp_dags.expandir(nos, arestas)
    assert r["nos"][1]["upstream"] == {"A"}
    assert r["nos"][2]["upstream"] == {"A"}
    assert r["dependencias"] == {("B", "A", 2)}


def test_grafia_e_do_chamador(exp_dags):
    """A expansão NÃO canoniza: quem chama grava a grafia registrada (PR #236)
    — 'a' e 'A' são pipelines distintos aqui, de propósito (a API nunca deixa
    os dois entrarem, mas a função pura não adivinha colação)."""
    r = exp_dags.expandir(
        [{"id": 1, "tipo": "aguarde"}],
        [_ar(origem_pipeline="a", destino_no=1),
         _ar(origem_pipeline="A", destino_no=1),
         _ar(origem_no=1, destino_pipeline="B")])
    assert r["nos"][1]["upstream"] == {"a", "A"}


# ── paridade port da API × canônico de dags (§3.2/§13) ───────────────────────

def test_paridade_expandir_matriz_identica(exp_dags):
    """A MESMA matriz de cenários nos dois módulos, resultado IDÊNTICO —
    divergir a semântica faz a suíte falhar antes de chegar em produção
    (precedente data_referencia/dependencias)."""
    for nome, (nos, arestas) in CENARIOS.items():
        r_api = exp_api.expandir(nos, arestas)
        r_dags = exp_dags.expandir(nos, arestas)
        assert r_api == r_dags, f"cenário '{nome}' divergiu entre api/ e dags/"


def test_paridade_docstring_declara_o_canonico():
    """O port declara quem manda: mudar a regra começa em dags/ (o mesmo
    contrato dos ports de data_referencia e dependencias)."""
    assert "dags/utils/malha_nos.py" in (exp_api.__doc__ or "")
    assert "canônico" in (exp_api.__doc__ or "")
