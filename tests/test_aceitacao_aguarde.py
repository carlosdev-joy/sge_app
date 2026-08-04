"""
Aceitação do AGUARDE — os três invariantes que o usuário exigiu depois do
incidente da malha Carga_Vida (2026-08-04):

  A. o Aguarde só libera quando TODOS os predecessores estão FINALIZADOS com
     sucesso — nada de liberar com alguém ainda rodando;
  B. a data é validada ANTES de a execução começar;
  C. datas diferentes entre os predecessores BLOQUEIAM.

Por que este arquivo existe, se já há testes de cada peça: os outros provam o
SQL emitido e a orquestração; aqui se pergunta o que o operador pergunta —
"com ESTAS linhas na tabela, o Aguarde libera?". O dublê do banco interpreta as
linhas de `etl_pipeline_execucao` em vez de devolver resultado pronto, então um
predicado que mudasse de semântica reprovaria aqui mesmo continuando a emitir
um SQL bem formado.

A tradução do `NOT EXISTS` feita pelo dublê (§_Cur.execute) foi conferida
contra o SQL Server do ambiente dev com os mesmos cenários — o par
banco-real/dublê está registrado no PR.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from datetime import date, datetime, time
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, _ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# `datas_dos_predecessores` importa utils.data_referencia em runtime (import
# tardio do módulo puro): sem registrar o pacote, o teste veria um erro de
# import onde deveria ver a regra de datas.
def _registrar_utils():
    if "utils" not in sys.modules:
        sys.modules["utils"] = types.ModuleType("utils")
    sys.modules["utils.data_referencia"] = _load(
        "utils_data_referencia_aceite", "dags/utils/data_referencia.py")


@pytest.fixture(scope="module")
def dep():
    _registrar_utils()
    return _load("utils_dependencias_aceite", "dags/utils/dependencias.py")


@pytest.fixture(scope="module")
def mc():
    return _load("utils_malha_ciclo_aceite", "dags/utils/malha_ciclo.py")


# ── banco dublê: interpreta as LINHAS, não devolve resposta pronta ──────────

class _Cur:
    def __init__(self, db):
        self.db = db
        self._rows = []

    def execute(self, sql, params=()):
        s = " ".join(str(sql).split())
        p = tuple(params)
        # Predicado de liberação: tradução direta do NOT EXISTS do módulo —
        # predecessor SEM linha de SUCESSO viva na data é faltante.
        if "SELECT dd.depende_de" in s and "NOT EXISTS" in s:
            pipeline, data_ref = p
            usa_078 = "substituida_em" in s
            faltantes = []
            for pred in self.db["deps"].get(pipeline, []):
                tem_sucesso = any(
                    e["pipeline"] == pred
                    and e["data_referencia"] == data_ref
                    and e["status"] == "SUCESSO"
                    and (not usa_078 or e.get("substituida_em") is None)
                    for e in self.db["execucoes"])
                if not tem_sucesso:
                    faltantes.append((pred,))
            self._rows = faltantes
            return
        if "dd.depende_de" in s or s.startswith("SELECT depende_de"):
            # predecessores_de: a MESMA tabela, sem o NOT EXISTS
            self._rows = [(x,) for x in self.db["deps"].get(p[0], [])]
            return
        if s.startswith("SELECT p.hora_virada, c.config_value"):
            self._rows = [(self.db["viradas"].get(p[0]), None)]
            return
        self._rows = []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _Conn:
    def __init__(self, deps=None, execucoes=None, viradas=None):
        self.db = {"deps": deps or {}, "execucoes": list(execucoes or []),
                   "viradas": viradas or {}}

    def cursor(self):
        return _Cur(self.db)

    def commit(self):
        pass


def _exec(pipeline, data, status, substituida=None):
    return {"pipeline": pipeline, "data_referencia": data, "status": status,
            "substituida_em": substituida}


_HOJE = date(2026, 8, 4)
_ONTEM = date(2026, 8, 3)
# Um Aguarde com duas entradas compila duas dependências para o mesmo filho:
# é essa a forma que o componente tem no banco.
_DEPS = {"FILHO": ["PIPE_A", "PIPE_B"]}


# ═══ A. só libera com TODOS finalizados ═════════════════════════════════════

def test_A1_um_ainda_executando_nao_libera(dep):
    """O caso que o usuário viu em produção: metade pronta, o Aguarde abriu."""
    conn = _Conn(_DEPS, [_exec("PIPE_A", _HOJE, "SUCESSO"),
                         _exec("PIPE_B", _HOJE, "EXECUTANDO")])
    liberado, faltam = dep.liberado(conn, "FILHO", _HOJE)
    assert liberado is False
    assert faltam == ["PIPE_B"]


def test_A2_um_aguardando_dependencia_nao_libera(dep):
    conn = _Conn(_DEPS, [_exec("PIPE_A", _HOJE, "SUCESSO"),
                         _exec("PIPE_B", _HOJE, "AGUARDANDO_DEPENDENCIA")])
    assert dep.liberado(conn, "FILHO", _HOJE) == (False, ["PIPE_B"])


def test_A3_um_com_falha_nao_libera(dep):
    conn = _Conn(_DEPS, [_exec("PIPE_A", _HOJE, "SUCESSO"),
                         _exec("PIPE_B", _HOJE, "FALHA")])
    assert dep.liberado(conn, "FILHO", _HOJE) == (False, ["PIPE_B"])


def test_A4_um_pulado_nao_libera(dep):
    """PULADO é fim de corrida, mas NÃO é sucesso: o filho não pode partir com
    um predecessor que não produziu dado."""
    conn = _Conn(_DEPS, [_exec("PIPE_A", _HOJE, "SUCESSO"),
                         _exec("PIPE_B", _HOJE, "PULADO")])
    assert dep.liberado(conn, "FILHO", _HOJE) == (False, ["PIPE_B"])


def test_A5_um_sem_linha_nenhuma_nao_libera(dep):
    conn = _Conn(_DEPS, [_exec("PIPE_A", _HOJE, "SUCESSO")])
    assert dep.liberado(conn, "FILHO", _HOJE) == (False, ["PIPE_B"])


def test_A6_rerun_em_andamento_fecha_o_aguarde_de_novo(dep):
    """Sucesso APOSENTADO por um rerun (substituida_em) não conta — senão o
    filho rodaria com a saída ANTIGA enquanto o pai refaz a dele."""
    conn = _Conn(_DEPS, [
        _exec("PIPE_A", _HOJE, "SUCESSO"),
        _exec("PIPE_B", _HOJE, "SUCESSO", substituida=datetime(2026, 8, 4, 9)),
        _exec("PIPE_B", _HOJE, "EXECUTANDO"),
    ])
    assert dep.liberado(conn, "FILHO", _HOJE) == (False, ["PIPE_B"])


def test_A7_sucesso_em_outra_data_nao_libera(dep):
    """O sucesso de ontem não abre o Aguarde de hoje."""
    conn = _Conn(_DEPS, [_exec("PIPE_A", _HOJE, "SUCESSO"),
                         _exec("PIPE_B", _ONTEM, "SUCESSO")])
    assert dep.liberado(conn, "FILHO", _HOJE) == (False, ["PIPE_B"])


def test_A8_todos_com_sucesso_na_data_libera(dep):
    """O único caso que abre."""
    conn = _Conn(_DEPS, [_exec("PIPE_A", _HOJE, "SUCESSO"),
                         _exec("PIPE_B", _HOJE, "SUCESSO")])
    assert dep.liberado(conn, "FILHO", _HOJE) == (True, [])


def test_A9_erro_de_consulta_nao_vira_liberado(dep, capsys):
    """D21: quando não dá para perguntar, a resposta é NÃO."""
    class _ConnRuim(_Conn):
        def cursor(self):
            raise RuntimeError("banco fora (teste)")
    liberado, faltam = dep.liberado(_ConnRuim(), "FILHO", _HOJE)
    assert liberado is False
    assert faltam and faltam[0].startswith(dep.ERRO_CONSULTA)


# ═══ B. a data é validada ANTES de começar ══════════════════════════════════

def test_B1_ciclo_com_corrida_viva_segura_a_malha(mc):
    """A malha não recomeça por cima de si mesma."""
    class _ConnMalha:
        def cursor(self):
            class C:
                def execute(self, sql, params=()):
                    s = " ".join(str(sql).split())
                    self._r = ([("PIPE_X", _HOJE, "EXECUTANDO")]
                               if "e.status IN" in s else [])

                def fetchall(self):
                    return self._r

                def fetchone(self):
                    return self._r[0] if self._r else None
            return C()
    est = mc.estado_do_ciclo(_ConnMalha(), "M1", _HOJE, datetime(2026, 8, 4))
    assert est["em_aberto"] == [("PIPE_X", _HOJE, "EXECUTANDO")]
    assert "PIPE_X" in mc.resumo(est)


def test_B2_recorte_do_ciclo_nao_barra_a_corrida_de_ontem(mc):
    """O corte é a virada corrente: a corrida encerrada ontem é histórico, e
    barrar por ela travaria toda malha com passado."""
    corte = mc.inicio_do_ciclo(datetime(2026, 8, 4, 9, 0), time(20, 0))
    assert corte == datetime(2026, 8, 3, 20, 0)
    assert datetime(2026, 8, 3, 1, 10) < corte     # ontem de manhã: fora
    assert datetime(2026, 8, 4, 1, 10) > corte     # esta madrugada: dentro


# ═══ C. datas diferentes BLOQUEIAM ══════════════════════════════════════════

def test_C1_predecessores_em_datas_diferentes_bloqueiam(dep):
    """A assinatura do incidente: um pai carimbando D-1 e outro D."""
    conn = _Conn(_DEPS, viradas={"PIPE_A": time(20, 0), "PIPE_B": None})
    datas = dep.datas_dos_predecessores(conn, "FILHO",
                                        datetime(2026, 8, 4, 21, 0))
    assert datas == {"PIPE_A": date(2026, 8, 5), "PIPE_B": date(2026, 8, 4)}
    assert dep.datas_divergentes(datas) is True
    detalhe = dep.detalhe_divergencia(datas)
    assert "PIPE_A->2026-08-05" in detalhe and "PIPE_B->2026-08-04" in detalhe


def test_C2_mesma_virada_nao_bloqueia(dep):
    conn = _Conn(_DEPS, viradas={"PIPE_A": time(20, 0), "PIPE_B": time(20, 0)})
    datas = dep.datas_dos_predecessores(conn, "FILHO",
                                        datetime(2026, 8, 4, 21, 0))
    assert set(datas.values()) == {date(2026, 8, 5)}
    assert dep.datas_divergentes(datas) is False


def test_C3_um_predecessor_so_nunca_diverge(dep):
    conn = _Conn({"FILHO": ["PIPE_A"]}, viradas={"PIPE_A": time(20, 0)})
    datas = dep.datas_dos_predecessores(conn, "FILHO",
                                        datetime(2026, 8, 4, 21, 0))
    assert dep.datas_divergentes(datas) is False
