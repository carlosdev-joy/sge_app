// Admin › Utilitários › Diretórios-raiz — cadastro e teste das raízes que a
// tela Utilitários pode abrir. Componente de APRESENTAÇÃO: recebe dados e
// callbacks por props (a rede fica no UtilitariosTab), o que é o que permite a
// bancada de node renderizar e clicar nele sem react-query.
//
// Raiz se DESATIVA, não se apaga (a auditoria referencia caminhos abaixo dela) —
// por isso não há botão Excluir aqui, e as inativas ficam visíveis, esmaecidas.
import { useState, type FormEvent } from 'react'
import { Zap, RefreshCw, Power, PowerOff, Plus, FolderTree, AlertTriangle } from 'lucide-react'
import { Button } from '../ui/Button'
import { Input, Select } from '../ui/Input'
import { Badge } from '../ui/Badge'
import { avisoRaiz, tomDoTeste, type RaizUtil, type ServidorUtil, type TesteRaiz } from '../../lib/utilitariosAdmin'

export interface UtilitariosRaizesProps {
  servidores: ServidorUtil[]
  raizes: RaizUtil[]
  /** Resultado do último Testar de cada raiz (por id). */
  testes: Record<number, TesteRaiz | undefined>
  testandoId: number | null
  incluindo: boolean
  /** Devolve true quando o servidor aceitou — só então o campo é limpo (um 409
   *  "já cadastrada" mantém o que o admin digitou). */
  onIncluir: (servidor: string, caminho: string) => Promise<boolean> | boolean
  onTestar: (id: number) => void
  onAtivar: (id: number, ativo: boolean) => void
}

const TOM_TESTE = {
  success: 'text-emerald-700 dark:text-emerald-300',
  warning: 'text-amber-700 dark:text-amber-300',
  error: 'text-red-700 dark:text-red-300',
} as const

export function UtilitariosRaizes({
  servidores, raizes, testes, testandoId, incluindo, onIncluir, onTestar, onAtivar,
}: UtilitariosRaizesProps) {
  const [servidor, setServidor] = useState(servidores[0]?.id ?? 'datastage')
  const [caminho, setCaminho] = useState('')
  const aviso = avisoRaiz(caminho)
  const podeIncluir = caminho.trim().length > 0 && aviso === null && !incluindo

  const incluir = async (e: FormEvent) => {
    e.preventDefault()
    if (!podeIncluir) return
    const ok = await onIncluir(servidor, caminho.trim())
    if (ok) setCaminho('')
  }

  const servidorAtual = servidores.find(s => s.id === servidor)

  return (
    <section className="bg-panel border border-edge rounded-lg shadow-sm" data-secao="raizes">
      <header className="flex items-center gap-2 px-4 py-3 border-b border-edge">
        <FolderTree size={16} className="text-[#1A5FA8] dark:text-blue-400 shrink-0" />
        <h3 className="text-sm font-semibold text-ink">Diretórios-raiz</h3>
        <span className="text-xs text-dim">— tudo abaixo de uma raiz ativa pode ser aberto; fora dela, nada.</span>
      </header>

      <form onSubmit={incluir} className="grid grid-cols-1 md:grid-cols-[180px_1fr_auto] gap-3 items-start px-4 py-3 border-b border-edge/60"
        data-form="incluir-raiz">
        <Select label="Servidor" value={servidor} onChange={e => setServidor(e.target.value)}
          ajuda={servidorAtual && !servidorAtual.configurado ? 'SSH não configurado nesta instância da API' : undefined}>
          {servidores.map(s => (
            <option key={s.id} value={s.id}>{s.label}{s.configurado ? '' : ' (não configurado)'}</option>
          ))}
        </Select>
        <Input label="Pasta raiz" value={caminho} onChange={e => setCaminho(e.target.value)}
          placeholder="/opt/IBM/InformationServer/Server/Projects" autoComplete="off" spellCheck={false}
          error={aviso ?? undefined}
          ajuda="Caminho absoluto no servidor. Barras repetidas e `..` são normalizados." />
        <div className="md:pt-5">
          <Button type="submit" size="sm" disabled={!podeIncluir} loading={incluindo} data-acao="incluir-raiz">
            <Plus size={13} /> Incluir
          </Button>
        </div>
      </form>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-dim border-b border-edge bg-canvas/50">
              <th className="px-4 py-2.5 text-left font-semibold">Servidor</th>
              <th className="px-4 py-2.5 text-left font-semibold">Caminho</th>
              <th className="px-4 py-2.5 text-left font-semibold">Estado</th>
              <th className="px-4 py-2.5 text-left font-semibold">Cadastro</th>
              <th className="px-4 py-2.5 w-24"></th>
            </tr>
          </thead>
          <tbody>
            {raizes.map(r => {
              const teste = testes[r.id]
              const resumo = teste ? tomDoTeste(teste) : null
              const testando = testandoId === r.id
              return (
                <RaizLinhas key={r.id} raiz={r} resumo={resumo} teste={teste} testando={testando}
                  bloqueado={testandoId !== null}
                  servidorLabel={servidores.find(s => s.id === r.servidor)?.label ?? r.servidor}
                  onTestar={onTestar} onAtivar={onAtivar} />
              )
            })}
            {raizes.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-xs text-dim" data-vazio="raizes">
                  Nenhuma raiz cadastrada — até cadastrar uma, a tela Utilitários não abre arquivo nenhum.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function RaizLinhas({ raiz, resumo, teste, testando, bloqueado, servidorLabel, onTestar, onAtivar }: {
  raiz: RaizUtil
  resumo: { tom: 'success' | 'warning' | 'error'; texto: string } | null
  teste: TesteRaiz | undefined
  testando: boolean
  bloqueado: boolean
  servidorLabel: string
  onTestar: (id: number) => void
  onAtivar: (id: number, ativo: boolean) => void
}) {
  const inativa = !raiz.ativo
  return (
    <>
      <tr className={`border-b border-edge/50 hover:bg-canvas/50 transition-colors ${inativa ? 'opacity-60' : ''}`}
        data-raiz={raiz.id} data-inativa={inativa ? '1' : undefined}>
        <td className="px-4 py-2 text-xs text-ink">{servidorLabel}</td>
        <td className="px-4 py-2"><span className="font-mono text-xs text-[#1A5FA8] dark:text-blue-400 break-all">{raiz.caminho}</span></td>
        <td className="px-4 py-2"><Badge value={inativa ? 'inativo' : 'ativo'}>{inativa ? 'inativa' : 'ativa'}</Badge></td>
        <td className="px-4 py-2 text-xs text-dim">{raiz.criado_por || '—'}{raiz.criado_em ? ` · ${raiz.criado_em}` : ''}</td>
        <td className="px-4 py-2">
          <div className="flex items-center gap-1 justify-end">
            <button type="button" onClick={() => onTestar(raiz.id)} disabled={bloqueado}
              className="text-slate-400 hover:text-emerald-600 dark:hover:text-emerald-400 p-1 rounded disabled:opacity-40"
              title="Testar no servidor: a pasta existe e o usuário SSH consegue listá-la?" data-acao="testar">
              {testando ? <RefreshCw size={13} className="animate-spin" /> : <Zap size={13} />}
            </button>
            {inativa ? (
              <button type="button" onClick={() => onAtivar(raiz.id, true)}
                className="text-slate-400 hover:text-emerald-600 dark:hover:text-emerald-400 p-1 rounded"
                title="Reativar: volta a liberar tudo abaixo desta pasta" data-acao="reativar">
                <Power size={13} />
              </button>
            ) : (
              <button type="button" onClick={() => onAtivar(raiz.id, false)}
                className="text-slate-400 hover:text-red-500 dark:hover:text-red-400 p-1 rounded"
                title="Desativar: nada abaixo desta pasta pode mais ser aberto (o histórico fica)" data-acao="desativar">
                <PowerOff size={13} />
              </button>
            )}
          </div>
        </td>
      </tr>
      {resumo && teste && (
        <tr className="border-b border-edge/50 bg-canvas/30" data-teste={raiz.id} data-tom={resumo.tom}>
          <td colSpan={5} className={`px-4 py-1.5 text-xs ${TOM_TESTE[resumo.tom]}`}>
            <span className="inline-flex items-center gap-1.5">
              {resumo.tom !== 'success' && <AlertTriangle size={12} className="shrink-0" />}
              <span>Teste: {resumo.texto}</span>
              {teste.caminho_real && teste.caminho_real !== raiz.caminho && (
                <span className="text-dim">· caminho real <span className="font-mono">{teste.caminho_real}</span></span>
              )}
              {typeof teste.duracao_ms === 'number' && <span className="text-dim">· {teste.duracao_ms} ms</span>}
            </span>
          </td>
        </tr>
      )}
    </>
  )
}
