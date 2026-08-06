"""
F10 da spec `docs/spec-malha-execucao.md` — o AGREGADO no servidor.

O DEFEITO que esta suíte trava, e ele é de CUSTO, não de conteúdo: o painel
perguntava `deps_svc.liberado()` **por membro esperando**. Numa malha de 40
membros com 12 esperando são 12 idas ao banco (36 no modo SEQUÊNCIA, porque
`inicio_do_ciclo_corrente()` gasta `SELECT GETDATE()` + a leitura da janela a
cada chamada) — e o painel se atualiza sozinho. O número de membros esperando é
justamente o número que cresce durante o incidente: o pior ordenamento possível.

O que se prova aqui, e por que cada prova existe:

  • **uma consulta de conjunto** para os pendentes, com o custo NÃO crescendo
    com quem espera. A prova é a contagem de statements, com dois cenários
    (2 esperando × 12 esperando) que têm de gastar o MESMO número — um teste que
    olhasse só o cenário de 12 passaria verde num N+1 com cache;
  • **o lote responde IGUAL ao predicado de uma linha**. Uma segunda redação do
    predicado é a divergência painel×motor que a paridade D29 existe para
    impedir, entrando pela porta do "mesmo SQL, só que em lote". Por isso são
    duas provas: a semântica (mesmo cenário, mesma resposta) e a estrutural (o
    texto do lote é montado dos MESMOS fragmentos);
  • **a cascata do deploy parcial é a mesma** — 085 → 084 → 082 → 078 → legado.
    Uma cascata que divergisse faria o painel e o motor discordarem exatamente
    no deploy parcial, que é quando a divergência é mais cara de diagnosticar;
  • **D21: erro na consulta nunca vira "liberado"**, nem em lote;
  • **o RAIO DE ALCANCE** (Decisão 63): quantos membros esta corrida tem parados
    atrás de cada pendente, e quantos deles são `ALTA`. É o número que separa
    "um job parado no fim da cadeia" de "um job parado que segura 18 outros";
  • **o ORDENAMENTO** (Decisão 73): o `refetchInterval` do painel só pode ir a
    15 s depois que o N+1 sai. Com o N+1 no caminho, encurtar o intervalo
    multiplica o estrago — o teste proíbe a ordem errada e permite as duas
    ordens certas.

⚠️ O interruptor `malha_corrida_ativa` fica **DESLIGADO** (o estado do dev e o
do dia do deploy): a LEITURA da corrida não depende dele, e esta fase tem de ser
testável assim.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from services import dependencias as deps_svc
from services import malha_corrida as mc
from routers import malhas as malhas_router
from tests.test_malha_corrida_porta import AGORA_BANCO, _guarda
from tests.test_malhas_f4_card import (ODATE, ODATE_ONTEM,
                                       FakeCur as FakeCurF4,
                                       FakeDb as FakeDbF4, _patch, _patch_agora,
                                       _pipes, auth)                # noqa: F401
from tests.test_malhas_f10 import _monta_malha

RAIZ = Path(__file__).resolve().parents[1]

# O prefixo do SQL de conjunto. É por ele que a contagem de statements do aceite
# distingue "a consulta dos pendentes" das dezenas de outras que o painel emite.
PREFIXO_LOTE = "SELECT dd.pipeline_name, dd.depende_de"
# O predicado de UMA linha — o que NÃO pode mais aparecer no caminho do painel.
PREFIXO_UMA_LINHA = "SELECT dd.depende_de FROM dbo.etl_pipeline_dependencia dd"


# ═════════════════════ o dublê: a F4 + o predicado em lote ══════════════════

class FakeDb(FakeDbF4):
    """FakeDb da F4 + as dependências, os nós e o grafo do snapshot."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        # Modo DATA por default (o do dev). Os testes do modo SEQUÊNCIA o ligam.
        self.config.setdefault("dependencia_modo_sequencia", "0")
        self.config.setdefault("dependencia_janela_sequencia_horas", "12")
        # Injeção de falha na leitura do grafo: "não consegui apurar o raio" tem
        # de ser uma resposta possível, e ela é DIFERENTE de "ninguém atrás".
        self.falhar_grafo = False
        # Banco SEM a coluna `notificado_em` (deploy parcial). O dublê imita o
        # SQL Server: "Invalid column name" — é essa marca, e não um `except`
        # cego, que autoriza a consulta de fallback.
        self.sem_notificado_em = False
        # None = a sonda do canal estoura (não perguntei); True/False = a
        # resposta do banco. O default é 'há canal', que é o mundo comum.
        self.canal_teams = True

    def depende(self, pipeline, de, origem_no=None):
        self.dependencias.append({"pipeline": pipeline, "depende_de": de,
                                  "origem_no": origem_no})

    def statements(self, prefixo):
        return [s for s in self.sqls if s.startswith(prefixo)]


class FakeCur(FakeCurF4):
    def execute(self, sql, params=()):  # noqa: C901 — dispatcher de dublê
        db = self.db
        s = " ".join(str(sql).split())
        p = tuple(params)
        if s.startswith(PREFIXO_LOTE):
            db.sqls.append(s)
            self._rows = self._lote(s, p)
            self.rowcount = -1
            return
        if s.startswith("SELECT TOP 1 1 FROM dbo.etl_msg_grupo"):
            # A sonda "há canal do Teams?". O dublê NÃO decide sozinho: ele
            # devolve o que o cenário montou, e um cenário que não a espera
            # (canal_teams=None) faz a consulta estourar — assim, chamá-la onde
            # não devia vira teste vermelho em vez de passar despercebido.
            db.sqls.append(s)
            if db.canal_teams is None:
                raise RuntimeError("lock timeout em etl_msg_grupo")
            self._rows = [(1,)] if db.canal_teams else []
            self.rowcount = -1
            return
        if s.startswith("SELECT pipeline_name, tipo, detectado_em") \
                and "notificado_em" in s and db.sem_notificado_em:
            db.sqls.append(s)
            raise RuntimeError("Invalid column name 'notificado_em'.")
        if s.startswith("SELECT mm.pipeline_name, p.criticidade, d.depende_de"):
            db.sqls.append(s)
            if db.falhar_grafo:
                raise RuntimeError("lock timeout em etl_malha_execucao_membro")
            self._rows = self._grafo(s, p)
            self.rowcount = -1
            return
        # O predicado de UMA LINHA continua atendido: é ele que os testes de
        # PARIDADE comparam com o lote. Que ele saia do caminho do painel é
        # provado pela CONTAGEM, não por ele deixar de existir no dublê — o
        # port continua sendo a função que o motor usa.
        if s.startswith(PREFIXO_UMA_LINHA) and "NOT EXISTS" in s:
            db.sqls.append(s)
            self._rows = [(f,) for f in self._faltantes(s, p[0], p[1])]
            self.rowcount = -1
            return
        # Os dois agregados do CARD que leem a 067. O dublê da base os atende
        # com `db.dependencias` no formato de TUPLA; daqui para baixo da cadeia
        # ele é DICT (a F8 o trocou), e sem estes dois `GET /malhas` estouraria
        # `KeyError: 0` em qualquer cenário que declare dependência — que é
        # justamente o cenário desta fase.
        if s.startswith("SELECT DISTINCT pipeline_name "
                        "FROM dbo.etl_pipeline_dependencia"):
            db.sqls.append(s)
            self._rows = [(x,) for x in
                          sorted({d["pipeline"] for d in db.dependencias})]
            self.rowcount = -1
            return
        if s.startswith("SELECT pipeline_name, depende_de "
                        "FROM dbo.etl_pipeline_dependencia"):
            db.sqls.append(s)
            self._rows = sorted((d["pipeline"], d["depende_de"])
                                for d in db.dependencias)
            self.rowcount = -1
            return
        super().execute(sql, params)

    # ── implementações ─────────────────────────────────────────────────────
    def _sem_sucesso(self, s, pipeline, corte_ou_data):
        """O predicado, avaliado DE VERDADE sobre o estado do dublê.

        As cláusulas são lidas do TEXTO (a regra de honestidade do dublê da F4):
        apagar `substituida_em IS NULL` do módulo tem de MUDAR o que o dublê
        devolve, senão a Decisão 55 cai com a suíte verde."""
        db = self.db
        exige_viva = _guarda(s, "AND e.substituida_em IS NULL")
        por_data = _guarda(s, "AND e.data_referencia = ?")
        for d in db.dependencias:
            if d["pipeline"].casefold() != str(pipeline).casefold():
                continue
            tem_sucesso = False
            for e in db.execucoes:
                if e["pipeline"].casefold() != d["depende_de"].casefold():
                    continue
                if e["status"] != "SUCESSO":
                    continue
                if exige_viva and e.get("substituida_em") is not None:
                    continue
                if por_data:
                    if e["data_referencia"] != corte_ou_data:
                        continue
                else:
                    momento = e.get("fim") or e.get("inicio")
                    if momento is None or momento < corte_ou_data:
                        continue
                tem_sucesso = True
            # 082: Aguarde SEGURADO faz o dependente NÃO liberar, mesmo com o
            # predecessor concluído — e o faltante vira o texto da retenção.
            no = db.nos.get(d.get("origem_no")) if d.get("origem_no") else None
            retido = (no or {}).get("retido_em") is not None
            if retido and _guarda(s, "n2.retido_em IS NOT NULL"):
                yield d["depende_de"], d["origem_no"]
            elif not tem_sucesso:
                yield d["depende_de"], None

    def _faltantes(self, s, pipeline, corte_ou_data):
        for dep, no in self._sem_sucesso(s, pipeline, corte_ou_data):
            yield (deps_svc.MSG_AGUARDE_RETIDO.format(no)
                   if no is not None and _guarda(s, "AS aguarde_retido")
                   else dep)

    def _lote(self, s, p):
        """A forma de CONJUNTO. O degrau é lido do TEXTO, e com ele a posição
        do último parâmetro: SEQ_085 leva (…nomes…, corrida, corte), SEQ_084
        leva (…nomes…, corte) e os três degraus da data levam (…nomes…, data)."""
        if "CROSS APPLY" in s:
            nomes, corte = p[:-2], p[-1]
        else:
            nomes, corte = p[:-1], p[-1]
        tem_retencao = _guarda(s, "AS aguarde_retido")
        out = []
        for nome in nomes:
            for dep, no in self._sem_sucesso(s, nome, corte):
                out.append((nome, dep, no) if tem_retencao else (nome, dep))
        return out

    def _grafo(self, s, p):
        """O snapshot + criticidade + arestas com as DUAS pontas dentro dele.

        ⚠️ REGRA DE HONESTIDADE DO DUBLÊ: as QUATRO guardas desta consulta são
        lidas do TEXTO (`_guarda`), nunca aplicadas de graça. A primeira versão
        deste método filtrava por `malha_execucao_id` em Python — e com isso o
        recorte por CORRIDA ficava impossível de derrubar por mutação: apagá-lo
        do SQL deixava a suíte inteira verde, porque quem o aplicava era o
        dublê. É o modo de falso verde nº 1 da lista desta spec ("dublê que
        aplica guarda que mora no WHERE"), e ele estava aqui.

        As quatro, e o que cada uma vale:
          • `mm.malha_execucao_id = ?` — o recorte da CORRIDA. Sem ele o grafo
            traz o snapshot de outras corridas (e de outras malhas), e a
            travessia atravessa um membro que só existiu ONTEM para chegar a um
            pendente de hoje: o raio infla e o número que decide a escalação
            mente para cima;
          • `mm.ativo_na_abertura = 1` — Decisão 52, o snapshot é o da abertura;
          • o `EXISTS` de `d.depende_de` — a aresta só conta com as DUAS pontas
            dentro do snapshot;
          • `m2.ativo_na_abertura = 1` dentro dele — a ponta de cima também.
        """
        db = self.db
        cid = int(p[0])
        so_esta_corrida = _guarda(s, "WHERE mm.malha_execucao_id = ?")
        so_ativos = _guarda(s, "AND mm.ativo_na_abertura = 1")
        pontas_no_snapshot = _guarda(s, "AND m2.pipeline_name = d.depende_de")
        pai_ativo = _guarda(s, "AND m2.ativo_na_abertura = 1")
        membros = [m for m in db.membros_corrida
                   if (not so_esta_corrida
                       or int(m["malha_execucao_id"]) == cid)
                   and (not so_ativos or m["ativo_na_abertura"])]

        def aceitos_por(membro):
            """A ponta de CIMA que o `EXISTS` aceita para ESTE membro — ele se
            amarra em `m2.malha_execucao_id = mm.malha_execucao_id`, ou seja, na
            corrida DA LINHA, e não na da lente."""
            if not pontas_no_snapshot:
                return None                     # sem guarda: qualquer aresta
            return {m["pipeline_name"].casefold() for m in db.membros_corrida
                    if int(m["malha_execucao_id"])
                    == int(membro["malha_execucao_id"])
                    and (not pai_ativo or m["ativo_na_abertura"])}

        out = []
        for m in sorted(membros, key=lambda m: (m["pipeline_name"],
                                                m["malha_execucao_id"])):
            nome = m["pipeline_name"]
            chave = db._pipeline_key(nome)
            critic = (db.pipelines.get(chave, {}) or {}).get("criticidade")
            nomes = aceitos_por(m)
            pais = [d["depende_de"] for d in db.dependencias
                    if d["pipeline"].casefold() == nome.casefold()
                    and (nomes is None or d["depende_de"].casefold() in nomes)]
            if not pais:
                out.append((nome, critic, None))
                continue
            out.extend((nome, critic, pai) for pai in sorted(pais))
        return out


FakeDb.cursor = lambda self: _cursor(self)


def _cursor(db):
    import copy
    db._snapshot = copy.deepcopy(db._estado())
    return FakeCur(db)


@pytest.fixture(autouse=True)
def _sem_cache_de_modo():
    """O modo de liberação tem cache de 30 s DENTRO do processo da API. Sem
    limpá-lo, o primeiro teste que ligasse o modo SEQUÊNCIA contaminaria os
    seguintes — e o cenário que sobrasse seria o do cache, não o do teste."""
    deps_svc.limpar_cache_modo()
    mc.limpar_cache()
    yield
    deps_svc.limpar_cache_modo()
    mc.limpar_cache()


# ═══════════════════════════ cenários de malha ══════════════════════════════

def _malha_de_40(client, db, *, esperando: int, com_dependencia=True):
    """Malha de 40 membros com `esperando` deles em AGUARDANDO_DEPENDENCIA.

    Os demais concluem. Cada um que espera tem um predecessor PRÓPRIO que não
    concluiu (`P{i}` depende de `RAIZ`), porque é o predicado que se mede — uma
    malha sem dependência nenhuma responderia rápido por não ter o que
    perguntar."""
    membros = [f"P{i}" for i in range(40)]
    _monta_malha(client, "M1", membros)
    c = db.abrir_corrida("M1", odate=ODATE,
                         aberta_em=AGORA_BANCO - timedelta(hours=1),
                         membros=membros)
    for i, nome in enumerate(membros):
        if i < esperando:
            if com_dependencia:
                db.depende(nome, "CARGA_A")
            db.execucao(nome, "AGUARDANDO_DEPENDENCIA",
                        criado_em=AGORA_BANCO - timedelta(minutes=30),
                        corrida=c["id"])
        else:
            db.execucao(nome, "SUCESSO",
                        inicio=AGORA_BANCO - timedelta(minutes=50),
                        fim=AGORA_BANCO - timedelta(minutes=40),
                        corrida=c["id"])
    return c


# ══════════ o aceite: UMA consulta de conjunto, nunca 24 round-trips ════════

def test_painel_de_40_membros_com_12_esperando_faz_uma_consulta_de_conjunto(
        client, auth):
    """O aceite da §10/F10, literal: 40 membros, 12 esperando, **uma** consulta
    de conjunto para os pendentes — nunca 24 round-trips."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        c = _malha_de_40(client, db, esperando=12)
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
    lote = db.statements(PREFIXO_LOTE)
    assert len(lote) == 1, f"{len(lote)} consultas de conjunto: {lote}"
    assert db.statements(PREFIXO_UMA_LINHA) == [], \
        "o predicado por membro voltou ao caminho corrente do painel"
    # E o resultado continua completo: uma consulta que responde menos não é
    # otimização, é omissão.
    esperando = [e for e in painel["execucoes"]
                 if e["status"] == "AGUARDANDO_DEPENDENCIA"]
    assert len(esperando) == 12
    assert all(e["faltantes"] == ["CARGA_A"] for e in esperando)


def test_o_custo_nao_cresce_com_o_numero_de_quem_espera(client, auth):
    """A prova de que é CONJUNTO e não N+1 com sorte: 2 esperando e 12
    esperando gastam o MESMO número de statements no painel inteiro.

    Contar só o cenário de 12 passaria verde num N+1 com cache; a diferença
    entre os dois cenários é o que não pode existir."""
    gastos = []
    for quantos in (2, 12):
        db = FakeDb(pipelines=_pipes())
        with _patch(db), _patch_agora():
            c = _malha_de_40(client, db, esperando=quantos)
            db.sqls.clear()             # só o GET conta, não a montagem
            # O modo de liberação tem cache de 30 s DENTRO do processo: sem
            # zerá-lo, a segunda medição herdaria o cache da primeira e sairia
            # uma consulta mais barata por um motivo que não é o desta fase.
            deps_svc.limpar_cache_modo()
            client.get(f"/malhas/M1/execucao?corrida={c['id']}")
        gastos.append(len(db.sqls))
    assert gastos[0] == gastos[1], (
        f"o painel gastou {gastos[0]} statements com 2 esperando e {gastos[1]} "
        "com 12 — o custo ainda cresce com quem espera")


def test_modo_sequencia_nao_le_o_relogio_uma_vez_por_membro(client, auth):
    """No modo SEQUÊNCIA cada `faltantes()` gastava também um `SELECT GETDATE()`
    e a leitura da janela — 3 idas por membro esperando. O corte é do LOTE, e é
    lido uma vez."""
    db = FakeDb(pipelines=_pipes())
    db.config["dependencia_modo_sequencia"] = "1"
    with _patch(db), _patch_agora():
        c = _malha_de_40(client, db, esperando=12)
        db.sqls.clear()
        client.get(f"/malhas/M1/execucao?corrida={c['id']}")
    assert len(db.statements(PREFIXO_LOTE)) == 1
    assert len([s for s in db.sqls if s.startswith("SELECT GETDATE()")]) <= 1


# ══════════════════ paridade: o lote é o MESMO predicado ════════════════════

def test_o_lote_responde_igual_ao_predicado_de_uma_linha(client, auth):
    """Paridade SEMÂNTICA. O cenário cobre a matriz que importa: predecessor em
    SUCESSO (libera), em FALHA (não), ausente (não) e SUCESSO APOSENTADO por um
    rerun (não — Decisão 55/078)."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A", "B", "C"])
        db.depende("A", "OK1")
        db.depende("B", "FALHOU")
        db.depende("C", "OK2")
        db.depende("C", "P_NAO_PARTIU")
        db.execucao("OK1", "SUCESSO", inicio=AGORA_BANCO, fim=AGORA_BANCO)
        db.execucao("FALHOU", "FALHA", inicio=AGORA_BANCO, fim=AGORA_BANCO)
        db.execucao("OK2", "SUCESSO", inicio=AGORA_BANCO, fim=AGORA_BANCO,
                    substituida=AGORA_BANCO)
        cur = db.cursor()
        uma = {nome: deps_svc.liberado(cur, nome, ODATE)[1]
               for nome in ("A", "B", "C")}
        lote = deps_svc.faltantes_em_lote(cur, ["A", "B", "C"], ODATE)
    assert lote == uma
    assert uma == {"A": [], "B": ["FALHOU"], "C": ["OK2", "P_NAO_PARTIU"]}


def test_o_lote_e_montado_dos_mesmos_fragmentos_do_predicado():
    """Paridade ESTRUTURAL — a que impede a divergência FUTURA.

    O texto do lote tem de conter, literalmente, os mesmos fragmentos de
    `NOT EXISTS` do predicado de uma linha. Uma segunda redação passaria na
    paridade semântica de hoje e divergiria no dia em que alguém mudasse um dos
    dois — que é exatamente o modo de falha que a paridade D29 existe para
    impedir."""
    pares = ((deps_svc.SQL_LOTE_SEQ_085, deps_svc._ONDE_SEM_SUCESSO_SEQ_085),
             (deps_svc.SQL_LOTE_SEQ_084, deps_svc._ONDE_SEM_SUCESSO_SEQ_084),
             (deps_svc.SQL_LOTE_082, deps_svc._ONDE_SEM_SUCESSO_078),
             (deps_svc.SQL_LOTE_078, deps_svc._ONDE_SEM_SUCESSO_078),
             (deps_svc.SQL_LOTE_LEGADO, deps_svc._ONDE_SEM_SUCESSO_LEGADO))
    for sql, fragmento in pares:
        assert fragmento[4:] in sql, sql
    # E o corte em três degraus da F6 é o MESMO objeto, não uma cópia.
    assert deps_svc._CORTE_SEQ_085 in deps_svc.SQL_LOTE_SEQ_085
    # O `IN (…)` é a ÚNICA diferença de recorte: nenhum degrau pode ter voltado
    # ao `= ?` de uma linha só (seria N+1 disfarçado de lote).
    for nome in ("SQL_LOTE_SEQ_085", "SQL_LOTE_SEQ_084", "SQL_LOTE_082",
                 "SQL_LOTE_078", "SQL_LOTE_LEGADO"):
        sql = getattr(deps_svc, nome)
        assert "pipeline_name IN ({m})" in sql, nome
        assert "pipeline_name = ?" not in sql, nome


def test_o_lote_desce_a_MESMA_cascata_do_deploy_parcial():
    """Sem a 085 o lote cai no degrau SEQ_084 (o corte vira a janela), e não na
    data — a mesma degradação que `liberado()` faz. Uma cascata que divergisse
    poria painel e motor em desacordo no deploy parcial."""
    chamadas: list = []

    class Cur:
        """Só o predicado é recordado — a leitura do modo e a do relógio são
        config de REQUEST, não de membro, e contá-las aqui embaralharia a prova
        da cascata com a do custo (que tem teste próprio)."""

        def execute(self, sql, params=()):
            s = " ".join(str(sql).split())
            if not s.startswith(PREFIXO_LOTE):
                return
            chamadas.append((s, tuple(params)))
            if len(chamadas) == 1:
                raise RuntimeError(
                    "[42S02] Invalid object name 'dbo.etl_malha_execucao'. (208)")

        def fetchall(self):
            return []

        def fetchone(self):
            return ("1",)               # modo SEQUENCIA ligado

    cur = Cur()
    deps_svc.limpar_cache_modo()
    with patch.object(deps_svc, "inicio_do_ciclo_corrente",
                      return_value=AGORA_BANCO):
        deps_svc.faltantes_em_lote(cur, ["A", "B"], ODATE, corrida=7)
    deps_svc.limpar_cache_modo()
    assert len(chamadas) == 2, chamadas
    assert "CROSS APPLY" in chamadas[0][0]
    assert chamadas[0][1] == ("A", "B", 7, AGORA_BANCO)
    assert "data_referencia" not in chamadas[1][0], "caiu na data, não no 084"
    assert chamadas[1][1] == ("A", "B", AGORA_BANCO)


def test_erro_na_consulta_em_lote_nunca_vira_liberado():
    """D21 — erro NUNCA vira "pode disparar", nem no painel, nem em lote. Todo
    nome do lote volta com o sentinel, e nenhum volta com lista vazia (que a
    tela leria como "não falta ninguém")."""
    class Cur:
        def execute(self, sql, params=()):
            raise RuntimeError("banco fora do ar")

        def fetchall(self):
            return []

        def fetchone(self):
            return None

    out = deps_svc.faltantes_em_lote(Cur(), ["A", "B"], ODATE)
    assert set(out) == {"A", "B"}
    assert all(v and v[0].startswith(deps_svc.ERRO_CONSULTA)
               for v in out.values())


def test_nome_pedido_sem_faltante_volta_como_lista_vazia():
    """`[]` é "perguntei e não falta ninguém"; chave ausente seria o chamador
    tendo de adivinhar qual dos dois aconteceu."""
    class Cur:
        def execute(self, sql, params=()):
            pass

        def fetchall(self):
            return []

        def fetchone(self):
            return None

    assert deps_svc.faltantes_em_lote(Cur(), ["A", "B"], ODATE) == {"A": [],
                                                                    "B": []}


def test_retencao_chega_pelo_lote_com_o_MESMO_texto(client, auth):
    """082 — o Aguarde SEGURADO é um faltante com dono e com texto próprio
    (`eh_retencao`). Perdê-lo no lote faria a tela chamar de "esperando outro
    pipeline" o que o motor sabe que é um nó travado pelo operador."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A"])
        db.nos[9] = {"id": 9, "malha": "M1", "tipo": "aguarde",
                     "retido_em": AGORA_BANCO, "retido_por": "C123456"}
        db.depende("A", "OK1", origem_no=9)
        db.execucao("OK1", "SUCESSO", inicio=AGORA_BANCO, fim=AGORA_BANCO)
        cur = db.cursor()
        lote = deps_svc.faltantes_em_lote(cur, ["A"], ODATE)
    assert lote["A"] == [deps_svc.MSG_AGUARDE_RETIDO.format(9)]
    assert deps_svc.eh_retencao(lote["A"][0])


# ═══════════ o FALTANTE do pendente: no painel sim, no card não ═════════════

def test_o_pendente_do_painel_ganha_o_faltante_e_o_card_nao(client, auth):
    """A F4 deixou `faltante` reservado com `None`. Ele nasce aqui — e nasce só
    no PAINEL: o card serve 40 malhas com orçamento de duas consultas, e ali
    `null` continua querendo dizer "não perguntei"."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A", "B"])
        c = db.abrir_corrida("M1", odate=ODATE,
                             aberta_em=AGORA_BANCO - timedelta(hours=1),
                             membros=["A", "B"])
        db.depende("A", "CARGA_A")
        db.execucao("A", "NAO_LIBEROU",
                    criado_em=AGORA_BANCO - timedelta(minutes=20),
                    corrida=c["id"])
        db.execucao("B", "SUCESSO", inicio=AGORA_BANCO, fim=AGORA_BANCO,
                    corrida=c["id"])
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
        card = next(m for m in client.get("/malhas").json()["malhas"]
                    if m["malha_name"] == "M1")
    pendente = painel["corrida"]["pendentes"][0]
    assert pendente["classe"] == "nao_liberou"
    assert pendente["faltante"] == "CARGA_A"
    assert pendente["faltantes"] == ["CARGA_A"]
    assert card["corrida"]["pendentes"][0]["faltante"] is None
    assert card["corrida"]["pendentes"][0]["faltantes"] is None


def test_grafia_divergente_entre_o_snapshot_e_o_cadastro_nao_perde_o_faltante(
        client, auth):
    """⚠️ O GOTCHA que já quebrou pipeline em produção, agora do lado da
    leitura: `execucoes[]` traz a grafia OFICIAL de `etl_pipeline` e
    `pendentes[]` traz a do SNAPSHOT (a do dia da abertura). O SQL Server compara
    sem distinguir caixa; o `dict` do Python distingue.

    Sem a ponte de `casefold`, o mesmo pipeline entraria DUAS vezes no `IN` e o
    faltante seria procurado numa chave inexistente — a aba `Travando` calando
    sobre quem está esperando, em silêncio."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A"])
        c = db.abrir_corrida("M1", odate=ODATE,
                             aberta_em=AGORA_BANCO - timedelta(hours=1),
                             membros=["a"])          # snapshot em minúscula
        db.depende("A", "CARGA_A")
        db.execucao("A", "NAO_LIBEROU",
                    criado_em=AGORA_BANCO - timedelta(minutes=20),
                    corrida=c["id"])
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
    lote = db.statements(PREFIXO_LOTE)
    assert len(lote) == 1 and lote[0].count("?") == 2, \
        "o mesmo pipeline entrou duas vezes no IN por causa da caixa"
    assert painel["execucoes"][0]["faltantes"] == ["CARGA_A"]
    assert _pendentes(painel)["a"]["faltante"] == "CARGA_A"
    assert _pendentes(painel)["a"]["alcance"] == 0


def test_falhou_nao_gasta_nome_no_lote(client, auth):
    """`falhou`/`orfa` são veredito sobre o PRÓPRIO pipeline: ele rodou, logo
    os predecessores dele concluíram. Perguntar de quem ele espera devolveria
    lista vazia e gastaria nome no `IN`."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A", "B"])
        c = db.abrir_corrida("M1", odate=ODATE,
                             aberta_em=AGORA_BANCO - timedelta(hours=1),
                             membros=["A", "B"])
        db.depende("A", "CARGA_A")
        db.execucao("A", "FALHA", inicio=AGORA_BANCO - timedelta(minutes=30),
                    fim=AGORA_BANCO - timedelta(minutes=29), corrida=c["id"])
        db.execucao("B", "SUCESSO", inicio=AGORA_BANCO, fim=AGORA_BANCO,
                    corrida=c["id"])
        client.get(f"/malhas/M1/execucao?corrida={c['id']}")
    # Nenhum esperando em `execucoes[]` e nenhum pendente que espere: o lote
    # não chega a ser emitido.
    assert db.statements(PREFIXO_LOTE) == []


# ═══════════════ o RAIO DE ALCANCE por travado (Decisão 63) ════════════════

def _corrida_em_cadeia(client, db, *, criticidades=None):
    """`A → B → C → D` (A falhou; B, C e D parados atrás) e `Z`, solto e OK."""
    membros = ["A", "B", "C", "OK1", "OK2"]
    _monta_malha(client, "M1", membros)
    for nome, critic in (criticidades or {}).items():
        db.pipelines[db._pipeline_key(nome)]["criticidade"] = critic
    c = db.abrir_corrida("M1", odate=ODATE,
                         aberta_em=AGORA_BANCO - timedelta(hours=1),
                         membros=membros)
    db.depende("B", "A")
    db.depende("C", "B")
    db.depende("OK1", "A")
    db.execucao("A", "FALHA", inicio=AGORA_BANCO - timedelta(minutes=30),
                fim=AGORA_BANCO - timedelta(minutes=29), corrida=c["id"])
    db.execucao("B", "NAO_LIBEROU",
                criado_em=AGORA_BANCO - timedelta(minutes=20), corrida=c["id"])
    # `C` não tem linha nenhuma: `nao_partiu`, e ele conta como parado atrás.
    # `OK1` depende de `A` e mesmo assim CONCLUIU (rerun anterior): NÃO está
    # parado, e contá-lo inflaria o número que decide a escalação.
    db.execucao("OK1", "SUCESSO", inicio=AGORA_BANCO - timedelta(minutes=55),
                fim=AGORA_BANCO - timedelta(minutes=50), corrida=c["id"])
    db.execucao("OK2", "SUCESSO", inicio=AGORA_BANCO - timedelta(minutes=55),
                fim=AGORA_BANCO - timedelta(minutes=50), corrida=c["id"])
    return c


def _pendentes(painel):
    return {p["pipeline"]: p for p in painel["corrida"]["pendentes"]}


def test_o_raio_conta_os_membros_PARADOS_atras_e_nao_a_malha_inteira(client, auth):
    """"4 pipelines parados atrás" — a palavra é *parados*. Quem já concluiu
    não está parado, e contá-lo transformaria o número que decide a escalação
    num número que só cresce com o tamanho da malha."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        c = _corrida_em_cadeia(client, db)
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
    pend = _pendentes(painel)
    assert pend["A"]["classe"] == "falhou"
    assert pend["A"]["alcance"] == 2, "B e C — nunca OK1, que concluiu"
    assert pend["B"]["alcance"] == 1                        # só C
    assert pend["C"]["alcance"] == 0                        # fim da cadeia
    # O raio sai de UMA consulta, e ela não se repete por pendente.
    assert len(db.statements(
        "SELECT mm.pipeline_name, p.criticidade, d.depende_de")) == 1


def test_o_raio_diz_quantos_dos_parados_sao_ALTA(client, auth):
    """O segundo número da Decisão 63: 18 parados atrás sem nenhum crítico
    espera o horário comercial; 2 com um `ALTA` no meio, não."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        c = _corrida_em_cadeia(client, db,
                               criticidades={"A": "Alta", "C": "Alta"})
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
    pend = _pendentes(painel)
    assert pend["A"]["criticidade"] == "Alta"
    assert pend["A"]["alcance_alta"] == 1, "só C entre os dois parados atrás"
    assert pend["B"]["criticidade"] == "Media"
    assert pend["B"]["alcance_alta"] == 1


def test_dependencia_circular_no_cadastro_nao_trava_a_leitura(client, auth):
    """Ciclo no cadastro é dado do usuário, não impossibilidade — e um passeio
    ingênuo giraria para sempre com o operador olhando um spinner às 3h. (O CTE
    recursivo em T-SQL teria estourado o `MAXRECURSION` e derrubado a leitura
    inteira; é por isto que o fecho é feito com conjunto de visitados.)"""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        membros = ["A", "B", "C"]
        _monta_malha(client, "M1", membros)
        c = db.abrir_corrida("M1", odate=ODATE,
                             aberta_em=AGORA_BANCO - timedelta(hours=1),
                             membros=membros)
        db.depende("B", "A")
        db.depende("C", "B")
        db.depende("A", "C")            # o ciclo
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
    pend = _pendentes(painel)
    # Todos `nao_partiu`; cada um alcança os outros DOIS, e nunca a si mesmo.
    assert {n: p["alcance"] for n, p in pend.items()} == {"A": 2, "B": 2, "C": 2}


def test_o_raio_nao_atravessa_a_fronteira_da_corrida(client, auth):
    """Dependente de FORA do snapshot não está parado por ESTA corrida, e
    contá-lo inflaria o número que decide acordar alguém."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A"])
        c = db.abrir_corrida("M1", odate=ODATE,
                             aberta_em=AGORA_BANCO - timedelta(hours=1),
                             membros=["A"])
        db.depende("CARGA_B", "A")      # CARGA_B não é membro desta corrida
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
    assert _pendentes(painel)["A"]["alcance"] == 0


def test_grafo_indisponivel_deixa_o_raio_nulo_e_o_resto_de_pe(client, auth):
    """"Não consegui apurar" é `null`, e é DIFERENTE de `0`. Publicar zero como
    se fosse medida é a mesma família de mentira que esta spec inteira ataca —
    e a faixa, os contadores e os faltantes continuam na tela."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        c = _corrida_em_cadeia(client, db)
        db.falhar_grafo = True
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
    pend = _pendentes(painel)
    assert pend["A"]["alcance"] is None and pend["A"]["alcance_alta"] is None
    assert pend["A"]["criticidade"] is None
    assert painel["corrida"]["membros_total"] == 5      # o resto continua
    assert pend["B"]["faltante"] == "A"                 # o lote também


# ═════════════════ o ORDENAMENTO que é aceite (Decisão 73) ══════════════════

def test_o_refetch_do_painel_so_encurta_depois_que_o_N_MAIS_1_sai():
    """⚠️ ORDENAMENTO, não preferência.

    Dobrar a frequência de um endpoint que ainda pergunta o predicado POR
    MEMBRO é o pior ordenamento possível: numa malha de 40 membros, durante um
    incidente, encurtar o intervalo multiplica o estrago. O teste proíbe a
    ordem errada e permite as duas ordens certas — 30 s com ou sem o agregado,
    e 15 s só com ele.

    A leitura é de FONTE de propósito: o que se prova é uma relação entre duas
    árvores de deploy (`api/` e o `dist/` do front), e ela não existe em
    nenhum runtime — o `dist/` sobe na etapa 3 e a `api/` na 7.

    ⚠️ A régua mede o MENOR intervalo que a fonte autoriza, e não "o número
    depois dos dois pontos": desde a F10 o `refetchInterval` é CONDICIONAL
    (15 s com corrida ABERTA, 60 s com ela fechada, 30 s sem ciclo — Decisão
    73), e uma regex que casasse só o primeiro literal deixaria passar um
    `5_000` escondido no segundo ramo."""
    router = (RAIZ / "api" / "routers" / "malhas.py").read_text(encoding="utf-8")
    corpo = router.split("def get_malha_execucao(", 1)[1]
    corpo = corpo.split("\n@router.", 1)[0]
    n_mais_1 = "deps_svc.liberado(" in corpo

    editor = (RAIZ / "ui-react" / "src" / "components" / "malhas"
              / "MalhaEditor.tsx").read_text(encoding="utf-8")
    trecho = editor.split("'malha-execucao'", 1)[1].split("\n  })", 1)[0]
    assert "refetchInterval:" in trecho, (
        "o painel perdeu o refetchInterval — a régua deste teste sumiu")
    bloco = trecho.split("refetchInterval:", 1)[1]
    # Só literais de milissegundos (`15_000`, `30000`): "15 s" no comentário ao
    # lado não é intervalo, e casá-lo faria o teste reprovar a própria prosa.
    numeros = [int(n.replace("_", ""))
               for n in re.findall(r"\b(\d{1,3}_\d{3}|\d{4,})\b", bloco)]
    assert numeros, "o refetchInterval do painel não tem intervalo nenhum"
    intervalo = min(numeros)

    if n_mais_1:
        assert intervalo >= 30_000, (
            "o painel encurtou o refetch para %d ms com o predicado ainda "
            "sendo perguntado POR MEMBRO — a Decisão 73 é ordenamento, não "
            "preferência" % intervalo)
    else:
        assert intervalo >= 15_000, (
            "refetch de %d ms é mais agressivo do que a Decisão 73 autoriza"
            % intervalo)
        # O outro lado: com o agregado no caminho, o painel TEM de aproveitar
        # — deixar os 30 s de sempre seria pagar o custo da fase e não colher
        # nada dela.
        assert intervalo <= 15_000, (
            "o agregado entrou e o painel continuou em %d ms: a Decisão 73 "
            "manda 15 s com corrida ABERTA depois que o N+1 sai" % intervalo)


def test_o_agregado_esta_no_caminho_corrente_do_painel():
    """O outro lado da mesma régua: o teste acima ficaria verde para sempre se
    alguém desistisse do agregado e deixasse os 30 s. Este exige o agregado."""
    fonte = (RAIZ / "api" / "routers" / "malhas.py").read_text(encoding="utf-8")
    corpo = fonte.split("def get_malha_execucao(", 1)[1].split("\n@router.", 1)[0]
    assert "faltantes_em_lote(" in corpo
    assert "deps_svc.liberado(" not in corpo


def test_a_api_declara_o_contrato_novo_dos_pendentes(client, auth):
    """Contrato congelado (o molde de `test_contrato_do_bloco_corrida`):
    acrescentar campo é barato, REMOVER é caro — o consumidor é outra árvore de
    deploy, e um campo que some vira tela em branco na janela entre as duas."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        c = _corrida_em_cadeia(client, db)
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
    assert set(painel["corrida"]["pendentes"][0]) == {
        "pipeline", "classe", "desde", "faltante", "faltantes",
        "alcance", "alcance_alta", "criticidade"}


# ═══ §18/12b — o dia com VÁRIAS corridas não pode ficar mudo, nem no PASSADO ═

def test_dia_ANTERIOR_com_duas_corridas_diz_quantas_foram(client, auth):
    """A pendência 12b, no caso que ela de fato descreve.

    O gesto de plantão é abrir a malha de manhã e navegar para **ONTEM** — o
    dia do incidente, e justamente o que tem duas corridas (a madrugada + o
    redisparo das 5h). Sem lente, `execucoes[]` traz o dia INTEIRO, então o
    canvas empilha os dois ciclos no mesmo desenho.

    A contagem era feita só quando o dia exibido era o da corrida CORRENTE:
    para qualquer dia anterior o bloco `corrida` já tinha saído pelo ramo do
    `data_referencia` divergente, a contagem nem chegava a rodar e
    `corridas_no_dia` ficava ausente. Resultado: a tela ficava MUDA sobre as
    duas madrugadas que ela estava misturando — exatamente o estado que a 12b
    existe para consertar, no dia em que ele mais dói."""
    db = FakeDb(pipelines=_pipes(),
                config={"dependencia_hora_virada": "00:00"})
    db.config[mc.CHAVE_ATIVA] = "0"
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A", "B"])
        db.abrir_corrida("M1", odate=ODATE_ONTEM, status="CONCLUIDA",
                         aberta_em=AGORA_BANCO - timedelta(hours=30),
                         membros=["A", "B"])
        db.abrir_corrida("M1", odate=ODATE_ONTEM, status="FALHA",
                         aberta_em=AGORA_BANCO - timedelta(hours=26),
                         membros=["A", "B"])
        # E HOJE abriu a de sempre: é ela a CORRENTE, e é o que fazia a
        # contagem de ontem nunca acontecer.
        db.abrir_corrida("M1", odate=ODATE, aberta_em=AGORA_BANCO,
                         membros=["A", "B"])
        painel = client.get(
            "/malhas/M1/execucao?data_referencia=2026-08-04").json()
    assert "corrida" not in painel, (
        "descrever UMA corrida sobre a lista das DUAS é a mentira que a fase "
        "mata — o bloco tem de sair")
    assert painel["corridas_no_dia"] == 2, (
        "o dia anterior com duas corridas ficou mudo: o canvas mistura os dois "
        "ciclos e a tela não tem como oferecer a escolha")


def test_dia_ANTERIOR_com_UMA_corrida_nao_inventa_escolha(client, auth):
    """O contraponto — sem ele o conserto acima poderia acender a frase de
    "escolha uma" em toda navegação por data, que é o caso comum."""
    db = FakeDb(pipelines=_pipes(),
                config={"dependencia_hora_virada": "00:00"})
    db.config[mc.CHAVE_ATIVA] = "0"
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A"])
        db.abrir_corrida("M1", odate=ODATE_ONTEM, status="CONCLUIDA",
                         aberta_em=AGORA_BANCO - timedelta(hours=30),
                         membros=["A"])
        db.abrir_corrida("M1", odate=ODATE, aberta_em=AGORA_BANCO,
                         membros=["A"])
        painel = client.get(
            "/malhas/M1/execucao?data_referencia=2026-08-04").json()
    assert "corridas_no_dia" not in painel


def test_malha_SEM_corrida_nenhuma_nao_gasta_a_consulta_da_contagem(client, auth):
    """O custo do conserto, com o interruptor `malha_corrida_ativa` em `0` — o
    estado do dev e o do dia do deploy.

    Sem corrida nenhuma no banco a contagem seria zero em TODO refetch de TODO
    painel aberto: custo puro, de 15 em 15 segundos, para uma resposta que já
    se sabe. O gatilho é a malha ter ao menos uma corrida registrada."""
    db = FakeDb(pipelines=_pipes(),
                config={"dependencia_hora_virada": "00:00"})
    db.config[mc.CHAVE_ATIVA] = "0"
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A"])
        db.sqls.clear()
        client.get("/malhas/M1/execucao?data_referencia=2026-08-04")
    assert db.statements("SELECT COUNT(*) FROM dbo.etl_malha_execucao") == []


# ═════ Decisão 66/3 — a FILA DE AVISO chega ao painel (`notificado_em`) ══════

def _com_evento_do_ciclo(client, db, *, notificado_em):
    """Corrida com um `MALHA_FALHOU` gravado no marcador do ciclo."""
    c = _corrida_em_cadeia(client, db)
    db.eventos.append({
        "pipeline_name": malhas_router.MARCADOR_CORRIDA.format(c["id"]),
        "data_referencia": ODATE, "tipo": "MALHA_FALHOU",
        "detectado_em": AGORA_BANCO - timedelta(minutes=52),
        "detalhe": "malha M1 falhou", "notificado_em": notificado_em})
    return c


def test_o_evento_do_ciclo_diz_se_o_aviso_saiu(client, auth):
    """`notificado_em` existe na 067 desde sempre e NUNCA foi lido pela tela.

    Ele é o único jeito de responder a pior pergunta do plantão — *o aviso
    saiu?*: webhook com 401 por URL rotacionada faz a guardiã logar e seguir, e
    a malha falha em silêncio para todo mundo menos para quem já está com esta
    tela aberta."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        c = _com_evento_do_ciclo(client, db, notificado_em=None)
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
    ev = painel["eventos_corrida"][0]
    assert ev["tipo"] == "MALHA_FALHOU"
    # Chave PRESENTE com `null` = está na fila. É o que acende o banner.
    assert "notificado_em" in ev and ev["notificado_em"] is None


def test_aviso_ja_enviado_chega_com_o_instante(client, auth):
    db = FakeDb(pipelines=_pipes())
    quando = AGORA_BANCO - timedelta(minutes=50)
    with _patch(db), _patch_agora():
        c = _com_evento_do_ciclo(client, db, notificado_em=quando)
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
    assert painel["eventos_corrida"][0]["notificado_em"] == \
        quando.strftime("%Y-%m-%d %H:%M:%S")


def test_banco_sem_a_coluna_OMITE_a_chave_em_vez_de_mandar_null(client, auth):
    """Deploy parcial (§11.1). As duas leituras são OPOSTAS e a tela precisa
    distingui-las: `null` é "está na fila e ninguém foi avisado" — banner
    vermelho —, e a AUSÊNCIA é "não perguntei". Mandar `null` num banco sem a
    coluna acenderia o banner em toda malha, que é o alarme falso da Decisão 26
    com roupa nova.

    E o painel continua inteiro: a degradação é da coluna, não da tela."""
    db = FakeDb(pipelines=_pipes())
    db.sem_notificado_em = True
    with _patch(db), _patch_agora():
        c = _com_evento_do_ciclo(client, db, notificado_em=None)
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
    ev = painel["eventos_corrida"][0]
    assert "notificado_em" not in ev
    assert ev["tipo"] == "MALHA_FALHOU"
    # O resto da leitura não sofre — inclusive o agregado desta fase.
    assert painel["corrida"]["membros_total"] == 5
    assert _pendentes(painel)["B"]["faltante"] == "A"


def test_sem_canal_do_Teams_o_painel_diz_que_NAO_HA_DESTINO(client, auth):
    """A terceira leitura de `notificado_em` nulo, que faltava.

    Sem canal configurado a guardiã sai cedo e **nada** é carimbado: todo
    evento fica `notificado_em NULL` para sempre. Lido como "está na fila", isso
    acende o banner vermelho *"N avisos ao Teams na fila — ninguém foi avisado
    ainda"* permanentemente, em QUALQUER instalação sem webhook — o dev
    inclusive. É o alarme falso crônico que a Decisão 26 proíbe: na primeira
    semana o operador aprende a ignorar o banner, e aí ele deixa de servir para
    o webhook que quebrou de verdade.

    O evento continua chegando com `notificado_em: null` (é o fato); o que a
    resposta acrescenta é o CONTEXTO que o transforma em "não há destino"."""
    db = FakeDb(pipelines=_pipes())
    db.canal_teams = False
    with _patch(db), _patch_agora():
        c = _com_evento_do_ciclo(client, db, notificado_em=None)
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
    assert painel["teams_configurado"] is False
    assert painel["eventos_corrida"][0]["notificado_em"] is None


def test_com_canal_configurado_o_aviso_sem_carimbo_E_fila_presa(client, auth):
    """O contraponto — sem ele, a correção poderia ter simplesmente apagado o
    banner para todo mundo, e o webhook com 401 voltaria a falhar em silêncio,
    que é exatamente o que a Decisão 66 existe para acabar."""
    db = FakeDb(pipelines=_pipes())
    db.canal_teams = True
    with _patch(db), _patch_agora():
        c = _com_evento_do_ciclo(client, db, notificado_em=None)
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
    assert painel["teams_configurado"] is True
    assert painel["eventos_corrida"][0]["notificado_em"] is None


def test_banco_sem_a_coluna_nao_gasta_consulta_perguntando_pelo_canal(
        client, auth):
    """Sem `notificado_em` não há banner a decidir — perguntar pelo canal seria
    ida ao banco por nada, a cada refetch de 15s de cada painel aberto.

    O dublê estoura se a sonda for chamada com o cenário que não a espera, então
    este teste falha se alguém tirar a guarda."""
    db = FakeDb(pipelines=_pipes())
    db.sem_notificado_em = True
    db.canal_teams = None          # perguntar aqui = RuntimeError no dublê
    with _patch(db), _patch_agora():
        c = _com_evento_do_ciclo(client, db, notificado_em=None)
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
    assert "teams_configurado" not in painel
    assert not [q for q in db.sqls if "etl_msg_grupo" in q]


def test_sonda_do_canal_indisponivel_OMITE_a_chave(client, auth):
    """Não perguntei ⇒ não afirmo. `False` diria "não há canal" e apagaria um
    banner legítimo; a ausência mantém o comportamento anterior."""
    db = FakeDb(pipelines=_pipes())
    db.canal_teams = None          # a sonda estoura
    with _patch(db), _patch_agora():
        c = _com_evento_do_ciclo(client, db, notificado_em=None)
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
    assert "teams_configurado" not in painel
    assert painel["eventos_corrida"][0]["notificado_em"] is None


def test_a_marca_da_coluna_e_o_que_autoriza_o_fallback():
    """A cascata reage à MARCA, e não a um `except` cego: um timeout de lock
    não pode virar "banco sem a coluna" — a segunda consulta pagaria o mesmo
    timeout e a tela perderia o banner por um motivo que não é o dela."""
    fonte = (RAIZ / "api" / "routers" / "malhas.py").read_text(encoding="utf-8")
    corpo = fonte.split("def _eventos_da_data(", 1)[1].split("\ndef ", 1)[0]
    assert 'if "notificado_em" not in str(e):' in corpo
    assert "raise" in corpo
