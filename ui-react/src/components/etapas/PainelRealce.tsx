// Painel do realce de dependências — mesma peça nos dois canvas (etapas e
// malha). F1 da spec de operação no nível de etapa (§6, Bloco D).
//
// Só aparece com algo em foco: sem clique, o canvas é o de sempre. Os textos
// do contador chegam PRONTOS do editor (cada canvas tem o seu substantivo:
// "etapas" no pipeline, "itens" na malha) — o painel não inventa palavra.
import { ArrowLeftRight, ArrowLeftToLine, ArrowRightToLine, Focus, Waypoints, X } from 'lucide-react'
import type { SentidoCadeia } from './layoutGrafo'

interface OpcaoSentido {
  valor: SentidoCadeia
  rotulo: string
  titulo: string
  Icon: React.ComponentType<{ size?: number; strokeWidth?: number }>
}

const OPCOES: OpcaoSentido[] = [
  {
    valor: 'tras',
    rotulo: 'Para trás',
    titulo: 'Dependências para trás — só o que precisa rodar ANTES do item em foco',
    Icon: ArrowLeftToLine,
  },
  {
    valor: 'ambos',
    rotulo: 'Ambos',
    titulo: 'Cadeia inteira — o que vem antes e o que vem depois',
    Icon: ArrowLeftRight,
  },
  {
    valor: 'frente',
    rotulo: 'Para frente',
    titulo: 'Dependências para frente — só o que roda DEPOIS do item em foco',
    Icon: ArrowRightToLine,
  },
]

interface Props {
  /** rótulo do que está em foco (nome do nó ou "origem → destino" da linha) */
  foco: string
  sentido: SentidoCadeia
  onSentido: (s: SentidoCadeia) => void
  isolar: boolean
  onIsolar: () => void
  onLimpar: () => void
  /** ex.: "depende de 3 etapas" — null quando o sentido não acende esse lado */
  textoTras: string | null
  /** ex.: "7 etapas dependem desta" */
  textoFrente: string | null
  /** quantos itens acesos de quantos existem no desenho — o contador honesto */
  acesos: number
  total: number
}

export function PainelRealce({
  foco, sentido, onSentido, isolar, onIsolar, onLimpar,
  textoTras, textoFrente, acesos, total,
}: Props) {
  return (
    <div className="w-64 rounded-lg border border-indigo-200 bg-panel/95 p-2.5 shadow-md backdrop-blur dark:border-indigo-800">
      <div className="flex items-start gap-1.5">
        <Waypoints size={14} className="mt-px shrink-0 text-indigo-600 dark:text-indigo-400" />
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-indigo-600 dark:text-indigo-400">
            Cadeia de dependências
          </p>
          <p className="truncate font-mono text-[11px] font-semibold leading-tight text-ink" title={foco}>
            {foco}
          </p>
        </div>
        <button
          type="button"
          onClick={onLimpar}
          title="Limpar o realce (Esc, ou clique no fundo do canvas)"
          className="shrink-0 rounded p-0.5 text-dim transition-colors hover:bg-edge/60 hover:text-ink"
        >
          <X size={13} />
        </button>
      </div>

      {/* Contador honesto — só o lado que está ACESO aparece. */}
      <div className="mt-2 space-y-0.5 border-t border-edge pt-2">
        {textoTras && <p className="text-[11px] leading-tight text-ink">{textoTras}</p>}
        {textoFrente && <p className="text-[11px] leading-tight text-ink">{textoFrente}</p>}
        <p className="text-[10px] leading-tight text-dim">
          {acesos} de {total} no desenho {isolar ? '· o resto está escondido' : '· o resto está esmaecido'}
        </p>
      </div>

      {/* Sentido do realce */}
      <div className="mt-2 flex rounded-md border border-edge p-0.5">
        {OPCOES.map((o) => {
          const ativo = sentido === o.valor
          return (
            <button
              key={o.valor}
              type="button"
              onClick={() => onSentido(o.valor)}
              title={o.titulo}
              aria-pressed={ativo}
              className={[
                'flex flex-1 items-center justify-center gap-1 rounded px-1 py-1 text-[10px] font-semibold transition-colors',
                ativo
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-dim hover:bg-edge/60 hover:text-ink',
              ].join(' ')}
            >
              <o.Icon size={12} strokeWidth={2.2} />
              {o.rotulo}
            </button>
          )
        })}
      </div>

      {/* Isolar — decisão 4 do §7: esconder o resto é SOB DEMANDA, nunca
          automático, e o caminho de volta é o mesmo botão. */}
      <button
        type="button"
        onClick={onIsolar}
        aria-pressed={isolar}
        title={isolar
          ? 'Mostrar de volta o desenho inteiro (o resto volta esmaecido)'
          : 'Esconder o que não pertence a esta cadeia — útil em desenho grande'}
        className={[
          'mt-1.5 flex w-full items-center justify-center gap-1.5 rounded-md border px-2 py-1 text-[11px] font-semibold transition-colors',
          isolar
            ? 'border-indigo-600 bg-indigo-600 text-white'
            : 'border-edge text-dim hover:bg-edge/60 hover:text-ink',
        ].join(' ')}
      >
        <Focus size={12} strokeWidth={2.2} />
        {isolar ? 'Mostrar o desenho inteiro' : 'Isolar a cadeia'}
      </button>
    </div>
  )
}
