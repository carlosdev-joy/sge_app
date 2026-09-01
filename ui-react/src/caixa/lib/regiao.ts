// A região do país a partir da UF — módulo PURO de propósito: sem import
// nenhum, ele compila e roda sozinho, e é assim que `tests/test_pio_regiao.py`
// consegue exercitar as 27 siglas de verdade num repo cujo front não tem
// test runner.
/** UF → região do IBGE. As 27 unidades federativas, sem exceção: uma UF que
 *  faltasse aqui cairia no fallback e apareceria como sigla solta no meio de
 *  nomes por extenso. */
const REGIAO_POR_UF: Record<string, string> = {
  AC: "Norte", AP: "Norte", AM: "Norte", PA: "Norte",
  RO: "Norte", RR: "Norte", TO: "Norte",

  AL: "Nordeste", BA: "Nordeste", CE: "Nordeste", MA: "Nordeste",
  PB: "Nordeste", PE: "Nordeste", PI: "Nordeste", RN: "Nordeste",
  SE: "Nordeste",

  DF: "Centro-Oeste", GO: "Centro-Oeste", MT: "Centro-Oeste", MS: "Centro-Oeste",

  ES: "Sudeste", MG: "Sudeste", RJ: "Sudeste", SP: "Sudeste",

  PR: "Sul", RS: "Sul", SC: "Sul",
};

/** "PR" → "Sul". O card mostra a REGIÃO, como sempre mostrou antes de a carga
 *  entrar (o mock já trazia "Sul", "Sudeste"…) — cidade e UF viraram
 *  "Curitiba / PR" ali por um descuido da ligação do PIO.
 *
 *  UF vazia devolve vazio: campo sem dado some da tela, e é isso que se quer.
 *  UF que não existe devolve **a própria sigla**, não vazio nem um palpite —
 *  se a carga trouxer lixo em `NOM_UF`, é melhor que ele apareça na tela do
 *  que sumir fingindo que o endereço não veio. */
export function regiaoDaUf(uf: string | null | undefined): string {
  const sigla = (uf || "").trim().toUpperCase();
  if (!sigla) return "";
  return REGIAO_POR_UF[sigla] ?? sigla;
}
