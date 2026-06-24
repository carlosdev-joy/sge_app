// Metadados visuais por tipo de etapa — fonte única reutilizada pelos nodes
// custom (EtapaNode), pela paleta e pela legenda do canvas.
// Espelha a paleta do ExecDiagram (pages/Jobs.tsx): cada acento tem par
// claro+escuro; nada de cor de paleta sem `dark:`.
import type { LucideIcon } from 'lucide-react'
import { Database, Terminal, FileCode2, Table2, Globe } from 'lucide-react'

export type EtapaType =
  | 'datastage'
  | 'shell'
  | 'python'
  | 'storedproc'
  | 'sql'
  | 'http'

export interface TypeMeta {
  label: string
  icon: LucideIcon
  // chip do ícone (fundo sólido + ícone branco) — vivo nos dois temas
  chip: string
  // badge pequeno do rodapé (fundo suave + texto, com par dark:)
  badge: string
  // pontinho da legenda / minimapa
  dot: string
  // cor base do node (usada no MiniMap nodeColor)
  hex: string
}

export const TYPE_META: Record<EtapaType, TypeMeta> = {
  datastage: {
    label: 'DataStage',
    icon: Database,
    chip: 'bg-blue-500 text-white',
    badge: 'bg-blue-50 text-blue-700 border border-blue-200 dark:bg-blue-900/30 dark:text-blue-300 dark:border-blue-800',
    dot: 'bg-blue-500',
    hex: '#3b82f6',
  },
  shell: {
    label: 'Shell',
    icon: Terminal,
    chip: 'bg-amber-500 text-white',
    badge: 'bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-800',
    dot: 'bg-amber-500',
    hex: '#f59e0b',
  },
  python: {
    label: 'Python',
    icon: FileCode2,
    chip: 'bg-green-500 text-white',
    badge: 'bg-green-50 text-green-700 border border-green-200 dark:bg-green-900/30 dark:text-green-300 dark:border-green-800',
    dot: 'bg-green-500',
    hex: '#22c55e',
  },
  storedproc: {
    label: 'Stored Proc',
    icon: Database,
    chip: 'bg-purple-500 text-white',
    badge: 'bg-purple-50 text-purple-700 border border-purple-200 dark:bg-purple-900/30 dark:text-purple-300 dark:border-purple-800',
    dot: 'bg-purple-500',
    hex: '#a855f7',
  },
  sql: {
    label: 'SQL',
    icon: Table2,
    chip: 'bg-cyan-500 text-white',
    badge: 'bg-cyan-50 text-cyan-700 border border-cyan-200 dark:bg-cyan-900/30 dark:text-cyan-300 dark:border-cyan-800',
    dot: 'bg-cyan-500',
    hex: '#06b6d4',
  },
  http: {
    label: 'HTTP',
    icon: Globe,
    chip: 'bg-orange-500 text-white',
    badge: 'bg-orange-50 text-orange-700 border border-orange-200 dark:bg-orange-900/30 dark:text-orange-300 dark:border-orange-800',
    dot: 'bg-orange-500',
    hex: '#f97316',
  },
}

export const TYPE_ORDER: EtapaType[] = [
  'datastage', 'shell', 'python', 'storedproc', 'sql', 'http',
]
