import { useState, useEffect, useRef, useCallback } from 'react'
import { Loader2 } from 'lucide-react'

interface AutocompleteProps {
  label?: string
  value: string
  onChange: (v: string) => void
  onSelect?: (v: string) => void
  fetchSuggestions: (q: string) => Promise<string[]>
  placeholder?: string
  className?: string
  minChars?: number
  disabled?: boolean
  onKeyDown?: (e: React.KeyboardEvent<HTMLInputElement>) => void
}

export function Autocomplete({
  label,
  value,
  onChange,
  onSelect,
  fetchSuggestions,
  placeholder,
  className = '',
  minChars = 1,
  disabled,
  onKeyDown,
}: AutocompleteProps) {
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [active, setActive] = useState(-1)
  const containerRef = useRef<HTMLDivElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const fetch = useCallback(
    (q: string) => {
      if (q.length < minChars) { setSuggestions([]); setOpen(false); return }
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(async () => {
        setLoading(true)
        try {
          const results = await fetchSuggestions(q)
          setSuggestions(results)
          setOpen(results.length > 0)
          setActive(-1)
        } catch {
          setSuggestions([])
        } finally {
          setLoading(false)
        }
      }, 280)
    },
    [fetchSuggestions, minChars],
  )

  useEffect(() => {
    fetch(value)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [value, fetch])

  // Close on outside click
  useEffect(() => {
    function handle(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handle)
    return () => document.removeEventListener('mousedown', handle)
  }, [])

  function select(v: string) {
    onChange(v)
    onSelect?.(v)
    setOpen(false)
    setActive(-1)
  }

  function handleKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (open && suggestions.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setActive(i => Math.min(i + 1, suggestions.length - 1))
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setActive(i => Math.max(i - 1, 0))
        return
      }
      if (e.key === 'Enter' && active >= 0) {
        e.preventDefault()
        select(suggestions[active])
        return
      }
      if (e.key === 'Escape') {
        setOpen(false)
        return
      }
    }
    onKeyDown?.(e)
  }

  return (
    <div ref={containerRef} className={`relative flex flex-col gap-1 ${className}`}>
      {label && <label className="text-xs text-dim font-medium">{label}</label>}
      <div className="relative">
        <input
          value={value}
          onChange={e => { onChange(e.target.value); setOpen(true) }}
          onFocus={() => { if (suggestions.length > 0) setOpen(true) }}
          onKeyDown={handleKey}
          placeholder={placeholder}
          disabled={disabled}
          autoComplete="off"
          className="w-full bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm placeholder-dim focus:outline-none focus:ring-1 focus:ring-blue-500 pr-7"
        />
        {loading && (
          <Loader2 size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-dim animate-spin" />
        )}
      </div>

      {open && suggestions.length > 0 && (
        <ul className="absolute z-50 top-full mt-1 w-full bg-panel border border-edge rounded-lg shadow-lg overflow-hidden max-h-52 overflow-y-auto">
          {suggestions.map((s, i) => (
            <li
              key={s}
              onMouseDown={() => select(s)}
              className={`px-3 py-2 text-sm cursor-pointer font-mono transition-colors ${
                i === active
                  ? 'bg-blue-100 text-blue-700 dark:bg-blue-600/20 dark:text-blue-300'
                  : 'text-ink hover:bg-edge/30'
              }`}
            >
              {highlight(s, value)}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function highlight(text: string, query: string) {
  if (!query) return <>{text}</>
  const idx = text.toLowerCase().indexOf(query.toLowerCase())
  if (idx === -1) return <>{text}</>
  return (
    <>
      {text.slice(0, idx)}
      <span className="text-blue-400 font-semibold">{text.slice(idx, idx + query.length)}</span>
      {text.slice(idx + query.length)}
    </>
  )
}
