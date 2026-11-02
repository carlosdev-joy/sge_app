// Card 7 (Devolução de Prêmio — VG + AP) lendo a FOTO diária.
//
// Mesmo contrato dos outros cards de foto (tipos e lógica pura em `card1Foto.ts`), com duas
// diferenças: o resumo traz o total e os 3 sub-cards (`por_situacao`), e a lista é de UM
// sub-card (`situacao`). Os dados bancários só saem em `/pio/card7/devolucao`, aberto no
// Resumo de um contrato — nunca na lista. A lista pede a MESMA foto do resumo.
import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../../lib/api";
import { TAMANHO_PAGINA_PIO } from "./pio";
import type { PaginaCard1, RespostaDevolucao, ResumoCard1 } from "./card1Foto";
import type { SituacaoDevolucao } from "./workflow";

export function useResumoCard7() {
  return useQuery({
    queryKey: ["pio", "card7", "resumo"],
    queryFn: () => apiFetch<ResumoCard1>("/pio/card7/resumo"),
    // A carga é diária: reconsultar a cada foco de janela só gera tráfego.
    staleTime: 5 * 60 * 1000,
  });
}

/** Sem sub-card escolhido (`situacao` nulo) NÃO há lista a pedir. */
export function usePropostasCard7(
  ativo: boolean, pagina: number, referencia: string | null | undefined, situacao: SituacaoDevolucao | null,
) {
  return useQuery({
    queryKey: ["pio", "card7", "propostas", referencia, situacao, pagina],
    enabled: ativo && Boolean(referencia) && situacao !== null,
    staleTime: 5 * 60 * 1000,
    queryFn: () => {
      const p = new URLSearchParams({
        situacao: situacao as string,
        data: referencia as string,
        limite: String(TAMANHO_PAGINA_PIO),
        offset: String(pagina * TAMANHO_PAGINA_PIO),
      });
      return apiFetch<PaginaCard1>(`/pio/card7/propostas?${p.toString()}`);
    },
  });
}

/** Dados da devolução e bancários de UM contrato, na foto da lista (`referencia`). */
export function useDevolucaoCard7(segmento: string, numero: string, referencia: string | null, ativo: boolean) {
  const n = Number(numero);
  return useQuery({
    queryKey: ["pio", "card7", "devolucao", segmento, numero, referencia],
    enabled: ativo && (segmento === "VG" || segmento === "AP") && Number.isInteger(n) && n > 0,
    staleTime: 5 * 60 * 1000,
    queryFn: () => {
      const p = new URLSearchParams({ segmento, numero: String(n) });
      if (referencia) p.set("data", referencia);
      return apiFetch<RespostaDevolucao>(`/pio/card7/devolucao?${p.toString()}`);
    },
  });
}
