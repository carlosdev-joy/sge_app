from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter,Body,Depends,Header,HTTPException
from deps import require_perm,PERM_EDITAR
from services.workspace_publication import ENABLED,validate_draft
router=APIRouter()

@router.post('/workspace-adapter/valida-arquivo/preview')
def preview_workspace_file(body:dict=Body(default={}),actor:dict=Depends(require_perm(PERM_EDITAR))):
 """Prévia estática do grafo local: não lê cadastro, SSH, arquivo ou segredo."""
 import json
 from services import valida_arquivo as va
 if not ENABLED():raise HTTPException(503,'Publicação do workspace desabilitada')
 if not {'tela_pipelines','tela_jobs'}.issubset(actor.get('permissoes',[])):raise HTTPException(403,'Permissão de consulta necessária')
 try:size=len(json.dumps(body,ensure_ascii=False).encode('utf-8'))
 except (UnicodeError,RecursionError,ValueError,TypeError) as error:raise HTTPException(422,'Texto ou estrutura da prévia inválidos') from error
 if size>1_000_000:raise HTTPException(422,'Prévia excede o tamanho permitido')
 nodes=body.get('nodes');catalog=body.get('catalog');task=body.get('taskId')
 if not isinstance(nodes,list) or not 1<=len(nodes)<=1000 or not isinstance(catalog,list) or len(catalog)>1000 or not isinstance(task,str):raise HTTPException(422,'Grafo e catálogo do rascunho obrigatórios')
 safe_catalog=[]
 for row in catalog:
  if not isinstance(row,dict) or row.get('param_type') not in ('String','Pathname') or row.get('param_source')!='fixo' or 'secretReference' in row:raise HTTPException(422,'Prévia aceita apenas diretórios fixos sem segredo')
  safe_catalog.append({key:row.get(key) for key in ('param_name','param_type','param_source','param_value')})
 try:
  config=va.normalizar(body.get('config'),safe_catalog)
  return va.impacto(config,nodes,task,safe_catalog)
 except (ValueError,TypeError,KeyError,AttributeError) as error:
  raise HTTPException(422,'Configuração ou grafo da prévia inválidos: '+str(error)) from error

@router.post('/workspace-adapter/validate/{draft_id}')
async def validate_workspace_draft(draft_id:UUID,body:dict=Body(default={}),actor:dict=Depends(require_perm(PERM_EDITAR)),authorization:str|None=Header(default=None)):
 if not ENABLED():raise HTTPException(503,'Publicação do workspace desabilitada')
 if not authorization or not authorization.startswith('Bearer '):raise HTTPException(401,'Sessão Bearer necessária')
 if not {'tela_pipelines','tela_jobs'}.issubset(actor.get('permissoes',[])):raise HTTPException(403,'Permissão de consulta necessária')
 revision=body.get('expectedRevision')
 if type(revision)is not int or revision<1:raise HTTPException(422,'Revisão obrigatória')
 return await validate_draft(draft_id,revision,actor)

@router.post('/workspace-adapter/secrets/{draft_id}', status_code=201)
def protect_workspace_parameter(draft_id:UUID,body:dict=Body(default={}),actor:dict=Depends(require_perm(PERM_EDITAR)),authorization:str|None=Header(default=None)):
 if not ENABLED():raise HTTPException(503,'Workspace desabilitado')
 from services.workspace_secrets import store_secret
 return store_secret(draft_id,body,actor,authorization)
