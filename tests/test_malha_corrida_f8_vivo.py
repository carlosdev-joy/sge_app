"""
F8 — o rerun **executado contra o SQL Server** (spec `docs/spec-malha-execucao.md`
§6.9/#3, §10 "### F8" e a pendência 13g da §18).

Por que este arquivo existe, no molde de `test_dependencias_f6_vivo.py`: os três
fatos que a F8 entrega **são do banco**, e nenhum dublê os prova.

  1. **A segunda `MALHA_CONCLUIDA` do dia.** Quem a engole é o índice único
     `ux_dep_evento_corrida`, e quem a deixa passar é o `DELETE` da reabertura.
     Um dublê que interpreta um `WHERE NOT EXISTS` prova o texto do statement;
     só o SQL Server prova que a chave de fato liberou.
  2. **A guarda do `ux_malha_exec_aberta`.** O ponto do §6.9/#3 é que a
     reabertura NÃO pode estourar 2601 dentro da transação do rerun. "Não
     estoura" é um fato do motor de índices — em dublê, é uma decisão do dublê.
  3. **A pendência 13g.** O `LEFT JOIN` com `(substituida_em IS NULL OR status =
     'EXECUTANDO')` decide se um membro aparece ou some. Errar aqui é a corrida
     fechar por cima de trabalho em andamento.

⚠️ **Como rodar** (o arquivo INTEIRO pula sem a variável — a senha nunca mora no
repositório):

    ORQ_TEST_MSSQL_PASSWORD='…' python3 -m pytest tests/test_malha_corrida_f8_vivo.py

⚠️ **Nada é commitado**, e o teardown CONFERE, depois do `ROLLBACK`, que nenhuma
linha com o prefixo do teste sobreviveu.

⚠️ **Nenhuma conta de tempo em Python** (Decisão 10): todo instante entra como
`DATEADD(...)` sobre `SYSDATETIME()`. O SQL Server do dev está ~3h à frente do
worker, e um `datetime.now()` daqui montaria um cenário que o banco não
reconhece.
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import date
from pathlib import Path

import pytest

# A conexão e o resgate do pymssql REAL são os mesmos da F6 — reusar é o que
# garante que os dois arquivos falem com o MESMO banco do MESMO jeito (e o
# `_pymssql_real` carrega a lição de por que isso importa).
from tests.test_dependencias_f6_vivo import _conectar

_ROOT = Path(__file__).parent.parent

ODATE = date(2026, 8, 4)
OUTRO_ODATE = date(2026, 8, 5)


@pytest.fixture(scope="module")
def mc():
    """O canônico de `dags/`, carregado por caminho (técnica da casa). É o
    módulo com `%s` — o mesmo texto que a guardiã manda em produção."""
    spec = importlib.util.spec_from_file_location(
        "malha_corrida_dags_f8_vivo", _ROOT / "dags/utils/malha_corrida.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Mundo:
    PREFIXO = "ZZ_F8VIVO_"

    def __init__(self, conn):
        self.conn = conn
        self.cur = conn.cursor()
        self.suf = uuid.uuid4().hex[:8].upper()

    def n(self, base):
        return f"{self.PREFIXO}{base}_{self.suf}"

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

    def corrida(self, malha, status="CONCLUIDA", data_ref=ODATE, seq=1,
                motivo=None):
        """Corrida com `aberta_em` 6h atrás. Fechada carrega `fechada_em`;
        ABERTA não pode carregar (é o `CK_mexec_coerente`, e o cenário respeita
        o modelo em vez de contorná-lo)."""
        fechada = status != "ABERTA"
        self.cur.execute(
            "INSERT INTO dbo.etl_malha_execucao (malha_name, data_referencia, "
            "sequencia, status, aberta_em, fechada_em, fechada_por, origem, "
            "modo_fechamento, motivo) OUTPUT INSERTED.id VALUES "
            "(%s, %s, %s, %s, DATEADD(hour, -6, SYSDATETIME()), "
            + ("DATEADD(hour, -1, SYSDATETIME()), 'guardia', "
               if fechada else "NULL, NULL, ") +
            "'manual', 'quiescencia', %s)",
            (malha, data_ref, seq, status, motivo))
        return self.cur.fetchone()[0]

    def membro(self, corrida_id, pipeline, raiz=0):
        self.cur.execute(
            "INSERT INTO dbo.etl_malha_execucao_membro (malha_execucao_id, "
            "pipeline_name, conta_para_fim, ativo_na_abertura, eh_raiz) "
            "VALUES (%s, %s, 1, 1, %s)", (corrida_id, pipeline, raiz))

    def gastar_a_memoria(self, corrida_id):
        """`falha_vista_em`/`atraso_visto_em` já carimbados pela tentativa 1 —
        é o estado normal de uma corrida que falhou e alertou."""
        self.cur.execute(
            "UPDATE dbo.etl_malha_execucao SET falha_vista_em = SYSDATETIME(), "
            "atraso_visto_em = SYSDATETIME() WHERE id = %s", (corrida_id,))

    def execucao(self, pipeline, corrida_id, status="SUCESSO",
                 substituida=False, data_ref=ODATE, tag="a"):
        self.cur.execute(
            "INSERT INTO dbo.etl_pipeline_execucao (pipeline_name, "
            "data_referencia, execution_id, status, inicio, "
            "malha_execucao_id) VALUES (%s, %s, %s, %s, "
            "DATEADD(hour, -3, SYSDATETIME()), %s)",
            (pipeline, data_ref, f"run-{tag}-{self.suf}", status, corrida_id))
        if substituida:
            self.cur.execute(
                "UPDATE dbo.etl_pipeline_execucao SET substituida_em = "
                "SYSDATETIME(), substituida_por = 'rerun:TESTE' "
                "WHERE pipeline_name = %s AND execution_id = %s",
                (pipeline, f"run-{tag}-{self.suf}"))

    def evento(self, marcador, tipo, corrida_id, data_ref=ODATE):
        self.cur.execute(
            "INSERT INTO dbo.etl_dependencia_evento (pipeline_name, "
            "data_referencia, tipo, detalhe, malha_execucao_id) "
            "VALUES (%s, %s, %s, N'tentativa 1', %s)",
            (marcador, data_ref, tipo, corrida_id))

    def gravar_conclusao(self, marcador, corrida_id, data_ref=ODATE) -> int:
        """O `INSERT ... WHERE NOT EXISTS` de `dependencias.gravar_evento`, na
        chave da 085. Devolve o `rowcount` — 0 é "o índice engoliu"."""
        self.cur.execute(
            "INSERT INTO dbo.etl_dependencia_evento (pipeline_name, "
            "data_referencia, tipo, detalhe, malha_execucao_id) "
            "SELECT %s, %s, 'MALHA_CONCLUIDA', N'conclusao', %s "
            "WHERE NOT EXISTS (SELECT 1 FROM dbo.etl_dependencia_evento "
            "WHERE pipeline_name = %s AND data_referencia = %s "
            "AND tipo = 'MALHA_CONCLUIDA' AND ISNULL(malha_execucao_id, -1) = "
            "ISNULL(CAST(%s AS BIGINT), -1))",
            (marcador, data_ref, corrida_id, marcador, data_ref, corrida_id))
        return self.cur.rowcount

    def eventos_de(self, corrida_id):
        self.cur.execute(
            "SELECT pipeline_name, tipo FROM dbo.etl_dependencia_evento "
            "WHERE malha_execucao_id = %s ORDER BY pipeline_name, tipo",
            (corrida_id,))
        return [tuple(r) for r in self.cur.fetchall()]


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
        cur = conn.cursor()
        sobrou = []
        for tabela, coluna in (("etl_pipeline", "pipeline_name"),
                               ("etl_malha", "malha_name"),
                               ("etl_malha_execucao", "malha_name"),
                               ("etl_pipeline_execucao", "pipeline_name")):
            cur.execute(f"SELECT COUNT(*) FROM dbo.{tabela} "
                        f"WHERE {coluna} LIKE %s", (f"{Mundo.PREFIXO}%",))
            n = cur.fetchone()[0]
            if n:
                sobrou.append(f"{tabela}={n}")
        conn.close()
        assert not sobrou, f"o ROLLBACK deixou lixo no banco dev: {sobrou}"


# ═══ 1. o ganho da fase: a SEGUNDA MALHA_CONCLUIDA do dia é gravada ═════════

def test_a_segunda_conclusao_do_dia_e_engolida_ANTES_e_gravada_DEPOIS(mundo, mc):
    """O aceite da F8, medido contra o índice de verdade.

    A primeira asserção é a que dá sentido às outras: **sem o descarte, o
    `INSERT ... WHERE NOT EXISTS` devolve 0** — a corrida reaberta guarda o
    MESMO `id`, então a chave (marcador, data, tipo, corrida) da tentativa 2 é
    byte a byte a da tentativa 1. Sem ela, o teste passaria mesmo que o índice
    nunca tivesse engolido nada, e não estaria provando fase nenhuma.
    """
    m = mundo
    malha = m.malha("M")
    pipe = m.pipeline("A")
    c = m.corrida(malha, "CONCLUIDA", motivo="porta 2")
    m.membro(c, pipe, raiz=1)
    m.execucao(pipe, c)
    m.evento("#no:38", "MALHA_CONCLUIDA", c)

    assert m.gravar_conclusao("#no:38", c) == 0, (
        "o indice ux_dep_evento_corrida NAO engoliu a 2a conclusao — o cenario "
        "nao reproduz o defeito, e o resto do teste nao prova nada")

    assert mc.reabrir_corrida(m.conn, c, "rerun:C123456", "reexecucao") is True
    assert m.gravar_conclusao("#no:38", c) == 1


def test_a_reabertura_zera_a_memoria_e_registra_o_desfecho_ANULADO(mundo, mc):
    """As duas metades do `SQL_REABRIR` que só o banco compõe: o `SYSDATETIME()`
    e o `CONVERT(VARCHAR(19), fechada_em, 120)` do `motivo`.

    A memória de efeito colateral é da TENTATIVA: sem zerar, uma falha NOVA
    depois do reprocesso ficaria muda para sempre. E o desfecho anulado migra
    para o `motivo` da corrida — é lá que "concluiu 05:12 e foi reprocessada"
    passa a morar depois que os eventos da tentativa 1 são descartados."""
    m = mundo
    malha = m.malha("M")
    c = m.corrida(malha, "FALHA", motivo="porta 2")
    m.gastar_a_memoria(c)

    assert mc.reabrir_corrida(m.conn, c, "rerun:C1", "reexecucao de A") is True
    d = mc.corrida(m.conn, c)
    assert d["status"] == "ABERTA" and d["fechada_em"] is None
    assert d["tentativas"] == 2 and d["reaberta_por"] == "rerun:C1"
    assert d["falha_vista_em"] is None and d["atraso_visto_em"] is None
    assert d["motivo"].startswith("porta 2 | reaberta apos FALHA de ")
    assert d["motivo"].endswith(": reexecucao de A")


def test_o_descarte_nao_alcanca_evento_de_MEMBRO_nem_de_outra_corrida(mundo, mc):
    """O `LEFT(pipeline_name, …)` do statement, contra o banco: o evento de um
    pipeline (`EXECUCAO_ORFA` de um membro) fala do pipeline, não do ciclo —
    apagá-lo seria perder histórico de verdade."""
    m = mundo
    malha = m.malha("M")
    pipe = m.pipeline("A")
    c1 = m.corrida(malha, "CONCLUIDA")
    m.evento("#no:38", "MALHA_CONCLUIDA", c1)
    m.evento(f"#corrida:{c1}", "MALHA_FALHOU", c1)
    m.evento(f"#corrida:{c1}", "MALHA_CANCELADA", c1)   # nao e desfecho anulavel
    m.evento(pipe, "EXECUCAO_ORFA", c1)                 # e do MEMBRO

    assert mc.descartar_desfecho(m.conn, c1) == 2
    assert m.eventos_de(c1) == [(f"#corrida:{c1}", "MALHA_CANCELADA"),
                                (pipe, "EXECUCAO_ORFA")]


# ═══ 2. a guarda do índice único: reabrir NUNCA pode estourar 2601 ══════════

def test_com_outra_corrida_aberta_a_reabertura_devolve_False_sem_estourar(
        mundo, mc):
    """§6.9/#3 — o cenário de plantão: a corrida do dia 04 concluiu, a do dia 05
    está aberta, e o operador reprocessa um membro do dia 04.

    A guarda mora no `WHERE` do próprio `UPDATE`, e não num `SELECT` antes: o
    gesto acontece DENTRO da transação que carimba `substituida_em`, e um 2601
    ali rolaria o rerun inteiro de volta. O pior caso tem de ser `rowcount = 0`
    — uma resposta, não um estrago. Se `pymssql` levantar aqui, o teste falha
    com a exceção, que é exatamente o que se quer detectar."""
    m = mundo
    malha = m.malha("M")
    velha = m.corrida(malha, "CONCLUIDA", data_ref=ODATE, seq=1)
    nova = m.corrida(malha, "ABERTA", data_ref=OUTRO_ODATE, seq=1)

    assert mc.reabrir_corrida(m.conn, velha, "rerun:C1") is False
    assert mc.corrida(m.conn, velha)["status"] == "CONCLUIDA"
    assert mc.corrida(m.conn, velha)["tentativas"] == 1
    assert mc.corrida(m.conn, nova)["status"] == "ABERTA"


def test_a_corrida_de_fim_de_linha_nao_volta_nem_sozinha(mundo, mc):
    m = mundo
    c = m.corrida(m.malha("M"), "EXPIRADA")
    assert mc.reabrir_corrida(m.conn, c, "rerun:C1") is False
    assert mc.corrida(m.conn, c)["status"] == "EXPIRADA"


# ═══ 3. pendência 13g: o membro APOSENTADO que ainda EXECUTA ════════════════

def test_a_linha_aposentada_que_ainda_EXECUTA_continua_viva(mundo, mc):
    """O `LEFT JOIN` do `SQL_ESTADO`, perguntado ao banco.

    O rerun carimba `substituida_em` num statement e a linha nova nasce no claim
    seguinte, que pode ser no ciclo seguinte da guardiã. Entre os dois, com o
    filtro puro, o membro que continua rodando no Airflow SUMIA de `vivos` — e
    vivo invisível deixa a corrida fechar por cima de trabalho em andamento."""
    m = mundo
    malha = m.malha("M")
    rodando, ok = m.pipeline("RODANDO"), m.pipeline("OK")
    c = m.corrida(malha, "ABERTA")
    m.membro(c, rodando)
    m.membro(c, ok, raiz=1)
    m.execucao(rodando, c, status="EXECUTANDO", substituida=True, tag="r")
    m.execucao(ok, c, status="SUCESSO", tag="o")

    est = mc.estado(m.conn, mc.corrida(m.conn, c))
    assert est["vivos"] == [rodando]
    assert est["ok"] == [ok] and est["pendentes"] == []


def test_a_linha_aposentada_em_SUCESSO_continua_FORA(mundo, mc):
    """A guarda nova é ESTREITA de propósito: se ela deixasse passar o SUCESSO
    aposentado, a Decisão 55 cairia — o rerun às 3h contaria a linha VELHA como
    OK e o painel diria "concluído" sobre trabalho que foi refeito."""
    m = mundo
    malha = m.malha("M")
    pipe = m.pipeline("A")
    c = m.corrida(malha, "ABERTA")
    m.membro(c, pipe, raiz=1)
    m.execucao(pipe, c, status="SUCESSO", substituida=True)

    est = mc.estado(m.conn, mc.corrida(m.conn, c))
    assert est["ok"] == [] and est["vivos"] == []
    assert [p["classe"] for p in est["pendentes"]] == ["nao_partiu"]


# ═══ 4. de que ciclo era a linha que o rerun aposentou ══════════════════════

def test_corridas_das_linhas_responde_pelo_vinculo_e_nao_pela_data(mundo, mc):
    """Com DUAS corridas da mesma malha no mesmo dia (§6.9/#7), perguntar
    `corrida_da_data(malha, data)` devolveria a MAIS RECENTE — e o rerun de um
    membro da primeira reabriria a errada. A linha sabe de qual ciclo ela é."""
    m = mundo
    malha = m.malha("M")
    a, b, fora = m.pipeline("A"), m.pipeline("B"), m.pipeline("FORA")
    c1 = m.corrida(malha, "CONCLUIDA", data_ref=ODATE, seq=1)
    c2 = m.corrida(malha, "ABERTA", data_ref=ODATE, seq=2)
    m.execucao(a, c1, tag="a")
    m.execucao(b, c2, tag="b")
    # linha sem vinculo: pipeline fora de malha nao inventa corrida nenhuma
    self_cur = m.cur
    self_cur.execute(
        "INSERT INTO dbo.etl_pipeline_execucao (pipeline_name, "
        "data_referencia, execution_id, status, inicio) VALUES "
        "(%s, %s, %s, 'SUCESSO', SYSDATETIME())",
        (fora, ODATE, f"run-f-{m.suf}"))

    assert [c["id"] for c in mc.corridas_das_linhas(m.conn, [a], ODATE)] == [c1]
    assert [c["id"] for c in mc.corridas_das_linhas(m.conn, [a, b], ODATE)] == \
        [c1, c2]
    assert mc.corridas_das_linhas(m.conn, [fora], ODATE) == []
    # e o ODATE é exigido: o reprocesso do dia 04 não alcança o ciclo do dia 05
    assert mc.corridas_das_linhas(m.conn, [a], OUTRO_ODATE) == []
