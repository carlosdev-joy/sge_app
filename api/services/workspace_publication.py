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
from services.workspace_dependencies import dependency_changes, dependency_diagnostics
from deps import AIRFLOW_URL,AIRFLOW_USER,AIRFLOW_PASSWORD,carregar_usuario

log=logging.getLogger("orquestra.workspace.publication")
TABLES={"etl_pipeline":("pipeline_name",),"etl_pipeline_job":("pipeline_name","job_name"),"etl_pipeline_param":("pipeline_name","param_name"),"etl_pipeline_job_param":("pipeline_name","job_name","param_name"),"etl_valida_arquivo_no":("pipeline_name","task_id"),"etl_valida_arquivo_config":("pipeline_name","task_id","entrada_id"),"etl_pipeline_dependencia":("pipeline_name","depende_de"),"etl_pipeline_owner":("pipeline_name",),"etl_job_lineage":("pipeline_name",)}
RUNTIME=frozenset({"dag_criada","last_execution","updated_at","created_at","atualizado_em","criado_em","dag_config_pendente_em"})
LINEAGE_RUNTIME=RUNTIME|{'extracted_at'}
NOTIFICATION_FLAGS=frozenset({'envia_msg_inicio','envia_msg_fim','envia_msg_erro'})
IDENT=re.compile(r"^[A-Za-z0-9_.-]+$")
FOLDER=re.compile(r"^[\w .-]+$")
ENABLED=lambda:os.getenv("WORKSPACE_PUBLICATIONS_ENABLED","false").lower()=="true"
class PublicationBlocked(Exception):
 def __init__(self,code,message,*,node_id=None,field='definition'):self.code=code;self.message=message;self.node_id=node_id;self.field=field;super().__init__(message)

def schema(cur):
 return bool(cur.execute("SELECT OBJECT_ID('dbo.etl_workspace_publicacao','U')").fetchone()[0])
def rows(cur,table,name):
 assert table in TABLES
 cur.execute('SELECT * FROM dbo.['+table+'] WHERE pipeline_name=?',(name,));keys=[d[0] for d in cur.description];return [dict(zip(keys,r)) for r in cur.fetchall()]
def active_hash(cur,name):
 return cur.execute("EXEC dbo.sp_workspace_active_hash @name=?",(name,)).fetchone()[0]
def physical_columns(cur,table):
 assert table in TABLES
 return {r[0] for r in cur.execute("SELECT name FROM sys.columns WHERE object_id=OBJECT_ID(?) AND is_identity=0 AND is_computed=0",('dbo.'+table,)).fetchall()}
def columns(cur,table):
 # Só as três flags históricas possuem aliases conhecidos; nenhum campo desconhecido é aceito.
 return {key.lower() if table=='etl_pipeline' and key.lower() in NOTIFICATION_FLAGS else key for key in physical_columns(cur,table)}
def sql_notification_fields(cur,table,record):
 if table!='etl_pipeline':return record
 names={key.lower():key for key in physical_columns(cur,table) if key.lower() in NOTIFICATION_FLAGS}
 return {names.get(key,key):value for key,value in record.items()}
def ignored_columns(cur,table):
 assert table in TABLES
 return (LINEAGE_RUNTIME if table=='etl_job_lineage' else RUNTIME) | {r[0] for r in cur.execute("SELECT name FROM sys.columns WHERE object_id=OBJECT_ID(?) AND (is_identity=1 OR is_computed=1)",('dbo.'+table,)).fetchall()}
def _json(value):
 if value is None:return None
 if isinstance(value,dict):return value
 if isinstance(value,str):
  try:return json.loads(value)
  except (ValueError,TypeError):return None
 return None

def authenticated_cipher(value):
 try:
  from services.conn_crypto import _fernet
  if not isinstance(value,str) or not value:raise ValueError()
  # extract_timestamp autentica HMAC sem decifrar/expor o texto claro.
  _fernet().extract_timestamp(value.encode('ascii'))
 except Exception:raise PublicationBlocked('secret_cipher_invalid','Valor protegido indisponível; confira a chave e a integridade do armazenamento') from None
 return value

def load_workspace_secrets(cur,definition,existing,legacy_version=None,draft_id=None):
 # Vault imutável: somente cifras, nunca texto claro. Sem UUID não há consulta adicional.
 def refs(value):
  if isinstance(value,dict):
   if isinstance(value.get('secretReference'),dict):yield value['secretReference']
   for child in value.values():yield from refs(child)
  elif isinstance(value,list):
   for child in value:yield from refs(child)
 references=list(refs(definition));identifiers=[reference['secretId'] for reference in references if 'secretId' in reference]
 if not references:return existing
 cur.execute("SELECT OBJECT_ID('dbo.etl_workspace_segredo','U')")
 if not cur.fetchone()[0]:raise PublicationBlocked('secret_schema_unavailable','Valores protegidos indisponíveis; aplique a migration 157')
 vault={}
 for id in set(str(value) for value in identifiers):
  try:canonical=str(uuid.UUID(id))
  except (ValueError,TypeError):raise PublicationBlocked('secret_reference','Referência protegida inválida')
  cur.execute('SELECT pipeline_name,job_name,param_name,ciphertext FROM dbo.etl_workspace_segredo WITH(HOLDLOCK) WHERE secret_id=? AND pipeline_name=?',(canonical,definition['identity']['pipelineName']))
  row=cur.fetchone()
  if row:vault[canonical]={'pipelineName':row[0],'jobName':row[1],'parameterName':row[2],'ciphertext':row[3]}
 baseline={}
 legacy=[reference for reference in references if 'secretId' not in reference]
 if legacy:
  cur.execute("SELECT OBJECT_ID('dbo.etl_workspace_segredo_legado','U')")
  if not cur.fetchone()[0]:raise PublicationBlocked('secret_schema_unavailable','Valores protegidos históricos indisponíveis; aplique a migration 157')
  if legacy_version is None and draft_id is not None:
   cur.execute('SELECT base_version_id FROM dbo.etl_workspace_rascunho WHERE draft_id=?',(str(draft_id),));source=cur.fetchone();legacy_version=source[0] if source else None
  for reference in legacy:
   job=reference.get('jobName');parameter=reference.get('parameterName')
   if not isinstance(parameter,str):raise PublicationBlocked('secret_reference','Referência protegida histórica inválida')
   cur.execute('SELECT ciphertext FROM dbo.etl_workspace_segredo_legado WITH(HOLDLOCK) WHERE version_id=? AND pipeline_name=? AND param_name=? AND (job_name=? OR (job_name IS NULL AND ? IS NULL))',(str(legacy_version) if legacy_version else None,definition['identity']['pipelineName'],parameter,job,job))
   row=cur.fetchone()
   if row:baseline[(str(job or '').rstrip().casefold(),parameter)]=authenticated_cipher(row[0])
 return {**existing,'_workspace_secrets':vault,'_workspace_legacy_secrets':baseline}

def materialize(definition,layout,existing):
 """Projeção completa; produção prepara cifras imutáveis antes desta função."""
 name=definition['identity']['pipelineName'];metadata=definition.get('metadata') or {};pipeline=dict(metadata.get('legacyPipeline') or {});pipeline['pipeline_name']=name
 for key in tuple(pipeline):
  lower=key.lower()
  if lower in NOTIFICATION_FLAGS and key!=lower:
   if lower in pipeline and pipeline[lower]!=pipeline[key]:raise PublicationBlocked('ambiguous_notification_flag','Configuração contém valores conflitantes de notificação',field=lower)
   pipeline[lower]=pipeline.pop(key)
 if 'alertPolicy' in definition:
  from services.pipeline_alerts import policy
  try:policy(definition['alertPolicy'])
  except HTTPException as error:raise PublicationBlocked('alert_policy_invalid','Política de alertas inválida ou não suportada',field='alertPolicy') from error
 if 'schedule' in definition:raise PublicationBlocked('unsupported_schedule','Use a agenda na configuração do pipeline; o campo schedule separado não é projetável')
 if 'parameters' in definition:raise PublicationBlocked('unsupported_parameters','Parâmetros separados não são projetáveis; use o catálogo do pipeline')
 policy_fields=('liberar_dependentes_sem_movimento','notificar_sem_movimento')
 previous_pipeline=next(iter(existing.get('etl_pipeline',[])),{})
 if any(field in pipeline and pipeline[field]!=previous_pipeline.get(field,False if field==policy_fields[0] else True) for field in policy_fields):pipeline['politica_sem_movimento_revisao']=int(previous_pipeline.get('politica_sem_movimento_revisao') or 0)+1
 captured=type(metadata.get('workspaceLineageVersion')) is int and metadata.get('workspaceLineageVersion')==1
 if 'workspaceLineageVersion' in metadata and not captured:raise PublicationBlocked('lineage_contract','Contrato de lineage inválido')
 projected={table:[] for table in TABLES if table!='etl_job_lineage' or captured};projected['etl_pipeline']=[pipeline]
 related=metadata.get('legacyTables') or {}
 if set(related)-{'etl_pipeline_param','etl_pipeline_dependencia','etl_pipeline_owner'}:raise PublicationBlocked('unsupported_configuration','Tabela adicional não é projetável pelo adaptador')
 for table in ('etl_pipeline_param','etl_pipeline_dependencia','etl_pipeline_owner'):
  projected[table]=[dict(row) for row in related.get(table,[])]
 # O snapshot pode omitir o CSV, mas uma lista vazia é remoção explícita.
 # Projetar NULL impede que UPDATE parcial conserve predecessores de outra versão.
 pipeline.setdefault('depends_on',','.join(str(row.get('depende_de') or '') for row in projected['etl_pipeline_dependencia'] if row.get('tipo')=='PIPELINE') or None)
 positions=layout.get('nodes') or {};nodes=definition.get('nodes') or [];edges=definition.get('edges') or []
 for order,node in enumerate(nodes,1):
  cfg=node.get('configuration') or {}
  unknown=sorted(set(cfg)-({'legacyJob','etl_pipeline_job_param','etl_valida_arquivo_no','etl_valida_arquivo_config','etl_job_lineage'} if captured else {'legacyJob','etl_pipeline_job_param','etl_valida_arquivo_no','etl_valida_arquivo_config'}))
  if unknown:raise PublicationBlocked('unsupported_configuration','Configuração adicional de etapa não é projetável',node_id=node.get('id'),field='configuration.'+unknown[0])
  if captured:
   lineage=cfg.get('etl_job_lineage')
   if not isinstance(lineage,list) or len(lineage)>5000 or any(not isinstance(row,dict) for row in lineage):raise PublicationBlocked('lineage_contract','Cada etapa exige uma lista de lineage válida')
   for row in lineage:projected['etl_job_lineage'].append({**row,'pipeline_name':name,'job_name':node['id']})
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
     if isinstance(reference,dict) and 'secretId' in reference:
      if set(reference)!=set(expected)|{'secretId'} or any(reference.get(key)!=value for key,value in expected.items()):raise PublicationBlocked('secret_reference','Referência protegida não corresponde ao parâmetro')
      try:identifier=str(uuid.UUID(reference['secretId']))
      except (ValueError,TypeError,AttributeError):raise PublicationBlocked('secret_reference','Referência protegida inválida')
      protected=existing.get('_workspace_secrets',{}).get(identifier)
      if not protected or any(protected.get(key)!=value for key,value in expected.items()) or not isinstance(protected.get('ciphertext'),str) or not protected['ciphertext']:raise PublicationBlocked('secret_reference','Valor protegido histórico indisponível')
      row['param_value']=authenticated_cipher(protected['ciphertext'])
      continue
     # Collation da origem já canonizada na leitura; a localização é imutável.
     if not isinstance(reference,dict) or set(reference)!=set(expected) or any((reference.get(k)!=v if k=='parameterName' else str(reference.get(k) or '').rstrip().casefold()!=str(v or '').rstrip().casefold()) for k,v in expected.items()):raise PublicationBlocked('secret_reference','Referência protegida não corresponde à localização do parâmetro')
     if '_workspace_legacy_secrets' in existing:
      baseline=existing['_workspace_legacy_secrets'].get((str(expected['jobName'] or '').rstrip().casefold(),expected['parameterName']))
      if not baseline:raise PublicationBlocked('secret_history_unavailable','Valor protegido desta versão não possui cifra histórica comprovada')
      row['param_value']=baseline
      continue
     old=next((r for r in existing.get(table,[]) if all((r.get(k)==row.get(k) if k=='param_name' else str(r.get(k) or '').rstrip().casefold()==str(row.get(k) or '').rstrip().casefold()) for k in TABLES[table])),None)
     if old is None or str(old.get('param_type') or '').lower()!='encrypted':raise PublicationBlocked('secret_reference','Parâmetro protegido não existe mais na origem')
     row['param_value']=old['param_value']
    elif reference is not None:raise PublicationBlocked('secret_reference','Referência protegida exige tipo encrypted')
 return projected

def engine_schedule_times(raw):
 """Horários de horarios_especificos que etl_dag_factory._build_cron usa: mesmo split e int(); a entrada ilegível o motor ignora."""
 for text in (raw or '').strip().split(','):
  parts=text.strip().split(':')
  try:hour,minute=int(parts[0]),int(parts[1]) if len(parts)>1 else 0
  except ValueError:continue
  yield text.strip(),hour,minute

def validate_projection(definition,layout,existing,connection_types,email_policy=None):
 from routers import jobs
 from services import param_vinculos
 errors=[]
 def error(node,field,code,message):errors.append({'nodeId':node,'field':field,'code':code,'message':message})
 try:projection=materialize(definition,layout,existing)
 except PublicationBlocked as e:return [{'nodeId':e.node_id,'field':e.field,'code':e.code,'message':e.message}],None
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
 if schedule_type not in {'daily','weekly','monthly','biweekly','custom','monthly_days_times','on_demand'}:error(None,'schedule_type','schedule','Tipo de agenda não suportado')
 if schedule_type!='on_demand' and not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?',str(pipeline.get('scheduled_time') or '')):error(None,'scheduled_time','schedule','Informe horário válido ou selecione sob demanda')
 # Os mesmos formatos e limites do cadastro anterior, sem normalização silenciosa.
 from routers import pipelines as schedules
 previous_pipeline=next(iter(existing.get('etl_pipeline',[])),{})
 # sync_rows grava com UPDATE parcial: chave omitida conserva a coluna publicada e null explícito a limpa.
 # A agenda abaixo é a que o motor lerá depois da gravação; a sobreposição é local e a projeção não muda.
 effective={**previous_pipeline,**pipeline};kind=effective.get('schedule_type') or 'daily'
 def invalid_days(days):return bool(days) and (not isinstance(days,str) or any(day not in {'0','1','2','3','4','5','6'} for day in days.split(',')))
 try:
  if kind=='custom':
   if not schedules._parse_horarios_especificos(effective.get('horarios_especificos')):error(None,'horarios_especificos','schedule','Informe pelo menos um horário de execução')
   if invalid_days(effective.get('dias_semana')):error(None,'dias_semana','schedule','Selecione dias da semana válidos')
  # Fora de sob demanda e dias do mês, a factory também usa os horários legíveis, e a tela os edita como horários específicos.
  # Agenda igual à publicada fica como está, como criticidade/SLA abaixo.
  elif kind not in {'on_demand','monthly_days_times'} and any(effective.get(field)!=previous_pipeline.get(field) for field in ('schedule_type','horarios_especificos','dias_semana')):
   # Formato e faixa pelo parser do cadastro, só para o diagnóstico: o retorno normalizado é descartado e o texto publica como está.
   try:schedules._parse_horarios_especificos(effective.get('horarios_especificos'))
   except HTTPException as exc:error(None,'horarios_especificos','schedule',str(exc.detail))
   # dias_semana entra no cron que cai no diário; nos demais tipos, só junto de horário legível.
   if (kind not in {'hourly','weekly','monthly','biweekly'} or next(engine_schedule_times(effective.get('horarios_especificos')),None)) and invalid_days(effective.get('dias_semana')):error(None,'dias_semana','schedule','Selecione dias da semana válidos')
  if kind=='monthly_days_times' and not schedules._validate_dias_horarios_mes(effective.get('dias_horarios_mes')):error(None,'dias_horarios_mes','schedule','Adicione dias e horários do mês')
  for mode,field,maximum in [('weekly','schedule_dow',6),('monthly','schedule_dom',28),('biweekly','schedule_dom',13)]:
   if kind==mode:
    number=effective.get(field);number=1 if number is None else number;minimum=0 if mode=='weekly' else 1
    if isinstance(number,bool) or not isinstance(number,int) or not minimum<=number<=maximum:error(None,field,'schedule','Informe um dia válido para a agenda')
 except (HTTPException,ValueError,TypeError,AttributeError) as exc:
  message=str(exc.detail) if isinstance(exc,HTTPException) else 'Confira os dias e horários da agenda'
  error(None,'schedule','schedule',message)
 for field,allowed in (('criticidade',{'Alta','Media','Baixa'}),('ambiente',{'PROD','HML','DEV'})):
  if field in pipeline and pipeline[field] not in allowed and pipeline[field]!=previous_pipeline.get(field):error(None,field,'pipeline_configuration','Selecione '+field+' válido')
 for field,minimum,maximum in (('sla_minutos',1,525600),('max_active_runs',1,10),('retries_count',0,10),('retry_delay_seconds',0,604800)):
  value=pipeline.get(field)
  if value is not None and (type(value) is not int or not minimum<=value<=maximum) and value!=previous_pipeline.get(field):error(None,field,'pipeline_configuration','Informe número inteiro válido para '+field)
 for field in ('hora_virada','nao_iniciar_antes','hora_limite_dependencia'):
  value=pipeline.get(field)
  if value and value!=previous_pipeline.get(field) and not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?',str(value)):error(None,field,'pipeline_configuration','Informe horário válido para '+field)
 if pipeline.get('email_destinatarios')!=previous_pipeline.get('email_destinatarios'):
  from services.email_mime import validar_destinatarios
  raw=pipeline.get('email_destinatarios')
  try:recipients=json.loads(raw) if isinstance(raw,str) else raw or []
  except (ValueError,TypeError):recipients=None
  if not isinstance(recipients,list) or any(not isinstance(item,str) for item in recipients):error(None,'email_destinatarios','pipeline_configuration','Informe destinatários em uma lista válida')
  else:
   valid,issues=validar_destinatarios(recipients,(email_policy or (None,None))[1])
   if issues:error(None,'email_destinatarios','pipeline_configuration','Confira formato, domínios permitidos e limite dos destinatários')
   else:pipeline['email_destinatarios']=json.dumps(valid,ensure_ascii=False)
 if pipeline.get('active') in (False,0) and previous_pipeline.get('active') not in (False,0) and len(str(pipeline.get('motivo_inativacao') or '').strip())<5:error(None,'motivo_inativacao','pipeline_configuration','Informe o motivo da inativação com pelo menos 5 caracteres')
 from services import job_params as parameter_rules
 for table in ('etl_pipeline_param','etl_pipeline_job_param'):
  known_names=set()
  for parameter in projection[table]:
   scope=(parameter.get('job_name'),str(parameter.get('param_name') or '').lower())
   if scope in known_names:error(parameter.get('job_name'),'parameters','duplicate','Parâmetro duplicado no mesmo escopo')
   known_names.add(scope)
   old=next((row for row in existing.get(table,[]) if all(row.get(key)==parameter.get(key) for key in TABLES[table])),None)
   if old is not None and all(old.get(key)==value for key,value in parameter.items()):continue
   if table=='etl_pipeline_job_param' and next((n['type'] for n in nodes if n['id']==parameter.get('job_name')),None)!='datastage':continue
   safe={**parameter,'param_value':'***' if str(parameter.get('param_type') or '').lower()=='encrypted' else parameter.get('param_value')}
   _,issues=parameter_rules.normalizar_item(safe)
   for message in issues:error(parameter.get('job_name'),'parameters','parameter_configuration',message)
   if table=='etl_pipeline_param' and parameter.get('param_destino','datastage') not in {'datastage','orquestra'}:error(None,'param_destino','parameter_configuration','Destino do parâmetro inválido')
 mssql={key for key,kind in connection_types.items() if kind in {'mssql','sqlserver'}}
 # Linha sem nome já é recusada pela checagem do catálogo acima; não serve de referência.
 # Destino omitido na linha projetada vale o DEFAULT 'datastage' da coluna (migration 129).
 catalog=[{'param_destino':'datastage',**p} for p in projection['etl_pipeline_param'] if 'param_name' in p]
 def links(job,kind,python=None):
  # Contrato do save legado (param_vinculos.preparar) sobre o catálogo projetado; texto vazio é sem vínculo.
  refs=job.get('param_vinculos_json')
  try:refs=json.loads(refs) if isinstance(refs,str) and refs else refs
  except ValueError:pass
  if refs:
   try:param_vinculos.normalizar(refs,kind,catalog,python)
   except ValueError as exc:return refs,[str(exc)]
  return refs,[]
 for node,job in zip(nodes,projection['etl_pipeline_job']):
  kind=node['type'];id=node['id'];cfg=node['configuration'];command=job.get('job_command');ssh=job.get('ssh_conn_id');issues=[]
  if not IDENT.fullmatch(id):issues.append('Identificador de etapa incompatível com Airflow')
  if ssh and connection_types.get(ssh)!='ssh':issues.append('Identificador SSH não encontrado')
  if job.get('mssql_conn_id') and job['mssql_conn_id'] not in mssql:issues.append('Identificador SQL não encontrado')
  if kind=='sql':issues+=jobs._validate_sql_node_conn(_json(job.get('sql_json')),mssql)
  elif kind=='python':
   python=_json(job.get('python_json'));refs,found=links(job,'python',python if isinstance(python,dict) else None);issues+=found
   issues+=jobs._validate_python_node(python,ssh,refs if isinstance(refs,dict) else None)
   # python_json NULL é o modo legado 'modulo': PythonModuleOperator roda no worker, sem SSH.
   if python is not None and not ssh:issues.append('Conexão SSH é obrigatória para Python')
  elif kind in {'datastage','shell'}:
   if not ssh:issues.append('Conexão SSH é obrigatória')
   if not isinstance(command,str) or not command.strip():issues.append('Comando da etapa obrigatório')
  elif kind=='storedproc':
   if not job.get('mssql_conn_id'):issues.append('Conexão SQL é obrigatória')
   if not isinstance(command,str) or not command.strip():issues.append('Procedimento obrigatório')
  elif kind=='http':
   if not jobs._valid_http_url(command):issues.append('URL HTTP inválida')
  elif kind=='decisao':issues+=jobs._validate_condition(_json(job.get('condition_json')),known,id,mssql)
  elif kind=='aguarde':
   issues+=jobs._validate_aguarde(_json(job.get('aguarde_json')))
   # Como no save do canvas legado, só conta entrada vinda de etapa do próprio fluxo.
   if not any(edge.get('target')==id and edge.get('source') in known for edge in definition.get('edges',[])):issues.append(jobs._AGUARDE_SEM_ENTRADA)
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
  # Python já conferiu acima. Os demais seguem o save legado, que roda antes da checagem de tipo e usa
  # o tipo atual da etapa: DataStage confere o catálogo (valor direto de mesmo nome tem prioridade na
  # corrida, não é conflito); qualquer outro tipo recusa vínculo não vazio, inclusive o que sobrou de troca de tipo.
  if kind!='python':issues+=links(job,kind)[1]
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
  q.execute('SELECT definition_json,layout_json,revision,read_only_json,estado,pipeline_name,base_version_id FROM dbo.etl_workspace_rascunho WHERE draft_id=?',(str(id),));row=q.fetchone()
  if row is None:raise HTTPException(404,'Rascunho não encontrado')
  if row[2]!=revision:raise HTTPException(409,'Revisão alterada; recarregue')
  definition=json.loads(row[0]);layout=json.loads(row[1]);existing=load_workspace_secrets(q,definition,{table:rows(q,table,row[5]) for table in TABLES},draft_id=id)
  errors,projection=validate_projection(definition,layout,existing,await connection_types(q),__import__('routers.jobs',fromlist=['_config_email_do_admin'])._config_email_do_admin(q))
  errors.extend(dependency_diagnostics(q,row[5],projection,existing))
  async with httpx.AsyncClient(base_url=AIRFLOW_URL,auth=(AIRFLOW_USER,AIRFLOW_PASSWORD),timeout=5,trust_env=False) as client:
   if not await airflow_idle(client,row[5]):errors.append({'nodeId':None,'field':'execution','code':'execution_active','message':'Pipeline possui execução ativa ou disparo pendente no Airflow'})
  errors +=[{'nodeId':None,'field':'definition','code':'read_only','message':message} for message in json.loads(row[3])]
  if row[4]!='ativo':errors.append({'nodeId':None,'field':'state','code':'draft_closed','message':'Rascunho encerrado'})
  if projection:
   for table,records in projection.items():
    allowed=columns(q,table)
    if table=='etl_job_lineage':errors.extend(lineage_column_diagnostics(q,records))
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
 if table=='etl_job_lineage':
  # Sem chave funcional: preservar inclusive duplicatas; identidade é técnica.
  allowed=columns(cur,table)
  cur.execute('DELETE FROM dbo.etl_job_lineage WHERE pipeline_name=?',(name,))
  for row in desired:
   values={key:(json.dumps(value,ensure_ascii=False) if isinstance(value,(dict,list)) else value) for key,value in row.items() if key in allowed and key not in LINEAGE_RUNTIME}
   fields=list(values)
   cur.execute('INSERT dbo.etl_job_lineage ('+','.join('['+key+']' for key in fields)+') VALUES ('+','.join('?' for _ in fields)+')',tuple(values[key] for key in fields))
  return
 allowed=columns(cur,table);keys=TABLES[table];present=rows(cur,table,name);desired_keys={tuple(str(r.get(k) or '') if k=='param_name' else str(r.get(k) or '').rstrip().casefold() for k in keys) for r in desired}
 for old in present:
  if tuple(str(old.get(k) or '') if k=='param_name' else str(old.get(k) or '').rstrip().casefold() for k in keys) not in desired_keys:
   cur.execute('DELETE FROM dbo.['+table+'] WHERE '+' AND '.join('['+k+']=?' for k in keys),tuple(old[k] for k in keys))
 for record in desired:
  record={k:v for k,v in record.items() if k in allowed and k not in RUNTIME};record=sql_notification_fields(cur,table,record);values={k:(json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v) for k,v in record.items()};key=tuple(values[k] for k in keys)
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
    existing=load_workspace_secrets(q,definition,{table:rows(q,table,op['name']) for table in TABLES},draft_id=op['draft']);errors,projection=validate_projection(definition,layout,existing,await connection_types(q),__import__('routers.jobs',fromlist=['_config_email_do_admin'])._config_email_do_admin(q))
    if any(set(record)-columns(q,table)-ignored_columns(q,table) for table,records in projection.items() for record in records) if projection else False:raise PublicationBlocked('unknown_column','Configuração contém campo não projetável')
    if projection and 'etl_job_lineage' in projection:errors.extend(lineage_column_diagnostics(q,projection['etl_job_lineage']))
    if errors:raise PublicationBlocked('publication_invalid','Configuração recusada na validação final; consulte os diagnósticos do rascunho')
    c.rollback();q.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE; SET XACT_ABORT ON')
    if dependency_changes(projection,existing):
     lock_result=q.execute("IF @@TRANCOUNT=0 BEGIN TRANSACTION; DECLARE @result INT; EXEC @result=sys.sp_getapplock @Resource=N'orquestra.workspace.dependencies',@LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=10000; SELECT @result").fetchone()
     if not lock_result or lock_result[0]<0:raise PublicationBlocked('dependency_busy','Outra publicação está atualizando dependências; tente novamente')
    renew_claim(q,id,token)
    q.execute('SELECT pending_operation_id FROM dbo.etl_workspace_pipeline WITH(UPDLOCK,HOLDLOCK) WHERE pipeline_name=?',(op['name'],));owner=q.fetchone()
    if not owner or str(owner[0]).lower()!=str(id).lower():raise PublicationBlocked('operation_conflict','Outra operação controla este pipeline')
    if q.execute('SELECT TOP(1) run_id FROM dbo.etl_workspace_execucao WHERE pipeline_name=? AND ativa=1',(op['name'],)).fetchone():raise PublicationBlocked('execution_active','Pipeline possui execução ativa')
    if q.execute("SELECT TOP(1) pipeline_name FROM dbo.etl_pipeline_execucao WITH(UPDLOCK,HOLDLOCK) WHERE pipeline_name=? AND status IN('EXECUTANDO','RUNNING','QUEUED','AGUARDANDO','AGUARDANDO_DEPENDENCIA')",(op['name'],)).fetchone():raise PublicationBlocked('execution_active','Pipeline possui execução ativa ou comando pendente')
    if active_hash(q,op['name'])!=op['expected']:raise PublicationBlocked('active_hash_conflict','Configuração ativa mudou; nenhuma projeção aplicada')
    q.execute("EXEC sp_set_session_context @key=N'workspace_operation',@value=?",(str(id),))
    dependency_errors=dependency_diagnostics(q,op['name'],projection,existing,lock=True)
    if dependency_errors:raise PublicationBlocked('dependency_invalid',dependency_errors[0]['message'])
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
    if 'etl_job_lineage' in projection:sync_rows(q,'etl_job_lineage',op['name'],projection['etl_job_lineage'])
    for (job,parameter),cipher in existing.get('_workspace_legacy_secrets',{}).items():
     q.execute('INSERT dbo.etl_workspace_segredo_legado(version_id,pipeline_name,job_name,param_name,ciphertext) SELECT ?,?,?,?,? WHERE NOT EXISTS(SELECT 1 FROM dbo.etl_workspace_segredo_legado WHERE version_id=? AND param_name=? AND (job_name=? OR (job_name IS NULL AND ? IS NULL)))',(str(op['version']),op['name'],job or None,parameter,cipher,str(op['version']),parameter,job or None,job or None))
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


def lineage_column_diagnostics(cur,records):
 """Valida contra o schema real; nunca truncar ou perder metadados importados."""
 cur.execute("SELECT c.name,t.name,c.max_length,c.is_nullable,c.is_identity,c.is_computed,c.default_object_id FROM sys.columns c JOIN sys.types t ON t.user_type_id=c.user_type_id WHERE c.object_id=OBJECT_ID('dbo.etl_job_lineage')")
 schema=list(cur.fetchall());errors=[]
 if not schema:return [{'nodeId':None,'field':'etl_job_lineage','code':'lineage_schema','message':'Lineage indisponível; aplique as migrations de lineage'}]
 for row in records:
  for name,kind,width,nullable,identity,computed,default in schema:
   if identity or computed or name in LINEAGE_RUNTIME:continue
   value=row.get(name)
   invalid=value is None and not nullable and not default
   if value is not None and kind in ('nvarchar','nchar','varchar','char'):
    if not isinstance(value,str):invalid=True
    else:
     try:size=len(value.encode('utf-16-le')) if kind.startswith('n') else len(value.encode('cp1252'))
     except UnicodeError:invalid=True
     else:invalid=width!=-1 and size>width
   if invalid:errors.append({'nodeId':row.get('job_name'),'field':'etl_job_lineage.'+name,'code':'lineage_value','message':'Campo de lineage inválido ou maior que a capacidade do cadastro: '+name})
 return errors[:500]
