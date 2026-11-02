// Os 3 sub-cards do Card 7 (Devolução de Prêmio): Devolução Realizada, em Andamento e
// Pendente (RITM0118567). Clicar no card principal NÃO lista nada: a lista de contratos só
// aparece depois do clique em UM destes. Os três SOMAM o card principal (a classificação é
// uma regra única no backend). Clicar de novo no escolhido o desmarca e a lista some.
import { dataBr } from "../lib/pio";
import { ROTULO_SUBCARD_DEVOLUCAO, formatarMoeda, type ResumoCard1 } from "../lib/card1Foto";
import type { SituacaoDevolucao } from "../lib/workflow";

const SITUACOES: SituacaoDevolucao[] = ["realizada", "andamento", "pendente"];

// Fundo sólido + texto branco (mesma linguagem de `STATUS_COR`); o tom diz o que o número é.
const COR: Record<SituacaoDevolucao, string> = {
  realizada: "bg-emerald-600", andamento: "bg-amber-600", pendente: "bg-red-700",
};

interface Props {
  resumo: { data?: ResumoCard1; isPending: boolean };
  selecionada: SituacaoDevolucao | null;
  onSelecionar: (situacao: SituacaoDevolucao | null) => void;
}

export default function DevolucaoSubcards({ resumo, selecionada, onSelecionar }: Props) {
  const dados = resumo.data;
  if (resumo.isPending) return <p className="text-xs text-dim">Consultando a foto do PIO…</p>;
  if (!dados?.disponivel) {
    return (
      <p className="text-xs text-red-600 dark:text-red-400">
        Não foi possível ler a foto do PIO. Os valores não são zero — são desconhecidos.
      </p>
    );
  }
  if (!dados.referencia || !dados.por_situacao) {
    return <p className="text-xs text-dim">Ainda não há foto publicada para Devolução de Prêmio.</p>;
  }

  return (
    <div className="space-y-2" data-testid="subcards-devolucao">
      <p className="text-xs text-dim">
        Escolha uma situação para ver os contratos · foto de {dataBr(dados.referencia)}
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        {SITUACOES.map((s) => {
          const bloco = dados.por_situacao![s];
          const ativo = selecionada === s;
          // Valor desconhecido (nenhum contrato com valor) não é R$ 0,00.
          const valor = bloco.valor === null && bloco.quantidade > 0 ? "—" : formatarMoeda(bloco.valor ?? 0);
          return (
            <button
              key={s}
              type="button"
              onClick={() => onSelecionar(ativo ? null : s)}
              aria-pressed={ativo}
              data-testid={`subcard-${s}`}
              className={`${COR[s]} rounded-lg p-3 text-white text-center cursor-pointer transition-all hover:-translate-y-0.5 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-blue-500 ${
                ativo ? "ring-2 ring-offset-2 ring-blue-500 ring-offset-panel" : "opacity-95"
              }`}
            >
              <div className="text-[11px] font-semibold uppercase tracking-wide text-white/90 leading-tight">
                {ROTULO_SUBCARD_DEVOLUCAO[s]}
              </div>
              <div className="mt-1 text-lg font-bold leading-tight tabular-nums break-words">{valor}</div>
              <div className="text-[11px] leading-tight tabular-nums text-white/80">
                {bloco.quantidade.toLocaleString("pt-BR")} contrato{bloco.quantidade === 1 ? "" : "s"}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
