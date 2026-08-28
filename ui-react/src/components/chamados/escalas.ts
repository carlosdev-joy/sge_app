// A régua de cor e o formato dos números das abas de Chamados.
//
// Separado de `graficos.tsx` porque o Fast Refresh só funciona quando um
// arquivo exporta apenas componentes — e porque estas duas coisas são de
// natureza diferente: aqui é a REGRA (o que a cor significa, como o número se
// escreve), ali é o desenho.
//
// A paleta é a validada: azul #2a78d6 / laranja #eb6834 (claro) e #3987e5 /
// #d95926 (escuro). O par passou os seis testes nos dois modos — banda de
// luminosidade, piso de croma, separação sob daltonismo (ΔE 24.7 protan claro,
// 26.8 escuro), piso de visão normal e contraste com a superfície.

export const RAMPA = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#2a78d6', '#1c5cab']

// Séries categóricas do fluxo. Slots 1 e 2 da paleta validada.
export const SERIE_ENTRADAS = '#2a78d6'
export const SERIE_SAIDAS = '#eb6834'

export function passoRampa(valor: number, maximo: number): string {
  if (maximo <= 0 || valor <= 0) return RAMPA[0]
  const i = Math.min(RAMPA.length - 1,
    Math.max(1, Math.round((valor / maximo) * (RAMPA.length - 1))))
  return RAMPA[i]
}

// "3 de 12 (25%)" — a regra da casa: percentagem nunca sozinha.
export function xDeY(parte: number, total: number): string {
  if (!total) return `${parte}`
  return `${parte} de ${total} (${Math.round((parte / total) * 100)}%)`
}
