// ── Faixa de conferência do nome do job contra o DataStage ───────────────────
// Usada nos DOIS lugares onde uma etapa DataStage é cadastrada: o modal da tela
// Jobs (Lista) e o dock de propriedades do canvas de Etapas. A regra de veredito
// mora em lib/dsJobs.ts (fonte única); aqui só a apresentação.
//
// Estados e por que cada um é visualmente diferente:
//   caixa        → ALERTA forte. É o incidente: o nome bate ignorando a caixa,
//                  mas o DataStage é case-sensitive e não vai achar o job.
//                  Traz a grafia oficial num botão de UM CLIQUE.
//   ausente      → aviso, com os nomes parecidos também acionáveis.
//   exato        → confirmação DISCRETA. Silêncio não distingue "conferi e está
//                  certo" de "não consegui conferir" — por isso o visto existe.
//   indivel.     → aviso honesto e neutro. NUNCA bloqueia o cadastro.
import { AlertTriangle, CheckCircle2, HelpCircle, Loader2 } from 'lucide-react'
import type { ConferenciaDs } from '../../lib/dsJobs'

export interface ConferenciaDsJobProps {
  conferencia: ConferenciaDs
  project: string | null
  carregando?: boolean
  /** Aplica a grafia oficial. Ausente = mostra o nome sem botão (só informativo). */
  onUsarGrafia?: (nome: string) => void
  /** Rótulo do botão de correção — muda entre "preencher" e "renomear". */
  rotuloAcao?: string
}

const CAIXA_BOX = 'border-amber-400 bg-amber-50 dark:border-amber-600 dark:bg-amber-900/25'
const AVISO_BOX = 'border-amber-200 bg-amber-50/70 dark:border-amber-800 dark:bg-amber-900/15'
const OK_BOX = 'border-emerald-200 bg-emerald-50/60 dark:border-emerald-800/60 dark:bg-emerald-900/15'
const NEUTRO_BOX = 'border-edge bg-panel'

export function ConferenciaDsJob({
  conferencia, project, carregando, onUsarGrafia, rotuloAcao = 'Usar esta grafia',
}: ConferenciaDsJobProps) {
  if (conferencia.status === 'vazio') return null

  if (carregando) {
    return (
      <div className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 ${NEUTRO_BOX}`}>
        <Loader2 size={13} className="shrink-0 animate-spin text-dim" />
        <p className="text-[11px] text-dim">Conferindo o nome no DataStage…</p>
      </div>
    )
  }

  if (conferencia.status === 'exato') {
    return (
      <div className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 ${OK_BOX}`}>
        <CheckCircle2 size={13} className="shrink-0 text-emerald-600 dark:text-emerald-400" />
        <p className="text-[11px] text-emerald-800 dark:text-emerald-300">
          Confere no DataStage{project ? <> (projeto <span className="font-mono">{project}</span>)</> : null}.
        </p>
      </div>
    )
  }

  if (conferencia.status === 'indisponivel') {
    return (
      <div className={`flex items-start gap-1.5 rounded-lg border px-2.5 py-1.5 ${NEUTRO_BOX}`}>
        <HelpCircle size={13} className="mt-0.5 shrink-0 text-dim" />
        <div className="min-w-0">
          <p className="text-[11px] text-dim">
            Não foi possível conferir o nome no DataStage agora — o cadastro segue
            normalmente.
          </p>
          {conferencia.motivo && (
            <p className="mt-0.5 break-words text-[10px] text-dim/70">{conferencia.motivo}</p>
          )}
        </div>
      </div>
    )
  }

  if (conferencia.status === 'caixa') {
    return (
      <div className={`flex flex-col gap-1.5 rounded-lg border px-2.5 py-2 ${CAIXA_BOX}`}>
        <div className="flex items-start gap-1.5">
          <AlertTriangle size={13} className="mt-0.5 shrink-0 text-amber-700 dark:text-amber-400" />
          <p className="text-[11px] leading-snug text-amber-900 dark:text-amber-200">
            <strong>O DataStage grava este job com OUTRA grafia.</strong> Ele
            diferencia maiúsculas de minúsculas — com o nome atual o disparo falha
            com “Cannot find job”. No projeto{' '}
            {project ? <span className="font-mono">{project}</span> : 'do pipeline'} o
            nome é <span className="font-mono font-semibold">{conferencia.sugestao}</span>.
          </p>
        </div>
        {onUsarGrafia && conferencia.sugestao && (
          <button
            type="button"
            onClick={() => onUsarGrafia(conferencia.sugestao!)}
            className="self-start rounded-md border border-amber-500 bg-amber-500/15 px-2 py-1 font-mono text-[11px] font-semibold text-amber-900 transition-colors hover:bg-amber-500/30 dark:border-amber-500/70 dark:text-amber-200"
          >
            {rotuloAcao}: {conferencia.sugestao}
          </button>
        )}
      </div>
    )
  }

  // 'ausente'
  return (
    <div className={`flex flex-col gap-1.5 rounded-lg border px-2.5 py-2 ${AVISO_BOX}`}>
      <div className="flex items-start gap-1.5">
        <AlertTriangle size={13} className="mt-0.5 shrink-0 text-amber-600 dark:text-amber-400" />
        <p className="text-[11px] leading-snug text-amber-800 dark:text-amber-300">
          Não existe job com esse nome no projeto{' '}
          {project ? <span className="font-mono">{project}</span> : 'do pipeline'} do
          DataStage. O cadastro não fica bloqueado, mas a execução vai falhar com
          “Cannot find job”.
        </p>
      </div>
      {conferencia.parecidos.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-[10px] text-amber-800/80 dark:text-amber-300/70">Parecidos:</span>
          {conferencia.parecidos.map(n => (
            <button
              key={n}
              type="button"
              disabled={!onUsarGrafia}
              onClick={() => onUsarGrafia?.(n)}
              className="rounded-full border border-amber-300 bg-amber-100/70 px-2 py-0.5 font-mono text-[10px] text-amber-900 transition-colors hover:bg-amber-200 disabled:cursor-default disabled:opacity-70 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-200 dark:hover:bg-amber-900/60"
            >
              {n}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
