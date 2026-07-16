// "Acompanhamento de Portabilidades" no visual NATIVO do Orquestra — tela
// oficial de /caixa-seguro/portabilidades desde a F4 da migração
// (docs/spec-caixa-ds-nativo.md); substitui o PortabilityTracking navy/glass.
// Dados mock e lógica de filtros iguais aos da tela original; os alertas de
// pendência que eram toasts no mount viraram callouts inline (padrão da F2 no
// Monitoramento). Gráficos de portabilidade já vivem no MonitoramentoOrq
// (seção condicional a Previdência, portada no piloto). Requer ProfileProvider
// (aplicado na rota, App.tsx — o MenuButtonOrq usa o perfil).
import { useMemo, useState } from "react";
import { Download, Search, AlertTriangle, ArrowRightLeft } from "lucide-react";
import * as XLSX from "xlsx";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Input, Select } from "../../components/ui/Input";
import { Checkbox } from "../../components/ui/Checkbox";
import { Badge } from "../../components/ui/Badge";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "../../components/ui/Table";
import { toast } from "../../components/ui/Toast";
import ChatAssistantOrq from "../components/ChatAssistantOrq";
import MenuButtonOrq from "../components/MenuButtonOrq";
import leoAvatar from "../assets/leo-avatar.png";

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

// Mesmo mock da tela original.
const portabilityRequests: PortabilityRequest[] = [
  { id: "1", dias: 0, fip: "08141", portabilidade: "10272091", nome: "ALINE SANTANA ALVES", movimento: "17/11/2025", protocolo: "17/11/2025", estagio: "Solicitação", status: "Pendente", cedente: "Brasilprev", valor: "Total", tipo: "aberta" },
  { id: "2", dias: 3, fip: "08142", portabilidade: "10272092", nome: "CARLOS EDUARDO SANTOS", movimento: "14/11/2025", protocolo: "14/11/2025", estagio: "Análise", status: "Em Andamento", cedente: "Itaú", valor: "R$ 125.000,00", tipo: "aberta" },
  { id: "3", dias: 9, fip: "08143", portabilidade: "10272093", nome: "MARIA FERNANDA OLIVEIRA", movimento: "08/11/2025", protocolo: "08/11/2025", estagio: "Solicitação", status: "Pendente", cedente: "Zurich Santander", valor: "R$ 89.500,00", tipo: "aberta" },
  { id: "4", dias: 1, fip: "08144", portabilidade: "10272094", nome: "JOÃO PAULO RODRIGUES", movimento: "16/11/2025", protocolo: "16/11/2025", estagio: "Finalização", status: "Concluída", cedente: "Brasilprev", valor: "R$ 210.000,00", tipo: "aberta" },
  { id: "5", dias: 12, fip: "08145", portabilidade: "10272095", nome: "PATRICIA SILVA COSTA", movimento: "05/11/2025", protocolo: "05/11/2025", estagio: "Análise", status: "Recusada", cedente: "Itaú", valor: "R$ 67.800,00", tipo: "aberta" },
  { id: "6", dias: 4, fip: "08146", portabilidade: "10272096", nome: "ROBERTO ALMEIDA SILVA", movimento: "13/11/2025", protocolo: "13/11/2025", estagio: "Pendente assinatura representantes CVP", status: "Pendente assinatura representantes CVP", cedente: "Postalis", valor: "R$ 340.000,00", tipo: "fechada" },
  { id: "7", dias: 17, fip: "08147", portabilidade: "10272097", nome: "FERNANDA COSTA LIMA", movimento: "31/10/2025", protocolo: "31/10/2025", estagio: "Em andamento com a Cedente", status: "Assinado, Em andamento com a Cedente", cedente: "Funcef", valor: "R$ 520.000,00", tipo: "fechada" },
  { id: "8", dias: 2, fip: "08148", portabilidade: "10272098", nome: "GUSTAVO HENRIQUE SOUSA", movimento: "15/11/2025", protocolo: "15/11/2025", estagio: "Assinado", status: "Assinado", cedente: "Petros", valor: "R$ 780.000,00", tipo: "fechada" },
  { id: "9", dias: 7, fip: "08149", portabilidade: "10272099", nome: "MARIANA SANTOS OLIVEIRA", movimento: "10/11/2025", protocolo: "10/11/2025", estagio: "Concluída", status: "Concluída, Pendente histórico de Contribuições", cedente: "PreviNorte", valor: "R$ 190.000,00", tipo: "fechada" },
  { id: "10", dias: 5, fip: "08150", portabilidade: "10272100", nome: "ANTONIO CARLOS PEREIRA", movimento: "12/11/2025", protocolo: "12/11/2025", estagio: "Cancelada", status: "Cancelada", cedente: "Postalis", valor: "R$ 150.000,00", tipo: "fechada" },
];

// Prazos estourados (mesmos predicados da tela original — também pintam o
// chip de dias na tabela).
const isAtrasada = (req: PortabilityRequest) =>
  (req.tipo === "aberta" && req.dias > 8) ||
  (req.tipo === "fechada" && req.status === "Pendente assinatura representantes CVP" && req.dias > 3) ||
  (req.tipo === "fechada" && req.status === "Assinado, Em andamento com a Cedente" && req.dias > 15);

// Badge nativo por status (chaves do MAP do ui/Badge, com par claro+escuro).
const statusBadgeKey = (status: string) => {
  switch (status) {
    case "Pendente":
      return "warning";
    case "Em Andamento":
      return "info";
    case "Concluída":
      return "success";
    case "Recusada":
      return "error";
    default:
      return "neutral";
  }
};

export default function PortabilidadesOrq() {
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedRequests, setSelectedRequests] = useState<string[]>([]);
  const [cedenteFilter, setCedenteFilter] = useState<string>("all");
  const [estagioFilter, setEstagioFilter] = useState<string>("all");
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");
  const [tipoAberta, setTipoAberta] = useState<boolean>(true);
  const [tipoFechada, setTipoFechada] = useState<boolean>(true);

  // Alertas de pendência (a tela antiga disparava 3 toasts no mount; aqui é
  // callout inline, padrão do Monitoramento nativo).
  const alertas = useMemo(() => {
    const abertas = portabilityRequests.filter((r) => r.tipo === "aberta" && r.status === "Pendente" && r.dias > 8).length;
    const cvp = portabilityRequests.filter((r) => r.tipo === "fechada" && r.status === "Pendente assinatura representantes CVP" && r.dias > 3).length;
    const cedente = portabilityRequests.filter((r) => r.tipo === "fechada" && r.status === "Assinado, Em andamento com a Cedente" && r.dias > 15).length;
    const itens: string[] = [];
    if (abertas > 0) itens.push(`Portabilidades abertas: ${abertas} solicitação(ões) pendente(s) há mais de 8 dias.`);
    if (cvp > 0) itens.push(`Portabilidades fechadas: ${cvp} solicitação(ões) pendente(s) de assinatura CVP há mais de 3 dias.`);
    if (cedente > 0) itens.push(`Portabilidades fechadas: ${cedente} solicitação(ões) em andamento com a cedente há mais de 15 dias.`);
    return itens;
  }, []);

  const filteredRequests = portabilityRequests.filter((req) => {
    const matchesSearch =
      req.nome.toLowerCase().includes(searchTerm.toLowerCase()) ||
      req.portabilidade.includes(searchTerm) ||
      req.fip.includes(searchTerm);

    const matchesStatus = statusFilter === "all" || req.status === statusFilter;
    const matchesCedente = cedenteFilter === "all" || req.cedente === cedenteFilter;
    const matchesEstagio = estagioFilter === "all" || req.estagio === estagioFilter;
    const matchesTipo = (tipoAberta && req.tipo === "aberta") || (tipoFechada && req.tipo === "fechada");

    let matchesDate = true;
    if (startDate || endDate) {
      const movDate = new Date(req.movimento.split("/").reverse().join("-"));
      if (startDate && endDate) {
        matchesDate = movDate >= new Date(startDate) && movDate <= new Date(endDate);
      } else if (startDate) {
        matchesDate = movDate >= new Date(startDate);
      } else if (endDate) {
        matchesDate = movDate <= new Date(endDate);
      }
    }

    return matchesSearch && matchesStatus && matchesCedente && matchesEstagio && matchesDate && matchesTipo;
  });

  const handleSelectAll = (checked: boolean) => {
    setSelectedRequests(checked ? filteredRequests.map((req) => req.id) : []);
  };

  const handleSelectRequest = (id: string, checked: boolean) => {
    setSelectedRequests(checked ? [...selectedRequests, id] : selectedRequests.filter((reqId) => reqId !== id));
  };

  const handleExportToExcel = () => {
    const dataToExport =
      selectedRequests.length > 0
        ? portabilityRequests.filter((req) => selectedRequests.includes(req.id))
        : filteredRequests;

    const exportData = dataToExport.map((req) => ({
      "Dias": req.dias,
      "FIP": req.fip,
      "Portabilidade": req.portabilidade,
      "Nome": req.nome,
      "Movimento": req.movimento,
      "Protocolo": req.protocolo,
      "Estágio": req.estagio,
      "Status": req.status,
      "Cedente": req.cedente,
      "Valor": req.valor,
    }));

    const ws = XLSX.utils.json_to_sheet(exportData);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Portabilidades");
    ws["!cols"] = [
      { wch: 8 }, { wch: 10 }, { wch: 15 }, { wch: 30 }, { wch: 15 },
      { wch: 15 }, { wch: 15 }, { wch: 15 }, { wch: 20 }, { wch: 20 },
    ];
    XLSX.writeFile(wb, `Portabilidades_${new Date().toISOString().split("T")[0]}.xlsx`);

    toast.success(`${dataToExport.length} registro(s) exportado(s) para Excel.`);
  };

  return (
    <div className="min-h-full bg-canvas font-sans text-ink">
      <div className="p-6 max-w-[1600px] mx-auto flex flex-col gap-5">
        {/* Cabeçalho */}
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-lg font-semibold text-ink flex items-center gap-2">
              <ArrowRightLeft size={18} className="text-[#1A5FA8]" />
              Acompanhamento de Portabilidades
            </h1>
            <p className="text-sm text-dim mt-0.5">Solicitações de portabilidade aberta e fechada</p>
          </div>
          <div className="flex items-center gap-2">
            <MenuButtonOrq />
            <Button variant="primary" size="md" onClick={handleExportToExcel}>
              <Download size={14} /> Exportar Excel
            </Button>
          </div>
        </div>

        {/* Alertas de prazo (callout inline, no lugar dos toasts do mount) */}
        {alertas.length > 0 && (
          <div className="flex items-start gap-3 rounded-lg border border-red-300 bg-red-50 px-4 py-3 dark:border-red-900 dark:bg-red-900/20">
            <AlertTriangle size={18} className="text-red-600 dark:text-red-400 mt-0.5 shrink-0" />
            <div>
              <p className="text-sm font-semibold text-red-700 dark:text-red-300">Portabilidades com atenção urgente</p>
              {alertas.map((a) => (
                <p key={a} className="text-xs text-red-600/90 dark:text-red-400/90">{a}</p>
              ))}
            </div>
          </div>
        )}

        <Card title="Solicitações de Portabilidade">
          {/* Filtros */}
          <div className="flex flex-col gap-4 mb-4">
            <div className="flex items-center gap-4 flex-wrap">
              <Checkbox
                checked={tipoAberta}
                onChange={(e) => setTipoAberta(e.target.checked)}
                label="Portabilidade Aberta"
              />
              <Checkbox
                checked={tipoFechada}
                onChange={(e) => setTipoFechada(e.target.checked)}
                label="Portabilidade Fechada"
              />
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <div className="relative flex-1 min-w-[240px] lg:max-w-80">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-dim pointer-events-none" />
                <Input
                  placeholder="Buscar por nome, portabilidade ou FIP..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full pl-9"
                />
              </div>

              <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="Status" className="w-48">
                <option value="all">Todos os Status</option>
                {tipoAberta && !tipoFechada && (
                  <>
                    <option value="Pendente">Pendente</option>
                    <option value="Em Andamento">Em Andamento</option>
                    <option value="Concluída">Concluída</option>
                    <option value="Recusada">Recusada</option>
                  </>
                )}
                {tipoFechada && !tipoAberta && (
                  <>
                    <option value="Assinado">Assinado</option>
                    <option value="Assinado, Em andamento com a Cedente">Em andamento com a Cedente</option>
                    <option value="Cancelada">Cancelada</option>
                    <option value="Concluída">Concluída</option>
                    <option value="Concluída, Pendente histórico de Contribuições">Concluída, Pendente histórico</option>
                    <option value="Pendente assinatura representantes CVP">Pendente assinatura CVP</option>
                  </>
                )}
                {tipoAberta && tipoFechada && (
                  <>
                    <option value="Pendente">Pendente</option>
                    <option value="Em Andamento">Em Andamento</option>
                    <option value="Assinado">Assinado</option>
                    <option value="Assinado, Em andamento com a Cedente">Em andamento com a Cedente</option>
                    <option value="Cancelada">Cancelada</option>
                    <option value="Concluída">Concluída</option>
                    <option value="Concluída, Pendente histórico de Contribuições">Concluída, Pendente histórico</option>
                    <option value="Pendente assinatura representantes CVP">Pendente assinatura CVP</option>
                    <option value="Recusada">Recusada</option>
                  </>
                )}
              </Select>

              <Select value={cedenteFilter} onChange={(e) => setCedenteFilter(e.target.value)} aria-label="Cedente" className="w-48">
                <option value="all">Todos os Cedentes</option>
                {tipoAberta && !tipoFechada && (
                  <>
                    <option value="Brasilprev">Brasilprev</option>
                    <option value="Itaú">Itaú</option>
                    <option value="Zurich Santander">Zurich Santander</option>
                  </>
                )}
                {tipoFechada && !tipoAberta && (
                  <>
                    <option value="Postalis">Postalis</option>
                    <option value="Funcef">Funcef</option>
                    <option value="Petros">Petros</option>
                    <option value="PreviNorte">PreviNorte</option>
                  </>
                )}
                {tipoAberta && tipoFechada && (
                  <>
                    <option value="Brasilprev">Brasilprev</option>
                    <option value="Itaú">Itaú</option>
                    <option value="Zurich Santander">Zurich Santander</option>
                    <option value="Postalis">Postalis</option>
                    <option value="Funcef">Funcef</option>
                    <option value="Petros">Petros</option>
                    <option value="PreviNorte">PreviNorte</option>
                  </>
                )}
              </Select>

              <Select value={estagioFilter} onChange={(e) => setEstagioFilter(e.target.value)} aria-label="Estágio" className="w-48">
                <option value="all">Todos os Estágios</option>
                <option value="Solicitação">Solicitação</option>
                <option value="Análise">Análise</option>
                <option value="Finalização">Finalização</option>
              </Select>

              <div className="flex gap-2">
                <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} aria-label="Data início" />
                <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} aria-label="Data fim" />
              </div>
            </div>
          </div>

          {/* Tabela */}
          <div className="rounded-lg border border-edge overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12">
                    <Checkbox
                      checked={selectedRequests.length === filteredRequests.length && filteredRequests.length > 0}
                      onChange={(e) => handleSelectAll(e.target.checked)}
                      aria-label="Selecionar todas"
                    />
                  </TableHead>
                  <TableHead>dia(s)</TableHead>
                  <TableHead>FIP</TableHead>
                  <TableHead>Portabilidade</TableHead>
                  <TableHead>Nome</TableHead>
                  <TableHead>Movimento</TableHead>
                  <TableHead>Protocolo</TableHead>
                  <TableHead>Estágio</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Cedente</TableHead>
                  <TableHead>Valor</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredRequests.map((request) => (
                  <TableRow key={request.id}>
                    <TableCell>
                      <Checkbox
                        checked={selectedRequests.includes(request.id)}
                        onChange={(e) => handleSelectRequest(request.id, e.target.checked)}
                        aria-label={`Selecionar portabilidade ${request.portabilidade}`}
                      />
                    </TableCell>
                    <TableCell>
                      <Badge value={isAtrasada(request) ? "error" : "success"}>{request.dias}</Badge>
                    </TableCell>
                    <TableCell>{request.fip}</TableCell>
                    <TableCell>
                      <span className="text-[#1A5FA8] dark:text-blue-400 underline cursor-pointer hover:opacity-80">
                        {request.portabilidade}
                      </span>
                    </TableCell>
                    <TableCell>{request.nome}</TableCell>
                    <TableCell>{request.movimento}</TableCell>
                    <TableCell>{request.protocolo}</TableCell>
                    <TableCell>{request.estagio}</TableCell>
                    <TableCell>
                      <Badge value={statusBadgeKey(request.status)}>{request.status}</Badge>
                    </TableCell>
                    <TableCell>{request.cedente}</TableCell>
                    <TableCell>{request.valor}</TableCell>
                  </TableRow>
                ))}
                {filteredRequests.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={11} className="text-center text-dim py-8">
                      Nenhuma solicitação encontrada
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>

          {selectedRequests.length > 0 && (
            <div className="mt-4 p-4 bg-canvas rounded-lg border border-edge">
              <p className="text-sm text-ink">{selectedRequests.length} solicitação(ões) selecionada(s)</p>
            </div>
          )}
        </Card>
      </div>

      {/* FAB de chat do Léo (gate useAssistentesIA dentro do componente) */}
      <ChatAssistantOrq
        assistente="leo"
        nome="Léo"
        avatar={leoAvatar}
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
}
