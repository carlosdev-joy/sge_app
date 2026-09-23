"""Retenção das conversas de AGENTE na DAG de limpeza (F4 da spec
docs/spec-agentes-datastage.md, critério 4).

O que se prende:

  1. **A purga apaga a CONVERSA vencida** — por `ultima_msg_em` (uma
     conversa retomada continua viva; `criada_em` a mataria no 31º dia
     mesmo em uso), com placeholder `%s` (pymssql — o gotcha do repo: `?`
     daria zero gravação com a task VERDE), commit e contagem.

  2. **A purga NÃO apaga proposta, fato nem aprendizado.** É o critério 4
     da F4, e quem o garante é o SCHEMA: `etl_agente_mensagem` tem FK com
     `ON DELETE CASCADE` (some junto, e deve mesmo), enquanto
     `etl_agente_fato`, `_proposta` e `_aprendizado` NÃO têm FK para a
     conversa — o que o agente aprendeu sobre um job sobrevive à conversa
     que o descobriu. Testamos as duas pontas: o DELETE só cita a tabela de
     conversa, e a migration 117 não criou FK dessas três para ela.

  3. **Sem a tabela (117 pendente) não executa DELETE nenhum** e diz isso —
     a API pode subir antes da etapa 6c.

  4. **O prazo espelha `services/agentes.RETENCAO_CONVERSAS_DIAS`** (api/ e
     dags/ não se importam; duas constantes que precisam concordar).

O Airflow não está instalado aqui: os módulos viram MagicMock e o arquivo da
DAG é carregado por caminho (mesmo padrão de test_log_cleanup_maestro.py).
"""
from __future__ import annotations

import importlib.util
import os
import re
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
MIGRATION = RAIZ / "sql" / "migrations" / "117_agentes.sql"


def _carregar():
    spec = importlib.util.spec_from_file_location("etl_log_cleanup_agentes_teste", ARQUIVO)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Cur:
    def __init__(self, tabela=True, apagadas=5):
        self.tabela, self.apagadas = tabela, apagadas
        self.execs: list[tuple[str, tuple]] = []
        self.rowcount = -1

    def execute(self, sql, params=None):
        self.execs.append((sql, tuple(params or ())))
        if "OBJECT_ID" in sql:
            self._row = (1234,) if self.tabela else (None,)
        else:
            self.rowcount = self.apagadas

    def fetchone(self):
        return self._row

    def close(self):
        pass


class _Conn:
    def __init__(self, cur):
        self._cur, self.commits = cur, 0

    def cursor(self):
        return self._cur

    def commit(self):
        self.commits += 1


# ═══════════ 1. a purga apaga a conversa vencida ═════════════════════════

def test_apaga_por_ultima_msg_em_e_commita():
    mod = _carregar()
    cur = _Cur(apagadas=7)
    conn = _Conn(cur)
    r = mod.apagar_conversas_agentes_antigas(conn)
    assert r == {"tabela": "ok", "apagadas": 7, "retencao_dias": 30}
    assert conn.commits == 1
    sql, params = cur.execs[-1]
    assert "DELETE FROM dbo.etl_agente_conversa" in sql
    # `ultima_msg_em`, não `criada_em`: conversa retomada continua viva.
    assert "ultima_msg_em <" in sql and "criada_em" not in sql
    assert params == (30,)


def test_placeholder_e_o_do_pymssql():
    """`?` aqui daria zero linhas apagadas com a task VERDE — o gotcha do
    repo (`dags/` usa `%s`, `api/` usa `?`)."""
    mod = _carregar()
    cur = _Cur()
    mod.apagar_conversas_agentes_antigas(_Conn(cur))
    sql, _ = cur.execs[-1]
    assert "%s" in sql and "?" not in sql


def test_sem_a_tabela_nao_executa_delete():
    mod = _carregar()
    cur = _Cur(tabela=False)
    conn = _Conn(cur)
    r = mod.apagar_conversas_agentes_antigas(conn)
    assert r["apagadas"] == 0 and "117" in r["tabela"]
    assert conn.commits == 0
    assert not any("DELETE" in s for s, _ in cur.execs)


def test_rowcount_negativo_nao_vira_contagem_falsa():
    """Driver que devolve -1 não pode virar "-1 apagadas" no XCom."""
    mod = _carregar()
    cur = _Cur(apagadas=-1)
    r = mod.apagar_conversas_agentes_antigas(_Conn(cur))
    assert r["apagadas"] == 0


def test_prazo_espelha_o_do_servico():
    from services import agentes as svc
    mod = _carregar()
    assert mod.RETENCAO_CONVERSAS_AGENTES_DIAS == svc.RETENCAO_CONVERSAS_DIAS == 30


def test_a_dag_ganhou_a_tarefa():
    fonte = ARQUIVO.read_text(encoding="utf-8")
    assert "def limpar_conversas_agentes()" in fonte
    assert re.search(r"^\s{4}limpar_conversas_agentes\(\)", fonte, re.M), \
        "a tarefa precisa ser CHAMADA no corpo da DAG, não só definida"
    # A do Maestro continua lá — uma não substituiu a outra.
    assert re.search(r"^\s{4}limpar_conversas_maestro\(\)", fonte, re.M)


# ═══════════ 2. critério 4: o que NÃO pode ser apagado junto ═════════════

def test_purga_so_toca_a_tabela_de_conversa():
    mod = _carregar()
    cur = _Cur()
    mod.apagar_conversas_agentes_antigas(_Conn(cur))
    sql_todo = " ".join(s for s, _ in cur.execs).lower()
    for tabela in ("etl_agente_fato", "etl_agente_proposta", "etl_agente_aprendizado"):
        assert tabela not in sql_todo, f"a purga não pode citar {tabela}"


def test_schema_nao_liga_fato_proposta_nem_aprendizado_a_conversa():
    """A outra ponta do critério 4: mesmo que alguém acrescente um DELETE
    em cascata amanhã, é o SCHEMA que garante a sobrevivência. Só a tabela
    de MENSAGEM tem FK para a conversa (com CASCADE — e deve ter)."""
    sql = MIGRATION.read_text(encoding="utf-8")
    fks = re.findall(r"FOREIGN KEY\s*\([^)]*\)\s*REFERENCES\s+dbo\.etl_agente_conversa", sql, re.I)
    assert len(fks) == 1, f"só etl_agente_mensagem pode referenciar a conversa; achei {len(fks)} FKs"
    # E a que existe é a da mensagem, com CASCADE.
    assert re.search(
        r"FK_etl_agente_mensagem_conversa\s+FOREIGN KEY.*?REFERENCES\s+dbo\.etl_agente_conversa\s*\([^)]*\)\s*ON DELETE CASCADE",
        sql, re.I | re.S), "a FK da mensagem precisa ser ON DELETE CASCADE"


def test_o_comentario_da_migration_explica_a_sobrevivencia():
    """Documentação executável: se alguém acrescentar a FK 'faltante' um
    dia, o comentário está lá dizendo por que ela não existe."""
    sql = MIGRATION.read_text(encoding="utf-8")
    assert re.search(r"etl_agente_fato\s*—\s*SEM FK", sql), \
        "o motivo de não haver FK precisa continuar escrito na migration"
