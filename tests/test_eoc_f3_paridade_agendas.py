"""EOC-F3 L3: igualdade legado × workspace nas 8 agendas.

A mesma intenção de agenda entra pelos dois caminhos reais e chega à factory:

- legado: o body que o PipelineFormModal monta (buildSchedulePayload real, pela
  bancada JS) → POST /pipelines/register (dublê estatal da F5) → linha gravada;
- workspace: o legacyPipeline que o WorkspaceScheduleFields real emite →
  validate_projection → linha projetada.

As duas linhas passam por etl_dag_factory._build_cron e _generate_dag_source. A
comparação cobre cron, linha `schedule=` e as constantes de agenda
(CALENDARIO_NOME, SOMENTE_DIAS_UTEIS, HORARIOS_ESPECIFICOS, DIAS_HORARIOS_MES,
RESTRICAO_DIA). Cada cenário também prende o cron esperado: uma mudança comum
aos dois caminhos (factory ou pipelineUtils) não passa como "igual".

Sem produto cartesiano: os 8 modos, os limites de cada um e hourly_n como lista.
"""
from __future__ import annotations

import ast
import datetime
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from services.workspace_publication import validate_projection
from tests.test_dependencias_f5 import FakePipeDb, _body_registro, _linha_pipeline, _patch_airflow, _patch_db
from tests.test_dependencias_f5 import auth_editor  # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parents[1]
for _mod in ["airflow", "airflow.decorators", "airflow.models", "airflow.operators", "airflow.operators.python",
             "airflow.operators.empty", "airflow.operators.bash", "airflow.providers.microsoft.mssql.hooks.mssql",
             "airflow.utils", "airflow.utils.trigger_rule", "airflow.sensors.external_task", "airflow.datasets",
             "pendulum", "airflow.providers.ssh.hooks.ssh", "airflow.utils.dates", "airflow.exceptions"]:
    sys.modules.setdefault(_mod, MagicMock())

AGENDA = ('scheduled_time', 'schedule_type', 'schedule_hour', 'schedule_minute', 'schedule_dow', 'schedule_dom',
          'horarios_especificos', 'dias_semana', 'dias_horarios_mes', 'somente_dias_uteis', 'calendario_nome')
CONSTANTES = ('CALENDARIO_NOME', 'SOMENTE_DIAS_UTEIS', 'HORARIOS_ESPECIFICOS', 'DIAS_HORARIOS_MES')
FACTORY_BASE = {'pipeline_name': 'PIPE_A', 'project_name': 'BI_CVP', 'domain': 'GERAL', 'tags': 'ETL',
                'envia_msg_inicio': 0, 'envia_msg_fim': 0, 'envia_msg_erro': 1, 'ambiente': 'PROD'}
JOB = {'job_name': 'Carga', 'job_type': 'shell', 'job_command': 'echo ok', 'execution_order': 1}

CRON = {
    'daily': '30 9 * * *', 'daily_meia_noite': '0 0 * * *', 'daily_23_59': '59 23 * * *',
    'weekly_domingo': '5 7 * * 0', 'weekly_sabado': '0 18 * * 6',
    'monthly_1': '0 6 1 * *', 'monthly_28': '15 2 28 * *', 'biweekly_13': '45 5 13,28 * *',
    'custom': '5,30 9,14 * * 1,3,5', 'monthly_days_times': '0,30 6,9,18 5,15 * *', 'on_demand': None,
}
HOURLY = {  # (a cada N, início, fim, minuto) → lista que os dois lados devem gravar
    (2, 8, 18, 0): ['08:00', '10:00', '12:00', '14:00', '16:00', '18:00'],
    (3, 0, 23, 15): ['00:15', '03:15', '06:15', '09:15', '12:15', '15:15', '18:15', '21:15'],
    (1, 0, 23, 45): [f'{h:02d}:45' for h in range(24)],
    (5, 22, 23, 0): ['22:00'],
    (23, 0, 23, 59): ['00:59', '23:59'],
    (4, 7, 7, 30): ['07:30'],
}


@pytest.fixture(scope='module')
def bancada():
    if not shutil.which('node') or not (ROOT / 'ui-react/node_modules/sucrase').is_dir():
        pytest.skip('Node/sucrase indisponível')
    result = subprocess.run(['node', 'tests/js/eoc_f3_agendas_harness.cjs'], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.fixture(scope='module')
def factory():
    spec = importlib.util.spec_from_file_location('etl_dag_factory_eoc_f3_agendas', ROOT / 'dags/etl_dag_factory.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def dias_permitidos():
    """Dias de mar/2026 que o check_agenda do dependente aceita para RESTRICAO_DIA."""
    spec = importlib.util.spec_from_file_location('dependencias_eoc_f3_agendas', ROOT / 'dags/utils/dependencias.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return lambda regras: [d for d in range(1, 32) if module.dia_permitido(regras, datetime.date(2026, 3, d))[0]]


@pytest.fixture
def legado(client, auth_editor, monkeypatch):  # noqa: F811
    """Body do modal → register real → linha de etl_pipeline gravada."""
    # Mesmo schema do dublê da F5 (anterior à 130); snapshot de parâmetros não é agenda.
    monkeypatch.setattr('services.param_snapshot.ativo', lambda cur, pipeline: False)

    def gravar(payload):
        db = FakePipeDb(pipelines={'PIPE_A': _linha_pipeline()})
        with _patch_db(db), _patch_airflow():
            response = client.post('/pipelines/register', json=_body_registro(**payload))
        assert response.status_code == 200, response.text
        return db.pipelines['PIPE_A']
    return gravar


def projetar(agenda, existing=None):
    """legacyPipeline do rascunho → validate_projection → (diagnósticos, linha projetada)."""
    pipeline = {'pipeline_name': 'PIPE_A', 'project_name': 'BI_CVP', 'domain': 'GERAL', 'active': 1, **agenda}
    definition = {'schemaVersion': 1, 'identity': {'pipelineName': 'PIPE_A'}, 'metadata': {'legacyPipeline': pipeline},
                  'nodes': [{'id': 'Carga', 'type': 'shell', 'configuration': {'legacyJob': {'job_command': 'echo ok', 'ssh_conn_id': 'ssh'}}}],
                  'edges': []}
    errors, projection = validate_projection(definition, {'nodes': {}}, existing or {}, {'ssh': 'ssh'})
    return errors, projection and projection['etl_pipeline'][0]


def publicado(agenda):
    errors, row = projetar(agenda)
    assert errors == [], errors
    return row


def dag(factory, row):
    """O que a factory gera a partir das colunas de agenda da linha."""
    pipeline = {**FACTORY_BASE, **{column: row.get(column) for column in AGENDA}}
    cron = factory._build_cron(pipeline)
    lines = factory._generate_dag_source(pipeline, [dict(JOB)]).splitlines()
    out = {'cron': cron, 'schedule': [line.strip() for line in lines if line.startswith('    schedule=')],
           'RESTRICAO_DIA': factory._derivar_restricao_dia(pipeline, cron[2])}
    for name in CONSTANTES:
        [line] = [line for line in lines if re.match(name + r'\s*=', line)]
        out[name] = line
        out[name + ':valor'] = ast.literal_eval(line.split('=', 1)[1].strip())
    return out


# ── Cobertura dos modos ─────────────────────────────────────────────────────

def test_os_oito_modos_da_tela_e_os_sete_persistidos_estao_cobertos(bancada):
    fonte = (ROOT / 'ui-react/src/components/pipelines/pipelineUtils.ts').read_text()
    modos = re.findall(r"'(\w+)'", re.search(r'SCHEDULE_TYPES = \[(.*?)\]', fonte).group(1))
    assert len(modos) == 8
    cobertos = {c['tipoWorkspace'] for c in bancada['cenarios'].values()} | {h['tipoWorkspace'] for h in bancada['hourly']}
    assert cobertos == set(modos)
    persistidos = {c['legado']['schedule_type'] for c in bancada['cenarios'].values()} | {h['legado']['schedule_type'] for h in bancada['hourly']}
    assert persistidos == set(modos) - {'hourly_n'}
    for nome, caso in bancada['cenarios'].items():
        assert caso['workspace']['schedule_type'] == caso['legado']['schedule_type'], nome


# ── Igualdade por modo ───────────────────────────────────────────────────────

@pytest.mark.parametrize('nome', list(CRON))
def test_legado_e_workspace_geram_o_mesmo_cron_e_as_mesmas_constantes(nome, bancada, factory, legado):
    caso = bancada['cenarios'][nome]
    pelo_legado, pelo_workspace = dag(factory, legado(caso['legado'])), dag(factory, publicado(caso['workspace']))
    assert pelo_workspace == pelo_legado
    assert pelo_legado['cron'][0] == CRON[nome]
    expected = 'schedule=None,  # sob demanda: só execução manual' if CRON[nome] is None else f'schedule="{CRON[nome]}",'
    assert pelo_legado['schedule'] == [expected]


def test_constantes_de_cada_modo_tem_o_valor_do_cadastro(bancada, factory, legado):
    def valores(nome):
        return dag(factory, publicado(bancada['cenarios'][nome]['workspace']))
    semanal = valores('weekly_domingo')
    assert (semanal['SOMENTE_DIAS_UTEIS:valor'], semanal['CALENDARIO_NOME:valor']) == (True, 'FERIADOS_B3')
    # Domingo é 0, não o padrão 1, também na restrição do dependente.
    assert semanal['RESTRICAO_DIA'] == {'schedule_type': 'weekly', 'schedule_dow': 0, 'schedule_dom': 1, 'dias_semana': '', 'dias_horarios_mes_dias': None}
    assert valores('custom')['HORARIOS_ESPECIFICOS:valor'] == ['09:05', '14:30']
    assert valores('custom')['RESTRICAO_DIA']['dias_semana'] == '1,3,5'
    assert valores('monthly_days_times')['DIAS_HORARIOS_MES:valor'] == {5: ['09:00'], 15: ['06:30', '18:00']}
    assert valores('biweekly_13')['RESTRICAO_DIA']['schedule_dom'] == 13
    sob_demanda = valores('on_demand')
    assert sob_demanda['cron'] == (None, None, None) and sob_demanda['RESTRICAO_DIA'] is None


@pytest.mark.parametrize('nome', ['monthly_days_times_fora_de_ordem', 'custom_repetido'])
def test_texto_livre_do_workspace_gera_o_mesmo_cron_e_a_mesma_agenda_efetiva(nome, bancada, factory, legado):
    """O workspace guarda o texto digitado (sem normalização silenciosa); o legado normaliza.

    O cron é o mesmo. As constantes têm a mesma agenda efetiva: o check_agenda só
    testa pertinência (`_hhmm not in HORARIOS_ESPECIFICOS`, `DIAS_HORARIOS_MES.get(dia)`).
    """
    caso = bancada['cenarios'][nome]
    pelo_legado, pelo_workspace = dag(factory, legado(caso['legado'])), dag(factory, publicado(caso['workspace']))
    assert caso['workspace'] != caso['legado']
    assert pelo_workspace['cron'][0] == pelo_legado['cron'][0]
    assert pelo_workspace['schedule'] == pelo_legado['schedule']
    if nome == 'custom_repetido':
        assert pelo_legado['cron'][0] == '0 8,9 * * 1'
        assert set(pelo_workspace['HORARIOS_ESPECIFICOS:valor']) == set(pelo_legado['HORARIOS_ESPECIFICOS:valor']) == {'08:00', '09:00'}
    else:
        assert pelo_legado['cron'][0] == '0,30 6,9,18 5,15 * *'
        assert pelo_workspace['DIAS_HORARIOS_MES:valor'] == pelo_legado['DIAS_HORARIOS_MES:valor'] == {5: ['09:00'], 15: ['06:30', '18:00']}


# ── hourly_n: açúcar de custom, mesma lista na mesma janela ─────────────────

@pytest.mark.parametrize('janela', list(HOURLY), ids=lambda j: 'a%d_%02d-%02d_m%02d' % j)
def test_hourly_n_mesma_janela_grava_a_mesma_lista_e_o_mesmo_cron(janela, bancada, factory, legado):
    [caso] = [h for h in bancada['hourly'] if tuple(h['janela']) == janela]
    lista = HOURLY[janela]
    assert caso['lista'] == lista and caso['tipoWorkspace'] == 'hourly_n'
    for lado in (caso['legado'], caso['workspace']):
        assert lado['schedule_type'] == 'custom'
        assert lado['horarios_especificos'] == ','.join(lista)
        assert lado['scheduled_time'] == lista[0] + ':00'
    pelo_legado, pelo_workspace = dag(factory, legado(caso['legado'])), dag(factory, publicado(caso['workspace']))
    assert pelo_workspace == pelo_legado
    minutos, horas = sorted({t[3:] for t in lista}), sorted({t[:2] for t in lista})
    assert pelo_legado['cron'][0] == f"{','.join(str(int(m)) for m in minutos)} {','.join(str(int(h)) for h in horas)} * * *"
    assert pelo_legado['HORARIOS_ESPECIFICOS:valor'] == lista


def test_hourly_n_com_janela_invertida_nao_publica(bancada):
    [caso] = [h for h in bancada['hourly'] if h['janela'] == [2, 18, 8, 0]]
    assert caso['lista'] == [] and caso['workspace']['horarios_especificos'] == ''
    errors, _ = projetar(caso['workspace'])
    assert [(e['field'], e['code']) for e in errors] == [('horarios_especificos', 'schedule')]
    # O legado barra a mesma janela no formulário, antes do envio.
    assert "Hora de término deve ser ≥ hora de início" in (ROOT / 'ui-react/src/components/pipelines/PipelineFormModal.tsx').read_text()


# ── Limites: None, booleano, dias e horário ─────────────────────────────────

@pytest.mark.parametrize('agenda,cron', [
    ({'schedule_type': 'weekly', 'scheduled_time': '06:00:00', 'schedule_dow': None}, '0 6 * * 1'),
    ({'schedule_type': 'monthly', 'scheduled_time': '06:00:00', 'schedule_dom': None}, '0 6 1 * *'),
    ({'schedule_type': 'biweekly', 'scheduled_time': '06:00:00', 'schedule_dom': None}, '0 6 1,16 * *'),
])
def test_dia_nulo_no_rascunho_vale_o_mesmo_padrao_que_o_formulario_grava(agenda, cron, factory, legado, dias_permitidos):
    # O formulário legado reabre NULL como 1 (`?? 1`) e grava 1; o rascunho preserva NULL.
    pelo_legado = dag(factory, legado({**agenda, 'schedule_dow': 1, 'schedule_dom': 1}))
    pelo_workspace = dag(factory, publicado(agenda))
    restricoes = pelo_legado.pop('RESTRICAO_DIA'), pelo_workspace.pop('RESTRICAO_DIA')
    assert pelo_workspace == pelo_legado and pelo_legado['cron'][0] == cron
    # RESTRICAO_DIA é repasse da coluna (None × 1); dia_permitido aplica o mesmo padrão 1.
    assert restricoes[1]['schedule_dow'] is None and restricoes[0]['schedule_dow'] == 1
    assert dias_permitidos(restricoes[1]) == dias_permitidos(restricoes[0]) == {'weekly': [2, 9, 16, 23, 30], 'monthly': [1], 'biweekly': [1, 16]}[agenda['schedule_type']]


@pytest.mark.parametrize('agenda,field', [
    ({'schedule_type': 'weekly', 'schedule_dow': True}, 'schedule_dow'),
    ({'schedule_type': 'weekly', 'schedule_dow': 7}, 'schedule_dow'),
    ({'schedule_type': 'weekly', 'schedule_dow': -1}, 'schedule_dow'),
    ({'schedule_type': 'weekly', 'schedule_dow': '0'}, 'schedule_dow'),
    ({'schedule_type': 'monthly', 'schedule_dom': False}, 'schedule_dom'),
    ({'schedule_type': 'monthly', 'schedule_dom': 0}, 'schedule_dom'),
    ({'schedule_type': 'monthly', 'schedule_dom': 29}, 'schedule_dom'),
    ({'schedule_type': 'biweekly', 'schedule_dom': 14}, 'schedule_dom'),
    ({'schedule_type': 'custom', 'horarios_especificos': '09:00', 'dias_semana': '1,7'}, 'dias_semana'),
    ({'schedule_type': 'custom', 'horarios_especificos': '09:00', 'dias_semana': ' 1'}, 'dias_semana'),
    ({'schedule_type': 'custom', 'horarios_especificos': '24:00'}, 'schedule'),
    ({'schedule_type': 'monthly_days_times', 'dias_horarios_mes': '[{"dia": 29, "horarios": ["09:00"]}]'}, 'schedule'),
    ({'schedule_type': 'daily', 'scheduled_time': '24:00:00'}, 'scheduled_time'),
    ({'schedule_type': 'daily', 'scheduled_time': '9:30'}, 'scheduled_time'),
    ({'schedule_type': 'daily', 'scheduled_time': ':00'}, 'scheduled_time'),
    ({'schedule_type': 'hourly_n', 'horarios_especificos': '08:00'}, 'schedule_type'),
])
def test_dia_ou_horario_fora_do_contrato_nao_publica(agenda, field):
    errors, _ = projetar({'scheduled_time': '06:00:00', **agenda})
    assert [(e['field'], e['code']) for e in errors] == [(field, 'schedule')]


def test_somente_dias_uteis_booleano_do_leitor_e_inteiro_do_formulario_geram_a_mesma_constante(bancada, factory, legado):
    caso = bancada['cenarios']['weekly_domingo']
    assert caso['legado']['somente_dias_uteis'] == 1
    pelo_leitor = publicado({**caso['workspace'], 'somente_dias_uteis': True})
    assert dag(factory, pelo_leitor) == dag(factory, legado(caso['legado']))


def test_tipo_nulo_publica_o_mesmo_diario_que_o_legado_e_sem_horario_nao_publica(bancada, factory, legado):
    """Linha antiga sem schedule_type: legado e factory entendem diário.

    Sem horário, a publicação recusa; senão a factory geraria 06:00 diário em silêncio.
    """
    assert bancada['leitura']['tipo_nulo']['legado'] == 'daily'
    linha = {'schedule_type': None, 'scheduled_time': '06:00:00', 'schedule_hour': 6, 'schedule_minute': 0}
    gravado = legado({**linha, 'schedule_type': 'daily'})
    assert dag(factory, publicado(linha)) == dag(factory, gravado)
    assert dag(factory, gravado)['cron'][0] == '0 6 * * *'
    errors, _ = projetar({'schedule_type': None, 'scheduled_time': None})
    assert [(e['field'], e['code']) for e in errors] == [('scheduled_time', 'schedule')]


# ── Leitura de linha existente: a tela mostra o que o motor executa (R1/R2) ──

# Tipo que o workspace deve mostrar e o cron que a factory gera da mesma linha.
LEITURA = {
    'tipo_nulo': ('daily', '0 6 * * *'),
    'tipo_nulo_sem_horario': ('daily', '0 6 * * *'),
    'tipo_vazio': ('daily', '15 7 * * *'),
    'tipo_ausente': ('daily', '0 6 * * *'),
    'daily_com_horarios': ('custom', '0 9,14 * * *'),
    'nulo_com_horarios': ('custom', '0 9,14 * * 1,3'),
    'weekly_com_horarios': ('custom', '30 8 * * *'),
    'daily_horarios_em_branco': ('daily', '0 6 * * *'),
    'daily_horarios_ilegiveis': ('daily', '0 6 * * *'),
    'daily_com_dias_do_mes': ('daily', '0 6 * * *'),
    'on_demand': ('on_demand', None),
    'on_demand_com_horarios': ('on_demand', None),
    'custom': ('custom', '0 9,14 * * *'),
}
# O pipelineToForm abre estas linhas num tipo que a factory não executa (tipo vazio
# fica '', horários ilegíveis ou em sob demanda, dias do mês fora de
# monthly_days_times). O workspace segue o motor; a divergência é do formulário
# legado e fica fora deste corretivo.
LEGADO_DIVERGE_DO_MOTOR = {'tipo_vazio', 'daily_horarios_ilegiveis', 'daily_com_dias_do_mes', 'on_demand_com_horarios'}


@pytest.mark.parametrize('nome', list(LEITURA))
def test_linha_existente_abre_no_tipo_que_o_motor_executa_sem_tocar_a_definicao(nome, bancada, factory):
    leitura, (tipo, cron) = bancada['leitura'][nome], LEITURA[nome]
    cron_gerado, horarios, _ = factory._build_cron(leitura['linha'])
    assert cron_gerado == cron
    assert leitura['workspace'] == tipo
    # Coerência com o motor: só sob demanda fica sem cron; só horários específicos têm lista.
    assert (tipo == 'on_demand') == (cron_gerado is None)
    assert (tipo == 'custom') == (horarios is not None)
    assert leitura['semDisparo'] == (tipo == 'on_demand')
    assert leitura['intacto'], 'a leitura não pode reescrever o legacyPipeline'
    if nome not in LEGADO_DIVERGE_DO_MOTOR:
        assert leitura['legado'] == tipo
    assert bancada['regra'] is not None and bancada['regra'][nome] == tipo


def test_r1_tipo_nulo_mostra_diario_com_o_horario_da_linha(bancada):
    assert (bancada['leitura']['tipo_nulo']['horario'], bancada['leitura']['tipo_vazio']['horario']) == ('06:00', '07:15')
    sem_horario = bancada['leitura']['tipo_nulo_sem_horario']
    assert (sem_horario['workspace'], sem_horario['horario']) == ('daily', '')
    # A recusa pede o horário do diário que a tela mostra, em vez de contradizer um "Sob demanda" selecionado.
    errors, _ = projetar({'schedule_type': None, 'scheduled_time': None})
    assert [(e['field'], e['message']) for e in errors] == [('scheduled_time', 'Informe horário válido ou selecione sob demanda')]


def test_r2_horarios_da_linha_aparecem_no_campo_e_editar_muda_o_cron(bancada, factory):
    for nome in ('daily_com_horarios', 'nulo_com_horarios', 'weekly_com_horarios', 'custom'):
        leitura = bancada['leitura'][nome]
        assert (leitura['horarios'], leitura['horario']) == (leitura['linha']['horarios_especificos'], None), nome
    editada = bancada['leitura_editada']
    assert 'erro' not in editada, editada
    # Só o que o campo grava muda; o tipo persistido continua o da linha (sem normalização ao ler).
    assert editada['value'] == {**bancada['leitura']['daily_com_horarios']['linha'], 'horarios_especificos': '10:00, 15:30', 'scheduled_time': '10:00:00'}
    assert editada['tipo'] == 'custom'
    row = publicado(editada['value'])
    assert row['schedule_type'] == 'daily'
    assert dag(factory, row)['cron'][:2] == ('0,30 10,15 * * *', ['10:00', '15:30'])


def test_resumo_da_agenda_na_pagina_usa_a_mesma_regra():
    fonte = (ROOT / 'ui-react/src/pages/PipelineWorkspace.tsx').read_text()
    assert re.search(r'const schedule=text\(metadata\.schedule_type\)&&effectiveScheduleType\(metadata\);', fonte)


# ── D1: horários que o motor usa fora de custom passam pela mesma faixa ─────

# Os tipos em que a factory usa horarios_especificos legíveis sem ser custom (None vale diário).
TIPOS_COM_HORARIOS = ('daily', 'weekly', 'monthly', 'biweekly', None)
AGENDA_D1 = {'scheduled_time': '06:00:00', 'schedule_dow': 3, 'schedule_dom': 5}


def publicada(agenda):
    """Linha ativa de etl_pipeline que o rascunho leu."""
    return {'etl_pipeline': [{'pipeline_name': 'PIPE_A', 'project_name': 'BI_CVP', 'domain': 'GERAL', 'active': 1, **agenda}]}


@pytest.mark.parametrize('horarios,fora,cron', [('24:00', '24:00', '0 24 * * *'), ('10:75', '10:75', '75 10 * * *'),
                                                ('9:60', '9:60', '60 9 * * *'), ('09:00,24:00', '24:00', '0 9,24 * * *'),
                                                ('24:00, manha', '24:00', '0 24 * * *')])
@pytest.mark.parametrize('tipo', TIPOS_COM_HORARIOS)
def test_d1_horario_fora_da_faixa_que_o_motor_usaria_nao_publica(tipo, horarios, fora, cron, factory):
    """Campo "Horários específicos" editado numa linha não custom (R2): o tipo gravado continua o da linha."""
    errors, row = projetar({**AGENDA_D1, 'schedule_type': tipo, 'horarios_especificos': horarios})
    assert [(e['field'], e['code']) for e in errors] == [('horarios_especificos', 'schedule')]
    # A mensagem do cadastro legado (_parse_horarios_especificos), com a entrada fora da faixa.
    assert errors[0]['message'] == f"Horário fora do intervalo: '{fora}'"
    # Sem a recusa, a factory geraria este cron fora da faixa.
    assert factory._build_cron(row)[0] == cron


@pytest.mark.parametrize('tipo', TIPOS_COM_HORARIOS)
def test_d1_limites_00_00_e_23_59_publicam_no_cron_do_motor(tipo, factory):
    row = publicado({**AGENDA_D1, 'schedule_type': tipo, 'horarios_especificos': '00:00, 23:59'})
    assert row['horarios_especificos'] == '00:00, 23:59' and row['schedule_type'] == tipo
    assert factory._build_cron(row)[:2] == ('0,59 0,23 * * *', ['00:00', '23:59'])


@pytest.mark.parametrize('tipo', TIPOS_COM_HORARIOS)
def test_d1_entrada_ilegivel_em_pipeline_novo_nao_publica(tipo, factory):
    """M1: a factory usaria só 09:00 e ignoraria o resto em silêncio; o cadastro recusa. Sem linha publicada, tudo é alteração."""
    errors, row = projetar({**AGENDA_D1, 'schedule_type': tipo, 'horarios_especificos': '09:00, manha, 9:'})
    assert [(e['field'], e['message']) for e in errors] == [('horarios_especificos', "Horário inválido: 'manha' (use HH:MM)")]
    assert row['horarios_especificos'] == '09:00, manha, 9:'
    assert factory._build_cron(row)[:2] == ('0 9 * * *', ['09:00'])


def test_d1_linha_antiga_ilegivel_sem_alteracao_continua_publicando(factory):
    linha = {'schedule_type': 'daily', 'scheduled_time': '06:00:00', 'horarios_especificos': 'manha, 9:'}
    errors, row = projetar(linha, publicada(linha))
    assert errors == [] and row['horarios_especificos'] == 'manha, 9:'
    assert factory._build_cron(row)[:2] == ('0 6 * * *', None)


def test_d1_agenda_antiga_fora_da_faixa_sem_alteracao_continua_como_esta():
    """Publicar outra mudança não exige corrigir a agenda que já está ativa (mesmo padrão de criticidade/SLA)."""
    linha = {**AGENDA_D1, 'schedule_type': 'daily', 'horarios_especificos': '24:00'}
    errors, row = projetar(linha, publicada(linha))
    assert errors == [] and row['horarios_especificos'] == '24:00'


@pytest.mark.parametrize('antes,depois', [
    ({'schedule_type': 'daily', 'horarios_especificos': '24:00'}, {'schedule_type': 'daily', 'horarios_especificos': '10:75'}),
    ({'schedule_type': 'daily', 'horarios_especificos': '09:00'}, {'schedule_type': 'daily', 'horarios_especificos': '9:60'}),
    # Sob demanda ignora os horários; passar a diário os torna efetivos.
    ({'schedule_type': 'on_demand', 'horarios_especificos': '24:00'}, {'schedule_type': 'daily', 'horarios_especificos': '24:00'}),
    ({'schedule_type': 'weekly', 'horarios_especificos': '24:00'}, {'schedule_type': None, 'horarios_especificos': '24:00'}),
])
def test_d1_agenda_alterada_em_relacao_a_publicada_confere_a_faixa(antes, depois):
    errors, _ = projetar({**AGENDA_D1, **depois}, publicada({**AGENDA_D1, **antes}))
    assert [(e['field'], e['code']) for e in errors] == [('horarios_especificos', 'schedule')]


@pytest.mark.parametrize('agenda,cron', [
    ({'schedule_type': 'on_demand', 'horarios_especificos': '24:00'}, (None, None, None)),
    ({'schedule_type': 'monthly_days_times', 'horarios_especificos': '24:00', 'dias_horarios_mes': '[{"dia": 5, "horarios": ["09:00"]}]'},
     ('0 9 5 * *', None, {5: ['09:00']})),
])
def test_d1_tipo_que_o_motor_nao_usa_os_horarios_continua_publicando(agenda, cron, factory):
    row = publicado({**AGENDA_D1, **agenda})
    assert row['horarios_especificos'] == '24:00'
    assert factory._build_cron(row) == cron


@pytest.mark.parametrize('horarios', ['24:00', '10:75', '9:60', '00:00, 23:59', '09:00, manha, 9:', ' 7:5 ,, 8 ', '-1:00', '10:30:99', '', None])
def test_d1_leitura_dos_horarios_e_a_mesma_da_factory(horarios, factory):
    """Anti-drift: a publicação lê os horários como _build_cron (mesmo split e int)."""
    from services.workspace_publication import engine_schedule_times
    lidos = sorted(f'{hour:02d}:{minute:02d}' for _, hour, minute in engine_schedule_times(horarios))
    assert (lidos or None) == factory._build_cron({'schedule_type': 'daily', 'horarios_especificos': horarios})[1]


# ── M1: formato dos horários alterados; M2: agenda efetiva depois do UPDATE parcial ──

def pos_sync(row, existing):
    """Linha que a factory lê depois do UPDATE parcial de sync_rows: chave omitida conserva, null explícito limpa."""
    return {**existing['etl_pipeline'][0], **row}


@pytest.mark.parametrize('horarios,entrada,usados', [('09:00,14;00', '14;00', ['09:00']), ('09:00, manha, 9:', 'manha', ['09:00']),
                                                     ('9:', '9:', None), ('14h', '14h', None)])
@pytest.mark.parametrize('tipo', TIPOS_COM_HORARIOS)
def test_m1_alteracao_para_horario_ilegivel_nao_publica(tipo, horarios, entrada, usados, factory):
    """Sem a recusa, a factory descartaria a entrada ilegível sem aviso: 09:00,14;00 perderia as 14h."""
    existing = publicada({**AGENDA_D1, 'schedule_type': tipo, 'horarios_especificos': '09:00,14:00'})
    errors, row = projetar({**AGENDA_D1, 'schedule_type': tipo, 'horarios_especificos': horarios}, existing)
    # A mensagem do cadastro legado (_parse_horarios_especificos), com a entrada ilegível.
    assert [(e['field'], e['code'], e['message']) for e in errors] == [('horarios_especificos', 'schedule', f"Horário inválido: '{entrada}' (use HH:MM)")]
    # Texto sem normalização; é isto que a factory usaria.
    assert row['horarios_especificos'] == horarios
    assert factory._build_cron(row)[1] == usados


@pytest.mark.parametrize('horarios,mensagem', [
    ('-1:00', "Horário fora do intervalo: '-1:00'"), ('23:60', "Horário fora do intervalo: '23:60'"),
    # A primeira entrada recusada, na ordem do texto, como no cadastro.
    ('14;00, 24:00', "Horário inválido: '14;00' (use HH:MM)"), ('24:00, 14;00', "Horário fora do intervalo: '24:00'"),
])
def test_m1_limites_e_ordem_do_diagnostico_sao_os_do_cadastro(horarios, mensagem):
    existing = publicada({**AGENDA_D1, 'schedule_type': 'daily', 'horarios_especificos': '09:00'})
    errors, _ = projetar({**AGENDA_D1, 'schedule_type': 'daily', 'horarios_especificos': horarios}, existing)
    assert [(e['field'], e['message']) for e in errors] == [('horarios_especificos', mensagem)]


@pytest.mark.parametrize('horarios,cron', [('9:0', ('0 9 * * *', ['09:00'])), (' 7:5 ,, 8 ', ('0,5 7,8 * * *', ['07:05', '08:00'])),
                                           ('10:30:99', ('30 10 * * *', ['10:30'])), ('', ('0 6 * * *', None)), (None, ('0 6 * * *', None))])
def test_m1_formatos_que_o_cadastro_aceita_publicam_sem_normalizar(horarios, cron, factory):
    existing = publicada({**AGENDA_D1, 'schedule_type': 'daily', 'horarios_especificos': '09:00,14:00'})
    errors, row = projetar({**AGENDA_D1, 'schedule_type': 'daily', 'horarios_especificos': horarios}, existing)
    assert errors == [] and row['horarios_especificos'] == horarios
    assert factory._build_cron(row)[:2] == cron


@pytest.mark.parametrize('linha', [
    {'schedule_type': 'daily', 'horarios_especificos': '09:00,14;00'},
    {'schedule_type': None, 'horarios_especificos': 'manha, 9:'},
    {'schedule_type': 'weekly', 'horarios_especificos': '24:00'},
    {'schedule_type': 'daily', 'horarios_especificos': '09:00', 'dias_semana': '1,7'},
])
def test_m1_agenda_publicada_invalida_sem_alteracao_continua_como_esta(linha):
    """Publicar outra mudança não exige corrigir a agenda ativa; o texto segue byte a byte."""
    linha = {**AGENDA_D1, **linha}
    errors, row = projetar({**linha, 'criticidade': 'Alta'}, publicada(linha))
    assert errors == []
    assert {campo: row[campo] for campo in linha} == linha


def test_m2_rascunho_sem_as_chaves_da_agenda_nao_altera_e_publica():
    """Chaves omitidas: a agenda efetiva é a publicada (mesmo inválida); a projeção não as restaura."""
    existing = publicada({**AGENDA_D1, 'schedule_type': 'daily', 'horarios_especificos': '24:00, 14;00', 'dias_semana': '1,7'})
    errors, row = projetar({'scheduled_time': '06:00:00'}, existing)
    assert errors == []
    assert not {'schedule_type', 'horarios_especificos', 'dias_semana'} & set(row)


@pytest.mark.parametrize('antes,depois,campo,cron', [
    # Sob demanda com 24:00 passa a diário sem trazer horarios_especificos: o UPDATE parcial mantém 24:00.
    ({'schedule_type': 'on_demand', 'horarios_especificos': '24:00'}, {'schedule_type': 'daily'}, 'horarios_especificos', '0 24 * * *'),
    ({'schedule_type': 'on_demand', 'horarios_especificos': '09:00,14;00'}, {'schedule_type': 'daily'}, 'horarios_especificos', '0 9 * * *'),
    ({'schedule_type': 'monthly_days_times', 'horarios_especificos': '9:60', 'dias_horarios_mes': '[{"dia": 5, "horarios": ["09:00"]}]'},
     {'schedule_type': 'weekly'}, 'horarios_especificos', '60 9 * * *'),
    # Tipo omitido: vale o publicado.
    ({'schedule_type': 'weekly', 'horarios_especificos': '09:00'}, {'horarios_especificos': '24:00'}, 'horarios_especificos', '0 24 * * *'),
    # Herdado custom: o parser inteiro do custom, como antes (diagnóstico geral da agenda); a factory cairia no diário.
    ({'schedule_type': 'custom', 'horarios_especificos': '09:00'}, {'horarios_especificos': '14;00'}, 'schedule', '0 6 * * *'),
    # dias_semana que o sob demanda ignorava passa a entrar no cron do diário.
    ({'schedule_type': 'on_demand', 'dias_semana': '1,7'}, {'schedule_type': 'daily'}, 'dias_semana', '0 6 * * 1,7'),
    # Agenda alterada confere também o dias_semana herdado que o motor usa.
    ({'schedule_type': 'daily', 'dias_semana': '1,7'}, {'schedule_type': 'daily', 'horarios_especificos': '09:00'}, 'dias_semana', '0 9 * * 1,7'),
])
def test_m2_agenda_efetiva_depois_do_update_parcial_e_conferida(antes, depois, campo, cron, factory):
    existing = publicada({**AGENDA_D1, **antes})
    errors, row = projetar({'scheduled_time': '06:00:00', **depois}, existing)
    assert [(e['field'], e['code']) for e in errors] == [(campo, 'schedule')]
    # A projeção não restaura as chaves omitidas; sem a recusa, a linha gravada geraria este cron.
    assert not (set(antes) - set(depois)) & set(row)
    assert factory._build_cron(pos_sync(row, existing))[0] == cron


def test_m2_null_explicito_limpa_e_o_motor_volta_ao_horario_da_agenda(factory):
    existing = publicada({**AGENDA_D1, 'schedule_type': 'on_demand', 'horarios_especificos': '24:00', 'dias_semana': '1,7'})
    errors, row = projetar({**AGENDA_D1, 'schedule_type': 'daily', 'horarios_especificos': None, 'dias_semana': None}, existing)
    assert errors == [] and row['horarios_especificos'] is None and row['dias_semana'] is None
    assert factory._build_cron(pos_sync(row, existing))[:2] == ('0 6 * * *', None)


def test_m2_tipo_omitido_vale_o_sob_demanda_publicado_que_ignora_os_horarios(factory):
    existing = publicada({**AGENDA_D1, 'schedule_type': 'on_demand'})
    errors, row = projetar({**AGENDA_D1, 'horarios_especificos': '24:00'}, existing)
    assert errors == [] and 'schedule_type' not in row
    assert factory._build_cron(pos_sync(row, existing)) == (None, None, None)


@pytest.mark.parametrize('agenda', [
    {'schedule_type': 'daily', 'dias_semana': '1,7'},
    {'schedule_type': None, 'horarios_especificos': '09:00', 'dias_semana': ' 1'},
    {'schedule_type': 'weekly', 'horarios_especificos': '09:00', 'dias_semana': 'seg'},
])
def test_b1_dias_semana_que_o_motor_usaria_fora_de_custom_e_conferido(agenda):
    errors, _ = projetar({**AGENDA_D1, **agenda})
    assert [(e['field'], e['code']) for e in errors] == [('dias_semana', 'schedule')]


@pytest.mark.parametrize('agenda,cron', [
    ({'schedule_type': 'weekly', 'dias_semana': '1,7'}, '0 6 * * 3'),
    ({'schedule_type': 'monthly', 'dias_semana': '9'}, '0 6 5 * *'),
    ({'schedule_type': 'on_demand', 'dias_semana': '9'}, None),
    ({'schedule_type': 'monthly_days_times', 'dias_semana': '9', 'dias_horarios_mes': '[{"dia": 5, "horarios": ["09:00"]}]'}, '0 9 5 * *'),
])
def test_b1_dias_semana_que_o_motor_ignora_continua_publicando(agenda, cron, factory):
    row = publicado({**AGENDA_D1, **agenda})
    assert row['dias_semana'] == agenda['dias_semana'] and factory._build_cron(row)[0] == cron


# ── on_demand: nunca cron ───────────────────────────────────────────────────

@pytest.mark.parametrize('resto', [
    {},
    {'scheduled_time': None},
    {'scheduled_time': '06:00:00', 'horarios_especificos': '09:00,10:00'},
    {'scheduled_time': '06:00:00', 'dias_horarios_mes': '[{"dia": 5, "horarios": ["09:00"]}]'},
    {'scheduled_time': '06:00:00', 'schedule_dow': True, 'schedule_dom': 99},
])
def test_sob_demanda_publica_sem_cron_mesmo_com_resto_de_agenda(resto, bancada, factory, legado):
    gerado = dag(factory, publicado({'schedule_type': 'on_demand', **resto}))
    assert gerado == dag(factory, legado(bancada['cenarios']['on_demand']['legado']))
    assert gerado['cron'] == (None, None, None)
    assert gerado['schedule'] == ['schedule=None,  # sob demanda: só execução manual']
    assert (gerado['HORARIOS_ESPECIFICOS:valor'], gerado['DIAS_HORARIOS_MES:valor']) == (None, None)
