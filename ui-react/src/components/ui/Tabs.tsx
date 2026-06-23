
interface Tab { id: string; label: string; icon?: string; badge?: number }
interface TabsProps {
  tabs: Tab[]
  active: string
  onChange: (id: string) => void
  size?: 'sm' | 'md'
}

export function Tabs({ tabs, active, onChange, size = 'md' }: TabsProps) {
  return (
    <div className="flex border-b border-edge overflow-x-auto">
      {tabs.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={`inline-flex items-center gap-1.5 px-4 ${size === 'sm' ? 'py-1.5 text-xs' : 'py-2.5 text-sm'} font-medium border-b-2 transition-colors whitespace-nowrap ${
            active === t.id
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-dim hover:text-ink'
          }`}
        >
          {t.icon && <span className="mr-1.5">{t.icon}</span>}
          {t.label}
          {t.badge != null && t.badge > 0 && (
            <span className="inline-flex items-center justify-center min-w-[1.25rem] px-1.5 py-0.5 rounded-full text-[10px] font-semibold leading-none bg-red-100 text-red-700 border border-red-300 dark:bg-red-900/50 dark:text-red-400 dark:border-red-800">
              {t.badge}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}
