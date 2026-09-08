// Texto de DSN/path com os `#PSet.X#` como badges (spec §8.3 do documento de
// origem): o valor real só existe em runtime, então não se tenta resolver — só se
// mostra que é um parâmetro, com a explicação no title.
import { partesParametro } from '../../../lib/lineageIsx'

const EXPLICACAO = 'Parâmetro do DataStage (Parameter Set): o valor é resolvido em runtime e não está no design do job.'

export function TextoComParametros({ texto, mono = true }: { texto: string | null | undefined; mono?: boolean }) {
  if (!texto) return <span className="text-dim">—</span>
  return (
    <span className={`${mono ? 'font-mono' : ''} break-all`} data-texto-parametros>
      {partesParametro(texto).map((p, i) => p.tipo === 'parametro' ? (
        <span key={i} title={EXPLICACAO} data-parametro={p.valor}
          className="inline-flex items-center mx-0.5 px-1.5 py-0.5 rounded border text-[10px] font-medium align-middle bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-900/40 dark:text-blue-300 dark:border-blue-800">
          {p.valor}
        </span>
      ) : <span key={i}>{p.valor}</span>)}
    </span>
  )
}
