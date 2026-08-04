"""
Testes do PORTÃO da etapa em espera no fonte gerado pela factory
(F5 — docs/spec-operacao-nivel-etapa.md §5 Bloco C, decisão 3 do §7).

⛔ **O teste-âncora deste arquivo é ``test_ancora_fonte_sem_delta_e_byte_
identico_ao_de_main``.** Ele guarda a mitigação que o §9 da spec declarou
OBRIGATÓRIA para esta fase:

    "F5 é a fase de risco real: mexe no log_start, que hoje existe em toda
     etapa de toda DAG — uma regressão ali afeta 100% dos pipelines.
     Mitigação: o portão só muda de comportamento quando existe pausa pedida;
     sem linha na tabela, o caminho é byte-idêntico ao atual, com teste de
     não-regressão do fonte gerado."

Como ele prova isso, e por que a prova é forte:

  1. gera o fonte com a factory DESTA branch;
  2. gera o MESMO fonte com a factory do commit base (``git show`` da main
     carregado como módulo separado) — não com um golden congelado a mão, que
     envelheceria em silêncio;
  3. remove do fonte novo **exatamente** as 12 linhas do delta da F5
     (declaradas aqui como constante) e compara os dois, byte a byte.

Se alguém mexer no ``log_start`` além do portão, a comparação quebra. Se
alguém mudar o delta do portão sem atualizar a constante, quebra também. É a
única barreira automática entre esta fase e 100% dos pipelines de produção.

Mesmo princípio dos demais testes de factory: módulos do Airflow stubados via
sys.modules antes do import; ``_generate_dag_source`` é função pura. Como nos
testes de notificação e do nó Aguarde, EXECUTAMOS a fonte gerada (com utils
stubados) para pegar NameError de tempo de carga.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_AIRFLOW_STUBS = [
    "airflow", "airflow.models", "airflow.operators", "airflow.operators.python",
    "airflow.operators.empty", "airflow.datasets", "airflow.utils",
    "airflow.utils.trigger_rule", "airflow.utils.state",
    "airflow.providers", "airflow.providers.microsoft", "airflow.providers.microsoft.mssql",
    "airflow.providers.microsoft.mssql.hooks", "airflow.providers.microsoft.mssql.hooks.mssql",
    "pendulum", "requests",
]
for _mod in _AIRFLOW_STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

_ROOT = Path(__file__).parent.parent

# Commit base desta branch (main no momento da F5). O fonte gerado por ELE é o
# padrão-ouro da não-regressão.
_COMMIT_BASE = "cbce3e2"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def factory():
    return _load_module("etl_dag_factory_espera_test",
                        _ROOT / "dags/etl_dag_factory.py")


# ═════════════════════════ O DELTA DA F5, DECLARADO ═══════════════════════════
# As ÚNICAS linhas que esta fase acrescenta ao fonte gerado. Estão aqui como
# dado (e não como regex frouxa) porque a lista precisa doer para mudar: cada
# linha nova aqui é uma linha nova rodando em toda etapa de todo pipeline.

_DELTA_IMPORT = [
    "",
    "# F5 — portao da etapa em espera (utils/espera.py). Import guardado:",
    "# sem os modulos no servidor a DAG importa igual, com o log_start de",
    "# sempre (PythonOperator) e o portao desligado.",
    "try:",
    "    from utils import espera as _espera",
    "    from utils.job_operators import LogStartOperator as _LogStart",
    "except Exception as _espera_err:  # noqa: BLE001",
    "    _espera = None",
    "    _LogStart = PythonOperator",
    '    print(f"[ESPERA] utils.espera indisponivel ({_espera_err}) — portao desligado")',
]

# A 3ª peça do delta NÃO é um bloco de linhas, e sim uma TROCA no bloco de cada
# etapa: `t_start_X = PythonOperator(` virou `t_start_X = _LogStart(`. Está
# aqui porque a inversa dela é o que a âncora aplica antes de comparar — e
# porque o alias existe para ter, no pior caso (utils ausente), o operador de
# antes: o import guardado faz `_LogStart = PythonOperator`.
_TROCA_LOG_START = ("= _LogStart(", "= PythonOperator(")

_DELTA_LOG_START = [
    "    # F5 — portao da etapa em espera: SEM pausa pedida (o caso normal)",
    "    # devolve None de imediato e o caminho abaixo e o de sempre.",
    "    if _espera is not None:",
    "        _espera.portao(hook, PIPELINE_NAME, job_name, execution_id)",
]

# Delta da F4 da spec-malha-data-unica (a trava de datas divergentes no push).
# Entra AQUI, na âncora da F5, pelo mesmo motivo que os blocos acima existem:
# a âncora não é "o fonte nunca muda", é "o fonte só muda no que foi
# DECLARADO". Mudança não declarada continua sendo pega.
_DELTA_DIVERGENCIA_IMPORT = [
    "            datas_dos_predecessores as _dep_datas_pred,",
    "            datas_divergentes as _dep_datas_divergentes,",
]
_DELTA_DIVERGENCIA_IMPORT2 = [
    "            detalhe_divergencia as _dep_detalhe_div,",
]
_DELTA_DIVERGENCIA_IMPORT3 = [
    "            gravar_evento as _dep_gravar_evento,",
]
_DELTA_DIVERGENCIA = [
    "                    # F4 (spec-malha-data-unica): a MESMA trava que a",
    "                    # guardia ja tinha (Decisao 5). Com os predecessores",
    "                    # em datas diferentes, a condicao do filho nao fecha",
    "                    # numa data so — liberar aqui junta dados de dois",
    "                    # dias na mesma corrida (incidente Carga_Vida).",
    "                    try:",
    "                        from datetime import datetime as _dt_div",
    "                        _datas_pred = _dep_datas_pred(conn, filho, _dt_div.now())",
    "                    except Exception as _e_div:",
    "                        _datas_pred = {}",
    "                        print(f'[DEP] viradas de {filho} indisponiveis ({_e_div}) — seguindo')",
    "                    if _dep_datas_divergentes(_datas_pred):",
    "                        _det = _dep_detalhe_div(_datas_pred)",
    "                        print(f'[DEP] {filho} NAO disparado — {_det}')",
    "                        try:",
    "                            _dep_gravar_evento(conn, filho, data_ref,",
    "                                               'DATA_DIVERGENTE', _det)",
    "                            conn.commit()",
    "                        except Exception as _e_ev:",
    "                            print(f'[DEP] evento DATA_DIVERGENTE de {filho} nao gravado: {_e_ev}')",
    "                        continue",
]


def _remover_delta(src: str) -> str:
    """Devolve o fonte SEM o delta da F5 — a operação inversa exata do que a
    factory passou a emitir. Falha ruidosamente (AssertionError) se um dos
    blocos não estiver lá exatamente uma vez: 'não achei o bloco' não pode
    virar 'byte-idêntico'."""
    velho, novo = _TROCA_LOG_START
    assert src.count(velho) >= 1, "nenhum t_start com o operador da F5"
    src = src.replace(velho, novo)
    linhas = src.split("\n")
    for bloco in (_DELTA_IMPORT, _DELTA_LOG_START,
                  _DELTA_DIVERGENCIA_IMPORT, _DELTA_DIVERGENCIA_IMPORT2,
                  _DELTA_DIVERGENCIA_IMPORT3, _DELTA_DIVERGENCIA):
        ocorrencias = [i for i in range(len(linhas) - len(bloco) + 1)
                       if linhas[i:i + len(bloco)] == bloco]
        # Os blocos do PUSH só existem em pipeline com dependência: cenário
        # sem dependente gera o fonte sem eles, e ausência ali é correta.
        opcional = bloco in (_DELTA_DIVERGENCIA_IMPORT, _DELTA_DIVERGENCIA_IMPORT2,
                             _DELTA_DIVERGENCIA_IMPORT3, _DELTA_DIVERGENCIA)
        assert len(ocorrencias) == 1 or (opcional and not ocorrencias), (
            f"bloco do portao esperado 1x, encontrado {len(ocorrencias)}x: "
            f"{bloco[1] if bloco[0] == '' else bloco[0]!r}")
        if not ocorrencias:
            continue
        i = ocorrencias[0]
        linhas = linhas[:i] + linhas[i + len(bloco):]
    return "\n".join(linhas)


@pytest.fixture(scope="module")
def factory_main():
    """A factory do commit base, carregada como módulo INDEPENDENTE.

    Pula (não falha) quando o git ou o commit não estão disponíveis — o teste
    estrutural ``test_delta_do_portao_e_so_o_declarado`` continua guardando o
    invariante nesse caso.
    """
    try:
        bruto = subprocess.run(
            ["git", "-C", str(_ROOT), "show", f"{_COMMIT_BASE}:dags/etl_dag_factory.py"],
            capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:  # pragma: no cover
        pytest.skip(f"git indisponivel para o fonte de referencia: {e}")
    if bruto.returncode != 0:  # pragma: no cover
        pytest.skip(f"commit base {_COMMIT_BASE} indisponivel: "
                    f"{bruto.stderr.decode('utf-8', 'replace')[:200]}")
    with tempfile.NamedTemporaryFile("wb", suffix="_factory_main.py",
                                     delete=False) as fh:
        fh.write(bruto.stdout)
        caminho = fh.name
    try:
        return _load_module("etl_dag_factory_main_ref", caminho)
    finally:
        Path(caminho).unlink(missing_ok=True)


# ══════════════════════════════ cenários de fonte ═════════════════════════════

def _pipeline(**overrides):
    base = {
        "pipeline_name": "PIPE_ESPERA", "project_name": "BI_CVP", "domain": "TESTE",
        "tags": "ETL", "scheduled_time": "06:00:00",
        "envia_msg_inicio": 1, "envia_msg_fim": 1, "envia_msg_erro": 1,
        "ambiente": "PROD", "schedule_type": "daily",
    }
    base.update(overrides)
    return base


def _job(name, jtype="datastage", order=1, depends=None, cond=None, cmd="ds.job"):
    j = {"job_name": name, "job_type": jtype, "job_command": cmd,
         "execution_order": order}
    if depends is not None:
        j["depends_on_jobs"] = depends
    if cond is not None:
        j["condition_json"] = json.dumps(cond)
    return j


def _jobs_variados():
    """Um pipeline com etapas de tipos DIFERENTES e um nó de decisão — para a
    comparação passar por todos os ramos de ``_task_block`` e pelos nós
    especiais (que NÃO têm log_start e por isso não podem ganhar portão)."""
    return [
        _job("ExtraiDS", order=1),
        _job("RodaProc", jtype="storedproc", order=2, depends="ExtraiDS",
             cmd="dbo.sp_teste"),
        _job("ChamaApi", jtype="http", order=3, depends="RodaProc",
             cmd="http://interno/health"),
        _job("Decide", jtype="decisao", order=4, depends="ChamaApi",
             cond={"tipo": "linhas", "operador": ">", "valor": 0,
                   "ramo_verdadeiro": ["Fecha"], "ramo_falso": []}),
        _job("Fecha", jtype="shell", order=5, depends="Decide",
             cmd="/opt/scripts/fecha.sh"),
    ]


_CENARIOS = {
    "simples": (_pipeline(), [_job("Unico", order=1)]),
    "variados": (_pipeline(), _jobs_variados()),
    "sob_demanda": (_pipeline(schedule_type="on_demand"), [_job("Unico", order=1)]),
    "sem_teams": (_pipeline(envia_msg_inicio=0, envia_msg_fim=0, envia_msg_erro=0),
                  [_job("Unico", order=1)]),
}


# ═══════════════════ ÂNCORA: não-regressão do fonte gerado ════════════════════

@pytest.mark.parametrize("cenario", sorted(_CENARIOS))
def test_ancora_fonte_sem_delta_e_byte_identico_ao_de_main(factory, factory_main,
                                                           cenario):
    """⛔ ÂNCORA DA F5 — ver o cabeçalho do arquivo.

    Tirando as 12 linhas do portão, a factory desta branch gera **exatamente**
    o mesmo texto que a de ``main``. Nenhum espaço, nenhuma vírgula, nenhuma
    reordenação de import.
    """
    pipeline, jobs = _CENARIOS[cenario]
    novo = factory._generate_dag_source(dict(pipeline), [dict(j) for j in jobs])
    antigo = factory_main._generate_dag_source(dict(pipeline),
                                               [dict(j) for j in jobs])
    assert _remover_delta(novo) == antigo


def test_delta_do_portao_e_so_o_declarado(factory):
    """Guarda estrutural que NÃO depende do git: o fonte novo contém os dois
    blocos do delta, e o nome ``_espera`` não aparece em nenhum outro lugar
    (nada de portão espalhado por outras tasks)."""
    src = factory._generate_dag_source(_pipeline(), _jobs_variados())
    assert "\n".join(_DELTA_IMPORT) in src
    assert "\n".join(_DELTA_LOG_START) in src
    # um `_LogStart(` por etapa executável (nós especiais não têm log_start)
    assert src.count("t_start_") == src.count("= _LogStart(") * 2
    # 6 ocorrências e nenhuma a mais: alias do import, nome do erro no
    # except, atribuição None, interpolação do aviso, guarda e chamada.
    assert src.count("_espera") == 6, src.count("_espera")


def test_log_start_usa_o_operador_que_reschedula(factory):
    """⛔ Sem `LogStartOperator` o `reschedule` do portão é IGNORADO pelo
    scheduler (ReadyToRescheduleDep: "Task is not in reschedule mode") e a
    espera vira polling de ~5s — medido na prova viva. O `log_end` NÃO muda:
    ele nunca reschedula."""
    src = factory._generate_dag_source(_pipeline(), _jobs_variados())
    assert "t_start_ExtraiDS = _LogStart(" in src
    assert "t_end_ExtraiDS = PythonOperator(" in src
    assert "from utils.job_operators import LogStartOperator as _LogStart" in src
    assert "    _LogStart = PythonOperator" in src   # degradação sem utils


# ═══════════════════════ o portão dentro do fonte gerado ══════════════════════

def test_fonte_gerado_compila_e_importa(factory):
    """A DAG gerada continua importando (é o que o Airflow faz ao ler o .py) —
    inclusive com ``utils.espera`` stubado."""
    src = factory._generate_dag_source(_pipeline(), _jobs_variados())
    ast.parse(src)
    util_mods = ("utils", "utils.datastage_operator", "utils.conditions",
                 "utils.job_operators", "utils.espera")
    saved = {m: sys.modules.get(m) for m in util_mods}
    try:
        for m in util_mods:
            sys.modules[m] = MagicMock()
        exec(compile(src, "<dag>", "exec"), {})
    finally:
        for m, prev in saved.items():
            if prev is None:
                sys.modules.pop(m, None)
            else:
                sys.modules[m] = prev


def test_portao_vem_antes_da_telemetria(factory):
    """Ordem que a tela depende: etapa segurada no portão NÃO recebe RUNNING.

    Gravar a telemetria antes de esperar mostraria como "executando" algo
    parado — e ainda estragaria a duração quando a liberação viesse."""
    src = factory._generate_dag_source(_pipeline(), _jobs_variados())
    corpo = src.split("def log_start(job_name, task_key, **context):")[1]
    corpo = corpo.split("\ndef ")[0]
    assert corpo.index("_espera.portao(") < corpo.index("_exec_telemetry(")


def test_portao_so_existe_no_log_start(factory):
    """``log_end`` e o flow_close NÃO ganham portão: a pausa segura o INÍCIO da
    etapa, nunca o fechamento (segurar o fim deixaria a etapa marcada RUNNING
    para sempre)."""
    src = factory._generate_dag_source(_pipeline(), _jobs_variados())
    corpo_end = src.split("def log_end(")[1].split("\ndef ")[0]
    assert "_espera" not in corpo_end


def test_import_do_portao_e_guardado(factory):
    """Sem ``utils/espera.py`` no servidor a DAG tem de continuar importando —
    deploy parcial não derruba pipeline de produção (mesma disciplina dos
    guards de migration em 073/074/075)."""
    src = factory._generate_dag_source(_pipeline(), [_job("Unico")])
    trecho = src.split("# F5 — portao da etapa em espera (utils/espera.py). "
                       "Import guardado:\n")[1]
    assert trecho.startswith("# sem os modulos")
    assert "except Exception as _espera_err" in trecho
    assert "_espera = None" in trecho


def test_no_especial_nao_ganha_portao(factory):
    """Nós de Decisão/Notificação/SQL/Aguarde não têm ``log_start_*`` — não há
    onde pendurar pausa neles, e o fonte não pode inventar uma."""
    src = factory._generate_dag_source(_pipeline(), _jobs_variados())
    assert "t_start_Decide" not in src
    bloco_dec = src.split("def _decide_Decide(")[1].split("\n\n")[0]
    assert "_espera" not in bloco_dec
