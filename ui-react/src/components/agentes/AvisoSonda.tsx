// O aviso sobre o cadastro do usuário no gateway de IA (F3.3 da spec).
//
// A distinção que este componente PRENDE: só `sem_cadastro` mostra o texto
// de "peça seu cadastro" (editável em Admin › Agentes). `gateway_indisponivel`
// é um problema de rede/infra — mandar o usuário abrir um chamado de cadastro
// ali seria empurrá-lo para uma fila errada por um problema que não é dele.
// Os dois textos moram em `lib/agentes.ts` (SONDA), e o critério 3 da F3 é
// verificado por teste sobre este fonte.
import type { EstadoSonda } from '../../lib/agentes'
import { SONDA } from '../../lib/agentes'

const TOM: Record<'ok' | 'aviso' | 'erro', { caixa: string; titulo: string }> = {
  // Sem cor fixa de fundo: tokens + um acento lateral por tom, que tem par
  // claro/escuro. Nada de `bg-yellow-50` sozinho (ilegível no escuro).
  ok: { caixa: 'border-l-4 border-l-emerald-500 dark:border-l-emerald-400', titulo: 'text-emerald-700 dark:text-emerald-300' },
  aviso: { caixa: 'border-l-4 border-l-amber-500 dark:border-l-amber-400', titulo: 'text-amber-700 dark:text-amber-300' },
  erro: { caixa: 'border-l-4 border-l-red-500 dark:border-l-red-400', titulo: 'text-red-700 dark:text-red-300' },
}

interface Props {
  estado: EstadoSonda
  /** `agentes_cadastro_texto`, só preenchido quando `estado === 'sem_cadastro'`. */
  cadastroTexto?: string | null
  onTentarDeNovo?: () => void
  recarregando?: boolean
}

export function AvisoSonda({ estado, cadastroTexto, onTentarDeNovo, recarregando }: Props) {
  const info = SONDA[estado]
  if (!info || estado === 'ok') return null  // cadastrado: a tela não fala do assunto
  const tom = TOM[info.tom]
  // O texto do Admin SÓ é usado quando a ação é de cadastro. Em qualquer
  // outro estado usamos o detalhe fixo — é o que impede `gateway_indisponivel`
  // de exibir "solicite seu cadastro".
  const detalhe = info.acao === 'cadastro'
    ? (cadastroTexto?.trim() || 'Solicite o cadastro no gateway de IA ao administrador.')
    : info.detalhe

  return (
    <div
      data-agentes-aviso={estado}
      className={`bg-panel border border-edge rounded-lg p-4 shadow-sm ${tom.caixa}`}
    >
      <p className={`text-sm font-semibold ${tom.titulo}`}>{info.titulo}</p>
      <p className="text-sm text-dim mt-1 whitespace-pre-wrap">{detalhe}</p>
      {onTentarDeNovo && info.tom === 'erro' && (
        <button
          type="button"
          onClick={onTentarDeNovo}
          disabled={recarregando}
          className="mt-3 text-sm font-medium text-[#1A5FA8] dark:text-blue-400 hover:underline disabled:opacity-50"
        >
          {recarregando ? 'Verificando…' : 'Verificar de novo'}
        </button>
      )}
    </div>
  )
}
