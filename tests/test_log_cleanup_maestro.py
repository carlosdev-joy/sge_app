"""Retenção das conversas do Maestro na DAG de limpeza (F3 da spec
docs/spec-maestro-parametros.md).

O que se prende: `apagar_conversas_antigas` em dags/etl_log_cleanup.py apaga
por `criado_em` com placeholder `%s` (pymssql — gotcha do repo: `?` daria zero
gravação com task verde), commita, devolve a contagem; sem a tabela (migration
110 pendente) não executa DELETE nenhum e diz isso; o prazo espelha
services/maestro.RETENCAO_CONVERSAS_DIAS; e a DAG ganhou a tarefa.

O Airflow não está instalado aqui: os módulos dele viram MagicMock e o arquivo
da DAG é carregado por caminho (padrão de test_pipeline_sob_demanda.py).
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
for _mod in ("airflow", "airflow.decorators", "airflow.providers", "airflow.providers.microsoft",
             "airflow.providers.microsoft.mssql", "airflow.providers.microsoft.mssql.hooks",
             "airflow.providers.microsoft.mssql.hooks.mssql", "pendulum"):
    sys.modules.setdefault(_mod, MagicMock())

RAIZ = Path(__file__).resolve().parents[1]
ARQUIVO = RAIZ / "dags" / "etl_log_cleanup.py"


def _carregar():
    spec = importlib.util.spec_from_file_location("etl_log_cleanup_teste", ARQUIVO)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Cur:
    def __init__(self, tabela=True, apagadas=3):
        self.tabela, self.apagadas = tabela, apagadas
        self.execs: list[tuple[str, tuple]] = []
        self.rowcount = -1
        self._row = None
        self.fechado = False

    def execute(self, sql, params=None):
        self.execs.append((sql, tuple(params or ())))
        if "OBJECT_ID" in sql:
            self._row = (123,) if self.tabela else (None,)
            self.rowcount = -1
        else:
            self.rowcount = self.apagadas

    def fetchone(self):
        return self._row

    def close(self):
        self.fechado = True


class _Conn:
    def __init__(self, cur):
        self._cur, self.commits = cur, 0

    def cursor(self):
        return self._cur

    def commit(self):
        self.commits += 1


def test_apaga_por_criado_em_com_placeholder_pymssql_e_commita():
    mod = _carregar()
    cur = _Cur(apagadas=7)
    conn = _Conn(cur)
    r = mod.apagar_conversas_antigas(conn)
    assert r == {"tabela": "ok", "apagadas": 7, "retencao_dias": 180}
    sql, params = cur.execs[1]
    assert sql.startswith("DELETE FROM dbo.etl_maestro_conversa") and "DATEADD(day, -%s, GETDATE())" in sql
    assert "?" not in sql and params == (180,)
    assert conn.commits == 1 and cur.fechado


def test_sem_a_tabela_nao_executa_delete():
    mod = _carregar()
    cur = _Cur(tabela=False)
    conn = _Conn(cur)
    r = mod.apagar_conversas_antigas(conn, dias=30)
    assert r["apagadas"] == 0 and "migration 110" in r["tabela"] and r["retencao_dias"] == 30
    assert len(cur.execs) == 1 and conn.commits == 0


def test_prazo_espelha_o_servico_e_a_dag_tem_a_tarefa():
    from services import maestro
    mod = _carregar()
    assert mod.RETENCAO_CONVERSAS_MAESTRO_DIAS == maestro.RETENCAO_CONVERSAS_DIAS == 180
    fonte = ARQUIVO.read_text(encoding="utf-8")
    assert "def limpar_conversas_maestro" in fonte and "limpar_conversas_maestro()" in fonte
    assert "MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)" in fonte
