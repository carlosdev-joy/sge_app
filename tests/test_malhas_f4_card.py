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
from tests.test_malhas_f10 import _monta_malha

ODATE = date(2026, 8, 5)
ODATE_ONTEM = date(2026, 8, 4)

# Os nomes de todos os cenários numa lista só: o cadastro de pipelines é
# preparação, não o que se prova, e um `_pipes` por teste só criaria ruído.
_NOMES = (["CARGA_A", "CARGA_B", "A", "B", "C", "OK1", "OK2", "OK3", "VIVO",
           "PULA", "FALHOU", "P_FALHOU", "P_NAO_LIBEROU", "P_NAO_PARTIU",
           "P_ORFA"] + [f"P{i}" for i in range(10)])


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
    def execute(self, sql, params=()):  # noqa: C901 — dispatcher de dublê
        db = self.db
        s = " ".join(str(sql).split())
        db.sqls.append(s)
        p = tuple(params)

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
    """A saúde não espera o fechamento: com 1 falha e 8 correndo o card já é
    vermelho e já nomeia. Esperar o desfecho é perder a madrugada."""
    db = FakeDb(pipelines=_pipes())
    membros = [f"P{i}" for i in range(9)]
    with _patch(db), _patch_agora():
        _monta_malha(client, "M1", membros)
        c = db.abrir_corrida("M1", odate=ODATE,
                             aberta_em=AGORA_BANCO - timedelta(minutes=20),
                             membros=membros)
        db.execucao("P0", "FALHA", inicio=AGORA_BANCO - timedelta(minutes=15),
                    fim=AGORA_BANCO - timedelta(minutes=14), corrida=c["id"])
        for p in membros[1:]:
            db.execucao(p, "EXECUTANDO",
                        inicio=AGORA_BANCO - timedelta(minutes=5),
                        corrida=c["id"])
        corrida = _card(client.get("/malhas"))["corrida"]
    assert corrida["saude"] == "COM_FALHA"
    assert corrida["membros_vivos"] == 8
    assert [x["pipeline"] for x in corrida["pendentes"]] == ["P0"]


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

    `total = ok + vivos + dispensados + travados` é a identidade que garante
    que o travado não é pintado: se ele entrasse na barra, `3 de 6` pintaria
    5/6 do trilho e, a 1,5 m, leria-se "quase pronto"."""
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
    assert (corrida["membros_total"]
            == corrida["membros_ok"] + corrida["membros_vivos"]
            + corrida["membros_dispensados"] + corrida["membros_travados"])


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
        "membros_dispensados", "membros_travados", "membros_fora_do_odate",
        "membros_inativos", "pendentes", "ultimo_movimento_em",
        "sem_sinal_min", "decorrido_min", "apurado_em",
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
