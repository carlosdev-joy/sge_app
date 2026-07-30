// Base de propostas da POC Caixa Seguro — FONTE ÚNICA para todas as telas.
//
// Antes, "Consulta Proposta" tinha um mock próprio com UMA proposta
// (80316460327404) que não existia na lista do Monitoramento Tático: buscar
// qualquer número da tela de acompanhamento não devolvia nada, e as duas telas
// contavam histórias diferentes sobre a mesma carteira. Aqui elas passam a ler
// a mesma base.
//
// Mock de apresentação: nada disto vem de banco.
import type { ProposalTrackingOrq } from "../components/ProposalCard";

export type PropostaStatus =
  | "pending_signature"
  | "awaiting_payment"
  | "signed_proposal"
  | "pending_documentation"
  | "pending_dps"
  | "refund_scheduled"
  | "refund_pending"
  | "valores_programados"
  | "sensitization_monitoring";

export type DocumentSubStatus = "incomplete" | "not_match" | "no_signature" | "illegible" | "non_compliant" | "procuration_curatela" | "all";
export type SignedSubStatus = "payment_cycle" | "payment_ended" | "all";
export type RefundSubStatus = "scheduled" | "pending" | "all";
export type PaymentSubStatus = "payment_phase" | "payment_ended_no_payment" | "all";

export interface Proposta extends ProposalTrackingOrq {
  status: PropostaStatus;
  policy?: string;
  documentSubStatus?: DocumentSubStatus;
  signedSubStatus?: SignedSubStatus;
  paymentSubStatus?: PaymentSubStatus;
  broker?: string;
  refundDate?: string;
  paymentMethod?: string;
  daysInPending?: number;
}

export const PROPOSTAS: Proposta[] = [
  { id: "1", number: "8047413032422-7", insuredName: "DIEBSON BITENCOURT DA SILVA", date: "17/10/2025", status: "pending_signature", value: "R$ 5.624,75", indicatorId: "0000122795-B", agency: "474", cpf: "025.359.088-03", product: "Vida Multipremiado Total", phone: "(11) 98765-4321", email: "diebson@email.com", daysInPending: 5 },
  { id: "2", number: "8047413032423-8", insuredName: "MARIA OLIVEIRA SANTOS", date: "18/10/2025", status: "pending_signature", value: "R$ 3.200,00", indicatorId: "0000122796-C", agency: "474", cpf: "123.456.789-00", product: "Vida Mulher", phone: "(11) 91234-5678", email: "maria@email.com", daysInPending: 3 },
  { id: "3", number: "8047413032424-9", insuredName: "JOÃO CARLOS FERREIRA", date: "19/10/2025", status: "awaiting_payment", paymentSubStatus: "payment_phase", value: "R$ 4.500,00", indicatorId: "0000122797-D", agency: "474", cpf: "234.567.890-11", product: "Vida Conforto", phone: "(11) 92345-6789", email: "joao@email.com", paymentMethod: "Boleto", daysInPending: 7 },
  { id: "4", number: "8047413032425-0", insuredName: "ANA PAULA COSTA", date: "20/10/2025", status: "awaiting_payment", paymentSubStatus: "payment_ended_no_payment", value: "R$ 6.800,00", indicatorId: "0000122798-E", agency: "474", cpf: "345.678.901-22", product: "Perda de Renda", phone: "(11) 93456-7890", email: "ana@email.com", paymentMethod: "Débito em Conta", daysInPending: 4 },
  { id: "5", number: "8047413032426-1", insuredName: "PEDRO HENRIQUE LIMA", date: "21/10/2025", status: "signed_proposal", signedSubStatus: "payment_cycle", value: "R$ 5.100,00", indicatorId: "0000122799-F", agency: "474", cpf: "456.789.012-33", product: "Vida Multipremiado Total", policy: "POL-2024-001", phone: "(11) 94567-8901", email: "pedro@email.com" },
  { id: "6", number: "8047413032427-2", insuredName: "CARLA REGINA SOUZA", date: "22/10/2025", status: "signed_proposal", signedSubStatus: "payment_ended", value: "R$ 7.300,00", indicatorId: "0000122800-G", agency: "474", cpf: "567.890.123-44", product: "Vida Mulher", policy: "POL-2024-002", phone: "(11) 95678-9012", email: "carla@email.com" },
  { id: "7", number: "8047413032428-3", insuredName: "ROBERTO SILVA SANTOS", date: "23/10/2025", status: "pending_documentation", value: "R$ 4.200,00", indicatorId: "0000122801-H", agency: "474", cpf: "678.901.234-55", product: "Vida Conforto", phone: "(11) 96789-0123", email: "roberto@email.com", documentSubStatus: "incomplete", broker: "João Silva", daysInPending: 12 },
  { id: "8", number: "8047413032429-4", insuredName: "LUCIA MARIA FERNANDES", date: "24/10/2025", status: "pending_documentation", value: "R$ 5.800,00", indicatorId: "0000122802-I", agency: "474", cpf: "789.012.345-66", product: "Perda de Renda", phone: "(11) 97890-1234", email: "lucia@email.com", documentSubStatus: "illegible", broker: "Maria Santos", daysInPending: 8 },
  { id: "14", number: "8047413032435-0", insuredName: "AMANDA CRISTINA ROCHA", date: "30/10/2025", status: "pending_documentation", value: "R$ 3.900,00", indicatorId: "0000122808-O", agency: "474", cpf: "345.678.901-30", product: "Vida Mulher", phone: "(11) 94444-5555", email: "amanda@email.com", documentSubStatus: "not_match", broker: "Carlos Pereira", daysInPending: 6 },
  { id: "15", number: "8047413032436-1", insuredName: "EDUARDO SANTOS LIMA", date: "31/10/2025", status: "pending_documentation", value: "R$ 5.200,00", indicatorId: "0000122809-P", agency: "474", cpf: "456.789.012-40", product: "Vida Multipremiado Total", phone: "(11) 95555-6666", email: "eduardo@email.com", documentSubStatus: "no_signature", broker: "Ana Paula", daysInPending: 10 },
  { id: "16", number: "8047413032437-2", insuredName: "MARCOS VINÍCIUS ALMEIDA", date: "01/11/2025", status: "pending_documentation", value: "R$ 650.000,00", indicatorId: "0000122810-Q", agency: "474", cpf: "567.890.123-50", product: "Previdência PGBL", phone: "(11) 96666-7777", email: "marcos@email.com", documentSubStatus: "non_compliant", broker: "Roberto Lima", daysInPending: 15 },
  { id: "17", number: "8047413032438-3", insuredName: "JULIANA COSTA PEREIRA", date: "02/11/2025", status: "pending_documentation", value: "R$ 820.000,00", indicatorId: "0000122811-R", agency: "474", cpf: "678.901.234-60", product: "Previdência VGBL", phone: "(11) 97777-8888", email: "juliana@email.com", documentSubStatus: "non_compliant", broker: "Patricia Santos", daysInPending: 18 },
  { id: "18", number: "8047413032439-4", insuredName: "ANTONIO CARLOS RODRIGUES", date: "03/11/2025", status: "pending_documentation", value: "R$ 45.000,00", indicatorId: "0000122812-S", agency: "474", cpf: "789.012.345-70", product: "Previdência Total", phone: "(11) 98888-9999", email: "antonio@email.com", documentSubStatus: "procuration_curatela", broker: "Fernando Alves", daysInPending: 9 },
  { id: "19", number: "8047413032440-5", insuredName: "BEATRIZ OLIVEIRA SOUZA", date: "04/11/2025", status: "pending_documentation", value: "R$ 32.500,00", indicatorId: "0000122813-T", agency: "474", cpf: "890.123.456-80", product: "Previdência Ativa", phone: "(11) 99999-0000", email: "beatriz@email.com", documentSubStatus: "procuration_curatela", broker: "Carla Regina", daysInPending: 11 },
  { id: "9", number: "8047413032430-5", insuredName: "FERNANDO AUGUSTO LIMA", date: "25/10/2025", status: "refund_scheduled", refundSubStatus: "scheduled", value: "R$ 3.500,00", indicatorId: "0000122803-J", agency: "474", cpf: "890.123.456-77", product: "Vida Multipremiado Total", policy: "POL-2024-003", phone: "(11) 98901-2345", email: "fernando@email.com", declineReason: "Análise de crédito negativa", refundDate: "15/12/2025" },
  { id: "10", number: "8047413032431-6", insuredName: "PATRICIA SANTOS COSTA", date: "26/10/2025", status: "refund_pending", refundSubStatus: "pending", value: "R$ 4.900,00", indicatorId: "0000122804-K", agency: "474", cpf: "901.234.567-88", product: "Vida Mulher", policy: "POL-2024-004", phone: "(11) 99012-3456", email: "patricia@email.com", declineReason: "Documentação irregular", receiptNumber: "REC-2024-12345" },
  { id: "13", number: "8047413032434-9", insuredName: "RAFAEL MENDES ALMEIDA", date: "29/10/2025", status: "refund_pending", refundSubStatus: "pending", value: "R$ 3.300,00", indicatorId: "0000122807-N", agency: "474", cpf: "234.567.890-20", product: "Vida Conforto", policy: "POL-2024-006", phone: "(11) 93333-4444", email: "rafael@email.com", declineReason: "Análise de risco", receiptNumber: "REC-2024-12346" },
  { id: "11", number: "8047413032432-7", insuredName: "MARCOS ANTONIO PEREIRA", date: "27/10/2025", status: "pending_dps", value: "R$ 2.800,00", indicatorId: "0000122805-L", agency: "474", cpf: "012.345.678-99", product: "Vida Conforto", phone: "(11) 91111-2222", email: "marcos@email.com", broker: "Carlos Oliveira", daysInPending: 6 },
  { id: "12", number: "8047413032433-8", insuredName: "JULIANA ROCHA ALVES", date: "28/10/2025", status: "valores_programados", value: "R$ 5.200,00", indicatorId: "0000122806-M", agency: "474", cpf: "123.456.789-10", product: "Perda de Renda", policy: "POL-2024-005", phone: "(11) 92222-3333", email: "juliana@email.com", declineReason: "Não atende critérios de aceitação", refundDate: "20/12/2025" },
  // Proposta histórica da primeira versão da POC. Mantida na base porque é o
  // número usado nas demonstrações — sumir com ela quebraria o roteiro de quem
  // já apresentou a tela.
  { id: "20", number: "80316460327404", insuredName: "JOYCE DA SILVA FORMIGONI", date: "23/10/2025", status: "pending_signature", value: "R$ 1.428,92", indicatorId: "106562-2", agency: "316", cpf: "397.750.878-48", product: "Vida Mulher", phone: "(11) 98765-4321", email: "joyce.formigoni@email.com", daysInPending: 2 },
];

/** Só os dígitos: deixa "397.750.878-48", "39775087848" e "397 750 878 48" iguais. */
export function somenteDigitos(valor: string): string {
  return (valor || "").replace(/\D/g, "");
}

export type ModoBusca = "proposta" | "cpf" | "agencia" | "sev" | "sr";

/**
 * Busca na base compartilhada. Devolve [] quando não acha — quem chama decide
 * a mensagem.
 *
 * Compara por dígitos, não por texto: o usuário digita CPF com pontuação, o
 * mock guarda com pontuação e o número da proposta às vezes vem sem o hífen.
 * Exigir igualdade literal era o que fazia a busca "não funcionar" mesmo com o
 * número certo na mão.
 */
export function buscarPropostas(modo: ModoBusca, termo: string): Proposta[] {
  const alvo = somenteDigitos(termo);
  if (!alvo) return [];

  return PROPOSTAS.filter((p) => {
    switch (modo) {
      case "proposta":
        return somenteDigitos(p.number).includes(alvo);
      case "cpf":
        return somenteDigitos(p.cpf).includes(alvo);
      case "agencia":
        return somenteDigitos(p.agency) === alvo;
      // SEV e SR são identificados pela matrícula do indicador no mock.
      case "sev":
      case "sr":
        return somenteDigitos(p.indicatorId).includes(alvo);
    }
  });
}

/** Rótulo do status para a tabela de resultado. */
export const ROTULO_STATUS: Record<PropostaStatus, string> = {
  pending_signature: "Aguardando assinatura",
  awaiting_payment: "Aguardando pagamento",
  signed_proposal: "Proposta assinada",
  pending_documentation: "Pendência documental",
  pending_dps: "Pendência de DPS",
  refund_scheduled: "Restituição agendada",
  refund_pending: "Proposta declinada",
  valores_programados: "Valores programados",
  sensitization_monitoring: "Monitoramento de sensibilização",
};
