// Card 5 (Emitidas — VG + AP, um contrato por linha) lendo a FOTO diária.
//
// Mesmo contrato do Card 1 (tipos e lógica pura em `card1Foto.ts`); muda só a
// fonte: `/pio/card5/resumo` (agregado) e `/pio/card5/propostas` (fato).
// A lista pede a MESMA foto do resumo (`data=referencia`).
import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../../lib/api";
import { TAMANHO_PAGINA_PIO } from "./pio";
import type { PaginaCard1, ResumoCard1 } from "./card1Foto";

export function useResumoCard5() {
  return useQuery({
    queryKey: ["pio", "card5", "resumo"],
    queryFn: () => apiFetch<ResumoCard1>("/pio/card5/resumo"),
    // A carga é diária: reconsultar a cada foco de janela só gera tráfego.
    staleTime: 5 * 60 * 1000,
  });
}

export function usePropostasCard5(ativo: boolean, pagina: number, referencia: string | null | undefined) {
  return useQuery({
    queryKey: ["pio", "card5", "propostas", referencia, pagina],
    enabled: ativo && Boolean(referencia),
    staleTime: 5 * 60 * 1000,
    queryFn: () => {
      const p = new URLSearchParams({
        data: referencia as string,
        limite: String(TAMANHO_PAGINA_PIO),
        offset: String(pagina * TAMANHO_PAGINA_PIO),
      });
      return apiFetch<PaginaCard1>(`/pio/card5/propostas?${p.toString()}`);
    },
  });
}
