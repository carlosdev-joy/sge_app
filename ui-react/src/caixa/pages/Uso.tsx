// "Uso do módulo" — monitoramento de usabilidade de /caixa-seguro/* (spec
// docs/spec-uso-busca-vendas.md). Visual NATIVO do Orquestra (tokens
// canvas/panel/edge/ink, claro+escuro): nenhum componente nem cor novos. Acesso
// = abertura de uma tela do módulo; quem vê esta tela é quem recebeu o recurso
// `caixa_seguro_uso` no Admin.
import { useState } from "react";
import {
  Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Activity, BarChart3, ChevronLeft, ChevronRight, Gauge, MousePointerClick, Users } from "lucide-react";
import { Banner } from "../../components/ui/Banner";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Hint } from "../../components/ui/Hint";
import { KpiCard } from "../../components/ui/KpiCard";
import { Skeleton } from "../../components/ui/Skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../../components/ui/Table";
import { Tabs } from "../../components/ui/Tabs";
import MenuButton from "../components/MenuButton";
import { JANELA_ONLINE_MIN, useUsoResumo, type UsoResumo } from "../lib/uso";
import {
  dataBrDeIso, dataHoraBr, deslocarReferencia, ehPeriodoAtual, hojeIso, media, NOME_GRANULARIDADE,
  numero, rotuloPeriodo, type Periodo,
} from "../lib/usoDatas";

const ABAS: { id: Periodo; label: string }[] = [
  { id: "dia", label: "Dia" },
  { id: "mes", label: "Mês" },
  { id: "ano", label: "Ano" },
];

// Mesma convenção dos gráficos de Monitoramento: eixo em slate-400 (legível nos
// dois temas) e tooltip por CSS vars, que acompanham claro/escuro sozinhas.
const EIXO = "#94a3b8";
const ACESSOS = "#1A5FA8"; // azul institucional (= primary do Orquestra)
const TOOLTIP = {
  background: "rgb(var(--panel))",
  border: "1px solid rgb(var(--edge))",
  borderRadius: 8,
  color: "rgb(var(--ink))",
  fontSize: 12,
};

const AJUDA_ACESSO =
  "Acesso é a abertura de uma tela do módulo Busca & Vendas. O mesmo usuário na mesma tela " +
  "conta uma vez a cada 30 minutos. Não mede cliques dentro da tela.\n" +
  "Online agora: usuários com a tela aberta nos últimos " + JANELA_ONLINE_MIN + " minutos.";

export default function Uso() {
  const [periodo, setPeriodo] = useState<Periodo>("dia");
  const [referencia, setReferencia] = useState<string>(hojeIso());
  const { data, isPending, isError, refetch } = useUsoResumo(periodo, referencia);

  const noPeriodoAtual = ehPeriodoAtual(periodo, referencia);
  const mudarPeriodo = (p: Periodo) => { setPeriodo(p); setReferencia(hojeIso()); };
  const andar = (passo: -1 | 1) => setReferencia(deslocarReferencia(periodo, referencia, passo));

  return (
    <div className="min-h-full bg-canvas font-sans text-ink">
      <div className="p-6 max-w-[1200px] mx-auto flex flex-col gap-5">
        {/* Cabeçalho — mesmo desenho das outras telas do módulo */}
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-lg font-semibold text-ink flex items-center gap-2">
              <BarChart3 size={18} className="text-[#1A5FA8]" />
              Uso do módulo
              <Hint texto={AJUDA_ACESSO} />
            </h1>
            <p className="text-sm text-dim mt-0.5">Quem acessa o Busca & Vendas e o que abre</p>
          </div>
          <MenuButton />
        </div>

        {/* Período */}
        <div className="flex items-end justify-between flex-wrap gap-3">
          <div className="min-w-[220px]">
            <Tabs tabs={ABAS} active={periodo} onChange={(id) => mudarPeriodo(id as Periodo)} />
          </div>
          <div className="flex items-center gap-2" role="group" aria-label="Navegar entre períodos">
            <Button variant="secondary" size="sm" onClick={() => andar(-1)} aria-label="Período anterior">
              <ChevronLeft size={14} />
            </Button>
            <span className="min-w-[150px] text-center text-sm font-medium text-ink" aria-live="polite">
              {rotuloPeriodo(periodo, referencia)}
            </span>
            <Button variant="secondary" size="sm" onClick={() => andar(1)} disabled={noPeriodoAtual}
                    aria-label="Próximo período">
              <ChevronRight size={14} />
            </Button>
          </div>
        </div>

        {isError && (
          <div className="rounded-lg overflow-hidden border border-edge">
            <Banner tom="erro" acao={<Button variant="secondary" size="sm" onClick={() => refetch()}>Tentar novamente</Button>}>
              Não foi possível carregar o uso do módulo.
            </Banner>
          </div>
        )}

        {isPending && !isError ? <Carregando /> : data && <Conteudo dados={data} />}
      </div>
    </div>
  );
}

function Carregando() {
  return (
    <div className="flex flex-col gap-5" aria-busy="true" aria-label="Carregando">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[92px] rounded-xl" />)}
      </div>
      <Skeleton className="h-[280px] rounded-lg" />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Skeleton className="h-[260px] rounded-lg" />
        <Skeleton className="h-[260px] rounded-lg" />
      </div>
    </div>
  );
}

function Conteudo({ dados }: { dados: UsoResumo }) {
  const vazio = dados.kpis.acessos === 0;
  const maxTela = Math.max(1, ...dados.por_tela.map((t) => t.acessos));
  const nomes = dados.usuarios_online.slice(0, 3).join(", ");
  const resto = dados.usuarios_online.length - 3;

  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard label="Online agora" value={numero(dados.online_agora)} color="green" icon={<Activity size={16} />}
                 sub={dados.online_agora > 0 && nomes ? `${nomes}${resto > 0 ? ` +${resto}` : ""}` : `últimos ${JANELA_ONLINE_MIN} min`} />
        <KpiCard label="Usuários no período" value={numero(dados.kpis.usuarios)} color="blue" icon={<Users size={16} />} />
        <KpiCard label="Acessos no período" value={numero(dados.kpis.acessos)} color="blue" icon={<MousePointerClick size={16} />} />
        <KpiCard label="Acessos por usuário" value={media(dados.kpis.acessos_por_usuario)} color="slate" icon={<Gauge size={16} />} />
      </div>

      {vazio ? (
        <Card>
          <p className="text-sm text-ink">Nenhum acesso registrado neste período.</p>
          <p className="text-xs text-dim mt-1">
            {dados.primeiro_registro
              ? `O registro de uso começou em ${dataBrDeIso(dados.primeiro_registro)}; períodos anteriores não têm dados.`
              : "Ainda não há acessos registrados no módulo."}
          </p>
        </Card>
      ) : (
        <>
          <Card title={`Acessos e usuários ${NOME_GRANULARIDADE[dados.periodo.granularidade]}`}>
            <div className="h-[260px]" role="img"
                 aria-label={`Gráfico de acessos e usuários ${NOME_GRANULARIDADE[dados.periodo.granularidade]}. Os números por tela e por usuário estão nas tabelas abaixo.`}>
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={dados.serie} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={EIXO} strokeOpacity={0.25} />
                  <XAxis dataKey="rotulo" tick={{ fill: EIXO, fontSize: 11 }} stroke={EIXO} interval="preserveStartEnd" />
                  <YAxis allowDecimals={false} tick={{ fill: EIXO, fontSize: 11 }} stroke={EIXO} />
                  <Tooltip contentStyle={TOOLTIP} cursor={{ fill: "rgba(148,163,184,0.12)" }} />
                  <Legend wrapperStyle={{ fontSize: 12 }}
                          formatter={(nome: string) => <span style={{ color: "rgb(var(--ink))" }}>{nome}</span>} />
                  <Bar dataKey="acessos" name="Acessos" fill={ACESSOS} radius={[3, 3, 0, 0]} />
                  <Line dataKey="usuarios" name="Usuários" type="monotone" stroke="rgb(var(--ink))"
                        strokeWidth={2} strokeDasharray="5 3" dot={{ r: 2.5 }} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-5 items-start">
            <Card title="Acessos por tela">
              <Table dense>
                <TableHeader>
                  <TableRow>
                    <TableHead>Tela</TableHead>
                    <TableHead className="text-right">Acessos</TableHead>
                    <TableHead className="text-right">Usuários</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {dados.por_tela.map((t) => (
                    <TableRow key={t.rota}>
                      <TableCell>
                        <div className="text-ink">{t.tela}</div>
                        <div className="mt-1 h-1.5 rounded-full bg-edge/50" aria-hidden="true">
                          <div className="h-1.5 rounded-full bg-[#1A5FA8]" style={{ width: `${(t.acessos / maxTela) * 100}%` }} />
                        </div>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{numero(t.acessos)}</TableCell>
                      <TableCell className="text-right tabular-nums">{numero(t.usuarios)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Card>

            <Card title="Ranking de usuários">
              <Table dense>
                <TableHeader>
                  <TableRow>
                    <TableHead>Usuário</TableHead>
                    <TableHead className="text-right">Acessos</TableHead>
                    <TableHead className="text-right">Dias ativos</TableHead>
                    <TableHead>Último acesso</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {dados.ranking.map((r) => (
                    <TableRow key={r.matricula}>
                      <TableCell>
                        <div className="text-ink whitespace-nowrap">{r.nome}</div>
                        <div className="text-xs text-dim">{r.matricula} · {r.tela_top}</div>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{numero(r.acessos)}</TableCell>
                      <TableCell className="text-right tabular-nums">{numero(r.dias_ativos)}</TableCell>
                      <TableCell className="whitespace-nowrap">{dataHoraBr(r.ultimo_acesso)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Card>
          </div>
        </>
      )}
    </>
  );
}
