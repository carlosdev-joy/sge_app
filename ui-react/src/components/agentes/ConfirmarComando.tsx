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
import { linhasDoComando, relogio, segundosRestantes } from '../../lib/terminalComando'

interface Props {
  rotuloServidor?: string
  cmd: ComandoTerminal
  agora: Date
  podeEscrever: boolean
  decidindo: boolean
  onDecidir: (cmdId: string, decisao: 'confirmar' | 'recusar') => void
}

export function ConfirmarComando({ cmd, agora, podeEscrever, decidindo, onDecidir, rotuloServidor }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => { ref.current?.focus({ preventScroll: false }) }, [cmd.cmd_id])
  const restante = segundosRestantes(cmd.expira_em, agora)
  const acabando = restante > 0 && restante <= 30
  const ids = { comando: `cmd-${cmd.cmd_id}-texto`, alvo: `cmd-${cmd.cmd_id}-alvo` }

  return (
    <div ref={ref} tabIndex={-1} role="group" aria-label="Confirmação de comando que altera o servidor"
         aria-describedby={`${ids.comando} ${ids.alvo}`}
         data-terminal-confirmar={cmd.cmd_id}
         className="relative rounded-md border border-amber-600 bg-amber-950/40 text-[13px] focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400">
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-amber-800 text-amber-200">
        <TriangleAlert className="w-4 h-4 shrink-0" aria-hidden="true" />
        <span className="font-medium">Este comando altera o servidor</span>
        <span className={`ml-auto text-[12px] tabular-nums ${acabando ? 'text-red-300 font-semibold' : 'text-amber-300'}`} aria-live="off">
          expira em {relogio(restante)}
        </span>
        <span className="sr-only" aria-live="assertive">{acabando && restante >= 28 ? 'Faltam 30 segundos para a proposta expirar.' : ''}</span>
      </div>
      <div className="px-3 py-2 flex flex-col gap-1.5">
        <pre id={ids.comando} className="font-mono text-gray-100 whitespace-pre-wrap break-all">
          <span className="text-gray-400 select-none" aria-hidden="true">$ </span>{cmd.comando}
        </pre>
        {linhasDoComando(cmd.comando) > 1 && (
          <p className="text-[12px] text-amber-200" data-terminal-multilinha>
            Atenção: o comando tem {linhasDoComando(cmd.comando)} linhas — todas serão executadas.
          </p>
        )}
        <p id={ids.alvo} className="text-[13px] text-amber-100" data-terminal-alvo>
          Vai rodar em <strong className="font-semibold">{rotuloServidor || cmd.servidor}</strong>
        </p>
        {cmd.motivo && (
          <p className="text-[12px] text-gray-400 max-w-[75ch]" data-terminal-alegacao>
            <span className="text-gray-300">Alegação do assistente (não verificada):</span> <span className="italic">{cmd.motivo}</span>
            <span className="block mt-0.5">Confira o comando acima — é ele que roda, não a explicação.</span>
          </p>
        )}
      </div>
      {podeEscrever ? (
        <div className="px-3 pb-3 flex flex-col-reverse sm:flex-row gap-2">
          {/* flex-col-reverse: no celular, Recusar fica em cima — o polegar cai no primeiro botão. */}
          <button type="button" disabled={decidindo} onClick={() => onDecidir(cmd.cmd_id, 'confirmar')}
                  data-terminal-confirmar-botao
                  className="min-h-11 sm:min-h-9 px-4 rounded-md bg-amber-500 text-gray-950 text-[13px] font-semibold hover:bg-amber-400
                             disabled:opacity-50 disabled:cursor-not-allowed
                             focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300 focus-visible:ring-offset-2 focus-visible:ring-offset-gray-950">
            {decidindo ? 'Executando…' : 'Confirmar e executar'}
          </button>
          <button type="button" disabled={decidindo} onClick={() => onDecidir(cmd.cmd_id, 'recusar')}
                  data-terminal-recusar-botao
                  className="min-h-11 sm:min-h-9 px-4 rounded-md border border-gray-600 text-gray-200 text-[13px] hover:bg-gray-800
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
