// Metadados visuais por tipo de etapa — fonte única reutilizada pelos nodes
// custom (EtapaNode), pela paleta e pela legenda do canvas.
// Espelha a paleta do ExecDiagram (pages/Jobs.tsx): cada acento tem par
// claro+escuro; nada de cor de paleta sem `dark:`.
import type { LucideIcon } from 'lucide-react'
import { Database, DatabaseZap, Terminal, FileCode2, Table2, Globe } from 'lucide-react'

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
  // badge pequeno (fundo suave + texto, com par dark:) — hoje SEM consumidor;
  // mantido porque documenta a identidade completa do tipo (par claro+escuro).
  badge: string
  // pontinho de legenda — hoje SEM consumidor (o minimapa usa `hex`); mantido
  // pelo mesmo motivo do badge.
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
    // Slate, não âmbar: o âmbar acumulava 3 significados no editor (shell,
    // aguarde e warning de validação); "terminal escuro" é idiomático para
    // shell e o glifo branco passa a ter contraste 3:1 (WCAG 1.4.11).
    chip: 'bg-slate-600 text-white',
    badge: 'bg-slate-50 text-slate-700 border border-slate-200 dark:bg-slate-900/30 dark:text-slate-300 dark:border-slate-800',
    dot: 'bg-slate-600',
    hex: '#475569',
  },
  python: {
    label: 'Python',
    icon: FileCode2,
    // green-600 (não 500): o glifo branco precisa de 3:1 sobre o chip.
    chip: 'bg-green-600 text-white',
    badge: 'bg-green-50 text-green-700 border border-green-200 dark:bg-green-900/30 dark:text-green-300 dark:border-green-800',
    dot: 'bg-green-600',
    hex: '#16a34a',
  },
  storedproc: {
    label: 'Stored Proc',
    // DatabaseZap, não Database: desambigua os 3 "bancos" (DataStage, Stored
    // Proc e nó SQL) mantendo a família visual — o raio diz "executa no banco".
    icon: DatabaseZap,
    chip: 'bg-purple-500 text-white',
    badge: 'bg-purple-50 text-purple-700 border border-purple-200 dark:bg-purple-900/30 dark:text-purple-300 dark:border-purple-800',
    dot: 'bg-purple-500',
    hex: '#a855f7',
  },
  // O nó SQL é um nó ESPECIAL: paleta (FluxoEditor), SqlNode e PainelSql têm as
  // cores/ícone hardcoded. Esta entrada não desenha nenhuma superfície — ela
  // documenta a identidade CANÔNICA (violet + Table2) e precisa espelhá-las.
  sql: {
    label: 'SQL',
    icon: Table2,
    chip: 'bg-violet-500 text-white',
    badge: 'bg-violet-50 text-violet-700 border border-violet-200 dark:bg-violet-900/30 dark:text-violet-300 dark:border-violet-800',
    dot: 'bg-violet-500',
    hex: '#8b5cf6',
  },
  http: {
    label: 'HTTP',
    icon: Globe,
    // orange-600 (não 500): o glifo branco precisa de 3:1 sobre o chip.
    chip: 'bg-orange-600 text-white',
    badge: 'bg-orange-50 text-orange-700 border border-orange-200 dark:bg-orange-900/30 dark:text-orange-300 dark:border-orange-800',
    dot: 'bg-orange-600',
    hex: '#ea580c',
  },
}

export const TYPE_ORDER: EtapaType[] = [
  'datastage', 'shell', 'python', 'storedproc', 'sql', 'http',
]

// Tipos que o backend aceita CRIAR pela paleta (arrastar-para-criar). `sql` é
// criável pela categoria "Fluxo" da paleta (nó especial, não entra aqui).
export const CREATABLE_TYPES: EtapaType[] = [
  'datastage', 'shell', 'python', 'storedproc', 'http',
]
