"""
F4 — DAG guardiã (dags/etl_dependencia_guardia.py) com Airflow stubado
(docs/retomada-f4-desenho.md §12; suíte docs/retomada-aceitacao.md, causa D).

Mesma técnica do test_ds_supervisao_dag: o erro mais caro é o de import time
(DAG que não carrega não aparece no scheduler e a guardiã fica muda), então o
módulo inteiro é executado com stubs — imports, Variables e montagem da DAG.

O CICLO é exercitado com as perguntas ao banco stubadas função a função sobre
o módulo REAL utils.dependencias (o que se testa aqui é o orquestração do
ciclo: ordem, guardas, contadores e efeitos) e com as costuras de Airflow
(_dag_pausada/_dagrun_existe/_trigger) e o relógio (_agora) injetados. As
funções PURAS (candidatos, deadline, dia_permitido, montar_conf, novo_run_id)
rodam de verdade.
"""
from __future__ import annotations

import importlib.util
import logging
import re
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_ROOT = Path(__file__).parent.parent
_DAGS = _ROOT / "dags"
if str(_DAGS) not in sys.path:
    sys.path.insert(0, str(_DAGS))

_STUBS = [
    "airflow", "airflow.models", "airflow.operators", "airflow.operators.python",
    "airflow.api", "airflow.api.client", "airflow.api.client.local_client",
    "airflow.providers", "airflow.providers.microsoft",
    "airflow.providers.microsoft.mssql", "airflow.providers.microsoft.mssql.hooks",
    "airflow.providers.microsoft.mssql.hooks.mssql",
    "pendulum",
]
for _m in _STUBS:
    sys.modules.setdefault(_m, MagicMock())

# Stubs PRÓPRIOS de DAG/PythonOperator, com snapshot logo após a carga: os
# módulos-stub são compartilhados entre arquivos de teste e outro arquivo
# pode reatribuí-los depois — o snapshot congela o que ESTA DAG declarou.
_DAG_STUB = MagicMock()
_DAG_STUB.return_value.__enter__ = lambda self: self
_DAG_STUB.return_value.__exit__ = lambda self, *a: False
sys.modules["airflow"].DAG = _DAG_STUB
_OP_STUB = MagicMock()
sys.modules["airflow.operators.python"].PythonOperator = _OP_STUB


def _variable_ausente(chave, *a, **k):
    """Variable.get de MagicMock devolveria um mock que int() converte em 1
    — mascarando os defaults. Ausente de verdade levanta, como o Airflow."""
    raise KeyError(chave)


sys.modules["airflow.models"].Variable.get = _variable_ausente


def _carregar():
    spec = importlib.util.spec_from_file_location(
        "etl_dependencia_guardia_test", _DAGS / "etl_dependencia_guardia.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GUARDIA = _carregar()
# A função REAL, capturada antes de qualquer `monkeypatch` — é o que permite um
# cenário exercitar a leitura de produção em vez de um dublê dela.
_APP_BASE_URL_DE_PRODUCAO = GUARDIA.dep.app_base_url
DAG_KWARGS = dict(_DAG_STUB.call_args.kwargs)
OP_KWARGS = dict(_OP_STUB.call_args.kwargs)
OP_CHAMADAS = _OP_STUB.call_count

# Segunda-feira 2026-08-03, 09:00 — o "agora" padrão dos cenários.
AGORA = datetime(2026, 8, 3, 9, 0)
HOJE = date(2026, 8, 3)

_CFG_LIVRE = {"regras_dia": {}, "nao_iniciar_antes": None, "hora_limite": None}


def _cfg(**kw) -> dict:
    base = {"regras_dia": {}, "nao_iniciar_antes": None, "hora_limite": None}
    base.update(kw)
    return base


def _mundo(monkeypatch, agora=AGORA, **sobrescreve):
    """Zera o mundo do ciclo (toda pergunta ao banco stubada em cima do
    módulo REAL utils.dependencias) e aplica as sobrescritas do cenário."""
    base = {
        "tabelas_067_presentes": lambda conn: True,
        "agora_do_banco": lambda conn: agora,
        "corridas_aguardando": lambda conn: [],
        "dependentes_com_dependencia": lambda conn: [],
        "predecessores_de": lambda conn, p: [],
        "virada_efetiva": lambda conn, p: time(0, 0),
        "config_dependente": lambda conn, p: _cfg(),
        # F6: a assinatura ganhou `corrida` (a da LINHA avaliada). O dublê
        # a aceita para que uma porta que a passe seja EXERCITADA aqui, e
        # não caia calada na rede de `TypeError` do fonte gerado.
        "liberado": lambda conn, p, d, corrida=None: (False, ["PIPE_A"]),
        "resumo_predecessores": lambda conn, p, d: {},
        "sucesso_recente_outra_data": lambda conn, p, d, inicio: [],
        "reservas_orfas": lambda conn, idade: [],
        "resgatar_reserva": lambda conn, p, d, r: True,
        # F5 §4.3 — corrida que COMEÇOU e cujo DagRun morreu sem fechar nada.
        "corridas_em_execucao": lambda conn, idade: [],
        "fechar_orfa_em_execucao": lambda conn, p, d, r, m: True,
        "fechar_nao_liberou": lambda conn, p, d, r, m: True,
        "gravar_evento": lambda conn, p, d, t, det, **kw: True,
        "eventos_nao_notificados": lambda conn, lim, jan: [],
        "marcar_notificado": lambda conn, i: None,
        "canal_teams_supervisao": lambda conn: None,
        # F11 (Decisão 69): o endereço do app. O DEFAULT do dublê é o mesmo
        # default de produção — vazio, migration 086 —, para que o cenário que
        # não fala de botão exercite o card SEM botão.
        "app_base_url": lambda conn: "",
        "reservar_corrida": lambda conn, p, d, rid, o: rid,
        "ordenar_corrida": lambda conn, p, d, rid, o: True,
        "devolver_reserva": lambda conn, p, d, rid, veio_de_adocao: None,
        # F14 — observadores de malha (base: migration presente, zero nós).
        "tabela_075_presente": lambda conn: True,
        "nos_observadores": lambda conn: [],
        "pipelines_todos_sucesso": lambda conn, pipes, d: False,
    }
    base.update(sobrescreve)
    for nome, fn in base.items():
        monkeypatch.setattr(GUARDIA.dep, nome, fn)
    monkeypatch.setattr(GUARDIA.Variable, "get", _variable_ausente)
    monkeypatch.setattr(GUARDIA, "_agora", lambda: agora)
    monkeypatch.setattr(GUARDIA, "_dag_pausada", lambda dag_id: False)
    monkeypatch.setattr(GUARDIA, "_dagrun_existe", lambda dag_id, run_id: False)
    monkeypatch.setattr(GUARDIA, "_trigger", lambda dag_id, run_id, conf: None)


def _linha(pipeline="PIPE_C", data_ref=HOJE, run_id="guardia__ja",
           criado_em=None):
    return (pipeline, data_ref, run_id,
            criado_em or datetime(2026, 8, 3, 6, 0))


# ═══════════════ §12.11 — carga da DAG, Variables e estrutura ═══════════════

def test_dag_carrega_com_uma_task_max_active_runs_e_catchup():
    assert DAG_KWARGS["dag_id"] == "etl_dependencia_guardia"
    assert DAG_KWARGS["max_active_runs"] == 1
    assert DAG_KWARGS["catchup"] is False
    assert DAG_KWARGS["schedule"] == "*/5 * * * *"      # default 5 (D47)
    assert OP_CHAMADAS == 1                             # UMA task: o ciclo
    assert OP_KWARGS["task_id"] == "ciclo"
    assert OP_KWARGS["execution_timeout"] == timedelta(minutes=4)


def test_nada_no_default_args_referencia_helper():
    """Gotcha D56 (vale também para DAG manuscrita): default_args só com
    valores simples — nenhum callable/helper."""
    assert all(not callable(v) for v in GUARDIA.default_args.values())


@pytest.mark.parametrize("bruto,esperado", [
    ("5", 5), ("15", 15), ("1", 1), ("59", 59),
    ("0", 5), ("60", 5), ("-3", 5), ("lixo", 5), ("", 5),
])
def test_intervalo_nunca_derruba_o_import(monkeypatch, bruto, esperado):
    """D47: ausente, lixo, 0 ou 60 → default 5 (*/60 é cron inválido)."""
    monkeypatch.setattr(GUARDIA.Variable, "get", lambda *a, **k: bruto)
    assert GUARDIA._intervalo() == esperado


def test_intervalo_com_variable_ausente(monkeypatch):
    def _explode(*a, **k):
        raise KeyError("Variable does not exist")
    monkeypatch.setattr(GUARDIA.Variable, "get", _explode)
    assert GUARDIA._intervalo() == 5


def test_lote_de_notificacao_com_clamp_minimo(monkeypatch):
    monkeypatch.setattr(GUARDIA.Variable, "get", lambda *a, **k: "0")
    assert GUARDIA._lote_notificacao() == 1
    monkeypatch.setattr(GUARDIA.Variable, "get", lambda *a, **k: "lixo")
    assert GUARDIA._lote_notificacao() == 50


def test_zero_sql_no_fonte_da_dag():
    """Decisão 15: NENHUMA pergunta ao banco mora na DAG — nem sobre as
    tabelas de dependência (assert do desenho §9) nem sobre nenhuma outra
    (até a sonda da 067 mora no módulo)."""
    import ast
    fonte = (_DAGS / "etl_dependencia_guardia.py").read_text(encoding="utf-8")
    for tabela in ("etl_pipeline_execucao", "etl_pipeline_dependencia",
                   "etl_dependencia_evento"):
        assert tabela not in fonte, tabela
    sql_re = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|MERGE)\b", re.I)
    constantes = [n.value for n in ast.walk(ast.parse(fonte))
                  if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    suspeitas = [c for c in constantes if "dbo." in c or sql_re.search(c)]
    assert not suspeitas, suspeitas


def test_sem_067_o_ciclo_termina_limpo(monkeypatch):
    """D52: sonda diz que falta migration → log e retorno limpo; NENHUMA
    outra pergunta é feita (nunca o except mudo do gotcha do placeholder)."""
    tocou = []
    _mundo(monkeypatch,
           tabelas_067_presentes=lambda conn: False,
           corridas_aguardando=lambda conn: tocou.append("varredura") or [],
           dependentes_com_dependencia=lambda conn: tocou.append("universo") or [])
    assert GUARDIA.ciclo() == {"migration_067": False}
    assert tocou == []


# ═══════════════════════ §12.3 — New Day (D44/D45/D48) ══════════════════════

def test_new_day_ordena_com_run_id_guardia(monkeypatch):
    ordens = []
    _mundo(monkeypatch,
           dependentes_com_dependencia=lambda conn: ["PIPE_C"],
           predecessores_de=lambda conn, p: ["PIPE_A"],
           resumo_predecessores=lambda conn, p, d: {"PIPE_A": set()},
           ordenar_corrida=lambda conn, p, d, rid, o:
               ordens.append((p, d, rid, o)) or True)
    saida = GUARDIA.ciclo()
    assert saida["ordenadas"] == 1
    p, d, rid, origem = ordens[0]
    assert (p, d, origem) == ("PIPE_C", HOJE, "guardia")
    assert rid.startswith("guardia__2026-08-03__PIPE_C__")
    assert len(rid) <= 250


def test_new_day_nao_ordena_dependente_fora_do_dia(monkeypatch):
    """C mensal do dia 5 num dia 3: não é previsto — nada é criado e nada
    alerta (a raiz do fim do JANELA_ESTOUROU de fim de semana, §5.3)."""
    ordens, eventos = [], []

    def _config(conn, p):
        if p == "PIPE_C":
            return _cfg(regras_dia={"schedule_type": "monthly",
                                    "schedule_dom": 5})
        return _cfg()

    _mundo(monkeypatch,
           dependentes_com_dependencia=lambda conn: ["PIPE_C"],
           predecessores_de=lambda conn, p: ["PIPE_A"],
           config_dependente=_config,
           ordenar_corrida=lambda conn, p, d, rid, o:
               ordens.append(p) or True,
           gravar_evento=lambda conn, p, d, t, det, **kw:
               eventos.append(t) or True)
    saida = GUARDIA.ciclo()
    assert saida["ordenadas"] == 0
    assert ordens == [] and eventos == []


def test_new_day_predecessor_fora_do_dia_bloqueia_sem_alerta(monkeypatch):
    """D44: pai semanal-domingo (com linha PULADO do cron) numa segunda —
    a condição não pode fechar em D → C não é ordenado e NADA alerta;
    PULADO sozinho não conta como esperado."""
    ordens, eventos = [], []

    def _config(conn, p):
        if p == "PIPE_A":
            return _cfg(regras_dia={"schedule_type": "weekly",
                                    "schedule_dow": 0})
        return _cfg()

    _mundo(monkeypatch,
           dependentes_com_dependencia=lambda conn: ["PIPE_C"],
           predecessores_de=lambda conn, p: ["PIPE_A"],
           config_dependente=_config,
           resumo_predecessores=lambda conn, p, d: {"PIPE_A": {"PULADO"}},
           ordenar_corrida=lambda conn, p, d, rid, o:
               ordens.append(p) or True,
           gravar_evento=lambda conn, p, d, t, det, **kw:
               eventos.append(t) or True)
    saida = GUARDIA.ciclo()
    assert saida["ordenadas"] == 0
    assert ordens == [] and eventos == []


def test_new_day_linha_apesar_da_agenda_conta_como_esperado(monkeypatch):
    """O mesmo pai fora do dia, mas com SUCESSO na data (rodou manual
    apesar da agenda) → conta como esperado e C é ordenado (D44, 2ª via)."""
    ordens = []

    def _config(conn, p):
        if p == "PIPE_A":
            return _cfg(regras_dia={"schedule_type": "weekly",
                                    "schedule_dow": 0})
        return _cfg()

    _mundo(monkeypatch,
           dependentes_com_dependencia=lambda conn: ["PIPE_C"],
           predecessores_de=lambda conn, p: ["PIPE_A"],
           config_dependente=_config,
           resumo_predecessores=lambda conn, p, d: {"PIPE_A": {"SUCESSO"}},
           ordenar_corrida=lambda conn, p, d, rid, o:
               ordens.append(p) or True)
    assert GUARDIA.ciclo()["ordenadas"] == 1
    assert ordens == ["PIPE_C"]


def test_new_day_viradas_divergentes_bloqueiam_e_viram_evento(monkeypatch):
    """Decisão 5: P1 (virada 20:00) e P2 (virada 00:00) às 21:00 produzem
    datas distintas → C NÃO é ordenado e nasce DATA_DIVERGENTE chaveado no
    min das datas, citando os pares."""
    ordens, eventos = [], []
    _mundo(monkeypatch,
           agora=datetime(2026, 8, 3, 21, 0),
           dependentes_com_dependencia=lambda conn: ["PIPE_C"],
           predecessores_de=lambda conn, p: ["PIPE_A", "PIPE_B"],
           virada_efetiva=lambda conn, p:
               time(20, 0) if p == "PIPE_A" else time(0, 0),
           ordenar_corrida=lambda conn, p, d, rid, o:
               ordens.append(p) or True,
           gravar_evento=lambda conn, p, d, t, det, **kw:
               eventos.append((p, d, t, det)) or True)
    saida = GUARDIA.ciclo()
    assert saida["ordenadas"] == 0 and ordens == []
    (p, d, tipo, det), = eventos
    assert (p, tipo) == ("PIPE_C", "DATA_DIVERGENTE")
    assert d == date(2026, 8, 3)                     # min(D_p): determinístico
    assert "PIPE_A->2026-08-04" in det and "PIPE_B->2026-08-03" in det


def test_new_day_corrida_existente_nao_assume_ordenacao(monkeypatch):
    """D48: ordenar_corrida devolvendo False (já havia corrida) → contador
    zero e NENHUM efeito colateral (nenhum evento por cima da corrida)."""
    eventos = []
    _mundo(monkeypatch,
           dependentes_com_dependencia=lambda conn: ["PIPE_C"],
           predecessores_de=lambda conn, p: ["PIPE_A"],
           resumo_predecessores=lambda conn, p, d: {"PIPE_A": set()},
           ordenar_corrida=lambda conn, p, d, rid, o: False,
           gravar_evento=lambda conn, p, d, t, det, **kw:
               eventos.append(t) or True)
    assert GUARDIA.ciclo()["ordenadas"] == 0
    assert eventos == []


def test_guarda_de_idade_nada_retroativo(monkeypatch):
    """D45 (§12.4): dependência recém-cadastrada com histórico velho no
    banco — o ciclo NÃO tem por onde ler o histórico (nenhuma função o
    devolve) e toda ordenação/disparo sai de calcular(agora, virada):
    nenhum INSERT nem trigger para data anterior à corrente."""
    ordens, disparos = [], []
    _mundo(monkeypatch,
           dependentes_com_dependencia=lambda conn: ["PIPE_C"],
           predecessores_de=lambda conn, p: ["PIPE_A"],
           resumo_predecessores=lambda conn, p, d: {"PIPE_A": set()},
           ordenar_corrida=lambda conn, p, d, rid, o:
               ordens.append(d) or True)
    monkeypatch.setattr(GUARDIA, "_trigger",
                        lambda dag_id, run_id, conf: disparos.append(conf))
    GUARDIA.ciclo()
    assert ordens == [HOJE]                  # só a data corrente, nunca passado
    assert disparos == []


# ══════════════════ §12.5 — rede de segurança (D16/D18/D22/D51) ═════════════

def test_rede_dispara_na_ordem_liberado_claim_trigger(monkeypatch):
    ordem, disparos = [], []
    _mundo(monkeypatch,
           corridas_aguardando=lambda conn: [_linha()],
           predecessores_de=lambda conn, p: ["PIPE_A"],
           liberado=lambda conn, p, d: ordem.append("liberado") or (True, []),
           reservar_corrida=lambda conn, p, d, rid, o:
               ordem.append("claim") or "guardia__ja")
    monkeypatch.setattr(
        GUARDIA, "_trigger",
        lambda dag_id, run_id, conf:
            ordem.append("trigger") or disparos.append((dag_id, run_id, conf)))
    saida = GUARDIA.ciclo()
    assert saida["disparadas"] == 1
    assert ordem == ["liberado", "claim", "trigger"]
    dag_id, run_id, conf = disparos[0]
    assert dag_id == "PIPE_C" and run_id == "guardia__ja"
    assert conf == {"data_referencia": "2026-08-03",
                    "dia_operacional": "2026-08-03",
                    "disparado_por": "guardia"}


def test_rede_nao_liberada_nao_chega_ao_claim(monkeypatch):
    claims = []
    _mundo(monkeypatch,
           corridas_aguardando=lambda conn: [_linha()],
           liberado=lambda conn, p, d: (False, ["PIPE_A"]),
           reservar_corrida=lambda conn, p, d, rid, o:
               claims.append(p) or rid)
    assert GUARDIA.ciclo()["disparadas"] == 0
    assert claims == []


def test_rede_segura_antes_da_janela_e_dispara_depois(monkeypatch):
    """D22: nao_iniciar_antes=10:00 — às 09:00 nem claim nem trigger (a
    linha fica); o primeiro ciclo após a hora dispara."""
    claims, disparos = [], []

    def _montar(agora):
        _mundo(monkeypatch, agora=agora,
               corridas_aguardando=lambda conn: [_linha()],
               predecessores_de=lambda conn, p: ["PIPE_A"],
               config_dependente=lambda conn, p:
                   _cfg(nao_iniciar_antes=time(10, 0)),
               liberado=lambda conn, p, d: (True, []),
               reservar_corrida=lambda conn, p, d, rid, o:
                   claims.append(p) or "guardia__ja")
        monkeypatch.setattr(GUARDIA, "_trigger",
                            lambda dag_id, run_id, conf: disparos.append(dag_id))

    _montar(datetime(2026, 8, 3, 9, 0))
    assert GUARDIA.ciclo()["disparadas"] == 0
    assert claims == [] and disparos == []

    _montar(datetime(2026, 8, 3, 10, 5))
    assert GUARDIA.ciclo()["disparadas"] == 1
    assert claims == ["PIPE_C"] and disparos == ["PIPE_C"]


def test_rede_filho_pausado_nao_dispara(monkeypatch):
    """Decisão 8: pausado não vira run queued eterno — a linha permanece
    aguardando (o deadline sabe alertar) e nem claim acontece."""
    claims, disparos = [], []
    _mundo(monkeypatch,
           corridas_aguardando=lambda conn: [_linha()],
           liberado=lambda conn, p, d: (True, []),
           reservar_corrida=lambda conn, p, d, rid, o:
               claims.append(p) or rid)
    monkeypatch.setattr(GUARDIA, "_dag_pausada", lambda dag_id: True)
    monkeypatch.setattr(GUARDIA, "_trigger",
                        lambda dag_id, run_id, conf: disparos.append(dag_id))
    assert GUARDIA.ciclo()["disparadas"] == 0
    assert claims == [] and disparos == []


def test_rede_perdedor_do_claim_nao_dispara(monkeypatch):
    """D18: reservar_corrida devolvendo None = outra ponta venceu — nenhum
    segundo disparo."""
    disparos = []
    _mundo(monkeypatch,
           corridas_aguardando=lambda conn: [_linha()],
           liberado=lambda conn, p, d: (True, []),
           reservar_corrida=lambda conn, p, d, rid, o: None)
    monkeypatch.setattr(GUARDIA, "_trigger",
                        lambda dag_id, run_id, conf: disparos.append(dag_id))
    assert GUARDIA.ciclo()["disparadas"] == 0
    assert disparos == []


def test_rede_trigger_que_levanta_devolve_a_reserva(monkeypatch):
    """D16 (metade F4): trigger levanta → devolver_reserva com os args
    certos (linha adotada → veio_de_adocao=True) e o ciclo não quebra — o
    varredura do ciclo seguinte É o retry."""
    devolucoes = []

    def _explode(dag_id, run_id, conf):
        raise RuntimeError("DAG nao serializada")

    _mundo(monkeypatch,
           corridas_aguardando=lambda conn: [_linha()],
           liberado=lambda conn, p, d: (True, []),
           reservar_corrida=lambda conn, p, d, rid, o: "guardia__ja",
           devolver_reserva=lambda conn, p, d, rid, veio_de_adocao:
               devolucoes.append((p, d, rid, veio_de_adocao)))
    monkeypatch.setattr(GUARDIA, "_trigger", _explode)
    saida = GUARDIA.ciclo()
    assert saida["disparadas"] == 0
    assert devolucoes == [("PIPE_C", HOJE, "guardia__ja", True)]


def test_um_pipeline_quebrado_nao_cancela_os_demais(monkeypatch):
    """D51: o 1º da varredura explode na consulta, o 2º dispara — o
    try/except é POR ITEM, dentro do laço."""
    disparos = []

    def _lib(conn, p, d):
        if p == "PIPE_X":
            raise RuntimeError("cadastro problematico")
        return True, []

    _mundo(monkeypatch,
           corridas_aguardando=lambda conn: [
               _linha(pipeline="PIPE_X", run_id="guardia__x"),
               _linha(pipeline="PIPE_C", run_id="guardia__c")],
           liberado=_lib,
           reservar_corrida=lambda conn, p, d, rid, o: "guardia__c")
    monkeypatch.setattr(GUARDIA, "_trigger",
                        lambda dag_id, run_id, conf: disparos.append(dag_id))
    assert GUARDIA.ciclo()["disparadas"] == 1
    assert disparos == ["PIPE_C"]


# ══════════════════════ §12.6 — resgate de órfã (§4.2) ══════════════════════

def test_resgate_so_sem_dagrun_no_airflow(monkeypatch):
    """Tripla guarda: as duas primeiras (inicio NULL + idade) vêm do módulo
    (reservas_orfas); a terceira — DagRun inexistente — decide aqui. DagRun
    existente → a corrida é do Airflow, não se mexe."""
    resgates, idades = [], []
    _mundo(monkeypatch,
           reservas_orfas=lambda conn, idade:
               idades.append(idade) or [("PIPE_C", HOJE, "guardia__orfa")],
           resgatar_reserva=lambda conn, p, d, r:
               resgates.append((p, d, r)) or True)
    monkeypatch.setattr(GUARDIA, "_dagrun_existe", lambda dag_id, run_id: True)
    assert GUARDIA.ciclo()["resgatadas"] == 0
    assert resgates == []
    assert idades == [10]        # max(10, 2×intervalo) com intervalo default 5

    _mundo(monkeypatch,
           reservas_orfas=lambda conn, idade: [("PIPE_C", HOJE, "guardia__orfa")],
           resgatar_reserva=lambda conn, p, d, r:
               resgates.append((p, d, r)) or True)
    assert GUARDIA.ciclo()["resgatadas"] == 1
    assert resgates == [("PIPE_C", HOJE, "guardia__orfa")]


def test_reserva_resgatada_dispara_no_mesmo_ciclo(monkeypatch):
    """E13: resgate → AGUARDANDO → a varredura (que roda depois) dispara."""
    disparos = []
    _mundo(monkeypatch,
           reservas_orfas=lambda conn, idade: [("PIPE_C", HOJE, "guardia__orfa")],
           corridas_aguardando=lambda conn: [_linha(run_id="guardia__orfa")],
           liberado=lambda conn, p, d: (True, []),
           reservar_corrida=lambda conn, p, d, rid, o: "guardia__orfa")
    monkeypatch.setattr(GUARDIA, "_trigger",
                        lambda dag_id, run_id, conf:
                            disparos.append((dag_id, run_id)))
    saida = GUARDIA.ciclo()
    assert saida["resgatadas"] == 1 and saida["disparadas"] == 1
    assert disparos == [("PIPE_C", "guardia__orfa")]


# ═════════ §12.6b — órfã que COMEÇOU e nunca fechou (§4.3, F5) ══════════════
#
# ⚠️ **DEFEITO ENCONTRADO NA REVISÃO ADVERSARIAL PRÉ-DEPLOY (2026-08-03).**
# `etl_dag_factory` emite `dagrun_timeout=timedelta(minutes=sla_minutos)` para
# pipeline com SLA. Uma etapa parada no portão da F5 fica `up_for_reschedule`
# até o teto (default 240 min). Estourando o `dagrun_timeout`, o scheduler
# marca o DagRun FAILED e **toda TI não-finalizada como SKIPPED** — então
# `registrar_falha` (ONE_FAILED) e `flow_close` (ALL_DONE) são PULADOS e
# ninguém grava FALHA: `etl_pipeline_execucao` fica EXECUTANDO para sempre,
# bloqueando todos os dependentes. `_resgatar_orfas` só cobria `inicio IS
# NULL` — corrida que COMEÇOU não era resgatada por ninguém.
#
# Os testes abaixo falham no `main` de hoje.

def _dagrun(estado, fim):
    return lambda dag_id, run_id: (estado, fim)


def test_orfa_em_execucao_com_dagrun_failed_e_fechada_como_falha(monkeypatch):
    fechadas, eventos = [], []
    _mundo(monkeypatch,
           corridas_em_execucao=lambda conn, idade:
               [("PIPE_C", HOJE, "dep__c", datetime(2026, 8, 3, 6, 0))],
           fechar_orfa_em_execucao=lambda conn, p, d, r, m:
               fechadas.append((p, d, r, m)) or True,
           gravar_evento=lambda conn, p, d, t, det, **kw:
               eventos.append((p, t, det)) or True)
    monkeypatch.setattr(GUARDIA, "_dagrun_terminado",
                        _dagrun("failed", datetime(2026, 8, 3, 7, 0)))
    assert GUARDIA.ciclo()["orfas_em_execucao"] == 1
    assert fechadas and fechadas[0][0] == "PIPE_C"
    assert "orfa" in fechadas[0][3]
    assert eventos and eventos[0][1] == "EXECUCAO_ORFA"


def test_corrida_parada_no_portao_JAMAIS_e_tocada(monkeypatch):
    """A etapa em espera deixa o DagRun `running` (up_for_reschedule não é
    estado terminal). Fechar essa corrida seria a rede de segurança matando
    exatamente a feature que ela existe para proteger."""
    fechadas = []
    _mundo(monkeypatch,
           corridas_em_execucao=lambda conn, idade:
               [("PIPE_C", HOJE, "dep__c", datetime(2026, 8, 3, 6, 0))],
           fechar_orfa_em_execucao=lambda conn, p, d, r, m:
               fechadas.append(p) or True)
    monkeypatch.setattr(GUARDIA, "_dagrun_terminado", _dagrun("running", None))
    assert GUARDIA.ciclo()["orfas_em_execucao"] == 0
    assert fechadas == []


def test_dagrun_recem_terminado_e_da_propria_dag(monkeypatch):
    """A janela entre o Airflow marcar o DagRun e o `registrar_falha` da DAG
    gravar FALHA é de segundos — nela quem fecha é a DAG, como sempre foi."""
    fechadas = []
    _mundo(monkeypatch,
           corridas_em_execucao=lambda conn, idade:
               [("PIPE_C", HOJE, "dep__c", datetime(2026, 8, 3, 6, 0))],
           fechar_orfa_em_execucao=lambda conn, p, d, r, m:
               fechadas.append(p) or True)
    # AGORA = 09:00; idade = max(15, 3×5) = 15 min → 08:59 é recentíssimo.
    monkeypatch.setattr(GUARDIA, "_dagrun_terminado",
                        _dagrun("failed", datetime(2026, 8, 3, 8, 59)))
    assert GUARDIA.ciclo()["orfas_em_execucao"] == 0
    assert fechadas == []


def test_dagrun_success_sem_fecho_ALERTA_mas_nao_inventa_verde(monkeypatch):
    """A guardiã não fecha como SUCESSO o que ela não viu suceder, nem como
    FALHA o que o Airflow diz ter concluído. Vira alerta + Finalização
    Manual — a lição do sucesso falso vale nos dois sentidos."""
    fechadas, eventos = [], []
    _mundo(monkeypatch,
           corridas_em_execucao=lambda conn, idade:
               [("PIPE_C", HOJE, "dep__c", datetime(2026, 8, 3, 6, 0))],
           fechar_orfa_em_execucao=lambda conn, p, d, r, m:
               fechadas.append(p) or True,
           gravar_evento=lambda conn, p, d, t, det, **kw:
               eventos.append((t, det)) or True)
    monkeypatch.setattr(GUARDIA, "_dagrun_terminado",
                        _dagrun("success", datetime(2026, 8, 3, 7, 0)))
    saida = GUARDIA.ciclo()
    assert saida["orfas_em_execucao"] == 1      # foi TOCADA (alertada)
    assert fechadas == []                       # mas NÃO fechada
    assert eventos[0][0] == "EXECUCAO_ORFA"
    assert "Finalizacao Manual" in eventos[0][1]


def test_sem_dagrun_no_airflow_so_alerta(monkeypatch):
    """Sem o Airflow confirmar o desfecho, o que a guardiã sabe é que não
    sabe — e isso vira alerta, não sentença."""
    fechadas, eventos = [], []
    _mundo(monkeypatch,
           corridas_em_execucao=lambda conn, idade:
               [("PIPE_C", HOJE, "dep__c", datetime(2026, 8, 3, 6, 0))],
           fechar_orfa_em_execucao=lambda conn, p, d, r, m:
               fechadas.append(p) or True,
           gravar_evento=lambda conn, p, d, t, det, **kw:
               eventos.append((t, det)) or True)
    monkeypatch.setattr(GUARDIA, "_dagrun_terminado",
                        lambda dag_id, run_id: None)
    assert GUARDIA.ciclo()["orfas_em_execucao"] == 1
    assert fechadas == [] and eventos[0][0] == "EXECUCAO_ORFA"


def test_erro_numa_orfa_nao_interrompe_o_ciclo(monkeypatch):
    """D51 aplicado à responsabilidade nova: erro em UM item não derruba o
    ciclo inteiro."""
    def _explode(dag_id, run_id):
        raise RuntimeError("airflow fora")
    _mundo(monkeypatch,
           corridas_em_execucao=lambda conn, idade:
               [("PIPE_C", HOJE, "dep__c", datetime(2026, 8, 3, 6, 0)),
                ("PIPE_D", HOJE, "dep__d", datetime(2026, 8, 3, 6, 0))])
    monkeypatch.setattr(GUARDIA, "_dagrun_terminado", _explode)
    assert GUARDIA.ciclo()["orfas_em_execucao"] == 0     # nenhuma, e sem crash


def test_orfa_e_tratada_ANTES_da_rede_de_seguranca(monkeypatch):
    """Uma corrida fechada como FALHA pode ser a resposta que falta para um
    dependente decidir o dia no MESMO ciclo. EXECUTANDO eterno não é resposta;
    FALHA é."""
    import inspect
    src = inspect.getsource(GUARDIA.ciclo)
    assert src.index("_resgatar_em_execucao") < src.index("_rede_seguranca(")


# ═══════════════════ §12.7 — deadline (D35/D46/D49) ═════════════════════════

def test_deadline_sem_hora_limite_nunca_alerta(monkeypatch):
    """Opt-in (D35): hora_limite NULL → nenhum JANELA_ESTOUROU, nunca."""
    eventos = []
    _mundo(monkeypatch,
           corridas_aguardando=lambda conn: [_linha()],
           liberado=lambda conn, p, d: (False, ["PIPE_A"]),
           resumo_predecessores=lambda conn, p, d: {"PIPE_A": set()},
           gravar_evento=lambda conn, p, d, t, det, **kw: eventos.append(t) or True)
    GUARDIA.ciclo()
    assert "JANELA_ESTOUROU" not in eventos


def test_deadline_pendente_nao_falha(monkeypatch):
    """Aceite F4: estourou → evento JANELA_ESTOUROU e o pipeline fica
    PENDENTE — nenhum fechamento nem mudança de status no caminho do
    deadline (a linha é recente: o fechamento do §6 nem a olha)."""
    eventos, fechamentos = [], []
    _mundo(monkeypatch,
           corridas_aguardando=lambda conn: [_linha()],
           config_dependente=lambda conn, p: _cfg(hora_limite=time(8, 0)),
           predecessores_de=lambda conn, p: ["PIPE_A"],
           liberado=lambda conn, p, d: (False, ["PIPE_A"]),
           resumo_predecessores=lambda conn, p, d: {"PIPE_A": {"EXECUTANDO"}},
           fechar_nao_liberou=lambda conn, p, d, r, m:
               fechamentos.append(p) or True,
           gravar_evento=lambda conn, p, d, t, det, **kw:
               eventos.append((t, det)) or True)
    saida = GUARDIA.ciclo()
    assert saida["deadlines"] == 1 and saida["fechadas"] == 0
    assert fechamentos == []
    tipo, det = eventos[0]
    assert tipo == "JANELA_ESTOUROU"
    assert det == "aguardando: PIPE_A"
    # anti-teste do D4: predecessor COM linha jamais vira "nenhum executou"
    assert "nenhum predecessor" not in det


def test_deadline_mensagem_liberado_sem_disparo(monkeypatch):
    """D46 msg 1: liberada mas o disparo falha repetidamente (trigger
    levantando) → o deadline diz exatamente isso."""
    eventos = []

    def _explode(dag_id, run_id, conf):
        raise RuntimeError("scheduler fora")

    _mundo(monkeypatch,
           corridas_aguardando=lambda conn: [_linha()],
           config_dependente=lambda conn, p: _cfg(hora_limite=time(8, 0)),
           predecessores_de=lambda conn, p: ["PIPE_A"],
           liberado=lambda conn, p, d: (True, []),
           reservar_corrida=lambda conn, p, d, rid, o: "guardia__ja",
           gravar_evento=lambda conn, p, d, t, det, **kw:
               eventos.append((t, det)) or True)
    monkeypatch.setattr(GUARDIA, "_trigger", _explode)
    GUARDIA.ciclo()
    assert ("JANELA_ESTOUROU",
            "liberado mas sem disparo - verifique DAG/scheduler") in eventos


def test_deadline_mensagem_nenhum_predecessor_executou(monkeypatch):
    """D46 msg 3: nenhuma linha de nenhum predecessor na data."""
    eventos = []
    _mundo(monkeypatch,
           corridas_aguardando=lambda conn: [_linha()],
           config_dependente=lambda conn, p: _cfg(hora_limite=time(8, 0)),
           predecessores_de=lambda conn, p: ["PIPE_A"],
           liberado=lambda conn, p, d: (False, ["PIPE_A"]),
           resumo_predecessores=lambda conn, p, d: {"PIPE_A": set()},
           gravar_evento=lambda conn, p, d, t, det, **kw:
               eventos.append((t, det)) or True)
    GUARDIA.ciclo()
    assert ("JANELA_ESTOUROU",
            "nenhum predecessor executou em 2026-08-03") in eventos


def test_deadline_no_passado_nao_alerta(monkeypatch):
    """Linha de reprocesso de data antiga: o instante do deadline fica fora
    do dia operacional corrente → log apenas, nunca alerta."""
    eventos = []
    _mundo(monkeypatch,
           corridas_aguardando=lambda conn:
               [_linha(data_ref=date(2026, 8, 1))],
           config_dependente=lambda conn, p: _cfg(hora_limite=time(8, 0)),
           predecessores_de=lambda conn, p: ["PIPE_A"],
           liberado=lambda conn, p, d: (False, ["PIPE_A"]),
           resumo_predecessores=lambda conn, p, d: {"PIPE_A": set()},
           gravar_evento=lambda conn, p, d, t, det, **kw:
               eventos.append(t) or True)
    assert GUARDIA.ciclo()["deadlines"] == 0
    assert "JANELA_ESTOUROU" not in eventos


def test_deadline_antes_da_hora_nao_alerta(monkeypatch):
    eventos = []
    _mundo(monkeypatch,
           corridas_aguardando=lambda conn: [_linha()],
           config_dependente=lambda conn, p: _cfg(hora_limite=time(23, 0)),
           predecessores_de=lambda conn, p: ["PIPE_A"],
           liberado=lambda conn, p, d: (False, ["PIPE_A"]),
           resumo_predecessores=lambda conn, p, d: {"PIPE_A": set()},
           gravar_evento=lambda conn, p, d, t, det, **kw:
               eventos.append(t) or True)
    assert GUARDIA.ciclo()["deadlines"] == 0
    assert eventos == []


def test_deadline_idempotente_no_ciclo_seguinte(monkeypatch):
    """D49: o evento já existe (gravar devolve False) → contador zero, sem
    duplicata nem reenvio."""
    _mundo(monkeypatch,
           corridas_aguardando=lambda conn: [_linha()],
           config_dependente=lambda conn, p: _cfg(hora_limite=time(8, 0)),
           predecessores_de=lambda conn, p: ["PIPE_A"],
           liberado=lambda conn, p, d: (False, ["PIPE_A"]),
           resumo_predecessores=lambda conn, p, d: {"PIPE_A": set()},
           gravar_evento=lambda conn, p, d, t, det, **kw: False)
    assert GUARDIA.ciclo()["deadlines"] == 0


# ═══════════════════ §12.8 — NAO_LIBEROU (§6, Decisão 11) ═══════════════════

_ONTEM_CEDO = datetime(2026, 8, 1, 6, 0)      # anterior à virada ANTERIOR


def test_fechamento_exige_idade_de_um_dia_operacional(monkeypatch):
    """Linha de ontem à noite (dentro do último dia operacional) NÃO fecha
    — é a cadeia noturna meramente lenta que o push ainda vai adotar."""
    fechamentos = []
    _mundo(monkeypatch,
           corridas_aguardando=lambda conn:
               [_linha(data_ref=date(2026, 8, 2),
                       criado_em=datetime(2026, 8, 2, 23, 0))],
           predecessores_de=lambda conn, p: ["PIPE_A"],
           liberado=lambda conn, p, d: (False, ["PIPE_A"]),
           resumo_predecessores=lambda conn, p, d: {"PIPE_A": set()},
           fechar_nao_liberou=lambda conn, p, d, r, m:
               fechamentos.append(p) or True)
    assert GUARDIA.ciclo()["fechadas"] == 0
    assert fechamentos == []


def test_fechamento_de_linha_velha_nao_liberada(monkeypatch):
    """Idade + não-liberada + sem EXECUTANDO → NAO_LIBEROU com motivo e
    evento próprio (o D41 de quem não tem deadline)."""
    fechamentos, eventos = [], []
    _mundo(monkeypatch,
           corridas_aguardando=lambda conn:
               [_linha(data_ref=date(2026, 8, 1), criado_em=_ONTEM_CEDO)],
           predecessores_de=lambda conn, p: ["PIPE_A"],
           liberado=lambda conn, p, d: (False, ["PIPE_A"]),
           resumo_predecessores=lambda conn, p, d: {"PIPE_A": set()},
           fechar_nao_liberou=lambda conn, p, d, r, m:
               fechamentos.append((p, d, r, m)) or True,
           gravar_evento=lambda conn, p, d, t, det, **kw:
               eventos.append((t, det)) or True)
    saida = GUARDIA.ciclo()
    assert saida["fechadas"] == 1
    p, d, r, m = fechamentos[0]
    assert (p, d, r) == ("PIPE_C", date(2026, 8, 1), "guardia__ja")
    assert m == "nenhum predecessor executou em 2026-08-01"
    assert any(t == "NAO_LIBEROU" for t, _ in eventos)


def test_linha_velha_liberada_vai_para_disparo_nao_fechamento(monkeypatch):
    fechamentos, disparos = [], []
    _mundo(monkeypatch,
           corridas_aguardando=lambda conn:
               [_linha(data_ref=date(2026, 8, 1), criado_em=_ONTEM_CEDO)],
           predecessores_de=lambda conn, p: ["PIPE_A"],
           liberado=lambda conn, p, d: (True, []),
           fechar_nao_liberou=lambda conn, p, d, r, m:
               fechamentos.append(p) or True,
           reservar_corrida=lambda conn, p, d, rid, o: "guardia__ja")
    monkeypatch.setattr(GUARDIA, "_trigger",
                        lambda dag_id, run_id, conf: disparos.append(dag_id))
    saida = GUARDIA.ciclo()
    assert saida["fechadas"] == 0 and saida["disparadas"] == 1
    assert fechamentos == [] and disparos == ["PIPE_C"]


def test_predecessor_executando_segura_o_fechamento(monkeypatch):
    """Pai de 30h rodando não derruba o filho que o espera."""
    fechamentos = []
    _mundo(monkeypatch,
           corridas_aguardando=lambda conn:
               [_linha(data_ref=date(2026, 8, 1), criado_em=_ONTEM_CEDO)],
           predecessores_de=lambda conn, p: ["PIPE_A"],
           liberado=lambda conn, p, d: (False, ["PIPE_A"]),
           resumo_predecessores=lambda conn, p, d: {"PIPE_A": {"EXECUTANDO"}},
           fechar_nao_liberou=lambda conn, p, d, r, m:
               fechamentos.append(p) or True)
    assert GUARDIA.ciclo()["fechadas"] == 0
    assert fechamentos == []


def test_fechamento_que_nao_pegou_a_linha_faz_rollback_do_evento(monkeypatch):
    """Ordem nova (revisão da F4): evento ANTES do fechamento, commit único.
    fechar devolve False (outra ponta mexeu) → rollback desfaz o evento junto
    — no banco real nada persiste; aqui provamos fechadas=0, commit ausente e
    rollback presente após a sequência."""
    chamadas = []
    _mundo(monkeypatch,
           corridas_aguardando=lambda conn:
               [_linha(data_ref=date(2026, 8, 1), criado_em=_ONTEM_CEDO)],
           predecessores_de=lambda conn, p: ["PIPE_A"],
           liberado=lambda conn, p, d: (False, ["PIPE_A"]),
           resumo_predecessores=lambda conn, p, d: {"PIPE_A": set()},
           fechar_nao_liberou=lambda conn, p, d, r, m:
               chamadas.append("fechar") or False,
           gravar_evento=lambda conn, p, d, t, det, **kw:
               chamadas.append(("evento", t)) or True)
    saida = GUARDIA.ciclo()
    assert saida["fechadas"] == 0
    # o evento veio ANTES do fechar (a ordem que não perde o card) e o ciclo
    # não commitou o par — o rollback (stub de conexão) desfez no banco real
    assert chamadas == [("evento", "NAO_LIBEROU"), "fechar"]


# ══════════ §12.9 — DATA_DIVERGENTE (exec) e PREDECESSOR_FALHOU (§7) ════════

def test_divergencia_de_execucao_cita_as_duas_datas(monkeypatch):
    """Aceite F4: o detalhe cita a data aguardada E a carimbada; a pergunta
    ao módulo leva o início do dia operacional corrente (D42)."""
    eventos, inicios = [], []
    _mundo(monkeypatch,
           corridas_aguardando=lambda conn: [_linha()],
           predecessores_de=lambda conn, p: ["PIPE_A"],
           sucesso_recente_outra_data=lambda conn, p, d, inicio:
               inicios.append(inicio) or [("PIPE_A", date(2026, 8, 4))],
           gravar_evento=lambda conn, p, d, t, det, **kw:
               eventos.append((t, det)) or True)
    saida = GUARDIA.ciclo()
    assert saida["eventos"] == 1
    tipo, det = eventos[0]
    assert tipo == "DATA_DIVERGENTE"
    assert "aguarda 2026-08-03" in det
    assert "PIPE_A concluiu hoje com data_referencia=2026-08-04" in det
    assert inicios == [datetime(2026, 8, 3, 0, 0)]   # a virada mais recente


def test_sucesso_de_ontem_nao_gera_divergencia(monkeypatch):
    """D42: a consulta (testada no módulo) não devolve o sucesso de ontem —
    lista vazia = nenhum evento, nenhum card."""
    eventos = []
    _mundo(monkeypatch,
           corridas_aguardando=lambda conn: [_linha()],
           predecessores_de=lambda conn, p: ["PIPE_A"],
           sucesso_recente_outra_data=lambda conn, p, d, inicio: [],
           gravar_evento=lambda conn, p, d, t, det, **kw:
               eventos.append(t) or True)
    assert GUARDIA.ciclo()["eventos"] == 0
    assert eventos == []


def test_predecessor_falhou_imediato_so_com_falha_sem_sucesso(monkeypatch):
    """Decisão 13: FALHA sem SUCESSO na data → evento imediato nomeando SÓ
    os falhados; FALHA com SUCESSO (Clear que re-rodou) não entra."""
    eventos = []
    _mundo(monkeypatch,
           corridas_aguardando=lambda conn: [_linha()],
           predecessores_de=lambda conn, p: ["PIPE_A", "PIPE_B"],
           resumo_predecessores=lambda conn, p, d: {
               "PIPE_A": {"FALHA"}, "PIPE_B": {"FALHA", "SUCESSO"}},
           gravar_evento=lambda conn, p, d, t, det, **kw:
               eventos.append((t, det)) or True)
    saida = GUARDIA.ciclo()
    assert saida["eventos"] == 1
    tipo, det = eventos[0]
    assert tipo == "PREDECESSOR_FALHOU"
    assert "PIPE_A" in det and "PIPE_B" not in det


def test_clear_que_virou_sucesso_nao_gera_predecessor_falhou(monkeypatch):
    eventos = []
    _mundo(monkeypatch,
           corridas_aguardando=lambda conn: [_linha()],
           predecessores_de=lambda conn, p: ["PIPE_B"],
           resumo_predecessores=lambda conn, p, d: {
               "PIPE_B": {"FALHA", "SUCESSO"}},
           gravar_evento=lambda conn, p, d, t, det, **kw:
               eventos.append(t) or True)
    assert GUARDIA.ciclo()["eventos"] == 0
    assert eventos == []


# ═══════════════════ §12.10 — Teams no fim do ciclo (§8) ════════════════════

_EV = {"id": 7, "pipeline": "PIPE_C", "data_ref": "2026-08-03",
       "tipo": "JANELA_ESTOUROU", "detalhe": "aguardando: PIPE_A",
       "detectado_em": "2026-08-03 08:00:00"}
_CANAL = {"id": 3, "webhook_url": "https://webhook/SEGREDO", "nome": "Canal BI"}


def _patch_envio(monkeypatch, resultado):
    """resultado: run_id do evento → (ok, motivo)."""
    chamadas = []

    def _fake(webhook, card, timeout=15):
        chamadas.append((webhook, card))
        ok, motivo = resultado(card)
        return ok, motivo

    import utils.ds_teams as ds_teams
    monkeypatch.setattr(ds_teams, "enviar_card", _fake)
    return chamadas


def test_notificado_em_so_apos_2xx(monkeypatch):
    """notificado_em só é marcado quando o envio devolve ok (2xx); falha de
    envio deixa o evento na fila para o próximo ciclo."""
    marcados = []
    ev2 = dict(_EV, id=8, tipo="NAO_LIBEROU")
    _mundo(monkeypatch,
           eventos_nao_notificados=lambda conn, lim, jan: [_EV, ev2],
           canal_teams_supervisao=lambda conn: dict(_CANAL),
           marcar_notificado=lambda conn, i: marcados.append(i))
    resultados = iter([(True, "HTTP 200"), (False, "webhook respondeu HTTP 500")])
    _patch_envio(monkeypatch, lambda card: next(resultados))
    saida = GUARDIA.ciclo()
    assert saida["notificados"] == 1
    assert marcados == [7]


def test_sem_canal_nada_e_enviado_e_os_eventos_ficam(monkeypatch, caplog):
    chamadas = _patch_envio(monkeypatch, lambda card: (True, "HTTP 200"))
    marcados = []
    _mundo(monkeypatch,
           eventos_nao_notificados=lambda conn, lim, jan: [_EV],
           canal_teams_supervisao=lambda conn: None,
           marcar_notificado=lambda conn, i: marcados.append(i))
    with caplog.at_level(logging.INFO, logger="airflow.task"):
        saida = GUARDIA.ciclo()
    assert saida["notificados"] == 0
    assert chamadas == [] and marcados == []
    assert "sem canal do Teams" in caplog.text


def test_lote_cheio_e_registrado_em_vez_de_truncar_calado(monkeypatch, caplog):
    """§8: fila do tamanho exato do lote → log explícito de que o restante
    sai no próximo ciclo; o limite pedido ao módulo é o da Variable (50)."""
    limites = []
    fila = [dict(_EV, id=i) for i in range(50)]
    _mundo(monkeypatch,
           eventos_nao_notificados=lambda conn, lim, jan:
               limites.append((lim, jan)) or fila,
           canal_teams_supervisao=lambda conn: dict(_CANAL))
    _patch_envio(monkeypatch, lambda card: (True, "HTTP 200"))
    with caplog.at_level(logging.INFO, logger="airflow.task"):
        saida = GUARDIA.ciclo()
    assert saida["notificados"] == 50
    assert limites == [(50, 2)]              # lote default e janela de 2 dias
    assert "próximo ciclo" in caplog.text


def test_falha_de_envio_loga_sem_a_url(monkeypatch, caplog):
    """A URL do webhook é credencial: o log cita o canal pelo NOME."""
    _mundo(monkeypatch,
           eventos_nao_notificados=lambda conn, lim, jan: [_EV],
           canal_teams_supervisao=lambda conn: dict(_CANAL))
    _patch_envio(monkeypatch, lambda card: (False, "webhook respondeu HTTP 500"))
    with caplog.at_level(logging.INFO, logger="airflow.task"):
        saida = GUARDIA.ciclo()
    assert saida["notificados"] == 0
    assert "SEGREDO" not in caplog.text
    assert "Canal BI" in caplog.text


def test_envio_usa_o_card_de_dependencia_com_o_webhook_do_canal(monkeypatch):
    chamadas = _patch_envio(monkeypatch, lambda card: (True, "HTTP 200"))
    _mundo(monkeypatch,
           eventos_nao_notificados=lambda conn, lim, jan: [_EV],
           canal_teams_supervisao=lambda conn: dict(_CANAL))
    GUARDIA.ciclo()
    (webhook, card), = chamadas
    assert webhook == "https://webhook/SEGREDO"
    corpo = card["attachments"][0]["content"]["body"]
    assert any("PIPE_C" in str(b.get("text", "")) for b in corpo)


# ═══ F11 (Decisão 69) — o botão do card, e a degradação por ausência ════════

_EV_MALHA = {"id": 21, "pipeline": "#corrida:12", "tipo": "MALHA_FALHOU",
             "data_ref": "2026-08-04", "detalhe": "PIPE_A falhou",
             "detectado_em": "2026-08-04 03:07:00", "malha": "Carga_Vida",
             "sequencia": 1, "corrida_id": 12}


def test_o_endereco_do_app_chega_ao_card_do_ciclo(monkeypatch):
    """O caminho inteiro, ponta a ponta: config → `_notificar` → card. Se a
    base parasse em qualquer degrau, o botão existiria no teste do ds_teams e
    não existiria no celular."""
    chamadas = _patch_envio(monkeypatch, lambda card: (True, "HTTP 200"))
    _mundo(monkeypatch,
           eventos_nao_notificados=lambda conn, lim, jan: [dict(_EV_MALHA)],
           canal_teams_supervisao=lambda conn: dict(_CANAL),
           app_base_url=lambda conn: "https://orquestra.exemplo.com")
    GUARDIA.ciclo()
    (_webhook, card), = chamadas
    acoes = card["attachments"][0]["content"]["actions"]
    assert acoes[0]["url"] == ("https://orquestra.exemplo.com/malha"
                               "?malha=Carga_Vida&modo=execucao&corrida=12")


def test_o_endereco_e_lido_UMA_vez_por_lote_e_nao_por_evento(monkeypatch):
    """Custo: o lote é de até 50 cards por ciclo de 5 min. Ler a config por
    evento seriam 50 idas ao banco para uma resposta que não muda no meio do
    lote."""
    leituras = []
    _patch_envio(monkeypatch, lambda card: (True, "HTTP 200"))
    _mundo(monkeypatch,
           eventos_nao_notificados=lambda conn, lim, jan:
               [dict(_EV_MALHA, id=i) for i in range(5)],
           canal_teams_supervisao=lambda conn: dict(_CANAL),
           app_base_url=lambda conn: leituras.append(1) or "https://x.exemplo")
    GUARDIA.ciclo()
    assert len(leituras) == 1


def test_sem_endereco_o_card_do_ciclo_sai_EXATAMENTE_como_hoje(monkeypatch):
    """O aceite literal da fase: `app_base_url` ausente → card sem botão e
    **sem erro no ciclo da guardiã**. Degradação por ausência."""
    chamadas = _patch_envio(monkeypatch, lambda card: (True, "HTTP 200"))
    _mundo(monkeypatch,
           eventos_nao_notificados=lambda conn, lim, jan: [dict(_EV_MALHA)],
           canal_teams_supervisao=lambda conn: dict(_CANAL))
    saida = GUARDIA.ciclo()
    (_webhook, card), = chamadas
    assert "actions" not in card["attachments"][0]["content"]
    assert saida["notificados"] == 1          # e o alerta CHEGOU assim mesmo


class _BancoQueRecusa:
    """Banco que nega toda leitura — a forma mais dura do `DENY SELECT`."""

    def __init__(self):
        self.tentativas = 0

    def cursor(self):
        self.tentativas += 1
        raise Exception("SELECT permission denied on object 'etl_app_config'")

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def test_config_ILEGIVEL_no_ciclo_nao_custa_o_alerta_das_3h(monkeypatch):
    """O outro lado da degradação por ausência: a config existe e o banco
    **recusa** a leitura (um `DENY SELECT` em `etl_app_config`, um lock).

    Aqui o `app_base_url` é o de PRODUÇÃO, não um dublê que devolve `''` — um
    dublê provaria que o ciclo aguenta uma função que nunca levanta, que é
    exatamente o que não está em dúvida. O que se prova é a COMPOSIÇÃO: a
    leitura de verdade, sobre um banco que diz não, dentro do ciclo que manda o
    alerta das 3h. O card sai sem botão, o alerta chega, e o ciclo termina
    normalmente — "a guardiã nunca cai" vale também para um enfeite de card."""
    banco = _BancoQueRecusa()
    mssql = sys.modules["airflow.providers.microsoft.mssql.hooks.mssql"]
    monkeypatch.setattr(mssql, "MsSqlHook",
                        lambda **kw: SimpleNamespace(get_conn=lambda: banco))
    chamadas = _patch_envio(monkeypatch, lambda card: (True, "HTTP 200"))
    _mundo(monkeypatch,
           eventos_nao_notificados=lambda conn, lim, jan: [dict(_EV_MALHA)],
           canal_teams_supervisao=lambda conn: dict(_CANAL),
           app_base_url=_APP_BASE_URL_DE_PRODUCAO)
    saida = GUARDIA.ciclo()
    (_webhook, card), = chamadas
    assert banco.tentativas >= 1, "o banco recusador nem chegou a ser usado"
    assert "actions" not in card["attachments"][0]["content"]
    assert saida["notificados"] == 1


# ═══ correções da revisão adversarial da F4 ═════════════════════════════════

def test_divergencia_converte_o_corte_para_a_regua_do_banco(monkeypatch):
    """Banco em UTC (+3h do local): o corte local 00:00 vira 03:00 na régua do
    banco — o pai que concluiu 21:30 locais de ONTEM (00:30 no carimbo UTC)
    fica ABAIXO do corte e NÃO vira DATA_DIVERGENTE falso."""
    inicios = []
    _mundo(monkeypatch,
           agora_do_banco=lambda conn: AGORA + timedelta(hours=3),
           corridas_aguardando=lambda conn: [_linha()],
           predecessores_de=lambda conn, p: ["PIPE_A"],
           sucesso_recente_outra_data=lambda conn, p, d, inicio:
               inicios.append(inicio) or [])
    GUARDIA.ciclo()
    assert inicios == [datetime(2026, 8, 3, 3, 0)], \
        "o corte tem que ir na régua do banco (local 00:00 + desvio 3h)"


def test_erro_de_consulta_adia_o_fechamento(monkeypatch):
    """'Não consegui perguntar' ≠ 'não liberou': o sentinel ERRO_CONSULTA nos
    faltantes ADIA o fechamento terminal (fechar uma corrida liberada por erro
    transitório seria irrecuperável)."""
    import utils.dependencias as dep_real
    fechamentos, eventos = [], []
    _mundo(monkeypatch,
           corridas_aguardando=lambda conn:
               [_linha(data_ref=date(2026, 8, 1), criado_em=_ONTEM_CEDO)],
           predecessores_de=lambda conn, p: ["PIPE_A"],
           liberado=lambda conn, p, d:
               (False, [f"{dep_real.ERRO_CONSULTA} deadlock victim"]),
           resumo_predecessores=lambda conn, p, d: {"PIPE_A": {"SUCESSO"}},
           fechar_nao_liberou=lambda conn, p, d, r, m:
               fechamentos.append(p) or True,
           gravar_evento=lambda conn, p, d, t, det, **kw:
               eventos.append(t) or True)
    saida = GUARDIA.ciclo()
    assert saida["fechadas"] == 0
    assert fechamentos == [] and eventos == []


# ═══════════ F14 — observadores de malha (Notificação/Fim, §5/§6) ═══════════
# docs/malha-componentes-desenho.md: a guardiã avalia os nós Notificação/Fim
# dentro do MESMO ciclo (Decisão 12 — nenhuma task nova), janela fixa {D, D-1}
# derivada do presente, evento com marcador #no:{id} idempotente pela chave.

# Desenho padrão dos cenários: A,B → Aguarde(1) → Notificação(2).
_NOS_F14 = [{"id": 1, "tipo": "aguarde"}, {"id": 2, "tipo": "notificacao"}]
_ARESTAS_F14 = [
    {"origem_pipeline": "PIPE_A", "destino_no": 1},
    {"origem_pipeline": "PIPE_B", "destino_no": 1},
    {"origem_no": 1, "destino_no": 2},
]


def _obs(no_id=2, tipo="notificacao", malha="M1", config=None,
         nos=None, arestas=None, criado_em=datetime(2026, 8, 1, 10, 0)):
    """criado_em default ANTERIOR à janela {D-1, D} dos cenários: o corte
    anti-retroativo só age quando o cenário o pede explicitamente."""
    return {"malha": malha, "no_id": no_id, "tipo": tipo, "config": config,
            "criado_em": criado_em,
            "nos": nos if nos is not None else _NOS_F14,
            "arestas": arestas if arestas is not None else _ARESTAS_F14}


def test_expandir_da_guardia_e_o_canonico_por_identidade():
    """Paridade por IDENTIDADE de objeto (como a F4 fez com liberado): a
    guardiã usa o MESMO expandir de dags/utils/malha_nos.py, nunca o port."""
    import utils.malha_nos as mn
    assert GUARDIA.expandir is mn.expandir


def test_notificacao_satisfeita_grava_evento_com_marcador(monkeypatch):
    """Condição fechada → 1 evento MALHA_NOTIFICACAO #no:{id} com o upstream
    expandido (via Aguarde) no detalhe, e card SEMPRE (notificar=True)."""
    gravados = []
    _mundo(monkeypatch,
           nos_observadores=lambda conn: [_obs()],
           pipelines_todos_sucesso=lambda conn, pipes, d: d == HOJE,
           gravar_evento=lambda conn, p, d, t, det, notificar=True, **kw:
               gravados.append((p, d, t, det, notificar)) or True)
    saida = GUARDIA.ciclo()
    assert saida["observadores"] == 1
    p, d, t, det, notificar = gravados[0]
    assert (p, d, t, notificar) == ("#no:2", HOJE, "MALHA_NOTIFICACAO", True)
    assert "M1" in det and "PIPE_A, PIPE_B" in det and "2026-08-03" in det


def test_notificacao_usa_titulo_e_mensagem_do_config(monkeypatch):
    gravados = []
    _mundo(monkeypatch,
           nos_observadores=lambda conn: [
               _obs(config={"titulo": "Onda 1 OK", "mensagem": "seguir"})],
           pipelines_todos_sucesso=lambda conn, pipes, d: d == HOJE,
           gravar_evento=lambda conn, p, d, t, det, notificar=True, **kw:
               gravados.append(det) or True)
    GUARDIA.ciclo()
    assert "Onda 1 OK" in gravados[0] and "seguir" in gravados[0]


def test_fim_satisfeito_grava_malha_concluida_sem_card_por_default(monkeypatch):
    """Decisão 14: o card do Fim é OPT-IN — config ausente → notificar=False;
    o evento (e o painel) saem sempre. Detalhe literal do §6."""
    gravados = []
    nos = [{"id": 1, "tipo": "aguarde"}, {"id": 9, "tipo": "fim"}]
    arestas = _ARESTAS_F14[:2] + [{"origem_no": 1, "destino_no": 9}]
    _mundo(monkeypatch,
           nos_observadores=lambda conn: [
               _obs(no_id=9, tipo="fim", nos=nos, arestas=arestas)],
           pipelines_todos_sucesso=lambda conn, pipes, d: d == HOJE,
           gravar_evento=lambda conn, p, d, t, det, notificar=True, **kw:
               gravados.append((p, t, det, notificar)) or True)
    saida = GUARDIA.ciclo()
    assert saida["observadores"] == 1
    p, t, det, notificar = gravados[0]
    assert (p, t, notificar) == ("#no:9", "MALHA_CONCLUIDA", False)
    assert det == ("Malha M1 concluída na data 2026-08-03 — "
                   "2 pipeline(s) com SUCESSO")


def test_fim_com_notificar_teams_true_vai_a_fila(monkeypatch):
    gravados = []
    nos = [{"id": 1, "tipo": "aguarde"}, {"id": 9, "tipo": "fim"}]
    arestas = _ARESTAS_F14[:2] + [{"origem_no": 1, "destino_no": 9}]
    _mundo(monkeypatch,
           nos_observadores=lambda conn: [
               _obs(no_id=9, tipo="fim", config={"notificar_teams": True},
                    nos=nos, arestas=arestas)],
           pipelines_todos_sucesso=lambda conn, pipes, d: d == HOJE,
           gravar_evento=lambda conn, p, d, t, det, notificar=True, **kw:
               gravados.append(notificar) or True)
    GUARDIA.ciclo()
    assert gravados == [True]


def test_janela_e_d_e_d_menos_1_e_so_ela(monkeypatch):
    """§5 passo 2 (eco do D45): as ÚNICAS datas perguntadas são D e D-1,
    derivadas do presente — nenhuma varredura de histórico."""
    perguntadas = []
    _mundo(monkeypatch,
           nos_observadores=lambda conn: [_obs()],
           pipelines_todos_sucesso=lambda conn, pipes, d:
               perguntadas.append(d) or False)
    saida = GUARDIA.ciclo()
    assert perguntadas == [HOJE - timedelta(days=1), HOJE]
    assert saida["observadores"] == 0       # malha saudável incompleta: zero


def test_conclusao_pos_meia_noite_sai_pela_janela_d_menos_1(monkeypatch):
    """A cadeia noturna que conclui 00:30 do dia seguinte (virada 00:00) não
    perde o aviso: a condição fecha em D-1 e o evento sai chaveado em D-1."""
    gravados = []
    _mundo(monkeypatch,
           nos_observadores=lambda conn: [_obs()],
           pipelines_todos_sucesso=lambda conn, pipes, d:
               d == HOJE - timedelta(days=1),
           gravar_evento=lambda conn, p, d, t, det, notificar=True, **kw:
               gravados.append(d) or True)
    saida = GUARDIA.ciclo()
    assert saida["observadores"] == 1
    assert gravados == [HOJE - timedelta(days=1)]


def test_evento_ja_gravado_nao_conta_nem_duplica(monkeypatch):
    """Idempotência pela chave (D49): gravar_evento False → contador zero;
    o 200º ciclo do dia é silencioso."""
    _mundo(monkeypatch,
           nos_observadores=lambda conn: [_obs()],
           pipelines_todos_sucesso=lambda conn, pipes, d: True,
           gravar_evento=lambda conn, p, d, t, det, notificar=True, **kw: False)
    assert GUARDIA.ciclo()["observadores"] == 0


def test_observador_sem_upstream_nunca_emite(monkeypatch):
    """Decisão 13: o 'todos com sucesso' vacuamente verdadeiro jamais vira
    evento — nó sem entrada pula ANTES de perguntar a condição."""
    perguntas, gravados = [], []
    _mundo(monkeypatch,
           nos_observadores=lambda conn: [_obs(arestas=[])],
           pipelines_todos_sucesso=lambda conn, pipes, d:
               perguntas.append(d) or True,
           gravar_evento=lambda conn, p, d, t, det, notificar=True, **kw:
               gravados.append(p) or True)
    assert GUARDIA.ciclo()["observadores"] == 0
    assert perguntas == [] and gravados == []


def test_viradas_divergentes_no_upstream_pulam_com_log(monkeypatch):
    """§5 passo 2: o observador não adivinha a data — viradas divergentes já
    têm o DATA_DIVERGENTE de configuração da F4 de guarda."""
    perguntas = []
    _mundo(monkeypatch,
           nos_observadores=lambda conn: [_obs()],
           virada_efetiva=lambda conn, p:
               time(0, 0) if p == "PIPE_A" else time(20, 0),
           pipelines_todos_sucesso=lambda conn, pipes, d:
               perguntas.append(d) or True)
    assert GUARDIA.ciclo()["observadores"] == 0
    assert perguntas == []


def test_sem_075_os_observadores_sao_pulados_e_o_ciclo_segue(monkeypatch):
    """Deploy parcial sem a 075: os observadores pulam com log e NENHUMA
    pergunta de nó é feita; o restante do ciclo (F4) roda normal."""
    tocou = []
    _mundo(monkeypatch,
           tabela_075_presente=lambda conn: False,
           nos_observadores=lambda conn: tocou.append("nos") or [])
    saida = GUARDIA.ciclo()
    assert saida["observadores"] == 0 and tocou == []
    assert "fechadas" in saida              # o ciclo inteiro rodou


def test_primeiro_observador_explode_segundo_avaliado(monkeypatch):
    """D51 nos observadores: erro em UM nó não interrompe o ciclo — o
    segundo ainda emite."""
    def _virada(conn, p):
        if p == "PIPE_X":
            raise RuntimeError("deadlock victim")
        return time(0, 0)
    quebrado = _obs(no_id=5, malha="M_QUEBRADA",
                    nos=[{"id": 4, "tipo": "aguarde"},
                         {"id": 5, "tipo": "notificacao"}],
                    arestas=[{"origem_pipeline": "PIPE_X", "destino_no": 4},
                             {"origem_no": 4, "destino_no": 5}])
    gravados = []
    _mundo(monkeypatch,
           nos_observadores=lambda conn: [quebrado, _obs()],
           virada_efetiva=_virada,
           pipelines_todos_sucesso=lambda conn, pipes, d: d == HOJE,
           gravar_evento=lambda conn, p, d, t, det, notificar=True, **kw:
               gravados.append(p) or True)
    saida = GUARDIA.ciclo()
    assert saida["observadores"] == 1
    assert gravados == ["#no:2"]


def test_uma_expansao_por_malha_e_upstream_por_no(monkeypatch):
    """Dois observadores da MESMA malha (Notificação no Aguarde + Fim nos
    terminais): cada um avalia o PRÓPRIO upstream expandido."""
    nos = [{"id": 1, "tipo": "aguarde"}, {"id": 2, "tipo": "notificacao"},
           {"id": 9, "tipo": "fim"}]
    arestas = _ARESTAS_F14 + [{"origem_pipeline": "PIPE_D", "destino_no": 9}]
    perguntas = []
    _mundo(monkeypatch,
           nos_observadores=lambda conn: [
               _obs(nos=nos, arestas=arestas),
               _obs(no_id=9, tipo="fim", nos=nos, arestas=arestas)],
           pipelines_todos_sucesso=lambda conn, pipes, d:
               perguntas.append((tuple(sorted(pipes)), d)) or False)
    GUARDIA.ciclo()
    assert (("PIPE_A", "PIPE_B"), HOJE) in perguntas
    assert (("PIPE_D",), HOJE) in perguntas


def test_no_criado_hoje_nao_emite_retroativo_de_ontem(monkeypatch):
    """Achado 1 da revisão adversarial: nó Notificação criado às 14:00 de D
    numa malha cujo D-1 concluiu com sucesso — SEM o corte, a janela {D-1, D}
    emitiria card retroativo de ontem que ninguém pediu (e dois cards no
    mesmo tick se D também fechou). Com o corte por criado_em: zero evento em
    D-1, evento normal em D."""
    gravados, perguntas = [], []
    _mundo(monkeypatch,
           nos_observadores=lambda conn: [
               _obs(criado_em=datetime(2026, 8, 3, 14, 0))],   # criado HOJE
           pipelines_todos_sucesso=lambda conn, pipes, d:
               perguntas.append(d) or True,                    # AMBAS fechariam
           gravar_evento=lambda conn, p, d, t, det, notificar=True, **kw:
               gravados.append(d) or True)
    saida = GUARDIA.ciclo()
    assert saida["observadores"] == 1
    assert gravados == [HOJE]                   # só D — nunca o retroativo
    assert perguntas == [HOJE]                  # D-1 nem é PERGUNTADO


def test_corte_aceita_criado_em_como_date_puro(monkeypatch):
    """Tolerância de tipo: criado_em date (dublê/driver) corta igual ao
    datetime do banco."""
    gravados = []
    _mundo(monkeypatch,
           nos_observadores=lambda conn: [_obs(criado_em=HOJE)],
           pipelines_todos_sucesso=lambda conn, pipes, d: True,
           gravar_evento=lambda conn, p, d, t, det, notificar=True, **kw:
               gravados.append(d) or True)
    GUARDIA.ciclo()
    assert gravados == [HOJE]
