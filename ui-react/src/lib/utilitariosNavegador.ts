// Lógica PURA do navegador de pastas (spec docs/spec-utilitarios-arquivos.md,
// F6): o contrato de `GET /utilitarios/pasta/listar`, o que pode ser aberto, o
// caminho das migalhas e o texto de cada entrada. Sem React, sem rede.
import { formatarTamanho } from './utilitariosArquivo'

export type TipoEntrada = 'raiz' | 'pasta' | 'arquivo' | 'link' | 'outro'

export interface EntradaPasta {
  nome: string
  tipo: TipoEntrada
  tamanho_bytes: number | null
  modificado_em: string | null
  /** Só em links: 'pasta' | 'arquivo' quando o alvo está dentro das raízes; null = fora ou quebrado. */
  alvo?: 'pasta' | 'arquivo' | null
}

export interface Listagem {
  /** null no nível zero (a lista das raízes). */
  caminho_real: string | null
  raiz: string | null
  pai: string | null
  entradas: EntradaPasta[]
  ocultos_omitidos: number
  truncado: boolean
  duracao_ms?: number
}

/** Dá para entrar? Raiz, pasta, ou link cujo alvo é pasta dentro das raízes. */
export function podeDescer(e: EntradaPasta): boolean {
  return e.tipo === 'raiz' || e.tipo === 'pasta' || (e.tipo === 'link' && e.alvo === 'pasta')
}

/** É um arquivo que dá para escolher? Arquivo, ou link cujo alvo é arquivo dentro das raízes. */
export function ehArquivo(e: EntradaPasta): boolean {
  return e.tipo === 'arquivo' || (e.tipo === 'link' && e.alvo === 'arquivo')
}

/** Caminho da entrada a partir da pasta atual (no nível zero, o nome já é a raiz). */
export function caminhoDaEntrada(atual: string | null, e: EntradaPasta): string {
  if (e.tipo === 'raiz' || atual === null) return e.nome
  return `${atual.replace(/\/+$/, '')}/${e.nome}`
}

/** Migalhas da raiz até a pasta atual: [{rotulo, caminho}], a raiz por inteiro
 *  e cada nível abaixo pelo nome. Nível zero → []. */
export function migalhas(caminhoReal: string | null, raiz: string | null): { rotulo: string; caminho: string }[] {
  if (!caminhoReal || !raiz) return []
  const saida = [{ rotulo: raiz, caminho: raiz }]
  if (caminhoReal === raiz) return saida
  if (!caminhoReal.startsWith(raiz + '/')) return [{ rotulo: caminhoReal, caminho: caminhoReal }]
  let acumulado = raiz
  for (const parte of caminhoReal.slice(raiz.length + 1).split('/')) {
    if (!parte) continue
    acumulado = `${acumulado}/${parte}`
    saida.push({ rotulo: parte, caminho: acumulado })
  }
  return saida
}

/** O que a linha diz do tipo: "pasta", "arquivo · 1,5 KB", "link → pasta", "link (fora ou quebrado)". */
export function descricaoEntrada(e: EntradaPasta): string {
  switch (e.tipo) {
    case 'raiz': return 'raiz liberada'
    case 'pasta': return 'pasta'
    case 'arquivo': return e.tamanho_bytes != null ? `arquivo · ${formatarTamanho(e.tamanho_bytes)}` : 'arquivo'
    case 'link':
      if (e.alvo === 'pasta') return 'link → pasta'
      if (e.alvo === 'arquivo') return e.tamanho_bytes != null ? `link → arquivo · ${formatarTamanho(e.tamanho_bytes)}` : 'link → arquivo'
      return 'link (fora dos diretórios liberados ou quebrado)'
    default: return 'outro'
  }
}

/** Erro do `apiFetch` na listagem → frase (o `detail` da API já vem em pt-BR). */
export function erroListagem(e: unknown): string {
  const err = e as { status?: number; detail?: unknown; message?: string } | null
  const detail = err?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (err?.status === 401) return 'Sua sessão expirou — entre de novo.'
  if (err?.status === 403) return 'Sem permissão para abrir esta pasta.'
  if (err?.status === 404) return 'Pasta não encontrada.'
  return 'Não foi possível listar a pasta.'
}
