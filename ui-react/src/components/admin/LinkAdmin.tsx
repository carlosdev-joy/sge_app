// Migalha "Admin › Grupo › Aba" de outras telas, virada link real para o
// endereço da aba (F4 de docs/spec-admin-reestruturacao.md). O texto sai do
// registro (rotuloAdmin): aba renomeada ou movida de grupo muda aqui sozinha.
//
// Quem não pode abrir o Admin (sem `tela_admin`) vê só o texto: um link que o
// guard de rota devolveria para a tela inicial é um beco sem saída, e a frase
// continua dizendo a quem pedir ("o administrador cadastra em …").
//
// `novaAba`: para telas de EDIÇÃO sem guarda de alterações não salvas (painel
// do nó no editor de fluxo, formulário de pipeline, editor de arquivo). Ali
// seguir o link na mesma aba descartaria o que a pessoa está editando.
import { Link } from 'react-router-dom'
import { ExternalLink } from 'lucide-react'
import { useAuthStore } from '../../store/auth'
import { canAccess } from '../../lib/nav'
import { caminhoDaAba, resolverAba, rotuloAdmin, type GrupoAdminId } from '../../lib/adminNav'

interface LinkAdminProps {
  grupo: GrupoAdminId
  aba: string
  /** bloco dentro da aba ("Modelos"), só no texto — a aba não tem âncora por bloco */
  secao?: string
  novaAba?: boolean
  className?: string
}

const CLASSE_LINK = 'font-medium text-blue-700 underline underline-offset-2 decoration-blue-700/40 hover:decoration-blue-700 '
  + 'dark:text-blue-300 dark:decoration-blue-300/40 dark:hover:decoration-blue-300 '
  + 'rounded-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-[#1A5FA8] focus-visible:ring-offset-1'

export function LinkAdmin({ grupo, aba, secao, novaAba = false, className = '' }: LinkAdminProps) {
  const perms = useAuthStore((s) => s.user?.permissoes) ?? []
  const destino = resolverAba(grupo, aba)
  const texto = rotuloAdmin(grupo, aba, secao)
  if (!destino || !canAccess('tela_admin', perms)) return <span className={className}>{texto}</span>

  if (novaAba) {
    // `relative`: o sr-only é absolute e precisa de um ancestral posicionado
    // (tests/test_casca_rolagem_por_foco.py).
    return (
      <Link to={caminhoDaAba(destino)} target="_blank" rel="noopener noreferrer"
        className={`relative ${CLASSE_LINK} ${className}`} data-link-admin={caminhoDaAba(destino)}>
        {texto}
        <ExternalLink size={11} className="inline-block ml-0.5 -mt-0.5 align-middle" aria-hidden="true" />
        <span className="sr-only"> (abre em nova aba)</span>
      </Link>
    )
  }
  return (
    <Link to={caminhoDaAba(destino)} className={`${CLASSE_LINK} ${className}`} data-link-admin={caminhoDaAba(destino)}>
      {texto}
    </Link>
  )
}
