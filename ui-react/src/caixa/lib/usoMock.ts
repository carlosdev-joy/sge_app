// Dados SIMULADOS da tela "Uso do módulo" — só existe na F1 da spec
// docs/spec-uso-busca-vendas.md (front antes do backend). A F3 apaga este
// arquivo junto com `USO_USA_MOCK`. Determinístico: o mesmo (período, data)
// devolve sempre o mesmo resultado, para a tela poder ser revisada.
import type { UsoRanking, UsoResumo, UsoSerie, UsoTela } from "./uso";
import { deIso, type GranularidadeUso, type Periodo } from "./usoDatas";

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

const TELAS: Omit<UsoTela, "acessos" | "usuarios">[] = [
  { tela: "Consulta de Propostas", rota: "/caixa-seguro" },
  { tela: "Monitoramento Tático de Emissão", rota: "/caixa-seguro/acompanhamento" },
  { tela: "Acompanhamento por status", rota: "/caixa-seguro/acompanhamento/:status" },
  { tela: "Portabilidades", rota: "/caixa-seguro/portabilidades" },
  { tela: "Painel de IA Operacional", rota: "/caixa-seguro/ia-operacional" },
  { tela: "Uso do módulo", rota: "/caixa-seguro/uso" },
];

const PESSOAS: [string, string][] = [
  ["C000123", "Ana Beatriz Souza"],
  ["C000457", "Marcos Vinícius Lima"],
  ["C000789", "Patrícia Gomes"],
  ["C001012", "Rafael Duarte"],
  ["C001345", "Juliana Prado"],
  ["C001678", "Eduardo Nunes"],
  ["C001901", "Camila Ferraz"],
  ["C002234", "Thiago Mendes"],
];

/** Pseudo-aleatório estável a partir de um texto. */
function semente(texto: string): () => number {
  let h = 2166136261;
  for (let i = 0; i < texto.length; i++) h = Math.imul(h ^ texto.charCodeAt(i), 16777619);
  return () => {
    h = Math.imul(h ^ (h >>> 15), 2246822507);
    h = Math.imul(h ^ (h >>> 13), 3266489909);
    return ((h ^= h >>> 16) >>> 0) / 4294967296;
  };
}

function montarSerie(periodo: Periodo, referencia: string, rnd: () => number): { serie: UsoSerie[]; granularidade: GranularidadeUso } {
  const d = deIso(referencia);
  if (periodo === "dia") {
    const serie = Array.from({ length: 24 }, (_, h) => {
      const comercial = h >= 8 && h <= 18;
      const acessos = comercial ? Math.round(6 + rnd() * 22) : Math.round(rnd() * 2);
      return { rotulo: `${String(h).padStart(2, "0")}h`, acessos, usuarios: Math.min(acessos, Math.max(acessos ? 1 : 0, Math.round(acessos * 0.45))) };
    });
    return { serie, granularidade: "hora" };
  }
  if (periodo === "mes") {
    const dias = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
    const serie = Array.from({ length: dias }, (_, i) => {
      const util = new Date(d.getFullYear(), d.getMonth(), i + 1).getDay() % 6 !== 0;
      const acessos = util ? Math.round(60 + rnd() * 140) : Math.round(rnd() * 8);
      return { rotulo: String(i + 1).padStart(2, "0"), acessos, usuarios: Math.min(acessos, Math.round(acessos * 0.1) + (util ? 3 : 0)) };
    });
    return { serie, granularidade: "dia" };
  }
  const serie = MESES.map((m) => {
    const acessos = Math.round(1200 + rnd() * 1800);
    return { rotulo: m, acessos, usuarios: Math.round(18 + rnd() * 14) };
  });
  return { serie, granularidade: "mes" };
}

export function resumoUsoSimulado(periodo: Periodo, referencia: string): UsoResumo {
  const rnd = semente(`${periodo}:${referencia}`);
  const { serie, granularidade } = montarSerie(periodo, referencia, rnd);
  const acessos = serie.reduce((s, x) => s + x.acessos, 0);
  const usuarios = Math.min(PESSOAS.length * 4, Math.max(...serie.map((x) => x.usuarios), 1) + 2);

  // Peso decrescente: a consulta é a tela mais aberta.
  const pesos = [0.42, 0.24, 0.14, 0.1, 0.07, 0.03];
  const por_tela: UsoTela[] = TELAS.map((t, i) => ({
    ...t,
    acessos: Math.round(acessos * pesos[i]),
    usuarios: Math.max(1, Math.round(usuarios * (1 - i * 0.14))),
  }));

  const ranking: UsoRanking[] = PESSOAS.map(([matricula, nome], i) => {
    const a = Math.round((acessos / 4.2) * Math.pow(0.68, i));
    return {
      matricula,
      nome,
      acessos: a,
      dias_ativos: Math.max(1, Math.min(periodo === "dia" ? 1 : periodo === "mes" ? 22 : 180, Math.round(a / 6))),
      ultimo_acesso: `${referencia}T${String(8 + i).padStart(2, "0")}:${String(10 + i * 4).padStart(2, "0")}:00`,
      tela_top: TELAS[i % 3].tela,
    };
  }).filter((r) => r.acessos > 0);

  return {
    online_agora: 3,
    usuarios_online: ["Ana Beatriz Souza", "Marcos Vinícius Lima", "Patrícia Gomes"],
    primeiro_registro: "2026-10-29",
    periodo: { inicio: referencia, fim: referencia, granularidade },
    kpis: { usuarios, acessos, acessos_por_usuario: usuarios ? acessos / usuarios : 0 },
    serie,
    por_tela,
    ranking,
  };
}
