// Utilitários — a faixa de transferência (spec docs/spec-utilitarios-transferencia.md,
// F2): fixa no canto inferior direito, mostra o download em curso (conectando →
// barra de progresso), o resultado ("Baixado …") ou o erro, com Fechar.
// Apresentação pura: o estado vem da página; daqui sai só o gesto de fechar.
//
// ⚠️ z-[60] e data-modal-exempt: os três botões que disparam o download vivem
// DENTRO de um Modal (z-50, backdrop preto a 70%) que continua aberto depois
// do clique — com z-40 a faixa nascia atrás do véu, e o Fechar dela caía no
// backdrop e fechava o MODAL (achado grave da revisão da F2). O Toast fica
// acima (z-[100]). O data-modal-exempt tira a faixa do trap de foco do
// overlay (ver ui/overlay.ts), senão clicar em Fechar devolvia o foco ao modal.
//
// A região `aria-live` existe SEMPRE, é só para leitor de tela (sr-only) e só
// muda em marcos (25/50/75/100 %) — o painel visível muda a cada bloco. Não há
// role="status" dentro dela: região viva dentro de região viva anuncia duas
// vezes. Todo botão é type="button" — a faixa pode estar dentro de um <form>.
import { Download, Check, AlertTriangle, RefreshCw, X } from 'lucide-react'
import {
  anuncioTransferencia, fraseTransferencia, percentual, type EstadoTransferencia,
} from '../../lib/utilitariosTransferencia'

export interface BarraTransferenciaProps {
  estado: EstadoTransferencia | null
  onFechar: () => void
}

export function BarraTransferencia({ estado, onFechar }: BarraTransferenciaProps) {
  const frase = estado ? fraseTransferencia(estado) : ''
  const pct = estado?.fase === 'baixando' ? percentual(estado.feito, estado.total) : null
  const emCurso = estado?.fase === 'conectando' || estado?.fase === 'baixando'
  // `relative` no invólucro: a região sr-only é `position: absolute` e vive AQUI, no fluxo
  // da página (não dentro da faixa fixa) — sem ancestral posicionado ela se ancoraria no
  // documento e, abaixo da dobra, esticaria a área rolável (ver ui/Checkbox).
  return (
    <div data-transferencia={estado?.fase ?? 'nenhuma'} className="relative">
      <div aria-live="polite" className="sr-only" data-anuncio>{anuncioTransferencia(estado)}</div>
      {estado && (
        <div className="fixed bottom-4 right-4 z-[60] w-[min(26rem,calc(100vw-2rem))] bg-panel border border-edge rounded-lg shadow-lg p-3 flex flex-col gap-2"
          data-painel-transferencia data-modal-exempt>
          <div className="flex items-start gap-2">
            {estado.fase === 'pronto' && <Check size={16} className="text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />}
            {estado.fase === 'erro' && <AlertTriangle size={16} className="text-red-500 shrink-0 mt-0.5" />}
            {estado.fase === 'conectando' && <RefreshCw size={16} className="animate-spin text-[#1A5FA8] dark:text-blue-400 shrink-0 mt-0.5" />}
            {estado.fase === 'baixando' && <Download size={16} className="text-[#1A5FA8] dark:text-blue-400 shrink-0 mt-0.5" />}
            <p className={`text-sm flex-1 break-words ${estado.fase === 'erro' ? 'text-red-700 dark:text-red-300' : 'text-ink'}`}
              data-frase>{frase}</p>
            {!emCurso && (
              <button type="button" onClick={onFechar} aria-label="Fechar" title="Fechar" data-acao="fechar-transferencia"
                className="text-dim hover:text-ink rounded p-0.5 hover:bg-canvas shrink-0">
                <X size={14} />
              </button>
            )}
          </div>
          {emCurso && (
            <div className="h-1.5 w-full rounded bg-edge overflow-hidden" data-barra
              role="progressbar" aria-valuemin={0} aria-valuemax={100}
              aria-valuenow={pct ?? undefined} aria-valuetext={pct === null ? 'em andamento' : `${pct}%`}>
              <div className={`h-full bg-[#1A5FA8] dark:bg-blue-400 ${pct === null ? 'w-1/3 animate-pulse' : ''}`}
                style={pct === null ? undefined : { width: `${pct}%` }} data-preenchido={pct ?? 'indeterminado'} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
