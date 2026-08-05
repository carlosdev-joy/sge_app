"""
F2 da corrida de malha — as responsabilidades novas da guardiã
(`dags/etl_dependencia_guardia.py`; spec docs/spec-malha-execucao.md §6, §7,
§10/F2 e §11).

Arquivo PRÓPRIO, e não mais 300 linhas dentro de
tests/test_dependencia_guardia_dag.py, por dois motivos: o de lá é a suíte da
F4/F5 (o ciclo antigo, cinco responsabilidades) e a fronteira entre "o que já
funcionava" e "o que a corrida trouxe" é a informação mais útil quando um dos
dois quebrar; e a fase inteira vive atrás de um interruptor — os cenários daqui
precisam ligá-lo, e os de lá precisam que ele fique desligado.

O molde é o de lá, reusado por IMPORT (precedente test_malha_corrida_paridade,
que importa o dublê de test_malha_corrida em vez de escrever o seu): mesma DAG
carregada com Airflow stubado, mesmo `_mundo` para as perguntas antigas, e um
`_corrida` novo para as perguntas do módulo `utils/malha_corrida.py`. Um dublê
próprio provaria a paridade entre dois dublês.

O QUE ESTA SUÍTE PROTEGE — cada bloco nomeia o defeito que evita:

  1. **o interruptor** — com `malha_corrida_ativa = 0` nada abre, nada fecha e
     o log não ganha UMA linha. É critério de aceite literal da fase, e é o
     único gesto de rollback que não exige reverter merge às 3h;
  2. **as portas 2 e 3** — a raiz assinada pelo Início abre; a raiz sem
     predecessor interno abre onde não há Início; `aberta_em` RECUA para a
     linha âncora e o ODATE é o canônico da malha, nunca o do membro;
  3. **a Decisão 17** — malha com Início não abre pela porta implícita, e a
     linha que rodou sozinha carimba o porquê nela mesma;
  4. **a Decisão 15** — corrida aberta de outro ODATE RECUSA, nunca adere em
     silêncio: adesão calada é o incidente `Carga_Vida` por dentro do
     mecanismo criado para matá-lo;
  5. **os sete desfechos** — com ênfase nos três que a spec trata como aceite:
     vivo segura a corrida, FALHA não emite `MALHA_CONCLUIDA` (teste de
     AUSÊNCIA), sábado é `SEM_TRABALHO` imediato;
  6. **`MALHA_FALHOU` na DETECÇÃO** — e uma vez só em 200 ciclos;
  7. **as três guardas da quiescência**;
  8. **a degradação** — sem a 085, UMA linha por ciclo e o ciclo inteiro segue.
     Uma exceção aqui derrubaria a guardiã, que é quem faz o push de
     dependências de toda a casa;
  9. **nenhuma conta de tempo em Python** — todo carimbo e toda comparação
     saem do banco (Decisão 10). No dev o SQL Server está ~3h à frente do
     worker: o teste é sintático porque o defeito é sintático.
"""
from __future__ import annotations

import ast
import importlib.util
import inspect
import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

# `GUARDIA` já vem carregado com os stubs de Airflow; `_mundo` zera as cinco
# responsabilidades antigas. Importar (em vez de recarregar) garante que os
# dois arquivos exercitam O MESMO objeto de módulo.
from tests.test_dependencia_guardia_dag import (  # noqa: E402
    AGORA, GUARDIA, HOJE, _cfg, _mundo)

_ROOT = Path(__file__).parent.parent
ODATE = HOJE
ONTEM = HOJE - timedelta(days=1)

# O relógio do BANCO, deslocado do relógio do Python de propósito: é o caso
# MEDIDO no dev (SQL Server ~3h à frente do worker). Qualquer aritmética de
# tempo feita em Python apareceria aqui como resultado errado.
AGORA_BANCO = AGORA + timedelta(hours=3)
MOMENTO_ANCORA = datetime(2026, 8, 3, 1, 10)


def _corrida(monkeypatch, **sobrescreve):
    """Zera o módulo da corrida e liga o interruptor.

    Os defaults descrevem o mundo mais comum: interruptor LIGADO, 085 presente,
    nenhuma malha, nenhuma corrida aberta, nenhum nó retido. Cada cenário
    sobrescreve só o que lhe interessa — o resto continua sendo o silêncio.
    """
    base = {
        "limpar_cache": lambda: None,
        "corrida_ativa": lambda conn: True,
        "tabela_085_presente": lambda conn: True,
        "teto_horas_da_malha": lambda conn, m: 24,
        "quiescencia_minutos": lambda conn: 15,
        "carencia_partida_min": lambda conn: 15,
        "odate_da_abertura": lambda conn, m, momento: ODATE,
        "raizes_da_malha": lambda conn, m: [],
        "partidas_a_cobrir": lambda conn, m, pipes, datas, teto: [],
        "corrida_aberta": lambda conn, m: None,
        "corridas_abertas": lambda conn: [],
        "corrida_da_data": lambda conn, m, d: None,
        "abrir_corrida": lambda conn, *a, **k: None,
        "congelar_snapshot": lambda conn, cid, m, conta_para_fim=None: 0,
        "vincular_execucao": lambda conn, p, d, e, cid: True,
        "carimbar_motivo": lambda conn, p, d, e, chave, texto: True,
        "estado": lambda conn, c, dispensa_sem_linha=None: _estado(),
        "relogios": lambda conn, c, car, qui: {"teto_vencido": False,
                                               "partida_vencida": False,
                                               "quiescente": True},
        "aguardando_do_snapshot": lambda conn, c: [],
        "ha_no_retido": lambda conn, m: False,
        # `marcar_visto` devolve True só na PRIMEIRA vez (é o `rowcount` do
        # carimbo que arbitra, §5.2). Um dublê que devolvesse True sempre
        # esconderia o defeito que a Decisão 12 existe para evitar: o mesmo
        # card 200 vezes num dia.
        "marcar_visto": _marcador_de_uma_vez(),
        "fechar_corrida": lambda conn, cid, desfecho, quem, motivo=None: True,
        "marcar_heartbeat": lambda conn, quem="guardia": True,
    }
    base.update(sobrescreve)
    for nome, fn in base.items():
        monkeypatch.setattr(GUARDIA.mc, nome, fn)


def _marcador_de_uma_vez():
    vistos: set = set()

    def _marcar(conn, cid, o_que):
        chave = (cid, o_que)
        if chave in vistos:
            return False
        vistos.add(chave)
        return True
    return _marcar


def _estado(**kw) -> dict:
    base = {"vivos": [], "ok": [], "pendentes": [], "dispensados": [],
            "fora_do_fim": [], "fora_do_odate": [], "inativos": [],
            "conta_para_fim": [], "linhas": 0, "membros": 0}
    base.update(kw)
    return base


def _corrida_dict(**kw) -> dict:
    base = {"id": 12, "malha_name": "M1", "data_referencia": ODATE,
            "sequencia": 1, "status": "ABERTA", "aberta_em": MOMENTO_ANCORA,
            "fechada_em": None, "fechada_por": None, "origem": "inicio",
            "aberta_por": "inicio:#1", "ancora_pipeline": "PIPE_A",
            "ancora_execution_id": "run_1", "no_inicio": 1, "no_fim": None,
            "modo_fechamento": "quiescencia", "teto_em": None,
            "teto_creditado_min": 0, "falha_vista_em": None,
            "atraso_visto_em": None, "tentativas": 1, "reaberta_em": None,
            "reaberta_por": None, "motivo": None}
    base.update(kw)
    return base


def _partida(pipeline="PIPE_A", data_ref=ODATE, execution_id="run_1",
             momento=MOMENTO_ANCORA, status="EXECUTANDO") -> dict:
    return {"pipeline": pipeline, "data_referencia": data_ref,
            "execution_id": execution_id, "momento": momento, "status": status}


def _desenho(malha="M1", membros=("PIPE_A", "PIPE_B"), nos=(), arestas=()):
    return {"malha": malha, "membros": list(membros), "nos": list(nos),
            "arestas": list(arestas)}


# Malha COM nó Início (id 1) que assina PIPE_A; PIPE_B depende de PIPE_A.
_COM_INICIO = _desenho(
    nos=[{"id": 1, "tipo": "inicio"}],
    arestas=[{"origem_no": 1, "origem_pipeline": None,
              "destino_no": None, "destino_pipeline": "PIPE_A"}])
# Malha SEM componente nenhum: a porta 3 é a única.
_SEM_INICIO = _desenho()


def _mundo_com_malhas(monkeypatch, desenhos, agora_banco=AGORA_BANCO, **kw):
    _mundo(monkeypatch,
           malhas_ativas_com_desenho=lambda conn: list(desenhos),
           agora_do_banco=lambda conn: agora_banco,
           **kw)


# ═══════════════ 1. o interruptor — o critério de aceite literal ════════════

def test_com_o_interruptor_em_zero_nada_abre_nada_fecha_e_o_log_nao_cresce(
        monkeypatch, caplog):
    """§11.2, Decisão 51 — o gesto de rollback da fase inteira.

    Sem esta garantia, o rollback da F2 às 3h seria "reverter o merge e refazer
    o ciclo de deploy". As três provas juntas: nenhuma pergunta do módulo da
    corrida chega ao banco, nenhuma responsabilidade nova roda, e o log é
    EXATAMENTE o de antes — uma linha, o resumo do ciclo. Uma linha a mais por
    ciclo são 288 por dia por ambiente, e é assim que um `grep` de plantão
    deixa de achar o que importa.
    """
    def _proibido(*a, **k):
        raise AssertionError("o interruptor esta em 0 — nada da corrida pode "
                             "ser perguntado")

    _mundo(monkeypatch)
    _corrida(monkeypatch, corrida_ativa=lambda conn: False,
             tabela_085_presente=_proibido, corridas_abertas=_proibido,
             marcar_heartbeat=_proibido)
    monkeypatch.setattr(GUARDIA.dep, "malhas_ativas_com_desenho", _proibido)

    with caplog.at_level(logging.INFO, logger="airflow.task"):
        saida = GUARDIA.ciclo()

    assert saida["corrida_ativa"] is False
    assert saida["corridas_abertas"] == 0 and saida["corridas_fechadas"] == 0
    linhas = [r.getMessage() for r in caplog.records]
    assert len(linhas) == 1 and "ciclo concluído" in linhas[0]
    assert not any(re.search(r"corrida|085", ln, re.I) for ln in linhas)


def test_sem_a_085_loga_uma_vez_por_ciclo_e_o_ciclo_inteiro_segue(
        monkeypatch, caplog):
    """§11.1 (célula `dags/` novo × 085 ausente) e §10/F2.

    A guardiã é quem faz o push de dependências de TODA a casa: uma exceção
    aqui não deixaria a corrida sem abrir — deixaria o sistema inteiro sem
    guardiã. Por isso a resposta é UMA linha `[GUARDIA]` com "085 ausente" e o
    ciclo seguindo; e é UMA, não uma por malha nem uma por responsabilidade,
    porque o aviso mora no portão e não dentro dos laços.
    """
    def _proibido(*a, **k):
        raise AssertionError("sem a 085 nada da corrida pode ser perguntado")

    _mundo(monkeypatch, dependentes_com_dependencia=lambda conn: [])
    _corrida(monkeypatch, tabela_085_presente=lambda conn: False,
             corridas_abertas=_proibido, marcar_heartbeat=_proibido)
    monkeypatch.setattr(GUARDIA.dep, "malhas_ativas_com_desenho", _proibido)

    with caplog.at_level(logging.INFO, logger="airflow.task"):
        saida = GUARDIA.ciclo()

    avisos = [r.getMessage() for r in caplog.records if "085 ausente" in r.getMessage()]
    assert len(avisos) == 1 and avisos[0].startswith("[GUARDIA]")
    assert saida["corrida_ativa"] is False
    # o ciclo INTEIRO segue: as cinco responsabilidades antigas responderam
    assert set(saida) >= {"fechadas", "ordenadas", "disparadas", "notificados"}


def test_o_heartbeat_so_e_carimbado_com_a_corrida_operando(monkeypatch):
    """§10/F2 — o contrato com a F3.

    O heartbeat responde "a guardiã deste deploy OPEROU a corrida", não "a
    guardiã está viva". Com o interruptor em 0 a resposta honesta à pergunta da
    F3 ("posso abrir corrida pela API?") é NÃO — carimbar assim mesmo faria a
    API abrir corridas que ninguém iria fechar, e corrida aberta BLOQUEIA o
    disparo: a API paralisaria a malha com uma trava que o motor não destrava.
    """
    batidas = []
    _mundo(monkeypatch)
    _corrida(monkeypatch,
             marcar_heartbeat=lambda conn, quem="guardia":
                 batidas.append(quem) or True)
    GUARDIA.ciclo()
    assert batidas == ["guardia"]

    batidas.clear()
    _corrida(monkeypatch, corrida_ativa=lambda conn: False,
             marcar_heartbeat=lambda conn, quem="guardia":
                 batidas.append(quem) or True)
    GUARDIA.ciclo()
    assert batidas == []


def test_o_interruptor_e_RELIDO_no_comeco_de_cada_ciclo(monkeypatch):
    """§11.2 — virar a chave tem de valer no ciclo seguinte, não no worker
    seguinte.

    `corrida_ativa` memoriza por PROCESSO de propósito (o ciclo avalia N malhas
    e perguntar por malha seriam N idas ao banco para uma resposta que não muda
    no meio do ciclo — o mesmo desenho de `modo_sequencia`). O preço disso é que
    um worker do Airflow reaproveitado carregaria a chave antiga **até morrer**:
    desligar a corrida às 3h não teria efeito nenhum até o pod reiniciar, e o
    interruptor deixaria de ser gesto de rollback. Por isso a limpeza mora no
    portão do ciclo, ANTES da pergunta.

    Que a chave limpa volta a ser lida do banco é invariante da F1
    (`test_limpar_cache_faz_a_chave_valer_de_novo`); o que se prova aqui é o
    gesto novo: a guardiã limpa, e limpa em TODO ciclo.
    """
    passos = []
    _mundo(monkeypatch)
    _corrida(monkeypatch,
             limpar_cache=lambda: passos.append("limpou"),
             corrida_ativa=lambda conn: passos.append("perguntou") or True)
    GUARDIA.ciclo()
    GUARDIA.ciclo()
    assert passos == ["limpou", "perguntou", "limpou", "perguntou"]


def test_a_capacidade_e_declarada_junto_com_o_consumidor():
    """§10/F1 dizia: "declarar capacidade que não existe é o defeito, não a
    cura". A F2 traz o consumidor, então a declaração entra AGORA — e a
    amarração é dos dois lados: o nome existe na tupla E as duas
    responsabilidades existem no fonte da guardiã."""
    from utils import dependencias as dep_real
    assert "malha_corrida_085" in dep_real.CAPACIDADES
    fonte = (_ROOT / "dags/etl_dependencia_guardia.py").read_text(encoding="utf-8")
    assert "def _abrir_corridas_malha" in fonte
    assert "def _fechar_corridas_malha" in fonte


# ═══════════════ 2. as portas 2 e 3 (Decisões 13 a 18) ══════════════════════

def _captura_abertura(chamadas):
    def _abrir(conn, malha, odate, origem, **kw):
        chamadas.append({"malha": malha, "odate": odate, "origem": origem, **kw})
        return dict(_corrida_dict(data_referencia=odate, origem=origem),
                    nova=True, odate_confere=True)
    return _abrir


def test_porta_2_a_raiz_assinada_pelo_inicio_abre_a_corrida(monkeypatch):
    """§6.2, porta 2 — o caminho feliz da fase.

    Três fatos numa asserção só, porque os três nascem do mesmo gesto e cada um
    sozinho seria uma corrida errada:

      • `origem='inicio'` e `aberta_por='inicio:#1'` — o ciclo tem dono;
      • `aberta_em` RECUA para o instante da linha âncora. Sem o recuo, a
        corrida nasceria até 5 min depois de a raiz partir e o recorte de tempo
        da Decisão 23 não veria o trabalho que a originou: as linhas virariam
        "não partiu" e a corrida iria a FALHA numa malha que rodou perfeita;
      • o ODATE é o CANÔNICO da malha (Decisão 18), calculado sobre o instante
        da âncora — nunca o que o membro carimbou.
    """
    chamadas, snapshots, vinculos = [], [], []
    _mundo_com_malhas(monkeypatch, [_COM_INICIO])
    _corrida(monkeypatch,
             partidas_a_cobrir=lambda conn, m, pipes, datas, teto:
                 [_partida()] if list(pipes) == ["PIPE_A"] else [],
             abrir_corrida=_captura_abertura(chamadas),
             congelar_snapshot=lambda conn, cid, m, conta_para_fim=None:
                 snapshots.append((cid, m, conta_para_fim)) or 2,
             vincular_execucao=lambda conn, p, d, e, cid:
                 vinculos.append((p, d, e, cid)) or True)

    saida = GUARDIA.ciclo()

    assert saida["corridas_abertas"] == 1
    assert len(chamadas) == 1
    c = chamadas[0]
    assert (c["malha"], c["odate"], c["origem"]) == ("M1", ODATE, "inicio")
    assert c["aberta_em"] == MOMENTO_ANCORA         # RECUA para a âncora
    assert c["aberta_por"] == "inicio:#1"
    assert c["ancora_pipeline"] == "PIPE_A" and c["ancora_execution_id"] == "run_1"
    assert c["no_inicio"] == 1 and c["no_fim"] is None
    assert c["modo_fechamento"] == "quiescencia"    # malha sem nó Fim
    # snapshot no MESMO gesto: corrida sem membros tem denominador zero e a
    # §6.5 a levaria a ABORTADA com a malha rodando ao lado
    assert snapshots == [(12, "M1", None)]
    assert vinculos == [("PIPE_A", ODATE, "run_1", 12)]


def test_porta_3_malha_sem_inicio_abre_pela_raiz_interna(monkeypatch):
    """§6.2, porta 3 (Decisão 16) — a maioria das malhas do dev não tem
    componente nenhum, e sem esta porta a corrida automática não existiria
    justamente para elas.

    A raiz é "membro sem predecessor DENTRO da malha", perguntada ao módulo (o
    MESMO predicado do `eh_raiz` do snapshot). Restringir às raízes é o que
    impede um membro do meio da cadeia de abrir a corrida DEPOIS de metade dos
    membros ter concluído — as linhas anteriores ficariam fora do recorte e a
    corrida iria a FALHA numa malha que rodou perfeitamente.
    """
    chamadas, perguntou = [], []
    _mundo_com_malhas(monkeypatch, [_SEM_INICIO])
    _corrida(monkeypatch,
             raizes_da_malha=lambda conn, m: perguntou.append(m) or ["PIPE_A"],
             partidas_a_cobrir=lambda conn, m, pipes, datas, teto:
                 [_partida()] if list(pipes) == ["PIPE_A"] else [],
             abrir_corrida=_captura_abertura(chamadas))

    assert GUARDIA.ciclo()["corridas_abertas"] == 1
    assert perguntou == ["M1"]
    assert chamadas[0]["origem"] == "implicita"
    assert chamadas[0]["aberta_por"] == "implicita:PIPE_A"
    assert chamadas[0]["no_inicio"] is None


def test_a_malha_COM_no_Fim_congela_o_modo_e_o_upstream_do_Fim(monkeypatch):
    """§6.9/#1 e #2 — o `modo_fechamento` é DERIVADO do desenho na abertura e
    congela com ele; nunca é configurado à mão.

    E o `conta_para_fim` do snapshot é o upstream do Fim ∩ membros: é o
    denominador do desfecho. Congelá-lo na abertura é o que impede a edição da
    malha no meio da madrugada de mudar a conta desta corrida (§6.9/#16) —
    vale da próxima em diante.

    O conjunto VAZIO é o caso separado que a spec obriga a distinguir de `None`:
    existe um Fim e ele não alcança ninguém. `None` significaria "malha sem
    Fim", isto é, todos contam — e o fechamento por quiescência decidiria em
    lugar do Fim, silenciosamente.
    """
    def _cenario(arestas):
        chamadas, snapshots = [], []
        desenho = _desenho(nos=[{"id": 7, "tipo": "fim"}], arestas=arestas)
        _mundo_com_malhas(monkeypatch, [desenho])
        _corrida(monkeypatch,
                 raizes_da_malha=lambda conn, m: ["PIPE_A"],
                 partidas_a_cobrir=lambda conn, m, pipes, datas, teto:
                     [_partida()],
                 abrir_corrida=_captura_abertura(chamadas),
                 congelar_snapshot=lambda conn, cid, m, conta_para_fim=None:
                     snapshots.append(conta_para_fim) or 2)
        GUARDIA.ciclo()
        return chamadas[0], snapshots[0]

    # o Fim alcança PIPE_A (que é membro); PIPE_B fica de fora dele
    chamada, conta = _cenario([{"origem_no": None, "origem_pipeline": "PIPE_A",
                                "destino_no": 7, "destino_pipeline": None}])
    assert chamada["modo_fechamento"] == "fim" and chamada["no_fim"] == 7
    assert conta == ["PIPE_A"]

    # Fim sem entrada nenhuma: conjunto vazio, e NÃO None
    chamada, conta = _cenario([])
    assert chamada["modo_fechamento"] == "fim"
    assert conta == [] and conta is not None


def test_a_raiz_que_parte_produz_UMA_corrida_e_o_ciclo_seguinte_ADERE(
        monkeypatch):
    """§10/F2 — "raiz da malha parte por cron → **uma** linha ABERTA".

    A abertura é INSERT-first (Decisão 14): o ciclo seguinte tenta de novo e o
    índice filtrado `ux_malha_exec_aberta` devolve a corrida que já existe.
    Violação NÃO é erro — é adesão. O que esta prova exige é o efeito colateral
    certo da adesão:

      • não conta como abertura nova (senão o resumo do ciclo diria "1 aberta"
        288 vezes por dia, e a métrica que responde "quantos ciclos nasceram
        hoje" viraria ruído);
      • **não recongela o snapshot** — ele é o denominador do "4 de 7" e é do
        desenho NO INSTANTE DA ABERTURA (§6.9/#16). Recongelar a cada 5 min
        faria a conta mudar embaixo do operador no meio da madrugada, sempre
        que alguém editasse a malha;
      • ainda VINCULA a linha, porque a raiz que partiu agora pertence ao ciclo
        em voo — e é o vínculo que faz o laço convergir no ciclo seguinte.
    """
    aberturas, snapshots, vinculos = [], [], []
    ja_existe = {"n": 0}

    def _abrir(conn, malha, odate, origem, **kw):
        ja_existe["n"] += 1
        return dict(_corrida_dict(data_referencia=odate),
                    nova=ja_existe["n"] == 1, odate_confere=True)

    _mundo_com_malhas(monkeypatch, [_SEM_INICIO])
    _corrida(monkeypatch,
             raizes_da_malha=lambda conn, m: ["PIPE_A"],
             partidas_a_cobrir=lambda conn, m, pipes, datas, teto: [_partida()],
             abrir_corrida=lambda conn, *a, **k:
                 aberturas.append(a[0]) or _abrir(conn, *a, **k),
             congelar_snapshot=lambda conn, cid, m, conta_para_fim=None:
                 snapshots.append(cid) or 2,
             vincular_execucao=lambda conn, p, d, e, cid:
                 vinculos.append(cid) or True)

    primeiro = GUARDIA.ciclo()["corridas_abertas"]
    segundo = GUARDIA.ciclo()["corridas_abertas"]

    assert (primeiro, segundo) == (1, 0)
    assert len(aberturas) == 2          # tentou nos dois ciclos: claim, não check
    assert snapshots == [12]            # congelou UMA vez
    assert vinculos == [12, 12]         # e vinculou nos dois


def test_a_janela_da_busca_e_D_menos_1_e_D_pela_virada_da_malha(monkeypatch):
    """D45 — nunca varredura de histórico. A busca das partidas é limitada às
    duas datas do PRESENTE (o mesmo recorte dos observadores) e ao teto da
    malha: uma corrida cujo `aberta_em` recuasse para além do próprio teto
    nasceria EXPIRADA no ato, e a guardiã que voltou depois de um dia fora
    ressuscitaria a madrugada de ontem."""
    vistos = []
    _mundo_com_malhas(monkeypatch, [_SEM_INICIO])
    _corrida(monkeypatch,
             raizes_da_malha=lambda conn, m: ["PIPE_A"],
             teto_horas_da_malha=lambda conn, m: 6,
             partidas_a_cobrir=lambda conn, m, pipes, datas, teto:
                 vistos.append((tuple(datas), teto)) or [])
    GUARDIA.ciclo()
    assert vistos == [((ONTEM, ODATE), 6)]


def test_decisao_17_malha_com_inicio_nao_abre_pela_porta_implicita(monkeypatch):
    """Decisão 17 — o membro com cron próprio não sequestra o ciclo, e o Início
    não vira decoração.

    Duas metades, e a segunda é a que faltou no incidente `Carga_Vida`: a
    corrida NÃO abre, e a própria linha carimba o porquê. De plantão se chega
    pelo pipeline, não pela malha — o diagnóstico tem de viajar com a execução,
    senão o que se vê é uma execução comum que por acaso ficou fora de tudo.
    """
    chamadas, carimbos, vinculos = [], [], []
    _mundo_com_malhas(monkeypatch, [_COM_INICIO])
    _corrida(monkeypatch,
             # PIPE_A (assinado pelo Início) não partiu; PIPE_B partiu sozinho
             partidas_a_cobrir=lambda conn, m, pipes, datas, teto:
                 [_partida(pipeline="PIPE_B", execution_id="run_b")]
                 if list(pipes) == ["PIPE_B"] else [],
             abrir_corrida=_captura_abertura(chamadas),
             carimbar_motivo=lambda conn, p, d, e, chave, texto:
                 carimbos.append((p, e, chave, texto)) or True,
             vincular_execucao=lambda conn, p, d, e, cid:
                 vinculos.append(p) or True)

    saida = GUARDIA.ciclo()

    assert saida["corridas_abertas"] == 0
    assert chamadas == []                       # nada abriu
    # e a linha fica com `malha_execucao_id` NULL: ninguém a vincula. Sem esta
    # asserção, um vínculo a uma corrida de outro dia passaria despercebido —
    # e a linha apareceria no card de um ciclo do qual não participou.
    assert vinculos == []
    assert len(carimbos) == 1
    pipeline, execution_id, chave, texto = carimbos[0]
    assert (pipeline, execution_id) == ("PIPE_B", "run_b")
    assert chave == GUARDIA.mc.MOTIVO_FORA_DA_CORRIDA
    assert "FORA" in texto and "M1" in texto


def test_com_corrida_aberta_o_membro_solto_nao_e_carimbado(monkeypatch):
    """A outra metade da Decisão 17: havendo ciclo em voo, a linha PERTENCE a
    ele (o recorte de tempo da Decisão 23 já a conta). Carimbar "rodou fora da
    corrida" ali seria mentira gravada no banco — e é a classe de defeito que
    faz o operador parar de confiar no diagnóstico."""
    carimbos = []
    _mundo_com_malhas(monkeypatch, [_COM_INICIO])
    _corrida(monkeypatch,
             partidas_a_cobrir=lambda conn, m, pipes, datas, teto:
                 [_partida(pipeline="PIPE_B")] if list(pipes) == ["PIPE_B"] else [],
             corrida_aberta=lambda conn, m: _corrida_dict(),
             carimbar_motivo=lambda conn, p, d, e, chave, texto:
                 carimbos.append(p) or True)
    GUARDIA.ciclo()
    assert carimbos == []


def test_decisao_15_corrida_de_outro_odate_recusa_e_nunca_adere_calada(
        monkeypatch):
    """Decisão 15 — o `Carga_Vida` por DENTRO do mecanismo criado para matá-lo.

    Cenário: corrida de terça travada; quarta 01:00 o cron parte. Aderir
    carimbaria **terça** em toda a carga de quarta, e para o motor estaria tudo
    coerente, porque é uma corrida só. A resposta é recusa NOMINAL: motivo na
    linha, evento `DATA_DIVERGENTE` e nenhum vínculo. O caminho automático de
    hoje já recusa nesse caso — trocar recusa explícita por adesão silenciosa
    seria regressão.
    """
    carimbos, eventos, vinculos = [], [], []

    def _abrir(conn, malha, odate, origem, **kw):
        # a corrida ABERTA é a de ontem: o índice único devolveu ela
        return dict(_corrida_dict(id=9, data_referencia=ONTEM), nova=False,
                    odate_confere=False)

    _mundo_com_malhas(monkeypatch, [_SEM_INICIO],
                      gravar_evento=lambda conn, p, d, t, det, **kw:
                          eventos.append((p, d, t, det, kw)) or True)
    _corrida(monkeypatch,
             raizes_da_malha=lambda conn, m: ["PIPE_A"],
             partidas_a_cobrir=lambda conn, m, pipes, datas, teto: [_partida()],
             abrir_corrida=_abrir,
             carimbar_motivo=lambda conn, p, d, e, chave, texto:
                 carimbos.append((p, chave, texto)) or True,
             vincular_execucao=lambda conn, p, d, e, cid:
                 vinculos.append(p) or True)

    saida = GUARDIA.ciclo()

    assert saida["corridas_abertas"] == 0       # aderir não é abrir
    assert vinculos == []                       # e a linha NÃO entra na corrida
    assert len(carimbos) == 1
    assert carimbos[0][1] == GUARDIA.mc.MOTIVO_OUTRO_ODATE
    assert "#9" in carimbos[0][2] and "2026-08-02" in carimbos[0][2]
    assert len(eventos) == 1
    pipeline, data, tipo, _det, kw = eventos[0]
    assert tipo == "DATA_DIVERGENTE"
    assert pipeline == "#corrida:9" and kw["malha_execucao_id"] == 9


def test_ancora_com_odate_proprio_divergente_abre_no_canonico_e_alerta(
        monkeypatch):
    """§6.2, último parágrafo — a corrida nasce com o ODATE CANÔNICO da malha,
    o `motivo` registra a discordância e sai `DATA_DIVERGENTE`.

    Divergência VISÍVEL é o oposto de divergência silenciosa. Deixar a corrida
    nascer com a data que o membro calculou sozinho seria eleger a régua errada
    — é exatamente a causa raiz (c) desta spec.
    """
    chamadas, eventos = [], []
    _mundo_com_malhas(monkeypatch, [_SEM_INICIO],
                      gravar_evento=lambda conn, p, d, t, det, **kw:
                          eventos.append((t, det)) or True)
    _corrida(monkeypatch,
             raizes_da_malha=lambda conn, m: ["PIPE_A"],
             # a linha carimbou ONTEM; o canônico da malha é HOJE
             partidas_a_cobrir=lambda conn, m, pipes, datas, teto:
                 [_partida(data_ref=ONTEM)],
             abrir_corrida=_captura_abertura(chamadas))

    GUARDIA.ciclo()

    assert chamadas[0]["odate"] == ODATE                    # o canônico vence
    assert "DATA_DIVERGENTE" in (chamadas[0]["motivo"] or "")
    assert [t for t, _ in eventos] == ["DATA_DIVERGENTE"]


def test_o_lote_da_corrida_e_so_o_ODATE_da_ancora(monkeypatch):
    """O DIA MUDO — achado da revisão adversarial, medido no dev antes de virar
    teste.

    `partidas_a_cobrir` varre a janela `{D-1, D}`, então basta a guardiã ficar
    fora do ar atravessando a virada (deploy, restart do worker, pool saturado)
    para o lote trazer as DUAS madrugadas juntas: a raiz de D-1 às 23:50 e a de
    D às 01:00. A âncora é a mais antiga, e a corrida nasce de **D-1**.

    Vincular o lote inteiro carimbava a linha de **D** com a corrida de **D-1**.
    Como `malha_execucao_id` é WRITE-ONCE (Decisão 9) e a busca exclui o que uma
    corrida DESTA malha já cobriu, o efeito medido foi permanente: o ciclo de D
    **nunca mais abria** — dia inteiro sem corrida, sem card e sem alarme, que é
    o defeito (a) desta spec produzido pelo mecanismo criado para matá-lo.

    A linha do outro ODATE volta no ciclo seguinte e passa pela conferência da
    Decisão 15, que é o único lugar onde divergência de data se decide.
    """
    vinculos = []
    _mundo_com_malhas(monkeypatch, [_SEM_INICIO])
    _corrida(monkeypatch,
             raizes_da_malha=lambda conn, m: ["PIPE_A"],
             odate_da_abertura=lambda conn, m, momento: ONTEM,
             partidas_a_cobrir=lambda conn, m, pipes, datas, teto: [
                 _partida(data_ref=ONTEM, execution_id="run_ontem",
                          momento=datetime(2026, 8, 2, 23, 50)),
                 _partida(data_ref=ODATE, execution_id="run_hoje",
                          momento=datetime(2026, 8, 3, 1, 0))],
             abrir_corrida=lambda conn, *a, **k:
                 dict(_corrida_dict(data_referencia=a[1]), nova=True,
                      odate_confere=True),
             vincular_execucao=lambda conn, p, d, e, cid:
                 vinculos.append((e, d)) or True)

    GUARDIA.ciclo()

    assert vinculos == [("run_ontem", ONTEM)]


def test_a_recusa_por_odate_carimba_so_as_linhas_do_lote(monkeypatch):
    """A outra metade do mesmo achado: o texto da recusa nomeia o ciclo que NÃO
    foi aberto (o da âncora). Carimbá-lo numa linha de outro dia gravaria no
    banco um diagnóstico sobre um ciclo do qual ela não participa — e é o motivo
    que o plantonista lê primeiro."""
    carimbos = []
    _mundo_com_malhas(monkeypatch, [_SEM_INICIO],
                      gravar_evento=lambda conn, p, d, t, det, **kw: True)
    _corrida(monkeypatch,
             raizes_da_malha=lambda conn, m: ["PIPE_A"],
             odate_da_abertura=lambda conn, m, momento: ONTEM,
             partidas_a_cobrir=lambda conn, m, pipes, datas, teto: [
                 _partida(data_ref=ONTEM, execution_id="run_ontem",
                          momento=datetime(2026, 8, 2, 23, 50)),
                 _partida(data_ref=ODATE, execution_id="run_hoje",
                          momento=datetime(2026, 8, 3, 1, 0))],
             abrir_corrida=lambda conn, *a, **k:
                 dict(_corrida_dict(id=9, data_referencia=ODATE), nova=False,
                      odate_confere=False),
             carimbar_motivo=lambda conn, p, d, e, chave, texto:
                 carimbos.append(e) or True)

    GUARDIA.ciclo()

    assert carimbos == ["run_ontem"]


def test_erro_em_uma_malha_nao_interrompe_as_outras(monkeypatch):
    """D51 — try/except por item, a mesma disciplina das cinco
    responsabilidades antigas. Uma malha com desenho quebrado não pode fazer as
    outras 40 ficarem sem ciclo."""
    chamadas = []

    def _partidas(conn, malha, pipes, datas, teto):
        if malha == "RUIM":
            raise RuntimeError("desenho quebrado")
        return [_partida()]

    _mundo_com_malhas(monkeypatch,
                      [_desenho(malha="RUIM"), _desenho(malha="BOA")])
    _corrida(monkeypatch,
             raizes_da_malha=lambda conn, m: ["PIPE_A"],
             partidas_a_cobrir=_partidas,
             abrir_corrida=_captura_abertura(chamadas))
    assert GUARDIA.ciclo()["corridas_abertas"] == 1
    assert [c["malha"] for c in chamadas] == ["BOA"]


# ═══════════════ 3. os sete desfechos (§6.5, Decisões 24 a 28) ══════════════

def _fechamentos(monkeypatch, agora=AGORA, **kw):
    """Cenário base do fechador: uma corrida aberta e o que se quiser mudar.

    `agora` é o relógio do WORKER, e é parâmetro de propósito: os cenários do
    §8 o movem para provar que nenhum desfecho depende dele."""
    fechou, eventos = [], []
    _mundo(monkeypatch, agora=agora,
           gravar_evento=lambda conn, p, d, t, det, notificar=True, **k:
               eventos.append({"pipeline": p, "tipo": t, "detalhe": det,
                               "notificar": notificar, **k}) or True)
    base = {
        "corridas_abertas": lambda conn: [_corrida_dict()],
        "fechar_corrida": lambda conn, cid, desfecho, quem, motivo=None:
            fechou.append((cid, desfecho, quem, motivo)) or True,
    }
    base.update(kw)
    _corrida(monkeypatch, **base)
    return fechou, eventos


def test_membro_em_execucao_segura_a_corrida_mesmo_com_todo_o_resto_verde(
        monkeypatch):
    """Decisão 25 e invariante §16/5 — o teste que prova que o teto não mata
    trabalho vivo, na sua forma mais simples: nada fecha com membro vivo.

    Fechar aqui liberaria o disparo por cima de pipelines `EXECUTANDO`, e as
    linhas que terminassem depois carregariam id de corrida fechada: o card
    ficaria com o desfecho errado e 7/7 verdes embaixo — mentira estável que
    nenhum refresh corrige.
    """
    fechou, eventos = _fechamentos(
        monkeypatch,
        estado=lambda conn, c, dispensa_sem_linha=None:
            _estado(vivos=["PIPE_B"], ok=["PIPE_A"], linhas=2, membros=2))
    assert GUARDIA.ciclo()["corridas_fechadas"] == 0
    assert fechou == [] and eventos == []


def test_uma_falha_com_o_resto_verde_fecha_FALHA_e_nao_inventa_verde(
        monkeypatch):
    """Decisão 24 e invariante §16/4 — teste de AUSÊNCIA.

    É a família inteira do campo agregado que mente: um membro em FALHA e todos
    os outros em SUCESSO não é "malha concluída". `MALHA_CONCLUIDA` NÃO pode
    sair, e é a ausência que se testa — a presença de `MALHA_FALHOU` sozinha
    não provaria nada.
    """
    fechou, eventos = _fechamentos(
        monkeypatch,
        estado=lambda conn, c, dispensa_sem_linha=None:
            _estado(ok=["PIPE_A", "PIPE_C"],
                    pendentes=[{"pipeline": "CARGA_A", "classe": "falhou",
                                "desde": MOMENTO_ANCORA, "faltante": None}],
                    linhas=3, membros=3))
    assert GUARDIA.ciclo()["corridas_fechadas"] == 1
    assert [f[1] for f in fechou] == ["FALHA"]
    tipos = [e["tipo"] for e in eventos]
    assert "MALHA_CONCLUIDA" not in tipos
    assert tipos == ["MALHA_FALHOU"]


def test_malha_falhou_sai_na_deteccao_e_uma_vez_so_em_muitos_ciclos(
        monkeypatch):
    """Decisão 12 — numa malha de 40 membros, `CARGA_A` falha às 01:12 e os
    outros 38 seguem até 05:00. Tocar o canal só no fechamento é tarde POR
    DEFINIÇÃO.

    E `falha_vista_em` é a memória que impede o mesmo card 200 vezes no dia: o
    `rowcount` do carimbo é o árbitro do "primeira vez", em UMA operação —
    ler-e-decidir deixaria a janela entre a leitura e a escrita, que é
    justamente o que dois workers da guardiã em paralelo encontrariam.
    """
    vistos = {"n": 0}

    def _marcar(conn, cid, o_que):
        if o_que != "falha":
            return True
        vistos["n"] += 1
        return vistos["n"] == 1              # só a PRIMEIRA vez

    fechou, eventos = _fechamentos(
        monkeypatch,
        marcar_visto=_marcar,
        # a corrida segue ABERTA: há vivo. O card não espera por isso.
        estado=lambda conn, c, dispensa_sem_linha=None:
            _estado(vivos=["PIPE_B"],
                    pendentes=[{"pipeline": "CARGA_A", "classe": "falhou",
                                "desde": MOMENTO_ANCORA, "faltante": None}],
                    linhas=2, membros=2))

    for _ in range(200):
        GUARDIA.ciclo()

    assert fechou == []                                   # nada fechou: há vivo
    assert [e["tipo"] for e in eventos] == ["MALHA_FALHOU"]
    assert eventos[0]["pipeline"] == "#corrida:12"
    assert eventos[0]["malha_execucao_id"] == 12
    assert "CARGA_A" in eventos[0]["detalhe"]


def test_sabado_com_tudo_pulado_e_sem_trabalho_imediato(monkeypatch):
    """Decisão 26/27 — o sábado da malha `somente_dias_uteis`.

    Sem o desfecho imediato: a corrida bloquearia a malha o dia inteiro,
    recusaria todo disparo manual do sábado e mandaria um alarme no domingo por
    um dia que funcionou exatamente como projetado. Na primeira semana o
    operador aprende a ignorar esse alarme — e aí ele deixa de servir para o
    caso real. Pior: com teto de 48h a corrida de sábado ainda estaria aberta
    na segunda 01:00, e a segunda seria PULADA em silêncio.

    Por isso: fecha JÁ (sem esperar teto nem quiescência) e o evento nasce FORA
    do lote de notificação.
    """
    fechou, eventos = _fechamentos(
        monkeypatch,
        # teto NÃO vencido e quiescência NÃO satisfeita: mesmo assim fecha
        relogios=lambda conn, c, car, qui: {"teto_vencido": False,
                                            "partida_vencida": False,
                                            "quiescente": False},
        estado=lambda conn, c, dispensa_sem_linha=None:
            _estado(dispensados=["PIPE_A", "PIPE_B"], linhas=2, membros=2))
    assert GUARDIA.ciclo()["corridas_fechadas"] == 1
    assert [f[1] for f in fechou] == ["SEM_TRABALHO"]
    assert [(e["tipo"], e["notificar"]) for e in eventos] == \
        [("MALHA_SEM_TRABALHO", False)]
    assert "MALHA_CONCLUIDA" not in [e["tipo"] for e in eventos]


def test_corrida_recem_aberta_com_zero_linhas_nao_vira_abortada(monkeypatch):
    """Decisão 28 — o piso absoluto por `aberta_em`.

    O disparo manual fecha o banco ANTES de chamar o Airflow, e entre o commit
    da corrida e o primeiro `EXECUTANDO` há latência de scheduler, pool
    saturado, DAG pausada e `nao_iniciar_antes`. Se a guardiã passar nessa
    fresta e abortar, as raízes registram `EXECUTANDO` apontando para uma
    corrida abortada: o card volta a mentir e o próximo disparo é liberado POR
    CIMA da malha rodando.
    """
    fechou, eventos = _fechamentos(
        monkeypatch,
        relogios=lambda conn, c, car, qui: {"teto_vencido": False,
                                            "partida_vencida": False,
                                            "quiescente": True},
        estado=lambda conn, c, dispensa_sem_linha=None:
            _estado(pendentes=[{"pipeline": "PIPE_A", "classe": "nao_partiu",
                                "desde": None, "faltante": None}],
                    linhas=0, membros=1))
    assert GUARDIA.ciclo()["corridas_fechadas"] == 0
    assert fechou == [] and eventos == []


def test_zero_linhas_depois_da_carencia_vira_abortada(monkeypatch):
    """A outra metade da Decisão 28 — passada a carência, a corrida que não
    chegou a começar É encerrada. Invariante §16/3: toda corrida aberta fecha,
    porque corrida aberta bloqueia disparo."""
    fechou, eventos = _fechamentos(
        monkeypatch,
        relogios=lambda conn, c, car, qui: {"teto_vencido": False,
                                            "partida_vencida": True,
                                            "quiescente": True},
        estado=lambda conn, c, dispensa_sem_linha=None:
            _estado(pendentes=[{"pipeline": "PIPE_A", "classe": "nao_partiu",
                                "desde": None, "faltante": None}],
                    linhas=0, membros=1))
    assert GUARDIA.ciclo()["corridas_fechadas"] == 1
    assert [f[1] for f in fechou] == ["ABORTADA"]
    assert [(e["tipo"], e["malha_execucao_id"]) for e in eventos] == \
        [("MALHA_ABORTADA", 12)]
    assert "MALHA_CONCLUIDA" not in [e["tipo"] for e in eventos]


def test_abortada_com_linha_de_outro_odate_nao_diz_que_a_malha_nao_rodou(monkeypatch):
    """O caso `Carga_Vida` chegando ao fechamento: a âncora carimbou outra data,
    então há execução VINCULADA à corrida e mesmo assim `linhas` (que conta o
    que rodou no ODATE DA CORRIDA) é 0.

    O desfecho continua `ABORTADA` — §6.5: zero trabalho no ODATE da corrida —
    mas o texto não pode dizer "não chegou a começar" para uma malha que rodou
    com a data errada. É a mesma família de mentira que esta spec existe para
    matar: o operador que lê isso às 3h procura DAG pausada, não data divergente,
    e o incidente segue de pé enquanto ele procura no lugar errado."""
    fechou, eventos = _fechamentos(
        monkeypatch,
        relogios=lambda conn, c, car, qui: {"teto_vencido": False,
                                            "partida_vencida": True,
                                            "quiescente": True},
        estado=lambda conn, c, dispensa_sem_linha=None:
            _estado(pendentes=[{"pipeline": "PIPE_A", "classe": "nao_partiu",
                                "desde": None, "faltante": None}],
                    fora_do_odate=[{"pipeline": "PIPE_A", "data": date(2026, 8, 3)}],
                    linhas=0, membros=1))
    assert GUARDIA.ciclo()["corridas_fechadas"] == 1
    assert [f[1] for f in fechou] == ["ABORTADA"]
    texto = eventos[0]["detalhe"]
    # o que ele PRECISA dizer
    assert "data divergente" in texto and "2026-08-03" in texto
    # e o que ele NÃO pode mais dizer
    assert "nao chegou a comecar" not in texto


def test_abortada_de_verdade_mantem_o_texto_de_sempre(monkeypatch):
    """O contraponto do teste acima — sem linha fora do ODATE, a frase original
    fica intacta. Sem este par, trocar o texto dos DOIS casos passaria verde."""
    fechou, eventos = _fechamentos(
        monkeypatch,
        relogios=lambda conn, c, car, qui: {"teto_vencido": False,
                                            "partida_vencida": True,
                                            "quiescente": True},
        estado=lambda conn, c, dispensa_sem_linha=None:
            _estado(pendentes=[{"pipeline": "PIPE_A", "classe": "nao_partiu",
                                "desde": None, "faltante": None}],
                    linhas=0, membros=1))
    assert GUARDIA.ciclo()["corridas_fechadas"] == 1
    assert [f[1] for f in fechou] == ["ABORTADA"]
    texto = eventos[0]["detalhe"]
    assert "nao chegou a comecar" in texto and "data divergente" not in texto


def test_teto_vencido_com_vivo_alarma_e_nao_fecha(monkeypatch):
    """Decisão 25 na sua forma cara: fechamento mensal com 26h de carga
    legítima e teto padrão de 24h.

    Às 24h a corrida sairia `EXPIRADA`, o fechamento desbloquearia o disparo, e
    o cron da madrugada seguinte partiria a corrida #13 por cima de 8 pipelines
    ainda `EXECUTANDO` — que é exatamente o que a corrida existe para impedir,
    agora com carimbo de aprovação do modelo. Teto com vivo é ALARME.
    """
    fechou, eventos = _fechamentos(
        monkeypatch,
        relogios=lambda conn, c, car, qui: {"teto_vencido": True,
                                            "partida_vencida": True,
                                            "quiescente": True},
        estado=lambda conn, c, dispensa_sem_linha=None:
            _estado(vivos=["PIPE_A"], ok=["PIPE_B"], linhas=2, membros=2))
    assert GUARDIA.ciclo()["corridas_fechadas"] == 0
    assert fechou == []
    assert [e["tipo"] for e in eventos] == ["MALHA_ATRASADA"]


def test_teto_vencido_sem_vivo_e_sem_quiescencia_expira(monkeypatch):
    """A rede de segurança do §6.6: corrida parada além do teto, sem nada vivo,
    vira `EXPIRADA` — e `MALHA_CONCLUIDA` NÃO sai (Decisão 24, ausência).

    Sem o teto, uma corrida travada congelaria a malha para sempre, sem tela
    para destravar: é a classe do `factory_log` órfão em RUNNING, elevada da
    geração para o ciclo.
    """
    fechou, eventos = _fechamentos(
        monkeypatch,
        relogios=lambda conn, c, car, qui: {"teto_vencido": True,
                                            "partida_vencida": True,
                                            "quiescente": False},
        estado=lambda conn, c, dispensa_sem_linha=None:
            _estado(ok=["PIPE_A"], linhas=1, membros=1))
    assert GUARDIA.ciclo()["corridas_fechadas"] == 1
    assert [f[1] for f in fechou] == ["EXPIRADA"]
    assert [e["tipo"] for e in eventos] == ["MALHA_EXPIRADA"]


def test_concluida_sem_no_fim_emite_o_card_com_o_marcador_da_corrida(
        monkeypatch):
    """§10/F2 — "malha sem nó Fim → o evento aparece no painel (marcador
    `#corrida:{id}`)". São 3 de 4 malhas no dev: sem isto, a maioria fecharia
    em silêncio."""
    fechou, eventos = _fechamentos(
        monkeypatch,
        estado=lambda conn, c, dispensa_sem_linha=None:
            _estado(ok=["PIPE_A", "PIPE_B"], linhas=2, membros=2))
    assert GUARDIA.ciclo()["corridas_fechadas"] == 1
    assert [f[1] for f in fechou] == ["CONCLUIDA"]
    # o id da corrida vai JUNTO, e não só o marcador: é ele que entra na chave
    # do `ux_dep_evento_corrida`. Sem ele a idempotência volta a ser por
    # (pipeline, dia, tipo) e a SEGUNDA corrida da mesma malha no mesmo dia
    # fecharia em silêncio — o card do redisparo nunca sairia
    assert [(e["tipo"], e["pipeline"], e["malha_execucao_id"])
            for e in eventos] == [("MALHA_CONCLUIDA", "#corrida:12", 12)]


def test_concluida_com_no_fim_deixa_o_card_para_o_observador(monkeypatch):
    """Havendo nó Fim, quem anuncia a conclusão é o OBSERVADOR da F14 — no
    mesmo ciclo, com o mesmo id de corrida na chave do índice. Emitir aqui
    TAMBÉM daria dois cards para a mesma conclusão: o mesmo fato chegando duas
    vezes ao celular é como se aprende a ignorar o canal."""
    fechou, eventos = _fechamentos(
        monkeypatch,
        corridas_abertas=lambda conn: [_corrida_dict(no_fim=18,
                                                     modo_fechamento="fim")],
        estado=lambda conn, c, dispensa_sem_linha=None:
            _estado(ok=["PIPE_A"], conta_para_fim=["PIPE_A"], linhas=1,
                    membros=1))
    assert GUARDIA.ciclo()["corridas_fechadas"] == 1
    assert [f[1] for f in fechou] == ["CONCLUIDA"]
    assert eventos == []


def test_com_no_fim_o_pendente_fora_do_fim_nao_impede_a_conclusao(monkeypatch):
    """§6.5 e §6.9/#2 — com `modo_fechamento='fim'`, quem decide são os membros
    que o Fim alcança. O que NÃO se afrouxa é a segunda cláusula: continua
    proibido fechar com qualquer membro do snapshot vivo (já provado acima).
    Sem ela, o Fim que não alcança todos seria o defeito do card mentiroso com
    outra roupa."""
    fechou, _ = _fechamentos(
        monkeypatch,
        corridas_abertas=lambda conn: [_corrida_dict(no_fim=18,
                                                     modo_fechamento="fim")],
        estado=lambda conn, c, dispensa_sem_linha=None:
            _estado(ok=["PIPE_A"], conta_para_fim=["PIPE_A"],
                    fora_do_fim=["PIPE_Z"],
                    pendentes=[{"pipeline": "PIPE_Z", "classe": "nao_partiu",
                                "desde": None, "faltante": None}],
                    linhas=1, membros=2))
    assert GUARDIA.ciclo()["corridas_fechadas"] == 1
    assert [f[1] for f in fechou] == ["CONCLUIDA"]


def _fechou_nada(*a, **k) -> bool:
    """`fechar_corrida` que devolve False: outra ponta chegou primeiro. Função
    nomeada (e não um `lambda: False`) para o cenário se ler como o fato."""
    return False


def test_outra_ponta_fechou_primeiro_nao_conta_e_nao_persiste_o_evento(
        monkeypatch):
    """Decisões 8 e 20 — `rowcount` de árbitro, e evento no MESMO commit.

    A API (F3) pode encerrar a corrida no exato instante em que a guardiã
    decide o desfecho. O `UPDATE` condicional devolve "não fui eu", e a resposta
    certa é desfazer TUDO: sem o rollback, o `MALHA_CONCLUIDA` já escrito
    ficaria pendurado na transação e sairia no lote junto com o
    `MALHA_CANCELADA` do operador — dois cards contando histórias opostas sobre
    a mesma corrida, e o card do canal é a superfície em que a confiança do
    plantão se perde primeiro.
    """
    desfeitos = []
    fechou, eventos = _fechamentos(
        monkeypatch,
        fechar_corrida=_fechou_nada,
        estado=lambda conn, c, dispensa_sem_linha=None:
            _estado(ok=["PIPE_A"], linhas=1, membros=1))
    monkeypatch.setattr(GUARDIA, "_rollback",
                        lambda conn: desfeitos.append("rollback"))
    assert GUARDIA.ciclo()["corridas_fechadas"] == 0
    assert desfeitos == ["rollback"]
    # o evento chegou a ser escrito na transação — e é justamente por isso que
    # o rollback é a única resposta possível
    assert [e["tipo"] for e in eventos] == ["MALHA_CONCLUIDA"]


# ═══════════════ 4. as três guardas da quiescência (§6.5) ═══════════════════

def test_guarda_1_linha_aguardando_e_liberada_adia_o_fechamento(monkeypatch):
    """Guarda 1 — a linha ordenada pelo New Day às 00:05, com a corrida aberta
    às 01:10, fica FORA do recorte de tempo e mesmo assim a rede de segurança
    vai dispará-la. Fechar aqui seria fechar a corrida no meio dela mesma."""
    fechou, _ = _fechamentos(
        monkeypatch,
        aguardando_do_snapshot=lambda conn, c: ["PIPE_B"],
        estado=lambda conn, c, dispensa_sem_linha=None:
            _estado(ok=["PIPE_A"], linhas=1, membros=2))
    _mundo(monkeypatch, liberado=lambda conn, p, d: (True, []))
    assert GUARDIA.ciclo()["corridas_fechadas"] == 0
    assert fechou == []


def test_guarda_1_nao_consegui_perguntar_nunca_vira_pode_fechar(monkeypatch):
    """A lição do `ERRO_CONSULTA`, literal: erro transitório de leitura adia o
    fechamento para o próximo ciclo. Adiar custa 5 min; fechar como FALHA uma
    corrida liberada custa o card mentiroso que a spec existe para matar."""
    fechou, _ = _fechamentos(
        monkeypatch,
        aguardando_do_snapshot=lambda conn, c: [GUARDIA.mc.ERRO_LEITURA],
        estado=lambda conn, c, dispensa_sem_linha=None:
            _estado(ok=["PIPE_A"], linhas=1, membros=1))
    assert GUARDIA.ciclo()["corridas_fechadas"] == 0
    assert fechou == []


def test_guarda_2_sem_quiescencia_nao_fecha(monkeypatch):
    """Guarda 2 — a carência existe porque o registro do SUCESSO commita e SÓ
    ENTÃO o disparo dos dependentes acontece: segundos no caminho feliz,
    minutos quando o push falha e a rede assume. Uma carência curta fecharia a
    corrida exatamente nessa fresta."""
    fechou, _ = _fechamentos(
        monkeypatch,
        relogios=lambda conn, c, car, qui: {"teto_vencido": False,
                                            "partida_vencida": True,
                                            "quiescente": False},
        estado=lambda conn, c, dispensa_sem_linha=None:
            _estado(ok=["PIPE_A"], linhas=1, membros=1))
    assert GUARDIA.ciclo()["corridas_fechadas"] == 0
    assert fechou == []


def test_guarda_3_no_retido_congela_relogios_e_desfechos(monkeypatch):
    """Decisão 30 — o defeito que já existe HOJE e que o teto pioraria.

    Um Aguarde segurado faz o predicado devolver False para o dependente, o que
    é literalmente "nenhum vivo, nenhum liberado": sem esta guarda a corrida
    fecharia como FALHA **por causa da trava que o próprio operador pôs**. E
    com o teto vencido ela seria encerrada sem terminar, também por causa da
    trava.
    """
    fechou, eventos = _fechamentos(
        monkeypatch,
        ha_no_retido=lambda conn, m: True,
        relogios=lambda conn, c, car, qui: {"teto_vencido": True,
                                            "partida_vencida": True,
                                            "quiescente": True},
        estado=lambda conn, c, dispensa_sem_linha=None:
            _estado(pendentes=[{"pipeline": "PIPE_B", "classe": "nao_liberou",
                                "desde": None, "faltante": None}],
                    ok=["PIPE_A"], linhas=2, membros=2))
    assert GUARDIA.ciclo()["corridas_fechadas"] == 0
    assert fechou == [] and eventos == []


def test_o_dia_do_membro_sem_linha_e_julgado_por_dia_permitido(monkeypatch):
    """§6.4 — "sem linha E dia não permitido" é DISPENSA, não pendência, e o
    julgamento REUSA `dia_permitido` (o mesmo de `_predecessor_esperado`) em
    vez de duplicá-lo dentro do módulo da corrida. Duas cópias da regra de
    agenda divergiriam no primeiro feriado."""
    capturado = {}

    def _estado_com_callback(conn, c, dispensa_sem_linha=None):
        capturado["A"] = dispensa_sem_linha("PIPE_A")
        capturado["B"] = dispensa_sem_linha("PIPE_B")
        capturado["Z"] = dispensa_sem_linha("PIPE_Z")
        return _estado(dispensados=["PIPE_A"], linhas=1, membros=1)

    def _config(conn, p):
        if p == "PIPE_A":       # semanal-domingo, e o ODATE é uma segunda
            return _cfg(regras_dia={"schedule_type": "weekly",
                                    "schedule_dow": 0})
        if p == "PIPE_B":
            return _cfg()
        return None             # sem cadastro

    _fechamentos(monkeypatch, estado=_estado_com_callback)
    _mundo(monkeypatch, config_dependente=_config)
    GUARDIA.ciclo()
    assert capturado["A"] is True        # dia não permitido → dispensado
    assert capturado["B"] is False       # dia livre → pendente, e nomeado
    # Sem cadastro NÃO dispensa: o membro aparece como pendente e a corrida diz
    # quem não rodou, em vez de dispensar em silêncio um pipeline que ninguém
    # sabe se devia rodar.
    assert capturado["Z"] is False


# ═══════════════ 5. o observador escopado pela corrida (§10/F2) ═════════════

_OBSERVADOR = {
    "malha": "M1", "no_id": 18, "tipo": "fim", "config": {},
    "criado_em": datetime(2026, 1, 1), "nos": [{"id": 18, "tipo": "fim"}],
    "arestas": [{"origem_no": None, "origem_pipeline": "PIPE_A",
                 "destino_no": 18, "destino_pipeline": None}],
}


def test_observador_usa_o_odate_da_corrida_aberta_e_carimba_o_id(monkeypatch):
    """§10/F2 — o observador passa a ler o ciclo em voo: uma cadeia longa pode
    ter começado antes de D-1, e a janela fixa não a alcançaria.

    E o evento carrega o id da corrida: sem ele, a idempotência do índice volta
    a ser por (pipeline, dia, tipo) e a SEGUNDA corrida da mesma malha no mesmo
    dia ficaria muda — que é o defeito que a 085 pôs a corrida na chave para
    resolver.
    """
    avaliadas, eventos = [], []
    _mundo(monkeypatch,
           nos_observadores=lambda conn: [_OBSERVADOR],
           pipelines_todos_sucesso=lambda conn, pipes, d:
               avaliadas.append(d) or True,
           gravar_evento=lambda conn, p, d, t, det, notificar=True, **kw:
               eventos.append((p, d, t, kw.get("malha_execucao_id"))) or True)
    _corrida(monkeypatch,
             corrida_aberta=lambda conn, m: _corrida_dict(id=31,
                                                          data_referencia=ONTEM))
    GUARDIA.ciclo()
    assert avaliadas == [ONTEM]          # só o ODATE da corrida, não {D-1, D}
    assert eventos == [("#no:18", ONTEM, "MALHA_CONCLUIDA", 31)]


def test_sem_corrida_aberta_a_janela_D_menos_1_e_D_volta_a_valer(monkeypatch):
    """A janela vira FALLBACK, não some: é o que vale com o interruptor
    desligado, sem a 085 e para malha sem corrida. E o id vem da corrida
    DAQUELA data (aberta ou fechada): gravar com o id enquanto ela está aberta
    e sem ele no ciclo seguinte produziria duas chaves distintas e DOIS cards
    para a mesma conclusão."""
    avaliadas, eventos = [], []
    _mundo(monkeypatch,
           nos_observadores=lambda conn: [_OBSERVADOR],
           pipelines_todos_sucesso=lambda conn, pipes, d:
               avaliadas.append(d) or (d == ODATE),
           gravar_evento=lambda conn, p, d, t, det, notificar=True, **kw:
               eventos.append((d, kw.get("malha_execucao_id"))) or True)
    _corrida(monkeypatch,
             corrida_aberta=lambda conn, m: None,
             corrida_da_data=lambda conn, m, d:
                 _corrida_dict(id=31, fechada_em=AGORA_BANCO,
                               status="CONCLUIDA") if d == ODATE else None)
    GUARDIA.ciclo()
    assert avaliadas == [ONTEM, ODATE]
    assert eventos == [(ODATE, 31)]      # a MESMA chave de quando estava aberta


def test_com_o_interruptor_desligado_o_observador_e_o_de_antes(monkeypatch):
    """A degradação do §16/10: com a corrida desligada o observador volta ao
    comportamento anterior byte a byte — janela {D-1, D} e evento SEM corrida.
    Nenhuma pergunta do módulo da corrida chega ao banco."""
    eventos = []

    def _proibido(*a, **k):
        raise AssertionError("interruptor desligado — nada da corrida")

    _mundo(monkeypatch,
           nos_observadores=lambda conn: [_OBSERVADOR],
           pipelines_todos_sucesso=lambda conn, pipes, d: d == ODATE,
           gravar_evento=lambda conn, p, d, t, det, notificar=True, **kw:
               eventos.append((d, kw.get("malha_execucao_id"))) or True)
    _corrida(monkeypatch, corrida_ativa=lambda conn: False,
             corrida_aberta=_proibido, corrida_da_data=_proibido)
    GUARDIA.ciclo()
    assert eventos == [(ODATE, None)]


# ═══════ 6. o predicado `estado` e os relógios, no módulo (§6.4/§6.5) ═══════

@pytest.fixture(scope="module")
def mc():
    spec = importlib.util.spec_from_file_location(
        "malha_corrida_f2", _ROOT / "dags/utils/malha_corrida.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Cursor:
    """Cursor de captura com respostas roteirizadas — o molde de
    tests/test_utils_dependencias.py."""

    def __init__(self, roteiro=None):
        self.roteiro = list(roteiro or [])
        self.execs: list = []
        self.rowcount = 0
        self._rows: list = []

    def execute(self, sql, params=()):
        self.execs.append((str(sql), tuple(params)))
        resposta = self.roteiro.pop(0) if self.roteiro else {}
        self._rows = list(resposta.get("rows", []))
        self.rowcount = resposta.get("rowcount", 0)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _Conn:
    def __init__(self, roteiro=None):
        self._cur = _Cursor(roteiro)

    def cursor(self):
        return self._cur


def _linha_estado(pipeline, conta_fim=1, ativo=1, raiz=0, status=None,
                  desde=None, orfa=0):
    return (pipeline, conta_fim, ativo, raiz, status, desde, orfa)


def test_estado_classifica_cada_membro_do_snapshot(mc):
    """§6.4, a tabela inteira numa passada — inclusive as duas linhas que a
    spec chama pelo nome: `PULADO` é DISPENSA (terminal legítimo, é o que já
    vale hoje) e `NAO_LIBEROU` é PENDÊNCIA com classe própria (Decisão 21: o
    painel diria "pendentes: A, B, C" e obrigaria o plantonista a abrir três
    telas para descobrir que são três problemas com três donos)."""
    linhas = [
        _linha_estado("P_OK", status="SUCESSO", desde=MOMENTO_ANCORA),
        _linha_estado("P_VIVO", status="EXECUTANDO", desde=MOMENTO_ANCORA),
        _linha_estado("P_ESPERA", status="AGUARDANDO_DEPENDENCIA"),
        _linha_estado("P_FALHOU", status="FALHA", desde=MOMENTO_ANCORA),
        _linha_estado("P_NAOLIB", status="NAO_LIBEROU"),
        _linha_estado("P_PULADO", status="PULADO"),
        _linha_estado("P_SEMLINHA", status=None),
        _linha_estado("P_INATIVO", ativo=0, status="SUCESSO"),
        _linha_estado("P_FORA_FIM", conta_fim=0, status="SUCESSO"),
    ]
    conn = _Conn([{"rows": linhas}, {"rows": [("P_OUTRO", ONTEM)]}])
    saida = mc.estado(conn, _corrida_dict(), dispensa_sem_linha=lambda p: False)

    assert saida["ok"] == ["P_FORA_FIM", "P_OK"]
    assert saida["vivos"] == ["P_ESPERA", "P_VIVO"]
    assert saida["dispensados"] == ["P_PULADO"]
    assert saida["inativos"] == ["P_INATIVO"]
    assert saida["fora_do_fim"] == ["P_FORA_FIM"]
    assert {p["pipeline"]: p["classe"] for p in saida["pendentes"]} == {
        "P_FALHOU": "falhou", "P_NAOLIB": "nao_liberou",
        "P_SEMLINHA": "nao_partiu"}
    assert saida["fora_do_odate"] == [{"pipeline": "P_OUTRO", "data": ONTEM}]
    assert saida["linhas"] == 8         # o membro sem linha não conta
    assert saida["membros"] == 9


def test_estado_membro_sem_linha_com_dia_fechado_e_dispensado(mc):
    conn = _Conn([{"rows": [_linha_estado("P", status=None)]}, {"rows": []}])
    saida = mc.estado(conn, _corrida_dict(), dispensa_sem_linha=lambda p: True)
    assert saida["dispensados"] == ["P"] and saida["pendentes"] == []


def test_estado_orfa_ja_alertada_sai_de_vivo_e_vira_pendente(mc):
    """Decisão 22 — o caso órfão mais comum do sistema (DagRun concluiu e a
    linha ficou EXECUTANDO, em que a guardiã corretamente se recusa a inventar
    verde e só alerta) viraria N horas de MALHA BLOQUEADA em vez de um alerta.
    A corrida fecha nomeando a linha órfã, que é a verdade, em vez de esperar
    24h para dizer que expirou."""
    conn = _Conn([{"rows": [_linha_estado("P", status="EXECUTANDO", orfa=1)]},
                  {"rows": []}])
    saida = mc.estado(conn, _corrida_dict(), dispensa_sem_linha=lambda p: False)
    assert saida["vivos"] == []
    assert [p["classe"] for p in saida["pendentes"]] == ["orfa"]


def test_estado_com_varias_linhas_o_vivo_vence_e_o_sucesso_apaga_a_falha(mc):
    """A prioridade do §6.4 quando o membro tem MAIS DE UMA linha viva no
    escopo — e o caso é real: `PULADO` do cron às 06:00 mais disparo manual às
    09:00, ou `FALHA` seguida de rerun bem-sucedido.

    `vivo` na frente de tudo (nunca fechar com trabalho em voo) e `ok` na
    frente de `falhou` — o MESMO julgamento de `liberado()` e do diagnóstico de
    predecessor falhado ("FALHA sem SUCESSO na data"). Sem isso a corrida iria
    a FALHA por causa da tentativa que o operador já consertou.
    """
    conn = _Conn([{"rows": [
        _linha_estado("P_RERUN", status="FALHA", desde=MOMENTO_ANCORA),
        _linha_estado("P_RERUN", status="SUCESSO", desde=MOMENTO_ANCORA),
        _linha_estado("P_MANUAL", status="PULADO"),
        _linha_estado("P_MANUAL", status="EXECUTANDO", desde=MOMENTO_ANCORA),
        # o par que decide a ordem entre `vivo` e `ok`: o membro concluiu de
        # manhã e está rodando DE NOVO agora (reprocesso dentro do ciclo). Se
        # `ok` vencesse, ele sairia do balde de vivos e a corrida poderia
        # fechar CONCLUIDA com a segunda execução ainda em voo — a invariante
        # §16/5 quebrada pelo caso mais comum de plantão
        _linha_estado("P_REEXEC", status="SUCESSO", desde=MOMENTO_ANCORA),
        _linha_estado("P_REEXEC", status="EXECUTANDO", desde=MOMENTO_ANCORA),
    ]}, {"rows": []}])
    saida = mc.estado(conn, _corrida_dict(), dispensa_sem_linha=lambda p: False)
    assert saida["ok"] == ["P_RERUN"]
    assert saida["vivos"] == ["P_MANUAL", "P_REEXEC"]
    assert saida["pendentes"] == []


def test_pulado_numa_linha_e_falha_em_outra_e_PROBLEMA_nao_dispensa(mc):
    """A última linha da ordem do §6.4, e a que muda o desfecho da corrida:
    `dispensado` fica ATRÁS dos pendentes.

    O caso é o do cron que pulou o membro às 06:00 e do disparo manual que
    falhou às 09:00. Se a dispensa vencesse, a corrida iria a `SEM_TRABALHO`
    ou a `CONCLUIDA` com uma FALHA embaixo — o card verde sobre trabalho
    quebrado, que é a família inteira de defeitos desta spec.
    """
    conn = _Conn([{"rows": [
        _linha_estado("P", status="PULADO"),
        _linha_estado("P", status="FALHA", desde=MOMENTO_ANCORA),
    ]}, {"rows": []}])
    saida = mc.estado(conn, _corrida_dict(), dispensa_sem_linha=lambda p: False)
    assert saida["dispensados"] == []
    assert [p["classe"] for p in saida["pendentes"]] == ["falhou"]


def test_as_classes_pendentes_declaradas_sao_as_que_o_predicado_PRODUZ(mc):
    """Amarração da Decisão 21: `CLASSES_PENDENTES` é o vocabulário que o
    painel da F4 vai usar para separar "rode o job de novo" de "solte a
    dependência" de "descubra por que a DAG nunca partiu".

    A tupla ainda não tem consumidor — e é justamente por isso que ela precisa
    de amarração agora: uma classe que o predicado produz e a tupla não declara
    (ou o contrário) só apareceria na F4, como um pendente que some do filtro
    do painel sem nenhum erro no caminho.
    """
    conn = _Conn([{"rows": [
        _linha_estado("P_FALHOU", status="FALHA", desde=MOMENTO_ANCORA),
        _linha_estado("P_ORFA", status="EXECUTANDO", orfa=1),
        _linha_estado("P_NAOLIB", status="NAO_LIBEROU"),
        _linha_estado("P_ESTRANHO", status="STATUS_QUE_AINDA_NAO_EXISTE"),
        # e os três que NÃO são pendência, para a igualdade valer nos dois
        # sentidos: nenhuma classe de fora da tupla cai no balde
        _linha_estado("P_OK", status="SUCESSO"),
        _linha_estado("P_VIVO", status="EXECUTANDO"),
        _linha_estado("P_PULADO", status="PULADO"),
    ]}, {"rows": []}])
    saida = mc.estado(conn, _corrida_dict(), dispensa_sem_linha=lambda p: False)
    assert {p["classe"] for p in saida["pendentes"]} == set(mc.CLASSES_PENDENTES)


def test_estado_status_desconhecido_e_pendente_nunca_vivo(mc):
    """Um status que o código não entende classificado como `vivo` congelaria a
    corrida até o teto — e o teto, por não poder matar vivo, só alarmaria. A
    corrida ficaria aberta para sempre bloqueando o disparo, que é o pior
    desfecho possível. Pendente é honesto e é terminal."""
    conn = _Conn([{"rows": [_linha_estado("P", status="ALGO_NOVO")]},
                  {"rows": []}])
    saida = mc.estado(conn, _corrida_dict(), dispensa_sem_linha=lambda p: False)
    assert saida["vivos"] == []
    assert [p["classe"] for p in saida["pendentes"]] == ["nao_partiu"]


def test_estado_degrada_sem_derrubar_o_ciclo(mc):
    """§16/10 — leitura degrada larga. Sem a 085 (ou com o banco fora por um
    instante) o fechador recebe "nada a fechar", nunca uma exceção que sobe até
    a task e derruba a guardiã inteira."""
    class _Explode(_Conn):
        def cursor(self):
            raise RuntimeError("Invalid object name 'dbo.etl_malha_execucao_membro'")

    saida = mc.estado(_Explode(), _corrida_dict())
    assert saida["vivos"] == [] and saida["pendentes"] == []
    assert saida["linhas"] == 0


def test_o_escopo_da_linha_exige_o_odate_nos_DOIS_ramos(mc):
    """Decisão 23 — o cenário real de plantão: às 3h o operador reprocessa
    `CARGA_B` para o dia 03 enquanto a corrida do dia 04 está aberta.

    Sem a exigência do ODATE no ramo do VÍNCULO, esse SUCESSO contaria como OK
    para o dia 04 — e se fosse o último pendente, a corrida fecharia
    `CONCLUIDA` sobre trabalho que não foi feito.
    """
    conn = _Conn([{"rows": []}, {"rows": []}])
    mc.estado(conn, _corrida_dict())
    sql, params = conn._cur.execs[0]
    normal = " ".join(sql.split())
    assert "e.data_referencia = %s" in normal
    assert ("(e.malha_execucao_id = %s OR COALESCE(e.inicio, e.criado_em) >= %s)"
            in normal)
    assert "e.substituida_em IS NULL" in normal
    assert params == (ODATE, 12, MOMENTO_ANCORA, 12)
    # e a segunda consulta é o espelho do mesmo predicado (§6.9/#15): a linha
    # que a corrida carimbou e cujo ODATE é OUTRO aparece nominalmente. Trocar
    # o `<>` por `=` devolveria as linhas certas do dia como se fossem
    # divergentes — o painel acusaria divergência exatamente quando não há
    sql_fora, params_fora = conn._cur.execs[1]
    normal_fora = " ".join(sql_fora.split())
    assert "e.malha_execucao_id = %s AND e.data_referencia <> %s" in normal_fora
    assert params_fora == (12, ODATE)


def test_aguardando_indisponivel_devolve_a_MARCA_nunca_lista_vazia(mc):
    """A outra ponta da guarda 1 — e a que o dublê da guardiã não pode provar.

    O cenário do fechador injeta `ERRO_LEITURA` e prova que a guardiã adia o
    fechamento; isso só vale se o MÓDULO de fato devolver a marca quando a
    consulta falha. Devolver `[]` diria "não há ninguém aguardando" com base
    numa pergunta que não foi respondida, e a corrida fecharia — como FALHA —
    por causa de um timeout de 200 ms. É a política do `ERRO_CONSULTA`, e é
    aqui que ela nasce.
    """
    class _Explode(_Conn):
        def cursor(self):
            raise RuntimeError("Adaptive Server connection timed out")

    assert mc.aguardando_do_snapshot(_Explode(), _corrida_dict()) == \
        [mc.ERRO_LEITURA]
    # e no caminho normal a lista é dos MEMBROS do snapshot naquele ODATE —
    # nunca de qualquer linha aguardando do banco inteiro
    conn = _Conn([{"rows": [("PIPE_B",)]}])
    assert mc.aguardando_do_snapshot(conn, _corrida_dict()) == ["PIPE_B"]
    sql, params = conn._cur.execs[0]
    normal = " ".join(sql.split())
    assert "JOIN dbo.etl_malha_execucao_membro m ON m.malha_execucao_id = %s" in normal
    assert "e.status = 'AGUARDANDO_DEPENDENCIA'" in normal
    assert params == (12, ODATE)


def test_a_marca_da_orfa_no_predicado_e_a_MESMA_da_guardia(mc):
    """Amarração de grafia: a classificação `orfa` do §6.4 depende do tipo de
    evento que a guardiã emite. Renomear um sem o outro faria a corrida parar
    de reconhecer a órfã em silêncio — e voltaria a bloquear a malha por horas
    em vez de fechar nomeando a linha."""
    assert mc.EVENTO_ORFA == GUARDIA.EVENTO_ORFA
    assert GUARDIA.EVENTO_ORFA in mc.SQL_ESTADO


def test_os_relogios_sao_todos_do_banco(mc):
    """Decisão 10 e invariante §16/9 — o teste que o relógio deslocado do dev
    (SQL Server ~3h à frente do worker) transformaria em falha se alguém
    trouxesse a conta para Python.

    As três respostas saem de UMA consulta: fossem três, seriam três idas ao
    banco por corrida por ciclo e a terceira poderia ler um instante diferente
    da primeira.
    """
    conn = _Conn([{"rows": [(1, 0, 1)]}])
    saida = mc.relogios(conn, _corrida_dict(), 15, 20)
    assert saida == {"teto_vencido": True, "partida_vencida": False,
                     "quiescente": True}
    sql, params = conn._cur.execs[0]
    assert len(conn._cur.execs) == 1
    assert "SYSDATETIME()" in sql and "DATEADD(MINUTE" in sql
    assert params == (15, 20, 20, 12)
    # a âncora da quiescência é o trabalho, NUNCA `atualizado_em` — que os
    # gestos administrativos (equalizar, marcar substituídas) bumpam sem que
    # nada tenha rodado, reiniciando o relógio de graça
    assert "COALESCE(e.fim, e.inicio, e.criado_em)" in " ".join(sql.split())
    assert "atualizado_em" not in sql


def test_relogio_indisponivel_nao_produz_desfecho_por_tempo(mc):
    class _Explode(_Conn):
        def cursor(self):
            raise RuntimeError("timeout")
    assert mc.relogios(_Explode(), _corrida_dict(), 15, 15) == {
        "teto_vencido": False, "partida_vencida": False, "quiescente": False}


def test_hold_indisponivel_assume_retido_e_ausente_assume_livre(mc):
    """As duas degradações do hold, e elas são OPOSTAS de propósito:

      • sem a coluna (075/082 fora) não existe nó, logo não há retenção →
        False, e a corrida fecha normalmente;
      • com a coluna presente e a consulta falhando → True. "Não consegui
        perguntar" nunca pode virar "pode fechar": adiar custa um ciclo de 5
        min, fechar como FALHA por causa de um timeout custa o card mentiroso.
    """
    class _SemColuna(_Conn):
        def cursor(self):
            raise Exception("(207) Invalid column name 'retido_em'.")

    class _Timeout(_Conn):
        def cursor(self):
            raise RuntimeError("Adaptive Server connection timed out")

    assert mc.ha_no_retido(_SemColuna(), "M1") is False
    assert mc.ha_no_retido(_Timeout(), "M1") is True
    assert mc.ha_no_retido(_Conn([{"rows": [(2,)]}]), "M1") is True
    assert mc.ha_no_retido(_Conn([{"rows": [(0,)]}]), "M1") is False


def test_a_busca_das_partidas_exclui_o_que_a_corrida_ja_cobriu(mc):
    """O laço que converge. Duas pernas, e cada uma resolve um caso real:

      • a linha JÁ carimbada por uma corrida desta malha — é o laço do sábado:
        o `PULADO` das 06:00 abre a corrida, ela fecha imediatamente, e sem
        esta perna o ciclo das 06:05 abriria a corrida #2, o das 06:10 a #3, e
        o dia sairia com 288 corridas;
      • a linha DENTRO do intervalo de uma corrida FECHADA desta malha — é o
        membro compartilhado: um pipeline de quatro malhas carimba a corrida de
        UMA (a coluna é proveniência, tem um dono só) e as outras três precisam
        de outro critério para saber que já viram aquela linha.

    A corrida ABERTA de propósito NÃO exclui: enquanto ela está aberta, cada
    raiz que parte tem de passar pela conferência de ODATE da Decisão 15.
    """
    conn = _Conn([{"rows": []}])
    mc.partidas_a_cobrir(conn, "M1", ["PIPE_B", "PIPE_A"], (ONTEM, ODATE), 24)
    sql, params = conn._cur.execs[0]
    normal = " ".join(sql.split())
    assert "e.malha_execucao_id = me.id" in normal
    assert "me.fechada_em IS NOT NULL" in normal
    assert "DATEADD(HOUR, -%s, SYSDATETIME())" in normal
    # A perna do INTERVALO — e SÓ ela — exige o mesmo ODATE (achado da revisão
    # adversarial, as duas metades medidas no dev). Sem a cláusula, a corrida de
    # D-1 que atravessou a virada "cobre" a madrugada de D e o ciclo de D nunca
    # abre: dia inteiro sem corrida, sem card e sem alarme. Com a cláusula na
    # perna da PROVENIÊNCIA, a linha âncora de ODATE divergente (que nasce
    # `fora_do_odate` por construção, §6.2) nunca contaria como coberta e a
    # guardiã abriria uma corrida `ABORTADA` a cada 5 min. A posição é o teste.
    assert ("me.fechada_em IS NOT NULL "
            "AND e.data_referencia = me.data_referencia") in normal
    assert "e.malha_execucao_id = me.id AND e.data_referencia" not in normal
    # ordenado e deduplicado: o mesmo conjunto produz sempre os mesmos
    # parâmetros, e o cache de plano do SQL Server vê UM statement
    assert params == ("PIPE_A", "PIPE_B", ONTEM, ODATE) + mc.STATUS_PARTIU \
        + (24, "M1")
    assert "PULADO" in mc.STATUS_PARTIU          # é ele que abre o sábado
    assert "AGUARDANDO_DEPENDENCIA" not in mc.STATUS_PARTIU
    assert "NAO_LIBEROU" not in mc.STATUS_PARTIU


def test_a_proveniencia_cobre_a_linha_mesmo_com_ODATE_divergente(mc):
    """A metade oposta do achado anterior, e a mais fácil de errar consertando
    a primeira.

    Quando a linha âncora carimbou um ODATE diferente do canônico — o
    `Carga_Vida` literal — a corrida nasce com o canônico e a linha entra
    `fora_do_odate` (§6.2): as duas datas divergem **por construção**. Se a
    perna da proveniência exigisse `e.data_referencia = me.data_referencia`, a
    linha jamais contaria como coberta e a guardiã abriria uma corrida nova a
    cada 5 min — cada uma fechando `ABORTADA` e mandando dois cards ao Teams.
    Medido no dev: 3 corridas em 3 ciclos, 6 eventos.

    Proveniência é DONA (Decisão 1, write-once), não data.

    A asserção olha o RAMO, não a presença do texto: a cláusula posta antes do
    grupo `OR` (isto é, aplicada às duas pernas de uma vez) é indistinguível
    por `in`/`not in` e foi justamente a primeira tentativa de conserto desta
    revisão — o teste tem de pegá-la."""
    sql = " ".join(mc.sql_partidas(1).split())
    corpo = sql.split("FROM dbo.etl_malha_execucao me")[1]
    # tudo que vale para as DUAS pernas mora entre o `me.malha_name` e o `OR`
    comum = corpo.split("OR (me.fechada_em IS NOT NULL")[0]
    assert "data_referencia" not in comum
    intervalo = corpo.split("OR (me.fechada_em IS NOT NULL")[1]
    assert "e.data_referencia = me.data_referencia" in intervalo


def test_lista_de_pipelines_vazia_nunca_vira_IN_vazio(mc):
    """Não há `IN ()` em T-SQL: lista vazia vira `1 = 0`. Omitir a cláusula
    varreria a maior tabela do schema num caminho que roda a cada 5 min."""
    assert "1 = 0" in mc.sql_partidas(0)
    assert "IN ()" not in mc.sql_partidas(0)
    assert mc.partidas_a_cobrir(_Conn(), "M1", [], (ONTEM, ODATE), 24) == []


def test_o_carimbo_na_linha_e_idempotente_e_alcanca_o_membro_compartilhado(mc):
    """Duas coisas, e a segunda foi MEDIDA no dev antes de virar teste.

    A idempotência: a guardiã passa a cada 5 min e o carimbo é o mesmo — sem o
    `NOT LIKE`, o motivo viraria uma parede de repetições em algumas horas.

    E a ausência da guarda por `malha_execucao_id IS NULL`: com `DEV_F10_A`
    membro de QUATRO malhas no dev, a corrida da primeira carimbava a linha e a
    recusa por ODATE divergente da segunda (Decisão 15) ficava sem gravar o
    motivo — `rowcount = 0`, diagnóstico perdido, e justamente no caso do
    §6.9/#6, que é o mais difícil de entender de plantão. Quem chama já garante
    o que a guarda tentava garantir.
    """
    conn = _Conn([{"rowcount": 1}])
    assert mc.carimbar_motivo(conn, "PIPE_A", ODATE, "run_1",
                              mc.MOTIVO_FORA_DA_CORRIDA, "texto") is True
    sql, params = conn._cur.execs[0]
    assert "malha_execucao_id" not in sql
    assert "motivo NOT LIKE %s" in sql
    assert params[-1] == "%" + mc.MOTIVO_FORA_DA_CORRIDA + "%"


def test_heartbeat_carimba_com_o_relogio_do_banco(mc):
    """O valor é convertido pelo BANCO. Um `isoformat()` do worker gravaria
    aqui um instante 3h atrasado, e a F3 concluiria que a guardiã está morta
    justamente quando ela acabou de passar."""
    conn = _Conn([{"rowcount": 1}])
    assert mc.marcar_heartbeat(conn) is True
    sql, params = conn._cur.execs[0]
    assert "CONVERT(VARCHAR(19), SYSDATETIME(), 120)" in sql
    assert params == ("guardia", mc.CHAVE_HEARTBEAT)
    # chave ausente → cria, sem MERGE (duas guardiãs em paralelo)
    conn = _Conn([{"rowcount": 0}, {"rowcount": 1}])
    assert mc.marcar_heartbeat(conn) is True
    assert "WHERE NOT EXISTS" in conn._cur.execs[1][0]


def test_heartbeat_lido_compara_no_banco(mc):
    conn = _Conn([{"rows": [("2026-08-05 04:00:00", 1)]}])
    assert mc.heartbeat_guardia(conn, 15) == {
        "visto_em": "2026-08-05 04:00:00", "recente": True}
    sql, params = conn._cur.execs[0]
    assert "DATEADD(MINUTE, -%s, SYSDATETIME())" in sql
    assert params == (15, mc.CHAVE_HEARTBEAT)
    assert mc.heartbeat_guardia(_Conn([{"rows": []}])) == {"visto_em": None,
                                                           "recente": False}


# ═══════════════ 7. as invariantes sintáticas da fase ═══════════════════════

def test_nenhuma_conta_de_tempo_em_python_nas_responsabilidades_novas():
    """Decisão 10 / invariante §16/9 — o defeito é sintático, então o teste é
    sintático.

    O que se proíbe: `datetime.now`, `date.today` e aritmética de `timedelta`
    dentro das funções da corrida. O `timedelta(days=1)` da janela {D-1, D} é a
    ÚNICA exceção e é de DATA, não de relógio: ele desloca um ODATE já
    calculado pelo banco, e é o mesmo gesto que o observador faz desde a F14.
    """
    fonte = (_ROOT / "dags/etl_dependencia_guardia.py").read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    alvos = {"_abrir_corridas_malha", "_abrir_uma_corrida",
             "_fechar_corridas_malha", "_fechar_uma_corrida",
             "_carimbar_fora_da_corrida", "_corrida_habilitada",
             "_porta_da_malha", "_quiescencia_liberada"}
    for no in ast.walk(arvore):
        if not (isinstance(no, ast.FunctionDef) and no.name in alvos):
            continue
        texto = ast.unparse(no)
        for proibido in ("datetime.now", "date.today", "_agora()",
                         "pendulum.now"):
            assert proibido not in texto, (no.name, proibido)
        # só a janela de DATAS pode usar timedelta, e só com days
        for uso in re.findall(r"timedelta\(([^)]*)\)", texto):
            assert uso.startswith("days="), (no.name, uso)


def test_o_modulo_da_corrida_nao_faz_conta_de_tempo(mc):
    """O mesmo, do lado do módulo: `SYSDATETIME`/`DATEADD` no SQL e nenhuma
    importação de relógio em Python. É o que faz o teto e a carência se
    comportarem igual com o banco 3h à frente do worker."""
    # Por AST: o módulo EXPLICA em docstring por que não usa `datetime.now()`,
    # e um `in` cru transformaria a explicação correta em falha de teste.
    arvore = ast.parse(inspect.getsource(mc))
    for no in ast.walk(arvore):
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute):
            assert no.func.attr not in ("now", "today", "utcnow"), \
                ast.unparse(no)
    assert "SYSDATETIME()" in mc.SQL_RELOGIOS
    assert "SYSDATETIME()" in mc.sql_partidas(1)


def test_a_guardia_continua_sem_uma_linha_de_sql():
    """Decisão 15 do desenho da F4, estendida à fase: TODA pergunta mora nos
    módulos de `utils/`. O teste existente já cobre as três tabelas antigas;
    aqui se acrescentam as duas da 085, para que a próxima fase não comece a
    escrever SQL solto na guardiã por conveniência."""
    fonte = (_ROOT / "dags/etl_dependencia_guardia.py").read_text(encoding="utf-8")
    for tabela in ("etl_malha_execucao", "etl_malha_execucao_membro",
                   "etl_malha_pipeline"):
        assert tabela not in fonte, tabela


def test_a_ordem_das_responsabilidades_no_ciclo(monkeypatch):
    """§6.3 — `_abrir_corridas_malha` ANTES do observador (ele passa a ler o
    ODATE do ciclo em voo, e a corrida aberta neste mesmo ciclo já vale para
    ele) e `_fechar_corridas_malha` DEPOIS dele e ANTES do Teams (o card do
    desfecho sai no lote do MESMO ciclo, e o observador do nó Fim ainda enxerga
    a corrida aberta quando grava a conclusão)."""
    ordem = []
    _mundo(monkeypatch)
    _corrida(monkeypatch)
    for nome in ("_abrir_corridas_malha", "_observadores_malha",
                 "_fechar_corridas_malha", "_notificar"):
        original = getattr(GUARDIA, nome)

        def _espia(*a, _nome=nome, _orig=original, **k):
            ordem.append(_nome)
            return _orig(*a, **k)
        monkeypatch.setattr(GUARDIA, nome, _espia)
    GUARDIA.ciclo()
    assert ordem == ["_abrir_corridas_malha", "_observadores_malha",
                     "_fechar_corridas_malha", "_notificar"]


# ═══ 8. o relógio deslocado (Decisão 10) — comportamento, não só sintaxe ═════
#
# O bloco 7 prova que a conta de tempo não está escrita em Python. Este prova o
# que aquilo COMPRA: com o SQL Server ~3h à frente do worker — o caso MEDIDO no
# dev, e a forma como este bug aparece —, o ciclo decide igual. Os dois testes
# movem o relógio do WORKER e mantêm o do BANCO, que é a decomposição que uma
# asserção sintática não consegue fazer: `_agora()` continua existindo na
# guardiã (as cinco responsabilidades antigas dependem dele), então o que se
# tem de provar é que ele não chega nas responsabilidades da corrida.

def test_o_dia_do_ciclo_sai_do_relogio_do_BANCO_e_nao_do_worker(monkeypatch):
    """§6.2 — o ODATE e a janela {D-1, D} da abertura saem de
    `agora_do_banco`, nunca do relógio da máquina que roda a task.

    Com o worker atrasado 3h em relação ao banco, uma janela derivada do worker
    ficaria um dia atrás durante as três primeiras horas do dia do banco: a
    guardiã procuraria as partidas de ontem, não acharia a raiz que acabou de
    partir e **nenhuma corrida abriria na madrugada** — o pior horário para
    descobrir isso. É a mesma classe do achado que fez `agora_do_banco` nascer
    (o DATA_DIVERGENTE falso diário da F4, com o banco em UTC e a guardiã
    em -03).
    """
    def _cenario(relogio_worker, relogio_banco):
        vistos = []
        _mundo(monkeypatch, agora=relogio_worker,
               malhas_ativas_com_desenho=lambda conn: [_SEM_INICIO],
               agora_do_banco=lambda conn: relogio_banco)
        _corrida(monkeypatch,
                 raizes_da_malha=lambda conn, m: ["PIPE_A"],
                 # o dublê DERIVA o ODATE do momento recebido — que é o que a
                 # função real faz (`calcular(momento, virada)`). Um dublê que
                 # devolvesse uma constante responderia a mesma coisa para os
                 # dois relógios e provaria a si mesmo.
                 odate_da_abertura=lambda conn, m, momento: momento.date(),
                 partidas_a_cobrir=lambda conn, m, pipes, datas, teto:
                     vistos.append(tuple(datas)) or [])
        GUARDIA.ciclo()
        return vistos[0]

    referencia = _cenario(AGORA, AGORA_BANCO)
    assert referencia == (ONTEM, ODATE)
    # o worker anda para os dois lados e o ciclo não se mexe
    assert _cenario(AGORA - timedelta(hours=3), AGORA_BANCO) == referencia
    assert _cenario(AGORA + timedelta(hours=15), AGORA_BANCO) == referencia
    # e quando é o BANCO que atravessa a virada, a janela acompanha ELE
    amanha = AGORA_BANCO + timedelta(days=1)
    assert _cenario(AGORA, amanha) == (ODATE, amanha.date())


def test_teto_e_carencia_decidem_pelo_banco_com_o_worker_3h_deslocado(
        monkeypatch):
    """§10/F2, aceite literal — "relógio do banco deslocado 3h do worker: o
    teto e a carência se comportam igual".

    O cenário é o do dev: o banco está à frente e, PARA ELE, o teto já venceu.
    Se qualquer desfecho consultasse o relógio do worker, a mesma corrida
    expiraria ou não conforme a máquina que pegou o ciclo — e com dois workers
    a resposta mudaria de ciclo para ciclo, que é a pior forma do defeito
    (irreprodutível de plantão).

    A carência de partida vai junto porque ela é a outra metade: com o worker
    atrasado, uma conta em Python acharia que a corrida "acabou de abrir" e
    nunca abortaria a corrida que nunca começou — e corrida aberta bloqueia o
    disparo.
    """
    teto = MOMENTO_ANCORA + timedelta(hours=24)
    corrida = _corrida_dict(teto_em=teto)

    def _relogios_do_banco(relogio_banco):
        """O dublê responde o que o BANCO responderia — as três comparações do
        `SQL_RELOGIOS`, feitas sobre o relógio dele."""
        def _rel(conn, c, carencia, quiescencia):
            return {
                "teto_vencido": relogio_banco > c["teto_em"],
                "partida_vencida":
                    relogio_banco > c["aberta_em"] + timedelta(minutes=carencia),
                "quiescente": False,
            }
        return _rel

    def _cenario(relogio_worker, relogio_banco, est):
        fechou, eventos = _fechamentos(
            monkeypatch, agora=relogio_worker,
            corridas_abertas=lambda conn: [dict(corrida)],
            relogios=_relogios_do_banco(relogio_banco),
            estado=lambda conn, c, dispensa_sem_linha=None: est)
        GUARDIA.ciclo()
        return [f[1] for f in fechou], [e["tipo"] for e in eventos]

    tres_relogios = (AGORA - timedelta(hours=3), AGORA, AGORA_BANCO)
    quiesceu = _estado(ok=["PIPE_A"], linhas=1, membros=1)
    vazia = _estado(pendentes=[{"pipeline": "PIPE_A", "classe": "nao_partiu",
                                "desde": None, "faltante": None}],
                    linhas=0, membros=1)

    # ── o teto ──────────────────────────────────────────────────────────────
    # para o BANCO o teto venceu (01:10 + 24h < 02:10 do dia seguinte)
    depois = teto + timedelta(hours=1)
    for worker in tres_relogios:
        assert _cenario(worker, depois, quiesceu) == \
            (["EXPIRADA"], ["MALHA_EXPIRADA"]), worker
    # e para o banco AINDA não venceu — nada fecha, com qualquer worker
    antes = teto - timedelta(hours=1)
    for worker in tres_relogios:
        assert _cenario(worker, antes, quiesceu) == ([], []), worker

    # ── a carência de partida ───────────────────────────────────────────────
    # 15 min depois de `aberta_em`, pelo relógio do BANCO
    for worker in tres_relogios:
        assert _cenario(worker, MOMENTO_ANCORA + timedelta(minutes=16),
                        vazia) == (["ABORTADA"], ["MALHA_ABORTADA"]), worker
    for worker in tres_relogios:
        assert _cenario(worker, MOMENTO_ANCORA + timedelta(minutes=5),
                        vazia) == ([], []), worker
