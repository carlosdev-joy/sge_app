import { cloneFlow, connectWorkspace, object, text, type WorkspaceDefinition, type WorkspaceNode, type WorkspaceEdge } from './workspace'
export function decisionCondition(node:WorkspaceNode) {
 const value=object(node.configuration.legacyJob).condition_json
 try{return typeof value==='string'?object(JSON.parse(value)):object(value)}catch{return {}}
}
export function decisionHandles(node:WorkspaceNode):string[] {
 const condition=decisionCondition(node)
 return Array.isArray(condition.casos)?[...condition.casos.map(c=>'caso:'+text(object(c).nome)),'senao']:['sim','nao']
}
export function decisionEdgeHandle(node:WorkspaceNode,edge:WorkspaceEdge):string|undefined {
 const condition=decisionCondition(node);const valid=decisionHandles(node)
 if(typeof edge.branch==='string'&&valid.includes(edge.branch))return edge.branch
 const matches=Array.isArray(condition.casos)?[...condition.casos.filter(c=>Array.isArray(object(c).ramo)&&(object(c).ramo as unknown[]).includes(edge.target)).map(c=>'caso:'+text(object(c).nome)),...(Array.isArray(condition.ramo_senao)&&condition.ramo_senao.includes(edge.target)?['senao']:[])]:[...(Array.isArray(condition.ramo_verdadeiro)&&condition.ramo_verdadeiro.includes(edge.target)?['sim']:[]),...(Array.isArray(condition.ramo_falso)&&condition.ramo_falso.includes(edge.target)?['nao']:[])]
 return matches.length===1?matches[0]:undefined
}
export function connectWorkspaceDecision(definition:WorkspaceDefinition,source:string,target:string,handle:string|null|undefined):WorkspaceDefinition {
 const node=definition.nodes.find(n=>n.id===source)
 if(node?.type!=='decisao')return connectWorkspace(definition,source,target)
 const raw=object(node.configuration.legacyJob).condition_json
 if(typeof raw==='string'&&raw){try{JSON.parse(raw)}catch{throw new Error('Corrija a configuração da decisão antes de conectar.')}}
 if(!handle||!decisionHandles(node).includes(handle))throw new Error('Selecione uma saída de decisão válida.')
 const existing=definition.edges.find(e=>e.source===source&&e.target===target)
 if(existing){if(decisionEdgeHandle(node,existing)===handle)return definition;throw new Error('Remova a ligação existente antes de trocar seu ramo.')}
 const next=connectWorkspace(definition,source,target);const condition=cloneFlow(decisionCondition(node))
 if(handle.startsWith('caso:'))condition.casos=(condition.casos as unknown[]).map(c=>{const row=object(c);return text(row.nome)===handle.slice(5)?{...row,ramo:[...(Array.isArray(row.ramo)?row.ramo:[]),target]}:row})
 else {const key=handle==='sim'?'ramo_verdadeiro':handle==='nao'?'ramo_falso':'ramo_senao';condition[key]=[...(Array.isArray(condition[key])?condition[key]:[]),target]}
 return {...next,edges:next.edges.map(e=>e.source===source&&e.target===target?{...e,branch:handle}:e),nodes:next.nodes.map(n=>n.id===source?{...n,configuration:{...n.configuration,legacyJob:{...object(n.configuration.legacyJob),condition_json:JSON.stringify(condition)}}}:n)}
}
export function removeWorkspaceEdges(definition:WorkspaceDefinition,removed:Set<string>):WorkspaceDefinition {
 const deleted=definition.edges.filter((_,index)=>removed.has(String(index)))
 const nodes=definition.nodes.map(node=>{const targets=new Set(deleted.filter(e=>e.source===node.id).map(e=>e.target));if(node.type!=='decisao'||!targets.size)return node
  const condition=cloneFlow(decisionCondition(node));const strip=(value:unknown)=>Array.isArray(value)?value.filter(id=>!targets.has(String(id))):value
  for(const key of ['ramo_verdadeiro','ramo_falso','ramo_senao'])if(key in condition)condition[key]=strip(condition[key])
  if(Array.isArray(condition.casos))condition.casos=condition.casos.map(c=>({...object(c),ramo:strip(object(c).ramo)}))
  return {...node,configuration:{...node.configuration,legacyJob:{...object(node.configuration.legacyJob),condition_json:JSON.stringify(condition)}}}
 })
 return {...definition,nodes,edges:definition.edges.filter((_,index)=>!removed.has(String(index)))}
}
