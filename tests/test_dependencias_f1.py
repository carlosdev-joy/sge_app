"""
Testes da F1 de docs/spec-dependencias-pipelines.md.

Duas frentes:
  • data de referência (ODATE) — módulo puro, sem Airflow;
  • cadastro de dependência — detecção de ciclo por BFS e validação de
    existência, com cursor falso no lugar do SQL Server.

Os dois casos que MOTIVARAM a spec estão aqui e falhavam antes:
  - 31/07 23:30 e 01/08 00:40 pertencerem à mesma corrida (virada 20:00);
  - ciclo com múltiplas dependências ser detectado.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime, time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_ROOT = Path(__file__).parent.parent
_DAGS = _ROOT / "dags"
if str(_DAGS) not in sys.path:
    sys.path.insert(0, str(_DAGS))


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(name, _ROOT / relpath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def dref():
    return _load("data_referencia_test", "dags/utils/data_referencia.py")


@pytest.fixture(scope="module")
def pipes():
    for m in ["pyodbc", "fastapi", "fastapi.responses", "pydantic"]:
        sys.modules.setdefault(m, MagicMock())
    sys.path.insert(0, str(_ROOT / "api"))
    return _load("pipelines_dep_test", "api/routers/pipelines.py")


# ───────────────────────── Data de referência (ODATE) ──────────────────────

def test_virada_padrao_usa_a_data_do_calendario(dref):
    """00:00 preserva o comportamento anterior à 067 — nada muda ao subir."""
    assert dref.calcular(datetime(2026, 7, 31, 23, 30)) == date(2026, 7, 31)
    assert dref.calcular(datetime(2026, 8, 1, 0, 40)) == date(2026, 8, 1)


def test_virada_20h_junta_as_duas_pontas_da_meia_noite(dref):
    """O caso que motivou a spec: 31/07 23:30 e 01/08 00:40, mesma corrida."""
    virada = time(20, 0)
    assert dref.calcular(datetime(2026, 7, 31, 23, 30), virada) == date(2026, 8, 1)
    assert dref.calcular(datetime(2026, 8, 1, 0, 40), virada) == date(2026, 8, 1)
    assert dref.mesma_corrida(
        dref.calcular(datetime(2026, 7, 31, 23, 30), virada),
        dref.calcular(datetime(2026, 8, 1, 0, 40), virada)) is True


def test_antes_da_virada_fica_no_dia_corrente(dref):
    assert dref.calcular(datetime(2026, 8, 1, 19, 59), time(20, 0)) == date(2026, 8, 1)
    # Exatamente na virada já conta como o dia seguinte.
    assert dref.calcular(datetime(2026, 8, 1, 20, 0), time(20, 0)) == date(2026, 8, 2)


def test_virada_invalida_nao_derruba_o_calculo(dref):
    """Valor estranho em etl_app_config não pode quebrar TODOS os pipelines."""
    assert dref.parse_virada("meia-noite") == dref.VIRADA_PADRAO
    assert dref.parse_virada(None) == dref.VIRADA_PADRAO
    assert dref.parse_virada("") == dref.VIRADA_PADRAO
    assert dref.parse_virada("20:00:00") == time(20, 0)
    assert dref.calcular(datetime(2026, 7, 31, 23, 30), "lixo") == date(2026, 7, 31)


def test_mesma_corrida_com_data_ausente_e_falso(dref):
    assert dref.mesma_corrida(None, date(2026, 8, 1)) is False
    assert dref.mesma_corrida(date(2026, 8, 1), None) is False


# ─────────────────────────── Cadastro: ciclo e existência ──────────────────

class FakeCur:
    """Cursor de mentira sobre um grafo {pipeline: [predecessores]}.

    Responde às duas consultas que o cadastro faz: dependências de um pipeline
    e existência de um pipeline.
    """

    def __init__(self, grafo, existentes=None, com_tabela=True):
        self.grafo = grafo
        self.existentes = set(existentes if existentes is not None else grafo.keys())
        self.com_tabela = com_tabela
        self._resultado = []

    def execute(self, sql, params=()):
        if "etl_pipeline_dependencia" in sql:
            if not self.com_tabela:
                raise RuntimeError("Invalid object name 'dbo.etl_pipeline_dependencia'")
            self._resultado = [(d,) for d in self.grafo.get(params[0], [])]
        elif "SELECT depends_on" in sql:
            deps = self.grafo.get(params[0], [])
            self._resultado = [(",".join(deps) if deps else None,)]
        elif "SELECT 1 FROM dbo.etl_pipeline" in sql:
            self._resultado = [(1,)] if params[0] in self.existentes else []
        else:
            self._resultado = []

    def fetchall(self):
        return self._resultado

    def fetchone(self):
        return self._resultado[0] if self._resultado else None


def test_ciclo_simples_e_recusado(pipes):
    cur = FakeCur({"A": ["B"], "B": []})
    with pytest.raises(ValueError, match="circular"):
        pipes._check_circular(cur, "B", ["A"])


def test_ciclo_pela_segunda_dependencia_e_recusado(pipes):
    """O BUG que a F1 corrige.

    A versão antiga seguia só `raw.split(",")[0]`: com A dependendo de X e B,
    o caminho A→B→A nunca era visto e o ciclo entrava no banco.
    """
    cur = FakeCur({"A": ["X", "B"], "X": [], "B": []})
    with pytest.raises(ValueError, match="circular"):
        pipes._check_circular(cur, "B", ["A"])


def test_ciclo_longo_pelo_ramo_do_meio_e_recusado(pipes):
    cur = FakeCur({"A": ["B"], "B": ["Z", "C"], "Z": [], "C": []})
    with pytest.raises(ValueError, match="circular"):
        pipes._check_circular(cur, "C", ["A"])


def test_grafo_em_diamante_sem_ciclo_passa(pipes):
    """A→B, A→C, B→D, C→D: converge em D, mas não é ciclo.

    Guarda contra 'visitados' por caminho, que faria isto explodir ou acusar
    ciclo onde não há.
    """
    cur = FakeCur({"B": ["D"], "C": ["D"], "D": [], "X": []})
    pipes._check_circular(cur, "A", ["B", "C"])  # não levanta


def test_ciclo_preexistente_no_grafo_nao_trava_a_busca(pipes):
    """Se o banco já tem um ciclo (dado legado), a validação termina."""
    cur = FakeCur({"M": ["N"], "N": ["M"]})
    pipes._check_circular(cur, "NOVO", ["M"])  # termina, sem laço infinito


def test_ciclo_cai_no_csv_sem_a_migration(pipes):
    """Sem a tabela 067, a validação continua pelo CSV — nunca aceita tudo."""
    cur = FakeCur({"A": ["X", "B"], "X": [], "B": []}, com_tabela=False)
    with pytest.raises(ValueError, match="circular"):
        pipes._check_circular(cur, "B", ["A"])


def test_predecessor_inexistente_e_reportado(pipes):
    cur = FakeCur({"A": [], "B": []}, existentes={"A", "B"})
    assert pipes._validar_existencia(cur, ["A", "FANTASMA", "B"]) == ["FANTASMA"]
    assert pipes._validar_existencia(cur, ["A", "B"]) == []


def test_gravar_dependencias_substitui_a_lista(pipes):
    cur = MagicMock()
    assert pipes._gravar_dependencias(cur, "C", ["A", "B"], "u123") is True
    sqls = [str(c.args[0]) for c in cur.execute.call_args_list]
    assert any("DELETE FROM dbo.etl_pipeline_dependencia" in s for s in sqls)
    assert sum("INSERT INTO dbo.etl_pipeline_dependencia" in s for s in sqls) == 2


def test_gravar_dependencias_degrada_sem_a_migration(pipes):
    """Deploy que leva a API antes da 067 não pode derrubar o cadastro."""
    cur = MagicMock()
    cur.execute.side_effect = RuntimeError("Invalid object name")
    assert pipes._gravar_dependencias(cur, "C", ["A"], None) is False
