"""
Paridade D29 — o painel usa o MESMO predicado do motor (F5 da retomada).

Dois níveis, mais exigentes que o precedente da F9 (data_referencia) porque
aqui há SQL:

  1. PARIDADE DE PREDICADO: o SQL emitido por api/services/dependencias
     (pyodbc, ?) tem de ser TEXTUALMENTE idêntico ao do canônico
     dags/utils/dependencias (pymssql, %s), normalizado whitespace e
     placeholder — divergir o SELECT quebra a suíte antes de produção.

  2. PARIDADE DE SEMÂNTICA: a matriz D14/D20/D21 executada contra um dublê de
     banco que AVALIA o predicado de verdade (estilo F9), nas duas árvores,
     com o MESMO resultado.

Mais o teste de AUSÊNCIA estrutural que o D15 consagrou: nenhum
COALESCE(inicio, criado_em) e nenhum ORDER BY criado_em no fonte do port nem
no router que o consome — foi exatamente esse SQL que fez o endpoint da 1ª F5
divergir do motor (B2/D14/D15/N9).
"""
from __future__ import annotations

import importlib.util
import os
import sys
from datetime import date
from datetime import datetime as _DT
from pathlib import Path
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from services import dependencias as deps_api

_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def deps_dags():
    """Canônico de dags/, carregado por caminho (técnica de test_malhas_f9)."""
    spec = importlib.util.spec_from_file_location(
        "dependencias_dags_f5", _ROOT / "dags/utils/dependencias.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── dublês ───────────────────────────────────────────────────────────────────

class CurCaptura:
    """Captura (sql, params) sem responder nada — nível 1 (texto).

    `falhar_em` = {índice da chamada: mensagem} força a exceção do deploy
    parcial na enésima tentativa, para a CASCATA ser comparada entre as
    árvores como o SQL feliz já é."""

    def __init__(self):
        self.chamadas: list[tuple] = []
        self.falhar_em: dict = {}

    def execute(self, sql, params=()):
        n = len(self.chamadas)
        self.chamadas.append((str(sql), tuple(params)))
        if n in self.falhar_em:
            raise RuntimeError(self.falhar_em[n])

    def fetchall(self):
        return []

    def fetchone(self):
        return None


class ConnCaptura:
    def __init__(self):
        self.cur = CurCaptura()

    def cursor(self):
        return self.cur


def _norm(sql: str) -> str:
    return " ".join(str(sql).split()).replace("%s", "?")


class BancoDuble:
    """Dublê que AVALIA o predicado EXISTS de verdade — nível 2 (semântica).

    dependencias: {pipeline: [predecessores]}
    execucoes: [(pipeline, data_referencia, status)] ou
               [(pipeline, data_referencia, status, substituida)] — a 4ª
               posição (opcional) é o carimbo da 078, e o dublê só a respeita
               quando o SQL EMITIDO filtra por ela: é assim que o teste
               distingue "as duas árvores filtram" de "o dublê filtrou por
               elas".
    quebrar=True simula banco indisponível (D21).
    """

    def __init__(self, dependencias, execucoes, quebrar=False):
        self.dependencias = dependencias
        self.execucoes = execucoes
        self.quebrar = quebrar

    def cursor(self):
        return CurDuble(self)


class CurDuble:
    def __init__(self, db):
        self.db = db
        self._rows: list[tuple] = []

    def execute(self, sql, params=()):
        if self.db.quebrar:
            raise RuntimeError("banco fora do ar")
        s = " ".join(str(sql).split())
        assert "NOT EXISTS" in s and "'SUCESSO'" in s, f"SQL fora do contrato: {s}"
        filtra_substituida = "substituida_em IS NULL" in s
        pipeline, data_ref = params
        falt = []
        for pred in self.db.dependencias.get(pipeline, []):
            tem_sucesso = False
            for linha in self.db.execucoes:
                p, d, st = linha[0], linha[1], linha[2]
                substituida = bool(linha[3]) if len(linha) > 3 else False
                if p == pred and d == data_ref and st == "SUCESSO" \
                        and not (substituida and filtra_substituida):
                    tem_sucesso = True
            if not tem_sucesso:
                falt.append((pred,))
        self._rows = falt

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


_D = date(2026, 8, 1)
_ONTEM = date(2026, 7, 31)


def _liberado_nas_duas_arvores(deps_dags, dependencias, execucoes):
    """Roda o MESMO cenário contra os dois módulos e exige o MESMO resultado."""
    duble_dags = BancoDuble(dependencias, execucoes)
    r_dags = deps_dags.liberado(duble_dags, "PIPE_C", _D)
    duble_api = BancoDuble(dependencias, execucoes)
    r_api = deps_api.liberado(duble_api.cursor(), "PIPE_C", _D)
    assert r_dags == r_api, (r_dags, r_api)
    return r_api


# ── nível 1: SQL idêntico ────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _modo_data(deps_dags):
    """Modo DATA nas duas árvores, sem gastar consulta (o cache preenchido faz
    `modo_sequencia` nem perguntar). A paridade do modo SEQUÊNCIA tem teste
    próprio abaixo."""
    deps_dags._MODO_CACHE["modo"] = False
    deps_api._MODO_CACHE.update({"modo": False, "ate": float("inf")})
    yield
    deps_dags.limpar_cache_modo()
    deps_api.limpar_cache_modo()


def test_paridade_sql_do_modo_sequencia(deps_dags):
    """O SQL do modo SEQUÊNCIA também tem de ser o MESMO nas duas árvores —
    senão o painel diria uma coisa e o motor faria outra, que é a doença que
    a paridade existe para impedir. Os DOIS degraus do modo (F6)."""
    for nome in ("SQL_LIBERADO_SEQ_084", "SQL_LIBERADO_SEQ_085"):
        assert _norm(getattr(deps_dags, nome).replace("%s", "?")) \
            == _norm(getattr(deps_api, nome)), nome


def _liga_sequencia(deps_dags, monkeypatch):
    """Modo SEQUÊNCIA ligado nas DUAS árvores, com o MESMO corte de janela.

    O corte é fixado porque ele sai de `GETDATE()` em cada árvore: deixá-lo
    livre faria a paridade de PARÂMETROS falhar por microssegundos e esconderia
    a divergência que este teste procura."""
    corte = _DT(2026, 8, 4, 13, 0)
    deps_dags.limpar_cache_modo()
    deps_api.limpar_cache_modo()
    deps_dags._MODO_CACHE["modo"] = True
    deps_api._MODO_CACHE.update({"modo": True, "ate": float("inf")})
    monkeypatch.setattr(deps_dags, "inicio_do_ciclo_corrente", lambda _c: corte)
    monkeypatch.setattr(deps_api, "inicio_do_ciclo_corrente", lambda _c: corte)
    return corte


def test_paridade_do_corte_em_tres_degraus(deps_dags, monkeypatch):
    """F6 — o corte da §8 emitido DE VERDADE pelas duas árvores: mesmo texto e
    MESMOS parâmetros, na mesma ordem (pipeline, corrida, janela).

    É o degrau mais alto do predicado canônico e ele decide DISPARO: se o motor
    cortasse pelo `aberta_em` da corrida e o painel pela janela de 12h, a tela
    diria "aguardando" para um filho já solto (ou o contrário) exatamente nas
    horas em que alguém está olhando para ela."""
    corte = _liga_sequencia(deps_dags, monkeypatch)
    try:
        conn = ConnCaptura()
        deps_dags.liberado(conn, "PIPE_C", _D, 77)
        cur = CurCaptura()
        deps_api.liberado(cur, "PIPE_C", _D, 77)
        assert len(conn.cur.chamadas) == 1 and len(cur.chamadas) == 1
        sql_dags, params_dags = conn.cur.chamadas[0]
        sql_api, params_api = cur.chamadas[0]
        assert _norm(sql_dags) == _norm(sql_api)
        assert params_dags == params_api == ("PIPE_C", 77, corte)
    finally:
        deps_dags.limpar_cache_modo()
        deps_api.limpar_cache_modo()


def test_paridade_da_cascata_sem_a_085(deps_dags, monkeypatch):
    """A DEGRADAÇÃO também tem de ser gêmea: com a 085 ausente, as duas árvores
    caem no MESMO degrau, com o MESMO SQL e os MESMOS parâmetros. Uma cascata
    que divergisse faria o painel e o motor discordarem justamente no deploy
    parcial — o momento em que a divergência é mais cara de diagnosticar."""
    corte = _liga_sequencia(deps_dags, monkeypatch)
    try:
        conn = ConnCaptura()
        conn.cur.falhar_em = {0: "Invalid object name 'dbo.etl_malha_execucao'."}
        deps_dags.liberado(conn, "PIPE_C", _D, 77)
        cur = CurCaptura()
        cur.falhar_em = {0: "Invalid object name 'dbo.etl_malha_execucao'."}
        deps_api.liberado(cur, "PIPE_C", _D, 77)
        assert len(conn.cur.chamadas) == len(cur.chamadas) == 2
        for (s_dags, p_dags), (s_api, p_api) in zip(conn.cur.chamadas,
                                                    cur.chamadas):
            assert _norm(s_dags) == _norm(s_api)
            assert p_dags == p_api
        # e o degrau em que pararam é o SEQ_084 — não a volta para a data
        assert "data_referencia" not in conn.cur.chamadas[1][0]
        assert conn.cur.chamadas[1][1] == ("PIPE_C", corte)
    finally:
        deps_dags.limpar_cache_modo()
        deps_api.limpar_cache_modo()


def test_paridade_sql_liberado(deps_dags):
    conn = ConnCaptura()
    deps_dags.liberado(conn, "PIPE_C", _D)
    cur = CurCaptura()
    deps_api.liberado(cur, "PIPE_C", _D)
    assert len(conn.cur.chamadas) == 1 and len(cur.chamadas) == 1
    sql_dags, params_dags = conn.cur.chamadas[0]
    sql_api, params_api = cur.chamadas[0]
    assert _norm(sql_dags) == _norm(sql_api)
    assert params_dags == params_api == ("PIPE_C", _D)


def test_paridade_sql_resumo_predecessores(deps_dags):
    conn = ConnCaptura()
    deps_dags.resumo_predecessores(conn, "PIPE_C", _D)
    cur = CurCaptura()
    deps_api.resumo_predecessores(cur, "PIPE_C", _D)
    sql_dags, params_dags = conn.cur.chamadas[0]
    sql_api, params_api = cur.chamadas[0]
    assert _norm(sql_dags) == _norm(sql_api)
    assert params_dags == params_api == (_D, "PIPE_C")


def test_sentinel_de_erro_identico(deps_dags):
    assert deps_api.ERRO_CONSULTA == deps_dags.ERRO_CONSULTA


# ── nível 2: matriz semântica D14/D20/D21 nas duas árvores ──────────────────

_GRAFO = {"PIPE_C": ["PAI_A", "PAI_B"]}


def test_todas_sucesso_libera(deps_dags):
    lib, falt = _liberado_nas_duas_arvores(deps_dags, _GRAFO, [
        ("PAI_A", _D, "SUCESSO"), ("PAI_B", _D, "SUCESSO")])
    assert lib is True and falt == []


def test_uma_falta_nao_libera(deps_dags):
    lib, falt = _liberado_nas_duas_arvores(deps_dags, _GRAFO, [
        ("PAI_A", _D, "SUCESSO")])
    assert lib is False and falt == ["PAI_B"]


def test_falha_nao_libera(deps_dags):
    lib, falt = _liberado_nas_duas_arvores(deps_dags, _GRAFO, [
        ("PAI_A", _D, "SUCESSO"), ("PAI_B", _D, "FALHA")])
    assert lib is False and falt == ["PAI_B"]


def test_pulado_intercalado_nao_mascara_sucesso(deps_dags):
    """D14/B2 — o caso que o endpoint da 1ª F5 errava: PULADO mais recente
    junto de um SUCESSO na data LIBERA (EXISTS, não 'mais recente')."""
    lib, falt = _liberado_nas_duas_arvores(deps_dags, _GRAFO, [
        ("PAI_A", _D, "SUCESSO"), ("PAI_A", _D, "PULADO"),
        ("PAI_B", _D, "PULADO"), ("PAI_B", _D, "SUCESSO"),
        ("PAI_B", _D, "PULADO")])
    assert lib is True and falt == []


def test_sucesso_em_outra_data_nao_libera(deps_dags):
    """D20: SUCESSO de ontem não conta para o ciclo de hoje."""
    lib, falt = _liberado_nas_duas_arvores(deps_dags, _GRAFO, [
        ("PAI_A", _ONTEM, "SUCESSO"), ("PAI_B", _D, "SUCESSO")])
    assert lib is False and falt == ["PAI_A"]


def test_corrida_substituida_nao_libera_nas_duas_arvores(deps_dags):
    """A terceira porta, com paridade: a corrida APOSENTADA por um rerun com
    cascata não conta como SUCESSO — nem para o motor, nem para o painel.

    Com o dependente reaberto, o painel tem de dizer "aguardando o
    predecessor" enquanto o motor ainda não libera; se só o motor filtrasse,
    a tela ficaria mostrando 'liberado' para uma corrida que não vai sair —
    a divergência painel×motor que a F5 existe para não repetir."""
    lib, falt = _liberado_nas_duas_arvores(deps_dags, _GRAFO, [
        ("PAI_A", _D, "SUCESSO", False),
        ("PAI_B", _D, "SUCESSO", True)])          # aposentada pelo rerun
    assert lib is False and falt == ["PAI_B"]


def test_sucesso_novo_ao_lado_da_substituida_libera_nas_duas_arvores(deps_dags):
    """E o outro lado: assim que o predecessor reexecuta e publica, o SUCESSO
    NOVO libera — a linha aposentada continua na tabela, e não atrapalha."""
    lib, falt = _liberado_nas_duas_arvores(deps_dags, _GRAFO, [
        ("PAI_A", _D, "SUCESSO", False),
        ("PAI_B", _D, "SUCESSO", True),
        ("PAI_B", _D, "SUCESSO", False)])
    assert lib is True and falt == []


def test_erro_de_consulta_nao_libera_nas_duas_arvores(deps_dags):
    """D21: exceção → NÃO liberado, com o sentinel nos faltantes — nos dois."""
    duble = BancoDuble(_GRAFO, [], quebrar=True)
    lib_dags, falt_dags = deps_dags.liberado(duble, "PIPE_C", _D)
    lib_api, falt_api = deps_api.liberado(duble.cursor(), "PIPE_C", _D)
    assert lib_dags is False and lib_api is False
    assert falt_dags[0].startswith(deps_dags.ERRO_CONSULTA)
    assert falt_api[0].startswith(deps_api.ERRO_CONSULTA)


# ── ausência estrutural (D15) ────────────────────────────────────────────────

def test_nenhum_coalesce_ou_order_by_no_sql_do_port():
    """O SQL DE FATO EMITIDO pelo port não tem COALESCE, criado_em nem ORDER
    BY — a captura olha o que vai ao banco, não comentário/docstring."""
    cur = CurCaptura()
    deps_api.faltantes(cur, "P", _D)
    deps_api.resumo_predecessores(cur, "P", _D)
    deps_api.virada_global(cur)
    deps_api.tabela_067(cur)
    sqls = " ".join(s for s, _ in cur.chamadas)
    assert "COALESCE" not in sqls.upper()
    assert "criado_em" not in sqls
    assert "ORDER BY" not in sqls.upper()


def test_nenhum_coalesce_ou_order_by_criado_em_no_router():
    """O endpoint /estado (e o router inteiro) não reintroduz a ordenação
    proibida — foi o SQL exato do endpoint revertido da 1ª F5."""
    fonte = (_ROOT / "api/routers/pipelines.py").read_text(encoding="utf-8")
    assert "COALESCE(inicio" not in fonte
    assert "ORDER BY criado_em" not in fonte
    assert "ORDER BY COALESCE" not in fonte


def test_estado_usa_exclusivamente_o_port():
    """O router não tem SELECT próprio com o predicado (NOT EXISTS sobre
    etl_pipeline_execucao): a pergunta de liberação sai SÓ de
    services.dependencias (Decisão 4)."""
    fonte = (_ROOT / "api/routers/pipelines.py").read_text(encoding="utf-8")
    assert "NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao" not in fonte
    assert "deps_svc.liberado" in fonte
