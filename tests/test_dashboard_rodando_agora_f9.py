"""
F9 da spec `docs/spec-malha-execucao.md` §9.8 — a correção do `jobs_ok` do
painel **"Rodando agora"** do Dashboard, executada contra o SQL Server.

O defeito, e por que ele entra nesta PR
───────────────────────────────────────
`api/routers/dashboard.py` montava a CTE assim:

    SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END) AS jobs_ok
    FROM dbo.etl_job_execution
    WHERE status='RUNNING'

As duas condições nunca são verdadeiras na MESMA linha. `jobs_ok` era 0 em toda
execução, `total_jobs` desabava para `jobs_running` (o `COUNT(*)` só via os jobs
de pé) e a barra ficava em 0% — na tela mais vista do produto, desde sempre, em
produção. Ele entra na mesma PR que extrai `ui/Progress` porque é o **molde**
que a camada de corrida da malha copiaria: uma barra derivada de um agregado
que ninguém conferiu contra o banco.

Por que ao vivo, e não com dublê
────────────────────────────────
O que se corrige aqui É a semântica de um `GROUP BY`. Um cursor falso prova que
o texto foi emitido; quem decide se `SUM(CASE …)` enxerga as linhas certas é o
SQL Server. E a prova precisa mostrar as DUAS consultas lado a lado, na mesma
transação e sobre as mesmas linhas: sem a antiga rodando junto, um teste que
afirma `jobs_ok == 2` ficaria verde num cenário que nunca teve o defeito.

⚠️ **Como rodar** (o bloco ao vivo pula sem a variável — a senha nunca mora no
repositório):

    ORQ_TEST_MSSQL_PASSWORD='…' python3 -m pytest tests/test_dashboard_rodando_agora_f9.py

⚠️ **Nada é commitado**: cada teste abre a própria transação, monta o cenário,
pergunta e dá `ROLLBACK` — e o teardown CONFERE, depois do rollback, que nenhuma
linha com o prefixo do teste sobreviveu.

⚠️ **Nenhuma conta de tempo em Python** (Decisão 10): todo instante do cenário
entra como `DATEADD(...)` sobre `GETDATE()`. O SQL Server do dev está ~3 h à
frente do worker.

⚠️ **Placeholder por árvore**: `api/` fala pyodbc (`?`) e o driver desta bancada
é o pymssql (`%s`), que é o de `dags/`. O texto executado ao vivo é o MESMO de
produção; a única adaptação é a troca do único `?` por `%s` no cenário com
filtro de projeto — e ela só é feita depois de o teste conferir que existe
exatamente **um** placeholder, para que a troca não possa ser ambígua.
"""
from __future__ import annotations

import uuid

import pytest

from routers.dashboard import _sql_executando_agora
from tests.test_dependencias_f6_vivo import _conectar

PREFIXO = "ZZ_F9DASH_"

# A consulta COMO ESTAVA em produção. Ela é executada lado a lado com a nova,
# na mesma transação: é ela que prova que o defeito existe NESTE cenário, e não
# só na descrição do commit.
SQL_ANTIGO = """
    WITH runs AS (
        SELECT execution_id, project, pipeline, MIN(start_time) AS inicio,
            COUNT(*) AS total_jobs,
            SUM(CASE WHEN status='RUNNING' THEN 1 ELSE 0 END) AS jobs_running,
            SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END) AS jobs_ok
        FROM dbo.etl_job_execution
        WHERE status='RUNNING'
        GROUP BY execution_id, project, pipeline
    )
    SELECT TOP 10 execution_id, project, pipeline, inicio,
        total_jobs, jobs_running, jobs_ok,
        DATEDIFF(SECOND, inicio, GETDATE()) AS elapsed_seconds
    FROM runs ORDER BY inicio DESC
"""


# ═══════════ 1. o CONTRATO do texto — sem banco, roda em toda máquina ═══════

def _norm(sql: str) -> str:
    """Tira os comentários `--` ANTES de colapsar o espaço.

    Sem isso a asserção de ausência (`WHERE` fora do agregado) seria satisfeita
    ou quebrada por texto de comentário — o teste passaria a medir a prosa em
    vez do statement."""
    sem_comentario = "\n".join(linha.split("--")[0] for linha in sql.splitlines())
    return " ".join(sem_comentario.split())


def test_a_agregacao_saiu_de_dentro_do_recorte_de_running():
    """O coração da correção: o `SUM(CASE … 'SUCCESS' …)` não pode mais estar
    no mesmo escopo de um `WHERE status='RUNNING'`. O recorte por status vira
    uma CTE de ENTRADA (`ativos`), e a contagem passa a ver a execução inteira."""
    sql = _norm(_sql_executando_agora(""))
    # a porta de entrada continua sendo o índice por status...
    assert "WITH ativos AS ( SELECT DISTINCT execution_id, project, pipeline" in sql
    assert "WHERE status='RUNNING'" in sql
    # ...e a contagem acontece DEPOIS do JOIN de volta, não dentro do recorte
    corpo_runs = sql.split("runs AS (")[1].split("SELECT TOP 10")[0]
    assert "SUM(CASE WHEN e.status='SUCCESS'" in corpo_runs
    assert "WHERE" not in corpo_runs, (
        "voltou um filtro para dentro do agregado — é exatamente assim que o "
        f"jobs_ok zera: {corpo_runs}")


def test_o_join_de_volta_carrega_pipeline_e_project():
    """`execution_id` é o `ts_nodash` do Airflow e COLIDE entre pipelines
    agendadas no mesmo tick (a razão já documentada na subconsulta de fila,
    migration 027). Um `JOIN` só por `execution_id` somaria os jobs de outro
    pipeline no `total_jobs` — trocaríamos um número mentiroso por outro."""
    sql = _norm(_sql_executando_agora(""))
    assert "a.execution_id = e.execution_id" in sql
    assert "a.pipeline = e.pipeline" in sql
    assert "a.project = e.project" in sql
    assert "GROUP BY e.execution_id, e.project, e.pipeline" in sql


def test_o_filtro_de_projeto_entra_uma_vez_so():
    """pyodbc é POSICIONAL: o endpoint passa `[fp]`, uma lista de um elemento.
    Repetir o `?` nas duas CTEs (o erro natural ao dividir a consulta em duas)
    estouraria em tempo de execução com "parâmetros insuficientes" — e só na
    tela filtrada por projeto, que ninguém abre no smoke."""
    com_filtro = _sql_executando_agora(" AND project = ? ")
    assert com_filtro.count("?") == 1
    # e ele mora na CTE de entrada, que é quem recorta o conjunto
    assert "?" in com_filtro.split("runs AS (")[0]
    assert _sql_executando_agora("").count("?") == 0


# ═══════════ 2. os números, perguntados ao SQL Server ═══════════════════════

class Mundo:
    """Cenário de jobs. Todo instante é `DATEADD` sobre `GETDATE()` — a régua
    do tempo é a do BANCO, nunca a do worker."""

    def __init__(self, conn):
        self.conn = conn
        self.cur = conn.cursor()
        self.suf = uuid.uuid4().hex[:8].upper()
        # `ts_nodash` COMPARTILHADO entre os pipelines do cenário: é a colisão
        # da migration 027, e é ela que o JOIN de três colunas tem de resistir.
        self.execution_id = f"ZZ{self.suf}"

    def n(self, base: str) -> str:
        return f"{PREFIXO}{base}_{self.suf}"

    def job(self, pipeline: str, job: str, status: str, min_atras: int,
            fim_min_atras: int | None = None):
        self.cur.execute(
            "INSERT INTO dbo.etl_job_execution "
            "(execution_id, project, job_name, pipeline, start_time, end_time, "
            " status, task_id) VALUES (%s, %s, %s, %s, "
            " DATEADD(MINUTE, %s, GETDATE()), "
            " CASE WHEN %s IS NULL THEN NULL "
            "      ELSE DATEADD(MINUTE, %s, GETDATE()) END, %s, %s)",
            (self.execution_id, self.n("PROJ"), job, pipeline, -min_atras,
             fim_min_atras, -(fim_min_atras or 0), status, f"t_{job}"))

    def perguntar(self, sql: str, params=None) -> dict:
        """Roda a consulta e indexa por pipeline — só as linhas do cenário."""
        cur = self.conn.cursor()
        cur.execute(sql, params) if params else cur.execute(sql)
        linhas = cur.fetchall()
        return {r[2]: {"total_jobs": r[4], "jobs_running": r[5],
                       "jobs_ok": r[6], "elapsed_seconds": r[7]}
                for r in linhas if str(r[2]).startswith(PREFIXO)}


@pytest.fixture
def mundo():
    conn = _conectar()
    if conn is None:
        pytest.skip("banco dev indisponivel — defina ORQ_TEST_MSSQL_PASSWORD")
    m = Mundo(conn)
    try:
        yield m
    finally:
        conn.rollback()
        # A limpeza é VERIFICADA, não presumida: um ROLLBACK que não
        # acontecesse (autocommit ligado por engano) deixaria jobs de mentira
        # numa base que o time usa para medir comportamento real.
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM dbo.etl_job_execution "
                    "WHERE pipeline LIKE %s", (f"{PREFIXO}%",))
        sobrou = cur.fetchone()[0]
        conn.close()
        assert not sobrou, f"o ROLLBACK deixou {sobrou} job(s) no banco dev"


def _cenario_de_tres_jobs(m: Mundo) -> str:
    """O caso do aceite: 2 de 3 jobs concluídos, o terceiro de pé."""
    p = m.n("PIPE_A")
    m.job(p, "JOB_1", "SUCCESS", 30, 20)
    m.job(p, "JOB_2", "SUCCESS", 20, 10)
    m.job(p, "JOB_3", "RUNNING", 10)
    return p


def test_o_defeito_existe_neste_cenario(mundo):
    """Publicado ANTES da correção, no molde da bancada da F4: sem isto, um
    teste que afirma `2/3` poderia estar verde num cenário que nunca teve o
    problema. O que o operador via era pior que o `0/3 ok` da spec — o
    denominador desabava junto, e a tela dizia **`0/1 ok`**."""
    p = _cenario_de_tres_jobs(mundo)
    antigo = mundo.perguntar(SQL_ANTIGO)[p]
    assert antigo["jobs_ok"] == 0
    assert antigo["total_jobs"] == 1            # e não 3
    assert antigo["total_jobs"] == antigo["jobs_running"]


def test_dois_de_tres_jobs_concluidos_deixam_de_exibir_zero(mundo):
    """O aceite literal da F9: "pipeline com 2 de 3 jobs concluídos deixa de
    exibir 0/3 ok"."""
    p = _cenario_de_tres_jobs(mundo)
    novo = mundo.perguntar(_sql_executando_agora(""))[p]
    assert novo["jobs_ok"] == 2
    assert novo["total_jobs"] == 3
    assert novo["jobs_running"] == 1


def test_a_colisao_de_ts_nodash_nao_mistura_dois_pipelines(mundo):
    """Dois pipelines agendados no mesmo tick compartilham o `execution_id`.
    Com um JOIN só por essa coluna, o pipeline A contaria os 2 jobs do B — e o
    `2/3 ok` viraria `3/5 ok`, número que não corresponde a nada."""
    a = _cenario_de_tres_jobs(mundo)
    b = mundo.n("PIPE_B")
    mundo.job(b, "JOB_1", "SUCCESS", 25, 15)
    mundo.job(b, "JOB_2", "RUNNING", 15)

    r = mundo.perguntar(_sql_executando_agora(""))
    assert r[a] == {**r[a], "total_jobs": 3, "jobs_ok": 2, "jobs_running": 1}
    assert r[b]["total_jobs"] == 2 and r[b]["jobs_ok"] == 1


def test_job_que_falhou_conta_no_total_e_nunca_como_ok(mundo):
    """`total_jobs` é a execução inteira; `jobs_ok` é só `SUCCESS`. Um FAILED
    no meio não pode ser confundido com progresso — "ausência de linha não é
    sucesso" vale igual para presença de linha errada."""
    p = mundo.n("PIPE_C")
    mundo.job(p, "JOB_1", "SUCCESS", 30, 25)
    mundo.job(p, "JOB_2", "FAILED", 25, 20)
    mundo.job(p, "JOB_3", "RUNNING", 20)

    r = mundo.perguntar(_sql_executando_agora(""))[p]
    assert r["total_jobs"] == 3
    assert r["jobs_ok"] == 1
    assert r["jobs_running"] == 1


def test_execucao_que_terminou_nao_aparece_no_rodando_agora(mundo):
    """O painel continua sendo "Rodando agora": a CTE `ativos` é o recorte, e
    tirar o filtro de status do agregado NÃO pode ter alargado a lista para o
    histórico inteiro."""
    vivo = _cenario_de_tres_jobs(mundo)
    morto = mundo.n("PIPE_D")
    mundo.job(morto, "JOB_1", "SUCCESS", 60, 50)
    mundo.job(morto, "JOB_2", "SUCCESS", 50, 40)

    r = mundo.perguntar(_sql_executando_agora(""))
    assert vivo in r
    assert morto not in r


def test_o_decorrido_passa_a_ser_o_da_execucao_inteira(mundo):
    """Consequência declarada da correção, e ela é uma melhora: `inicio` era o
    começo do primeiro job AINDA DE PÉ, então o "há X rodando" da tela pulava
    para frente a cada job que terminava. Agora é o começo da execução — que é
    o que a frase sempre disse estar mostrando.

    A asserção é de GEOMETRIA, não de relógio de parede: o decorrido tem de
    corresponder ao job mais ANTIGO (30 min), não ao que está de pé (10 min)."""
    p = _cenario_de_tres_jobs(mundo)
    novo = mundo.perguntar(_sql_executando_agora(""))[p]["elapsed_seconds"]
    antigo = mundo.perguntar(SQL_ANTIGO)[p]["elapsed_seconds"]
    assert 29 * 60 <= novo <= 31 * 60, novo
    assert 9 * 60 <= antigo <= 11 * 60, antigo


def test_o_filtro_de_projeto_continua_recortando(mundo):
    """O `where_proj` mudou de lugar (foi para a CTE de entrada). Se ele tivesse
    ficado de fora, a tela filtrada por projeto passaria a listar todo mundo.

    ⚠️ Troca de placeholder por árvore: `api/` fala pyodbc (`?`), esta bancada
    fala pymssql (`%s`). A troca só acontece depois de conferir que existe UM
    placeholder — o teste de contrato acima guarda essa contagem."""
    p = _cenario_de_tres_jobs(mundo)
    sql = _sql_executando_agora(" AND project = ? ")
    assert sql.count("?") == 1
    sql = sql.replace("?", "%s")

    do_projeto = mundo.perguntar(sql, (mundo.n("PROJ"),))
    assert do_projeto[p]["jobs_ok"] == 2

    de_outro = mundo.perguntar(sql, (mundo.n("PROJ_QUE_NAO_EXISTE"),))
    assert de_outro == {}
