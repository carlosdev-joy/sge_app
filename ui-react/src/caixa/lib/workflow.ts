// Fonte ÚNICA da sequência do Workflow de propostas (Busca & Vendas).
//
// Por que este arquivo existe: até aqui a home tinha DOIS workflows com listas
// de status diferentes — o painel do botão "Workflow" (ProposalWorkflowSheet,
// 9 status: "Ag. Link Pagamento", "Cotação", "Rascunho"…) e o card colapsável
// abaixo da busca (InlineWorkflow, 10 status). Mesma tela, dois vocabulários,
// dois mocks. Com os dados reais entrando card a card, os dois precisam ler a
// MESMA lista: é aqui que ela mora, e é aqui que a fonte real vai ser plugada.
//
// A SEQUÊNCIA abaixo é a ordem da operação, definida pelo usuário em
// 2026-08-31 — não é ordem alfabética nem a ordem em que os status foram
// implementados. Quem inserir status novo "no fim, para não mexer no resto"
// quebra a leitura da tela sem quebrar nada que dê erro; por isso
// `tests/test_caixa_workflow_sequencia.py` prende ordem, nomes e sinais.

// ── Sinal do card ───────────────────────────────────────────────────────────
// O ícone à direita do número, que diz o que aquele número significa:
//   • aviso    (amarelo)  — parada esperando alguém agir;
//   • perda    (vermelho) — negócio perdido;
//   • positivo (verde)    — avançou no funil.
export type SinalWorkflow = "aviso" | "perda" | "positivo";

export type StatusWorkflow =
  | "pending_signature"
  | "awaiting_payment"
  | "paid"
  | "in_analysis"
  | "emission_sent"
  | "declined"
  | "refund_scheduled"
  | "sensitization_monitoring";

export interface EtapaWorkflow {
  value: StatusWorkflow;
  label: string;
  sinal: SinalWorkflow;
}

// Os rótulos ficam em Title Case: o painel do Sheet aplica `uppercase` no CSS
// (é a régua tipográfica DELE), e o card inline segue o padrão das outras
// telas nativas. Mesmo texto, cada tela na sua régua — em vez de caixa alta
// gravada no dado, que forçaria a mesma forma nos dois lugares.
// Nomes no PLURAL e sem o sujeito repetido ("Proposta…" em oito cards seguidos
// não distingue nada): o card conta um grupo, e o que o olho precisa achar é o
// que muda de um para o outro.
export const SEQUENCIA_WORKFLOW: EtapaWorkflow[] = [
  { value: "pending_signature",        label: "Pendentes de Assinatura", sinal: "aviso" },
  { value: "awaiting_payment",         label: "Pendentes de Pagamento",  sinal: "aviso" },
  { value: "paid",                     label: "Assinadas e Pagas",       sinal: "positivo" },
  { value: "in_analysis",              label: "Em Análise",              sinal: "aviso" },
  { value: "emission_sent",            label: "Emitidas",                sinal: "positivo" },
  { value: "declined",                 label: "Rejeitadas",              sinal: "perda" },
  { value: "refund_scheduled",         label: "Devoluções de Prêmio",    sinal: "aviso" },
  { value: "sensitization_monitoring", label: "Sensibilizações",         sinal: "positivo" },
];

// Rótulo do selo na lista de propostas: o MESMO nome do card, no singular —
// ali ele qualifica UMA proposta, e divide a linha com o número dela e o
// "x dias pendente".
export const STATUS_LABEL_CURTO: Record<StatusWorkflow, string> = {
  pending_signature: "Pendente de Assinatura",
  awaiting_payment: "Pendente de Pagamento",
  paid: "Assinada e Paga",
  in_analysis: "Em Análise",
  emission_sent: "Emitida",
  declined: "Rejeitada",
  refund_scheduled: "Devolução de Prêmio",
  sensitization_monitoring: "Sensibilização",
};

// Fundo sólido com texto branco: legível nos dois temas sem par claro/escuro.
// Tom 600+ nos âmbares porque aqui a cor não é só o selo pequeno da lista — no
// painel do Sheet ela pinta o card INTEIRO, e branco sobre amber-500 fica no
// limite da legibilidade.
export const STATUS_COR: Record<StatusWorkflow, string> = {
  pending_signature: "bg-[#F26B00]",
  awaiting_payment: "bg-amber-600",
  paid: "bg-emerald-600",
  in_analysis: "bg-red-600",
  emission_sent: "bg-blue-600",
  declined: "bg-red-700",
  refund_scheduled: "bg-amber-700",
  sensitization_monitoring: "bg-[#0F4C88]",
};

// ── Sub-status ──────────────────────────────────────────────────────────────
// ⚠️ O filtro de sub-status compara IGUALDADE: proposta sem o campo SOME ao
// filtrar por qualquer opção, aparecendo só em "Todos os sub-status" — sem
// nenhum aviso na tela. Daí a regra: todo status que tem sub-filtro exige o
// campo em TODAS as suas propostas (o teste prende isso).
export type SubStatusAnalise = "incomplete" | "mismatch" | "no_signature" | "illegible" | "dps";
export type SubStatusPagamento = "payment_cycle" | "payment_ended";
export type SubStatusDevolucao = "scheduled" | "pending_value";

export const SUB_STATUS_ANALISE: Record<SubStatusAnalise, string> = {
  incomplete: "Proposta incompleta",
  mismatch: "Documento não corresponde à proposta",
  no_signature: "Proposta sem assinatura",
  illegible: "Documento ilegível",
  dps: "Aguardando envio da DPS",
};

export const SUB_STATUS_PAGAMENTO: Record<SubStatusPagamento, string> = {
  payment_cycle: "Em fase de pagamento",
  payment_ended: "Ciclo de pagamento encerrado",
};

export const SUB_STATUS_DEVOLUCAO: Record<SubStatusDevolucao, string> = {
  scheduled: "Devolução programada",
  pending_value: "Valor pendente de devolução",
};

export const FORMA_PAGAMENTO: Record<string, string> = {
  boleto: "Boleto",
  debit: "Débito em Conta",
  credit: "Crédito em Conta",
};

// ── Propostas ───────────────────────────────────────────────────────────────
// Mock enquanto os dados reais não entram. Quando entrarem, é ESTA constante
// que dá lugar à consulta — os dois componentes já leem daqui.
export interface PropostaWorkflow {
  id: string;
  number: string;
  insuredName: string;
  date: string;
  status: StatusWorkflow;
  value: string;
  indicatorId: string;
  agency: string;
  cpf: string;
  product: string;
  phone: string;
  email: string;
  region: string;
  ageRange: string;
  broker: string;
  daysInPending: number;
  /** Renda declarada, já formatada. Só as propostas vindas da carga do PIO a
   *  têm (VLR_RENDA_FORMAL); nas de exemplo o campo some do modal. */
  individualIncome?: string;
  declineReason?: string;
  analiseSubStatus?: SubStatusAnalise;
  pagamentoSubStatus?: SubStatusPagamento;
  refundSubStatus?: SubStatusDevolucao;
  paymentMethod?: "boleto" | "debit" | "credit";
  policy?: string;
}

export const propostasWorkflow: PropostaWorkflow[] = [
  // 1 — Pendente de assinatura
  { id: "1", number: "80316460327404", insuredName: "Maria Silva", status: "pending_signature", value: "R$ 2.200,00", product: "Perda de Renda", region: "Sul", ageRange: "45-60", broker: "Mariana", daysInPending: 5, date: "23/10/2025", indicatorId: "106562-2", agency: "316", cpf: "397.750.878-48", phone: "(11) 98765-4321", email: "maria@example.com" },
  { id: "4", number: "80316460327407", insuredName: "Carlos Oliveira", status: "pending_signature", value: "R$ 950,00", product: "Vida Conforto", region: "Nordeste", ageRange: "25-35", broker: "Carlos", daysInPending: 6, date: "20/10/2025", indicatorId: "106565-5", agency: "313", cpf: "345.678.901-22", phone: "(11) 98765-4324", email: "carlos@example.com" },

  // 2 — Assinada, pendente de pagamento (absorve o antigo "Proposta Assinada":
  // a Adriana vinha de `signed_proposal`, com o ciclo de pagamento encerrado)
  { id: "12", number: "80316460327415", insuredName: "Pedro Santos", status: "awaiting_payment", value: "R$ 2.400,00", product: "Vida Multipremiado", region: "Sudeste", ageRange: "30-40", broker: "Pedro", daysInPending: 4, date: "12/10/2025", indicatorId: "106573-3", agency: "305", cpf: "123.456.789-10", phone: "(11) 98765-4332", email: "pedro@example.com", paymentMethod: "debit", pagamentoSubStatus: "payment_cycle" },
  { id: "13", number: "80316460327416", insuredName: "Lucia Oliveira", status: "awaiting_payment", value: "R$ 1.650,00", product: "Vida Conforto", region: "Norte", ageRange: "45-60", broker: "Lucia", daysInPending: 6, date: "11/10/2025", indicatorId: "106574-4", agency: "304", cpf: "234.567.890-21", phone: "(11) 98765-4333", email: "lucia@example.com", paymentMethod: "boleto", pagamentoSubStatus: "payment_cycle" },
  { id: "13b", number: "80316460327414", insuredName: "Antonio Souza", status: "awaiting_payment", value: "R$ 1.980,00", product: "Vida Multipremiado", region: "Centro-Oeste", ageRange: "35-50", broker: "Antonio", daysInPending: 3, date: "11/10/2025", indicatorId: "106574-5", agency: "304", cpf: "345.678.901-43", phone: "(11) 98765-4337", email: "antonio@example.com", paymentMethod: "credit", pagamentoSubStatus: "payment_cycle" },
  { id: "15", number: "80316460327418", insuredName: "Adriana Lima", status: "awaiting_payment", value: "R$ 1.950,00", product: "Perda de Renda", region: "Nordeste", ageRange: "35-50", broker: "Adriana", daysInPending: 0, date: "09/10/2025", indicatorId: "106576-6", agency: "302", cpf: "456.789.012-43", phone: "(11) 98765-4335", email: "adriana@example.com", paymentMethod: "boleto", pagamentoSubStatus: "payment_ended", policy: "12345678" },

  // 3 — Assinada e paga
  { id: "2", number: "80316460327405", insuredName: "João Santos", status: "paid", value: "R$ 1.800,00", product: "Vida Multipremiado", region: "Sudeste", ageRange: "30-40", broker: "João", daysInPending: 0, date: "22/10/2025", indicatorId: "106563-3", agency: "315", cpf: "123.456.789-00", phone: "(11) 98765-4322", email: "joao@example.com" },

  // 4 — Em crítica (análise): funde a antiga "Pendência Documental" com a
  // "Pendência de DPS" — a DPS virou o sub-status `dps`, e é ele que troca o
  // botão da proposta entre "Upload" e "Enviar Link DPS".
  { id: "3", number: "80316460327406", insuredName: "Ana Costa", status: "in_analysis", value: "R$ 3.000,00", product: "Vida Mulher", region: "Sul", ageRange: "50-65", broker: "Ana", daysInPending: 8, date: "21/10/2025", indicatorId: "106564-4", agency: "314", cpf: "234.567.890-11", phone: "(11) 98765-4323", email: "ana@example.com", analiseSubStatus: "incomplete" },
  { id: "9", number: "80316460327412", insuredName: "Juliana Costa", status: "in_analysis", value: "R$ 1.900,00", product: "Vida Conforto", region: "Nordeste", ageRange: "30-45", broker: "Juliana", daysInPending: 10, date: "15/10/2025", indicatorId: "106570-0", agency: "308", cpf: "890.123.456-77", phone: "(11) 98765-4329", email: "juliana@example.com", analiseSubStatus: "mismatch" },
  { id: "10", number: "80316460327413", insuredName: "Roberto Silva", status: "in_analysis", value: "R$ 2.100,00", product: "Vida Mulher", region: "Sul", ageRange: "40-55", broker: "Roberto", daysInPending: 7, date: "14/10/2025", indicatorId: "106571-1", agency: "307", cpf: "901.234.567-88", phone: "(11) 98765-4330", email: "roberto@example.com", analiseSubStatus: "no_signature" },
  { id: "11", number: "80316460327414", insuredName: "Carla Mendes", status: "in_analysis", value: "R$ 1.750,00", product: "Perda de Renda", region: "Centro-Oeste", ageRange: "35-50", broker: "Carla", daysInPending: 12, date: "13/10/2025", indicatorId: "106572-2", agency: "306", cpf: "012.345.678-99", phone: "(11) 98765-4331", email: "carla@example.com", analiseSubStatus: "illegible" },
  { id: "14", number: "80316460327417", insuredName: "Marcos Costa", status: "in_analysis", value: "R$ 2.800,00", product: "Vida Mulher", region: "Sul", ageRange: "50-65", broker: "Marcos", daysInPending: 5, date: "10/10/2025", indicatorId: "106575-5", agency: "303", cpf: "345.678.901-32", phone: "(11) 98765-4334", email: "marcos@example.com", analiseSubStatus: "dps" },

  // 5 — Emitidas
  { id: "18", number: "80316460327421", insuredName: "Sergio Barbosa", status: "emission_sent", value: "R$ 1.720,00", product: "Vida Conforto", region: "Sul", ageRange: "40-55", broker: "Sergio", daysInPending: 0, date: "06/10/2025", indicatorId: "106579-9", agency: "299", cpf: "789.012.345-76", phone: "(11) 98765-4339", email: "sergio@example.com", policy: "45678901" },

  // 6 — Rejeitadas: recusadas que ainda NÃO entraram na devolução de prêmio.
  // É o estado de origem do card 7 — o botão "Gerenciar Devolução" move a
  // proposta daqui para lá.
  // ⚠️ Nasce com `refundSubStatus` mesmo ainda não estando na devolução: o
  // botão "Gerenciar Devolução" a move para o card 7 EM TEMPO DE EXECUÇÃO, e
  // lá o filtro de sub-status compara igualdade — sem o campo, ela entraria no
  // card 7 e sumiria assim que alguém filtrasse por sub-status.
  { id: "19", number: "80316460327422", insuredName: "Tatiane Rocha", status: "declined", value: "R$ 2.050,00", product: "Vida Mulher", region: "Sudeste", ageRange: "30-45", broker: "Tatiane", daysInPending: 3, date: "05/10/2025", indicatorId: "106580-0", agency: "298", cpf: "890.123.456-87", phone: "(11) 98765-4340", email: "tatiane@example.com", declineReason: "Divergência entre a renda declarada e a comprovada. Proposta recusada na análise.", refundSubStatus: "scheduled" },

  // 7 — Devolução de prêmio de propostas rejeitadas
  { id: "5", number: "80316460327408", insuredName: "Fernanda Lima", status: "refund_scheduled", value: "R$ 2.700,00", product: "Perda de Renda", region: "Centro-Oeste", ageRange: "35-50", broker: "Fernanda", daysInPending: 0, date: "19/10/2025", indicatorId: "106566-6", agency: "312", cpf: "456.789.012-33", phone: "(11) 98765-4325", email: "fernanda@example.com", declineReason: "Renda insuficiente para o valor solicitado. Perfil de risco não compatível com os critérios de aceitação.", refundSubStatus: "scheduled", policy: "34567890" },
  { id: "7", number: "80316460327410", insuredName: "Paula Rodrigues", status: "refund_scheduled", value: "R$ 1.500,00", product: "Vida Conforto", region: "Norte", ageRange: "40-55", broker: "Paula", daysInPending: 0, date: "17/10/2025", indicatorId: "106568-8", agency: "310", cpf: "678.901.234-55", phone: "(11) 98765-4327", email: "paula@example.com", declineReason: "Histórico de saúde pré-existente incompatível com as condições da apólice. Necessária reavaliação médica.", refundSubStatus: "scheduled", policy: "45678901" },
  { id: "16", number: "80316460327419", insuredName: "Ricardo Santos", status: "refund_scheduled", value: "R$ 2.300,00", product: "Vida Mulher", region: "Sul", ageRange: "40-55", broker: "Ricardo", daysInPending: 7, date: "08/10/2025", indicatorId: "106577-7", agency: "301", cpf: "567.890.123-54", phone: "(11) 98765-4336", email: "ricardo@example.com", declineReason: "Informações inconsistentes na documentação.", refundSubStatus: "pending_value", policy: "23456789" },

  // 8 — Monitoramento de sensibilização
  { id: "6", number: "80316460327409", insuredName: "Rafael Mendes", status: "sensitization_monitoring", value: "R$ 2.500,00", product: "Vida Mulher", region: "Sudeste", ageRange: "28-45", broker: "Rafael", daysInPending: 2, date: "18/10/2025", indicatorId: "106567-7", agency: "311", cpf: "567.890.123-44", phone: "(11) 98765-4326", email: "rafael@example.com" },
  { id: "8", number: "80316460327411", insuredName: "Bruno Alves", status: "sensitization_monitoring", value: "R$ 3.200,00", product: "Perda de Renda", region: "Sul", ageRange: "35-50", broker: "Bruno", daysInPending: 4, date: "16/10/2025", indicatorId: "106569-9", agency: "309", cpf: "789.012.345-66", phone: "(11) 98765-4328", email: "bruno@example.com" },
];

/** Contagem por status da sequência, derivada da lista — nunca um dicionário
 *  escrito à mão. Chave esquecida ali fazia a proposta ser DESCARTADA em
 *  silêncio, e o card nascia zerado com dado na base.
 *
 *  `reais` são as contagens que vêm da carga do PIO. Para o status que tem
 *  número real, ele SUBSTITUI o do mock (não soma): as duas fontes descrevem o
 *  mesmo card, e somar daria um total que não existe em lugar nenhum. O `all`
 *  é a soma do que os cards mostram, para o cabeçalho não contradizer a
 *  fileira logo abaixo dele. */
export function contarPorStatus(
  propostas: PropostaWorkflow[],
  sobrescrito: Record<string, string> = {},
  reais: Partial<Record<StatusWorkflow, number>> = {},
): Record<string, number> {
  const contagem: Record<string, number> = {};
  SEQUENCIA_WORKFLOW.forEach((etapa) => {
    contagem[etapa.value] = 0;
  });
  propostas.forEach((proposta) => {
    const status = sobrescrito[proposta.id] || proposta.status;
    if (contagem[status] !== undefined) contagem[status]++;
  });
  SEQUENCIA_WORKFLOW.forEach((etapa) => {
    const real = reais[etapa.value];
    if (real !== undefined) contagem[etapa.value] = real;
  });
  contagem.all = SEQUENCIA_WORKFLOW.reduce(
    (soma, etapa) => soma + (contagem[etapa.value] || 0), 0);
  return contagem;
}
