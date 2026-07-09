// PILOTO A/B — "Monitoramento Tático de Emissão" reconstruído no visual NATIVO
// do Orquestra (tokens canvas/panel/edge/ink, claro+escuro, componentes de
// components/ui/*) em vez do navy/glass da POC. Rota /caixa-seguro/acompanhamento-orq,
// lado a lado com a original (/caixa-seguro/acompanhamento) para comparação.
// Dados mock, iguais aos da tela original. Assistentes IA ficam fora do piloto
// (ortogonais à comparação de visual).
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, PieChart, Pie, Cell,
} from "recharts";
import { Download, AlertTriangle, ArrowLeft, LayoutDashboard } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Tabs } from "../../components/ui/Tabs";
import { Select } from "../../components/ui/Input";
import { toast } from "../../components/ui/Toast";

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

export default function MonitoramentoOrq() {
  const navigate = useNavigate();
  const [produto, setProduto] = useState<Produto>("vida");
  const [ano, setAno] = useState(String(new Date().getFullYear()));
  const [mes, setMes] = useState("all");

  const exportar = () => {
    toast.success("Relatório Excel gerado com sucesso.");
  };

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
            <Link
              to="/caixa-seguro/acompanhamento"
              className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium text-dim border border-edge hover:text-ink hover:bg-edge/40 transition-colors"
            >
              <ArrowLeft size={13} /> Ver versão atual (navy)
            </Link>
            <Button variant="primary" size="md" onClick={exportar}>
              <Download size={14} /> Exportar Excel
            </Button>
          </div>
        </div>

        {/* Faixa do piloto */}
        <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-2 text-xs text-blue-800 dark:border-blue-900 dark:bg-blue-900/20 dark:text-blue-300">
          Piloto A/B — visual nativo do Orquestra (tokens canvas/panel/ink, claro + escuro). Compare com <span className="font-semibold">/acompanhamento</span> (navy/glass da POC).
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
              onChange={(id) => setProduto(id as Produto)}
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

        {/* KPI cards — planos, neutros, clicáveis (borda de acento por categoria) */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {statusData.map((s) => (
            <button
              key={s.status}
              onClick={() => navigate(`/caixa-seguro/acompanhamento/${s.status}`)}
              className={`text-left bg-panel border border-edge ${s.accent} border-l-4 rounded-lg p-4 shadow-sm hover:shadow-md hover:border-blue-400 transition-all`}
            >
              <div className="text-[11px] font-semibold uppercase tracking-wide text-dim leading-tight min-h-[2.2em]">{s.title}</div>
              <div className={`text-3xl font-bold tabular-nums mt-1 ${s.text}`}>{s.count}</div>
              <div className="text-xs text-dim mt-0.5">{s.value}</div>
            </button>
          ))}
        </div>

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

        <p className="text-xs text-dim">Total emitido no período: <span className="font-semibold text-ink">{brl(8_540_120)}</span> · dados ilustrativos (mock).</p>
      </div>
    </div>
  );
}
