import React, { useState } from "react";
import MenuButton from "../components/MenuButton";
import ProposalWorkflowSheet from "../components/ProposalWorkflowSheet";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Legend, Tooltip, LineChart, Line } from "recharts";
import { Loader2, Star, Filter, AlertTriangle } from "lucide-react";
import { useToast } from "../hooks/use-toast";

const AICommercialPanel = () => {
  const { toast } = useToast();
  const [aiResult, setAiResult] = useState<string>("");
  const [alertText, setAlertText] = useState<string>("Aguardando análise da IA...");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [npsRatingFilter, setNpsRatingFilter] = useState<string>("all");
  const [npsDateFilter, setNpsDateFilter] = useState<string>("all");
  const [negativeAlertShown, setNegativeAlertShown] = useState(false);

  // Mock NPS data
  const npsData = [
    { id: 1, name: "Maria Santos", rating: 5, comment: "Adorei as novas funcionalidades! O painel está muito intuitivo e fácil de usar.", date: "2024-11-20", anonymous: false },
    { id: 2, name: "Anônimo", rating: 4, comment: "Muito bom! Só sinto falta de notificações mais detalhadas sobre os sinistros.", date: "2024-11-19", anonymous: true },
    { id: 3, name: "João Silva", rating: 5, comment: "Perfeito! A visualização dos dados está excelente. Gostaria de ver mais gráficos interativos.", date: "2024-11-18", anonymous: false },
    { id: 4, name: "Anônimo", rating: 3, comment: "O extrato do cliente poderia ser melhor organizado. Às vezes fica confuso encontrar informações específicas.", date: "2024-11-17", anonymous: true },
    { id: 5, name: "Paula Costa", rating: 5, comment: "Sistema incrível! Facilitou muito meu trabalho diário. A busca rápida de propostas é fantástica.", date: "2024-11-16", anonymous: false },
    { id: 6, name: "Anônimo", rating: 2, comment: "Poderíamos ter mais opções de filtros avançados. O sistema às vezes fica lento.", date: "2024-11-15", anonymous: true },
    { id: 7, name: "Carlos Mendes", rating: 4, comment: "Muito útil! Sugiro adicionar notificações push para alterações importantes nas propostas.", date: "2024-11-14", anonymous: false },
    { id: 8, name: "Anônimo", rating: 5, comment: "Excelente plataforma! Os relatórios automatizados economizam muito tempo.", date: "2024-11-13", anonymous: true },
    { id: 9, name: "Ana Paula", rating: 4, comment: "Ótimo sistema! Seria interessante ter integração com o WhatsApp Business para facilitar contato com clientes.", date: "2024-11-12", anonymous: false },
    { id: 10, name: "Anônimo", rating: 3, comment: "Bom, mas precisa melhorar a visualização mobile. Alguns botões ficam pequenos demais.", date: "2024-11-11", anonymous: true },
  ];

  const getRatingDistribution = () => {
    const distribution = [
      { rating: 5, count: 0 },
      { rating: 4, count: 0 },
      { rating: 3, count: 0 },
      { rating: 2, count: 0 },
      { rating: 1, count: 0 },
    ];
    
    npsData.forEach(item => {
      const idx = distribution.findIndex(d => d.rating === item.rating);
      if (idx !== -1) distribution[idx].count++;
    });
    
    return distribution;
  };

  const getFilteredNpsData = () => {
    let filtered = npsData;
    
    if (npsRatingFilter !== "all") {
      filtered = filtered.filter(item => item.rating === parseInt(npsRatingFilter));
    }
    
    if (npsDateFilter !== "all") {
      const today = new Date();
      const filterDate = new Date(today);
      
      if (npsDateFilter === "7days") {
        filterDate.setDate(today.getDate() - 7);
      } else if (npsDateFilter === "30days") {
        filterDate.setDate(today.getDate() - 30);
      }
      
      filtered = filtered.filter(item => new Date(item.date) >= filterDate);
    }
    
    return filtered;
  };

  const calculateNPSScore = () => {
    const total = npsData.length;
    const promoters = npsData.filter(d => d.rating >= 4).length;
    const detractors = npsData.filter(d => d.rating <= 2).length;
    return Math.round(((promoters - detractors) / total) * 100);
  };

  const ratingDistribution = getRatingDistribution();
  const filteredNpsData = getFilteredNpsData();
  const npsScore = calculateNPSScore();

  // Termos negativos para alerta
  const negativeTerms = ['lento', 'erro', 'problema', 'ruim', 'difícil', 'confuso', 'travando', 'bug', 'demora', 'falha', 'péssimo', 'horrível', 'piorou', 'complicado'];

  // Função para calcular frequência de palavras dos comentários
  const getWordFrequency = () => {
    const stopWords = ['a', 'o', 'e', 'de', 'da', 'do', 'que', 'em', 'para', 'com', 'um', 'uma', 'os', 'as', 'no', 'na', 'é', 'são', 'muito', 'mais', 'mas', 'já', 'se', 'como', 'por', 'está', 'ao', 'das', 'dos', 'às', 'aos', 'esse', 'essa', 'isso', 'este', 'esta', 'isto', 'seu', 'sua', 'seus', 'suas', 'meu', 'minha', 'me', 'nos', 'só', 'ou', 'também', 'ter', 'ser', 'foi', 'tem', 'quando', 'fica', 'ficam', 'algumas', 'alguns', 'sobre', 'bem', 'bom'];
    
    const wordCount: { [key: string]: number } = {};
    
    filteredNpsData.forEach(review => {
      const words = review.comment
        .toLowerCase()
        .replace(/[.,!?;:()""'']/g, '')
        .split(/\s+/)
        .filter(word => word.length > 3 && !stopWords.includes(word));
      
      words.forEach(word => {
        wordCount[word] = (wordCount[word] || 0) + 1;
      });
    });

    const sortedWords = Object.entries(wordCount)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 15);
    
    const maxCount = sortedWords.length > 0 ? sortedWords[0][1] : 1;
    const minCount = sortedWords.length > 0 ? sortedWords[sortedWords.length - 1][1] : 1;

    return sortedWords.map(([word, count], index) => {
      const isNegative = negativeTerms.includes(word);
      // Escala de tamanho baseada na frequência relativa
      const ratio = (count - minCount) / (maxCount - minCount || 1);
      let sizeClass = 'text-sm';
      if (ratio >= 0.8) sizeClass = 'text-3xl font-bold';
      else if (ratio >= 0.6) sizeClass = 'text-2xl font-bold';
      else if (ratio >= 0.4) sizeClass = 'text-xl font-semibold';
      else if (ratio >= 0.2) sizeClass = 'text-lg font-medium';
      else sizeClass = 'text-base';

      return {
        word,
        count,
        size: sizeClass,
        color: isNegative ? 'hsl(0, 80%, 60%)' : `hsl(${(index * 25) % 360}, ${60 + (index % 3) * 10}%, ${55 + (index % 4) * 5}%)`,
        isNegative
      };
    });
  };

  const wordCloudData = getWordFrequency();

  // Detectar termos negativos frequentes e mostrar alerta
  const frequentNegativeTerms = wordCloudData.filter(item => item.isNegative && item.count >= 2);
  
  // Efeito para mostrar alerta de termos negativos
  React.useEffect(() => {
    if (frequentNegativeTerms.length > 0 && !negativeAlertShown) {
      toast({
        variant: "destructive",
        title: "⚠️ Alerta: Termos Negativos Frequentes",
        description: `Detectados termos de insatisfação: ${frequentNegativeTerms.map(t => `"${t.word}" (${t.count}x)`).join(', ')}. Recomenda-se investigar as causas.`,
      });
      setNegativeAlertShown(true);
    }
  }, [frequentNegativeTerms.length, negativeAlertShown, toast]);

  // Reset alert when filter changes
  React.useEffect(() => {
    setNegativeAlertShown(false);
  }, [npsRatingFilter, npsDateFilter]);

  // Comparativo de Produtos - Dados robustos
  const productComparativeData = [
    { produto: "Vida Multipremiado", emissoes: 450, declínios: 25, pendentes: 38, conversao: 94.7, ticketMedio: 2850, crescimento: 12 },
    { produto: "Vida Mulher", emissoes: 320, declínios: 18, pendentes: 22, conversao: 94.6, ticketMedio: 2200, crescimento: 8 },
    { produto: "Vida Conforto", emissoes: 280, declínios: 32, pendentes: 45, conversao: 89.7, ticketMedio: 1500, crescimento: -3 },
    { produto: "Perda de Renda", emissoes: 349, declínios: 28, pendentes: 31, conversao: 92.5, ticketMedio: 2400, crescimento: 15 },
    { produto: "Prev Crescer", emissoes: 380, declínios: 15, pendentes: 18, conversao: 96.2, ticketMedio: 45000, crescimento: 22 },
    { produto: "Prev Mulher", emissoes: 290, declínios: 12, pendentes: 14, conversao: 96.0, ticketMedio: 35000, crescimento: 18 },
  ];

  // Tendência mensal por categoria
  const monthlyTrendData = [
    { mes: "Jul", vida: 850, previdencia: 520, prestamista: 380 },
    { mes: "Ago", vida: 920, previdencia: 580, prestamista: 410 },
    { mes: "Set", vida: 980, previdencia: 650, prestamista: 450 },
    { mes: "Out", vida: 1050, previdencia: 720, prestamista: 490 },
    { mes: "Nov", vida: 1120, previdencia: 800, prestamista: 530 },
  ];

  // Correlação idade x valor médio
  const ageValueCorrelation = [
    { faixa: "18-25", ticketMedio: 1200, quantidade: 180 },
    { faixa: "26-35", ticketMedio: 2100, quantidade: 420 },
    { faixa: "36-45", ticketMedio: 3200, quantidade: 580 },
    { faixa: "46-55", ticketMedio: 4500, quantidade: 390 },
    { faixa: "56-65", ticketMedio: 5800, quantidade: 210 },
  ];

  // Motivos de declínio por produto
  const declineByProduct = [
    { produto: "Vida Conforto", documentacao: 15, saude: 12, renda: 5 },
    { produto: "Perda de Renda", documentacao: 8, saude: 5, renda: 15 },
    { produto: "Vida Mulher", documentacao: 10, saude: 5, renda: 3 },
    { produto: "Multipremiado", documentacao: 12, saude: 8, renda: 5 },
  ];

  // Performance por região
  const regionPerformance = [
    { regiao: "Sul", meta: 1500, realizado: 1680, conversao: 95 },
    { regiao: "Sudeste", meta: 2500, realizado: 2350, conversao: 92 },
    { regiao: "Nordeste", meta: 1200, realizado: 1100, conversao: 88 },
    { regiao: "Centro-Oeste", meta: 800, realizado: 920, conversao: 94 },
    { regiao: "Norte", meta: 600, realizado: 480, conversao: 85 },
  ];


  const handleAIAnalysis = (type: string) => {
    setIsAnalyzing(true);
    
    setTimeout(() => {
      let result = "";
      
      switch(type) {
        case "pendencias":
          result = "📊 Análise de Pendências:\n\n1️⃣ Padrão identificado: Vida Conforto e Perda de Renda apresentam maior tempo de pendência (6 e 5 dias).\n2️⃣ Região Sul concentra 40% das pendências.\n3️⃣ Faixa etária 45-60 anos tem maior índice de atraso.\n4️⃣ Sugestão: Implementar follow-up automatizado após 3 dias de pendência.\n\n💡 Insights Previdência:\n• Portabilidades pendentes há mais de 8 dias: 12 solicitações\n• Principal banco cedente: Brasilprev (35% das solicitações)\n• Taxa de conclusão de portabilidade: 65%";
          break;
        case "previsao":
          result = "🤖 Previsão de Risco:\n\n• Vida Conforto: 68% de risco de pendência (faixa etária 25-35)\n• Perda de Renda: 55% de risco (valores acima de R$ 2.500)\n• Vida Mulher: 32% de risco (região Sul)\n\n📈 Previdência:\n• Prev Crescer: 42% de risco de recusa em portabilidades\n• Prev Mulher: 28% de risco (documentação incompleta)\n• Prev Ativa: 35% de risco (valores incompatíveis)\n\nRecomendação: Priorizar contato proativo nas primeiras 24h e revisar documentação antes do envio.";
          break;
        case "aprendizado":
          result = "🧠 Insights de Machine Learning:\n\n✅ Produtos com maior taxa de conversão:\n• Vida Mulher na região Sul (89% de efetividade)\n• Multipremiado na região Sudeste (85%)\n\n⚠️ Produtos com alto índice de declínio:\n• Perda de Renda no Centro-Oeste (renda insuficiente)\n• Vida Conforto no Norte (histórico de saúde)\n\n💼 Insights Previdência:\n• Prev Crescer: melhor performance em região Sudeste (taxa de conversão 92%)\n• Portabilidades de Itaú têm tempo médio de processamento 30% menor\n• Prev Mulher: público-alvo 28-45 anos com maior taxa de adesão\n• Portabilidades acima de R$ 100k têm 15% mais chance de recusa\n\n🎯 Recomendação: Segmentar abordagem por perfil demográfico e histórico médico. Para previdência, priorizar portabilidades abaixo de R$ 100k e focar em clientes Itaú.";
          break;
        case "alertas":
          setAlertText("🚨 ALERTAS AUTOMÁTICOS:\n\n• Vida Conforto — Alto risco de pendência no Nordeste (72%)\n• Perda de Renda — Declínio elevado no Centro-Oeste (45%)\n• Vida Mulher — Oportunidade de aumento de vendas no Sul (+30%)");
          result = "Alertas gerados e exibidos na caixa de alertas acima.";
          break;
        case "atualizacao":
          result = "🔄 Aprendizado Contínuo:\n\nA IA identificou mudanças recentes:\n• Redução de 15% nas pendências de Vida Mulher no Sudeste\n• Aumento de aprovações em valores entre R$ 2.000-3.000\n• Nova tendência: Faixa 30-40 anos com melhor conversão\n\nPrecisão atual: 87% (↑ 5% vs. mês anterior)";
          break;
      }
      
      setAiResult(result);
      setIsAnalyzing(false);
    }, 2000);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-[hsl(211,100%,15%)] via-[hsl(211,100%,25%)] to-[hsl(211,100%,35%)] relative overflow-hidden">
      {/* Animated background lines */}
      <div className="absolute inset-0 opacity-5 pointer-events-none">
        <div className="absolute top-1/4 left-0 w-full h-px bg-gradient-to-r from-transparent via-[hsl(211,100%,50%)] to-transparent animate-pulse" />
        <div className="absolute top-2/4 left-0 w-full h-px bg-gradient-to-r from-transparent via-[hsl(211,100%,60%)] to-transparent animate-pulse" style={{ animationDelay: '1s' }} />
        <div className="absolute top-3/4 left-0 w-full h-px bg-gradient-to-r from-transparent via-[hsl(211,100%,50%)] to-transparent animate-pulse" style={{ animationDelay: '2s' }} />
      </div>

      
      <main className="container mx-auto px-6 py-8 max-w-7xl relative z-10">
        <div className="mb-6 flex items-center gap-4">
          <MenuButton />
          <ProposalWorkflowSheet />
        </div>

        <h1 className="text-4xl font-bold mb-2 text-center text-white drop-shadow-[0_0_15px_rgba(255,255,255,0.3)]">
          🤖 Painel de IA Operacional
        </h1>
        <p className="text-center text-white/80 mb-8">Análise Inteligente de Dados e Insights</p>

        {/* NPS Section - Compacto */}
        <Card className="mb-8 bg-white/10 backdrop-blur-md border-white/20 shadow-[0_8px_32px_rgba(0,0,0,0.2)]">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between flex-wrap gap-4">
              <CardTitle className="text-white text-xl">📊 Pesquisa de Satisfação NPS</CardTitle>
              <div className="flex items-center gap-2 bg-[hsl(211,100%,50%)] px-3 py-1.5 rounded-lg">
                <span className="text-white text-xs font-medium">Score NPS:</span>
                <span className="text-white text-xl font-bold">{npsScore}</span>
              </div>
            </div>
          </CardHeader>
          <CardContent className="max-h-[500px] overflow-y-auto">
            {/* Filters */}
            <div className="flex gap-3 mb-4 flex-wrap">
              <div className="flex items-center gap-2">
                <Filter className="h-4 w-4 text-white" />
                <Select value={npsRatingFilter} onValueChange={setNpsRatingFilter}>
                  <SelectTrigger className="w-[150px] h-8 bg-white/10 border-white/20 text-white text-sm">
                    <SelectValue placeholder="Filtrar por nota" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todas as notas</SelectItem>
                    <SelectItem value="5">⭐ 5 - Ótimo</SelectItem>
                    <SelectItem value="4">⭐ 4</SelectItem>
                    <SelectItem value="3">⭐ 3</SelectItem>
                    <SelectItem value="2">⭐ 2</SelectItem>
                    <SelectItem value="1">⭐ 1 - Ruim</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              
              <Select value={npsDateFilter} onValueChange={setNpsDateFilter}>
                <SelectTrigger className="w-[150px] h-8 bg-white/10 border-white/20 text-white text-sm">
                  <SelectValue placeholder="Filtrar por data" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todas as datas</SelectItem>
                  <SelectItem value="7days">Últimos 7 dias</SelectItem>
                  <SelectItem value="30days">Últimos 30 dias</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
              {/* Rating Distribution Chart */}
              <div>
                <h3 className="text-white text-sm font-semibold mb-2">Distribuição de Notas</h3>
                <ResponsiveContainer width="100%" height={120}>
                  <BarChart data={ratingDistribution} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                    <XAxis type="number" stroke="white" tick={{ fontSize: 10 }} />
                    <YAxis dataKey="rating" type="category" stroke="white" tick={{ fontSize: 10 }} width={20} />
                    <Tooltip 
                      contentStyle={{ 
                        backgroundColor: "rgba(255,255,255,0.95)", 
                        border: "1px solid rgba(255,255,255,0.3)",
                        borderRadius: "8px",
                        color: "hsl(211,100%,25%)"
                      }}
                    />
                    <Bar dataKey="count" fill="hsl(211,80%,60%)" radius={[0, 8, 8, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* Word Cloud - Dinâmico */}
              <div>
                <h3 className="text-white text-sm font-semibold mb-2">☁️ Nuvem de Palavras {filteredNpsData.length < npsData.length && <span className="text-xs text-white/60">(filtrado)</span>}</h3>
                <div className="bg-white/5 rounded-lg p-3 h-[120px] flex flex-wrap items-center justify-center gap-2 overflow-hidden">
                  {wordCloudData.length > 0 ? (
                    wordCloudData.map((item, idx) => (
                      <span
                        key={idx}
                        className={`${item.size} cursor-pointer transition-all duration-200 hover:scale-125 hover:drop-shadow-[0_0_8px_rgba(255,255,255,0.5)] relative group`}
                        style={{ color: item.color }}
                      >
                        {item.word}
                        <span className="absolute -top-6 left-1/2 -translate-x-1/2 bg-black/90 text-white text-xs px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-10 pointer-events-none">
                          {item.count}x mencionado
                        </span>
                      </span>
                    ))
                  ) : (
                    <span className="text-white/50 text-sm">Nenhum dado disponível para o filtro selecionado</span>
                  )}
                </div>
              </div>
            </div>

            {/* Reviews - Compacto */}
            <div className="mb-4">
              <h3 className="text-white text-sm font-semibold mb-2">Avaliações dos Usuários</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-[200px] overflow-y-auto pr-2">
                {filteredNpsData.map((review) => (
                  <div 
                    key={review.id}
                    className="bg-white/5 border border-white/10 rounded-lg p-2 hover:bg-white/10 transition-colors"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-white text-xs font-semibold">
                        {review.anonymous ? "🔒 Anônimo" : review.name}
                      </span>
                      <div className="flex items-center gap-0.5">
                        {[...Array(5)].map((_, i) => (
                          <Star
                            key={i}
                            className={`h-3 w-3 ${
                              i < review.rating
                                ? "fill-yellow-400 text-yellow-400"
                                : "text-white/30"
                            }`}
                          />
                        ))}
                      </div>
                    </div>
                    <p className="text-white/80 text-xs line-clamp-2">{review.comment}</p>
                    <p className="text-white/50 text-[10px] mt-1">
                      {new Date(review.date).toLocaleDateString('pt-BR')}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            {/* Alerta de Termos Negativos */}
            {frequentNegativeTerms.length > 0 && (
              <div className="bg-red-500/20 border border-red-500/50 rounded-lg p-3 mb-4 flex items-start gap-3">
                <AlertTriangle className="h-5 w-5 text-red-400 flex-shrink-0 mt-0.5" />
                <div>
                  <h4 className="text-red-400 font-semibold text-sm mb-1">Alerta: Termos Negativos Detectados</h4>
                  <p className="text-white/80 text-xs">
                    Os seguintes termos de insatisfação foram identificados: {frequentNegativeTerms.map(t => `"${t.word}" (${t.count}x)`).join(', ')}.
                    Recomenda-se investigar as causas e tomar ações corretivas.
                  </p>
                </div>
              </div>
            )}

            {/* Key Insights - Fonte Aumentada */}
            <div className="bg-[hsl(211,100%,50%)]/10 border border-[hsl(211,100%,50%)]/30 rounded-lg p-4">
              <h3 className="text-white text-lg font-bold mb-2">💡 Principais Insights</h3>
              <ul className="text-white/80 text-base space-y-2">
                <li>• <strong className="text-green-400">Positivos:</strong> Funcionalidades intuitivas, visualização de dados, relatórios automatizados</li>
                <li>• <strong className="text-yellow-400">Melhorias:</strong> Extrato do cliente, notificações sobre sinistros, filtros avançados</li>
                <li>• <strong className="text-blue-400">Sugestões Externas:</strong> Notificações push, integração WhatsApp Business</li>
              </ul>
            </div>
          </CardContent>
        </Card>

        {/* Comparativo de Produtos */}
        <Card className="mb-8 bg-white/10 backdrop-blur-md border-white/20 shadow-[0_8px_32px_rgba(0,0,0,0.2)]">
          <CardHeader>
            <CardTitle className="text-white text-2xl">📊 Comparativo de Performance por Produto</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="border-b border-white/30">
                    <TableHead className="text-white">Produto</TableHead>
                    <TableHead className="text-white text-center">Emissões</TableHead>
                    <TableHead className="text-white text-center">Declínios</TableHead>
                    <TableHead className="text-white text-center">Pendentes</TableHead>
                    <TableHead className="text-white text-center">Taxa Conversão</TableHead>
                    <TableHead className="text-white text-center">Ticket Médio</TableHead>
                    <TableHead className="text-white text-center">Crescimento</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {productComparativeData.map((prod, idx) => (
                    <TableRow key={idx} className="border-b border-white/20 hover:bg-white/5 transition-colors">
                      <TableCell className="text-white font-medium">{prod.produto}</TableCell>
                      <TableCell className="text-center text-green-400 font-semibold">{prod.emissoes}</TableCell>
                      <TableCell className="text-center text-red-400">{prod.declínios}</TableCell>
                      <TableCell className="text-center text-yellow-400">{prod.pendentes}</TableCell>
                      <TableCell className="text-center text-white">{prod.conversao}%</TableCell>
                      <TableCell className="text-center text-white">R$ {prod.ticketMedio.toLocaleString('pt-BR')}</TableCell>
                      <TableCell className={`text-center font-semibold ${prod.crescimento >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {prod.crescimento >= 0 ? '+' : ''}{prod.crescimento}%
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>

        {/* Gráficos de Correlação e Tendências */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          {/* Tendência Mensal por Categoria */}
          <Card className="bg-white/10 backdrop-blur-md border-white/20 shadow-[0_8px_32px_rgba(0,0,0,0.2)]">
            <CardHeader>
              <CardTitle className="text-white">📈 Tendência Mensal por Categoria</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={monthlyTrendData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                  <XAxis dataKey="mes" stroke="white" />
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
                  <Line type="monotone" dataKey="vida" stroke="hsl(211,80%,60%)" strokeWidth={2} name="Vida" />
                  <Line type="monotone" dataKey="previdencia" stroke="hsl(150,80%,50%)" strokeWidth={2} name="Previdência" />
                  <Line type="monotone" dataKey="prestamista" stroke="hsl(40,80%,50%)" strokeWidth={2} name="Prestamista" />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Correlação Idade x Valor */}
          <Card className="bg-white/10 backdrop-blur-md border-white/20 shadow-[0_8px_32px_rgba(0,0,0,0.2)]">
            <CardHeader>
              <CardTitle className="text-white">🎯 Correlação: Faixa Etária x Ticket Médio</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={ageValueCorrelation}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                  <XAxis dataKey="faixa" stroke="white" />
                  <YAxis stroke="white" />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: "rgba(255,255,255,0.95)", 
                      border: "1px solid rgba(255,255,255,0.3)",
                      borderRadius: "8px",
                      color: "hsl(211,100%,25%)"
                    }}
                    formatter={(value, name) => [
                      name === 'ticketMedio' ? `R$ ${Number(value).toLocaleString('pt-BR')}` : value,
                      name === 'ticketMedio' ? 'Ticket Médio' : 'Quantidade'
                    ]}
                  />
                  <Legend wrapperStyle={{ color: "white" }} />
                  <Bar dataKey="ticketMedio" fill="hsl(211,80%,60%)" name="Ticket Médio" radius={[8, 8, 0, 0]} />
                  <Bar dataKey="quantidade" fill="hsl(150,60%,50%)" name="Quantidade" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Motivos de Declínio por Produto */}
          <Card className="bg-white/10 backdrop-blur-md border-white/20 shadow-[0_8px_32px_rgba(0,0,0,0.2)]">
            <CardHeader>
              <CardTitle className="text-white">⚠️ Motivos de Declínio por Produto</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={declineByProduct} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                  <XAxis type="number" stroke="white" />
                  <YAxis dataKey="produto" type="category" stroke="white" width={100} />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: "rgba(255,255,255,0.95)", 
                      border: "1px solid rgba(255,255,255,0.3)",
                      borderRadius: "8px",
                      color: "hsl(211,100%,25%)"
                    }}
                  />
                  <Legend wrapperStyle={{ color: "white" }} />
                  <Bar dataKey="documentacao" stackId="a" fill="hsl(40,80%,50%)" name="Documentação" />
                  <Bar dataKey="saude" stackId="a" fill="hsl(0,70%,50%)" name="Saúde" />
                  <Bar dataKey="renda" stackId="a" fill="hsl(270,60%,50%)" name="Renda" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Performance Regional */}
          <Card className="bg-white/10 backdrop-blur-md border-white/20 shadow-[0_8px_32px_rgba(0,0,0,0.2)]">
            <CardHeader>
              <CardTitle className="text-white">🌎 Performance Regional: Meta vs Realizado</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={regionPerformance}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                  <XAxis dataKey="regiao" stroke="white" />
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
                  <Bar dataKey="meta" fill="hsl(211,50%,40%)" name="Meta" radius={[8, 8, 0, 0]} />
                  <Bar dataKey="realizado" fill="hsl(150,70%,50%)" name="Realizado" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>

        {/* Alertas IA */}
        <Card className="mb-8 border-red-400 border-2 bg-white/10 backdrop-blur-md shadow-[0_8px_32px_rgba(0,0,0,0.2)] animate-glow-pulse">
          <CardHeader>
            <CardTitle className="text-red-400 flex items-center gap-2">
              <span className="animate-pulse">⚠️</span>
              Alertas Inteligentes
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="bg-red-400/10 p-4 rounded-lg whitespace-pre-line border border-red-400/30 text-white">
              {alertText}
            </div>
          </CardContent>
        </Card>

        {/* Botões de IA */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
          <Button 
            onClick={() => handleAIAnalysis("pendencias")} 
            disabled={isAnalyzing} 
            className="h-auto py-4 bg-gradient-primary hover:opacity-90 text-white shadow-lg hover:scale-105 transition-all"
          >
            {isAnalyzing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : "🔍"}
            <span className="ml-2">Análise Inteligente de Pendências</span>
          </Button>
          <Button 
            onClick={() => handleAIAnalysis("previsao")} 
            disabled={isAnalyzing} 
            className="h-auto py-4 bg-gradient-primary hover:opacity-90 text-white shadow-lg hover:scale-105 transition-all"
          >
            {isAnalyzing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : "🤖"}
            <span className="ml-2">Previsão de Risco por Produto</span>
          </Button>
          <Button 
            onClick={() => handleAIAnalysis("aprendizado")} 
            disabled={isAnalyzing} 
            className="h-auto py-4 bg-gradient-primary hover:opacity-90 text-white shadow-lg hover:scale-105 transition-all"
          >
            {isAnalyzing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : "🧠"}
            <span className="ml-2">Aprendizado com Casos Declinados</span>
          </Button>
          <Button 
            onClick={() => handleAIAnalysis("alertas")} 
            disabled={isAnalyzing} 
            className="h-auto py-4 bg-gradient-primary hover:opacity-90 text-white shadow-lg hover:scale-105 transition-all"
          >
            {isAnalyzing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : "🚨"}
            <span className="ml-2">Gerar Alertas Automáticos</span>
          </Button>
          <Button 
            onClick={() => handleAIAnalysis("atualizacao")} 
            disabled={isAnalyzing} 
            className="h-auto py-4 bg-gradient-primary hover:opacity-90 text-white shadow-lg hover:scale-105 transition-all"
          >
            {isAnalyzing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : "🔄"}
            <span className="ml-2">Aprendizado Contínuo</span>
          </Button>
        </div>

        {/* Resultados da IA */}
        {aiResult && (
          <Card className="border-white border-2 bg-white/10 backdrop-blur-md shadow-[0_8px_32px_rgba(0,0,0,0.2)] animate-slide-in-bottom">
            <CardHeader>
              <CardTitle className="text-white">📈 Resultados e Insights da IA</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="bg-white/10 p-6 rounded-lg whitespace-pre-line border border-white/30 text-white">
                {aiResult}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Footer */}
        <footer className="mt-12 text-center text-white/70 text-sm pb-8">
          <p>Powered by IA Operacional CAIXA</p>
        </footer>
      </main>

    </div>
  );
};

export default AICommercialPanel;
