// Configuração do nó Fim da malha — controla se a guardiã envia o card do
// Teams quando todos os pipelines upstream do Fim concluem (MALHA_CONCLUIDA).
// É OPT-IN por design: malhas sem destinatário não geram ruído.
import { useState } from 'react'
import { CheckSquare, Square, Flag } from 'lucide-react'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { toast } from '../ui/Toast'

export interface ConfigFim {
  notificar_teams?: boolean | null
}

interface Props {
  malha: string
  config: ConfigFim | null
  podeEditar: boolean
  onSalvar: (cfg: ConfigFim) => Promise<void>
  onClose: () => void
}

export function FimMalhaModal({ malha: _, config, podeEditar, onSalvar, onClose }: Props) {
  const [notificar, setNotificar] = useState<boolean>(config?.notificar_teams === true)
  const [salvando, setSalvando] = useState(false)

  async function salvar() {
    setSalvando(true)
    try {
      await onSalvar({ notificar_teams: notificar })
      onClose()
    } catch (e) {
      toast.error(`Não foi possível salvar: ${(e as Error).message}`)
    } finally {
      setSalvando(false)
    }
  }

  const Check = notificar ? CheckSquare : Square

  return (
    <Modal open onClose={onClose} title="Nó Fim da malha" size="sm">
      <div className="flex flex-col gap-4">
        <p className="flex items-start gap-2 text-[12px] text-dim">
          <Flag size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span>
            Quando todos os pipelines upstream do Fim concluem, a guardiã
            registra o encerramento do ciclo. O canal do Teams é o configurado
            no nó Início desta malha.
          </span>
        </p>

        <button
          type="button"
          disabled={!podeEditar}
          onClick={() => setNotificar(v => !v)}
          className="flex items-center gap-2 rounded-md border border-edge bg-canvas px-3 py-2.5 text-[13px] text-ink transition-colors hover:bg-panel disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Check size={16} className={notificar ? 'text-primary' : 'text-dim'} />
          Enviar card no Teams quando o ciclo encerrar
        </button>

        <p className="text-[11px] text-dim">
          {notificar
            ? 'A guardiã enviará o card de conclusão no canal do Teams desta malha.'
            : 'Nenhum aviso de conclusão será enviado ao Teams.'}
        </p>

        <div className="flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onClose}>
            {podeEditar ? 'Cancelar' : 'Fechar'}
          </Button>
          {podeEditar && (
            <Button size="sm" loading={salvando} onClick={salvar}>
              Salvar
            </Button>
          )}
        </div>
      </div>
    </Modal>
  )
}
