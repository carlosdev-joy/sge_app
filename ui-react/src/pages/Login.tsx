import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/auth'
import { apiFetch } from '../lib/api'

const LOGO = 'https://rseofspzecpjtqzcbaol.supabase.co/storage/v1/object/public/mundolc/Vertical_Branco.png'

const BULLETS = [
  'Centralize e controle todos os pipelines em um só lugar',
  'Crie e gerencie DAGs com rastreamento de origem e destino',
  'Vincule jobs aos pipelines e acompanhe execuções em tempo real',
  'Logs detalhados e dashboard com os principais indicadores',
]

export default function Login() {
  const [matricula, setMatricula]   = useState('')
  const [senha, setSenha]           = useState('')
  const [error, setError]           = useState('')
  const [loading, setLoading]       = useState(false)
  const [capsLock, setCapsLock]     = useState(false)
  const setAuth = useAuthStore((s) => s.setAuth)
  const navigate = useNavigate()

  const checkCapsLock = (e: React.KeyboardEvent) => {
    setCapsLock(e.getModifierState('CapsLock'))
  }

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await apiFetch<{ token: string; usuario: any }>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ usuario: matricula, senha }),
      })
      setAuth(res.usuario, res.token)
      navigate('/dashboard')
    } catch (err: any) {
      setError(err.message ?? 'Erro ao fazer login')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-white dark:bg-neutral-950">
      <div className="w-full max-w-3xl rounded-2xl overflow-hidden shadow-2xl flex">

        {/* ── Painel esquerdo — marca ──────────────────────────────── */}
        <div
          className="hidden md:flex flex-col justify-between p-10 w-[400px] shrink-0 text-white"
          style={{ background: 'rgba(0,0,0,0.18)' }}
        >
          <div>
            <img
              src={LOGO}
              alt="Caixa Vida e Previdência"
              className="h-14 w-auto mb-8"
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
            />
            <h1 className="text-[22px] font-medium leading-tight mb-1">ORQUESTRA</h1>
            <p className="text-white/55 text-sm mb-6">
              ORQ · Organizador de Rotinas, Queues e Execução
            </p>
            <div className="inline-flex items-center gap-2 bg-white/10 border border-white/20 rounded-full px-3 py-1.5 text-xs font-medium mb-8">
              <span className="text-base leading-none">⬡</span>
              <span>Plataforma de Engenharia de Dados</span>
            </div>
            <ul className="flex flex-col gap-3.5">
              {BULLETS.map((item) => (
                <li key={item} className="flex items-start gap-3 text-sm text-white/80 leading-snug">
                  <span className="mt-[5px] w-1.5 h-1.5 rounded-full bg-blue-300 shrink-0" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
          <p className="text-[11px] text-white/30 mt-8">
            Desenvolvido pela Engenharia de Dados
          </p>
        </div>

        {/* ── Painel direito — formulário ──────────────────────────── */}
        <div className="flex-1 bg-white dark:bg-neutral-900 p-8 md:p-10 flex flex-col justify-center">

          {/* Logo só em mobile */}
          <div className="flex md:hidden justify-center mb-6">
            <img
              src={LOGO}
              alt="Caixa Vida e Previdência"
              className="h-10 w-auto"
              style={{ filter: 'invert(35%) sepia(80%) saturate(600%) hue-rotate(190deg)' }}
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
            />
          </div>

          <div className="mb-7">
            <p className="text-lg font-semibold text-gray-900 dark:text-white">
              Entrar no ORQUESTRA
            </p>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              Use sua matrícula de rede. Sem acesso, fale com a engenharia de dados.
            </p>
          </div>

          <form onSubmit={handleLogin} className="flex flex-col gap-5">

            {/* Matrícula */}
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="login_user"
                className="text-[11px] font-bold tracking-widest uppercase text-gray-500 dark:text-gray-400"
              >
                Matrícula
              </label>
              <input
                id="login_user"
                type="text"
                value={matricula}
                onChange={(e) => setMatricula(e.target.value)}
                placeholder="ex: CVP12345"
                autoComplete="username"
                autoFocus
                required
                className="w-full px-3.5 py-2.5 rounded-lg border border-gray-200 dark:border-neutral-700
                           bg-white dark:bg-neutral-800 text-gray-900 dark:text-white
                           placeholder:text-gray-400 dark:placeholder:text-gray-600
                           text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
                           transition-shadow"
              />
            </div>

            {/* Senha + aviso Caps Lock */}
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="login_pass"
                className="text-[11px] font-bold tracking-widest uppercase text-gray-500 dark:text-gray-400"
              >
                Senha
              </label>
              <input
                id="login_pass"
                type="password"
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                onKeyUp={checkCapsLock}
                onKeyDown={checkCapsLock}
                autoComplete="current-password"
                required
                className="w-full px-3.5 py-2.5 rounded-lg border border-gray-200 dark:border-neutral-700
                           bg-white dark:bg-neutral-800 text-gray-900 dark:text-white
                           placeholder:text-gray-400 dark:placeholder:text-gray-600
                           text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
                           transition-shadow"
              />
              {capsLock && (
                <div
                  className="flex items-center gap-2 mt-0.5 px-3 py-2 rounded-xl text-xs font-bold"
                  style={{ background: '#FAEEDA', border: '0.5px solid #EF9F27', color: '#633806' }}
                >
                  <span className="text-sm">⇪</span>
                  Caps Lock ativado — verifique antes de digitar
                </div>
              )}
            </div>

            {/* Erro */}
            {error && (
              <div className="px-3 py-2.5 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 text-sm">
                {error}
              </div>
            )}

            {/* Botão */}
            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 rounded-lg font-bold text-sm tracking-wide text-white
                         transition-all disabled:opacity-60 disabled:cursor-not-allowed
                         hover:brightness-110 active:scale-[.98]"
              style={{ background: 'linear-gradient(135deg, #1A5FA8 0%, #0D3D6B 100%)' }}
            >
              {loading ? 'Entrando…' : 'ENTRAR'}
            </button>
          </form>

          <p className="text-center text-xs text-gray-400 dark:text-gray-600 mt-6 leading-relaxed">
            Pressione <strong>Enter</strong> para entrar
            {' · '}
            <span className="text-blue-600 dark:text-blue-400 font-semibold whitespace-nowrap">
              Desenvolvido pela Engenharia de Dados
            </span>
          </p>
        </div>

      </div>
    </div>
  )
}
