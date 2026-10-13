"""EOC-F3b-L2: projeção positiva dos seis tipos sem caso na F4.

O rascunho tem a forma que o LegacyFlowReader (.NET) entrega: a linha de
etl_pipeline_job em legacyJob, colunas JSON como texto, BIT como bool, GUID
como texto e as tabelas filhas por etapa. A prova é a volta: legado → rascunho
→ projeção devolve as mesmas linhas, e a regra legada de cada tipo continua
recusando a configuração inválida com diagnóstico na etapa.
"""
import copy
import json
import pytest
from services.workspace_publication import validate_projection

NAME = 'PUB_EOC_F3'
CONNECTIONS = {'ssh': 'ssh', 'sql': 'mssql'}
PIPELINE = {'pipeline_name': NAME, 'project_name': 'Projeto', 'domain': 'Dominio', 'schedule_type': 'on_demand', 'active': 1, 'criticidade': 'Media', 'depends_on': None}
PARAMS = [
    {'pipeline_name': NAME, 'param_name': 'DIR_ENTRADA', 'param_type': 'Pathname', 'param_source': 'fixo', 'param_value': '/dados/entrada', 'param_destino': 'orquestra'},
    {'pipeline_name': NAME, 'param_name': 'DIR_SCRIPTS', 'param_type': 'String', 'param_source': 'fixo', 'param_value': '/opt/scripts', 'param_destino': 'orquestra'},
]
# (raízes de anexo, domínios, modelos existentes, exigir modelo) do Admin › E-mail
EMAIL_POLICY = (['/dados/saida'], ['example.test'], [7], False)
ENTRADA_A = '6f1c2a9e-3b4d-4e5f-8a7b-1c2d3e4f5a6b'
ENTRADA_B = '0a9b8c7d-6e5f-4a3b-9c2d-1e0f9a8b7c6d'


def job(name, kind, order, depends=None, **columns):
    return {'pipeline_name': NAME, 'job_name': name, 'job_type': kind, 'execution_order': order, 'depends_on_jobs': depends,
            'job_command': None, 'ssh_conn_id': None, 'layout_x': 100 * order, 'layout_y': 40, 'active': 1, **columns}


def read_legacy(jobs, children=None, params=PARAMS):
    """Mesma forma do LegacyFlowReader; não chama código do adaptador."""
    children = children or {}
    nodes, edges, positions = [], [], {}
    for row in sorted(jobs, key=lambda r: (r['execution_order'], r['job_name'])):
        id = row['job_name']
        config = {'legacyJob': dict(row), 'etl_job_lineage': []}
        for table, key in (('etl_pipeline_job_param', 'job_name'), ('etl_valida_arquivo_no', 'task_id'), ('etl_valida_arquivo_config', 'task_id')):
            config[table] = [dict(child) for child in children.get(table, []) if child[key] == id]
        nodes.append({'id': id, 'type': row['job_type'], 'configuration': config})
        positions[id] = {'x': row['layout_x'], 'y': row['layout_y']}
        edges += [{'source': parent.strip(), 'target': id} for parent in (row['depends_on_jobs'] or '').split(',') if parent.strip()]
    metadata = {'workspaceLineageVersion': 1, 'legacyPipeline': dict(PIPELINE),
                'legacyTables': {'etl_pipeline_param': [dict(p) for p in params], 'etl_pipeline_dependencia': [], 'etl_pipeline_owner': []}}
    return {'schemaVersion': 1, 'identity': {'pipelineName': NAME}, 'metadata': metadata, 'nodes': nodes, 'edges': edges}, {'schemaVersion': 1, 'nodes': positions}


def project(jobs, children=None, existing=None, policy=EMAIL_POLICY, params=PARAMS):
    definition, layout = read_legacy(jobs, children, params)
    existing = existing or {}
    before = copy.deepcopy((definition, layout, existing))
    errors, projection = validate_projection(definition, layout, existing, CONNECTIONS, policy)
    assert (definition, layout, existing) == before, 'a validação não pode alterar o rascunho nem o estado lido'
    return errors, projection


# ── Cenários no contrato legado ─────────────────────────────────────────────
# Cada um devolve (linhas de etl_pipeline_job, tabelas filhas). 'Origem' é a etapa
# de entrada comum; as demais seguem o CSV depends_on_jobs do cadastro legado.

def origem():
    return job('Origem', 'shell', 1, job_command='echo inicio', ssh_conn_id='ssh')


def python_arquivo():
    py = {'modo': 'arquivo', 'interpretador': '/usr/bin/python3.11', 'script_path': '/opt/scripts/carga.py'}
    return [origem(), job('Carga_Py', 'python', 2, 'Origem', ssh_conn_id='ssh', python_json=json.dumps(py), param_vinculos_json=None)], {}


def python_codigo_vinculo():
    # Diretório vazio no nó: o valor vem do vínculo ao parâmetro fixo do pipeline.
    py = {'modo': 'codigo', 'destino_dir': '', 'arquivo': 'gera_saida.py', 'codigo': 'print("ok")\n'}
    return [origem(), job('Gera_Py', 'python', 2, 'Origem', ssh_conn_id='ssh', python_json=json.dumps(py),
                          param_vinculos_json=json.dumps({'destino_dir': 'DIR_SCRIPTS'}))], {}


def python_modulo():
    # python_json NULL é o modo legado 'modulo' (PythonModuleOperator).
    return [origem(), job('Modulo_Py', 'python', 2, 'Origem', job_command='pacote.rotina', ssh_conn_id='ssh', python_json=None)], {}


def decisao_binaria():
    cond = {'tipo': 'contagem', 'tabela': 'Banco.dbo.Movimento', 'database': 'Banco', 'mssql_conn_id': 'sql', 'operador': '>', 'valor': 0,
            'ramo_verdadeiro': ['Processa'], 'ramo_falso': ['Avisa'], 'on_error': 'falhar'}
    return [origem(), job('Decide', 'decisao', 2, 'Origem', condition_json=json.dumps(cond)),
            job('Processa', 'shell', 3, 'Decide', job_command='echo sim', ssh_conn_id='ssh'),
            job('Avisa', 'shell', 4, 'Decide', job_command='echo nao', ssh_conn_id='ssh')], {}


def decisao_switch():
    cond = {'tipo': 'valor_sql', 'source_job': 'Consulta', 'comparacao': 'numero', 'on_error': 'senao',
            'casos': [{'nome': 'alto', 'operador': '>', 'valor': '100', 'ramo': ['Lote_Grande']},
                      {'nome': 'baixo', 'operador': '<=', 'valor': '100', 'ramo': ['Lote_Pequeno']}],
            'ramo_senao': ['Sem_Lote']}
    sql = {'sql': 'SELECT COUNT(*) FROM dbo.Movimento', 'mssql_conn_id': 'sql', 'on_error': 'falhar'}
    return [job('Consulta', 'sql', 1, sql_json=json.dumps(sql)), job('Escolhe', 'decisao', 2, 'Consulta', condition_json=json.dumps(cond)),
            job('Lote_Grande', 'shell', 3, 'Escolhe', job_command='echo g', ssh_conn_id='ssh'),
            job('Lote_Pequeno', 'shell', 4, 'Escolhe', job_command='echo p', ssh_conn_id='ssh'),
            job('Sem_Lote', 'shell', 5, 'Escolhe', job_command='echo s', ssh_conn_id='ssh')], {}


def aguarde(politica='todas_terminarem'):
    config = None if politica is None else json.dumps({'politica': politica})
    return [origem(), job('Perna_A', 'shell', 2, 'Origem', job_command='echo a', ssh_conn_id='ssh'),
            job('Perna_B', 'shell', 3, 'Origem', job_command='echo b', ssh_conn_id='ssh'),
            job('Encontro', 'aguarde', 4, 'Perna_A,Perna_B', aguarde_json=config),
            job('Limpa', 'shell', 5, 'Encontro', job_command='echo limpa', ssh_conn_id='ssh')], {}


def valida_arquivo():
    header = {'pipeline_name': NAME, 'task_id': 'Valida', 'ssh_conn_id': 'ssh', 'timeout_segundos': 120, 'revisao': 3, 'atualizado_em': '2026-10-01T10:00:00'}
    base = {'pipeline_name': NAME, 'task_id': 'Valida', 'se_nao_existe': 'falhar'}
    entries = [
        {**base, 'entrada_id': ENTRADA_A, 'ordem': 0, 'tipo': 'arquivo', 'param_name': None, 'diretorio_literal': '/dados/recebidos',
         'arquivo': 'MOVIMENTO_D.csv', 'alvo': 'Carga', 'se_zero_linhas': 'pular', 'ignorar_cabecalho': True},
        {**base, 'entrada_id': ENTRADA_B, 'ordem': 1, 'tipo': 'dataset', 'param_name': 'DIR_ENTRADA', 'diretorio_literal': None,
         'arquivo': 'clientes.ds', 'alvo': 'Publica', 'se_zero_linhas': 'executar', 'ignorar_cabecalho': False},
    ]
    jobs = [origem(), job('Valida', 'valida_arquivo', 2, 'Origem'),
            job('Carga', 'datastage', 3, 'Valida', job_command='dsjob -run Projeto Carga', ssh_conn_id='ssh'),
            job('Publica', 'shell', 4, 'Carga', job_command='echo publica', ssh_conn_id='ssh')]
    return jobs, {'etl_valida_arquivo_no': [header], 'etl_valida_arquivo_config': entries}


def notificacao():
    cfg = {'grupo_id': 3, 'template_id': None, 'mensagem': 'Carga {pipeline} concluída'}
    return [origem(), job('Avisa_Equipe', 'notificacao', 2, 'Origem', notify_json=json.dumps(cfg))], {}


def email(**changes):
    cfg = {'assunto': 'Carga diária', 'corpo': 'Segue o resumo.\n', 'html': False, 'modelo_id': None, 'destinatarios': ['ops@example.test'],
           'incluir_pipeline': True, 'anexo': {'raiz': '/dados/saida/relatorios', 'nome': 'resumo_{data}.csv'}, **changes}
    return [origem(), job('Envia_Resumo', 'email', 2, 'Origem', notify_json=json.dumps(cfg, ensure_ascii=False))], {}


SCENARIOS = {
    'python_arquivo': python_arquivo, 'python_codigo_vinculo': python_codigo_vinculo, 'python_modulo': python_modulo,
    'decisao_binaria': decisao_binaria, 'decisao_switch': decisao_switch,
    'aguarde': aguarde, 'aguarde_sem_config': lambda: aguarde(None),
    'valida_arquivo': valida_arquivo, 'notificacao': notificacao,
    'email': email, 'email_modelo': lambda: email(modelo_id=7, corpo='', anexo=None, destinatarios=[]),
}
JSON_COLUMN = {'python': 'python_json', 'decisao': 'condition_json', 'aguarde': 'aguarde_json', 'notificacao': 'notify_json', 'email': 'notify_json'}


@pytest.mark.parametrize('scenario', SCENARIOS)
def test_legado_valido_volta_identico_na_projecao(scenario):
    jobs, children = SCENARIOS[scenario]()
    errors, projection = project(jobs, children)
    assert errors == []
    # Identidade, ordem, vínculos (CSV), layout e colunas JSON: mesma linha do cadastro.
    assert projection['etl_pipeline_job'] == jobs
    for table in ('etl_valida_arquivo_no', 'etl_valida_arquivo_config', 'etl_pipeline_job_param'):
        assert projection[table] == children.get(table, [])
    assert projection['etl_pipeline_param'] == PARAMS
    assert projection['etl_pipeline'] == [PIPELINE]


@pytest.mark.parametrize('scenario', [s for s in SCENARIOS if s not in {'valida_arquivo', 'aguarde_sem_config', 'python_modulo'}])
def test_coluna_json_do_tipo_volta_sem_normalizacao(scenario):
    # Campo futuro, acento e espaçamento do texto gravado não podem ser reescritos
    # na publicação: o factory lê a coluna como o cadastro legado a deixou.
    jobs, _ = SCENARIOS[scenario]()
    for row in jobs:
        column = JSON_COLUMN.get(row['job_type'])
        if column and row[column] is not None:
            row[column] = json.dumps({**json.loads(row[column]), 'campo_futuro': {'observação': 'ação'}}, ensure_ascii=False, indent=1)
    errors, projection = project(jobs)
    assert errors == []
    changed = [(o[c], p[c]) for o, p in zip(jobs, projection['etl_pipeline_job']) for c in [JSON_COLUMN.get(o['job_type'])] if c and o[c] is not None]
    assert changed and all(original == projected for original, projected in changed)


def test_valida_arquivo_preserva_tabelas_filhas_por_entrada():
    jobs, children = valida_arquivo()
    _, projection = project(jobs, children)
    by_id = {row['entrada_id']: row for row in projection['etl_valida_arquivo_config']}
    assert set(by_id) == {ENTRADA_A, ENTRADA_B}
    # Diretório literal e referência ao catálogo são caminhos distintos; nenhum vira o outro.
    assert (by_id[ENTRADA_A]['diretorio_literal'], by_id[ENTRADA_A]['param_name']) == ('/dados/recebidos', None)
    assert (by_id[ENTRADA_B]['diretorio_literal'], by_id[ENTRADA_B]['param_name']) == (None, 'DIR_ENTRADA')
    assert [row['ordem'] for row in projection['etl_valida_arquivo_config']] == [0, 1]
    assert by_id[ENTRADA_A]['ignorar_cabecalho'] is True and by_id[ENTRADA_B]['se_zero_linhas'] == 'executar'
    assert projection['etl_valida_arquivo_no'][0]['revisao'] == 3


def _set_json(jobs, name, column, **changes):
    row = next(r for r in jobs if r['job_name'] == name)
    row[column] = json.dumps({**json.loads(row[column]), **changes})


def _python_relativo(jobs, children):_set_json(jobs, 'Carga_Py', 'python_json', script_path='carga.py')
def _python_modo(jobs, children):_set_json(jobs, 'Carga_Py', 'python_json', modo='jar')
def _python_sem_ssh(jobs, children):next(r for r in jobs if r['job_name'] == 'Carga_Py').update(ssh_conn_id=None)
def _decisao_ramo_ausente(jobs, children):_set_json(jobs, 'Decide', 'condition_json', ramo_verdadeiro=['Inexistente'])
def _decisao_sql_conexao(jobs, children):_set_json(jobs, 'Decide', 'condition_json', mssql_conn_id='ssh')
def _switch_ramo_duplo(jobs, children):_set_json(jobs, 'Escolhe', 'condition_json', ramo_senao=['Lote_Grande'])
def _aguarde_politica(jobs, children):_set_json(jobs, 'Encontro', 'aguarde_json', politica='qualquer_uma')
def _valida_alvo_antes(jobs, children):children['etl_valida_arquivo_config'][0]['alvo'] = 'Origem'
def _valida_ssh(jobs, children):children['etl_valida_arquivo_no'][0]['ssh_conn_id'] = 'sql'
def _valida_sem_entradas(jobs, children):children['etl_valida_arquivo_config'].clear()
def _notificacao_grupo(jobs, children):_set_json(jobs, 'Avisa_Equipe', 'notify_json', grupo_id='equipe')
def _email_dominio(jobs, children):_set_json(jobs, 'Envia_Resumo', 'notify_json', destinatarios=['ops@outro.test'])
def _email_anexo_fora(jobs, children):_set_json(jobs, 'Envia_Resumo', 'notify_json', anexo={'raiz': '/etc', 'nome': 'passwd'})
def _email_modelo_ausente(jobs, children):_set_json(jobs, 'Envia_Resumo', 'notify_json', modelo_id=99)


@pytest.mark.parametrize('scenario,break_it,node,fragment', [
    ('python_arquivo', _python_relativo, 'Carga_Py', 'caminho do script inválido'),
    ('python_arquivo', _python_modo, 'Carga_Py', 'modo do nó Python inválido'),
    ('python_arquivo', _python_sem_ssh, 'Carga_Py', 'Servidor SSH é obrigatório'),
    ('decisao_binaria', _decisao_ramo_ausente, 'Decide', "job 'Inexistente' não existe"),
    ('decisao_binaria', _decisao_sql_conexao, 'Decide', "conexão MSSQL 'ssh'"),
    ('decisao_switch', _switch_ramo_duplo, 'Escolhe', 'em mais de um ramo'),
    ('aguarde', _aguarde_politica, 'Encontro', 'política do nó Aguarde inválida'),
    ('valida_arquivo', _valida_alvo_antes, 'Valida', 'destinos do Valida Arquivo inválidos'),
    ('valida_arquivo', _valida_ssh, 'Valida', 'Conexão SSH do Valida Arquivo não encontrada'),
    ('valida_arquivo', _valida_sem_entradas, 'Valida', 'Configure as entradas'),
    ('notificacao', _notificacao_grupo, 'Avisa_Equipe', 'grupo_id da notificação deve ser inteiro'),
    ('email', _email_dominio, 'Envia_Resumo', 'domínio não permitido'),
    ('email', _email_anexo_fora, 'Envia_Resumo', 'não está entre as permitidas'),
    ('email', _email_modelo_ausente, 'Envia_Resumo', 'não existe mais no catálogo'),
])
def test_configuracao_invalida_do_tipo_tem_diagnostico_na_etapa(scenario, break_it, node, fragment):
    jobs, children = SCENARIOS[scenario]()
    break_it(jobs, children)
    errors, _ = project(jobs, children)
    assert errors, 'configuração inválida não pode publicar'
    assert {(e['nodeId'], e['field'], e['code']) for e in errors} == {(node, 'configuration', 'node_configuration')}
    assert any(fragment in e['message'] for e in errors), errors


def test_email_exigir_modelo_recusa_no_novo_e_preserva_no_existente():
    # Ligar a padronização no Admin não pode quebrar o nó de corpo livre que já roda.
    policy = EMAIL_POLICY[:3] + (True,)
    jobs, _ = email()
    errors, _ = project(jobs, policy=policy)
    assert [e['nodeId'] for e in errors] == ['Envia_Resumo'] and 'exige modelo' in errors[0]['message']
    existing = {'etl_pipeline_job': [dict(row) for row in jobs]}
    errors, projection = project(jobs, existing=existing, policy=policy)
    assert errors == [] and projection['etl_pipeline_job'] == jobs


def test_decisao_valida_ramos_contra_etapas_do_proprio_rascunho():
    # Membro de ramo removido do fluxo deixa de existir para a decisão, mesmo que o JSON siga citando.
    jobs, _ = decisao_binaria()
    jobs = [row for row in jobs if row['job_name'] != 'Avisa']
    errors, _ = project(jobs)
    assert any(e['nodeId'] == 'Decide' and "job 'Avisa' não existe" in e['message'] for e in errors)


# ── EOC-F3b: divergências A1–A3 corrigidas (2.22.1) ─────────────────────────
# Cada caso era aceito (A1, A3) ou recusado (A2) só pelo workspace; a regra é a
# do save legado, aplicada sobre o catálogo e o grafo projetados.

def _param(name, **changes):
    return [dict(p, **changes) if p['param_name'] == name else dict(p) for p in PARAMS]


@pytest.mark.parametrize('refs,params,fragment', [
    ({'destino_dir': 'NAO_EXISTE'}, PARAMS, "Parâmetro de pipeline 'NAO_EXISTE' não encontrado"),
    ({'destino_dir': 'dir_scripts'}, PARAMS, "Parâmetro de pipeline 'dir_scripts' não encontrado"),
    # Linhas válidas no catálogo, mas que não servem de caminho Python.
    ({'destino_dir': 'DIR_SCRIPTS'}, _param('DIR_SCRIPTS', param_type='Integer', param_value='10'), 'exige parâmetro String/Pathname fixo'),
    ({'destino_dir': 'DIR_SCRIPTS'}, _param('DIR_SCRIPTS', param_source='run_id', param_value=None), 'exige parâmetro String/Pathname fixo'),
    ({'script_path': 'DIR_SCRIPTS'}, PARAMS, 'apenas no caminho do script ou diretório de publicação do modo ativo'),
    (['DIR_SCRIPTS'], PARAMS, 'Vínculos devem ser um objeto'),
], ids=['inexistente', 'case', 'tipo', 'source', 'destino', 'nao_objeto'])
def test_a1_vinculo_python_invalido_e_recusado_como_no_save_legado(refs, params, fragment):
    from services import param_vinculos
    jobs, _ = python_codigo_vinculo()
    row = next(r for r in jobs if r['job_name'] == 'Gera_Py')
    row['param_vinculos_json'] = json.dumps(refs)
    with pytest.raises(ValueError) as legacy:
        param_vinculos.normalizar(refs, 'python', params, json.loads(row['python_json']))
    errors, _ = project(jobs, params=params)
    assert {(e['nodeId'], e['field'], e['code']) for e in errors} == {('Gera_Py', 'configuration', 'node_configuration')}
    # Mesma mensagem do contrato legado, sem reescrever.
    assert str(legacy.value) in [e['message'] for e in errors] and fragment in str(legacy.value)


@pytest.mark.parametrize('text', ['', '{}', 'null', '{"script_path": "DIR_SCRIPTS"}'])
def test_a1_vinculo_python_vazio_ou_valido_com_catalogo_sem_nome(text):
    # preparar() do legado ignora vínculo vazio; o texto gravado volta como está.
    jobs, _ = python_arquivo()
    next(r for r in jobs if r['job_name'] == 'Carga_Py')['param_vinculos_json'] = text
    params = PARAMS + [{'pipeline_name': NAME, 'param_type': 'String', 'param_source': 'fixo', 'param_value': 'x'}]
    errors, projection = project(jobs, params=params)
    # Só a linha sem nome do catálogo é apontada; a etapa não quebra a validação.
    assert {(e['nodeId'], e['code']) for e in errors} == {(None, 'parameter_configuration')}
    assert projection['etl_pipeline_job'] == jobs


def test_a1_vinculo_python_valido_volta_byte_a_byte():
    jobs, _ = python_codigo_vinculo()
    row = next(r for r in jobs if r['job_name'] == 'Gera_Py')
    row['param_vinculos_json'] = '{ "destino_dir" :  "DIR_SCRIPTS" }'
    errors, projection = project(jobs)
    assert errors == [] and projection['etl_pipeline_job'] == jobs


def test_a2_python_modulo_sem_ssh_publica_como_no_legado():
    # python_json NULL roda no worker (PythonModuleOperator): SSH não é exigido.
    jobs, _ = python_modulo()
    next(r for r in jobs if r['job_name'] == 'Modulo_Py')['ssh_conn_id'] = None
    errors, projection = project(jobs)
    assert errors == [] and projection['etl_pipeline_job'] == jobs


@pytest.mark.parametrize('ssh', ['sql', 'nao_existe'])
def test_a2_python_modulo_com_ssh_informada_invalida_continua_recusado(ssh):
    jobs, _ = python_modulo()
    next(r for r in jobs if r['job_name'] == 'Modulo_Py')['ssh_conn_id'] = ssh
    errors, _ = project(jobs)
    assert [(e['nodeId'], e['message']) for e in errors] == [('Modulo_Py', 'Identificador SSH não encontrado')]


@pytest.mark.parametrize('scenario,node', [('python_arquivo', 'Carga_Py'), ('python_codigo_vinculo', 'Gera_Py')])
def test_a2_python_arquivo_e_codigo_sem_ssh_continuam_recusados(scenario, node):
    jobs, _ = SCENARIOS[scenario]()
    next(r for r in jobs if r['job_name'] == node).update(ssh_conn_id=None)
    errors, _ = project(jobs)
    messages = [e['message'] for e in errors]
    # Diagnósticos de antes preservados: a regra legada do modo e a do adaptador.
    assert {e['nodeId'] for e in errors} == {node} and messages[-1] == 'Conexão SSH é obrigatória para Python'
    assert any(m.startswith('Servidor SSH é obrigatório para o nó Python') for m in messages)


@pytest.mark.parametrize('depends', [None, '', 'Fantasma'], ids=['sem_entrada', 'csv_vazio', 'so_etapa_ausente'])
def test_a3_aguarde_sem_predecessor_no_grafo_projetado_e_recusado(depends):
    jobs, _ = aguarde()
    next(r for r in jobs if r['job_name'] == 'Encontro')['depends_on_jobs'] = depends
    errors, _ = project(jobs)
    assert [e['message'] for e in errors if e['nodeId'] == 'Encontro'] == [
        'o Aguarde precisa de ao menos uma etapa ligada a ele (sem entrada, ele não tem o que esperar)']
    assert {e['nodeId'] for e in errors} <= {'Encontro', None}


def test_a3_aguarde_com_uma_entrada_publica():
    jobs, _ = aguarde()
    next(r for r in jobs if r['job_name'] == 'Encontro')['depends_on_jobs'] = 'Perna_A'
    errors, projection = project(jobs)
    assert errors == [] and projection['etl_pipeline_job'] == jobs


# ── EOC-F3b: vínculo DataStage (2.22.1) ─────────────────────────────────────
# Mesmo contrato do save legado (param_vinculos.preparar → normalizar 'datastage')
# sobre o catálogo projetado. O valor direto da etapa tem prioridade na corrida
# (param_snapshot), então o vínculo de mesmo nome não é conflito.
DT_REF = {'pipeline_name': NAME, 'param_name': 'DT_REF', 'param_type': 'String', 'param_source': 'fixo', 'param_value': '2026-10-01', 'param_destino': 'datastage'}
PARAMS_DS = PARAMS + [DT_REF]


def datastage_vinculo(refs='{"pData": "DT_REF"}'):
    return [origem(), job('Carga_DS', 'datastage', 2, 'Origem', job_command='dsjob -run Projeto Carga', ssh_conn_id='ssh', param_vinculos_json=refs)], {}


@pytest.mark.parametrize('refs', [
    {'pData': 'NAO_EXISTE'}, {'pData': 'dt_ref'}, {'pData': 'DIR_ENTRADA'}, {'p Data': 'DT_REF'}, ['DT_REF'],
], ids=['inexistente', 'case', 'exclusivo_orquestra', 'alvo_invalido', 'nao_objeto'])
def test_vinculo_datastage_invalido_e_recusado_como_no_save_legado(refs):
    from services import param_vinculos
    with pytest.raises(ValueError) as legacy:
        param_vinculos.normalizar(refs, 'datastage', PARAMS_DS)
    jobs, _ = datastage_vinculo(json.dumps(refs))
    errors, projection = project(jobs, params=PARAMS_DS)
    assert [(e['nodeId'], e['field'], e['code'], e['message']) for e in errors] == [('Carga_DS', 'configuration', 'node_configuration', str(legacy.value))]
    assert projection['etl_pipeline_job'] == jobs


@pytest.mark.parametrize('text', ['', '{}', 'null', None, '{ "pData" :  "DT_REF" }'], ids=['texto_vazio', 'objeto_vazio', 'null', 'sem_coluna', 'valido'])
def test_vinculo_datastage_vazio_ou_valido_publica_byte_a_byte(text):
    jobs, _ = datastage_vinculo(text)
    errors, projection = project(jobs, params=PARAMS_DS)
    assert errors == [] and projection['etl_pipeline_job'] == jobs


def test_vinculo_datastage_destino_omitido_no_catalogo_vale_o_default_datastage():
    # A coluna param_destino tem DEFAULT 'datastage' (migration 129): linha projetada sem ela é DataStage.
    params = PARAMS + [{k: v for k, v in DT_REF.items() if k != 'param_destino'}]
    errors, _ = project(datastage_vinculo()[0], params=params)
    assert errors == []


def test_vinculo_datastage_com_valor_direto_de_mesmo_nome_publica():
    jobs, _ = datastage_vinculo()
    direct = {'pipeline_name': NAME, 'job_name': 'Carga_DS', 'param_name': 'pData', 'param_type': 'String', 'param_source': 'fixo', 'param_value': '2026-09-30'}
    children = {'etl_pipeline_job_param': [direct]}
    errors, projection = project(jobs, children, params=PARAMS_DS)
    assert errors == [] and projection['etl_pipeline_job'] == jobs and projection['etl_pipeline_job_param'] == [direct]


# ── EOC-F3b A5: vínculo nos demais tipos (2.22.1) ───────────────────────────
# O save legado roda preparar → normalizar para toda etapa, com o tipo atual:
# fora de DataStage e Python, vínculo não vazio é recusado. O caso de risco é o
# vínculo que sobrou de uma troca de tipo (ex.: DataStage → Shell).
def outros_tipos():
    jobs, children = valida_arquivo()
    jobs[2:] = [job('Carga', 'shell', 3, 'Valida', job_command='echo carga', ssh_conn_id='ssh'), jobs[3]]
    for extra, _ in (decisao_switch(), aguarde(), notificacao(), email()):
        jobs += [row for row in extra if row['job_name'] not in {r['job_name'] for r in jobs}]
    jobs += [job('Proc', 'storedproc', 20, 'Origem', job_command='dbo.usp_carga', mssql_conn_id='sql'),
             job('Chama', 'http', 21, 'Origem', job_command='https://api.example.test/carga')]
    return jobs, children


def by_name(rows):
    return sorted(rows, key=lambda r: r['job_name'])


OUTROS = {'shell': 'Carga', 'sql': 'Consulta', 'storedproc': 'Proc', 'http': 'Chama', 'decisao': 'Escolhe',
          'aguarde': 'Encontro', 'notificacao': 'Avisa_Equipe', 'email': 'Envia_Resumo', 'valida_arquivo': 'Valida'}


def test_outros_tipos_cobre_todo_tipo_do_cadastro_fora_de_datastage_e_python():
    from routers.jobs import VALID_JOB_TYPES
    jobs, children = outros_tipos()
    assert set(OUTROS) == VALID_JOB_TYPES - {'datastage', 'python'}
    assert {(r['job_type'], r['job_name']) for r in jobs} >= set(OUTROS.items())
    assert project(jobs, children)[0] == []


@pytest.mark.parametrize('refs', [{'pData': 'DT_REF'}, ['DT_REF']], ids=['valido_no_datastage', 'nao_objeto'])
@pytest.mark.parametrize('kind', OUTROS)
def test_a5_vinculo_em_outro_tipo_e_recusado_como_no_save_legado(kind, refs):
    from services import param_vinculos
    with pytest.raises(ValueError) as legacy:
        param_vinculos.normalizar(refs, kind, PARAMS_DS)
    jobs, children = outros_tipos()
    next(r for r in jobs if r['job_name'] == OUTROS[kind])['param_vinculos_json'] = json.dumps(refs)
    errors, projection = project(jobs, children, params=PARAMS_DS)
    assert [(e['nodeId'], e['field'], e['code'], e['message']) for e in errors] == [(OUTROS[kind], 'configuration', 'node_configuration', str(legacy.value))]
    assert by_name(projection['etl_pipeline_job']) == by_name(jobs)


@pytest.mark.parametrize('text', ['', '{}', 'null', '[]', None], ids=['texto_vazio', 'objeto_vazio', 'null', 'lista_vazia', 'sem_coluna'])
def test_a5_vinculo_vazio_em_todos_os_outros_tipos_publica_byte_a_byte(text):
    jobs, children = outros_tipos()
    for row in jobs:
        row['param_vinculos_json'] = text
    errors, projection = project(jobs, children, params=PARAMS_DS)
    assert errors == [] and by_name(projection['etl_pipeline_job']) == by_name(jobs)


def _trocar_tipo(definition, node, kind):
    # O rascunho troca o tipo da etapa; a linha legada guardada ainda tem o tipo antigo.
    target = next(n for n in definition['nodes'] if n['id'] == node)
    target['type'] = kind


def test_a5_troca_de_tipo_vale_o_tipo_atual_da_etapa_e_nao_o_da_linha_antiga():
    jobs, _ = datastage_vinculo()
    definition, layout = read_legacy(jobs, params=PARAMS_DS)
    _trocar_tipo(definition, 'Carga_DS', 'shell')
    errors, projection = validate_projection(copy.deepcopy(definition), layout, {}, CONNECTIONS, EMAIL_POLICY)
    assert [(e['nodeId'], e['message']) for e in errors] == [('Carga_DS', 'Vínculos disponíveis somente em DataStage e Python.')]
    assert projection['etl_pipeline_job'][1]['job_type'] == 'shell'
    assert projection['etl_pipeline_job'][1]['param_vinculos_json'] == jobs[1]['param_vinculos_json']
    # Volta: Shell guardado com vínculo, etapa agora DataStage com o mesmo vínculo válido, publica.
    jobs[1]['job_type'] = 'shell'
    definition, layout = read_legacy(jobs, params=PARAMS_DS)
    _trocar_tipo(definition, 'Carga_DS', 'datastage')
    errors, projection = validate_projection(definition, layout, {}, CONNECTIONS, EMAIL_POLICY)
    assert errors == [] and projection['etl_pipeline_job'][1]['job_type'] == 'datastage'


def test_a5_python_e_datastage_dao_um_unico_diagnostico_de_vinculo():
    # O vínculo DataStage que sobrou numa etapa que virou Python cai na regra Python, uma vez só.
    jobs, _ = python_codigo_vinculo()
    next(r for r in jobs if r['job_name'] == 'Gera_Py')['param_vinculos_json'] = json.dumps({'pData': 'DT_REF'})
    jobs += datastage_vinculo(json.dumps({'pData': 'NAO_EXISTE'}))[0][1:]
    errors, _ = project(jobs, params=PARAMS_DS)
    messages = [(e['nodeId'], e['message']) for e in errors]
    assert messages.count(('Carga_DS', "Parâmetro de pipeline 'NAO_EXISTE' não encontrado.")) == 1
    python = [m for n, m in messages if n == 'Gera_Py']
    assert python.count('Python permite referência apenas no caminho do script ou diretório de publicação do modo ativo.') == 1
    assert 'Vínculos disponíveis somente em DataStage e Python.' not in [m for _, m in messages]


def test_migration_171_e_a_proxima_e_so_incrementa_o_patch():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    numbers = sorted(int(p.name[:3]) for p in (root / 'sql/migrations').glob('[0-9][0-9][0-9]_*.sql'))
    assert numbers[-2:] == [170, 171]
    [migration] = (root / 'sql/migrations').glob('171_*.sql')
    sql = migration.read_text(encoding='utf-8')
    assert sql.count("N'Publicação de Python, DataStage e Aguarde com as regras do cadastro'") == 1
    assert 'ELSE IF EXISTS (SELECT 1 FROM dbo.etl_versao_ferramenta WHERE titulo = @titulo)' in sql
    assert "SET @nova = CONCAT(@maior, '.', @menor, '.', @patch + 1);" in sql
    assert "config_key = 'app_version'" in sql and "config_key = 'app_release_name'" in sql
    assert sql.rstrip().endswith('GO')
