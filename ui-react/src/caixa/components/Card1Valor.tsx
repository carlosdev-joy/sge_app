// O número do Card 1 (Pendentes de Assinatura): PRÊMIO em destaque, quantidade
// de contratos logo abaixo, em fonte menor (RITM0117336). Só este card tem dois
// valores; os outros sete seguem com o número único de sempre.
//
// "…" enquanto lê e "—" quando não conseguiu: zero seria uma resposta, e nenhuma
// das duas situações é uma resposta. A data da foto aparece só no tooltip (title):
// texto fixo no card, depois da meia-noite, parecia erro (decisão do Carlos, 28/10).
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

// Valor longo (ex.: "R$ 492.469.590,63") não cabe no card estreito do celular e, com
// `break-words`, quebrava no meio do número. Abaixo de `sm` o corpo encolhe conforme o
// tamanho do texto; de `sm` para cima vale o `destaque` pedido. Classes LITERAIS: o
// Tailwind só gera o que está escrito inteiro no fonte.
const A_PARTIR_DE_SM: Record<string, string> = { "text-lg": "sm:text-lg", "text-xl": "sm:text-xl" };

function tamanhoDoValor(texto: string, destaque: string): string {
  const grande = A_PARTIR_DE_SM[destaque];
  if (!grande) return destaque;
  if (texto.length >= 15) return `text-sm ${grande}`;
  if (texto.length >= 12) return `text-base ${grande}`;
  return destaque;
}

export default function Card1Valor({ resumo, tom = "neutro", destaque = "text-lg" }: Card1ValorProps) {
  const apagado = tom === "colorido" ? "text-white/80" : "text-dim";

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
  // Prêmio desconhecido (nenhum contrato com valor informado) não é R$ 0,00.
  const valorTexto = dados.premio_total === null && quantidade > 0 ? "—" : formatarMoeda(dados.premio_total ?? 0);
  const parcial = dados.premios_informados !== undefined && dados.premios_informados < quantidade;
  const titulo = `Foto de ${dataBr(dados.referencia)}${
    dados.atualizacao ? `, publicada em ${dataHoraBr(dados.atualizacao)}` : ""}${
    parcial ? `. Prêmio somado de ${dados.premios_informados} dos ${quantidade} contratos (os demais sem valor na origem)` : ""}`;
  return (
    <span className="block" title={titulo}>
      <span className={`block ${tamanhoDoValor(valorTexto, destaque)} font-bold leading-tight tabular-nums break-words`}>
        {valorTexto}
      </span>
      <span className={`block text-[11px] font-normal leading-tight tabular-nums ${apagado}`}>
        {quantidade.toLocaleString("pt-BR")} contrato{quantidade === 1 ? "" : "s"}
      </span>
    </span>
  );
}
