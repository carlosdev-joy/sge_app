
// ─────────────────────────────────────────────────────────────────────────────
// `badgeTom` — spec docs/spec-malha-execucao.md §9.9.
//
// Até aqui TODO badge de aba era pintado de vermelho. Isso funciona para a
// única aba com badge que existe hoje ("Erros e avisos" do DsConsole), onde o
// número É o problema — e quebra na hora em que a aba conta coisa saudável: o
// painel da corrida abre com `Agora (2)`, dois pipelines rodando bem, e o
// operador leria "2 problemas" às 3h. `Agora` é neutro, `Travando` é alerta.
//
// O default continua sendo `alerta` DE PROPÓSITO: mudar o padrão para neutro
// repintaria o badge de erros do DsConsole sem que ninguém tivesse pedido, e
// tirar cor de um contador de falhas é o tipo de silêncio que esta casa não
// aceita. Quem tem badge saudável declara.
// ─────────────────────────────────────────────────────────────────────────────

export type BadgeTomTab = 'neutro' | 'alerta'

interface Tab {
  id: string
  label: string
  icon?: string
  badge?: number
  /** Cor do badge. Omitido = 'alerta' (o vermelho de sempre). */
  badgeTom?: BadgeTomTab
}
interface TabsProps {
  tabs: Tab[]
  active: string
  onChange: (id: string) => void
  size?: 'sm' | 'md'
}

const BADGE_TOM: Record<BadgeTomTab, string> = {
  // Par claro+escuro obrigatório (docs/ui-temas-cores.md:63-82) — as classes
  // do tom `alerta` são as de sempre, byte a byte.
  alerta:
    'bg-red-100 text-red-700 border-red-300 ' +
    'dark:bg-red-900/50 dark:text-red-400 dark:border-red-800',
  // Sem `dark:` DE PROPÓSITO: `edge` e `dim` são tokens de superfície, e o
  // valor deles já troca com o tema (index.css). Duplicar em `dark:` seria
  // repetir a mesma cor e sugerir, para quem lê depois, que existe um ajuste
  // de tema aqui que não existe.
  neutro: 'bg-edge/60 text-dim border-edge',
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
            <span className={`inline-flex items-center justify-center min-w-[1.25rem] px-1.5 py-0.5 rounded-full text-[10px] font-semibold leading-none border ${BADGE_TOM[t.badgeTom ?? 'alerta']}`}>
              {t.badge}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}
