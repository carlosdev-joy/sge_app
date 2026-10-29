// Card 4 (Em Análise — críticas por certificado) lendo a FOTO diária.
//
// Mesmo contrato do Card 1 (tipos e lógica pura em `card1Foto.ts`); muda só a
// fonte: `/pio/card4/resumo` (agregado) e `/pio/card4/propostas` (fato).
// A lista pede a MESMA foto do resumo (`data=referencia`).
import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../../lib/api";
import { TAMANHO_PAGINA_PIO } from "./pio";
import type { PaginaCard1, PendenciasCard4, ResumoCard1 } from "./card1Foto";

export function useResumoCard4() {
  return useQuery({
    queryKey: ["pio", "card4", "resumo"],
    queryFn: () => apiFetch<ResumoCard1>("/pio/card4/resumo"),
    // A carga é diária: reconsultar a cada foco de janela só gera tráfego.
    staleTime: 5 * 60 * 1000,
  });
}

export function usePropostasCard4(ativo: boolean, pagina: number, referencia: string | null | undefined) {
  return useQuery({
    queryKey: ["pio", "card4", "propostas", referencia, pagina],
    enabled: ativo && Boolean(referencia),
    staleTime: 5 * 60 * 1000,
    queryFn: () => {
      const p = new URLSearchParams({
        data: referencia as string,
        limite: String(TAMANHO_PAGINA_PIO),
        offset: String(pagina * TAMANHO_PAGINA_PIO),
      });
      return apiFetch<PaginaCard1>(`/pio/card4/propostas?${p.toString()}`);
    },
  });
}

/** As mensagens de crítica de UM certificado, na foto da lista (`referencia`). */
export function usePendenciasCard4(certificado: string, referencia: string | null, ativo: boolean) {
  const numero = Number(certificado);
  return useQuery({
    queryKey: ["pio", "card4", "pendencias", certificado, referencia],
    enabled: ativo && Number.isInteger(numero) && numero > 0,
    staleTime: 5 * 60 * 1000,
    queryFn: () => {
      const p = new URLSearchParams({ certificado: String(numero) });
      if (referencia) p.set("data", referencia);
      return apiFetch<PendenciasCard4>(`/pio/card4/pendencias?${p.toString()}`);
    },
  });
}
