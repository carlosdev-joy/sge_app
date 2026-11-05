// Um comando executado (ou proposto/bloqueado) dentro do terminal do agente.
//
// SUPERFÍCIE FIXA ESCURA (docs/ui-temas-cores.md §4): o terminal é `bg-gray-950` nos
// dois temas, então texto claro sem `dark:` é intencional aqui — não "conserte".
// O estado nunca depende só de cor: o selo traz o texto ("leitura", "escrita"...).
import { useState } from 'react'
import { Ban, Check, Clock, Copy, X } from 'lucide-react'
import type { ComandoTerminal } from '../../lib/terminalComando'
import {
  ROTULO_CLASSE, duracaoCurta, estadoEfetivo, limitarSaida, rastro,
} from '../../lib/terminalComando'
import { ConfirmarComando } from './ConfirmarComando'
import { toast } from '../ui/Toast'

// Estado depois da decisão, visível de relance (crítica do impeccable): o que EXECUTOU, FALHOU ou foi BLOQUEADO não pode ficar
// parecido com uma leitura. Texto + ícone + cor (nunca só cor).
const SELO_ESTADO: Partial<Record<string, { cls: string; Icone: typeof Check }>> = {
  executado: { cls: 'border-emerald-700 text-emerald-300', Icone: Check },
  falhou: { cls: 'border-red-700 text-red-300', Icone: X },
  bloqueado: { cls: 'border-red-700 text-red-300', Icone: Ban },
  recusado: { cls: 'border-gray-600 text-gray-300', Icone: X },
  expirado: { cls: 'border-gray-600 text-gray-300', Icone: Clock },
  executando: { cls: 'border-blue-700 text-blue-300', Icone: Clock },
}
const BORDA_DO_BLOCO: Partial<Record<string, string>> = { falhou: 'border-red-900', bloqueado: 'border-red-900' }

const SELO_CLASSE = {
  leitura: 'border-emerald-700 text-emerald-300',
  escrita: 'border-amber-600 text-amber-300',
  proibido: 'border-red-700 text-red-300',
} as const

interface Props {
  /** Rótulo do servidor (o mesmo do cabeçalho) para o card de confirmação; sem ele, o id. */
  rotuloServidor?: string
  cmd: ComandoTerminal
  agora: Date
  podeEscrever: boolean
  decidindo: boolean
  onDecidir: (cmdId: string, decisao: 'confirmar' | 'recusar') => void
}

export function ComandoBloco({ cmd, agora, podeEscrever, decidindo, onDecidir, rotuloServidor }: Props) {
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

  // `decidindo`: o usuário confirmou e o comando está rodando — mesmo que o relógio passe do prazo durante a execução, o card
  // continua "Executando…" (antes virava "expirado · nada foi executado" com o comando ainda rodando; QA da F5).
  if (proposta && (estado === 'proposto' || decidindo)) {
    return <ConfirmarComando cmd={cmd} agora={agora} podeEscrever={podeEscrever} rotuloServidor={rotuloServidor}
                             decidindo={decidindo} onDecidir={onDecidir} />
  }

  return (
    <div className={`rounded-md border bg-gray-900/60 text-[13px] ${BORDA_DO_BLOCO[estado]
           ?? (cmd.classe === 'escrita' && estado === 'executado' ? 'border-amber-800' : 'border-gray-800')}`}
         data-terminal-comando={cmd.cmd_id} data-estado={estado}>
      <div className="flex flex-wrap items-center gap-2 px-3 py-1.5 border-b border-gray-800">
        <span className={`text-[11px] px-1.5 py-0.5 rounded border ${SELO_CLASSE[cmd.classe]}`}>
          {ROTULO_CLASSE[cmd.classe]}
        </span>
        {(() => {
          const selo = SELO_ESTADO[estado]
          const detalhe = estado === 'expirado' ? 'nada foi executado' : rastro({ ...cmd, estado }).replace(/^\S+\s?/, '')
          return (
            <span className="inline-flex items-center gap-1.5 text-[11px] text-gray-400" data-terminal-estado>
              {selo && (
                <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border ${selo.cls}`}>
                  <selo.Icone className="w-3 h-3" aria-hidden="true" />{estado}
                </span>
              )}
              {!selo && estado}
              {detalhe && <span>{detalhe}</span>}
            </span>
          )
        })()}
        <span className="text-[11px] text-gray-400 ml-auto">
          {cmd.servidor}{cmd.duracao_ms != null ? ` · ${duracaoCurta(cmd.duracao_ms)}` : ''}
          {cmd.codigo_saida != null && cmd.codigo_saida !== 0 ? ` · código ${cmd.codigo_saida}` : ''}
        </span>
        <button type="button" onClick={() => { void copiar() }} aria-label="Copiar comando"
                className="p-1.5 rounded text-gray-400 hover:text-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400">
          <Copy className="w-3.5 h-3.5" aria-hidden="true" />
        </button>
      </div>
      <pre className="px-3 py-2 font-mono text-gray-100 whitespace-pre-wrap break-all">
        <span className="text-gray-400 select-none" aria-hidden="true">$ </span>{cmd.comando}
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
      {(cmd.interrompido || (cmd.notas?.length ?? 0) > 0) && (
        <ul className="px-3 pb-2 text-[12px] text-amber-200 flex flex-col gap-0.5" data-terminal-notas>
          {cmd.interrompido && <li>Interrompido: passou do limite de tempo do servidor.</li>}
          {cmd.notas?.map(n => <li key={n}>{n.replace(/^\[|\]$/g, '')}</li>)}
        </ul>
      )}
      {cmd.classe === 'proibido' && cmd.motivo && (
        <p className="px-3 pb-2 text-[12px] text-red-300">Motivo: {cmd.motivo.replace(/^bloqueado:\s*/i, '')}.</p>
      )}
    </div>
  )
}
