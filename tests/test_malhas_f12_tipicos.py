"""
F12 da spec `docs/spec-malha-execucao.md` — a **duração TÍPICA por membro**
(§9.5, Decisão 64): o número que decide *posso esperar*.

`4 de 7 · 2 rodando · há 12 min` não diz se os dois vivos são de 5 min ou de
3h — e, pior, `4 de 7` com os dois mais pesados ainda por rodar parece "quase
lá" e manda o operador dormir. Esta suíte prova o SERVIDOR desse número; o que
o operador LÊ está em `test_malhas_f12_front.py`.

O que se prova aqui, e por que cada prova existe:

  • **o piso `n ≥ 5` é DURO e mora no `HAVING`** — membro com 3 execuções não
    aparece no payload, e por isso não há como a tela publicar `(n=3)` ao lado
    de nada. Um número sem amostra com cara de medida é o defeito que esta spec
    inteira existe para não cometer;
  • **`p50` e `n` viajam JUNTOS** — não existe item com um sem o outro;
  • **só execução LIMPA entra na mediana** (sem `FAILED`/`RUNNING`, sem
    `end_time` nulo): uma execução que quebrou no meio termina cedo e puxaria a
    mediana para baixo, e o número serviria para tudo menos para decidir
    esperar;
  • **`completo`** (a pré-condição da Decisão 56b): só é `true` com TODOS os
    membros do snapshot acima do piso. Faltando um, o percentual de tempo
    típico não existe na tela — e é este campo que diz isso ao front;
  • **degradação por AUSÊNCIA DE CHAVE** (Decisão 41): erro de leitura, banco
    sem histórico ou lente sem corrida devolvem 200 SEM a chave `tipicos`, e o
    painel volta a mostrar só o decorrido. Nunca 500, nunca `tipicos: null`;
  • **uma consulta por painel, e cacheada** — a duração típica é número de
    escala de DIAS, e o painel refaz a leitura a cada 15–30 s;
  • **o `CAST` do lado PEQUENO**, que é custo medido e não estética:
    `etl_malha_execucao_membro.pipeline_name` é NVARCHAR e
    `etl_job_execution.pipeline` é VARCHAR. Comparados direto, a coluna da
    tabela GRANDE é convertida e o seek morre — 4.822 leituras lógicas e 169 ms
    contra 156 e 10 ms, medidos no dev com 480.000 linhas.

⚠️ REGRA DE HONESTIDADE DO DUBLÊ (a mesma da F4/F10): toda guarda que mora no
SQL é lida do TEXTO do statement (`_guarda`). Apagar uma cláusula do módulo tem
de MUDAR o que o dublê devolve — senão a mutação passa verde e o teste vira
enfeite.

⚠️ O interruptor `malha_corrida_ativa` fica DESLIGADO (o estado do dev e o do
dia do deploy): a LEITURA da corrida não depende dele.
"""
from __future__ import annotations

import os
import statistics
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from routers import malhas as malhas_router
from tests.test_malha_corrida_porta import _guarda
from tests.test_malha_corrida_agregado_f10 import (FakeCur as FakeCurF10,
                                                   FakeDb as FakeDbF10)
from tests.test_malhas_f4_card import (ODATE, _patch, _patch_agora,  # noqa: F401
                                       _pipes, auth)
from tests.test_malhas_f10 import _monta_malha

# O prefixo do agregado desta fase — é por ele que a contagem de statements
# distingue "a consulta da duração típica" das dezenas que o painel emite.
PREFIXO_TIPICOS = "WITH membros AS ("

ABERTURA = datetime(2026, 8, 5, 1, 0)


# ═══════════════════ o dublê: a F10 + o histórico de jobs ═══════════════════

class FakeDb(FakeDbF10):
    """FakeDb da F10 + `etl_job_execution` (o histórico de sempre)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.jobs: list[dict] = []
        # Lock timeout na maior tabela do schema às 3h é cenário real — e a
        # resposta a ele é o painel calar sobre o típico, não estourar.
        self.falhar_tipicos = False

    def cursor(self):
        # A cadeia de dublês instancia o cursor pelo NOME do módulo dela; sem
        # esta linha, o dispatcher desta fase nunca entraria no caminho e a
        # consulta nova cairia no "SQL não previsto" — teste vermelho pela
        # razão errada.
        super().cursor()            # mantém o snapshot da transação
        return FakeCur(self)

    def job(self, pipeline, execution_id, inicio, fim, status="SUCCESS",
            job_name="J1"):
        self.jobs.append({"pipeline": pipeline, "execution_id": execution_id,
                          "job_name": job_name, "start_time": inicio,
                          "end_time": fim, "status": status})

    def historico(self, pipeline, quantas, minutos, *, ate=None, sufixo=""):
        """`quantas` execuções LIMPAS de `minutos` cada, uma por dia.

        Duas linhas de job por execução, porque a duração do PIPELINE é de
        ponta a ponta (`MIN(start_time)` → `MAX(end_time)`) e não a soma dos
        jobs — um dublê de um job só não distinguiria as duas leituras."""
        fim_janela = ate or (ABERTURA - timedelta(days=1))
        for i in range(quantas):
            ini = fim_janela - timedelta(days=i)
            exec_id = f"{pipeline}{sufixo}__{i}"
            self.job(pipeline, exec_id, ini,
                     ini + timedelta(minutes=minutos / 2), job_name="J1")
            self.job(pipeline, exec_id, ini + timedelta(minutes=minutos / 2),
                     ini + timedelta(minutes=minutos), job_name="J2")


class FakeCur(FakeCurF10):
    def execute(self, sql, params=()):  # noqa: C901 — dispatcher de dublê
        db = self.db
        s = " ".join(str(sql).split())
        if s.startswith(PREFIXO_TIPICOS):
            db.sqls.append(s)
            if db.falhar_tipicos:
                raise RuntimeError("lock timeout em etl_job_execution")
            # O driver conta os marcadores; o dublê também (a mesma trava da
            # F4: um dublê mais permissivo que o pyodbc deixa passar SQL que o
            # banco recusaria na primeira chamada).
            assert s.count("?") == len(tuple(params)), (
                "SQL com %d marcador(es) e %d parametro(s):\n%s"
                % (s.count("?"), len(tuple(params)), s))
            self._rows = self._tipicos(s, tuple(params))
            self.rowcount = -1
            return
        super().execute(sql, params)

    def _tipicos(self, s, p):
        """O agregado, avaliado DE VERDADE sobre o estado do dublê.

        As SEIS guardas são lidas do TEXTO: o recorte da corrida, o snapshot da
        abertura, a janela, as duas de execução limpa, o teto de amostra e o
        piso. Aplicar qualquer uma "de graça" tornaria a cláusula
        indestrutível por mutação — que é como uma regra desaparece do SQL com
        a suíte verde."""
        db = self.db
        cid, dias, limite, piso = int(p[0]), int(p[1]), int(p[2]), int(p[3])
        so_corrida = _guarda(s, "WHERE mm.malha_execucao_id = ?")
        so_ativos = _guarda(s, "AND mm.ativo_na_abertura = 1")
        tem_janela = _guarda(
            s, "AND j.start_time >= DATEADD(DAY, ?, SYSDATETIME())")
        exige_fim = _guarda(s, "HAVING COUNT(*) = COUNT(j.end_time)")
        exige_limpa = _guarda(
            s, "AND SUM(CASE WHEN j.status IN ('FAILED','RUNNING') "
               "THEN 1 ELSE 0 END) = 0")
        tem_limite = _guarda(s, "FROM execucoes WHERE rn <= ?")
        tem_piso = _guarda(s, "HAVING COUNT(*) >= ?")

        membros = [m for m in db.membros_corrida
                   if (not so_corrida or int(m["malha_execucao_id"]) == cid)
                   and (not so_ativos or m["ativo_na_abertura"])]
        # O SQL Server compara nome de pipeline SEM distinguir caixa (é a
        # collation do banco); o dict do Python distingue. O dublê imita o
        # banco, senão a ponte de caixa do módulo passaria despercebida.
        nomes = {str(m["pipeline_name"]).strip().casefold(): m["pipeline_name"]
                 for m in membros}
        # A janela é do relógio do BANCO — `SYSDATETIME()`, nunca `datetime.now`
        # do processo (o dublê põe o banco 3h à frente, como no dev).
        corte = db.agora_banco + timedelta(days=dias)

        por_execucao: dict = {}
        for j in db.jobs:
            chave_pipe = str(j["pipeline"]).strip().casefold()
            if chave_pipe not in nomes:
                continue
            if tem_janela and j["start_time"] < corte:
                continue
            por_execucao.setdefault((chave_pipe, j["execution_id"]),
                                    []).append(j)

        duracoes: dict = {}
        for (chave_pipe, _exec_id), linhas in por_execucao.items():
            if exige_fim and any(x["end_time"] is None for x in linhas):
                continue
            if exige_limpa and any(x["status"] in ("FAILED", "RUNNING")
                                   for x in linhas):
                continue
            inicio = min(x["start_time"] for x in linhas)
            fim = max(x["end_time"] for x in linhas
                      if x["end_time"] is not None)
            duracoes.setdefault(chave_pipe, []).append(
                (inicio, int((fim - inicio).total_seconds())))

        saida = []
        for chave_pipe, execucoes in duracoes.items():
            execucoes.sort(key=lambda x: x[0], reverse=True)
            recortadas = execucoes[:limite] if tem_limite else execucoes
            segundos = [d for _, d in recortadas if d > 0]
            if not segundos:
                continue
            if tem_piso and len(segundos) < piso:
                continue
            saida.append((nomes[chave_pipe],
                          float(statistics.median(segundos)), len(segundos)))
        return sorted(saida)


def _cadastro():
    """O cadastro da F4 mais os nomes desta fase — os cenários da spec falam de
    `CARGA_D` (o que demora 2x) e `CARGA_E` (o que não tem amostra)."""
    base = _pipes()
    modelo = dict(next(iter(base.values())))
    for nome in ("CARGA_D", "CARGA_E"):
        base[nome] = dict(modelo)
    return base


@pytest.fixture(autouse=True)
def _sem_cache_tipicos():
    """O cache é do PROCESSO: sem esta limpeza um teste herdaria o número do
    anterior e a suíte provaria o cache em vez da consulta."""
    malhas_router.limpar_cache_tipicos()
    yield
    malhas_router.limpar_cache_tipicos()


def _painel(db, client, *, membros=("CARGA_B",), corrida=True):
    _monta_malha(client, "M1", list(membros))
    c = None
    if corrida:
        c = db.abrir_corrida("M1", odate=ODATE, aberta_em=ABERTURA,
                             membros=list(membros))
    alvo = f"?corrida={c['id']}" if c else f"?data_referencia={ODATE}"
    return client.get(f"/malhas/M1/execucao{alvo}").json(), c


# ═══════════════ o aceite: 23 execuções → típico 18 min (n=23) ══════════════

def test_o_membro_com_23_execucoes_traz_o_tipico_e_o_n(client, auth):
    """O aceite literal da fase, do lado do servidor: `típico 18 min (n=23)`.

    O `p50` sai em SEGUNDOS (a unidade crua da fonte, igual ao irmão mais velho
    `GET /execucoes/duracao-media`); quem vira minutos é a tela."""
    db = FakeDb(pipelines=_cadastro())
    with _patch(db), _patch_agora():
        db.historico("CARGA_B", 23, minutos=18)
        painel, _ = _painel(db, client)
    itens = painel["tipicos"]["itens"]
    assert itens == [{"pipeline": "CARGA_B", "p50_seg": 18 * 60, "n": 23}]
    assert painel["tipicos"]["piso_n"] == 5


def test_p50_e_n_nunca_viajam_um_sem_o_outro(client, auth):
    """O `n` não aparece sozinho na tela porque não existe sozinho no payload:
    é a garantia estrutural do aceite, e não um `if` no componente."""
    db = FakeDb(pipelines=_cadastro())
    with _patch(db), _patch_agora():
        db.historico("CARGA_B", 23, minutos=18)
        db.historico("CARGA_D", 9, minutos=41)
        painel, _ = _painel(db, client, membros=("CARGA_B", "CARGA_D"))
    for item in painel["tipicos"]["itens"]:
        assert set(item) == {"pipeline", "p50_seg", "n"}
        assert item["p50_seg"] > 0 and item["n"] >= 5


# ═══════════════ o piso é DURO: 3 execuções não viram número ════════════════

def test_o_piso_e_duro_membro_com_3_execucoes_some_do_payload(client, auth):
    """Aceite: membro com **3** execuções → só o decorrido, sem "típico" e sem
    `n`. O piso mora no `HAVING` do servidor — a tela não tem como errar."""
    db = FakeDb(pipelines=_cadastro())
    with _patch(db), _patch_agora():
        db.historico("CARGA_B", 23, minutos=18)
        db.historico("CARGA_E", 3, minutos=7)
        painel, _ = _painel(db, client, membros=("CARGA_B", "CARGA_E"))
    nomes = [i["pipeline"] for i in painel["tipicos"]["itens"]]
    assert nomes == ["CARGA_B"]
    assert painel["tipicos"]["com_historico"] == 1
    assert painel["tipicos"]["membros"] == 2


def test_o_piso_de_5_e_o_limiar_exato(client, auth):
    """5 entra, 4 não — o limiar declarado, não "por volta de cinco"."""
    db = FakeDb(pipelines=_cadastro())
    with _patch(db), _patch_agora():
        db.historico("CARGA_B", 5, minutos=18)
        db.historico("CARGA_E", 4, minutos=18)
        painel, _ = _painel(db, client, membros=("CARGA_B", "CARGA_E"))
    assert [i["pipeline"] for i in painel["tipicos"]["itens"]] == ["CARGA_B"]


# ═══════════════ `completo`: a pré-condição da Decisão 56b ══════════════════

def test_completo_exige_TODOS_os_membros_acima_do_piso(client, auth):
    """Decisão 56b: o percentual de tempo típico só existe com `n ≥ 5` em
    TODOS os membros. Faltando um, ele some por completo — não é estimado, não
    é "aproximado com ressalva". `completo` é o campo que diz isso ao front."""
    db = FakeDb(pipelines=_cadastro())
    with _patch(db), _patch_agora():
        db.historico("CARGA_B", 23, minutos=18)
        db.historico("CARGA_D", 11, minutos=40)
        db.historico("CARGA_E", 3, minutos=7)      # o que falta
        painel, _ = _painel(db, client,
                            membros=("CARGA_B", "CARGA_D", "CARGA_E"))
    assert painel["tipicos"]["completo"] is False

    db2 = FakeDb(pipelines=_cadastro())
    with _patch(db2), _patch_agora():
        db2.historico("CARGA_B", 23, minutos=18)
        db2.historico("CARGA_D", 11, minutos=40)
        painel2, _ = _painel(db2, client, membros=("CARGA_B", "CARGA_D"))
    assert painel2["tipicos"]["completo"] is True


def test_snapshot_vazio_nao_vira_completo(client, auth):
    """`membros = 0` com lista vazia satisfaz "todos têm histórico" por
    vacuidade — e publicaria um percentual sobre nada."""
    db = FakeDb(pipelines=_cadastro())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["CARGA_B"])
        c = db.abrir_corrida("M1", odate=ODATE, aberta_em=ABERTURA, membros=[])
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
    assert painel["tipicos"]["itens"] == []
    assert painel["tipicos"]["completo"] is False


# ═══════════════ só execução LIMPA entra na mediana ═════════════════════════

def test_execucao_com_job_FAILED_nao_entra_na_mediana(client, auth):
    """Execução que quebrou no meio termina cedo: contá-la puxaria a mediana
    para baixo e o número serviria para tudo, menos para decidir esperar."""
    db = FakeDb(pipelines=_cadastro())
    with _patch(db), _patch_agora():
        db.historico("CARGA_B", 6, minutos=18)
        # uma execução curta e SUJA, bem no meio da janela
        quebrada = ABERTURA - timedelta(days=2, hours=3)
        db.job("CARGA_B", "quebrada", quebrada,
               quebrada + timedelta(minutes=1), status="FAILED")
        painel, _ = _painel(db, client)
    item = painel["tipicos"]["itens"][0]
    assert (item["n"], item["p50_seg"]) == (6, 18 * 60)


def test_execucao_ainda_em_curso_nao_entra_na_mediana(client, auth):
    """`end_time` nulo é execução VIVA: medir "até agora" transformaria a
    mediana num número que cresce sozinho enquanto o operador olha."""
    db = FakeDb(pipelines=_cadastro())
    with _patch(db), _patch_agora():
        db.historico("CARGA_B", 6, minutos=18)
        db.job("CARGA_B", "viva", ABERTURA - timedelta(hours=1), None,
               status="RUNNING")
        painel, _ = _painel(db, client)
    assert painel["tipicos"]["itens"][0]["n"] == 6


def test_a_duracao_e_de_ponta_a_ponta_nao_a_soma_dos_jobs(client, auth):
    """O que o operador vê passar é `MIN(start_time)` → `MAX(end_time)` — a
    mesma identidade de execução que o card de fim das DAGs geradas usa."""
    db = FakeDb(pipelines=_cadastro())
    with _patch(db), _patch_agora():
        for i in range(5):
            ini = ABERTURA - timedelta(days=i + 1)
            # dois jobs SOBREPOSTOS de 10 min: a soma daria 20, a ponta a
            # ponta dá 12 — e 12 é o tempo que passou no relógio.
            db.job("CARGA_B", f"e{i}", ini, ini + timedelta(minutes=10), "SUCCESS", "J1")
            db.job("CARGA_B", f"e{i}", ini + timedelta(minutes=2),
                   ini + timedelta(minutes=12), "SUCCESS", "J2")
        painel, _ = _painel(db, client)
    assert painel["tipicos"]["itens"][0]["p50_seg"] == 12 * 60


# ═══════════════ a janela e o teto de amostra ═══════════════════════════════

def test_a_janela_de_90_dias_recorta_o_historico(client, auth):
    """Mediana de execuções de um ano atrás descreve uma malha que já mudou de
    forma — job novo, servidor novo. O corte é do relógio do BANCO."""
    db = FakeDb(pipelines=_cadastro())
    with _patch(db), _patch_agora():
        db.historico("CARGA_B", 6, minutos=18)
        db.historico("CARGA_B", 20, minutos=90, sufixo="_velho",
                     ate=ABERTURA - timedelta(days=200))
        painel, _ = _painel(db, client)
    item = painel["tipicos"]["itens"][0]
    assert (item["n"], item["p50_seg"]) == (6, 18 * 60)
    assert painel["tipicos"]["janela_dias"] == malhas_router.TIPICO_JANELA_DIAS


def test_o_teto_de_execucoes_limita_a_amostra(client, auth):
    """A mediana de 30 já é estável; o que passa disso só envelhece o número."""
    db = FakeDb(pipelines=_cadastro())
    with _patch(db), _patch_agora():
        db.historico("CARGA_B", 60, minutos=18)
        painel, _ = _painel(db, client)
    assert painel["tipicos"]["itens"][0]["n"] == malhas_router.TIPICO_MAX_EXECUCOES
    assert painel["tipicos"]["limite_execucoes"] == 30


def test_as_execucoes_mais_recentes_e_que_valem(client, auth):
    """Com o teto batendo, o recorte tem de ser pelo TOPO: a malha de hoje é a
    das últimas noites, não a de três meses atrás."""
    db = FakeDb(pipelines=_cadastro())
    with _patch(db), _patch_agora():
        db.historico("CARGA_B", 30, minutos=10)                    # recentes
        db.historico("CARGA_B", 30, minutos=60, sufixo="_antigo",
                     ate=ABERTURA - timedelta(days=40))            # antigas
        painel, _ = _painel(db, client)
    assert painel["tipicos"]["itens"][0]["p50_seg"] == 10 * 60


# ═══════════════ escopo: o snapshot, e só ele ═══════════════════════════════

def test_so_os_membros_do_snapshot_entram(client, auth):
    """`etl_job_execution` é o histórico do banco INTEIRO. Sem o recorte do
    snapshot, o painel de uma malha de 3 membros leria a casa toda."""
    db = FakeDb(pipelines=_cadastro())
    with _patch(db), _patch_agora():
        db.historico("CARGA_B", 23, minutos=18)
        db.historico("P1", 23, minutos=18)         # de outra malha
        painel, _ = _painel(db, client)
    assert [i["pipeline"] for i in painel["tipicos"]["itens"]] == ["CARGA_B"]


def test_o_nome_do_membro_e_comparado_SEM_caixa(client, auth):
    """O snapshot guarda a grafia do dia da abertura e o histórico guarda a que
    a DAG escreveu. Divergirem em caixa é o GOTCHA que já quebrou pipeline em
    produção — aqui ele custaria o número sumindo em silêncio."""
    db = FakeDb(pipelines=_cadastro())
    with _patch(db), _patch_agora():
        db.historico("carga_b", 23, minutos=18)    # o histórico, em minúsculas
        painel, _ = _painel(db, client, membros=("CARGA_B",))
    assert painel["tipicos"]["itens"][0]["n"] == 23


# ═══════════════ degradação: 200 sem a chave, nunca 500 ═════════════════════

def test_erro_de_leitura_degrada_sem_a_chave_e_sem_500(client, auth):
    """Lock timeout na maior tabela do schema às 3h. A resposta é o painel
    calar sobre o típico — o resto da visão intacto (princípio 6)."""
    db = FakeDb(pipelines=_cadastro())
    with _patch(db), _patch_agora():
        db.historico("CARGA_B", 23, minutos=18)
        db.falhar_tipicos = True
        _monta_malha(client, "M1", ["CARGA_B"])
        c = db.abrir_corrida("M1", odate=ODATE, aberta_em=ABERTURA,
                             membros=["CARGA_B"])
        r = client.get(f"/malhas/M1/execucao?corrida={c['id']}")
    assert r.status_code == 200
    painel = r.json()
    assert "tipicos" not in painel          # ausência, nunca `null`
    assert painel["corrida"]["id"] == c["id"]
    assert "execucoes" in painel


def test_sem_corrida_na_lente_a_chave_nem_existe(client, auth):
    """Sem snapshot não há "típico de quem": navegar por DIA continua byte a
    byte o que era antes desta fase."""
    db = FakeDb(pipelines=_cadastro())
    with _patch(db), _patch_agora():
        db.historico("CARGA_B", 23, minutos=18)
        painel, _ = _painel(db, client, corrida=False)
    assert "tipicos" not in painel
    assert not [s for s in db.sqls if s.startswith(PREFIXO_TIPICOS)]


def test_membro_sem_historico_nenhum_nao_quebra_nada(client, auth):
    """O dia 1 de uma malha nova: nenhum membro tem amostra. A lista sai
    VAZIA, `completo` sai `false`, e nenhuma frase desta fase é renderizada."""
    db = FakeDb(pipelines=_cadastro())
    with _patch(db), _patch_agora():
        painel, _ = _painel(db, client, membros=("CARGA_B", "CARGA_D"))
    assert painel["tipicos"]["itens"] == []
    assert painel["tipicos"]["completo"] is False
    assert painel["tipicos"]["com_historico"] == 0


# ═══════════════ custo: uma consulta por painel, e cacheada ═════════════════

def test_uma_consulta_por_painel_e_o_custo_nao_cresce_com_o_membro(client, auth):
    """O agregado é de CONJUNTO: 1 membro e 12 membros gastam o MESMO
    statement. Um `N+1` aqui multiplicaria o custo do refetch pelo tamanho da
    malha — e o tamanho da malha é o que cresce durante o incidente."""
    db = FakeDb(pipelines=_cadastro())
    with _patch(db), _patch_agora():
        for i in range(12):
            db.historico(f"P{i}", 8, minutos=5 + i)
        _monta_malha(client, "M1", [f"P{i}" for i in range(12)])
        c = db.abrir_corrida("M1", odate=ODATE, aberta_em=ABERTURA,
                             membros=[f"P{i}" for i in range(12)])
        db.sqls.clear()
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
    assert len(db.statements(PREFIXO_TIPICOS)) == 1
    assert len(painel["tipicos"]["itens"]) == 12


def test_o_cache_tira_a_consulta_do_caminho_do_refetch(client, auth):
    """O painel relê a cada 15–30 s e a duração típica é número de escala de
    DIAS: dentro de uma madrugada ela não muda. Sem o cache, a consulta mais
    pesada desta camada seria a única a rodar em toda leitura sem que nada nela
    pudesse ter mudado."""
    db = FakeDb(pipelines=_cadastro())
    with _patch(db), _patch_agora():
        db.historico("CARGA_B", 23, minutos=18)
        _monta_malha(client, "M1", ["CARGA_B"])
        c = db.abrir_corrida("M1", odate=ODATE, aberta_em=ABERTURA,
                             membros=["CARGA_B"])
        db.sqls.clear()
        p1 = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
        p2 = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
        assert len(db.statements(PREFIXO_TIPICOS)) == 1
        assert p1["tipicos"] == p2["tipicos"]
        # ...e o cache é por CORRIDA: outra corrida não herda o número dela.
        malhas_router.limpar_cache_tipicos()
        client.get(f"/malhas/M1/execucao?corrida={c['id']}")
    assert len(db.statements(PREFIXO_TIPICOS)) == 2


# ═══════════════ o custo que só o TEXTO do SQL garante ══════════════════════

def test_o_join_converte_o_lado_PEQUENO_para_varchar(client, auth):
    """GOTCHA MEDIDO, e a razão de o `CAST` estar do lado do snapshot.

    `etl_malha_execucao_membro.pipeline_name` é NVARCHAR e
    `etl_job_execution.pipeline` é VARCHAR. Comparados direto, o NVARCHAR tem
    precedência e a COLUNA da tabela grande é convertida: o predicado deixa de
    ser sargável e o seek vira scan do índice inteiro — **4.822 leituras
    lógicas e 169 ms** contra **156 e 10 ms**, medidos no dev com 480.000
    linhas e 7 membros. É o mesmo alerta que a migration 085 escreveu sobre
    `ancora_execution_id`, agora com número."""
    sql = " ".join(malhas_router._SQL_TIPICOS.split())
    assert "CAST(mm.pipeline_name AS VARCHAR(200))" in sql
    # a coluna da tabela GRANDE entra CRUA no predicado — nada de
    # `CAST(j.pipeline …)`, que devolveria o scan pela outra porta
    assert "ON j.pipeline = m.pipeline_name" in sql
    assert "CAST(j.pipeline" not in sql


def test_a_janela_e_medida_no_relogio_do_BANCO(client, auth):
    """Decisão 10: nenhuma conta de tempo em Python no servidor. O corte da
    janela é `DATEADD` sobre `SYSDATETIME()` — com o SQL Server 3h à frente do
    container da API (o desvio medido no dev), somar dias em Python cortaria o
    histórico no lugar errado."""
    sql = " ".join(malhas_router._SQL_TIPICOS.split())
    assert "DATEADD(DAY, ?, SYSDATETIME())" in sql
    assert "GETDATE()" not in sql


def test_nao_se_enumera_o_dominio_de_status_no_where(client, auth):
    """O lever de custo que NÃO foi puxado, e a razão escrita.

    Enumerar `status` no `WHERE` tornaria a faixa de `start_time` sargável
    (o índice é `(pipeline, status, start_time)`) e a leitura cairia. O preço
    seria uma linha de status DESCONHECIDO ficar invisível — e uma execução
    suja passaria por limpa, em silêncio, na conta que decide se alguém
    acorda."""
    sql = " ".join(malhas_router._SQL_TIPICOS.split())
    # o filtro de sujeira mora no HAVING (depois do GROUP BY), nunca no WHERE
    assert ("HAVING COUNT(*) = COUNT(j.end_time) AND SUM(CASE WHEN j.status "
            "IN ('FAILED','RUNNING') THEN 1 ELSE 0 END) = 0") in sql
    assert "AND j.status IN (" not in sql
