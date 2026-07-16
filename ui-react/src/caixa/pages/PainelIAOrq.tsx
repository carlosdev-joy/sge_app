// "Painel de IA Operacional" no visual NATIVO do Orquestra — tela oficial de
// /caixa-seguro/ia-operacional desde a F5 da migração
// (docs/spec-caixa-ds-nativo.md); substitui o AICommercialPanel navy/glass.
// Dados mock e análises simuladas iguais aos da tela original; gráficos no
// padrão recharts do piloto (eixos slate-400, tooltip via CSS vars --panel/
// --edge/--ink). O botão do ProposalWorkflowSheet do header antigo fica FORA
// (decisão de escopo da F3 — o workflow inteiro volta nas F6–F8). O toast de
// termos negativos foi absorvido pelo callout inline que a tela já tinha
// (padrão da F2). Requer ProfileProvider (aplicado na rota, App.tsx).
import { useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Legend, Tooltip, LineChart, Line,
} from "recharts";
import { Bot, Star, Filter, AlertTriangle } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Select } from "../../components/ui/Input";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "../../components/ui/Table";
import MenuButtonOrq from "../components/MenuButtonOrq";
import ProposalWorkflowSheetOrq from "../components/ProposalWorkflowSheetOrq";

// ── Tema dos gráficos (mesmo padrão do MonitoramentoOrq) ────────────────────
const AXIS = "#94a3b8"; // slate-400: legível no claro e no escuro
const AZUL = "#1A5FA8"; // azul institucional CVP
const VERDE = "#10b981"; // emerald-500
const AMBAR = "#f59e0b"; // amber-500
const VERMELHO = "#ef4444"; // red-500
const ROXO = "#8b5cf6"; // violet-500
const AZUL_ESCURO = "#0F4C88"; // meta (tom mais fechado do azul CVP)
const tooltipStyle = {
  background: "rgb(var(--panel))",
  border: "1px solid rgb(var(--edge))",
  borderRadius: 8,
  color: "rgb(var(--ink))",
  fontSize: 12,
} as const;

// ── Dados mock (mesmos números da tela original) ────────────────────────────
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

const productComparativeData = [
  { produto: "Vida Multipremiado", emissoes: 450, declínios: 25, pendentes: 38, conversao: 94.7, ticketMedio: 2850, crescimento: 12 },
  { produto: "Vida Mulher", emissoes: 320, declínios: 18, pendentes: 22, conversao: 94.6, ticketMedio: 2200, crescimento: 8 },
  { produto: "Vida Conforto", emissoes: 280, declínios: 32, pendentes: 45, conversao: 89.7, ticketMedio: 1500, crescimento: -3 },
  { produto: "Perda de Renda", emissoes: 349, declínios: 28, pendentes: 31, conversao: 92.5, ticketMedio: 2400, crescimento: 15 },
  { produto: "Prev Crescer", emissoes: 380, declínios: 15, pendentes: 18, conversao: 96.2, ticketMedio: 45000, crescimento: 22 },
  { produto: "Prev Mulher", emissoes: 290, declínios: 12, pendentes: 14, conversao: 96.0, ticketMedio: 35000, crescimento: 18 },
];

const monthlyTrendData = [
  { mes: "Jul", vida: 850, previdencia: 520, prestamista: 380 },
  { mes: "Ago", vida: 920, previdencia: 580, prestamista: 410 },
  { mes: "Set", vida: 980, previdencia: 650, prestamista: 450 },
  { mes: "Out", vida: 1050, previdencia: 720, prestamista: 490 },
  { mes: "Nov", vida: 1120, previdencia: 800, prestamista: 530 },
];

const ageValueCorrelation = [
  { faixa: "18-25", ticketMedio: 1200, quantidade: 180 },
  { faixa: "26-35", ticketMedio: 2100, quantidade: 420 },
  { faixa: "36-45", ticketMedio: 3200, quantidade: 580 },
  { faixa: "46-55", ticketMedio: 4500, quantidade: 390 },
  { faixa: "56-65", ticketMedio: 5800, quantidade: 210 },
];

const declineByProduct = [
  { produto: "Vida Conforto", documentacao: 15, saude: 12, renda: 5 },
  { produto: "Perda de Renda", documentacao: 8, saude: 5, renda: 15 },
  { produto: "Vida Mulher", documentacao: 10, saude: 5, renda: 3 },
  { produto: "Multipremiado", documentacao: 12, saude: 8, renda: 5 },
];

const regionPerformance = [
  { regiao: "Sul", meta: 1500, realizado: 1680, conversao: 95 },
  { regiao: "Sudeste", meta: 2500, realizado: 2350, conversao: 92 },
  { regiao: "Nordeste", meta: 1200, realizado: 1100, conversao: 88 },
  { regiao: "Centro-Oeste", meta: 800, realizado: 920, conversao: 94 },
  { regiao: "Norte", meta: 600, realizado: 480, conversao: 85 },
];

// Termos negativos para o alerta da nuvem de palavras (mesma lista da POC).
const negativeTerms = ["lento", "erro", "problema", "ruim", "difícil", "confuso", "travando", "bug", "demora", "falha", "péssimo", "horrível", "piorou", "complicado"];

// Análises simuladas dos botões de IA (mesmos textos da POC).
const AI_RESULTS: Record<string, string> = {
  pendencias: "📊 Análise de Pendências:\n\n1️⃣ Padrão identificado: Vida Conforto e Perda de Renda apresentam maior tempo de pendência (6 e 5 dias).\n2️⃣ Região Sul concentra 40% das pendências.\n3️⃣ Faixa etária 45-60 anos tem maior índice de atraso.\n4️⃣ Sugestão: Implementar follow-up automatizado após 3 dias de pendência.\n\n💡 Insights Previdência:\n• Portabilidades pendentes há mais de 8 dias: 12 solicitações\n• Principal banco cedente: Brasilprev (35% das solicitações)\n• Taxa de conclusão de portabilidade: 65%",
  previsao: "🤖 Previsão de Risco:\n\n• Vida Conforto: 68% de risco de pendência (faixa etária 25-35)\n• Perda de Renda: 55% de risco (valores acima de R$ 2.500)\n• Vida Mulher: 32% de risco (região Sul)\n\n📈 Previdência:\n• Prev Crescer: 42% de risco de recusa em portabilidades\n• Prev Mulher: 28% de risco (documentação incompleta)\n• Prev Ativa: 35% de risco (valores incompatíveis)\n\nRecomendação: Priorizar contato proativo nas primeiras 24h e revisar documentação antes do envio.",
  aprendizado: "🧠 Insights de Machine Learning:\n\n✅ Produtos com maior taxa de conversão:\n• Vida Mulher na região Sul (89% de efetividade)\n• Multipremiado na região Sudeste (85%)\n\n⚠️ Produtos com alto índice de declínio:\n• Perda de Renda no Centro-Oeste (renda insuficiente)\n• Vida Conforto no Norte (histórico de saúde)\n\n💼 Insights Previdência:\n• Prev Crescer: melhor performance em região Sudeste (taxa de conversão 92%)\n• Portabilidades de Itaú têm tempo médio de processamento 30% menor\n• Prev Mulher: público-alvo 28-45 anos com maior taxa de adesão\n• Portabilidades acima de R$ 100k têm 15% mais chance de recusa\n\n🎯 Recomendação: Segmentar abordagem por perfil demográfico e histórico médico. Para previdência, priorizar portabilidades abaixo de R$ 100k e focar em clientes Itaú.",
  atualizacao: "🔄 Aprendizado Contínuo:\n\nA IA identificou mudanças recentes:\n• Redução de 15% nas pendências de Vida Mulher no Sudeste\n• Aumento de aprovações em valores entre R$ 2.000-3.000\n• Nova tendência: Faixa 30-40 anos com melhor conversão\n\nPrecisão atual: 87% (↑ 5% vs. mês anterior)",
};

const ALERTAS_TEXT = "🚨 ALERTAS AUTOMÁTICOS:\n\n• Vida Conforto — Alto risco de pendência no Nordeste (72%)\n• Perda de Renda — Declínio elevado no Centro-Oeste (45%)\n• Vida Mulher — Oportunidade de aumento de vendas no Sul (+30%)";

const AI_BUTTONS: { tipo: string; emoji: string; label: string }[] = [
  { tipo: "pendencias", emoji: "🔍", label: "Análise Inteligente de Pendências" },
  { tipo: "previsao", emoji: "🤖", label: "Previsão de Risco por Produto" },
  { tipo: "aprendizado", emoji: "🧠", label: "Aprendizado com Casos Declinados" },
  { tipo: "alertas", emoji: "🚨", label: "Gerar Alertas Automáticos" },
  { tipo: "atualizacao", emoji: "🔄", label: "Aprendizado Contínuo" },
];

export default function PainelIAOrq() {
  const [aiResult, setAiResult] = useState<string>("");
  const [alertText, setAlertText] = useState<string>("Aguardando análise da IA...");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [npsRatingFilter, setNpsRatingFilter] = useState<string>("all");
  const [npsDateFilter, setNpsDateFilter] = useState<string>("all");

  const getRatingDistribution = () => {
    const distribution = [
      { rating: 5, count: 0 },
      { rating: 4, count: 0 },
      { rating: 3, count: 0 },
      { rating: 2, count: 0 },
      { rating: 1, count: 0 },
    ];
    npsData.forEach((item) => {
      const idx = distribution.findIndex((d) => d.rating === item.rating);
      if (idx !== -1) distribution[idx].count++;
    });
    return distribution;
  };

  const getFilteredNpsData = () => {
    let filtered = npsData;
    if (npsRatingFilter !== "all") {
      filtered = filtered.filter((item) => item.rating === parseInt(npsRatingFilter));
    }
    if (npsDateFilter !== "all") {
      const today = new Date();
      const filterDate = new Date(today);
      if (npsDateFilter === "7days") filterDate.setDate(today.getDate() - 7);
      else if (npsDateFilter === "30days") filterDate.setDate(today.getDate() - 30);
      filtered = filtered.filter((item) => new Date(item.date) >= filterDate);
    }
    return filtered;
  };

  const calculateNPSScore = () => {
    const total = npsData.length;
    const promoters = npsData.filter((d) => d.rating >= 4).length;
    const detractors = npsData.filter((d) => d.rating <= 2).length;
    return Math.round(((promoters - detractors) / total) * 100);
  };

  const ratingDistribution = getRatingDistribution();
  const filteredNpsData = getFilteredNpsData();
  const npsScore = calculateNPSScore();

  // Frequência de palavras dos comentários (mesma lógica/stop words da POC).
  const getWordFrequency = () => {
    const stopWords = ["a", "o", "e", "de", "da", "do", "que", "em", "para", "com", "um", "uma", "os", "as", "no", "na", "é", "são", "muito", "mais", "mas", "já", "se", "como", "por", "está", "ao", "das", "dos", "às", "aos", "esse", "essa", "isso", "este", "esta", "isto", "seu", "sua", "seus", "suas", "meu", "minha", "me", "nos", "só", "ou", "também", "ter", "ser", "foi", "tem", "quando", "fica", "ficam", "algumas", "alguns", "sobre", "bem", "bom"];

    const wordCount: { [key: string]: number } = {};
    filteredNpsData.forEach((review) => {
      const words = review.comment
        .toLowerCase()
        .replace(/[.,!?;:()""'']/g, "")
        .split(/\s+/)
        .filter((word) => word.length > 3 && !stopWords.includes(word));
      words.forEach((word) => {
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
      const ratio = (count - minCount) / (maxCount - minCount || 1);
      let sizeClass: string;
      if (ratio >= 0.8) sizeClass = "text-3xl font-bold";
      else if (ratio >= 0.6) sizeClass = "text-2xl font-bold";
      else if (ratio >= 0.4) sizeClass = "text-xl font-semibold";
      else if (ratio >= 0.2) sizeClass = "text-lg font-medium";
      else sizeClass = "text-base";

      return {
        word,
        count,
        size: sizeClass,
        // Lightness via CSS var --nuvem-l: 40% no claro, 65% no escuro (o
        // <style> abaixo troca com html.dark) — a rotação de matiz é a da POC.
        color: isNegative
          ? "hsl(0, 75%, var(--nuvem-l, 45%))"
          : `hsl(${(index * 25) % 360}, ${60 + (index % 3) * 10}%, var(--nuvem-l, 45%))`,
        isNegative,
      };
    });
  };

  const wordCloudData = getWordFrequency();
  const frequentNegativeTerms = wordCloudData.filter((item) => item.isNegative && item.count >= 2);

  const handleAIAnalysis = (type: string) => {
    setIsAnalyzing(true);
    setTimeout(() => {
      if (type === "alertas") {
        setAlertText(ALERTAS_TEXT);
        setAiResult("Alertas gerados e exibidos na caixa de alertas acima.");
      } else {
        setAiResult(AI_RESULTS[type] ?? "");
      }
      setIsAnalyzing(false);
    }, 2000);
  };

  return (
    <div className="min-h-full bg-canvas font-sans text-ink">
      <div className="p-6 max-w-[1600px] mx-auto flex flex-col gap-5">
        {/* Cabeçalho */}
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-lg font-semibold text-ink flex items-center gap-2">
              <Bot size={18} className="text-[#1A5FA8]" />
              Painel de IA Operacional
            </h1>
            <p className="text-sm text-dim mt-0.5">Análise Inteligente de Dados e Insights</p>
          </div>
          <div className="flex items-center gap-2">
            <MenuButtonOrq />
            <ProposalWorkflowSheetOrq />
          </div>
        </div>

        {/* Pesquisa de Satisfação NPS */}
        <Card
          title="📊 Pesquisa de Satisfação NPS"
          action={
            <span className="inline-flex items-center gap-2 bg-[#1A5FA8] text-white px-3 py-1.5 rounded-lg">
              <span className="text-xs font-medium">Score NPS:</span>
              <span className="text-xl font-bold tabular-nums">{npsScore}</span>
            </span>
          }
        >
          {/* Filtros */}
          <div className="flex gap-3 mb-4 flex-wrap items-center">
            <Filter className="h-4 w-4 text-dim" />
            <Select value={npsRatingFilter} onChange={(e) => setNpsRatingFilter(e.target.value)} aria-label="Filtrar por nota" className="w-[160px]">
              <option value="all">Todas as notas</option>
              <option value="5">⭐ 5 - Ótimo</option>
              <option value="4">⭐ 4</option>
              <option value="3">⭐ 3</option>
              <option value="2">⭐ 2</option>
              <option value="1">⭐ 1 - Ruim</option>
            </Select>
            <Select value={npsDateFilter} onChange={(e) => setNpsDateFilter(e.target.value)} aria-label="Filtrar por data" className="w-[160px]">
              <option value="all">Todas as datas</option>
              <option value="7days">Últimos 7 dias</option>
              <option value="30days">Últimos 30 dias</option>
            </Select>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
            {/* Distribuição de notas */}
            <div>
              <h3 className="text-sm font-semibold text-ink mb-2">Distribuição de Notas</h3>
              <ResponsiveContainer width="100%" height={120}>
                <BarChart data={ratingDistribution} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke={AXIS} strokeOpacity={0.2} />
                  <XAxis type="number" stroke={AXIS} tick={{ fill: AXIS, fontSize: 10 }} />
                  <YAxis dataKey="rating" type="category" stroke={AXIS} tick={{ fill: AXIS, fontSize: 10 }} width={20} />
                  <Tooltip contentStyle={tooltipStyle} cursor={{ fill: AXIS, fillOpacity: 0.08 }} />
                  <Bar dataKey="count" name="Avaliações" fill={AZUL} radius={[0, 8, 8, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Nuvem de palavras */}
            <div>
              <h3 className="text-sm font-semibold text-ink mb-2">
                ☁️ Nuvem de Palavras {filteredNpsData.length < npsData.length && <span className="text-xs text-dim">(filtrado)</span>}
              </h3>
              <div className="nuvem-palavras bg-canvas border border-edge rounded-lg p-3 h-[120px] flex flex-wrap items-center justify-center gap-2 overflow-hidden">
                {wordCloudData.length > 0 ? (
                  wordCloudData.map((item, idx) => (
                    <span
                      key={idx}
                      className={`${item.size} cursor-pointer transition-all duration-200 hover:scale-125 relative group`}
                      style={{ color: item.color }}
                    >
                      {item.word}
                      <span className="absolute -top-6 left-1/2 -translate-x-1/2 bg-ink text-panel text-xs px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-10 pointer-events-none">
                        {item.count}x mencionado
                      </span>
                    </span>
                  ))
                ) : (
                  <span className="text-dim text-sm">Nenhum dado disponível para o filtro selecionado</span>
                )}
              </div>
            </div>
          </div>

          {/* Avaliações */}
          <div className="mb-4">
            <h3 className="text-sm font-semibold text-ink mb-2">Avaliações dos Usuários</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-[200px] overflow-y-auto pr-2">
              {filteredNpsData.map((review) => (
                <div key={review.id} className="bg-canvas border border-edge rounded-lg p-2 hover:border-blue-400 transition-colors">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-semibold text-ink">
                      {review.anonymous ? "🔒 Anônimo" : review.name}
                    </span>
                    <div className="flex items-center gap-0.5">
                      {[...Array(5)].map((_, i) => (
                        <Star
                          key={i}
                          className={`h-3 w-3 ${i < review.rating ? "fill-amber-400 text-amber-400" : "text-edge"}`}
                        />
                      ))}
                    </div>
                  </div>
                  <p className="text-xs text-dim line-clamp-2">{review.comment}</p>
                  <p className="text-[10px] text-dim mt-1">{new Date(review.date).toLocaleDateString("pt-BR")}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Alerta de termos negativos (callout inline — a POC tinha este box
              E um toast no mount; o toast foi absorvido aqui, padrão da F2) */}
          {frequentNegativeTerms.length > 0 && (
            <div className="flex items-start gap-3 rounded-lg border border-red-300 bg-red-50 px-4 py-3 mb-4 dark:border-red-900 dark:bg-red-900/20">
              <AlertTriangle className="h-5 w-5 text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
              <div>
                <h4 className="text-sm font-semibold text-red-700 dark:text-red-300 mb-1">Alerta: Termos Negativos Detectados</h4>
                <p className="text-xs text-red-600/90 dark:text-red-400/90">
                  Os seguintes termos de insatisfação foram identificados: {frequentNegativeTerms.map((t) => `"${t.word}" (${t.count}x)`).join(", ")}.
                  Recomenda-se investigar as causas e tomar ações corretivas.
                </p>
              </div>
            </div>
          )}

          {/* Principais insights */}
          <div className="rounded-lg border border-[#1A5FA8]/30 bg-[#1A5FA8]/5 p-4">
            <h3 className="text-base font-bold text-ink mb-2">💡 Principais Insights</h3>
            <ul className="text-sm text-dim space-y-2">
              <li>• <strong className="text-emerald-600 dark:text-emerald-400">Positivos:</strong> Funcionalidades intuitivas, visualização de dados, relatórios automatizados</li>
              <li>• <strong className="text-amber-600 dark:text-amber-400">Melhorias:</strong> Extrato do cliente, notificações sobre sinistros, filtros avançados</li>
              <li>• <strong className="text-blue-600 dark:text-blue-400">Sugestões Externas:</strong> Notificações push, integração WhatsApp Business</li>
            </ul>
          </div>
        </Card>

        {/* Comparativo de Produtos */}
        <Card title="📊 Comparativo de Performance por Produto">
          <div className="rounded-lg border border-edge overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Produto</TableHead>
                  <TableHead className="text-center">Emissões</TableHead>
                  <TableHead className="text-center">Declínios</TableHead>
                  <TableHead className="text-center">Pendentes</TableHead>
                  <TableHead className="text-center">Taxa Conversão</TableHead>
                  <TableHead className="text-center">Ticket Médio</TableHead>
                  <TableHead className="text-center">Crescimento</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {productComparativeData.map((prod, idx) => (
                  <TableRow key={idx}>
                    <TableCell className="font-medium">{prod.produto}</TableCell>
                    <TableCell className="text-center text-emerald-600 dark:text-emerald-400 font-semibold">{prod.emissoes}</TableCell>
                    <TableCell className="text-center text-red-600 dark:text-red-400">{prod.declínios}</TableCell>
                    <TableCell className="text-center text-amber-600 dark:text-amber-400">{prod.pendentes}</TableCell>
                    <TableCell className="text-center">{prod.conversao}%</TableCell>
                    <TableCell className="text-center">R$ {prod.ticketMedio.toLocaleString("pt-BR")}</TableCell>
                    <TableCell
                      className={`text-center font-semibold ${
                        prod.crescimento >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"
                      }`}
                    >
                      {prod.crescimento >= 0 ? "+" : ""}{prod.crescimento}%
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </Card>

        {/* Gráficos de correlação e tendências */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <Card title="📈 Tendência Mensal por Categoria">
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={monthlyTrendData}>
                <CartesianGrid strokeDasharray="3 3" stroke={AXIS} strokeOpacity={0.2} />
                <XAxis dataKey="mes" stroke={AXIS} tick={{ fill: AXIS, fontSize: 12 }} />
                <YAxis stroke={AXIS} tick={{ fill: AXIS, fontSize: 12 }} />
                <Tooltip contentStyle={tooltipStyle} />
                <Legend wrapperStyle={{ color: AXIS, fontSize: 12 }} />
                <Line type="monotone" dataKey="vida" stroke={AZUL} strokeWidth={2} name="Vida" dot={{ fill: AZUL, r: 3 }} />
                <Line type="monotone" dataKey="previdencia" stroke={VERDE} strokeWidth={2} name="Previdência" dot={{ fill: VERDE, r: 3 }} />
                <Line type="monotone" dataKey="prestamista" stroke={AMBAR} strokeWidth={2} name="Prestamista" dot={{ fill: AMBAR, r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </Card>

          <Card title="🎯 Correlação: Faixa Etária x Ticket Médio">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={ageValueCorrelation}>
                <CartesianGrid strokeDasharray="3 3" stroke={AXIS} strokeOpacity={0.2} />
                <XAxis dataKey="faixa" stroke={AXIS} tick={{ fill: AXIS, fontSize: 12 }} />
                <YAxis stroke={AXIS} tick={{ fill: AXIS, fontSize: 12 }} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  cursor={{ fill: AXIS, fillOpacity: 0.08 }}
                  formatter={(value, name) => [
                    name === "Ticket Médio" ? `R$ ${Number(value).toLocaleString("pt-BR")}` : value,
                    name,
                  ]}
                />
                <Legend wrapperStyle={{ color: AXIS, fontSize: 12 }} />
                <Bar dataKey="ticketMedio" fill={AZUL} name="Ticket Médio" radius={[8, 8, 0, 0]} />
                <Bar dataKey="quantidade" fill={VERDE} name="Quantidade" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>

          <Card title="⚠️ Motivos de Declínio por Produto">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={declineByProduct} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke={AXIS} strokeOpacity={0.2} />
                <XAxis type="number" stroke={AXIS} tick={{ fill: AXIS, fontSize: 12 }} />
                <YAxis dataKey="produto" type="category" stroke={AXIS} width={110} tick={{ fill: AXIS, fontSize: 11 }} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: AXIS, fillOpacity: 0.08 }} />
                <Legend wrapperStyle={{ color: AXIS, fontSize: 12 }} />
                <Bar dataKey="documentacao" stackId="a" fill={AMBAR} name="Documentação" />
                <Bar dataKey="saude" stackId="a" fill={VERMELHO} name="Saúde" />
                <Bar dataKey="renda" stackId="a" fill={ROXO} name="Renda" />
              </BarChart>
            </ResponsiveContainer>
          </Card>

          <Card title="🌎 Performance Regional: Meta vs Realizado">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={regionPerformance}>
                <CartesianGrid strokeDasharray="3 3" stroke={AXIS} strokeOpacity={0.2} />
                <XAxis dataKey="regiao" stroke={AXIS} tick={{ fill: AXIS, fontSize: 12 }} />
                <YAxis stroke={AXIS} tick={{ fill: AXIS, fontSize: 12 }} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: AXIS, fillOpacity: 0.08 }} />
                <Legend wrapperStyle={{ color: AXIS, fontSize: 12 }} />
                <Bar dataKey="meta" fill={AZUL_ESCURO} name="Meta" radius={[8, 8, 0, 0]} />
                <Bar dataKey="realizado" fill={VERDE} name="Realizado" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </div>

        {/* Alertas inteligentes */}
        <Card title="⚠️ Alertas Inteligentes">
          <div className="rounded-lg border border-red-300 bg-red-50 p-4 whitespace-pre-line text-sm text-red-700 dark:border-red-900 dark:bg-red-900/20 dark:text-red-300">
            {alertText}
          </div>
        </Card>

        {/* Botões de análise IA */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {AI_BUTTONS.map((btn) => (
            <Button
              key={btn.tipo}
              variant="primary"
              onClick={() => handleAIAnalysis(btn.tipo)}
              disabled={isAnalyzing}
              loading={isAnalyzing}
              className="h-auto py-4 justify-center"
            >
              {!isAnalyzing && <span>{btn.emoji}</span>}
              <span>{btn.label}</span>
            </Button>
          ))}
        </div>

        {/* Resultados da IA */}
        {aiResult && (
          <Card title="📈 Resultados e Insights da IA">
            <div className="rounded-lg border border-edge bg-canvas p-6 whitespace-pre-line text-sm text-ink">
              {aiResult}
            </div>
          </Card>
        )}
      </div>

      {/* Lightness da nuvem de palavras por tema (html.dark) */}
      <style>{`
        .nuvem-palavras { --nuvem-l: 40%; }
        html.dark .nuvem-palavras { --nuvem-l: 65%; }
      `}</style>
    </div>
  );
}
