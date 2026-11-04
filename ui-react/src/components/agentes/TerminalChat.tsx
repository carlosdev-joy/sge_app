// O chat estilo terminal do agente "Terminal" (spec docs/spec-agente-terminal.md, F1).
//
// Apresentação pura: quem fala com a API (ou com o simulador da F1) é o container.
// Moldura e cabeçalho usam tokens do tema; o CORPO do terminal é `bg-gray-950` fixo
// nos dois temas (docs/ui-temas-cores.md §4) — texto claro sem `dark:` é intencional.
//
// Acessibilidade: histórico `role="log"` + `aria-live="polite"`; foco volta ao campo
// depois de enviar; "executando" tem texto; selo "Somente leitura"/"Escrita habilitada"
// tem texto, não só cor.
import { useEffect, useRef, useState } from 'react'
import { SendHorizontal, ShieldCheck, TriangleAlert, MessageSquarePlus } from 'lucide-react'
import type { MensagemTerminal } from '../../lib/terminalComando'
import { MAX_ENTRADA, entradaValida, estadoEfetivo } from '../../lib/terminalComando'
import { EXEMPLOS_TERMINAL } from '../../lib/terminalSimulado'
import { ComandoBloco } from './ComandoBloco'

interface Props {
  mensagens: MensagemTerminal[]
  enviando: boolean
  podeEscrever: boolean
  servidor: string
  servidores: { id: string; label: string }[]
  decidindo: ReadonlySet<string>
  erro?: string | null
  bloqueado?: boolean
  motivoBloqueio?: string
  onServidor: (id: string) => void
  onEnviar: (texto: string) => void
  onDecidir: (cmdId: string, decisao: 'confirmar' | 'recusar') => void
  onNova: () => void
}

export function TerminalChat({
  mensagens, enviando, podeEscrever, servidor, servidores, decidindo, erro, bloqueado, motivoBloqueio,
  onServidor, onEnviar, onDecidir, onNova,
}: Props) {
  const [texto, setTexto] = useState('')
  const [agora, setAgora] = useState(() => new Date())
  const campo = useRef<HTMLTextAreaElement>(null)
  const fim = useRef<HTMLDivElement>(null)
  // Proposta VIVA (não vencida no relógio do front): governa o relógio e o foco.
  const temProposta = mensagens.some(m => 'comando' in m && estadoEfetivo(m.comando, agora) === 'proposto')

  // Relógio só enquanto há proposta viva (contagem regressiva do card). Ao ligar, atualiza
  // `agora` na hora: com a página aberta há tempo, o 1º quadro não pode mostrar prazo velho.
  useEffect(() => {
    if (!temProposta) return
    setAgora(new Date())
    const t = setInterval(() => setAgora(new Date()), 1000)
    return () => clearInterval(t)
  }, [temProposta])

  useEffect(() => { fim.current?.scrollIntoView({ block: 'end' }) }, [mensagens.length, enviando])
  // Com proposta viva o foco fica no card de confirmação (aviso ao leitor de tela), não no campo.
  useEffect(() => { if (!enviando && !bloqueado && !temProposta) campo.current?.focus() }, [enviando, bloqueado, temProposta])

  function enviar(valor: string = texto) {
    if (!entradaValida(valor) || enviando || bloqueado) return
    onEnviar(valor.trim())
    setTexto('')
  }

  return (
    <section className="relative flex flex-col h-full min-h-0 rounded-lg border border-edge bg-panel overflow-hidden"
             aria-label="Terminal do agente" data-terminal>
      <header className="flex flex-wrap items-center gap-2 px-3 py-2 border-b border-edge">
        <label className="flex items-center gap-2 text-[13px] text-dim">
          Servidor
          <select value={servidor} onChange={e => onServidor(e.target.value)}
                  className="h-8 rounded-md border border-edge bg-panel text-ink text-[13px] px-2
                             focus:outline-none focus-visible:ring-2 focus-visible:ring-[#1A5FA8]">
            {servidores.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </label>
        {podeEscrever ? (
          <span data-terminal-modo="escrita"
                className="inline-flex items-center gap-1 text-[12px] px-2 py-0.5 rounded-full border
                           bg-amber-50 border-amber-300 text-amber-800
                           dark:bg-amber-900/30 dark:border-amber-800 dark:text-amber-300">
            <TriangleAlert className="w-3.5 h-3.5" aria-hidden="true" /> Escrita habilitada
          </span>
        ) : (
          <span data-terminal-modo="leitura"
                className="inline-flex items-center gap-1 text-[12px] px-2 py-0.5 rounded-full border
                           bg-green-50 border-green-300 text-green-800
                           dark:bg-green-900/30 dark:border-green-800 dark:text-green-300">
            <ShieldCheck className="w-3.5 h-3.5" aria-hidden="true" /> Somente leitura
          </span>
        )}
        <button type="button" onClick={onNova} disabled={mensagens.length === 0 || enviando}
                title={mensagens.length === 0 ? 'A conversa ainda está vazia' : 'Começar uma conversa do zero'}
                className="ml-auto inline-flex items-center gap-1.5 h-8 px-3 rounded-md border border-edge bg-panel text-ink
                           text-[13px] font-medium hover:bg-canvas disabled:opacity-50 disabled:cursor-not-allowed
                           focus:outline-none focus-visible:ring-2 focus-visible:ring-[#1A5FA8]">
          <MessageSquarePlus className="w-4 h-4" aria-hidden="true" /> Nova conversa
        </button>
      </header>

      {/* Corpo do terminal: fundo fixo escuro nos dois temas. */}
      <div className="flex-1 min-h-0 overflow-y-auto bg-gray-950 text-gray-200 px-3 py-3 flex flex-col gap-3 font-mono"
           role="log" aria-live="polite" aria-label="Histórico do terminal" tabIndex={0}>
        {mensagens.length === 0 && (
          <div className="font-sans text-[13px] text-gray-400" data-terminal-vazio>
            <p className="text-gray-200">Pergunte em linguagem livre ou digite um comando.</p>
            <p className="mt-1">Eu consulto o servidor, o DataStage e os bancos liberados para você. Comandos que alteram algo só rodam depois do seu “Confirmar”.</p>
            <ul className="mt-3 flex flex-col gap-1.5">
              {EXEMPLOS_TERMINAL.map(ex => (
                <li key={ex}>
                  <button type="button" onClick={() => enviar(ex)} disabled={bloqueado || enviando}
                          className="text-left text-blue-300 hover:underline disabled:opacity-50
                                     focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 rounded">
                    › {ex}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
        {mensagens.map(m => {
          if (m.papel === 'usuario') {
            return <p key={m.id} className="text-[13px] text-gray-100 whitespace-pre-wrap break-words">
              <span className="text-blue-400 select-none" aria-hidden="true">› </span>{m.texto}
            </p>
          }
          if (m.papel === 'assistente') {
            return <p key={m.id} className="font-sans text-[13px] text-gray-300 whitespace-pre-wrap break-words">{m.texto}</p>
          }
          return <ComandoBloco key={m.id} cmd={m.comando} agora={agora} podeEscrever={podeEscrever}
                               decidindo={decidindo.has(m.comando.cmd_id)} onDecidir={onDecidir} />
        })}
        {enviando && <p className="font-sans text-[13px] text-gray-400" data-terminal-executando>Consultando o servidor…</p>}
        {erro && <p role="alert" className="font-sans text-[13px] text-red-300">{erro}</p>}
        <div ref={fim} />
      </div>

      <form className="border-t border-edge p-2 flex items-end gap-2"
            onSubmit={e => { e.preventDefault(); enviar() }}>
        <label className="sr-only" htmlFor="terminal-entrada">Mensagem ou comando</label>
        <textarea id="terminal-entrada" ref={campo} value={texto} rows={2} maxLength={MAX_ENTRADA}
                  disabled={bloqueado}
                  onChange={e => setTexto(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviar() } }}
                  aria-describedby="terminal-dica"
                  placeholder={bloqueado ? (motivoBloqueio ?? 'Terminal indisponível') : 'Pergunte ou digite um comando'}
                  className="flex-1 resize-none rounded-md border border-edge bg-canvas text-ink text-[13px] font-mono px-3 py-2
                             placeholder:text-dim disabled:opacity-60
                             focus:outline-none focus-visible:ring-2 focus-visible:ring-[#1A5FA8]" />
        <button type="submit" disabled={!entradaValida(texto) || enviando || bloqueado}
                className="h-9 px-3 inline-flex items-center gap-1.5 rounded-md bg-[#1A5FA8] text-white text-[13px] font-medium
                           hover:bg-[#164f8c] disabled:opacity-50 disabled:cursor-not-allowed
                           focus:outline-none focus-visible:ring-2 focus-visible:ring-[#1A5FA8] focus-visible:ring-offset-2">
          <SendHorizontal className="w-4 h-4" aria-hidden="true" /> Enviar
        </button>
      </form>
      <p id="terminal-dica" className="sr-only sm:not-sr-only px-3 pb-2 text-[11px] text-dim">
        Enter envia · Shift+Enter quebra a linha
      </p>
    </section>
  )
}
