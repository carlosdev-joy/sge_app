import { create } from 'zustand'
import { CheckCircle, AlertCircle, Info, X } from 'lucide-react'

interface ToastItem { id: number; message: string; type: 'success' | 'error' | 'info' }
interface ToastStore {
  toasts: ToastItem[]
  add: (message: string, type?: ToastItem['type']) => void
  remove: (id: number) => void
}

let _id = 0

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  add: (message, type = 'info') => {
    const id = ++_id
    set((s) => ({ toasts: [...s.toasts, { id, message, type }] }))
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), 4000)
  },
  remove: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}))

export const toast = {
  success: (msg: string) => useToastStore.getState().add(msg, 'success'),
  error:   (msg: string) => useToastStore.getState().add(msg, 'error'),
  info:    (msg: string) => useToastStore.getState().add(msg, 'info'),
}

const ICONS = { success: CheckCircle, error: AlertCircle, info: Info }
const COLORS = {
  success: 'border-green-700 bg-panel',
  error:   'border-red-700 bg-panel',
  info:    'border-blue-700 bg-panel',
}
const ICON_COLORS = { success: 'text-green-400', error: 'text-red-400', info: 'text-blue-400' }

export function ToastContainer() {
  const { toasts, remove } = useToastStore()
  return (
    <div className="fixed bottom-4 left-4 z-[100] flex flex-col gap-2">
      {toasts.map((t) => {
        const Icon = ICONS[t.type]
        return (
          <div key={t.id} className={`flex items-start gap-3 px-4 py-3 rounded-lg border shadow-xl w-80 ${COLORS[t.type]}`}>
            <Icon size={16} className={`mt-0.5 shrink-0 ${ICON_COLORS[t.type]}`} />
            <span className="text-sm text-ink flex-1">{t.message}</span>
            <button onClick={() => remove(t.id)} className="text-dim hover:text-white shrink-0">
              <X size={14} />
            </button>
          </div>
        )
      })}
    </div>
  )
}
