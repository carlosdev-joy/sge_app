"""Consulta contextual do draft; não escreve cadastro, revisão, vault ou execução."""
from __future__ import annotations
import hashlib
import json
import re
from fastapi import HTTPException
from db import get_db_conn

SENSITIVE=re.compile(r'(?i)(\b(?:password|passwd|pwd|senha|client_secret|access_token|refresh_token|api_key|apikey|token|secret|authorization|connection_string|connectionstring)(?:\\?["\'])*\s*[=:]\s*[^\s;]+|\b(?:Bearer|Basic)\s+[A-Za-z0-9+/=_-]{8,}|gAAAA[A-Za-z0-9_=-]+)')
SECRET_KEY=re.compile(r'(?i)^(password|passwd|pwd|senha|secret|client_secret|access_token|refresh_token|token|authorization|api_key|apikey|connection_string|connectionstring)$')


def protected_content(value):
 if isinstance(value,dict):return any((SECRET_KEY.fullmatch(key) and item not in (None,'','***')) or protected_content(item) for key,item in value.items())
 if isinstance(value,list):return any(protected_content(item) for item in value)
 if isinstance(value,str):
  if SENSITIVE.search(value):return True
  if value.lstrip().startswith(('{','[')):
   try:return protected_content(json.loads(value))
   except (ValueError,TypeError):pass
   except RecursionError:return True
 return False

def guarded_draft(draft_id,body,actor,authorization):
 revision,fence=body.get('expectedRevision'),body.get('fence')
 if type(revision)is not int or revision<1 or type(fence)is not int or fence<1:raise HTTPException(422,'Revisão e posse de edição obrigatórias')
 if not authorization or not authorization.startswith('Bearer ') or not authorization[7:]:raise HTTPException(401,'Sessão Bearer necessária')
 if not {'tela_pipelines','tela_jobs','acao_editar'}.issubset(actor.get('permissoes',[])):raise HTTPException(403,'Permissão de edição necessária')
 try:
  if len(json.dumps(body,ensure_ascii=False).encode('utf-8'))>1_000_000:raise HTTPException(422,'Consulta excede o tamanho permitido')
 except (UnicodeError,TypeError,ValueError,RecursionError):raise HTTPException(422,'Texto ou estrutura da consulta inválidos') from None
 session=hashlib.sha256(authorization[7:].encode('utf-8')).hexdigest()
 try:c=get_db_conn();q=c.cursor()
 except Exception:raise HTTPException(503,'Consulta do rascunho indisponível') from None
 try:
  q.execute('SET XACT_ABORT ON; SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
  q.execute('SELECT pipeline_name,definition_json,revision,estado,read_only_json FROM dbo.etl_workspace_rascunho WITH(UPDLOCK,HOLDLOCK) WHERE draft_id=?',str(draft_id));draft=q.fetchone()
  if not draft:raise HTTPException(404,'Rascunho não encontrado')
  q.execute('SELECT matricula FROM dbo.etl_sessao WHERE token_hash=? AND expira_em>GETDATE() AND matricula=?',session,actor.get('matricula'))
  if not q.fetchone():raise HTTPException(401,'Sessão expirada ou inválida')
  if draft[2]!=revision:raise HTTPException(409,'Revisão alterada; recarregue')
  if draft[3]!='ativo' or json.loads(draft[4]):raise HTTPException(409,'Rascunho disponível somente para consulta')
  q.execute("SELECT TOP(1) o.operation_id FROM dbo.etl_workspace_publicacao o LEFT JOIN dbo.etl_workspace_pipeline p ON p.pending_operation_id=o.operation_id WHERE o.draft_id=? AND (o.estado NOT IN('publicado','erro') OR p.pipeline_name IS NOT NULL)",str(draft_id))
  if q.fetchone():raise HTTPException(409,'Publicação em andamento; aguarde a confirmação')
  q.execute('SELECT holder_user,holder_session_hash,fence,CASE WHEN expires_at>SYSUTCDATETIME() THEN 1 ELSE 0 END FROM dbo.etl_workspace_lease WITH(UPDLOCK,HOLDLOCK) WHERE draft_id=?',str(draft_id));lease=q.fetchone()
  if not lease or lease[0]!=actor.get('matricula') or lease[1]!=session or lease[2]!=fence or not lease[3]:raise HTTPException(409,'Posse de edição expirada ou substituída')
  definition=json.loads(draft[1])
  if definition.get('schemaVersion')!=1:raise HTTPException(409,'Configuração somente para consulta')
  return definition
 except HTTPException:raise
 except Exception:raise HTTPException(503,'Consulta do rascunho indisponível') from None
 finally:c.rollback();q.close();c.close()


def safe_editor(rows):
 from services import maestro
 if not isinstance(rows,list) or len(rows)>maestro.MAX_PARAMS_EDITOR:raise HTTPException(422,'Lista de parâmetros inválida ou maior que o limite do Maestro')
 if any(not isinstance(row,dict) for row in rows):raise HTTPException(422,'Parâmetro inválido')
 clean=[]
 for row in rows:
  if str(row.get('param_type') or '').lower()=='encrypted' or 'secretReference' in row:continue
  selected={key:value for key,value in row.items() if key in maestro._COLS}
  if any(value is not None and type(value) not in (str,int,float,bool) for value in selected.values()):raise HTTPException(422,'Campo de parâmetro inválido')
  if protected_content(selected):raise HTTPException(422,'Remova credenciais do contexto do Maestro')
  clean.append(selected)
 return maestro.sanear_editor(clean)


def draft_maestro_context(definition,context):
 from services import maestro
 pipeline=definition['identity']['pipelineName'];job=context.get('job_name');level=context.get('nivel','etapa')
 nodes=definition.get('nodes') or []
 if level=='etapa' and not any(node.get('id')==job and node.get('type')=='datastage' for node in nodes):raise HTTPException(422,'Etapa DataStage ausente da revisão salva; salve o rascunho primeiro')
 # Os parâmetros configurados não comprovam declaração ISX: desconhecido é explícito.
 unavailable={'disponivel':False,'status':None,'extracted_at':None,'itens':[]}
 declarations=unavailable if level=='etapa' else {'nivel':'pipeline','jobs':[{'job_name':node['id'],**unavailable} for node in nodes if node.get('type')=='datastage'][:maestro.MAX_JOBS_PIPELINE],'truncados':max(0,sum(node.get('type')=='datastage' for node in nodes)-maestro.MAX_JOBS_PIPELINE)}
 defaults=definition.get('metadata',{}).get('legacyTables',{}).get('etl_pipeline_param',[])
 return {'pipeline':pipeline,'job':job if level=='etapa' else None,'declarados':declarations,'defaults':safe_editor(defaults) if level=='etapa' else []}


def source_rows(data,method):
 """Conversão sem persistência nem truncamento do extrator para linhas do draft."""
 if not isinstance(data,list) or len(data)>5000 or any(not isinstance(row,dict) for row in data):raise HTTPException(422,'Extração de lineage inválida ou maior que o limite')
 rows=[]
 for stage in data:
  row={key:stage.get(key) for key in ('direction','object_type','object_name','stage_name','stage_type_raw','database_name','sql_expression','file_path','dsx_source_file','apt_code') if key in stage}
  row['direction']=row.get('direction') or 'transformacao'
  row['object_name']=row.get('object_name') or row.get('file_path') or row.get('stage_name') or '?'
  row['extraction_method']=method
  if method=='isx_auto':
   row['stage_internal_id']=stage.get('internal_id')
   from services.lineage_isx import _object_name
   row['object_name']=stage.get('object_name') or _object_name(stage)
  for source,target in (('output_columns','columns_json'),('columns_detail','columns_json'),('input_columns','input_columns_json'),('expressions','expressions_json')):
   if source in stage:row[target]=json.dumps(stage[source],ensure_ascii=False)
  if 'columns_json' not in row and 'columns' in stage:row['columns_json']=json.dumps(stage['columns'],ensure_ascii=False)
  if protected_content(row):raise HTTPException(422,'A extração contém conteúdo protegido e não pode ser aplicada')
  rows.append(row)
 return rows
