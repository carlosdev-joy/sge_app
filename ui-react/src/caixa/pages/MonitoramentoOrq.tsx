// "Monitoramento Tático de Emissão" no visual NATIVO do Orquestra (tokens
// canvas/panel/edge/ink, claro+escuro) — tela OFICIAL de /caixa-seguro/acompanhamento
// desde a F2 da migração (docs/spec-caixa-ds-nativo.md); nasceu como piloto A/B
// (PRs #194–#197) e substituiu o SalesManagement navy/glass. Dados mock, iguais
// aos da tela original. Requer ProfileProvider (aplicado na rota, App.tsx).
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, PieChart, Pie, Cell,
} from "recharts";
import { Download, AlertTriangle, ArrowRight, HelpCircle, LayoutDashboard } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Tabs } from "../../components/ui/Tabs";
import { Select } from "../../components/ui/Input";
import { Modal } from "../../components/ui/Modal";
import { toast } from "../../components/ui/Toast";
import ChatAssistantOrq from "../components/ChatAssistantOrq";
import MenuButtonOrq from "../components/MenuButtonOrq";
import ProductTourOrq from "../components/ProductTourOrq";
import { Skeleton } from "../../components/ui/Skeleton";
import { useProfile } from "../contexts/ProfileContext";
import lariAvatar from "../assets/lari-avatar.png";
import diegoAvatar from "../assets/diego-avatar.png";
import leoAvatar from "../assets/leo-avatar.png";

type Produto = "vida" | "previdencia" | "prestamista";

// ── Tema dos gráficos (recharts segue os tokens do Orquestra) ──────────────
const AXIS = "#94a3b8"; // slate-400: legível no claro e no escuro
const EMISSOES = "#1A5FA8"; // azul institucional CVP (= primary do Orquestra)
const DECLINIOS = "#F26B00"; // laranja CAIXA — acento de negativo/atenção
const DONUT = ["#1A5FA8", "#f59e0b", "#ef4444"];
// Tooltip via CSS vars → acompanha claro/escuro automaticamente.
const tooltipStyle = {
  background: "rgb(var(--panel))",
  border: "1px solid rgb(var(--edge))",
  borderRadius: 8,
  color: "rgb(var(--ink))",
  fontSize: 12,
} as const;
const brl = (n: number) => `R$ ${n.toLocaleString("pt-BR")}`;

// ── Dados mock (mesmos números da tela original) ───────────────────────────
const statusData = [
  { status: "pending_signature", title: "Aguardando Assinatura", count: 217, value: "R$ 1.245.680,00", accent: "border-blue-500", text: "text-blue-500 dark:text-blue-400" },
  { status: "awaiting_payment", title: "Aguardando Pagamento", count: 150, value: "R$ 856.420,00", accent: "border-sky-500", text: "text-sky-500 dark:text-sky-400" },
  { status: "signed_proposal", title: "Proposta Assinada", count: 456, value: "R$ 2.654.320,00", accent: "border-emerald-500", text: "text-emerald-600 dark:text-emerald-400" },
  { status: "pending_documentation", title: "Pendência Documental", count: 43, value: "R$ 298.750,00", accent: "border-amber-500", text: "text-amber-600 dark:text-amber-400" },
  { status: "pending_dps", title: "Pendência de DPS", count: 28, value: "R$ 187.560,00", accent: "border-indigo-500", text: "text-indigo-500 dark:text-indigo-400" },
  { status: "refund_pending", title: "Propostas Declinadas", count: 89, value: "R$ 512.340,00", accent: "border-red-500", text: "text-red-600 dark:text-red-400" },
  { status: "valores_programados", title: "Valores Programados", count: 45, value: "R$ 287.900,00", accent: "border-cyan-500", text: "text-cyan-600 dark:text-cyan-400" },
  { status: "sensitization_monitoring", title: "Monitoramento de Sensibilização", count: 4, value: "4 movimentos", accent: "border-slate-400", text: "text-slate-600 dark:text-slate-300" },
];

const insuranceStatusData = [
  { name: "Ativos", value: 456 },
  { name: "Pendentes de Análise", value: 217 },
  { name: "Declinados", value: 204 },
];

const declineReasonsData = [
  { reason: "Documentação Incompleta", count: 89 },
  { reason: "Análise de Crédito", count: 54 },
  { reason: "Desistência Cliente", count: 31 },
  { reason: "Divergência Cadastral", count: 30 },
];

const generalResultData = [
  { month: "Jan", Emissões: 180, Declínios: 15 },
  { month: "Fev", Emissões: 240, Declínios: 18 },
  { month: "Mar", Emissões: 290, Declínios: 22 },
  { month: "Abr", Emissões: 320, Declínios: 19 },
  { month: "Mai", Emissões: 280, Declínios: 15 },
];

const productResult: Record<Produto, { product: string; Emissões: number; Declínios: number }[]> = {
  vida: [
    { product: "Vida Multipremiado", Emissões: 340, Declínios: 20 },
    { product: "Perda de Renda", Emissões: 280, Declínios: 16 },
    { product: "Vida Sênior", Emissões: 210, Declínios: 12 },
    { product: "Vida Empresarial", Emissões: 190, Declínios: 9 },
  ],
  previdencia: [
    { product: "Prev Crescer", Emissões: 380, Declínios: 15 },
    { product: "Prev Mulher", Emissões: 290, Declínios: 12 },
    { product: "Previdência 1215", Emissões: 310, Declínios: 18 },
    { product: "Prev Ativa", Emissões: 260, Declínios: 10 },
  ],
  prestamista: [
    { product: "Prestamista Habitacional", Emissões: 420, Declínios: 28 },
    { product: "Prestamista Veículos", Emissões: 350, Declínios: 22 },
    { product: "Prestamista Consignado", Emissões: 290, Declínios: 15 },
    { product: "Prestamista Pessoal", Emissões: 240, Declínios: 11 },
  ],
};

const PRODUTOS: { id: Produto; label: string }[] = [
  { id: "vida", label: "Seguro de Vida" },
  { id: "previdencia", label: "Previdência" },
  { id: "prestamista", label: "Prestamista" },
];

// Comparativo de performance entre produtos (mesmos números da POC)
const comparativo = [
  { tipo: "Seguro de Vida", emissoes: "1.399", aprovacao: "94.7%", ticket: "R$ 5.420", portabilidades: null as number | null },
  { tipo: "Previdência", emissoes: "1.045", aprovacao: "95.8%", ticket: "R$ 8.750", portabilidades: 196 },
  { tipo: "Prestamista", emissoes: "1.300", aprovacao: "93.3%", ticket: "R$ 3.850", portabilidades: null as number | null },
];
const comparativoBar = [
  { tipo: "Vida", Emissões: 1399, Declínios: 74 },
  { tipo: "Previdência", Emissões: 1045, Declínios: 46 },
  { tipo: "Prestamista", Emissões: 1300, Declínios: 92 },
];

// Propostas pendentes por motivo (por produto) — count + vencidas (>8 dias)
const pendingByReason: Record<Produto, { reason: string; count: number; overdue: number }[]> = {
  vida: [
    { reason: "Aguardando DPS", count: 28, overdue: 12 },
    { reason: "Aguardando Documentos", count: 43, overdue: 8 },
    { reason: "Em Análise", count: 35, overdue: 3 },
    { reason: "Validação Cadastral", count: 21, overdue: 5 },
  ],
  previdencia: [
    { reason: "Propostas fora da conformidade", count: 45, overdue: 18 },
    { reason: "Pendências de Curatela/Procuração e a Rogo", count: 38, overdue: 12 },
    { reason: "Aguardando Documentos", count: 32, overdue: 8 },
    { reason: "Em Análise", count: 27, overdue: 5 },
  ],
  prestamista: [
    { reason: "Aguardando DPS", count: 35, overdue: 15 },
    { reason: "Aguardando Documentos", count: 48, overdue: 10 },
    { reason: "Em Análise", count: 38, overdue: 6 },
    { reason: "Validação Cadastral", count: 24, overdue: 4 },
  ],
};

const sensitizationData = [
  { month: "Jan", count: 12 }, { month: "Fev", count: 18 }, { month: "Mar", count: 15 },
  { month: "Abr", count: 22 }, { month: "Mai", count: 19 },
];

// Portabilidade (só Previdência, como na POC)
const portabilidadeStatus = [
  { status: "Pendente", quantidade: 45, valor: 2350000 },
  { status: "Concluída", quantidade: 128, valor: 6890000 },
  { status: "Recusada", quantidade: 23, valor: 1180000 },
];
const bancosOrigem = [
  { name: "Brasilprev", value: 58 }, { name: "Itaú", value: 42 },
  { name: "Zurich Santander", value: 35 }, { name: "Outros", value: 61 },
];
const BANCOS = ["#1A5FA8", "#F26B00", "#10b981", "#94a3b8"];
const motivosRecusa = [
  { motivo: "Documentação Incompleta", count: 8 }, { motivo: "Prazo Vencido", count: 6 },
  { motivo: "Dados Divergentes", count: 5 }, { motivo: "Cancelamento Cliente", count: 4 },
];
const conformidade500k = [
  { proposta: "Proposta 8047413032437-2", valor: 650000, cliente: "MARCOS VINÍCIUS ALMEIDA", dias: 15 },
  { proposta: "Proposta 8047413032438-3", valor: 820000, cliente: "JULIANA COSTA PEREIRA", dias: 18 },
];

// Informativos por status — o "?" no card abre o balão do assistente (mesmos
// textos/assistentes da POC). Só os status com entrada aqui exibem o "?".
const statusHelpInfo: Record<string, { avatar: string; avatarName: string; message: string }> = {
  pending_signature: { avatar: lariAvatar, avatarName: "Lari", message: "Este status corresponde a propostas que estão pendentes de assinatura. Você pode utilizar o botão 'Enviar Link' para enviar ao cliente o link para assinatura da proposta via e-mail, WhatsApp ou SMS!" },
  awaiting_payment: { avatar: diegoAvatar, avatarName: "Diego", message: "Estas são propostas já assinadas que aguardam o pagamento. Você pode gerenciar as opções de pagamento e enviar lembretes ao cliente através do botão 'Gerenciar Pagamento'." },
  pending_documentation: { avatar: lariAvatar, avatarName: "Lari", message: "Propostas com pendências documentais precisam de documentos adicionais. Use o botão 'Upload de Documentos' para enviar os arquivos necessários e dar andamento à proposta." },
  pending_dps: { avatar: leoAvatar, avatarName: "Léo", message: "Pendência de DPS (Declaração Pessoal de Saúde) significa que o cliente precisa preencher informações de saúde. Clique em 'Enviar Link DPS' para enviar o formulário ao segurado." },
  refund_pending: { avatar: diegoAvatar, avatarName: "Diego", message: "Estas são propostas que foram declinadas pela seguradora. Você pode gerenciar o reembolso através do botão 'Gerenciar Reembolso' ou criar uma nova venda revisando as informações." },
};

export default function MonitoramentoOrq() {
  const navigate = useNavigate();
  const { profile } = useProfile();
  const [produto, setProduto] = useState<Produto>("vida");
  const [ano, setAno] = useState(String(new Date().getFullYear()));
  const [mes, setMes] = useState("all");
  const [carregandoTroca, setCarregandoTroca] = useState(false);
  const [mostrarTour, setMostrarTour] = useState(false);
  const [agencia, setAgencia] = useState("all");
  const [regiao, setRegiao] = useState("all");

  // Troca de produto com skeletons nos KPIs (mesmo comportamento da tela
  // original, que simulava 600ms de transição).
  const trocarProduto = (novo: Produto) => {
    if (novo === produto || carregandoTroca) return;
    setCarregandoTroca(true);
    setTimeout(() => {
      setProduto(novo);
      setCarregandoTroca(false);
    }, 600);
  };

  const exportar = () => {
    toast.success("Relatório Excel gerado com sucesso.");
  };

  const pending = pendingByReason[produto];
  const pendingMax = Math.max(...pending.map((p) => p.count));
  const [activeHelp, setActiveHelp] = useState<string | null>(null);
  const help = activeHelp ? statusHelpInfo[activeHelp] : null;

  return (
    <div className="min-h-full bg-canvas font-sans text-ink">
      <div className="p-6 max-w-[1600px] mx-auto flex flex-col gap-5">
        {/* Cabeçalho */}
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-lg font-semibold text-ink flex items-center gap-2">
              <LayoutDashboard size={18} className="text-[#1A5FA8]" />
              Monitoramento Tático de Emissão
            </h1>
            <p className="text-sm text-dim mt-0.5">Painel individual de desempenho e efetividade</p>
          </div>
          <div className="flex items-center gap-2">
            <MenuButtonOrq />
            <Button variant="secondary" size="md" onClick={() => setMostrarTour(true)}>
              🎯 Tour do Produto
            </Button>
            <Button variant="primary" size="md" onClick={exportar}>
              <Download size={14} /> Exportar Excel
            </Button>
          </div>
        </div>

        {/* Alerta de pendências urgentes (callout inline, no lugar do toast) */}
        <div className="flex items-start gap-3 rounded-lg border border-red-300 bg-red-50 px-4 py-3 dark:border-red-900 dark:bg-red-900/20">
          <AlertTriangle size={18} className="text-red-600 dark:text-red-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-semibold text-red-700 dark:text-red-300">Propostas com atenção urgente</p>
            <p className="text-xs text-red-600/90 dark:text-red-400/90">8 proposta(s) pendente(s) há mais de 10 dias.</p>
          </div>
        </div>

        {/* Toolbar: produto (Tabs) + período (Selects) */}
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-[280px]">
            <Tabs
              tabs={PRODUTOS}
              active={produto}
              onChange={(id) => trocarProduto(id as Produto)}
            />
          </div>
          <div className="flex items-end gap-3">
            <Select label="Mês" value={mes} onChange={(e) => setMes(e.target.value)} className="w-36">
              <option value="all">Todos</option>
              {["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"].map((m, i) => (
                <option key={m} value={String(i + 1)}>{m}</option>
              ))}
            </Select>
            <Select label="Ano" value={ano} onChange={(e) => setAno(e.target.value)} className="w-28">
              {["2024", "2025", "2026"].map((a) => <option key={a} value={a}>{a}</option>)}
            </Select>
          </div>
        </div>

        {/* Filtros de agência/região — só perfil operacional (paridade com a
            tela original; valores mock, como lá) */}
        {profile === "operational" && (
          <div className="flex flex-wrap items-end gap-3">
            <Select label="Agência" value={agencia} onChange={(e) => setAgencia(e.target.value)} className="w-48">
              <option value="all">Todas as agências</option>
              {["474", "475", "476"].map((a) => <option key={a} value={a}>Agência {a}</option>)}
            </Select>
            <Select label="Região" value={regiao} onChange={(e) => setRegiao(e.target.value)} className="w-48">
              <option value="all">Todas as regiões</option>
              <option value="norte">Norte</option>
              <option value="nordeste">Nordeste</option>
              <option value="centro-oeste">Centro-Oeste</option>
              <option value="sudeste">Sudeste</option>
              <option value="sul">Sul</option>
            </Select>
          </div>
        )}

        {/* KPI cards — planos, neutros, clicáveis (borda de acento por categoria);
            skeletons durante a troca de produto */}
        {carregandoTroca ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {statusData.map((s) => (
              <div key={s.status} className="bg-panel border border-edge rounded-lg p-4">
                <Skeleton className="h-4 w-2/3 mb-3" />
                <Skeleton className="h-9 w-1/2 mb-2" />
                <Skeleton className="h-3 w-1/3" />
              </div>
            ))}
          </div>
        ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {statusData.map((s) => (
            <div key={s.status} className="relative">
              <button
                onClick={() => navigate(`/caixa-seguro/acompanhamento/${s.status}`)}
                className={`w-full text-left bg-panel border border-edge ${s.accent} border-l-4 rounded-lg p-4 shadow-sm hover:shadow-md hover:border-blue-400 transition-all`}
              >
                <div className="text-[11px] font-semibold uppercase tracking-wide text-dim leading-tight min-h-[2.2em] pr-6">{s.title}</div>
                <div className={`text-3xl font-bold tabular-nums mt-1 ${s.text}`}>{s.count}</div>
                <div className="text-xs text-dim mt-0.5">{s.value}</div>
              </button>
              {statusHelpInfo[s.status] && (
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); setActiveHelp(s.status); }}
                  className="absolute top-2 right-2 text-dim hover:text-[#1A5FA8] transition-colors"
                  title="O que é este status?"
                  aria-label={`Ajuda sobre ${s.title}`}
                >
                  <HelpCircle size={16} />
                </button>
              )}
            </div>
          ))}
        </div>
        )}

        {/* Comparativo de performance entre produtos */}
        <Card title="Comparativo de Performance entre Produtos">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-5">
            {comparativo.map((p) => (
              <div key={p.tipo} className="bg-canvas border border-edge rounded-lg p-4">
                <h4 className="text-sm font-semibold text-ink mb-3">{p.tipo}</h4>
                <div className="flex flex-col gap-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-dim">Total Emissões</span>
                    <span className="font-bold text-ink tabular-nums">{p.emissoes}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-dim">Taxa Aprovação</span>
                    <span className="font-bold text-emerald-600 dark:text-emerald-400 tabular-nums">{p.aprovacao}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-dim">Ticket Médio</span>
                    <span className="font-bold text-ink tabular-nums">{p.ticket}</span>
                  </div>
                  {p.portabilidades != null && (
                    <div className="flex justify-between text-sm">
                      <span className="text-dim">Portabilidades</span>
                      <span className="font-bold text-blue-500 dark:text-blue-400 tabular-nums">{p.portabilidades}</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={comparativoBar}>
              <CartesianGrid strokeDasharray="3 3" stroke={AXIS} strokeOpacity={0.2} />
              <XAxis dataKey="tipo" tick={{ fill: AXIS, fontSize: 12 }} stroke={AXIS} />
              <YAxis tick={{ fill: AXIS, fontSize: 12 }} stroke={AXIS} />
              <Tooltip contentStyle={tooltipStyle} cursor={{ fill: AXIS, fillOpacity: 0.08 }} />
              <Legend wrapperStyle={{ color: AXIS, fontSize: 12 }} />
              <Bar dataKey="Emissões" fill={EMISSOES} radius={[4, 4, 0, 0]} />
              <Bar dataKey="Declínios" fill={DECLINIOS} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        {/* Gráficos */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <Card title="Emissões vs Declínios (mensal)">
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={generalResultData}>
                <CartesianGrid strokeDasharray="3 3" stroke={AXIS} strokeOpacity={0.2} />
                <XAxis dataKey="month" tick={{ fill: AXIS, fontSize: 12 }} stroke={AXIS} />
                <YAxis tick={{ fill: AXIS, fontSize: 12 }} stroke={AXIS} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: AXIS, fillOpacity: 0.08 }} />
                <Legend wrapperStyle={{ color: AXIS, fontSize: 12 }} />
                <Bar dataKey="Emissões" fill={EMISSOES} radius={[4, 4, 0, 0]} />
                <Bar dataKey="Declínios" fill={DECLINIOS} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>

          <Card title="Status de seguros">
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie
                  data={insuranceStatusData}
                  cx="50%" cy="50%"
                  innerRadius={60} outerRadius={100}
                  paddingAngle={2}
                  dataKey="value"
                  label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
                  labelLine={false}
                >
                  {insuranceStatusData.map((_, i) => <Cell key={i} fill={DONUT[i % DONUT.length]} />)}
                </Pie>
                <Tooltip contentStyle={tooltipStyle} />
              </PieChart>
            </ResponsiveContainer>
          </Card>

          <Card title="Motivos de declínio">
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={declineReasonsData} layout="vertical" margin={{ left: 40 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={AXIS} strokeOpacity={0.2} />
                <XAxis type="number" tick={{ fill: AXIS, fontSize: 12 }} stroke={AXIS} />
                <YAxis type="category" dataKey="reason" width={150} tick={{ fill: AXIS, fontSize: 11 }} stroke={AXIS} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: AXIS, fillOpacity: 0.08 }} />
                <Bar dataKey="count" name="Quantidade" fill={EMISSOES} radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>

          <Card title="Emissões e declínios por produto">
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={productResult[produto]}>
                <CartesianGrid strokeDasharray="3 3" stroke={AXIS} strokeOpacity={0.2} />
                <XAxis dataKey="product" tick={{ fill: AXIS, fontSize: 11 }} stroke={AXIS} />
                <YAxis tick={{ fill: AXIS, fontSize: 12 }} stroke={AXIS} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: AXIS, fillOpacity: 0.08 }} />
                <Legend wrapperStyle={{ color: AXIS, fontSize: 12 }} />
                <Bar dataKey="Emissões" fill={EMISSOES} radius={[4, 4, 0, 0]} />
                <Bar dataKey="Declínios" fill={DECLINIOS} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </div>

        {/* Propostas Pendentes por Motivo */}
        <Card
          title="Propostas Pendentes por Motivo"
          action={
            <Button variant="secondary" size="sm" onClick={() => toast.success("Relatório de Propostas Pendentes exportado.")}>
              <Download size={13} /> Exportar
            </Button>
          }
        >
          <div className="flex flex-col gap-3">
            {pending.map((item) => (
              <div key={item.reason} className="bg-canvas border border-edge rounded-lg p-4">
                <div className="flex items-center justify-between gap-3 mb-2 flex-wrap">
                  <span className="text-sm font-medium text-ink">{item.reason}</span>
                  <div className="flex items-center gap-2">
                    <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium border border-edge text-dim">{item.count} total</span>
                    {item.overdue > 0 && (
                      <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium bg-red-100 text-red-700 border border-red-300 dark:bg-red-900/40 dark:text-red-300 dark:border-red-800">
                        <AlertTriangle size={11} /> {item.overdue} &gt;8 dias
                      </span>
                    )}
                  </div>
                </div>
                <div className="w-full bg-edge/60 rounded-full h-2 overflow-hidden">
                  <div className="bg-[#1A5FA8] h-2 rounded-full transition-all" style={{ width: `${(item.count / pendingMax) * 100}%` }} />
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Propostas Pendentes de Sensibilização */}
        <Card title="Propostas Pendentes de Sensibilização">
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={sensitizationData}>
              <CartesianGrid strokeDasharray="3 3" stroke={AXIS} strokeOpacity={0.2} />
              <XAxis dataKey="month" tick={{ fill: AXIS, fontSize: 12 }} stroke={AXIS} />
              <YAxis tick={{ fill: AXIS, fontSize: 12 }} stroke={AXIS} />
              <Tooltip contentStyle={tooltipStyle} />
              <Line type="monotone" dataKey="count" name="Pendentes" stroke={EMISSOES} strokeWidth={2} dot={{ fill: EMISSOES, r: 4 }} />
            </LineChart>
          </ResponsiveContainer>
        </Card>

        {/* Portabilidade — só Previdência (como na POC) */}
        {produto === "previdencia" && (
          <>
            <Card title="Acompanhamento de Portabilidade">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div>
                  <h4 className="text-sm font-semibold text-ink mb-3">Solicitações por status</h4>
                  <ResponsiveContainer width="100%" height={260}>
                    <BarChart data={portabilidadeStatus}>
                      <CartesianGrid strokeDasharray="3 3" stroke={AXIS} strokeOpacity={0.2} />
                      <XAxis dataKey="status" tick={{ fill: AXIS, fontSize: 12 }} stroke={AXIS} />
                      <YAxis allowDecimals={false} tick={{ fill: AXIS, fontSize: 12 }} stroke={AXIS} />
                      <Tooltip contentStyle={tooltipStyle} cursor={{ fill: AXIS, fillOpacity: 0.08 }} />
                      <Bar dataKey="quantidade" name="Solicitações" fill={EMISSOES} radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-ink mb-3">Valor por status (R$)</h4>
                  <ResponsiveContainer width="100%" height={260}>
                    <BarChart data={portabilidadeStatus}>
                      <CartesianGrid strokeDasharray="3 3" stroke={AXIS} strokeOpacity={0.2} />
                      <XAxis dataKey="status" tick={{ fill: AXIS, fontSize: 12 }} stroke={AXIS} />
                      <YAxis tick={{ fill: AXIS, fontSize: 12 }} stroke={AXIS} tickFormatter={(v) => `R$ ${(Number(v) / 1e6).toFixed(1)}M`} />
                      <Tooltip contentStyle={tooltipStyle} cursor={{ fill: AXIS, fillOpacity: 0.08 }} formatter={(value) => `R$ ${(Number(value) / 1000).toLocaleString("pt-BR")} mil`} />
                      <Bar dataKey="valor" name="Valor" fill="#10b981" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-ink mb-3">Principais Bancos de Origem</h4>
                  <ResponsiveContainer width="100%" height={260}>
                    <PieChart>
                      <Pie
                        data={bancosOrigem} cx="50%" cy="50%" outerRadius={90}
                        dataKey="value" labelLine={false}
                        label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
                      >
                        {bancosOrigem.map((_, i) => <Cell key={i} fill={BANCOS[i % BANCOS.length]} />)}
                      </Pie>
                      <Tooltip contentStyle={tooltipStyle} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-ink mb-3">Principais Motivos de Recusa</h4>
                  <ResponsiveContainer width="100%" height={260}>
                    <BarChart data={motivosRecusa} layout="vertical" margin={{ left: 40 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke={AXIS} strokeOpacity={0.2} />
                      <XAxis type="number" tick={{ fill: AXIS, fontSize: 12 }} stroke={AXIS} />
                      <YAxis type="category" dataKey="motivo" width={140} tick={{ fill: AXIS, fontSize: 11 }} stroke={AXIS} />
                      <Tooltip contentStyle={tooltipStyle} cursor={{ fill: AXIS, fillOpacity: 0.08 }} />
                      <Bar dataKey="count" name="Quantidade" fill={DECLINIOS} radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </Card>

            <Card
              title="Detalhamento de Portabilidades"
              action={
                <Button variant="secondary" size="sm" onClick={() => navigate("/caixa-seguro/portabilidades")}>
                  Ver todas <ArrowRight size={13} />
                </Button>
              }
            >
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="bg-canvas border border-edge rounded-lg p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-dim">Total de Solicitações</span>
                    <span className="text-2xl font-bold text-ink tabular-nums">196</span>
                  </div>
                  <div className="text-xs text-dim mt-1">Todas as portabilidades</div>
                </div>
                <div className="rounded-lg p-4 border border-amber-300 bg-amber-50 dark:border-amber-900 dark:bg-amber-900/20">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-amber-700 dark:text-amber-300">Pendentes &gt; 8 dias</span>
                    <span className="text-2xl font-bold text-amber-700 dark:text-amber-300 tabular-nums">12</span>
                  </div>
                  <div className="text-xs text-amber-600/90 dark:text-amber-400/90 mt-1">Requer atenção urgente</div>
                </div>
              </div>
            </Card>

            <Card
              title="Pendências Fora da Conformidade > R$ 500k"
              action={
                <Button variant="secondary" size="sm" onClick={() => navigate("/caixa-seguro/acompanhamento/pending_documentation")}>
                  Ver detalhamento <ArrowRight size={13} />
                </Button>
              }
            >
              <div className="rounded-lg p-4 mb-4 border border-red-300 bg-red-50 dark:border-red-900 dark:bg-red-900/20">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-semibold text-red-700 dark:text-red-300">Total de Propostas</span>
                  <span className="text-2xl font-bold text-red-700 dark:text-red-300 tabular-nums">2</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-red-600/90 dark:text-red-400/90">Valor Total</span>
                  <span className="text-lg font-bold text-red-600 dark:text-red-300 tabular-nums">R$ 1.470.000,00</span>
                </div>
              </div>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={conformidade500k} layout="vertical" margin={{ left: 40 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={AXIS} strokeOpacity={0.2} />
                  <XAxis type="number" tick={{ fill: AXIS, fontSize: 12 }} stroke={AXIS} tickFormatter={(v) => `R$ ${(Number(v) / 1000).toFixed(0)}k`} />
                  <YAxis type="category" dataKey="proposta" width={180} tick={{ fill: AXIS, fontSize: 11 }} stroke={AXIS} />
                  <Tooltip contentStyle={tooltipStyle} cursor={{ fill: AXIS, fillOpacity: 0.08 }} formatter={(value) => brl(Number(value))} />
                  <Bar dataKey="valor" name="Valor" fill="#ef4444" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">
                {conformidade500k.map((c) => (
                  <div key={c.proposta} className="bg-canvas border border-edge rounded-lg p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-dim">{c.proposta}</span>
                      <span className="text-sm font-bold text-ink tabular-nums">{brl(c.valor)}</span>
                    </div>
                    <div className="text-xs text-dim mt-1">{c.cliente} — {c.dias} dias pendente</div>
                  </div>
                ))}
              </div>
            </Card>
          </>
        )}

        <p className="text-xs text-dim">Total emitido no período: <span className="font-semibold text-ink">{brl(8_540_120)}</span> · dados ilustrativos (mock).</p>

        {/* Informativo do status — balão do assistente no Modal nativo do Orquestra */}
        <Modal open={!!activeHelp} onClose={() => setActiveHelp(null)} title="Sobre este status" size="lg">
          {help && (
            <div className="flex items-start gap-5">
              <img
                src={help.avatar}
                alt={help.avatarName}
                className="w-24 h-24 rounded-full border-4 border-[#1A5FA8] shadow object-cover shrink-0 animate-bounce"
                style={{ animationDuration: "2s" }}
              />
              <div className="flex-1 min-w-0">
                <div className="relative bg-[#1A5FA8] text-white rounded-2xl p-5 shadow">
                  <div className="absolute -left-2 top-6 w-0 h-0 border-t-8 border-t-transparent border-b-8 border-b-transparent border-r-8 border-r-[#1A5FA8]" />
                  <p className="text-xs font-semibold opacity-90 mb-1">{help.avatarName}</p>
                  <p className="text-sm leading-relaxed">{help.message}</p>
                </div>
                <div className="mt-4 flex justify-end">
                  <Button variant="primary" size="sm" onClick={() => setActiveHelp(null)}>Entendi!</Button>
                </div>
              </div>
            </div>
          )}
        </Modal>
      </div>

      {/* Tour do produto (nativo) */}
      {mostrarTour && <ProductTourOrq productType={produto} onClose={() => setMostrarTour(false)} />}

      {/* FAB de chat do assistente conforme o produto (gate useAssistentesIA) */}
      {produto === "vida" && <ChatAssistantOrq assistente="diego" nome="Diego" avatar={diegoAvatar} pageContext="Seguro de Vida - Gestão Comercial" />}
      {produto === "previdencia" && <ChatAssistantOrq assistente="leo" nome="Léo" avatar={leoAvatar} pageContext="Previdência - Gestão Comercial" />}
      {produto === "prestamista" && <ChatAssistantOrq assistente="lari" nome="Lari" avatar={lariAvatar} pageContext="Prestamista - Gestão Comercial" />}
    </div>
  );
}
