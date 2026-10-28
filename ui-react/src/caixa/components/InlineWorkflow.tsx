// Workflow inline da home no DS nativo — card colapsável com resumo por
// status, filtros com sub-status, alerta em lote e lista de propostas com ação
// por status, incluindo o movimento de Emissão (sensitization_monitoring →
// emission_sent, estado local). Todos os diálogos são os nativos das F3/F7/F8.
//
// A sequência dos cards, os rótulos e as propostas vêm de `lib/workflow.ts` —
// a MESMA fonte que o painel do botão "Workflow" (ProposalWorkflowSheet) lê.
// Antes cada um tinha a sua lista e o seu mock, na mesma tela.
import { useState } from "react";
import { ChevronDown, ChevronUp, CircleCheck, Send, TrendingDown, TriangleAlert } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Select } from "../../components/ui/Input";
import { toast } from "../../components/ui/Toast";
import Card1Valor from "./Card1Valor";
import ProposalDetailDialog from "./ProposalDetailDialog";
import ResendLinkDialog from "./ResendLinkDialog";
import DocumentUploadDialog from "./DocumentUploadDialog";
import DPSLinkDialog from "./DPSLinkDialog";
import SendAlertDialog from "./SendAlertDialog";
import PaymentOptionsDialog from "./PaymentOptionsDialog";
import RefundManagementDialog from "./RefundManagementDialog";
import {
  contarPorStatus,
  propostasWorkflow,
  FORMA_PAGAMENTO,
  SEQUENCIA_WORKFLOW,
  STATUS_COR,
  STATUS_LABEL_CURTO,
  SUB_STATUS_ANALISE,
  SUB_STATUS_DEVOLUCAO,
  SUB_STATUS_PAGAMENTO,
  type PropostaWorkflow,
  type SinalWorkflow,
  type StatusWorkflow,
} from "../lib/workflow";
import {
  dataBr,
  propostaDoPio,
  contagemPorCard,
  useContagensPio,
  usePropostasPio,
  ORIGEM_PIO,
  TAMANHO_PAGINA_PIO,
} from "../lib/pio";
import {
  listaDoCard,
  STATUS_CARD1,
  STATUS_CARD2,
  useResumoCard1,
  usePropostasCard1,
  dataHoraBr,
  canaisDeEnvio,
} from "../lib/pioCard1";
import { useResumoCard2, usePropostasCard2 } from "../lib/pioCard2";

// ÍCONE, não bolinha: a forma carrega o significado sozinha. Um triângulo de
// alerta, uma seta caindo e um "certo" são lidos de relance mesmo em preto e
// branco — a cor vira reforço, não a informação. E o `title`/`aria-label` leva
// a frase inteira, para quem usa leitor de tela.
//
// Discretos de propósito (14px, traço fino, tom 500): o número é a informação
// principal do card; o sinal qualifica, não compete.
const SINAL_ICONE: Record<SinalWorkflow, LucideIcon> = {
  aviso:    TriangleAlert,   // atenção: algo esperando
  perda:    TrendingDown,    // negócio que caiu — não é "erro", é perda
  positivo: CircleCheck,     // avançou
};

// Tom 500 nos três: forte o bastante para distinguir, fraco o bastante para
// não brigar com o número ao lado. O dark: mantém o contraste no tema escuro,
// onde o 500 puro fica apagado.
const SINAL_CLASSE: Record<SinalWorkflow, string> = {
  aviso:    "text-amber-500 dark:text-amber-400",
  perda:    "text-red-500 dark:text-red-400",
  positivo: "text-emerald-500 dark:text-emerald-400",
};

const SINAL_TEXTO: Record<SinalWorkflow, string> = {
  aviso:    "Aviso: propostas paradas aguardando ação",
  perda:    "Perda: negócios que não seguiram adiante",
  positivo: "Ação positiva: propostas que avançaram no funil",
};

// Qual campo cada status filtra no segundo Select. Um mapa só, em vez de três
// blocos repetidos: status novo com sub-status entra aqui e passa a valer no
// filtro E na contagem, sem depender de alguém lembrar dos dois lugares.
const SUB_FILTRO: Partial<Record<StatusWorkflow, { campo: keyof PropostaWorkflow; opcoes: Record<string, string> }>> = {
  awaiting_payment: { campo: "pagamentoSubStatus", opcoes: SUB_STATUS_PAGAMENTO },
  in_analysis:      { campo: "analiseSubStatus",   opcoes: SUB_STATUS_ANALISE },
  refund_scheduled: { campo: "refundSubStatus",    opcoes: SUB_STATUS_DEVOLUCAO },
};

// As propostas de exemplo dos status que JÁ leem do PIO saem de cena: mock e
// carga descrevem o mesmo card, e misturar os dois é o jeito mais rápido de
// alguém ler um número de teste como se fosse produção.
const PROPOSTAS_DE_EXEMPLO = propostasWorkflow.filter((p) => !ORIGEM_PIO[p.status]);

export default function InlineWorkflow() {
  const [isExpanded, setIsExpanded] = useState(false);
  const [selectedStatus, setSelectedStatus] = useState("all");
  const [selectedSubStatus, setSelectedSubStatus] = useState("all");
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [resendDialogOpen, setResendDialogOpen] = useState(false);
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [dpsDialogOpen, setDpsDialogOpen] = useState(false);
  const [alertDialogOpen, setAlertDialogOpen] = useState(false);
  const [paymentDialogOpen, setPaymentDialogOpen] = useState(false);
  const [refundDialogOpen, setRefundDialogOpen] = useState(false);
  const [selectedProposal, setSelectedProposal] = useState<PropostaWorkflow | null>(null);
  const [proposalStatuses, setProposalStatuses] = useState<Record<string, string>>({});
  const [sendingEmission, setSendingEmission] = useState<string | null>(null);
  const [pagina, setPagina] = useState(0);

  /** Trocar de card volta para a primeira página: sem isso, sair de um card
   *  com 8.700 propostas na página 40 e entrar em outro com 12 deixaria a
   *  lista vazia, com cara de "não há nada aqui". */
  const selecionar = (status: string) => {
    setSelectedStatus(status);
    setSelectedSubStatus("all");
    setPagina(0);
  };

  // ── A carga do PIO ────────────────────────────────────────────────────────
  const contagens = useContagensPio();
  const cardSelecionado = ORIGEM_PIO[selectedStatus as StatusWorkflow];
  // O Card 1 lê a FOTO diária (agregado para o número, fato para a lista); os
  // outros sete seguem na carga legada. O hook legado recebe `undefined` no
  // Card 1, o que o desliga — a lista não é pedida às duas fontes.
  // Cards 1 e 2 leem a FOTO diária (agregado para o número, fato para a lista);
  // os outros seis seguem na carga legada. O hook legado recebe `undefined` nos
  // cards de foto, o que o desliga — a lista não é pedida às duas fontes.
  const emCard1 = selectedStatus === STATUS_CARD1;
  const emCard2 = selectedStatus === STATUS_CARD2;
  const resumoCard1 = useResumoCard1();
  const resumoCard2 = useResumoCard2();
  const paginaPio = usePropostasPio(emCard1 || emCard2 ? undefined : cardSelecionado, isExpanded, pagina, "");
  const fotoCard1 = usePropostasCard1(emCard1 && isExpanded, pagina, resumoCard1.data?.referencia);
  const fotoCard2 = usePropostasCard2(emCard2 && isExpanded, pagina, resumoCard2.data?.referencia);
  const lista = listaDoCard(
    emCard1 || emCard2, paginaPio,
    (item) => propostaDoPio(item, selectedStatus as StatusWorkflow),
    emCard2 ? resumoCard2 : resumoCard1, emCard2 ? fotoCard2 : fotoCard1,
    selectedStatus as StatusWorkflow);

  // Contagem real por card, só para os status que têm origem no PIO.
  const reais: Partial<Record<StatusWorkflow, number>> = {};
  if (contagens.data?.disponivel) {
    const porCard = contagemPorCard(contagens.data.cards);
    (Object.entries(ORIGEM_PIO) as [StatusWorkflow, string][]).forEach(
      ([status, card]) => {
        // Card SEM linha na carga é zero de verdade — a carga rodou e não achou
        // proposta naquele estado. Diferente de não ter conseguido ler, que é o
        // `disponivel: false` tratado abaixo.
        reais[status] = porCard.get(card) ?? 0;
      });
  }
  // A quantidade do Card 1 vem da foto, a mesma conta do total da lista. Sem
  // leitura da foto, ele NÃO cai na contagem legada: dois números para o mesmo
  // card seria pior que um "—".
  delete reais[STATUS_CARD1];
  if (resumoCard1.data?.disponivel && resumoCard1.data.referencia) {
    reais[STATUS_CARD1] = resumoCard1.data.quantidade;
  }
  // Idem o Card 2: a quantidade é a da foto, nunca a contagem legada.
  delete reais[STATUS_CARD2];
  if (resumoCard2.data?.disponivel && resumoCard2.data.referencia) {
    reais[STATUS_CARD2] = resumoCard2.data.quantidade;
  }

  const counts = contarPorStatus(PROPOSTAS_DE_EXEMPLO, proposalStatuses, reais);

  // Card que lê do PIO NÃO oferece sub-filtro: a carga não traz forma de
  // pagamento nem motivo de análise, e o filtro roda sobre as propostas de
  // exemplo. Deixá-lo na tela daria um seletor que não altera coisa alguma —
  // o usuário escolheria "Cartão de crédito" e continuaria vendo a lista
  // inteira, achando que aquilo é o recorte pedido.
  const subFiltroAtivo = cardSelecionado
    ? undefined
    : SUB_FILTRO[selectedStatus as StatusWorkflow];

  const filteredProposals = cardSelecionado
    ? lista.propostas   // já vêm ordenadas pela consulta: mais antigas primeiro
    : PROPOSTAS_DE_EXEMPLO
        .filter((proposta) => {
          const statusAtual = proposalStatuses[proposta.id] || proposta.status;
          if (selectedStatus !== "all" && statusAtual !== selectedStatus) return false;
          if (subFiltroAtivo && selectedSubStatus !== "all") {
            return proposta[subFiltroAtivo.campo] === selectedSubStatus;
          }
          return true;
        })
        .sort((a, b) => b.daysInPending - a.daysInPending);

  const totalDaPagina = lista.total;
  const temMaisPaginas = cardSelecionado
    ? (pagina + 1) * TAMANHO_PAGINA_PIO < totalDaPagina
    : false;

  const handleSendEmission = (proposalId: string) => {
    setSendingEmission(proposalId);
    setTimeout(() => {
      setProposalStatuses((prev) => ({ ...prev, [proposalId]: "emission_sent" }));
      setSendingEmission(null);
      toast.success("Movimento de Emissão enviado com sucesso. Aguardando confirmação.");
    }, 2000);
  };

  const abrir = (proposta: PropostaWorkflow, setter: (v: boolean) => void) => {
    setSelectedProposal(proposta);
    setter(true);
  };

  return (
    <div className="space-y-4">
      <div className="bg-panel border border-edge rounded-lg">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="w-full px-6 py-4 flex items-center justify-between hover:bg-canvas/60 transition-colors rounded-lg text-ink"
          aria-expanded={isExpanded}
        >
          <div className="flex items-center gap-3">
            <span className="font-semibold text-lg">Workflow</span>
            <span className="inline-flex items-center rounded-full border border-edge px-2 py-0.5 text-xs font-medium text-dim">
              {counts.all} propostas
            </span>
          </div>
          {isExpanded ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
        </button>

        {isExpanded && (
          <div className="p-6 border-t border-edge space-y-4">
            {/* Cards-resumo por status — 4 + 4 nas telas largas */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
              {SEQUENCIA_WORKFLOW.map((status) => (
                <button
                  key={status.value}
                  onClick={() => selecionar(status.value)}
                  className={`relative p-2 rounded-lg border-2 transition-all ${
                    selectedStatus === status.value
                      ? "border-[#1A5FA8] bg-[#1A5FA8]/10"
                      : "border-edge hover:border-[#1A5FA8]/50"
                  }`}
                >
                  {/* Sinal no canto INFERIOR direito, FORA do fluxo.
                      Duas razões, nesta ordem:
                      1. no topo ele disputaria espaço com o rótulo, que é o
                         elemento de altura variável ("Pendentes de
                         Assinatura" quebra em duas linhas, "Emitidas" não);
                         embaixo convive com o número, que é curto e
                         centralizado;
                      2. tira o ícone do fluxo e devolve ao número o centro
                         do card. Antes os dois eram centralizados JUNTOS, e
                         o número mudava de posição conforme tivesse 1 ou 2
                         dígitos — numa fileira de cards, dançavam. */}
                  {(() => {
                    const Icone = SINAL_ICONE[status.sinal];
                    return (
                      <Icone
                        className={`absolute bottom-1.5 right-1.5 h-3.5 w-3.5 ${SINAL_CLASSE[status.sinal]}`}
                        strokeWidth={2}
                        role="img"
                        aria-label={SINAL_TEXTO[status.sinal]}
                      >
                        <title>{SINAL_TEXTO[status.sinal]}</title>
                      </Icone>
                    );
                  })()}
                  {/* Sem folga lateral: com o sinal embaixo, o rótulo usa a
                      largura inteira e quebra em menos linhas. */}
                  <div className="text-xs font-medium text-center text-ink">{status.label}</div>
                  {/* Card com origem no PIO não pode mostrar zero enquanto
                      carrega nem quando a leitura falha: zero é uma resposta
                      que ninguém investiga. "…" e "—" são perguntas. */}
                  <div className="text-xl font-bold text-center mt-1 text-ink">
                    {status.value === STATUS_CARD1 || status.value === STATUS_CARD2 ? (
                      <Card1Valor resumo={status.value === STATUS_CARD2 ? resumoCard2 : resumoCard1} />
                    ) : ORIGEM_PIO[status.value] && contagens.isPending ? (
                      <span className="text-dim" title="consultando a carga">…</span>
                    ) : ORIGEM_PIO[status.value] && !contagens.data?.disponivel ? (
                      <span
                        className="text-dim"
                        title="não foi possível ler a carga do PIO — o número não é zero, é desconhecido"
                      >
                        —
                      </span>
                    ) : (
                      counts[status.value].toLocaleString("pt-BR")
                    )}
                  </div>
                </button>
              ))}
            </div>

            {/* Filtros */}
            <div className="flex gap-3 flex-wrap">
              <div className="flex-1 min-w-[220px]">
                <Select
                  value={selectedStatus}
                  onChange={(e) => selecionar(e.target.value)}
                  aria-label="Filtrar por status"
                  className="w-full"
                >
                  <option value="all">Todas as Propostas ({counts.all})</option>
                  {SEQUENCIA_WORKFLOW.map((status) => (
                    <option key={status.value} value={status.value}>
                      {status.label} ({counts[status.value]})
                    </option>
                  ))}
                </Select>
              </div>

              {subFiltroAtivo && (
                <div className="flex-1 min-w-[220px]">
                  <Select
                    value={selectedSubStatus}
                    onChange={(e) => setSelectedSubStatus(e.target.value)}
                    aria-label="Filtrar por sub-status"
                    className="w-full"
                  >
                    <option value="all">Todos os sub-status</option>
                    {Object.entries(subFiltroAtivo.opcoes).map(([valor, rotulo]) => (
                      <option key={valor} value={valor}>
                        {rotulo}
                      </option>
                    ))}
                  </Select>
                </div>
              )}
            </div>

            {/* Alerta em lote */}
            {filteredProposals.length > 0 && selectedStatus !== "all" && (
              <Button variant="primary" onClick={() => setAlertDialogOpen(true)} className="w-full justify-center">
                Enviar Alertas para Responsáveis
              </Button>
            )}

            {/* Procedência da lista — de onde vieram estas linhas e de quando.
                Um número sem data de carga não deixa distinguir "a fila
                esvaziou" de "a carga das 07:30 não rodou". */}
            {cardSelecionado && lista.disponivel && !lista.carregando && !lista.detalheIndisponivel && (lista.referencia || !lista.deFoto) && (
              <p className="text-xs text-dim">
                {totalDaPagina.toLocaleString("pt-BR")} proposta{totalDaPagina === 1 ? "" : "s"} {lista.deFoto ? "na foto" : "na carga"}
                {lista.referencia ? ` de ${dataBr(lista.referencia)}` : ""}
                {lista.deFoto && lista.atualizacao ? `, publicada em ${dataHoraBr(lista.atualizacao)}` : ""}
                {filteredProposals.length > 0 && (
                  <> · mostrando {filteredProposals.length.toLocaleString("pt-BR")}, as mais antigas primeiro</>
                )}
              </p>
            )}
            {lista.deFoto && lista.disponivel && !lista.carregando && !lista.referencia && (
          <p className="text-xs text-dim">Nenhuma foto do Card 1 foi publicada ainda; não há número nem lista a mostrar.</p>
        )}
        {lista.deFoto && lista.disponivel && lista.detalheIndisponivel && (
              <p className="text-xs text-dim">
                O detalhe das propostas desta data já saiu da retenção (a lista guarda menos tempo
                que o total do card). O número do card continua válido.
              </p>
            )}
            {cardSelecionado && lista.carregando && (
              <p className="text-xs text-dim">Consultando {lista.deFoto ? "a foto" : "a carga"} do PIO…</p>
            )}
            {cardSelecionado && !lista.carregando && !lista.disponivel && (
              <p className="text-xs text-red-600 dark:text-red-400">
                Não foi possível ler {lista.deFoto ? "a foto" : "a carga"} do PIO. A lista não está vazia — ela é desconhecida.
              </p>
            )}
            {/* Em "Todas as Propostas" a lista mostra só o que não vem da
                carga: juntar 8.700 linhas reais às de exemplo não caberia na
                tela nem diria nada. */}
            {selectedStatus === "all" && Object.keys(ORIGEM_PIO).length > 0 && (
              <p className="text-xs text-dim">
                As propostas com dados reais aparecem ao selecionar o card correspondente.
              </p>
            )}

            {/* Lista */}
            <div className="max-h-[400px] overflow-y-auto pr-1">
              <div className="space-y-3">
                {filteredProposals.map((proposta) => {
                  const statusAtual = (proposalStatuses[proposta.id] || proposta.status) as StatusWorkflow;
                  return (
                    <div
                      key={proposta.id}
                      className="bg-canvas border border-edge rounded-lg p-4 hover:shadow-md transition-shadow cursor-pointer"
                      onClick={() => abrir(proposta, setDetailDialogOpen)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") abrir(proposta, setDetailDialogOpen);
                      }}
                    >
                      <div className="flex items-start justify-between gap-4 flex-wrap">
                        <div className="flex-1 min-w-[240px] space-y-2">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-semibold text-ink">{proposta.number}</span>
                            <span className={`${STATUS_COR[statusAtual] ?? "bg-slate-500"} text-white rounded-full px-2 py-0.5 text-xs font-medium`}>
                              {STATUS_LABEL_CURTO[statusAtual] ?? statusAtual}
                            </span>
                            {proposta.daysInPending > 0 && (
                              <span className="inline-flex items-center rounded-full border border-[#F26B00] text-[#F26B00] px-2 py-0.5 text-xs font-medium">
                                {proposta.daysInPending} dias pendente
                              </span>
                            )}
                          </div>
                          <div className="text-sm text-dim">
                            <p className="font-medium text-ink">{proposta.insuredName}</p>
                            <p>
                              {proposta.product} - {proposta.value}
                            </p>
                            <p>
                              Região: {proposta.region} | Faixa: {proposta.ageRange}
                            </p>
                            {statusAtual === "in_analysis" && proposta.analiseSubStatus && (
                              <p className="text-red-600 dark:text-red-400 font-medium">
                                {SUB_STATUS_ANALISE[proposta.analiseSubStatus]}
                              </p>
                            )}
                            {statusAtual === "awaiting_payment" && proposta.paymentMethod && (
                              <p className="font-medium text-ink">Forma de Pagamento: {FORMA_PAGAMENTO[proposta.paymentMethod]}</p>
                            )}
                          </div>
                        </div>
                        <div className="flex flex-col gap-2" onClick={(e) => e.stopPropagation()}>
                          {statusAtual === "pending_signature" && (
                            <Button variant="primary" size="sm" onClick={() => abrir(proposta, setResendDialogOpen)}>
                              <Send className="h-4 w-4" />
                              Enviar
                            </Button>
                          )}
                          {/* A DPS virou sub-status da crítica: o botão segue a
                              pendência da proposta, não mais o card. */}
                          {statusAtual === "in_analysis" &&
                            (proposta.analiseSubStatus === "dps" ? (
                              <Button variant="primary" size="sm" onClick={() => abrir(proposta, setDpsDialogOpen)}>
                                Enviar Link DPS
                              </Button>
                            ) : (
                              <Button variant="danger" size="sm" onClick={() => abrir(proposta, setUploadDialogOpen)}>
                                Upload
                              </Button>
                            ))}
                          {statusAtual === "awaiting_payment" && (
                            <Button variant="primary" size="sm" onClick={() => abrir(proposta, setPaymentDialogOpen)}>
                              Alterar forma de pagamento
                            </Button>
                          )}
                          {statusAtual === "sensitization_monitoring" && (
                            <Button
                              variant="primary"
                              size="sm"
                              onClick={() => handleSendEmission(proposta.id)}
                              disabled={sendingEmission === proposta.id}
                              loading={sendingEmission === proposta.id}
                            >
                              {sendingEmission === proposta.id ? "Enviando..." : "Enviar movimento de Emissão"}
                            </Button>
                          )}
                          {/* Rejeitada e devolução compartilham o diálogo: na
                              rejeitada ele INICIA a devolução (o card 6 vira o
                              7); na devolução, gerencia a que já existe. */}
                          {(statusAtual === "declined" || statusAtual === "refund_scheduled") && (
                            <Button variant="danger" size="sm" onClick={() => abrir(proposta, setRefundDialogOpen)}>
                              Gerenciar Devolução
                            </Button>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}

              </div>
            </div>

            {/* Paginação — navegar, não acumular: são 8.700 propostas em
                "Pendentes de Assinatura" sozinha, e empilhá-las no DOM
                travaria a tela para mostrar o que ninguém vai rolar. */}
            {cardSelecionado && (pagina > 0 || temMaisPaginas) && (
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <span className="text-xs text-dim">
                  Página {pagina + 1} de {Math.max(1, Math.ceil(totalDaPagina / TAMANHO_PAGINA_PIO)).toLocaleString("pt-BR")}
                </span>
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setPagina((p) => Math.max(0, p - 1))}
                    disabled={pagina === 0 || lista.buscando}
                  >
                    Anterior
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setPagina((p) => p + 1)}
                    disabled={!temMaisPaginas || lista.buscando}
                  >
                    Próxima
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {selectedProposal && (
        <>
          <ProposalDetailDialog
            proposal={{
              ...selectedProposal,
              status: (proposalStatuses[selectedProposal.id] || selectedProposal.status) as StatusWorkflow,
            }}
            foto={selectedProposal.foto}
            open={detailDialogOpen}
            onClose={() => setDetailDialogOpen(false)}
          />
          <ResendLinkDialog
            proposal={{
              number: selectedProposal.number,
              insuredName: selectedProposal.insuredName,
              cpf: selectedProposal.cpf,
              value: selectedProposal.value,
              email: selectedProposal.email,
              phone: selectedProposal.phone,
            }}
            contatos={selectedProposal.foto ? canaisDeEnvio(selectedProposal.foto.contato) : undefined}
            open={resendDialogOpen}
            onClose={() => setResendDialogOpen(false)}
          />
          <DocumentUploadDialog
            proposalNumber={selectedProposal.number}
            insuredName={selectedProposal.insuredName}
            open={uploadDialogOpen}
            onClose={() => setUploadDialogOpen(false)}
          />
          <DPSLinkDialog
            proposalNumber={selectedProposal.number}
            insuredName={selectedProposal.insuredName}
            open={dpsDialogOpen}
            onClose={() => setDpsDialogOpen(false)}
          />
          <PaymentOptionsDialog
            proposal={{
              number: selectedProposal.number,
              insuredName: selectedProposal.insuredName,
              value: selectedProposal.value,
              paymentMethod: selectedProposal.paymentMethod || "boleto",
              email: selectedProposal.email,
              phone: selectedProposal.phone,
            }}
            open={paymentDialogOpen}
            onClose={() => setPaymentDialogOpen(false)}
          />
          <RefundManagementDialog
            proposal={{
              number: selectedProposal.number,
              insuredName: selectedProposal.insuredName,
              cpf: selectedProposal.cpf,
              product: selectedProposal.product,
              policy: selectedProposal.policy || "N/A",
              value: selectedProposal.value,
            }}
            open={refundDialogOpen}
            onClose={() => setRefundDialogOpen(false)}
            onStatusChange={() => {
              setProposalStatuses((prev) => ({ ...prev, [selectedProposal.id]: "refund_scheduled" }));
            }}
          />
        </>
      )}

      <SendAlertDialog proposals={filteredProposals} open={alertDialogOpen} onClose={() => setAlertDialogOpen(false)} />
    </div>
  );
}
