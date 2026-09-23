# Spec: Feedback de Progresso no Agente DataStage

**Data:** 2026-09-22  
**Contexto:** Sessão de mapeamento colaborativo — após validação do agente em produção  
**Prioridade:** Melhoria de UX — entrega junto ao ajuste fino do agente

---

> **✅ Itens A e D IMPLEMENTADOS em 23/09/2026** (branch `feat/agentes-progresso-sse`). Diferenças em relação ao
> texto abaixo: (1) **sem mudança no nginx** — o header `X-Accel-Buffering: no` desliga o buffer só desta resposta, e
> um keep-alive (`: keep-alive`) sai a cada 15 s, abaixo do `proxy_read_timeout 300s` da rota `/orquestra/` (conferido
> com um nginx 1.27 usando o mesmo bloco de produção: os eventos chegam no ritmo em que são emitidos); (2) a rodada
> roda numa task própria — cliente que fecha a aba não perde a resposta, que é gravada e aparece no histórico;
> (3) o leitor do front junta eventos partidos entre pedaços da rede (inclusive no meio de um caractere UTF-8) — o
> exemplo abaixo, que separa cada pedaço por `\n`, quebraria; (4) `duracao_ms` também vai no endpoint JSON e fica
> gravado, então a retomada mostra quanto cada resposta levou; (5) se a API ainda não tiver o `/stream`, a tela usa o
> endpoint JSON. **Smoke em produção:** `curl -N` no `/orquestra/agentes/datastage/conversar/stream` e conferir que
> os eventos chegam aos poucos (o `nginx.conf` de produção está à frente do repo — se tiver `gzip` para
> `text/event-stream`, eles ficariam retidos).

## Problema

O usuário que inicia uma consulta no agente DataStage fica sem feedback durante o processamento.
A tela exibe apenas "Mapeamento DataStage..." sem indicar o que está acontecendo nem quanto tempo
vai levar. Perguntas que envolvem `isx_extrair` (export via istool) podem levar de 30 a 90
segundos — o usuário não sabe se a tela travou ou está trabalhando.

---

## O que muda

### Item A — SSE (Server-Sent Events): eventos de progresso em tempo real

O backend emite eventos intermediários durante o processamento da rodada. O front exibe cada
evento como texto de status animado enquanto aguarda a resposta final.

#### Backend (`api/routers/agentes.py` + `api/services/agentes.py`)

**Novo endpoint SSE:**

```
POST /agentes/datastage/conversar/stream
```

Mesma autenticação e validação do endpoint existente (`POST /agentes/datastage/conversar`).
A diferença é o transporte: em vez de retornar JSON no fim, abre um `text/event-stream` e
emite eventos `data: {...}\n\n` conforme o processamento avança.

**Formato dos eventos:**

```json
{ "tipo": "status", "texto": "Localizando job no projeto BI_PRESTAMISTA..." }
{ "tipo": "status", "texto": "Extraindo ISX via istool — pode levar até 60s..." }
{ "tipo": "status", "texto": "Analisando stages e colunas..." }
{ "tipo": "status", "texto": "Consultando DataStage ao vivo..." }
{ "tipo": "resposta", "conversa_id": "...", "texto": "...", "status": "ok", "duracao_ms": 42300 }
{ "tipo": "erro", "detalhe": "..." }
```

**Pontos de emissão no `conversar()` em `agentes.py`:**

| Momento | Texto sugerido |
|---|---|
| Início da rodada (ferramenta pedida pelo modelo) | `"Consultando DataStage..."` |
| `resolver_projeto` chamado | `"Verificando projeto {projeto}..."` |
| `dsjob` chamado | `"Consultando job {job_name} ao vivo..."` |
| `isx_extrair` chamado | `"Extraindo definição do job via istool — pode levar até 60s..."` |
| Parse ISX concluído | `"Analisando stages e colunas..."` |
| `dsx_consulta` chamado | `"Lendo arquivo DSX do projeto..."` |
| Resposta do gateway recebida | `"Formatando resposta..."` |

**Implementação sugerida:**

```python
# Em conversar(), recebe um callback opcional emit_status
async def conversar(..., emit_status=None):
    ...
    if emit_status:
        await emit_status("Consultando DataStage...")
    ...

# No endpoint SSE:
async def conversar_stream(...):
    async def gen():
        queue = asyncio.Queue()

        async def emit(texto: str):
            await queue.put({"tipo": "status", "texto": texto})

        task = asyncio.create_task(conversar(..., emit_status=emit))
        while not task.done():
            try:
                evento = await asyncio.wait_for(queue.get(), timeout=1.0)
                yield f"data: {json.dumps(evento)}\n\n"
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"  # evita timeout do proxy/nginx
        resultado = await task
        yield f"data: {json.dumps({'tipo': 'resposta', **resultado})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})  # nginx: desliga buffer
```

**Atenção nginx:** adicionar `proxy_buffering off` no location do endpoint SSE para que os
eventos cheguem imediatamente ao browser sem buffer.

---

#### Frontend (componente da tela Agentes)

Substituir o `fetch` simples por `EventSource` (ou `fetch` com `ReadableStream`) no hook
que chama `/agentes/datastage/conversar`.

**Estado novo:**

```tsx
const [statusTexto, setStatusTexto] = useState<string | null>(null);
```

**Lógica de consumo SSE:**

```tsx
const enviarMensagem = async (texto: string) => {
  setStatusTexto("Aguardando agente...");
  
  const response = await fetch("/agentes/datastage/conversar/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders },
    body: JSON.stringify({ mensagem: texto, conversa_id: conversaId }),
  });

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const linhas = decoder.decode(value).split("\n");
    for (const linha of linhas) {
      if (!linha.startsWith("data: ")) continue;
      const evento = JSON.parse(linha.slice(6));
      if (evento.tipo === "status") {
        setStatusTexto(evento.texto);
      } else if (evento.tipo === "resposta") {
        setStatusTexto(null);
        // processar resposta final normalmente
        tratarResposta(evento);
      } else if (evento.tipo === "erro") {
        setStatusTexto(null);
        tratarErro(evento.detalhe);
      }
    }
  }
};
```

**Exibição no componente:**

```tsx
{statusTexto && (
  <div className="flex items-center gap-2 text-sm text-dim animate-pulse">
    <Spinner size={14} />
    {statusTexto}
  </div>
)}
```

O spinner atual "Mapeamento DataStage..." é substituído por este componente dinâmico.

---

### Item D — Duração visível na resposta

O backend já calcula e inclui `duracao_ms` no payload de resposta (campo presente no evento
`tipo: "resposta"` do SSE e também no JSON do endpoint atual). O front deve exibir esse valor
formatado abaixo de cada resposta do agente.

**Formato sugerido:**

```
respondido em 4s        (< 10s)
respondido em 42s       (>= 10s, < 120s)
respondido em 2min 15s  (>= 120s)
```

**Implementação frontend:**

```tsx
function formatarDuracao(ms: number): string {
  const s = Math.round(ms / 1000);
  if (s < 120) return `respondido em ${s}s`;
  return `respondido em ${Math.floor(s / 60)}min ${s % 60}s`;
}

// Abaixo de cada balão de resposta do agente:
<span className="text-[11px] text-dim mt-1">
  {formatarDuracao(mensagem.duracao_ms)}
</span>
```

**Objetivo:** o usuário calibra a expectativa para as próximas perguntas. Uma pergunta que
levou 45s com `isx_extrair` vai levar um tempo similar na próxima — ver o histórico de
durações ajuda a decidir quando perguntar algo simples vs. algo que vai esperar.

---

## O que NÃO muda

- Autenticação: mesma lógica de `x-api-key` / `agentes_gateway_campo_usuario`
- RBAC: `require_agente` continua guardando o endpoint SSE da mesma forma
- Endpoint atual (`POST /agentes/datastage/conversar`): mantido para compatibilidade — o SSE
  é um endpoint novo, não substitui o atual imediatamente
- Lógica de `conversar()` em `agentes.py`: o `emit_status` é um parâmetro opcional com
  default `None` — sem SSE, o comportamento é idêntico ao atual, zero regressão
- Banco de dados: nenhuma migração necessária

---

## Arquivos a alterar

| Arquivo | O que muda |
|---|---|
| `api/routers/agentes.py` | Novo endpoint `POST /agentes/datastage/conversar/stream` com `StreamingResponse` |
| `api/services/agentes.py` | `conversar()` recebe `emit_status=None`; pontos de emissão nas chamadas de ferramenta |
| `nginx.conf` (container `airflow-ui`) | `proxy_buffering off` + `proxy_read_timeout 120s` no location do `/stream` |
| Componente da tela Agentes (frontend) | Hook de envio usa SSE; estado `statusTexto`; exibe duração por resposta |

---

## Contexto de deploy

As mudanças de backend (`agentes.py`, `routers/agentes.py`) seguem o mesmo fluxo das
correções já feitas nesta sessão: editar em `/opt/airflow/api/`, `docker cp` para o container
`orquestra-api`, restart.

O frontend requer rebuild do React e redeploy do container `airflow-ui` — coordenar com o
time de front.

---

## Alterações já feitas nesta sessão (para o dev puxar junto)

> **✅ Portadas para o repositório em 23/09/2026** (PR da F6, #427), sobre o código das F4–F6 — a branch
> `feat/agente-datastage-melhorias` não é mergeada: ela partiu de uma base antiga e traria de volta a versão
> da F3 de `agentes.py` e o "sync de produção" de 27/08. No port: o prompt foi mesclado com o que a F5/F6
> acrescentaram (fatos, propostas, aprendizados); `_resolver_matriculas` passou a ignorar a caixa da
> matrícula, a não gerar "None (MAT)" com nome em branco e a nunca derrubar a extração se a consulta falhar;
> a mudança de modo do `isx_engine.py` (644 → 755) não foi trazida. O Item A (SSE) e o Item D (duração)
> desta spec vão numa PR própria.

As seguintes mudanças foram feitas diretamente nos containers em produção e precisam ser
portadas para o repositório antes do próximo deploy:

### `api/services/agentes.py`
- `_prompt_sistema()`: reescrito com instruções de raciocínio, armadilhas de pasta, diferença
  SEQUENCE vs PARALLEL, interpretação de `children` (job_name vs activity), orientações de
  resposta ao usuário
- `_limpar_children()`: nova função — remove `CJobActivity` dos stages e o campo `activity`
  dos children antes de serializar para o modelo
- `_resolver_matriculas()`: nova função — enriquece `created_by`/`modified_by` com nome
  completo do usuário quando a matrícula existe em `etl_usuario`
- `_isx_extrair()`: chama `_limpar_children()` e `_resolver_matriculas()` antes de serializar

### `dags/utils/isx_engine.py`
- `_API_CAMINHO_RE` (linha 59): adicionado `+` ao charset — corrige BFS que não atravessava
  pastas cujo nome contém espaço (ex: `04. ODS`, `00. ControleCarga`) porque a API REST do
  DataStage codifica espaços como `+` nos campos `id`/`$ref` que devolve
