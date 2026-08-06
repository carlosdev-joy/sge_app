"""
F4 + F4+ da spec docs/spec-malha-execucao.md — o card e o painel deixam de
mentir.

O DEFEITO que esta suíte existe para travar (o primeiro teste é ele, literal):
`CARGA_A` falha às 03:00, `CARGA_B` conclui às 03:40, e o card diz **sucesso ·
CARGA_B** porque a chave de comparação é "a execução mais recente entre os
membros". Depois da F4 o status é o da CORRIDA, e ele diz *falhou* NOMEANDO
`CARGA_A`.

O que mais se prova aqui, e por que cada prova existe:

  • **duas consultas para a lista inteira** — 4 malhas e 40 malhas gastam o
    MESMO número de statements no bloco da corrida. Um N+1 aqui multiplicaria
    por 40 o custo de cada refetch da tela de acompanhamento;
  • **`substituida_em IS NULL` no numerador E no painel** (Decisão 55, F4+/1):
    depois de um rerun, a faixa e o canvas contam a MESMA linha. O teste
    compara os dois na mesma resposta — que é o único jeito de pegar "corrigi
    a barra e esqueci o nó";
  • **o denominador NÃO ENCOLHE** (Decisão 52, F4+/2): a guardiã marcando 3
    membros como `PULADO` no ciclo seguinte não pode transformar `2 de 7` em
    `2 de 4`. O progresso andando para a frente enquanto a situação piora é o
    card mentindo com matemática nova;
  • **`membros_travados` fica FORA do que a barra preenche** (Decisão 54,
    F4+/3): vale `total = ok + vivos + dispensados + travados`, e é essa
    identidade que impede a barra de pintar 5/6 e ser lida como "quase pronto";
  • **degradação por AUSÊNCIA DE CAMPO** (Decisão 41): sem a 085 o payload sai
    SEM a chave `corrida` — nunca com `corrida: null`, nunca com uma flag que o
    front tenha de interpretar — e `ultima_execucao` continua lá, que é o
    fallback "(membro mais recente)";
  • **nenhuma conta de tempo em Python** (Decisão 10): o dublê põe o banco 3h à
    frente do processo, como no dev. Saúde `ATRASADA`, `SEM_PROGRESSO` e
    `apurado_em` saem todos do relógio do BANCO — qualquer `datetime.now()` no
    servidor vira teste vermelho, não teste verde por sorte.

O dublê é o da F3 (`test_malha_corrida_porta`), que já modela a 085 inteira,
estendido com as DUAS consultas novas e com o `SELECT` do painel. A **regra de
honestidade** vale igual: cláusula que mora no `WHERE` só é aplicada pelo dublê
se o SQL emitido a contiver (`_guarda`), senão apagar `substituida_em IS NULL`
do módulo deixaria a suíte verde.

⚠️ O interruptor `malha_corrida_ativa` fica **DESLIGADO** em quase toda esta
suíte, de propósito: é o estado do dia do deploy (§11.2, ele só vai a `1`
depois da F7), e a LEITURA da corrida não pode depender dele. Quem governa o
interruptor é quem ABRE e quem FECHA.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from deps import PERM_EDITAR, PERM_EXECUTAR, get_current_user
from services import malha_corrida as mc
from tests.test_malha_corrida_porta import (AGORA_API, AGORA_BANCO, FakeCur as
                                            FakeCurF3, FakeDb as FakeDbF3,
                                            _guarda, _proj)
from tests.test_malhas_f10 import _cria_no, _monta_malha

ODATE = date(2026, 8, 5)
ODATE_ONTEM = date(2026, 8, 4)

# Os nomes de todos os cenários numa lista só: o cadastro de pipelines é
# preparação, não o que se prova, e um `_pipes` por teste só criaria ruído.
_NOMES = (["CARGA_A", "CARGA_B", "A", "B", "C", "OK1", "OK2", "OK3", "VIVO",
           "PULA", "FALHOU", "P_FALHOU", "P_NAO_LIBEROU", "P_NAO_PARTIU",
           "P_ORFA"] + [f"P{i}" for i in range(40)])


def _pipes():
    base = {"active": 1, "criticidade": "Media", "depends_on": None,
            "scheduled_time": "07:30:00", "schedule_type": "daily",
            "schedule_hour": 7, "schedule_minute": 30, "schedule_dow": 1,
            "schedule_dom": 1, "horarios_especificos": None,
            "dias_semana": None, "dias_horarios_mes": None,
            "somente_dias_uteis": 0, "calendario_nome": None,
            "hora_virada": None, "agenda_no": None, "dag_criada": 1}
    return {nome: dict(base) for nome in _NOMES}


# ═════════════════ dublê: a F3 + as duas consultas da F4 ════════════════════

class FakeDb(FakeDbF3):
    """FakeDb da F3 + o CONTADOR de statements (o orçamento de consultas é
    requisito de aceite da F4, não detalhe de implementação)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.sqls: list[str] = []
        # "Não consegui apurar" tem de ser uma resposta possível: lock timeout
        # em `etl_pipeline_execucao` às 3h é o cenário real.
        self.falhar_denominador = False
        # O dia do deploy: a 085 está no banco e o interruptor está em 0. A
        # leitura tem de funcionar assim mesmo — é o que torna esta fase
        # testável antes da F7.
        self.config[mc.CHAVE_ATIVA] = "0"

    def cursor(self):
        cur = super().cursor()
        return cur

    def execucao(self, pipeline, status, *, odate=ODATE, inicio=None, fim=None,
                 corrida=None, substituida=None, criado_em=None):
        """Uma linha de `etl_pipeline_execucao` — o insumo da classificação."""
        self.execucoes.append({
            "pipeline": pipeline, "data_referencia": odate,
            "execution_id": f"x__{pipeline}__{len(self.execucoes)}",
            "status": status, "inicio": inicio,
            "fim": fim, "disparado_por": "teste", "motivo": None,
            "criado_em": criado_em or inicio or AGORA_BANCO,
            "substituida_em": substituida, "malha_execucao_id": corrida})


def _qtd_quiescencia(db):
    return db.config.get(mc.CHAVE_QUIESCENCIA)


class FakeCur(FakeCurF3):
    # As três consultas que a F4 acrescenta. Ficam nomeadas aqui porque a
    # checagem de marcadores abaixo precisa saber QUAIS statements ela audita:
    # o dublê herdado atende dezenas de outros, e uma checagem global sobre
    # texto de SQL que este arquivo não escreveu seria contrato de outra fase.
    _DA_F4 = ("SELECT m.malha_name, c.id",
              "SELECT mm.malha_execucao_id",
              "SELECT pipeline_name, status, inicio")

    def execute(self, sql, params=()):  # noqa: C901 — dispatcher de dublê
        db = self.db
        s = " ".join(str(sql).split())
        db.sqls.append(s)
        p = tuple(params)

        # ⚠️ O DRIVER CONTA OS MARCADORES — e o dublê tem de contar também.
        #
        # `pyodbc` recusa o statement com "The SQL contains 1 parameter
        # markers, but 2 parameters were supplied". Sem esta linha o dublê era
        # MAIS PERMISSIVO que o driver, e a mutação que apaga o
        # `WHERE m.malha_name = ?` do módulo (deixando o parâmetro na tupla)
        # passava VERDE aqui — a suíte inteira dizendo "ok" sobre um SQL que o
        # banco recusaria na primeira chamada. É a mesma família da regra de
        # honestidade do `_guarda`: o dublê não pode ser mais generoso que a
        # coisa que ele imita.
        if s.startswith(self._DA_F4):
            assert s.count("?") == len(p), (
                "SQL com %d marcador(es) e %d parametro(s) — o pyodbc "
                "recusaria:\n%s\nparams=%r" % (s.count("?"), len(p), s, p))

        # A degradação vem ANTES do dispatch: sem a 085 as consultas novas têm
        # de morrer como morreriam no banco (208, Invalid object name), e não
        # ser atendidas por um dublê complacente. É o `sp_rename` do aceite.
        if not db.com_085 and "etl_malha_execucao" in s and "OBJECT_ID(" not in s:
            raise RuntimeError(
                "[42S02] Invalid object name 'dbo.etl_malha_execucao'. (208)")

        # ── (A) a corrida CORRENTE de cada malha ───────────────────────────
        if s.startswith("SELECT m.malha_name, c.id, c.malha_name"):
            self._rows = self._correntes(s, p)
            self.rowcount = -1
            return
        # ── (B) o snapshot de TODAS as corridas de uma vez ─────────────────
        if s.startswith("SELECT mm.malha_execucao_id, mm.pipeline_name"):
            if db.falhar_denominador:
                raise RuntimeError("lock timeout em etl_pipeline_execucao")
            self._rows = self._denominador_das_corridas(s, p)
            self.rowcount = -1
            return
        # ── o SELECT de `execucoes[]` do painel (com ou sem lente) ─────────
        if s.startswith("SELECT pipeline_name, status, inicio"):
            self._rows = self._painel(s, p)
            self.rowcount = -1
            return
        # ── os eventos do painel (`eventos[]` + `eventos_no[]`) ────────────
        # O dublê da F15 devolve lista VAZIA aqui ("sem eventos nestes
        # cenários"), e essa complacência esconderia exatamente o que a F4
        # precisa provar: `etl_dependencia_evento` é chaveada por (pipeline,
        # data, tipo) e NÃO pela corrida, então o `MALHA_CONCLUIDA` da corrida
        # anterior do MESMO dia continua chegando ao painel. Um dublê que
        # devolve vazio faz o teste do canvas verde passar sem canvas nenhum.
        if s.startswith("SELECT pipeline_name, tipo, detectado_em"):
            self._rows = [
                (e.get("pipeline_name") or e.get("pipeline"), e["tipo"],
                 e.get("detectado_em") or db.agora_banco, e.get("detalhe"))
                for e in db.eventos if e.get("data_referencia") == p[0]]
            self.rowcount = -1
            return
        super().execute(sql, params)

    # ── implementações ─────────────────────────────────────────────────────
    def _correntes(self, s, p):
        db = self.db
        i = 0
        alvo = None
        if _guarda(s, "AND me.id = ?"):
            alvo, i = int(p[i]), i + 1
        malha = p[i] if _guarda(s, "WHERE m.malha_name = ?") else None
        out = []
        for nome in sorted(db.malhas):
            if malha is not None and nome.casefold() != str(malha).casefold():
                continue
            candidatas = [c for c in db.corridas
                          if c["malha_name"].casefold() == nome.casefold()
                          and (alvo is None or c["id"] == alvo)]
            if not candidatas:
                continue                      # CROSS APPLY: a malha não sai
            c = max(candidatas, key=lambda x: (x["aberta_em"], x["id"]))
            teto = 1 if (c["teto_em"] is not None
                         and c["teto_em"] < db.agora_banco) else 0
            decorrido = int(
                (db.agora_banco - c["aberta_em"]).total_seconds() // 60)
            out.append((nome,) + _proj(c) + (teto, decorrido, db.agora_banco,
                                             _qtd_quiescencia(db)))
        return out

    def _denominador_das_corridas(self, s, p):
        """O LEFT JOIN do snapshot com a linha viva de cada membro.

        As quatro cláusulas do escopo são lidas do TEXTO (regra de honestidade):
        `data_referencia`, `substituida_em`, a proveniência/janela e o teto por
        `fechada_em`. Apagar qualquer uma do módulo muda o que o dublê devolve."""
        db = self.db
        ids = {int(x) for x in p}
        exige_odate = _guarda(s, "AND e.data_referencia = me.data_referencia")
        exige_viva = _guarda(s, "AND e.substituida_em IS NULL")
        recorta = _guarda(s, "AND (e.malha_execucao_id = me.id")
        tem_teto = _guarda(s, "OR COALESCE(e.inicio, e.criado_em) <= "
                              "me.fechada_em")
        out = []
        for m in sorted(db.membros_corrida,
                        key=lambda m: (m["malha_execucao_id"],
                                       m["pipeline_name"])):
            cid = int(m["malha_execucao_id"])
            if cid not in ids:
                continue
            c = db.por_id(cid)
            base = (cid, m["pipeline_name"], m["ativo_na_abertura"],
                    m["conta_para_fim"])
            fora = 1 if any(
                e.get("malha_execucao_id") == cid
                and e["pipeline"].casefold() == m["pipeline_name"].casefold()
                and e["data_referencia"] != c["data_referencia"]
                for e in db.execucoes) else 0
            linhas = []
            for e in db.execucoes:
                if e["pipeline"].casefold() != m["pipeline_name"].casefold():
                    continue
                if exige_odate and e["data_referencia"] != c["data_referencia"]:
                    continue
                if exige_viva and e.get("substituida_em") is not None:
                    continue
                if recorta:
                    momento = e.get("inicio") or e.get("criado_em")
                    proveniencia = e.get("malha_execucao_id") == cid
                    na_janela = momento >= c["aberta_em"] and (
                        not tem_teto or c["fechada_em"] is None
                        or momento <= c["fechada_em"])
                    if not (proveniencia or na_janela):
                        continue
                linhas.append(e)
            if not linhas:
                out.append(base + (None, None, 0, None, None, fora,
                                   db.agora_banco))
                continue
            for e in linhas:
                orfa = 1 if any(
                    ev["pipeline_name"] == e["pipeline"]
                    and ev["tipo"] == mc.EVENTO_ORFA
                    for ev in db.eventos) else 0
                movimento = e.get("fim") or e.get("inicio") or e.get("criado_em")
                sem_sinal = int(
                    (db.agora_banco - movimento).total_seconds() // 60)
                out.append(base + (e["status"],
                                   e.get("inicio") or e.get("criado_em"), orfa,
                                   sem_sinal, movimento, fora, db.agora_banco))
        return out

    def _painel(self, s, p):
        """`execucoes[]` — o dia inteiro, ou o escopo da corrida quando há
        lente. `substituida_em IS NULL` é lido do texto: sem ele, a linha
        aposentada volta a pintar o nó de verde."""
        db = self.db
        data_ref = p[0]
        exige_viva = _guarda(s, "AND substituida_em IS NULL")
        com_lente = _guarda(s, "AND (malha_execucao_id = ?")
        tem_teto = _guarda(s, "AND COALESCE(inicio, criado_em) <= ?")
        out = []
        for e in db.execucoes:
            if e["data_referencia"] != data_ref:
                continue
            if exige_viva and e.get("substituida_em") is not None:
                continue
            if com_lente:
                cid, aberta = int(p[1]), p[2]
                momento = e.get("inicio") or e.get("criado_em")
                na_janela = momento >= aberta and (
                    not tem_teto or momento <= p[3])
                if not (e.get("malha_execucao_id") == cid or na_janela):
                    continue
            out.append((e["pipeline"], e["status"], e.get("inicio"),
                        e.get("fim"), e.get("disparado_por"), e.get("motivo"),
                        e["execution_id"]))
        return out


FakeDb.cursor = lambda self: _cursor(self)


def _cursor(db):
    import copy
    db._snapshot = copy.deepcopy(db._estado())
    return FakeCur(db)


# ═══════════════════════════ fixtures e helpers ═════════════════════════════

@pytest.fixture(autouse=True)
def _sem_cache():
    mc.limpar_cache()
    yield
    mc.limpar_cache()


@pytest.fixture
def auth(app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "OPER1", "perfil": "operador",
        "permissoes": [PERM_EDITAR, PERM_EXECUTAR, "tela_malha"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _patch(db):
    return patch("routers.malhas.get_db_conn", side_effect=db.conectar)


def _patch_agora():
    return patch("routers.malhas._agora", return_value=AGORA_API)


def _card(resp, malha="M1"):
    return next(m for m in resp.json()["malhas"] if m["malha_name"] == malha)


def _estado_na_tela(card) -> tuple:
    """O que o card MOSTRA — a regra do front, em uma linha: a corrida quando
    ela existe, o "membro mais recente" quando não.

    Existe porque o aceite desta fase é sobre o que o gestor LÊ às 8h, e não
    sobre chaves de JSON. `MalhaCard` (`Malha.tsx`) faz exatamente isto:
    `const corrida = malha.corrida ?? null` e, sem ela, o fallback declarado
    com o sufixo "(membro mais recente)"."""
    corrida = card.get("corrida")
    if corrida:
        culpado = (corrida["pendentes"][0]["pipeline"]
                   if corrida["pendentes"] else None)
        return (corrida["status"], corrida["saude"], culpado)
    ultima = card.get("ultima_execucao")
    if not ultima:
        return ("sem execução registrada", None, None)
    return (ultima["status"], "(membro mais recente)", ultima["pipeline"])


def _cenario_defeito(db, client):
    """O defeito relatado, montado uma vez: CARGA_A falha 03:00, CARGA_B
    conclui 03:40 — e CARGA_B é a execução MAIS RECENTE da malha."""
    _monta_malha(client, "M1", ["CARGA_A", "CARGA_B"])
    c = db.abrir_corrida("M1", odate=ODATE,
                         aberta_em=datetime(2026, 8, 5, 1, 10),
                         membros=["CARGA_A", "CARGA_B"])
    db.execucao("CARGA_A", "FALHA", inicio=datetime(2026, 8, 5, 3, 0),
                fim=datetime(2026, 8, 5, 3, 5), corrida=c["id"])
    db.execucao("CARGA_B", "SUCESSO", inicio=datetime(2026, 8, 5, 3, 30),
                fim=datetime(2026, 8, 5, 3, 40), corrida=c["id"])
    return c


# ═════════════════════════════ o DEFEITO ════════════════════════════════════

def test_card_diz_falhou_e_nomeia_quem_falhou(client, auth):
    """O aceite da F4, literal. HOJE o card diz `sucesso · CARGA_B`; o campo
    que dizia isso continua no payload (é o fallback declarado), mas quem
    responde pelo estado da malha passa a ser a CORRIDA — e ela nomeia."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _cenario_defeito(db, client)
        card = _card(client.get("/malhas"))

    # o campo do defeito continua lá, e continua dizendo o que sempre disse:
    # é ele que a malha SEM corrida usa, com o sufixo "(membro mais recente)"
    assert card["ultima_execucao"]["status"] == "SUCESSO"
    assert card["ultima_execucao"]["pipeline"] == "CARGA_B"

    # ...e o que a tela passa a ler diz a verdade, com nome e sobrenome
    corrida = card["corrida"]
    assert corrida["status"] == "ABERTA"
    assert corrida["saude"] == "COM_FALHA"
    assert [(x["pipeline"], x["classe"]) for x in corrida["pendentes"]] == [
        ("CARGA_A", "falhou")]
    assert (corrida["membros_total"], corrida["membros_ok"]) == (2, 1)


def test_o_estado_na_tela_deixa_de_ser_o_do_membro_mais_recente(client, auth):
    """O MESMO cenário, olhado como o gestor olha: o que o card MOSTRA.

    Este teste nasceu escrito ao contrário — afirmando o comportamento de hoje,
    `("SUCESSO", "(membro mais recente)", "CARGA_B")`. Contra o código desta
    branch ele ficou VERMELHO com a diferença exata:

        assert ('ABERTA', 'COM_FALHA', 'CARGA_A')
            == ('SUCESSO', '(membro mais recente)', 'CARGA_B')

    e contra a `main` (o código anterior à fase) ficou VERDE — porque lá o card
    não tem bloco `corrida` e o único estado disponível é o do membro que
    executou por último. É essa dupla execução que prova que o teste mede o
    DEFEITO, e não a própria opinião.

    Guardado agora na forma de regressão: se alguém devolver a decisão para
    `melhor[malha] = max((momento, pipeline))`, esta linha volta a ser
    `SUCESSO · CARGA_B` e este teste cai."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _cenario_defeito(db, client)
        card = _card(client.get("/malhas"))
    assert _estado_na_tela(card) == ("ABERTA", "COM_FALHA", "CARGA_A")
    # ...e o fallback continua guardado e continua dizendo o que sempre disse:
    # ele é o que a malha SEM corrida mostra, com a confissão no sufixo
    assert (card["ultima_execucao"]["status"],
            card["ultima_execucao"]["pipeline"]) == ("SUCESSO", "CARGA_B")


def test_leitura_da_corrida_independe_do_interruptor(client, auth):
    """§11.2 — o interruptor governa quem ABRE e quem FECHA, não quem LÊ.

    Com ele em `0` (o estado do dia do deploy, e o do dev até a F7) uma corrida
    que EXISTE continua aparecendo: escondê-la seria esconder justamente a
    corrida presa que o operador precisa encerrar, já que `POST .../encerrar`
    não passa pelo portão."""
    db = FakeDb(pipelines=_pipes())
    assert db.config[mc.CHAVE_ATIVA] == "0"
    with _patch(db), _patch_agora():
        _cenario_defeito(db, client)
        card = _card(client.get("/malhas"))
    assert card["corrida"]["saude"] == "COM_FALHA"


def test_corrida_em_voo_sem_falha_e_azul(client, auth):
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A", "B", "C"])
        c = db.abrir_corrida("M1", odate=ODATE,
                             aberta_em=AGORA_BANCO - timedelta(minutes=20),
                             membros=["A", "B", "C"])
        db.execucao("A", "SUCESSO", inicio=AGORA_BANCO - timedelta(minutes=18),
                    fim=AGORA_BANCO - timedelta(minutes=10), corrida=c["id"])
        db.execucao("B", "EXECUTANDO", inicio=AGORA_BANCO - timedelta(minutes=9),
                    corrida=c["id"])
        db.execucao("C", "AGUARDANDO_DEPENDENCIA",
                    criado_em=AGORA_BANCO - timedelta(minutes=9),
                    corrida=c["id"])
        corrida = _card(client.get("/malhas"))["corrida"]
    assert corrida["status"] == "ABERTA"
    assert corrida["saude"] == "OK"
    assert (corrida["membros_total"], corrida["membros_ok"],
            corrida["membros_vivos"]) == (3, 1, 2)
    assert corrida["pendentes"] == []


def test_falha_pinta_vermelho_com_a_malha_inteira_correndo(client, auth):
    """O aceite da F4, com os números da spec: `CARGA_A` em falha e **38
    membros correndo**.

    A saúde não espera o fechamento. Com 38 pipelines em voo a corrida só
    fecharia horas depois — e é exatamente aí que o card de hoje ficaria azul
    (ou verde, pelo membro mais recente) enquanto a madrugada já está perdida.
    A proporção importa: 1 em 39 é o caso em que "a maioria está indo bem" é
    verdade e irrelevante."""
    db = FakeDb(pipelines=_pipes())
    correndo = [f"P{i}" for i in range(38)]
    membros = ["CARGA_A"] + correndo
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", membros)
        c = db.abrir_corrida("M1", odate=ODATE,
                             aberta_em=AGORA_BANCO - timedelta(minutes=20),
                             membros=membros)
        db.execucao("CARGA_A", "FALHA",
                    inicio=AGORA_BANCO - timedelta(minutes=15),
                    fim=AGORA_BANCO - timedelta(minutes=14), corrida=c["id"])
        for p in correndo:
            db.execucao(p, "EXECUTANDO",
                        inicio=AGORA_BANCO - timedelta(minutes=5),
                        corrida=c["id"])
        card = _card(client.get("/malhas"))
    corrida = card["corrida"]
    # o ciclo continua ABERTO — e mesmo assim o card já é vermelho e já nomeia
    assert corrida["status"] == "ABERTA"
    assert corrida["saude"] == "COM_FALHA"
    assert (corrida["membros_total"], corrida["membros_vivos"]) == (39, 38)
    assert [x["pipeline"] for x in corrida["pendentes"]] == ["CARGA_A"]
    assert _estado_na_tela(card) == ("ABERTA", "COM_FALHA", "CARGA_A")


def test_pendentes_distinguem_as_quatro_classes(client, auth):
    """Decisão 21 — três problemas com três donos não podem virar
    "3 pendentes": rodar o job de novo, soltar a dependência e descobrir por
    que a DAG nunca partiu são ações diferentes."""
    db = FakeDb(pipelines=_pipes())
    membros = ["P_FALHOU", "P_NAO_LIBEROU", "P_NAO_PARTIU", "P_ORFA"]
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", membros)
        c = db.abrir_corrida("M1", odate=ODATE,
                             aberta_em=AGORA_BANCO - timedelta(hours=2),
                             membros=membros)
        db.execucao("P_FALHOU", "FALHA", inicio=AGORA_BANCO - timedelta(hours=1),
                    fim=AGORA_BANCO - timedelta(minutes=50), corrida=c["id"])
        db.execucao("P_NAO_LIBEROU", "NAO_LIBEROU",
                    criado_em=AGORA_BANCO - timedelta(hours=1), corrida=c["id"])
        db.execucao("P_ORFA", "EXECUTANDO",
                    inicio=AGORA_BANCO - timedelta(hours=1), corrida=c["id"])
        # a órfã só sai de "vivo" DEPOIS de alertada (Decisão 22)
        db.eventos.append({"pipeline_name": "P_ORFA", "data_referencia": ODATE,
                           "tipo": mc.EVENTO_ORFA, "detalhe": None,
                           "malha_execucao_id": c["id"]})
        corrida = _card(client.get("/malhas"))["corrida"]
    assert {x["pipeline"]: x["classe"] for x in corrida["pendentes"]} == {
        "P_FALHOU": "falhou", "P_NAO_LIBEROU": "nao_liberou",
        "P_NAO_PARTIU": "nao_partiu", "P_ORFA": "orfa"}
    assert corrida["membros_vivos"] == 0      # a órfã alertada não é vivo


# ══════════════════ o orçamento de consultas (o N+1 que não há) ═════════════

@pytest.mark.parametrize("quantas", [4, 40])
def test_lista_gasta_duas_consultas_qualquer_que_seja_o_numero_de_malhas(
        client, auth, quantas):
    """Aceite da F4: **duas** consultas no total para o bloco da corrida — e o
    número não pode crescer com a lista. A tela de acompanhamento faz refetch;
    40 malhas × 1 consulta por malha seria o custo multiplicado por 40 a cada
    ciclo de polling."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        for i in range(quantas):
            nome = f"M{i:03d}"
            _monta_malha(client, nome, ["A", "B"])
            db.abrir_corrida(nome, odate=ODATE,
                             aberta_em=AGORA_BANCO - timedelta(hours=1),
                             membros=["A", "B"])
        db.sqls.clear()
        resp = client.get("/malhas")
    assert resp.status_code == 200
    assert sum(1 for m in resp.json()["malhas"] if m.get("corrida")) == quantas
    da_corrida = [s for s in db.sqls if "etl_malha_execucao" in s]
    assert len(da_corrida) == 2, "\n".join(da_corrida)


def test_o_custo_TOTAL_da_lista_nao_cresce_com_o_numero_de_malhas(client, auth):
    """A contagem das DUAS consultas do bloco não basta sozinha: ela provaria
    o orçamento da corrida enquanto um N+1 podia ter entrado ao lado (um probe
    de tabela por malha, uma sonda de config por card).

    Aqui se mede o statement por statement do endpoint inteiro — todas as
    chamadas ao cursor — com 4 malhas e com 40. Os dois números têm de ser o
    MESMO: `GET /malhas` é a tela de acompanhamento, ela faz refetch a cada
    20 s com corrida em voo, e cada statement a mais é multiplicado por 3 por
    minuto e por operador."""
    def gasto(quantas):
        db = FakeDb(pipelines=_pipes())
        with _patch(db), _patch_agora():
            for i in range(quantas):
                nome = f"M{i:03d}"
                _monta_malha(client, nome, ["A", "B"])
                db.abrir_corrida(nome, odate=ODATE,
                                 aberta_em=AGORA_BANCO - timedelta(hours=1),
                                 membros=["A", "B"])
                db.execucao("A", "SUCESSO",
                            inicio=AGORA_BANCO - timedelta(minutes=50),
                            fim=AGORA_BANCO - timedelta(minutes=40))
            db.sqls.clear()
            resp = client.get("/malhas")
        assert resp.status_code == 200
        assert len(resp.json()["malhas"]) == quantas
        return list(db.sqls)

    com_4, com_40 = gasto(4), gasto(40)
    assert len(com_4) == len(com_40), (
        "o endpoint gastou %d statements com 4 malhas e %d com 40 — o que "
        "cresceu:\n%s" % (len(com_4), len(com_40),
                          "\n".join(sorted(set(com_40) - set(com_4))[:5])))
    # e o bloco da corrida são DOIS deles, nomeados, para o número acima nunca
    # ser "constante porque nada foi consultado"
    assert len([s for s in com_40 if "etl_malha_execucao" in s]) == 2


# ═════════════ F4+/1 — `substituida_em IS NULL` nos DOIS lugares ════════════

def test_rerun_a_faixa_e_o_canvas_contam_a_mesma_linha(client, auth):
    """Decisão 55. `A` concluiu, alguém reexecutou e a linha antiga foi
    APOSENTADA (`substituida_em`), com a nova ainda não registrada.

    Sem a cláusula, a faixa diria `2 de 3` e o nó de `A` ficaria VERDE no
    canvas — a mesma tela contando duas coisas diferentes. O teste compara os
    dois na MESMA resposta, que é o único jeito de pegar "arrumei a barra e
    esqueci o nó"."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A", "B", "C"])
        c = db.abrir_corrida("M1", odate=ODATE,
                             aberta_em=datetime(2026, 8, 5, 1, 0),
                             membros=["A", "B", "C"])
        db.execucao("A", "SUCESSO", inicio=datetime(2026, 8, 5, 1, 5),
                    fim=datetime(2026, 8, 5, 1, 10), corrida=c["id"],
                    substituida=datetime(2026, 8, 5, 3, 0))
        db.execucao("B", "SUCESSO", inicio=datetime(2026, 8, 5, 1, 20),
                    fim=datetime(2026, 8, 5, 1, 30), corrida=c["id"])
        db.execucao("C", "SUCESSO", inicio=datetime(2026, 8, 5, 1, 35),
                    fim=datetime(2026, 8, 5, 1, 45), corrida=c["id"])
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()

    # a faixa
    assert painel["corrida"]["membros_ok"] == 2
    assert [x["pipeline"] for x in painel["corrida"]["pendentes"]] == ["A"]
    # ...e o canvas, na mesma resposta
    assert [e["pipeline_name"] for e in painel["execucoes"]] == ["B", "C"]


# ═════════ F4+/2 — o denominador do SNAPSHOT, que não encolhe ═══════════════

def test_denominador_nao_encolhe_quando_a_guardia_pula_membros(client, auth):
    """Decisão 52 — o cenário `Carga_Vida`: às 02:00 o card diz `2 de 7`; às
    02:40 a guardiã marca 3 membros como `PULADO` por divergência de ODATE.

    Com `esperados = total − dispensados` o card passaria a dizer **`2 de 4`**,
    e o olho leria "avançou" onde três pipelines foram BARRADOS."""
    db = FakeDb(pipelines=_pipes())
    membros = [f"P{i}" for i in range(7)]
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", membros)
        c = db.abrir_corrida("M1", odate=ODATE,
                             aberta_em=AGORA_BANCO - timedelta(hours=1),
                             membros=membros)
        for p in membros[:2]:
            db.execucao(p, "SUCESSO",
                        inicio=AGORA_BANCO - timedelta(minutes=50),
                        fim=AGORA_BANCO - timedelta(minutes=40),
                        corrida=c["id"])
        antes = _card(client.get("/malhas"))["corrida"]

        for p in membros[4:]:                 # a guardiã pula 3 no ciclo seguinte
            db.execucao(p, "PULADO",
                        inicio=AGORA_BANCO - timedelta(minutes=20),
                        fim=AGORA_BANCO - timedelta(minutes=20),
                        corrida=c["id"])
        depois = _card(client.get("/malhas"))["corrida"]

    assert (antes["membros_total"], antes["membros_ok"]) == (7, 2)
    assert (depois["membros_total"], depois["membros_ok"]) == (7, 2)
    assert depois["membros_dispensados"] == 3
    assert antes["membros_dispensados"] == 0


def test_membro_inativado_na_abertura_fica_fora_do_denominador_mas_visivel(
        client, auth):
    """§6.9/#9 — quem já estava inativo quando a corrida abriu não infla o
    denominador, e também não some: vira `membros_inativos`."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A", "B"])
        c = db.abrir_corrida("M1", odate=ODATE,
                             aberta_em=AGORA_BANCO - timedelta(hours=1),
                             membros=["A"])
        db.membros_corrida.append(
            {"malha_execucao_id": c["id"], "pipeline_name": "B",
             "conta_para_fim": 1, "ativo_na_abertura": 0, "eh_raiz": 0})
        db.execucao("A", "SUCESSO", inicio=AGORA_BANCO - timedelta(minutes=50),
                    fim=AGORA_BANCO - timedelta(minutes=40), corrida=c["id"])
        corrida = _card(client.get("/malhas"))["corrida"]
    assert (corrida["membros_total"], corrida["membros_ok"]) == (1, 1)
    assert corrida["membros_inativos"] == 1


# ═════════════ F4+/3 — o travado FORA do que a barra preenche ═══════════════

def test_travado_e_campo_proprio_e_a_identidade_da_barra_fecha(client, auth):
    """Decisão 54 — a barra responde UMA coisa: quanto já ficou pronto.

    `total = ok + vivos + dispensados + travados + nao_partiram` é a identidade
    que garante que o travado não é pintado: se ele entrasse na barra, `3 de 6`
    pintaria 5/6 do trilho e, a 1,5 m, leria-se "quase pronto"."""
    db = FakeDb(pipelines=_pipes())
    membros = ["OK1", "OK2", "OK3", "VIVO", "PULA", "FALHOU"]
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", membros)
        c = db.abrir_corrida("M1", odate=ODATE,
                             aberta_em=AGORA_BANCO - timedelta(minutes=30),
                             membros=membros)
        for p in membros[:3]:
            db.execucao(p, "SUCESSO",
                        inicio=AGORA_BANCO - timedelta(minutes=25),
                        fim=AGORA_BANCO - timedelta(minutes=20), corrida=c["id"])
        db.execucao("VIVO", "EXECUTANDO",
                    inicio=AGORA_BANCO - timedelta(minutes=5), corrida=c["id"])
        db.execucao("PULA", "PULADO",
                    inicio=AGORA_BANCO - timedelta(minutes=25),
                    fim=AGORA_BANCO - timedelta(minutes=25), corrida=c["id"])
        db.execucao("FALHOU", "FALHA",
                    inicio=AGORA_BANCO - timedelta(minutes=15),
                    fim=AGORA_BANCO - timedelta(minutes=14), corrida=c["id"])
        corrida = _card(client.get("/malhas"))["corrida"]
    assert corrida["membros_ok"] == 3
    assert corrida["membros_vivos"] == 1
    assert corrida["membros_dispensados"] == 1
    assert corrida["membros_travados"] == 1
    assert corrida["membros_nao_partiram"] == 0
    assert (corrida["membros_total"]
            == corrida["membros_ok"] + corrida["membros_vivos"]
            + corrida["membros_dispensados"] + corrida["membros_travados"]
            + corrida["membros_nao_partiram"])


def test_corrida_recem_aberta_nao_nasce_com_o_chip_vermelho(client, auth):
    """⚠️ REGRESSÃO de um alarme falso DIÁRIO, encontrado na revisão
    adversarial da F4.

    Toda corrida abre antes de qualquer pipeline ter linha em
    `etl_pipeline_execucao` — o Início dispara as raízes, e nos primeiros
    segundos o snapshot inteiro está sem linha. A classificação conservadora
    manda todo mundo para `nao_partiu` (que é a resposta certa: separar
    "não roda hoje" exigiria um `dia_permitido` POR MEMBRO, o N+1 que a fase
    existe para não ter). Com `travados = len(pendentes)`, o card de TODA
    malha nascia às 01:10 com

        em andamento · corrida de 05/08 · 0 de 7   ▲ 7 travados
        ↳ não chegou a iniciar: A

    — chip vermelho e um culpado escolhido por ordem alfabética, sobre um
    ciclo perfeitamente saudável, todas as noites. As Decisões 26/27 são
    literais sobre isto: alarme falso treina o operador a ignorar o alarme.

    A tabela da Decisão 54 é a régua: chip é para `falhou`, `orfa` e
    `nao_liberou`; `nao_partiu` fica no trilho vazio e ganha campo próprio.
    O NÚMERO não some — some o vermelho."""
    db = FakeDb(pipelines=_pipes())
    membros = ["A", "B", "C", "OK1", "OK2", "OK3", "VIVO"]
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", membros)
        db.abrir_corrida("M1", odate=ODATE,
                         aberta_em=AGORA_BANCO - timedelta(seconds=30),
                         membros=membros)
        corrida = _card(client.get("/malhas"))["corrida"]
    assert corrida["status"] == "ABERTA"
    assert corrida["saude"] == "OK"          # azul, não âmbar, não vermelho
    assert corrida["membros_travados"] == 0, "chip vermelho numa corrida de 30s"
    assert corrida["membros_nao_partiram"] == 7
    assert (corrida["membros_total"], corrida["membros_ok"]) == (7, 0)
    # e a informação continua inteira: quem ainda não partiu está nomeado
    assert [x["classe"] for x in corrida["pendentes"]] == ["nao_partiu"] * 7


def test_chip_vermelho_conta_falhou_orfa_e_nao_liberou(client, auth):
    """O outro lado da mesma régua: as três classes que SÃO problema com dono
    continuam no chip, e o `nao_partiu` que está junto delas não engorda o
    número (`▲ 4 travados` em vez de `▲ 3` diria "há mais um incêndio")."""
    db = FakeDb(pipelines=_pipes())
    membros = ["P_FALHOU", "P_ORFA", "P_NAO_LIBEROU", "P_NAO_PARTIU"]
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", membros)
        c = db.abrir_corrida("M1", odate=ODATE,
                             aberta_em=AGORA_BANCO - timedelta(hours=1),
                             membros=membros)
        db.execucao("P_FALHOU", "FALHA",
                    inicio=AGORA_BANCO - timedelta(minutes=40),
                    fim=AGORA_BANCO - timedelta(minutes=39), corrida=c["id"])
        db.execucao("P_ORFA", "EXECUTANDO",
                    inicio=AGORA_BANCO - timedelta(minutes=40), corrida=c["id"])
        db.eventos.append({"pipeline": "P_ORFA", "pipeline_name": "P_ORFA",
                           "data_referencia": ODATE, "tipo": mc.EVENTO_ORFA,
                           "detectado_em": AGORA_BANCO, "detalhe": ""})
        db.execucao("P_NAO_LIBEROU", "NAO_LIBEROU",
                    criado_em=AGORA_BANCO - timedelta(minutes=40),
                    corrida=c["id"])
        corrida = _card(client.get("/malhas"))["corrida"]
    assert corrida["membros_travados"] == 3
    assert corrida["membros_nao_partiram"] == 1
    assert corrida["saude"] == "COM_FALHA"


# ═══════════════════ a lente: duas corridas no mesmo ODATE ══════════════════

def test_duas_corridas_do_mesmo_odate_nao_se_sobrepoem(client, auth):
    """Aceite da F4 — redisparar depois de um incidente é gesto diário, e o
    par (malha, data) deixa de ser identidade nesse instante. Sem a lente, a
    segunda madrugada apagaria a primeira na tela."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A", "B"])
        c1 = db.abrir_corrida("M1", odate=ODATE,
                              aberta_em=datetime(2026, 8, 5, 1, 0),
                              membros=["A", "B"], status="FALHA")
        db.execucao("A", "FALHA", inicio=datetime(2026, 8, 5, 1, 5),
                    fim=datetime(2026, 8, 5, 1, 6), corrida=c1["id"])
        db.execucao("B", "SUCESSO", inicio=datetime(2026, 8, 5, 1, 10),
                    fim=datetime(2026, 8, 5, 1, 20), corrida=c1["id"])
        c2 = db.abrir_corrida("M1", odate=ODATE,
                              aberta_em=datetime(2026, 8, 5, 5, 0),
                              membros=["A", "B"])
        db.execucao("A", "SUCESSO", inicio=datetime(2026, 8, 5, 5, 5),
                    fim=datetime(2026, 8, 5, 5, 10), corrida=c2["id"])
        db.execucao("B", "SUCESSO", inicio=datetime(2026, 8, 5, 5, 15),
                    fim=datetime(2026, 8, 5, 5, 25), corrida=c2["id"])

        p1 = client.get(f"/malhas/M1/execucao?corrida={c1['id']}").json()
        p2 = client.get(f"/malhas/M1/execucao?corrida={c2['id']}").json()
        lista = client.get("/malhas/M1/corridas").json()

    assert p1["corrida"]["sequencia"] == 1 and p2["corrida"]["sequencia"] == 2
    assert p1["corrida"]["status"] == "FALHA"
    assert [x["pipeline"] for x in p1["corrida"]["pendentes"]] == ["A"]
    assert p2["corrida"]["membros_ok"] == 2 and p2["corrida"]["pendentes"] == []
    # a #1 (FECHADA) não enxerga as linhas da #2, que começaram depois dela
    assert sorted((e["pipeline_name"], e["status"])
                  for e in p1["execucoes"]) == [("A", "FALHA"),
                                                ("B", "SUCESSO")]
    assert len(lista["corridas"]) == 2


def test_o_MALHA_CONCLUIDA_da_corrida_anterior_nao_conclui_a_de_agora(
        client, auth):
    """⚠️ REGRESSÃO da revisão adversarial — o verde que sobrava para o CANVAS.

    Cenário: a corrida #1 de 05/08 concluiu, e o nó Fim emitiu
    `MALHA_CONCLUIDA` às 04:02. Evento emitido é histórico verdadeiro e não se
    apaga. Às 05:00 o operador redispara (gesto diário), e a corrida #2 do
    MESMO ODATE nasce e falha.

    Este teste fixa as DUAS metades do fato:

      1. o `malha_concluida` do payload — a fonte do banner verde — responde
         pelo STATUS DA CORRIDA em foco, e sai `None`. Essa metade a F4 já
         tinha;
      2. `eventos_no` CONTINUA trazendo o evento das 04:02, porque a tabela é
         chaveada por (pipeline, data, tipo) e o marcador do nó não carrega o
         id do ciclo (a Decisão 49 só chega na F9). É por isso que o front
         **não pode** derivar o verde do nó Fim desse evento — a guarda está
         em `MalhaEditor.execDoComponente` e é travada em
         `test_malhas_f4_front.py`. Se um dia o evento passar a ser filtrado
         por corrida, esta linha cai e o par de testes é revisto junto."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["CARGA_A", "CARGA_B"])
        fim = _cria_no(client, "M1", "fim")
        c1 = db.abrir_corrida("M1", odate=ODATE,
                              aberta_em=datetime(2026, 8, 5, 1, 0),
                              membros=["CARGA_A", "CARGA_B"],
                              status="CONCLUIDA")
        for p in ("CARGA_A", "CARGA_B"):
            db.execucao(p, "SUCESSO", inicio=datetime(2026, 8, 5, 1, 5),
                        fim=datetime(2026, 8, 5, 1, 20), corrida=c1["id"])
        db.eventos.append({"pipeline_name": f"#no:{fim}",
                           "data_referencia": ODATE, "tipo": "MALHA_CONCLUIDA",
                           "detectado_em": datetime(2026, 8, 5, 4, 2),
                           "detalhe": "malha concluída", "malha_execucao_id": None})
        c2 = db.abrir_corrida("M1", odate=ODATE,
                              aberta_em=datetime(2026, 8, 5, 5, 0),
                              membros=["CARGA_A", "CARGA_B"])
        db.execucao("CARGA_A", "FALHA", inicio=datetime(2026, 8, 5, 5, 5),
                    fim=datetime(2026, 8, 5, 5, 6), corrida=c2["id"])
        db.execucao("CARGA_B", "EXECUTANDO", inicio=datetime(2026, 8, 5, 5, 15),
                    corrida=c2["id"])
        painel = client.get(f"/malhas/M1/execucao?corrida={c2['id']}").json()

    assert painel["corrida"]["status"] == "ABERTA"
    assert painel["corrida"]["saude"] == "COM_FALHA"
    # (1) o banner verde não sai — quem responde é o status da corrida em foco
    assert painel["malha_concluida"] is None
    # (2) ...e o evento das 04:02 continua no payload: é o insumo que o nó Fim
    #     do canvas NÃO pode ler como "esta corrida concluiu"
    assert [(e["tipo_no"], e["tipo"], e["criado_em"])
            for e in painel["eventos_no"]] == [
        ("fim", "MALHA_CONCLUIDA", "2026-08-05 04:02:00")]


def test_lente_de_corrida_de_outra_malha_e_404(client, auth):
    """Nunca a corrente disfarçada: o ◀ ▶ "funcionando" com o ciclo errado é
    pior que o botão quebrado."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A"])
        _monta_malha(client, "M2", ["A"])
        alheia = db.abrir_corrida("M2", odate=ODATE, aberta_em=AGORA_BANCO,
                                  membros=["A"])
        resp = client.get(f"/malhas/M1/execucao?corrida={alheia['id']}")
    assert resp.status_code == 404


def test_sem_parametro_o_painel_usa_o_odate_da_corrida(client, auth):
    """§9.6 — a divergência confessada entre o ODATE do painel (virada GLOBAL)
    e o do disparo some: os dois passam a ler o mesmo registro."""
    db = FakeDb(pipelines=_pipes(), config={"dependencia_hora_virada": "00:00"})
    db.config[mc.CHAVE_ATIVA] = "0"
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A"])
        db.abrir_corrida("M1", odate=ODATE_ONTEM,
                         aberta_em=datetime(2026, 8, 4, 1, 0), membros=["A"])
        painel = client.get("/malhas/M1/execucao").json()
    assert painel["data_referencia"] == "2026-08-04"
    assert painel["corrida"]["data_referencia"] == "2026-08-04"


def test_navegacao_por_dia_nao_traz_a_faixa_de_outro_dia(client, auth):
    """Data explícita é navegação por dia. A faixa falando de 05/08 sobre uma
    lista de 03/08 seria o card mentindo com layout novo."""
    db = FakeDb(pipelines=_pipes(), config={"dependencia_hora_virada": "00:00"})
    db.config[mc.CHAVE_ATIVA] = "0"
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A"])
        db.abrir_corrida("M1", odate=ODATE, aberta_em=AGORA_BANCO,
                         membros=["A"])
        painel = client.get(
            "/malhas/M1/execucao?data_referencia=2026-08-03").json()
    assert painel["data_referencia"] == "2026-08-03"
    assert "corrida" not in painel


def test_dia_com_DUAS_corridas_nao_mistura_a_faixa_de_uma_com_o_canvas_das_duas(
        client, auth):
    """O buraco que sobrou entre a navegação por dia e a lente (achado 4 da
    revisão da F4).

    Sem lente, `execucoes[]` traz o DIA INTEIRO — as linhas das duas corridas.
    O bloco `corrida`, porém, descreveria só a última. Resultado: o nó da
    corrida #1 verde no canvas ao lado de uma faixa dizendo `0 de 2` da #2, na
    MESMA tela — a Decisão 55 pelo avesso, e a mesma família de defeito que
    esta fase inteira existe para matar.

    Com mais de uma corrida no dia o bloco SAI, e `corridas_no_dia` diz ao
    front que há uma escolha a oferecer (o ◀ ▶, que aplica a lente e recorta as
    duas pontas juntas). Não é a mesma coisa que "este dia não teve corrida",
    onde o bloco simplesmente não vem e não há ação nenhuma a sugerir."""
    db = FakeDb(pipelines=_pipes(), config={"dependencia_hora_virada": "00:00"})
    db.config[mc.CHAVE_ATIVA] = "0"
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A", "B"])
        # duas corridas no MESMO ODATE: a #1 fechada (o ciclo da madrugada) e a
        # #2 aberta (o rerun das 5h) — o gesto que o próprio aceite descreve.
        db.abrir_corrida("M1", odate=ODATE, status="CONCLUIDA",
                         aberta_em=datetime(2026, 8, 5, 1, 10),
                         membros=["A", "B"])
        db.abrir_corrida("M1", odate=ODATE,
                         aberta_em=datetime(2026, 8, 5, 5, 0),
                         membros=["A", "B"])
        painel = client.get(
            "/malhas/M1/execucao?data_referencia=2026-08-05").json()
    assert "corrida" not in painel, \
        "com duas corridas no dia, descrever UMA sobre a lista das DUAS é a mentira"
    assert painel["corridas_no_dia"] == 2


def test_dia_com_UMA_corrida_mantem_a_faixa(client, auth):
    """O contraponto — sem ele, o conserto acima poderia ter simplesmente
    apagado a faixa de toda navegação por data, que é o caso comum."""
    db = FakeDb(pipelines=_pipes(), config={"dependencia_hora_virada": "00:00"})
    db.config[mc.CHAVE_ATIVA] = "0"
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A"])
        db.abrir_corrida("M1", odate=ODATE, aberta_em=AGORA_BANCO,
                         membros=["A"])
        painel = client.get(
            "/malhas/M1/execucao?data_referencia=2026-08-05").json()
    assert painel["corrida"]["data_referencia"] == "2026-08-05"
    assert "corridas_no_dia" not in painel


# ════════════════════ o banner verde e o card verde juntos ══════════════════

def test_malha_concluida_sai_do_status_da_corrida(client, auth):
    """§9.6 — o evento vira RASTRO. Com a corrida em FALHA, um
    `MALHA_CONCLUIDA` de uma corrida ANTERIOR do mesmo dia não pode pintar o
    banner de verde: evento emitido é histórico verdadeiro e não se apaga."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A"])
        c = db.abrir_corrida("M1", odate=ODATE, aberta_em=AGORA_BANCO,
                             membros=["A"], status="FALHA")
        db.execucao("A", "FALHA", inicio=AGORA_BANCO, fim=AGORA_BANCO,
                    corrida=c["id"])
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
    assert painel["corrida"]["status"] == "FALHA"
    assert painel["malha_concluida"] is None


def test_corrida_concluida_alimenta_o_banner(client, auth):
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A"])
        c = db.abrir_corrida("M1", odate=ODATE,
                             aberta_em=AGORA_BANCO - timedelta(hours=2),
                             membros=["A"], status="CONCLUIDA")
        db.execucao("A", "SUCESSO",
                    inicio=AGORA_BANCO - timedelta(hours=2),
                    fim=AGORA_BANCO - timedelta(hours=1), corrida=c["id"])
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
    assert painel["malha_concluida"]["em"] == painel["corrida"]["fechada_em"]
    assert painel["corrida"]["saude"] is None      # terminal: o status já diz


# ══════ F6 — a TERCEIRA porta: o painel pergunta pela corrida da LENTE ══════

def _espiao_do_predicado():
    """Recorde de `(pipeline, data_ref, corrida)` de cada consulta ao port.

    O predicado é o mesmo objeto do motor; aqui só se prova o ARGUMENTO — se o
    painel não entregar a corrida, ele responderia pela janela de 12h enquanto
    o motor responde pelo `aberta_em`, e a tela voltaria a contar uma história
    diferente da do motor (a doença que o D29 matou, entrando pelo corte)."""
    vistos: list = []

    def _liberado(cur, pipeline, data_ref, corrida=None):
        vistos.append((pipeline, data_ref, corrida))
        return False, ["PAI_X"]
    return vistos, _liberado


def test_painel_com_lente_pergunta_o_predicado_com_a_corrida(client, auth):
    """Decisão 39 — a corrida da LINHA avaliada, e no painel a linha veio do
    recorte da LENTE: é a corrida dela que corta."""
    vistos, espiao = _espiao_do_predicado()
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora(), \
            patch("routers.malhas.deps_svc.liberado", espiao):
        _monta_malha(client, "M1", ["A"])
        c = db.abrir_corrida("M1", odate=ODATE, aberta_em=AGORA_BANCO,
                             membros=["A"])
        db.execucao("A", "AGUARDANDO_DEPENDENCIA", corrida=c["id"])
        painel = client.get(f"/malhas/M1/execucao?corrida={c['id']}").json()
    assert painel["execucoes"][0]["faltantes"] == ["PAI_X"]
    assert vistos == [("A", ODATE, c["id"])]


def test_painel_sem_lente_pergunta_sem_corrida(client, auth):
    """Navegação por DIA não tem lente: sem corrida, o predicado resolve pelos
    degraus 2 e 3 — o comportamento de antes da fase. Inventar uma corrida aqui
    recortaria o dia inteiro pelo relógio de um ciclo só."""
    vistos, espiao = _espiao_do_predicado()
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora(), \
            patch("routers.malhas.deps_svc.liberado", espiao):
        _monta_malha(client, "M1", ["A"])
        db.execucao("A", "AGUARDANDO_DEPENDENCIA", odate=ODATE_ONTEM)
        client.get(f"/malhas/M1/execucao?data_referencia={ODATE_ONTEM}").json()
    assert vistos == [("A", ODATE_ONTEM, None)]


# ═══════════════════════ degradação (Decisão 41 e §11.1) ════════════════════

def test_sem_a_085_a_chave_corrida_nao_existe(client, auth):
    """A degradação é por AUSÊNCIA DE CAMPO — nunca `corrida: null`, nunca uma
    flag que o front tenha de interpretar para decidir renderizar.

    E `ultima_execucao` continua no payload: é o fallback "(membro mais
    recente)" que o card degradado mostra."""
    db = FakeDb(pipelines=_pipes(), com_085=False)
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["CARGA_A", "CARGA_B"])
        db.execucao("CARGA_B", "SUCESSO", inicio=datetime(2026, 8, 5, 3, 30),
                    fim=datetime(2026, 8, 5, 3, 40))
        corpo = client.get("/malhas").json()
        painel = client.get("/malhas/M1/execucao").json()
    card = next(m for m in corpo["malhas"] if m["malha_name"] == "M1")
    assert "corrida" not in card
    assert card["ultima_execucao"]["pipeline"] == "CARGA_B"
    assert corpo["migration_085_pendente"] is True
    assert "corrida" not in painel
    assert painel["migration_085_pendente"] is True
    assert painel["execucoes"], "o painel continua de pé sem a 085"


def test_sem_a_085_o_card_e_o_painel_degradam_JUNTOS(client, auth):
    """Aceite da F4 — "o banner verde some junto com o card verde, e a palavra
    'concluída' não aparece em nenhum dos dois".

    O cenário é o pior possível: a malha rodou de verdade, o nó Fim emitiu
    `MALHA_CONCLUIDA` (evento emitido é histórico verdadeiro, e não se apaga) e
    o banco está SEM a 085. Sem disciplina, o painel pintaria o banner verde
    sozinho enquanto o card ao lado, sem corrida, não pode afirmar nada.

    A API responde a isso com **um sinal em cada payload** — a mesma flag, nos
    dois — e é ela que o painel usa para calar o banner
    (`MalhaEditor.tsx`: `!corrida && !sem085 && …`, provado em
    `test_malhas_f4_front.py`). Aqui se prova a metade do servidor: a flag
    viaja nos DOIS, nenhum dos dois ganha o bloco `corrida`, e nenhum dos dois
    diz "CONCLUIDA" pela malha."""
    db = FakeDb(pipelines=_pipes(), com_085=False)
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["CARGA_A", "CARGA_B"])
        db.execucao("CARGA_A", "FALHA", inicio=datetime(2026, 8, 5, 3, 0),
                    fim=datetime(2026, 8, 5, 3, 5))
        db.execucao("CARGA_B", "SUCESSO", inicio=datetime(2026, 8, 5, 3, 30),
                    fim=datetime(2026, 8, 5, 3, 40))
        corpo = client.get("/malhas").json()
        painel = client.get("/malhas/M1/execucao").json()
    card = next(m for m in corpo["malhas"] if m["malha_name"] == "M1")

    # o MESMO sinal nos dois payloads — é o que sincroniza as duas superfícies
    assert corpo["migration_085_pendente"] is True
    assert painel["migration_085_pendente"] is True
    # ...e nenhuma das duas ganha o bloco do ciclo
    assert "corrida" not in card and "corrida" not in painel
    # o card cai no fallback DECLARADO, que fala de um MEMBRO e não da malha
    assert _estado_na_tela(card) == ("SUCESSO", "(membro mais recente)",
                                     "CARGA_B")
    # e em lugar nenhum dos dois payloads existe um "CONCLUIDA" da MALHA: o
    # único status que sobra é o de `etl_pipeline_execucao`, cujo domínio nem
    # tem essa palavra
    assert card["ultima_execucao"]["status"] in ("SUCESSO", "FALHA")
    assert all(e["status"] != "CONCLUIDA" for e in painel["execucoes"])
    # o painel continua de pé: sem a 085 ele perde o CICLO, não a tela
    assert {e["pipeline_name"] for e in painel["execucoes"]} == {"CARGA_A",
                                                                "CARGA_B"}


def test_fora_do_odate_e_contado_e_nomeavel(client, auth):
    """Decisão 66 — o incidente que originou a spec (`Carga_Vida`): membros da
    MESMA corrida rodando com datas de referência diferentes.

    O número existe no payload (`membros_fora_do_odate`) para virar banner
    âmbar nominal, e o membro continua contando no denominador: ele não foi
    dispensado, ele rodou o dia errado."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A", "B"])
        c = db.abrir_corrida("M1", odate=ODATE,
                             aberta_em=AGORA_BANCO - timedelta(hours=1),
                             membros=["A", "B"])
        db.execucao("A", "SUCESSO", inicio=AGORA_BANCO - timedelta(minutes=50),
                    fim=AGORA_BANCO - timedelta(minutes=40), corrida=c["id"])
        # B rodou VINCULADO a esta corrida, mas carimbando o ODATE de ontem
        db.execucao("B", "SUCESSO", odate=ODATE_ONTEM,
                    inicio=AGORA_BANCO - timedelta(minutes=30),
                    fim=AGORA_BANCO - timedelta(minutes=20), corrida=c["id"])
        corrida = _card(client.get("/malhas"))["corrida"]
    assert corrida["membros_fora_do_odate"] == 1
    assert corrida["membros_total"] == 2
    # a linha de outro ODATE não conta como concluída nesta corrida — o membro
    # fica pendente, que é o fato: para ESTE dia, ele não rodou
    assert corrida["membros_ok"] == 1
    assert [x["pipeline"] for x in corrida["pendentes"]] == ["B"]


def test_sem_a_085_a_lente_responde_404_e_nao_500(client, auth):
    db = FakeDb(pipelines=_pipes(), com_085=False)
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A"])
        resp = client.get("/malhas/M1/execucao?corrida=7")
    assert resp.status_code == 404


def test_malha_sem_corrida_nao_ganha_a_chave(client, auth):
    """A degradação da Decisão 41 é POR MALHA: a que tem ciclo mostra o ciclo,
    a que não tem cai no fallback — na MESMA lista."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A"])
        _monta_malha(client, "M2", ["B"])
        db.abrir_corrida("M1", odate=ODATE, aberta_em=AGORA_BANCO,
                         membros=["A"])
        db.execucao("B", "SUCESSO", inicio=AGORA_BANCO, fim=AGORA_BANCO)
        corpo = client.get("/malhas").json()
    cards = {m["malha_name"]: m for m in corpo["malhas"]}
    assert "corrida" in cards["M1"]
    assert "corrida" not in cards["M2"]
    assert cards["M2"]["ultima_execucao"]["pipeline"] == "B"
    assert "migration_085_pendente" not in corpo


# ═════════════════ os relógios: tudo do BANCO (Decisão 10) ══════════════════

def test_saude_atrasada_sai_do_relogio_do_banco(client, auth):
    """O dublê põe o banco 3h à frente do processo. Um teto vencido só pelo
    relógio do BANCO tem de ser visto; calculado em Python (3h atrás) ele não
    teria vencido, e a corrida sairia `OK` — o alarme que não toca."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A"])
        c = db.abrir_corrida("M1", odate=ODATE,
                             aberta_em=AGORA_BANCO - timedelta(hours=2),
                             teto_horas=1, membros=["A"])
        db.execucao("A", "EXECUTANDO",
                    inicio=AGORA_BANCO - timedelta(minutes=10),
                    corrida=c["id"])
        corrida = _card(client.get("/malhas"))["corrida"]
    assert corrida["status"] == "ABERTA"
    assert corrida["saude"] == "ATRASADA"


def test_saude_sem_progresso_com_vivo_parado(client, auth):
    """§9.3 — vivo que não se mexe há tempo demais é o sintoma nº 1 da execução
    órfã, a classe de defeito mais cara do produto. O limiar é múltiplo da
    quiescência e a comparação é do banco."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A"])
        c = db.abrir_corrida("M1", odate=ODATE,
                             aberta_em=AGORA_BANCO - timedelta(hours=20),
                             teto_horas=48, membros=["A"])
        db.execucao("A", "EXECUTANDO",
                    inicio=AGORA_BANCO - timedelta(hours=20), corrida=c["id"])
        corrida = _card(client.get("/malhas"))["corrida"]
    assert corrida["saude"] == "SEM_PROGRESSO"
    assert corrida["sem_sinal_min"] >= 20 * 60


def test_carga_longa_nao_vira_sem_progresso(client, auth):
    """O espelho do teste acima, e o mais importante dos dois: uma carga
    honesta de meia hora NÃO pode pintar de âmbar. Alarme falso semanal treina
    o operador a ignorar o alarme (Decisões 26/27)."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A"])
        c = db.abrir_corrida("M1", odate=ODATE,
                             aberta_em=AGORA_BANCO - timedelta(minutes=35),
                             membros=["A"])
        db.execucao("A", "EXECUTANDO",
                    inicio=AGORA_BANCO - timedelta(minutes=30), corrida=c["id"])
        corrida = _card(client.get("/malhas"))["corrida"]
    assert corrida["saude"] == "OK"


def test_apurado_em_e_decorrido_saem_do_banco(client, auth):
    """Decisão 40 + Decisão 60 — `apurado_em` é o relógio do BANCO e
    `decorrido_min` já vem subtraído pelo SERVIDOR. O front soma a ele o
    próprio delta local; se `apurado_em` viesse do processo, o desvio de 3h
    apareceria como "atualizado há -3h"."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A"])
        db.abrir_corrida("M1", odate=ODATE,
                         aberta_em=AGORA_BANCO - timedelta(minutes=90),
                         membros=["A"])
        corrida = _card(client.get("/malhas"))["corrida"]
    assert corrida["apurado_em"] == AGORA_BANCO.strftime("%Y-%m-%d %H:%M:%S")
    assert corrida["apurado_em"] != AGORA_API.strftime("%Y-%m-%d %H:%M:%S")
    assert corrida["decorrido_min"] == 90


def test_denominador_indisponivel_publica_o_ciclo_sem_contadores(client, auth):
    """Lock timeout na consulta (B) às 3h: o ESTADO do ciclo (o fato mais
    valioso do payload) continua saindo, e os contadores vêm `null`.

    `null` é "não consegui apurar", e é diferente de `0`, que a tela
    desenharia como barra vazia — uma medida que ninguém tomou."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A"])
        db.abrir_corrida("M1", odate=ODATE, aberta_em=AGORA_BANCO,
                         membros=["A"], status="FALHA")
        db.falhar_denominador = True
        corrida = _card(client.get("/malhas"))["corrida"]
    assert corrida["status"] == "FALHA"
    assert corrida["membros_total"] is None
    assert corrida["membros_travados"] is None
    assert corrida["saude"] is None
    assert corrida["pendentes"] == []


def test_contrato_do_bloco_corrida(client, auth):
    """As chaves que o front da F4 consome, congeladas.

    Este teste existe para que acrescentar campo seja barato e REMOVER campo
    seja caro: o consumidor é outra árvore de deploy (o `dist/` sobe na etapa 3
    e a `api/` na 7), e um campo que some sem aviso vira tela em branco na
    janela entre as duas."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _cenario_defeito(db, client)
        corrida = _card(client.get("/malhas"))["corrida"]
    assert set(corrida) == {
        # cabeçalho do ciclo (o mesmo de `GET /malhas/{m}/corridas`)
        "id", "malha_name", "data_referencia", "sequencia", "status",
        "aberta_em", "fechada_em", "fechada_por", "origem", "aberta_por",
        "ancora_pipeline", "modo_fechamento", "teto_em", "tentativas",
        "reaberta_em", "reaberta_por", "motivo",
        # derivados da leitura (F4)
        "saude", "membros_total", "membros_ok", "membros_vivos",
        "membros_dispensados", "membros_travados", "membros_nao_partiram",
        "membros_fora_do_odate",
        "membros_inativos", "pendentes", "ultimo_movimento_em",
        "sem_sinal_min", "decorrido_min", "apurado_em",
        # Separa "a corrida abriu com snapshot vazio" (fato: alguém olhe o
        # cadastro da malha) de "a consulta não respondeu" (tente de novo) —
        # sem ele os dois chegavam à tela iguais, de contadores em branco.
        "sem_membros",
    }
    assert set(corrida["pendentes"][0]) == {"pipeline", "classe", "desde",
                                            "faltante"}


def test_pendentes_vem_do_mais_grave_para_o_menos(client, auth):
    """O card tem espaço para UM nome e ele tem de ser o do problema mais
    grave. Em ordem alfabética, `AAA_nao_partiu` roubaria a linha de
    `ZZZ_falhou` — e o operador leria "a DAG não partiu" numa madrugada em que
    o que houve foi uma FALHA."""
    db = FakeDb(pipelines=_pipes())
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", ["A", "B", "C"])
        c = db.abrir_corrida("M1", odate=ODATE,
                             aberta_em=AGORA_BANCO - timedelta(hours=1),
                             membros=["A", "B", "C"])
        # A: sem linha (nao_partiu) · B: NAO_LIBEROU · C: FALHA
        db.execucao("B", "NAO_LIBEROU",
                    criado_em=AGORA_BANCO - timedelta(minutes=40),
                    corrida=c["id"])
        db.execucao("C", "FALHA", inicio=AGORA_BANCO - timedelta(minutes=30),
                    fim=AGORA_BANCO - timedelta(minutes=29), corrida=c["id"])
        corrida = _card(client.get("/malhas"))["corrida"]
    assert [x["classe"] for x in corrida["pendentes"]] == [
        "falhou", "nao_liberou", "nao_partiu"]
    assert corrida["pendentes"][0]["pipeline"] == "C"
