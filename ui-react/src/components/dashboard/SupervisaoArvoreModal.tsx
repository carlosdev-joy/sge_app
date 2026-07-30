import { useMemo, useState } from 'react'
import {
  ReactFlow, Background, Controls,
  type Node, type Edge,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Modal } from '../ui/Modal'
import { Select } from '../ui/Input'
import {
  JobNode, STATUS, statusLabel, type DsGraphStatus,
} from '../console/DsRunGraphModal'
import { ArrowRight, ArrowDown, Timer } from 'lucide-react'

// Diagrama da árvore de níveis de um job supervisionado.
//
// Diferença essencial em relação ao diagrama do Console DataStage: lá o desenho
// é de UM nível por vez e descer exige um novo `dsjob` por clique (drill-down).
// Aqui a árvore inteira já está no banco — a DAG varreu em largura e gravou
// nivel/job_pai de cada job —, então dá para desenhar os 4 níveis de uma vez,
// sem SSH e sem clique. É essa varredura que revelou o abort três níveis abaixo
// que as sequences intermediárias reportavam como "concluído".
//
// O vocabulário visual (cor, ícone, rótulo) vem de DsRunGraphModal de propósito:
// os dois diagramas têm de parecer o mesmo diagrama.

export interface ArvoreFilho {
  run_inicio: string
  job_filho: string
  status_code: number
  status: string
  falhou: boolean
  nivel: number
  job_pai: string | null
  inicio?: string | null
  fim?: string | null
  duracao_seg?: number | null
}

export interface ArvoreRun {
  inicio: string | null
  fim: string | null
  resultado: string
}

type Dir = 'LR' | 'TB'

// Mesmos códigos do Console DataStage (dsCodeToStatus em DsConsole.tsx) — o
// DataStage não tem um código só para "abortou", e tratar 96/97/13 como sucesso
// esconderia falha de verdade. 0 e -1 são "disparado, sem status no log".
function codigoParaStatus(code: number): DsGraphStatus {
  if (code === 1 || code === 11) return 'ok'
  if (code === 2 || code === 12) return 'warning'
  if (code === 21) return 'reset'
  if (code === 3 || code === 13 || code === 96 || code === 97 || code === 98) return 'aborted'
  if (code === 0) return 'running'
  return 'unknown'
}

function resultadoParaStatus(resultado: string | undefined): DsGraphStatus {
  return resultado === 'ok' ? 'ok'
    : resultado === 'aborted' ? 'aborted'
    : resultado === 'running' ? 'running' : 'unknown'
}

/** '2026-07-29 06:12:03' → '06:12' */
function hora(iso: string | null | undefined): string {
  if (!iso) return ''
  const parte = iso.split(' ')[1] ?? iso.split('T')[1]
  return parte ? parte.slice(0, 5) : ''
}

function duracao(seg: number | null | undefined): string {
  if (seg == null) return ''
  const h = Math.floor(seg / 3600)
  const m = Math.floor((seg % 3600) / 60)
  if (h) return `${h}h${String(m).padStart(2, '0')}m`
  if (m) return `${m}min`
  return `${seg}s`
}

/** Linha de tempo do nó: '06:12 → 06:19 (7min)', ou '—' quando não se sabe. */
function janela(f: ArvoreFilho): string {
  const ini = hora(f.inicio), fim = hora(f.fim)
  if (!ini && !fim) return '—'
  const d = duracao(f.duracao_seg)
  return `${ini || '—'} → ${fim || '—'}${d ? ` (${d})` : ''}`
}

const nodeTypes = { job: JobNode }

const FILTRAVEL: DsGraphStatus[] = ['ok', 'warning', 'aborted', 'running']

export function SupervisaoArvoreModal({
  open, onClose, rootJob, filhos, runs,
}: {
  open: boolean
  onClose: () => void
  rootJob: string
  filhos: ArvoreFilho[]
  runs: ArvoreRun[]
}) {
  const [dir, setDir] = useState<Dir>('LR')
  const [filtro, setFiltro] = useState<Set<DsGraphStatus>>(new Set())
  const [runSel, setRunSel] = useState<string | null>(null)

  // Um dia pode ter vários runs do mesmo job; cada um tem a sua árvore. Os
  // filhos já vêm marcados com o run a que pertencem.
  const runsComArvore = useMemo(() => {
    const chaves = [...new Set(filhos.map(f => f.run_inicio))].sort()
    return chaves.map(k => ({
      chave: k,
      run: runs.find(r => r.inicio === k),
      total: filhos.filter(f => f.run_inicio === k).length,
    }))
  }, [filhos, runs])

  // Default: o run MAIS RECENTE do dia (mesma escolha do diagrama do console).
  const chaveAtual = runSel ?? runsComArvore[runsComArvore.length - 1]?.chave ?? null
  const runAtual = runsComArvore.find(r => r.chave === chaveAtual)

  const doRun = useMemo(
    () => filhos.filter(f => f.run_inicio === chaveAtual),
    [filhos, chaveAtual])

  const visiveis = useMemo(
    () => doRun.filter(f => filtro.size === 0 || filtro.has(codigoParaStatus(f.status_code))),
    [doRun, filtro])

  // Gargalo = o job de maior duração conhecida. Só entre os visíveis: filtrar
  // por status e continuar apontando um gargalo escondido confundiria.
  const gargalo = useMemo(() => {
    let nome: string | null = null, maior = -1
    visiveis.forEach(f => {
      if (f.duracao_seg != null && f.duracao_seg > maior) { maior = f.duracao_seg; nome = f.job_filho }
    })
    return { nome, seg: maior >= 0 ? maior : null }
  }, [visiveis])

  const { nodes, edges } = useMemo(() => {
    const ns: Node[] = []
    const es: Edge[] = []

    // Agrupa por nível para posicionar: o nível é a COLUNA (ou a linha, em
    // vertical) e a posição dentro do nível é a ordem de leitura.
    const porNivel = new Map<number, ArvoreFilho[]>()
    visiveis.forEach(f => {
      const n = f.nivel ?? 1
      if (!porNivel.has(n)) porNivel.set(n, [])
      porNivel.get(n)!.push(f)
    })

    const raizStatus = resultadoParaStatus(runAtual?.run?.resultado)
    const alturaRaiz = Math.max(0, ((porNivel.get(1)?.length ?? 1) - 1) * 40)
    ns.push({
      id: '__root__', type: 'job',
      position: dir === 'TB' ? { x: 320, y: 0 } : { x: 0, y: alturaRaiz },
      data: {
        label: rootJob, status: raizStatus,
        sub: `nível 0 · ${statusLabel(raizStatus)}`,
        time: runAtual?.run
          ? `${hora(runAtual.run.inicio) || '—'} → ${hora(runAtual.run.fim) || '—'}`
          : undefined,
        isRoot: true, dir,
      } as unknown as Record<string, unknown>,
    })

    const idPorJob = new Map<string, string>()
    ;[...porNivel.keys()].sort((a, b) => a - b).forEach(nivel => {
      porNivel.get(nivel)!.forEach((f, i) => {
        const id = `n${nivel}-${i}`
        idPorJob.set(f.job_filho, id)
        ns.push({
          id, type: 'job',
          position: dir === 'TB'
            ? { x: i * 300, y: nivel * 190 }
            : { x: nivel * 340, y: i * 92 },
          data: {
            label: f.job_filho,
            status: codigoParaStatus(f.status_code),
            sub: `nível ${nivel} · ${f.status}`,
            time: janela(f),
            dir,
            critical: gargalo.nome === f.job_filho,
          } as unknown as Record<string, unknown>,
        })
      })
    })

    // Aresta = quem disparou quem. job_pai nulo é o histórico anterior à
    // migration 065, quando só existia o primeiro nível: aí o pai é a raiz.
    visiveis.forEach(f => {
      const destino = idPorJob.get(f.job_filho)
      if (!destino) return
      const origem = f.job_pai && idPorJob.has(f.job_pai)
        ? idPorJob.get(f.job_pai)!
        : '__root__'
      const st = codigoParaStatus(f.status_code)
      es.push({
        id: `e-${destino}`, source: origem, target: destino,
        animated: st === 'aborted',
        style: {
          stroke: st === 'aborted' ? '#ef4444' : st === 'warning' ? '#f59e0b' : '#94a3b8',
          strokeWidth: st === 'aborted' ? 2 : 1,
        },
      })
    })

    return { nodes: ns, edges: es }
  }, [visiveis, rootJob, dir, runAtual, gargalo.nome])

  const niveis = [...new Set(doRun.map(f => f.nivel ?? 1))].sort()
  const comFalha = doRun.filter(f => f.falhou).length
  const semHorario = doRun.length > 0 && doRun.every(f => !f.inicio && !f.fim)

  return (
    <Modal open={open} onClose={onClose} title={`Fluxo do processo — ${rootJob}`} size="2xl">
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-dim">
            {doRun.length} job(s) em {niveis.length} nível(is)
            {comFalha > 0 && <span className="text-red-600 dark:text-red-400 font-medium"> · {comFalha} com falha</span>}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {runsComArvore.length > 1 && (
            <>
              <span className="text-xs text-dim">Execução:</span>
              <Select value={chaveAtual ?? ''} onChange={ev => setRunSel(ev.target.value)} className="w-auto">
                {runsComArvore.map(r => (
                  <option key={r.chave} value={r.chave}>
                    {hora(r.chave) || r.chave} · {r.total} job(s)
                    {r.run ? ` · ${statusLabel(resultadoParaStatus(r.run.resultado))}` : ''}
                  </option>
                ))}
              </Select>
            </>
          )}
          <div className="inline-flex rounded-lg border border-edge overflow-hidden">
            <button onClick={() => setDir('LR')} title="Esquerda → direita"
              className={`px-2 py-1.5 text-xs flex items-center gap-1 ${dir === 'LR' ? 'bg-[#1A5FA8] text-white' : 'bg-panel text-dim hover:text-ink'}`}>
              <ArrowRight size={13} /> Horizontal
            </button>
            <button onClick={() => setDir('TB')} title="Cima → baixo"
              className={`px-2 py-1.5 text-xs flex items-center gap-1 border-l border-edge ${dir === 'TB' ? 'bg-[#1A5FA8] text-white' : 'bg-panel text-dim hover:text-ink'}`}>
              <ArrowDown size={13} /> Vertical
            </button>
          </div>
          {gargalo.nome && gargalo.seg != null && (
            <span className="px-2 py-1.5 text-xs rounded-lg border border-violet-300 dark:border-violet-800 bg-violet-50 dark:bg-violet-900/20 text-violet-700 dark:text-violet-300 inline-flex items-center gap-1"
              title={`Job de maior duração conhecida: ${gargalo.nome}`}>
              <Timer size={13} /> gargalo: {duracao(gargalo.seg)}
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-dim">Filtrar:</span>
          {FILTRAVEL.map(st => {
            const cnt = doRun.filter(f => codigoParaStatus(f.status_code) === st).length
            const ativo = filtro.has(st)
            const Icon = STATUS[st].Icon
            return (
              <button key={st} disabled={cnt === 0}
                onClick={() => setFiltro(prev => {
                  const next = new Set(prev)
                  if (next.has(st)) next.delete(st)
                  else next.add(st)
                  return next
                })}
                className={`px-2 py-1 rounded-lg text-[11px] border inline-flex items-center gap-1 transition-colors
                  ${cnt === 0 ? 'opacity-40 cursor-default border-edge text-dim'
                    : ativo ? 'bg-[#1A5FA8] text-white border-[#1A5FA8]'
                    : 'bg-panel text-ink border-edge hover:bg-edge/40'}`}>
                <Icon size={11} className={ativo ? '' : STATUS[st].text} /> {statusLabel(st)} ({cnt})
              </button>
            )
          })}
          {filtro.size > 0 && (
            <button onClick={() => setFiltro(new Set())} className="text-[11px] text-dim hover:text-ink underline ml-1">limpar</button>
          )}
        </div>

        {semHorario && (
          <p className="text-[11px] text-amber-700 dark:text-amber-400">
            Sem horário por job nesta execução — ela foi coletada antes da migration 066.
            As próximas execuções já trazem início, fim e duração.
          </p>
        )}

        {doRun.length === 0 ? (
          <p className="text-sm text-dim p-4">
            Nenhum job abaixo deste ainda foi lido nesta data. A varredura profunda
            roda no primeiro ciclo <strong>depois</strong> que a execução termina —
            execução em andamento mostra só o nível 1, e vai completando.
          </p>
        ) : visiveis.length === 0 ? (
          <p className="text-sm text-dim p-4">Nenhum job com o filtro selecionado.</p>
        ) : (
          <>
            <p className="text-[11px] text-dim">
              A seta vermelha é o caminho da falha. O desenho vem do banco — nenhuma
              consulta ao DataStage acontece ao abrir esta janela.
            </p>
            <div className="relative rounded-lg border border-edge bg-canvas" style={{ height: '58vh' }}>
              <ReactFlow
                key={dir}
                nodes={nodes} edges={edges} nodeTypes={nodeTypes}
                fitView nodesDraggable={false} nodesConnectable={false} elementsSelectable={false}
                minZoom={0.15}
              >
                <Background />
                <Controls showInteractive={false} />
              </ReactFlow>
            </div>
          </>
        )}
      </div>
    </Modal>
  )
}
