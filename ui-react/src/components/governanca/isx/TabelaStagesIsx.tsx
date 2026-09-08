// Tabela-resumo dos stages: nome, tipo, direção, banco/arquivo, colunas. Clicar
// numa linha abre o painel do stage (mesmo gesto do nó no grafo).
import { COR_DIRECAO, direcaoDe, idDoStage, resumoStage, type StageIsx } from '../../../lib/lineageIsx'

interface Props {
  stages: StageIsx[]
  selecionado: string | null
  onSelecionar: (stage: string) => void
}

export function TabelaStagesIsx({ stages, selecionado, onSelecionar }: Props) {
  return (
    <div className="border border-edge rounded-lg overflow-x-auto bg-panel" data-tabela-stages>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-dim border-b border-edge">
            <th className="px-3 py-2 font-medium">Stage</th>
            <th className="px-3 py-2 font-medium">Tipo</th>
            <th className="px-3 py-2 font-medium">Direção</th>
            <th className="px-3 py-2 font-medium">Banco / arquivo</th>
            <th className="px-3 py-2 font-medium text-right">Colunas</th>
          </tr>
        </thead>
        <tbody>
          {stages.map(s => {
            const id = idDoStage(s)
            const dir = direcaoDe(s.direction)
            const cor = COR_DIRECAO[dir]
            const ativo = id === selecionado
            return (
              <tr key={id} data-stage={id} data-selecionado={ativo ? '1' : undefined}
                onClick={() => onSelecionar(id)}
                className={`border-b border-edge/50 cursor-pointer hover:bg-canvas ${ativo ? 'bg-canvas' : ''}`}>
                <td className="px-3 py-1.5 font-mono text-ink">{id}</td>
                <td className="px-3 py-1.5 text-ink">{s.object_type ?? s.stage_type_raw ?? '—'}
                  {s.stage_type_raw && s.object_type && s.stage_type_raw !== s.object_type && (
                    <span className="ml-1 text-[10px] text-dim">({s.stage_type_raw})</span>)}
                </td>
                <td className="px-3 py-1.5">
                  <span className={`inline-flex items-center px-1.5 py-0.5 rounded border text-[10px] font-medium ${cor.borda} ${cor.fundo} ${cor.texto}`}>{cor.rotulo}</span>
                </td>
                <td className="px-3 py-1.5 font-mono text-ink break-all">{resumoStage(s)}</td>
                <td className="px-3 py-1.5 text-right text-ink">
                  {s.output_columns.length > 0 ? `${s.output_columns.length} saída` : ''}
                  {s.output_columns.length > 0 && s.input_columns.length > 0 ? ' · ' : ''}
                  {s.input_columns.length > 0 ? `${s.input_columns.length} entrada` : ''}
                  {s.output_columns.length === 0 && s.input_columns.length === 0 ? '—' : ''}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
