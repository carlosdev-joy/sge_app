import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useProfile } from "../contexts/ProfileContext";
import Header from "../components/Header";
import MenuButton from "../components/MenuButton";
import ProposalWorkflowSheet from "../components/ProposalWorkflowSheet";
import DateFilters from "../components/DateFilters";
import SensitizationDialog from "../components/SensitizationDialog";
import LeoAssistant from "../components/LeoAssistant";
import DiegoAssistant from "../components/DiegoAssistant";
import LariAssistant from "../components/LariAssistant";
import ProductTour from "../components/ProductTour";
import { NPSDialog } from "../components/NPSDialog";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Alert, AlertDescription } from "../components/ui/alert";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, ResponsiveContainer, PieChart, Pie, Cell, Legend, Tooltip, LineChart, Line } from "recharts";
import { AlertTriangle, TrendingUp, TrendingDown, User, Eye, Download, ArrowRight, HelpCircle, X } from "lucide-react";
import { useToast } from "../hooks/use-toast";
import * as XLSX from "xlsx";
import lariAvatar from "../assets/lari-avatar.png";
import diegoAvatar from "../assets/diego-avatar.png";
import leoAvatar from "../assets/leo-avatar.png";


const SalesManagement = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { profile } = useProfile();
  const [selectedDay, setSelectedDay] = useState<string>("all");
  const [selectedMonth, setSelectedMonth] = useState<string>("all");
  const [selectedYear, setSelectedYear] = useState<string>(new Date().getFullYear().toString());
  const [isSensitizationDialogOpen, setIsSensitizationDialogOpen] = useState(false);
  const [agencyFilter, setAgencyFilter] = useState<string>("all");
  const [regionFilter, setRegionFilter] = useState<string>("all");
  const [productType, setProductType] = useState<"vida" | "previdencia" | "prestamista">("vida");
  const [portabilityStartDate, setPortabilityStartDate] = useState<string>("");
  const [portabilityEndDate, setPortabilityEndDate] = useState<string>("");
  const [isLoadingTransition, setIsLoadingTransition] = useState(false);
  const [showProductTour, setShowProductTour] = useState(false);
  const [activeStatusHelp, setActiveStatusHelp] = useState<string | null>(null);
  const [showNPSDialog, setShowNPSDialog] = useState(false);

  // Show NPS dialog after 30 seconds
  useEffect(() => {
    const timer = setTimeout(() => {
      setShowNPSDialog(true);
    }, 30000);
    
    return () => clearTimeout(timer);
  }, []);

  // Push notifications for pending items
  useEffect(() => {
    const checkPendingItems = () => {
      // Check portabilities pending > 8 days
      if (productType === "previdencia") {
        const pendingPortabilityCount = 12; // Mock data
        if (pendingPortabilityCount > 0) {
          toast({
            title: "⚠️ Portabilidades Pendentes",
            description: `${pendingPortabilityCount} solicitação(ões) pendente(s) há mais de 8 dias.`,
            variant: "destructive",
          });
        }
      }

      // Check proposals pending > 10 days
      const pendingProposalsCount = 8; // Mock data
      if (pendingProposalsCount > 0) {
        toast({
          title: "⚠️ Propostas com Atenção Urgente",
          description: `${pendingProposalsCount} proposta(s) pendente(s) há mais de 10 dias.`,
          variant: "destructive",
        });
      }
    };

    // Check immediately and then every 30 minutes
    checkPendingItems();
    const interval = setInterval(checkPendingItems, 30 * 60 * 1000);
    
    return () => clearInterval(interval);
  }, [productType, toast]);

  // Dados mockados do funcionário
  const employeeData = {
    name: "João Silva",
    matricula: "12345",
    department: "Seguros",
  };

  const statusHelpInfo: { [key: string]: { avatar: string; avatarName: string; message: string } } = {
    pending_signature: {
      avatar: lariAvatar,
      avatarName: "Lari",
      message: "Este status corresponde a propostas que estão pendentes de assinatura. Você pode utilizar o botão 'Enviar Link' para enviar ao cliente o link para assinatura da proposta via e-mail, WhatsApp ou SMS!"
    },
    awaiting_payment: {
      avatar: diegoAvatar,
      avatarName: "Diego",
      message: "Estas são propostas já assinadas que aguardam o pagamento. Você pode gerenciar as opções de pagamento e enviar lembretes ao cliente através do botão 'Gerenciar Pagamento'."
    },
    pending_documentation: {
      avatar: lariAvatar,
      avatarName: "Lari",
      message: "Propostas com pendências documentais precisam de documentos adicionais. Use o botão 'Upload de Documentos' para enviar os arquivos necessários e dar andamento à proposta."
    },
    pending_dps: {
      avatar: leoAvatar,
      avatarName: "Léo",
      message: "Pendência de DPS (Declaração Pessoal de Saúde) significa que o cliente precisa preencher informações de saúde. Clique em 'Enviar Link DPS' para enviar o formulário ao segurado."
    },
    refund_pending: {
      avatar: diegoAvatar,
      avatarName: "Diego",
      message: "Estas são propostas que foram declinadas pela seguradora. Você pode gerenciar o reembolso através do botão 'Gerenciar Reembolso' ou criar uma nova venda revisando as informações."
    }
  };

  const statusData = [
    {
      status: "pending_signature",
      title: "Aguardando Assinatura",
      count: 217,
      value: "R$ 1.245.680,00",
      bgColor: "bg-[hsl(211,70%,40%)]",
      hoverColor: "hover:bg-[hsl(211,70%,35%)]",
      glowColor: "shadow-[0_0_20px_rgba(0,85,177,0.4)]",
    },
    {
      status: "awaiting_payment",
      title: "Aguardando Pagamento",
      count: 150,
      value: "R$ 856.420,00",
      bgColor: "bg-[hsl(211,60%,45%)]",
      hoverColor: "hover:bg-[hsl(211,60%,40%)]",
      glowColor: "shadow-[0_0_20px_rgba(99,183,232,0.3)]",
    },
    {
      status: "signed_proposal",
      title: "Proposta Assinada",
      count: 456,
      value: "R$ 2.654.320,00",
      bgColor: "bg-[hsl(211,80%,50%)]",
      hoverColor: "hover:bg-[hsl(211,80%,45%)]",
      glowColor: "shadow-[0_0_25px_rgba(99,183,232,0.5)]",
    },
    {
      status: "pending_documentation",
      title: "Pendência Documental",
      count: 43,
      value: "R$ 298.750,00",
      bgColor: "bg-[hsl(211,50%,35%)]",
      hoverColor: "hover:bg-[hsl(211,50%,30%)]",
      glowColor: "shadow-[0_0_15px_rgba(0,85,177,0.25)]",
    },
    {
      status: "pending_dps",
      title: "Pendência de DPS",
      count: 28,
      value: "R$ 187.560,00",
      bgColor: "bg-[hsl(211,45%,30%)]",
      hoverColor: "hover:bg-[hsl(211,45%,25%)]",
      glowColor: "shadow-[0_0_15px_rgba(0,85,177,0.2)]",
    },
    {
      status: "refund_pending",
      title: "Propostas Declinadas",
      count: 89,
      value: "R$ 512.340,00",
      bgColor: "bg-[hsl(211,40%,25%)]",
      hoverColor: "hover:bg-[hsl(211,40%,20%)]",
      glowColor: "shadow-[0_0_15px_rgba(0,85,177,0.15)]",
    },
    {
      status: "valores_programados",
      title: "Valores Programados",
      count: 45,
      value: "R$ 287.900,00",
      bgColor: "bg-[hsl(202,73%,50%)]",
      hoverColor: "hover:bg-[hsl(202,73%,45%)]",
      glowColor: "shadow-[0_0_20px_rgba(99,183,232,0.4)]",
    },
    {
      status: "sensitization_monitoring",
      title: "Monitoramento de Sensibilização",
      count: 4,
      value: "4 movimentos",
      bgColor: "bg-[hsl(211,70%,50%)]",
      hoverColor: "hover:bg-[hsl(211,70%,45%)]",
      glowColor: "shadow-[0_0_20px_rgba(99,183,232,0.4)]",
    },
  ];

  const handleExportReport = () => {
    toast({
      title: "Relatório em preparação",
      description: "Seu relatório Excel está sendo gerado e será baixado em instantes.",
    });
    
    setTimeout(() => {
      toast({
        title: "Download concluído",
        description: "Relatório de vendas exportado com sucesso!",
      });
    }, 2000);
  };

  // Gráfico 2: Status de seguros (Ativos, Pendentes, Declinados)
  const insuranceStatusData = [
    { name: "Ativos", value: 456, percentage: 52, color: "hsl(var(--caixa-blue))" },
    { name: "Pendentes de Análise", value: 217, percentage: 25, color: "hsl(var(--caixa-orange))" },
    { name: "Declinados", value: 204, percentage: 23, color: "hsl(var(--destructive))" },
  ];

  // Gráfico 3: Motivos de declínio
  const declineReasonsData = [
    { reason: "Documentação Incompleta", count: 89 },
    { reason: "Análise de Crédito", count: 54 },
    { reason: "Desistência Cliente", count: 31 },
    { reason: "Divergência Cadastral", count: 30 },
  ];

  // Gráfico 4: Propostas pendentes por motivo
  const getPendingByReasonData = () => {
    if (productType === "previdencia") {
      return [
        { reason: "Propostas fora da conformidade", count: 45, overdue: 18 },
        { reason: "Pendências relacionadas a Curatela/Procuração e a Rogo", count: 38, overdue: 12 },
        { reason: "Aguardando Documentos", count: 32, overdue: 8 },
        { reason: "Em Análise", count: 27, overdue: 5 },
      ];
    } else if (productType === "prestamista") {
      return [
        { reason: "Aguardando DPS", count: 35, overdue: 15 },
        { reason: "Aguardando Documentos", count: 48, overdue: 10 },
        { reason: "Em Análise", count: 38, overdue: 6 },
        { reason: "Validação Cadastral", count: 24, overdue: 4 },
      ];
    }
    // Default: Seguro de Vida
    return [
      { reason: "Aguardando DPS", count: 28, overdue: 12 },
      { reason: "Aguardando Documentos", count: 43, overdue: 8 },
      { reason: "Em Análise", count: 35, overdue: 3 },
      { reason: "Validação Cadastral", count: 21, overdue: 5 },
    ];
  };

  const pendingByReasonData = getPendingByReasonData();

  const totalOverdue = pendingByReasonData.reduce((sum, item) => sum + item.overdue, 0);

  // Gráfico 5: Propostas pendentes de sensibilização
  const sensitizationData = [
    { month: "Jan", count: 12 },
    { month: "Fev", count: 18 },
    { month: "Mar", count: 15 },
    { month: "Abr", count: 22 },
    { month: "Mai", count: 19 },
  ];

  // Gráfico 6: Resultado geral (emissões vs declínios)
  const generalResultData = [
    { month: "Jan", emissoesCount: 180, decliniosCount: 15, emissoesValue: 1024000, decliniosValue: 85000 },
    { month: "Fev", emissoesCount: 240, decliniosCount: 18, emissoesValue: 1368000, decliniosValue: 102000 },
    { month: "Mar", emissoesCount: 290, decliniosCount: 22, emissoesValue: 1653000, decliniosValue: 125000 },
    { month: "Abr", emissoesCount: 320, decliniosCount: 19, emissoesValue: 1824000, decliniosValue: 108000 },
    { month: "Mai", emissoesCount: 280, decliniosCount: 15, emissoesValue: 1596000, decliniosValue: 85000 },
  ];

  // Gráfico 7: Emissões e declínios por produto
  const getProductResultData = () => {
    if (productType === "previdencia") {
      return [
        { product: "Prev Crescer", emissoes: 380, declínios: 15 },
        { product: "Prev Mulher", emissoes: 290, declínios: 12 },
        { product: "Previdência 1215", emissoes: 310, declínios: 18 },
        { product: "Prev Ativa", emissoes: 260, declínios: 10 },
      ];
    } else if (productType === "prestamista") {
      return [
        { product: "Prestamista Habitacional", emissoes: 420, declínios: 28 },
        { product: "Prestamista Veículos", emissoes: 350, declínios: 22 },
        { product: "Prestamista Consignado", emissoes: 290, declínios: 15 },
        { product: "Prestamista Pessoal", emissoes: 240, declínios: 20 },
      ];
    }
    // Default: Seguro de Vida
    return [
      { product: "Vida Multipremiado", emissoes: 450, declínios: 25 },
      { product: "Vida Mulher", emissoes: 320, declínios: 18 },
      { product: "Vida Conforto", emissoes: 280, declínios: 22 },
      { product: "Perda de Renda", emissoes: 349, declínios: 24 },
    ];
  };

  const productResultData = getProductResultData();

  const handleCardClick = (status: string) => {
    if (status === "sensitization_monitoring") {
      setIsSensitizationDialogOpen(true);
    } else {
      navigate(`/caixa-seguro/acompanhamento/${status}`);
    }
  };

  const handleProductTypeChange = (newType: "vida" | "previdencia" | "prestamista") => {
    setIsLoadingTransition(true);
    setTimeout(() => {
      setProductType(newType);
      setIsLoadingTransition(false);
    }, 600);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-[hsl(211,100%,15%)] via-[hsl(211,100%,25%)] to-[hsl(211,100%,35%)] relative overflow-hidden">
      {productType === "previdencia" && <LeoAssistant />}
      {/* Animated background lines */}
      <div className="absolute inset-0 opacity-5 pointer-events-none">
        <div className="absolute top-1/4 left-0 w-full h-px bg-gradient-to-r from-transparent via-[hsl(211,100%,50%)] to-transparent animate-pulse" />
        <div className="absolute top-2/4 left-0 w-full h-px bg-gradient-to-r from-transparent via-[hsl(211,100%,60%)] to-transparent animate-pulse" style={{ animationDelay: '1s' }} />
        <div className="absolute top-3/4 left-0 w-full h-px bg-gradient-to-r from-transparent via-[hsl(211,100%,50%)] to-transparent animate-pulse" style={{ animationDelay: '2s' }} />
      </div>

      <Header />
      
      <main className="container mx-auto px-6 py-8 max-w-7xl relative z-10">
        <div className="mb-6 flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-4">
            <MenuButton />
            <ProposalWorkflowSheet />
          </div>
          <Card className="bg-white/10 backdrop-blur-md border-white/20 px-4 py-2">
            <div className="flex items-center gap-3">
              <User className="h-5 w-5 text-white" />
              <p className="text-sm font-semibold text-white">{employeeData.name}</p>
            </div>
          </Card>
        </div>

        <div className="flex items-center justify-between mb-4 flex-wrap gap-4">
          <div>
            <h1 className="text-4xl font-bold text-white drop-shadow-[0_0_15px_rgba(255,255,255,0.3)]">
              Monitoramento Tático de Emissão
            </h1>
            <p className="text-white/80">Painel Individual de Desempenho e Efetividade</p>
            <div className="mt-3 h-1 w-28 rounded-full bg-gradient-to-r from-[#F26B00] to-[#FFB380]" />
          </div>
          <Button
            onClick={handleExportReport}
            className="bg-white/20 hover:bg-white/30 text-white border border-white/30"
          >
            <Download className="h-4 w-4 mr-2" />
            Exportar Relatório Excel
          </Button>
        </div>

        <DateFilters 
          selectedDay={selectedDay}
          selectedMonth={selectedMonth}
          selectedYear={selectedYear}
          onDayChange={setSelectedDay}
          onMonthChange={setSelectedMonth}
          onYearChange={setSelectedYear}
        />

        {/* Product Type Navigation */}
        <div className="mt-6 mb-4 flex gap-3 justify-center items-center flex-wrap">
          <Button
            onClick={() => handleProductTypeChange("vida")}
            variant={productType === "vida" ? "default" : "outline"}
            className={productType === "vida" 
              ? "bg-white text-[hsl(211,100%,25%)] hover:bg-white/90" 
              : "bg-white/10 text-white border-white/30 hover:bg-white/20"}
            disabled={isLoadingTransition}
          >
            Seguro de Vida
          </Button>
          <Button
            onClick={() => handleProductTypeChange("previdencia")}
            variant={productType === "previdencia" ? "default" : "outline"}
            className={productType === "previdencia" 
              ? "bg-white text-[hsl(211,100%,25%)] hover:bg-white/90" 
              : "bg-white/10 text-white border-white/30 hover:bg-white/20"}
            disabled={isLoadingTransition}
          >
            Previdência
          </Button>
          <Button
            onClick={() => handleProductTypeChange("prestamista")}
            variant={productType === "prestamista" ? "default" : "outline"}
            className={productType === "prestamista" 
              ? "bg-white text-[hsl(211,100%,25%)] hover:bg-white/90" 
              : "bg-white/10 text-white border-white/30 hover:bg-white/20"}
            disabled={isLoadingTransition}
          >
            Prestamista
          </Button>
          <Button
            onClick={() => setShowProductTour(true)}
            variant="outline"
            className="bg-primary/20 text-white border-primary/40 hover:bg-primary/30"
          >
            🎯 Tour do Produto
          </Button>
        </div>

        {/* Loading Overlay */}
        {isLoadingTransition && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg p-8 flex flex-col items-center gap-4">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[hsl(211,100%,25%)]"></div>
              <p className="text-[hsl(211,100%,25%)] font-semibold">Carregando dados...</p>
            </div>
          </div>
        )}

        {/* Agency and Region Filters (Operational Profile Only) */}
        {profile === "operational" && (
          <div className="mt-4 flex gap-4">
            <Select value={agencyFilter} onValueChange={setAgencyFilter}>
              <SelectTrigger className="w-[200px] bg-white/10 border-white/20 text-white">
                <SelectValue placeholder="Filtrar por agência" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todas as agências</SelectItem>
                <SelectItem value="474">Agência 474</SelectItem>
                <SelectItem value="475">Agência 475</SelectItem>
                <SelectItem value="476">Agência 476</SelectItem>
              </SelectContent>
            </Select>
            
            <Select value={regionFilter} onValueChange={setRegionFilter}>
              <SelectTrigger className="w-[200px] bg-white/10 border-white/20 text-white">
                <SelectValue placeholder="Filtrar por região" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todas as regiões</SelectItem>
                <SelectItem value="norte">Norte</SelectItem>
                <SelectItem value="nordeste">Nordeste</SelectItem>
                <SelectItem value="centro-oeste">Centro-Oeste</SelectItem>
                <SelectItem value="sudeste">Sudeste</SelectItem>
                <SelectItem value="sul">Sul</SelectItem>
              </SelectContent>
            </Select>
          </div>
        )}

        {/* Status Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 mb-8 mt-8">
          {statusData.map((item, index) => (
            <Card
              key={item.status}
              className={`group ${item.bgColor} ${item.hoverColor} ${item.glowColor} border border-white/10 rounded-xl cursor-pointer transition-all duration-300 hover:-translate-y-1 hover:shadow-2xl animate-slide-in-bottom`}
              style={{ animationDelay: `${index * 0.1}s` }}
              onClick={() => handleCardClick(item.status)}
            >
              <CardContent className="p-6 text-white relative overflow-hidden">
                <div className="absolute top-0 right-0 w-28 h-28 bg-white/10 rounded-full blur-2xl -mr-10 -mt-10 transition-transform duration-500 group-hover:scale-125" />
                <div className="flex items-center justify-center gap-2 mb-3 relative z-10">
                  <h3 className="text-sm font-semibold uppercase tracking-wider text-white/90 text-center">{item.title}</h3>
                  {statusHelpInfo[item.status] && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setActiveStatusHelp(activeStatusHelp === item.status ? null : item.status);
                      }}
                      className="hover:scale-110 transition-transform"
                    >
                      <HelpCircle className="h-5 w-5 opacity-80 hover:opacity-100" />
                    </button>
                  )}
                </div>
                <div className="text-6xl font-bold tracking-tight text-center mb-1 relative z-10 drop-shadow-sm">{item.count}</div>
                <p className="text-center text-base font-medium text-white/85 relative z-10">{item.value}</p>
                <div className="absolute inset-x-0 bottom-0 h-1 bg-gradient-to-r from-transparent via-white/50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
                {item.status === "sensitization_monitoring" && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full mt-4 bg-white/20 border-white/30 text-white hover:bg-white/30 relative z-10"
                    onClick={(e) => {
                      e.stopPropagation();
                      setIsSensitizationDialogOpen(true);
                    }}
                  >
                    <Eye className="h-4 w-4 mr-2" />
                    Ver Movimentos
                  </Button>
                )}
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Status Help Dialog */}
        {activeStatusHelp && statusHelpInfo[activeStatusHelp] && (
          <div 
            className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4 animate-in fade-in-0"
            onClick={() => setActiveStatusHelp(null)}
          >
            <div 
              className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full animate-in zoom-in-95 slide-in-from-bottom-4"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="p-8 relative">
                <button
                  onClick={() => setActiveStatusHelp(null)}
                  className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 transition-colors"
                >
                  <X className="h-6 w-6" />
                </button>
                
                <div className="flex items-start gap-6">
                  <div className="relative">
                    <img
                      src={statusHelpInfo[activeStatusHelp].avatar}
                      alt={statusHelpInfo[activeStatusHelp].avatarName}
                      className="w-32 h-32 rounded-full border-4 border-[hsl(211,70%,50%)] shadow-lg animate-bounce object-cover"
                      style={{ animationDuration: '2s' }}
                    />
                  </div>
                  
                  <div className="flex-1">
                    <div className="bg-[hsl(211,70%,50%)] text-white rounded-2xl p-6 relative shadow-xl animate-in slide-in-from-left-5">
                      <div className="absolute -left-3 top-8 w-0 h-0 border-t-8 border-t-transparent border-b-8 border-b-transparent border-r-8 border-r-[hsl(211,70%,50%)]" />
                      <p className="text-sm font-semibold mb-2 opacity-90">
                        {statusHelpInfo[activeStatusHelp].avatarName}
                      </p>
                      <p className="text-lg leading-relaxed">
                        {statusHelpInfo[activeStatusHelp].message}
                      </p>
                    </div>
                  </div>
                </div>
                
                <div className="mt-6 flex justify-end">
                  <Button
                    onClick={() => setActiveStatusHelp(null)}
                    className="bg-[hsl(211,70%,50%)] hover:bg-[hsl(211,70%,45%)] text-white"
                  >
                    Entendi!
                  </Button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Alertas */}
        {totalOverdue > 0 && (
          <Alert className="mb-8 bg-white/10 backdrop-blur-md border-white/20">
            <AlertTriangle className="h-4 w-4 text-white" />
            <AlertDescription className="text-white">
              <strong>Atenção!</strong> Você possui <strong>{totalOverdue} propostas</strong> pendentes há mais de 8 dias desde a quitação.
            </AlertDescription>
          </Alert>
        )}

        {/* Comparison Dashboard - Show FIRST for all product types */}
        <Card className="bg-white/10 backdrop-blur-md border-white/20 shadow-[0_8px_32px_rgba(0,0,0,0.2)] mb-8">
          <CardHeader>
            <CardTitle className="text-white">Comparativo de Performance entre Produtos</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
              <div className="bg-white/5 rounded-lg p-4 border border-white/10">
                <h4 className="text-white font-semibold mb-3">Seguro de Vida</h4>
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-white/70">Total Emissões:</span>
                    <span className="text-white font-bold">1.399</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-white/70">Taxa Aprovação:</span>
                    <span className="text-green-400 font-bold">94.7%</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-white/70">Ticket Médio:</span>
                    <span className="text-white font-bold">R$ 5.420</span>
                  </div>
                </div>
              </div>
              <div className="bg-white/5 rounded-lg p-4 border border-white/10">
                <h4 className="text-white font-semibold mb-3">Previdência</h4>
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-white/70">Total Emissões:</span>
                    <span className="text-white font-bold">1.045</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-white/70">Taxa Aprovação:</span>
                    <span className="text-green-400 font-bold">95.8%</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-white/70">Ticket Médio:</span>
                    <span className="text-white font-bold">R$ 8.750</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-white/70">Portabilidades:</span>
                    <span className="text-blue-400 font-bold">196</span>
                  </div>
                </div>
              </div>
              <div className="bg-white/5 rounded-lg p-4 border border-white/10">
                <h4 className="text-white font-semibold mb-3">Prestamista</h4>
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-white/70">Total Emissões:</span>
                    <span className="text-white font-bold">1.300</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-white/70">Taxa Aprovação:</span>
                    <span className="text-green-400 font-bold">93.3%</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-white/70">Ticket Médio:</span>
                    <span className="text-white font-bold">R$ 3.850</span>
                  </div>
                </div>
              </div>
            </div>
            
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={[
                { tipo: "Vida", emissoes: 1399, declínios: 74 },
                { tipo: "Previdência", emissoes: 1045, declínios: 46 },
                { tipo: "Prestamista", emissoes: 1300, declínios: 92 }
              ]}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                <XAxis dataKey="tipo" stroke="rgba(255,255,255,0.8)" />
                <YAxis stroke="rgba(255,255,255,0.8)" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "rgba(255,255,255,0.95)",
                    border: "1px solid rgba(0,0,0,0.1)",
                    borderRadius: "8px",
                  }}
                />
                <Legend wrapperStyle={{ color: "white" }} />
                <Bar dataKey="emissoes" name="Emissões" fill="#3E96D1" radius={[4, 4, 0, 0]} />
                <Bar dataKey="declínios" name="Declínios" fill="#DB6A1E" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>


        {/* Gráfico 2: Status de Seguros */}
        <Card className="bg-white/10 backdrop-blur-md border-white/20 shadow-[0_8px_32px_rgba(0,0,0,0.2)] mb-8">
          <CardHeader>
            <div className="flex items-center justify-between flex-wrap gap-4">
              <CardTitle className="text-white">Status de Seguros</CardTitle>
              <div className="flex items-center gap-3">
                <DateFilters 
                  selectedDay={selectedDay}
                  selectedMonth={selectedMonth}
                  selectedYear={selectedYear}
                  onDayChange={setSelectedDay}
                  onMonthChange={setSelectedMonth}
                  onYearChange={setSelectedYear}
                />
                <Button
                  onClick={() => toast({ title: "Exportando...", description: "Relatório analítico de Status de Seguros está sendo exportado." })}
                  size="sm"
                  className="bg-white/20 hover:bg-white/30 text-white border border-white/30"
                >
                  <Download className="h-4 w-4 mr-2" />
                  Exportar
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={insuranceStatusData}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={({ name, percentage }: any) => `${name}: ${percentage}%`}
                    outerRadius={100}
                    fill="#3E96D1"
                    dataKey="value"
                  >
                    {insuranceStatusData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: "rgba(255,255,255,0.95)", 
                      border: "1px solid rgba(255,255,255,0.3)",
                      borderRadius: "8px",
                      color: "hsl(211,100%,25%)"
                    }}
                  />
                  <Legend wrapperStyle={{ color: "white" }} />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex flex-col justify-center gap-4">
                {insuranceStatusData.map((item, index) => (
                  <div key={index} className="flex items-center justify-between p-4 bg-white/5 rounded-lg border border-white/10">
                    <div className="flex items-center gap-3">
                      <div className="w-4 h-4 rounded-full" style={{ backgroundColor: item.color }} />
                      <span className="font-medium text-white">{item.name}</span>
                    </div>
                    <div className="text-right">
                      <div className="text-2xl font-bold text-white">{item.value}</div>
                      <div className="text-sm text-white/70">{item.percentage}%</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Gráfico 3: Motivos de Declínio */}
        <Card className="bg-white/10 backdrop-blur-md border-white/20 shadow-[0_8px_32px_rgba(0,0,0,0.2)] mb-8">
          <CardHeader>
            <div className="flex items-center justify-between flex-wrap gap-4">
              <CardTitle className="text-white">Motivos de Declínio</CardTitle>
              <div className="flex items-center gap-3">
                <DateFilters 
                  selectedDay={selectedDay}
                  selectedMonth={selectedMonth}
                  selectedYear={selectedYear}
                  onDayChange={setSelectedDay}
                  onMonthChange={setSelectedMonth}
                  onYearChange={setSelectedYear}
                />
                <Button
                  onClick={() => toast({ title: "Exportando...", description: "Relatório analítico de Motivos de Declínio está sendo exportado." })}
                  size="sm"
                  className="bg-white/20 hover:bg-white/30 text-white border border-white/30"
                >
                  <Download className="h-4 w-4 mr-2" />
                  Exportar
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={350}>
              <BarChart data={declineReasonsData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                <XAxis type="number" stroke="white" />
                <YAxis type="category" dataKey="reason" stroke="white" width={150} />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: "rgba(255,255,255,0.95)", 
                    border: "1px solid rgba(255,255,255,0.3)",
                    borderRadius: "8px",
                    color: "hsl(211,100%,25%)"
                  }}
                />
                <Bar dataKey="count" fill="#3E96D1" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Gráfico 4: Propostas Pendentes por Motivo */}
        <Card className="bg-white/10 backdrop-blur-md border-white/20 shadow-[0_8px_32px_rgba(0,0,0,0.2)] mb-8">
          <CardHeader>
            <div className="flex items-center justify-between flex-wrap gap-4">
              <CardTitle className="text-white">Propostas Pendentes por Motivo</CardTitle>
              <Button
                onClick={() => toast({ title: "Exportando...", description: "Relatório analítico de Propostas Pendentes está sendo exportado." })}
                size="sm"
                className="bg-white/20 hover:bg-white/30 text-white border border-white/30"
              >
                <Download className="h-4 w-4 mr-2" />
                Exportar
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {pendingByReasonData.map((item, index) => (
                <div key={index} className="p-4 bg-white/5 rounded-lg border border-white/10">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-medium text-white">{item.reason}</span>
                    <div className="flex items-center gap-4">
                      <Badge variant="outline" className="bg-white/10 text-white border-white/20">
                        {item.count} total
                      </Badge>
                      {item.overdue > 0 && (
                        <Badge className="gap-1 bg-red-500/80 text-white">
                          <AlertTriangle className="h-3 w-3" />
                          {item.overdue} &gt;8 dias
                        </Badge>
                      )}
                    </div>
                  </div>
                  <div className="w-full bg-white/10 rounded-full h-2">
                    <div 
                      className="bg-white/70 h-2 rounded-full transition-all"
                      style={{ width: `${(item.count / 127) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Gráfico 5: Propostas Pendentes de Sensibilização */}
        <Card className="bg-white/10 backdrop-blur-md border-white/20 shadow-[0_8px_32px_rgba(0,0,0,0.2)] mb-8">
          <CardHeader>
            <div className="flex items-center justify-between flex-wrap gap-4">
              <CardTitle className="text-white">Propostas Pendentes de Sensibilização</CardTitle>
              <div className="flex items-center gap-3">
                <DateFilters 
                  selectedDay={selectedDay}
                  selectedMonth={selectedMonth}
                  selectedYear={selectedYear}
                  onDayChange={setSelectedDay}
                  onMonthChange={setSelectedMonth}
                  onYearChange={setSelectedYear}
                />
                <Button
                  onClick={() => toast({ title: "Exportando...", description: "Relatório analítico de Sensibilização está sendo exportado." })}
                  size="sm"
                  className="bg-white/20 hover:bg-white/30 text-white border border-white/30"
                >
                  <Download className="h-4 w-4 mr-2" />
                  Exportar
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={sensitizationData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                <XAxis dataKey="month" stroke="white" />
                <YAxis stroke="white" />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: "rgba(255,255,255,0.95)", 
                    border: "1px solid rgba(255,255,255,0.3)",
                    borderRadius: "8px",
                    color: "hsl(211,100%,25%)"
                  }}
                />
                <Line 
                  type="monotone" 
                  dataKey="count" 
                  stroke="white" 
                  strokeWidth={3}
                  dot={{ fill: "white", r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Gráfico 6: Resultado Geral - Emissões vs Declínios */}
        <Card className="bg-white/10 backdrop-blur-md border-white/20 shadow-[0_8px_32px_rgba(0,0,0,0.2)] mb-8">
          <CardHeader>
            <div className="flex items-center justify-between flex-wrap gap-4">
              <CardTitle className="text-white">Resultado Geral - Emissões vs Declínios</CardTitle>
              <div className="flex items-center gap-3">
                <DateFilters 
                  selectedMonth={selectedMonth}
                  selectedYear={selectedYear}
                  onMonthChange={setSelectedMonth}
                  onYearChange={setSelectedYear}
                  showDay={false}
                />
                <Button
                  onClick={() => toast({ title: "Exportando...", description: "Relatório analítico de Resultado Geral está sendo exportado." })}
                  size="sm"
                  className="bg-white/20 hover:bg-white/30 text-white border border-white/30"
                >
                  <Download className="h-4 w-4 mr-2" />
                  Exportar
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
              <div className="p-6 bg-white/5 rounded-lg border border-white/10">
                <div className="flex items-center gap-2 mb-2">
                  <TrendingUp className="h-5 w-5 text-white" />
                  <span className="text-sm text-white/70">Total Emissões</span>
                </div>
                <div className="text-3xl font-bold text-white">1.310</div>
                <div className="text-lg text-white/70">R$ 7.465.000</div>
              </div>
              <div className="p-6 bg-white/5 rounded-lg border border-white/10">
                <div className="flex items-center gap-2 mb-2">
                  <TrendingDown className="h-5 w-5 text-red-400" />
                  <span className="text-sm text-white/70">Total Declínios</span>
                </div>
                <div className="text-3xl font-bold text-red-400">89</div>
                <div className="text-lg text-white/70">R$ 505.000</div>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={350}>
              <BarChart data={generalResultData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                <XAxis dataKey="month" stroke="white" />
                <YAxis stroke="white" />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: "rgba(255,255,255,0.95)", 
                    border: "1px solid rgba(255,255,255,0.3)",
                    borderRadius: "8px",
                    color: "hsl(211,100%,25%)"
                  }}
                />
                <Legend wrapperStyle={{ color: "white" }} />
                <Bar dataKey="emissoesCount" name="Emissões" fill="#3E96D1" radius={[4, 4, 0, 0]} />
                <Bar dataKey="decliniosCount" name="Declínios" fill="#DB6A1E" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Gráfico 7: Emissões e Declínios por Produto */}
        <Card className="bg-white/10 backdrop-blur-md border-white/20 shadow-[0_8px_32px_rgba(0,0,0,0.2)] mb-8">
          <CardHeader>
            <div className="flex items-center justify-between flex-wrap gap-4">
              <CardTitle className="text-white">Emissões e Declínios por Produto</CardTitle>
              <div className="flex items-center gap-3">
                <DateFilters 
                  selectedDay={selectedDay}
                  selectedMonth={selectedMonth}
                  selectedYear={selectedYear}
                  onDayChange={setSelectedDay}
                  onMonthChange={setSelectedMonth}
                  onYearChange={setSelectedYear}
                />
                <Button
                  onClick={() => toast({ title: "Exportando...", description: "Relatório analítico por Produto está sendo exportado." })}
                  size="sm"
                  className="bg-white/20 hover:bg-white/30 text-white border border-white/30"
                >
                  <Download className="h-4 w-4 mr-2" />
                  Exportar
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={350}>
              <BarChart data={productResultData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                <XAxis dataKey="product" stroke="white" />
                <YAxis stroke="white" />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: "rgba(255,255,255,0.95)", 
                    border: "1px solid rgba(255,255,255,0.3)",
                    borderRadius: "8px",
                    color: "hsl(211,100%,25%)"
                  }}
                />
                <Legend wrapperStyle={{ color: "white" }} />
                <Bar dataKey="emissoes" name="Emissões" fill="#3E96D1" radius={[4, 4, 0, 0]} />
                <Bar dataKey="declínios" name="Declínios" fill="#DB6A1E" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Acompanhamento de Portabilidade - Only for Previdência */}
        {productType === "previdencia" && (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
              {/* Card de Acompanhamento de Portabilidade */}
              <Card className="bg-white/10 backdrop-blur-md border-white/20 shadow-[0_8px_32px_rgba(0,0,0,0.2)]">
                <CardHeader>
                  <div className="flex items-center justify-between flex-wrap gap-4">
                    <CardTitle className="text-white">Acompanhamento de Portabilidade</CardTitle>
                    <div className="flex items-center gap-3">
                      <div className="flex items-center gap-2">
                        <input
                          type="date"
                          value={portabilityStartDate}
                          onChange={(e) => setPortabilityStartDate(e.target.value)}
                          className="px-3 py-1 text-sm bg-white/10 border border-white/20 text-white rounded-md"
                        />
                        <span className="text-white">até</span>
                        <input
                          type="date"
                          value={portabilityEndDate}
                          onChange={(e) => setPortabilityEndDate(e.target.value)}
                          className="px-3 py-1 text-sm bg-white/10 border border-white/20 text-white rounded-md"
                        />
                      </div>
                      <Button
                        onClick={() => {
                          const portabilityData = [
                            { status: "Pendente", quantidade: 45, valor: 2350000 },
                            { status: "Concluída", quantidade: 128, valor: 6890000 },
                            { status: "Recusada", quantidade: 23, valor: 1180000 }
                          ];
                          
                          const exportData = portabilityData.map(item => ({
                            "Status": item.status,
                            "Quantidade": item.quantidade,
                            "Valor": `R$ ${(item.valor / 1000).toFixed(0)}k`
                          }));
                          
                          const ws = XLSX.utils.json_to_sheet(exportData);
                          const wb = XLSX.utils.book_new();
                          XLSX.utils.book_append_sheet(wb, ws, "Portabilidades");
                          XLSX.writeFile(wb, `Portabilidades_${new Date().toISOString().split('T')[0]}.xlsx`);
                          
                          toast({ title: "Exportação Concluída", description: "Dados de portabilidade exportados para Excel." });
                        }}
                        size="sm"
                        className="bg-white/20 hover:bg-white/30 text-white border border-white/30"
                      >
                        <Download className="h-4 w-4 mr-2" />
                        Exportar
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* Status das Solicitações */}
                  <div>
                    <h3 className="text-white font-semibold mb-4">Status das Solicitações</h3>
                    <ResponsiveContainer width="100%" height={300}>
                      <BarChart data={[
                        { status: "Pendente", quantidade: 45, valor: 2350000 },
                        { status: "Concluída", quantidade: 128, valor: 6890000 },
                        { status: "Recusada", quantidade: 23, valor: 1180000 }
                      ]}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                        <XAxis dataKey="status" stroke="white" />
                        <YAxis stroke="white" />
                        <Tooltip 
                          contentStyle={{ 
                            backgroundColor: "rgba(255,255,255,0.95)", 
                            border: "1px solid rgba(255,255,255,0.3)",
                            borderRadius: "8px",
                            color: "hsl(211,100%,25%)"
                          }}
                          formatter={(value, name) => {
                            if (name === "valor") {
                              return `R$ ${(Number(value) / 1000).toFixed(0)}k`;
                            }
                            return value;
                          }}
                        />
                        <Legend wrapperStyle={{ color: "white" }} />
                        <Bar dataKey="quantidade" name="Quantidade" fill="#3E96D1" />
                        <Bar dataKey="valor" name="Valor (R$)" fill="hsl(142,76%,36%)" />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Principais Bancos */}
                  <div>
                    <h3 className="text-white font-semibold mb-4">Principais Bancos de Origem</h3>
                    <ResponsiveContainer width="100%" height={300}>
                      <PieChart>
                        <Pie
                          data={[
                            { name: "Brasilprev", value: 58, color: "hsl(211,80%,60%)" },
                            { name: "Itaú", value: 42, color: "hsl(27,100%,47%)" },
                            { name: "Zurich Santander", value: 35, color: "hsl(142,76%,36%)" },
                            { name: "Outros", value: 61, color: "hsl(0,0%,60%)" }
                          ]}
                          cx="50%"
                          cy="50%"
                          labelLine={false}
                          label={({ name, percent }: any) => `${name} ${(percent * 100).toFixed(0)}%`}
                          outerRadius={100}
                          fill="#3E96D1"
                          dataKey="value"
                        >
                          {[
                            { name: "Brasilprev", value: 58, color: "hsl(211,80%,60%)" },
                            { name: "Itaú", value: 42, color: "hsl(27,100%,47%)" },
                            { name: "Zurich Santander", value: 35, color: "hsl(142,76%,36%)" },
                            { name: "Outros", value: 61, color: "hsl(0,0%,60%)" }
                          ].map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip 
                          contentStyle={{ 
                            backgroundColor: "rgba(255,255,255,0.95)", 
                            border: "1px solid rgba(255,255,255,0.3)",
                            borderRadius: "8px",
                            color: "hsl(211,100%,25%)"
                          }}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                {/* Portabilidades Recusadas */}
                <div className="mt-6">
                  <h3 className="text-white font-semibold mb-4">Principais Motivos de Recusa</h3>
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={[
                      { motivo: "Documentação Incompleta", count: 8 },
                      { motivo: "Prazo Vencido", count: 6 },
                      { motivo: "Dados Divergentes", count: 5 },
                      { motivo: "Cancelamento Cliente", count: 4 }
                    ]} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                      <XAxis type="number" stroke="white" />
                      <YAxis type="category" dataKey="motivo" stroke="white" width={150} />
                      <Tooltip 
                        contentStyle={{ 
                          backgroundColor: "rgba(255,255,255,0.95)", 
                          border: "1px solid rgba(255,255,255,0.3)",
                          borderRadius: "8px",
                          color: "hsl(211,100%,25%)"
                        }}
                      />
                      <Bar dataKey="count" name="Quantidade" fill="hsl(0,84%,60%)" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                </CardContent>
              </Card>

              {/* Card de Detalhamento de Portabilidades */}
              <Card 
                className="bg-white/10 backdrop-blur-md border-white/20 shadow-[0_8px_32px_rgba(0,0,0,0.2)] cursor-pointer hover:bg-white/15 transition-all"
                onClick={() => navigate("/caixa-seguro/portabilidades")}
              >
                <CardHeader>
                  <CardTitle className="text-white flex items-center justify-between">Detalhamento de Portabilidades
                    <ArrowRight className="h-5 w-5" />
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div className="p-4 bg-white/5 rounded-lg border border-white/10">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-white/70">Total de Solicitações</span>
                        <span className="text-2xl font-bold text-white">196</span>
                      </div>
                      <div className="text-sm text-white/60">Todas as portabilidades</div>
                    </div>
                    
                    <div className="p-4 bg-yellow-500/10 rounded-lg border border-yellow-500/30">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-yellow-300">Pendentes {'>'} 8 dias</span>
                        <span className="text-2xl font-bold text-yellow-300">12</span>
                      </div>
                      <div className="text-sm text-yellow-200/80">Requer atenção urgente</div>
                    </div>

                    <Button 
                      className="w-full bg-white/20 hover:bg-white/30 text-white border border-white/30"
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate("/caixa-seguro/portabilidades");
                      }}
                    >
                      Ver Todas as Portabilidades
                    </Button>
                  </div>
                </CardContent>
              </Card>

              {/* Pendências Fora da Conformidade > 500k */}
              <Card className="bg-white/10 backdrop-blur-md border-white/20 shadow-[0_8px_32px_rgba(0,0,0,0.2)] mt-8 col-span-1 lg:col-span-2">
                <CardHeader>
                  <CardTitle className="text-white flex items-center justify-between">
                    <span>⚠️ Pendências Fora da Conformidade {'>'} R$ 500k</span>
                    <Button 
                      onClick={() => navigate('/caixa-seguro/acompanhamento/pending_documentation?substatus=non_compliant')}
                      className="bg-white/20 hover:bg-white/30 text-white"
                    >
                      Ver Detalhamento
                      <ArrowRight className="w-4 h-4 ml-2" />
                    </Button>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="mb-4 p-4 bg-red-500/10 rounded-lg border border-red-500/30">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-red-300 font-semibold">Total de Propostas</span>
                      <span className="text-3xl font-bold text-red-300">2</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-red-200/80">Valor Total</span>
                      <span className="text-2xl font-bold text-red-200">R$ 1.470.000,00</span>
                    </div>
                  </div>

                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={[
                      { proposta: "Proposta 8047413032437-2", valor: 650000, quantidade: 1 },
                      { proposta: "Proposta 8047413032438-3", valor: 820000, quantidade: 1 }
                    ]} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                      <XAxis type="number" stroke="white" />
                      <YAxis type="category" dataKey="proposta" stroke="white" width={180} />
                      <Tooltip 
                        contentStyle={{ 
                          backgroundColor: "rgba(255,255,255,0.95)", 
                          border: "1px solid rgba(255,255,255,0.3)",
                          borderRadius: "8px",
                          color: "hsl(211,100%,25%)"
                        }}
                        formatter={(value) => `R$ ${Number(value).toLocaleString('pt-BR')}`}
                      />
                      <Bar dataKey="valor" name="Valor" fill="hsl(0,84%,60%)" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>

                  <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div className="p-3 bg-white/5 rounded-lg border border-white/10 hover:bg-white/10 transition-colors">
                      <div className="flex items-center justify-between">
                        <span className="text-white/70 text-sm">Proposta 8047413032437-2</span>
                        <span className="text-white font-bold">R$ 650.000,00</span>
                      </div>
                      <div className="text-xs text-white/60 mt-1">MARCOS VINÍCIUS ALMEIDA - 15 dias pendente</div>
                    </div>
                    <div className="p-3 bg-white/5 rounded-lg border border-white/10 hover:bg-white/10 transition-colors">
                      <div className="flex items-center justify-between">
                        <span className="text-white/70 text-sm">Proposta 8047413032438-3</span>
                        <span className="text-white font-bold">R$ 820.000,00</span>
                      </div>
                      <div className="text-xs text-white/60 mt-1">JULIANA COSTA PEREIRA - 18 dias pendente</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </>
        )}
      </main>

      <SensitizationDialog 
        open={isSensitizationDialogOpen} 
        onOpenChange={setIsSensitizationDialogOpen}
      />

      {showProductTour && (
        <ProductTour 
          productType={productType} 
          onClose={() => setShowProductTour(false)} 
        />
      )}

      <NPSDialog open={showNPSDialog} onOpenChange={setShowNPSDialog} />

      {productType === "previdencia" && <LeoAssistant pageContext="Previdência - Gestão Comercial" />}
      {productType === "vida" && <DiegoAssistant pageContext="Seguro de Vida - Gestão Comercial" />}
      {productType === "prestamista" && <LariAssistant pageContext="Prestamista - Gestão Comercial" />}
    </div>
  );
};

export default SalesManagement;

