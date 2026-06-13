import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/auth'
import { apiFetch } from '../lib/api'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'

export default function Login() {
  const [matricula, setMatricula] = useState('')
  const [senha, setSenha] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const setAuth = useAuthStore((s) => s.setAuth)
  const navigate = useNavigate()

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
    <div className="min-h-screen bg-[#0f1117] flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="text-4xl font-bold text-blue-400 mb-2">⬡</div>
          <h1 className="text-2xl font-bold text-[#e2e8f0]">ORQUESTRA</h1>
          <p className="text-[#94a3b8] text-sm mt-1">Pipeline Orchestration Platform</p>
        </div>
        <form onSubmit={handleLogin} className="bg-[#1a1d27] border border-[#2a2d3a] rounded-xl p-6 flex flex-col gap-4">
          <Input
            label="Matrícula"
            value={matricula}
            onChange={(e) => setMatricula(e.target.value)}
            placeholder="ex: C123456"
            autoFocus
            required
          />
          <Input
            label="Senha"
            type="password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            placeholder="••••••••"
            required
          />
          {error && <p className="text-red-400 text-sm bg-red-900/20 border border-red-800 rounded px-3 py-2">{error}</p>}
          <Button type="submit" loading={loading} className="w-full justify-center mt-1">
            Entrar
          </Button>
        </form>
      </div>
    </div>
  )
}
