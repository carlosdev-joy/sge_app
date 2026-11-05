// O Terminal ligado à API (F5 da spec docs/spec-agente-terminal.md) — container: estado e rede; quem desenha é o `TerminalChat`.
//
// Reaproveita do chat dos outros agentes o que já foi endurecido: a sonda do gateway de IA (aviso + campo bloqueado), o
// `pedidoRef` que descarta resposta atrasada depois de "Nova conversa", e o fallback do stream para o JSON quando a rota de
// stream ainda não existe. Confirmar/Recusar falam com `/agentes/terminal/confirmar|recusar`; depois de QUALQUER recusa da API
// (409/503) o card é reidratado pelo `GET /agentes/terminal/comandos/{id}` — o estado do servidor é a verdade, não o do card.
import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { TerminalChat } from './TerminalChat'
import { AvisoSonda } from './AvisoSonda'
import { apiFetch } from '../../lib/api'
import type { AgenteCatalogo, EstadoSonda, RespostaConversa } from '../../lib/agentes'
import { SONDA, codigoDoErro, mensagemDeErro } from '../../lib/agentes'
import { conversarPorStream, rotaStreamAusente } from '../../lib/agentesStream'
import type { ArtefatoTerminalApi, ComandoApi, ComandoTerminal, MensagemTerminal } from '../../lib/terminalComando'
import { mensagensDaResposta, reidratar, substituirComando, textoDoErroDeDecisao } from '../../lib/terminalComando'
import { toast } from '../ui/Toast'

let seq = 0
const novoId = () => `t${++seq}`

interface Servidor { id: string; label: string; configurado: boolean }
interface ResultadoDecisao {
  cmd_id: string; estado: ComandoTerminal['estado']; saida?: string | null; codigo_saida?: number | null
  duracao_ms?: number | null; decidido_por?: string | null; truncada?: boolean; interrompido?: boolean
}

export function TerminalAgente({ agente, sonda, cadastroTexto, onRecarregarSonda, recarregandoSonda }: {
  agente: AgenteCatalogo & { escrita?: boolean }
  sonda?: EstadoSonda
  cadastroTexto?: string | null
  onRecarregarSonda: () => void
  recarregandoSonda: boolean
}) {
  const [mensagens, setMensagens] = useState<MensagemTerminal[]>([])
  const [conversaId, setConversaId] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const [statusTexto, setStatusTexto] = useState<string | null>(null)
  const [decidindo, setDecidindo] = useState<ReadonlySet<string>>(() => new Set())
  const pedidoRef = useRef(0)
  // Conversa ≠ pedido: enviar outra pergunta ou "Parar" NÃO troca de conversa — uma decisão em voo continua dona do seu card.
  // Só "Nova conversa" incrementa este contador (2ª rodada do QA da F5).
  const conversaRef = useRef(0)
  const servidores = useQuery<{ servidores: Servidor[] }>({
    queryKey: ['agentes-terminal-servidores'], queryFn: () => apiFetch('/agentes/terminal/servidores'), retry: false,
  })
  const infoSonda = sonda ? SONDA[sonda] : null
  const bloqueado = infoSonda?.bloqueia ?? false

  async function enviar(conteudo: string) {
    if (!conteudo.trim() || enviando || bloqueado) return
    const meu = ++pedidoRef.current
    const abandonado = () => pedidoRef.current !== meu
    setMensagens(m => [...m, { id: novoId(), papel: 'usuario', texto: conteudo }])
    setEnviando(true)
    setStatusTexto(null)
    const corpo = JSON.stringify(conversaId ? { mensagem: conteudo, conversa_id: conversaId } : { mensagem: conteudo })
    try {
      let r: RespostaConversa | null
      try {
        r = await conversarPorStream(agente.id, corpo, t => { if (!abandonado()) setStatusTexto(t) }, abandonado)
      } catch (e) {
        if (!rotaStreamAusente(e)) throw e
        r = await apiFetch<RespostaConversa>(`/agentes/${agente.id}/conversar`, { method: 'POST', body: corpo })
      }
      if (r === null || abandonado()) return
      setConversaId(r.conversa_id)
      const novas = mensagensDaResposta({ texto: r.texto, artefatos: r.artefatos as ArtefatoTerminalApi[] }, new Date(), novoId)
      setMensagens(m => [...m, ...novas])
    } catch (e) {
      if (abandonado()) return
      const msg = mensagemDeErro(e, 'Não foi possível falar com o Terminal agora.')
      toast.error(msg)
      setMensagens(m => [...m, { id: novoId(), papel: 'assistente', texto: msg }])
    } finally {
      if (!abandonado()) {
        setEnviando(false)
        setStatusTexto(null)
      }
    }
  }

  function comandoAtual(cmdId: string): ComandoTerminal | null {
    for (const m of mensagens) if (m.papel === 'comando' && m.comando.cmd_id === cmdId) return m.comando
    return null
  }

  async function reidratarCard(cmdId: string, conversa: number) {
    const atual = comandoAtual(cmdId)
    if (!atual) return
    try {
      const r = await apiFetch<{ comando: ComandoApi }>(`/agentes/terminal/comandos/${encodeURIComponent(cmdId)}`)
      if (conversaRef.current !== conversa) return  // "Nova conversa" no meio: o card não volta para a conversa nova
      setMensagens(m => substituirComando(m, reidratar(atual, r.comando, new Date())))
    } catch {
      /* sem estado novo: o card fica como está (a próxima ação reconsulta) */
    }
  }

  async function decidir(cmdId: string, decisao: 'confirmar' | 'recusar') {
    const atual = comandoAtual(cmdId)
    if (!atual || decidindo.has(cmdId)) return  // duplo clique = uma decisão (o servidor também garante)
    const conversa = conversaRef.current  // a decisão pertence a ESTA conversa; depois de "Nova conversa" o resultado só vira toast
    setDecidindo(s => new Set(s).add(cmdId))
    try {
      const corpo = decisao === 'confirmar' ? { cmd_id: cmdId, hash: atual.hash ?? '' } : { cmd_id: cmdId }
      const r = await apiFetch<{ resultado: ResultadoDecisao }>(`/agentes/terminal/${decisao}`, {
        method: 'POST', body: JSON.stringify(corpo),
      })
      const res = r.resultado
      if (conversaRef.current !== conversa) {
        toast.info(res.estado === 'recusado' ? 'O comando foi recusado (veja na auditoria).'
          : res.estado === 'executado' ? 'O comando confirmado foi executado (veja na auditoria).' : 'O comando confirmado terminou com erro.')
        return
      }
      setMensagens(m => substituirComando(m, {
        ...atual, estado: res.estado, expira_em: null, decidido_por: res.decidido_por ?? null,
        decidido_em: new Date().toISOString(), saida: res.saida ?? atual.saida ?? null,
        codigo_saida: res.codigo_saida ?? null, duracao_ms: res.duracao_ms ?? null,
        truncada: !!res.truncada, interrompido: !!res.interrompido,
      }))
      if (decisao === 'confirmar') {
        if (res.estado === 'executado') toast.success('Comando executado')
        else toast.error('O comando terminou com erro — veja a saída')
      }
    } catch (e) {
      const { texto, reidratar: deveReidratar } = textoDoErroDeDecisao(codigoDoErro(e))
      toast.error(texto)
      if (deveReidratar && conversaRef.current === conversa) await reidratarCard(cmdId, conversa)
    } finally {
      setDecidindo(s => { const n = new Set(s); n.delete(cmdId); return n })
    }
  }

  function nova() {
    pedidoRef.current++
    conversaRef.current++
    setMensagens([])
    setConversaId(null)
    setEnviando(false)
    setStatusTexto(null)
    setDecidindo(new Set())
  }

  const lista = (servidores.data?.servidores ?? []).filter(s => s.configurado).map(s => ({ id: s.id, label: s.label }))
  return (
    <TerminalChat
      mensagens={mensagens} enviando={enviando} statusTexto={statusTexto} podeEscrever={!!agente.escrita}
      servidores={lista} decidindo={decidindo} bloqueado={bloqueado}
      motivoBloqueio={infoSonda?.bloqueia ? infoSonda.titulo : undefined}
      aviso={sonda ? (
        <AvisoSonda estado={sonda} cadastroTexto={cadastroTexto} onTentarDeNovo={onRecarregarSonda} recarregando={recarregandoSonda} />
      ) : undefined}
      onEnviar={t => { void enviar(t) }} onDecidir={(id, d) => { void decidir(id, d) }} onNova={nova}
      onParar={() => {
        // Abandona a rodada: a resposta que chegar depois é descartada (o servidor pode ainda terminar a consulta).
        pedidoRef.current++
        setEnviando(false)
        setStatusTexto(null)
        setMensagens(m => [...m, { id: novoId(), papel: 'assistente', texto: 'Parei de esperar esta resposta. O que já rodou fica na auditoria.' }])
      }}
    />
  )
}
