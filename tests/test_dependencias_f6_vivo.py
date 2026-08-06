"""
F6 — o corte do modo SEQUÊNCIA **executado contra o SQL Server** (spec
`docs/spec-malha-execucao.md` §8, Decisões 38 e 39; aceite da §10 "### F6").

Por que este arquivo é separado do resto da suíte: **o que a F6 entrega é
SQL**. O corte em três degraus é um `COALESCE` de três subconsultas, uma delas
com `TOP 1` correlacionado por `dd.origem_no`, comparando INSTANTES
(`ISNULL(e.fim, e.inicio) >= …`). Dublê nenhum prova que esse texto resolve o
degrau certo por LINHA — um dublê prova que o texto foi emitido e que os
parâmetros foram os certos, e é isso que os arquivos irmãos fazem. Quem decide
se `COALESCE` escolhe o 1º degrau quando a corrida já fechou, se o `TOP 1` acha
a corrida da malha que assinou a linha, e se `>=` deixa passar o pai das 23h30
para o filho da 01h, é o SQL Server. Este arquivo pergunta a ele.

E o predicado desta fase é o PREDICADO CANÔNICO DE LIBERAÇÃO, consultado em
três portas (push da factory, guardiã e API). Errar aqui não atrasa uma tela:
ou solta o que devia segurar, ou segura a casa inteira.

⚠️ **Como rodar** (o arquivo INTEIRO pula sem a variável — a senha nunca mora
no repositório):

    ORQ_TEST_MSSQL_PASSWORD='…' python3 -m pytest tests/test_dependencias_f6_vivo.py

Host/porta/usuário/banco têm default de ambiente dev (`127.0.0.1:1433`, `sa`,
`orquestra_dev`) e são sobrescritos por `ORQ_TEST_MSSQL_HOST`, `…_PORT`,
`…_USER`, `…_DATABASE`.

⚠️ **Nada é commitado.** Cada teste abre a própria transação, monta o cenário,
pergunta e dá `ROLLBACK` — e o teardown CONFERE, depois do rollback, que
nenhuma linha com o prefixo do teste sobreviveu. Teste ao vivo em base suja
mede o lixo; base suja depois do teste é pior ainda, porque o lixo passa a
mentir para o próximo.

⚠️ **Nenhuma conta de tempo em Python.** Os instantes do cenário são escritos
em T-SQL (`DATEADD(...)` sobre `SYSDATETIME()`): o SQL Server do dev está ~3h à
frente do worker, e um `datetime.now()` daqui montaria um cenário que o banco
não reconhece. O que o teste fixa é a GEOMETRIA (o pai concluiu antes da
abertura e dentro da janela), nunca o relógio de parede.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import uuid
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_AIRFLOW_STUBS = [
    "airflow", "airflow.models", "airflow.operators", "airflow.operators.python",
    "airflow.datasets", "airflow.utils", "airflow.utils.trigger_rule",
    "pendulum", "requests",
]
for _mod in _AIRFLOW_STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

_ROOT = Path(__file__).parent.parent

# A data de referência do cenário. No modo SEQUÊNCIA ela sai da conta do
# predicado (é esse o ponto do modo) — fica aqui só porque as colunas são NOT
# NULL, e é ela que o teste do interruptor DESLIGADO usa para provar que, com o
# modo em 0, a pergunta volta a ser "SUCESSO nesta data".
DATA_REF = date(2026, 8, 5)
OUTRA_DATA = date(2026, 8, 4)


def _pymssql_real():
    """O pymssql **de verdade**, mesmo com a suíte irmã tendo-o stubado.

    `tests/test_conexao_nativa_fluxo.py` põe um `MagicMock` em
    `sys.modules["pymssql"]` já no import (é assim que ela testa a resolução de
    conexão sem banco), e o stub vale para a sessão inteira. Sem esta função,
    rodando a suíte toda estes testes conversariam com o MOCK: `execute`
    engoliria tudo, `fetchone()` devolveria um `MagicMock` — e um arquivo
    inteiro de testes de banco ficaria VERDE sem nunca ter falado com o SQL
    Server. É o "verde pelo motivo errado" na sua forma mais cara, e foi a
    conferência de limpeza do teardown que o pegou na primeira execução.

    O stub é DEVOLVIDO ao seu lugar no fim: a sessão sai daqui como entrou."""
    stub = sys.modules.pop("pymssql", None)
    try:
        import pymssql                       # noqa: PLC0415 — o de verdade
        return pymssql
    except ImportError:                                   # pragma: no cover
        return None
    finally:
        if isinstance(stub, MagicMock):
            sys.modules["pymssql"] = stub


def _conectar():
    """Conexão pymssql com o dev, ou `None` (o arquivo pula). pymssql é o
    driver de `dags/` — é ele que entende o `%s` do canônico, e é por isso que
    o SQL testado aqui é o mesmo texto que a DAG manda em produção."""
    senha = os.getenv("ORQ_TEST_MSSQL_PASSWORD")
    if not senha:
        return None
    driver = _pymssql_real()
    if driver is None:                                    # pragma: no cover
        return None
    conn = driver.connect(
        server=os.getenv("ORQ_TEST_MSSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("ORQ_TEST_MSSQL_PORT", "1433")),
        user=os.getenv("ORQ_TEST_MSSQL_USER", "sa"),
        password=senha,
        database=os.getenv("ORQ_TEST_MSSQL_DATABASE", "orquestra_dev"),
    )
    # A sonda que separa "banco" de "dublê": um mock devolveria um MagicMock
    # aqui e seguiria em frente. Falhar é melhor que pular — pular esconderia
    # que a suíte de banco deixou de ser de banco.
    cur = conn.cursor()
    cur.execute("SELECT 1")
    assert cur.fetchone()[0] == 1, (
        "a conexao nao e um SQL Server de verdade — o modulo pymssql esta "
        "stubado nesta sessao e estes testes mediriam o dublê")
    return conn


@pytest.fixture(scope="module")
def dep():
    """O canônico de `dags/`, carregado por caminho (técnica da casa)."""
    spec = importlib.util.spec_from_file_location(
        "dependencias_dags_f6_vivo", _ROOT / "dags/utils/dependencias.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Mundo:
    """Montador de cenário — e a régua do tempo é sempre a do BANCO.

    Todo instante entra como `DATEADD(...)` sobre `SYSDATETIME()`: `min=-240`
    é "concluiu 4h atrás", `dias/hora` ancora na meia-noite do banco (para o
    cenário da virada). Nomes carregam um sufixo único por teste, e o prefixo
    é o que o teardown usa para conferir que o `ROLLBACK` levou tudo."""

    PREFIXO = "ZZ_F6VIVO_"

    def __init__(self, conn, dep, modo_sequencia=True):
        self.conn = conn
        self.dep = dep
        self.cur = conn.cursor()
        self.suf = uuid.uuid4().hex[:8].upper()
        # O modo vem do CACHE do módulo, e não de um UPDATE em
        # `etl_app_config`: a linha do interruptor é lida pelo ambiente dev
        # inteiro, e um UPDATE aqui a manteria travada até o rollback — um
        # teste não pode segurar a configuração de quem está trabalhando ao
        # lado. `limpar_cache_modo` existe exatamente para isto.
        self.dep.limpar_cache_modo()
        self.dep._MODO_CACHE["modo"] = modo_sequencia

    # ── nomes ────────────────────────────────────────────────────────────
    def n(self, base):
        return f"{self.PREFIXO}{base}_{self.suf}"

    # ── montagem ─────────────────────────────────────────────────────────
    def pipeline(self, base):
        nome = self.n(base)
        self.cur.execute(
            "INSERT INTO dbo.etl_pipeline (pipeline_name) VALUES (%s)", (nome,))
        return nome

    def malha(self, base):
        nome = self.n(base)
        self.cur.execute(
            "INSERT INTO dbo.etl_malha (malha_name) VALUES (%s)", (nome,))
        return nome

    def no_aguarde(self, malha):
        """O nó que ASSINA a dependência (migration 075) — é dele que sai a
        malha do 2º degrau, e é por ele que a malha é DETERMINADA."""
        self.cur.execute(
            "INSERT INTO dbo.etl_malha_no (malha_name, tipo) OUTPUT INSERTED.id "
            "VALUES (%s, 'aguarde')", (malha,))
        return self.cur.fetchone()[0]

    def reter(self, no_id):
        self.cur.execute(
            "UPDATE dbo.etl_malha_no SET retido_em = SYSDATETIME(), "
            "retido_por = 'TESTE' WHERE id = %s", (no_id,))

    def corrida(self, malha, min=0, seq=1):
        """Corrida ABERTA cujo `aberta_em` é `SYSDATETIME() + min` minutos."""
        self.cur.execute(
            "INSERT INTO dbo.etl_malha_execucao (malha_name, data_referencia, "
            "sequencia, status, aberta_em, origem, modo_fechamento) "
            "OUTPUT INSERTED.id VALUES (%s, %s, %s, 'ABERTA', "
            "DATEADD(minute, %s, SYSDATETIME()), 'manual', 'fim')",
            (malha, DATA_REF, seq, min))
        return self.cur.fetchone()[0]

    def corrida_ancorada(self, malha, dias, hora, seq=1):
        """Corrida cujo `aberta_em` é a meia-noite do banco − `dias`, + `hora`.
        Existe para o cenário da virada, que precisa de um instante ANTES de
        uma meia-noite real — algo que um delta em minutos não garante."""
        self.cur.execute(
            "INSERT INTO dbo.etl_malha_execucao (malha_name, data_referencia, "
            "sequencia, status, aberta_em, origem, modo_fechamento) "
            "OUTPUT INSERTED.id VALUES (%s, %s, %s, 'ABERTA', "
            "DATEADD(hour, %s, DATEADD(day, %s, "
            "CAST(CAST(SYSDATETIME() AS date) AS datetime2))), 'manual', 'fim')",
            (malha, DATA_REF, seq, hora, -dias))
        return self.cur.fetchone()[0]

    def fechar(self, corrida_id, min=0):
        self.cur.execute(
            "UPDATE dbo.etl_malha_execucao SET status = 'CONCLUIDA', "
            "fechada_em = DATEADD(minute, %s, SYSDATETIME()) WHERE id = %s",
            (min, corrida_id))

    def aberta_em(self, corrida_id):
        self.cur.execute(
            "SELECT aberta_em FROM dbo.etl_malha_execucao WHERE id = %s",
            (corrida_id,))
        return self.cur.fetchone()[0]

    def execucao(self, pipeline, min=0, status="SUCESSO", substituida=False,
                 data_ref=DATA_REF, tag="a"):
        """Execução que começou e terminou em `SYSDATETIME() + min` minutos."""
        self.cur.execute(
            "INSERT INTO dbo.etl_pipeline_execucao (pipeline_name, "
            "data_referencia, execution_id, status, inicio, fim, substituida_em) "
            "VALUES (%s, %s, %s, %s, DATEADD(minute, %s, SYSDATETIME()), "
            "DATEADD(minute, %s, SYSDATETIME()), NULL)",
            (pipeline, data_ref, f"run-{tag}-{self.suf}", status, min, min))
        if substituida:
            self.cur.execute(
                "UPDATE dbo.etl_pipeline_execucao SET substituida_em = "
                "SYSDATETIME() WHERE pipeline_name = %s AND execution_id = %s",
                (pipeline, f"run-{tag}-{self.suf}"))

    def execucao_no_instante_da_abertura(self, pipeline, corrida_id, tag="a"):
        """Execução cujo `fim` é EXATAMENTE o `aberta_em` da corrida — copiado
        da coluna, não recalculado, porque a borda do `>=` só existe se os dois
        instantes forem o mesmo valor de `datetime2`."""
        self.cur.execute(
            "INSERT INTO dbo.etl_pipeline_execucao (pipeline_name, "
            "data_referencia, execution_id, status, inicio, fim) "
            "SELECT %s, %s, %s, 'SUCESSO', me.aberta_em, me.aberta_em "
            "FROM dbo.etl_malha_execucao me WHERE me.id = %s",
            (pipeline, DATA_REF, f"run-{tag}-{self.suf}", corrida_id))

    def execucao_ancorada(self, pipeline, dias, hora, minuto=0, tag="a"):
        self.cur.execute(
            "INSERT INTO dbo.etl_pipeline_execucao (pipeline_name, "
            "data_referencia, execution_id, status, inicio, fim) VALUES "
            "(%s, %s, %s, 'SUCESSO', "
            " DATEADD(minute, %s, DATEADD(hour, %s, DATEADD(day, %s, "
            "  CAST(CAST(SYSDATETIME() AS date) AS datetime2)))), "
            " DATEADD(minute, %s, DATEADD(hour, %s, DATEADD(day, %s, "
            "  CAST(CAST(SYSDATETIME() AS date) AS datetime2)))))",
            (pipeline, DATA_REF, f"run-{tag}-{self.suf}",
             minuto, hora, -dias, minuto, hora, -dias))

    def fim_de(self, pipeline):
        self.cur.execute(
            "SELECT MAX(fim) FROM dbo.etl_pipeline_execucao "
            "WHERE pipeline_name = %s", (pipeline,))
        return self.cur.fetchone()[0]

    def dependencia(self, filho, pai, origem_no=None):
        """`origem_no` é a assinatura: preenchido = linha compilada por uma
        malha; NULL = dependência avulsa do `POST /dependencias`."""
        self.cur.execute(
            "INSERT INTO dbo.etl_pipeline_dependencia (pipeline_name, "
            "depende_de, tipo, origem_no) VALUES (%s, %s, 'PIPELINE', %s)",
            (filho, pai, origem_no))

    # ── a pergunta ───────────────────────────────────────────────────────
    def avaliar(self, pipeline, corrida=None, data_ref=DATA_REF):
        """`liberado()` de verdade, com a guarda de honestidade obrigatória.

        `liberado` traduz QUALQUER exceção em "não liberado" com o sentinel
        (D21). Sem conferir o sentinel, todo teste de "não libera" ficaria
        verde também quando o SQL nem compila — verde pelo motivo errado, que
        é o defeito que esta fase inteira existe para não cometer."""
        lib, falt = self.dep.liberado(self.conn, pipeline, data_ref, corrida)
        assert not any(str(f).startswith(self.dep.ERRO_CONSULTA) for f in falt), (
            f"o predicado NAO conseguiu perguntar ao banco: {falt}")
        return lib, falt

    def corte_da_janela(self):
        """O 3º degrau, calculado como o módulo o calcula (relógio do BANCO)."""
        return self.dep.inicio_do_ciclo_corrente(self.conn)


@pytest.fixture
def mundo(dep):
    """Cenário isolado: transação própria, `ROLLBACK` no fim e CONFERÊNCIA de
    que o rollback levou tudo o que o teste inseriu."""
    conn = _conectar()
    if conn is None:
        pytest.skip("banco dev indisponivel — defina ORQ_TEST_MSSQL_PASSWORD")
    m = Mundo(conn, dep)
    try:
        yield m
    finally:
        conn.rollback()
        dep.limpar_cache_modo()
        # A limpeza é VERIFICADA, não presumida: um `ROLLBACK` que não
        # acontecesse (autocommit ligado por engano, por exemplo) deixaria
        # pipelines e corridas de mentira num banco que o time usa para medir
        # comportamento real.
        cur = conn.cursor()
        sobrou = []
        for tabela, coluna in (("etl_pipeline", "pipeline_name"),
                               ("etl_malha", "malha_name"),
                               ("etl_malha_execucao", "malha_name"),
                               ("etl_malha_no", "malha_name"),
                               ("etl_pipeline_execucao", "pipeline_name"),
                               ("etl_pipeline_dependencia", "pipeline_name")):
            cur.execute(f"SELECT COUNT(*) FROM dbo.{tabela} "
                        f"WHERE {coluna} LIKE %s", (f"{Mundo.PREFIXO}%",))
            n = cur.fetchone()[0]
            if n:
                sobrou.append(f"{tabela}={n}")
        conn.close()
        assert not sobrou, f"o ROLLBACK deixou lixo no banco dev: {sobrou}"


# ═════════ 1. o corte é `aberta_em`, e não a janela (aceite, bullet 1) ══════

def test_pai_dentro_da_janela_mas_antes_da_abertura_NAO_libera(mundo):
    """**O bullet 1 do aceite.** Malha com corrida aberta (01:10 na narrativa
    da spec) e pai que concluiu às 22:00 do dia anterior — DENTRO das 12h da
    janela. O corte é `aberta_em`: o sucesso é da rodada PASSADA e não conta.

    A geometria é o que importa (o relógio de parede é do banco): o pai
    concluiu 4h atrás, a corrida abriu 30 min atrás, a janela é de 12h. As três
    asserções são: (a) a janela sozinha teria contado o pai — é o defeito que
    a Decisão 38 evita, e sem esta asserção o teste passaria mesmo se a janela
    também segurasse; (b) o corte é o `aberta_em`; (c) NÃO libera."""
    m = mundo
    filho, pai = m.pipeline("FILHO"), m.pipeline("PAI")
    malha = m.malha("M")
    no = m.no_aguarde(malha)
    corrida = m.corrida(malha, min=-30)
    m.execucao(pai, min=-240)                    # concluiu 4h atras
    m.dependencia(filho, pai, origem_no=no)

    fim_do_pai = m.fim_de(pai)
    assert m.corte_da_janela() < fim_do_pai, (
        "cenario invalido: a janela de 12h TEM de alcancar o pai, senao o "
        "teste nao distingue o corte novo do antigo")
    assert m.aberta_em(corrida) > fim_do_pai, "o pai tem de ser ANTERIOR a abertura"

    assert m.avaliar(filho, corrida) == (False, [pai])


def test_pai_concluido_DEPOIS_da_abertura_libera(mundo):
    """O controle positivo do bullet 1: o corte novo não é "segura sempre".
    Sem este teste, um `COALESCE` que devolvesse um instante absurdo (ou um
    `>=` virado) passaria no teste de cima e travaria a produção inteira."""
    m = mundo
    filho, pai = m.pipeline("FILHO"), m.pipeline("PAI")
    malha = m.malha("M")
    no = m.no_aguarde(malha)
    corrida = m.corrida(malha, min=-120)
    m.execucao(pai, min=-60)                     # concluiu DENTRO da corrida
    m.dependencia(filho, pai, origem_no=no)

    assert m.avaliar(filho, corrida) == (True, [])


def test_pai_que_terminou_NO_INSTANTE_da_abertura_conta(mundo):
    """A borda do `>=`, medida no banco (é lá que `datetime2` compara). O
    membro que a corrida dispara na abertura pode carimbar `fim` no MESMO
    instante do `aberta_em`; com `>` esse sucesso sumiria e o filho ficaria
    esperando um pai que já terminou."""
    m = mundo
    filho, pai = m.pipeline("FILHO"), m.pipeline("PAI")
    malha = m.malha("M")
    no = m.no_aguarde(malha)
    corrida = m.corrida(malha, min=-30)
    m.execucao_no_instante_da_abertura(pai, corrida)
    m.dependencia(filho, pai, origem_no=no)

    assert m.fim_de(pai) == m.aberta_em(corrida), "cenario invalido: nao empatou"
    assert m.avaliar(filho, corrida) == (True, [])


# ═══════ 2. a janela continua inteira para quem não tem corrida ════════════

def test_dependencia_avulsa_continua_cortada_pela_janela_de_12h(mundo):
    """**Bullet 2.** `origem_no IS NULL` (dependência criada à mão pelo
    `POST /dependencias`) não tem corrida em degrau nenhum: os dois primeiros
    devolvem NULL e quem responde é a janela — INALTERADA. Remover a janela
    quebraria toda dependência avulsa de uma vez."""
    m = mundo
    filho, pai = m.pipeline("FILHO"), m.pipeline("PAI")
    m.execucao(pai, min=-240)                    # 4h atras: dentro das 12h
    m.dependencia(filho, pai, origem_no=None)

    assert m.avaliar(filho, corrida=None) == (True, [])


def test_dependencia_avulsa_com_pai_FORA_da_janela_continua_segurando(mundo):
    """O outro lado da mesma régua — e a prova de que o teste de cima mede a
    janela, e não "avulsa passa sempre": o mesmo pai, 13h atrás, fica fora das
    12h e a linha segura."""
    m = mundo
    filho, pai = m.pipeline("FILHO"), m.pipeline("PAI")
    m.execucao(pai, min=-13 * 60)
    m.dependencia(filho, pai, origem_no=None)

    assert m.avaliar(filho, corrida=None) == (False, [pai])


def test_corte_resolvido_POR_LINHA_na_mesma_consulta(mundo):
    """**O coração da Decisão 38, e o teste que nenhum dublê de um caso só
    consegue fazer.** Um filho, DUAS linhas de naturezas diferentes, UMA
    consulta:

      • linha assinada pela malha (`origem_no` = nó) → cortada pelo `aberta_em`
        da corrida aberta → o pai de 4h atrás NÃO conta;
      • linha avulsa (`origem_no IS NULL`) → cortada pela janela de 12h → o
        pai de 4h atrás CONTA.

    Um corte único — qualquer que fosse — daria `[PAI_A, PAI_B]` ou `[]`. A
    resposta certa é exatamente uma faltante, e é ela que prova que o degrau é
    resolvido linha a linha, dentro do mesmo `SELECT`."""
    m = mundo
    filho = m.pipeline("FILHO")
    pai_malha, pai_avulso = m.pipeline("PAI_A"), m.pipeline("PAI_B")
    malha = m.malha("M")
    no = m.no_aguarde(malha)
    m.corrida(malha, min=-30)
    m.execucao(pai_malha, min=-240, tag="a")
    m.execucao(pai_avulso, min=-240, tag="b")
    m.dependencia(filho, pai_malha, origem_no=no)
    m.dependencia(filho, pai_avulso, origem_no=None)

    assert m.avaliar(filho, corrida=None) == (False, [pai_malha])


# ═════════════ 3. a corrida atravessa a virada do dia (bullet 3) ════════════

def test_corrida_que_atravessa_a_virada_o_filho_da_01h_ve_o_pai_das_23h30(mundo):
    """**Bullet 3.** Malha que começa 23h e termina 01h: o filho avaliado
    depois da meia-noite tem de ENXERGAR o pai que concluiu às 23h30 do dia
    anterior. O corte é um INSTANTE (`aberta_em`), não uma virada de data —
    com corte na virada, a corrida que atravessa a meia-noite travaria em
    silêncio, que é o defeito que a `inicio_do_ciclo_corrente` já documentava
    e que a corrida agora resolve com precisão.

    O cenário é ancorado na meia-noite do BANCO (23:00 e 23:30 de dois dias
    atrás) para que a travessia seja real e o pai fique, com folga, FORA da
    janela de 12h — assim quem libera só pode ser a corrida."""
    m = mundo
    filho, pai = m.pipeline("FILHO"), m.pipeline("PAI")
    malha = m.malha("M")
    no = m.no_aguarde(malha)
    corrida = m.corrida_ancorada(malha, dias=2, hora=23)      # 23:00
    m.execucao_ancorada(pai, dias=2, hora=23, minuto=30)      # 23:30
    m.dependencia(filho, pai, origem_no=no)

    fim_do_pai = m.fim_de(pai)
    assert m.aberta_em(corrida) < fim_do_pai
    assert fim_do_pai.date() < m.corte_da_janela().date(), (
        "cenario invalido: o pai tem de estar num DIA anterior ao da avaliacao")
    assert fim_do_pai < m.corte_da_janela(), (
        "cenario invalido: a janela de 12h nao pode alcancar o pai, senao nao "
        "se sabe quem liberou")

    assert m.avaliar(filho, corrida) == (True, [])


# ═════ 4. o corte não muda de significado no meio do ciclo (Decisão 39) ═════

def test_corrida_que_FECHA_entre_duas_avaliacoes_nao_muda_o_corte(mundo):
    """**Bullet 4.** A corrida é PARÂMETRO, não subconsulta viva. Fecha-se a
    corrida entre duas avaliações da MESMA linha e a resposta tem de ser a
    mesma — o 1º degrau não filtra por `fechada_em`, de propósito.

    E o teste mostra o que a subconsulta viva teria feito: avaliada SEM a
    corrida depois do fechamento, a mesma linha cai na janela de 12h e o pai
    da rodada passada passa a contar — a virada silenciosa, no meio da
    madrugada, sem nada no banco explicando o quê."""
    m = mundo
    filho, pai = m.pipeline("FILHO"), m.pipeline("PAI")
    malha = m.malha("M")
    no = m.no_aguarde(malha)
    corrida = m.corrida(malha, min=-30)
    m.execucao(pai, min=-240)
    m.dependencia(filho, pai, origem_no=no)

    antes = m.avaliar(filho, corrida)
    m.fechar(corrida)
    depois = m.avaliar(filho, corrida)
    assert antes == depois == (False, [pai]), (
        "o corte mudou de significado porque a corrida fechou")

    assert m.avaliar(filho, corrida=None) == (True, []), (
        "cenario invalido: sem a corrida da linha a janela TEM de soltar — e "
        "e essa a virada silenciosa que a Decisao 39 evita")


def test_a_corrida_da_LINHA_ganha_da_corrida_aberta_AGORA(mundo):
    """A ordem dos degraus, no cenário em que ela decide: a corrida #1 fechou,
    a #2 (rerun/próximo ciclo) já abriu, e o pai concluiu ENTRE as duas.

      • avaliada com a corrida #1 (a da linha) → o pai é DESTA rodada → LIBERA;
      • avaliada pela corrida aberta agora (#2) → o pai seria "da rodada
        passada" → seguraria.

    Trocar o 1º degrau pelo 2º é trocar "a corrida desta linha" por "a corrida
    aberta no instante da avaliação" — exatamente o que a Decisão 39 proíbe."""
    m = mundo
    filho, pai = m.pipeline("FILHO"), m.pipeline("PAI")
    malha = m.malha("M")
    no = m.no_aguarde(malha)
    primeira = m.corrida(malha, min=-180, seq=1)
    m.fechar(primeira, min=-120)
    segunda = m.corrida(malha, min=-60, seq=2)
    m.execucao(pai, min=-90)                    # entre o fechamento e a #2
    m.dependencia(filho, pai, origem_no=no)

    assert m.avaliar(filho, primeira) == (True, [])
    assert m.avaliar(filho, segunda) == (False, [pai])
    assert m.avaliar(filho, corrida=None) == (False, [pai]), (
        "sem corrida em maos o degrau 2 responde, e ele olha a ABERTA")


# ══════════ 5. o 2º degrau: a malha que ASSINOU, e só ela ═══════════════════

def test_degrau_2_usa_a_malha_que_ASSINOU_a_linha_e_nao_qualquer_uma(mundo):
    """A malha do 2º degrau vem do NÓ (`dd.origem_no`, migration 075), então
    ela é DETERMINADA por linha — não se pergunta "de que malha este pipeline é
    membro", que é a pergunta ambígua do membro compartilhado.

    Duas linhas do mesmo filho, assinadas por malhas diferentes; só a malha A
    tem corrida aberta. O pai de A (anterior à abertura) segura; o pai de B,
    cuja malha não tem corrida, é julgado pela janela e passa. Um degrau 2 que
    pegasse "qualquer corrida aberta" seguraria os dois."""
    m = mundo
    filho = m.pipeline("FILHO")
    pai_a, pai_b = m.pipeline("PAI_A"), m.pipeline("PAI_B")
    malha_a, malha_b = m.malha("MA"), m.malha("MB")
    no_a, no_b = m.no_aguarde(malha_a), m.no_aguarde(malha_b)
    m.corrida(malha_a, min=-30)
    m.execucao(pai_a, min=-240, tag="a")
    m.execucao(pai_b, min=-240, tag="b")
    m.dependencia(filho, pai_a, origem_no=no_a)
    m.dependencia(filho, pai_b, origem_no=no_b)

    assert m.avaliar(filho, corrida=None) == (False, [pai_a])


def test_degrau_2_ignora_corrida_ja_FECHADA(mundo):
    """`me2.fechada_em IS NULL` no 2º degrau: corrida encerrada não corta mais
    nada. Sem essa guarda, a última corrida da malha continuaria segurando os
    filhos depois de fechada — e o pipeline avulso da mesma malha ficaria preso
    a um ciclo que acabou."""
    m = mundo
    filho, pai = m.pipeline("FILHO"), m.pipeline("PAI")
    malha = m.malha("M")
    no = m.no_aguarde(malha)
    corrida = m.corrida(malha, min=-30)
    m.execucao(pai, min=-240)
    m.dependencia(filho, pai, origem_no=no)

    assert m.avaliar(filho, corrida=None) == (False, [pai])
    m.fechar(corrida)
    assert m.avaliar(filho, corrida=None) == (True, []), (
        "corrida FECHADA nao pode continuar cortando pelo degrau 2")


# ═══════════ 6. o que o SQL novo tinha de continuar respeitando ═════════════

def test_aguarde_RETIDO_continua_segurando_no_corte_novo(mundo):
    """O `OR EXISTS (… retido_em IS NOT NULL)` sobreviveu à reescrita: nó
    segurado pelo operador segura o filho mesmo com o pai concluído DENTRO da
    corrida. A F6 reescreveu o `WHERE` inteiro do modo — esta é a garantia de
    que a retenção da F2/082 não caiu junto."""
    m = mundo
    filho, pai = m.pipeline("FILHO"), m.pipeline("PAI")
    malha = m.malha("M")
    no = m.no_aguarde(malha)
    corrida = m.corrida(malha, min=-120)
    m.execucao(pai, min=-60)                     # sucesso DESTA rodada
    m.dependencia(filho, pai, origem_no=no)
    assert m.avaliar(filho, corrida) == (True, [])

    m.reter(no)
    lib, falt = m.avaliar(filho, corrida)
    # E o faltante é a TRAVA, com o id do nó — não o nome do pai: quem segura
    # é o Aguarde, e é isso que o operador precisa ler para saber onde soltar.
    assert lib is False
    assert falt == [m.dep.MSG_AGUARDE_RETIDO.format(no)]


def test_sucesso_SUBSTITUIDO_nao_conta_no_corte_novo(mundo):
    """`e.substituida_em IS NULL` também sobreviveu: sucesso de uma corrida
    substituída (rerun) não é sucesso desta rodada, mesmo carimbado depois da
    abertura."""
    m = mundo
    filho, pai = m.pipeline("FILHO"), m.pipeline("PAI")
    malha = m.malha("M")
    no = m.no_aguarde(malha)
    corrida = m.corrida(malha, min=-120)
    m.execucao(pai, min=-60, substituida=True)
    m.dependencia(filho, pai, origem_no=no)

    assert m.avaliar(filho, corrida) == (False, [pai])


def test_status_diferente_de_sucesso_nao_conta(mundo):
    """A guarda mais antiga do predicado, reconferida depois da reescrita:
    `EXECUTANDO` dentro da corrida não libera ninguém."""
    m = mundo
    filho, pai = m.pipeline("FILHO"), m.pipeline("PAI")
    malha = m.malha("M")
    no = m.no_aguarde(malha)
    corrida = m.corrida(malha, min=-120)
    m.execucao(pai, min=-60, status="EXECUTANDO")
    m.dependencia(filho, pai, origem_no=no)

    assert m.avaliar(filho, corrida) == (False, [pai])


# ═════════════ 7. o interruptor desligado — o que o dev vê hoje ════════════

def test_com_o_modo_DESLIGADO_a_corrida_nao_muda_nada(dep):
    """`dependencia_modo_sequencia = 0` (o valor do dev e o da produção hoje):
    a pergunta volta a ser "SUCESSO NESTA data de referência" e a corrida
    passada é ignorada — inclusive quando ela existe e está aberta.

    É o teste que diz que esta fase é INERTE até o interruptor virar: sucesso
    na data libera mesmo tendo acontecido antes da abertura da corrida, e
    sucesso em outra data não libera mesmo dentro dela."""
    conn = _conectar()
    if conn is None:
        pytest.skip("banco dev indisponivel — defina ORQ_TEST_MSSQL_PASSWORD")
    m = Mundo(conn, dep, modo_sequencia=False)
    try:
        filho = m.pipeline("FILHO")
        pai_ok, pai_outra = m.pipeline("PAI_OK"), m.pipeline("PAI_OUTRA")
        malha = m.malha("M")
        no = m.no_aguarde(malha)
        corrida = m.corrida(malha, min=-30)
        m.execucao(pai_ok, min=-240, data_ref=DATA_REF, tag="a")
        m.execucao(pai_outra, min=-10, data_ref=OUTRA_DATA, tag="b")
        m.dependencia(filho, pai_ok, origem_no=no)
        assert m.avaliar(filho, corrida) == (True, []), (
            "no modo DATA o sucesso na data libera, mesmo anterior a abertura")

        m.dependencia(filho, pai_outra, origem_no=no)
        assert m.avaliar(filho, corrida) == (False, [pai_outra]), (
            "no modo DATA o sucesso de outra data nao libera, mesmo DENTRO da "
            "corrida")
    finally:
        conn.rollback()
        dep.limpar_cache_modo()
        conn.close()


# ═════════════ 8. paridade EXECUTADA: o gêmeo de api/ no banco ═════════════

def test_o_SQL_GEMEO_da_api_responde_igual_no_banco(mundo):
    """A paridade textual (`test_dependencias_f5_paridade.py`) prova que os
    dois textos são o mesmo a menos do placeholder. Este teste prova a outra
    metade: que esse texto, do jeito que `api/` o escreve, COMPILA e responde
    igual no SQL Server.

    A árvore `api/` fala pyodbc (`?`) e não roda sob pymssql; a tradução
    `?` → `%s` é a mesma que a paridade normaliza, e é ela que permite mandar o
    texto do painel para o banco do motor. Divergir aqui é a tela contando uma
    história diferente da do motor — a doença que o D29 matou, voltando pela
    porta do corte."""
    # `api/services/dependencias.py` só importa `logging` e `datetime` — dá
    # para ler o SQL do gêmeo sem levantar a API inteira (`pythonpath = api`
    # está no pytest.ini).
    from services import dependencias as deps_api          # noqa: PLC0415

    m = mundo
    filho = m.pipeline("FILHO")
    pai_malha, pai_avulso = m.pipeline("PAI_A"), m.pipeline("PAI_B")
    malha = m.malha("M")
    no = m.no_aguarde(malha)
    m.corrida(malha, min=-30)
    m.execucao(pai_malha, min=-240, tag="a")
    m.execucao(pai_avulso, min=-240, tag="b")
    m.dependencia(filho, pai_malha, origem_no=no)
    m.dependencia(filho, pai_avulso, origem_no=None)

    params = (filho, None, m.corte_da_janela())
    cur = m.conn.cursor()
    cur.execute(m.dep.SQL_LIBERADO_SEQ_085, params)
    do_motor = sorted(cur.fetchall())
    cur.execute(deps_api.SQL_LIBERADO_SEQ_085.replace("?", "%s"), params)
    do_painel = sorted(cur.fetchall())

    assert do_motor == do_painel
    assert [linha[0] for linha in do_motor] == [pai_malha], (
        "cenario invalido: o SQL tem de DISCRIMINAR, senao a igualdade acima "
        "seria a de duas listas vazias")
