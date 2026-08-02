// Badge de criticidade — extraído da tela Malha na F8 para ser compartilhado
// entre a página (cards de pipeline/malha) e o nó do MalhaEditor, sem import
// circular página↔componente. Mesmo domínio do backend (etl_pipeline.criticidade,
// texto livre): valor fora do domínio degrada para MEDIA.

const CRIT_STYLES: Record<string, string> = {
  CRITICA: 'bg-pink-100 text-pink-800 border border-pink-200 dark:bg-pink-900/40 dark:text-pink-300 dark:border-pink-800',
  ALTA:    'bg-red-100 text-red-700 border border-red-200 dark:bg-red-900/40 dark:text-red-300 dark:border-red-800',
  MEDIA:   'bg-amber-100 text-amber-700 border border-amber-200 dark:bg-amber-900/40 dark:text-amber-300 dark:border-amber-800',
  BAIXA:   'bg-green-100 text-green-700 border border-green-200 dark:bg-green-900/40 dark:text-green-300 dark:border-green-800',
}

export function CritBadge({ crit }: { crit: string }) {
  const upper = crit?.toUpperCase() ?? 'MEDIA'
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase ${CRIT_STYLES[upper] ?? CRIT_STYLES['MEDIA']}`}>
      {upper}
    </span>
  )
}
