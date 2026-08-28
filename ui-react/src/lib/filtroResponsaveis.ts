// O filtro de responsáveis da aba de Indicadores — a parte que decide.
//
// Separada do componente porque é ONDE MORAM AS DECISÕES: o que a URL leva ao
// servidor e o que a tela afirma sobre o recorte em vigor. As duas coisas
// erram em silêncio — uma URL malformada devolve a fila inteira com cara de
// filtrada, e um resumo errado faz um print desta tela virar "a fila tem 16
// chamados" quando são 16 de uma pessoa.

/** O rótulo de quem não tem dono. Igual ao `SEM_RESPONSAVEL` da API. */
export const SEM_RESPONSAVEL = 'sem responsável'

/**
 * Marca ou desmarca um nome, preservando a ordem de escolha.
 *
 * A ordem importa para o resumo ("Ana e Bruno" na ordem em que foram
 * marcados); reordenar a cada clique faria o texto dançar sob o dedo de quem
 * está marcando o terceiro nome.
 */
export function alternar(escolhidos: string[], nome: string): string[] {
  return escolhidos.includes(nome)
    ? escolhidos.filter(n => n !== nome)
    : [...escolhidos, nome]
}

/**
 * A query string para `/chamados/indicadores`.
 *
 * Repete o parâmetro (`?responsavel=A&responsavel=B`) porque é assim que o
 * FastAPI monta uma lista. Juntar com vírgula produziria UM nome chamado
 * "A,B", que não casa com ninguém — e a resposta viria vazia parecendo "esta
 * pessoa não tem chamados".
 *
 * `encodeURIComponent` não é detalhe: nomes têm espaço e acento, e "sem
 * responsável" tem os dois.
 */
export function urlIndicadores(escolhidos: string[]): string {
  const nomes = escolhidos.map(n => (n || '').trim()).filter(Boolean)
  if (!nomes.length) return '/chamados/indicadores'
  const q = nomes.map(n => `responsavel=${encodeURIComponent(n)}`).join('&')
  return `/chamados/indicadores?${q}`
}

/** O texto do seletor fechado — quem está filtrado, sem precisar abrir. */
export function resumoDoFiltro(escolhidos: string[], totalGeral: number): string {
  const nomes = escolhidos.filter(Boolean)
  if (!nomes.length) return `todos (${totalGeral})`
  if (nomes.length === 1) return nomes[0]
  if (nomes.length === 2) return `${nomes[0]} e ${nomes[1]}`
  // A partir de três, o nome de cada um não cabe no gatilho e a contagem
  // informa mais: quem quer os nomes abre a lista e vê as marcas.
  return `${nomes.length} responsáveis`
}

/**
 * O aviso de que TODO número da aba está recortado.
 *
 * Devolve string vazia quando não há filtro — a ausência de aviso é a
 * afirmação de que os números são da fila inteira.
 */
export function avisoDoFiltro(escolhidos: string[]): string {
  const nomes = escolhidos.filter(Boolean)
  if (!nomes.length) return ''
  const quem = nomes.length === 1
    ? nomes[0]
    : `${nomes.slice(0, -1).join(', ')} e ${nomes[nomes.length - 1]}`
  return `todos os números abaixo são apenas de ${quem}`
}
