"""
Testes da correção do incidente 2026-07-04 do módulo Cópia de Dados
(engine bcp_native "concluiu" com 0 linha copiada e 1M na origem — os dois
processos bcp saíram com exit 0 sem mover dado nenhum):

  - total_nas_mensagens: total final ("N rows copied.") nas mensagens de UM
    processo bcp (None quando o resumo não apareceu);
  - copiar_faixa_bcp (INTEGRAÇÃO com bcp FALSO): a RECONCILIAÇÃO leitor ×
    escritor — exit 0 nas duas pontas NÃO basta; o total exportado pelo
    queryout tem que bater com o gravado pelo ``bcp in`` (divergência ou
    resumo ausente → faixa 'erro' com as caudas das mensagens);
  - _classificar_desfecho: defesa em profundidade no nível da EXECUÇÃO —
    nenhuma faixa falhou mas ZERO linha fluiu com rows_total > 0 → 'erro'
    (origem legitimamente vazia segue 'concluido').

Mesmo harness do test_copias_bcp.py: os módulos das DAGs importam
pymssql/airflow (indisponíveis aqui), então as funções são EXTRAÍDAS por AST
e compiladas num namespace controlado. O teste de integração roda o
copiar_faixa_bcp REAL (os.pipe + subprocess) contra um script que imita o
protocolo de mensagens do bcp — valida também o plumbing /dev/fd/N.
"""
from __future__ import annotations

import ast
import logging
import os
import re
import stat
import subprocess
import threading
import types
from collections import deque
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

_RAIZ = Path(__file__).parent.parent
_BULK_COPY = _RAIZ / "dags" / "utils" / "bulk_copy.py"
_COPY_EXEC = _RAIZ / "dags" / "etl_copy_exec.py"

_NOMES_BULK = {
    "_BCP_LOTE_RE", "_BCP_TOTAL_RE",
    "quote_ident", "redigir_cmd", "_redigir_texto",
    "montar_cmd_bcp_queryout", "montar_cmd_bcp_in",
    "parse_progresso_bcp", "total_nas_mensagens",
    "_conn_params", "_drenar_stream", "copiar_faixa_bcp",
}

_NOMES_EXEC = {"_classificar_desfecho"}


def _extrair(path: Path, nomes: set, ns_extra: dict | None = None) -> dict:
    """Compila apenas os símbolos pedidos do módulo (sem importar
    pymssql/airflow). Sanidade extra: ast.parse do ARQUIVO INTEIRO."""
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
    ns = {"re": re, "os": os, "subprocess": subprocess,
          "threading": threading, "deque": deque,
          "date": date, "datetime": datetime, "Decimal": Decimal,
          "log": logging.getLogger("test_copias_bcp_reconciliacao")}
    ns.update(ns_extra or {})
    mod = ast.Module(body=keep, type_ignores=[])
    exec(compile(mod, str(path), "exec"), ns)
    return ns


@pytest.fixture(scope="module")
def bc():
    """Namespace com as funções do engine bcp do bulk_copy.py."""
    return _extrair(_BULK_COPY, _NOMES_BULK)


@pytest.fixture(scope="module")
def classificar():
    """_classificar_desfecho do etl_copy_exec.py (função PURA)."""
    return _extrair(_COPY_EXEC, _NOMES_EXEC)["_classificar_desfecho"]


# ═════════════════════ total_nas_mensagens (função pura) ════════════════════

def test_total_nas_mensagens_resumo_presente(bc):
    linhas = ["Starting copy...",
              "1000 rows successfully bulk-copied to host-file. Total received: 1000",
              "1234567 rows copied.",
              "Network packet size (bytes): 4096",
              "Clock Time (ms.) Total     : 5000   Average : (246913.4 rows per sec.)"]
    assert bc["total_nas_mensagens"](linhas) == 1234567


def test_total_nas_mensagens_zero_e_ultimo_vence(bc):
    assert bc["total_nas_mensagens"](["0 rows copied."]) == 0
    # resumo repetido (não deveria acontecer, mas o ÚLTIMO é o que vale)
    assert bc["total_nas_mensagens"](
        ["5 rows copied.", "7 rows copied."]) == 7


def test_total_nas_mensagens_ausente_eh_none(bc):
    assert bc["total_nas_mensagens"](["Starting copy...", "banner"]) is None
    assert bc["total_nas_mensagens"]([]) is None
    assert bc["total_nas_mensagens"](None) is None


# ══════════════ copiar_faixa_bcp — integração com bcp FALSO ═════════════════
#
# O script abaixo imita o PROTOCOLO do bcp real: o leitor ("queryout") grava
# 1 byte por "linha" no datafile (/dev/fd/N do pipe) e imprime o resumo
# "N rows copied."; o escritor ("in") lê o stdin até EOF e imprime progresso
# ("N rows sent to SQL Server. Total sent: N") + resumo. Env vars controlam
# quantas linhas cada ponta REPORTA — é o que permite simular o incidente
# (dados não fluem mas ambos saem 0).

_FAKE_BCP = """#!/usr/bin/env python3
import os, sys

modo, datafile = sys.argv[2], sys.argv[3]
if modo == "queryout":
    n = int(os.environ.get("FAKE_BCP_LEITOR_LINHAS", "0"))
    with open(datafile, "wb") as f:
        f.write(b"X" * n)
    if os.environ.get("FAKE_BCP_LEITOR_SEM_RESUMO") != "1":
        print(f"{n} rows copied.")
    print("Clock Time (ms.) Total     : 1")
    sys.exit(int(os.environ.get("FAKE_BCP_LEITOR_EXIT", "0")))
else:  # "in"
    lidas = len(sys.stdin.buffer.read())
    rep = os.environ.get("FAKE_BCP_ESCRITOR_LINHAS")
    n = int(rep) if rep is not None else lidas
    if n:
        print(f"{n} rows sent to SQL Server. Total sent: {n}")
    print(f"{n} rows copied.")
    sys.exit(int(os.environ.get("FAKE_BCP_ESCRITOR_EXIT", "0")))
"""

_ENVS_FAKE = ("FAKE_BCP_LEITOR_LINHAS", "FAKE_BCP_LEITOR_SEM_RESUMO",
              "FAKE_BCP_LEITOR_EXIT", "FAKE_BCP_ESCRITOR_LINHAS",
              "FAKE_BCP_ESCRITOR_EXIT")


@pytest.fixture()
def faixa_bcp(bc, tmp_path, monkeypatch):
    """Executor de UMA faixa contra o bcp falso: ``run(**envs)`` → resultado
    de copiar_faixa_bcp + lista de deltas do on_lote."""
    fake = tmp_path / "bcp"
    fake.write_text(_FAKE_BCP, encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    conn = types.SimpleNamespace(host="srv", port=1433,
                                 login="usr", password="s3nh4!")

    def run(**envs):
        for e in _ENVS_FAKE:
            monkeypatch.delenv(e, raising=False)
        for e, v in envs.items():
            monkeypatch.setenv(e, str(v))
        deltas = []
        r = bc["copiar_faixa_bcp"](
            {"path": str(fake), "flags": {"-u"}}, "SELECT * FROM t",
            conn, "SRC_DB", conn, "DST_DB", "dbo", "destino", 50000,
            on_lote=deltas.append)
        return r, deltas

    return run


def test_faixa_bcp_reconciliada_conclui(faixa_bcp):
    r, deltas = faixa_bcp(FAKE_BCP_LEITOR_LINHAS=5)
    assert r["status"] == "concluido"
    assert r["rows"] == 5
    assert r["erro_msg"] is None
    assert deltas == [5]  # progresso por lote chegou ao on_lote


def test_faixa_bcp_origem_vazia_conclui_com_zero(faixa_bcp):
    # 0 == 0 é reconciliação VÁLIDA (faixa/origem legitimamente vazia) —
    # o caso "zero geral com rows_total > 0" é pego no nível da execução
    # (_classificar_desfecho), não da faixa.
    r, _ = faixa_bcp(FAKE_BCP_LEITOR_LINHAS=0)
    assert r["status"] == "concluido"
    assert r["rows"] == 0


def test_faixa_bcp_divergencia_eh_erro(faixa_bcp):
    # Incidente 2026-07-04: exit 0 nas duas pontas mas os dados não fluíram
    # (leitor exportou 5, escritor gravou 0) → NUNCA mais "concluído".
    r, _ = faixa_bcp(FAKE_BCP_LEITOR_LINHAS=5, FAKE_BCP_ESCRITOR_LINHAS=0)
    assert r["status"] == "erro"
    assert r["rows"] == 0
    assert "totais divergem" in r["erro_msg"]
    assert "leitor exportou 5" in r["erro_msg"]
    assert "gravou 0" in r["erro_msg"]
    # diagnóstico: a cauda das mensagens do leitor vai na mensagem
    assert "rows copied" in r["erro_msg"]


def test_faixa_bcp_resumo_ausente_eh_erro(faixa_bcp):
    # Leitor sem "N rows copied." (morto/mudo) → não há prova de exportação.
    r, _ = faixa_bcp(FAKE_BCP_LEITOR_LINHAS=0, FAKE_BCP_LEITOR_SEM_RESUMO=1)
    assert r["status"] == "erro"
    assert "resumo ausente" in r["erro_msg"]


def test_faixa_bcp_erro_mantem_senha_redigida(faixa_bcp):
    r, _ = faixa_bcp(FAKE_BCP_LEITOR_LINHAS=5, FAKE_BCP_ESCRITOR_LINHAS=0)
    assert "s3nh4!" not in (r["erro_msg"] or "")


def test_faixa_bcp_exit_nao_zero_segue_erro(faixa_bcp):
    # regressão: o caminho de falha por exit code continua intacto
    r, _ = faixa_bcp(FAKE_BCP_LEITOR_LINHAS=5, FAKE_BCP_LEITOR_EXIT=1)
    assert r["status"] == "erro"
    assert "bcp queryout exit 1" in r["erro_msg"]


# ═══════════ _classificar_desfecho — defesa no nível da execução ════════════

def _faixa(status, rows, erro=None):
    return {"range_index": 1, "status": status, "rows": rows,
            "erro_msg": erro}


def test_desfecho_concluido_normal(classificar):
    st, msg = classificar([_faixa("concluido", 500), _faixa("concluido", 500)],
                          1000)
    assert (st, msg) == ("concluido", None)


def test_desfecho_zero_linhas_com_origem_populada_eh_erro(classificar):
    # Incidente 2026-07-04: todas as faixas "concluíram" com 0 linha e
    # rows_total=1_000_000 → a execução NÃO pode terminar 'concluido'.
    st, msg = classificar([_faixa("concluido", 0)], 1_000_000)
    assert st == "erro"
    assert "nenhuma linha copiada" in msg
    assert "1000000" in msg


def test_desfecho_origem_vazia_segue_concluido(classificar):
    assert classificar([_faixa("concluido", 0)], 0) == ("concluido", None)
    assert classificar([_faixa("concluido", 0)], None) == ("concluido", None)


def test_desfecho_erro_tem_precedencia(classificar):
    st, msg = classificar(
        [_faixa("concluido", 10), _faixa("erro", 0, "boom")], 100)
    assert (st, msg) == ("erro", "boom")


def test_desfecho_erro_sem_mensagem_ganha_generica(classificar):
    st, msg = classificar([_faixa("erro", 0)], 100)
    assert (st, msg) == ("erro", "erro na cópia")


def test_desfecho_cancelado(classificar):
    st, msg = classificar(
        [_faixa("concluido", 10), _faixa("cancelado", 5)], 100)
    assert (st, msg) == ("cancelado", None)


def test_desfecho_rows_none_tratado_como_zero(classificar):
    st, _ = classificar([_faixa("concluido", None)], 100)
    assert st == "erro"


# ═══════════════════════════ sanidade dos módulos ═══════════════════════════

def test_dags_tocadas_compilam():
    for p in (_BULK_COPY, _COPY_EXEC):
        ast.parse(p.read_text(encoding="utf-8"))
