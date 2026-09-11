"""Reparse prioritário depois de publicar (`_solicitar_reparse` do factory).

O Airflow varre a pasta de DAGs a cada `dag_dir_list_interval` (5 min por
padrão). Sem um empurrão, a DAG recém-gravada demora a aparecer — e o fluxo
"Gerar DAG" da UI, que ESPERA a ativação, chega a marcar TIMEOUT numa publicação
que deu certo. Uma linha em `dag_priority_parsing_request` faz o arquivo furar
a fila do scheduler.

O que se prende aqui:

  1. **Best-effort de verdade**: nada do que acontecer na conexão pode derrubar
     a geração — o arquivo já está gravado e o scheduler o leria de qualquer
     forma na varredura seguinte.
  2. **Uma conexão para o lote**: a regeração em massa passa por centenas de
     pipelines; uma conexão por arquivo seriam centenas de conexões ao
     metastore para gravar uma linha cada.
  3. **Só Postgres**: metastore que não é Postgres não tem essa fila.
  4. **Senha percent-encoded** é decodificada (`%40` → `@`) — sem isso a
     conexão falharia justamente nas senhas com caractere especial.
  5. **Sem pedido repetido** do mesmo arquivo: o id é o md5 do `fileloc`, como
     o próprio Airflow faz, e é ele que devolve sentido ao `ON CONFLICT`.
  6. **Um arquivo com erro não cala o lote** — e o alvo do clique fura a fila
     na hora, sem esperar a geração dos pendentes de terceiros.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_AIRFLOW_STUBS = [
    "airflow", "airflow.models", "airflow.operators", "airflow.operators.python",
    "airflow.operators.empty", "airflow.datasets", "airflow.utils",
    "airflow.utils.trigger_rule", "airflow.utils.state",
    "airflow.providers", "airflow.providers.microsoft", "airflow.providers.microsoft.mssql",
    "airflow.providers.microsoft.mssql.hooks", "airflow.providers.microsoft.mssql.hooks.mssql",
    "pendulum", "requests",
]
for _mod in _AIRFLOW_STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

_ROOT = Path(__file__).parent.parent
CONN = "postgresql+psycopg2://airflow:s%40nha@postgres:5432/airflow"


@pytest.fixture(scope="module")
def factory():
    spec = importlib.util.spec_from_file_location(
        "etl_dag_factory_reparse_test", _ROOT / "dags/etl_dag_factory.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Cursor:
    def __init__(self, registro):
        self.registro = registro

    def execute(self, sql, params=None):
        self.registro["sql"].append(" ".join(sql.split()))
        self.registro["params"].append(tuple(params or ()))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Conexao:
    def __init__(self, registro):
        self.registro = registro
        self.autocommit = False
        self.fechada = False

    def cursor(self):
        return _Cursor(self.registro)

    def close(self):
        self.fechada = True


@pytest.fixture
def psycopg2(monkeypatch):
    """psycopg2 de mentira, registrando conexões e comandos."""
    registro = {"conexoes": [], "sql": [], "params": [], "erro": None}
    conexoes: list[_Conexao] = []

    def _connect(**kwargs):
        registro["conexoes"].append(kwargs)
        if registro["erro"] is not None:
            raise registro["erro"]
        c = _Conexao(registro)
        conexoes.append(c)
        return c

    falso = MagicMock()
    falso.connect = _connect
    monkeypatch.setitem(sys.modules, "psycopg2", falso)
    registro["abertas"] = conexoes
    return registro


def _ambiente(monkeypatch, conn=CONN, chave="AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"):
    for k in ("AIRFLOW__DATABASE__SQL_ALCHEMY_CONN", "AIRFLOW__CORE__SQL_ALCHEMY_CONN"):
        monkeypatch.delenv(k, raising=False)
    if conn is not None:
        monkeypatch.setenv(chave, conn)


def test_uma_conexao_para_o_lote_inteiro(factory, psycopg2, monkeypatch, capsys):
    """Centenas de pipelines na regeração em massa — não centenas de conexões."""
    _ambiente(monkeypatch)
    factory._solicitar_reparse([f"/opt/airflow/dags/P{i}.py" for i in range(50)])
    assert len(psycopg2["conexoes"]) == 1
    assert len(psycopg2["sql"]) == 50
    assert psycopg2["abertas"][0].fechada is True
    # ⛔ Sem `autocommit` nada é gravado: não há commit explícito, e o close()
    # do finally descarta a transação implícita — com o log continuando a dizer
    # "reparse solicitado". Falso verde perfeito; por isso a asserção existe.
    assert psycopg2["abertas"][0].autocommit is True
    assert "50 arquivo(s)" in capsys.readouterr().out


def test_insere_na_fila_do_scheduler_sem_repetir_pedido(factory, psycopg2, monkeypatch):
    import hashlib

    _ambiente(monkeypatch)
    factory._solicitar_reparse(["/dags/A.py", "/dags/A.py", "/dags/B.py", "", None])
    # duplicata e vazio somem ANTES do banco
    assert [p[1] for p in psycopg2["params"]] == ["/dags/A.py", "/dags/B.py"]
    sql = psycopg2["sql"][0]
    assert "INSERT INTO dag_priority_parsing_request (id, fileloc)" in sql
    # ⛔ O id É o md5 do fileloc, como o Airflow faz (`generate_md5_hash`): a
    # tabela não tem unique em `fileloc` (índice grande demais para o MySQL), e
    # o md5 na PK é o jeito de o MODELO impor a unicidade. Com id aleatório o
    # ON CONFLICT nunca dispararia e a deduplicação deixaria de ser atômica.
    assert "ON CONFLICT (id) DO NOTHING" in sql
    assert psycopg2["params"][0][0] == hashlib.md5(b"/dags/A.py").hexdigest()
    assert len(psycopg2["params"][0][0]) == 32                    # cabe no VARCHAR(32)


def test_senha_com_caractere_especial_e_decodificada(factory, psycopg2, monkeypatch):
    """`@` na senha vem como `%40` na URL: sem o unquote a conexão falharia."""
    _ambiente(monkeypatch)
    factory._solicitar_reparse(["/dags/A.py"])
    kw = psycopg2["conexoes"][0]
    assert kw["password"] == "s@nha" and kw["user"] == "airflow"
    assert kw["host"] == "postgres" and kw["port"] == 5432 and kw["dbname"] == "airflow"
    # Os dois tetos cobrem coisas diferentes: `connect_timeout` limita o aperto
    # de mão (metastore caído), `statement_timeout` limita o comando já
    # conectado (lock na tabela) — sem o segundo, o INSERT penduraria sem prazo
    # e o log da geração ficaria órfão em RUNNING.
    assert kw["connect_timeout"] == 10
    assert "statement_timeout=15000" in kw["options"]


def test_le_tambem_a_variavel_antiga(factory, psycopg2, monkeypatch):
    _ambiente(monkeypatch, chave="AIRFLOW__CORE__SQL_ALCHEMY_CONN")
    factory._solicitar_reparse(["/dags/A.py"])
    assert len(psycopg2["conexoes"]) == 1


def test_metastore_que_nao_e_postgres_nao_tenta(factory, psycopg2, monkeypatch):
    """A fila de prioridade é do Postgres. Em SQLite (ou sem a variável) a
    função sai calada — não é erro, é ausência do recurso."""
    _ambiente(monkeypatch, conn="sqlite:////opt/airflow/airflow.db")
    factory._solicitar_reparse(["/dags/A.py"])
    _ambiente(monkeypatch, conn=None)
    factory._solicitar_reparse(["/dags/A.py"])
    assert psycopg2["conexoes"] == []


def test_lista_vazia_nao_abre_conexao(factory, psycopg2, monkeypatch):
    _ambiente(monkeypatch)
    for vazio in ([], None, ["", None]):
        factory._solicitar_reparse(vazio)
    assert psycopg2["conexoes"] == []


def test_erro_num_arquivo_nao_impede_os_demais(factory, psycopg2, monkeypatch, capsys):
    """Uma falha no terceiro de oitenta não pode calar os setenta e sete
    seguintes: cada arquivo tem o seu try."""
    _ambiente(monkeypatch)

    class _CursorRuim(_Cursor):
        def execute(self, sql, params=None):
            if params and params[1].endswith("B.py"):
                raise RuntimeError("deadlock detected")
            super().execute(sql, params)

    monkeypatch.setattr(_Conexao, "cursor", lambda self: _CursorRuim(self.registro))
    factory._solicitar_reparse(["/dags/A.py", "/dags/B.py", "/dags/C.py"])
    assert [p[1] for p in psycopg2["params"]] == ["/dags/A.py", "/dags/C.py"]
    saida = capsys.readouterr().out
    assert "/dags/B.py" in saida and "2 arquivo(s)" in saida
    assert psycopg2["abertas"][0].fechada is True


def test_ancora_falha_no_banco_nao_derruba_a_geracao(factory, psycopg2, monkeypatch, capsys):
    """⛔ Âncora do best-effort. O arquivo da DAG JÁ foi gravado quando esta
    função roda: uma exceção aqui abortaria a geração do lote inteiro por causa
    de um empurrão que o scheduler dispensa — ele leria o arquivo na varredura
    seguinte de qualquer forma."""
    _ambiente(monkeypatch)
    psycopg2["erro"] = RuntimeError("could not connect to server")
    factory._solicitar_reparse(["/dags/A.py"])      # não levanta
    assert "reparse nao solicitado" in capsys.readouterr().out


def test_ancora_sem_psycopg2_tambem_nao_derruba(factory, monkeypatch, capsys):
    """O import é dentro do try de propósito: ambiente sem o driver (ou com o
    metastore em outro banco) não pode quebrar a publicação."""
    monkeypatch.setenv("AIRFLOW__DATABASE__SQL_ALCHEMY_CONN", CONN)
    monkeypatch.setitem(sys.modules, "psycopg2", None)   # `import` levanta ImportError
    factory._solicitar_reparse(["/dags/A.py"])
    assert "reparse nao solicitado" in capsys.readouterr().out


# ── a fiação, rodando gerar_dags de verdade ─────────────────────────────────
# Um teste que lê o FONTE por substring fica verde com a fiação quebrada: mover
# a chamada para dentro do laço (as centenas de conexões que a adaptação existe
# para evitar) não muda contagem nem ordem do texto. Aqui roda-se a geração
# inteira, com o arnês de tests/test_dag_factory_pendente_publicacao.py.

@pytest.fixture
def geracao(monkeypatch):
    """(rodar, chamadas) — `rodar(conf)` executa `gerar_dags` e devolve o que
    foi pedido de reparse, em ordem."""
    from tests.test_dag_factory_pendente_publicacao import _rodar

    chamadas: list[list[str]] = []

    def _rodar_com(factory, tmp_path, conf=None):
        monkeypatch.setattr(factory, "_solicitar_reparse",
                            lambda filelocs: chamadas.append(list(filelocs)))
        _rodar(factory, monkeypatch, tmp_path, conf=conf)
        return chamadas
    return _rodar_com


def test_a_geracao_pede_o_reparse_do_que_gravou(factory, geracao, tmp_path):
    """Sem alvo (regeração em massa): um pedido só, no fim, com os arquivos
    gravados — e cada um existe mesmo no disco."""
    chamadas = geracao(factory, tmp_path)
    assert len(chamadas) == 1, f"esperado UM pedido para o lote, veio {len(chamadas)}"
    (lote,) = chamadas
    assert lote and all(Path(f).is_file() for f in lote), lote
    assert all(f.endswith(".py") for f in lote)


def test_o_alvo_do_clique_fura_a_fila_na_hora(factory, geracao, tmp_path):
    """⛔ Âncora. A SP de pendentes é GLOBAL: o clique "Gerar DAG" de um
    pipeline entra num lote que pode ter dezenas de pendentes de terceiros. Se
    o pedido dele só saísse no fim, ficaria esperando a geração de todos —
    justamente o clique que a UI está esperando para confirmar a ativação."""
    chamadas = geracao(factory, tmp_path, conf={"pipeline_name": "PIPE_PEND",
                                                "aguardar_ativacao": True})
    # o alvo sai sozinho, no seu próprio pedido, antes do fechamento do lote
    assert chamadas[0] == [c for c in chamadas[0] if c.endswith("PIPE_PEND.py")]
    assert len(chamadas[0]) == 1 and Path(chamadas[0][0]).is_file()
