// Estados que indicam chamado encerrado (não-ativo para fins de INC visual)
const ESTADOS_ENCERRADO = new Set(['resolvido', 'encerrado'])

export interface Chamado {
  sys_id: string
  numero: string
  tipo: string             // 'incident' | 'ritm' | 'task' | 'change'
  titulo: string | null
  descricao?: string | null
  estado_kanban: string    // 'novo' | 'andamento' | 'aguardando' | 'resolvido' | 'outros'
  estado_origem?: string | null
  atribuido_a: string | null
  atribuido_a_email?: string | null
  grupo?: string | null
  demandante?: string | null
  prioridade?: string | null
  categoria_diaadia?: string | null
  tipo_demanda?: string | null
  objetos?: string | null
  catalogo?: string | null
  veredito?: string | null
  triagem_origem?: string | null
  triagem_erro?: string | null
  triagem_em?: string | null
  resumo?: string | null
  lacunas?: string[]
  perguntas?: string | null
  aberto_em?: string | null
  url?: string | null
  tem_anexo?: boolean
  sla_vencido?: boolean
  prazo?: string | null
  idade_dias?: number | null
  pai_sys_id?: string | null
}

export interface NotaChamado {
  sys_id_nota: string
  autor: string | null
  autor_email: string | null
  criado_em: string | null
  texto: string | null
  tipo: string   // 'work_notes' | 'comments'
}

export interface AnexoChamado {
  sys_id_anexo: string
  nome_arquivo: string | null
  mime_type: string | null
  tamanho_bytes: number | null
  url_proxy: string
  criado_em: string | null
}

export interface ChamadoDetalhe {
  chamado: Chamado
  notas: NotaChamado[]
  anexos: AnexoChamado[]
}

// INC ativo = tipo incident + estado NÃO encerrado
export function isINCAtivo(c: Pick<Chamado, 'tipo' | 'estado_kanban'>): boolean {
  return c.tipo === 'incident' && !ESTADOS_ENCERRADO.has(c.estado_kanban)
}

export function formatBytes(b: number | null | undefined): string {
  if (!b) return '—'
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`
  return `${(b / (1024 * 1024)).toFixed(1)} MB`
}

export function formatDataNota(s: string | null | undefined): string {
  if (!s) return '—'
  const d = new Date(s)
  if (isNaN(d.getTime())) return s
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit' }) +
    ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}
