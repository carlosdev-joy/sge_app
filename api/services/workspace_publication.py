"""F4: projeção restrita do snapshot imutável e reconciliação durável.

Não recebe configuração por HTTP e nunca devolve cifra/referência resolvida.
"""
from __future__ import annotations
import asyncio
import ast
import datetime
import hashlib
import json
import logging
import os
import re
import uuid
from pathlib import Path
import httpx
from fastapi import HTTPException
from db import get_db_conn
from deps import AIRFLOW_URL,AIRFLOW_USER,AIRFLOW_PASSWORD,carregar_usuario

log=logging.getLogger("orquestra.workspace.publication")
TABLES={"etl_pipeline":("pipeline_name",),"etl_pipeline_job":("pipeline_name","job_name"),"etl_pipeline_param":("pipeline_name","param_name"),"etl_pipeline_job_param":("pipeline_name","job_name","param_name"),"etl_valida_arquivo_no":("pipeline_name","task_id"),"etl_valida_arquivo_config":("pipeline_name","task_id","entrada_id"),"etl_pipeline_dependencia":("pipeline_name","depende_de"),"etl_pipeline_owner":("pipeline_name",)}
RUNTIME=frozenset({"dag_criada","last_execution","updated_at","created_at","atualizado_em","criado_em","dag_config_pendente_em"})
IDENT=re.compile(r"^[A-Za-z0-9_.-]+$")
FOLDER=re.compile(r"^[\w .-]+$")
ENABLED=lambda:os.getenv("WORKSPACE_PUBLICATIONS_ENABLED","false").lower()=="true"
class PublicationBlocked(Exception):
 def __init__(self,code,message):self.code=code;self.message=message;super().__init__(message)

def schema(cur):
 return bool(cur.execute("SELECT OBJECT_ID('dbo.etl_workspace_publicacao','U')").fetchone()[0])
def rows(cur,table,name):
 assert table in TABLES
 cur.execute('SELECT * FROM dbo.['+table+'] WHERE pipeline_name=?',(name,));keys=[d[0] for d in cur.description];return [dict(zip(keys,r)) for r in cur.fetchall()]
def active_hash(cur,name):
 return cur.execute("EXEC dbo.sp_workspace_active_hash @name=?",(name,)).fetchone()[0]
def columns(cur,table):
 assert table in TABLES
 return {r[0] for r in cur.execute("SELECT name FROM sys.columns WHERE object_id=OBJECT_ID(?) AND is_identity=0 AND is_computed=0",('dbo.'+table,)).fetchall()}
def ignored_columns(cur,table):
 assert table in TABLES
 return RUNTIME | {r[0] for r in cur.execute("SELECT name FROM sys.columns WHERE object_id=OBJECT_ID(?) AND (is_identity=1 OR is_computed=1)",('dbo.'+table,)).fetchall()}
def _json(value):
 if value is None:return None
 if isinstance(value,dict):return value
 if isinstance(value,str):
  try:return json.loads(value)
  except (ValueError,TypeError):return None
 return None

def materialize(definition,layout,existing):
 """Projeção completa; encrypted só usa a cifra atual da MESMA localização."""
 name=definition['identity']['pipelineName'];metadata=definition.get('metadata') or {};pipeline=dict(metadata.get('legacyPipeline') or {});pipeline['pipeline_name']=name
 if 'schedule' in definition:raise PublicationBlocked('unsupported_schedule','Use a agenda na configuração do pipeline; o campo schedule separado não é projetável')
 if 'parameters' in definition:raise PublicationBlocked('unsupported_parameters','Parâmetros separados não são projetáveis; use o catálogo do pipeline')
 projected={table:[] for table in TABLES};projected['etl_pipeline']=[pipeline]
 related=metadata.get('legacyTables') or {}
 if set(related)-{'etl_pipeline_param','etl_pipeline_dependencia','etl_pipeline_owner'}:raise PublicationBlocked('unsupported_configuration','Tabela adicional não é projetável pelo adaptador')
 for table in ('etl_pipeline_param','etl_pipeline_dependencia','etl_pipeline_owner'):
  projected[table]=[dict(row) for row in related.get(table,[])]
 positions=layout.get('nodes') or {};nodes=definition.get('nodes') or [];edges=definition.get('edges') or []
 for order,node in enumerate(nodes,1):
  cfg=node.get('configuration') or {}
  if set(cfg)-{'legacyJob','etl_pipeline_job_param','etl_valida_arquivo_no','etl_valida_arquivo_config'}:raise PublicationBlocked('unsupported_configuration','Configuração adicional de etapa não é projetável')
  job=dict(cfg.get('legacyJob') or {});job.update(pipeline_name=name,job_name=node['id'],job_type=node['type']);job.setdefault('execution_order',order)
  parents=[edge['source'] for edge in edges if edge['target']==node['id']];job['depends_on_jobs']=','.join(parents) or None
  if node['id'] in positions:job.update(layout_x=positions[node['id']]['x'],layout_y=positions[node['id']]['y'])
  projected['etl_pipeline_job'].append(job)
  for table in ('etl_pipeline_job_param','etl_valida_arquivo_no','etl_valida_arquivo_config'):
   for row in cfg.get(table,[]):
    row=dict(row);row['pipeline_name']=name;row['job_name' if table=='etl_pipeline_job_param' else 'task_id']=node['id'];projected[table].append(row)
 for table,records in projected.items():
  for row in records:
   row['pipeline_name']=name
   if table.endswith('_param'):
    reference=row.pop('secretReference',None);row.pop('tem_valor',None)
    encrypted=str(row.get('param_type') or '').lower()=='encrypted'
    if encrypted:
     expected={'pipelineName':name,'jobName':row.get('job_name'),'parameterName':row.get('param_name')}
     # Collation da origem já canonizada na leitura; a localização é imutável.
     if not isinstance(reference,dict) or set(reference)!=set(expected) or any((reference.get(k)!=v if k=='parameterName' else str(reference.get(k) or '').rstrip().casefold()!=str(v or '').rstrip().casefold()) for k,v in expected.items()):raise PublicationBlocked('secret_reference','Referência protegida não corresponde à localização do parâmetro')
     old=next((r for r in existing.get(table,[]) if all((r.get(k)==row.get(k) if k=='param_name' else str(r.get(k) or '').rstrip().casefold()==str(row.get(k) or '').rstrip().casefold()) for k in TABLES[table])),None)
     if old is None or str(old.get('param_type') or '').lower()!='encrypted':raise PublicationBlocked('secret_reference','Parâmetro protegido não existe mais na origem')
     row['param_value']=old['param_value']
    elif reference is not None:raise PublicationBlocked('secret_reference','Referência protegida exige tipo encrypted')
 return projected

def validate_projection(definition,layout,existing,connection_types,email_policy=None):
 from routers import jobs
 errors=[]
 def error(node,field,code,message):errors.append({'nodeId':node,'field':field,'code':code,'message':message})
 try:projection=materialize(definition,layout,existing)
 except PublicationBlocked as e:return [{'nodeId':None,'field':'definition','code':e.code,'message':e.message}],None
 pipeline=projection['etl_pipeline'][0];name=pipeline['pipeline_name'];nodes=definition['nodes'];ids=[n['id'] for n in nodes]
 if not IDENT.fullmatch(name) or len(name)>200:error(None,'identity.pipelineName','engine_identity','Identificador incompatível com Airflow')
 for field in ('project_name','domain'):
  value=pipeline.get(field)
  if not isinstance(value,str) or not FOLDER.fullmatch(value) or value in {'.','..'} or value.endswith(('.', ' ')):error(None,'metadata.'+field,'invalid_folder','Informe projeto/domínio sem separadores de caminho ou segmentos relativos')
 if not nodes:error(None,'nodes','empty_flow','Adicione pelo menos uma etapa')
 if len(nodes)>500:error(None,'nodes','limit','O adaptador suporta até 500 etapas por publicação')
 if len({n.rstrip().casefold() for n in ids})!=len(ids):error(None,'nodes','duplicate','Identificadores duplicados na collation do pipeline')
 known=set(ids);adj={n:set() for n in ids}
 for edge in definition.get('edges',[]):
  if edge.get('source') not in known or edge.get('target') not in known:error(None,'edges','missing_node','Dependência referencia etapa ausente')
  else:adj[edge['source']].add(edge['target'])
 if jobs._graph_has_cycle(adj):error(None,'edges','cycle','Dependências contêm ciclo')
 schedule_type=pipeline.get('schedule_type') or 'daily'
 if schedule_type not in {'daily','weekly','monthly','custom','monthly_days_times','on_demand'}:error(None,'schedule_type','schedule','Tipo de agenda não suportado')
 if schedule_type!='on_demand' and not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?',str(pipeline.get('scheduled_time') or '')):error(None,'scheduled_time','schedule','Informe horário válido ou selecione sob demanda')
 mssql={key for key,kind in connection_types.items() if kind in {'mssql','sqlserver'}}
 for node,job in zip(nodes,projection['etl_pipeline_job']):
  kind=node['type'];id=node['id'];cfg=node['configuration'];command=job.get('job_command');ssh=job.get('ssh_conn_id');issues=[]
  if not IDENT.fullmatch(id):issues.append('Identificador de etapa incompatível com Airflow')
  if ssh and connection_types.get(ssh)!='ssh':issues.append('Identificador SSH não encontrado')
  if job.get('mssql_conn_id') and job['mssql_conn_id'] not in mssql:issues.append('Identificador SQL não encontrado')
  if kind=='sql':issues+=jobs._validate_sql_node_conn(_json(job.get('sql_json')),mssql)
  elif kind=='python':issues+=jobs._validate_python_node(_json(job.get('python_json')),ssh,_json(job.get('param_vinculos_json')));issues+=[] if ssh else ['Conexão SSH é obrigatória para Python']
  elif kind in {'datastage','shell'}:
   if not ssh:issues.append('Conexão SSH é obrigatória')
   if not isinstance(command,str) or not command.strip():issues.append('Comando da etapa obrigatório')
  elif kind=='storedproc':
   if not job.get('mssql_conn_id'):issues.append('Conexão SQL é obrigatória')
   if not isinstance(command,str) or not command.strip():issues.append('Procedimento obrigatório')
  elif kind=='http':
   if not jobs._valid_http_url(command):issues.append('URL HTTP inválida')
  elif kind=='decisao':issues+=jobs._validate_condition(_json(job.get('condition_json')),known,id,mssql)
  elif kind=='aguarde':issues+=jobs._validate_aguarde(_json(job.get('aguarde_json')))
  elif kind=='notificacao':issues+=jobs._validate_notify(_json(job.get('notify_json')))
  elif kind=='email':issues+=jobs._validate_email(_json(job.get('notify_json')),*(email_policy or (None,None,None,False)),no_novo=not any(r['job_name']==id for r in existing.get('etl_pipeline_job',[])))
  elif kind=='valida_arquivo':
   configs=cfg.get('etl_valida_arquivo_config') or [];parents=cfg.get('etl_valida_arquivo_no') or []
   if len(parents)!=1 or not configs:issues.append('Configure as entradas e a conexão do Valida Arquivo')
   if parents and connection_types.get(parents[0].get('ssh_conn_id'))!='ssh':issues.append('Conexão SSH do Valida Arquivo não encontrada')
   if len(parents)==1 and configs:
    from services import valida_arquivo as va
    try:
     inputs=[{**row,'ignorar_cabecalho':bool(row.get('ignorar_cabecalho'))} for row in sorted(configs,key=lambda row:row.get('ordem',0))]
     config=va.normalizar({**parents[0],'entradas':inputs},projection['etl_pipeline_param'])
     va.impacto(config,projection['etl_pipeline_job'],id,projection['etl_pipeline_param'])
    except (ValueError,TypeError,KeyError):issues.append('Configuração e destinos do Valida Arquivo inválidos; revise entradas, diretórios, políticas e dependências')
  else:issues.append('Tipo de etapa não suportado')
  for message in issues:error(id,'configuration','node_configuration',message)
 # Não alterar coerções/normalizações dos validadores: representação permanece fiel.
 return errors,projection

async def connection_types(cur):
 result={r[0]:r[1] for r in cur.execute("SELECT conn_id,conn_type FROM dbo.etl_conexao").fetchall()}
 async with httpx.AsyncClient(base_url=AIRFLOW_URL,auth=(AIRFLOW_USER,AIRFLOW_PASSWORD),timeout=4,follow_redirects=False,trust_env=False) as client:
  offset=0
  while True:
   response=await client.get('/api/v1/connections',params={'limit':100,'offset':offset});response.raise_for_status();payload=response.json();items=payload.get('connections',[])
   for item in items:result.setdefault(item['connection_id'],item['conn_type'])
   offset+=len(items)
   if offset>=payload.get('total_entries',offset) or not items:break
   if offset>2000:raise PublicationBlocked('connection_catalog_limit','Catálogo de conexões excedeu o limite')
 return result

async def validate_draft(id,revision,actor):
 c=get_db_conn();q=c.cursor()
 try:
  q.execute('SELECT definition_json,layout_json,revision,read_only_json,estado,pipeline_name FROM dbo.etl_workspace_rascunho WHERE draft_id=?',(str(id),));row=q.fetchone()
  if row is None:raise HTTPException(404,'Rascunho não encontrado')
  if row[2]!=revision:raise HTTPException(409,'Revisão alterada; recarregue')
  definition=json.loads(row[0]);layout=json.loads(row[1]);existing={table:rows(q,table,row[5]) for table in TABLES}
  errors,projection=validate_projection(definition,layout,existing,await connection_types(q),__import__('routers.jobs',fromlist=['_config_email_do_admin'])._config_email_do_admin(q))
  async with httpx.AsyncClient(base_url=AIRFLOW_URL,auth=(AIRFLOW_USER,AIRFLOW_PASSWORD),timeout=5,trust_env=False) as client:
   if not await airflow_idle(client,row[5]):errors.append({'nodeId':None,'field':'execution','code':'execution_active','message':'Pipeline possui execução ativa ou disparo pendente no Airflow'})
  errors +=[{'nodeId':None,'field':'definition','code':'read_only','message':message} for message in json.loads(row[3])]
  if row[4]!='ativo':errors.append({'nodeId':None,'field':'state','code':'draft_closed','message':'Rascunho encerrado'})
  if projection:
   for table,records in projection.items():
    allowed=columns(q,table)
    for record in records:
     unknown=set(record)-allowed-ignored_columns(q,table)
     if unknown:errors.append({'nodeId':record.get('job_name') or record.get('task_id'),'field':table,'code':'unknown_column','message':'Configuração contém campo não projetável: '+', '.join(sorted(unknown))})
  return {'revision':row[2],'valid':not errors,'diagnostics':errors[:500]}
 except HTTPException:raise
 except PublicationBlocked as e:raise HTTPException(503,e.message)
 except Exception:raise HTTPException(503,'Dependência de validação indisponível')
 finally:q.close();c.close()

def removed_job_names(existing,desired):
 target={row['job_name'].rstrip().casefold() for row in desired}
 return [row['job_name'] for row in existing if row['job_name'].rstrip().casefold() not in target]

def sync_rows(cur,table,name,desired):
 allowed=columns(cur,table);keys=TABLES[table];present=rows(cur,table,name);desired_keys={tuple(str(r.get(k) or '') if k=='param_name' else str(r.get(k) or '').rstrip().casefold() for k in keys) for r in desired}
 for old in present:
  if tuple(str(old.get(k) or '') if k=='param_name' else str(old.get(k) or '').rstrip().casefold() for k in keys) not in desired_keys:
   cur.execute('DELETE FROM dbo.['+table+'] WHERE '+' AND '.join('['+k+']=?' for k in keys),tuple(old[k] for k in keys))
 for record in desired:
  record={k:v for k,v in record.items() if k in allowed and k not in RUNTIME};values={k:(json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v) for k,v in record.items()};key=tuple(values[k] for k in keys)
  found=cur.execute('SELECT 1 FROM dbo.['+table+'] WHERE '+' AND '.join('['+k+']=?' for k in keys),key).fetchone()
  if found:
   fields=[k for k in values if k not in keys]
   if fields:cur.execute('UPDATE dbo.['+table+'] SET '+','.join('['+k+']=?' for k in fields)+' WHERE '+' AND '.join('['+k+']=?' for k in keys),tuple(values[k] for k in fields)+key)
  else:
   fields=list(values);cur.execute('INSERT dbo.['+table+'] ('+','.join('['+k+']' for k in fields)+') VALUES ('+','.join('?' for _ in fields)+')',tuple(values[k] for k in fields))

def load_operation(cur,id):
 cur.execute('SELECT o.operation_id,o.draft_id,o.version_id,o.pipeline_name,o.revision,o.ator,o.expected_active_hash,o.projection_hash,o.estado,o.factory_run_id,v.definition_json,v.layout_json,v.content_hash FROM dbo.etl_workspace_publicacao o JOIN dbo.etl_workspace_versao v ON v.version_id=o.version_id WHERE o.operation_id=?',(str(id),));r=cur.fetchone()
 if r is None:raise PublicationBlocked('not_found','Publicação não encontrada')
 result=dict(zip(('id','draft','version','name','revision','actor','expected','projected','state','run','definition','layout','content_hash'),r))
 # pyodbc retorna UUID uppercase; pymssql retorna uuid.UUID. Canonizar fronteira.
 result['version']=str(uuid.UUID(str(result['version'])))
 return result
def dag_marker_values(params):
 # Airflow 2.11 REST serializa Param; versões anteriores podem devolver escalares.
 keys=('workspace_version_id','workspace_content_hash','workspace_projection_hash')
 result={}
 for key in keys:
  value=(params or {}).get(key)
  if isinstance(value,dict) and value.get('__class')=='airflow.models.param.Param':value=value.get('value')
  result[key]=value
 return result

async def airflow_idle(client,name):
 response=await client.get('/api/v1/dags/'+name+'/dagRuns',params={'state':['running','queued'],'limit':100})
 if response.status_code==404:return True
 response.raise_for_status();return not response.json().get('dag_runs')

REMOVE_UNPROJECTED_REGISTRY = """DELETE p FROM dbo.etl_workspace_pipeline p JOIN dbo.etl_workspace_publicacao o ON o.operation_id=p.pending_operation_id WHERE o.operation_id=? AND o.projection_hash IS NULL AND o.inherited_projection_hash IS NULL AND p.version_id IS NULL"""
RELEASE_UNPROJECTED_GATE = """UPDATE p SET pending_operation_id=NULL FROM dbo.etl_workspace_pipeline p JOIN dbo.etl_workspace_publicacao o ON o.operation_id=p.pending_operation_id WHERE o.operation_id=? AND o.projection_hash IS NULL AND o.inherited_projection_hash IS NULL"""

def release_unprojected(cur,id):
 cur.execute(REMOVE_UNPROJECTED_REGISTRY,(str(id),))
 cur.execute(RELEASE_UNPROJECTED_GATE,(str(id),))

class ClaimLost(Exception):
 pass

def renew_claim(cur,id,token):
 cur.execute("UPDATE dbo.etl_workspace_publicacao WITH(UPDLOCK,HOLDLOCK) SET processing_until=DATEADD(second,90,SYSUTCDATETIME()) WHERE operation_id=? AND processing_token=? AND processing_until>SYSUTCDATETIME() AND estado NOT IN('publicado','erro')",(str(id),token))
 if cur.rowcount!=1:raise ClaimLost()

async def process_operation(id):
 c=get_db_conn();q=c.cursor();claimed=False;token=str(uuid.uuid4())
 try:
  # Lease do reconciliador é persistente; locks de longa duração ficam fora de HTTP.
  q.execute("UPDATE dbo.etl_workspace_publicacao SET processing_until=DATEADD(second,90,SYSUTCDATETIME()),processing_token=?,tentativas=tentativas+1 WHERE operation_id=? AND estado NOT IN('publicado','erro') AND (processing_until IS NULL OR processing_until<SYSUTCDATETIME())",(token,str(id)));claimed=q.rowcount==1;c.commit()
  if not claimed:return
  op=load_operation(q,id);definition=json.loads(op['definition']);layout=json.loads(op['layout'])
  try:user=carregar_usuario(q,op['actor'])
  except HTTPException:raise PublicationBlocked('permission_revoked','Sessão ou usuário de publicação revogado')
  if not {'tela_pipelines','tela_jobs','acao_editar','acao_publicar'}.issubset(user['permissoes']):raise PublicationBlocked('permission_revoked','Permissão de publicação foi revogada')
  async with httpx.AsyncClient(base_url=AIRFLOW_URL,auth=(AIRFLOW_USER,AIRFLOW_PASSWORD),timeout=10,follow_redirects=False,trust_env=False) as client:
   if op['state']=='pendente':
    if not await airflow_idle(client,op['name']):raise PublicationBlocked('execution_active','Pipeline possui execução ativa ou disparo pendente no Airflow')
    existing={table:rows(q,table,op['name']) for table in TABLES};errors,projection=validate_projection(definition,layout,existing,await connection_types(q),__import__('routers.jobs',fromlist=['_config_email_do_admin'])._config_email_do_admin(q))
    if any(set(record)-columns(q,table)-ignored_columns(q,table) for table,records in projection.items() for record in records) if projection else False:raise PublicationBlocked('unknown_column','Configuração contém campo não projetável')
    if errors:raise PublicationBlocked('publication_invalid','Configuração recusada na validação final; consulte os diagnósticos do rascunho')
    c.rollback();q.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE; SET XACT_ABORT ON')
    renew_claim(q,id,token)
    q.execute('SELECT pending_operation_id FROM dbo.etl_workspace_pipeline WITH(UPDLOCK,HOLDLOCK) WHERE pipeline_name=?',(op['name'],));owner=q.fetchone()
    if not owner or str(owner[0]).lower()!=str(id).lower():raise PublicationBlocked('operation_conflict','Outra operação controla este pipeline')
    if q.execute('SELECT TOP(1) run_id FROM dbo.etl_workspace_execucao WHERE pipeline_name=? AND ativa=1',(op['name'],)).fetchone():raise PublicationBlocked('execution_active','Pipeline possui execução ativa')
    if q.execute("SELECT TOP(1) pipeline_name FROM dbo.etl_pipeline_execucao WITH(UPDLOCK,HOLDLOCK) WHERE pipeline_name=? AND status IN('EXECUTANDO','RUNNING','QUEUED','AGUARDANDO','AGUARDANDO_DEPENDENCIA')",(op['name'],)).fetchone():raise PublicationBlocked('execution_active','Pipeline possui execução ativa ou comando pendente')
    if active_hash(q,op['name'])!=op['expected']:raise PublicationBlocked('active_hash_conflict','Configuração ativa mudou; nenhuma projeção aplicada')
    q.execute("EXEC sp_set_session_context @key=N'workspace_operation',@value=?",(str(id),))
    # Remove referências antes de remover seus alvos; insere os alvos antes das referências.
    for table in ('etl_valida_arquivo_config','etl_valida_arquivo_no','etl_pipeline_job_param'):
     desired=projection[table];keys=TABLES[table]
     desired_keys={tuple(str(r.get(k) or '') if k=='param_name' else str(r.get(k) or '').rstrip().casefold() for k in keys) for r in desired}
     for old in existing[table]:
      if tuple(str(old.get(k) or '') if k=='param_name' else str(old.get(k) or '').rstrip().casefold() for k in keys) not in desired_keys:q.execute('DELETE FROM dbo.['+table+'] WHERE '+' AND '.join('['+k+']=?' for k in keys),tuple(old[k] for k in keys))
    sync_rows(q,'etl_pipeline',op['name'],projection['etl_pipeline'])
    # Job removido com lineage tem configuração associada; apagar lineage somente do job removido.
    for removed in removed_job_names(existing['etl_pipeline_job'],projection['etl_pipeline_job']):
     q.execute('DELETE FROM dbo.etl_job_lineage WHERE pipeline_name=? AND job_name=?',(op['name'],removed))
    sync_rows(q,'etl_pipeline_job',op['name'],projection['etl_pipeline_job'])
    for table in ('etl_pipeline_param','etl_pipeline_job_param','etl_valida_arquivo_no','etl_valida_arquivo_config','etl_pipeline_dependencia','etl_pipeline_owner'):sync_rows(q,table,op['name'],projection[table])
    projected=active_hash(q,op['name']);q.execute("UPDATE dbo.etl_workspace_publicacao SET estado='projetado',projection_hash=?,erro_resumido=NULL,atualizada_em=SYSUTCDATETIME() WHERE operation_id=?",(projected,str(id)));c.commit();op['state']='projetado';op['projected']=projected
   if op['state'] in {'projetado','gerando'}:
    if active_hash(q,op['name'])!=op['projected']:raise PublicationBlocked('projection_hash_conflict','Projeção divergiu; publicação não confirmada')
    c.rollback();renew_claim(q,id,token);c.commit()
    body={'dag_run_id':op['run'],'conf':{'pipeline_name':op['name'],'workspace_operation_id':str(id),'aguardar_ativacao':True}}
    response=await client.post('/api/v1/dags/etl_dag_factory/dagRuns',json=body)
    if response.status_code!=409:response.raise_for_status()
    renew_claim(q,id,token)
    q.execute("UPDATE dbo.etl_workspace_publicacao SET estado='gerando',atualizada_em=SYSUTCDATETIME() WHERE operation_id=?",(str(id),));c.commit()
    run=await client.get('/api/v1/dags/etl_dag_factory/dagRuns/'+op['run']);run.raise_for_status();state=run.json().get('state')
    retry=q.execute('SELECT retry_requested FROM dbo.etl_workspace_publicacao WHERE operation_id=?',(str(id),)).fetchone()[0];c.rollback()
    if retry and state in {'success','failed'}:
     reset=await client.post('/api/v1/dags/etl_dag_factory/clearTaskInstances',json={'dag_run_id':op['run'],'dry_run':False,'reset_dag_runs':True,'only_failed':False});reset.raise_for_status()
     renew_claim(q,id,token)
     q.execute('UPDATE dbo.etl_workspace_publicacao SET retry_requested=0 WHERE operation_id=?',(str(id),));c.commit();return
    if state=='failed':raise PublicationBlocked('factory_failed','Factory recusou a geração; retome após corrigir a dependência ou publique um rascunho corrigido')
    if state!='success':return
    # Confirmação independe de DAG antiga: marcadores do arquivo e do DAG serializado.
    file=Path(os.getenv('WORKSPACE_DAG_ROOT',os.getenv('DAGS_FOLDER','/opt/airflow/dags')))/'generated'/definition['metadata']['legacyPipeline']['project_name']/definition['metadata']['legacyPipeline']['domain']/(op['name']+'.py')
    source=file.read_text();markers={'workspace_version_id':str(op['version']),'workspace_content_hash':op['content_hash'],'workspace_projection_hash':op['projected']}
    assignments=[node.value for node in ast.parse(source).body if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='WORKSPACE_MARKERS' for target in node.targets)]
    if len(assignments)!=1 or ast.literal_eval(assignments[0])!=markers:raise PublicationBlocked('artifact_mismatch','Arquivo DAG não confirma a versão/hash esperados')
    details=await client.get('/api/v1/dags/'+op['name']+'/details')
    if details.status_code==404:return
    details.raise_for_status();dag=details.json()
    if dag.get('has_import_errors'):raise PublicationBlocked('dag_import_error','DAG apresenta erro de importação')
    params=dag_marker_values(dag.get('params'))
    if any(params.get(k)!=v for k,v in markers.items()):return
    renew_claim(q,id,token);c.commit()
    paused=not bool(definition['metadata']['legacyPipeline'].get('active',1))
    changed=await client.patch('/api/v1/dags/'+op['name'],json={'is_paused':paused});changed.raise_for_status()
    confirmed=await client.get('/api/v1/dags/'+op['name']);confirmed.raise_for_status()
    if confirmed.json().get('has_import_errors') is not False:raise PublicationBlocked('dag_import_error','Estado de importação da DAG não confirmado')
    if confirmed.json().get('is_paused')!=paused:return
    renew_claim(q,id,token)
    q.execute('SELECT pending_operation_id FROM dbo.etl_workspace_pipeline WITH(UPDLOCK,HOLDLOCK) WHERE pipeline_name=?',(op['name'],));owner=q.fetchone()
    if not owner or str(owner[0]).lower()!=str(id).lower() or active_hash(q,op['name'])!=op['projected']:raise PublicationBlocked('projection_hash_conflict','Projeção divergiu na confirmação')
    q.execute('UPDATE dbo.etl_workspace_pipeline SET version_id=?,active_hash=?,pending_operation_id=NULL WHERE pipeline_name=?',(str(op['version']),op['projected'],op['name']))
    q.execute("UPDATE dbo.etl_workspace_publicacao SET estado='publicado',erro_resumido=NULL,atualizada_em=SYSUTCDATETIME() WHERE operation_id=?",(str(id),))
    q.execute("UPDATE dbo.etl_workspace_rascunho SET estado='publicado',revision=revision+1,atualizado_em=SYSUTCDATETIME() WHERE draft_id=? AND revision=?",(str(op['draft']),op['revision']))
    q.execute('UPDATE dbo.etl_workspace_lease SET expires_at=SYSUTCDATETIME() WHERE draft_id=?',(str(op['draft']),))
    q.execute("INSERT dbo.etl_workspace_evento(entidade_id,ator,acao,revision,operation_id) VALUES(?,?,'confirmar_publicacao',?,?)",(str(op['draft']),op['actor'],op['revision'],str(id)));c.commit()
 except ClaimLost:
  c.rollback()
 except PublicationBlocked as e:
  c.rollback()
  if not q.execute("SELECT 1 FROM dbo.etl_workspace_publicacao WITH(UPDLOCK,HOLDLOCK) WHERE operation_id=? AND processing_token=? AND processing_until>SYSUTCDATETIME() AND estado NOT IN('publicado','erro')",(str(id),token)).fetchone():c.rollback();return
  q.execute("UPDATE dbo.etl_workspace_publicacao SET estado='erro',erro_resumido=?,processing_until=NULL,atualizada_em=SYSUTCDATETIME() WHERE operation_id=?",(e.code+': '+e.message,str(id)))
  # Quarentena herdada continua mesmo se esta intenção ainda não projetou.
  release_unprojected(q,id);c.commit()
 except Exception:
  c.rollback();q.execute("UPDATE dbo.etl_workspace_publicacao SET erro_resumido=N'Dependência indisponível; reconciliação será retomada',atualizada_em=SYSUTCDATETIME() WHERE operation_id=? AND processing_token=? AND processing_until>SYSUTCDATETIME() AND estado NOT IN('publicado','erro')",(str(id),token));c.commit();log.warning('Publicação aguardando dependência; detalhes redigidos')
 finally:
  try:
   if claimed:
    q.execute('UPDATE dbo.etl_workspace_publicacao SET processing_until=NULL,processing_token=NULL WHERE operation_id=? AND processing_token=?',(str(id),token));q.execute("EXEC sp_set_session_context @key=N'workspace_operation',@value=NULL");c.commit()
  finally:q.close();c.close()

async def reconcile_once():
 c=get_db_conn();q=c.cursor()
 try:
  if not schema(q):return
  pending=[str(r[0]) for r in q.execute("SELECT TOP(20) operation_id FROM dbo.etl_workspace_publicacao WHERE estado NOT IN('publicado','erro') ORDER BY criada_em").fetchall()]
  runs=[tuple(r) for r in q.execute('SELECT pipeline_name,run_id,activity_epoch FROM dbo.etl_workspace_execucao WHERE ativa=1').fetchall()]
 finally:q.close();c.close()
 async with httpx.AsyncClient(base_url=AIRFLOW_URL,auth=(AIRFLOW_USER,AIRFLOW_PASSWORD),timeout=5,trust_env=False) as client:
  from services.workspace_operations import reconcile_commands
  await reconcile_commands(client)
  for name,run,epoch in runs:
   response=await client.get('/api/v1/dags/'+name+'/dagRuns/'+run)
   if response.is_success and response.json().get('state') in {'success','failed'}:
    c=get_db_conn();q=c.cursor()
    try:q.execute('UPDATE dbo.etl_workspace_execucao SET ativa=0,encerrada_em=SYSUTCDATETIME() WHERE pipeline_name=? AND run_id=? AND activity_epoch=?',(name,run,epoch));c.commit()
    finally:q.close();c.close()
 for id in pending:await process_operation(id)
async def reconcile_loop():
 while True:
  if ENABLED():
   try:await reconcile_once()
   except asyncio.CancelledError:raise
   except Exception:log.warning('Reconciliador workspace aguardando dependência; detalhes redigidos')
  await asyncio.sleep(5)
