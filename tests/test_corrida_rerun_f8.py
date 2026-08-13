"""
F8 da spec docs/spec-malha-execucao.md — o rerun e os avisos.

O que se prova aqui é a **tabela de decisão** que a F8 acrescenta, e ela é toda
de router: dada o situação do ciclo, o gesto reabre, registra reprocesso ou só
avisa. O comportamento de banco das peças que ela usa (`reabrir_corrida`,
`descartar_desfecho`, `corridas_das_linhas`) já é provado contra o dublê
interpretador de tests/test_malha_corrida.py, nas DUAS árvores — repeti-lo aqui
provaria o dublê duas vezes e a decisão nenhuma.

As três perguntas que estes testes respondem:

  1. rerun com cascata e nenhuma outra corrida aberta → **reabre**;
  2. rerun com OUTRA corrida aberta (o plantão do dia 04 reprocessando o dia 03)
     → **não reabre**, grava `MALHA_REPROCESSO` na corrida antiga, e a do dia 04
     não é tocada — o desenho não passa por cima do próprio índice único;
  3. rerun sem dependente aposentado (`rowcount = 0`) → **não toca em corrida
     nenhuma**: reabrir um ciclo por um gesto que não vai fazer nada rodar de
     novo o deixaria aberto até o teto, bloqueando o disparo por nada.

A seção 7 fecha o que as seções 1–3 **não podem** fechar. Nelas o registro é
roteirizado (`reabre=False` é uma decisão do dublê), e a regra da honestidade da
casa é explícita: guarda que mora no `WHERE` só é aplicada pelo dublê se o SQL
emitido a contiver. Lá isso é aceitável porque o objeto é a decisão do router; o
que ficava sem dono era a JUNÇÃO — o gesto inteiro, com o módulo de verdade, o
índice sendo avaliado e o `commit` no lugar certo. É o que a seção 7 monta:
`_aplicar_cascata` sobre `api/services/malha_corrida.py` REAL e sobre o dublê
INTERPRETADOR de `test_malha_corrida.py`, que executa `ux_malha_exec_aberta`.
Quem decide que a corrida do dia 03 não reabre passa a ser o índice.
"""
from __future__ import annotations

from datetime import date

import pytest

ODATE = date(2026, 8, 4)
ODATE_ONTEM = date(2026, 8, 3)


@pytest.fixture(scope="module")
def E():
    import routers.execucoes as _e
    return _e


def _corrida(cid=12, malha="M1", status="CONCLUIDA", data=ODATE, tentativas=1):
    return {"id": cid, "malha_name": malha, "status": status,
            "data_referencia": data, "tentativas": tentativas,
            "sequencia": 1, "aberta_em": None, "fechada_em": None}


class _McFalso:
    """O módulo da corrida com as respostas roteirizadas — e o registro do que
    foi PEDIDO a ele. A decisão do router é o objeto do teste; o SQL não."""

    STATUS_ABERTA = "ABERTA"
    REABREM = ("CONCLUIDA", "FALHA")

    def __init__(self, corridas, *, reabre=True, aberta=None, tem_085=True):
        self._corridas = corridas
        self._reabre = reabre
        self._aberta = aberta
        self._tem_085 = tem_085
        self.reaberturas: list = []
        self.eventos: list = []

    def tabela_085_presente(self, cur):
        return self._tem_085

    def corridas_das_linhas(self, cur, pipelines, data_ref):
        return [c for c in self._corridas if c["data_referencia"] == data_ref]

    def reabrir_corrida(self, cur, corrida_id, quem, motivo=None):
        self.reaberturas.append((corrida_id, quem, motivo))
        if not self._reabre:
            return False
        for c in self._corridas:
            if c["id"] == corrida_id:
                c["status"] = "ABERTA"
                c["tentativas"] = int(c["tentativas"]) + 1
        return True

    def corrida(self, cur, corrida_id):
        for c in self._corridas:
            if c["id"] == corrida_id:
                return c
        return None

    def corrida_aberta(self, cur, malha):
        return self._aberta


@pytest.fixture
def cenario(E, monkeypatch):
    """Monta o router com o módulo falso, o portão do §11.1 ABERTO e o
    escritor de evento capturado. Devolve uma função que roda o efeito."""
    def montar(mc_falso, *, portao=(True, None), data_ref=ODATE):
        monkeypatch.setattr(E, "mc", mc_falso)
        monkeypatch.setattr(E, "_corrida_operavel", lambda cur, malha: portao)
        import routers.malhas as M
        monkeypatch.setattr(
            M, "_evento_da_corrida",
            lambda cur, c, tipo, detalhe, notificar=True:
                mc_falso.eventos.append((c["id"], tipo, detalhe)) or True)
        saida = {"avisos": [], "corridas_reabertas": [],
                 "corridas_com_reprocesso": []}
        E._efeito_na_corrida(object(), "CARGA_A", ["CARGA_B"], data_ref,
                             "C123456", saida)
        return saida
    return montar


# ═══════════════ 1. reabre quando não há outra corrida aberta ═══════════════

def test_rerun_com_cascata_reabre_a_corrida_do_dia(cenario):
    """O aceite da fase: corrida `CONCLUIDA`, ninguém mais aberto, rerun com
    cascata → volta a `ABERTA` com `tentativas = 2`."""
    mc = _McFalso([_corrida(status="CONCLUIDA")])
    saida = cenario(mc)

    assert [r[0] for r in mc.reaberturas] == [12]
    assert mc.reaberturas[0][1] == "rerun:C123456"
    assert saida["corridas_reabertas"] == [
        {"malha": "M1", "data_referencia": "2026-08-04", "tentativas": 2}]
    assert saida["corridas_com_reprocesso"] == []
    assert mc.eventos == []            # reabriu: não é reprocesso fora do ciclo
    assert any("voltou a ABERTA" in a for a in saida["avisos"])
    # Decisão 74: a corrida se chama pela DATA. `#12` é chave de banco, e numa
    # malha diária lê-se como "12ª tentativa hoje".
    assert all("#" not in a for a in saida["avisos"])


@pytest.mark.parametrize("status", ["CONCLUIDA", "FALHA"])
def test_reabre_tanto_a_concluida_quanto_a_que_falhou(cenario, status):
    mc = _McFalso([_corrida(status=status)])
    assert cenario(mc)["corridas_reabertas"] != []


# ═════════ 2. NÃO reabre havendo outra aberta — e grava REPROCESSO ══════════

def test_com_outra_corrida_aberta_grava_reprocesso_e_nao_reabre(cenario):
    """§6.9/#3 — o cenário de plantão: a corrida do dia 03 concluiu, a do dia 04
    está aberta, e o operador reprocessa um membro do dia 03.

    Reabrir a #12 zeraria `fechada_em` com a #13 aberta e violaria
    `ux_malha_exec_aberta` DENTRO da transação que carimba `substituida_em`: ou
    o rerun inteiro rolaria de volta, ou a corrida não reabriria e ninguém
    perceberia. A regra é explícita — não reabre, e o fato fica registrado na
    corrida antiga.
    """
    velha = _corrida(cid=12, status="CONCLUIDA", data=ODATE_ONTEM)
    nova = _corrida(cid=13, status="ABERTA", data=ODATE)
    mc = _McFalso([velha, nova], reabre=False, aberta=nova)

    # O lote do rerun é do dia 03 — e é a corrida DAQUELE dia que entra em cena,
    # porque quem responde "de que ciclo era esta linha" é o vínculo da linha.
    saida = cenario(mc, data_ref=ODATE_ONTEM)

    assert saida["corridas_reabertas"] == []
    assert [e[1] for e in mc.eventos] == ["MALHA_REPROCESSO"]
    assert mc.eventos[0][0] == 12                    # na corrida ANTIGA
    assert "outro ciclo desta malha em andamento" in mc.eventos[0][2]
    assert saida["corridas_com_reprocesso"] == [
        {"malha": "M1", "data_referencia": "2026-08-03",
         "status": "CONCLUIDA"}]
    # E a do dia 04 não é tocada: nem status, nem tentativas, nem evento.
    assert nova["status"] == "ABERTA" and nova["tentativas"] == 1
    assert all(e[0] != 13 for e in mc.eventos)


def test_fim_de_linha_tambem_registra_reprocesso_com_outra_frase(cenario):
    """`EXPIRADA`/`ABORTADA`/`CANCELADA` não voltam (§6.1). A causa é OUTRA e o
    conserto também: "há outro ciclo em voo" é temporário e esperado; "este
    ciclo é fim de linha" é definitivo. Uma frase só para os dois casos manda o
    operador procurar o ciclo errado."""
    mc = _McFalso([_corrida(status="EXPIRADA")], reabre=False, aberta=None)
    saida = cenario(mc)
    assert [e[1] for e in mc.eventos] == ["MALHA_REPROCESSO"]
    assert "encerrado como EXPIRADA" in mc.eventos[0][2]
    assert any("não volta" in a for a in saida["avisos"])


# ═══════════ 3. corrida ABERTA: nada a reabrir, e a frase da D65 ════════════

def test_corrida_em_andamento_so_avisa_que_a_reexecucao_entra_nela(cenario):
    """Decisão 65 — o gesto mais delicado do modelo não pode ser um clique de
    3h no escuro: a reexecução ENTRA no ciclo em voo, e o relógio de fechamento
    dele **não** reinicia por causa dela."""
    mc = _McFalso([_corrida(status="ABERTA")])
    saida = cenario(mc)
    assert mc.reaberturas == [] and mc.eventos == []
    assert saida["corridas_reabertas"] == []
    assert any("NÃO reinicia" in a for a in saida["avisos"])


# ═══════════════════ 4. o portão do §11.1 e a degradação ════════════════════

def test_interruptor_desligado_deixa_o_rerun_exatamente_como_antes(cenario):
    """Reabrir corrida que o `dags/` deployado não sabe fechar é o mesmo estrago
    de ABRIR uma: ela ficaria aberta até o teto bloqueando o disparo. Com o
    portão fechado o rerun responde como antes desta fase — e isso inclui o
    estado de hoje no dev, com `malha_corrida_ativa = 0`."""
    mc = _McFalso([_corrida(status="CONCLUIDA")])
    saida = cenario(mc, portao=(False, "malha_corrida_desligada"))
    assert mc.reaberturas == [] and mc.eventos == []
    assert saida["avisos"] == []


@pytest.mark.parametrize("motivo,trecho", [
    ("migration_085_pendente", "migration 085"),
    ("guardia_sem_heartbeat", "guardiã está sem sinal"),
    ("dags_desatualizado", "deploy de dags/ pendente"),
    ("capacidade_dags_desconhecida", "não foi possível confirmar"),
])
def test_as_outras_recusas_do_portao_SAO_ditas_ao_operador(cenario, motivo,
                                                           trecho):
    """O contraponto do teste acima, e a distinção que ele guarda.

    O interruptor em `0` significa "a feature não existe neste ambiente" —
    anunciar em todo rerun o que ela deixou de fazer é ruído. As outras três
    recusas são ANOMALIAS DE AMBIENTE: a 085 que ninguém aplicou, o `dags/` que
    ficou para trás no deploy (a etapa 5 é padrão-NÃO, a 7 é automática — a
    célula mais provável da matriz §11.1), a guardiã sem heartbeat. Cada uma
    tem conserto, nenhuma aparece em outro lugar da tela, e calar sobre elas
    entrega ao operador um rerun VERDE com o ciclo intacto em FALHA.

    Foi exatamente esse silêncio que fez o caso `Carga_Vida` (2026-08-12) só
    ser explicável com consulta ao banco.
    """
    mc = _McFalso([_corrida(status="FALHA")])
    saida = cenario(mc, portao=(False, motivo))
    assert mc.reaberturas == [] and mc.eventos == []
    assert len(saida["avisos"]) == 1, "a recusa do portão ficou muda"
    aviso = saida["avisos"][0]
    assert trecho in aviso
    assert "o reprocesso roda, mas o ciclo continua como está" in aviso


def test_sem_a_085_o_efeito_nem_e_tentado(cenario):
    mc = _McFalso([_corrida()], tem_085=False)
    saida = cenario(mc)
    assert mc.reaberturas == [] and saida["avisos"] == []


def test_falha_no_meio_vira_aviso_e_nunca_derruba_o_rerun(E, monkeypatch):
    """O clear JÁ aconteceu no Airflow quando esta função roda. Levantar aqui
    transformaria um reprocesso bem-sucedido em 500 na tela, com as tasks
    limpas do mesmo jeito."""
    class _Explode(_McFalso):
        def reabrir_corrida(self, *a, **kw):
            raise RuntimeError("deadlock (teste)")

    mc = _Explode([_corrida(status="CONCLUIDA")])
    monkeypatch.setattr(E, "mc", mc)
    monkeypatch.setattr(E, "_corrida_operavel", lambda cur, malha: (True, None))
    saida = {"avisos": [], "corridas_reabertas": [],
             "corridas_com_reprocesso": []}
    E._efeito_na_corrida(object(), "CARGA_A", [], ODATE, "C1", saida)
    assert saida["corridas_reabertas"] == []
    assert any("não pôde ser atualizado" in a for a in saida["avisos"])


# ══════ 4b. o gatilho: sem corrida APOSENTADA, nada de ciclo tocado ═════════

class _ConnFalsa:
    def cursor(self):
        return self

    def execute(self, *a, **kw):
        self.rowcount = 0

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


@pytest.mark.parametrize("aposentadas,esperado", [(0, False), (2, True)])
def test_o_efeito_no_ciclo_so_roda_com_corrida_aposentada(E, monkeypatch,
                                                          aposentadas,
                                                          esperado):
    """O gatilho é `marcar_substituidas` com `rowcount > 0`, e não "o usuário
    pediu cascata".

    Sem dependente aposentado nada vai rodar de novo — reabrir o ciclo ali
    deixaria uma corrida ABERTA que ninguém vai fazer avançar, e ela bloquearia
    o disparo da malha até o teto (24h por padrão). O aceite da fase diz isso
    com todas as letras: "rerun de pipeline SEM dependentes aposentados → não
    reabre nada".
    """
    chamou: list = []
    monkeypatch.setattr(E, "get_db_conn", lambda: _ConnFalsa())
    monkeypatch.setattr(E.deps_svc, "tabela_067", lambda cur: True)
    monkeypatch.setattr(E.rerun_svc, "reviver_corrida", lambda *a, **kw: 1)
    monkeypatch.setattr(E.rerun_svc, "aposentar_irmas", lambda *a, **kw: 0)
    monkeypatch.setattr(E.rerun_svc, "afetados", lambda cur, p, d: {
        "com_corrida": ["CARGA_B"], "cascata_indisponivel": False,
        "truncado": False})
    monkeypatch.setattr(E.rerun_svc, "marcar_substituidas",
                        lambda *a, **kw: aposentadas)
    monkeypatch.setattr(E.rerun_svc, "registrar_auditoria",
                        lambda *a, **kw: True)
    monkeypatch.setattr(E, "_efeito_na_corrida",
                        lambda *a, **kw: chamou.append(True))

    saida = E._aplicar_cascata("CARGA_A", ODATE, "etapa_x", "run_1",
                               "C123456", True, 1)
    assert bool(chamou) is esperado
    assert saida["corridas_substituidas"] == aposentadas
    # e as chaves novas existem SEMPRE, mesmo vazias — o front não precisa
    # descobrir se a API é da F8 por tentativa e erro.
    assert saida["corridas_reabertas"] == []
    assert saida["corridas_com_reprocesso"] == []


# ═════════════ 5. a prévia — a frase ANTES do clique (Decisão 65) ═══════════

@pytest.fixture
def previa(E, monkeypatch):
    """A prévia com o portão do §11.1 ABERTO por padrão — o mesmo default do
    `cenario`, e pelo mesmo motivo: o objeto do teste é o leitura do ciclo, não
    a matriz de deploy. Quem quer o portão FECHADO passa `portao=`."""
    def montar(mc_falso, *, portao=(True, None), pipeline="CARGA_A"):
        monkeypatch.setattr(E, "mc", mc_falso)
        monkeypatch.setattr(E, "_corrida_operavel", lambda cur, malha: portao)
        return E._previa_da_corrida(object(), pipeline, ODATE)
    return montar


@pytest.mark.parametrize("status,aberta,efeito,sem_cascata", [
    ("ABERTA",    None, "em_andamento", "em_andamento"),
    ("CONCLUIDA", None, "reabre", "nao_toca"),
    ("FALHA",     None, "reabre", "nao_toca"),
    ("CONCLUIDA", "outra", "fora_do_ciclo", "nao_toca"),
    ("EXPIRADA",  None, "fora_do_ciclo", "nao_toca"),
])
def test_previa_do_ciclo_diz_o_efeito_certo(previa, status, aberta, efeito,
                                            sem_cascata):
    outra = _corrida(cid=99, status="ABERTA") if aberta else None
    p = previa(_McFalso([_corrida(status=status)], aberta=outra))
    assert p["efeito"] == efeito
    assert p["malha"] == "M1" and p["data_referencia"] == "2026-08-04"
    assert p["mensagem"]
    # ⚠️ A SEGUNDA leitura do mesmo ciclo. `_efeito_na_corrida` só roda dentro
    # de `if cascata:` e com dependente aposentado — e a opção que nasce marcada
    # no modal é "apenas este pipeline". Sem este par, a tela prometeria
    # "volta a ficar ABERTO" justamente na opção em que a reabertura nunca
    # acontece.
    assert p["efeito_sem_cascata"] == sem_cascata
    assert p["mensagem_sem_cascata"]
    if efeito == "reabre":
        assert "NÃO volta a abrir" in p["mensagem_sem_cascata"]


def test_previa_sem_corrida_nenhuma_e_None_e_o_modal_fica_como_antes(previa):
    """"Sem certeza, sem frase" — pipeline fora de malha, banco sem a 085 e
    leitura indisponível dão a MESMA resposta, e o modal degrada para o que era
    antes desta fase."""
    assert previa(_McFalso([])) is None
    assert previa(_McFalso([_corrida()], tem_085=False)) is None

    class _Explode(_McFalso):
        def corridas_das_linhas(self, *a, **kw):
            raise RuntimeError("banco fora do ar (teste)")
    assert previa(_Explode([_corrida()])) is None


def test_previa_calada_quando_a_API_nao_pode_OPERAR_a_corrida(previa):
    """O portão do §11.1 governa a PRÉVIA, não só o efeito.

    Sem isto o modal dizia "este ciclo volta a ficar ABERTO" e
    `_efeito_na_corrida` pulava o ciclo em silêncio (ele só loga) — e o estado
    em que isso acontece é o de HOJE: `malha_corrida_ativa = 0`. Também é o
    estado de todo rollback (o interruptor existe para ser desligado COM
    corridas no banco), do `dags/` deployado sem a capacidade e da guardiã sem
    heartbeat. A promessa e o gesto têm de morrer na mesma condição."""
    for portao in [(False, "interruptor_desligado"),
                   (False, "dags_desatualizado"),
                   (False, "guardia_sem_heartbeat")]:
        assert previa(_McFalso([_corrida(status="CONCLUIDA")]),
                      portao=portao) is None


# ══════════ 6. o rótulo humano da corrida (Decisão 74) ══════════════════════

def test_a_frase_chama_a_corrida_pela_DATA_nunca_pelo_id(E):
    frase = E._frase_da_corrida(_corrida(), "está em andamento")
    assert "ciclo de 2026-08-04" in frase and "M1" in frase
    assert "#" not in frase


# ══ 7. o gesto INTEIRO: módulo real, índice avaliado, commit no lugar ═══════

class _ConnEspia:
    """A conexão do rerun, com a ORDEM dos gestos registrada.

    É ela que prova a exigência central do §6.9/#3, que nenhum teste de unidade
    alcança: o efeito sobre o ciclo acontece **antes** do `commit`, na MESMA
    transação que carimbou `substituida_em`. Se ele escorregar para depois, o
    rerun passa a ter dois commits — e a spec diz o que acontece então: ou o
    2601 rola o rerun inteiro de volta, ou a corrida não reabre e ninguém
    percebe.
    """

    def __init__(self, db, ordem):
        self.db, self.ordem = db, ordem
        self._cur = db.cursor()
        executar = self._cur.execute

        def espiao(sql, params=()):
            s = " ".join(str(sql).split())
            if s.startswith("UPDATE me SET me.status = 'ABERTA'"):
                self.ordem.append("reabrir")
            elif s.startswith("DELETE FROM dbo.etl_dependencia_evento"):
                self.ordem.append("descartar")
            return executar(sql, params)

        self._cur.execute = espiao

    def cursor(self):
        return self._cur

    def commit(self):
        self.ordem.append("commit")
        self.db.commit()

    def rollback(self):
        self.ordem.append("rollback")
        self.db.rollback()


@pytest.fixture
def gesto_inteiro(E, monkeypatch):
    """`_aplicar_cascata` de verdade sobre o dublê INTERPRETADOR da 085.

    O `mc` aqui **não é dublê**: é `api/services/malha_corrida.py`, e o
    `ux_malha_exec_aberta` é avaliado pelo banco em miniatura de
    `test_malha_corrida.py` — que levanta o 2601 de verdade se o `NOT EXISTS`
    sumir do `SQL_REABRIR`. Ninguém neste arquivo decide se a corrida reabre;
    o modelo decide.

    O que segue dublado, e por que isso não devolve o problema pela janela:
      • `rerun_svc` — o carimbo de `substituida_em` é da F4, tem suíte própria,
        e o seu SQL não está no contrato deste dublê. O que importa aqui é o
        `rowcount` que ele devolve, que é o GATILHO da fase;
      • o portão do §11.1 — lê heartbeat e o que está no disco do `dags/`;
        tem os seus testes na seção 4;
      • `_evento_da_corrida` — statement de `routers.malhas` (F3), capturado
        para que o teste veja O QUE foi gravado e em QUAL corrida.
    """
    from services import malha_corrida as mca
    from tests.test_malha_corrida import banco as construir_banco

    def montar(*, ciclos, execucoes, oficial, data_ref, aposentadas=1,
               alvos=("PIPE_B",), eventos_na_fila=()):
        db = construir_banco(execucoes=list(execucoes))
        db.eventos = list(eventos_na_fila)
        cur = db.cursor()
        for malha, odate, desfecho in ciclos:
            c = mca.abrir_corrida(cur, malha, odate, "manual")
            if desfecho is not None:
                mca.fechar_corrida(cur, c["id"], desfecho, "guardia")

        ordem: list = []
        eventos: list = []
        conn = _ConnEspia(db, ordem)
        monkeypatch.setattr(E, "get_db_conn", lambda: conn)
        monkeypatch.setattr(E, "_corrida_operavel", lambda cur, m: (True, None))
        monkeypatch.setattr(E.deps_svc, "tabela_067", lambda cur: True)
        monkeypatch.setattr(E.rerun_svc, "reviver_corrida", lambda *a, **k: 1)
        monkeypatch.setattr(E.rerun_svc, "aposentar_irmas", lambda *a, **k: 0)
        monkeypatch.setattr(E.rerun_svc, "afetados", lambda cur, p, d: {
            "com_corrida": list(alvos), "cascata_indisponivel": False,
            "truncado": False})
        monkeypatch.setattr(E.rerun_svc, "marcar_substituidas",
                            lambda *a, **k: aposentadas)
        monkeypatch.setattr(E.rerun_svc, "registrar_auditoria",
                            lambda *a, **k: True)
        import routers.malhas as M
        monkeypatch.setattr(
            M, "_evento_da_corrida",
            lambda cur, c, tipo, detalhe, notificar=True:
                eventos.append((c["id"], tipo, detalhe)) or True)

        saida = E._aplicar_cascata(oficial, data_ref, "etapa_x", "run_1",
                                   "C123456", True, 1)
        return {"db": db, "saida": saida, "ordem": ordem, "eventos": eventos,
                "mc": mca, "cur": cur}
    return montar


def test_a_reabertura_e_o_descarte_acontecem_ANTES_do_commit_do_rerun(
        gesto_inteiro):
    """§6.9/#3 — "na mesma transação que carimba `substituida_em`" é requisito,
    não estilo.

    A ordem observada é a prova: reabrir, descartar, e só então commitar. Com o
    efeito depois do `commit`, o rerun teria duas transações — e a spec descreve
    os dois desfechos disso, ambos ruins: um 2601 que rola o rerun inteiro de
    volta, ou uma corrida que não reabre sem ninguém perceber.

    E o descarte não é um segundo gesto que alguém possa esquecer de pedir: ele
    sai junto, porque reabrir sem descartar produz uma corrida que roda de novo
    e **conclui em silêncio**.
    """
    r = gesto_inteiro(
        ciclos=[("M1", ODATE, "CONCLUIDA")],
        execucoes=[{"pipeline_name": "PIPE_A", "data_referencia": ODATE,
                    "execution_id": "run_1", "malha_execucao_id": 1},
                   {"pipeline_name": "PIPE_B", "data_referencia": ODATE,
                    "execution_id": "run_2", "malha_execucao_id": 1}],
        eventos_na_fila=[
            {"pipeline_name": "#corrida:1", "tipo": "MALHA_CONCLUIDA",
             "data_referencia": ODATE, "malha_execucao_id": 1},
            # A linha do lado ERRADO da guarda de marcador: tipo de desfecho,
            # mas carimbada num PIPELINE. É ela que exercita o `LEFT(...)` do
            # `SQL_DESCARTAR_DESFECHO` desta árvore — sem uma linha assim, o
            # `tipo IN (...)` sozinho já barraria tudo e apagar a guarda não
            # pintaria nada de vermelho.
            {"pipeline_name": "PIPE_A", "tipo": "MALHA_ATRASADA",
             "data_referencia": ODATE, "malha_execucao_id": 1}],
        oficial="PIPE_A", data_ref=ODATE)

    assert r["ordem"] == ["reabrir", "descartar", "commit"]
    assert r["saida"]["corridas_reabertas"] == [
        {"malha": "M1", "data_referencia": "2026-08-04", "tentativas": 2}]
    # O estado do modelo, lido de volta pelo módulo de verdade.
    reaberta = r["mc"].corrida(r["cur"], 1)
    assert reaberta["status"] == "ABERTA" and reaberta["tentativas"] == 2
    # A chave da tentativa 2 ficou livre — é isto que faz a segunda
    # MALHA_CONCLUIDA do dia existir (o efeito no índice está provado ao vivo
    # em tests/test_malha_corrida_f8_vivo.py) — e o evento do MEMBRO ficou.
    assert [(e["pipeline_name"], e["tipo"]) for e in r["db"].eventos] == [
        ("PIPE_A", "MALHA_ATRASADA")]


def test_reprocessar_o_dia_03_com_o_04_aberto_conclui_sem_erro_e_nao_toca_no_04(
        gesto_inteiro):
    """O aceite que existe para provar que o desenho não passa por cima do
    próprio índice — e aqui quem recusa a reabertura é o índice, não o roteiro
    do dublê.

    Cenário de plantão: a corrida do dia 03 concluiu, a do dia 04 está aberta, e
    o operador reprocessa um membro do dia 03. Os quatro fatos do aceite, nesta
    ordem de importância:

      1. **o rerun conclui sem erro** — `commit`, e nenhum aviso de pós-clear
         parcial. Se o `NOT EXISTS` sumir do `SQL_REABRIR`, o dublê levanta o
         2601 real e este teste fica vermelho;
      2. a corrida do dia 03 **não** reabre — segue `CONCLUIDA`, `tentativas`
         não anda;
      3. `MALHA_REPROCESSO` é gravado **na corrida antiga**, dizendo a causa
         certa (há outro ciclo em voo — temporário — e não "fim de linha", que é
         definitivo e mandaria o operador procurar outra coisa);
      4. a do dia 04 não é afetada em nada.
    """
    r = gesto_inteiro(
        ciclos=[("M1", ODATE_ONTEM, "CONCLUIDA"), ("M1", ODATE, None)],
        execucoes=[{"pipeline_name": "PIPE_A",
                    "data_referencia": ODATE_ONTEM,
                    "execution_id": "run_1", "malha_execucao_id": 1},
                   {"pipeline_name": "PIPE_B",
                    "data_referencia": ODATE_ONTEM,
                    "execution_id": "run_2", "malha_execucao_id": 1}],
        oficial="PIPE_A", data_ref=ODATE_ONTEM)
    mc, cur = r["mc"], r["cur"]

    # 1. o rerun conclui — e sem o aviso que denuncia transação rolada.
    assert "commit" in r["ordem"] and "rollback" not in r["ordem"]
    assert not [a for a in r["saida"]["avisos"] if "pós-clear" in a]
    assert not [a for a in r["saida"]["avisos"] if "não pôde ser atualizado" in a]

    # 2. a do dia 03 não voltou.
    velha = mc.corrida(cur, 1)
    assert velha["status"] == "CONCLUIDA" and velha["tentativas"] == 1
    assert r["saida"]["corridas_reabertas"] == []

    # 3. o reprocesso ficou registrado na corrida ANTIGA, com a causa certa.
    assert [(e[0], e[1]) for e in r["eventos"]] == [(1, "MALHA_REPROCESSO")]
    assert "outro ciclo desta malha em andamento" in r["eventos"][0][2]
    assert r["saida"]["corridas_com_reprocesso"] == [
        {"malha": "M1", "data_referencia": "2026-08-03",
         "status": "CONCLUIDA"}]

    # 4. a do dia 04 saiu ilesa.
    nova = mc.corrida(cur, 2)
    assert nova["status"] == "ABERTA" and nova["tentativas"] == 1
    assert nova["fechada_em"] is None and nova["reaberta_em"] is None


def test_sem_dependente_aposentado_a_corrida_fica_INTOCADA(gesto_inteiro):
    """O aceite "rerun de pipeline SEM dependentes aposentados → não reabre
    nada", conferido no ESTADO e não na chamada.

    O teste irmão da seção 4b prova o gatilho (`_efeito_na_corrida` nem é
    chamado). Este prova a consequência: a corrida continua `CONCLUIDA`, com uma
    tentativa só, e a fila de alerta dela intacta. São coisas diferentes — um
    dia alguém pode mover a decisão para dentro do efeito, e aí o teste do
    gatilho passaria a proteger uma linha que não decide mais nada.
    """
    r = gesto_inteiro(
        ciclos=[("M1", ODATE, "CONCLUIDA")],
        execucoes=[{"pipeline_name": "PIPE_A", "data_referencia": ODATE,
                    "execution_id": "run_1", "malha_execucao_id": 1}],
        eventos_na_fila=[{"pipeline_name": "#corrida:1", "tipo":
                          "MALHA_CONCLUIDA", "data_referencia": ODATE,
                          "malha_execucao_id": 1}],
        oficial="PIPE_A", data_ref=ODATE, aposentadas=0)

    assert r["ordem"] == ["commit"]
    parada = r["mc"].corrida(r["cur"], 1)
    assert parada["status"] == "CONCLUIDA" and parada["tentativas"] == 1
    assert len(r["db"].eventos) == 1        # nada foi descartado
    assert r["eventos"] == []               # nem MALHA_REPROCESSO
    assert r["saida"]["corridas_reabertas"] == []
    assert r["saida"]["corridas_com_reprocesso"] == []
