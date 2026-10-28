// Uso do módulo Busca & Vendas (spec docs/spec-uso-busca-vendas.md).
//
// Contrato de `GET /caixa/uso/resumo` e os hooks de leitura. Os helpers de data
// e de formatação ficam em `usoDatas.ts`.
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../../lib/api";

import type { GranularidadeUso, Periodo } from "./usoDatas";
export type { GranularidadeUso, Periodo } from "./usoDatas";

export interface UsoKpis {
  usuarios: number;
  acessos: number;
  acessos_por_usuario: number;
}

export interface UsoSerie {
  rotulo: string;
  acessos: number;
  usuarios: number;
}

export interface UsoTela {
  tela: string;
  rota: string;
  acessos: number;
  usuarios: number;
}

export interface UsoRanking {
  matricula: string;
  nome: string;
  acessos: number;
  dias_ativos: number;
  ultimo_acesso: string | null;
  tela_top: string;
}

export interface UsoResumo {
  /** Quem teve presença nos últimos 10 min — independe do período escolhido. */
  online_agora: number;
  usuarios_online: string[];
  /** Data do primeiro evento já registrado (a medição começa na publicação). */
  primeiro_registro: string | null;
  periodo: { inicio: string; fim: string; granularidade: GranularidadeUso };
  kpis: UsoKpis;
  serie: UsoSerie[];
  por_tela: UsoTela[];
  ranking: UsoRanking[];
}

/** Janela de "online agora", em minutos — a mesma do servidor. */
export const JANELA_ONLINE_MIN = 10;

// ── Leitura ────────────────────────────────────────────────────────────────

export function buscarResumoUso(periodo: Periodo, referencia: string): Promise<UsoResumo> {
  const p = new URLSearchParams({ periodo, referencia });
  return apiFetch<UsoResumo>(`/caixa/uso/resumo?${p.toString()}`);
}

export function useUsoResumo(periodo: Periodo, referencia: string) {
  return useQuery({
    queryKey: ["caixa", "uso", "resumo", periodo, referencia],
    queryFn: () => buscarResumoUso(periodo, referencia),
    // "Online agora" muda sozinho: reconsulta a cada minuto com a aba visível.
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}
