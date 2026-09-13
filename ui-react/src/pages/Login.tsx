import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/auth'
import { apiLogin, mensagemErroLogin } from '../lib/api'
import { firstVisiblePath } from '../lib/nav'
import { Logo, ORQUESTRA_SUBTITLE } from '../components/layout/Logo'
import { ArrowRight, Database, Tickets, Network, CodeXml, BrainCircuit, LoaderCircle, Eye, EyeOff, Sun, Moon } from 'lucide-react'
import { Input } from '../components/ui/Input'
import { getTheme, toggleTheme } from '../lib/theme'
import { usePublicVersion } from '../lib/publicVersion'
import './Login.css'

const CAPACIDADES = [
  { titulo: 'Pipelines', texto: 'Monitore e gerencie seus pipelines de dados em tempo real.', Icone: Database },
  { titulo: 'Chamados', texto: 'Centralize, acompanhe e resolva solicitações.', Icone: Tickets },
  { titulo: 'Lineage', texto: 'Visualize a origem e o fluxo dos dados entre sistemas.', Icone: Network },
  { titulo: 'Desenvolvimento', texto: 'Crie e gerencie ETL e integrações de forma colaborativa.', Icone: CodeXml },
  { titulo: 'IA', texto: 'Automatize processos e gere insights com inteligência artificial.', Icone: BrainCircuit },
]

export default function Login() {
  const [matricula, setMatricula]   = useState('')
  const [senha, setSenha]           = useState('')
  const [error, setError]           = useState('')
  const [loading, setLoading]       = useState(false)
  const [capsLock, setCapsLock]     = useState(false)
  const [mostrarSenha, setMostrarSenha] = useState(false)
  const [theme, setTheme] = useState(getTheme)
  const emCurso = useRef(false)
  const versao = usePublicVersion()
  const setAuth = useAuthStore((s) => s.setAuth)
  const navigate = useNavigate()

  const checkCapsLock = (e: React.KeyboardEvent) => {
    setCapsLock(e.getModifierState('CapsLock'))
  }

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    if (emCurso.current) return
    setMostrarSenha(false)
    if (!matricula.trim() || !senha) {
      setError(mensagemErroLogin({ status: 422 }))
      return
    }
    emCurso.current = true
    setError('')
    setLoading(true)
    try {
      const res = await apiLogin(matricula, senha)
      setAuth(res.usuario, res.token)
      navigate(firstVisiblePath(res.usuario?.permissoes))
    } catch (err: unknown) {
      setError(mensagemErroLogin(err))
    } finally {
      emCurso.current = false
      setLoading(false)
    }
  }

  return (
    <main className="orq-login">
      <div className="orq-login-card">
        <section className="orq-login-brand" aria-label="Sobre a plataforma ORQ">
          <div className="orq-login-positioning">
            <Logo variant="white" iconSize={120} className="orq-login-logo" />
            <p className="orq-login-description">{ORQUESTRA_SUBTITLE}</p>
          </div>
          <ul className="orq-login-capabilities">
            {CAPACIDADES.map(({ titulo, texto, Icone }) => (
              <li key={titulo}>
                <Icone size={20} strokeWidth={1.8} aria-hidden="true" />
                <div>
                  <h2>{titulo}</h2>
                  <p>{texto}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section className="orq-login-form-panel" aria-labelledby="login-title">
          <div className="orq-login-form-content">
            <header className="orq-login-form-heading">
              <h1 id="login-title">Entrar no <span>ORQ</span></h1>
              <p>Use sua matrícula de rede. Sem acesso, fale com a engenharia de dados.</p>
            </header>

            <form noValidate onSubmit={handleLogin} className="orq-login-form" aria-busy={loading}>
              <div className="orq-login-field">
                <label htmlFor="login_user">Matrícula</label>
                <Input id="login_user" type="text" value={matricula}
                  onChange={e => setMatricula(e.target.value)} placeholder="Digite sua matrícula"
                  autoComplete="username" autoCapitalize="none" spellCheck={false} required autoFocus
                  readOnly={loading} aria-describedby={error ? 'login-error' : undefined} />
              </div>
              <div className="orq-login-field">
                <label htmlFor="login_pass">Senha</label>
                <div className="orq-login-password">
                  <Input id="login_pass" type={mostrarSenha ? 'text' : 'password'} value={senha}
                    onChange={e => setSenha(e.target.value)} onKeyUp={checkCapsLock} onKeyDown={checkCapsLock}
                    autoComplete="current-password" required readOnly={loading}
                    aria-describedby={[capsLock && 'login-caps-lock', error && 'login-error'].filter(Boolean).join(' ') || undefined} />
                  <button type="button" className="orq-login-password-toggle" disabled={loading}
                    aria-label={mostrarSenha ? 'Ocultar senha' : 'Mostrar senha'} aria-controls="login_pass"
                    onClick={() => setMostrarSenha(v => !v)}>
                    {mostrarSenha ? <EyeOff size={20} aria-hidden="true" /> : <Eye size={20} aria-hidden="true" />}
                  </button>
                </div>
                {capsLock && (
                  <p id="login-caps-lock" role="status"
                    className="rounded-lg px-3 py-2 text-xs bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-100">
                    ⇪ Caps Lock ativado — verifique antes de digitar
                  </p>
                )}
              </div>
              {error && <p id="login-error" role="alert" aria-live="polite" aria-atomic="true" className="rounded-lg px-3 py-2.5 text-sm bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-200">{error}</p>}
              <button type="submit" disabled={loading} className="orq-login-submit">
                {loading ? <><LoaderCircle size={17} className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> Entrando…</> : <>ENTRAR <ArrowRight size={17} aria-hidden="true" /></>}
              </button>
            </form>

            <footer className="orq-login-footer">
              <p>Desenvolvido pela <span>Engenharia de Dados</span></p>
              {versao && <p className="orq-login-version">Versão {versao}</p>}
            </footer>
          </div>
          <button type="button" className="orq-login-theme"
            aria-label={theme === 'dark' ? 'Mudar para tema claro' : 'Mudar para tema escuro'}
            onClick={() => setTheme(toggleTheme())}>
            {theme === 'dark' ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}
          </button>
        </section>
      </div>
    </main>
  )
}
