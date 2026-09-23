// SSE do agente: executa `lib/agentes.ts` e `lib/agentesStream.ts` de verdade
// (transpilados com sucrase), com o `apiFetchBruto` trocado por um stream de
// teste que entrega os eventos PARTIDOS em pedaços arbitrários.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const root = path.resolve(__dirname, '../..')
const { transform } = require(path.join(root, 'ui-react/node_modules/sucrase'))
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'agentes-sse-'))
const escrever = (nome, codigo) => fs.writeFileSync(path.join(tmp, nome), codigo)
const tr = src => transform(src, { transforms: ['typescript', 'imports'], production: true }).code

;(async () => {
  try {
    escrever('agentes.js', tr(fs.readFileSync(path.join(root, 'ui-react/src/lib/agentes.ts'), 'utf8')))
    escrever('agentesStream.js', tr(fs.readFileSync(path.join(root, 'ui-react/src/lib/agentesStream.ts'), 'utf8')))
    // `./api` de teste: o próximo "servidor" é trocado por cada caso
    escrever('api.js', `let proximo = null
exports.definir = f => { proximo = f }
exports.apiFetchBruto = (...a) => proximo(...a)`)
    const lib = require(path.join(tmp, 'agentes.js'))
    const api = require(path.join(tmp, 'api.js'))
    const { conversarPorStream, rotaStreamAusente } = require(path.join(tmp, 'agentesStream.js'))

    // ── lerEventosSSE ──
    let r = lib.lerEventosSSE('data: {"tipo":"status","texto":"a"}\n\n: keep-alive\n\ndata: {"tipo":"sta')
    assert.deepEqual(r.eventos, [{ tipo: 'status', texto: 'a' }])
    assert.equal(r.resto, 'data: {"tipo":"sta', 'o evento pela metade fica para o próximo pedaço')
    r = lib.lerEventosSSE(r.resto + 'tus","texto":"b"}\r\n\r\n')
    assert.deepEqual(r.eventos, [{ tipo: 'status', texto: 'b' }])
    assert.equal(r.resto, '')
    r = lib.lerEventosSSE('data: {quebrado\n\ndata: {"tipo":"status","texto":"c"}\n\n')
    assert.deepEqual(r.eventos, [{ tipo: 'status', texto: 'c' }], 'JSON inválido é ignorado sem parar a leitura')
    r = lib.lerEventosSSE('data: {"sem_tipo":1}\n\n')
    assert.equal(r.eventos.length, 0)

    // ── formatarDuracao ──
    assert.equal(lib.formatarDuracao(4000), 'respondido em 4s')
    assert.equal(lib.formatarDuracao(42300), 'respondido em 42s')
    assert.equal(lib.formatarDuracao(135000), 'respondido em 2min 15s')
    assert.equal(lib.formatarDuracao(200), 'respondido em 1s')
    assert.equal(lib.formatarDuracao(undefined), '')
    assert.equal(lib.formatarDuracao(-5), '')

    // ── histórico: grupos por DIA de calendário e hora/dia ──
    const agora = new Date(2026, 8, 23, 8, 0)  // 23/09 08:00 (hora local)
    const iso = (d, h, m = 0) => {
      const x = new Date(2026, 8, d, h, m)
      const p = n => String(n).padStart(2, '0')
      return `${x.getFullYear()}-${p(x.getMonth() + 1)}-${p(x.getDate())} ${p(x.getHours())}:${p(x.getMinutes())}:00`
    }
    assert.equal(lib.grupoDaConversa(iso(23, 1, 8), agora), 'Hoje')
    assert.equal(lib.grupoDaConversa(iso(22, 23, 49), agora), 'Ontem', 'ontem 23h, hoje 8h: é Ontem, não "há 9 horas"')
    assert.equal(lib.grupoDaConversa(iso(19, 10), agora), 'Últimos 7 dias')
    assert.equal(lib.grupoDaConversa(iso(10, 10), agora), 'Mais antigas')
    assert.equal(lib.grupoDaConversa(null, agora), 'Mais antigas')
    assert.equal(lib.grupoDaConversa('lixo', agora), 'Mais antigas')
    assert.equal(lib.horaOuDia(iso(23, 1, 8), agora), '01:08')
    assert.equal(lib.horaOuDia(iso(19, 10), agora), '19/09')
    assert.equal(lib.horaOuDia(undefined, agora), '')
    assert.deepEqual([...lib.GRUPOS_HISTORICO], ['Hoje', 'Ontem', 'Últimos 7 dias', 'Mais antigas'])

    // ── conversarPorStream ──
    const enc = new TextEncoder()
    const servir = (pedacos) => api.definir(async () => ({
      body: new ReadableStream({ start(c) {
        for (const p of pedacos) c.enqueue(typeof p === 'string' ? enc.encode(p) : p)
        c.close()
      } }),
    }))
    const texto = 'data: {"tipo":"status","texto":"Pergunta recebida…"}\n\n: keep-alive\n\n'
      + 'data: {"tipo":"status","texto":"Consultando JobX ao vivo no DataStage…"}\n\n'
      + 'data: {"tipo":"resposta","conversa_id":"c1","texto":"ok","status":"ok","projeto":null,"artefatos":[],"duracao_ms":4200}\n\n'
    // partido em pedaços de 5 BYTES: eventos cortados no meio e o "…" (3 bytes
    // em UTF-8) cortado no meio do caractere — o `decode(..., {stream: true})`
    // tem de segurar o byte pela metade até o próximo pedaço
    const bytes = enc.encode(texto)
    const pedacos = []
    for (let i = 0; i < bytes.length; i += 5) pedacos.push(bytes.slice(i, i + 5))
    servir(pedacos)
    const status = []
    const resp = await conversarPorStream('datastage', '{}', t => status.push(t), () => false)
    assert.deepEqual(status, ['Pergunta recebida…', 'Consultando JobX ao vivo no DataStage…'])
    assert.equal(resp.conversa_id, 'c1')
    assert.equal(resp.duracao_ms, 4200)

    // erro depois de aberto → relançado no shape do apiFetch (detail)
    servir(['data: {"tipo":"erro","detail":{"code":"erro_interno","message":"falhou"}}\n\n'])
    await assert.rejects(conversarPorStream('datastage', '{}', () => {}, () => false),
      e => e.message === 'falhou' && e.detail.code === 'erro_interno')

    // stream que termina sem resposta → erro claro
    servir(['data: {"tipo":"status","texto":"a"}\n\n'])
    await assert.rejects(conversarPorStream('datastage', '{}', () => {}, () => false), /terminou antes da resposta/)

    // conversa trocada no meio → para de ler e devolve null
    servir([texto])
    const status2 = []
    let n = 0
    const r2 = await conversarPorStream('datastage', '{}', t => status2.push(t), () => ++n > 1)
    assert.equal(r2, null)
    assert.ok(status2.length <= 1)

    // rota ausente (API antiga) × 404 de conversa
    assert.equal(rotaStreamAusente({ status: 404, detail: 'Not Found' }), true)
    assert.equal(rotaStreamAusente({ status: 405, detail: 'Method Not Allowed' }), true)
    assert.equal(rotaStreamAusente({ status: 404, detail: { code: 'conversa_nao_encontrada' } }), false)
    assert.equal(rotaStreamAusente({ status: 503, detail: { code: 'agente_desligado' } }), false)
    console.log('ok')
  } catch (e) {
    console.error(e)
    process.exitCode = 1
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true })
  }
})()
