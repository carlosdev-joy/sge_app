// Nós de COMPONENTE da malha (F12 — docs/malha-componentes-desenho.md §10):
// Início, Aguarde, Notificação e Fim. São o DESENHO da malha (etl_malha_no,
// migration 075) misturado aos nós-pipeline no MalhaEditor — nenhum deles
// executa nada: Início planta agendamento (F13), Aguarde compila dependências
// (F11), Notificação/Fim são observados pela guardiã (F14).
//
// Identidade visual (mesma família do canvas de Etapas — o operador reencontra
// o componente com a MESMA cara):
//   • Aguarde     — barra de sincronização (BPMN) âmbar-600 com medalhão de
//                   ampulheta (Hourglass), idêntico ao Aguarde das Etapas;
//   • Notificação — tile teal-600 com sino (BellRing), como nas Etapas;
//   • Início      — tile emerald-600 com Play (o desenho não fixa o glifo;
//                   Play é a partida, verde é o start do BPMN — escolha
//                   registrada na F12; contraste do glifo branco 3.8:1);
//   • Fim         — tile slate-600 com Flag (bandeira de chegada; slate é o
//                   terminal NEUTRO de propósito — vermelho leria como FALHA
//                   na visão de execução; contraste 7.6:1).
// Chips em -600: o glifo branco precisa de 3:1 (WCAG 1.4.11).
//
// Handles CONDICIONAIS pela gramática do desenho (§2.1): Início só tem SAÍDA
// (nada liga NO Início), Notificação e Fim só têm ENTRADA (observadores
// terminais), Aguarde tem as duas. A gramática vira geometria: a ligação
// proibida nem nasce no gesto — e o 422 do servidor segue de autoridade.
//
// Orientação (074): horizontal = target Left / source Right; vertical =
// target Top / source Bottom — e a barra do Aguarde gira junto (perpendicular
// ao fluxo nas DUAS direções). Trocar a posição dos handles muda a geometria
// que o React Flow memoriza por nó — useUpdateNodeInternals avisa (lição do
// MalhaPipelineNode).
//
// Invólucro na LARGURA do desenho (w-12, lição da PR #238): os handles ancoram
// no bounding box — encostados no visual, nunca "morrendo no nada"; o rótulo
// transborda de propósito (w-[128px]).
import { memo, useEffect } from 'react'
import { Handle, Position, useUpdateNodeInternals, type NodeProps } from '@xyflow/react'
import { Hourglass } from 'lucide-react'
import type { Orientacao } from '../etapas/layoutGrafo'
// Metadados (rótulo/chip/ícone por tipo) em módulo PURO — compartilhados com
// a paleta e o minimapa do MalhaEditor sem quebrar o react-refresh daqui.
import { COMPONENTE_META, type TipoComponente } from './componenteMeta'

export interface MalhaComponenteNodeData {
  // id da linha em etl_malha_no — o id do NÓ no canvas é "no:{noId}" (§9).
  noId: number
  tipo: TipoComponente
  // Contagens de arestas de nó (payload do detalhe) — o subtítulo do card é
  // honesto sobre o que está ligado; o aviso estrutural mora no banner.
  entradas: number
  saidas: number
  // config_json do nó (título da Notificação etc.) — edição rica é a F13.
  config?: Record<string, unknown> | null
  orientacao?: Orientacao
  [key: string]: unknown
}

// Bolinha dos handles — a mesma dos irmãos (14px de alvo, neutra nos 2 temas).
const HANDLE_CLS =
  '!h-3.5 !w-3.5 !rounded-full !border-2 !border-panel !bg-slate-400 dark:!bg-slate-500'

// Tile/barra têm 32px; handles laterais no centro vertical do desenho (top:
// 16). Nos handles Top/Bottom o offset não se aplica — eles ancoram no eixo
// horizontal do bounding box (o rótulo faz parte do nó; a aresta chega nele).
const VISUAL_H = 32
const HANDLE_Y = VISUAL_H / 2

function plural(n: number, singular: string, plural: string): string {
  return `${n} ${n === 1 ? singular : plural}`
}

// Subtítulo por tipo — o que está LIGADO, dito no card (nada de estado de
// execução aqui: a camada de execução dos nós é a F15).
function subtitulo(data: MalhaComponenteNodeData): string {
  const tituloRaw = data.config?.titulo
  const titulo = typeof tituloRaw === 'string' ? tituloRaw.trim() : ''
  switch (data.tipo) {
    case 'inicio':
      return data.saidas === 0 ? 'ligue às raízes' : plural(data.saidas, 'raiz', 'raízes')
    case 'aguarde':
      // Decisão 6 do desenho: política única — todas com sucesso.
      return 'todas com sucesso'
    case 'notificacao':
      if (titulo) return titulo
      return data.entradas === 0 ? 'sem entradas' : plural(data.entradas, 'entrada', 'entradas')
    case 'fim':
      return data.entradas === 0 ? 'sem entradas' : plural(data.entradas, 'ligado', 'ligados')
  }
}

// Tooltip por tipo — a semântica em linguagem de operador (§3.1/§5/§6).
const TITULO: Record<TipoComponente, string> = {
  inicio: 'Início da malha — planta o agendamento da malha nos pipelines raiz ligados a ele',
  aguarde: 'Libera quando TODAS as entradas tiverem SUCESSO na mesma data de referência; '
    + 'falha segura a malha e a guardiã alerta',
  notificacao: 'Notificação — a guardiã emite o aviso quando todas as entradas '
    + 'tiverem SUCESSO na data',
  fim: 'Fim da malha — a conclusão é registrada quando todos os ligados a ele '
    + 'tiverem SUCESSO na data',
}

// Handles condicionais pela gramática §2.1 (ver cabeçalho).
function HandlesGramatica({ tipo, vertical }: { tipo: TipoComponente; vertical: boolean }) {
  const alvoLateral = vertical ? undefined : { top: HANDLE_Y }
  return (
    <>
      {tipo !== 'inicio' && (
        <Handle
          type="target"
          position={vertical ? Position.Top : Position.Left}
          className={HANDLE_CLS}
          style={alvoLateral}
        />
      )}
      {(tipo === 'inicio' || tipo === 'aguarde') && (
        <Handle
          type="source"
          position={vertical ? Position.Bottom : Position.Right}
          className={HANDLE_CLS}
          style={alvoLateral}
        />
      )}
    </>
  )
}

function ComponenteNodeImpl({ id, data, selected }: NodeProps & { data: MalhaComponenteNodeData }) {
  const meta = COMPONENTE_META[data.tipo]
  const vertical = data.orientacao === 'vertical'
  // Trocar a orientação muda a posição dos handles — sem o aviso, as arestas
  // ficariam ancoradas na geometria antiga até um drag forçar a remedição.
  const updateNodeInternals = useUpdateNodeInternals()
  useEffect(() => { updateNodeInternals(id) }, [vertical, id, updateNodeInternals])

  const selecaoCls = selected
    ? 'ring-2 ring-blue-500 ring-offset-2 ring-offset-canvas'
    : 'dark:group-hover:ring-1 dark:group-hover:ring-slate-500/60'

  return (
    <div className="group flex w-12 flex-col items-center" title={TITULO[data.tipo]}>
      <HandlesGramatica tipo={data.tipo} vertical={vertical} />

      {data.tipo === 'aguarde' ? (
        // Barra de sincronização (BPMN) perpendicular ao fluxo — gira com a
        // orientação — com o medalhão da ampulheta centrado nela. O invólucro
        // 32×32 segura o anel de seleção (na barra fina ele cortava em tocos —
        // lição do Aguarde das Etapas).
        <div
          className={[
            'relative flex h-8 w-8 items-center justify-center rounded-full',
            selecaoCls,
          ].join(' ')}
        >
          <div
            className={[
              'rounded-full bg-amber-600 shadow-sm transition-shadow group-hover:shadow-md',
              vertical ? 'h-2.5 w-8' : 'h-8 w-2.5',
            ].join(' ')}
          />
          <div
            className={[
              'absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2',
              'flex h-7 w-7 items-center justify-center rounded-full',
              'border-2 border-panel bg-amber-600 text-white shadow-sm',
            ].join(' ')}
          >
            <Hourglass size={15} strokeWidth={2.4} />
          </div>
        </div>
      ) : (
        // Cards (tile de ícone) — Início / Notificação / Fim.
        <div
          className={[
            `relative flex h-8 w-8 items-center justify-center rounded-xl ${meta.chip}`,
            'shadow-sm transition-shadow group-hover:shadow-md',
            selecaoCls,
          ].join(' ')}
        >
          <meta.Icon size={16} strokeWidth={2.2} />
        </div>
      )}

      {/* Rótulo embaixo — transborda o invólucro de propósito (PR #238). */}
      <p className="mt-1.5 w-[128px] break-words text-center text-[11px] font-semibold leading-tight text-ink">
        {meta.rotulo}
      </p>
      <p className="mt-0.5 w-[128px] line-clamp-1 text-center text-[9px] leading-tight text-dim">
        {subtitulo(data)}
      </p>
    </div>
  )
}

const ComponenteNode = memo(ComponenteNodeImpl)

// Quatro types registrados no React Flow (um por componente, como no desenho
// §10-F12) — todos renderizam pelo mesmo impl, guiado por data.tipo.
export const InicioNode = ComponenteNode
export const AguardeNode = ComponenteNode
export const NotificacaoNode = ComponenteNode
export const FimNode = ComponenteNode
