
interface Tab { id: string; label: string; icon?: string }
interface TabsProps {
  tabs: Tab[]
  active: string
  onChange: (id: string) => void
  size?: 'sm' | 'md'
}

export function Tabs({ tabs, active, onChange, size = 'md' }: TabsProps) {
  return (
    <div className="flex border-b border-edge">
      {tabs.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={`px-4 ${size === 'sm' ? 'py-1.5 text-xs' : 'py-2.5 text-sm'} font-medium border-b-2 transition-colors whitespace-nowrap ${
            active === t.id
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-dim hover:text-ink'
          }`}
        >
          {t.icon && <span className="mr-1.5">{t.icon}</span>}
          {t.label}
        </button>
      ))}
    </div>
  )
}
