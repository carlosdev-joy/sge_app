// O número do Card 1 (Pendentes de Assinatura): PRÊMIO em destaque, quantidade
// de contratos logo abaixo, em fonte menor (RITM0117336). Só este card tem dois
// valores; os outros sete seguem com o número único de sempre.
//
// "…" enquanto lê e "—" quando não conseguiu: zero seria uma resposta, e nenhuma
// das duas situações é uma resposta. Foto que não é de hoje ganha a data — é o que
// separa "a fila esvaziou" de "a carga das 07:30 não rodou".
import { dataBr } from "../lib/pio";
import { dataHoraBr, formatarMoeda, type ResumoCard1 } from "../lib/pioCard1";

interface Card1ValorProps {
  resumo: { data?: ResumoCard1; isPending: boolean };
  /** `colorido`: o card tem fundo de cor e texto branco (gaveta). `neutro`:
   *  fundo de painel, texto de tema (Workflow da home). */
  tom?: "neutro" | "colorido";
  /** Tamanho do número em destaque. */
  destaque?: string;
}

export default function Card1Valor({ resumo, tom = "neutro", destaque = "text-lg" }: Card1ValorProps) {
  const apagado = tom === "colorido" ? "text-white/80" : "text-dim";
  const alerta = tom === "colorido"
    ? "text-white font-semibold"
    : "text-amber-700 dark:text-amber-400 font-medium";

  if (resumo.isPending) {
    return <span className={apagado} title="consultando a foto do dia">…</span>;
  }
  const dados = resumo.data;
  if (!dados?.disponivel) {
    return (
      <span
        className={apagado}
        title="não foi possível ler a foto do PIO — o número não é zero, é desconhecido"
      >
        —
      </span>
    );
  }
  if (!dados.referencia) {
    return (
      <span className={apagado} title="nenhuma foto publicada ainda">
        —
      </span>
    );
  }

  const quantidade = dados.quantidade;
  const titulo = `Foto de ${dataBr(dados.referencia)}${
    dados.atualizacao ? `, publicada em ${dataHoraBr(dados.atualizacao)}` : ""}`;
  return (
    <span className="block" title={titulo}>
      <span className={`block ${destaque} font-bold leading-tight tabular-nums break-words`}>
        {formatarMoeda(dados.premio_total ?? 0)}
      </span>
      <span className={`block text-[11px] font-normal leading-tight tabular-nums ${apagado}`}>
        {quantidade.toLocaleString("pt-BR")} contrato{quantidade === 1 ? "" : "s"}
      </span>
      {dados.desatualizado && (
        <span className={`block text-[10px] leading-tight ${alerta}`}>
          foto de {dataBr(dados.referencia).slice(0, 5)}
        </span>
      )}
    </span>
  );
}
