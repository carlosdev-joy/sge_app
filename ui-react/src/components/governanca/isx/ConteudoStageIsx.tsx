// Conteúdo do painel de um stage: SQL completo, banco, arquivo com badges de
// parâmetro, colunas de saída/entrada, expressões `saída ← expressão (origem)` e o
// APT code colapsado. Apresentação pura (sem o overlay) — é o que a bancada
// tests/js/lineage_isx_harness.cjs renderiza; o Sheet fica em PainelStageIsx.
import { useState } from 'react'
import { TextoComParametros } from './TextoComParametros'
import { COR_DIRECAO, direcaoDe, idDoStage, type ColunaIsx, type StageIsx } from '../../../lib/lineageIsx'

function TabelaColunas({ titulo, colunas, marca }: { titulo: string; colunas: ColunaIsx[]; marca: string }) {
  if (colunas.length === 0) return null
  return (
    <div data-colunas={marca}>
      <h4 className="text-xs font-semibold text-dim uppercase tracking-wide mb-1">{titulo} ({colunas.length})</h4>
      <div className="border border-edge rounded-md overflow-x-auto">
        <table className="w-full text-xs">
          <thead><tr className="text-left text-dim border-b border-edge">
            <th className="px-2 py-1 font-medium">Coluna</th><th className="px-2 py-1 font-medium">Tipo</th><th className="px-2 py-1 font-medium text-right">Tamanho</th>
          </tr></thead>
          <tbody>
            {colunas.map((c, i) => (
              <tr key={`${c.name}-${i}`} className="border-b border-edge/50">
                <td className="px-2 py-1 font-mono text-ink">{c.name}</td>
                <td className="px-2 py-1 text-ink">{c.type ?? '—'}</td>
                <td className="px-2 py-1 text-right text-ink">{c.length ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function ConteudoStageIsx({ stage }: { stage: StageIsx }) {
  const [aptAberto, setAptAberto] = useState(false)
  const dir = direcaoDe(stage.direction)
  const cor = COR_DIRECAO[dir]
  const id = idDoStage(stage)
  return (
    <div className="flex flex-col gap-4" data-conteudo-stage={id}>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className={`inline-flex items-center px-2 py-0.5 rounded border font-medium ${cor.borda} ${cor.fundo} ${cor.texto}`}>{cor.rotulo}</span>
        <span className="text-ink">{stage.object_type ?? '—'}</span>
        {stage.stage_type_raw && <span className="font-mono text-dim">{stage.stage_type_raw}</span>}
        {stage.stage_internal_id && <span className="font-mono text-dim">{stage.stage_internal_id}</span>}
      </div>

      {(stage.database_name || (stage.object_name !== id && stage.object_name !== stage.file_path)) && (
        <dl className="text-xs grid grid-cols-[7rem_1fr] gap-y-1">
          {stage.database_name && (<><dt className="text-dim">Banco / DSN</dt><dd data-banco><TextoComParametros texto={stage.database_name} /></dd></>)}
          {/* objeto = tabela-alvo; quando é o próprio arquivo, a linha "Arquivo" abaixo já o mostra */}
          {stage.object_name !== id && stage.object_name !== stage.file_path && (
            <><dt className="text-dim">Objeto</dt><dd data-objeto><TextoComParametros texto={stage.object_name} /></dd></>)}
        </dl>
      )}

      {stage.file_path && (
        <div className="text-xs">
          <div className="text-dim mb-1">Arquivo</div>
          <div data-arquivo><TextoComParametros texto={stage.file_path} /></div>
        </div>
      )}

      {stage.sql_expression && (
        <div>
          <h4 className="text-xs font-semibold text-dim uppercase tracking-wide mb-1">SQL</h4>
          {/* Superfície sempre escura (exceção documentada em docs/ui-temas-cores.md §4). */}
          <pre data-sql className="bg-gray-950 text-gray-200 rounded-lg p-3 overflow-auto max-h-[50vh] font-mono text-xs leading-relaxed whitespace-pre">{stage.sql_expression}</pre>
        </div>
      )}

      <TabelaColunas titulo="Colunas de saída" colunas={stage.output_columns} marca="saida" />
      <TabelaColunas titulo="Colunas de entrada" colunas={stage.input_columns} marca="entrada" />

      {stage.expressions.length > 0 && (
        <div data-expressoes>
          <h4 className="text-xs font-semibold text-dim uppercase tracking-wide mb-1">Expressões ({stage.expressions.length})</h4>
          <div className="border border-edge rounded-md overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="text-left text-dim border-b border-edge">
                <th className="px-2 py-1 font-medium">Saída</th><th className="px-2 py-1 font-medium">Expressão</th><th className="px-2 py-1 font-medium">Origem</th>
              </tr></thead>
              <tbody>
                {stage.expressions.map((e, i) => (
                  <tr key={`${e.output_col}-${i}`} className="border-b border-edge/50 align-top" data-expressao={e.output_col}>
                    <td className="px-2 py-1 font-mono text-ink whitespace-nowrap">{e.output_col}</td>
                    <td className="px-2 py-1 font-mono text-ink break-all">{e.expression}</td>
                    <td className="px-2 py-1 font-mono text-dim break-all">{e.source_col || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {stage.apt_code && (
        <div data-apt>
          <button type="button" onClick={() => setAptAberto(v => !v)} data-acao="apt"
            className="text-xs text-dim hover:text-ink underline-offset-2 hover:underline">
            {aptAberto ? 'Ocultar APT code (lógica compilada)' : 'Ver APT code (lógica compilada do Transformer)'}
          </button>
          {aptAberto && (
            <pre data-apt-code className="mt-1 bg-gray-950 text-gray-200 rounded-lg p-3 overflow-auto max-h-[40vh] font-mono text-[11px] leading-relaxed whitespace-pre">{stage.apt_code}</pre>
          )}
        </div>
      )}
    </div>
  )
}
