// Tipos e helpers compartilhados pelas três abas do grupo Acesso (Usuários ·
// Perfis e Permissões · Roles do Airflow), que até a F3 de
// docs/spec-admin-reestruturacao.md eram uma aba só (UsuariosTab).
//
// As três leem a MESMA query `['admin-perfis']` (Usuários: select de perfil e
// o que o modal de extras marca como "do perfil"; Roles: select de perfil;
// Perfis: a matriz). Cache compartilhado pelo react-query: salvar um perfil em
// Perfis invalida essa chave e as outras duas abas relêem ao montar — mesmo
// comportamento de quando as três viviam no mesmo componente.
import { adminPost } from './comum'

export interface PerfilRow { perfil_nome: string; descricao?: string; permissoes: string[] }

export const Q_ADMIN_PERFIS = ['admin-perfis'] as const

export const buscarPerfis = () => adminPost<{ perfis: PerfilRow[] }>('perfil_list')

/** Nomes para os selects de perfil; sem a lista (ainda carregando ou erro), os três de fábrica. */
export function nomesDePerfis(perfis: PerfilRow[]): string[] {
  return perfis.length ? perfis.map(p => p.perfil_nome) : ['admin', 'operador', 'consulta']
}
