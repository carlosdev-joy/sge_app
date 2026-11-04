// Card de confirmação de um comando de ESCRITA (spec docs/spec-agente-terminal.md §3).
//
// Superfície fixa escura do terminal (docs/ui-temas-cores.md §4). Regras de UX:
//   • o Enter no campo de texto NUNCA confirma — só o clique/Enter no botão focado;
//   • o foco vai para o card (tabIndex=-1), não para um botão, para o leitor de tela
//     anunciar o aviso antes de qualquer ação;
//   • sem o recurso de escrita o card vira aviso, sem botões.
import { useEffect, useRef } from 'react'
import { TriangleAlert } from 'lucide-react'
import type { ComandoTerminal } from '../../lib/terminalComando'
import { relogio, segundosRestantes } from '../../lib/terminalComando'

interface Props {
  cmd: ComandoTerminal
  agora: Date
  podeEscrever: boolean
  decidindo: boolean
  onDecidir: (cmdId: string, decisao: 'confirmar' | 'recusar') => void
}

export function ConfirmarComando({ cmd, agora, podeEscrever, decidindo, onDecidir }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => { ref.current?.focus({ preventScroll: false }) }, [cmd.cmd_id])
  const restante = segundosRestantes(cmd.expira_em, agora)

  return (
    <div ref={ref} tabIndex={-1} role="group" aria-label="Confirmação de comando que altera o servidor"
         data-terminal-confirmar={cmd.cmd_id}
         className="rounded-md border border-amber-600 bg-amber-950/40 text-[13px] focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400">
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-amber-800 text-amber-200">
        <TriangleAlert className="w-4 h-4 shrink-0" aria-hidden="true" />
        <span className="font-medium">Este comando altera o servidor</span>
        <span className="ml-auto text-[12px] text-amber-300" aria-live="off">
          expira em {relogio(restante)}
        </span>
      </div>
      <div className="px-3 py-2 flex flex-col gap-1.5">
        <pre className="font-mono text-gray-100 whitespace-pre-wrap break-all">
          <span className="text-gray-500 select-none" aria-hidden="true">$ </span>{cmd.comando}
        </pre>
        <p className="text-[12px] text-gray-400">Servidor: <span className="text-gray-200">{cmd.servidor}</span></p>
        {cmd.motivo && <p className="text-[12px] text-gray-300">Motivo: {cmd.motivo}</p>}
      </div>
      {podeEscrever ? (
        <div className="px-3 pb-3 flex flex-col sm:flex-row gap-2">
          <button type="button" disabled={decidindo} onClick={() => onDecidir(cmd.cmd_id, 'confirmar')}
                  data-terminal-confirmar-botao
                  className="h-9 px-4 rounded-md bg-amber-500 text-gray-950 text-[13px] font-semibold hover:bg-amber-400
                             disabled:opacity-50 disabled:cursor-not-allowed
                             focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300 focus-visible:ring-offset-2 focus-visible:ring-offset-gray-950">
            {decidindo ? 'Executando…' : 'Confirmar e executar'}
          </button>
          <button type="button" disabled={decidindo} onClick={() => onDecidir(cmd.cmd_id, 'recusar')}
                  data-terminal-recusar-botao
                  className="h-9 px-4 rounded-md border border-gray-600 text-gray-200 text-[13px] hover:bg-gray-800
                             disabled:opacity-50 disabled:cursor-not-allowed
                             focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400">
            Recusar
          </button>
        </div>
      ) : (
        <p className="px-3 pb-3 text-[12px] text-amber-200" data-terminal-sem-escrita>
          Você não tem permissão para executar comandos que alteram o servidor. Peça ao administrador.
        </p>
      )}
    </div>
  )
}
