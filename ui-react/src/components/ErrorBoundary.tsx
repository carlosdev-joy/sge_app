// ErrorBoundary global do Orquestra (F10 da migração Caixa) — antes dele,
// qualquer throw de render desmontava a SPA inteira em tela branca (visto na
// revisão da F6: um :status malicioso derrubava o root). Mostra um painel de
// recuperação com recarregar/voltar; o erro segue indo ao console.
import React from 'react'

interface Props {
  children: React.ReactNode
}

interface State {
  error: Error | null
}

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('ErrorBoundary capturou:', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="min-h-screen bg-canvas flex items-center justify-center p-6">
        <div className="bg-panel border border-edge rounded-xl shadow-2xl max-w-lg w-full p-8 text-center">
          <p className="text-4xl mb-4">⚠️</p>
          <h1 className="text-lg font-semibold text-ink mb-2">Algo deu errado nesta tela</h1>
          <p className="text-sm text-dim mb-6 break-words">
            {this.state.error.message || 'Erro inesperado de renderização.'}
          </p>
          <div className="flex justify-center gap-3">
            <button
              onClick={() => { this.setState({ error: null }); window.history.back() }}
              className="px-3.5 py-1.5 text-sm rounded-md font-medium bg-white hover:bg-slate-50 text-slate-700 border border-slate-300 shadow-sm dark:bg-edge dark:hover:bg-edge/70 dark:text-ink dark:border-edge transition-colors"
            >
              Voltar
            </button>
            <button
              onClick={() => window.location.reload()}
              className="px-3.5 py-1.5 text-sm rounded-md font-medium bg-[#1A5FA8] hover:bg-[#0F4C88] text-white shadow-sm transition-colors"
            >
              Recarregar a página
            </button>
          </div>
        </div>
      </div>
    )
  }
}
