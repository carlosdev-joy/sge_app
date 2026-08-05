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
import { AlertTriangle, Hourglass, Lock } from 'lucide-react'
import type { Orientacao } from '../etapas/layoutGrafo'
// Metadados (rótulo/chip/ícone por tipo) em módulo PURO — compartilhados com
// a paleta e o minimapa do MalhaEditor sem quebrar o react-refresh daqui.
import { COMPONENTE_META, type TipoComponente } from './componenteMeta'

// F15 (desenho §8): estado do componente na VISÃO DE EXECUÇÃO — camada
// derivada de dados que o payload já tem (execucoes[] × upstream do servidor
// + eventos_no[] da F14), montada pelo MalhaEditor. Ausente (null/undefined)
// = modo Montagem OU nó sem dado na data — o card fica neutro, a regra F9 de
// nunca inventar cor.
export type ExecComponente =
  | {
      // Início: as raízes ligadas contadas POR STATUS (nunca por presença de
      // linha — PULADO e FALHA são linha registrada e NÃO são partida bem
      // sucedida; verde é SUCESSO em todo o canvas) + a próxima execução do
      // agendamento (display-only — a autoridade é o scheduler).
      kind: 'inicio'
      raizes: number
      sucesso: number
      falha: number
      pulado: number
      emCurso: number       // EXECUTANDO / AGUARDANDO_DEPENDENCIA / outros
      semLinha: number      // sem execução registrada na data
      proxima: string | null
    }
  | {
      // Aguarde: derivação client-side de execucoes[] × upstream (§8) — o
      // upstream vem do SERVIDOR (§3.2), o front nunca expande.
      kind: 'aguarde'
      estado: 'satisfeito' | 'bloqueado' | 'aguardando'
      faltam: string[]
      bloqueiam: string[]
      // Quantas entradas o nó tem no desenho. Sem ela o card dizia só "faltam
      // 3" e a pergunta seguinte era sempre "de quantas?" — o operador conta
      // as setas na tela para saber se o número fecha.
      total: number
    }
  // Notificação/Fim: `semEntradas` = upstream VAZIO (nenhum pipeline chega,
  // nem através de Aguarde) — a guardiã PULA o nó e nunca emite (Decisão 13);
  // prometer "aguardando" ali seria promessa falsa.
  | { kind: 'notificacao'; emitidaEm: string | null; semEntradas: boolean }
  // F4 (§9.3): o Fim é o único nó que fala de CICLO, e até esta fase ele tinha
  // dois estados só — verde (concluída) ou apagado. Faltava o terceiro, que é
  // o do meio da madrugada: `cicloAberto` = existe uma corrida ABERTA nesta
  // lente. Anel azul DISCRETO e tooltip, **sem texto novo no nó** (D75/#11: o
  // número já está na faixa a 3 cm de distância).
  | {
      kind: 'fim'
      concluidaEm: string | null
      semEntradas: boolean
      cicloAberto?: boolean
    }

export interface MalhaComponenteNodeData {
  // id da linha em etl_malha_no — o id do NÓ no canvas é "no:{noId}" (§9).
  noId: number
  tipo: TipoComponente
  // Contagens de arestas de nó (payload do detalhe) — o subtítulo do card é
  // honesto sobre o que está ligado; o aviso estrutural mora no banner.
  entradas: number
  saidas: number
  // config_json do nó (título da Notificação etc.).
  config?: Record<string, unknown> | null
  orientacao?: Orientacao
  // F13 (só no Início): resumo do agendamento da MALHA (o agendamento mora
  // nela, Decisão 8 — o nó é o plugue) e o badge de contradição — alguma
  // raiz assinada ganhou dependência por outra porta (§2.2): o motor
  // obedece a dependência e o agendamento da malha está inerte nela.
  agendaResumo?: string | null
  contradicao?: boolean
  // F15: estado do componente na visão de Execução (null/ausente = neutro).
  execNo?: ExecComponente | null
  // 082: Aguarde SEGURADO — enquanto estiver, ele não solta ninguém. Ausente
  // = o banco não tem a migration e a tela não oferece nem mostra a trava.
  retidoEm?: string | null
  retidoPor?: string | null
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
      // F13: com agendamento configurado, o resumo da malha manda; senão a
      // contagem honesta do que está ligado.
      if (data.agendaResumo) return data.agendaResumo
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

// ── Camada de execução (F15 — desenho §8) ───────────────────────────────────
// Anel por CIMA do desenho (outline, como no MalhaPipelineNode: não briga com
// o ring azul de seleção) — SÓ quando o dado sustenta o estado; linha de
// estado embaixo do subtítulo; detalhe completo no tooltip.

const ANEL = {
  verde: 'outline outline-2 outline-offset-2 outline-green-500/70 dark:outline-green-400/60',
  teal: 'outline outline-2 outline-offset-2 outline-teal-500/70 dark:outline-teal-400/60',
  vermelho: 'outline outline-2 outline-offset-2 outline-red-500/80 dark:outline-red-400/70',
  ambar: 'outline outline-2 outline-offset-2 outline-amber-400/60 dark:outline-amber-500/50',
  // F4 — "ciclo aberto" no nó Fim. DISCRETO (opacidade menor que a dos outros)
  // e SEM animação: a §9.15/#13 fecha a lista dos três animados desta camada
  // (o segmento vivo da barra, o dot de ABERTA e a aresta ativa), e o anel de
  // um nó que só espera não entra nela.
  azul: 'outline outline-2 outline-offset-2 outline-blue-500/60 dark:outline-blue-400/50',
}

function horaCurtaLocal(iso: string | null): string | null {
  if (!iso) return null
  const d = new Date(iso)
  return isNaN(d.getTime())
    ? iso
    : d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

// Anel do estado — string vazia = apagado (evento ausente ≠ problema).
// VERDE É SUCESSO, em todo o canvas: o Início só acende verde com TODAS as
// raízes em SUCESSO; falha pinta vermelho; PULADO/em curso/sem linha ficam
// sem anel (o texto conta a verdade).
function execAnel(e: ExecComponente): string {
  switch (e.kind) {
    case 'inicio':
      if (e.falha > 0) return ANEL.vermelho
      return e.raizes > 0 && e.sucesso === e.raizes ? ANEL.verde : ''
    case 'aguarde':
      return e.estado === 'satisfeito' ? ANEL.verde
        : e.estado === 'bloqueado' ? ANEL.vermelho : ANEL.ambar
    case 'notificacao':
      return e.emitidaEm ? ANEL.teal : ''
    case 'fim':
      if (e.concluidaEm) return ANEL.verde
      // O ciclo está ABERTO: o nó não está apagado, está esperando. Só o anel
      // muda — a linha de estado embaixo continua dizendo "em andamento", que
      // já era a verdade e continua sendo.
      return e.cicloAberto ? ANEL.azul : ''
  }
}

function plur(n: number, s: string, p: string): string {
  return `${n} ${n === 1 ? s : p}`
}

// Linha de estado sob o subtítulo (texto curto; a lista completa vai no
// tooltip). null = nada a dizer.
function execLinha(e: ExecComponente): { texto: string; cls: string } | null {
  switch (e.kind) {
    case 'inicio': {
      if (e.falha > 0) {
        return { texto: `${plur(e.falha, 'raiz', 'raízes')} com falha`,
                 cls: 'text-red-700 dark:text-red-400' }
      }
      if (e.sucesso === e.raizes) {
        return { texto: `todas com sucesso (${e.raizes})`,
                 cls: 'text-green-700 dark:text-green-400' }
      }
      if (e.semLinha === e.raizes) {
        return { texto: 'sem execução na data', cls: 'text-dim' }
      }
      if (e.pulado > 0 && e.sucesso === 0 && e.emCurso === 0) {
        // Dia em que a regra de agenda não deixou rodar (sábado com
        // somente_dias_uteis, blackout): PULADO não é partida.
        return { texto: `${plur(e.pulado, 'pulada', 'puladas')}`, cls: 'text-dim' }
      }
      return { texto: `${e.sucesso}/${e.raizes} com sucesso`, cls: 'text-dim' }
    }
    case 'aguarde':
      if (e.estado === 'satisfeito') {
        return { texto: 'satisfeito', cls: 'text-green-700 dark:text-green-400' }
      }
      if (e.estado === 'bloqueado') {
        return {
          texto: `bloqueado: ${e.bloqueiam.join(', ')}`,
          cls: 'text-red-700 dark:text-red-400',
        }
      }
      return {
        texto: `aguardando (falta${e.faltam.length === 1 ? '' : 'm'} `
          + `${e.faltam.length} de ${e.total})`,
        cls: 'text-amber-700 dark:text-amber-400',
      }
    case 'notificacao':
      if (e.emitidaEm) {
        return { texto: `emitida às ${horaCurtaLocal(e.emitidaEm)}`,
                 cls: 'text-teal-700 dark:text-teal-400' }
      }
      return e.semEntradas
        ? { texto: 'sem entradas — não emite', cls: 'text-dim' }
        : { texto: 'aguardando', cls: 'text-dim' }
    case 'fim':
      if (e.concluidaEm) {
        return { texto: `concluída às ${horaCurtaLocal(e.concluidaEm)}`,
                 cls: 'text-green-700 dark:text-green-400' }
      }
      return e.semEntradas
        ? { texto: 'sem entradas — não conclui', cls: 'text-dim' }
        : { texto: 'em andamento', cls: 'text-dim' }
  }
}

// Detalhe do estado para o tooltip (anexado ao título semântico do tipo).
function execTitulo(e: ExecComponente): string | null {
  switch (e.kind) {
    case 'inicio': {
      const detalhe = [
        `sucesso: ${e.sucesso}`,
        ...(e.falha > 0 ? [`falha: ${e.falha}`] : []),
        ...(e.pulado > 0 ? [`pulado: ${e.pulado}`] : []),
        ...(e.emCurso > 0 ? [`em curso: ${e.emCurso}`] : []),
        ...(e.semLinha > 0 ? [`sem execução: ${e.semLinha}`] : []),
      ].join(' · ')
      const partes = [`raízes ligadas: ${e.raizes} — ${detalhe}`]
      if (e.proxima) partes.push(`próxima execução: ${e.proxima}`)
      return partes.join('\n')
    }
    case 'aguarde':
      if (e.estado === 'satisfeito') {
        return `todas as ${e.total} entradas com SUCESSO na data`
      }
      if (e.estado === 'bloqueado') {
        return `bloqueado por: ${e.bloqueiam.join(', ')}`
      }
      // Diz também quantas JÁ estão prontas: sem isso, uma entrada que rodou
      // fora de ordem (pipeline ainda no cron antigo, publicação pendente)
      // vira um número que não fecha com o desenho.
      return `${e.total - e.faltam.length} de ${e.total} com SUCESSO na data\n`
        + `aguardando: ${e.faltam.join(', ')}`
    case 'notificacao':
      if (e.emitidaEm) return `notificação emitida às ${horaCurtaLocal(e.emitidaEm)}`
      return e.semEntradas
        ? 'nenhum pipeline chega a este nó (nem através de um Aguarde) — a '
          + 'guardiã não avalia e NENHUM evento será emitido: ligue as entradas'
        : 'aguardando — o evento sai quando todas as entradas tiverem SUCESSO na data'
    case 'fim':
      if (e.concluidaEm) return `malha concluída às ${horaCurtaLocal(e.concluidaEm)}`
      if (e.semEntradas) {
        return 'nenhum pipeline chega a este nó (nem através de um Aguarde) — a '
          + 'conclusão NUNCA será registrada: ligue as entradas'
      }
      // F4: com a corrida no payload, o nó Fim diz que o CICLO está aberto —
      // e não só que ele próprio ainda não acendeu.
      return e.cicloAberto
        ? 'ciclo aberto — esta corrida ainda não passou pelo Fim; a conclusão é '
          + 'registrada quando todos os ligados tiverem SUCESSO na data'
        : 'em andamento — a conclusão é registrada quando todos os ligados tiverem SUCESSO na data'
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

  // F15: camada de execução — anel/linha SÓ quando o editor passou estado
  // (modo Execução com dado na data); sem ela o card é o da montagem.
  const exec = data.execNo ?? null
  const anelExec = exec ? execAnel(exec) : ''
  const linhaExec = exec ? execLinha(exec) : null
  const tituloExec = exec ? execTitulo(exec) : null
  const titulo = tituloExec
    ? `${TITULO[data.tipo]}\n${tituloExec}`
    : TITULO[data.tipo]

  return (
    <div className="group flex w-12 flex-col items-center" title={titulo}>
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
            anelExec,
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
            {/* 082: cadeado do Aguarde SEGURADO — a informação mais dura do
                card: enquanto estiver ali, nada passa por este ponto. */}
            {data.retidoEm && (
              <span
                title={`Aguarde SEGURADO${data.retidoPor ? ` por ${data.retidoPor}` : ''}`
                  + ` em ${data.retidoEm} — nenhum pipeline depois dele é liberado até você soltar.`}
                className="absolute -left-2 -top-2 flex h-4 w-4 items-center justify-center rounded-full border border-panel bg-red-600 text-white"
              >
                <Lock size={9} strokeWidth={2.6} />
              </span>
            )}
          </div>
        </div>
      ) : (
        // Cards (tile de ícone) — Início / Notificação / Fim.
        <div
          className={[
            `relative flex h-8 w-8 items-center justify-center rounded-xl ${meta.chip}`,
            'shadow-sm transition-shadow group-hover:shadow-md',
            selecaoCls,
            anelExec,
          ].join(' ')}
        >
          <meta.Icon size={16} strokeWidth={2.2} />
          {/* 082: cadeado do Início SEGURADO — a malha não parte enquanto
              estiver ali. Mesmo canto e mesma cor do cadeado do Aguarde: é a
              mesma informação, no ponto onde ela vale. */}
          {data.tipo === 'inicio' && data.retidoEm && (
            <span
              title={`Início SEGURADO${data.retidoPor ? ` por ${data.retidoPor}` : ''}`
                + ` em ${data.retidoEm} — a malha não parte até você soltar.`}
              className="absolute -left-1.5 -top-1.5 flex h-4 w-4 items-center justify-center rounded-full border border-panel bg-red-600 text-white"
            >
              <Lock size={9} strokeWidth={2.6} />
            </span>
          )}
          {/* F13: badge de contradição no Início (§2.2) — raiz assinada com
              dependência; o texto completo mora no banner de avisos. */}
          {data.tipo === 'inicio' && data.contradicao && (
            <span
              title="Alguma raiz deste Início tem dependência cadastrada — o motor obedece a dependência e o agendamento da malha está inerte nela (veja o banner de avisos)."
              className="absolute -right-1.5 -top-1.5 flex h-4 w-4 items-center justify-center rounded-full border border-panel bg-amber-500 text-white"
            >
              <AlertTriangle size={9} strokeWidth={2.6} />
            </span>
          )}
        </div>
      )}

      {/* Rótulo embaixo — transborda o invólucro de propósito (PR #238). */}
      <p className="mt-1.5 w-[128px] break-words text-center text-[11px] font-semibold leading-tight text-ink">
        {meta.rotulo}
      </p>
      <p className="mt-0.5 w-[128px] line-clamp-1 text-center text-[9px] leading-tight text-dim">
        {subtitulo(data)}
      </p>
      {/* F15: linha de estado da visão de Execução — só com dado na data. */}
      {linhaExec && (
        <p className={`mt-0.5 w-[128px] break-words text-center text-[9px] font-semibold leading-tight line-clamp-2 ${linhaExec.cls}`}>
          {linhaExec.texto}
        </p>
      )}
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
