// Datas e formatação da tela "Uso do módulo" (spec docs/spec-uso-busca-vendas.md).
// Funções puras, sem React nem rede — a bancada em tests/js e o mock importam daqui.
// Datas trafegam como texto `AAAA-MM-DD` e são montadas SEM fuso (new Date(a, m, d)
// no horário local): `new Date("2026-10-28")` é UTC e, no Brasil, vira 27/10.
export type Periodo = "dia" | "mes" | "ano";
export type GranularidadeUso = "hora" | "dia" | "mes";

const doisDigitos = (n: number) => String(n).padStart(2, "0");

export function paraIso(d: Date): string {
  return `${d.getFullYear()}-${doisDigitos(d.getMonth() + 1)}-${doisDigitos(d.getDate())}`;
}

export function deIso(iso: string): Date {
  const [a, m, d] = iso.split("-").map(Number);
  return new Date(a, (m || 1) - 1, d || 1);
}

export function hojeIso(): string {
  return paraIso(new Date());
}

/** Anda um período para trás (-1) ou para a frente (+1) a partir da referência. */
export function deslocarReferencia(periodo: Periodo, referencia: string, passo: -1 | 1): string {
  const d = deIso(referencia);
  if (periodo === "dia") d.setDate(d.getDate() + passo);
  // Dia 1 antes de somar mês: 31/10 + 1 mês viraria 01/12 (30/11 não existe).
  else if (periodo === "mes") { d.setDate(1); d.setMonth(d.getMonth() + passo); }
  else { d.setDate(1); d.setMonth(0); d.setFullYear(d.getFullYear() + passo); }
  return paraIso(d);
}

/** O período da referência é o corrente (hoje cai dentro dele)? */
export function ehPeriodoAtual(periodo: Periodo, referencia: string, hoje: string = hojeIso()): boolean {
  const r = deIso(referencia);
  const h = deIso(hoje);
  if (periodo === "dia") return paraIso(r) === paraIso(h);
  if (periodo === "mes") return r.getFullYear() === h.getFullYear() && r.getMonth() === h.getMonth();
  return r.getFullYear() === h.getFullYear();
}

/** Não deixa a referência ir além de hoje. */
export function limitarAHoje(referencia: string, hoje: string = hojeIso()): string {
  return referencia > hoje ? hoje : referencia;
}

export function rotuloPeriodo(periodo: Periodo, referencia: string): string {
  const d = deIso(referencia);
  if (periodo === "dia") return d.toLocaleDateString("pt-BR");
  if (periodo === "ano") return String(d.getFullYear());
  const mes = d.toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
  // Só a 1ª letra: `capitalize` do CSS poria maiúscula também no "de".
  return mes.charAt(0).toUpperCase() + mes.slice(1);
}

export const NOME_GRANULARIDADE: Record<GranularidadeUso, string> = {
  hora: "por hora",
  dia: "por dia",
  mes: "por mês",
};

/** Quantidade com milhar em pt-BR. */
export const numero = (n: number) => n.toLocaleString("pt-BR");

/** Média com uma casa, em pt-BR. */
export const media = (n: number) =>
  n.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

/** `2026-10-28T14:05:00` → `28/10/2026 14:05`. Texto ilegível volta como veio. */
export function dataHoraBr(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.toLocaleDateString("pt-BR")} ${d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
}

/** `2026-10-28` (ou com hora) → `28/10/2026`, sem passar por fuso. */
export function dataBrDeIso(iso: string | null): string {
  if (!iso) return "—";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return a && m && d ? `${d}/${m}/${a}` : iso;
}
