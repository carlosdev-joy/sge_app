// Tela `/agentes` (F3 da spec docs/spec-agentes-datastage.md).
//
// Container: é daqui que saem as chamadas de API; os componentes em
// `components/agentes/` só desenham. Sem subrotas — agente e conversa vão em
// query (`?agente=&conversa=`), como a spec define.
//
// Três estados que a tela precisa distinguir, e que o critério 1 da F3
// verifica: (a) SEM grant nenhum, o catálogo volta VAZIO e isso não é erro —
// é o estado normal antes de o admin liberar o primeiro agente, e merece uma
// explicação, não um 403 em branco; (b) com grant, mas com a sonda do gateway
// impeditiva, a tela abre e explica o motivo sem deixar conversar; (c) tudo
// certo, conversa liberada.
import { useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Bot, ClipboardCheck, History, MessageSquarePlus } from 'lucide-react'
import type { ReactNode } from 'react'
import { apiFetch } from '../lib/api'
import type {
  AgenteCatalogo, ArtefatoFerramenta, CatalogoResposta, ConversaDetalhe, DecisaoProposta, EstadoSonda,
  MensagemChat, PropostaAgente, RespostaConversa, StatusAgentes,
} from '../lib/agentes'
import { SONDA, aplicarDecisao, chaveDaConversa, codigoDoErro, mensagemDeErro } from '../lib/agentes'
import { conversarPorStream, rotaStreamAusente } from '../lib/agentesStream'
import { HistoricoConversas } from '../components/agentes/HistoricoConversas'
import { AvisoSonda } from '../components/agentes/AvisoSonda'
import { ChatAgente } from '../components/agentes/ChatAgente'
import { CuradoriaAprendizados } from '../components/agentes/CuradoriaAprendizados'
import { GrafoJobAgente } from '../components/agentes/GrafoJobAgente'
import { IndicadorProjeto } from '../components/agentes/IndicadorProjeto'
import { toast } from '../components/ui/Toast'

interface ConversaGuardada {
  conversa_id: string
  projeto: string | null
  mensagens: MensagemChat[]
}

function lerGuardada(agenteId: string): ConversaGuardada | null {
  try {
    const cru = localStorage.getItem(chaveDaConversa(agenteId))
    if (!cru) return null
    const dado = JSON.parse(cru) as ConversaGuardada
    if (!dado?.conversa_id || !Array.isArray(dado.mensagens)) return null
    return dado
  } catch {
    return null  // storage bloqueado/corrompido nunca derruba a tela
  }
}

function guardar(agenteId: string, dado: ConversaGuardada) {
  try {
    localStorage.setItem(chaveDaConversa(agenteId), JSON.stringify(dado))
  } catch {
    /* cota/modo privado: a conversa segue no servidor, só não sobrevive ao F5 */
  }
}

/**
 * O par (pipeline, job) mais recente entre os artefatos — é o que permite
 * abrir o grafo. `GET /lineage/isx/job` precisa dos DOIS; um artefato que só
 * tenha `job_name` (o agente resolveu o projeto, mas o job não está mapeado
 * em nenhum pipeline) não dá para plotar, e aí o botão nem aparece.
 */
function jobPlotavel(mensagens: MensagemChat[]): { pipeline: string; job: string } | null {
  for (let i = mensagens.length - 1; i >= 0; i--) {
    const arts = mensagens[i].artefatos
    if (!arts) continue
    for (let j = arts.length - 1; j >= 0; j--) {
      const args = (arts[j] as ArtefatoFerramenta).args ?? {}
      const pipeline = typeof args.pipeline_name === 'string' ? args.pipeline_name.trim() : ''
      const job = typeof args.job_name === 'string' ? args.job_name.trim() : ''
      if (pipeline && job) return { pipeline, job }
    }
  }
  return null
}

/**
 * Botão da barra do topo (curadoria, histórico, nova conversa): mesmo tamanho,
 * ícone + rótulo FIXO — o estado não troca o texto (antes: "histórico" ↔
 * "ocultar histórico"), ele aparece no destaque e em `aria-pressed`, que o
 * leitor de tela anuncia. Botão sem `ativo` (nova conversa) é ação simples,
 * sem `aria-pressed`. Só tokens do tema + o azul da marca com par escuro.
 */
function BotaoBarra({ icone, rotulo, ativo, onClick, desabilitado, dica, dados }: {
  icone: ReactNode
  rotulo: string
  ativo?: boolean
  onClick: () => void
  desabilitado?: boolean
  dica?: string
  dados: string
}) {
  const alternavel = ativo !== undefined
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={desabilitado}
      aria-pressed={alternavel ? ativo : undefined}
      title={dica}
      data-agentes-botao={dados}
      className={`inline-flex items-center gap-1.5 h-8 px-3 rounded-md border text-[13px] font-medium
                  transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#1A5FA8]
                  disabled:opacity-50 disabled:cursor-not-allowed
                  ${ativo
                    ? 'border-[#1A5FA8] bg-[#1A5FA8]/10 text-[#1A5FA8] dark:border-blue-400 dark:bg-blue-400/15 dark:text-blue-300'
                    : 'border-edge bg-panel text-ink hover:bg-canvas'}`}
    >
      {icone}
      {rotulo}
    </button>
  )
}

let seq = 0
const novoId = () => `m${Date.now()}_${seq++}`

/**
 * A conversa com UM agente. Montado com `key={agente.id}`, o que faz o React
 * descartar e recriar todo este estado ao trocar de agente — em vez de um
 * `useEffect` que chamaria cinco `setState` em cascata só para zerar tudo
 * (é o "you might not need an effect": resetar estado ao mudar de entrada é
 * trabalho de `key`, não de efeito). O estado inicial vem do localStorage no
 * inicializador preguiçoso do `useState`, uma vez, sem render extra.
 */
function PainelConversa({ agente, sonda, cadastroTexto, onRecarregarSonda, recarregandoSonda }: {
  agente: AgenteCatalogo
  sonda?: EstadoSonda
  cadastroTexto?: string | null
  onRecarregarSonda: () => void
  recarregandoSonda: boolean
}) {
  const guardada = useMemo(() => lerGuardada(agente.id), [agente.id])
  const [mensagens, setMensagens] = useState<MensagemChat[]>(() => guardada?.mensagens ?? [])
  const [projeto, setProjeto] = useState<string | null>(() => guardada?.projeto ?? null)
  const [conversaId, setConversaId] = useState<string | null>(() => guardada?.conversa_id ?? null)
  const [texto, setTexto] = useState('')
  const [enviando, setEnviando] = useState(false)
  // Frase de progresso da rodada em curso (evento `status` do stream).
  const [statusTexto, setStatusTexto] = useState<string | null>(null)
  const [grafoAberto, setGrafoAberto] = useState(false)
  const [stageSel, setStageSel] = useState<string | null>(null)
  const [historicoAberto, setHistoricoAberto] = useState(false)
  const [curadoriaAberta, setCuradoriaAberta] = useState(false)
  // Curadoria e histórico se EXCLUEM: a curadoria ocupa o lugar do chat E do
  // histórico, então os dois "ligados" deixavam o histórico destacado na
  // barra e escondido atrás da curadoria (relato de produção de 23/09).
  // Abrir um fecha o outro — o botão destacado é sempre o painel na tela.
  function alternarCuradoria() {
    const abrir = !curadoriaAberta
    setCuradoriaAberta(abrir)
    if (abrir) setHistoricoAberto(false)
  }
  function alternarHistorico() {
    const abrir = !historicoAberto
    setHistoricoAberto(abrir)
    if (abrir) setCuradoriaAberta(false)
  }
  const [retomando, setRetomando] = useState(false)
  const [decidindo, setDecidindo] = useState<ReadonlySet<number>>(() => new Set())
  // Descarta resposta que chega DEPOIS de "nova conversa" — mesmo cuidado do
  // `pedidoRef` do MaestroChat.
  const pedidoRef = useRef(0)

  const infoSonda = sonda ? SONDA[sonda] : null
  const bloqueado = infoSonda?.bloqueia ?? false

  async function enviar(mensagemBruta?: string) {
    const conteudo = (mensagemBruta ?? texto).trim()
    if (!conteudo || enviando) return
    // Assumir o pedido INVALIDA a retomada em voo — e quem invalida tem de
    // limpar o estado dela, senão `retomando` fica preso em `true` e todo
    // clique futuro no histórico é descartado em silêncio (`if (retomando)
    // return`). Achado da revisão adversarial da F4.
    const meuPedido = ++pedidoRef.current
    setRetomando(false)
    setMensagens(m => [...m, { id: novoId(), papel: 'user', texto: conteudo }])
    setTexto('')
    setEnviando(true)
    setStatusTexto(null)
    const corpo = JSON.stringify(conversaId
      ? { mensagem: conteudo, conversa_id: conversaId }
      : { mensagem: conteudo })
    const abandonado = () => pedidoRef.current !== meuPedido
    try {
      let r: RespostaConversa | null
      try {
        // Progresso em tempo real (spec de feedback). Se a API ainda não
        // tem a rota de stream (a `dist/` subiu antes dela), cai no JSON.
        r = await conversarPorStream(agente.id, corpo,
          t => { if (!abandonado()) setStatusTexto(t) }, abandonado)
      } catch (e) {
        if (!rotaStreamAusente(e)) throw e
        r = await apiFetch<RespostaConversa>(`/agentes/${agente.id}/conversar`, { method: 'POST', body: corpo })
      }
      if (r === null || abandonado()) return  // conversa trocou no meio
      setConversaId(r.conversa_id)
      setProjeto(r.projeto)
      setMensagens(m => {
        const novas = [...m, {
          id: novoId(), papel: 'assistant' as const, texto: r.texto,
          artefatos: r.artefatos, status: r.status,
          propostas: r.propostas?.length ? r.propostas : undefined,
          propostasRecusadas: r.propostas_recusadas?.length ? r.propostas_recusadas : undefined,
          aprendizadosUsados: r.aprendizados_usados?.length ? r.aprendizados_usados.map(a => a.titulo) : undefined,
          aprendizadosSugeridos: r.aprendizados_sugeridos?.length ? r.aprendizados_sugeridos : undefined,
          duracaoMs: typeof r.duracao_ms === 'number' ? r.duracao_ms : undefined,
        }]
        guardar(agente.id, { conversa_id: r.conversa_id, projeto: r.projeto, mensagens: novas })
        return novas
      })
    } catch (e) {
      if (pedidoRef.current !== meuPedido) return
      const msg = mensagemDeErro(e, 'Não foi possível falar com o agente agora.')
      toast.error(msg)
      setMensagens(m => [...m, { id: novoId(), papel: 'assistant', texto: msg }])
    } finally {
      if (pedidoRef.current === meuPedido) {
        setEnviando(false)
        setStatusTexto(null)
      }
    }
  }

  async function retomar(id: string) {
    if (retomando) return
    // Espelho do que `novaConversa` faz: incrementar `pedidoRef` invalida a
    // resposta de um `enviar` em voo, e o `finally` dele NÃO vai rodar
    // (`pedidoRef.current !== meuPedido`). Sem este `setEnviando(false)`,
    // `enviando` fica `true` para sempre: o campo e o Enter param, a bolha
    // "está consultando…" congela, e a conversa recém-retomada nunca pode
    // ser continuada — justamente a função central da F4. Achado da revisão
    // adversarial (o `novaConversa` já tinha a compensação; o `retomar`
    // copiou o incremento e esqueceu dela).
    const meuPedido = ++pedidoRef.current
    setEnviando(false)
    setStatusTexto(null)
    setRetomando(true)
    try {
      const d = await apiFetch<ConversaDetalhe>(`/agentes/conversas/${encodeURIComponent(id)}`)
      if (pedidoRef.current !== meuPedido) return
      // `em` só nas do ASSISTENTE: é a resposta que pode ter envelhecido —
      // a pergunta do usuário não "vence" (critério 3 da F4).
      const msgs: MensagemChat[] = d.mensagens.map((m, i) => ({
        id: `${id}_${i}`,
        papel: m.papel,
        texto: m.conteudo,
        artefatos: m.papel === 'assistant' ? m.artefatos : undefined,
        status: m.status ?? undefined,
        em: m.papel === 'assistant' ? m.criada_em : undefined,
        propostas: m.papel === 'assistant' && m.propostas?.length ? m.propostas : undefined,
        duracaoMs: m.papel === 'assistant' && typeof m.duracao_ms === 'number' ? m.duracao_ms : undefined,
      }))
      setMensagens(msgs)
      setConversaId(d.conversa_id)
      setProjeto(d.projeto)
      setGrafoAberto(false)
      setStageSel(null)
      guardar(agente.id, { conversa_id: d.conversa_id, projeto: d.projeto, mensagens: msgs })
    } catch (e) {
      if (pedidoRef.current !== meuPedido) return
      // `conversa_expirada` é o caso NORMAL de quem guardou um link de mais
      // de 30 dias — merece a explicação, não "erro ao carregar".
      const expirou = codigoDoErro(e) === 'conversa_expirada'
      toast.error(expirou
        ? 'Essa conversa passou dos 30 dias e não está mais disponível.'
        : mensagemDeErro(e, 'Não foi possível abrir a conversa.'))
    } finally {
      if (pedidoRef.current === meuPedido) setRetomando(false)
    }
  }

  // F5: aprovar/recusar uma proposta. Independe de `pedidoRef` de propósito:
  // a decisão é sobre UMA proposta que já está gravada no servidor, e vale
  // mesmo que o usuário troque de conversa enquanto ela é salva — por isso
  // `aplicarDecisao` procura a proposta pelo id em vez de assumir a conversa
  // aberta (se ela não estiver mais na tela, nada muda aqui, e a conversa
  // retomada depois já vem com o estado atual do servidor).
  async function decidir(id: number, decisao: DecisaoProposta) {
    if (decidindo.has(id)) return
    setDecidindo(s => new Set(s).add(id))
    const aplicar = (p: PropostaAgente) => setMensagens(m => {
      const novas = aplicarDecisao(m, p)
      if (novas === m) return m  // a proposta não está na conversa aberta agora
      // `conversa_id`/`projeto` do que JÁ está guardado, não do fechamento
      // desta função: eles podem ter mudado enquanto a decisão era salva, e
      // o guardado é sempre o par das mensagens que estão na tela.
      const atual = lerGuardada(agente.id)
      if (atual) guardar(agente.id, { ...atual, mensagens: novas })
      return novas
    })
    try {
      const r = await apiFetch<{ proposta: PropostaAgente }>(`/agentes/propostas/${id}/decidir`, {
        method: 'POST',
        body: JSON.stringify({ decisao }),
      })
      aplicar(r.proposta)
      toast.success(decisao === 'aprovar' ? 'Proposta aprovada e registrada.' : 'Proposta recusada.')
    } catch (e) {
      // 409 `proposta_ja_decidida` traz a proposta como está no servidor
      // (outra aba decidiu antes): sincroniza o cartão em vez de deixá-lo
      // pedindo uma decisão que já não cabe.
      const detalhe = (e as { detail?: { proposta?: PropostaAgente } } | null)?.detail
      if (codigoDoErro(e) === 'proposta_ja_decidida' && detalhe?.proposta) aplicar(detalhe.proposta)
      toast.error(mensagemDeErro(e, 'Não foi possível registrar a decisão.'))
    } finally {
      setDecidindo(s => {
        const n = new Set(s)
        n.delete(id)
        return n
      })
    }
  }

  function novaConversa() {
    // Mesma regra de `enviar`/`retomar`: incrementar o pedido invalida o
    // que estiver em voo, e o `finally` do outro não roda — então quem
    // incrementa limpa as DUAS flags. Faltava `setRetomando(false)` aqui:
    // clicar em "nova conversa" durante uma retomada deixava `retomando`
    // preso e o histórico parava de responder.
    pedidoRef.current++
    setMensagens([])
    setProjeto(null)
    setConversaId(null)
    setGrafoAberto(false)
    setStageSel(null)
    setEnviando(false)
    setStatusTexto(null)
    setRetomando(false)
    try { localStorage.removeItem(chaveDaConversa(agente.id)) } catch { /* ignore */ }
  }

  const plotavel = useMemo(() => jobPlotavel(mensagens), [mensagens])

  return (
    <>
      <div role="group" aria-label="Ações da conversa" className="flex flex-wrap justify-end gap-2 -mt-1"
           data-agentes-barra>
        {agente.curador && (
          // Só para quem tem `agente_curador` (o catálogo diz); a API recusa
          // os demais com 403 de qualquer jeito (critério 4 da F6).
          <BotaoBarra
            icone={<ClipboardCheck className="w-4 h-4" aria-hidden="true" />}
            rotulo="Curadoria"
            ativo={curadoriaAberta}
            onClick={alternarCuradoria}
            dados="curadoria"
          />
        )}
        <BotaoBarra
          icone={<History className="w-4 h-4" aria-hidden="true" />}
          rotulo="Histórico"
          ativo={historicoAberto}
          onClick={alternarHistorico}
          dados="historico"
        />
        <BotaoBarra
          icone={<MessageSquarePlus className="w-4 h-4" aria-hidden="true" />}
          rotulo="Nova conversa"
          onClick={novaConversa}
          // Sempre na barra (a largura não pula); sem mensagens não há o que recomeçar.
          desabilitado={mensagens.length === 0}
          dica={mensagens.length === 0 ? 'A conversa ainda está vazia' : 'Começar uma conversa do zero'}
          dados="nova"
        />
      </div>

      {sonda && (
        <AvisoSonda
          estado={sonda}
          cadastroTexto={cadastroTexto}
          onTentarDeNovo={onRecarregarSonda}
          recarregando={recarregandoSonda}
        />
      )}

      <div className="flex flex-wrap items-center justify-between gap-2">
        <IndicadorProjeto
          projeto={projeto}
          desabilitado={bloqueado || enviando}
          onTrocar={nome => enviar(`Usar o projeto DataStage ${nome}.`)}
        />
        {plotavel && (
          <button
            type="button"
            onClick={() => setGrafoAberto(v => !v)}
            className="text-[13px] text-[#1A5FA8] dark:text-blue-400 hover:underline"
          >
            {grafoAberto ? 'ocultar grafo' : `ver grafo de ${plotavel.job}`}
          </button>
        )}
      </div>

      {grafoAberto && plotavel && (
        <GrafoJobAgente
          pipeline={plotavel.pipeline}
          job={plotavel.job}
          stageSel={stageSel}
          onSelecionarStage={setStageSel}
          onFechar={() => setGrafoAberto(false)}
        />
      )}

      {curadoriaAberta && agente.curador ? (
        <CuradoriaAprendizados onFechar={() => setCuradoriaAberta(false)} />
      ) : (
      <div className="flex-1 min-h-0 flex flex-col sm:flex-row gap-3">
        {historicoAberto && (
          <HistoricoConversas
            agenteId={agente.id}
            conversaAtual={conversaId}
            onRetomar={id => { void retomar(id) }}
            onFechar={() => setHistoricoAberto(false)}
          />
        )}
        <div className="flex-1 min-w-0 min-h-0 bg-canvas rounded-lg">
        <ChatAgente
          mensagens={mensagens}
          valor={texto}
          onValor={setTexto}
          onEnviar={() => enviar()}
          enviando={enviando}
          statusTexto={statusTexto}
          bloqueado={bloqueado}
          motivoBloqueio={infoSonda?.bloqueia ? infoSonda.titulo : undefined}
          nomeAgente={agente.nome}
          onDecidir={(id, d) => { void decidir(id, d) }}
          decidindo={decidindo}
        />
        </div>
      </div>
      )}
    </>
  )
}

export default function Agentes() {
  const [params, setParams] = useSearchParams()
  const agenteParam = params.get('agente')

  const catalogo = useQuery<CatalogoResposta>({
    queryKey: ['agentes-catalogo'],
    queryFn: () => apiFetch('/agentes/catalogo'),
  })
  const status = useQuery<StatusAgentes>({
    queryKey: ['agentes-status'],
    queryFn: () => apiFetch('/agentes/status'),
    retry: false,
  })

  const agentes = useMemo(() => catalogo.data?.agentes ?? [], [catalogo.data])
  const agente = useMemo(
    () => agentes.find(a => a.id === agenteParam) ?? agentes[0] ?? null,
    [agentes, agenteParam])

  if (catalogo.isLoading) {
    return <p className="text-sm text-dim p-6">Carregando agentes…</p>
  }

  // Critério 1 da F3: sem grant o catálogo volta VAZIO — e isso é o estado
  // normal antes de o admin liberar o primeiro agente, não um erro. A tela
  // abre e explica; quem chamar a API direto é que leva 403.
  if (!agente) {
    return (
      <div className="p-6 max-w-2xl" data-agentes-vazio>
        <div className="bg-panel border border-edge rounded-lg p-6 shadow-sm text-center">
          <Bot className="w-8 h-8 mx-auto text-dim" aria-hidden="true" />
          <h2 className="text-base font-semibold text-ink mt-3">Nenhum agente liberado para você</h2>
          <p className="text-sm text-dim mt-2">
            Os agentes de IA são liberados usuário a usuário pelo administrador. Se você precisa
            usar o agente de mapeamento DataStage, peça a liberação em Admin › Agentes.
          </p>
          {catalogo.isError && (
            <p className="text-sm text-dim mt-3">
              {mensagemDeErro(catalogo.error, 'Não foi possível carregar o catálogo de agentes.')}
            </p>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-6 flex flex-col gap-4 h-[calc(100vh-7rem)] min-h-0">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-lg font-semibold text-ink flex items-center gap-2">
            <Bot className="w-5 h-5 text-[#1A5FA8] dark:text-blue-400" aria-hidden="true" />
            {agente.nome}
          </h1>
          <p className="text-sm text-dim mt-0.5 max-w-2xl">{agente.descricao}</p>
        </div>
        {agentes.length > 1 && (
          <label className="text-sm text-dim flex items-center gap-2">
            Agente
            <select
              value={agente.id}
              onChange={e => {
                const p = new URLSearchParams(params)
                p.set('agente', e.target.value)
                setParams(p, { replace: true })
              }}
              className="rounded border border-edge bg-panel text-ink px-2 py-1 text-sm
                         focus:outline-none focus:ring-2 focus:ring-[#1A5FA8]"
            >
              {agentes.map(a => <option key={a.id} value={a.id}>{a.nome}</option>)}
            </select>
          </label>
        )}
      </header>

      {/* `key`: trocar de agente descarta a conversa anterior por completo. */}
      <PainelConversa
        key={agente.id}
        agente={agente}
        sonda={status.data?.estado}
        cadastroTexto={catalogo.data?.cadastro_texto}
        onRecarregarSonda={() => { void status.refetch() }}
        recarregandoSonda={status.isFetching}
      />
    </div>
  )
}
