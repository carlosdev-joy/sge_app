"""
Testes do módulo Cópia de Dados: compilador (services/copy_sql.py) e router
(api/routers/copias.py).

O compilador é função pura (sem I/O) — testado direto. O router é exercido
pelo TestClient do conftest, com get_db_conn/get_airflow_client mockados em
routers.copias e a autenticação sobrescrita via dependency_overrides (mesmo
padrão de test_pipelines_dias_horarios_mes.py).
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Replica o mock de pyodbc do conftest (garante o import de api.main mesmo se
# este arquivo for coletado antes do conftest configurar o ambiente).
if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_pipelines_*)

from deps import PERM_EDITAR, PERM_EXECUTAR, get_current_user
from services.copy_sql import (
    compile_job, compile_transform, quote_ident, quote_literal, validate_sql_expr,
)


# ═════════════════════════ compilador copy_sql ══════════════════════════════

def test_pad_condicional_j_f_gera_case_exato():
    """Caso canônico da spec: CNPJ (J→14) / CPF (F→11) com zeros à esquerda."""
    tr = {"tipo": "pad_condicional", "campo_condicao": "tipo_pessoa",
          "casos": [{"valor": "J", "tamanho": 14}, {"valor": "F", "tamanho": 11}]}
    expr = compile_transform("cod_pessoa", tr)
    assert expr == (
        "CASE WHEN [tipo_pessoa] = 'J' THEN RIGHT(REPLICATE('0', 14) + "
        "LTRIM(RTRIM(CAST([cod_pessoa] AS VARCHAR(50)))), 14) "
        "WHEN [tipo_pessoa] = 'F' THEN RIGHT(REPLICATE('0', 11) + "
        "LTRIM(RTRIM(CAST([cod_pessoa] AS VARCHAR(50)))), 11) "
        "ELSE [cod_pessoa] END"
    )


def test_quote_literal_escapa_aspas_simples():
    assert quote_literal("O'Brien") == "'O''Brien'"
    # Valor malicioso num caso do pad_condicional sai escapado (sem quebra do literal)
    tr = {"tipo": "pad_condicional", "campo_condicao": "tp",
          "casos": [{"valor": "J'; DROP TABLE x --", "tamanho": 5}]}
    expr = compile_transform("col", tr)
    assert "= 'J''; DROP TABLE x --'" in expr


def test_quote_ident_rejeita_colchete_e_aspas():
    with pytest.raises(ValueError):
        quote_ident("col]x")
    with pytest.raises(ValueError):
        quote_ident("col'x")
    with pytest.raises(ValueError):
        quote_ident("col; DROP TABLE x")
    with pytest.raises(ValueError):
        quote_ident("")


def test_quote_ident_aceita_acentos_e_simbolos_da_allowlist():
    assert quote_ident("Descrição do Item") == "[Descrição do Item]"
    assert quote_ident("col_2$#@") == "[col_2$#@]"


@pytest.mark.parametrize("expr_ruim,motivo", [
    ("1; DROP TABLE x", ";"),
    ("valor -- comentario", "--"),
    ("valor /* cmt */", "/*"),
    ("DELETE FROM x WHERE 1=1", "DELETE"),
    ("EXEC xp_cmdshell", "EXEC"),
    ("SELECT * INTO y", "INTO"),
])
def test_sql_livre_rejeita_perigosos(expr_ruim, motivo):
    with pytest.raises(ValueError):
        validate_sql_expr(expr_ruim)
    with pytest.raises(ValueError):
        compile_transform("col", {"tipo": "sql", "expressao": expr_ruim})


def test_sql_livre_rejeita_expressao_gigante():
    with pytest.raises(ValueError):
        validate_sql_expr("A" * 2001)


def test_sql_livre_aceita_expressao_valida():
    expr = compile_transform("col", {"tipo": "sql",
                                     "expressao": "COALESCE([col], 'N/D')"})
    assert expr == "COALESCE([col], 'N/D')"


def test_cast_allowlist():
    assert compile_transform("v", {"tipo": "cast", "tipo_sql": "DECIMAL(10, 2)"}) \
        == "CAST([v] AS DECIMAL(10,2))"
    assert compile_transform("v", {"tipo": "cast", "tipo_sql": "varchar(20)"}) \
        == "CAST([v] AS VARCHAR(20))"
    for ruim in ("VARCHAR(MAX)", "TEXT", "XML", "VARBINARY(10)", "DECIMAL(10)", ""):
        with pytest.raises(ValueError):
            compile_transform("v", {"tipo": "cast", "tipo_sql": ruim})


def test_transforms_simples():
    assert compile_transform("a", {"tipo": "trim"}) == "LTRIM(RTRIM([a]))"
    assert compile_transform("a", {"tipo": "upper"}) == "UPPER([a])"
    assert compile_transform("a", {"tipo": "lower"}) == "LOWER([a])"
    assert compile_transform("a", {"tipo": "pad_fixo", "tamanho": 8}) \
        == "RIGHT(REPLICATE('0', 8) + LTRIM(RTRIM(CAST([a] AS VARCHAR(50)))), 8)"
    assert compile_transform("a", {"tipo": "substring", "inicio": 2, "tamanho": 5}) \
        == "SUBSTRING([a], 2, 5)"
    assert compile_transform("a", None) == "[a]"


def test_transform_tipo_desconhecido_e_tamanho_invalido():
    with pytest.raises(ValueError):
        compile_transform("a", {"tipo": "regex"})
    with pytest.raises(ValueError):
        compile_transform("a", {"tipo": "pad_fixo", "tamanho": 0})
    with pytest.raises(ValueError):
        compile_transform("a", {"tipo": "pad_fixo", "tamanho": "quatorze"})


def _job_base(**ov):
    base = {
        "src_database": "DB_ORIGEM", "src_schema": "dbo", "src_table": "Clientes",
        "colunas": [
            {"origem": "id", "destino": "id", "transform": None},
            {"origem": "nome_cliente", "destino": "nome", "transform": {"tipo": "trim"}},
        ],
    }
    base.update(ov)
    return base


def test_compile_job_sem_filtro():
    out = compile_job(_job_base())
    assert out["select_sql"] == (
        "SELECT [id] AS [id], LTRIM(RTRIM([nome_cliente])) AS [nome] "
        "FROM [DB_ORIGEM].[dbo].[Clientes] WITH (NOLOCK)")
    assert out["count_sql"] == \
        "SELECT COUNT_BIG(*) FROM [DB_ORIGEM].[dbo].[Clientes] WITH (NOLOCK)"
    assert out["dst_columns"] == ["id", "nome"]
    assert "ORDER BY" not in out["select_sql"].upper()


def test_compile_job_com_filtro():
    out = compile_job(_job_base(src_filtro="ativo = 1 AND uf = 'SP'"))
    assert out["select_sql"].endswith(" WHERE (ativo = 1 AND uf = 'SP')")
    assert out["count_sql"] == ("SELECT COUNT_BIG(*) FROM [DB_ORIGEM].[dbo].[Clientes] "
                                "WITH (NOLOCK) WHERE (ativo = 1 AND uf = 'SP')")


def test_compile_job_filtro_malicioso_rejeitado():
    with pytest.raises(ValueError):
        compile_job(_job_base(src_filtro="1=1; DROP TABLE x"))
    with pytest.raises(ValueError):
        compile_job(_job_base(src_filtro="1=1 UNION SELECT senha INTO y"))


def test_compile_job_rejeicoes():
    with pytest.raises(ValueError):        # identificador inválido
        compile_job(_job_base(src_table="Clientes]; DROP"))
    with pytest.raises(ValueError):        # colunas vazias
        compile_job(_job_base(colunas=[]))
    with pytest.raises(ValueError):        # origem ausente
        compile_job(_job_base(colunas=[{"destino": "x", "transform": None}]))
    with pytest.raises(ValueError):        # destino duplicado
        compile_job(_job_base(colunas=[
            {"origem": "a", "destino": "x", "transform": None},
            {"origem": "b", "destino": "X", "transform": None},
        ]))
    with pytest.raises(ValueError):        # src_database obrigatório
        compile_job(_job_base(src_database=""))


def test_compile_job_aceita_colunas_json_inteiro():
    """compile_job aceita o próprio dict {"colunas": [...]} do colunas_json."""
    out = compile_job(_job_base(colunas={"colunas": [
        {"origem": "id", "destino": "id", "transform": None}]}))
    assert out["dst_columns"] == ["id"]


# ═════════════════════════ router /copias ═══════════════════════════════════

def _mock_cursor():
    cur = MagicMock()
    cur.description = []
    return cur


def _mock_conn(cur):
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


class _FakeResp:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    @property
    def is_success(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


class _FakeAirflowClient:
    """Stub do httpx.AsyncClient de get_airflow_client (async context manager)."""

    def __init__(self, post_resp=None, get_resp=None, get_exc=None):
        self.post_calls: list = []
        self.get_calls: list = []
        self._post_resp = post_resp or _FakeResp(200, {})
        self._get_resp = get_resp or _FakeResp(200, {})
        self._get_exc = get_exc  # simula falha de rede no GET (best-effort)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kw):
        self.post_calls.append((url, kw))
        return self._post_resp

    async def get(self, url, **kw):
        self.get_calls.append((url, kw))
        if self._get_exc is not None:
            raise self._get_exc
        return self._get_resp


@pytest.fixture
def auth_operador(app):
    """Usuário autenticado com permissões de edição e execução (override da
    dependency — require_perm resolve get_current_user por baixo)."""
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "TESTER", "perfil": "admin",
        "permissoes": [PERM_EDITAR, PERM_EXECUTAR],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _body_copia(**ov):
    base = {
        "nome": "Copia Clientes",
        "src_conn_id": "SQL_ORIGEM", "src_database": "DB_A", "src_table": "Clientes",
        "dst_conn_id": "SQL_DESTINO", "dst_database": "DB_B", "dst_table": "Clientes",
        "colunas": [{"origem": "id", "destino": "id", "transform": None}],
    }
    base.update(ov)
    return base


def test_router_copias_registrado(client):
    """Endpoints de /copias devem aparecer no schema OpenAPI."""
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json().get("paths", {})
    for p in ("/copias", "/copias/preview", "/copias/exec/{exec_id}",
              "/copias/introspect/databases"):
        assert p in paths, f"rota {p} não registrada em api/main.py"


def test_post_copias_422_sem_nome(client, auth_operador):
    r = client.post("/copias", json=_body_copia(nome=""))
    assert r.status_code == 422
    assert "nome" in r.json()["detail"]


def test_post_copias_422_sem_conn(client, auth_operador):
    r = client.post("/copias", json=_body_copia(src_conn_id=""))
    assert r.status_code == 422
    assert "src_conn_id" in r.json()["detail"]


def test_post_copias_422_sem_colunas(client, auth_operador):
    r = client.post("/copias", json=_body_copia(colunas=[]))
    assert r.status_code == 422
    assert "colunas" in r.json()["detail"]


def test_post_copias_422_streams_fora_da_faixa(client, auth_operador):
    r = client.post("/copias", json=_body_copia(streams=9))
    assert r.status_code == 422
    r = client.post("/copias", json=_body_copia(batch_size=999))
    assert r.status_code == 422


def test_post_copias_422_coluna_invalida(client, auth_operador):
    r = client.post("/copias", json=_body_copia(
        colunas=[{"origem": "id]; DROP", "destino": "id", "transform": None}]))
    assert r.status_code == 422


def test_post_copias_422_particao_fora_das_colunas_de_destino(client, auth_operador):
    """Finding 1: particao_coluna referencia o nome de DESTINO (alias do select
    compilado) — precisa estar entre as colunas de destino incluídas."""
    r = client.post("/copias", json=_body_copia(particao_coluna="nao_incluida"))
    assert r.status_code == 422
    assert "particao_coluna" in r.json()["detail"]
    # nome de ORIGEM de uma coluna renomeada também não vale (contrato: destino)
    r = client.post("/copias", json=_body_copia(
        colunas=[{"origem": "nome_cliente", "destino": "nome", "transform": None}],
        particao_coluna="nome_cliente"))
    assert r.status_code == 422
    assert "particao_coluna" in r.json()["detail"]


def test_post_copias_aceita_particao_pelo_nome_de_destino(client, auth_operador):
    """particao_coluna com o nome de DESTINO (case-insensitive) passa a validação."""
    cur = _mock_cursor()
    cur.fetchone.side_effect = [None, (10,)]  # nome livre → INSERT OUTPUT id
    with patch("routers.copias.get_db_conn", return_value=_mock_conn(cur)):
        r = client.post("/copias", json=_body_copia(
            colunas=[{"origem": "nome_cliente", "destino": "nome", "transform": None}],
            particao_coluna="NOME"))
    assert r.status_code == 200
    assert r.json()["id"] == 10


def test_post_copias_422_origem_igual_destino(client, auth_operador):
    """Finding 2: origem == destino (comparação case-insensitive) → 422 com
    mensagem sobre o risco de truncar a própria origem."""
    r = client.post("/copias", json=_body_copia(
        dst_conn_id="sql_origem", dst_database="db_a",
        dst_schema="DBO", dst_table="clientes"))
    assert r.status_code == 422
    assert "origem e destino" in r.json()["detail"]
    assert "truncar" in r.json()["detail"]
    # basta UM campo diferente para deixar de ser a mesma tabela
    cur = _mock_cursor()
    cur.fetchone.side_effect = [None, (11,)]
    with patch("routers.copias.get_db_conn", return_value=_mock_conn(cur)):
        r = client.post("/copias", json=_body_copia(
            dst_conn_id="sql_origem", dst_database="db_a", dst_table="Clientes_novo"))
    assert r.status_code == 200


def test_post_copias_unicidade_do_nome_considera_apenas_ativas(client, auth_operador):
    """Finding 4: a checagem de nome único filtra ativo = 1 — o soft delete
    libera o nome para uma nova cópia (índice filtrado UX_copy_job_nome)."""
    cur = _mock_cursor()
    # SELECT de unicidade (só ativas) não encontra → INSERT OUTPUT id
    cur.fetchone.side_effect = [None, (12,)]
    with patch("routers.copias.get_db_conn", return_value=_mock_conn(cur)):
        r = client.post("/copias", json=_body_copia())
    assert r.status_code == 200
    selects = [str(c.args[0]) for c in cur.execute.call_args_list
               if c.args and "SELECT id FROM dbo.etl_copy_job" in str(c.args[0])
               and "nome = ?" in str(c.args[0])]
    assert selects, "esperava SELECT de unicidade do nome"
    assert "ativo = 1" in selects[0], \
        "a unicidade do nome deve considerar apenas cópias ativas (ativo = 1)"


def test_post_copias_422_nome_duplicado_entre_ativas(client, auth_operador):
    cur = _mock_cursor()
    cur.fetchone.side_effect = [(5,)]  # já existe cópia ATIVA com o nome
    with patch("routers.copias.get_db_conn", return_value=_mock_conn(cur)):
        r = client.post("/copias", json=_body_copia())
    assert r.status_code == 422
    assert "nome" in r.json()["detail"]


def test_get_copias_degrada_sem_tabela(client, auth_operador):
    """Tabela da migration 052 ausente → data [] (nunca 500)."""
    with patch("routers.copias.get_db_conn",
               side_effect=Exception("Invalid object name 'dbo.etl_copy_job'")):
        r = client.get("/copias")
    assert r.status_code == 200
    assert r.json() == {"data": []}


def _job_row(**ov):
    """Linha de dbo.etl_copy_job como o SELECT do /executar devolve:
    (id, nome, src_conn_id, src_database, src_schema, src_table,
     dst_conn_id, dst_database, dst_schema, dst_table)."""
    base = {"id": 1, "nome": "Copia Clientes",
            "src_conn_id": "SQL_ORIGEM", "src_database": "DB_A",
            "src_schema": "dbo", "src_table": "Clientes",
            "dst_conn_id": "SQL_DESTINO", "dst_database": "DB_B",
            "dst_schema": "dbo", "dst_table": "Clientes"}
    base.update(ov)
    return (base["id"], base["nome"], base["src_conn_id"], base["src_database"],
            base["src_schema"], base["src_table"], base["dst_conn_id"],
            base["dst_database"], base["dst_schema"], base["dst_table"])


def test_executar_cria_exec_e_chama_airflow(client, auth_operador):
    cur = _mock_cursor()
    # job existe → INSERT atômico devolve OUTPUT INSERTED.id
    cur.fetchone.side_effect = [_job_row(), (77,)]
    fake = _FakeAirflowClient(post_resp=_FakeResp(200, {"dag_run_id": "x"}))
    with patch("routers.copias.get_db_conn", return_value=_mock_conn(cur)), \
         patch("routers.copias.get_airflow_client", return_value=fake):
        r = client.post("/copias/1/executar")
    assert r.status_code == 200
    body = r.json()
    assert body["exec_id"] == 77
    assert body["status"] == "pendente"
    assert body["dag_run_id"].startswith("copy_77_")
    assert len(fake.post_calls) == 1
    url, kw = fake.post_calls[0]
    assert url == "/api/v1/dags/etl_copy_exec/dagRuns"
    assert kw["json"]["conf"] == {"exec_id": 77}
    # antes de disparar, consultou se a DAG está pausada (best-effort)
    assert any(u == "/api/v1/dags/etl_copy_exec" for u, _ in fake.get_calls)


def test_executar_insert_atomico_guarda_na_mesma_instrucao(client, auth_operador):
    """Finding 6: a guarda de exec ativa é o próprio INSERT — INSERT ... SELECT
    ... WHERE NOT EXISTS na MESMA instrução (sem SELECT prévio separado)."""
    cur = _mock_cursor()
    cur.fetchone.side_effect = [_job_row(), (77,)]
    fake = _FakeAirflowClient(post_resp=_FakeResp(200, {}))
    with patch("routers.copias.get_db_conn", return_value=_mock_conn(cur)), \
         patch("routers.copias.get_airflow_client", return_value=fake):
        r = client.post("/copias/1/executar")
    assert r.status_code == 200
    inserts = [str(c.args[0]) for c in cur.execute.call_args_list
               if c.args and "INSERT INTO dbo.etl_copy_exec" in str(c.args[0])]
    assert len(inserts) == 1, "esperava exatamente 1 INSERT em etl_copy_exec"
    sql = inserts[0]
    assert "OUTPUT INSERTED.id" in sql
    assert "WHERE NOT EXISTS" in sql, \
        "a guarda de exec ativa deve estar NA MESMA instrução do INSERT"
    assert "copy_job_id = ? AND status IN (?, ?, ?)" in sql


def test_executar_409_com_exec_ativa(client, auth_operador):
    cur = _mock_cursor()
    # INSERT atômico não insere (0 linhas → OUTPUT vazio) → 409; o SELECT
    # seguinte é só informativo (id/status da exec ativa p/ a mensagem).
    cur.fetchone.side_effect = [_job_row(), None, (55, "executando")]
    fake = _FakeAirflowClient()
    with patch("routers.copias.get_db_conn", return_value=_mock_conn(cur)), \
         patch("routers.copias.get_airflow_client", return_value=fake):
        r = client.post("/copias/1/executar")
    assert r.status_code == 409
    assert "55" in r.json()["detail"]
    assert fake.post_calls == []  # não chega a acionar o Airflow


def test_executar_422_origem_igual_destino(client, auth_operador):
    """Finding 2: job com origem == destino (case-insensitive) não executa."""
    cur = _mock_cursor()
    cur.fetchone.side_effect = [_job_row(
        dst_conn_id="sql_origem", dst_database="db_a",
        dst_schema="DBO", dst_table="clientes")]
    fake = _FakeAirflowClient()
    with patch("routers.copias.get_db_conn", return_value=_mock_conn(cur)), \
         patch("routers.copias.get_airflow_client", return_value=fake):
        r = client.post("/copias/1/executar")
    assert r.status_code == 422
    assert "origem e destino" in r.json()["detail"]
    assert fake.post_calls == []


def test_executar_409_dag_pausada(client, auth_operador):
    """Finding 3: DAG etl_copy_exec pausada no Airflow → 409 antes de disparar
    (sem criar execução), com mensagem orientando a despausar."""
    cur = _mock_cursor()
    cur.fetchone.side_effect = [_job_row()]
    fake = _FakeAirflowClient(get_resp=_FakeResp(200, {"is_paused": True}))
    with patch("routers.copias.get_db_conn", return_value=_mock_conn(cur)), \
         patch("routers.copias.get_airflow_client", return_value=fake):
        r = client.post("/copias/1/executar")
    assert r.status_code == 409
    assert "pausada" in r.json()["detail"]
    assert "etl_copy_exec" in r.json()["detail"]
    assert fake.post_calls == []  # não dispara nem cria a execução
    inserts = [str(c.args[0]) for c in cur.execute.call_args_list
               if c.args and "INSERT" in str(c.args[0])]
    assert inserts == []


def test_executar_segue_se_consulta_da_dag_falhar(client, auth_operador):
    """Finding 3 (best-effort): falha de rede ao consultar a DAG não bloqueia
    o disparo — o trigger segue normalmente."""
    cur = _mock_cursor()
    cur.fetchone.side_effect = [_job_row(), (79,)]
    fake = _FakeAirflowClient(post_resp=_FakeResp(200, {}),
                              get_exc=ConnectionError("rede fora"))
    with patch("routers.copias.get_db_conn", return_value=_mock_conn(cur)), \
         patch("routers.copias.get_airflow_client", return_value=fake):
        r = client.post("/copias/1/executar")
    assert r.status_code == 200
    assert r.json()["exec_id"] == 79
    assert len(fake.post_calls) == 1


def test_executar_502_se_airflow_falha_marca_erro(client, auth_operador):
    cur = _mock_cursor()
    cur.fetchone.side_effect = [_job_row(), (78,)]
    fake = _FakeAirflowClient(post_resp=_FakeResp(500, text="boom"))
    with patch("routers.copias.get_db_conn", return_value=_mock_conn(cur)), \
         patch("routers.copias.get_airflow_client", return_value=fake):
        r = client.post("/copias/1/executar")
    assert r.status_code == 502
    # a execução foi marcada como erro (UPDATE ... status = 'erro')
    updates = [str(c.args[0]) for c in cur.execute.call_args_list
               if c.args and "status = 'erro'" in str(c.args[0])]
    assert updates, "esperava UPDATE marcando a execução como 'erro'"


def test_cancelar_muda_status_para_cancelando(client, auth_operador):
    cur = _mock_cursor()
    cur.fetchone.side_effect = [("executando", "copy_77_x")]
    with patch("routers.copias.get_db_conn", return_value=_mock_conn(cur)):
        r = client.post("/copias/exec/77/cancelar")
    assert r.status_code == 200
    assert r.json() == {"id": 77, "status": "cancelando"}
    updates = [str(c.args[0]) for c in cur.execute.call_args_list
               if c.args and "cancelando" in str(c.args[0])]
    assert updates, "esperava UPDATE para status 'cancelando'"


def test_cancelar_pendente_sem_dagrun_iniciado_finaliza_direto(client, auth_operador):
    """Finding 3: exec 'pendente' com dagRun ainda na fila (queued) é
    finalizada direto como 'cancelado' (concluido_em=GETDATE())."""
    cur = _mock_cursor()
    cur.rowcount = 1
    cur.fetchone.side_effect = [("pendente", "copy_10_x")]
    fake = _FakeAirflowClient(get_resp=_FakeResp(200, {"state": "queued"}))
    with patch("routers.copias.get_db_conn", return_value=_mock_conn(cur)), \
         patch("routers.copias.get_airflow_client", return_value=fake):
        r = client.post("/copias/exec/10/cancelar")
    assert r.status_code == 200
    assert r.json() == {"id": 10, "status": "cancelado"}
    assert any("/dagRuns/copy_10_x" in u for u, _ in fake.get_calls)
    updates = [str(c.args[0]) for c in cur.execute.call_args_list
               if c.args and "'cancelado'" in str(c.args[0])]
    assert updates and "concluido_em = GETDATE()" in updates[0]


def test_cancelar_pendente_com_dagrun_rodando_vira_cancelando(client, auth_operador):
    """Finding 3: se o dagRun já está running, mantém o fluxo 'cancelando'
    (a DAG observa o status e finaliza como 'cancelado')."""
    cur = _mock_cursor()
    cur.fetchone.side_effect = [("pendente", "copy_11_x")]
    fake = _FakeAirflowClient(get_resp=_FakeResp(200, {"state": "running"}))
    with patch("routers.copias.get_db_conn", return_value=_mock_conn(cur)), \
         patch("routers.copias.get_airflow_client", return_value=fake):
        r = client.post("/copias/exec/11/cancelar")
    assert r.status_code == 200
    assert r.json() == {"id": 11, "status": "cancelando"}


def test_cancelar_nao_reabre_execucao_concluida(client, auth_operador):
    cur = _mock_cursor()
    cur.fetchone.side_effect = [("concluido", "copy_77_x")]
    with patch("routers.copias.get_db_conn", return_value=_mock_conn(cur)):
        r = client.post("/copias/exec/77/cancelar")
    assert r.status_code == 200
    assert r.json()["status"] == "concluido"


def test_exec_progresso_404_inexistente(client, auth_operador):
    cur = _mock_cursor()
    cur.fetchone.side_effect = [None]
    with patch("routers.copias.get_db_conn", return_value=_mock_conn(cur)):
        r = client.get("/copias/exec/999")
    assert r.status_code == 404


def test_copias_sem_auth_401(client):
    assert client.get("/copias").status_code == 401
    assert client.post("/copias", json={}).status_code == 401
    assert client.post("/copias/1/executar").status_code == 401
