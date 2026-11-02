// Card 8 (Sensibilizações — último movimento de propostas Vida, VG + AP) lendo a FOTO diária.
//
// Mesmo contrato dos outros cards de foto (tipos e lógica pura em `card1Foto.ts`):
// `/pio/card8/resumo` (agregado) e `/pio/card8/propostas` (fato). A lista pede a MESMA foto do
// resumo (`data=referencia`). Sem filtros: a foto tem ~6,5 milhões de linhas e não traz o segurado.
import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../../lib/api";
import { TAMANHO_PAGINA_PIO } from "./pio";
import type { PaginaCard1, ResumoCard1 } from "./card1Foto";

export function useResumoCard8() {
  return useQuery({
    queryKey: ["pio", "card8", "resumo"],
    queryFn: () => apiFetch<ResumoCard1>("/pio/card8/resumo"),
    // A carga é diária: reconsultar a cada foco de janela só gera tráfego.
    staleTime: 5 * 60 * 1000,
  });
}

export function usePropostasCard8(ativo: boolean, pagina: number, referencia: string | null | undefined) {
  return useQuery({
    queryKey: ["pio", "card8", "propostas", referencia, pagina],
    enabled: ativo && Boolean(referencia),
    staleTime: 5 * 60 * 1000,
    queryFn: () => {
      const p = new URLSearchParams({
        data: referencia as string,
        limite: String(TAMANHO_PAGINA_PIO),
        offset: String(pagina * TAMANHO_PAGINA_PIO),
      });
      return apiFetch<PaginaCard1>(`/pio/card8/propostas?${p.toString()}`);
    },
  });
}
