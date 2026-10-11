import json
from uuid import UUID
import pytest
from fastapi import HTTPException
from services import workspace_advisory as s
from tests.test_workspace_secrets import Connection,ACTOR,ID

BODY={'expectedRevision':1,'fence':2}


@pytest.mark.parametrize('settings,status',[({'session':False},401),({'revision':2},409),({'holder':'OTHER'},409),({'fence':3},409),({'live':0},409),({'pending':True},409),({'readonly':True},409)])
def test_advisory_denies_stale_state_without_mutation(monkeypatch,settings,status):
 connection=Connection(**settings);monkeypatch.setattr(s,'get_db_conn',lambda:connection)
 with pytest.raises(HTTPException) as error:s.guarded_draft(UUID(ID),BODY,ACTOR,'Bearer unit-token')
 assert error.value.status_code==status
 assert connection.rolled and connection.closed and not connection.committed
 assert all(not sql.startswith(('INSERT','UPDATE','DELETE')) for sql,args in connection.queries)


def test_advisory_uses_saved_identity_and_never_writes(monkeypatch):
 connection=Connection();monkeypatch.setattr(s,'get_db_conn',lambda:connection)
 assert s.guarded_draft(UUID(ID),BODY,ACTOR,'Bearer unit-token')['schemaVersion']==1
 assert connection.rolled and connection.closed and not connection.committed
 assert all(not sql.startswith(('INSERT','UPDATE','DELETE')) for sql,args in connection.queries)


@pytest.mark.parametrize('patch',[{'fence':True},{'expectedRevision':0},{'fence':'2'}])
def test_invalid_guard_command_before_db(monkeypatch,patch):
 monkeypatch.setattr(s,'get_db_conn',lambda:pytest.fail('Invalid command opened DB'))
 with pytest.raises(HTTPException) as error:s.guarded_draft(ID,{**BODY,**patch},ACTOR,'Bearer unit-token')
 assert error.value.status_code==422


def test_safe_editor_excludes_refs_and_encrypted_regardless_of_case():
 sent=s.safe_editor([{'param_name':'SECRET','param_type':'encrypted','param_value':'sentinel-secret'},{'param_name':'OTHER','secretReference':{'secretId':ID},'param_value':'sentinel-reference'},{'param_name':'DATE','param_type':'String','param_source':'data_anterior','extra':'sentinel-extra'}])
 assert sent==[{'param_name':'DATE','param_type':'String','param_source':'data_anterior'}]
 assert 'sentinel' not in json.dumps(sent) and ID not in json.dumps(sent)


@pytest.mark.parametrize('rows',[{},[None],[{'param_name':'PARAM','param_value':{'nested':'x'}}],[{'param_name':'PARAM','param_value':'password=credential'}]])
def test_editor_invalid_or_credential_value_is_rejected(rows):
 with pytest.raises(HTTPException) as error:s.safe_editor(rows)
 assert error.value.status_code==422 and 'credential' not in error.value.detail


def test_context_has_draft_defaults_and_does_not_infer_isx_declarations():
 definition={'identity':{'pipelineName':'DRAFT'},'nodes':[{'id':'DS','type':'datastage'}],'metadata':{'legacyTables':{'etl_pipeline_param':[{'param_name':'DATE','param_type':'String','param_value':'draft-default'}]}}}
 result=s.draft_maestro_context(definition,{'nivel':'etapa','job_name':'DS'})
 assert result['pipeline']=='DRAFT' and result['defaults'][0]['param_value']=='draft-default'
 assert result['declarados']['disponivel'] is False
 with pytest.raises(HTTPException):s.draft_maestro_context(definition,{'nivel':'etapa','job_name':'unsaved'})


def test_source_rows_keep_full_metadata_without_truncation_or_default_secrets():
 row={'direction':'destino','object_name':'A'*700,'stage_name':'stage','output_columns':[{'name':'OUT'}],'input_columns':[{'name':'IN'}],'apt_code':'apt','expressions':[{'expression':'x'}],'internal_id':'PX01','default':'secret-sentinel'}
 result=s.source_rows([row,row],'isx_auto')
 assert len(result)==2 and result[0]==result[1]
 assert len(result[0]['object_name'])==700 and result[0]['apt_code']=='apt'
 assert result[0]['stage_internal_id']=='PX01' and json.loads(result[0]['input_columns_json'])==[{'name':'IN'}]
 assert 'secret-sentinel' not in json.dumps(result)


@pytest.mark.parametrize('route',['maestro','lineage/dsx','lineage/isx'])
@pytest.mark.asyncio
async def test_advisory_http_denies_auth_rbac_native_session_and_flag(monkeypatch,route):
 from fastapi import FastAPI
 import httpx
 from deps import get_current_user
 from routers import workspace_publication as routes
 app=FastAPI();app.include_router(routes.router)
 monkeypatch.setattr(routes,'ENABLED',lambda:True)
 monkeypatch.setattr(s,'get_db_conn',lambda:pytest.fail('Denied HTTP opened DB'))
 target='/workspace-adapter/maestro/'+ID if route=='maestro' else '/workspace-adapter/lineage/'+ID+'/'+route.split('/')[1]+'-preview'
 async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
  assert (await client.post(target,json=BODY)).status_code==401
  for permissions in (['tela_jobs','tela_pipelines'],['acao_editar','tela_jobs'],['acao_editar','tela_pipelines']):
   app.dependency_overrides[get_current_user]=lambda:{'matricula':'QA','permissoes':permissions}
   assert (await client.post(target,json=BODY,headers={'Authorization':'Bearer unit-token'})).status_code==403
  app.dependency_overrides[get_current_user]=lambda:ACTOR
  assert (await client.post(target,json=BODY)).status_code==401
  monkeypatch.setattr(routes,'ENABLED',lambda:False)
  assert (await client.post(target,json=BODY,headers={'Authorization':'Bearer unit-token'})).status_code==503


@pytest.mark.asyncio
async def test_maestro_draft_never_uses_active_context_and_rejects_expired_response(monkeypatch):
 from routers import workspace_publication as routes
 from routers import maestro as router_maestro
 definition={'identity':{'pipelineName':'DRAFT'},'nodes':[{'id':'DS','type':'datastage'}],'metadata':{'legacyTables':{'etl_pipeline_param':[]}}}
 guards=[];sent=[]
 def guard(*args):
  guards.append(args)
  if len(guards)==2:raise HTTPException(409,'Revisão alterada')
  return definition
 async def converse(body,actor,trusted):sent.append((body,trusted));return {'resposta':'safe','proposta':None}
 monkeypatch.setattr(s,'guarded_draft',guard);monkeypatch.setattr(router_maestro,'conversar_contextual',converse);monkeypatch.setattr(routes,'ENABLED',lambda:True)
 request={**BODY,'mensagens':[{'role':'user','content':'Orientar carga mensal'}],'contexto':{'nivel':'etapa','job_name':'DS','pipeline_name':'ACTIVE-WRONG','params':[{'param_name':'DATE','param_type':'String','param_value':'local'}],'unknown':'sentinel-extra'}}
 with pytest.raises(HTTPException) as error:await routes.workspace_maestro(UUID(ID),request,ACTOR,'Bearer unit-token')
 assert error.value.status_code==409 and len(guards)==2
 assert sent[0][0]['contexto']['pipeline_name']=='DRAFT' and sent[0][1]['pipeline']=='DRAFT'
 assert 'sentinel-extra' not in json.dumps(sent)


@pytest.mark.parametrize('credential',['{"password":"unit-sentinel"}','api_key=unit-sentinel','client_secret=unit-sentinel','{"nested":{"access_token":"unit-sentinel"}}'])
def test_credentials_in_json_and_alternative_names_are_rejected(credential):
 assert s.protected_content(credential)
 with pytest.raises(HTTPException):s.safe_editor([{'param_name':'PARAM','param_type':'String','param_value':credential}])
 with pytest.raises(HTTPException):s.source_rows([{'object_name':'TABLE','columns_detail':[{'name':'FIELD','description':credential}]}],'dsx_auto')



def test_isx_object_name_matches_existing_connector_and_file_semantics():
 rows=s.source_rows([{'stage_name':'Connector','sql_tag':'TableName','sql_expression':'DB.REAL_TABLE\nignored'},{'stage_name':'FileStage','classe':'arquivo','file_path':'/data/input.csv'}],'isx_auto')
 assert rows[0]['object_name']=='DB.REAL_TABLE' and rows[1]['object_name']=='/data/input.csv'
