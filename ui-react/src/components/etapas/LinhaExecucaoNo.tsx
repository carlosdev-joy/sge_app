// Camada de execução DENTRO do nó do canvas de Etapas (F3, §3 Bloco A).
//
// Um componente só, usado pelos cinco tipos de nó (etapa, decisão, SQL,
// notificação, aguarde) para não repetir a mesma marcação cinco vezes. Ele
// entrega as DUAS coisas que o §3 pede em cada etapa — status e horários — sem
// mexer na identidade visual do nó:
//
//   • o ANEL de status vai no TILE do ícone, em `outline` (a mesma escolha do
//     MalhaPipelineNode na F9: outline não briga com o `ring` box-shadow da
//     seleção nem com o anel âmbar de pendência — os três convivem);
//   • a LINHA de baixo do nó, que na montagem mostra "tipo · #ordem", passa a
//     mostrar "● sucesso · 09:49:59 → 09:50:15 · 16s". Ela cabe no lugar que já
//     existe (w-[128px]) e evita um badge espremido sobre um tile de 32px.
//
// O tooltip completo (status, início, fim, duração, tentativa, host) fica no
// `title` desta linha — ver `decorarEtapa` em execucaoEtapas.ts, que monta tudo.
// O anel de status NÃO sai daqui como helper exportado: `react-refresh/
// only-export-components` (regra ativa no eslint.config.js) reclama de export
// não-componente em arquivo de componente. Cada nó aplica `exec?.anel ?? ''`
// direto no tile — uma expressão, não vale um módulo.
import type { ExecNoEtapa } from './execucaoEtapas'

export function LinhaExecucaoNo({ exec }: { exec: ExecNoEtapa }) {
  // DUAS linhas, não uma: numa linha só de 128px o horário era cortado
  // ("sucesso · 18:01:06 → 1…") — e horário pela metade é pior que horário
  // nenhum num painel de incidente. Status em cima, janela embaixo; a largura
  // continua a mesma dos irmãos, então nada muda no espaçamento do grafo.
  return (
    <>
      <p
        className={[
          'mt-0.5 flex w-[128px] items-center justify-center gap-1 text-center',
          'text-[9px] font-semibold leading-tight',
          exec.pulada ? 'text-dim/70' : 'text-dim',
        ].join(' ')}
        title={exec.titulo}
      >
        <span
          className={`h-1.5 w-1.5 shrink-0 rounded-full ${exec.dot} ${exec.animado ? 'animate-pulse' : ''}`}
        />
        <span className="truncate">{exec.rotulo}</span>
      </p>
      {exec.status && (
        <p
          className="w-[128px] text-center text-[9px] leading-tight text-dim/70"
          title={exec.titulo}
        >
          {exec.resumo}
        </p>
      )}
    </>
  )
}
