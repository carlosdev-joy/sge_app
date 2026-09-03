// Lógica PURA do navegador de pastas (spec docs/spec-utilitarios-arquivos.md,
// F6): o contrato de `GET /utilitarios/pasta/listar`, o que pode ser aberto, o
// caminho das migalhas e o texto de cada entrada. Sem React, sem rede.
import { formatarTamanho, raizDe } from './utilitariosArquivo'

export type TipoEntrada = 'raiz' | 'pasta' | 'arquivo' | 'link' | 'outro'

export interface EntradaPasta {
  nome: string
  tipo: TipoEntrada
  tamanho_bytes: number | null
  modificado_em: string | null
  /** Só em links: 'pasta' | 'arquivo' quando o alvo está dentro das raízes;
   *  'desconhecido' quando o servidor não chegou a resolver (acima do teto de
   *  links por listagem) — o clique tenta; null = fora ou quebrado. */
  alvo?: 'pasta' | 'arquivo' | 'desconhecido' | null
}

export interface Listagem {
  /** Caminho LEXICAL pedido (normalizado) — é por ele que se navega e se preenche
   *  o formulário, porque o `ler`/`gravar` conferem lexicalmente. null no nível zero. */
  caminho: string | null
  /** O que o servidor diz que o caminho é (raiz-symlink resolvida); informativo. */
  caminho_real: string | null
  raiz: string | null
  pai: string | null
  entradas: EntradaPasta[]
  ocultos_omitidos: number
  truncado: boolean
  links_nao_resolvidos?: number
  duracao_ms?: number
}

/** Dá para entrar? Raiz, pasta, ou link cujo alvo é pasta dentro das raízes. */
export function podeDescer(e: EntradaPasta): boolean {
  return e.tipo === 'raiz' || e.tipo === 'pasta' || (e.tipo === 'link' && e.alvo === 'pasta')
}

/** Link que o servidor não verificou: o clique tenta listar (o servidor decide). */
export function podeTentar(e: EntradaPasta): boolean {
  return e.tipo === 'link' && e.alvo === 'desconhecido'
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
      if (e.alvo === 'desconhecido') return 'link (não verificado — clique para tentar)'
      return 'link (fora dos diretórios liberados ou quebrado)'
    default: return 'outro'
  }
}

/** Onde o navegador abre: na pasta digitada, se ela está abaixo de uma raiz
 *  (lexicalmente); senão, com uma raiz só, direto nela; com várias, na lista
 *  das raízes (null). */
export function inicioNavegacao(diretorio: string, raizes: string[]): string | null {
  // Só barras vira '' e cai fora — raiz nunca é `/`, então nada se perde.
  const d = diretorio.trim().replace(/\/+$/, '')
  if (d.startsWith('/') && raizDe(d, raizes)) return d
  if (raizes.length === 1) return raizes[0].trim().replace(/\/+$/, '')
  return null
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
