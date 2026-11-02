// "Workflow de Propostas" (gaveta) no DS nativo — cards de status clicáveis,
// filtro e lista. O componente traz o próprio botão-gatilho, como o original.
//
// A sequência, os rótulos e as propostas vêm de `lib/workflow.ts`, a MESMA
// fonte do card colapsável da home (InlineWorkflow). Até 2026-08-31 este
// painel tinha lista e mock PRÓPRIOS — 9 status que não existiam em nenhum
// outro lugar do sistema ("Ag. Link Pagamento", "Cotação", "Rascunho") sobre
// 13 propostas que não eram as da tela. Duas verdades na mesma tela; com os
// dados reais entrando, tinha que virar uma.
import { useState } from "react";
import { FileText } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Sheet } from "../../components/ui/Sheet";
import { Select } from "../../components/ui/Input";
import {
  contarPorStatus,
  propostasWorkflow,
  SEQUENCIA_WORKFLOW,
  STATUS_COR,
  STATUS_LABEL_CURTO,
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
  STATUS_CARD3,
  STATUS_CARD4,
  STATUS_CARD5,
  STATUS_CARD6,
  STATUS_CARD7,
  STATUS_CARD8,
  seloDaProposta,
  STATUS_DE_FOTO,
  useResumoCard1,
  usePropostasCard1,
  dataHoraBr,
} from "../lib/pioCard1";
import { useResumoCard2, usePropostasCard2 } from "../lib/pioCard2";
import { useResumoCard3, usePropostasCard3 } from "../lib/pioCard3";
import { useResumoCard4, usePropostasCard4 } from "../lib/pioCard4";
import { useResumoCard5, usePropostasCard5 } from "../lib/pioCard5";
import { useResumoCard6, usePropostasCard6 } from "../lib/pioCard6";
import { useResumoCard7, usePropostasCard7 } from "../lib/pioCard7";
import { useResumoCard8, usePropostasCard8 } from "../lib/pioCard8";
import DevolucaoSubcards from "./DevolucaoSubcards";
import type { SituacaoDevolucao } from "../lib/workflow";
import Card1Valor from "./Card1Valor";

// Mesma regra do card inline: as de exemplo somem dos status que já leem a
// carga, para não conviverem com dado real na mesma lista.
const PROPOSTAS_DE_EXEMPLO = propostasWorkflow.filter((p) => !ORIGEM_PIO[p.status]);

export default function ProposalWorkflowSheet() {
  const [aberto, setAberto] = useState(false);
  const [selectedStatus, setSelectedStatus] = useState<string>("all");
  const [pagina, setPagina] = useState(0);
  /** Card 7: o sub-card escolhido. Sem ele NÃO há lista (o card principal só abre os 3 sub-cards). */
  const [devolucao, setDevolucao] = useState<SituacaoDevolucao | null>(null);

  const contagens = useContagensPio();
  const cardSelecionado = ORIGEM_PIO[selectedStatus as StatusWorkflow];
  // `aberto` no lugar do enabled: a gaveta fechada não consulta milhares de linhas.
  // Card 1 = foto diária; os outros sete, a carga legada (ver InlineWorkflow).
  // Cards 1 e 2 leem a FOTO diária (agregado para o número, fato para a lista);
  // os outros seis seguem na carga legada. O hook legado recebe `undefined` nos
  // cards de foto, o que o desliga — a lista não é pedida às duas fontes.
  const emCard1 = selectedStatus === STATUS_CARD1;
  const emCard2 = selectedStatus === STATUS_CARD2;
  const emCard3 = selectedStatus === STATUS_CARD3;
  const emCard4 = selectedStatus === STATUS_CARD4;
  const emCard5 = selectedStatus === STATUS_CARD5;
  const emCard6 = selectedStatus === STATUS_CARD6;
  const emCard7 = selectedStatus === STATUS_CARD7;
  const emCard8 = selectedStatus === STATUS_CARD8;
  const emFoto = emCard1 || emCard2 || emCard3 || emCard4 || emCard5 || emCard6 || emCard7 || emCard8;
  /** Card 7 sem sub-card escolhido: não há lista nem aviso de lista a mostrar. */
  const semLista = emCard7 && devolucao === null;
  const resumoCard1 = useResumoCard1();
  const resumoCard2 = useResumoCard2();
  const resumoCard3 = useResumoCard3();
  const resumoCard4 = useResumoCard4();
  const resumoCard5 = useResumoCard5();
  const resumoCard6 = useResumoCard6();
  const resumoCard7 = useResumoCard7();
  const resumoCard8 = useResumoCard8();
  const paginaPio = usePropostasPio(emFoto ? undefined : cardSelecionado, aberto, pagina, "");
  const fotoCard1 = usePropostasCard1(emCard1 && aberto, pagina, resumoCard1.data?.referencia);
  const fotoCard2 = usePropostasCard2(emCard2 && aberto, pagina, resumoCard2.data?.referencia);
  const fotoCard3 = usePropostasCard3(emCard3 && aberto, pagina, resumoCard3.data?.referencia);
  const fotoCard4 = usePropostasCard4(emCard4 && aberto, pagina, resumoCard4.data?.referencia);
  const fotoCard5 = usePropostasCard5(emCard5 && aberto, pagina, resumoCard5.data?.referencia);
  const fotoCard6 = usePropostasCard6(emCard6 && aberto, pagina, resumoCard6.data?.referencia);
  const fotoCard7 = usePropostasCard7(emCard7 && aberto, pagina, resumoCard7.data?.referencia, devolucao);
  const fotoCard8 = usePropostasCard8(emCard8 && aberto, pagina, resumoCard8.data?.referencia);
  // Resumo e página do card selecionado (os três hooks rodam sempre: ordem fixa).
  const resumos = { [STATUS_CARD1]: resumoCard1, [STATUS_CARD2]: resumoCard2, [STATUS_CARD3]: resumoCard3, [STATUS_CARD4]: resumoCard4, [STATUS_CARD5]: resumoCard5, [STATUS_CARD6]: resumoCard6, [STATUS_CARD7]: resumoCard7, [STATUS_CARD8]: resumoCard8 } as Record<string, typeof resumoCard1>;
  const fotos = { [STATUS_CARD1]: fotoCard1, [STATUS_CARD2]: fotoCard2, [STATUS_CARD3]: fotoCard3, [STATUS_CARD4]: fotoCard4, [STATUS_CARD5]: fotoCard5, [STATUS_CARD6]: fotoCard6, [STATUS_CARD7]: fotoCard7, [STATUS_CARD8]: fotoCard8 } as Record<string, typeof fotoCard1>;
  const lista = listaDoCard(
    emFoto, paginaPio,
    (item) => propostaDoPio(item, selectedStatus as StatusWorkflow),
    resumos[selectedStatus] ?? resumoCard1, fotos[selectedStatus] ?? fotoCard1,
    selectedStatus as StatusWorkflow);

  const reais: Partial<Record<StatusWorkflow, number>> = {};
  if (contagens.data?.disponivel) {
    const porCard = contagemPorCard(contagens.data.cards);
    (Object.entries(ORIGEM_PIO) as [StatusWorkflow, string][]).forEach(
      ([status, card]) => {
        reais[status] = porCard.get(card) ?? 0;
      });
  }
  // Quantidade do Card 1 = a da foto; sem ela, nunca a contagem legada.
  delete reais[STATUS_CARD1];
  if (resumoCard1.data?.disponivel && resumoCard1.data.referencia) {
    reais[STATUS_CARD1] = resumoCard1.data.quantidade;
  }
  // Idem o Card 2: a quantidade é a da foto, nunca a contagem legada.
  delete reais[STATUS_CARD2];
  if (resumoCard2.data?.disponivel && resumoCard2.data.referencia) {
    reais[STATUS_CARD2] = resumoCard2.data.quantidade;
  }
  // Idem o Card 3.
  delete reais[STATUS_CARD3];
  if (resumoCard3.data?.disponivel && resumoCard3.data.referencia) {
    reais[STATUS_CARD3] = resumoCard3.data.quantidade;
  }
  // Idem o Card 4 (quantidade = CERTIFICADOS, nunca linhas de crítica).
  delete reais[STATUS_CARD4];
  if (resumoCard4.data?.disponivel && resumoCard4.data.referencia) {
    reais[STATUS_CARD4] = resumoCard4.data.quantidade;
  }
  // Idem o Card 5 (quantidade = CONTRATOS emitidos na foto).
  delete reais[STATUS_CARD5];
  if (resumoCard5.data?.disponivel && resumoCard5.data.referencia) {
    reais[STATUS_CARD5] = resumoCard5.data.quantidade;
  }
  // Idem o Card 6 (quantidade = CERTIFICADOS rejeitados, nunca linhas de motivo).
  delete reais[STATUS_CARD6];
  if (resumoCard6.data?.disponivel && resumoCard6.data.referencia) {
    reais[STATUS_CARD6] = resumoCard6.data.quantidade;
  }
  // Idem o Card 7 (quantidade = CONTRATOS com devolução, nunca a contagem legada).
  delete reais[STATUS_CARD7];
  if (resumoCard7.data?.disponivel && resumoCard7.data.referencia) {
    reais[STATUS_CARD7] = resumoCard7.data.quantidade;
  }
  // Idem o Card 8 (quantidade = IDENTIFICAÇÕES com último movimento, nunca a contagem legada).
  delete reais[STATUS_CARD8];
  if (resumoCard8.data?.disponivel && resumoCard8.data.referencia) {
    reais[STATUS_CARD8] = resumoCard8.data.quantidade;
  }

  const contagem = contarPorStatus(PROPOSTAS_DE_EXEMPLO, {}, reais);

  const selecionar = (status: string) => {
    setSelectedStatus(status);
    setPagina(0);
    setDevolucao(null);
  };

  const escolherDevolucao = (situacao: SituacaoDevolucao | null) => {
    setDevolucao(situacao);
    setPagina(0);
  };

  const filteredProposals = cardSelecionado
    ? lista.propostas
    : selectedStatus === "all"
      ? PROPOSTAS_DE_EXEMPLO
      : PROPOSTAS_DE_EXEMPLO.filter((p) => p.status === selectedStatus);

  const totalDaPagina = lista.total;
  const temMaisPaginas = cardSelecionado
    ? (pagina + 1) * TAMANHO_PAGINA_PIO < totalDaPagina
    : false;

  return (
    <>
      <Button variant="secondary" size="md" onClick={() => setAberto(true)}>
        <FileText size={16} />
        Workflow
      </Button>

      <Sheet open={aberto} onClose={() => setAberto(false)} title="Workflow de Propostas" widthClass="max-w-2xl">
        {/* Cards de status (clicáveis: filtram a lista). Duas colunas porque
            são OITO cards: em três, o último fica sozinho na linha de baixo. */}
        <div className="grid grid-cols-2 gap-2 mb-6">
          {SEQUENCIA_WORKFLOW.map((etapa) => (
            <button
              key={etapa.value}
              onClick={() => selecionar(etapa.value)}
              className={`${STATUS_COR[etapa.value]} rounded-lg p-3 text-white text-center cursor-pointer transition-all hover:-translate-y-0.5 hover:shadow-lg ${
                selectedStatus === etapa.value ? "ring-2 ring-offset-2 ring-[#1A5FA8] ring-offset-panel" : ""
              }`}
            >
              <div className="text-[11px] font-semibold uppercase tracking-wide text-white/90 mb-1 leading-tight">{etapa.label}</div>
              {/* "…" enquanto lê e "—" quando não conseguiu: zero seria uma
                  resposta, e nenhuma das duas situações é uma resposta. */}
              <div className="text-2xl font-bold tracking-tight">
                {STATUS_DE_FOTO.includes(etapa.value)
                  ? <Card1Valor resumo={resumos[etapa.value]} tom="colorido" destaque="text-xl" />
                  : ORIGEM_PIO[etapa.value] && contagens.isPending
                  ? "…"
                  : ORIGEM_PIO[etapa.value] && !contagens.data?.disponivel
                    ? <span title="não foi possível ler a carga do PIO">—</span>
                    : contagem[etapa.value].toLocaleString("pt-BR")}
              </div>
            </button>
          ))}
        </div>

        {/* Filtro */}
        <div className="mb-4">
          <Select value={selectedStatus} onChange={(e) => selecionar(e.target.value)} aria-label="Filtrar por status" className="w-full">
            <option value="all">Todos os Status ({contagem.all})</option>
            {SEQUENCIA_WORKFLOW.map((etapa) => (
              <option key={etapa.value} value={etapa.value}>
                {etapa.label} ({contagem[etapa.value]})
              </option>
            ))}
          </Select>
        </div>

        {emCard7 && (
          <DevolucaoSubcards resumo={resumoCard7} selecionada={devolucao} onSelecionar={escolherDevolucao} />
        )}

        {/* Procedência: número sem data de carga não distingue "esvaziou" de
            "a carga das 07:30 não rodou". */}
        {cardSelecionado && !semLista && lista.disponivel && !lista.carregando && !lista.detalheIndisponivel && (lista.referencia || !lista.deFoto) && (
          <p className="text-xs text-dim mb-3">
            {totalDaPagina.toLocaleString("pt-BR")} proposta{totalDaPagina === 1 ? "" : "s"} {lista.deFoto ? "na foto" : "na carga"}
            {lista.referencia ? ` de ${dataBr(lista.referencia)}` : ""}
            {!semLista && lista.deFoto && lista.atualizacao ? `, publicada em ${dataHoraBr(lista.atualizacao)}` : ""}
            {filteredProposals.length > 0 && (
              <> · mostrando {filteredProposals.length.toLocaleString("pt-BR")}, {lista.ordem === "identificacao" ? "por nº de identificação" : "as mais antigas primeiro"}</>
            )}
          </p>
        )}
        {!semLista && lista.deFoto && lista.disponivel && !lista.carregando && !lista.referencia && (
          <p className="text-xs text-dim mb-3">Ainda não há foto publicada para {STATUS_LABEL_CURTO[selectedStatus as StatusWorkflow]}; não há número nem lista a mostrar.</p>
        )}
        {!semLista && lista.deFoto && lista.disponivel && lista.detalheIndisponivel && (
          <p className="text-xs text-dim mb-3">
            O detalhe das propostas desta data já saiu da retenção. O número do card continua válido.
          </p>
        )}
        {cardSelecionado && !semLista && lista.carregando && (
          <p className="text-xs text-dim mb-3">Consultando {lista.deFoto ? "a foto" : "a carga"} do PIO…</p>
        )}
        {cardSelecionado && !semLista && !lista.carregando && !lista.disponivel && (
          <p className="text-xs text-red-600 dark:text-red-400 mb-3">
            Não foi possível ler {lista.deFoto ? "a foto" : "a carga"} do PIO. A lista não está vazia — ela é desconhecida.
          </p>
        )}
        {selectedStatus === "all" && Object.keys(ORIGEM_PIO).length > 0 && (
          <p className="text-xs text-dim mb-3">
            As propostas com dados reais aparecem ao selecionar o card correspondente.
          </p>
        )}

        {/* Lista */}
        <div className="flex flex-col gap-3">
          {filteredProposals.map((proposta) => (
            <div key={proposta.id} className="bg-canvas border border-edge rounded-lg p-4 hover:shadow-md transition-shadow">
              <div className="flex justify-between items-start mb-2 gap-3">
                <div>
                  <div className="font-semibold text-lg text-ink">{proposta.insuredName}</div>
                  <div className="text-sm text-dim">Proposta: {proposta.number}</div>
                </div>
                {(() => {
                  const selo = seloDaProposta(
                    proposta, STATUS_COR[proposta.status as StatusWorkflow] ?? "bg-slate-500",
                    STATUS_LABEL_CURTO[proposta.status as StatusWorkflow] ?? proposta.status);
                  return (
                    <span
                      className={`${selo.classe} rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap`}
                      data-testid="selo-status"
                      data-tom={proposta.foto?.emitida?.tom}
                    >
                      {selo.rotulo}
                    </span>
                  );
                })()}
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm text-ink">
                <div>
                  <span className="text-dim">Produto:</span> {proposta.product}
                </div>
                <div>
                  <span className="text-dim">Valor:</span> {proposta.value}
                </div>
                <div>
                  <span className="text-dim">Região:</span> {proposta.region}
                </div>
                <div>
                  <span className="text-dim">Corretor:</span> {proposta.broker}
                </div>
                {proposta.daysInPending > 0 && (
                  <div className="col-span-2 text-red-600 dark:text-red-400 font-medium">
                    ⏱️ {proposta.daysInPending} dias em pendência
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Paginação — navegar, não acumular: são milhares de propostas por
            categoria, e empilhá-las no DOM travaria a gaveta. */}
        {cardSelecionado && (pagina > 0 || temMaisPaginas) && (
          <div className="flex items-center justify-between gap-3 flex-wrap mt-4">
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
      </Sheet>
    </>
  );
}
