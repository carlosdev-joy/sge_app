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


@router.post('/workspace-adapter/maestro/{draft_id}')
async def workspace_maestro(draft_id:UUID,body:dict=Body(default={}),actor:dict=Depends(require_perm(PERM_EDITAR)),authorization:str|None=Header(default=None)):
 if not ENABLED():raise HTTPException(503,'Workspace desabilitado')
 from services.workspace_advisory import guarded_draft,safe_editor,draft_maestro_context,protected_content
 from routers.maestro import _validar_corpo,conversar_contextual
 definition=guarded_draft(draft_id,body,actor,authorization)
 conversation,messages,context,reference=_validar_corpo(body)
 if protected_content(messages):raise HTTPException(422,'Remova credenciais da conversa do Maestro')
 safe_context={key:context.get(key) for key in ('nivel','job_name','referencia')}
 safe_context['pipeline_name']=definition['identity']['pipelineName']
 safe_context['params']=safe_editor(context.get('params') or [])
 trusted=draft_maestro_context(definition,safe_context)
 if safe_context['nivel']=='etapa' and 'draftDefaults' in body:trusted['defaults']=safe_editor(body['draftDefaults'])
 response=await conversar_contextual({'conversa_id':conversation,'mensagens':messages,'contexto':safe_context},actor,trusted)
 guarded_draft(draft_id,body,actor,authorization)
 # Credencial inventada pelo provedor também não entra na proposta/UI.
 import json
 if any(str(row.get('param_type') or '').lower()=='encrypted' for row in (response.get('proposta') or {}).get('params',[])):raise HTTPException(422,'Parâmetros protegidos devem ser configurados pelo formulário de valor protegido')
 if protected_content(response):raise HTTPException(503,'Resposta do Maestro contém conteúdo protegido; tente novamente')
 return response


@router.post('/workspace-adapter/lineage/{draft_id}/dsx-preview')
async def workspace_lineage_dsx(draft_id:UUID,body:dict=Body(default={}),actor:dict=Depends(require_perm(PERM_EDITAR)),authorization:str|None=Header(default=None)):
 if not ENABLED():raise HTTPException(503,'Workspace desabilitado')
 from services.workspace_advisory import guarded_draft,protected_content,source_rows
 from routers.lineage import lineage_extract_dsx
 definition=guarded_draft(draft_id,body,actor,authorization)
 if definition.get('metadata',{}).get('workspaceLineageVersion')!=1:raise HTTPException(409,'Reimporte o pipeline para capturar lineage no rascunho')
 if not any(node.get('id')==body.get('jobName') and node.get('type')=='datastage' for node in definition.get('nodes',[])):raise HTTPException(422,'Etapa DataStage ausente da revisão salva; salve o rascunho primeiro')
 project=body.get('projectName');job=body.get('dataStageJob')
 if not isinstance(project,str) or not project or len(project)>100 or not isinstance(job,str) or not job or len(job)>200:raise HTTPException(422,'Informe projeto e job DataStage válidos')
 try:result=await lineage_extract_dsx({'project_name':project,'job_name':job},actor)
 except HTTPException as error:
  if error.status_code>=500:raise HTTPException(503,'Extrator DSX indisponível; confira os arquivos e a configuração') from None
  raise HTTPException(422,'Projeto ou job DSX indisponível; confira a origem e tente novamente') from None
 guarded_draft(draft_id,body,actor,authorization)
 if protected_content(result):raise HTTPException(422,'A extração contém conteúdo protegido e não pode ser aplicada')
 return {'rows':source_rows(result.get('dados') or [],'dsx_auto'),'source':result.get('dsx_file')}


@router.post('/workspace-adapter/lineage/{draft_id}/isx-preview')
async def workspace_lineage_isx(draft_id:UUID,body:dict=Body(default={}),actor:dict=Depends(require_perm(PERM_EDITAR)),authorization:str|None=Header(default=None)):
 if not ENABLED():raise HTTPException(503,'Workspace desabilitado')
 from services.workspace_advisory import guarded_draft,source_rows
 from services import lineage_isx as svc
 from routers.lineage_isx import _no_executor,_TETO_EXTRAIR_S
 definition=guarded_draft(draft_id,body,actor,authorization)
 if definition.get('metadata',{}).get('workspaceLineageVersion')!=1:raise HTTPException(409,'Reimporte o pipeline para capturar lineage no rascunho')
 if not any(node.get('id')==body.get('jobName') and node.get('type')=='datastage' for node in definition.get('nodes',[])):raise HTTPException(422,'Etapa DataStage ausente da revisão salva; salve o rascunho primeiro')
 project=body.get('projectName');job=body.get('dataStageJob')
 if not isinstance(project,str) or not project or len(project)>50 or not isinstance(job,str) or not job or len(job)>200:raise HTTPException(422,'Informe projeto e job DataStage válidos')
 try:
  # Mapa/config existentes; nenhum cabeçalho/cache ativo é consultado ou gravado.
  with svc.banco() as (_connection,cur):mapping=svc.mapa_tipos(cur)
  cfg=svc.config()
  _meta,result,_cache=await _no_executor(svc.extrair,cfg,project,job,None,False,True,mapping,teto=_TETO_EXTRAIR_S)
 except Exception as error:
  if isinstance(error,HTTPException) and error.status_code==504:raise
  raise HTTPException(503,'Extrator ISX indisponível; confira a configuração DataStage e tente novamente') from None
 guarded_draft(draft_id,body,actor,authorization)
 return {'rows':source_rows(result.get('stages') or [],'isx_auto'),'source':'DataStage ISX'}
