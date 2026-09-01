// Busca de propostas da home no DS nativo — porte do SearchProposals shadcn
// (mesmos modos, mock e resultado). O card "Workflow" (InlineWorkflow) voltou à
// home na F8; em 2026-09-01 desceu para DEPOIS do fluxo de busca (ver o
// comentário no ponto onde ele é renderizado).
// A classe .search-section marca a área destacada pelo Tutorial.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search, Edit, ExternalLink } from "lucide-react";
import InlineWorkflow from "./InlineWorkflow";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { RadioGroup, RadioItem } from "../../components/ui/RadioGroup";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "../../components/ui/Table";
import ProposalDetailDialog, { type ProposalOrq } from "./ProposalDetailDialog";
import { type ModoBusca } from "../lib/propostas";
import {
  dataBr,
  propostaDoPio,
  useBuscaPio,
  STATUS_POR_CARD,
} from "../lib/pio";
import {
  STATUS_COR,
  STATUS_LABEL_CURTO,
  type PropostaWorkflow,
  type StatusWorkflow,
} from "../lib/workflow";

const searchOptions: { value: ModoBusca; label: string; campo: string; placeholder: string }[] = [
  { value: "proposta", label: "Nº da Proposta", campo: "Nº da Proposta", placeholder: "80474130324227 ou 8047413032422-7" },
  { value: "cpf", label: "CPF", campo: "Nº do CPF", placeholder: "000.000.000-00" },
  { value: "agencia", label: "Agência/Data", campo: "Nº da Agência", placeholder: "474" },
  { value: "sev", label: "SEV/Data", campo: "Matrícula do SEV", placeholder: "0000122795-B" },
  { value: "sr", label: "SR/Data", campo: "Matrícula do SR", placeholder: "0000122795-B" },
];

export default function SearchProposals() {
  const navigate = useNavigate();
  const [selectedMode, setSelectedMode] = useState<ModoBusca | "">("");
  const [searchValue, setSearchValue] = useState<string>("");
  // O que foi de fato pesquisado — só muda no clique/Enter. Separado do que
  // está sendo digitado: sem isso a lista se refaria a cada tecla, e o "nenhuma
  // encontrada" piscaria no meio do CPF sendo digitado.
  const [consulta, setConsulta] = useState<{ modo: ModoBusca; termo: string } | null>(null);
  const [detalhe, setDetalhe] = useState<PropostaWorkflow | null>(null);

  const opcaoAtual = searchOptions.find((o) => o.value === selectedMode);

  // A busca lê a carga do PIO, nas TRÊS tabelas de detalhe. Era um filtro sobre
  // 20 propostas de exemplo em memória até 2026-09-01: a lógica estava certa
  // (comparava dígitos, ignorava máscara) mas a fonte tinha 20 linhas, então
  // nenhum número real aparecia e a busca parecia quebrada.
  const busca = useBuscaPio(consulta?.modo ?? "", consulta?.termo ?? "", true);
  const isSearching = busca.isFetching;

  const itens = busca.data?.itens ?? [];
  const searchResults: PropostaWorkflow[] | null = !consulta || busca.isPending
    ? null
    : itens.map((item) =>
        propostaDoPio(item, STATUS_POR_CARD[item.card ?? ""] ?? "pending_signature"));

  const handleSearch = () => {
    if (!selectedMode || !searchValue.trim() || isSearching) return;
    setConsulta({ modo: selectedMode, termo: searchValue.trim() });
  };

  // Trocar o modo zera o que estava na tela: manter o resultado de um CPF
  // enquanto o campo já pergunta a agência confunde quem apresenta.
  const handleModeChange = (modo: string) => {
    setSelectedMode(modo as ModoBusca);
    setSearchValue("");
    setConsulta(null);
  };

  return (
    <div className="space-y-6 search-section">
      <div className="flex items-center gap-3">
        <Search className="h-5 w-5 text-[#1A5FA8] dark:text-blue-400" />
        <h2 className="text-xl font-semibold text-[#1A5FA8] dark:text-blue-400">Pesquisar Propostas</h2>
      </div>

      <div className="bg-panel border border-edge rounded-xl p-6">
        <p className="text-sm font-semibold text-ink mb-4">Como deseja realizar a busca?</p>
        <RadioGroup value={selectedMode} onValueChange={handleModeChange} label="Modo de pesquisa">
          <div className="flex flex-wrap gap-6">
            {searchOptions.map((option) => (
              <RadioItem key={option.value} value={option.value} label={option.label} />
            ))}
          </div>
        </RadioGroup>
      </div>

      {!selectedMode && (
        <div className="bg-panel border border-edge rounded-lg py-6 px-8 text-center">
          <p className="text-[#1A5FA8] dark:text-blue-400 font-medium">
            Por favor, selecione o modo de pesquisa.
          </p>
        </div>
      )}

      {/* Um único campo para TODOS os modos. Antes só "proposta" tinha busca
          ligada — o campo de CPF não tinha value/onChange nem o botão tinha
          onClick, e agência/SEV/SR não tinham campo nenhum. */}
      {opcaoAtual && (
        <div className="space-y-2">
          <label htmlFor="busca-caixa" className="text-sm font-medium text-ink">
            {opcaoAtual.campo}
          </label>
          <div className="flex gap-4">
            <div className="flex-1">
              <Input
                id="busca-caixa"
                placeholder={opcaoAtual.placeholder}
                className="w-full"
                value={searchValue}
                onChange={(e) => setSearchValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSearch();
                }}
              />
            </div>
            <Button
              variant="primary"
              onClick={handleSearch}
              disabled={isSearching || !searchValue.trim()}
              loading={isSearching}
              className="px-8"
            >
              {isSearching ? "Buscando..." : "Pesquisar"}
            </Button>
          </div>
          <p className="text-xs text-dim">
            Pontuação é ignorada: com ou sem ponto, traço ou barra o resultado é o mesmo.
          </p>
        </div>
      )}

      {/* A carga não conseguiu ser lida: nem "achou" nem "não achou" — a lista
          é DESCONHECIDA, e dizer isso evita concluir que a proposta não existe. */}
      {consulta && !busca.isPending && !busca.data?.disponivel && (
        <div className="bg-panel border border-edge rounded-lg py-8 px-8 text-center space-y-1">
          <p className="text-red-600 dark:text-red-400 font-medium">
            Não foi possível ler a carga do PIO.
          </p>
          <p className="text-sm text-dim">
            O resultado não está vazio — ele é desconhecido. Tente novamente em instantes.
          </p>
        </div>
      )}

      {/* Nada encontrado. Além de dizer isso, a tela precisa dizer o QUE ela
          procurou: a carga só tem os três cards e os últimos 30 dias de venda,
          então uma proposta emitida, rejeitada ou mais antiga não está aqui —
          e sem essa frase quem procura conclui que a busca está quebrada. */}
      {searchResults?.length === 0 && busca.data?.disponivel && (
        <div className="bg-panel border border-edge rounded-lg py-8 px-8 text-center space-y-2">
          <p className="text-ink font-medium">Nenhuma proposta encontrada.</p>
          <p className="text-sm text-dim">
            Confira o {opcaoAtual?.campo.toLowerCase()} digitado ou tente outro modo de pesquisa.
          </p>
          <p className="text-xs text-dim max-w-lg mx-auto">
            A busca cobre as propostas da carga do PIO, e o período muda com o
            estado da proposta: pendentes de assinatura, pendentes de pagamento,
            assinadas e pagas e devoluções de prêmio saem dos <strong>últimos 30
            dias de venda</strong>; em crítica, emitidas, rejeitadas e
            sensibilizadas, do <strong>ano corrente</strong>
            {busca.data?.referencia ? `. Carga de ${dataBr(busca.data.referencia)}` : ""}.
          </p>
        </div>
      )}

      {/* Resultado da busca */}
      {searchResults && searchResults.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm text-dim">
            {searchResults.length === 1
              ? "1 proposta encontrada"
              : `${searchResults.length} propostas encontradas`}
          </p>
          <div className="bg-panel border border-edge rounded-lg overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nº Proposta</TableHead>
                  <TableHead>CPF</TableHead>
                  <TableHead>Cliente</TableHead>
                  <TableHead>Produto</TableHead>
                  <TableHead>Prêmio</TableHead>
                  <TableHead>Data Venda</TableHead>
                  <TableHead>Agência</TableHead>
                  <TableHead>Matrícula</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {searchResults.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell>
                      <button
                        onClick={() => setDetalhe(p)}
                        className="text-[#1A5FA8] dark:text-blue-400 hover:underline font-medium"
                      >
                        {p.number}
                      </button>
                    </TableCell>
                    <TableCell>{p.cpf}</TableCell>
                    <TableCell>{p.insuredName}</TableCell>
                    <TableCell>{p.product}</TableCell>
                    <TableCell>{p.value}</TableCell>
                    <TableCell>{p.date}</TableCell>
                    <TableCell>{p.agency}</TableCell>
                    <TableCell>{p.indicatorId}</TableCell>
                    <TableCell>
                      {/* O status é o CARD de onde a linha veio — é a única
                          informação de estado que a carga tem. Cor e rótulo
                          saem de `lib/workflow.ts`, os mesmos do card
                          correspondente: a mesma proposta não pode ter uma cor
                          na busca e outra no Workflow. */}
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium text-white whitespace-nowrap ${
                          STATUS_COR[p.status as StatusWorkflow] ?? "bg-slate-500"
                        }`}
                      >
                        {STATUS_LABEL_CURTO[p.status as StatusWorkflow] ?? p.status}
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        {p.status === "pending_signature" && (
                          <Button variant="ghost" size="sm" title="Editar" aria-label="Editar proposta">
                            <Edit className="h-4 w-4" />
                          </Button>
                        )}
                        {/* As duas telas conversando: leva ao Monitoramento
                            Tático já no status desta proposta. */}
                        <Button
                          variant="ghost"
                          size="sm"
                          title="Abrir no Monitoramento Tático de Emissão"
                          aria-label={`Abrir ${p.number} no monitoramento`}
                          onClick={() => navigate(`/caixa-seguro/acompanhamento/${p.status}`)}
                        >
                          <ExternalLink className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      )}

      {/* Workflow inline. Fica DEPOIS do fluxo de busca inteiro (campo →
          "nenhuma encontrada" → tabela) desde 2026-09-01, a pedido do usuário:
          com ele no meio, quem escolhia o modo lá em cima tinha de rolar a
          página toda para digitar, e rolar de novo para ver o resultado. Antes
          disso ele reproduzia a posição da tela antiga (F8) — mover foi uma
          decisão explícita, não arrumação. */}
      <InlineWorkflow />

      {/* Detalhe da proposta */}
      {detalhe && (
        <ProposalDetailDialog
          proposal={detalhe as ProposalOrq}
          open
          onClose={() => setDetalhe(null)}
        />
      )}
    </div>
  );
}
