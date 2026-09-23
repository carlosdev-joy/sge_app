// Cartão de uma proposta do agente (F5): o que será gravado, a evidência ao
// lado, e Aprovar/Recusar.
//
// A evidência fica LADO A LADO com o valor, não escondida atrás de um clique:
// o risco 15 da spec é o operador aprovar no automático, e o que o impede é
// ver, na hora de decidir, o trecho que as ferramentas leram. Depois de
// decidida, o cartão fica como registro (quem, quando) e os botões somem.
//
// Apresentação pura — quem chama a API é `pages/Agentes.tsx`.
import { useId } from 'react'
import { Check, X } from 'lucide-react'
import type { DecisaoProposta, PropostaAgente } from '../../lib/agentes'
import { ESTADO_PROPOSTA, TIPOS_PROPOSTA, quando, valorDaProposta } from '../../lib/agentes'

interface Props {
  proposta: PropostaAgente
  decidindo: boolean
  onDecidir: (id: number, decisao: DecisaoProposta) => void
}

const TOM_ESTADO: Record<PropostaAgente['estado'], string> = {
  pendente: 'text-amber-700 dark:text-amber-300',
  aprovada: 'text-emerald-700 dark:text-emerald-300',
  recusada: 'text-dim',
  expirada: 'text-dim',
}

export function CartaoProposta({ proposta, decidindo, onDecidir }: Props) {
  const tituloId = useId()
  const pendente = proposta.estado === 'pendente'
  const tipo = TIPOS_PROPOSTA[proposta.tipo] ?? proposta.tipo

  return (
    <section
      role="group"
      aria-labelledby={tituloId}
      className="mt-2 rounded-lg border border-edge bg-canvas px-3 py-2.5 text-sm"
      data-agentes-proposta={proposta.estado}
    >
      <h3 id={tituloId} className="text-[13px] font-semibold text-ink">
        Proposta de registro · {tipo} · <span className="font-mono">{proposta.job_name}</span>
      </h3>

      <div className="grid gap-2 mt-2 sm:grid-cols-2">
        <div className="min-w-0">
          <p className="text-[11px] uppercase tracking-wide text-dim">O que será gravado</p>
          <p className="text-ink font-medium break-words mt-0.5">{proposta.chave}</p>
          <p className="text-ink whitespace-pre-wrap break-words mt-0.5" data-agentes-proposta-valor>
            {valorDaProposta(proposta.valor)}
          </p>
          {proposta.motivo && (
            <p className="text-[12px] text-dim mt-1 break-words">Motivo: {proposta.motivo}</p>
          )}
        </div>
        <div className="min-w-0">
          <p className="text-[11px] uppercase tracking-wide text-dim">Evidência lida pelas ferramentas</p>
          <blockquote
            className="mt-0.5 border-l-2 border-edge pl-2 font-mono text-[12px] text-ink whitespace-pre-wrap break-words"
            data-agentes-proposta-evidencia
          >
            {proposta.evidencia || '—'}
          </blockquote>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 mt-2.5">
        <p className={`text-[12px] ${TOM_ESTADO[proposta.estado]}`} aria-live="polite">
          {ESTADO_PROPOSTA[proposta.estado]}
          {!pendente && proposta.decidida_em && ` · ${quando(proposta.decidida_em)}`}
          {proposta.estado === 'aprovada' && ' — registrado para as próximas consultas'}
        </p>
        {pendente && (
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => onDecidir(proposta.id, 'recusar')}
              disabled={decidindo}
              aria-label={`Recusar proposta: ${proposta.chave}`}
              className="rounded-md border border-edge bg-panel px-2.5 py-1 text-[13px] text-ink
                         hover:bg-canvas disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
            >
              <X className="w-3.5 h-3.5" aria-hidden="true" />
              Recusar
            </button>
            <button
              type="button"
              onClick={() => onDecidir(proposta.id, 'aprovar')}
              disabled={decidindo}
              aria-label={`Aprovar proposta: ${proposta.chave}`}
              className="rounded-md px-2.5 py-1 text-[13px] font-medium bg-[#1A5FA8] text-white
                         hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
            >
              <Check className="w-3.5 h-3.5" aria-hidden="true" />
              {decidindo ? 'Salvando…' : 'Aprovar'}
            </button>
          </div>
        )}
      </div>
    </section>
  )
}
