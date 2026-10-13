// Descoberta do Pipeline (F2 da UX profissional): contrato puro da lista única.
// Filtros na URL, consulta paginada ao índice .NET, rótulos visíveis de situação
// (sem depender de hover), destino de entrada e menu secundário. Sem React: a
// bancada tests/js/pipeline_index_harness.cjs executa este arquivo como está.
import type { WorkspaceCapabilities, WorkspaceExperience } from './workspace'

export type PipelineIndexState = 'all' | 'draft' | 'published' | 'editing' | 'inactive'
export interface PipelineIndexItem {
 pipelineName: string; displayName: string | null; project: string | null; domain: string | null; responsible: string | null
 hasDraft: boolean; draftRevision: number | null; hasPublished: boolean; publishedVersionNumber: number | null; isActive: boolean | null; managed: boolean
 updatedAt: string | null; updatedSource: 'draft' | 'version' | null; editorUser: string | null; editorName: string | null; leaseExpiresAt: string | null
}
export interface PipelineIndexPage { total: number; limit: number; offset: number; items: PipelineIndexItem[] }
export interface PipelineIndexFilters { search: string; project: string; domain: string; state: PipelineIndexState; page: number }

export const PIPELINE_INDEX_LIMIT = 50
export const PIPELINE_INDEX_DEBOUNCE_MS = 250
const STATES: readonly PipelineIndexState[] = ['all', 'draft', 'published', 'editing', 'inactive']
const clean = (value: string | null | undefined, max = 200) => String(value ?? '').trim().slice(0, max)

// ── Filtros na URL ─────────────────────────────────────────────────────────
// Voltar à lista restaura busca, filtros e página; valor desconhecido vira o padrão.
// "Em edição" é resumo autorizado a todo leitor do índice (posse válida, sem definição).
export function filtersFromSearch(search: URLSearchParams): PipelineIndexFilters {
 const raw = search.get('estado') ?? 'all'
 const state = (STATES as readonly string[]).includes(raw) ? raw as PipelineIndexState : 'all'
 const page = Number(search.get('pagina') ?? '1')
 return { search: clean(search.get('busca')), project: clean(search.get('projeto')), domain: clean(search.get('dominio')), state, page: Number.isInteger(page) && page > 0 && page <= 20000 ? page : 1 }
}
// Preserva chaves alheias (ex.: legado) e omite o que é padrão.
export function filtersToSearch(filters: PipelineIndexFilters, base: URLSearchParams = new URLSearchParams()): URLSearchParams {
 const next = new URLSearchParams(base)
 const set = (key: string, value: string, fallback = '') => { if (value && value !== fallback) next.set(key, value); else next.delete(key) }
 set('busca', clean(filters.search)); set('projeto', clean(filters.project)); set('dominio', clean(filters.domain)); set('estado', filters.state, 'all'); set('pagina', String(filters.page), '1')
 return next
}
// Mudar busca/filtro volta à primeira página; mudar só a página preserva o resto.
export function withFilter(filters: PipelineIndexFilters, patch: Partial<Omit<PipelineIndexFilters, 'page'>>): PipelineIndexFilters {
 return { ...filters, ...patch, page: 1 }
}
export function hasActiveFilters(filters: PipelineIndexFilters): boolean {
 return !!(filters.search || filters.project || filters.domain || filters.state !== 'all')
}

// ── Consulta ───────────────────────────────────────────────────────────────
export function pipelineIndexQueryKey(token: string | null, filters: PipelineIndexFilters) {
 return ['pipeline-index', token, filters.search, filters.project, filters.domain, filters.state, filters.page] as const
}
export function pipelineIndexPath(filters: PipelineIndexFilters): string {
 const query = new URLSearchParams({ limit: String(PIPELINE_INDEX_LIMIT), offset: String((filters.page - 1) * PIPELINE_INDEX_LIMIT) })
 if (filters.search) query.set('search', filters.search)
 if (filters.project) query.set('project', filters.project)
 if (filters.domain) query.set('domain', filters.domain)
 if (filters.state !== 'all') query.set('state', filters.state)
 return `/workspace/pipeline-index?${query}`
}
export function pageSummary(page: Pick<PipelineIndexPage, 'total' | 'limit' | 'offset'> & { count: number }): { text: string; hasPrevious: boolean; hasNext: boolean; pages: number; current: number } {
 const pages = Math.max(1, Math.ceil(page.total / page.limit)); const current = Math.floor(page.offset / page.limit) + 1
 const text = page.total === 0 ? 'Nenhum pipeline' : page.count === 0 ? `Página ${current} sem resultados; ${page.total} no total` : `${page.offset + 1}–${page.offset + page.count} de ${page.total}`
 return { text, hasPrevious: current > 1, hasNext: page.offset + page.count < page.total, pages, current }
}

// ── Situação visível ───────────────────────────────────────────────────────
// Flags coexistem: publicado e em desenvolvimento aparecem juntos na mesma linha.
// Edição em andamento vem só da posse válida informada pelo servidor.
export type PipelineChipTone = 'success' | 'info' | 'warning' | 'neutral'
export interface PipelineChip { key: 'published' | 'draft' | 'editing' | 'inactive' | 'unpublished'; label: string; tone: PipelineChipTone }
export function pipelineChips(item: PipelineIndexItem, me?: string | null): PipelineChip[] {
 const chips: PipelineChip[] = []
 if (item.hasPublished) chips.push({ key: 'published', label: item.publishedVersionNumber ? `Publicado · versão ${item.publishedVersionNumber}` : 'Publicado', tone: 'success' })
 else chips.push({ key: 'unpublished', label: 'Ainda não publicado', tone: 'neutral' })
 if (item.hasDraft) chips.push({ key: 'draft', label: item.draftRevision ? `Em desenvolvimento · revisão ${item.draftRevision}` : 'Em desenvolvimento', tone: 'info' })
 if (item.editorUser) chips.push({ key: 'editing', label: me && item.editorUser.toLowerCase() === me.toLowerCase() ? 'Em edição por você' : `Em edição por ${item.editorName || item.editorUser}`, tone: 'warning' })
 if (item.hasPublished && item.isActive === false) chips.push({ key: 'inactive', label: 'Inativo', tone: 'neutral' })
 return chips
}
export function pipelineTitle(item: Pick<PipelineIndexItem, 'displayName' | 'pipelineName'>): string { return item.displayName?.trim() || item.pipelineName }
// Data mapeada à origem; sem origem conhecida, nada é inventado.
export function updatedLabel(item: Pick<PipelineIndexItem, 'updatedAt' | 'updatedSource'>, format: (date: Date) => string = date => date.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })): string | null {
 if (!item.updatedAt || !item.updatedSource) return null
 const date = new Date(item.updatedAt)
 if (Number.isNaN(date.getTime())) return null
 return `${item.updatedSource === 'draft' ? 'Rascunho salvo' : 'Versão criada'} em ${format(date)}`
}

// ── Entrada e menu ─────────────────────────────────────────────────────────
// O nome sempre leva à Visão geral; com rascunho e permissão de edição há
// "Continuar montagem". Capacidades vêm do servidor; a experiência não as concede.
export type PipelineDestination = 'visao-geral' | 'montagem' | 'execucao' | 'configuracao' | 'versoes'
export interface PipelineRoute { tab: PipelineDestination; experience: WorkspaceExperience }
type Actions = WorkspaceCapabilities['actions']
export function overviewRoute(actions: Actions): PipelineRoute { return { tab: 'visao-geral', experience: actions.editDraft ? 'desenvolvimento' : 'consulta' } }
export function resumeAction(item: PipelineIndexItem, actions: Actions, me?: string | null): { label: string; route: PipelineRoute } | null {
 if (!item.hasDraft || !actions.editDraft || !actions.consultStages) return null
 const other = !!item.editorUser && (!me || item.editorUser.toLowerCase() !== me.toLowerCase())
 return { label: other ? 'Abrir montagem' : 'Continuar montagem', route: { tab: 'montagem', experience: 'desenvolvimento' } }
}
export type LegacyView = 'cadastro' | 'lineage' | 'historico'
export type PipelineMenuEntry = { kind: 'route'; label: string; route: PipelineRoute } | { kind: 'legacy'; label: string; view: LegacyView }
export function pipelineMenu(item: PipelineIndexItem, actions: Actions): PipelineMenuEntry[] {
 const developing = actions.editDraft ? 'desenvolvimento' : 'consulta'
 const entries: PipelineMenuEntry[] = [{ kind: 'route', label: 'Visão geral', route: overviewRoute(actions) }]
 if (actions.consultStages) entries.push({ kind: 'route', label: 'Montagem', route: { tab: 'montagem', experience: developing } })
 if (item.hasPublished && actions.consultStages && actions.consultLogs) entries.push({ kind: 'route', label: 'Execução', route: { tab: 'execucao', experience: 'sustentacao' } })
 entries.push({ kind: 'route', label: 'Configuração', route: { tab: 'configuracao', experience: developing } })
 if (actions.consultVersions) entries.push({ kind: 'route', label: 'Versões', route: { tab: 'versoes', experience: developing } })
 // Consultas do cadastro anterior: só leitura, e só existe cadastro quando publicado.
 if (item.hasPublished) entries.push({ kind: 'legacy', label: 'Ver cadastro publicado', view: 'cadastro' }, { kind: 'legacy', label: 'Lineage', view: 'lineage' }, { kind: 'legacy', label: 'Histórico de alterações', view: 'historico' })
 return entries
}
// O cadastro anterior só filtra por LIKE; escolhe a grafia exata e, se não houver,
// a única igual sem distinção de maiúsculas (a mesma identidade do SQL legado).
export function legacyRecord<T extends { pipeline_name: string }>(rows: readonly T[], name: string): T | null {
 const exact = rows.find(row => row.pipeline_name === name)
 if (exact) return exact
 const folded = rows.filter(row => row.pipeline_name.toLowerCase() === name.toLowerCase())
 return folded.length === 1 ? folded[0] : null
}

// ── Erros ──────────────────────────────────────────────────────────────────
// 503 é dependência/esquema indisponível (o servidor nomeia a migration): oferece a lista anterior.
export function indexErrorMessage(error: { status?: number; message?: string } | null | undefined): { text: string; offerLegacy: boolean } {
 if (!error) return { text: '', offerLegacy: false }
 if (error.status === 403) return { text: 'Sua sessão não tem permissão para consultar esta lista.', offerLegacy: false }
 if (error.status === 422) return { text: error.message || 'Filtro inválido.', offerLegacy: false }
 return { text: error.message && error.status === 503 ? error.message : 'Não foi possível carregar os pipelines agora.', offerLegacy: true }
}

// ── Criação essencial ──────────────────────────────────────────────────────
// Mesmas regras do servidor: até 200 unidades UTF-16 e identificador aceito pelo
// motor (a validação de publicação recusa outros e o identificador não muda depois).
export const DESCRIPTION_MAX = 500 // largura de etl_pipeline.descricao
export interface CreateFieldErrors { name?: string; identifier?: string; description?: string }
export function createFieldErrors(fields: { name: string; identifier: string; description: string }): CreateFieldErrors {
 const errors: CreateFieldErrors = {}
 if (!fields.name.trim()) errors.name = 'Informe o nome do pipeline.'
 else if (fields.name.trim().length > 200) errors.name = 'Use no máximo 200 caracteres.'
 if (!fields.identifier) errors.identifier = 'Informe o identificador técnico.'
 else if (fields.identifier.length > 200) errors.identifier = 'Use no máximo 200 caracteres.'
 else if (!/^[A-Za-z0-9_.-]+$/.test(fields.identifier)) errors.identifier = 'Use letras sem acento, números, sublinhado (_), ponto ou hífen, sem espaços.'
 if (fields.description.length > DESCRIPTION_MAX) errors.description = `Use no máximo ${DESCRIPTION_MAX} caracteres.`
 return errors
}
// Conflito de identidade vira erro no campo, com o existente localizável na lista.
export function createConflict(error: { status?: number; code?: unknown } | null | undefined): string | null {
 if (error?.status !== 409) return null
 if (error.code === 'pipeline_exists') return 'Já existe um pipeline publicado com este identificador.'
 // O servidor usa draft_conflict para índice único e também para disputa concorrente.
 if (error.code === 'draft_conflict') return 'Há um rascunho com este identificador ou uma criação concorrente. Confira a lista antes de tentar de novo.'
 return null
}
