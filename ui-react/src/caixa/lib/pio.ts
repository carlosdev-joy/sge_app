// Ligação dos cards do Workflow com os dados REAIS do PIO.
//
// Fonte: `dbo.PIO_PROPOSTA_PENDENTE_AGG` (o número do card) e `_DET` (a lista),
// no próprio banco do Orquestra, recarregadas uma vez por dia às 07:30 pela
// `PRC_PIO_CARGA_PROPOSTA_PENDENTE`. A API expõe as duas em /pio/*.
//
// Hoje **só o primeiro card** lê daqui — ver `ORIGEM_PIO` abaixo. Os demais
// seguem no mock até a carga trazer as outras categorias; ligar cada um é
// acrescentar uma linha naquele mapa, e nada mais.
import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../../lib/api";
import type { PropostaWorkflow, StatusWorkflow } from "./workflow";

/** Card → categoria (STA_ASSINATURA) da carga. A ausência aqui é o que mantém
 *  um card no mock; a presença é o que o liga ao dado real. */
export const ORIGEM_PIO: Partial<Record<StatusWorkflow, string>> = {
  pending_signature: "PE",
  // Quando a carga trouxer as outras categorias:
  // awaiting_payment: "PP", paid: "AP", in_analysis: "AN",
  // emission_sent: "EM", declined: "RE",
};

export interface ContagemPio {
  categoria: string;
  descricao: string;
  quantidade: number;
  carga: string | null;
}

export interface ContagensPio {
  disponivel: boolean;
  referencia: string | null;
  categorias: ContagemPio[];
}

export interface ItemPio {
  proposta: string;
  nome: string;
  cpf: string;
  agencia: string;
  matricula: string;
  data_venda: string | null;
  dias_pendente: number;
  produto: string;
  area_produto: string;
  premio: number | null;
  imp_segurada: number | null;
  cidade: string;
  uf: string;
  telefone: string;
  email: string;
  idade: number | null;
  situacao: string;
  pago: string;
}

export interface PaginaPio {
  disponivel: boolean;
  categoria: string;
  referencia: string | null;
  total: number;
  limite: number;
  offset: number;
  itens: ItemPio[];
}

export const TAMANHO_PAGINA_PIO = 50;

/** Contagem por categoria da carga mais recente. */
export function useContagensPio() {
  return useQuery({
    queryKey: ["pio", "contagens"],
    queryFn: () => apiFetch<ContagensPio>("/pio/contagens"),
    // A carga é diária: reconsultar a cada foco de janela só gera tráfego.
    staleTime: 5 * 60 * 1000,
  });
}

/** Uma página da lista de propostas. `ativo` evita buscar 8.700 registros
 *  enquanto o card nem foi aberto. */
export function usePropostasPio(categoria: string | undefined, ativo: boolean,
                                pagina: number, busca: string) {
  return useQuery({
    queryKey: ["pio", "propostas", categoria, pagina, busca],
    enabled: Boolean(categoria) && ativo,
    staleTime: 5 * 60 * 1000,
    queryFn: () => {
      const p = new URLSearchParams({
        categoria: categoria as string,
        limite: String(TAMANHO_PAGINA_PIO),
        offset: String(pagina * TAMANHO_PAGINA_PIO),
      });
      if (busca.trim()) p.set("busca", busca.trim());
      return apiFetch<PaginaPio>(`/pio/propostas?${p.toString()}`);
    },
  });
}

const MOEDA = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

/** "2026-08-02" → "02/08/2026". Sem `new Date()`: a string vem em ISO e o
 *  construtor a interpretaria como UTC, o que joga a venda para o dia
 *  anterior em qualquer fuso a oeste de Greenwich — o nosso. */
export function dataBr(iso: string | null): string {
  if (!iso) return "";
  const [ano, mes, dia] = iso.split("-");
  return ano && mes && dia ? `${dia}/${mes}/${ano}` : iso;
}

/** Item da carga → o formato que a lista e o modal já sabem exibir.
 *
 *  Campos que o PIO não tem ficam VAZIOS, nunca inventados: string vazia some
 *  da tela, enquanto um valor plausível vira dado errado que ninguém
 *  desconfia. */
export function propostaDoPio(item: ItemPio, status: StatusWorkflow): PropostaWorkflow {
  return {
    id: `pio-${item.proposta}`,
    number: item.proposta,
    insuredName: item.nome,
    date: dataBr(item.data_venda),
    status,
    value: item.premio === null ? "" : MOEDA.format(item.premio),
    indicatorId: item.matricula,
    agency: item.agencia,
    cpf: item.cpf,
    product: item.produto,
    phone: item.telefone,
    email: item.email,
    region: [item.cidade, item.uf].filter(Boolean).join(" / "),
    ageRange: item.idade === null ? "" : `${item.idade} anos`,
    broker: item.matricula,
    daysInPending: item.dias_pendente,
  };
}
