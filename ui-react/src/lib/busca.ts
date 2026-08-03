// Normaliza p/ busca acento-insensível (case + diacríticos simples).
// Nasceu na paleta do FluxoEditor e virou util quando a lista de malhas
// passou a filtrar por nome/descrição: duas implementações divergiriam e
// "fechamento" deixaria de achar "Fechamento Diário" numa das telas.
export function normalizeBusca(s: string): string {
  return s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
}
