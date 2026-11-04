// Um comando executado (ou proposto/bloqueado) dentro do terminal do agente.
//
// SUPERFÍCIE FIXA ESCURA (docs/ui-temas-cores.md §4): o terminal é `bg-gray-950` nos
// dois temas, então texto claro sem `dark:` é intencional aqui — não "conserte".
// O estado nunca depende só de cor: o selo traz o texto ("leitura", "escrita"...).
import { useState } from 'react'
import { Copy } from 'lucide-react'
import type { ComandoTerminal } from '../../lib/terminalComando'
import {
  ROTULO_CLASSE, duracaoCurta, estadoEfetivo, limitarSaida, rastro,
} from '../../lib/terminalComando'
import { ConfirmarComando } from './ConfirmarComando'
import { toast } from '../ui/Toast'

const SELO_CLASSE = {
  leitura: 'border-emerald-700 text-emerald-300',
  escrita: 'border-amber-600 text-amber-300',
  proibido: 'border-red-700 text-red-300',
} as const

interface Props {
  cmd: ComandoTerminal
  agora: Date
  podeEscrever: boolean
  decidindo: boolean
  onDecidir: (cmdId: string, decisao: 'confirmar' | 'recusar') => void
}

export function ComandoBloco({ cmd, agora, podeEscrever, decidindo, onDecidir }: Props) {
  const [tudo, setTudo] = useState(false)
  const estado = estadoEfetivo(cmd, agora)
  const { texto, ocultas } = limitarSaida(cmd.saida, tudo ? Number.MAX_SAFE_INTEGER : undefined)
  const proposta = cmd.classe === 'escrita' && cmd.estado === 'proposto'

  async function copiar() {
    try {
      await navigator.clipboard.writeText(cmd.comando)
      toast.success('Comando copiado')
    } catch {
      toast.error('Não foi possível copiar')
    }
  }

  if (proposta && estado === 'proposto') {
    return <ConfirmarComando cmd={cmd} agora={agora} podeEscrever={podeEscrever}
                             decidindo={decidindo} onDecidir={onDecidir} />
  }

  return (
    <div className="rounded-md border border-gray-800 bg-gray-900/60 text-[13px]" data-terminal-comando={cmd.cmd_id}>
      <div className="flex flex-wrap items-center gap-2 px-3 py-1.5 border-b border-gray-800">
        <span className={`text-[11px] px-1.5 py-0.5 rounded border ${SELO_CLASSE[cmd.classe]}`}>
          {ROTULO_CLASSE[cmd.classe]}
        </span>
        <span className="text-[11px] text-gray-400" data-terminal-estado>
          {estado === 'expirado' ? 'expirado — nada foi executado' : rastro({ ...cmd, estado })}
        </span>
        <span className="text-[11px] text-gray-400 ml-auto">
          {cmd.servidor}{cmd.duracao_ms != null ? ` · ${duracaoCurta(cmd.duracao_ms)}` : ''}
          {cmd.codigo_saida != null && cmd.codigo_saida !== 0 ? ` · código ${cmd.codigo_saida}` : ''}
        </span>
        <button type="button" onClick={() => { void copiar() }} aria-label="Copiar comando"
                className="p-1 rounded text-gray-400 hover:text-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400">
          <Copy className="w-3.5 h-3.5" aria-hidden="true" />
        </button>
      </div>
      <pre className="px-3 py-2 font-mono text-gray-100 whitespace-pre-wrap break-all">
        <span className="text-gray-500 select-none" aria-hidden="true">$ </span>{cmd.comando}
      </pre>
      {cmd.saida ? (
        <>
          <pre className="px-3 pb-2 font-mono text-gray-300 whitespace-pre overflow-x-auto max-h-96"
               tabIndex={0} role="region" aria-label="Saída do comando">{texto}</pre>
          {(ocultas > 0 || cmd.truncada) && (
            <div className="px-3 pt-1.5 pb-2 flex flex-wrap items-center gap-3 text-[12px] text-gray-400">
              {ocultas > 0 && (
                <button type="button" onClick={() => setTudo(true)}
                        className="underline hover:text-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 rounded">
                  Mostrar tudo (+{ocultas} linhas)
                </button>
              )}
              {cmd.truncada && <span>Saída cortada no servidor (limite de tamanho).</span>}
            </div>
          )}
        </>
      ) : null}
      {cmd.classe === 'proibido' && cmd.motivo && (
        <p className="px-3 pb-2 text-[12px] text-red-300">Bloqueado: {cmd.motivo}.</p>
      )}
    </div>
  )
}
