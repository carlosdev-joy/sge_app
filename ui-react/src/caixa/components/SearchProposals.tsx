// Busca de propostas da home no DS nativo — porte do SearchProposals shadcn
// (mesmos modos, mock e resultado). Desde a F8 o card "Workflow"
// (InlineWorkflow) voltou à home, na mesma posição da versão antiga.
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
import {
  buscarPropostas,
  ROTULO_STATUS,
  type ModoBusca,
  type Proposta,
} from "../lib/propostas";

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
  const [isSearching, setIsSearching] = useState(false);
  // null = ainda não pesquisou nesta sessão; [] = pesquisou e não achou. Os dois
  // casos precisam de telas diferentes — antes, busca sem resultado não dizia
  // absolutamente nada e parecia que o botão estava quebrado.
  const [searchResults, setSearchResults] = useState<Proposta[] | null>(null);
  const [detalhe, setDetalhe] = useState<Proposta | null>(null);

  const opcaoAtual = searchOptions.find((o) => o.value === selectedMode);

  const handleSearch = () => {
    if (!selectedMode || !searchValue.trim() || isSearching) return;
    setIsSearching(true);
    setSearchResults(null);
    // Atraso curto só para a POC parecer uma consulta de verdade.
    setTimeout(() => {
      setSearchResults(buscarPropostas(selectedMode, searchValue));
      setIsSearching(false);
    }, 600);
  };

  // Trocar o modo zera o que estava na tela: manter o resultado de um CPF
  // enquanto o campo já pergunta a agência confunde quem apresenta.
  const handleModeChange = (modo: string) => {
    setSelectedMode(modo as ModoBusca);
    setSearchValue("");
    setSearchResults(null);
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

      {/* Workflow inline (mesma posição da tela antiga) */}
      <InlineWorkflow />

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

      {/* Nada encontrado: dizer isso é o mínimo — o silêncio de antes fazia a
          tela parecer quebrada. */}
      {searchResults?.length === 0 && (
        <div className="bg-panel border border-edge rounded-lg py-8 px-8 text-center space-y-1">
          <p className="text-ink font-medium">Nenhuma proposta encontrada.</p>
          <p className="text-sm text-dim">
            Confira o {opcaoAtual?.campo.toLowerCase()} digitado ou tente outro modo de pesquisa.
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
                      {/* Chip laranja CAIXA para "Aguardando assinatura" (acento da POC) */}
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium text-white whitespace-nowrap ${
                          p.status === "pending_signature" ? "bg-[#F26B00]" : "bg-emerald-600"
                        }`}
                      >
                        {ROTULO_STATUS[p.status]}
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
