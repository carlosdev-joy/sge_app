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
  3. desfaz no fonte novo **exatamente** o delta declarado aqui como constante
     e compara os dois, byte a byte.

Se alguém mexer no ``log_start`` além do portão, a comparação quebra. Se
alguém mudar o delta do portão sem atualizar a constante, quebra também. É a
única barreira automática entre esta fase e 100% dos pipelines de produção.

⚠️ O arquivo virou a âncora de TODA fase que toca o fonte gerado, e não só da
F5 do portão: a F4 da spec-malha-data-unica e as F5/F6 da spec-malha-execucao
(o ODATE pela corrida e o corte de liberação pela corrida) declaram os deltas
delas aqui pelo mesmo motivo — a âncora
não é "o fonte nunca muda", é "o fonte só muda no que foi DECLARADO". A partir
da corrida, "desfazer" tem dois modos: **remoção** (bloco novo, some) e
**troca** (a fase reescreveu um trecho que já existia — ``_TROCAS_DA_CORRIDA``
o devolve ao texto do commit base). Fase que reescreve sem declarar a troca
quebra aqui, que é o ponto.

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

# Delta da F5 da spec-malha-execucao: o import guardado do modulo da corrida.
# Guardado pela mesma razao do de cima, e por uma pior: sem `utils/malha_corrida`
# no servidor, um import solto derrubaria o carregamento de TODA DAG regenerada.
_DELTA_IMPORT_CORRIDA = [
    '',
    '# F5 — o ODATE vem da corrida da malha (utils/malha_corrida.py).',
    '# Import guardado: sem o modulo no servidor a DAG importa igual e a',
    '# data de referencia volta a ser calculada como sempre foi.',
    'try:',
    '    from utils import malha_corrida as _corrida',
    'except Exception as _corrida_err:  # noqa: BLE001',
    '    _corrida = None',
    '    print(f"[MALHA] utils.malha_corrida indisponivel ({_corrida_err}) — ODATE sem corrida")',
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


_DELTA_MALHA_CICLO = [
    '    # F5 (spec-malha-data-unica): a malha comeca do ZERO. Vale so para',
    '    # disparo por AGENDA — quem vem por evento ja passou pelas travas do',
    '    # push (F4) e herdou a data do pai, entao re-julgar aqui pararia a',
    '    # propria cascata que acabou de ser liberada.',
    "    if _origem == 'agenda':",
    '        try:',
    '            from utils.malha_ciclo import (',
    '                equalizar as _mc_equalizar,',
    '                equalizar_ligado as _mc_eq_ligado,',
    '                estado_do_ciclo as _mc_estado,',
    '                inicio_do_ciclo as _mc_inicio,',
    '                inicio_retido as _mc_inicio_retido,',
    '                malhas_do_pipeline as _mc_malhas,',
    '                resumo as _mc_resumo,',
    '                virada_da_malha as _mc_virada,',
    '            )',
    '            from datetime import datetime as _dt_malha',
    '            _conn_malha = hook.get_conn()',
    '            try:',
    '                # F5 (spec-malha-execucao §7): com a corrida LIGADA, quem',
    '                # diz se a malha pode comecar e a CORRIDA — o disparo abre,',
    '                # a guardia fecha, e o ciclo deixa de ser inferido por',
    "                # 'inicio do ciclo + membro mais recente'. As cinco",
    '                # perguntas de utils/malha_ciclo (virada, inicio, estado,',
    '                # equalizacao, resumo) e a heuristica de janela viram UMA',
    '                # chamada, ja feita em _odate_do_run.',
    '                # Sem a 085 (ou com o interruptor em 0) o bloco de baixo',
    '                # roda igualzinho: ele e o fallback declarado no §7.',
    '                _com_corrida = (_corrida is not None',
    '                                and _corrida.corrida_ativa(_conn_malha))',
    '                for _malha in _mc_malhas(_conn_malha, PIPELINE_NAME):',
    '                    # 082: Inicio SEGURADO trava a malha inteira ANTES',
    '                    # de partir. O hold do Aguarde e obedecido pelo',
    '                    # predicado de liberacao; o do Inicio precisa ser',
    '                    # perguntado aqui, porque ele nao compila linha',
    '                    # nenhuma na 067 — so planta agendamento.',
    '                    # FICA NAS DUAS metades: hold e gesto humano sobre a',
    '                    # PARTIDA, e a corrida nao o substitui (F7 e que',
    '                    # reescreve hold). Nao se remove codigo que ainda',
    '                    # protege alguem.',
    '                    _no_seg = _mc_inicio_retido(_conn_malha, _malha)',
    '                    if _no_seg:',
    "                        print(f'[MALHA] Inicio #{_no_seg} SEGURADO — execucao pulada')",
    "                        return False, f'malha {_malha} segurada no Inicio #{_no_seg}'",
    '                    if _com_corrida:',
    '                        continue',
    '                    _dref = _data_referencia(context)',
    '                    _desde = _mc_inicio(_dt_malha.now(),',
    '                                        _mc_virada(_conn_malha, _malha))',
    '                    _est = _mc_estado(_conn_malha, _malha, _dref, _desde)',
    "                    if _est['divergentes'] and not _est['em_aberto'] \\",
    '                            and _mc_eq_ligado(_conn_malha, _malha):',
    '                        _feitos = _mc_equalizar(_conn_malha, _malha, _dref,',
    "                                                _est['divergentes'], 'agenda')",
    '                        _conn_malha.commit()',
    '                        for _p, _de, _para in _feitos:',
    "                            print(f'[MALHA] {_p}: data {_de} -> {_para} (equalizada)')",
    '                        _est = _mc_estado(_conn_malha, _malha, _dref, _desde)',
    "                    if _est['em_aberto'] or _est['divergentes']:",
    '                        _res = _mc_resumo(_est)',
    "                        print(f'[MALHA] {_malha} nao esta limpa — execucao pulada: {_res}')",
    "                        return False, f'malha {_malha} nao esta limpa — {_res}'",
    '            finally:',
    '                _conn_malha.close()',
    '        except Exception as e:',
    '            print(f"[MALHA] Aviso: estado da malha nao verificado ({e}) — seguindo.")',
    '    # F5 (Decisao 34) — duas corridas abertas com ODATEs diferentes para',
    '    # este pipeline: RECUSA nominal, nunca escolha. Fica FORA do',
    "    # `if _origem == 'agenda'` de proposito: o ODATE e do RUN, nao da",
    '    # agenda, e um disparo manual sem data tem exatamente o mesmo',
    '    # problema. Quem chega por push nao cai aqui porque herdou a data do',
    '    # pai (degrau 2) — e a porta do push tem a recusa dela (Decisao 35).',
    '    try:',
    '        _odate = _odate_do_run(context)',
    '    except Exception as _e_od:',
    '        # A checagem e LEITURA, e leitura degrada: se nem o ODATE deu',
    '        # para resolver, a carga segue pelo caminho de sempre. Quem',
    '        # registra a linha (o check_agenda, logo abaixo) tem o proprio',
    '        # try — nenhuma das duas pode derrubar o pipeline.',
    "        print(f'[MALHA] ODATE nao resolvido ({_e_od}) — sem checagem de ambiguidade')",
    "        _odate = {'ambiguo': False, 'data': None, 'detalhe': None}",
    "    if _odate['ambiguo']:",
    '        print(f"[MALHA] {_odate[\'detalhe\']}")',
    '        try:',
    '            from utils.dependencias import gravar_evento as _dep_evento_amb',
    '            _conn_amb = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID).get_conn()',
    '            try:',
    "                _dep_evento_amb(_conn_amb, PIPELINE_NAME, _odate['data'],",
    "                                'DATA_DIVERGENTE', _odate['detalhe'])",
    '                _conn_amb.commit()',
    '            finally:',
    '                _conn_amb.close()',
    '        except Exception as _e_amb:',
    "            print(f'[MALHA] evento de ODATE ambiguo nao gravado ({_e_amb})')",
    "        return False, str(_odate['detalhe'])[:500]",
]

# ═══════════ O DELTA DA F5 DA CORRIDA (spec-malha-execucao) ══════════════════
# Aqui o delta deixa de ser so ACRESCIMO: esta fase REESCREVE funcoes que ja
# existiam (`_data_referencia` e o upsert de `_registrar_execucao`). Por isso o
# mecanismo da ancora ganhou um segundo modo — a TROCA declarada: um par
# (novo, velho) que a inversa aplica ao contrario, exatamente como
# `_TROCA_LOG_START` sempre fez para `= _LogStart(`. A regra da ancora nao muda:
# o fonte so pode mudar no que esta declarado NESTE arquivo.

_VELHO_CABECALHO_ODATE = [
    'def _data_referencia(context):',
    '    """A que dia de processamento (ODATE) esta corrida pertence.',
    '',
    "    1) Heranca: conf['data_referencia'] (carimbo do predecessor, ou de um",
    '       disparo manual com data) prevalece; valor invalido loga e recalcula,',
    '       nunca aborta.',
    '    2) Calculo: momento LOGICO do run (data_interval_end/logical_date em',
    '       LOCAL_TZ) deslocado pela hora de virada do pipeline (fallback:',
    '       config global; qualquer erro degrada para 00:00 = data do',
    '       calendario, o comportamento de sempre).',
    '    NUNCA o relogio de parede: atraso de fila ou rerun no dia seguinte nao',
    '    pode mudar a data da corrida."""',
    "    dr = context.get('dag_run')",
    "    conf = (getattr(dr, 'conf', None) or {}) if dr is not None else {}",
    "    herdada = conf.get('data_referencia')",
    '    if herdada:',
    '        try:',
    '            from datetime import datetime as _dt',
    "            return _dt.strptime(str(herdada).strip(), '%Y-%m-%d').date()",
    '        except (ValueError, TypeError):',
    "            print(f'[EXEC] data_referencia herdada invalida ({herdada!r}) — recalculando')",
]

_NOVO_CABECALHO_ODATE = [
    'def _odate_pela_virada(context):',
    '    """Degrau 4 do §7 — o calculo de SEMPRE, palavra por palavra.',
    '',
    '    Momento LOGICO do run (data_interval_end/logical_date em LOCAL_TZ)',
    '    deslocado pela hora de virada do pipeline (fallback: config global;',
    '    qualquer erro degrada para 00:00 = data do calendario). NUNCA o',
    '    relogio de parede: atraso de fila ou rerun no dia seguinte nao pode',
    '    mudar a data da corrida.',
    '',
    '    Esta funcao e o comportamento anterior a esta fase, extraido para ca',
    '    SEM UMA VIRGULA de diferenca — e ela que responde quando o pipeline',
    '    nao e de malha, quando o interruptor esta desligado e quando a 085',
    '    nao esta no banco. Mexer aqui e mexer no ODATE de todo pipeline do',
    '    produto."""',
]

# O corpo do calculo pela virada NAO aparece em troca nenhuma: ele saiu de
# `_data_referencia` para `_odate_pela_virada` SEM UMA VIRGULA de diferenca,
# e e por isso que a ancora consegue comparar as duas arvores linha a linha.
_DELTA_ODATE = [
    '',
    'def _odate_da_corrida(context, run_id, conf, herdada):',
    '    """Degraus 0 a 3 do §7 numa chamada SO ao modulo da corrida.',
    '',
    '    Nenhum SQL aqui de proposito (D52): o fonte gerado so muda com',
    '    force_all, e uma consulta errada congelada em N pipelines nao teria',
    '    conserto barato. A regra da precedencia mora em utils/malha_corrida,',
    '    que tem teste unitario e gemeo na API.',
    '',
    # O aviso longo sobre a sonda mora na FACTORY, não aqui: o texto do §12.2
    # exige que a marca `_corrida.odate(` case só na CHAMADA — escrevê-la no
    # docstring emitido punha uma segunda ocorrência dentro do arquivo
    # publicado, e uma DAG que perdesse a chamada mas guardasse o texto passaria
    # na sonda dizendo OK.
    '    ⚠️ A chamada logo abaixo e a SONDA do §12.2 — ver o comentario na',
    '    factory antes de renomear o alias ou a funcao.',
    '',
    '    Devolve None quando nao ha o que responder (modulo ausente ou banco',
    '    fora): o chamador segue pela heranca e pelo calculo, como sempre."""',
    '    if _corrida is None:',
    '        return None',
    '    try:',
    '        _conn_od = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID).get_conn()',
    '        try:',
    '            return _corrida.odate(_conn_od, PIPELINE_NAME, run_id=run_id,',
    "                                  conf_id=conf.get('malha_execucao_id'),",
    '                                  herdada=herdada)',
    '        finally:',
    '            _conn_od.close()',
    '    except Exception as e:',
    "        print(f'[MALHA] ODATE da corrida indisponivel ({e}) — seguindo pelo calculo de sempre')",
    '        # FALHOU e diferente de NAO HA CORRIDA, e a diferenca custa caro:',
    '        # quem responde pelo calculo proprio grava a linha com essa data,',
    '        # e a partir dai o degrau 0 a le e a FIXA para o run inteiro. Um',
    '        # blip de pool no primeiro instante do run bastaria para trazer de',
    '        # volta o Carga_Vida — o membro carimbando a propria data enquanto',
    '        # a malha corre em outra. Marcando a falha, a proxima task tenta de',
    '        # novo em vez de herdar a resposta de um banco que estava mudo.',
    "        return {'falhou': True}",
    '',
    '# Memoria do ODATE por run_id (Decisao 36). NAO e cache de performance:',
    '# e o que impede a funcao de responder DUAS coisas diferentes no mesmo',
    '# run. O degrau 3 le estado MUTAVEL (a corrida aberta), e se ela fechar',
    '# no meio do pipeline a chamada seguinte cairia no degrau 4, calcularia',
    '# outra data, o UPDATE de _registrar_execucao erraria a chave e o INSERT',
    '# criaria uma SEGUNDA linha do mesmo run em outro ODATE — a doenca desta',
    '# spec, fabricada pela cura.',
    '#',
    '# Este dicionario cobre as chamadas do MESMO processo; o que atravessa',
    '# tasks (check_agenda as 01:10 e publish_dataset as 04:52 sao processos',
    '# diferentes) e o degrau 0 do modulo, que le o ODATE ja gravado na',
    '# linha deste run_id. Os dois juntos sao a memoizacao — sozinho, o',
    '# dicionario consertaria so a metade barata do problema.',
    '_ODATE_DO_RUN = {}',
    '',
    'def _odate_do_run(context):',
    '    """A resposta do §7 para ESTE run: {data, corrida, ambiguo, degrau,',
    '    detalhe}. Resolvida UMA vez por processo (Decisao 36)."""',
    "    run_id = str(context.get('run_id') or '')",
    '    if run_id in _ODATE_DO_RUN:',
    '        return _ODATE_DO_RUN[run_id]',
    "    dr = context.get('dag_run')",
    "    conf = (getattr(dr, 'conf', None) or {}) if dr is not None else {}",
    '    herdada = None',
    "    _bruto = conf.get('data_referencia')",
    '    if _bruto:',
    '        try:',
    '            from datetime import datetime as _dt',
    "            herdada = _dt.strptime(str(_bruto).strip(), '%Y-%m-%d').date()",
    '        except (ValueError, TypeError):',
    "            print(f'[EXEC] data_referencia herdada invalida ({_bruto!r}) — recalculando')",
    '    _resp = _odate_da_corrida(context, run_id, conf, herdada) or {}',
    "    if _resp.get('ambiguo'):",
    '        # Decisao 34: duas corridas abertas com ODATEs diferentes NAO se',
    '        # resolvem por escolha. A data aqui existe so para a linha PULADA',
    '        # ter onde morar (e o degrau 4, o calculo do proprio pipeline) —',
    '        # nenhuma corrida a reivindica, e por isso corrida fica None.',
    "        resposta = {'data': _odate_pela_virada(context), 'corrida': None,",
    "                    'ambiguo': True, 'degrau': _resp.get('degrau'),",
    "                    'detalhe': _resp.get('detalhe')}",
    "    elif _resp.get('data') is not None:",
    "        resposta = {'data': _resp['data'], 'corrida': _resp.get('corrida_id'),",
    "                    'ambiguo': False, 'degrau': _resp.get('degrau'),",
    "                    'detalhe': None}",
    '    elif herdada is not None:',
    '        # Degrau 2 SEM o modulo (deploy parcial / interruptor desligado):',
    '        # a heranca de hoje, com o mesmo resultado da linha de cima.',
    "        resposta = {'data': herdada, 'corrida': None, 'ambiguo': False,",
    "                    'degrau': 'conf_data', 'detalhe': None}",
    '    else:',
    "        resposta = {'data': _odate_pela_virada(context), 'corrida': None,",
    "                    'ambiguo': False, 'degrau': 'calculo', 'detalhe': None}",
    '    # Resposta dada com o banco MUDO nao vira memoria: memoizar aqui',
    '    # transformaria uma indisponibilidade de um segundo na data oficial',
    '    # do run inteiro. Sem memoizar, a proxima task refaz a pergunta — e',
    '    # se o banco ja tiver voltado, o degrau 0 (a linha gravada) responde.',
    '    # O risco residual esta declarado na §18: se a linha JA nasceu com a',
    '    # data do calculo, nada a reconcilia depois.',
    "    if _resp.get('falhou'):",
    '        print(f"[EXEC] ODATE de {PIPELINE_NAME}: {resposta[\'data\']} "',
    '              f"(degrau={resposta[\'degrau\']}) — resolvido SEM o banco, "',
    '              f"NAO memoizado; a proxima task pergunta de novo")',
    '        return resposta',
    '    # O dicionario e do RUN, nao do processo: um worker atende muitos runs',
    '    # e guardar todos vazaria memoria por nada.',
    '    if len(_ODATE_DO_RUN) > 20:',
    '        _ODATE_DO_RUN.clear()',
    '    _ODATE_DO_RUN[run_id] = resposta',
    '    print(f"[EXEC] ODATE de {PIPELINE_NAME}: {resposta[\'data\']} "',
    '          f"(degrau={resposta[\'degrau\']}, corrida={resposta[\'corrida\']})")',
    '    return resposta',
    '',
    'def _data_referencia(context):',
    '    """A que dia de processamento (ODATE) esta corrida pertence — a',
    '    precedencia do §7 da spec-malha-execucao, nesta ordem:',
    '',
    '    0) o ODATE ja gravado na linha deste run_id (o run tem UM ODATE, e',
    '       ele nao muda entre as tasks — Decisao 36);',
    "    1) conf['malha_execucao_id'], VALIDADO (corrida aberta e de malha",
    '       deste pipeline): a cascata por push dentro da corrida;',
    "    2) conf['data_referencia']: a heranca de hoje — push fora de malha,",
    '       rerun, disparo manual com data;',
    '    3) corrida ABERTA de alguma malha deste pipeline: o membro com cron',
    '       proprio ADERE ao ciclo em voo em vez de calcular a propria data',
    '       (Decisao 33 — o `Carga_Vida` invertido);',
    '    4) o calculo pela virada, byte a byte o de antes desta fase.',
    '',
    '    Os degraus 0, 1 e 3 so existem com a 085 aplicada E o interruptor',
    '    ligado; sem eles a funcao e, de fora, a mesma de sempre."""',
    "    return _odate_do_run(context)['data']",
]

_VELHO_REGISTRO_DATA = [
    '        data_ref = _data_referencia(context)',
]

_NOVO_REGISTRO_DATA = [
    '        _odate = _odate_do_run(context)',
    "        data_ref = _odate['data']",
    '        # F5 — PROVENIENCIA do ODATE desta linha (Decisao 1): de onde a',
    "        # data veio, nao 'de que malha o pipeline participa'. None = a",
    '        # linha nao veio de corrida nenhuma, que e o caso da imensa',
    '        # maioria e o unico caso possivel sem a 085.',
    "        _vinculo = _odate['corrida']",
]

_VELHO_UPSERT = [
    '        conn = hook.get_conn()',
    '        try:',
    '            cur = conn.cursor()',
    '            cur.execute(',
    "                'UPDATE dbo.etl_pipeline_execucao '",
    "                'SET status=%s, motivo=%s, disparado_por=%s, atualizado_em=GETDATE(), ' + upd_extra + ' '",
    "                'WHERE pipeline_name=%s AND data_referencia=%s AND execution_id=%s' + guarda_terminal,",
    '                (status, motivo, origem, PIPELINE_NAME, data_ref, run_id),',
    '            )',
    '            precisa_insert = (cur.rowcount == 0)',
    '            if precisa_insert and guarda_terminal:',
    "                # rowcount 0 com a guarda pode ser 'linha existe e e terminal'",
    '                # — nesse caso NAO insere (duplicaria a chave) nem rebaixa.',
    '                cur.execute(',
    "                    'SELECT 1 FROM dbo.etl_pipeline_execucao '",
    "                    'WHERE pipeline_name=%s AND data_referencia=%s AND execution_id=%s',",
    '                    (PIPELINE_NAME, data_ref, run_id),',
    '                )',
    '                if cur.fetchone():',
    "                    print(f'[EXEC] PULADO nao rebaixa estado terminal: {PIPELINE_NAME} run_id={run_id}')",
    '                    conn.commit()',
    '                    return',
    '            if precisa_insert:',
    '                cur.execute(',
    "                    'INSERT INTO dbo.etl_pipeline_execucao '",
    "                    '(pipeline_name, data_referencia, execution_id, status, inicio, fim, disparado_por, motivo) '",
    "                    'VALUES (%s, %s, %s, %s, ' + ins_inicio + ', ' + ins_fim + ', %s, %s)',",
    '                    (PIPELINE_NAME, data_ref, run_id, status, origem, motivo),',
    '                )',
    '            conn.commit()',
    '        finally:',
    '            conn.close()',
    "        print(f'[EXEC] {status} registrado: {PIPELINE_NAME} data_ref={data_ref} run_id={run_id} origem={origem}')",
]

_NOVO_UPSERT = [
    '        def _upsert(vinculo):',
    '            # WRITE-ONCE (Decisao 9): COALESCE(malha_execucao_id, %s) —',
    '            # o UPDATE roda a CADA estado do run e o Clear do rerun REUSA',
    '            # o run_id; sem o COALESCE, a linha da corrida #12',
    '            # reexecutada amanha passaria a pertencer a #13. Sem vinculo',
    '            # o texto do SQL fica IDENTICO ao de antes desta fase — e e',
    '            # esse o caminho de todo pipeline fora de malha e de todo',
    '            # banco sem a 085.',
    "            upd_corrida = (', malha_execucao_id=COALESCE(malha_execucao_id, %s)'",
    "                           if vinculo is not None else '')",
    '            par_corrida = (vinculo,) if vinculo is not None else ()',
    "            ins_col = ', malha_execucao_id' if vinculo is not None else ''",
    "            ins_val = ', %s' if vinculo is not None else ''",
    '            # Conexao propria por tentativa: o retry sem a coluna so',
    '            # acontece depois de um statement ter estourado, e insistir',
    '            # na mesma conexao herdaria a transacao abortada.',
    '            conn = hook.get_conn()',
    '            try:',
    '                cur = conn.cursor()',
    '                cur.execute(',
    "                    'UPDATE dbo.etl_pipeline_execucao '",
    "                    'SET status=%s, motivo=%s, disparado_por=%s, atualizado_em=GETDATE()' + upd_corrida + ', ' + upd_extra + ' '",
    "                    'WHERE pipeline_name=%s AND data_referencia=%s AND execution_id=%s' + guarda_terminal,",
    '                    (status, motivo, origem) + par_corrida + (PIPELINE_NAME, data_ref, run_id),',
    '                )',
    '                precisa_insert = (cur.rowcount == 0)',
    '                if precisa_insert and guarda_terminal:',
    "                    # rowcount 0 com a guarda pode ser 'linha existe e e terminal'",
    '                    # — nesse caso NAO insere (duplicaria a chave) nem rebaixa.',
    '                    cur.execute(',
    "                        'SELECT 1 FROM dbo.etl_pipeline_execucao '",
    "                        'WHERE pipeline_name=%s AND data_referencia=%s AND execution_id=%s',",
    '                        (PIPELINE_NAME, data_ref, run_id),',
    '                    )',
    '                    if cur.fetchone():',
    "                        print(f'[EXEC] PULADO nao rebaixa estado terminal: {PIPELINE_NAME} run_id={run_id}')",
    '                        conn.commit()',
    '                        return True',
    '                if precisa_insert:',
    '                    cur.execute(',
    "                        'INSERT INTO dbo.etl_pipeline_execucao '",
    "                        '(pipeline_name, data_referencia, execution_id, status, inicio, fim, disparado_por, motivo' + ins_col + ') '",
    "                        'VALUES (%s, %s, %s, %s, ' + ins_inicio + ', ' + ins_fim + ', %s, %s' + ins_val + ')',",
    '                        (PIPELINE_NAME, data_ref, run_id, status, origem, motivo) + par_corrida,',
    '                    )',
    '                conn.commit()',
    '            finally:',
    '                conn.close()',
    '            return False',
    '        try:',
    '            _terminal = _upsert(_vinculo)',
    '        except Exception as _e_085:',
    '            # Cascata do _MARCA_085 (a mesma de utils/dependencias.py): o',
    '            # deploy pode ter subido dags/ novo num banco sem a 085. Nesse',
    '            # caso a linha e gravada SEM a coluna — perder o registro da',
    '            # execucao porque o vinculo nao cabe seria trocar um dado',
    '            # extra por todo o resto.',
    "            if _vinculo is None or 'malha_execucao_id' not in str(_e_085):",
    '                raise',
    "            print(f'[EXEC] coluna malha_execucao_id ausente ({_e_085}) — registrando sem o vinculo da corrida')",
    '            _terminal = _upsert(None)',
    '        if _terminal:',
    '            return',
    "        print(f'[EXEC] {status} registrado: {PIPELINE_NAME} data_ref={data_ref} run_id={run_id} origem={origem}'",
    "              + (f' corrida=#{_vinculo}' if _vinculo is not None else ''))",
]

_VELHO_PUSH_DATA = [
    '        data_ref = _data_referencia(context)',
]

_NOVO_PUSH_DATA = [
    '        _odate = _odate_do_run(context)',
    "        data_ref = _odate['data']",
    '        # F5 — a corrida do PAI viaja no conf (§7, degrau 1). E',
    '        # otimizacao de heranca, nunca identidade: o filho valida o id',
    '        # antes de obedecer (Decisao 37). Sem corrida, a chave nem entra',
    '        # no conf e o disparo sai como sempre saiu.',
    "        _corrida_pai = _odate['corrida']",
]

# A recusa por ODATE ambiguo na porta do PUSH. Vem logo depois do bloco da F4
# acima (que ja era declarado): as duas travas sao vizinhas de proposito — a de
# cima cuida de predecessores em datas diferentes, esta cuida do FILHO que e
# membro de duas malhas com corridas abertas em ODATEs diferentes.
_DELTA_PUSH_AMBIGUO = [
    '                    # F5 (Decisao 35) — a recusa por ODATE ambiguo vale',
    '                    # TAMBEM nesta porta, e e AQUI que ela dispara de',
    '                    # verdade: a checagem da agenda so roda em disparo por',
    '                    # cron, e o pipeline compartilhado por duas malhas e,',
    '                    # quase por definicao, um DEPENDENTE — ele chega por',
    '                    # push. Empurrar a data do pai para dentro dele faria',
    '                    # uma das duas corridas rodar com o ODATE da outra, que',
    '                    # e o incidente Carga_Vida por dentro do mecanismo',
    '                    # criado para mata-lo.',
    '                    _od_filho = (_corrida.odate(conn, filho) if _corrida is not None',
    "                                 else {'data': None, 'corrida_id': None,",
    "                                       'ambiguo': False, 'detalhe': None})",
    "                    if _od_filho['ambiguo']:",
    '                        print(f"[DEP] {filho} NAO disparado — {_od_filho[\'detalhe\']}")',
    '                        try:',
    '                            _dep_gravar_evento(conn, filho, data_ref,',
    "                                               'DATA_DIVERGENTE',",
    "                                               _od_filho['detalhe'])",
    '                            conn.commit()',
    '                        except Exception as _e_amb:',
    "                            print(f'[DEP] evento de ODATE ambiguo de {filho} nao gravado: {_e_amb}')",
    '                        continue',
]

_DELTA_PUSH_GANHO = [
    '                        # F5 (Decisao 35) — ate aqui isto era SILENCIO',
    '                        # TOTAL: a malha A empurrava e ganhava o claim, a',
    '                        # malha B empurrava, recebia None, imprimia esta',
    '                        # linha e seguia. A corrida B ficava sem o membro',
    '                        # e nada no banco dizia por que. O evento e a',
    '                        # marca — e so existe quando ha corrida aberta do',
    '                        # filho DIFERENTE da do pai; disputa comum entre',
    '                        # dois pais da MESMA corrida continua muda.',
    '                        #',
    '                        # As DUAS proveniencias tem de ser CONHECIDAS: o',
    "                        # `corrida_id` e None tanto para 'nao ha corrida'",
    "                        # quanto para 'ha duas do MESMO ODATE e nenhuma e",
    "                        # dona' (Decisao 2), e comparar None com um id",
    '                        # trata desconhecido como diferente. Reproduzido',
    '                        # no dev em 2026-08-05: pai e filho na MESMA',
    '                        # corrida #666, o pai sem dono so por tambem ser',
    '                        # membro da #667 do mesmo dia, e o evento saia',
    "                        # dizendo 'corrida #None empurrou' — alarme falso",
    '                        # exatamente no caso que a F5 existe para tratar,',
    '                        # e alarme falso ensina a ignorar o canal.',
    "                        if (_od_filho['corrida_id'] is not None",
    '                                and _corrida_pai is not None',
    "                                and _od_filho['corrida_id'] != _corrida_pai):",
    '                            _det_sm = (f"MALHA_CORRIDA_SEM_MEMBRO: {filho} ja tinha "',
    '                                       f"corrida em {data_ref} quando {PIPELINE_NAME} "',
    '                                       f"(corrida #{_corrida_pai}) empurrou — o membro "',
    '                                       f"ficou com a corrida #{_od_filho[\'corrida_id\']} "',
    '                                       f"e nenhuma execucao nova foi criada")',
    '                            try:',
    '                                _dep_gravar_evento(conn, filho, data_ref,',
    "                                                   'DATA_DIVERGENTE', _det_sm)",
    '                                conn.commit()',
    '                            except Exception as _e_sm:',
    "                                print(f'[DEP] evento de membro tomado ({filho}) nao gravado: {_e_sm}')",
]

_VELHO_PUSH_CONF = [
    '                    try:',
    '                        from airflow.api.client.local_client import Client',
    '                        Client(None, None).trigger_dag(',
    '                            dag_id=filho, run_id=ganho,',
    '                            conf=_dep_montar_conf(data_ref, dia_op, PIPELINE_NAME))',
]

# A montagem do conf sai de DENTRO do `try` do trigger e ganha rede para o
# ROLLBACK: com `dags/utils/` revertido para antes da F5 e o `generated/` ainda
# regerado (o force_all não se desfaz no deploy, e o deploy nunca limpa a
# pasta), a chamada de 4 argumentos levantava TypeError, a reserva era devolvida
# e a CASCATA INTEIRA parava com o pai VERDE — medido no dev em 2026-08-05.
_NOVO_PUSH_CONF = [
    '                    try:',
    '                        _conf_f = _dep_montar_conf(data_ref, dia_op,',
    '                                                   PIPELINE_NAME, _corrida_pai)',
    '                    except TypeError:',
    '                        # ROLLBACK da F5: `dags/utils/` volta para antes da',
    '                        # fase (montar_conf de 3 argumentos) mas o',
    '                        # `generated/` continua o regerado — o force_all',
    '                        # NAO se desfaz no deploy e o deploy nunca limpa a',
    '                        # pasta. Sem esta rede, TODO disparo por',
    '                        # dependencia levanta TypeError, a reserva e',
    '                        # devolvida e a CASCATA INTEIRA para com o pai',
    '                        # VERDE (medido no dev em 2026-08-05). A chave da',
    '                        # corrida e ADITIVA: perde-la e perder a',
    '                        # otimizacao de heranca, nao a carga — o filho',
    '                        # resolve a proveniencia sozinho pelo degrau 0.',
    "                        print('[DEP] utils.dependencias anterior a F5 — '",
    "                              'conf sem a corrida do pai')",
    '                        _conf_f = _dep_montar_conf(data_ref, dia_op, PIPELINE_NAME)',
    '                    try:',
    '                        from airflow.api.client.local_client import Client',
    '                        Client(None, None).trigger_dag(',
    '                            dag_id=filho, run_id=ganho, conf=_conf_f)',
]

# F6 — a porta do PUSH passa a entregar ao predicado a corrida da LINHA
# avaliada (a do FILHO, `_od_filho['corrida_id']`), que no modo SEQUÊNCIA é o
# 1º degrau do corte da §8. Uma linha vira um bloco, então é TROCA e não adição.
# A rede de `TypeError` é a mesma que a F5 precisou em `montar_conf`, pelo mesmo
# motivo: `dags/utils/` revertido com o `generated/` já regerado faria TODO push
# levantar e a cascata inteira parar com o pai VERDE.
_VELHO_PUSH_LIBERADO = [
    '                    lib, faltantes = _dep_liberado(conn, filho, data_ref)',
]

_NOVO_PUSH_LIBERADO = [
    '                    # F6 (Decisao 39) — a corrida da LINHA avaliada entra',
    '                    # no predicado. A linha avaliada e a do FILHO, entao a',
    '                    # corrida e a dele (`_od_filho`), nunca a do pai: no',
    '                    # modo SEQUENCIA e o `aberta_em` DELA que corta o que',
    '                    # conta como sucesso desta rodada. Ela vem como',
    "                    # PARAMETRO — se fosse subconsulta por 'corrida aberta",
    "                    # agora', uma corrida que fechasse entre duas",
    '                    # avaliacoes derrubaria o corte para a janela de 12h em',
    '                    # SILENCIO, no meio da madrugada.',
    '                    try:',
    '                        lib, faltantes = _dep_liberado(',
    "                            conn, filho, data_ref, _od_filho['corrida_id'])",
    '                    except TypeError:',
    '                        # ROLLBACK da F6: `dags/utils/` volta para antes da',
    '                        # fase (liberado de 3 argumentos) e o `generated/`',
    '                        # segue regerado — a mesma rede que a F5 precisou',
    '                        # em `montar_conf`, pelo mesmo motivo: sem ela TODO',
    '                        # push levanta TypeError e a cascata inteira para',
    '                        # com o pai VERDE. A corrida e ADITIVA — sem ela o',
    '                        # corte cai no degrau 2, que resolve a corrida pela',
    '                        # malha que ASSINOU a dependencia.',
    "                        print('[DEP] utils.dependencias anterior a F6 — '",
    "                              'liberacao sem a corrida da linha')",
    '                        lib, faltantes = _dep_liberado(conn, filho, data_ref)',
]

# As trocas, em pares (novo, velho). Removidas as adicoes, o que sobra tem de
# voltar a ser, byte a byte, o texto do commit base.
_TROCAS_DA_CORRIDA = [
    (_NOVO_CABECALHO_ODATE, _VELHO_CABECALHO_ODATE),
    (_NOVO_REGISTRO_DATA, _VELHO_REGISTRO_DATA),
    (_NOVO_UPSERT, _VELHO_UPSERT),
    (_NOVO_PUSH_DATA, _VELHO_PUSH_DATA),
    (_NOVO_PUSH_LIBERADO, _VELHO_PUSH_LIBERADO),
    (_NOVO_PUSH_CONF, _VELHO_PUSH_CONF),
]



def _ocorrencias(linhas, bloco):
    return [i for i in range(len(linhas) - len(bloco) + 1)
            if linhas[i:i + len(bloco)] == bloco]


def _remover_delta(src: str) -> str:
    """Devolve o fonte SEM o delta das fases — a operação inversa exata do que a
    factory passou a emitir. Falha ruidosamente (AssertionError) se um dos
    blocos não estiver lá exatamente uma vez: 'não achei o bloco' não pode
    virar 'byte-idêntico'.

    Dois modos, e o segundo nasceu na F5 da corrida: **remoção** (o bloco é
    acréscimo puro — sai e pronto) e **troca** (a fase REESCREVEU um trecho que
    já existia — o novo volta a ser o velho, exatamente como
    ``_TROCA_LOG_START`` sempre fez para o operador do log_start). Uma fase que
    reescreve sem declarar a troca quebra aqui, que é o ponto."""
    velho, novo = _TROCA_LOG_START
    assert src.count(velho) >= 1, "nenhum t_start com o operador da F5"
    src = src.replace(velho, novo)
    linhas = src.split("\n")
    for bloco_novo, bloco_velho in _TROCAS_DA_CORRIDA:
        ocorrencias = _ocorrencias(linhas, bloco_novo)
        assert len(ocorrencias) == 1, (
            f"troca da corrida esperada 1x, encontrada {len(ocorrencias)}x: "
            f"{bloco_novo[0]!r}")
        i = ocorrencias[0]
        linhas = linhas[:i] + bloco_velho + linhas[i + len(bloco_novo):]
    for bloco in (_DELTA_IMPORT, _DELTA_IMPORT_CORRIDA, _DELTA_LOG_START,
                  _DELTA_DIVERGENCIA_IMPORT, _DELTA_DIVERGENCIA_IMPORT2,
                  _DELTA_DIVERGENCIA_IMPORT3, _DELTA_DIVERGENCIA,
                  _DELTA_PUSH_AMBIGUO, _DELTA_PUSH_GANHO,
                  _DELTA_ODATE, _DELTA_MALHA_CICLO):
        ocorrencias = _ocorrencias(linhas, bloco)
        # Os blocos do PUSH só existem em pipeline com dependência: cenário
        # sem dependente gera o fonte sem eles, e ausência ali é correta.
        opcional = bloco in (_DELTA_DIVERGENCIA_IMPORT, _DELTA_DIVERGENCIA_IMPORT2,
                             _DELTA_DIVERGENCIA_IMPORT3, _DELTA_DIVERGENCIA)
        assert len(ocorrencias) == 1 or (opcional and not ocorrencias), (
            f"bloco do delta esperado 1x, encontrado {len(ocorrencias)}x: "
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
