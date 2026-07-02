// Wizard de cadastro/edição de uma Cópia de Dados (5 passos, Modal 2xl),
// no estilo do PipelineFormModal: stepper clicável, validação por passo,
// confirmação ao sair com dados preenchidos.
//
// Passos: 1 Origem · 2 Destino · 3 Colunas & Transformações · 4 Performance
// · 5 Revisão. Introspecção via GET /copias/introspect/* (com hint quando a
// consulta cai para o caminho lento via Airflow).
import { useState, useEffect, useRef, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { useAuthStore } from '../../store/auth'
import { Button } from '../ui/Button'
import { Input, Select } from '../ui/Input'
import { Modal } from '../ui/Modal'
import { Spinner } from '../ui/Spinner'
import { toast } from '../ui/Toast'
import { AlertTriangle, Eye, Play, Plus, Save, Search, X } from 'lucide-react'
import {
  type CasoPad, type ColunaInfo, type ColunaMapeada, type Conexao,
  type ColumnsResp, type CopiaDetalhe, type DatabasesResp, type PreviewResp,
  type TablesResp, type Transform, type TransformTipo,
  CAST_TIPOS_SUGERIDOS, PARTICAO_TIPOS, TRANSFORM_OPTIONS,
  fmtRows, novoTransform, transformResumo,
} from './transformUtils'

// ── Tipos locais do formulário ────────────────────────────────────────────────

interface FormState {
  nome: string
  src_conn_id: string
  src_database: string
  src_schema: string
  src_table: string
  src_filtro: string
  dst_conn_id: string
  dst_database: string
  dst_schema: string
  dst_table: string
  criar_tabela: boolean
  truncar_antes: boolean
  particao_coluna: string
  streams: number
  batch_size: number
}

// Linha do passo Colunas: mapeamento origem→destino + transformação + incluir.
interface LinhaColuna {
  origem: string
  tipo: string          // tipo SQL da coluna de origem (exibição)
  destino: string
  incluir: boolean
  transform: Transform | null
}

const defaultForm = (): FormState => ({
  nome: '',
  src_conn_id: '', src_database: '', src_schema: 'dbo', src_table: '', src_filtro: '',
  dst_conn_id: '', dst_database: '', dst_schema: 'dbo', dst_table: '',
  criar_tabela: false, truncar_antes: false,
  particao_coluna: '', streams: 4, batch_size: 50000,
})

function copiaToForm(c: CopiaDetalhe): FormState {
  return {
    nome: c.nome,
    src_conn_id: c.src_conn_id, src_database: c.src_database,
    src_schema: c.src_schema || 'dbo', src_table: c.src_table,
    src_filtro: c.src_filtro ?? '',
    dst_conn_id: c.dst_conn_id, dst_database: c.dst_database,
    dst_schema: c.dst_schema || 'dbo', dst_table: c.dst_table,
    criar_tabela: c.criar_tabela, truncar_antes: c.truncar_antes,
    particao_coluna: c.particao_coluna ?? '',
    streams: c.streams || 4, batch_size: c.batch_size || 50000,
  }
}

const BATCH_OPTS = [10000, 25000, 50000, 100000]

// ── Stepper (5 passos, mesmo padrão do PipelineFormModal) ─────────────────────

const STEPS = ['Origem', 'Destino', 'Colunas', 'Performance', 'Revisão'] as const
type Step = 0 | 1 | 2 | 3 | 4

function Stepper({ step, setStep, errors }: {
  step: Step; setStep: (s: Step) => void; errors: Record<number, string[]>
}) {
  return (
    <div className="flex items-center gap-0 mb-1">
      {STEPS.map((label, i) => {
        const hasErr = (errors[i]?.length ?? 0) > 0
        const active = i === step
        const done   = i < step && !hasErr
        return (
          <button key={i} type="button" onClick={() => setStep(i as Step)}
            className="flex items-center gap-0 group">
            <div className="flex flex-col items-center">
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold border transition-colors
                ${hasErr ? 'bg-red-500 border-red-500 text-white' :
                  active ? 'bg-blue-600 border-blue-600 text-white' :
                  done   ? 'bg-green-600 border-green-600 text-white' :
                           'bg-panel border-edge text-dim'}`}>
                {hasErr ? '!' : done ? '✓' : i + 1}
              </div>
              <span className={`text-[9px] mt-0.5 whitespace-nowrap transition-colors
                ${hasErr ? 'text-red-500 font-semibold' : active ? 'text-blue-600 dark:text-blue-300 font-semibold' : done ? 'text-green-600 dark:text-green-400' : 'text-dim'}`}>
                {label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div className={`w-6 h-0.5 mt-[-10px] mx-0.5 transition-colors
                ${i < step ? 'bg-green-500' : 'bg-edge'}`} />
            )}
          </button>
        )
      })}
    </div>
  )
}

// ── Estado de loading/erro da introspecção ────────────────────────────────────

function IntrospectStatus({ carregando, erro, rotulo, viaAirflow }: {
  carregando: boolean; erro?: string | null; rotulo: string; viaAirflow: boolean
}) {
  if (carregando) {
    return (
      <div className="flex items-center gap-2 text-xs text-dim py-1.5">
        <Spinner size={14} />
        <span>Carregando {rotulo}…</span>
        {viaAirflow && (
          <span className="text-amber-700 dark:text-amber-400">
            consultando via Airflow (pode levar ~30s)
          </span>
        )}
      </div>
    )
  }
  if (erro) {
    return (
      <p className="text-xs text-red-700 dark:text-red-400 py-1.5">
        Falha ao carregar {rotulo}: {erro}
      </p>
    )
  }
  return null
}

// Hint pós-resposta: avisa que o servidor só respondeu pelo caminho lento.
function ViaAirflowHint({ via }: { via?: string }) {
  if (via !== 'airflow') return null
  return (
    <p className="text-[11px] text-amber-700 dark:text-amber-400">
      ⓘ Consulta feita via Airflow (caminho lento) — as próximas consultas
      deste servidor podem levar ~30s.
    </p>
  )
}

// ── Seletor de tabela (busca + lista com nº de linhas pt-BR) ──────────────────

function TabelaPicker({ tabelas, schema, table, onSelect }: {
  tabelas: { schema: string; name: string; rows: number }[]
  schema: string
  table: string
  onSelect: (schema: string, name: string) => void
}) {
  const [busca, setBusca] = useState('')
  const filtradas = useMemo(() => {
    const q = busca.trim().toLowerCase()
    if (!q) return tabelas
    return tabelas.filter(t => `${t.schema}.${t.name}`.toLowerCase().includes(q))
  }, [tabelas, busca])

  return (
    <div className="flex flex-col gap-2">
      <div className="relative">
        <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-dim" />
        <input value={busca} onChange={e => setBusca(e.target.value)}
          placeholder="Buscar tabela…"
          className="w-full bg-panel border border-edge text-ink rounded-md pl-8 pr-3 py-1.5 text-sm placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500" />
      </div>
      <div className="border border-edge rounded-lg overflow-hidden">
        <div className="max-h-56 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-canvas">
              <tr className="text-xs text-dim border-b border-edge">
                <th className="px-3 py-2 text-left font-semibold">Tabela</th>
                <th className="px-3 py-2 text-right font-semibold">Linhas</th>
              </tr>
            </thead>
            <tbody>
              {filtradas.map(t => {
                const sel = t.schema === schema && t.name === table
                return (
                  <tr key={`${t.schema}.${t.name}`}
                    onClick={() => onSelect(t.schema, t.name)}
                    className={`border-b border-edge/50 cursor-pointer transition-colors ${
                      sel ? 'bg-blue-50 dark:bg-blue-900/25' : 'hover:bg-canvas/70'}`}>
                    <td className="px-3 py-1.5">
                      <span className={`font-mono text-xs ${sel ? 'text-blue-700 dark:text-blue-300 font-semibold' : 'text-ink'}`}>
                        {t.schema}.{t.name}
                      </span>
                    </td>
                    <td className="px-3 py-1.5 text-right text-xs text-dim whitespace-nowrap">
                      {fmtRows(t.rows)}
                    </td>
                  </tr>
                )
              })}
              {filtradas.length === 0 && (
                <tr><td colSpan={2} className="px-3 py-6 text-center text-xs text-dim">
                  Nenhuma tabela encontrada.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ── Editor da transformação de uma coluna (campos dinâmicos por tipo) ─────────

function TransformEditor({ transform, colunas, onChange }: {
  transform: Transform
  colunas: ColunaInfo[]
  onChange: (t: Transform) => void
}) {
  const t = transform

  if (t.tipo === 'pad_condicional') {
    const casos = t.casos ?? []
    const setCaso = (i: number, patch: Partial<CasoPad>) =>
      onChange({ ...t, casos: casos.map((c, j) => j === i ? { ...c, ...patch } : c) })
    return (
      <div className="flex flex-col gap-2 bg-canvas border border-edge rounded-lg p-2.5">
        <Select label="Campo da condição" value={t.campo_condicao ?? ''}
          onChange={e => onChange({ ...t, campo_condicao: e.target.value })}>
          <option value="">Selecione…</option>
          {colunas.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
        </Select>
        <div className="flex flex-col gap-1.5">
          <label className="text-xs text-dim font-medium">
            Casos (quando o campo = valor → completa com zeros até o tamanho)
          </label>
          {casos.map((c, i) => (
            <div key={i} className="flex items-center gap-2">
              <input value={c.valor} placeholder={i === 0 ? 'J' : i === 1 ? 'F' : 'valor'}
                onChange={e => setCaso(i, { valor: e.target.value })}
                className="w-20 bg-panel border border-edge text-ink rounded-md px-2 py-1 text-xs font-mono placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500" />
              <span className="text-xs text-dim">→ tamanho</span>
              <input type="number" min={1} max={8000} value={c.tamanho}
                placeholder={i === 0 ? '14' : i === 1 ? '11' : ''}
                onChange={e => setCaso(i, { tamanho: parseInt(e.target.value) || 0 })}
                className="w-20 bg-panel border border-edge text-ink rounded-md px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500" />
              <button type="button" title="Remover caso"
                onClick={() => onChange({ ...t, casos: casos.filter((_, j) => j !== i) })}
                className="text-dim hover:text-red-500 transition-colors">
                <X size={13} />
              </button>
            </div>
          ))}
          <button type="button"
            onClick={() => onChange({ ...t, casos: [...casos, { valor: '', tamanho: 11 }] })}
            className="self-start inline-flex items-center gap-1 text-xs text-blue-700 dark:text-blue-400 hover:underline">
            <Plus size={12} /> Adicionar caso
          </button>
          <p className="text-[10px] text-dim">
            Sugestão: J com 14 (CNPJ) e F com 11 (CPF). Valores fora dos casos ficam inalterados.
          </p>
        </div>
      </div>
    )
  }

  if (t.tipo === 'pad_fixo') {
    return (
      <div className="flex items-center gap-2 bg-canvas border border-edge rounded-lg p-2.5">
        <label className="text-xs text-dim font-medium">Tamanho final</label>
        <input type="number" min={1} max={8000} value={t.tamanho ?? 0}
          onChange={e => onChange({ ...t, tamanho: parseInt(e.target.value) || 0 })}
          className="w-24 bg-panel border border-edge text-ink rounded-md px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500" />
      </div>
    )
  }

  if (t.tipo === 'substring') {
    return (
      <div className="flex items-center gap-2 bg-canvas border border-edge rounded-lg p-2.5">
        <label className="text-xs text-dim font-medium">Início</label>
        <input type="number" min={1} max={8000} value={t.inicio ?? 1}
          onChange={e => onChange({ ...t, inicio: parseInt(e.target.value) || 1 })}
          className="w-20 bg-panel border border-edge text-ink rounded-md px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500" />
        <label className="text-xs text-dim font-medium">Tamanho</label>
        <input type="number" min={1} max={8000} value={t.tamanho ?? 0}
          onChange={e => onChange({ ...t, tamanho: parseInt(e.target.value) || 0 })}
          className="w-20 bg-panel border border-edge text-ink rounded-md px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500" />
      </div>
    )
  }

  if (t.tipo === 'cast') {
    return (
      <div className="flex flex-col gap-1 bg-canvas border border-edge rounded-lg p-2.5">
        <label className="text-xs text-dim font-medium">Tipo SQL de destino</label>
        <input list="copias-cast-tipos" value={t.tipo_sql ?? ''}
          onChange={e => onChange({ ...t, tipo_sql: e.target.value.toUpperCase() })}
          placeholder="ex: DECIMAL(18,2)"
          className="w-48 bg-panel border border-edge text-ink rounded-md px-2 py-1 text-xs font-mono placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500" />
        <datalist id="copias-cast-tipos">
          {CAST_TIPOS_SUGERIDOS.map(tp => <option key={tp} value={tp} />)}
        </datalist>
        <p className="text-[10px] text-dim">
          Aceitos: INT, BIGINT, DECIMAL(p,s), VARCHAR(n), NVARCHAR(n), DATE, DATETIME, FLOAT, BIT.
        </p>
      </div>
    )
  }

  if (t.tipo === 'sql') {
    return (
      <div className="flex flex-col gap-1 bg-canvas border border-edge rounded-lg p-2.5">
        <label className="text-xs text-dim font-medium">Expressão T-SQL (somente leitura)</label>
        <input value={t.expressao ?? ''}
          onChange={e => onChange({ ...t, expressao: e.target.value })}
          placeholder="ex: UPPER(LTRIM(RTRIM([nome])))"
          className="w-full bg-panel border border-edge text-ink rounded-md px-2 py-1 text-xs font-mono placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500" />
        <p className="text-[10px] text-dim">
          Sem ponto e vírgula, comentários ou comandos DML/DDL — validado no servidor.
        </p>
      </div>
    )
  }

  return null // trim / upper / lower — sem parâmetros
}

// ── Wizard ────────────────────────────────────────────────────────────────────

export function CopiaWizard({ copia, onClose, onExecutado }: {
  copia?: CopiaDetalhe               // presente ao editar
  onClose: () => void
  onExecutado: (execId: number) => void  // abre o modal de progresso na página
}) {
  const qc = useQueryClient()
  const user = useAuthStore(s => s.user)
  const isAdmin = useAuthStore(s => s.isAdmin)
  const podeExecutar = isAdmin() || !!user?.permissoes?.includes('acao_executar')
  const isEdit = !!copia

  const [form, setForm] = useState<FormState>(copia ? copiaToForm(copia) : defaultForm())
  const [rows, setRows] = useState<LinhaColuna[]>([])
  const [step, setStep] = useState<Step>(0)
  const [stepErrors, setStepErrors] = useState<Record<number, string[]>>({})
  const [confirmClose, setConfirmClose] = useState(false)
  const [preview, setPreview] = useState<PreviewResp | null>(null)
  // Modo edição resiliente: linhas semeadas de colunas_json porque a
  // introspecção falhou — a lista pode estar desatualizada (aviso no passo 3).
  const [rowsDesatualizadas, setRowsDesatualizadas] = useState(false)
  // Fica true assim que QUALQUER introspecção responder via 'airflow' —
  // passa a avisar nos loadings seguintes que a consulta pode levar ~30s.
  const [viaAirflow, setViaAirflow] = useState(false)

  function f<K extends keyof FormState>(k: K, v: FormState[K]) {
    setForm(prev => ({ ...prev, [k]: v }))
  }

  // ── Introspecção ──────────────────────────────────────────────────────────

  const { data: connData, isLoading: connLoading } = useQuery<{ connections: Conexao[] }>({
    queryKey: ['copias-conexoes'],
    queryFn: () => apiFetch('/copias/conexoes'),
    staleTime: 60_000,
  })
  const conexoes = connData?.connections ?? []

  const srcDbsQ = useQuery<DatabasesResp>({
    queryKey: ['copias-databases', form.src_conn_id],
    queryFn: () => apiFetch(`/copias/introspect/databases?conn_id=${encodeURIComponent(form.src_conn_id)}`),
    enabled: !!form.src_conn_id,
    staleTime: 300_000,
  })
  const dstDbsQ = useQuery<DatabasesResp>({
    queryKey: ['copias-databases', form.dst_conn_id],
    queryFn: () => apiFetch(`/copias/introspect/databases?conn_id=${encodeURIComponent(form.dst_conn_id)}`),
    enabled: !!form.dst_conn_id,
    staleTime: 300_000,
  })
  const srcTablesQ = useQuery<TablesResp>({
    queryKey: ['copias-tables', form.src_conn_id, form.src_database],
    queryFn: () => apiFetch(`/copias/introspect/tables?conn_id=${encodeURIComponent(form.src_conn_id)}&database=${encodeURIComponent(form.src_database)}`),
    enabled: !!form.src_conn_id && !!form.src_database,
    staleTime: 300_000,
  })
  const dstTablesQ = useQuery<TablesResp>({
    queryKey: ['copias-tables', form.dst_conn_id, form.dst_database],
    queryFn: () => apiFetch(`/copias/introspect/tables?conn_id=${encodeURIComponent(form.dst_conn_id)}&database=${encodeURIComponent(form.dst_database)}`),
    enabled: !!form.dst_conn_id && !!form.dst_database && !form.criar_tabela,
    staleTime: 300_000,
  })
  const colsQ = useQuery<ColumnsResp>({
    queryKey: ['copias-columns', form.src_conn_id, form.src_database, form.src_schema, form.src_table],
    queryFn: () => apiFetch(
      `/copias/introspect/columns?conn_id=${encodeURIComponent(form.src_conn_id)}` +
      `&database=${encodeURIComponent(form.src_database)}` +
      `&schema=${encodeURIComponent(form.src_schema)}` +
      `&table=${encodeURIComponent(form.src_table)}`),
    enabled: !!form.src_conn_id && !!form.src_database && !!form.src_table,
    staleTime: 300_000,
  })
  const colunas = useMemo(() => colsQ.data?.columns ?? [], [colsQ.data])

  // Marca o modo lento assim que alguma resposta vier via 'airflow'.
  useEffect(() => {
    const vias = [srcDbsQ.data?.via, dstDbsQ.data?.via, srcTablesQ.data?.via,
                  dstTablesQ.data?.via, colsQ.data?.via]
    if (vias.includes('airflow')) setViaAirflow(true)
  }, [srcDbsQ.data, dstDbsQ.data, srcTablesQ.data, dstTablesQ.data, colsQ.data])

  // ── Inicialização das linhas de colunas (passo 3) ─────────────────────────
  // Reconstrói quando a origem muda; ao editar a MESMA origem salva, preserva
  // o mapeamento/transformações gravados em colunas_json.
  const srcKey = `${form.src_conn_id}|${form.src_database}|${form.src_schema}|${form.src_table}`
  const initKeyRef = useRef('')
  // A origem do formulário ainda é a origem SALVA da cópia em edição?
  const origemSalva = !!copia &&
    copia.src_conn_id === form.src_conn_id && copia.src_database === form.src_database &&
    (copia.src_schema || 'dbo') === form.src_schema && copia.src_table === form.src_table
  useEffect(() => {
    if (!colsQ.data || initKeyRef.current === srcKey) return
    initKeyRef.current = srcKey
    const salvas = new Map<string, ColunaMapeada>(
      origemSalva ? copia!.colunas.map(c => [c.origem, c]) : [])
    setRows(colsQ.data.columns.map(c => {
      const s = salvas.get(c.name)
      return {
        origem: c.name, tipo: c.type,
        destino: s?.destino ?? c.name,
        incluir: salvas.size > 0 ? !!s : true,
        transform: s?.transform ?? null,
      }
    }))
    setRowsDesatualizadas(false)
    // Coluna de partição (nome de DESTINO): mantém a salva quando a origem é a
    // mesma; caso contrário aplica a sugestão do backend (primeira PK
    // numérica/data — nesse momento origem == destino, sem rename).
    setForm(prev => ({
      ...prev,
      particao_coluna: origemSalva
        ? (copia!.particao_coluna ?? '')
        : (colsQ.data.particao_sugerida ?? ''),
    }))
    setPreview(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [colsQ.data, srcKey])

  // Modo edição resiliente: se a introspecção da origem SALVA falhar, semeia
  // as linhas a partir do mapeamento gravado (tipo desconhecido) — permite
  // salvar alterações que não dependem da lista de colunas.
  useEffect(() => {
    if (!colsQ.isError || !origemSalva || rows.length > 0) return
    setRows(copia!.colunas.map(c => ({
      origem: c.origem, tipo: 'desconhecido', destino: c.destino,
      incluir: true, transform: c.transform,
    })))
    setRowsDesatualizadas(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [colsQ.isError, origemSalva, rows.length])

  // Troca de origem: limpa NA HORA o que depende da introspecção antiga
  // (colunas, partição e amostra), sem esperar a nova resposta chegar.
  function resetOrigem(patch: Partial<FormState>) {
    initKeyRef.current = ''
    setRows([])
    setRowsDesatualizadas(false)
    setPreview(null)
    setForm(prev => ({ ...prev, ...patch, particao_coluna: '' }))
  }

  function setRow(i: number, patch: Partial<LinhaColuna>) {
    // particao_coluna referencia o nome de DESTINO de uma coluna incluída:
    // acompanha o rename aqui; se a coluna sair da seleção, o efeito da
    // partição (abaixo) reseta o valor.
    const antes = rows[i]
    if (antes && form.particao_coluna && antes.destino.trim() === form.particao_coluna &&
        patch.destino !== undefined && patch.destino.trim() !== form.particao_coluna) {
      setForm(prev => ({ ...prev, particao_coluna: patch.destino!.trim() }))
    }
    setRows(prev => prev.map((r, j) => j === i ? { ...r, ...patch } : r))
    setPreview(null)
  }

  const colunasPayload = (): ColunaMapeada[] =>
    rows.filter(r => r.incluir).map(r => ({
      origem: r.origem, destino: r.destino.trim(), transform: r.transform,
    }))

  // Colunas elegíveis para partição: somente as INCLUÍDAS, pelo nome de
  // DESTINO (alias do select compilado — a DAG aplica as faixas sobre ele).
  const colunasParticao = useMemo(() => {
    const incluidas = rows.filter(r => r.incluir && r.destino.trim())
    const elegiveis = incluidas.filter(r => PARTICAO_TIPOS.has(r.tipo.toLowerCase()))
    if (form.particao_coluna &&
        !elegiveis.some(r => r.destino.trim() === form.particao_coluna)) {
      const extra = incluidas.find(r => r.destino.trim() === form.particao_coluna)
      if (extra) elegiveis.push(extra) // ex.: tipo desconhecido no modo resiliente
    }
    return elegiveis
  }, [rows, form.particao_coluna])

  // Reseta a partição quando a coluna escolhida deixa de estar incluída
  // (renomeações são acompanhadas em setRow).
  useEffect(() => {
    if (!form.particao_coluna || rows.length === 0) return
    if (!rows.some(r => r.incluir && r.destino.trim() === form.particao_coluna))
      setForm(prev => ({ ...prev, particao_coluna: '' }))
  }, [rows, form.particao_coluna])

  // ── Preview (amostra transformada) ────────────────────────────────────────

  const previewMut = useMutation({
    mutationFn: () => apiFetch<PreviewResp>('/copias/preview', {
      method: 'POST',
      body: JSON.stringify({
        src_conn_id: form.src_conn_id,
        src_database: form.src_database,
        src_schema: form.src_schema,
        src_table: form.src_table,
        src_filtro: form.src_filtro.trim() || null,
        colunas: colunasPayload(),
      }),
    }),
    onSuccess: d => {
      setPreview(d)
      if (d.via === 'airflow') setViaAirflow(true)
      // A amostra renderiza abaixo da tabela de colunas — garante que fique visível
      setTimeout(() => previewRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 50)
    },
    onError: (e: any) => toast.error(e?.message || 'Falha ao gerar a amostra'),
  })
  const previewRef = useRef<HTMLDivElement>(null)

  // ── Validação por passo ───────────────────────────────────────────────────

  function validateStep(s: number): string[] {
    const e: string[] = []
    if (s === 0) {
      if (!form.src_conn_id) e.push('Selecione a conexão de origem')
      if (!form.src_database) e.push('Selecione o banco de origem')
      if (!form.src_table) e.push('Selecione a tabela de origem')
      // Não avança ao passo Colunas sem a introspecção da origem resolvida
      // (no modo edição resiliente as linhas vêm de colunas_json e liberam).
      if (form.src_table && rows.length === 0) {
        if (colsQ.isFetching) e.push('Aguarde a leitura das colunas da origem para avançar')
        else if (colsQ.isError) e.push('Falha ao ler as colunas da origem — revise a conexão/tabela antes de avançar')
      }
    }
    if (s === 1) {
      if (!form.dst_conn_id) e.push('Selecione a conexão de destino')
      if (!form.dst_database) e.push('Selecione o banco de destino')
      if (!form.dst_table.trim()) {
        e.push(form.criar_tabela ? 'Informe o nome da nova tabela' : 'Selecione a tabela de destino')
      }
      if (!form.dst_schema.trim()) e.push('Informe o schema de destino')
      const mesmaTabela =
        !!form.src_conn_id &&
        form.src_conn_id.trim().toLowerCase() === form.dst_conn_id.trim().toLowerCase() &&
        !!form.dst_database &&
        form.src_database.toLowerCase() === form.dst_database.toLowerCase() &&
        form.src_schema.trim().toLowerCase() === form.dst_schema.trim().toLowerCase() &&
        !!form.dst_table.trim() &&
        form.src_table.toLowerCase() === form.dst_table.trim().toLowerCase()
      if (mesmaTabela)
        e.push('O destino não pode ser igual à origem (mesma conexão, banco, schema e tabela): ' +
          'a cópia gravaria sobre a própria fonte — e com "Truncar destino" os dados de origem seriam apagados antes da leitura')
    }
    if (s === 2) {
      const incluidas = rows.filter(r => r.incluir)
      if (incluidas.length === 0) e.push('Inclua ao menos uma coluna')
      incluidas.forEach(r => {
        if (!r.destino.trim()) e.push(`Coluna "${r.origem}": nome de destino é obrigatório`)
        const t = r.transform
        if (!t) return
        if (t.tipo === 'pad_condicional') {
          if (!t.campo_condicao) e.push(`Coluna "${r.origem}": informe o campo da condição`)
          const casos = t.casos ?? []
          if (casos.length === 0) e.push(`Coluna "${r.origem}": adicione ao menos um caso`)
          casos.forEach((c, i) => {
            if (!c.valor.trim()) e.push(`Coluna "${r.origem}": caso ${i + 1} sem valor`)
            if (!c.tamanho || c.tamanho < 1) e.push(`Coluna "${r.origem}": caso ${i + 1} com tamanho inválido`)
          })
        }
        if (t.tipo === 'pad_fixo' && (!t.tamanho || t.tamanho < 1))
          e.push(`Coluna "${r.origem}": tamanho do preenchimento inválido`)
        if (t.tipo === 'substring' && ((!t.inicio || t.inicio < 1) || (!t.tamanho || t.tamanho < 1)))
          e.push(`Coluna "${r.origem}": início/tamanho do substring inválidos`)
        if (t.tipo === 'cast' && !(t.tipo_sql ?? '').trim())
          e.push(`Coluna "${r.origem}": informe o tipo SQL do cast`)
        if (t.tipo === 'sql' && !(t.expressao ?? '').trim())
          e.push(`Coluna "${r.origem}": informe a expressão SQL`)
      })
      const destinos = incluidas.map(r => r.destino.trim().toLowerCase()).filter(Boolean)
      if (new Set(destinos).size !== destinos.length)
        e.push('Há nomes de destino duplicados entre as colunas incluídas')
    }
    if (s === 3) {
      if (form.streams < 1 || form.streams > 8) e.push('Streams deve estar entre 1 e 8')
      if (form.batch_size < 1000 || form.batch_size > 200000) e.push('Batch size fora da faixa permitida')
    }
    if (s === 4) {
      if (!form.nome.trim()) e.push('Nome da cópia é obrigatório')
    }
    return e
  }

  function goNext() {
    const e = validateStep(step)
    if (e.length) { setStepErrors(prev => ({ ...prev, [step]: e })); return }
    setStepErrors(prev => ({ ...prev, [step]: [] }))
    if (step < 4) setStep((step + 1) as Step)
  }
  function goPrev() { if (step > 0) setStep((step - 1) as Step) }

  // ── Salvar (+ opcional executar) ──────────────────────────────────────────

  const saveMut = useMutation({
    mutationFn: async (executarDepois: boolean) => {
      const body: Record<string, unknown> = {
        ...(copia ? { id: copia.id } : {}),
        nome: form.nome.trim(),
        src_conn_id: form.src_conn_id,
        src_database: form.src_database,
        src_schema: form.src_schema.trim() || 'dbo',
        src_table: form.src_table,
        src_filtro: form.src_filtro.trim() || null,
        dst_conn_id: form.dst_conn_id,
        dst_database: form.dst_database,
        dst_schema: form.dst_schema.trim() || 'dbo',
        dst_table: form.dst_table.trim(),
        criar_tabela: form.criar_tabela,
        truncar_antes: form.truncar_antes,
        particao_coluna: form.particao_coluna || null,
        streams: form.streams,
        batch_size: form.batch_size,
        colunas: colunasPayload(),
      }
      const salvo = await apiFetch<{ id: number }>('/copias', {
        method: 'POST', body: JSON.stringify(body),
      })
      let execId: number | null = null
      let execErro: string | null = null
      if (executarDepois) {
        try {
          const ex = await apiFetch<{ exec_id: number }>(
            `/copias/${salvo.id}/executar`, { method: 'POST' })
          execId = ex.exec_id
        } catch (err: any) {
          execErro = err?.message || 'falha ao disparar a execução'
        }
      }
      return { id: salvo.id, execId, execErro }
    },
    onSuccess: res => {
      qc.invalidateQueries({ queryKey: ['copias'] })
      // O detalhe em cache ficaria obsoleto — remove (prefixo) para a próxima
      // edição reabrir com os dados frescos do servidor.
      qc.removeQueries({ queryKey: ['copia-detalhe'] })
      if (res.execErro) toast.error(`Cópia salva, mas a execução falhou: ${res.execErro}`)
      else toast.success(isEdit ? 'Cópia atualizada!' : 'Cópia salva!')
      onClose()
      if (res.execId != null) onExecutado(res.execId)
    },
    onError: (e: any) => {
      setStepErrors(prev => ({ ...prev, 4: [e?.message || 'Erro ao salvar a cópia'] }))
    },
  })

  function validateAllAndSave(executarDepois: boolean) {
    const allErrors: Record<number, string[]> = {}
    let firstBad = -1
    for (const s of [0, 1, 2, 3, 4]) {
      const e = validateStep(s)
      if (e.length) { allErrors[s] = e; if (firstBad < 0) firstBad = s }
    }
    if (firstBad >= 0) {
      setStepErrors(prev => ({ ...prev, ...allErrors }))
      setStep(firstBad as Step)
      return
    }
    saveMut.mutate(executarDepois)
  }

  // Fechar com confirmação se há conteúdo preenchido (evita perder o trabalho).
  const hasContent = isEdit ? step > 0 : (!!form.src_conn_id || step > 0)
  function requestClose() {
    if (saveMut.isPending) return
    if (hasContent) setConfirmClose(true)
    else onClose()
  }

  const curStepErrors = stepErrors[step] ?? []
  const incluidas = rows.filter(r => r.incluir)
  const transformadas = incluidas.filter(r => r.transform)

  return (
    <>
    <Modal open title={isEdit ? `Editar cópia: ${copia!.nome}` : 'Nova cópia de dados'}
      onClose={requestClose} size="2xl">
      <div className="flex flex-col gap-4">

        <Stepper step={step} setStep={setStep} errors={stepErrors} />

        {curStepErrors.length > 0 && (
          <div className="bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800 rounded-lg px-3 py-2">
            {curStepErrors.map((e, i) => (
              <p key={i} className="text-xs text-red-700 dark:text-red-400">⚠ {e}</p>
            ))}
          </div>
        )}

        {/* ── PASSO 1: ORIGEM ── */}
        {step === 0 && (
          <div className="flex flex-col gap-3">
            {connLoading
              ? <IntrospectStatus carregando rotulo="conexões" viaAirflow={viaAirflow} />
              : (
                <Select label="Conexão de origem (Airflow) *" value={form.src_conn_id}
                  onChange={e => resetOrigem({
                    src_conn_id: e.target.value,
                    src_database: '', src_table: '', src_schema: 'dbo',
                  })}>
                  <option value="">Selecione…</option>
                  {conexoes.map(c => (
                    <option key={c.conn_id} value={c.conn_id}>
                      {c.conn_id} — {c.host}{c.port ? `:${c.port}` : ''}
                    </option>
                  ))}
                </Select>
              )}
            {!connLoading && conexoes.length === 0 && (
              <p className="text-xs text-amber-700 dark:text-amber-400">
                Nenhuma connection MSSQL encontrada no Airflow — cadastre-a lá primeiro.
              </p>
            )}

            {form.src_conn_id && (
              srcDbsQ.isLoading || srcDbsQ.isError
                ? <IntrospectStatus carregando={srcDbsQ.isLoading}
                    erro={(srcDbsQ.error as any)?.message} rotulo="bancos" viaAirflow={viaAirflow} />
                : (
                  <div className="flex flex-col gap-1">
                    <Select label="Banco de origem *" value={form.src_database}
                      onChange={e => resetOrigem({
                        src_database: e.target.value, src_table: '', src_schema: 'dbo',
                      })}>
                      <option value="">Selecione…</option>
                      {(srcDbsQ.data?.databases ?? []).map(d => <option key={d} value={d}>{d}</option>)}
                    </Select>
                    <ViaAirflowHint via={srcDbsQ.data?.via} />
                  </div>
                )
            )}

            {form.src_database && (
              srcTablesQ.isLoading || srcTablesQ.isError
                ? <IntrospectStatus carregando={srcTablesQ.isLoading}
                    erro={(srcTablesQ.error as any)?.message} rotulo="tabelas" viaAirflow={viaAirflow} />
                : (
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">Tabela de origem *</label>
                    <TabelaPicker tabelas={srcTablesQ.data?.tables ?? []}
                      schema={form.src_schema} table={form.src_table}
                      onSelect={(schema, name) => {
                        if (schema === form.src_schema && name === form.src_table) return
                        resetOrigem({ src_schema: schema, src_table: name })
                      }} />
                    <ViaAirflowHint via={srcTablesQ.data?.via} />
                  </div>
                )
            )}

            {form.src_table && (
              <div className="flex flex-col gap-1">
                <Input label="Filtro opcional (WHERE, sem a palavra WHERE)"
                  value={form.src_filtro}
                  onChange={e => { f('src_filtro', e.target.value); setPreview(null) }}
                  placeholder="ex: dt_movimento >= '2025-01-01'"
                  className="font-mono" />
                <p className="text-[10px] text-dim">
                  Aplica-se à leitura da origem (linhas copiadas e contagem total).
                </p>
              </div>
            )}
          </div>
        )}

        {/* ── PASSO 2: DESTINO ── */}
        {step === 1 && (
          <div className="flex flex-col gap-3">
            <Select label="Conexão de destino (Airflow) *" value={form.dst_conn_id}
              onChange={e => setForm(prev => ({
                ...prev, dst_conn_id: e.target.value, dst_database: '',
                dst_table: '', dst_schema: 'dbo',
              }))}>
              <option value="">Selecione…</option>
              {conexoes.map(c => (
                <option key={c.conn_id} value={c.conn_id}>
                  {c.conn_id} — {c.host}{c.port ? `:${c.port}` : ''}
                </option>
              ))}
            </Select>

            {form.dst_conn_id && (
              dstDbsQ.isLoading || dstDbsQ.isError
                ? <IntrospectStatus carregando={dstDbsQ.isLoading}
                    erro={(dstDbsQ.error as any)?.message} rotulo="bancos" viaAirflow={viaAirflow} />
                : (
                  <div className="flex flex-col gap-1">
                    <Select label="Banco de destino *" value={form.dst_database}
                      onChange={e => setForm(prev => ({
                        ...prev, dst_database: e.target.value, dst_table: '', dst_schema: 'dbo',
                      }))}>
                      <option value="">Selecione…</option>
                      {(dstDbsQ.data?.databases ?? []).map(d => <option key={d} value={d}>{d}</option>)}
                    </Select>
                    <ViaAirflowHint via={dstDbsQ.data?.via} />
                  </div>
                )
            )}

            {form.dst_database && (
              <label className="flex items-center gap-2 cursor-pointer bg-canvas border border-edge rounded-lg px-3 py-2">
                <input type="checkbox" checked={form.criar_tabela}
                  onChange={e => setForm(prev => ({
                    ...prev, criar_tabela: e.target.checked, dst_table: '', dst_schema: 'dbo',
                  }))}
                  className="accent-blue-500" />
                <span className="text-sm text-ink">Criar nova tabela no destino</span>
              </label>
            )}

            {form.dst_database && form.criar_tabela && (
              <div className="grid grid-cols-2 gap-3">
                <Input label="Schema" value={form.dst_schema}
                  onChange={e => f('dst_schema', e.target.value)}
                  placeholder="dbo" className="font-mono" />
                <Input label="Nome da nova tabela *" value={form.dst_table}
                  onChange={e => f('dst_table', e.target.value)}
                  placeholder="ex: clientes_copia" className="font-mono" />
                <p className="col-span-2 text-[10px] text-dim -mt-1">
                  A tabela é criada como heap (sem índices), com os tipos da origem;
                  colunas com zeros à esquerda viram VARCHAR do tamanho necessário.
                </p>
              </div>
            )}

            {form.dst_database && !form.criar_tabela && (
              dstTablesQ.isLoading || dstTablesQ.isError
                ? <IntrospectStatus carregando={dstTablesQ.isLoading}
                    erro={(dstTablesQ.error as any)?.message} rotulo="tabelas" viaAirflow={viaAirflow} />
                : (
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-dim font-medium">Tabela de destino (existente) *</label>
                    <TabelaPicker tabelas={dstTablesQ.data?.tables ?? []}
                      schema={form.dst_schema} table={form.dst_table}
                      onSelect={(schema, name) => setForm(prev => ({
                        ...prev, dst_schema: schema, dst_table: name,
                      }))} />
                    <ViaAirflowHint via={dstTablesQ.data?.via} />
                  </div>
                )
            )}

            {form.dst_table && (
              <label className="flex items-start gap-2 cursor-pointer bg-canvas border border-edge rounded-lg px-3 py-2">
                <input type="checkbox" checked={form.truncar_antes}
                  onChange={e => f('truncar_antes', e.target.checked)}
                  className="mt-0.5 accent-red-500" />
                <span className="text-sm text-ink">Truncar destino antes de copiar</span>
              </label>
            )}
            {form.truncar_antes && (
              <div className="flex items-start gap-2 p-3 rounded-lg bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800">
                <AlertTriangle size={16} className="text-red-500 shrink-0 mt-0.5" />
                <p className="text-sm text-red-700 dark:text-red-300">
                  Atenção: TODAS as linhas de{' '}
                  <span className="font-mono font-semibold">
                    {form.dst_schema}.{form.dst_table || '?'}
                  </span>{' '}
                  serão apagadas antes de cada execução desta cópia.
                </p>
              </div>
            )}
          </div>
        )}

        {/* ── PASSO 3: COLUNAS & TRANSFORMAÇÕES ── */}
        {step === 2 && (
          <div className="flex flex-col gap-3">
            {(colsQ.isLoading || colsQ.isError) && (
              <IntrospectStatus carregando={colsQ.isLoading}
                erro={(colsQ.error as any)?.message} rotulo="colunas" viaAirflow={viaAirflow} />
            )}
            {colsQ.data && <ViaAirflowHint via={colsQ.data.via} />}

            {rowsDesatualizadas && (
              <div className="flex items-start gap-2 p-3 rounded-lg bg-amber-50 border border-amber-200 dark:bg-amber-900/15 dark:border-amber-800/40">
                <AlertTriangle size={16} className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
                <p className="text-xs text-amber-700 dark:text-amber-400">
                  Não foi possível ler as colunas na origem — exibindo o mapeamento
                  salvo, que pode estar desatualizado. Você ainda pode salvar
                  alterações que não dependem da lista de colunas.
                </p>
              </div>
            )}

            {rows.length > 0 && (
              <>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-dim">
                    {incluidas.length} de {rows.length} coluna{rows.length !== 1 ? 's' : ''} incluída{incluidas.length !== 1 ? 's' : ''}
                    {transformadas.length > 0 && ` · ${transformadas.length} com transformação`}
                  </span>
                  <div className="flex gap-2">
                    <button type="button"
                      onClick={() => { setRows(prev => prev.map(r => ({ ...r, incluir: true }))); setPreview(null) }}
                      className="text-[11px] text-blue-700 dark:text-blue-400 hover:underline">
                      Incluir todas
                    </button>
                    <button type="button"
                      onClick={() => { setRows(prev => prev.map(r => ({ ...r, incluir: false }))); setPreview(null) }}
                      className="text-[11px] text-blue-700 dark:text-blue-400 hover:underline">
                      Excluir todas
                    </button>
                  </div>
                </div>

                <div className="border border-edge rounded-lg overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-xs text-dim border-b border-edge bg-canvas/50">
                        <th className="px-3 py-2 w-8"></th>
                        <th className="px-3 py-2 text-left font-semibold">Origem</th>
                        <th className="px-3 py-2 text-left font-semibold">Destino</th>
                        <th className="px-3 py-2 text-left font-semibold">Transformação</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r, i) => (
                        <tr key={r.origem} className={`border-b border-edge/50 align-top ${!r.incluir ? 'opacity-50' : ''}`}>
                          <td className="px-3 py-2">
                            <input type="checkbox" checked={r.incluir}
                              onChange={e => setRow(i, { incluir: e.target.checked })}
                              className="accent-blue-500" title="Incluir coluna" />
                          </td>
                          <td className="px-3 py-2">
                            <span className="font-mono text-xs text-ink">{r.origem}</span>
                            <span className="block text-[10px] text-dim">{r.tipo}</span>
                          </td>
                          <td className="px-3 py-2">
                            <input value={r.destino} disabled={!r.incluir}
                              onChange={e => setRow(i, { destino: e.target.value })}
                              className="w-40 bg-panel border border-edge text-ink rounded-md px-2 py-1 text-xs font-mono placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-60" />
                          </td>
                          <td className="px-3 py-2">
                            <div className="flex flex-col gap-2">
                              <select value={r.transform?.tipo ?? ''} disabled={!r.incluir}
                                onChange={e => setRow(i, {
                                  transform: e.target.value
                                    ? novoTransform(e.target.value as TransformTipo)
                                    : null,
                                })}
                                className="w-56 bg-panel border border-edge text-ink rounded-md px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-60">
                                {TRANSFORM_OPTIONS.map(o => (
                                  <option key={o.value} value={o.value}>{o.label}</option>
                                ))}
                              </select>
                              {r.incluir && r.transform && (
                                <TransformEditor transform={r.transform} colunas={colunas}
                                  onChange={t => setRow(i, { transform: t })} />
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="flex items-center gap-3">
                  <Button variant="secondary" size="sm" loading={previewMut.isPending}
                    disabled={incluidas.length === 0}
                    onClick={() => previewMut.mutate()}>
                    <Eye size={13} /> Visualizar amostra
                  </Button>
                  {previewMut.isPending && viaAirflow && (
                    <span className="text-[11px] text-amber-700 dark:text-amber-400">
                      consultando via Airflow (pode levar ~30s)
                    </span>
                  )}
                </div>

                {preview && (
                  <div ref={previewRef} className="border border-edge rounded-lg overflow-hidden">
                    <div className="px-3 py-1.5 border-b border-edge bg-canvas/50 flex items-center justify-between">
                      <span className="text-[11px] text-dim">
                        Amostra transformada — {preview.rows.length} linha{preview.rows.length !== 1 ? 's' : ''} (máx. 50)
                      </span>
                      <button type="button" onClick={() => setPreview(null)}
                        className="text-dim hover:text-ink transition-colors"><X size={13} /></button>
                    </div>
                    <div className="overflow-auto max-h-64">
                      <table className="w-full text-xs">
                        <thead className="sticky top-0 bg-canvas">
                          <tr className="text-[10px] text-dim border-b border-edge">
                            {preview.columns.map(c => (
                              <th key={c} className="px-2 py-1.5 text-left font-semibold whitespace-nowrap font-mono">{c}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {preview.rows.map((linha, i) => (
                            <tr key={i} className="border-b border-edge/40">
                              {linha.map((v, j) => (
                                <td key={j} className="px-2 py-1 font-mono whitespace-nowrap text-ink">
                                  {v == null ? <span className="text-dim italic">NULL</span> : String(v)}
                                </td>
                              ))}
                            </tr>
                          ))}
                          {preview.rows.length === 0 && (
                            <tr><td colSpan={Math.max(1, preview.columns.length)}
                              className="px-3 py-4 text-center text-dim">Nenhuma linha na origem.</td></tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* ── PASSO 4: PERFORMANCE ── */}
        {step === 3 && (
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1">
              <Select label="Coluna de partição (paraleliza a leitura em faixas)"
                value={form.particao_coluna}
                onChange={e => f('particao_coluna', e.target.value)}>
                <option value="">Nenhuma (1 stream)</option>
                {colunasParticao.map(r => (
                  <option key={r.origem} value={r.destino.trim()}>
                    {r.destino.trim()} ({r.tipo}){colsQ.data?.particao_sugerida === r.origem ? ' — sugerida' : ''}
                  </option>
                ))}
              </Select>
              <p className="text-[10px] text-dim">
                Apenas colunas incluídas (pelo nome de destino) de tipo numérico
                (int/bigint/decimal) ou de data (date/datetime) podem ser divididas
                em faixas. Sem partição, a cópia usa 1 stream.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <Select label="Streams paralelos" value={String(form.streams)}
                disabled={!form.particao_coluna}
                onChange={e => f('streams', parseInt(e.target.value) || 4)}>
                {[1, 2, 3, 4, 5, 6, 7, 8].map(n => (
                  <option key={n} value={n}>{n}{n === 4 ? ' (padrão)' : ''}</option>
                ))}
              </Select>
              <Select label="Batch size (linhas por lote)" value={String(form.batch_size)}
                onChange={e => f('batch_size', parseInt(e.target.value) || 50000)}>
                {BATCH_OPTS.map(n => (
                  <option key={n} value={n}>{fmtRows(n)}{n === 50000 ? ' (padrão)' : ''}</option>
                ))}
              </Select>
            </div>
            {!form.particao_coluna && (
              <p className="text-[11px] text-dim">
                Sem coluna de partição a cópia roda com 1 stream — o valor acima é ignorado.
              </p>
            )}
          </div>
        )}

        {/* ── PASSO 5: REVISÃO ── */}
        {step === 4 && (
          <div className="flex flex-col gap-3">
            <Input label="Nome da cópia *" value={form.nome}
              onChange={e => f('nome', e.target.value)}
              placeholder="ex: Clientes DMDB41 → DW" maxLength={200} />

            <div className="border border-edge rounded-xl overflow-hidden">
              <div className="bg-canvas border-b border-edge px-3 py-2">
                <span className="text-[10px] font-bold uppercase tracking-wider text-blue-700 dark:text-blue-400">Origem → Destino</span>
              </div>
              <div className="p-3 text-xs flex flex-col gap-1.5">
                <div>
                  <span className="text-dim">Origem: </span>
                  <span className="font-mono text-ink">
                    {form.src_conn_id} · {form.src_database}.{form.src_schema}.{form.src_table}
                  </span>
                </div>
                {form.src_filtro.trim() && (
                  <div>
                    <span className="text-dim">Filtro: </span>
                    <span className="font-mono text-ink">WHERE {form.src_filtro.trim()}</span>
                  </div>
                )}
                <div>
                  <span className="text-dim">Destino: </span>
                  <span className="font-mono text-ink">
                    {form.dst_conn_id} · {form.dst_database}.{form.dst_schema}.{form.dst_table}
                  </span>
                  {form.criar_tabela && (
                    <span className="ml-2 text-green-700 dark:text-green-400">(tabela nova)</span>
                  )}
                </div>
                {form.truncar_antes && (
                  <div className="text-red-700 dark:text-red-400 font-medium">
                    ⚠ O destino será truncado antes de cada execução.
                  </div>
                )}
              </div>
            </div>

            <div className="border border-edge rounded-xl overflow-hidden">
              <div className="bg-canvas border-b border-edge px-3 py-2">
                <span className="text-[10px] font-bold uppercase tracking-wider text-blue-700 dark:text-blue-400">Colunas & Performance</span>
              </div>
              <div className="p-3 text-xs flex flex-col gap-1.5">
                <div>
                  <span className="text-dim">Colunas: </span>
                  <span className="text-ink">
                    {incluidas.length} incluída{incluidas.length !== 1 ? 's' : ''}
                    {transformadas.length > 0 && ` · ${transformadas.length} com transformação`}
                  </span>
                </div>
                {transformadas.length > 0 && (
                  <ul className="flex flex-col gap-0.5 pl-1">
                    {transformadas.map(r => (
                      <li key={r.origem} className="text-ink">
                        <span className="font-mono">{r.origem}</span>
                        {r.destino.trim() !== r.origem && (
                          <span className="font-mono"> → {r.destino.trim()}</span>
                        )}
                        <span className="text-dim">: {transformResumo(r.transform)}</span>
                      </li>
                    ))}
                  </ul>
                )}
                <div>
                  <span className="text-dim">Partição: </span>
                  <span className="text-ink">
                    {form.particao_coluna
                      ? `${form.particao_coluna} · ${form.streams} stream${form.streams !== 1 ? 's' : ''}`
                      : 'nenhuma (1 stream)'}
                  </span>
                  <span className="text-dim"> · Batch: </span>
                  <span className="text-ink">{fmtRows(form.batch_size)} linhas</span>
                </div>
              </div>
            </div>

            {saveMut.isError && (
              <div className="bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800 rounded-lg px-3 py-2 text-xs text-red-700 dark:text-red-400">
                Erro ao salvar: {(saveMut.error as any)?.message}
              </div>
            )}
          </div>
        )}

        {/* ── Navegação ── */}
        <div className="flex justify-between items-center pt-1 border-t border-edge">
          <Button variant="secondary" onClick={step === 0 ? requestClose : goPrev}>
            {step === 0 ? 'Cancelar' : '← Voltar'}
          </Button>
          <div className="flex gap-2">
            {step < 4 ? (
              <Button onClick={goNext}>Próximo →</Button>
            ) : (
              <>
                <Button variant="secondary" loading={saveMut.isPending}
                  onClick={() => validateAllAndSave(false)}>
                  <Save size={13} /> Salvar
                </Button>
                {podeExecutar && (
                  <Button loading={saveMut.isPending}
                    onClick={() => validateAllAndSave(true)}>
                    <Play size={13} /> Salvar e executar
                  </Button>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </Modal>

    {/* Confirmação ao sair sem finalizar (evita perder dados preenchidos) */}
    {confirmClose && (
      <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
        <div className="absolute inset-0 bg-black/60" onClick={() => setConfirmClose(false)} />
        <div className="relative w-full max-w-sm bg-panel border border-edge rounded-xl shadow-2xl p-5 flex flex-col gap-4">
          <h3 className="text-base font-semibold text-ink">Sair sem finalizar?</h3>
          <p className="text-sm text-dim">
            Você tem informações preenchidas que ainda{' '}
            <strong className="text-ink">não foram salvas</strong>. Se sair agora, vai perder tudo.
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setConfirmClose(false)}>Continuar editando</Button>
            <Button variant="danger" onClick={() => { setConfirmClose(false); onClose() }}>Sair sem salvar</Button>
          </div>
        </div>
      </div>
    )}
    </>
  )
}
