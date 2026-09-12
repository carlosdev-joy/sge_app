"""Tabela do nó SQL — `dags/utils/sql_node.py` (F4 da spec
docs/spec-email-tabela-sql-e-ajustes.md).

O nó SQL sempre publicou só o valor escalar, que a Decisão `valor_sql` lê. Aqui
ele passa a publicar também a TABELA do resultado, para o nó de e-mail a jusante
mostrar o que a consulta trouxe.

O que se prende:
  1. **O escalar sai CRU** — convertê-lo mudaria o que a Decisão compara;
  2. o corte acontece na ORIGEM, com teto de leitura, teto de linhas, teto de
     colunas e teto por célula;
  3. nada aqui pode levantar exceção: a tabela é um extra, e o nó existe para
     entregar o escalar.
"""
from __future__ import annotations

import datetime as _dt
import decimal as _decimal
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "dags"))

from utils import sql_node as sn  # noqa: E402


class _Cursor:
    """Cursor pyodbc de mentira: `description` + `fetchmany` é tudo que se usa."""

    def __init__(self, colunas, linhas):
        self.description = [(c,) for c in colunas]
        self._linhas = linhas
        self.pedidos = []

    def fetchmany(self, n):
        self.pedidos.append(n)
        saida, self._linhas = self._linhas[:n], self._linhas[n:]
        return saida

    # usados só pelo caminho do código gerado
    def execute(self, *_a, **_k):
        self.executado = True

    def close(self):
        pass


def test_o_escalar_sai_cru_e_a_tabela_convertida():
    """⛔ Âncora da fase. A Decisão `valor_sql` compara o escalar com régua
    tipada (texto/data/número): se ele viesse convertido, uma data viraria texto
    ISO e fluxos em produção passariam a decidir diferente sem ninguém mexer
    neles. A tabela, essa sim, precisa ser texto — o XCom é JSON."""
    quando = _dt.datetime(2026, 9, 11, 16, 18, 5)
    cur = _Cursor(["quando", "valor"], [(quando, _decimal.Decimal("12.50"))])
    escalar, tabela = sn.ler_resultado(cur)
    assert escalar is quando                       # o MESMO objeto, sem conversão
    assert tabela["rows"] == [["2026-09-11 16:18:05", "12.50"]]
    assert "_escalar" not in tabela, "o escalar não pode viajar duas vezes no XCom"


def test_escalar_e_tabela_vem_da_mesma_leitura():
    """Ler o cursor duas vezes daria linhas diferentes num SELECT sem ORDER BY —
    o fluxo decidiria por um valor que o e-mail não mostra."""
    cur = _Cursor(["a"], [("primeiro",), ("segundo",)])
    escalar, tabela = sn.ler_resultado(cur)
    assert escalar == "primeiro" and tabela["rows"][0] == ["primeiro"]
    assert len(cur.pedidos) == 1, "o cursor foi lido mais de uma vez"


@pytest.mark.parametrize("bruto, esperado", [
    (None, None), (True, True), (7, 7), (1.5, 1.5), ("texto", "texto"),
    (_decimal.Decimal("0.1"), "0.1"),
    (_dt.date(2026, 9, 11), "2026-09-11"),
    (_dt.time(16, 18), "16:18:00"),
    (b"\x00\x01\x02", "<3 bytes>"),
])
def test_valor_publicavel(bruto, esperado):
    assert sn.valor_publicavel(bruto) == esperado


def test_celula_gigante_e_cortada():
    """VARCHAR(MAX) com um JSON dentro entupiria o XCom e o corpo do e-mail."""
    v = sn.valor_publicavel("x" * 5000)
    assert len(v) == sn.LIMITE_CELULA and v.endswith("…")


def test_corta_linhas_mas_conta_o_que_leu():
    cur = _Cursor(["n"], [(i,) for i in range(60)])
    _, t = sn.ler_resultado(cur)
    assert len(t["rows"]) == sn.LIMITE_LINHAS
    assert t["total"] == 60 and t["truncado"] is True and t["havia_mais"] is False


def test_teto_de_leitura_vira_havia_mais():
    """Acima do teto o total é um PISO, e quem monta o aviso precisa saber disso
    para escrever "mais de 1.000" em vez de afirmar um número errado."""
    cur = _Cursor(["n"], [(i,) for i in range(sn.TETO_LEITURA + 500)])
    _, t = sn.ler_resultado(cur)
    assert cur.pedidos == [sn.TETO_LEITURA], "leu mais do que o teto"
    assert t["total"] == sn.TETO_LEITURA and t["havia_mais"] is True and t["truncado"] is True


def test_corta_colunas_e_diz_quantas_ficaram_fora():
    colunas = [f"c{i}" for i in range(20)]
    cur = _Cursor(colunas, [tuple(range(20))])
    _, t = sn.ler_resultado(cur)
    assert t["columns"] == colunas[:sn.LIMITE_COLUNAS]
    assert len(t["rows"][0]) == sn.LIMITE_COLUNAS and t["colunas_ocultas"] == 5


def test_resultado_vazio_e_cursor_sem_conjunto_nao_quebram():
    _, vazio = sn.ler_resultado(_Cursor(["a"], []))
    assert vazio["rows"] == [] and vazio["total"] == 0 and vazio["columns"] == ["a"]
    escalar, sem_conjunto = sn.ler_resultado(_Cursor([], []))
    assert escalar is None and sem_conjunto["columns"] == [] and sem_conjunto["rows"] == []


def test_o_resumo_do_log_conta_a_verdade():
    """É por esta linha que o smoke sabe se o worker está com o código novo — e
    ela não pode afirmar um total exato quando o teto de leitura foi atingido."""
    _, pequeno = sn.ler_resultado(_Cursor(["a", "b"], [("x", "y")]))
    assert sn.resumo_para_log(pequeno) == "1 linha(s) publicada(s), 2 coluna(s)"

    _, cortado = sn.ler_resultado(_Cursor(["a"], [(i,) for i in range(60)]))
    assert sn.resumo_para_log(cortado) == "50 linha(s) publicada(s), 1 coluna(s), de 60 lidas"

    _, teto = sn.ler_resultado(_Cursor(["a"], [(i,) for i in range(sn.TETO_LEITURA + 1)]))
    assert "mais de 1000 lidas" in sn.resumo_para_log(teto)

    assert sn.resumo_para_log(None)     # não explode com tabela ausente


# ── o código GERADO pelo factory ────────────────────────────────────────────
# O módulo acima é puro; o que roda em produção é a função que o
# etl_dag_factory escreve dentro do .py da DAG. Aqui ela é recortada da fonte
# gerada e executada de verdade, com um cursor e um `ti` de mentira.

import importlib.util  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

for _m in ("airflow", "airflow.models", "airflow.operators", "airflow.operators.python",
           "airflow.operators.empty", "airflow.datasets", "airflow.utils",
           "airflow.utils.trigger_rule", "airflow.utils.state", "airflow.providers",
           "airflow.providers.microsoft", "airflow.providers.microsoft.mssql",
           "airflow.providers.microsoft.mssql.hooks",
           "airflow.providers.microsoft.mssql.hooks.mssql", "pendulum", "requests"):
    sys.modules.setdefault(_m, MagicMock())


def _factory():
    spec = importlib.util.spec_from_file_location("factory_sql_tabela", _ROOT / "dags/etl_dag_factory.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _funcao_gerada(fonte: str, nome: str) -> str:
    linhas = fonte.splitlines()
    ini = next(i for i, l in enumerate(linhas) if l.startswith(f"def {nome}("))
    fim = ini + 1
    while fim < len(linhas) and (not linhas[fim].strip() or linhas[fim][:1] in (" ", "\t")):
        fim += 1
    return "\n".join(linhas[ini:fim])


@pytest.fixture(scope="module")
def resolver():
    """A `_resolve_e_roda_sql` REAL, recortada da fonte que o factory gera."""
    fonte = _factory()._generate_dag_source(
        {"pipeline_name": "PIPE_SQL", "project_name": "BI", "domain": "T", "tags": "ETL",
         "scheduled_time": "06:00:00", "envia_msg_inicio": 0, "envia_msg_fim": 0,
         "envia_msg_erro": 0, "ambiente": "PROD", "schedule_type": "daily"},
        [{"job_name": "NO_SQL", "job_type": "sql", "job_command": "", "execution_order": 1,
          "sql_json": '{"sql": "SELECT 1", "mssql_conn_id": "SQL69", "on_error": "falhar"}'}])
    ns = {"MSSQL_CONN_ID": "mssql_default"}
    exec(compile(_funcao_gerada(fonte, "_resolve_e_roda_sql"), "<gerado>", "exec"), ns)
    return ns["_resolve_e_roda_sql"]


def _ambiente(colunas, linhas, monkeypatch, push_explode=False):
    cur = _Cursor(colunas, linhas)
    conn = MagicMock()
    conn.cursor.return_value = cur
    resolver_mod = MagicMock()
    resolver_mod.abrir_conexao_mssql.return_value = conn
    monkeypatch.setitem(sys.modules, "utils.conn_resolver", resolver_mod)
    ti = MagicMock()
    if push_explode:
        ti.xcom_push.side_effect = RuntimeError("xcom fora do ar")
    return ti, conn


def test_o_codigo_gerado_publica_a_tabela_e_devolve_o_escalar(resolver, monkeypatch):
    quando = _dt.datetime(2026, 9, 11, 16, 18)
    ti, _ = _ambiente(["quando", "quem"], [(quando, "ana")], monkeypatch)
    valor = resolver("SELECT 1", "SQL69", "master", {"ti": ti}, on_error="falhar")

    assert valor is quando, "o return_value da task tem de continuar sendo o escalar CRU"
    ti.xcom_push.assert_called_once()
    assert ti.xcom_push.call_args.kwargs["key"] == "tabela"
    publicado = ti.xcom_push.call_args.kwargs["value"]
    assert publicado["columns"] == ["quando", "quem"]
    assert publicado["rows"] == [["2026-09-11 16:18:00", "ana"]]


def test_a_tabela_e_extra_e_nunca_derruba_o_no(resolver, monkeypatch, capsys):
    """⛔ O nó SQL existe para entregar o escalar à Decisão. Se publicar a tabela
    falhar (XCom fora do ar, payload recusado), a task tem de seguir verde com o
    valor — o contrário transformaria um extra em ponto de falha do fluxo."""
    ti, _ = _ambiente(["a"], [("valor",)], monkeypatch, push_explode=True)
    assert resolver("SELECT 1", "SQL69", None, {"ti": ti}, on_error="falhar") == "valor"
    assert "tabela nao publicada" in capsys.readouterr().out


def test_sem_ti_no_contexto_o_no_segue_funcionando(resolver, monkeypatch):
    """Chamada fora de uma task (teste, script) não tem `ti` — e não pode quebrar."""
    # um ambiente por chamada: o cursor de mentira é consumido pela leitura,
    # como o de verdade seria
    _ambiente(["a"], [("valor",)], monkeypatch)
    assert resolver("SELECT 1", "SQL69", None, {}, on_error="falhar") == "valor"
    _ambiente(["a"], [("valor",)], monkeypatch)
    assert resolver("SELECT 1", "SQL69", None, None, on_error="falhar") == "valor"


def test_worker_sem_o_modulo_novo_ainda_entrega_o_escalar(resolver, monkeypatch, capsys):
    """Deploy que atualizou `dags/` sem reiniciar o worker: `utils/` fica em
    cache e `utils.sql_node` pode não existir para o processo. O nó continua
    entregando o escalar — e o log diz o que fazer."""
    ti, conn = _ambiente(["a"], [("valor",)], monkeypatch)
    monkeypatch.setitem(sys.modules, "utils.sql_node", None)   # import falha
    conn.cursor.return_value.fetchone = lambda: ("valor",)
    assert resolver("SELECT 1", "SQL69", None, {"ti": ti}, on_error="falhar") == "valor"
    saida = capsys.readouterr().out
    assert "utils.sql_node indisponivel" in saida and "reinicie o worker" in saida
    ti.xcom_push.assert_not_called()
