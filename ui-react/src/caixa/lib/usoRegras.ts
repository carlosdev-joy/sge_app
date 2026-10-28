// Regras PURAS do rastreio de uso (spec docs/spec-uso-busca-vendas.md §4): sem rede,
// sem React, para a bancada de testes (tests/test_uso_busca_vendas_front.py) importar.

export const JANELA_DEDUPE_MS = 30 * 60 * 1000;
export const INTERVALO_PRESENCA_MS = 4 * 60 * 1000;

/** Prefixo do módulo: só o que está sob ele é medido. */
export const PREFIXO_MODULO = "/caixa-seguro";

export const ehRotaDoModulo = (pathname: string) =>
  pathname === PREFIXO_MODULO || pathname.startsWith(`${PREFIXO_MODULO}/`);

/** Decide se o acesso deve ser enviado agora e, se sim, anota o instante.
 *  Pura em relação ao relógio: quem chama passa o `agora`. */
export function deveRegistrarAcesso(
  rota: string, agora: number, vistos: Map<string, number>,
  janelaMs: number = JANELA_DEDUPE_MS,
): boolean {
  const ultimo = vistos.get(rota);
  if (ultimo !== undefined && agora - ultimo < janelaMs) return false;
  vistos.set(rota, agora);
  return true;
}
