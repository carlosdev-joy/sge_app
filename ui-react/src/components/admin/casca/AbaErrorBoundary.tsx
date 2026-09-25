// ErrorBoundary POR ABA do Admin (docs/spec-admin-reestruturacao.md §3.1).
// Uma aba que quebra não derruba a casca: o sub-menu e o cabeçalho continuam de
// pé. Caso típico com lazy por aba: deploy novo apaga o chunk antigo e o import
// dinâmico falha — aí a saída certa é recarregar a página.
// O ErrorBoundary global (components/ErrorBoundary.tsx) não serve aqui: ele
// ocupa a tela inteira (min-h-screen) e trocaria a casca pelo painel de erro.
import React from 'react'
import { RefreshCw } from 'lucide-react'
import { Button } from '../../ui/Button'

interface Props { children: React.ReactNode }
interface State { error: Error | null }

// Mensagens do Chrome/Firefox/Safari/Vite para chunk que não carregou.
const FALHA_DE_CHUNK = /dynamically imported module|importing a module script failed|failed to fetch|chunkloaderror|loading chunk|error loading dynamically/i

export class AbaErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('Aba do admin falhou:', error, info.componentStack)
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children
    const chunk = FALHA_DE_CHUNK.test(`${error.name} ${error.message}`)
    return (
      <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg border px-4 py-3 text-sm
        border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
        <p className="min-w-0 flex-1 break-words">
          {chunk
            ? 'Esta aba foi atualizada. Recarregue a página.'
            : <>Esta aba encontrou um erro e não pôde ser exibida. As demais seções continuam disponíveis.
                {error.message && <span className="block text-xs opacity-80 mt-0.5">{error.message}</span>}</>}
        </p>
        <Button size="sm" variant="secondary" onClick={() => window.location.reload()}>
          <RefreshCw size={13} aria-hidden /> Recarregar
        </Button>
      </div>
    )
  }
}
