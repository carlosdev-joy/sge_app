// Ligação dos cards do Workflow com os dados REAIS do PIO.
//
// Fonte: `dbo.PIO_AGG` (o número de cada card) e uma tabela de detalhe POR CARD
// (a lista), no próprio banco do Orquestra, recarregadas uma vez por dia às
// 07:30 pela `PRC_PIO_CARGA_DIARIA`. A API expõe as duas em /pio/*.
//
// A carga entrega DOIS cards hoje — ver `ORIGEM_PIO` abaixo. Os demais seguem no
// mock até ela trazer mais; ligar cada um é acrescentar uma linha naquele mapa,
// e nada mais.
import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../../lib/api";
import type { PropostaWorkflow, StatusWorkflow } from "./workflow";
import { regiaoDaUf } from "./regiao";

/** Card do Workflow → COD_CARD da carga. A ausência aqui é o que mantém um card
 *  no mock; a presença é o que o liga ao dado real.
 *
 *  ⚠️ O COD_CARD escolhe a TABELA de detalhe do lado da API (PEND_ASSIN →
 *  PIO_PROPOSTA_PENDENTE_DET, PEND_PGTO → PIO_PROPOSTA_PEND_PGTO_DET). Card novo
 *  aqui exige o COD_CARD correspondente no dicionário `CARDS` de
 *  `api/routers/pio.py` — sem isso a API responde vazio, não erro. */
export const ORIGEM_PIO: Partial<Record<StatusWorkflow, string>> = {
  // Cards 1–3 — fonte TDDB48, últimos 30 dias de venda.
  pending_signature: "PEND_ASSIN",
  awaiting_payment: "PEND_PGTO",
  paid: "ASSINA_PAGA",
  // Cards 4–8 — fonte DMDB05, ano corrente (o 7 é de 30 dias). Colunas com
  // nomes diferentes; quem traduz é o esquema em `api/routers/pio.py`.
  in_analysis: "CRITICA",
  emission_sent: "EMITIDA",
  declined: "REJEITADA",
  refund_scheduled: "DEVOL_PREMIO",
  sensitization_monitoring: "SENSIBILIZACAO",
};

export interface ContagemPio {
  card: string;
  descricao: string;
  quantidade: number;
  carga: string | null;
}

export interface ContagensPio {
  disponivel: boolean;
  referencia: string | null;
  cards: ContagemPio[];
}

export interface ItemPio {
  /** COD_CARD de onde a linha veio. Numa busca em todos os cards, é o que diz
   *  em que estado a proposta está. */
  card?: string;
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
  renda: number | null;
  cidade: string;
  uf: string;
  telefone: string;
  email: string;
  idade: number | null;
  situacao: string;
  pago: string;
}

/** Card do Workflow de cada COD_CARD — o inverso de `ORIGEM_PIO`, derivado
 *  dele para não virar uma segunda lista à mão que diverge da primeira.
 *  A busca em todos os cards precisa disto: a proposta vem da carga sabendo só
 *  de qual card saiu, e é o card que diz o status na tela. */
export const STATUS_POR_CARD: Record<string, StatusWorkflow> = Object.fromEntries(
  Object.entries(ORIGEM_PIO).map(([status, card]) => [card, status as StatusWorkflow]),
);

export interface PaginaPio {
  disponivel: boolean;
  card: string;
  referencia: string | null;
  total: number;
  limite: number;
  offset: number;
  itens: ItemPio[];
}

export const TAMANHO_PAGINA_PIO = 50;

/** `card → quantidade`, SOMANDO linhas repetidas do mesmo card.
 *
 *  ⚠️ Um `new Map(cards.map(...))` sobrescreve a chave repetida e fica com a
 *  ÚLTIMA — foi assim que o card "Emitidas" mostrou 11.824 de 771.774 em
 *  2026-09-01: a carga grava a `PIO_AGG` por SITUAÇÃO dentro do card, e a
 *  EMITIDA veio em quatro linhas. Nenhum erro, um número plausível, e nada na
 *  tela para desconfiar.
 *
 *  A API já soma; isto aqui é a segunda tranca, porque o modo de falhar é
 *  silencioso e o custo de somar de novo é zero. */
export function contagemPorCard(cards: ContagemPio[]): Map<string, number> {
  const mapa = new Map<string, number>();
  for (const c of cards) {
    mapa.set(c.card, (mapa.get(c.card) ?? 0) + c.quantidade);
  }
  return mapa;
}

/** Contagem por card da carga mais recente. */
export function useContagensPio() {
  return useQuery({
    queryKey: ["pio", "contagens"],
    queryFn: () => apiFetch<ContagensPio>("/pio/contagens"),
    // A carga é diária: reconsultar a cada foco de janela só gera tráfego.
    staleTime: 5 * 60 * 1000,
  });
}

/** Uma página da lista de propostas. `ativo` evita buscar milhares de registros
 *  enquanto o card nem foi aberto. */
export function usePropostasPio(card: string | undefined, ativo: boolean,
                                pagina: number, busca: string) {
  return useQuery({
    queryKey: ["pio", "propostas", card, pagina, busca],
    enabled: Boolean(card) && ativo,
    staleTime: 5 * 60 * 1000,
    queryFn: () => {
      const p = new URLSearchParams({
        card: card as string,
        limite: String(TAMANHO_PAGINA_PIO),
        offset: String(pagina * TAMANHO_PAGINA_PIO),
      });
      if (busca.trim()) p.set("busca", busca.trim());
      return apiFetch<PaginaPio>(`/pio/propostas?${p.toString()}`);
    },
  });
}

/** Modos da Consulta de Propostas → o campo que a API compara.
 *
 *  ⚠️ SEV e SR caem os DOIS em `matricula`: a carga tem uma coluna só
 *  (`NUM_MATRICULA`) e não distingue um do outro. Os dois modos devolvem o
 *  mesmo resultado, e isso é sabido — decisão do usuário em 2026-09-01. */
export const MODO_BUSCA_PIO: Record<string, string> = {
  proposta: "proposta",
  cpf: "cpf",
  agencia: "agencia",
  sev: "matricula",
  sr: "matricula",
};

/** Busca em TODOS os cards da carga. Diferente de `usePropostasPio`, que lista
 *  um card: aqui quem procura tem o número na mão e não sabe (nem precisa
 *  saber) em que estado a proposta está. */
export function useBuscaPio(modo: string, termo: string, ativo: boolean) {
  const campo = MODO_BUSCA_PIO[modo] ?? "livre";
  return useQuery({
    queryKey: ["pio", "busca", campo, termo],
    enabled: ativo && Boolean(termo.trim()),
    staleTime: 5 * 60 * 1000,
    queryFn: () => {
      const p = new URLSearchParams({
        card: "TODOS",
        modo: campo,
        busca: termo.trim(),
        limite: String(TAMANHO_PAGINA_PIO),
      });
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
    // Três valores que a tela precisa manter separados, e que já se
    // confundiram uma vez: `value` é o PRÊMIO (o que se paga por mês),
    // `individualIncome` é a renda do PROPONENTE e `insuredAmount` é a
    // importância segurada (o capital COBERTO pela apólice).
    individualIncome: item.renda === null ? "" : MOEDA.format(item.renda),
    insuredAmount: item.imp_segurada === null ? "" : MOEDA.format(item.imp_segurada),
    indicatorId: item.matricula,
    agency: item.agencia,
    cpf: item.cpf,
    product: item.produto,
    phone: item.telefone,
    email: item.email,
    region: regiaoDaUf(item.uf),
    ageRange: item.idade === null ? "" : `${item.idade} anos`,
    broker: item.matricula,
    daysInPending: item.dias_pendente,
  };
}
