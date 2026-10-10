"""Projeção executável F4: referências binárias, tipos reais e gate do worker."""
import copy
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from services.workspace_publication import materialize, validate_projection, PublicationBlocked, renew_claim, ClaimLost


def flow(kind='shell', job=None, config=None):
    return {'schemaVersion':1,'identity':{'pipelineName':'PUB'},'metadata':{'legacyPipeline':{'project_name':'Projeto','domain':'Dominio','schedule_type':'on_demand','active':1}},'nodes':[{'id':'Etapa','type':kind,'configuration':{'legacyJob':job or {'job_command':'true','ssh_conn_id':'ssh'},**(config or {})}}],'edges':[]}
LAYOUT={'schemaVersion':1,'nodes':{'Etapa':{'x':17,'y':23}}}
CONNECTIONS={'ssh':'ssh','sql':'mssql'}


def test_projection_preserves_custom_columns_nulls_and_layout():
    definition=flow(job={'job_command':'literal','ssh_conn_id':'ssh','future':None})
    errors, projected=validate_projection(definition,LAYOUT,{},CONNECTIONS)
    assert not errors
    assert projected['etl_pipeline_job'][0]['future'] is None
    assert projected['etl_pipeline_job'][0]['layout_x']==17
    assert projected['etl_pipeline_job'][0]['job_command']=='literal'
    assert 'future' not in definition['nodes'][0]


def test_secret_binary_parameter_names_are_distinct_and_location_bound():
    definition=flow(config={'etl_pipeline_job_param':[{'param_name':'SEGREDO','param_type':'encrypted','param_value':'***','secretReference':{'pipelineName':'pub ','jobName':'etapa ','parameterName':'SEGREDO'}}]})
    existing={'etl_pipeline_job_param':[{'pipeline_name':'PUB','job_name':'Etapa','param_name':'segredo','param_type':'encrypted','param_value':'wrong'},{'pipeline_name':'PUB','job_name':'Etapa','param_name':'SEGREDO','param_type':'encrypted','param_value':'correct'}]}
    assert materialize(definition,LAYOUT,existing)['etl_pipeline_job_param'][0]['param_value']=='correct'
    definition['nodes'][0]['configuration']['etl_pipeline_job_param'][0]['secretReference']['jobName']='Other'
    with pytest.raises(PublicationBlocked,match='localização'):materialize(definition,LAYOUT,existing)


@pytest.mark.parametrize('kind,job',[
 ('shell',{'job_command':'true','ssh_conn_id':'ssh'}),
 ('datastage',{'job_command':'dsjob -run Projeto Job','ssh_conn_id':'ssh'}),
 ('sql',{'sql_json':{'sql':'SELECT 1','mssql_conn_id':'sql'}}),
 ('storedproc',{'job_command':'dbo.proc','mssql_conn_id':'sql'}),
 ('http',{'job_command':'https://example.com'}),
])
def test_runtime_types_accept_existing_contract(kind,job):
    assert validate_projection(flow(kind,job),LAYOUT,{},CONNECTIONS)[0]==[]


@pytest.mark.parametrize('change', ['schedule','parameters','unknown_config','unknown_table','missing_secret'])
def test_no_silent_loss_or_unresolvable_secret(change):
    definition=flow()
    if change in {'schedule','parameters'}:definition[change]={}
    elif change=='unknown_config':definition['nodes'][0]['configuration']['future']={}
    elif change=='unknown_table':definition['metadata']['legacyTables']={'future':[]}
    else:definition['metadata']['legacyTables']={'etl_pipeline_param':[{'param_name':'P','param_type':'Encrypted','secretReference':{'pipelineName':'PUB','jobName':None,'parameterName':'P'}}]}
    errors,_=validate_projection(definition,LAYOUT,{},CONNECTIONS)
    assert errors


@pytest.mark.parametrize('folder',['../out','a/b','a\\b','..','Projeto.','Projeto '])
def test_generated_artifact_cannot_escape_root(folder):
    definition=flow();definition['metadata']['legacyPipeline']['project_name']=folder
    assert any(e['code']=='invalid_folder' for e in validate_projection(definition,LAYOUT,{},CONNECTIONS)[0])


def test_wrong_connection_cycle_and_bad_sql_have_node_diagnostics():
    definition=flow('sql',{'sql_json':{'sql':'DELETE FROM dbo.T','mssql_conn_id':'absent'}})
    errors,_=validate_projection(definition,LAYOUT,{},CONNECTIONS)
    assert len(errors)>=2 and all(e['nodeId']=='Etapa' for e in errors)
    definition=flow();definition['edges']=[{'source':'Etapa','target':'Etapa'}]
    assert any(e['code']=='cycle' for e in validate_projection(definition,LAYOUT,{},CONNECTIONS)[0])


def test_claim_lost_stops_every_durable_transition():
    cursor=MagicMock();cursor.rowcount=0
    with pytest.raises(ClaimLost):renew_claim(cursor,'op','old-token')
    sql,args=cursor.execute.call_args.args
    assert 'processing_token=?' in sql and 'processing_until>SYSUTCDATETIME()' in sql and args==('op','old-token')


def test_engine_gate_uses_dag_markers_and_propagates_refusal(monkeypatch):
    path=Path(__file__).parents[1]/'config/airflow_local_settings.py'
    spec=importlib.util.spec_from_file_location('workspace_policy_fixture',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    cursor=MagicMock();connection=MagicMock();connection.cursor.return_value=cursor
    hook=MagicMock();hook.return_value.get_conn.return_value=connection
    monkeypatch.setitem(sys.modules,'airflow.providers.microsoft.mssql.hooks.mssql',SimpleNamespace(MsSqlHook=hook))
    monkeypatch.setenv('WORKSPACE_PUBLICATIONS_ENABLED','true')
    original=MagicMock();task=SimpleNamespace(pre_execute=original,dag_id='PUB',dag=SimpleNamespace(params={'workspace_version_id':'trusted-version','workspace_content_hash':'trusted-hash'}))
    module.task_instance_mutation_hook(SimpleNamespace(task=task))
    context={'dag_run':SimpleNamespace(run_id='same-run',conf={'workspace_version_id':'forged'}),'params':{'workspace_content_hash':'forged'}}
    task.pre_execute(context)
    assert cursor.execute.call_args.args[1]==('PUB','same-run','trusted-version','trusted-hash',None)
    assert original.call_count==1
    cursor.execute.side_effect=RuntimeError('blocked')
    with pytest.raises(RuntimeError,match='blocked'):task.pre_execute(context)
    assert original.call_count==1
    assert connection.close.call_count==2


def test_case_only_change_preserves_lineage_identity():
    from services.workspace_publication import removed_job_names
    assert removed_job_names([{'job_name':'Etapa_A '},{'job_name':'Removida'}],[{'job_name':'etapa_a'}])==['Removida']


def test_existing_unicode_project_preserved_without_path_escape():
    definition=flow();definition['metadata']['legacyPipeline']['project_name']='Atuária'
    errors,projected=validate_projection(definition,LAYOUT,{},CONNECTIONS)
    assert not errors and projected['etl_pipeline'][0]['project_name']=='Atuária'


@pytest.mark.parametrize('as_uuid',[False,True])
def test_sql_driver_guid_representation_matches_engine_artifact(as_uuid):
    import uuid
    from services.workspace_publication import load_operation
    version=uuid.UUID('4c1fcc8f-814a-42fc-ba64-a93b86a71e6c')
    cursor=MagicMock();cursor.fetchone.return_value=('operation','draft',version if as_uuid else str(version).upper(),'PUB',1,'ALICE',None,'a'*64,'gerando','workspace_run','{}','{}','b'*64)
    assert load_operation(cursor,'operation')['version']==str(version)


@pytest.mark.parametrize('serialized',[False,True])
def test_airflow_rest_params_match_dag_marker_values(serialized):
    from services.workspace_publication import dag_marker_values
    markers={'workspace_version_id':'4c1fcc8f-814a-42fc-ba64-a93b86a71e6c','workspace_content_hash':'a'*64,'workspace_projection_hash':'b'*64}
    payload={k:{'__class':'airflow.models.param.Param','description':None,'schema':{},'value':v} for k,v in markers.items()} if serialized else markers
    assert dag_marker_values(payload)==markers


@pytest.mark.parametrize('invalid',[None,{}, {'__class':'Other','value':'trusted'}, {'__class':'airflow.models.param.Param'}, {'value':'trusted'}])
def test_airflow_unrecognized_or_missing_markers_do_not_confirm(invalid):
    from services.workspace_publication import dag_marker_values
    assert dag_marker_values({'workspace_content_hash':invalid})['workspace_content_hash']!='trusted'

@pytest.mark.parametrize('schedule',[
 {'schedule_type':'daily','scheduled_time':'06:00:00'},
 {'schedule_type':'weekly','scheduled_time':'06:00:00','schedule_dow':None},
 {'schedule_type':'monthly','scheduled_time':'06:00:00','schedule_dom':None},
 {'schedule_type':'biweekly','scheduled_time':'06:00:00'},
 {'schedule_type':'weekly','scheduled_time':'06:00:00','schedule_dow':0},
 {'schedule_type':'monthly','scheduled_time':'06:00:00','schedule_dom':28},
 {'schedule_type':'biweekly','scheduled_time':'06:00:00','schedule_dom':13},
 {'schedule_type':'custom','scheduled_time':'08:00:00','horarios_especificos':'08:00,10:00,12:00','dias_semana':'1,5'},
 {'schedule_type':'monthly_days_times','scheduled_time':'06:00:00','dias_horarios_mes':'[{"dia":1,"horarios":["09:00","10:30"]}]'},
])
def test_workspace_agendas_preservam_contrato_legado(schedule):
    definition=flow();definition['metadata']['legacyPipeline'].update(schedule)
    before=copy.deepcopy(definition)
    errors,projection=validate_projection(definition,LAYOUT,{},CONNECTIONS)
    assert not errors
    assert all(projection['etl_pipeline'][0][k]==v for k,v in schedule.items())
    assert definition==before

@pytest.mark.parametrize('schedule',[
 {'schedule_type':'biweekly','schedule_dom':14},
 {'schedule_type':'weekly','schedule_dow':True},
 {'schedule_type':'monthly','schedule_dom':0},
 {'schedule_type':'custom','horarios_especificos':'09:00,99:00'},
 {'schedule_type':'custom','horarios_especificos':''},
 {'schedule_type':'monthly_days_times','dias_horarios_mes':'[{"dia":29,"horarios":["09:00"]}]'},
 {'schedule_type':'monthly_days_times','dias_horarios_mes':'[]'},
 {'schedule_type':'monthly_days_times','dias_horarios_mes':{}},
])
def test_workspace_agendas_invalidas_nao_publicam(schedule):
    definition=flow();definition['metadata']['legacyPipeline'].update(scheduled_time='06:00:00',**schedule)
    errors,_=validate_projection(definition,LAYOUT,{},CONNECTIONS)
    assert any(e['code']=='schedule' for e in errors)
