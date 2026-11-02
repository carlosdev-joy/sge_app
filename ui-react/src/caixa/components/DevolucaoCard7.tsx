// "Dados da Devolução" do Resumo do Seguro (Card 7): valor devolvido, banco, agência, conta,
// status e data do crédito (ou a prevista, em andamento) de UM contrato (RITM0118567). Os dados
// bancários só vêm de `/pio/card7/devolucao`, aberto aqui — nunca na lista. A foto NÃO traz
// e-mail, telefone, celular, nome do banco nem dígito da agência: a tela diz isso, não inventa.
import { dataBr, formatarMoeda } from "../lib/card1Foto";
import { useDevolucaoCard7 } from "../lib/pioCard7";
import type { DevolucaoCard7 as DevolucaoDoContrato } from "../lib/workflow";

function Campo({ rotulo, valor, apagado = false }: { rotulo: string; valor: string; apagado?: boolean }) {
  return (
    <div>
      <p className="text-sm text-dim">{rotulo}</p>
      <p className={apagado ? "text-sm text-dim italic" : "font-semibold text-ink"}>{valor}</p>
    </div>
  );
}

const NAO_INFORMADO = "Não informado";
const FORA_DA_FOTO = "Não disponível nesta foto";

export default function DevolucaoCard7({ devolucao, referencia, numero }: {
  devolucao: DevolucaoDoContrato; referencia: string | null; numero: string;
}) {
  const q = useDevolucaoCard7(devolucao.segmento, numero, referencia, true);
  const d = q.data?.devolucao ?? null;
  const rotuloData = devolucao.situacao === "andamento" ? "Data prevista para crédito:" : devolucao.situacao === "realizada" ? "Data do crédito:" : "Data do movimento:";

  return (
    <div className="bg-canvas p-6 rounded-lg border border-edge" data-testid="devolucao-card7">
      {q.isPending && <p className="text-sm text-dim">Consultando a devolução…</p>}
      {!q.isPending && !q.data?.disponivel && (
        <p className="text-sm text-red-600 dark:text-red-400">
          Não foi possível ler a devolução. Os dados não estão vazios — são desconhecidos.
        </p>
      )}
      {q.data?.disponivel && !q.data.encontrado && (
        <p className="text-sm text-dim">Este contrato não está na foto do dia.</p>
      )}
      {d && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Campo rotulo="Valor devolvido:" valor={d.valor === null ? NAO_INFORMADO : formatarMoeda(d.valor)} />
          <Campo rotulo="Status da devolução:" valor={d.status} />
          <Campo rotulo={rotuloData} valor={d.data_movimento ? dataBr(d.data_movimento) : NAO_INFORMADO} />
          <Campo rotulo="Instituição financeira:" valor={d.banco ? `Banco ${d.banco}` : NAO_INFORMADO} />
          <Campo rotulo="Agência:" valor={d.agencia ?? NAO_INFORMADO} />
          <Campo rotulo="Operação:" valor={d.operacao ?? NAO_INFORMADO} />
          <Campo rotulo="Conta:" valor={d.conta ?? NAO_INFORMADO} />
          <Campo rotulo="Dígito da conta:" valor={d.digito_conta ?? NAO_INFORMADO} />
          <div />
          <Campo rotulo="E-mail do cliente:" valor={FORA_DA_FOTO} apagado />
          <Campo rotulo="Telefone do cliente:" valor={FORA_DA_FOTO} apagado />
          <Campo rotulo="Celular do cliente:" valor={FORA_DA_FOTO} apagado />
        </div>
      )}
    </div>
  );
}
