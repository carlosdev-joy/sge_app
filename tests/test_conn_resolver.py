"""
Testes do ConexaoOrquestra (dags/utils/conn_resolver.py — incidente 2026-07-04).

A resolução de conexão nativa construía ``airflow.models.Connection`` com
``password=``, o que aciona o Fernet INTERNO do Airflow
(AIRFLOW__CORE__FERNET_KEY) — uma chave core malformada no .env derrubava a
introspecção/cópia de TODA conexão nativa, mesmo com a ORQUESTRA_CONN_KEY
correta. O fix devolve ``ConexaoOrquestra``: objeto leve com a MESMA
interface de atributos que as DAGs usam, sem tocar no ORM/Fernet do Airflow.

Harness AST (o módulo importa airflow, indisponível aqui) — mesmo padrão de
test_copias_server_side.py, com suporte a ClassDef.
"""
from __future__ import annotations

import ast
import logging
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import json
import pytest

_RAIZ = Path(__file__).parent.parent
_CONN_RESOLVER = _RAIZ / "dags" / "utils" / "conn_resolver.py"

_NOMES = {"ConexaoOrquestra"}


def _extrair(path: Path, nomes: set, ns_extra: dict | None = None) -> dict:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)  # SyntaxError se o arquivo estiver inválido
    keep = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)) and node.name in nomes:
            keep.append(node)
        elif isinstance(node, ast.Assign):
            alvos = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if any(a in nomes for a in alvos):
                keep.append(node)
    achados = {n.name for n in keep
               if isinstance(n, (ast.FunctionDef, ast.ClassDef))} | {
        t.id for n in keep if isinstance(n, ast.Assign)
        for t in n.targets if isinstance(t, ast.Name)}
    faltando = nomes - achados
    assert not faltando, f"símbolos não encontrados em {path.name}: {faltando}"
    ns = {"re": re, "date": date, "datetime": datetime, "Decimal": Decimal,
          "json": json, "log": logging.getLogger("test_conn_resolver")}
    ns.update(ns_extra or {})
    mod = ast.Module(body=keep, type_ignores=[])
    exec(compile(mod, str(path), "exec"), ns)
    return ns


@pytest.fixture(scope="module")
def Conexao():
    return _extrair(_CONN_RESOLVER, _NOMES)["ConexaoOrquestra"]


def test_atributos_da_interface_de_connection(Conexao):
    """A interface que as DAGs consomem: _conn_params (host/port/login/
    password) e charset_da_conexao (extra_dejson)."""
    c = Conexao("SQL69", "sql69.cvp", 1433, "usr_etl", "s3cr3t",
                extra='{"charset": "CP1252"}')
    assert (c.host, c.port, c.login, c.password) == \
        ("sql69.cvp", 1433, "usr_etl", "s3cr3t")
    assert c.conn_id == "SQL69" and c.conn_type == "mssql"
    assert c.extra_dejson == {"charset": "CP1252"}
    assert c.extra_dejson.get("charset") == "CP1252"


def test_extra_dejson_tolerante(Conexao):
    """Mesmo contrato de charset_da_conexao: vazio/None/ilegível → {}."""
    assert Conexao("C", "h", None, "u", "p").extra_dejson == {}
    assert Conexao("C", "h", None, "u", "p", extra="").extra_dejson == {}
    assert Conexao("C", "h", None, "u", "p", extra="{lixo").extra_dejson == {}


def test_repr_nunca_expoe_a_senha(Conexao):
    c = Conexao("SQL69", "sql69.cvp", 1433, "usr_etl", "s3nh4-secreta!")
    assert "s3nh4-secreta!" not in repr(c)
    assert "s3nh4-secreta!" not in str(c)
    assert "SQL69" in repr(c) and "sql69.cvp" in repr(c)


def test_nao_importa_o_orm_connection():
    """Guarda de regressão do incidente: o módulo NÃO pode voltar a importar
    airflow.models.connection.Connection (o setter de password dele aciona o
    Fernet core do Airflow)."""
    src = _CONN_RESOLVER.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module != "airflow.models.connection", \
                "conn_resolver voltou a importar o ORM Connection do Airflow"
        if isinstance(node, ast.Import):
            assert not any(a.name.startswith("airflow.models.connection")
                           for a in node.names)
