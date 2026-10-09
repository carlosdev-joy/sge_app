import { Bell, Database, FileCheck2, FileCode2, GitBranch, Globe, Hourglass, Mail, Table2, Terminal } from 'lucide-react'
export const WORKSPACE_TYPES = [
 ['datastage','DataStage',Database],['sql','SQL',Table2],['python','Python',FileCode2],['shell','Shell',Terminal],['storedproc','Stored Proc',Database],['http','HTTP',Globe],['decisao','Decisão',GitBranch],['aguarde','Aguarde',Hourglass],['notificacao','Notificação',Bell],['email','E-mail',Mail],['valida_arquivo','Valida Arquivo',FileCheck2],
] as const
export function typeLabel(type:string):string { return WORKSPACE_TYPES.find(t=>t[0]===type)?.[1] ?? type }
