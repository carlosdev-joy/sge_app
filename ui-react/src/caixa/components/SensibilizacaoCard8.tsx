// "Dados da Sensibilização" do Resumo do Seguro (Card 8): valor do prêmio, movimento encaminhado e
// data de envio do movimento (RITM0118664), mais a situação ATUAL da proposta. A foto guarda o
// ÚLTIMO movimento de cada identificação nos últimos 12 meses: estado do MOVIMENTO e estado da
// PROPOSTA são diferentes e aparecem separados. Sem dados do segurado (a foto não os traz).
import { dataBr } from "../lib/card1Foto";
import type { SensibilizacaoCard8 as Sensibilizacao } from "../lib/workflow";

function Campo({ rotulo, valor, apagado = false }: { rotulo: string; valor: string; apagado?: boolean }) {
  return (
    <div>
      <p className="text-sm text-dim">{rotulo}</p>
      <p className={apagado ? "text-sm text-dim italic" : "font-semibold text-ink break-words"}>{valor}</p>
    </div>
  );
}

const NAO_INFORMADO = "Não informado";
const LINHA: Record<string, string> = { VG: "Vida em Grupo", AP: "Acidentes Pessoais" };

export default function SensibilizacaoCard8({ proposal, s }: { proposal: { value?: string; product?: string }; s: Sensibilizacao }) {
  return (
    <div className="bg-canvas p-6 rounded-lg border border-edge space-y-4" data-testid="sensibilizacao-card8">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Campo rotulo="Valor do prêmio:" valor={proposal.value || NAO_INFORMADO} />
        <Campo rotulo="Movimento encaminhado:" valor={s.statusMovimento} />
        <Campo rotulo="Data de envio do movimento:" valor={s.dataEnvio ? dataBr(s.dataEnvio) : NAO_INFORMADO} />
        <Campo rotulo="Data do movimento:" valor={s.dataMovimento ? dataBr(s.dataMovimento) : NAO_INFORMADO} />
        <Campo rotulo="Situação atual da proposta:" valor={s.statusAtual} />
        <Campo rotulo="Motivo:" valor={s.motivo ?? NAO_INFORMADO} />
        <Campo rotulo="Identificação:" valor={s.identificacao || NAO_INFORMADO} />
        <Campo rotulo="Linha de negócio:" valor={LINHA[s.linha] ?? NAO_INFORMADO} />
        <Campo rotulo="Produto:" valor={proposal.product || NAO_INFORMADO} />
      </div>
      <p className="text-xs text-dim italic">
        {s.podeSensibilizar
          ? "A situação da proposta difere do último movimento encaminhado."
          : "O último movimento encaminhado já corresponde à situação da proposta."}
        {" "}A foto traz só o último movimento da identificação e não traz os dados do segurado.
      </p>
    </div>
  );
}
