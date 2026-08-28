// Copiar um texto para a área de transferência, com as saídas que o navegador
// realmente dá.
//
// ⚠️ `navigator.clipboard` NÃO está sempre disponível, e este é o caso onde
// isso morde: ele exige contexto seguro (HTTPS ou localhost) e pode ser negado
// por permissão. O Orquestra roda atrás do proxy da Caixa e é alcançado por
// mais de um nome — supor a API presente é supor uma configuração de rede.
//
// Por isso a função devolve QUAL das saídas aconteceu, em vez de um booleano:
// a tela precisa dizer coisas diferentes para "copiei" e para "não consegui
// copiar, o número está selecionado — use Ctrl+C". Botão de copiar que falha em
// silêncio é pior que a ausência dele: o usuário cola o que estava antes na
// área de transferência e manda para outra pessoa.

export type ResultadoCopia = 'copiado' | 'selecionado' | 'falhou'

export interface AmbienteCopia {
  /** `navigator.clipboard.writeText`, quando existe. */
  escrever?: (texto: string) => Promise<void>
  /** O caminho legado (`document.execCommand`), que funciona sem HTTPS. */
  legado?: (texto: string) => boolean
}

/** O caminho legado padrão: textarea fora da vista, seleciona, copia, remove. */
function legadoPadrao(texto: string): boolean {
  const doc = globalThis.document
  if (!doc?.body) return false
  const area = doc.createElement('textarea')
  area.value = texto
  // `readOnly` evita o teclado virtual saltar no toque; a posição fixa e a
  // opacidade zero evitam o salto de rolagem que um elemento fora da tela causa.
  area.readOnly = true
  area.style.cssText = 'position:fixed;top:0;left:0;opacity:0;pointer-events:none'
  doc.body.appendChild(area)
  try {
    area.select()
    return doc.execCommand('copy')
  } catch {
    return false
  } finally {
    area.remove()
  }
}

export async function copiarTexto(
  texto: string, amb: AmbienteCopia = {},
): Promise<ResultadoCopia> {
  const valor = (texto || '').trim()
  if (!valor) return 'falhou'

  const escrever = amb.escrever
    ?? globalThis.navigator?.clipboard?.writeText.bind(globalThis.navigator.clipboard)
  if (escrever) {
    try {
      await escrever(valor)
      return 'copiado'
    } catch {
      // Cai para o legado: a recusa aqui costuma ser de permissão ou de
      // contexto inseguro, e o `execCommand` passa nos dois casos.
    }
  }

  const legado = amb.legado ?? legadoPadrao
  return legado(valor) ? 'copiado' : 'selecionado'
}

/** O que o botão diz depois de cada saída. */
export const AVISO_COPIA: Record<ResultadoCopia, string> = {
  copiado: 'copiado',
  // "selecionado" não é sucesso disfarçado: ele PEDE uma ação ao usuário.
  selecionado: 'use Ctrl+C',
  falhou: 'não copiou',
}
