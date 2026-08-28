// A aritmética das colunas arrastáveis.
//
// Separada do componente porque é ONDE MORAM AS DECISÕES — largura mínima,
// o que fazer com uma preferência salva que não corresponde mais às colunas —
// e decisão em função pura é decisão que o teste alcança sem renderizar nada.

/** Menor largura que uma coluna pode ter, em pixels. */
export const LARGURA_MINIMA = 48

/**
 * A largura depois de arrastar `delta` pixels.
 *
 * O piso não é enfeite: sem ele, um arrasto rápido para a esquerda leva a
 * coluna a zero (ou a negativo, que o navegador trata como zero) e o conteúdo
 * fica INALCANÇÁVEL — não há alça para trazer de volta o que não tem largura.
 */
export function novaLargura(atual: number, delta: number, minima?: number): number {
  return Math.max(minima ?? LARGURA_MINIMA, Math.round(atual + delta))
}

export interface ColunaSalvavel {
  chave: string
  largura: number
  minima?: number
}

/**
 * Junta as larguras salvas com as colunas de hoje.
 *
 * Salvo e atual PODEM divergir: uma versão nova acrescenta, remove ou renomeia
 * coluna, e o `localStorage` do usuário continua com o mapa antigo. Por isso a
 * junção é por CHAVE e a lista de colunas manda:
 *
 *   - chave que sumiu do código é ignorada (não vira coluna fantasma);
 *   - chave nova ganha a largura padrão (não vira coluna de largura zero);
 *   - valor inválido — texto, `NaN`, negativo — cai no padrão, porque
 *     `localStorage` é editável pelo usuário e um `NaN` viraria coluna sumida.
 */
export function larguraDasColunas(
  colunas: ColunaSalvavel[], salvas: unknown,
): Record<string, number> {
  const mapa = (salvas && typeof salvas === 'object')
    ? salvas as Record<string, unknown> : {}
  const saida: Record<string, number> = {}
  for (const c of colunas) {
    const bruto = mapa[c.chave]
    const n = typeof bruto === 'number' ? bruto : Number(bruto)
    saida[c.chave] = Number.isFinite(n) && n > 0
      ? Math.max(c.minima ?? LARGURA_MINIMA, Math.round(n))
      : c.largura
  }
  return saida
}

export interface Fatia {
  /** A página realmente mostrada, já corrigida. */
  pagina: number
  paginas: number
  /** Posição do primeiro e do último item, 1-based, para dizer na tela. */
  primeiro: number
  ultimo: number
  inicio: number
  fim: number
}

/**
 * Qual pedaço da lista aparece.
 *
 * ⚠️ A página pedida é CORRIGIDA em vez de obedecida. Ela vive em estado, e a
 * lista debaixo dela muda por fora — o usuário filtra, o bloco do painel troca,
 * a consulta volta com menos linhas. Uma página 5 sobre uma lista que encolheu
 * para 12 itens renderiza uma tabela VAZIA, que é indistinguível de "não há
 * nada aqui" — e o usuário conclui a segunda.
 */
export function fatiar(total: number, pagina: number, porPagina: number): Fatia {
  const tamanho = Math.max(1, Math.floor(porPagina) || 1)
  const paginas = Math.max(1, Math.ceil(total / tamanho))
  const atual = Math.min(Math.max(0, Math.floor(pagina) || 0), paginas - 1)
  const inicio = atual * tamanho
  const fim = Math.min(total, inicio + tamanho)
  return {
    pagina: atual, paginas, inicio, fim,
    // Lista vazia não tem "item 1 de 0": o primeiro vira 0 e a tela não
    // afirma uma posição que não existe.
    primeiro: total ? inicio + 1 : 0,
    ultimo: fim,
  }
}

const PREFIXO = 'orquestra.tabela.'

/**
 * Lê a preferência do usuário.
 *
 * Todo acesso a `localStorage` é embrulhado: em janela anônima, com cookies de
 * terceiros bloqueados ou com armazenamento desabilitado, o próprio ACESSO
 * lança — e uma tabela que não abre por causa de uma preferência de largura
 * seria um preço absurdo. Falhou, usa o padrão.
 */
export function lerLarguras(id: string): unknown {
  try {
    const cru = globalThis.localStorage?.getItem(PREFIXO + id)
    return cru ? JSON.parse(cru) : null
  } catch {
    return null
  }
}

/** Grava a preferência. Falha em silêncio — de propósito: ver `lerLarguras`. */
export function salvarLarguras(id: string, larguras: Record<string, number>): void {
  try {
    globalThis.localStorage?.setItem(PREFIXO + id, JSON.stringify(larguras))
  } catch {
    /* preferência é conforto, não função: perder o ajuste não quebra a tela */
  }
}
