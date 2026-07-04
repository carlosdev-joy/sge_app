"""
Testes do script_create_table (DDL do destino do módulo Cópia de Dados) —
foco na regra de LARGURA das colunas com transformação pad_fixo/
pad_condicional (incidente 2026-07-04, DM_Clientes_contratos): o pad produz
strings de EXATAMENTE n chars, então a coluna de destino precisa nascer
VARCHAR(max(tamanhos do pad, largura ORIGINAL da coluna texto)) — a regra
antiga só alargava origem NUMÉRICA e uma origem VARCHAR(11) com
pad_condicional de 14 (CNPJ) nascia varchar(11) e estourava
"String data, right truncation" na carga.

Mesmo harness AST dos demais testes de cópia (sem importar pymssql/airflow);
a conexão de origem é um STUB de cursor que devolve o sys.columns fingido.
"""
from __future__ import annotations

import ast
import logging
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

_RAIZ = Path(__file__).parent.parent
_BULK_COPY = _RAIZ / "dags" / "utils" / "bulk_copy.py"

_NOMES = {"quote_ident", "_TIPOS_NUMERICOS", "_render_sql_type",
          "_COLLATION_RE", "_collate_sql", "script_create_table"}


def _extrair(path: Path, nomes: set) -> dict:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)  # SyntaxError se o arquivo estiver inválido
    keep = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name in nomes:
            keep.append(node)
        elif isinstance(node, ast.Assign):
            alvos = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if any(a in nomes for a in alvos):
                keep.append(node)
    achados = {n.name for n in keep if isinstance(n, ast.FunctionDef)} | {
        t.id for n in keep if isinstance(n, ast.Assign)
        for t in n.targets if isinstance(t, ast.Name)}
    faltando = nomes - achados
    assert not faltando, f"símbolos não encontrados em {path.name}: {faltando}"
    ns = {"re": re, "date": date, "datetime": datetime, "Decimal": Decimal,
          "log": logging.getLogger("test_copias_ddl")}
    mod = ast.Module(body=keep, type_ignores=[])
    exec(compile(mod, str(path), "exec"), ns)
    return ns


@pytest.fixture(scope="module")
def bc():
    return _extrair(_BULK_COPY, _NOMES)


class _CursorStub:
    """Cursor pymssql fingido: devolve as linhas do sys.columns da origem
    (name, tipo, max_length, precision, scale, is_nullable, collation)."""

    def __init__(self, linhas):
        self._linhas = linhas

    def execute(self, *_a, **_k):
        pass

    def fetchall(self):
        return self._linhas

    def close(self):
        pass


class _ConnStub:
    def __init__(self, linhas):
        self._linhas = linhas

    def cursor(self):
        return _CursorStub(self._linhas)


_PAD_CNPJ = {"tipo": "pad_condicional", "campo_condicao": "tipo_pessoa",
             "casos": [{"valor": "J", "tamanho": 14},
                       {"valor": "F", "tamanho": 11}]}


def _ddl(bc, linhas, dst_columns, transforms):
    return bc["script_create_table"](
        _ConnStub(linhas), "DB_A", "dbo", "origem",
        dst_columns, transforms, dst_schema="dbo", dst_table="destino")


def test_pad_sobre_origem_varchar_alarga_para_o_maior_caso(bc):
    # Incidente 2026-07-04: origem varchar(11) + pad_condicional 14 (CNPJ)
    # nascia varchar(11) → truncation na carga. Agora: VARCHAR(14).
    ddl = _ddl(bc, [("num_cpf_cnpj", "varchar", 11, 0, 0, True, None)],
               ["num_cpf_cnpj"],
               [{"origem": "num_cpf_cnpj", "transform": _PAD_CNPJ}])
    assert "[num_cpf_cnpj] VARCHAR(14) NULL" in ddl


def test_pad_menor_que_a_origem_nao_encolhe(bc):
    # pad de 5 sobre varchar(30): valores sem pad continuam passando — a
    # largura NUNCA encolhe abaixo da original.
    ddl = _ddl(bc, [("codigo", "varchar", 30, 0, 0, False, None)], ["codigo"],
               [{"origem": "codigo",
                 "transform": {"tipo": "pad_fixo", "tamanho": 5}}])
    assert "[codigo] VARCHAR(30) NOT NULL" in ddl


def test_pad_sobre_nvarchar_usa_largura_em_chars(bc):
    # max_length de N* é em BYTES (2×chars): nvarchar(12) = 24 bytes.
    ddl = _ddl(bc, [("doc", "nvarchar", 24, 0, 0, True, None)], ["doc"],
               [{"origem": "doc",
                 "transform": {"tipo": "pad_fixo", "tamanho": 11}}])
    assert "[doc] VARCHAR(12) NULL" in ddl


def test_pad_sobre_numerico_mantem_regra_original(bc):
    ddl = _ddl(bc, [("cpf", "bigint", 8, 19, 0, True, None)], ["cpf"],
               [{"origem": "cpf", "transform": _PAD_CNPJ}])
    assert "[cpf] VARCHAR(14) NULL" in ddl


def test_pad_sobre_varchar_max_mantem_o_tipo(bc):
    # (n)varchar(max) (max_length = -1) já comporta o pad — fica como está.
    ddl = _ddl(bc, [("obs", "varchar", -1, 0, 0, True, None)], ["obs"],
               [{"origem": "obs",
                 "transform": {"tipo": "pad_fixo", "tamanho": 14}}])
    assert "[obs] VARCHAR(MAX) NULL" in ddl


def test_sem_transform_preserva_tipo_original(bc):
    ddl = _ddl(bc, [("nome", "varchar", 80, 0, 0, True, None),
                    ("idade", "int", 4, 10, 0, False, None)],
               ["nome", "idade"], [])
    assert "[nome] VARCHAR(80) NULL" in ddl
    assert "[idade] INT NOT NULL" in ddl


def test_collation_da_origem_preservada(bc):
    # Réplica FIEL: coluna texto nasce com a COLLATION da origem (sem isso
    # ela ganha a collation default do BANCO de destino).
    ddl = _ddl(bc, [("nome", "varchar", 80, 0, 0, True,
                     "SQL_Latin1_General_CP1_CI_AS"),
                    ("idade", "int", 4, 10, 0, False, None)],
               ["nome", "idade"], [])
    assert ("[nome] VARCHAR(80) COLLATE SQL_Latin1_General_CP1_CI_AS NULL"
            in ddl)
    assert "[idade] INT NOT NULL" in ddl          # sem COLLATE em não-texto


def test_collation_mantida_na_coluna_alargada_pelo_pad(bc):
    ddl = _ddl(bc, [("num_cpf_cnpj", "varchar", 11, 0, 0, True,
                     "Latin1_General_CI_AI")],
               ["num_cpf_cnpj"],
               [{"origem": "num_cpf_cnpj", "transform": _PAD_CNPJ}])
    assert ("[num_cpf_cnpj] VARCHAR(14) COLLATE Latin1_General_CI_AI NULL"
            in ddl)


def test_collate_sql_guarda_de_identificador(bc):
    assert bc["_collate_sql"]("Latin1_General_BIN2") == \
        " COLLATE Latin1_General_BIN2"
    assert bc["_collate_sql"](None) == ""
    assert bc["_collate_sql"]("") == ""
    # nome fora do padrão de identificador nunca vai para o DDL
    assert bc["_collate_sql"]("x; DROP TABLE t") == ""
