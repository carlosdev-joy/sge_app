from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter,Body,Depends,Header,HTTPException
from deps import require_perm,PERM_EDITAR
from services.workspace_publication import ENABLED,validate_draft
router=APIRouter()
@router.post('/workspace-adapter/validate/{draft_id}')
async def validate_workspace_draft(draft_id:UUID,body:dict=Body(default={}),actor:dict=Depends(require_perm(PERM_EDITAR)),authorization:str|None=Header(default=None)):
 if not ENABLED():raise HTTPException(503,'Publicação do workspace desabilitada')
 if not authorization or not authorization.startswith('Bearer '):raise HTTPException(401,'Sessão Bearer necessária')
 if not {'tela_pipelines','tela_jobs'}.issubset(actor.get('permissoes',[])):raise HTTPException(403,'Permissão de consulta necessária')
 revision=body.get('expectedRevision')
 if type(revision)is not int or revision<1:raise HTTPException(422,'Revisão obrigatória')
 return await validate_draft(draft_id,revision,actor)
