import { apiFetch } from '../../lib/api'

export const PROJETOS = ['BI_CVP', 'BI_VIDA', 'BI_PREVIDENCIA', 'BI_PRESTAMISTA']

export const adminPost = <T,>(action: string, extra: Record<string, unknown> = {}) =>
  apiFetch<T>('/admin', { method: 'POST', body: JSON.stringify({ action, ...extra }) })
