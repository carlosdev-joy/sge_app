"""Valores protegidos imutáveis fora de snapshots. Nenhuma leitura resolve texto claro."""
from __future__ import annotations
import hashlib
import json
import re
import uuid
from fastapi import HTTPException
from db import get_db_conn
from services.conn_crypto import encrypt_password

PARAMETER = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?$')
MIGRATION = 'Valores protegidos indisponíveis; aplique a migration 157'

def secret_request(body):
 if not isinstance(body, dict):raise HTTPException(422, 'Dados do valor protegido inválidos')
 revision, fence = body.get('expectedRevision'), body.get('fence')
 name, job, value = body.get('parameterName'), body.get('jobName'), body.get('value')
 if type(revision) is not int or revision < 1 or type(fence) is not int or fence < 1:raise HTTPException(422, 'Revisão e posse de edição obrigatórias')
 if not isinstance(name, str) or len(name) > 128 or not PARAMETER.fullmatch(name):raise HTTPException(422, 'Nome de parâmetro inválido')
 if job is not None and (not isinstance(job, str) or not job or len(job) > 200):raise HTTPException(422, 'Etapa inválida')
 try:valid = isinstance(value, str) and 0 < len(value.encode('utf-8')) <= 16000 and value != '***'
 except UnicodeError:valid = False
 if not valid:raise HTTPException(422, 'Informe um valor protegido de até 16000 bytes')
 return revision, fence, name, job, value

def store_secret(draft_id, body, actor, authorization):
 revision, fence, name, job, value = secret_request(body)
 if not authorization or not authorization.startswith('Bearer ') or not authorization[7:]:raise HTTPException(401, 'Sessão Bearer necessária')
 if not {'tela_pipelines','tela_jobs','acao_editar'}.issubset(actor.get('permissoes', [])):raise HTTPException(403, 'Permissão de edição necessária')
 try:cipher = encrypt_password(value)
 except Exception:raise HTTPException(503, 'Armazenamento protegido indisponível') from None
 session = hashlib.sha256(authorization[7:].encode('utf-8')).hexdigest()
 try:c = get_db_conn();q = c.cursor()
 except Exception:raise HTTPException(503, 'Armazenamento protegido indisponível') from None
 try:
  q.execute('SET XACT_ABORT ON; SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
  q.execute("SELECT OBJECT_ID('dbo.etl_workspace_segredo','U')")
  if not q.fetchone()[0]:raise HTTPException(503, MIGRATION)
  # Mesma ordem do save .NET: rascunho -> sessão -> publicação -> lease.
  q.execute('SELECT pipeline_name,definition_json,revision,estado,read_only_json FROM dbo.etl_workspace_rascunho WITH(UPDLOCK,HOLDLOCK) WHERE draft_id=?', str(draft_id));draft = q.fetchone()
  if not draft:raise HTTPException(404, 'Rascunho não encontrado')
  q.execute('SELECT matricula FROM dbo.etl_sessao WHERE token_hash=? AND expira_em>GETDATE() AND matricula=?', session, actor.get('matricula'))
  if not q.fetchone():raise HTTPException(401, 'Sessão expirada ou inválida')
  if draft[2] != revision:raise HTTPException(409, 'Revisão alterada; recarregue')
  if draft[3] != 'ativo' or json.loads(draft[4]):raise HTTPException(409, 'Rascunho indisponível para edição')
  q.execute("SELECT TOP(1) operation_id FROM dbo.etl_workspace_publicacao WHERE draft_id=? AND estado NOT IN('publicado','erro')", str(draft_id))
  if q.fetchone():raise HTTPException(409, 'Publicação em andamento')
  q.execute('SELECT holder_user,holder_session_hash,fence,CASE WHEN expires_at>SYSUTCDATETIME() THEN 1 ELSE 0 END FROM dbo.etl_workspace_lease WITH(UPDLOCK,HOLDLOCK) WHERE draft_id=?', str(draft_id));lease = q.fetchone()
  if not lease or lease[0] != actor.get('matricula') or lease[1] != session or lease[2] != fence or not lease[3]:raise HTTPException(409, 'Posse de edição expirada ou substituída')
  definition = json.loads(draft[1]);nodes = definition.get('nodes', [])
  if definition.get('schemaVersion') != 1 or any(n.get('type') not in {'datastage','sql','python','shell','storedproc','http','decisao','aguarde','notificacao','email','valida_arquivo'} for n in nodes):raise HTTPException(409, 'Configuração somente para consulta')
  if job is not None and not any(n.get('id') == job and n.get('type') == 'datastage' for n in nodes):raise HTTPException(422, 'Etapa não pertence à revisão salva; salve o rascunho primeiro')
  id = str(uuid.uuid4())
  q.execute('INSERT dbo.etl_workspace_segredo(secret_id,pipeline_name,job_name,param_name,ciphertext,criado_por,draft_id) VALUES(?,?,?,?,?,?,?)', id, draft[0], job, name, cipher, actor.get('matricula'), str(draft_id))
  q.execute("INSERT dbo.etl_workspace_evento(entidade_id,ator,acao,revision) VALUES(?,?,'proteger_parametro',?)", str(draft_id), actor.get('matricula'), revision)
  c.commit()
  return {'secretReference': {'secretId': id, 'pipelineName': draft[0], 'jobName': job, 'parameterName': name}}
 except HTTPException:
  c.rollback();raise
 except Exception:
  c.rollback();raise HTTPException(503, 'Armazenamento protegido indisponível') from None
 finally:c.close()
