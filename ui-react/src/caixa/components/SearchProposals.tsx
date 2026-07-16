// Busca de propostas da home no DS nativo — porte do SearchProposals shadcn
// (mesmos modos, mock e resultado). Desde a F8 o card "Workflow"
// (InlineWorkflow) voltou à home, na mesma posição da versão antiga.
// A classe .search-section marca a área destacada pelo Tutorial.
import { useState } from "react";
import { Search, Edit } from "lucide-react";
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

interface ProposalResult {
  number: string;
  cpf: string;
  client: string;
  product: string;
  premium: string;
  saleDate: string;
  agency: string;
  registration: string;
  status: string;
}

const searchOptions = [
  { value: "proposta", label: "Nº da Proposta" },
  { value: "cpf", label: "CPF" },
  { value: "agencia", label: "Agência/Data" },
  { value: "sev", label: "SEV/Data" },
  { value: "sr", label: "SR/Data" },
];

// Mesmo mock da tela original — só a proposta 80316460327404 retorna resultado.
const mockProposalData: ProposalResult = {
  number: "80316460327404",
  cpf: "397.750.878-48",
  client: "JOYCE DA SILVA FORMIGONI",
  product: "Vida Mulher",
  premium: "R$ 1.428,92",
  saleDate: "23/10/2025",
  agency: "316",
  registration: "106562-2",
  status: "Aguardando assinatura",
};

export default function SearchProposals() {
  const [selectedMode, setSelectedMode] = useState<string>("");
  const [searchValue, setSearchValue] = useState<string>("");
  const [isSearching, setIsSearching] = useState(false);
  const [searchResult, setSearchResult] = useState<ProposalResult | null>(null);
  const [isDetailDialogOpen, setIsDetailDialogOpen] = useState(false);

  const handleSearch = () => {
    if (searchValue === "80316460327404") {
      setIsSearching(true);
      setSearchResult(null);
      setTimeout(() => {
        setSearchResult(mockProposalData);
        setIsSearching(false);
      }, 1500);
    }
  };

  // Resultado da busca no shape que o diálogo de detalhe consome.
  const getProposalDetail = (): ProposalOrq | null => {
    if (!searchResult) return null;
    return {
      id: "1",
      number: searchResult.number,
      insuredName: searchResult.client,
      date: searchResult.saleDate,
      status: "pending_signature",
      value: searchResult.premium,
      indicatorId: searchResult.registration,
      agency: searchResult.agency,
      cpf: searchResult.cpf,
      product: searchResult.product,
      phone: "(11) 98765-4321",
      email: "joyce.formigoni@email.com",
    };
  };

  const proposalDetail = getProposalDetail();

  return (
    <div className="space-y-6 search-section">
      <div className="flex items-center gap-3">
        <Search className="h-5 w-5 text-[#1A5FA8] dark:text-blue-400" />
        <h2 className="text-xl font-semibold text-[#1A5FA8] dark:text-blue-400">Pesquisar Propostas</h2>
      </div>

      <div className="bg-panel border border-edge rounded-xl p-6">
        <p className="text-sm font-semibold text-ink mb-4">Como deseja realizar a busca?</p>
        <RadioGroup value={selectedMode} onValueChange={setSelectedMode} label="Modo de pesquisa">
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

      {selectedMode === "proposta" && (
        <div className="space-y-2">
          <label htmlFor="busca-proposta" className="text-sm font-medium text-ink">
            Nº da Proposta
          </label>
          <div className="flex gap-4">
            <div className="flex-1">
              <Input
                id="busca-proposta"
                placeholder="00000000000000-0"
                className="w-full"
                value={searchValue}
                onChange={(e) => setSearchValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !isSearching) handleSearch();
                }}
              />
            </div>
            <Button variant="primary" onClick={handleSearch} disabled={isSearching} loading={isSearching} className="px-8">
              {isSearching ? "Buscando..." : "Pesquisar"}
            </Button>
          </div>
        </div>
      )}

      {selectedMode === "cpf" && (
        <div className="space-y-2">
          <label htmlFor="busca-cpf" className="text-sm font-medium text-ink">
            Nº do CPF
          </label>
          <div className="flex gap-4">
            <div className="flex-1">
              <Input id="busca-cpf" placeholder="000.000.000-00" className="w-full" />
            </div>
            <Button variant="primary" className="px-8">
              Pesquisar
            </Button>
          </div>
        </div>
      )}

      {/* Resultado da busca */}
      {searchResult && (
        <div className="bg-panel border border-edge rounded-lg overflow-hidden">
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
              <TableRow>
                <TableCell>
                  <button
                    onClick={() => setIsDetailDialogOpen(true)}
                    className="text-[#1A5FA8] dark:text-blue-400 hover:underline font-medium"
                  >
                    {searchResult.number}
                  </button>
                </TableCell>
                <TableCell>{searchResult.cpf}</TableCell>
                <TableCell>{searchResult.client}</TableCell>
                <TableCell>{searchResult.product}</TableCell>
                <TableCell>{searchResult.premium}</TableCell>
                <TableCell>{searchResult.saleDate}</TableCell>
                <TableCell>{searchResult.agency}</TableCell>
                <TableCell>{searchResult.registration}</TableCell>
                <TableCell>
                  {/* Chip laranja CAIXA para "Aguardando assinatura" (acento da POC) */}
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium text-white whitespace-nowrap ${
                      searchResult.status === "Aguardando assinatura" ? "bg-[#F26B00]" : "bg-emerald-600"
                    }`}
                  >
                    {searchResult.status}
                  </span>
                </TableCell>
                <TableCell>
                  {searchResult.status === "Aguardando assinatura" && (
                    <Button variant="ghost" size="sm" title="Editar" aria-label="Editar proposta">
                      <Edit className="h-4 w-4" />
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      )}

      {/* Detalhe da proposta */}
      {proposalDetail && (
        <ProposalDetailDialog
          proposal={proposalDetail}
          open={isDetailDialogOpen}
          onClose={() => setIsDetailDialogOpen(false)}
        />
      )}
    </div>
  );
}
