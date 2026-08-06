"""
F11 — os caminhos até a corrida, **executados contra o SQL Server**
(`docs/spec-malha-execucao.md` §9.8, Decisão 69, e as pendências 11 e 13f do §18).

Por que este arquivo existe, no molde de `test_malha_corrida_f8_vivo.py`: os
três fatos que a F11 depende **são do banco**, e nenhum dublê os prova.

  1. **A malha do NÓ (pendência 11).** O card de `MALHA_CONCLUIDA` do nó Fim
     saía com sujeito `#no:38`. A correção é um `LEFT JOIN` que resolve o
     marcador em `etl_malha_no.malha_name` — um dublê provaria o TEXTO do
     `JOIN`; só o SQL Server prova que ele casa a linha certa (a chave é uma
     concatenação de string com `CAST`, não uma FK).
  2. **`COALESCE` de duas fontes de malha.** `COALESCE(NULL, NULL)` é erro de
     COMPILAÇÃO no SQL Server, e a coluna é montada por composição justamente
     por isso. Um dublê aceita qualquer string; o banco é quem recusa.
  3. **A pendência 13f.** "Pipeline sem cadastro com corridas ambíguas passou
     a gravar `DATA_DIVERGENTE`" — a pergunta é se isso vira **card no Teams**.
     Quem responde é a guarda de EXISTÊNCIA do `WHERE` da fila, e ela é um
     `EXISTS` correlacionado: só rodando é que se sabe se ela de fato filtra.

⚠️ **Como rodar** (o arquivo INTEIRO pula sem a variável — a senha nunca mora no
repositório):

    ORQ_TEST_MSSQL_PASSWORD='…' python3 -m pytest tests/test_malha_corrida_f11_vivo.py

⚠️ **Nada é commitado**, e o teardown CONFERE, depois do `ROLLBACK`, que nenhuma
linha com o prefixo do teste sobreviveu.

⚠️ **Nenhuma conta de tempo em Python** (Decisão 10): todo instante entra como
`SYSDATETIME()`. O SQL Server do dev está ~3h à frente do worker.
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import date
from pathlib import Path

import pytest

from tests.test_dependencias_f6_vivo import _conectar

_ROOT = Path(__file__).parent.parent

ODATE = date(2026, 8, 4)


def _modulo(nome: str, rel: str):
    spec = importlib.util.spec_from_file_location(nome, _ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def dep():
    """O canônico de `dags/` — a árvore com `%s` (pymssql), que é o MESMO texto
    que a guardiã manda em produção."""
    return _modulo("dependencias_dags_f11_vivo", "dags/utils/dependencias.py")


@pytest.fixture(scope="module")
def teams():
    return _modulo("ds_teams_f11_vivo", "dags/utils/ds_teams.py")


class Mundo:
    PREFIXO = "ZZ_F11VIVO_"

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

    def no(self, malha, tipo="fim"):
        self.cur.execute(
            "INSERT INTO dbo.etl_malha_no (malha_name, tipo, config_json) "
            "OUTPUT INSERTED.id VALUES (%s, %s, N'{}')", (malha, tipo))
        return self.cur.fetchone()[0]

    def corrida(self, malha, data_ref=ODATE, seq=1):
        self.cur.execute(
            "INSERT INTO dbo.etl_malha_execucao (malha_name, data_referencia, "
            "sequencia, status, aberta_em, fechada_em, fechada_por, origem, "
            "modo_fechamento) OUTPUT INSERTED.id VALUES "
            "(%s, %s, %s, 'CONCLUIDA', DATEADD(hour, -6, SYSDATETIME()), "
            "DATEADD(hour, -1, SYSDATETIME()), 'guardia', 'manual', "
            "'quiescencia')", (malha, data_ref, seq))
        return self.cur.fetchone()[0]

    def evento(self, chave, tipo, corrida_id=None, data_ref=ODATE):
        self.cur.execute(
            "INSERT INTO dbo.etl_dependencia_evento (pipeline_name, "
            "data_referencia, tipo, detalhe, malha_execucao_id) "
            "VALUES (%s, %s, %s, N'detalhe do teste', %s)",
            (chave, data_ref, tipo, corrida_id))

    def da_fila(self, dep_mod, chave):
        """A linha DESTE teste dentro da fila real — o banco dev tem eventos de
        outros cenários, e filtrar aqui é o que torna a asserção sobre a linha,
        e não sobre o estado do ambiente."""
        for ev in dep_mod.eventos_nao_notificados(self.conn, 500, 30):
            if ev["pipeline"] == chave:
                return ev
        return None


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
                               ("etl_malha_no", "malha_name"),
                               ("etl_malha_execucao", "malha_name"),
                               ("etl_dependencia_evento", "pipeline_name")):
            cur.execute(f"SELECT COUNT(*) FROM dbo.{tabela} "
                        f"WHERE {coluna} LIKE %s", (f"{Mundo.PREFIXO}%",))
            n = cur.fetchone()[0]
            if n:
                sobrou.append(f"{tabela}={n}")
        conn.close()
        assert not sobrou, f"o ROLLBACK deixou lixo no banco dev: {sobrou}"


# ═══ 1. Pendência 11 — a fila resolve a malha do NÓ ═════════════════════════

def test_a_fila_resolve_a_malha_do_marcador_de_no(mundo, dep, teams):
    """O defeito medido na `main`: `MALHA_CONCLUIDA` do nó Fim chegava ao
    celular com sujeito `#no:38` e fato `Pipeline: #no:38`.

    O evento do nó NÃO tem `malha_execucao_id` — é por isso que a resolução da
    F2 (que só olhava a corrida) o deixava mudo. Aqui o cenário é o real: nó
    gravado, evento com o marcador, `malha_execucao_id` NULL."""
    malha = mundo.malha("MALHA")
    no_id = mundo.no(malha, "fim")
    chave = f"#no:{no_id}"
    mundo.evento(chave, "MALHA_CONCLUIDA")

    ev = mundo.da_fila(dep, chave)
    assert ev is not None, "o evento do nó sumiu da fila"
    assert ev["malha"] == malha
    assert ev["corrida_id"] is None      # nó não tem corrida — e não inventa

    card = teams.montar_card_dependencia(ev)
    texto = str(card)
    assert "#no:" not in texto and chave not in texto
    assert malha in texto


def test_a_corrida_tem_precedencia_sobre_o_no_na_malha_do_evento(mundo, dep):
    """O `COALESCE` tem ordem, e ela não é arbitrária: a corrida é a fonte mais
    específica (é ELA que o card nomeia pela data). O nó é o fallback de quem
    não tem corrida nenhuma."""
    malha_no = mundo.malha("MALHA_DO_NO")
    malha_corrida = mundo.malha("MALHA_DA_CORRIDA")
    no_id = mundo.no(malha_no, "fim")
    corrida_id = mundo.corrida(malha_corrida)
    chave = f"#no:{no_id}"
    mundo.evento(chave, "MALHA_CONCLUIDA", corrida_id=corrida_id)

    ev = mundo.da_fila(dep, chave)
    assert ev["malha"] == malha_corrida
    assert ev["corrida_id"] == corrida_id


def test_evento_de_no_APAGADO_continua_fora_do_canal(mundo, dep):
    """O `LEFT JOIN` novo é do CARD, não do filtro. Se ele tivesse virado a
    guarda, o evento de um nó já excluído voltaria a virar card — o achado 2 da
    revisão da F14, reintroduzido pela correção da pendência 11."""
    mundo.cur.execute("SELECT ISNULL(MAX(id), 0) + 90000 FROM dbo.etl_malha_no")
    inexistente = mundo.cur.fetchone()[0]
    chave = f"#no:{inexistente}"
    mundo.evento(chave, "MALHA_CONCLUIDA")
    assert mundo.da_fila(dep, chave) is None


# ═══ 2. Pendência 13f — o DATA_DIVERGENTE de quem não tem cadastro ══════════

def test_data_divergente_de_pipeline_SEM_CADASTRO_nao_vira_card(mundo, dep):
    """Pendência 13f do §18, respondida com o banco.

    A F7 pôs a recusa por ODATE ambíguo ANTES da checagem de cadastro
    (`etl_dependencia_guardia.py:620` × `:634`), então um pipeline **sem
    cadastro** com corridas ambíguas passou a GRAVAR `DATA_DIVERGENTE` onde
    antes só logava "sem cadastro". A pergunta da pendência é se isso virou
    RUÍDO NOVO no celular.

    A resposta é **não**, e quem responde é a guarda de existência da fila
    (achado 2 da revisão da F14): "sem cadastro" é exatamente
    `config_dependente() is None`, que é exatamente "não existe em
    `etl_pipeline`" — a mesma condição que o `EXISTS` do `WHERE` exige para o
    evento sair ao canal. O evento FICA na tabela (histórico, filosofia F4
    §7.2) e aparece no painel; ele só não vira card para uma coisa que o
    cadastro não conhece.

    ⚠️ Este teste é a rede: se algum dia a guarda de existência sair da fila, é
    aqui que o ruído novo aparece — antes de aparecer no celular do plantão."""
    fantasma = mundo.n("SEM_CADASTRO")     # de propósito NÃO inserido
    mundo.evento(fantasma, "DATA_DIVERGENTE")

    # gravado, sim — o rastro do incidente não se perde…
    mundo.cur.execute(
        "SELECT COUNT(*) FROM dbo.etl_dependencia_evento "
        "WHERE pipeline_name = %s", (fantasma,))
    assert mundo.cur.fetchone()[0] == 1
    # …e fora do canal, que é o que a pendência perguntava.
    assert mundo.da_fila(dep, fantasma) is None


def test_o_MESMO_evento_com_cadastro_vira_card(mundo, dep):
    """A contraprova, sem a qual o teste acima passaria por qualquer motivo
    (uma fila quebrada devolveria vazio para tudo)."""
    real = mundo.pipeline("COM_CADASTRO")
    mundo.evento(real, "DATA_DIVERGENTE")
    assert mundo.da_fila(dep, real) is not None


# ═══ 3. A config da Decisão 69, medida no banco ═════════════════════════════

def test_a_chave_app_base_url_EXISTE_no_banco(mundo):
    """A migration 086 aplicada, medida — e não presumida.

    A chave existir é o que a torna DESCOBERTA na tela de configuração: sem a
    linha, ligar o botão viraria um `INSERT` à mão no banco de produção, que é
    o gesto que esta migration existe para evitar. O VALOR é outra história
    (nasce vazio de propósito, pendência 9 do §18) e tem teste próprio logo
    abaixo."""
    mundo.cur.execute("SELECT COUNT(*) FROM dbo.etl_app_config "
                      "WHERE config_key = 'app_base_url'")
    assert mundo.cur.fetchone()[0] == 1, \
        "migration 086 não aplicada neste banco (etapa 6c do deploy.sh)"


def test_app_base_url_existe_e_o_default_e_SEM_BOTAO(mundo, dep, teams):
    """A migration 086 cria a chave VAZIA de propósito: o endereço muda por
    ambiente e migration não adivinha host de produção. O que este teste fixa é
    a consequência — com o default, o card sai **exatamente como hoje**."""
    base = dep.app_base_url(mundo.conn)
    assert isinstance(base, str)
    if base == "":
        card = teams.montar_card_malha(
            {"tipo": "MALHA_FALHOU", "malha": "M", "data_ref": "2026-08-04"},
            base)
        assert "actions" not in card["attachments"][0]["content"]
    else:
        # Ambiente com a chave já preenchida (o dev depois da pendência 9):
        # então o botão TEM de existir e apontar para lá.
        assert base.startswith("http")
        card = teams.montar_card_malha(
            {"tipo": "MALHA_FALHOU", "malha": "M", "data_ref": "2026-08-04",
             "corrida_id": 12}, base)
        url = card["attachments"][0]["content"]["actions"][0]["url"]
        assert url == f"{base.rstrip('/')}/malha?malha=M&modo=execucao&corrida=12"


# ═══ 4. A malha ÚNICA do dependente (Decisão 70), medida no servidor ════════

def test_a_malha_do_dependente_e_NULL_quando_ele_esta_em_DUAS(mundo):
    """`HAVING COUNT(*) = 1` — a regra inteira da coluna, executada pelo SQL
    Server e não por um dublê.

    ⚠️ Este teste nasceu de uma MUTAÇÃO que sobreviveu: com o `HAVING` apagado
    da consulta, a suíte inteira continuava verde, porque o dublê do banco
    reimplementava a regra em Python. É o modo de falso verde "dublê que aplica
    a guarda que mora no WHERE", e a única cura é perguntar ao servidor.

    O ponto sutil que só o banco responde: `HAVING` **sem** `GROUP BY` sobre
    uma correlacionada. Com 2 malhas o grupo único é descartado, a subconsulta
    escalar não devolve linha nenhuma e o resultado é `NULL` — que é a resposta
    certa ("não sei qual"), e não "a primeira". O link do Dashboard abrindo a
    malha errada com cara de certa é pior que o link de hoje, que abre a lista.
    """
    from routers.pipelines import SQL_MALHA_UNICA_DO_PIPELINE

    so_uma = mundo.pipeline("EM_UMA_MALHA")
    em_duas = mundo.pipeline("EM_DUAS_MALHAS")
    m1, m2 = mundo.malha("M_ALFA"), mundo.malha("M_BETA")
    for pipe, malhas in ((so_uma, [m1]), (em_duas, [m1, m2])):
        for malha in malhas:
            mundo.cur.execute(
                "INSERT INTO dbo.etl_malha_pipeline (malha_name, pipeline_name) "
                "VALUES (%s, %s)", (malha, pipe))

    # A consulta é a do router, byte a byte — só o `d` da correlação vira uma
    # tabela derivada aqui, porque o `FROM` de lá é a consulta de dependências.
    mundo.cur.execute(
        "SELECT d.pipeline_name, " + SQL_MALHA_UNICA_DO_PIPELINE + " "
        "FROM (SELECT %s AS pipeline_name UNION ALL SELECT %s) d "
        "ORDER BY d.pipeline_name", (so_uma, em_duas))
    resultado = dict(mundo.cur.fetchall())

    assert resultado[so_uma] == m1
    assert resultado[em_duas] is None, \
        "o servidor escolheu uma malha para um pipeline que está em duas"
