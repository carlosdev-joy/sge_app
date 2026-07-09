import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import MenuButton from "../components/MenuButton";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { Checkbox } from "../components/ui/checkbox";
import { Badge } from "../components/ui/badge";
import { Download, Search, ArrowLeft } from "lucide-react";
import { useToast } from "../hooks/use-toast";
import * as XLSX from "xlsx";
import LeoAssistant from "../components/LeoAssistant";

interface PortabilityRequest {
  id: string;
  dias: number;
  fip: string;
  portabilidade: string;
  nome: string;
  movimento: string;
  protocolo: string;
  estagio: string;
  status: string;
  cedente: string;
  valor: string;
  tipo: "aberta" | "fechada";
}

const PortabilityTracking = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedRequests, setSelectedRequests] = useState<string[]>([]);
  const [cedenteFilter, setCedenteFilter] = useState<string>("all");
  const [estagioFilter, setEstagioFilter] = useState<string>("all");
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");
  const [tipoAberta, setTipoAberta] = useState<boolean>(true);
  const [tipoFechada, setTipoFechada] = useState<boolean>(true);

  // Mock data for portability requests
  const portabilityRequests: PortabilityRequest[] = [
    {
      id: "1",
      dias: 0,
      fip: "08141",
      portabilidade: "10272091",
      nome: "ALINE SANTANA ALVES",
      movimento: "17/11/2025",
      protocolo: "17/11/2025",
      estagio: "Solicitação",
      status: "Pendente",
      cedente: "Brasilprev",
      valor: "Total",
      tipo: "aberta"
    },
    {
      id: "2",
      dias: 3,
      fip: "08142",
      portabilidade: "10272092",
      nome: "CARLOS EDUARDO SANTOS",
      movimento: "14/11/2025",
      protocolo: "14/11/2025",
      estagio: "Análise",
      status: "Em Andamento",
      cedente: "Itaú",
      valor: "R$ 125.000,00",
      tipo: "aberta"
    },
    {
      id: "3",
      dias: 9,
      fip: "08143",
      portabilidade: "10272093",
      nome: "MARIA FERNANDA OLIVEIRA",
      movimento: "08/11/2025",
      protocolo: "08/11/2025",
      estagio: "Solicitação",
      status: "Pendente",
      cedente: "Zurich Santander",
      valor: "R$ 89.500,00",
      tipo: "aberta"
    },
    {
      id: "4",
      dias: 1,
      fip: "08144",
      portabilidade: "10272094",
      nome: "JOÃO PAULO RODRIGUES",
      movimento: "16/11/2025",
      protocolo: "16/11/2025",
      estagio: "Finalização",
      status: "Concluída",
      cedente: "Brasilprev",
      valor: "R$ 210.000,00",
      tipo: "aberta"
    },
    {
      id: "5",
      dias: 12,
      fip: "08145",
      portabilidade: "10272095",
      nome: "PATRICIA SILVA COSTA",
      movimento: "05/11/2025",
      protocolo: "05/11/2025",
      estagio: "Análise",
      status: "Recusada",
      cedente: "Itaú",
      valor: "R$ 67.800,00",
      tipo: "aberta"
    },
    {
      id: "6",
      dias: 4,
      fip: "08146",
      portabilidade: "10272096",
      nome: "ROBERTO ALMEIDA SILVA",
      movimento: "13/11/2025",
      protocolo: "13/11/2025",
      estagio: "Pendente assinatura representantes CVP",
      status: "Pendente assinatura representantes CVP",
      cedente: "Postalis",
      valor: "R$ 340.000,00",
      tipo: "fechada"
    },
    {
      id: "7",
      dias: 17,
      fip: "08147",
      portabilidade: "10272097",
      nome: "FERNANDA COSTA LIMA",
      movimento: "31/10/2025",
      protocolo: "31/10/2025",
      estagio: "Em andamento com a Cedente",
      status: "Assinado, Em andamento com a Cedente",
      cedente: "Funcef",
      valor: "R$ 520.000,00",
      tipo: "fechada"
    },
    {
      id: "8",
      dias: 2,
      fip: "08148",
      portabilidade: "10272098",
      nome: "GUSTAVO HENRIQUE SOUSA",
      movimento: "15/11/2025",
      protocolo: "15/11/2025",
      estagio: "Assinado",
      status: "Assinado",
      cedente: "Petros",
      valor: "R$ 780.000,00",
      tipo: "fechada"
    },
    {
      id: "9",
      dias: 7,
      fip: "08149",
      portabilidade: "10272099",
      nome: "MARIANA SANTOS OLIVEIRA",
      movimento: "10/11/2025",
      protocolo: "10/11/2025",
      estagio: "Concluída",
      status: "Concluída, Pendente histórico de Contribuições",
      cedente: "PreviNorte",
      valor: "R$ 190.000,00",
      tipo: "fechada"
    },
    {
      id: "10",
      dias: 5,
      fip: "08150",
      portabilidade: "10272100",
      nome: "ANTONIO CARLOS PEREIRA",
      movimento: "12/11/2025",
      protocolo: "12/11/2025",
      estagio: "Cancelada",
      status: "Cancelada",
      cedente: "Postalis",
      valor: "R$ 150.000,00",
      tipo: "fechada"
    }
  ];

  // Check for pending requests > 8 days and show notifications
  useEffect(() => {
    const pendingOldRequests = portabilityRequests.filter(
      req => req.tipo === "aberta" && req.status === "Pendente" && req.dias > 8
    );

    const pendingCVPRequests = portabilityRequests.filter(
      req => req.tipo === "fechada" && req.status === "Pendente assinatura representantes CVP" && req.dias > 3
    );

    const pendingCedenteRequests = portabilityRequests.filter(
      req => req.tipo === "fechada" && req.status === "Assinado, Em andamento com a Cedente" && req.dias > 15
    );

    if (pendingOldRequests.length > 0) {
      toast({
        title: "⚠️ Portabilidades Abertas Pendentes",
        description: `${pendingOldRequests.length} solicitação(ões) pendente(s) há mais de 8 dias.`,
        variant: "destructive",
      });
    }

    if (pendingCVPRequests.length > 0) {
      toast({
        title: "⚠️ Portabilidades Fechadas - Assinatura CVP",
        description: `${pendingCVPRequests.length} solicitação(ões) pendente(s) de assinatura CVP há mais de 3 dias.`,
        variant: "destructive",
      });
    }

    if (pendingCedenteRequests.length > 0) {
      toast({
        title: "⚠️ Portabilidades Fechadas - Cedente",
        description: `${pendingCedenteRequests.length} solicitação(ões) em andamento com a cedente há mais de 15 dias.`,
        variant: "destructive",
      });
    }
  }, []);

  const filteredRequests = portabilityRequests.filter(req => {
    const matchesSearch = 
      req.nome.toLowerCase().includes(searchTerm.toLowerCase()) ||
      req.portabilidade.includes(searchTerm) ||
      req.fip.includes(searchTerm);
    
    const matchesStatus = statusFilter === "all" || req.status === statusFilter;
    const matchesCedente = cedenteFilter === "all" || req.cedente === cedenteFilter;
    const matchesEstagio = estagioFilter === "all" || req.estagio === estagioFilter;
    
    // Tipo filter
    const matchesTipo = (tipoAberta && req.tipo === "aberta") || (tipoFechada && req.tipo === "fechada");
    
    // Date filter
    let matchesDate = true;
    if (startDate || endDate) {
      const movDate = new Date(req.movimento.split('/').reverse().join('-'));
      if (startDate && endDate) {
        const start = new Date(startDate);
        const end = new Date(endDate);
        matchesDate = movDate >= start && movDate <= end;
      } else if (startDate) {
        matchesDate = movDate >= new Date(startDate);
      } else if (endDate) {
        matchesDate = movDate <= new Date(endDate);
      }
    }
    
    return matchesSearch && matchesStatus && matchesCedente && matchesEstagio && matchesDate && matchesTipo;
  });

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedRequests(filteredRequests.map(req => req.id));
    } else {
      setSelectedRequests([]);
    }
  };

  const handleSelectRequest = (id: string, checked: boolean) => {
    if (checked) {
      setSelectedRequests([...selectedRequests, id]);
    } else {
      setSelectedRequests(selectedRequests.filter(reqId => reqId !== id));
    }
  };

  const handleExportToExcel = () => {
    const dataToExport = selectedRequests.length > 0
      ? portabilityRequests.filter(req => selectedRequests.includes(req.id))
      : filteredRequests;

    const exportData = dataToExport.map(req => ({
      "Dias": req.dias,
      "FIP": req.fip,
      "Portabilidade": req.portabilidade,
      "Nome": req.nome,
      "Movimento": req.movimento,
      "Protocolo": req.protocolo,
      "Estágio": req.estagio,
      "Status": req.status,
      "Cedente": req.cedente,
      "Valor": req.valor
    }));

    const ws = XLSX.utils.json_to_sheet(exportData);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Portabilidades");

    // Adjust column widths
    const colWidths = [
      { wch: 8 },  // Dias
      { wch: 10 }, // FIP
      { wch: 15 }, // Portabilidade
      { wch: 30 }, // Nome
      { wch: 15 }, // Movimento
      { wch: 15 }, // Protocolo
      { wch: 15 }, // Estágio
      { wch: 15 }, // Status
      { wch: 20 }, // Cedente
      { wch: 20 }  // Valor
    ];
    ws['!cols'] = colWidths;

    XLSX.writeFile(wb, `Portabilidades_${new Date().toISOString().split('T')[0]}.xlsx`);

    toast({
      title: "Exportação Concluída",
      description: `${dataToExport.length} registro(s) exportado(s) para Excel.`,
    });
  };


  const getStatusColor = (status: string) => {
    switch (status) {
      case "Pendente":
        return "bg-yellow-500/20 text-yellow-300 border-yellow-500/30";
      case "Em Andamento":
        return "bg-blue-500/20 text-blue-300 border-blue-500/30";
      case "Concluída":
        return "bg-green-500/20 text-green-300 border-green-500/30";
      case "Recusada":
        return "bg-red-500/20 text-red-300 border-red-500/30";
      default:
        return "bg-gray-500/20 text-gray-300 border-gray-500/30";
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-[hsl(211,70%,15%)] via-[hsl(211,60%,20%)] to-[hsl(211,50%,25%)]">
      
      <div className="container mx-auto px-4 py-6">
        <div className="flex items-center gap-4 mb-6">
          <Button
            onClick={() => navigate("/caixa-seguro/acompanhamento")}
            variant="outline"
            size="sm"
            className="bg-white/10 hover:bg-white/20 text-white border-white/20"
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            Voltar
          </Button>
          <h1 className="text-3xl font-bold text-white">Acompanhamento de Portabilidades</h1>
        </div>

        <Card className="bg-white/10 backdrop-blur-md border-white/20 shadow-[0_8px_32px_rgba(0,0,0,0.2)]">
          <CardHeader>
            <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
              <div className="flex flex-col gap-3">
                <CardTitle className="text-white">Solicitações de Portabilidade</CardTitle>
                <div className="flex items-center gap-4">
                  <label className="flex items-center gap-2 text-white cursor-pointer">
                    <Checkbox
                      checked={tipoAberta}
                      onCheckedChange={(checked) => setTipoAberta(checked as boolean)}
                      className="border-white/50"
                    />
                    <span>Portabilidade Aberta</span>
                  </label>
                  <label className="flex items-center gap-2 text-white cursor-pointer">
                    <Checkbox
                      checked={tipoFechada}
                      onCheckedChange={(checked) => setTipoFechada(checked as boolean)}
                      className="border-white/50"
                    />
                    <span>Portabilidade Fechada</span>
                  </label>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-3 w-full lg:w-auto">
                <div className="relative flex-1 lg:flex-none lg:w-80">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-white/50" />
                  <Input
                    placeholder="Buscar por nome, portabilidade ou FIP..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-10 bg-white/10 border-white/20 text-white placeholder:text-white/50"
                  />
                </div>
                <Select value={statusFilter} onValueChange={setStatusFilter}>
                  <SelectTrigger className="w-full lg:w-48 bg-white/10 border-white/20 text-white">
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos os Status</SelectItem>
                    {tipoAberta && !tipoFechada && (
                      <>
                        <SelectItem value="Pendente">Pendente</SelectItem>
                        <SelectItem value="Em Andamento">Em Andamento</SelectItem>
                        <SelectItem value="Concluída">Concluída</SelectItem>
                        <SelectItem value="Recusada">Recusada</SelectItem>
                      </>
                    )}
                    {tipoFechada && !tipoAberta && (
                      <>
                        <SelectItem value="Assinado">Assinado</SelectItem>
                        <SelectItem value="Assinado, Em andamento com a Cedente">Em andamento com a Cedente</SelectItem>
                        <SelectItem value="Cancelada">Cancelada</SelectItem>
                        <SelectItem value="Concluída">Concluída</SelectItem>
                        <SelectItem value="Concluída, Pendente histórico de Contribuições">Concluída, Pendente histórico</SelectItem>
                        <SelectItem value="Pendente assinatura representantes CVP">Pendente assinatura CVP</SelectItem>
                      </>
                    )}
                    {tipoAberta && tipoFechada && (
                      <>
                        <SelectItem value="Pendente">Pendente</SelectItem>
                        <SelectItem value="Em Andamento">Em Andamento</SelectItem>
                        <SelectItem value="Assinado">Assinado</SelectItem>
                        <SelectItem value="Assinado, Em andamento com a Cedente">Em andamento com a Cedente</SelectItem>
                        <SelectItem value="Cancelada">Cancelada</SelectItem>
                        <SelectItem value="Concluída">Concluída</SelectItem>
                        <SelectItem value="Concluída, Pendente histórico de Contribuições">Concluída, Pendente histórico</SelectItem>
                        <SelectItem value="Pendente assinatura representantes CVP">Pendente assinatura CVP</SelectItem>
                        <SelectItem value="Recusada">Recusada</SelectItem>
                      </>
                    )}
                  </SelectContent>
                </Select>
                <Select value={cedenteFilter} onValueChange={setCedenteFilter}>
                  <SelectTrigger className="w-full lg:w-48 bg-white/10 border-white/20 text-white">
                    <SelectValue placeholder="Cedente" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos os Cedentes</SelectItem>
                    {tipoAberta && !tipoFechada && (
                      <>
                        <SelectItem value="Brasilprev">Brasilprev</SelectItem>
                        <SelectItem value="Itaú">Itaú</SelectItem>
                        <SelectItem value="Zurich Santander">Zurich Santander</SelectItem>
                      </>
                    )}
                    {tipoFechada && !tipoAberta && (
                      <>
                        <SelectItem value="Postalis">Postalis</SelectItem>
                        <SelectItem value="Funcef">Funcef</SelectItem>
                        <SelectItem value="Petros">Petros</SelectItem>
                        <SelectItem value="PreviNorte">PreviNorte</SelectItem>
                      </>
                    )}
                    {tipoAberta && tipoFechada && (
                      <>
                        <SelectItem value="Brasilprev">Brasilprev</SelectItem>
                        <SelectItem value="Itaú">Itaú</SelectItem>
                        <SelectItem value="Zurich Santander">Zurich Santander</SelectItem>
                        <SelectItem value="Postalis">Postalis</SelectItem>
                        <SelectItem value="Funcef">Funcef</SelectItem>
                        <SelectItem value="Petros">Petros</SelectItem>
                        <SelectItem value="PreviNorte">PreviNorte</SelectItem>
                      </>
                    )}
                  </SelectContent>
                </Select>
                <Select value={estagioFilter} onValueChange={setEstagioFilter}>
                  <SelectTrigger className="w-full lg:w-48 bg-white/10 border-white/20 text-white">
                    <SelectValue placeholder="Estágio" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos os Estágios</SelectItem>
                    <SelectItem value="Solicitação">Solicitação</SelectItem>
                    <SelectItem value="Análise">Análise</SelectItem>
                    <SelectItem value="Finalização">Finalização</SelectItem>
                  </SelectContent>
                </Select>
                <div className="flex gap-2">
                  <Input
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    className="w-auto bg-white/10 border-white/20 text-white"
                    placeholder="Data início"
                  />
                  <Input
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    className="w-auto bg-white/10 border-white/20 text-white"
                    placeholder="Data fim"
                  />
                </div>
                <Button
                  onClick={handleExportToExcel}
                  className="bg-white/20 hover:bg-white/30 text-white border border-white/30"
                >
                  <Download className="h-4 w-4 mr-2" />
                  Exportar Excel
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="rounded-lg border border-white/20 overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="bg-white/5 hover:bg-white/10 border-white/20">
                    <TableHead className="text-white w-12">
                      <Checkbox
                        checked={selectedRequests.length === filteredRequests.length && filteredRequests.length > 0}
                        onCheckedChange={handleSelectAll}
                        className="border-white/50"
                      />
                    </TableHead>
                    <TableHead className="text-white">dia(s)</TableHead>
                    <TableHead className="text-white">FIP</TableHead>
                    <TableHead className="text-white">Portabilidade</TableHead>
                    <TableHead className="text-white">Nome</TableHead>
                    <TableHead className="text-white">Movimento</TableHead>
                    <TableHead className="text-white">Protocolo</TableHead>
                    <TableHead className="text-white">Estágio</TableHead>
                    <TableHead className="text-white">Status</TableHead>
                    <TableHead className="text-white">Cedente</TableHead>
                    <TableHead className="text-white">Valor</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredRequests.map((request) => (
                    <TableRow 
                      key={request.id}
                      className="border-white/10 hover:bg-white/5"
                    >
                      <TableCell>
                        <Checkbox
                          checked={selectedRequests.includes(request.id)}
                          onCheckedChange={(checked) => handleSelectRequest(request.id, checked as boolean)}
                          className="border-white/50"
                        />
                      </TableCell>
                      <TableCell>
                        <Badge 
                          variant={
                            (request.tipo === "aberta" && request.dias > 8) ||
                            (request.tipo === "fechada" && request.status === "Pendente assinatura representantes CVP" && request.dias > 3) ||
                            (request.tipo === "fechada" && request.status === "Assinado, Em andamento com a Cedente" && request.dias > 15)
                              ? "destructive"
                              : "secondary"
                          }
                          className={
                            (request.tipo === "aberta" && request.dias > 8) ||
                            (request.tipo === "fechada" && request.status === "Pendente assinatura representantes CVP" && request.dias > 3) ||
                            (request.tipo === "fechada" && request.status === "Assinado, Em andamento com a Cedente" && request.dias > 15)
                              ? "bg-red-500/20 text-red-300"
                              : "bg-green-500/20 text-green-300"
                          }
                        >
                          {request.dias}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-white/90">{request.fip}</TableCell>
                      <TableCell>
                        <span className="text-blue-300 underline cursor-pointer hover:text-blue-200">
                          {request.portabilidade}
                        </span>
                      </TableCell>
                      <TableCell className="text-white/90">{request.nome}</TableCell>
                      <TableCell className="text-white/90">{request.movimento}</TableCell>
                      <TableCell className="text-white/90">{request.protocolo}</TableCell>
                      <TableCell className="text-white/90">{request.estagio}</TableCell>
                      <TableCell>
                        <Badge className={getStatusColor(request.status)}>
                          {request.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-white/90">{request.cedente}</TableCell>
                      <TableCell className="text-white/90">{request.valor}</TableCell>
                    </TableRow>
                  ))}
                  {filteredRequests.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={11} className="text-center text-white/50 py-8">
                        Nenhuma solicitação encontrada
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>

            {selectedRequests.length > 0 && (
              <div className="mt-4 p-4 bg-white/5 rounded-lg border border-white/20">
                <p className="text-white">
                  {selectedRequests.length} solicitação(ões) selecionada(s)
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <MenuButton />
      <LeoAssistant 
        pageContext="Portabilidade"
        suggestedQuestions={[
          "Quais portabilidades estão pendentes há mais de 8 dias?",
          "Como acompanhar o status de uma portabilidade?",
          "Qual o valor total das portabilidades em andamento?",
          "Como exportar o relatório de portabilidades?",
        ]}
      />
    </div>
  );
};

export default PortabilityTracking;
