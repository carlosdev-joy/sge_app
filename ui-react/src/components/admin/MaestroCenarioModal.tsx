// Admin › Maestro — o modal de um cenário do catálogo (novo ou edição):
// código/título/descrição, a RECEITA (uma linha por parâmetro, com marcadores
// `<NOME>` no lugar do nome real), os exemplos de pedido e o "Simular", que
// pede ao servidor a régua + a prévia com os marcadores no nome.
//
// Não reusa o JobParamsEditor da etapa de propósito: aquele valida o nome pela
// régua do DataStage (recusaria `<DATA_INICIAL>`) e pede a prévia por nome —
// aqui as linhas são poucas e a validação passa pelos marcadores.
import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { Button } from '../ui/Button'
import { Input, Textarea } from '../ui/Input'
import { Modal } from '../ui/Modal'
import { Switch } from '../ui/Switch'
import { apiFetch } from '../../lib/api'
import {
  DS_FORMATOS_SUGERIDOS, DS_PARAM_ANCORAS, DS_PARAM_SOURCES, DS_PARAM_TYPES, ehOrigemData, hojeLocalISO, type JobParam,
} from '../../lib/dsParams'
import {
  cenarioParaApi, cenarioVazio, errosDoCenario, formDoCenario, linhaVazia, mensagemErroAdmin,
  type CenarioApi, type CenarioForm, type PreviaCenario,
} from '../../lib/maestroAdmin'

export interface MaestroCenarioModalProps {
  /** `null` fechado; `'novo'` cria; um cenário edita. */
  aberto: CenarioApi | 'novo' | null
  salvando: boolean
  onFechar: () => void
  onSalvar: (corpo: ReturnType<typeof cenarioParaApi>, id: number | null) => void
}

const campo = 'bg-panel border border-edge text-ink rounded-md px-2 py-1 text-xs placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500 min-w-0 w-full'

export function MaestroCenarioModal({ aberto, salvando, onFechar, onSalvar }: MaestroCenarioModalProps) {
  // `key` no consumidor remonta o modal a cada abertura: o estado nasce do
  // cenário certo sem efeito de sincronização.
  const [form, setForm] = useState<CenarioForm>(() => (aberto && aberto !== 'novo' ? formDoCenario(aberto) : cenarioVazio()))
  const [referencia, setReferencia] = useState(() => hojeLocalISO())
  const [simulacao, setSimulacao] = useState<{ previa: PreviaCenario[]; erros: string[]; referencia: string } | null>(null)
  const [simulando, setSimulando] = useState(false)

  const erros = errosDoCenario(form)
  const id = aberto && aberto !== 'novo' ? aberto.id : null

  function mudarLinha(i: number, patch: Partial<JobParam>) {
    setSimulacao(null)
    setForm(f => ({ ...f, linhas: f.linhas.map((l, k) => (k === i ? { ...l, ...patch } : l)) }))
  }

  async function simular() {
    setSimulando(true)
    try {
      // Só a receita vai: o admin simula antes de ter código/título prontos.
      const r = await apiFetch<{ previa: PreviaCenario[]; erros: string[]; referencia: string }>(
        '/maestro/admin/cenarios/validar', { method: 'POST', body: JSON.stringify({ receita: cenarioParaApi(form).receita, referencia }) })
      setSimulacao(r)
    } catch (e: unknown) {
      setSimulacao({ previa: [], erros: [mensagemErroAdmin(e, 'Não foi possível simular')], referencia })
    } finally {
      setSimulando(false)
    }
  }

  return (
    <Modal open={aberto !== null} onClose={onFechar} title={id === null ? 'Novo cenário' : `Cenário ${form.codigo || ''}`} size="xl">
      <div className="flex flex-col gap-4" data-maestro-cenario-modal>
        <div className="grid gap-3 md:grid-cols-[14rem_1fr]">
          <Input label="Código" value={form.codigo} onChange={e => setForm({ ...form, codigo: e.target.value })}
                 placeholder="ex.: mensal_anterior" ajuda="Identificador do cenário: minúsculas, números e _ (o Maestro cita no rastro da conversa)." />
          <Input label="Título" value={form.titulo} onChange={e => setForm({ ...form, titulo: e.target.value })}
                 placeholder="ex.: Carga mensal do mês anterior" />
        </div>
        <Textarea label="Descrição (o que o Maestro lê para reconhecer o cenário)" value={form.descricao} rows={2}
                  onChange={e => setForm({ ...form, descricao: e.target.value })}
                  placeholder="Quando usar, o que os parâmetros representam, particularidades (ex.: vale em qualquer dia do mês)." />

        <div className="flex flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-dim">Receita — um parâmetro por linha; nomes entre &lt; &gt; são marcadores que o Maestro troca pelo nome real do job</span>
            <Button size="sm" variant="ghost" className="ml-auto" onClick={() => { setSimulacao(null); setForm(f => ({ ...f, linhas: [...f.linhas, linhaVazia()] })) }} data-maestro-receita-add>
              <Plus size={13} /> Parâmetro
            </Button>
          </div>
          <div className="overflow-x-auto rounded-lg border border-edge">
            <table className="w-full text-xs">
              <thead className="bg-canvas/60 text-dim">
                <tr>
                  <th className="px-2 py-1.5 text-left font-medium">Marcador / nome</th>
                  <th className="px-2 py-1.5 text-left font-medium">Tipo</th>
                  <th className="px-2 py-1.5 text-left font-medium">Origem</th>
                  <th className="px-2 py-1.5 text-left font-medium">Meses</th>
                  <th className="px-2 py-1.5 text-left font-medium">Âncora</th>
                  <th className="px-2 py-1.5 text-left font-medium">Dias</th>
                  <th className="px-2 py-1.5 text-left font-medium">Formato / valor</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody>
                {form.linhas.map((l, i) => {
                  const data = ehOrigemData(l.param_source)
                  return (
                    <tr key={l.id} className="border-t border-edge/60" data-maestro-receita-linha={l.param_name}>
                      <td className="px-2 py-1"><input className={`${campo} font-mono`} value={l.param_name} placeholder="<DATA_INICIAL>" onChange={e => mudarLinha(i, { param_name: e.target.value })} /></td>
                      <td className="px-2 py-1">
                        <select className={campo} value={l.param_type} onChange={e => mudarLinha(i, { param_type: e.target.value })}>
                          {DS_PARAM_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                        </select>
                      </td>
                      <td className="px-2 py-1">
                        <select className={campo} value={l.param_source ?? 'fixo'} onChange={e => mudarLinha(i, { param_source: e.target.value })}>
                          {DS_PARAM_SOURCES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                        </select>
                      </td>
                      <td className="px-2 py-1"><input className={`${campo} w-16`} value={l.param_offset_meses ?? ''} disabled={!data} placeholder="0" onChange={e => mudarLinha(i, { param_offset_meses: e.target.value })} /></td>
                      <td className="px-2 py-1">
                        <select className={campo} value={l.param_ancora ?? ''} disabled={!data} onChange={e => mudarLinha(i, { param_ancora: e.target.value })}>
                          {DS_PARAM_ANCORAS.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
                        </select>
                      </td>
                      <td className="px-2 py-1"><input className={`${campo} w-16`} value={l.param_offset_dias ?? ''} disabled={!data} placeholder="0" onChange={e => mudarLinha(i, { param_offset_dias: e.target.value })} /></td>
                      <td className="px-2 py-1">
                        {data ? (
                          <input className={`${campo} font-mono`} list="maestro-formatos" value={l.param_formato ?? ''} placeholder="%Y-%m-%d" onChange={e => mudarLinha(i, { param_formato: e.target.value })} />
                        ) : (l.param_source === 'run_id' || l.param_type === 'Encrypted') ? (
                          <span className="text-dim">{l.param_type === 'Encrypted' ? 'sem valor (o usuário digita)' : 'run_id em runtime'}</span>
                        ) : (
                          <input className={`${campo} font-mono`} value={l.param_value} placeholder="valor fixo" onChange={e => mudarLinha(i, { param_value: e.target.value })} />
                        )}
                      </td>
                      <td className="px-1 py-1">
                        <button type="button" title="Remover" aria-label="Remover parâmetro" className="rounded p-1 text-dim hover:text-red-600"
                                onClick={() => { setSimulacao(null); setForm(f => ({ ...f, linhas: f.linhas.filter((_, k) => k !== i) })) }}>
                          <Trash2 size={13} />
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <datalist id="maestro-formatos">{DS_FORMATOS_SUGERIDOS.map(f => <option key={f} value={f} />)}</datalist>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-1 text-[11px] text-dim">
              Simular com a referência
              <input type="date" value={referencia} onChange={e => { setSimulacao(null); setReferencia(e.target.value) }}
                     className="rounded-md border border-edge bg-panel px-2 py-0.5 text-xs text-ink focus:outline-none focus:ring-1 focus:ring-blue-500" />
            </label>
            <Button size="sm" variant="secondary" onClick={() => { void simular() }} disabled={simulando || !form.linhas.length} data-maestro-simular>
              {simulando ? 'Simulando…' : 'Simular'}
            </Button>
          </div>
          {simulacao && (
            <div className="rounded-md border border-edge bg-canvas/40 px-2.5 py-1.5 text-xs" data-maestro-simulacao>
              {simulacao.erros.length > 0 ? (
                <ul className="flex flex-col gap-0.5 text-red-700 dark:text-red-300">{simulacao.erros.map(e => <li key={e}>{e}</li>)}</ul>
              ) : (
                <ul className="flex flex-col gap-0.5">
                  {simulacao.previa.map(p => (
                    <li key={p.param_name} title={p.descricao}>
                      <span className="font-mono text-ink">{p.param_name}</span> com a referência {simulacao.referencia}: <span className="font-mono text-ink">{p.valor}</span>
                      <span className="text-dim"> · {p.descricao}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        <Textarea label="Exemplos de pedido (uma frase por linha; o 1º exemplo dos 4 primeiros cenários ativos vira sugestão de abertura do chat)" value={form.exemplosTexto} rows={3}
                  onChange={e => setForm({ ...form, exemplosTexto: e.target.value })}
                  placeholder={'carga mensal do mês anterior com data inicial e final\nprocessar o mês passado inteiro'} />

        <div className="flex flex-wrap items-center gap-3">
          <Switch label="Cenário ativo (o Maestro o oferece)" checked={form.ativo} onChange={e => setForm({ ...form, ativo: e.target.checked })} />
        </div>

        {erros.length > 0 && (
          <ul className="flex flex-col gap-0.5 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-[11px] text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300" data-maestro-cenario-erros>
            {erros.map(e => <li key={e}>{e}</li>)}
          </ul>
        )}

        <div className="flex justify-end gap-2 border-t border-edge pt-3">
          <Button variant="secondary" onClick={onFechar} disabled={salvando}>Cancelar</Button>
          <Button variant="primary" onClick={() => onSalvar(cenarioParaApi(form), id)} disabled={salvando || erros.length > 0} data-maestro-cenario-salvar>
            {salvando ? 'Salvando…' : 'Salvar cenário'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
