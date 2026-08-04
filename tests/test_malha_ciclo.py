"""
utils/malha_ciclo.py — a malha começa do ZERO no gatilho AUTOMÁTICO (F5 da
docs/spec-malha-data-unica.md).

A API já barrava o disparo pela tela (F1). Faltava o cron: sem esta camada, a
proteção valia só para quem clicava, e o scheduler continuava partindo malha
suja — que foi como a Carga_Vida acabou com metade dos membros no dia 3 e
metade no dia 4.

Módulo com banco, sem Airflow: os testes usam um conn dublê que responde às
consultas por prefixo, e cobrem o que só se vê no runtime — recorte do ciclo,
degradação por falha de consulta (que aqui NÃO pode barrar produção) e as
guardas do recarimbo.
"""
from __future__ import annotations

import importlib.util
from datetime import date, datetime, time
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, _ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mc():
    return _load("utils_malha_ciclo_test", "dags/utils/malha_ciclo.py")


class _Cur:
    def __init__(self, db):
        self.db = db
        self._rows = []

    def execute(self, sql, params=()):
        s = " ".join(str(sql).split())
        self.db["execs"].append((s, tuple(params)))
        if self.db.get("explode"):
            raise RuntimeError("banco indisponível (teste)")
        if s.startswith("SELECT TOP 1 m.malha_name"):
            self._rows = [(self.db["malha"],)] if self.db.get("malha") else []
        elif s.startswith("SELECT CAST(equalizar_data AS INT)"):
            self._rows = [(self.db.get("equalizar", 0),)]
        elif s.startswith("SELECT hora_virada"):
            self._rows = [(self.db.get("virada"),)]
        elif "e.status IN" in s:
            self._rows = list(self.db.get("em_aberto", []))
        elif "e.data_referencia <> %s" in s:
            self._rows = list(self.db.get("divergentes", []))
        elif s.startswith("SELECT COUNT(*) FROM dbo.etl_pipeline_execucao"):
            pipe = params[0]
            self._rows = [(1 if pipe in self.db.get("ja_na_data", ()) else 0,)]
        elif s.startswith("UPDATE dbo.etl_pipeline_execucao"):
            self.db["updates"].append(tuple(params))
            self._rows = []
        else:
            self._rows = []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _Conn:
    def __init__(self, **db):
        self.db = {"execs": [], "updates": [], **db}
        self.commits = 0

    def cursor(self):
        return _Cur(self.db)

    def commit(self):
        self.commits += 1


# ── recorte do ciclo ────────────────────────────────────────────────────────

def test_inicio_do_ciclo_com_virada(mc):
    """Virada 20:00 às 21h de 04/08 → o ciclo começou às 20:00 de 04/08."""
    assert mc.inicio_do_ciclo(datetime(2026, 8, 4, 21, 0), time(20, 0)) \
        == datetime(2026, 8, 4, 20, 0)


def test_inicio_do_ciclo_antes_da_virada_volta_um_dia(mc):
    assert mc.inicio_do_ciclo(datetime(2026, 8, 4, 3, 0), time(20, 0)) \
        == datetime(2026, 8, 3, 20, 0)


def test_inicio_do_ciclo_sem_virada_e_meia_noite(mc):
    assert mc.inicio_do_ciclo(datetime(2026, 8, 4, 3, 0), None) \
        == datetime(2026, 8, 4, 0, 0)


# ── leituras ────────────────────────────────────────────────────────────────

def test_malha_do_pipeline(mc):
    conn = _Conn(malha="M1")
    assert mc.malha_do_pipeline(conn, "PIPE_A") == "M1"


def test_sem_malha_devolve_none(mc):
    assert mc.malha_do_pipeline(_Conn(), "PIPE_A") is None


def test_falha_de_consulta_nao_barra(mc, capsys):
    """Erro aqui NÃO pode virar 'malha suja': barrar a produção inteira por um
    problema transitório de banco seria pior que o defeito que a trava evita."""
    conn = _Conn(explode=True)
    assert mc.malha_do_pipeline(conn, "PIPE_A") is None
    est = mc.estado_do_ciclo(conn, "M1", date(2026, 8, 4), datetime(2026, 8, 4))
    assert est == {"em_aberto": [], "divergentes": []}
    assert "indisponivel" in capsys.readouterr().out


def test_estado_do_ciclo_separa_as_duas_perguntas(mc):
    conn = _Conn(em_aberto=[("PIPE_X", date(2026, 8, 4), "EXECUTANDO")],
                 divergentes=[("PIPE_Y", date(2026, 8, 3), "SUCESSO")])
    est = mc.estado_do_ciclo(conn, "M1", date(2026, 8, 4), datetime(2026, 8, 4))
    assert est["em_aberto"] == [("PIPE_X", date(2026, 8, 4), "EXECUTANDO")]
    assert est["divergentes"] == [("PIPE_Y", date(2026, 8, 3), "SUCESSO")]


def test_resumo_diz_quem_segura(mc):
    texto = mc.resumo({"em_aberto": [("PIPE_X", date(2026, 8, 4), "EXECUTANDO")],
                       "divergentes": [("PIPE_Y", date(2026, 8, 3), "SUCESSO")]})
    assert "PIPE_X" in texto and "executando" in texto
    assert "PIPE_Y em 2026-08-03" in texto


# ── equalização ─────────────────────────────────────────────────────────────

def test_equalizar_recarimba_e_deixa_rastro(mc):
    conn = _Conn()
    feitos = mc.equalizar(conn, "M1", date(2026, 8, 4),
                          [("PIPE_Y", date(2026, 8, 3), "SUCESSO")], "agenda")
    assert feitos == [("PIPE_Y", date(2026, 8, 3), date(2026, 8, 4))]
    (nova, motivo, pipe, antiga, status) = conn.db["updates"][0]
    assert nova == date(2026, 8, 4) and pipe == "PIPE_Y"
    assert antiga == date(2026, 8, 3) and status == "SUCESSO"
    assert "equalizada" in motivo and "M1" in motivo   # histórico não muda mudo


def test_equalizar_pula_quem_ja_tem_corrida_na_data(mc, capsys):
    conn = _Conn(ja_na_data=("PIPE_Y",))
    feitos = mc.equalizar(conn, "M1", date(2026, 8, 4),
                          [("PIPE_Y", date(2026, 8, 3), "SUCESSO")], "agenda")
    assert feitos == []
    assert conn.db["updates"] == []
    assert "ja tem corrida" in capsys.readouterr().out


def test_equalizar_um_erro_nao_derruba_os_outros(mc):
    class _ConnParcial(_Conn):
        def cursor(self):
            cur = _Cur(self.db)
            original = cur.execute

            def execute(sql, params=()):
                if "UPDATE" in str(sql) and params and params[2] == "PIPE_RUIM":
                    raise RuntimeError("deadlock (teste)")
                return original(sql, params)
            cur.execute = execute
            return cur

    conn = _ConnParcial()
    feitos = mc.equalizar(conn, "M1", date(2026, 8, 4),
                          [("PIPE_RUIM", date(2026, 8, 3), "SUCESSO"),
                           ("PIPE_BOM", date(2026, 8, 3), "SUCESSO")], "agenda")
    assert [f[0] for f in feitos] == ["PIPE_BOM"]


def test_equalizar_ligado_le_a_marca(mc):
    assert mc.equalizar_ligado(_Conn(equalizar=1), "M1") is True
    assert mc.equalizar_ligado(_Conn(equalizar=0), "M1") is False
    assert mc.equalizar_ligado(_Conn(explode=True), "M1") is False   # sem a 081


def test_virada_da_malha_aceita_time_e_texto(mc):
    assert mc.virada_da_malha(_Conn(virada=time(20, 0)), "M1") == time(20, 0)
    assert mc.virada_da_malha(_Conn(virada="20:00:00"), "M1") == time(20, 0)
    assert mc.virada_da_malha(_Conn(virada=None), "M1") is None
