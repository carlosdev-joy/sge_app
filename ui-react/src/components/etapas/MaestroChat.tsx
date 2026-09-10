// O Maestro na seção "Parâmetros do job" (Etapas e Fluxos, via JobTypeFields):
// o botão com o avatar e, aberto, o painel flutuante — estado da conversa,
// chamadas a POST /maestro/conversar e GET /maestro/historico, e o "Aplicar
// no editor" (que só entrega as linhas ao pai: quem mescla e salva é ele).
//
// O painel vai por PORTAL para o body, com `data-modal-exempt`: o Modal de
// Etapas prende o foco dentro dele (ui/overlay.ts) e só solta para overlays
// que se marcam assim. Escape fecha o chat e NÃO sobe ao document (o Modal
// escuta Escape lá) — o usuário fecha o chat, não a etapa. Não usa
// `useOverlay`: o chat é flutuante e o usuário precisa continuar editando a
// etapa com ele aberto.
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { apiFetch, type ErroApi } from '../../lib/api'
import {
  MAESTRO_MAX_MENSAGEM, MAESTRO_NOME, chaveDaConversa, contextoDoEditor, esquecerConversa, guardarConversa,
  historicoParaEnvio, lerConversaGuardada, mensagemDeBoasVindas, mensagemDeErro, novoConversaId, propostaParaEditor,
  type JobParamLinha, type MaestroHistoricoConversa, type MaestroMensagem, type MaestroNivel, type MaestroResposta,
} from '../../lib/maestro'
import { Button } from '../ui/Button'
import { toast } from '../ui/Toast'
import { MaestroAvatar } from './MaestroAvatar'
import { MaestroPainel } from './MaestroPainel'

export interface MaestroChatProps {
  pipeline?: string
  jobName?: string
  /** As linhas ATUAIS do editor (contexto do pedido; sem valor Encrypted ao sair). */
  params: JobParamLinha[]
  /** A data do "Simular com a referência" da seção — a prévia do Maestro usa a mesma. */
  referencia: string
  sugestoes: string[]
  /** Recebe as linhas da proposta já como draft do editor; o pai mescla com as suas. */
  onAplicar: (novos: JobParamLinha[]) => void
  compact?: boolean
  /** 'etapa' (padrão) ou 'pipeline' (defaults do wizard: herança para as etapas). */
  nivel?: MaestroNivel
}

export function MaestroChat({ pipeline, jobName, params, referencia, sugestoes, onAplicar, compact, nivel = 'etapa' }: MaestroChatProps) {
  // A conversa é guardada por chave (nível + pipeline + job) fora do
  // componente: trocar de passo no wizard (ou reabrir o mesmo cadastro) volta
  // com a conversa e a proposta ainda não aplicada, em vez de zerar.
  const chave = chaveDaConversa(nivel, pipeline, jobName)
  const guardada = lerConversaGuardada(chave)
  const [aberto, setAberto] = useState(guardada?.aberto ?? false)
  const [conversaId, setConversaId] = useState(() => guardada?.conversaId ?? novoConversaId())
  const [mensagens, setMensagens] = useState<MaestroMensagem[]>(() => guardada?.mensagens ?? [mensagemDeBoasVindas(nivel)])
  const [entrada, setEntrada] = useState('')
  const [carregando, setCarregando] = useState(false)
  const [historico, setHistorico] = useState<MaestroHistoricoConversa[] | null>(null)
  const [historicoCarregando, setHistoricoCarregando] = useState(false)
  const rolagemRef = useRef<HTMLDivElement>(null)
  const proximoId = useRef((guardada?.mensagens ?? []).reduce((m, x) => Math.max(m, x.id), 0) + 1)

  useEffect(() => {
    guardarConversa(chave, { conversaId, mensagens, aberto })
  }, [chave, conversaId, mensagens, aberto])
  // Pedido vigente: uma resposta que chega depois de "Nova conversa" / abrir
  // outra conversa (ou um histórico pedido e já fechado) é descartada em vez
  // de cair na conversa errada (achados 3 e 4 da revisão adversarial da F2).
  const pedidoRef = useRef(0)
  const historicoPedidoRef = useRef(0)

  useEffect(() => {
    const el = rolagemRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [mensagens, carregando, aberto])

  function novaMensagem(m: Omit<MaestroMensagem, 'id'>): MaestroMensagem {
    return { ...m, id: proximoId.current++ }
  }

  async function enviar(texto?: string) {
    const pergunta = (texto ?? entrada).trim()
    if (!pergunta || carregando) return
    if (pergunta.length > MAESTRO_MAX_MENSAGEM) {
      toast.error(`A mensagem passa de ${MAESTRO_MAX_MENSAGEM} caracteres.`)
      return
    }
    const minha = novaMensagem({ papel: 'user', texto: pergunta })
    const historicoAtual = [...mensagens, minha]
    const meuPedido = ++pedidoRef.current
    setMensagens(historicoAtual)
    setEntrada('')
    setCarregando(true)
    try {
      const r = await apiFetch<MaestroResposta>('/maestro/conversar', {
        method: 'POST',
        body: JSON.stringify({
          conversa_id: conversaId,
          mensagens: historicoParaEnvio(historicoAtual),
          contexto: contextoDoEditor(pipeline, jobName, params, referencia, nivel),
        }),
      })
      if (pedidoRef.current !== meuPedido) return   // a conversa mudou enquanto esperava
      if (r.conversa_id && r.conversa_id !== conversaId) setConversaId(r.conversa_id)
      const { conversa_id: _cid, resposta, ...resultado } = r
      void _cid
      setMensagens(prev => [...prev, novaMensagem({ papel: 'assistant', texto: resposta || '(sem texto)', resultado })])
    } catch (e: unknown) {
      if (pedidoRef.current !== meuPedido) return
      const texto = mensagemDeErro(e as ErroApi)
      setMensagens(prev => [...prev, novaMensagem({ papel: 'assistant', texto, erro: true })])
      toast.error(texto)
    } finally {
      if (pedidoRef.current === meuPedido) setCarregando(false)
    }
  }

  function aplicar(m: MaestroMensagem) {
    const itens = m.resultado?.proposta?.params
    if (!itens?.length || m.aplicada) return
    onAplicar(propostaParaEditor(itens))
    setMensagens(prev => prev.map(x => (x.id === m.id ? { ...x, aplicada: true } : x)))
  }

  function novaConversa() {
    pedidoRef.current++            // resposta em voo, se houver, é descartada
    setCarregando(false)
    esquecerConversa(chave)
    setConversaId(novoConversaId())
    setMensagens([mensagemDeBoasVindas(nivel)])
    setEntrada('')
    setHistorico(null)
  }

  async function alternarHistorico() {
    if (historico) {
      historicoPedidoRef.current++   // um fetch em voo não reabre a lista
      setHistorico(null)
      setHistoricoCarregando(false)
      return
    }
    const meuPedido = ++historicoPedidoRef.current
    setHistorico([])
    setHistoricoCarregando(true)
    try {
      const d = await apiFetch<{ conversas: MaestroHistoricoConversa[] }>('/maestro/historico')
      if (historicoPedidoRef.current !== meuPedido) return
      setHistorico(d.conversas ?? [])
    } catch (e: unknown) {
      if (historicoPedidoRef.current !== meuPedido) return
      toast.error(mensagemDeErro(e as ErroApi))
      setHistorico(null)
    } finally {
      if (historicoPedidoRef.current === meuPedido) setHistoricoCarregando(false)
    }
  }

  function abrirConversa(c: MaestroHistoricoConversa) {
    pedidoRef.current++
    setCarregando(false)
    const lidas: MaestroMensagem[] = [mensagemDeBoasVindas(nivel)]
    for (const r of c.rodadas) {
      lidas.push(novaMensagem({ papel: 'user', texto: r.mensagem }))
      if (r.resposta) lidas.push(novaMensagem({ papel: 'assistant', texto: r.resposta }))
    }
    setConversaId(c.conversa_id)
    setMensagens(lidas)
    setHistorico(null)
  }

  const painel = aberto && typeof document !== 'undefined' ? createPortal(
    <MaestroPainel
      mensagens={mensagens}
      carregando={carregando}
      sugestoes={sugestoes}
      entrada={entrada}
      onEntrada={setEntrada}
      onEnviar={() => { void enviar() }}
      onSugestao={s => { void enviar(s) }}
      onAplicar={aplicar}
      onFechar={() => setAberto(false)}
      onNovaConversa={novaConversa}
      historico={historico}
      historicoCarregando={historicoCarregando}
      onHistorico={() => { void alternarHistorico() }}
      onAbrirConversa={abrirConversa}
      referencia={referencia}
      nivel={nivel}
      rolagemRef={rolagemRef}
      onKeyDown={e => {
        if (e.key === 'Escape') { e.stopPropagation(); setAberto(false) }
      }}
    />,
    document.body,
  ) : null

  return (
    <>
      <Button size="sm" variant="ghost" onClick={() => setAberto(v => !v)}
              title={`Descreva o cenário e o ${MAESTRO_NOME} diz como preencher cada parâmetro`}
              aria-expanded={aberto}
              className={compact ? 'text-[11px]' : ''}
              data-maestro-botao>
        <MaestroAvatar size={compact ? 16 : 18} estado={carregando ? 'pensando' : 'ouvindo'} />
        {MAESTRO_NOME}
      </Button>
      {painel}
    </>
  )
}
