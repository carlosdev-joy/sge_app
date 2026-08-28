// O cabeçalho do card do kanban: número, o gesto de ver o conteúdo e o link
// para o ServiceNow.
//
// Componente próprio pelo mesmo motivo de `RodapeCard`: o que ele entrega é uma
// AFFORDANCE — a promessa de que há algo para ver — e promessa só se verifica
// olhando o que foi renderizado. Dentro de `pages/Chamados.tsx` isso era
// inalcançável para teste: a página importa react-query e não monta em bancada.
//
// ⚠️ O gesto precisa ser ANUNCIADO. A primeira versão abria o detalhe pelo
// título, com `hover:underline` e um `title`: quem não passasse o mouse — ou
// estivesse no toque — não tinha como saber que havia o que ver. Affordance que
// só existe no hover é affordance que não existe.
import { ExternalLink, FileText } from 'lucide-react'

const AJUDA = 'Ver descrição, histórico de notas e anexos deste chamado'

export function CabecalhoCard({ numero, titulo, url, aoAbrirDetalhe }: {
  numero: string
  titulo: string | null
  url: string | null
  aoAbrirDetalhe: () => void
}) {
  return (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs font-semibold text-ink">{numero}</span>
        <div className="flex items-center gap-2 shrink-0">
          {/* Ícone E palavra. Ícone sozinho vira adivinhação: "lupa" pode ser
              buscar, ampliar ou inspecionar, e quem chega na tela pela
              primeira vez não deveria precisar testar para descobrir. */}
          <button type="button" data-detalhe onClick={aoAbrirDetalhe}
            className="flex items-center gap-1 text-[10px] text-blue-600
              dark:text-blue-400 hover:underline"
            title={AJUDA}>
            <FileText size={11} aria-hidden />
            detalhes
          </button>
          {/* Os dois gestos de "ver mais" ficam juntos, e a diferença entre
              eles é dita: um abre AQUI, o outro abre no ServiceNow. */}
          {url && (
            <a href={url} data-servicenow target="_blank" rel="noopener noreferrer"
              className="text-blue-600 dark:text-blue-400"
              title="Abrir este chamado no ServiceNow (nova aba)">
              <ExternalLink size={12} />
            </a>
          )}
        </div>
      </div>
      {/* O título segue clicando para o mesmo lugar: quem já descobriu o gesto
          tem um alvo maior, e quem não descobriu tem o botão acima. */}
      <button type="button" data-titulo onClick={aoAbrirDetalhe}
        className="text-xs text-ink leading-snug text-left hover:underline"
        title={AJUDA}>
        {titulo || '(sem título)'}
      </button>
    </>
  )
}
