// Card 1 (Pendentes de Assinatura) lendo a FOTO diária — RITM0117336.
//
// Fonte: `/pio/card1/resumo` (agregado: prêmio e quantidade do card) e
// `/pio/card1/propostas` (fato: lista, detalhe e contatos). Os outros sete cards
// seguem em `lib/pio.ts`; a lógica pura está em `card1Foto.ts` (reexportada aqui).
//
// ⚠️ A lista pede a MESMA foto do resumo (`data=referencia`): se uma publicação
// nova chegar entre as duas chamadas, número e lista não podem ser de dias
// diferentes. Sem a referência, a lista nem é pedida.
import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../../lib/api";
import { TAMANHO_PAGINA_PIO } from "./pio";
import type { PaginaCard1, ResumoCard1 } from "./card1Foto";

export * from "./card1Foto";

export function useResumoCard1() {
  return useQuery({
    queryKey: ["pio", "card1", "resumo"],
    queryFn: () => apiFetch<ResumoCard1>("/pio/card1/resumo"),
    // A carga é diária: reconsultar a cada foco de janela só gera tráfego.
    staleTime: 5 * 60 * 1000,
  });
}

export function usePropostasCard1(ativo: boolean, pagina: number, referencia: string | null | undefined) {
  return useQuery({
    queryKey: ["pio", "card1", "propostas", referencia, pagina],
    enabled: ativo && Boolean(referencia),
    staleTime: 5 * 60 * 1000,
    queryFn: () => {
      const p = new URLSearchParams({
        data: referencia as string,
        limite: String(TAMANHO_PAGINA_PIO),
        offset: String(pagina * TAMANHO_PAGINA_PIO),
      });
      return apiFetch<PaginaCard1>(`/pio/card1/propostas?${p.toString()}`);
    },
  });
}
