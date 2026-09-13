import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/auth'
import { apiFetch } from '../lib/api'
import { firstVisiblePath } from '../lib/nav'
import { Logo, ORQUESTRA_SUBTITLE } from '../components/layout/Logo'
import { ArrowRight, Database, Tickets, Network, CodeXml, BrainCircuit, LoaderCircle } from 'lucide-react'
import { Input } from '../components/ui/Input'
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
  const setAuth = useAuthStore((s) => s.setAuth)
  const navigate = useNavigate()

  const checkCapsLock = (e: React.KeyboardEvent) => {
    setCapsLock(e.getModifierState('CapsLock'))
  }

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    if (loading) return
    setError('')
    setLoading(true)
    try {
      const res = await apiFetch<{ token: string; usuario: any }>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ usuario: matricula, senha }),
      })
      setAuth(res.usuario, res.token)
      navigate(firstVisiblePath(res.usuario?.permissoes))
    } catch (err: any) {
      setError(err.message ?? 'Erro ao fazer login')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="orq-login">
      <div className="orq-login-card">
        <section className="orq-login-brand" aria-label="Sobre a plataforma ORQ">
          <div className="orq-login-positioning">
            <Logo variant="white" iconSize={110} className="orq-login-logo" />
            <p className="orq-login-description">{ORQUESTRA_SUBTITLE}</p>
          </div>
          <ul className="orq-login-capabilities">
            {CAPACIDADES.map(({ titulo, texto, Icone }) => (
              <li key={titulo}>
                <Icone size={26} strokeWidth={1.6} aria-hidden="true" />
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

            <form onSubmit={handleLogin} className="orq-login-form" aria-busy={loading}>
              <div className="orq-login-field">
                <label htmlFor="login_user">Matrícula</label>
                <Input id="login_user" type="text" value={matricula}
                  onChange={e => setMatricula(e.target.value)} placeholder="Digite sua matrícula"
                  autoComplete="username" autoCapitalize="none" spellCheck={false} required />
              </div>
              <div className="orq-login-field">
                <label htmlFor="login_pass">Senha</label>
                <Input id="login_pass" type="password" value={senha}
                  onChange={e => setSenha(e.target.value)} onKeyUp={checkCapsLock} onKeyDown={checkCapsLock}
                  autoComplete="current-password" required
                  aria-describedby={capsLock ? 'login-caps-lock' : undefined} />
                {capsLock && (
                  <p id="login-caps-lock" role="status"
                    className="rounded-lg px-3 py-2 text-xs bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-100">
                    ⇪ Caps Lock ativado — verifique antes de digitar
                  </p>
                )}
              </div>
              {error && <p role="alert" className="rounded-lg px-3 py-2.5 text-sm bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-200">{error}</p>}
              <button type="submit" disabled={loading} className="orq-login-submit">
                {loading ? <><LoaderCircle size={17} className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> Entrando…</> : <>ENTRAR <ArrowRight size={17} aria-hidden="true" /></>}
              </button>
            </form>

            <footer className="orq-login-footer">
              <p>Pressione <strong>Enter</strong> para entrar.</p>
              <p>Desenvolvido pela <span>Engenharia de Dados</span></p>
            </footer>
          </div>
        </section>
      </div>
    </main>
  )
}
