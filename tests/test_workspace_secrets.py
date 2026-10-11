import json
from uuid import UUID
import pytest
from fastapi import HTTPException
from services import workspace_secrets as s
from services.workspace_publication import materialize, PublicationBlocked

ID='c1111111-1111-4111-8111-111111111111'
ACTOR={'matricula':'QA','permissoes':['tela_pipelines','tela_jobs','acao_editar']}
BODY={'expectedRevision':1,'fence':2,'parameterName':'Senha','jobName':None,'value':'SENTINEL_ONLY_FOR_UNIT_TEST'}

class Connection:
 def __init__(self, *, session=True, revision=1, holder='QA', fence=2, live=1, pending=False, schema=True, readonly=False):
  self.queries=[];self.committed=False;self.rolled=False;self.closed=False
  self.settings=locals()
 def cursor(self):return self
 def execute(self,sql,*args):self.queries.append((sql,args));self.query=sql;return self
 def fetchone(self):
  x=self.settings
  if 'OBJECT_ID' in self.query:return (1 if x['schema'] else None,)
  if 'FROM dbo.etl_workspace_rascunho' in self.query:return ('PIPE',json.dumps({'schemaVersion':1,'nodes':[]}),x['revision'],'ativo','["consulta"]' if x['readonly'] else '[]')
  if 'FROM dbo.etl_sessao' in self.query:return ('QA',) if x['session'] else None
  if 'FROM dbo.etl_workspace_publicacao' in self.query:return (ID,) if x['pending'] else None
  if 'FROM dbo.etl_workspace_lease' in self.query:return (x['holder'],__import__('hashlib').sha256(b'unit-token').hexdigest(),x['fence'],x['live'])
  raise AssertionError(self.query)
 def commit(self):self.committed=True
 def rollback(self):self.rolled=True
 def close(self):self.closed=True

@pytest.mark.parametrize('patch',[{'expectedRevision':True},{'fence':0},{'parameterName':'a.b.c'},{'parameterName':42},{'jobName':False},{'value':None},{'value':''},{'value':'***'},{'value':'x'*16001},{'value':'\ud800'}])
def test_invalid_secret_request_is_rejected_before_storage(patch):
 with pytest.raises(HTTPException) as error:s.secret_request({**BODY,**patch})
 assert error.value.status_code==422
 assert BODY['value'] not in error.value.detail

@pytest.mark.parametrize('settings,status',[({'schema':False},503),({'session':False},401),({'revision':2},409),({'holder':'OTHER'},409),({'fence':3},409),({'live':0},409),({'pending':True},409),({'readonly':True},409)])
def test_secret_write_denies_stale_unauthorized_or_unavailable_state(monkeypatch,settings,status):
 connection=Connection(**settings);monkeypatch.setattr(s,'get_db_conn',lambda:connection);monkeypatch.setattr(s,'encrypt_password',lambda _: 'cipher-sentinel')
 with pytest.raises(HTTPException) as error:s.store_secret(UUID(ID),BODY,ACTOR,'Bearer unit-token')
 assert error.value.status_code==status
 assert connection.rolled and connection.closed and not connection.committed
 assert not any(sql.startswith('INSERT') for sql,_ in connection.queries)


def test_secret_write_only_persists_cipher_and_returns_reference(monkeypatch):
 connection=Connection();monkeypatch.setattr(s,'get_db_conn',lambda:connection);monkeypatch.setattr(s,'encrypt_password',lambda _: 'cipher-sentinel')
 result=s.store_secret(UUID(ID),BODY,ACTOR,'Bearer unit-token')
 assert connection.committed and connection.closed and not connection.rolled
 assert result['secretReference']['pipelineName']=='PIPE'
 assert result['secretReference']['jobName'] is None
 assert result['secretReference']['parameterName']=='Senha'
 assert BODY['value'] not in json.dumps(connection.queries)+json.dumps(result)
 assert 'cipher-sentinel' not in json.dumps(result)
 assert not any(sql.startswith(('UPDATE','DELETE')) for sql,_ in connection.queries)
 assert all('etl_pipeline_param' not in sql for sql,_ in connection.queries)

@pytest.mark.parametrize('auth,actor,status',[(None,ACTOR,401),('Basic unit',ACTOR,401),('Bearer unit-token',{'matricula':'QA','permissoes':[]},403)])
def test_secret_write_requires_native_bearer_and_edit_permissions(auth,actor,status):
 with pytest.raises(HTTPException) as error:s.store_secret(UUID(ID),BODY,actor,auth)
 assert error.value.status_code==status


def protected_definition():
 ref={'secretId':ID,'pipelineName':'PIPE','jobName':None,'parameterName':'Senha'}
 return {'identity':{'pipelineName':'PIPE'},'metadata':{'legacyTables':{'etl_pipeline_param':[{'param_name':'Senha','param_type':'Encrypted','param_value':'***','secretReference':ref}]}},'nodes':[],'edges':[]}


def test_historical_vault_cipher_is_projected_without_active_fallback(monkeypatch):
 from cryptography.fernet import Fernet
 key=Fernet.generate_key();monkeypatch.setenv('ORQUESTRA_CONN_KEY',key.decode());cipher=Fernet(key).encrypt(b'unit-test-only').decode()
 definition=protected_definition();snapshot=json.dumps(definition)
 vault={ID:{'pipelineName':'PIPE','jobName':None,'parameterName':'Senha','ciphertext':cipher}}
 projected=materialize(definition,{}, {'_workspace_secrets':vault,'etl_pipeline_param':[{'pipeline_name':'PIPE','param_name':'Senha','param_type':'Encrypted','param_value':'newer-active-cipher'}]})
 assert projected['etl_pipeline_param'][0]['param_value']==cipher
 assert 'secretReference' not in projected['etl_pipeline_param'][0]
 assert json.dumps(definition)==snapshot and cipher not in snapshot

@pytest.mark.parametrize('field,value',[('pipelineName','OTHER'),('jobName','NODE'),('parameterName','Other'),('secretId','invalid')])
def test_vault_reference_cannot_be_reassigned(field,value):
 definition=protected_definition();definition['metadata']['legacyTables']['etl_pipeline_param'][0]['secretReference'][field]=value
 with pytest.raises(PublicationBlocked):materialize(definition,{}, {'_workspace_secrets':{ID:{'pipelineName':'PIPE','jobName':None,'parameterName':'Senha','ciphertext':'unit-cipher'}}})


def test_missing_historical_secret_never_falls_back_to_active_cipher():
 with pytest.raises(PublicationBlocked):materialize(protected_definition(),{}, {'etl_pipeline_param':[{'pipeline_name':'PIPE','param_name':'Senha','param_type':'Encrypted','param_value':'newer-active-cipher'}]})

@pytest.mark.parametrize('mode',['corrupt','truncated','wrong-key'])
def test_vault_cipher_integrity_failure_blocks_projection(monkeypatch,mode):
 from cryptography.fernet import Fernet
 key=Fernet.generate_key();cipher=Fernet(key).encrypt(b'unit-test-only').decode()
 if mode=='corrupt':cipher=cipher[:-8]+'AAAAAAAA'
 elif mode=='truncated':cipher=cipher[:40]
 else:key=Fernet.generate_key()
 monkeypatch.setenv('ORQUESTRA_CONN_KEY',key.decode())
 with pytest.raises(PublicationBlocked) as error:materialize(protected_definition(),{}, {'_workspace_secrets':{ID:{'pipelineName':'PIPE','jobName':None,'parameterName':'Senha','ciphertext':cipher}}})
 assert error.value.code=='secret_cipher_invalid' and cipher not in error.value.message

def test_legacy_snapshot_restores_historical_cipher_even_after_replacement_or_removal(monkeypatch):
 from cryptography.fernet import Fernet
 key=Fernet.generate_key();monkeypatch.setenv('ORQUESTRA_CONN_KEY',key.decode())
 first=Fernet(key).encrypt(b'unit-s1').decode();second=Fernet(key).encrypt(b'unit-s2').decode()
 definition=protected_definition();del definition['metadata']['legacyTables']['etl_pipeline_param'][0]['secretReference']['secretId']
 for active in ([{'pipeline_name':'PIPE','param_name':'Senha','param_type':'Encrypted','param_value':second}],[]):
  projected=materialize(definition,{}, {'etl_pipeline_param':active,'_workspace_legacy_secrets':{('', 'Senha'):first}})
  assert projected['etl_pipeline_param'][0]['param_value']==first
 with pytest.raises(PublicationBlocked) as error:materialize(definition,{}, {'etl_pipeline_param':[{'pipeline_name':'PIPE','param_name':'Senha','param_type':'Encrypted','param_value':second}],'_workspace_legacy_secrets':{}})
 assert error.value.code=='secret_history_unavailable'

@pytest.mark.asyncio
async def test_secret_route_enforces_auth_rbac_bearer_and_feature_flag(monkeypatch):
 from fastapi import FastAPI
 import httpx
 from deps import get_current_user
 from routers import workspace_publication as routes
 app=FastAPI();app.include_router(routes.router)
 monkeypatch.setattr(routes,'ENABLED',lambda:True)
 monkeypatch.setattr(s,'get_db_conn',lambda:pytest.fail('Denied HTTP must not open database'))
 async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
  target='/workspace-adapter/secrets/'+ID
  response=await client.post(target,json=BODY)
  assert response.status_code==401
  for permissions,expected in [(['tela_pipelines','tela_jobs'],403),(['acao_editar','tela_pipelines'],403)]:
   app.dependency_overrides[get_current_user]=lambda:{'matricula':'QA','permissoes':permissions}
   response=await client.post(target,json=BODY,headers={'Authorization':'Bearer unit-token'})
   assert response.status_code==expected and BODY['value'] not in response.text
  app.dependency_overrides[get_current_user]=lambda:ACTOR
  response=await client.post(target,json=BODY)
  assert response.status_code==401
  monkeypatch.setattr(routes,'ENABLED',lambda:False)
  response=await client.post(target,json=BODY,headers={'Authorization':'Bearer unit-token'})
  assert response.status_code==503 and BODY['value'] not in response.text
