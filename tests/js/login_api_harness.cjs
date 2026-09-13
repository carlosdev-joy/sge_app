// Regressão: executa api.ts real sem navegador, com transporte e tempo controlados.
const fs = require('fs')
const path = require('path')
const vm = require('vm')
const assert = require('node:assert/strict')
const raiz = path.resolve(__dirname, '../..')
const { transform } = require(path.join(raiz, 'ui-react/node_modules/sucrase'))
const fonte = process.argv[2] || path.join(raiz, 'ui-react/src/lib/api.ts')
const js = transform(fs.readFileSync(fonte, 'utf8'), { transforms: ['typescript', 'imports'] }).code
let resposta, timeout, timers = 0, redirects = 0, removidos = 0, chamadas = []
const contexto = {
  exports: {}, AbortController, Error, TypeError, SyntaxError,
  setTimeout(fn) { timeout = fn; timers++; return timers },
  clearTimeout() { timers-- },
  fetch: async (url, opts) => { chamadas.push({ url, opts }); return resposta(url, opts) },
  localStorage: { getItem: () => 'token-anterior', removeItem: () => removidos++ },
  window: { location: { set href(v) { assert.equal(v, '/login'); redirects++ } } },
}
vm.runInNewContext(js, contexto)
const { apiLogin, apiFetch, mensagemErroLogin } = contexto.exports
const ok = { token: 'nova-sessao', usuario: { matricula: 'CVP1', permissoes: ['tela_utilitarios'] } }
const http = (status, detail) => new Response(JSON.stringify({ detail }), { status })
async function erro(fn) { try { await fn(); assert.fail('Esperava rejeição') } catch (e) { return e } }
async function main() {
  assert.equal(typeof apiLogin, 'function', 'Login precisa de transporte dedicado')
  resposta = () => new Response(JSON.stringify(ok), { status: 200 })
  assert.deepEqual(await apiLogin('  CVP1  ', '  senha com espaços  '), ok)
  let pedido = chamadas.at(-1)
  assert.equal(pedido.url, '/orquestra/auth/login')
  assert.equal(pedido.opts.method, 'POST')
  assert.equal(pedido.opts.headers.Authorization, undefined)
  assert.equal(pedido.opts.credentials, 'omit')
  assert.deepEqual(JSON.parse(pedido.opts.body), { usuario: 'CVP1', senha: '  senha com espaços  ' })
  assert.equal(timers, 0)
  const mensagens = {
    401: 'Matrícula ou senha incorreta. Use a mesma senha da sua rede corporativa',
    403: 'Sua matrícula não tem acesso liberado. Abra um chamado para a Engenharia de Dados',
    422: 'Preencha matrícula e senha.',
    500: 'Não foi possível abrir sua sessão. O problema é do sistema, não da sua senha',
    502: 'Serviço de autenticação indisponível. Não é a sua senha — tente em alguns minutos',
  }
  for (const status of [401, 403, 422, 500, 502]) {
    for (const detail of ['Matrícula inexistente', 'Senha inválida; detalhe interno']) {
      resposta = () => http(status, detail)
      const e = await erro(() => apiLogin('CVP1', 'senha'))
      assert.equal(e.tipo, 'http'); assert.equal(e.status, status)
      assert.equal(mensagemErroLogin(e), mensagens[status])
      assert.equal(redirects, 0); assert.equal(removidos, 0); assert.equal(timers, 0)
    }
  }
  resposta = () => new Response('<html>Gateway</html>', { status: 502 })
  assert.equal(mensagemErroLogin(await erro(() => apiLogin('CVP1', 'x'))), mensagens[502])
  resposta = () => { throw new TypeError('Failed to fetch') }
  const rede = await erro(() => apiLogin('CVP1', 'x'))
  assert.equal(rede.tipo, 'transporte')
  assert.equal(mensagemErroLogin(rede), 'Não foi possível conectar ao ORQ. Verifique sua conexão corporativa')
  resposta = (_, opts) => new Promise((resolve, reject) => opts.signal.addEventListener('abort', () => reject(new Error('AbortError'))))
  const pendente = erro(() => apiLogin('CVP1', 'x'))
  timeout()
  assert.equal((await pendente).tipo, 'transporte'); assert.equal(timers, 0)
  resposta = () => ({ ok: true, json: async () => { throw new TypeError('Conexão interrompida no corpo') } })
  assert.equal((await erro(() => apiLogin('CVP1', 'x'))).tipo, 'transporte')
  for (const body of ['<html>sem JSON</html>', '{}']) {
    resposta = () => new Response(body, { status: 200 })
    assert.equal((await erro(() => apiLogin('CVP1', 'x'))).tipo, 'resposta')
  }
  // O interceptador GLOBAL continua expirando 401 em telas autenticadas.
  resposta = () => http(401, 'Sessão vencida')
  await erro(() => apiFetch('/pipelines'))
  assert.equal(redirects, 1); assert.equal(removidos, 1)
  assert.equal(chamadas.at(-1).opts.headers.Authorization, 'Bearer token-anterior')
  // O shape de erro global permanece status/detail/message.
  resposta = () => http(403, 'Acesso negado')
  const global = await erro(() => apiFetch('/pipelines'))
  assert.equal(global.status, 403); assert.equal(global.detail, 'Acesso negado'); assert.equal(global.message, 'Acesso negado')
  console.log('OK: login dedicado, statuses, antienumeração, senha preservada, transporte, timeout e API global.')
}
main().catch(e => { console.error(e); process.exitCode = 1 })
