"""
F8 da spec docs/spec-malha-execucao.md — o rerun e os avisos.

O que se prova aqui é a **tabela de decisão** que a F8 acrescenta, e ela é toda
de router: dada a situação do ciclo, o gesto reabre, registra reprocesso ou só
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

@pytest.mark.parametrize("status,aberta,efeito", [
    ("ABERTA",    None, "em_andamento"),
    ("CONCLUIDA", None, "reabre"),
    ("FALHA",     None, "reabre"),
    ("CONCLUIDA", "outra", "fora_do_ciclo"),
    ("EXPIRADA",  None, "fora_do_ciclo"),
])
def test_previa_do_ciclo_diz_o_efeito_certo(E, monkeypatch, status, aberta,
                                            efeito):
    outra = _corrida(cid=99, status="ABERTA") if aberta else None
    mc = _McFalso([_corrida(status=status)], aberta=outra)
    monkeypatch.setattr(E, "mc", mc)
    previa = E._previa_da_corrida(object(), "CARGA_A", ODATE)
    assert previa["efeito"] == efeito
    assert previa["malha"] == "M1" and previa["data_referencia"] == "2026-08-04"
    assert previa["mensagem"]


def test_previa_sem_corrida_nenhuma_e_None_e_o_modal_fica_como_antes(E,
                                                                    monkeypatch):
    """"Sem certeza, sem frase" — pipeline fora de malha, banco sem a 085 e
    leitura indisponível dão a MESMA resposta, e o modal degrada para o que era
    antes desta fase."""
    monkeypatch.setattr(E, "mc", _McFalso([]))
    assert E._previa_da_corrida(object(), "CARGA_A", ODATE) is None
    monkeypatch.setattr(E, "mc", _McFalso([_corrida()], tem_085=False))
    assert E._previa_da_corrida(object(), "CARGA_A", ODATE) is None

    class _Explode(_McFalso):
        def corridas_das_linhas(self, *a, **kw):
            raise RuntimeError("banco fora do ar (teste)")
    monkeypatch.setattr(E, "mc", _Explode([_corrida()]))
    assert E._previa_da_corrida(object(), "CARGA_A", ODATE) is None


# ══════════ 6. o rótulo humano da corrida (Decisão 74) ══════════════════════

def test_a_frase_chama_a_corrida_pela_DATA_nunca_pelo_id(E):
    frase = E._frase_da_corrida(_corrida(), "está em andamento")
    assert "corrida de 2026-08-04" in frase and "M1" in frase
    assert "#" not in frase
