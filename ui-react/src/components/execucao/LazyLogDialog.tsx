import { Component, Suspense, type ReactNode } from 'react'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'

interface Props {
  title: string
  onClose: () => void
  children: ReactNode
}

// Uma falha ao buscar o módulo de logs não deve desmontar a página de operação.
class LogLoadBoundary extends Component<Props, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <Modal open title={this.props.title} onClose={this.props.onClose}>
        <p role="alert" className="text-sm text-ink">
          Não foi possível carregar os detalhes. Recarregue a página para tentar novamente.
        </p>
        <div className="mt-4 flex justify-end">
          <Button variant="secondary" onClick={this.props.onClose}>Fechar</Button>
        </div>
      </Modal>
    )
  }
}

export function LazyLogDialog({ title, onClose, children }: Props) {
  return (
    <LogLoadBoundary title={title} onClose={onClose}>
      <Suspense fallback={
        <Modal open title={title} onClose={onClose}>
          <p role="status" className="text-sm text-ink">Carregando detalhes…</p>
          <div className="mt-4 flex justify-end">
            <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          </div>
        </Modal>
      }>
        {children}
      </Suspense>
    </LogLoadBoundary>
  )
}
