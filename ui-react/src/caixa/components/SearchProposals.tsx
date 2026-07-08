import { Search, Edit, Loader2 } from "lucide-react";
import { RadioGroup, RadioGroupItem } from "./ui/radio-group";
import { Label } from "./ui/label";
import { Input } from "./ui/input";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Badge } from "./ui/badge";
import { useState } from "react";
import InlineWorkflow from "./InlineWorkflow";
import ProposalDetailDialog from "./ProposalDetailDialog";

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

const SearchProposals = () => {
  const [selectedMode, setSelectedMode] = useState<string>("");
  const [searchValue, setSearchValue] = useState<string>("");
  const [isSearching, setIsSearching] = useState(false);
  const [searchResult, setSearchResult] = useState<ProposalResult | null>(null);
  const [isDetailDialogOpen, setIsDetailDialogOpen] = useState(false);

  const searchOptions = [
    { value: "proposta", label: "Nº da Proposta" },
    { value: "cpf", label: "CPF" },
    { value: "agencia", label: "Agência/Data" },
    { value: "sev", label: "SEV/Data" },
    { value: "sr", label: "SR/Data" },
  ];

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

  const handleOpenDetail = () => {
    setIsDetailDialogOpen(true);
  };

  // Convert search result to proposal format for detail dialog
  const getProposalDetail = () => {
    if (!searchResult) return null;
    
    return {
      id: "1",
      number: searchResult.number,
      insuredName: searchResult.client,
      date: searchResult.saleDate,
      status: "pending_signature" as const,
      value: searchResult.premium,
      indicatorId: searchResult.registration,
      agency: searchResult.agency,
      cpf: searchResult.cpf,
      product: searchResult.product,
      phone: "(11) 98765-4321",
      email: "joyce.formigoni@email.com",
    };
  };

  const getStatusBadgeColor = (status: string) => {
    if (status === "Aguardando assinatura") {
      return "bg-[hsl(var(--orange))] text-white hover:bg-[hsl(var(--orange))]/90";
    }
    return "bg-[hsl(var(--green))] text-white";
  };

  return (
    <div className="space-y-6 search-section">
      <div className="flex items-center gap-3">
        <Search className="h-5 w-5 text-primary" />
        <h2 className="text-xl font-semibold text-primary">Pesquisar Propostas</h2>
      </div>

      <div className="border-2 border-dashed border-primary rounded-lg p-6 bg-white">
        <Label className="text-primary font-semibold mb-4 block">
          Como deseja realizar a busca?
        </Label>
        
        <RadioGroup
          value={selectedMode}
          onValueChange={setSelectedMode}
          className="flex flex-wrap gap-6"
        >
          {searchOptions.map((option) => (
            <div key={option.value} className="flex items-center space-x-2">
              <RadioGroupItem
                value={option.value}
                id={option.value}
                className="border-primary text-primary"
              />
              <Label
                htmlFor={option.value}
                className="text-sm font-normal cursor-pointer text-foreground"
              >
                {option.label}
              </Label>
            </div>
          ))}
        </RadioGroup>
      </div>

      {!selectedMode && (
        <div className="bg-white rounded-lg py-6 px-8 text-center">
          <p className="text-primary font-medium">
            Por favor, selecione o modo de pesquisa.
          </p>
        </div>
      )}

      {/* Inline Workflow */}
      <InlineWorkflow />

      {selectedMode === "proposta" && (
        <div className="space-y-4">
          <Label htmlFor="proposta" className="text-primary font-medium">
            Nº da Proposta
          </Label>
          <div className="flex gap-4">
            <Input
              id="proposta"
              placeholder="00000000000000-0"
              className="flex-1"
              value={searchValue}
              onChange={(e) => setSearchValue(e.target.value)}
            />
            <Button 
              className="bg-[hsl(var(--orange))] hover:bg-[hsl(var(--orange))]/90 text-white px-8"
              onClick={handleSearch}
              disabled={isSearching}
            >
              {isSearching ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Buscando...
                </>
              ) : (
                "Pesquisar"
              )}
            </Button>
          </div>
        </div>
      )}

      {selectedMode === "cpf" && (
        <div className="space-y-4">
          <Label htmlFor="cpf" className="text-primary font-medium">
            Nº do CPF
          </Label>
          <div className="flex gap-4">
            <Input
              id="cpf"
              placeholder="000.000.000-00"
              className="flex-1"
            />
            <Button className="bg-[hsl(var(--orange))] hover:bg-[hsl(var(--orange))]/90 text-white px-8">
              Pesquisar
            </Button>
          </div>
        </div>
      )}

      {/* Search Result */}
      {searchResult && (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-primary text-primary-foreground">
                  <th className="px-4 py-3 text-left text-sm font-semibold">Nº Proposta</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">CPF</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Cliente</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Produto</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Prêmio</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Data Venda</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Agência</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Matrícula</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Status</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">Ações</th>
                </tr>
              </thead>
              <tbody>
                 <tr className="border-b hover:bg-muted/50 transition-colors">
                  <td className="px-4 py-3 text-sm">
                    <button 
                      onClick={handleOpenDetail}
                      className="text-primary hover:underline font-medium"
                    >
                      {searchResult.number}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-sm">{searchResult.cpf}</td>
                  <td className="px-4 py-3 text-sm">{searchResult.client}</td>
                  <td className="px-4 py-3 text-sm">{searchResult.product}</td>
                  <td className="px-4 py-3 text-sm">{searchResult.premium}</td>
                  <td className="px-4 py-3 text-sm">{searchResult.saleDate}</td>
                  <td className="px-4 py-3 text-sm">{searchResult.agency}</td>
                  <td className="px-4 py-3 text-sm">{searchResult.registration}</td>
                  <td className="px-4 py-3 text-sm">
                    <Badge className={getStatusBadgeColor(searchResult.status)}>
                      {searchResult.status}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-sm">
                    {searchResult.status === "Aguardando assinatura" && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-8 w-8 p-0"
                        title="Editar"
                      >
                        <Edit className="h-4 w-4" />
                      </Button>
                    )}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Proposal Detail Dialog */}
      {searchResult && getProposalDetail() && (
        <ProposalDetailDialog
          proposal={getProposalDetail()!}
          open={isDetailDialogOpen}
          onOpenChange={setIsDetailDialogOpen}
        />
      )}
    </div>
  );
};

export default SearchProposals;
