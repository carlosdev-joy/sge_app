import type { WorkspaceDefinition, WorkspaceLayout } from './workspace'

/** Layout visual por dependências. Só Organizar persiste o novo desenho. */
export function arrangeWorkspace(definition:WorkspaceDefinition, layout:WorkspaceLayout, rowGap=120):WorkspaceLayout {
 const ids=new Set(definition.nodes.map(n=>n.id));const incoming=new Map([...ids].map(id=>[id,0]));const next=new Map([...ids].map(id=>[id,[] as string[]]));const level=new Map([...ids].map(id=>[id,0]))
 for(const e of definition.edges)if(ids.has(e.source)&&ids.has(e.target)){incoming.set(e.target,incoming.get(e.target)!+1);next.get(e.source)!.push(e.target)}
 const queue=[...ids].filter(id=>!incoming.get(id));const visited=new Set<string>()
 for(let i=0;i<queue.length;i++){const id=queue[i];visited.add(id);for(const target of next.get(id)!){level.set(target,Math.max(level.get(target)!,level.get(id)!+1));incoming.set(target,incoming.get(target)!-1);if(!incoming.get(target))queue.push(target)}}
 // Ciclos/inconsistências continuam diagnosticáveis; nunca ocultar seus nós.
 let tail=Math.max(0,...level.values())+1;for(const id of ids)if(!visited.has(id))level.set(id,tail++)
 const columns=new Map<number,string[]>();for(const id of ids){const n=level.get(id)!;columns.set(n,[...(columns.get(n)??[]),id])}
 const tallest=Math.max(1,...[...columns.values()].map(c=>c.length));const positions={...layout.nodes}
 for(const [column,rows] of columns)rows.forEach((id,index)=>{positions[id]={...positions[id],x:100+column*210,y:80+(tallest-rows.length)*rowGap/2+index*rowGap}})
 return {...layout,nodes:positions}
}
