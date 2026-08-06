import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'
import { normalizeBusca } from '../lib/busca'
import { useAuthStore } from '../store/auth'
import { PageSpinner } from '../components/ui/Spinner'
import { Button } from '../components/ui/Button'
import { Modal } from '../components/ui/Modal'
import { Input, Select, Textarea } from '../components/ui/Input'
import { Autocomplete } from '../components/ui/Autocomplete'
import { toast } from '../components/ui/Toast'
import { CritBadge } from '../components/malhas/CritBadge'
import { MalhaEditor } from '../components/malhas/MalhaEditor'
import {
  estiloStatus, resumoCorrida, resumoEsperada, CORRIDA_INTERROMPIDA,
} from '../components/malhas/statusExecucao'
// F9 (§9.9): a pílula de estado e o bloco de progresso, os dois compartilhados
// com a faixa do painel (F10) e com o Dashboard (F11) — uma fonte, três
// superfícies.
import { CorridaBadge } from '../components/malhas/CorridaBadge'
import { CorridaProgresso } from '../components/malhas/CorridaProgresso'
// F4 (spec-malha-execucao §9.1): o relógio LOCAL do carimbo de frescor e do
// decorrido — nunca `apurado_em`, que é o relógio do BANCO (Decisão 60).
import { useDecorrido } from '../components/malhas/useDecorrido'
import { frescor } from '../components/malhas/tempoCorrida'
import type { CorridaApi, CorridaEsperadaApi } from '../types'
import {
  RefreshCw, Network, X, Search, HelpCircle, Play,
  Plus, Edit, Users, Power, Trash2, AlertTriangle, Boxes,
} from 'lucide-react'

// O inventário de pipelines (Cards/Diagrama + CSV) MIGROU para
// components/malhas/CatalogoPipelines.tsx e vive em Catálogo & Lineage
// (/governanca) desde a F9 — decisão do usuário na spec §8: esta tela exibe
// SÓ malhas. O DependencyGraph SVG legado morreu na realocação (spec §4b).

// ─── Malhas (F7) — agrupadoras de pipelines ──────────────────────────────────
// Malha = agrupador nomeado de pipelines (análogo da sequence mestre do
// DataStage / SMART Folder do Control-M). Nesta fase existe a entidade, os
// membros e a lista; o diagrama de montagem (MalhaEditor) chega na F8.

// F8 (spec-malha-execucao §6.9/#16 e #17) — o aviso que os gestos de EDIÇÃO
// passam a devolver quando há ciclo em voo.
//
// O snapshot da corrida congela membros e regra de fechamento na abertura, então
// editar durante o ciclo é legítimo e vale do PRÓXIMO em diante. O que faltava
// era dizer isso: sem a frase, quem adiciona um membro às 3h não o vê no
// denominador do painel e conclui que a tela quebrou.
//
// Chave OPCIONAL de propósito: malha sem corrida aberta (e API anterior à F8)
// não a manda, e o gesto se comporta exatamente como antes.
interface RespostaComAvisoDeCiclo { aviso_ciclo?: string }

function avisarCiclo(r: RespostaComAvisoDeCiclo | undefined) {
  // `info`, não `error`: o gesto DEU CERTO — o que muda é o alcance dele no
  // tempo. Pintar de vermelho ensinaria o operador a temer uma edição legítima.
  if (r?.aviso_ciclo) toast.info(r.aviso_ciclo)
}

// Última corrida registrada entre os pipelines da malha. `em` é o INÍCIO da
// corrida (a API cai em criado_em quando ela ainda não partiu) — nunca a
// data_referencia, que é o dia de PROCESSAMENTO e pode estar longe do relógio.
interface UltimaExecucao {
  em: string | null
  status: string
  pipeline: string
}

// Resumo do horário de disparo. `origem` diz de ONDE ele saiu, e é o que
// permite o tooltip ser honesto: 'malha' = agendamento próprio (nó Início),
// 'membros' = derivado dos pipelines que disparam sozinhos, 'nenhum' = a
// malha só anda por disparo manual.
interface Gatilho {
  origem: 'malha' | 'membros' | 'nenhum'
  resumo: string
  horario: string | null
  qtd_pipelines: number
  horarios: string[]
  detalhes: { pipeline: string; resumo: string; horario: string }[]
}

interface ApiMalha {
  malha_name: string
  descricao: string | null
  ativo: 0 | 1 | boolean
  criado_em: string | null
  qtd_pipelines: number
  qtd_ativos: number
  criticidade: string | null // agregada = a mais alta entre os membros
  // Aditivos do card. Opcionais de propósito: numa API antiga (deploy parcial
  // do front) a chave não vem e a linha correspondente some, em vez de a tela
  // exibir "undefined etapas".
  qtd_etapas?: number
  ultima_execucao?: UltimaExecucao | null
  gatilho?: Gatilho | null
  // Há agendamento salvo na malha que NÃO está vigente (o Início foi excluído,
  // ou ainda não foi desenhado): nenhuma raiz o carrega, então ele não é
  // gatilho — mas continua guardado e volta a valer quando o Início religar.
  agendamento_guardado?: boolean
  // F4 — a CORRIDA (o ciclo da malha). É ELA que responde "a malha rodou?".
  // Opcional, e a ausência é o contrato (Decisão 41): API anterior à fase,
  // banco sem a 085 e malha sem ciclo nenhum degradam no MESMO lugar, o
  // fallback "(membro mais recente)" logo abaixo. Nunca vem `null`.
  corrida?: CorridaApi
  // F9 (Decisão 58) — a corrida que NÃO ABRIU: o gatilho venceu e nenhuma
  // corrida nasceu. Chave ausente = não há o que acusar (o caso normal), e ela
  // só chega para malha ATIVA que já teve corrida antes — o que mantém a lista
  // muda no dia do deploy, com o interruptor ainda em 0.
  corrida_esperada?: CorridaEsperadaApi
}

interface MalhasResponse {
  malhas: ApiMalha[]
  // Deploy parcial (API nova + migration 070 não aplicada): a API degrada
  // devolvendo lista vazia + esta flag, em vez de 500.
  migration_pendente?: boolean
  // F4: a 085 não está neste banco. NÃO é o que o card testa para decidir
  // renderizar (isso é a ausência da chave `corrida`) — é o que permite DIZER
  // ao operador que falta informação, em vez de degradar em silêncio.
  migration_085_pendente?: boolean
  // F9: esta API sabe responder sobre corrida. Marcador POSITIVO de versão, e
  // ele existe por causa da janela de deploy: o `dist/` sobe na etapa 3 e a
  // `api/` só na 7, então por alguns minutos o front novo fala com a API
  // velha — que não manda `corrida` nem flag nenhuma. Sem esta chave, o front
  // não distinguiria "esta malha não tem ciclo" (silêncio correto no dia do
  // deploy) de "esta API não sabe responder" (a hora de dizer que falta
  // informação). Ausente = API anterior à F9.
  corrida_suportada?: boolean
}

interface MalhaMembro {
  pipeline_name: string
  active: 0 | 1 | boolean
  criticidade: string | null
  schedule_type: string | null
  layout_x: number | null
  layout_y: number | null
}

interface MalhaDetalheResponse {
  malha: ApiMalha
  membros: MalhaMembro[]
}

function formataData(iso: string | null): string | null {
  if (!iso) return null
  const d = new Date(iso)
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString('pt-BR')
}

// Data E hora curtas ("03/08 13:47") — o card precisa das duas: só a data não
// distingue duas corridas do mesmo dia, e só a hora esconde que a última foi
// na semana passada. O ano fica no title (formataDataHoraLonga).
function formataDataHora(iso: string | null | undefined): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const dia = d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })
  const hora = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
  return `${dia} ${hora}`
}

function formataDataHoraLonga(iso: string | null | undefined): string | null {
  if (!iso) return null
  const d = new Date(iso)
  return isNaN(d.getTime()) ? iso : d.toLocaleString('pt-BR')
}

// Explicação do gatilho no title — é aqui que a tela para de mentir: o resumo
// curto cabe no card, mas de ONDE ele veio (e quais pipelines disparam) só
// cabe no tooltip.
function tituloGatilho(g: Gatilho): string {
  if (g.origem === 'malha') {
    return `Agendamento da própria malha (nó Início): ${g.resumo}\n`
      + 'Todos os pipelines raiz ligados ao Início disparam neste horário.'
  }
  if (g.origem === 'membros') {
    const linhas = g.detalhes.map(d => `• ${d.pipeline} — ${d.resumo}`).join('\n')
    return `A malha não tem agendamento próprio — o horário é derivado dos `
      + `${g.qtd_pipelines} pipeline(s) que disparam sozinhos:\n${linhas}`
  }
  return 'Nenhum pipeline desta malha dispara sozinho: ela anda por disparo '
    + 'manual ou por dependência de um pipeline de fora.'
}

const AVISO_AGENDA_GUARDADA =
  'Esta malha tem um agendamento salvo que NÃO está em vigor: nenhum pipeline '
  + 'raiz está ligado ao componente Início, então nada dispara por ele. '
  + 'Desenhe o Início e ligue-o às raízes para o agendamento voltar a valer — '
  + 'a configuração continua guardada.'

/** A malha tem algo que ANDA sozinho na tela (Decisão 73)?
 *
 *  Duas coisas andam: a corrida em voo (o `x de y` e o decorrido) e a corrida
 *  que não abriu (o atraso, que cresce a cada minuto). As duas governam o
 *  polling E o alarme de dado velho, e por isso vivem numa função só: separá-las
 *  já produziu o card mais grave da manhã sendo o único a envelhecer em
 *  silêncio, com o relógio congelado no "há 7h12" da abertura da página. */
function emMovimento(m: ApiMalha): boolean {
  return m.corrida?.status === 'ABERTA' || !!m.corrida_esperada
}

// ─── Card de malha (mesma linguagem do PipelineCard) ─────────────────────────

function MalhaCard({ malha, tempo, semDadosDeCorrida, onAcompanhar, onAbrir,
                    onMembros, onRenomear, onToggle }: {
  malha: ApiMalha
  /** Os DOIS instantes do relógio LOCAL (Decisão 60): quando a resposta chegou
   *  e que horas são agora. `apurado_em` (relógio do banco) não participa de
   *  conta nenhuma — no dev ele está 3 h à frente. */
  tempo: { respostaEm: number; agora: number }
  /** O ciclo não está disponível NESTE ambiente — porque a 085 não foi
   *  aplicada, ou porque a API ainda é a anterior a esta fase (a janela entre
   *  as etapas 3 e 7 do deploy). Nos dois casos a frase para o operador é a
   *  mesma, e a degradação é DITA, não só silenciosa. */
  semDadosDeCorrida: boolean
  onAcompanhar: () => void
  onAbrir: () => void
  onMembros: () => void
  onRenomear: () => void
  onToggle: () => void
}) {
  const ativa = !!malha.ativo
  const criado = formataData(malha.criado_em)
  const ultima = malha.ultima_execucao ?? null
  const estilo = ultima ? estiloStatus(ultima.status) : null
  const gatilho = malha.gatilho ?? null
  // ── F4: o bloco da CORRIDA ────────────────────────────────────────────────
  // Até aqui o status do card era `max((momento, pipeline))` entre os membros —
  // "a execução mais recente". Com `CARGA_A` falhando às 03:00 e `CARGA_B`
  // concluindo às 03:40, o card dizia **sucesso · CARGA_B** e o gestor abria a
  // tela às 8h vendo verde numa malha que falhou. Agora quem responde é o
  // CICLO, e a saúde manda na cor enquanto ele está aberto: falha detectada às
  // 03:00 pinta o card de vermelho às 03:00, sem esperar o fechamento —
  // descobrir às 05:00 é depois do SLA.
  const corrida = malha.corrida ?? null
  const resumo = useMemo(
    () => (corrida ? resumoCorrida(corrida, tempo, malha.qtd_pipelines) : null),
    [corrida, tempo, malha.qtd_pipelines])
  // ── F9: a corrida que NÃO ABRIU (Decisão 58) ──────────────────────────────
  // Ela tem PRECEDÊNCIA sobre a corrida anterior no bloco do card, e a razão é
  // a pergunta que o operador faz às 8h: "a madrugada rodou?". Mostrar a
  // corrida de ontem, verde e "concluída", com carimbo de frescor recente, é
  // responder "sim" a uma noite em que nada aconteceu. A anterior não some —
  // vira a linha de baixo, que é o que dá a medida do que se perdeu.
  const esperada = malha.corrida_esperada ?? null
  const previsao = useMemo(
    () => (esperada ? resumoEsperada(esperada, tempo) : null),
    [esperada, tempo])
  return (
    <div className="bg-panel border border-edge rounded-lg px-4 py-3 flex flex-col gap-2 hover:shadow-md hover:border-[#1A5FA8]/40 transition-all">
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`w-2 h-2 rounded-full shrink-0 ${ativa ? 'bg-green-400' : 'bg-slate-400'}`} />
        <span className="font-mono text-sm font-semibold text-ink flex-1 min-w-0 truncate">{malha.malha_name}</span>
        {malha.criticidade && <CritBadge crit={malha.criticidade} />}
        {ativa ? (
          <span className="text-[10px] text-green-600 dark:text-green-400 font-medium">● Ativa</span>
        ) : (
          <span className="text-[10px] text-dim">○ Inativa</span>
        )}
      </div>
      {malha.descricao && (
        <p className="text-[11px] text-dim line-clamp-2">{malha.descricao}</p>
      )}
      <div className="flex flex-col gap-0.5 text-[11px] text-dim">
        <span title="Pipelines membros e o total de etapas (jobs) somando todos eles — a complexidade da malha">
          ⚙ {malha.qtd_pipelines} pipeline{malha.qtd_pipelines !== 1 ? 's' : ''} ({malha.qtd_ativos} ativo{malha.qtd_ativos !== 1 ? 's' : ''})
          {typeof malha.qtd_etapas === 'number' && (
            <> · {malha.qtd_etapas} etapa{malha.qtd_etapas !== 1 ? 's' : ''}</>
          )}
        </span>
        {gatilho && (
          <span className="truncate" title={tituloGatilho(gatilho)}>
            🕒 gatilho: {gatilho.resumo}
          </span>
        )}
        {malha.agendamento_guardado && (
          <span className="truncate text-amber-700 dark:text-amber-400" title={AVISO_AGENDA_GUARDADA}>
            ⚠ agendamento guardado, sem Início ligado
          </span>
        )}
        {previsao ? (
          // ── "não abriu" (Decisão 58) — o card que hoje não existe ─────────
          // Sem ele, a malha que NÃO rodou é a única que não aparece em lugar
          // nenhum: o card mostraria a corrida de ontem, verde, com carimbo de
          // frescor recente. Âmbar (o ciclo não acabou mal — ele não começou),
          // sem barra (não há o que preencher) e com a corrida anterior logo
          // abaixo, que é a medida do que se perdeu.
          <div
            className={`flex flex-col gap-0.5 rounded-md border px-2 py-1.5 ${previsao.faixa}`}
            title={previsao.titulo}
          >
            <div className="flex items-center gap-1.5 min-w-0">
              <CorridaBadge corrida={corrida} esperada={esperada} />
              <span className="truncate opacity-80">· {previsao.cabecalho}</span>
            </div>
            <div className="flex items-center gap-2">
              <span
                className="h-px flex-1 border-t border-dashed border-current opacity-40"
                aria-hidden="true"
              />
              <span className="shrink-0 opacity-80">{previsao.semCorrida}</span>
            </div>
            {previsao.bloqueio && (
              <span className="font-medium">↳ {previsao.bloqueio}</span>
            )}
            {/* A anterior vira contexto, não manchete: "está pior que ontem?"
                é a pergunta seguinte, e ela precisa do fato de ontem. */}
            {resumo && (
              <span className="truncate opacity-80">
                ↳ anterior: {resumo.identidade} · {resumo.estilo.rotulo}
                {resumo.tempo ? ` · ${resumo.tempo}` : ''}
              </span>
            )}
          </div>
        ) : resumo ? (
          // O bloco da corrida SUBSTITUI a linha "▶ última execução": as duas
          // juntas seriam duas respostas para a mesma pergunta, e a antiga é a
          // que mente. Sem "%" em superfície nenhuma (Decisão 56): o rótulo é
          // sempre `x de y`, e o substantivo é "pipelines".
          <div
            className={`flex flex-col gap-0.5 rounded-md border px-2 py-1.5 ${resumo.faixa}`}
            title={resumo.titulo}
          >
            <div className="flex items-center gap-1.5 min-w-0">
              <CorridaBadge corrida={corrida} />
              <span className="shrink-0 opacity-80">· {resumo.identidade}</span>
              {resumo.tempo && <span className="truncate opacity-80">· {resumo.tempo}</span>}
            </div>
            {/* A barra responde UMA coisa: quanto já ficou pronto. O travado
                fica fora dela (Decisão 54) e o denominador não encolhe
                (Decisão 52) — as duas regras moram no componente. */}
            <CorridaProgresso
              resumo={resumo}
              variante="card"
              congelado={CORRIDA_INTERROMPIDA.has(corrida!.status)}
            />
            {resumo.culpado && <span className="font-medium truncate">↳ {resumo.culpado}</span>}
            {resumo.vivos && <span className="opacity-80">↳ {resumo.vivos}</span>}
            {resumo.encerramento && <span className="opacity-80">{resumo.encerramento}</span>}
            {resumo.motivo && <span className="italic opacity-80 line-clamp-2">{resumo.motivo}</span>}
            {resumo.foraDoOdate && (
              <span className="font-medium text-amber-700 dark:text-amber-400">
                ⚠ {resumo.foraDoOdate}
              </span>
            )}
          </div>
        ) : ultima ? (
          // FALLBACK DECLARADO (Decisão 41): sem a chave `corrida` o card volta
          // ao texto de hoje — e diz de onde ele saiu. "(membro mais recente)"
          // não é enfeite: é a confissão de que este status é de UM pipeline, e
          // não da malha. A palavra "concluída" não aparece aqui.
          <span
            className="flex items-center gap-1 min-w-0"
            title={`${ultima.pipeline} · ${ultima.status}`
              + (formataDataHoraLonga(ultima.em) ? ` · ${formataDataHoraLonga(ultima.em)}` : '')
              + '\nEste é o status do MEMBRO que executou por último — não o da '
              + 'malha inteira. O ciclo da malha aparece aqui quando houver '
              + 'corrida registrada.'}
          >
            <span className="shrink-0">▶ última execução: {formataDataHora(ultima.em) ?? '—'}</span>
            <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${estilo!.dot}`} />
            <span className="truncate">{estilo!.rotulo}</span>
          </span>
        ) : (
          <span className="italic" title="Nenhuma corrida registrada para os pipelines desta malha">
            ▶ sem execução registrada
          </span>
        )}
        {!resumo && ultima && (
          <span className="truncate opacity-75">
            (membro mais recente — {ultima.pipeline})
          </span>
        )}
        {/* Aditivo à Decisão 41: a degradação é DITA, e igual em todos os cards
            afetados — quem não é técnico não pode ler o card degradado como um
            card diferente, e sim como uma tela sem parte da informação. Sai só
            com a FLAG (a 085 ausente); com o interruptor da corrida ainda em 0,
            que é o estado do dia do deploy, a lista inteira cairia neste aviso
            e o operador chegaria de manhã com 100% das malhas "sem informação"
            (§11.3). */}
        {!resumo && semDadosDeCorrida && (
          <span
            className="flex items-center gap-1 text-amber-700 dark:text-amber-400"
            title="O registro do ciclo da malha ainda não está disponível neste ambiente — a migration 085 não foi aplicada, ou o servidor ainda é o anterior a esta versão. O que está na tela continua verdadeiro; o que falta é o ciclo."
          >
            <AlertTriangle size={11} className="shrink-0" />
            sem dados de corrida — sistema em atualização
          </span>
        )}
        {criado && <span>📅 criada em {criado}</span>}
      </div>
      {/* ── Decisão 72: as posições são FIXAS e `Acompanhar` existe SEMPRE ──
          Dois defeitos de bancada moram aqui. (i) O interruptor da corrida
          nasce em `0` (§11.2): no dia do deploy NENHUMA malha tem corrida, e um
          botão que só existisse com corrida deixaria a fase inteira não
          testável — este leva à lente de execução da data corrente, que já
          funciona hoje. (ii) Botão que muda de lugar entre estados faz clicar
          em "Diagrama" no card 1 e acertar "Membros" no card 2; por isso nada
          some e nada troca de ordem: o que não cabe num estado é DESABILITADO,
          nunca removido. */}
      <div className="flex flex-wrap gap-1.5 pt-2 border-t border-edge mt-auto">
        <Button
          size="sm" onClick={onAcompanhar}
          title="Acompanhar a execução desta malha — a corrida em andamento, ou o dia corrente quando não há nenhuma"
        >
          <Play size={12} /> Acompanhar
        </Button>
        <Button variant="secondary" size="sm" onClick={onAbrir} title="Abrir o diagrama de montagem — desenhar uma aresta cadastra a dependência real">
          <Network size={12} /> Diagrama
        </Button>
        <Button variant="secondary" size="sm" onClick={onMembros} title="Ver e editar os pipelines desta malha">
          <Users size={12} /> Membros
        </Button>
        <Button variant="ghost" size="sm" onClick={onRenomear} title="Renomear a malha e editar a descrição">
          <Edit size={12} /> Renomear
        </Button>
        <Button variant="ghost" size="sm" onClick={onToggle} title={ativa ? 'Inativar a malha' : 'Reativar a malha'}>
          <Power size={12} /> {ativa ? 'Inativar' : 'Reativar'}
        </Button>
      </div>
    </div>
  )
}

// ─── Modal: nova malha ───────────────────────────────────────────────────────

function NovaMalhaModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const [nome, setNome] = useState('')
  const [descricao, setDescricao] = useState('')

  const criarMut = useMutation({
    mutationFn: () => apiFetch('/malhas', {
      method: 'POST',
      body: JSON.stringify({
        malha_name: nome.trim(),
        ...(descricao.trim() ? { descricao: descricao.trim() } : {}),
      }),
    }),
    onSuccess: () => {
      toast.success(`Malha "${nome.trim()}" criada.`)
      qc.invalidateQueries({ queryKey: ['malhas'] })
      setNome(''); setDescricao('')
      onClose()
    },
    // 422 da API (nome duplicado/inválido) chega como `detail` string em pt-BR.
    onError: (e: Error) => toast.error(e.message || 'Erro ao criar a malha'),
  })

  return (
    <Modal open={open} onClose={onClose} title="Nova malha">
      <div className="flex flex-col gap-3">
        <Input
          label="Nome"
          value={nome}
          onChange={e => setNome(e.target.value)}
          placeholder="ex: malha_fechamento_diario"
          ajuda="Identificador único da malha — os pipelines membros são adicionados depois, em Membros."
          autoFocus
        />
        <Textarea
          label="Descrição"
          value={descricao}
          onChange={e => setDescricao(e.target.value)}
          placeholder="opcional — o que esta malha orquestra"
          rows={3}
        />
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button
            onClick={() => criarMut.mutate()}
            loading={criarMut.isPending}
            disabled={!nome.trim()}
          >
            <Plus size={14} /> Criar malha
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ─── Modal: renomear/editar malha ────────────────────────────────────────────

function RenomearMalhaModal({ malha, onClose }: { malha: ApiMalha; onClose: () => void }) {
  const qc = useQueryClient()
  const [nome, setNome] = useState(malha.malha_name)
  const [descricao, setDescricao] = useState(malha.descricao ?? '')

  const salvarMut = useMutation({
    mutationFn: (body: { novo_nome?: string; descricao?: string }) =>
      apiFetch(`/malhas/${encodeURIComponent(malha.malha_name)}`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      toast.success('Malha atualizada.')
      qc.invalidateQueries({ queryKey: ['malhas'] })
      onClose()
    },
    onError: (e: Error) => toast.error(e.message || 'Erro ao atualizar a malha'),
  })

  function salvar() {
    const body: { novo_nome?: string; descricao?: string } = {}
    const nomeTrim = nome.trim()
    if (nomeTrim && nomeTrim !== malha.malha_name) body.novo_nome = nomeTrim
    if (descricao.trim() !== (malha.descricao ?? '')) body.descricao = descricao.trim()
    if (Object.keys(body).length === 0) { onClose(); return } // nada mudou: no-op
    salvarMut.mutate(body)
  }

  return (
    <Modal open onClose={onClose} title="Renomear malha">
      <div className="flex flex-col gap-3">
        <Input
          label="Nome"
          value={nome}
          onChange={e => setNome(e.target.value)}
          autoFocus
        />
        <Textarea
          label="Descrição"
          value={descricao}
          onChange={e => setDescricao(e.target.value)}
          placeholder="opcional — o que esta malha orquestra"
          rows={3}
        />
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={salvar} loading={salvarMut.isPending} disabled={!nome.trim()}>
            Salvar
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ─── Modal: membros da malha ─────────────────────────────────────────────────

function MembrosModal({ malhaName, onClose }: { malhaName: string; onClose: () => void }) {
  const qc = useQueryClient()
  const [busca, setBusca] = useState('')

  const { data, isLoading, isError, error } = useQuery<MalhaDetalheResponse>({
    queryKey: ['malha', malhaName],
    queryFn: () => apiFetch(`/malhas/${encodeURIComponent(malhaName)}`),
  })
  const membros = data?.membros ?? []

  function invalidar() {
    qc.invalidateQueries({ queryKey: ['malha', malhaName] })
    qc.invalidateQueries({ queryKey: ['malhas'] }) // contagens/criticidade dos cards
  }

  const addMut = useMutation({
    mutationFn: (pipeline_name: string) =>
      apiFetch<RespostaComAvisoDeCiclo>(
        `/malhas/${encodeURIComponent(malhaName)}/pipelines`, {
          method: 'POST',
          body: JSON.stringify({ pipeline_name }),
        }),
    onSuccess: (r, pipeline_name) => {
      toast.success(`Pipeline "${pipeline_name}" adicionado à malha.`)
      // O membro entra no CADASTRO agora e no CICLO em voo só no próximo: o
      // quadro de membros da corrida congelou na abertura. Sem esta frase, o
      // operador não vê o pipeline no denominador do painel e conclui que a
      // tela quebrou.
      avisarCiclo(r)
      setBusca('')
      invalidar()
    },
    // 422 da API: pipeline inexistente / já membro — detail em pt-BR.
    onError: (e: Error) => toast.error(e.message || 'Erro ao adicionar o pipeline'),
  })

  const removerMut = useMutation({
    mutationFn: (pipeline_name: string) =>
      apiFetch<RespostaComAvisoDeCiclo>(
        `/malhas/${encodeURIComponent(malhaName)}/pipelines/${encodeURIComponent(pipeline_name)}`, {
          method: 'DELETE',
        }),
    onSuccess: (r, pipeline_name) => {
      toast.success(`Pipeline "${pipeline_name}" removido da malha.`)
      // Efeito OPOSTO ao de adicionar, e por isso a frase é outra: o membro
      // sai do cadastro, mas continua contando no ciclo em voo até ele fechar.
      avisarCiclo(r)
      invalidar()
    },
    onError: (e: Error) => toast.error(e.message || 'Erro ao remover o pipeline'),
  })

  function remover(pipeline_name: string) {
    if (!confirm(`Remover "${pipeline_name}" da malha "${malhaName}"?\n\nO pipeline continua existindo — sai apenas desta malha.`)) return
    removerMut.mutate(pipeline_name)
  }

  return (
    <Modal open onClose={onClose} title={`Membros — ${malhaName}`} size="lg">
      <div className="flex flex-col gap-4">

        {/* Adicionar por busca (mesmo padrão de autocomplete da tela de Etapas) */}
        <div className="flex items-end gap-2">
          <Autocomplete
            label="Adicionar pipeline"
            value={busca}
            onChange={setBusca}
            onSelect={setBusca}
            fetchSuggestions={q =>
              apiFetch<{ data: { pipeline_name: string }[] }>(`/pipelines?limit=10&filter_name=${encodeURIComponent(q)}`)
                .then(r => r.data.map(p => p.pipeline_name))
            }
            placeholder="busque por nome..."
            className="flex-1"
          />
          <Button
            onClick={() => addMut.mutate(busca.trim())}
            loading={addMut.isPending}
            disabled={!busca.trim()}
          >
            <Plus size={14} /> Adicionar
          </Button>
        </div>

        {/* Lista de membros */}
        {isLoading ? (
          <PageSpinner />
        ) : isError ? (
          <div className="rounded-lg border border-red-200 bg-red-50 dark:bg-red-900/20 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-300">
            Erro ao carregar os membros: {(error as Error)?.message ?? 'Erro desconhecido'}
          </div>
        ) : membros.length === 0 ? (
          <p className="text-sm text-dim text-center py-6">
            Nenhum pipeline nesta malha ainda — adicione pelo campo acima.
          </p>
        ) : (
          <div className="flex flex-col gap-1.5">
            {membros.map(m => (
              <div key={m.pipeline_name} className="flex items-center gap-2 px-3 py-2 bg-canvas border border-edge rounded-md">
                <span className={`w-2 h-2 rounded-full shrink-0 ${m.active ? 'bg-green-400' : 'bg-slate-400'}`} />
                <span className="font-mono text-xs text-ink flex-1 min-w-0 truncate">{m.pipeline_name}</span>
                {m.criticidade && <CritBadge crit={m.criticidade} />}
                {m.schedule_type && (
                  <span className="text-[10px] text-dim">
                    {m.schedule_type === 'on_demand' ? 'sob demanda' : m.schedule_type}
                  </span>
                )}
                <button
                  onClick={() => remover(m.pipeline_name)}
                  title="Remover da malha"
                  className="text-dim hover:text-red-400 transition-colors shrink-0"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          </div>
        )}

        <p className="text-[11px] text-dim border-t border-edge pt-3">
          Aqui você define apenas <strong className="text-ink">quem participa</strong> da malha —
          o diagrama de montagem (nós, dependências e layout) chega na F8.
        </p>
      </div>
    </Modal>
  )
}

// ─── Modal: o que é a malha (ajuda da tela) ──────────────────────────────────
// A explicação vive AQUI, atrás de um botão, e não como texto fixo na página:
// o espaço da tela é dos cards. O conteúdo é o mesmo do §1.3 do manual do
// usuário — as duas fontes precisam contar a MESMA história.

function AjudaMalhaModal({ onClose }: { onClose: () => void }) {
  return (
    <Modal open onClose={onClose} title="O que é a malha?" size="lg">
      <div className="flex flex-col gap-4 text-sm text-ink leading-relaxed">

        <p>
          Uma <strong>malha</strong> é um agrupamento de pipelines que rodam juntos
          como um processo só — o equivalente à sequence mestre do DataStage ou a
          uma pasta SMART do Control-M. A malha <strong>não executa nada por si</strong>:
          ela é a planta de como os pipelines se encadeiam.
        </p>

        <div>
          <h3 className="text-sm font-semibold text-ink mb-1.5">A tela tem dois níveis</h3>

          <p className="text-[13px] text-dim">
            <strong className="text-ink">1. A lista</strong> (esta tela) — cada card é
            uma malha, com nome, se está ativa, criticidade (a mais alta entre os
            pipelines dela), o tamanho (pipelines e etapas), o horário de gatilho e a
            última execução. Daqui você abre a malha, gerencia os pipelines membros,
            renomeia ou inativa. Inativar não apaga nada: só faz a malha parar de
            emitir notificações e avisos de conclusão — as dependências e o
            agendamento já criados continuam valendo.
          </p>

          <p className="text-[13px] text-dim mt-2">
            <strong className="text-ink">2. O diagrama</strong> (ao abrir uma malha) —
            tem dois modos:
          </p>
          <ul className="mt-1.5 flex flex-col gap-2 text-[13px] text-dim">
            <li className="border-l-2 border-edge pl-3">
              <strong className="text-ink">Montagem</strong>: onde você desenha.
              Arrastar uma seta entre dois pipelines <strong>cadastra a dependência de
              verdade</strong> — o pipeline de destino passa a esperar o de origem
              concluir com sucesso no mesmo dia de processamento. O desenho <em>é</em> a
              configuração, não um diagrama decorativo. Aqui também ficam os quatro
              componentes: <strong className="text-ink">Início</strong> (agenda a malha
              inteira de uma vez — o horário configurado nele é copiado para os
              primeiros pipelines), <strong className="text-ink">Aguarde</strong> (junta
              várias pernas: tudo que entra precisa <strong className="text-ink">concluir com
              sucesso</strong> antes do que sai começar),
              <strong className="text-ink"> Notificação</strong> (avisa no painel e no Teams
              quando todas as entradas dele concluírem com sucesso) e{' '}
              <strong className="text-ink">Fim</strong> (registra a conclusão da malha no dia;
              o card no Teams é opcional).
            </li>
            <li className="border-l-2 border-edge pl-3">
              <strong className="text-ink">Execução</strong>: onde você acompanha.
              Escolhe um dia e vê o que aconteceu — cada pipeline com seu status, o
              Aguarde mostrando se as entradas concluíram, Notificação e Fim acesos com o
              horário em que dispararam, e o banner verde quando a malha inteira
              concluiu. É aqui também que fica o botão <strong className="text-ink">Disparar
              malha</strong>, que roda tudo manualmente com a data que você está vendo;
              as dependências fazem o resto andar sozinho.
            </li>
          </ul>

          <p className="text-[13px] text-dim mt-2">
            O critério é sempre o mesmo: <strong className="text-ink">todas as entradas com
            SUCESSO na mesma data de referência</strong>. Falha, execução em andamento ou
            pulado não liberam nada — a malha segura e a guardiã alerta.
          </p>
        </div>

        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 dark:border-amber-800 dark:bg-amber-900/20">
          <h3 className="text-[13px] font-semibold text-amber-800 dark:text-amber-300 mb-1">
            A regra que evita surpresa
          </h3>
          <p className="text-[12px] text-amber-800 dark:text-amber-200 leading-relaxed">
            A dependência é <strong>global</strong>, não pertence à malha. Se dois
            desenhos usam o mesmo par de pipelines, é a mesma dependência: por isso uma
            dependência criada pelo componente de uma malha aparece <strong>com
            cadeado</strong> nas outras e só pode ser desfeita pela malha que a criou.
            Do mesmo jeito, um pipeline só pode ser agendado pelo Início de uma malha
            por vez.
          </p>
        </div>

        <div className="flex justify-end pt-1">
          <Button variant="secondary" onClick={onClose}>Entendi</Button>
        </div>
      </div>
    </Modal>
  )
}

// ─── Visão Malhas (lista) ────────────────────────────────────────────────────

function MalhasView({ onAbrir, onAcompanhar }: {
  onAbrir: (malha: string) => void
  /** (F9/Decisão 72) Abrir a malha já na lente de EXECUÇÃO. `corrida` só vai
   *  junto quando existe ciclo registrado — sem ela o painel usa a corrida
   *  corrente do servidor, que é o comportamento correto no dia do deploy. */
  onAcompanhar: (malha: string, corrida?: number | null) => void
}) {
  const [showCriar, setShowCriar] = useState(false)
  const [renomear, setRenomear] = useState<ApiMalha | null>(null)
  const [membrosDe, setMembrosDe] = useState<string | null>(null)
  // Filtro CLIENT-SIDE: o endpoint devolve a lista inteira (dezenas de
  // malhas, não milhares) — filtrar aqui responde a cada tecla sem round-trip.
  const [busca, setBusca] = useState('')
  const [statusFiltro, setStatusFiltro] = useState('')

  const qc = useQueryClient()
  const { data, isLoading, isError, error, refetch, dataUpdatedAt, isFetching } =
    useQuery<MalhasResponse>({
      queryKey: ['malhas'],
      queryFn: () => apiFetch('/malhas'),
      // F4 (Decisão 73) — polling CONDICIONAL: 20 s enquanto alguma malha tem
      // corrida em voo, e NADA quando não há o que acompanhar. Ligar polling
      // incondicional numa tela que hoje não tem nenhum seria pagar o custo
      // das 24 h por causa das 4 da madrugada. O recorte é a lista inteira (e
      // não só as malhas visíveis): o filtro é client-side, e uma corrida em
      // voo escondida por um filtro continua sendo uma corrida em voo.
      //
      // F9: `não abriu` entra no MESMO predicado, e a Decisão 73 o nomeia. Ele
      // é um estado de RELÓGIO — "previsto para 01:00 · há 7h12" cresce —, e
      // sem polling a tela congelaria naquele "há 7h12" enquanto alguém
      // dispara a malha na mão do outro lado. Pior: `acompanhando` também
      // governa o alarme de dado velho, então o card mais grave da manhã seria
      // o único a envelhecer em silêncio.
      refetchInterval: q =>
        (q.state.data?.malhas ?? []).some(emMovimento) ? 20_000 : false,
    })
  // useMemo (e não `data?.malhas ?? []` solto): o `[]` de fallback nasce novo
  // a cada render e faria o filtro abaixo recalcular sempre.
  const malhas = useMemo(() => data?.malhas ?? [], [data])
  const migrationPendente = data?.migration_pendente === true
  // Os DOIS jeitos de não haver ciclo neste ambiente, e eles dizem a mesma
  // frase ao operador: o banco sem a 085, e a API anterior a esta fase (a
  // janela do deploy em que o `dist/` novo fala com a `api/` velha). O que
  // NUNCA decide renderização é isto: quem decide é a ausência da chave
  // `corrida` por malha (Decisão 41).
  const sem085 = data?.migration_085_pendente === true
  const apiAnterior = data !== undefined && data.corrida_suportada !== true
  const semDadosDeCorrida = sem085 || apiAnterior
  // Alguma corrida em voo — ou alguma que deveria ter aberto e não abriu — é
  // o que há para envelhecer na tela; é o MESMO predicado do polling, e é ele
  // que decide se o carimbo de frescor vira ALARME.
  const acompanhando = malhas.some(emMovimento)
  const agora = useDecorrido(acompanhando)
  // Decisão 60: o frescor é o relógio local CONSIGO MESMO. `dataUpdatedAt` é o
  // instante LOCAL em que a resposta chegou — misturar com `apurado_em` (o
  // relógio do banco, 3 h à frente no dev) daria "atualizado há -3h".
  const fresco = frescor(dataUpdatedAt, agora)
  const tempo = useMemo(() => ({ respostaEm: dataUpdatedAt, agora }),
                        [dataUpdatedAt, agora])

  const toggleMut = useMutation({
    mutationFn: (m: ApiMalha) =>
      apiFetch<RespostaComAvisoDeCiclo>(
        `/malhas/${encodeURIComponent(m.malha_name)}`, {
          method: 'PATCH',
          body: JSON.stringify({ ativo: !m.ativo }),
        }),
    onSuccess: (r, m) => {
      toast.success(m.ativo ? `Malha "${m.malha_name}" inativada.` : `Malha "${m.malha_name}" reativada.`)
      // Inativar NÃO interrompe o ciclo em voo — ele segue até fechar sozinho,
      // e o que a inativação impede é o PRÓXIMO abrir. Sem a frase, o operador
      // inativa a malha achando que parou a madrugada.
      avisarCiclo(r)
      qc.invalidateQueries({ queryKey: ['malhas'] })
    },
    onError: (e: Error) => toast.error(e.message || 'Erro ao alterar a malha'),
  })

  function alternar(m: ApiMalha) {
    const acao = m.ativo ? 'Inativar' : 'Reativar'
    if (!confirm(`${acao} a malha "${m.malha_name}"?`)) return
    toggleMut.mutate(m)
  }

  const filtradas = useMemo(() => {
    const q = normalizeBusca(busca.trim())
    const visiveis = malhas.filter(m => {
      if (statusFiltro === '1' && !m.ativo) return false
      if (statusFiltro === '0' && m.ativo) return false
      if (!q) return true
      return normalizeBusca(m.malha_name).includes(q)
        || normalizeBusca(m.descricao ?? '').includes(q)
    })
    // Decisão 58 — "não abriu" ORDENA PRIMEIRO. É a única reordenação da lista,
    // e ela existe porque este é o estado que o operador precisa ver ANTES de
    // procurar: a malha que não rodou não aparece em lugar nenhum hoje, e numa
    // grade de 40 cards em ordem alfabética ela some no meio das que rodaram
    // bem. O resto mantém a ordem do servidor (`sort` estável desde o ES2019) —
    // ordenar por gravidade embaralharia a lista a cada refetch de 20 s, e um
    // card que troca de lugar debaixo do cursor é um clique errado às 3h.
    return visiveis.slice().sort((a, b) =>
      Number(!!b.corrida_esperada) - Number(!!a.corrida_esperada))
  }, [malhas, busca, statusFiltro])

  const filtroAtivo = busca.trim() !== '' || statusFiltro !== ''
  const ativas = filtradas.filter(m => m.ativo).length
  const totalPipelines = filtradas.reduce((s, m) => s + m.qtd_pipelines, 0)
  // Só soma etapas se a API DEVOLVEU o campo (deploy parcial com API antiga):
  // `?? 0` mostraria "0 etapas" para malhas com centenas — a mesma regra de
  // omissão que o card usa, senão a stats bar contradiz os cards.
  const temEtapas = filtradas.some(m => typeof m.qtd_etapas === 'number')
  const totalEtapas = filtradas.reduce((s, m) => s + (m.qtd_etapas ?? 0), 0)
  // Contador próprio do "não abriu" (Decisão 58). Só existe quando existe: uma
  // pílula "0 não abriram" verde todo dia treinaria o olho a passar por ela —
  // e no dia em que o número fosse 1 ele não seria visto.
  const naoAbriram = filtradas.filter(m => m.corrida_esperada).length

  return (
    <div className="flex flex-col gap-4">

      {/* Aviso discreto de deploy parcial: API nova sem a migration 070. */}
      {migrationPendente && (
        <div className="flex items-center gap-2 text-[12px] text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg px-3 py-2">
          <AlertTriangle size={14} className="shrink-0" />
          <span>migration 070 pendente — as tabelas de malha ainda não existem neste ambiente; peça o deploy para criar malhas.</span>
        </div>
      )}

      {/* Toolbar */}
      <div className="flex flex-wrap gap-2 items-center">
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-2.5 text-dim pointer-events-none" />
          <input
            type="search"
            value={busca}
            onChange={e => setBusca(e.target.value)}
            placeholder="Buscar por nome ou descrição…"
            aria-label="Buscar malha por nome ou descrição"
            className="w-72 bg-panel border border-edge text-ink rounded-md pl-8 pr-3 py-1.5 text-sm placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>
        <Select
          value={statusFiltro}
          onChange={e => setStatusFiltro(e.target.value)}
          title="Filtrar por situação da malha"
          aria-label="Filtrar por situação da malha"
          className="w-32"
        >
          <option value="">Todas</option>
          <option value="1">Ativas</option>
          <option value="0">Inativas</option>
        </Select>
        {filtroAtivo && (
          <button
            onClick={() => { setBusca(''); setStatusFiltro('') }}
            title="Limpar os filtros"
            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md text-sm border border-edge bg-canvas text-dim hover:text-ink hover:bg-edge/40 transition-colors"
          >
            <X size={13} /> Limpar
          </button>
        )}
        <div className="flex items-center gap-1 ml-auto">
          {/* Carimbo de frescor — UM por página (Decisão 60), nunca um por
              card: precisão de segundo em polling de 20 s sugere tempo real, e
              dois cards com "há 8s" e "há 31s" na mesma tela fazem duvidar dos
              dois. Acima de 90 s sem refetch com sucesso ele vira ALARME —
              mas só quando há corrida em voo: sem nada acontecendo, "dado de
              10:58" é fato, não incidente. */}
          {!isLoading && !isError && (
            <span
              className={`mr-1 text-[11px] ${fresco.velho && acompanhando
                ? 'font-medium text-amber-700 dark:text-amber-400' : 'text-dim'}`}
              title={acompanhando
                ? 'Esta lista se atualiza sozinha a cada 20 s enquanto houver corrida em andamento.'
                : 'Sem corrida em andamento, a lista não se atualiza sozinha — use o botão ao lado.'}
            >
              {fresco.velho && acompanhando ? '⚠ ' : '· '}
              {isFetching ? 'atualizando…' : `atualizado ${fresco.texto}`}
            </span>
          )}
          <Button
            onClick={() => setShowCriar(true)}
            disabled={migrationPendente}
            title={migrationPendente ? 'Indisponível até a migration 070 ser aplicada' : 'Criar uma nova malha'}
          >
            <Plus size={14} /> Nova malha
          </Button>
          <button
            onClick={() => refetch()}
            title="Atualizar dados"
            className="inline-flex items-center px-2.5 py-1.5 rounded-md text-sm border border-edge bg-canvas text-dim hover:text-ink hover:bg-edge/40 transition-colors"
          >
            <RefreshCw size={13} />
          </button>
        </div>
      </div>

      {/* Stats bar (mesma linguagem das stats-pills do catálogo). Com filtro
          ligado a 1ª pílula vira "N de M" — a conta some do rodapé e o
          operador nunca acha que a lista inteira encolheu. */}
      {!isLoading && !isError && malhas.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {[
            {
              label: filtroAtivo ? `${filtradas.length} de ${malhas.length}` : `${malhas.length}`,
              sub: `malha${malhas.length !== 1 ? 's' : ''}`,
            },
            { label: `${ativas}`, sub: `ativa${ativas !== 1 ? 's' : ''}` },
            { label: `${totalPipelines}`, sub: `pipeline${totalPipelines !== 1 ? 's' : ''} agrupados` },
            ...(temEtapas
              ? [{ label: `${totalEtapas}`, sub: `etapa${totalEtapas !== 1 ? 's' : ''}` }]
              : []),
            // Decisão 58 — contador próprio, e ÂMBAR: é a pílula que responde
            // "a madrugada rodou?" antes de o olho descer para os cards.
            ...(naoAbriram > 0
              ? [{
                label: `${naoAbriram}`,
                sub: `não abri${naoAbriram !== 1 ? 'ram' : 'u'}`,
                tom: 'border-amber-300 bg-amber-50 text-amber-800 '
                  + 'dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300',
              }]
              : []),
          ].map(s => (
            <div
              key={s.sub}
              className={`rounded px-3 py-1.5 flex items-center gap-1.5 border ${
                'tom' in s && s.tom ? s.tom : 'bg-panel border-edge'}`}
            >
              <strong className={`font-bold text-sm ${'tom' in s && s.tom ? '' : 'text-ink'}`}>
                {s.label}
              </strong>
              <span className={`text-xs ${'tom' in s && s.tom ? '' : 'text-dim'}`}>{s.sub}</span>
            </div>
          ))}
        </div>
      )}

      {/* Conteúdo */}
      {isLoading ? (
        <PageSpinner />
      ) : isError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 dark:bg-red-900/20 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          Erro ao carregar malhas: {(error as Error)?.message ?? 'Erro desconhecido'}
        </div>
      ) : malhas.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Boxes size={40} className="text-dim mb-3" />
          <p className="font-semibold text-ink">Nenhuma malha cadastrada</p>
          <p className="text-sm text-dim mt-1 max-w-md">
            Uma malha agrupa pipelines — o análogo da sequence mestre do DataStage.
            O diagrama de montagem chega na F8.
          </p>
          {!migrationPendente && (
            <Button className="mt-4" onClick={() => setShowCriar(true)}>
              <Plus size={14} /> Criar a primeira malha
            </Button>
          )}
        </div>
      ) : filtradas.length === 0 ? (
        // Estado vazio do FILTRO — diferente de "nenhuma malha cadastrada":
        // aqui existem malhas, o filtro é que não casou nenhuma.
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Search size={40} className="text-dim mb-3" />
          <p className="font-semibold text-ink">Nenhuma malha para este filtro</p>
          <p className="text-sm text-dim mt-1 max-w-md">
            As {malhas.length} malha{malhas.length !== 1 ? 's' : ''} cadastrada{malhas.length !== 1 ? 's' : ''} continua{malhas.length !== 1 ? 'm' : ''} lá —
            ajuste a busca ou a situação.
          </p>
          <Button variant="secondary" className="mt-4" onClick={() => { setBusca(''); setStatusFiltro('') }}>
            <X size={14} /> Limpar filtros
          </Button>
        </div>
      ) : (
        <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))' }}>
          {filtradas.map(m => (
            <MalhaCard
              key={m.malha_name}
              malha={m}
              tempo={tempo}
              semDadosDeCorrida={semDadosDeCorrida}
              onAcompanhar={() => onAcompanhar(m.malha_name, m.corrida?.id)}
              onAbrir={() => onAbrir(m.malha_name)}
              onMembros={() => setMembrosDe(m.malha_name)}
              onRenomear={() => setRenomear(m)}
              onToggle={() => alternar(m)}
            />
          ))}
        </div>
      )}

      <NovaMalhaModal open={showCriar} onClose={() => setShowCriar(false)} />
      {renomear && (
        <RenomearMalhaModal
          key={renomear.malha_name}
          malha={renomear}
          onClose={() => setRenomear(null)}
        />
      )}
      {membrosDe && (
        <MembrosModal malhaName={membrosDe} onClose={() => setMembrosDe(null)} />
      )}
    </div>
  )
}

// ─── Main page ───────────────────────────────────────────────────────────────
// Desde a F9 a tela exibe SÓ malhas (decisão do usuário na spec §8) — o
// inventário de pipelines vive em Catálogo & Lineage (/governanca). Com
// `?malha=` na URL a página vira o diagrama de montagem em tela cheia (F8) —
// mesmo padrão de deep-link da tela Fluxos (?pipeline=).

export default function Malha() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const malhaAberta = (searchParams.get('malha') ?? '').trim()
  // (F3) Lente e data com que o diagrama abre — é o que torna a visão de
  // Execução LINKÁVEL e permite ao drill-down das etapas voltar exatamente
  // para onde saiu. Depois de aberto, o editor manda no seu próprio estado
  // (a URL é o ponto de partida, não um controlador ao vivo — sincronizar os
  // dois sentidos criaria uma segunda fonte de verdade para o mesmo estado).
  const modoInicial = (searchParams.get('modo') ?? '').trim() === 'execucao'
    ? 'execucao' as const
    : undefined
  const dataInicial = (searchParams.get('data') ?? '').trim() || null
  // (F9) `?corrida=` — a LENTE com que a Execução abre. Só número: um parâmetro
  // estragado na URL não pode virar `NaN` numa query string enviada ao
  // servidor. Inválido = sem lente, que é o comportamento de sempre.
  const corridaParam = Number((searchParams.get('corrida') ?? '').trim())
  const corridaInicial = Number.isInteger(corridaParam) && corridaParam > 0
    ? corridaParam : null
  const [membrosAberto, setMembrosAberto] = useState(false)
  const [ajudaAberta, setAjudaAberta] = useState(false)
  const user = useAuthStore(s => s.user)
  const isViewer = user?.perfil === 'consulta'

  // ── Diagrama de montagem em tela cheia (F8) ────────────────────────────────
  if (malhaAberta) {
    return (
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="flex items-center gap-2 text-lg font-semibold text-ink">
            <Boxes size={20} className="text-[#1A5FA8]" /> Malha
            <span className="font-mono text-base text-dim">· {malhaAberta}</span>
          </h1>
          <div className="ml-auto flex items-center gap-2">
            {!isViewer && (
              <Button
                variant="secondary" size="sm"
                onClick={() => setMembrosAberto(true)}
                title="Ver e remover os pipelines membros desta malha"
              >
                <Users size={13} /> Membros
              </Button>
            )}
            {/* Fechar limpa TODOS os parâmetros (malha, modo e data) — voltar
                à lista com `?modo=execucao` pendurado deixaria a próxima malha
                aberta numa lente que ninguém pediu. */}
            <Button variant="secondary" size="sm" onClick={() => setSearchParams({})} title="Voltar à lista de malhas">
              <X size={13} /> Voltar
            </Button>
          </div>
        </div>
        <div className="h-[calc(100vh-11rem)]">
          <MalhaEditor
            malha={malhaAberta}
            readOnly={isViewer}
            modoInicial={modoInicial}
            dataInicial={dataInicial}
            corridaInicial={corridaInicial}
            // (F3) Descer até o canvas de Etapas do pipeline, na MESMA data —
            // e levando de onde se veio (`de=malha:…`), que é o que dá a volta
            // óbvia lá do outro lado. Ver a decisão registrada em pages/Fluxos.
            onAbrirEtapas={(pipeline, data) => navigate(
              `/fluxos?pipeline=${encodeURIComponent(pipeline)}`
              + `&modo=execucao&data=${encodeURIComponent(data)}`
              + `&de=malha:${encodeURIComponent(malhaAberta)}`)}
          />
        </div>
        {membrosAberto && (
          <MembrosModal malhaName={malhaAberta} onClose={() => setMembrosAberto(false)} />
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">

      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-0">
          <h1 className="text-xl font-bold text-ink">Malha de Pipelines</h1>
          <p className="text-sm text-dim mt-0.5">
            Agrupe pipelines em malhas — a lente de montagem da orquestração
          </p>
        </div>
        {/* A explicação inteira mora no modal, não na página: espaço de tela é
            para as malhas. */}
        <Button
          variant="ghost" size="sm" className="mt-0.5"
          onClick={() => setAjudaAberta(true)}
          title="O que é uma malha, o que a lista mostra e o que dá para fazer no diagrama"
        >
          <HelpCircle size={14} /> O que é a malha?
        </Button>
      </div>

      <MalhasView
        onAbrir={n => setSearchParams({ malha: n })}
        // (F9/Decisão 72) `Acompanhar` leva à lente de EXECUÇÃO — e leva
        // `corrida` junto quando o card tinha uma. Sem o id, o painel abriria
        // na corrida CORRENTE do servidor: quem clicou num card que mostrava a
        // de ontem cairia na de hoje, e a tela responderia outra pergunta.
        // Sem corrida nenhuma (o dia do deploy), a lente é a data corrente —
        // que já funciona hoje, e é o que torna esta fase testável.
        onAcompanhar={(n, corrida) => setSearchParams(
          corrida
            ? { malha: n, modo: 'execucao', corrida: String(corrida) }
            : { malha: n, modo: 'execucao' })}
      />
      {ajudaAberta && <AjudaMalhaModal onClose={() => setAjudaAberta(false)} />}
    </div>
  )
}
