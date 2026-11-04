// Container do Terminal na F1 (spec docs/spec-agente-terminal.md): estado + SIMULADOR.
// Nenhuma chamada de rede. A F5 troca `simularResposta`/`simularDecisao` pela API real.
import { useRef, useState } from 'react'
import { SquareTerminal } from 'lucide-react'
import { TerminalChat } from './TerminalChat'
import type { MensagemTerminal } from '../../lib/terminalComando'
import { aplicarComando, podeDecidir } from '../../lib/terminalComando'
import { simularDecisao, simularResposta } from '../../lib/terminalSimulado'
import { useAuthStore } from '../../store/auth'

const SERVIDORES = [
  { id: 'airflow', label: 'Servidor Orquestra/Airflow' },
  { id: 'datastage', label: 'Servidor DataStage' },
]

let seq = 0
const novoId = () => `u${++seq}`

export function TerminalSimulado({ podeEscrever }: { podeEscrever: boolean }) {
  const matricula = useAuthStore(s => s.user?.matricula ?? 'usuario')
  const [mensagens, setMensagens] = useState<MensagemTerminal[]>([])
  const [enviando, setEnviando] = useState(false)
  const [servidor, setServidor] = useState(SERVIDORES[0].id)
  const [decidindo, setDecidindo] = useState<ReadonlySet<string>>(new Set())
  // Só `nova()` incrementa: invalida respostas/decisões em voo da conversa anterior. Enviar uma
  // mensagem NÃO pode invalidar uma decisão pendente (QA F1, N1: o card ficava preso).
  const conversa = useRef(0)

  function enviar(texto: string) {
    const minha = conversa.current
    setMensagens(m => [...m, { id: novoId(), papel: 'usuario', texto }])
    setEnviando(true)
    setTimeout(() => {
      if (minha !== conversa.current) return  // "Nova conversa" no meio: descarta
      setMensagens(m => [...m, ...simularResposta(texto, servidor)])
      setEnviando(false)
    }, 700)
  }

  function decidir(cmdId: string, decisao: 'confirmar' | 'recusar') {
    const alvo = mensagens.find(m => m.papel === 'comando' && m.comando.cmd_id === cmdId)
    if (!alvo || alvo.papel !== 'comando' || decidindo.has(cmdId)) return  // duplo clique = 1 decisão
    // Mesma régua da tela: só decide escrita viva e com permissão (o backend real é a autoridade).
    if (!podeDecidir(alvo.comando, new Date(), podeEscrever)) return
    const minha = conversa.current
    setDecidindo(s => new Set(s).add(cmdId))
    setTimeout(() => {
      if (minha !== conversa.current) return  // "Nova conversa" no meio: não ressuscita o comando
      setMensagens(m => aplicarComando(m, simularDecisao(alvo.comando, decisao, matricula)))
      setDecidindo(s => { const n = new Set(s); n.delete(cmdId); return n })
    }, decisao === 'confirmar' ? 900 : 100)
  }

  function nova() {
    conversa.current++
    setMensagens([])
    setEnviando(false)
    setDecidindo(new Set())
  }

  return (
    <div className="p-4 sm:p-6 flex flex-col gap-4 h-[calc(100vh-7rem)] min-h-0">
      <header className="min-w-0">
        <h1 className="text-lg font-semibold text-ink flex items-center gap-2">
          <SquareTerminal className="w-5 h-5 text-[#1A5FA8] dark:text-blue-400" aria-hidden="true" />
          Terminal
        </h1>
        <p className="text-sm text-dim mt-0.5 max-w-2xl">
          Consulte o servidor, o DataStage e os bancos em linguagem livre. Prévia com dados simulados — nada é executado.
        </p>
      </header>
      <div className="flex-1 min-h-0">
        <TerminalChat
          mensagens={mensagens} enviando={enviando} podeEscrever={podeEscrever}
          servidor={servidor} servidores={SERVIDORES} decidindo={decidindo}
          onServidor={setServidor} onEnviar={enviar} onDecidir={decidir} onNova={nova}
        />
      </div>
    </div>
  )
}
