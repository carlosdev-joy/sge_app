# Spec: Tela Admin — Gerenciamento de Agentes

**Data:** 2026-09-23  
**Contexto:** Hoje qualquer ajuste de prompt requer editar código + docker cp + restart do container.
A tela de Admin deve permitir criar agentes, configurar acesso e editar o prompt sem deploy.  
**Prioridade:** Alta — elimina ciclo deploy/restart para evolução contínua dos agentes

---

> **📋 RASCUNHO — trazido para o repo em 23/09/2026** (commit `c7cff0f` da branch `feat/agente-datastage-melhorias`).
> Nada disto está implementado. Antes de implementar, decidir os pontos em que esta spec conflita com o que as
> F1–F6 de `docs/spec-agentes-datastage.md` já decidiram e entregaram:
>
> 1. **Acesso `tela_padrao` / `perfil`** — o agente **DataStage** é, por decisão do usuário (21/09, 3ª–5ª rodadas),
>    **só por concessão manual, usuário a usuário, e só para o perfil `desenvolvedor`**; `require_agente` ignora de
>    propósito o recurso vindo de perfil (risco 26). Os modos novos só podem valer para **agentes futuros** — o
>    catálogo/migração inicial não pode abrir o `datastage` por perfil ou para a tela inteira.
> 2. **"Nova seção Admin › Agentes"** — a seção **já existe** (F3/F6: interruptores, gateway, limites, "Quem pode
>    usar" e "Curadores"). A tela proposta deve **estender** a `AgentesTab.tsx`, não criar outra.
> 3. **`prompt_sistema` editável substituindo o do código** — o prompt carrega as regras das F5/F6 (propostas com
>    evidência literal, aprendizados, blocos `<ferramenta>`/`<aprendizados>` delimitados, projeto antes de consultar).
>    O backend continua impondo as travas (allowlist, projeto validado, régua de proposta), mas um prompt editado sem
>    essas seções quebraria propostas/aprendizados em silêncio. Separar a parte **editável** (instruções do domínio)
>    da parte **fixa** montada pelo código — inclusive a lista de comandos do `dsjob` (`{comandos}`), gerada da
>    allowlist (anti-drift).
> 4. **Ferramentas por agente (`ferramentas_json`)** — a allowlist é **em código** e "ferramenta nova só por PR"
>    (B-02, risco 24); a config pode só **restringir** o conjunto, nunca ampliar.
> 5. **Migration `XXXX`** — a próxima livre é a **120** (116–119 já usadas pelos agentes); T-SQL idempotente.
> 6. **Interruptores duplicados** — `enabled` por agente como "nível adicional" daria três chaves para o DataStage
>    (`agentes_enabled`, `agente_datastage_enabled`, `enabled`); o kill switch da F3 e o 503 `agente_desligado` (chat e
>    curadoria) só olham as antigas. Decidir qual manda ou migrar. Idem `curador_enabled`: `require_agente(curador=True)`
>    e a curadoria exigem o grant `agente_curador` e não conhecem esse flag.
> 7. **Agente criado pelo banco não funciona sozinho** — o `CATALOGO` e as dependências `require_agente(...)` (montadas
>    no carregamento do módulo), `agente_do_recurso`/`elegivel_por_perfil` (validação do grant em `user_perm_set`), a rota
>    `/agentes/datastage/conversar` e a orquestração (ferramentas, projeto, prompt) são por código e específicos do
>    DataStage; o `RBAC_RECURSOS` do `Admin.tsx` é a 2ª lista à mão; permissão nova exige relogin. Um agente só no banco
>    apareceria no catálogo sem endpoint, sem ferramentas e sem recurso concedível — a spec precisa dizer como ele conversa.
> 8. **Cache de 60 s por processo** — com mais de um worker da API, cada um invalida o próprio cache; o `PUT` só
>    limpa o do worker que o atendeu (os outros levam até 60 s).

## Problema

O catálogo de agentes e os prompts estão hardcoded em `api/services/agentes.py`. Cada ajuste exige:
1. Editar o arquivo Python
2. `docker cp` para o container
3. `docker restart orquestra-api`
4. Verificar que o container voltou

Isso é impraticável para evolução contínua — prompts precisam de ajuste fino frequente, e novos
agentes deveriam poder ser criados sem envolver o time de dev a cada iteração.

---

## O que muda

### Modelo de dados

**Nova tabela `etl_agente_config`:**

```sql
CREATE TABLE dbo.etl_agente_config (
    id               INT IDENTITY PRIMARY KEY,
    agente_id        VARCHAR(50)  NOT NULL UNIQUE,  -- ex: 'datastage', 'qualidade'
    nome             VARCHAR(100) NOT NULL,
    descricao        VARCHAR(500) NOT NULL,

    -- Controle de acesso
    acesso           VARCHAR(20)  NOT NULL DEFAULT 'manual_por_usuario',
    -- 'manual_por_usuario': só quem o admin liberar individualmente (modelo atual)
    -- 'tela_padrao': qualquer usuário com acesso à tela de Agentes
    -- 'perfil': qualquer usuário com o perfil listado em perfis_elegiveis

    perfis_elegiveis VARCHAR(200) NULL,
    -- JSON array de perfis, ex: '["desenvolvedor"]'
    -- Usado apenas quando acesso = 'perfil'

    -- Flags de habilitação (espelham etl_app_config, mas por agente)
    enabled          BIT          NOT NULL DEFAULT 0,
    curador_enabled  BIT          NOT NULL DEFAULT 0,

    -- Prompt e ferramentas
    prompt_sistema   NVARCHAR(MAX) NULL,
    -- Quando NULL: o backend usa o prompt hardcoded (compatibilidade)
    -- Quando preenchido: substitui o hardcoded

    ferramentas_json NVARCHAR(MAX) NULL,
    -- JSON array das ferramentas disponíveis para o agente
    -- NULL = todas as ferramentas da allowlist padrão

    -- Auditoria
    criado_em        DATETIME     NOT NULL DEFAULT GETDATE(),
    criado_por       VARCHAR(20)  NULL,
    atualizado_em    DATETIME     NOT NULL DEFAULT GETDATE(),
    atualizado_por   VARCHAR(20)  NULL,
)
```

**Migração inicial:** popular com o agente `datastage` existente (prompt atual como valor padrão).

---

### Backend (`api/`)

#### Carregamento do prompt com cache

Em `agentes.py`, `_prompt_sistema()` passa a ler do banco com cache de 60s:

```python
_prompt_cache: dict[str, tuple[str, float]] = {}  # agente_id → (prompt, expira_em)
_PROMPT_CACHE_TTL = 60  # segundos

def _prompt_sistema(agente_id: str, projeto: str | None, ...) -> str:
    agora = time.monotonic()
    if agente_id in _prompt_cache:
        prompt_db, expira = _prompt_cache[agente_id]
        if agora < expira:
            return _montar_prompt(prompt_db, projeto, ...)
    # cache miss ou expirado — lê do banco
    try:
        prompt_db = _com_cursor(abrir_conn, lambda cur: _ler_prompt_db(cur, agente_id))
    except Exception:
        prompt_db = None  # fallback para hardcoded
    _prompt_cache[agente_id] = (prompt_db, agora + _PROMPT_CACHE_TTL)
    return _montar_prompt(prompt_db, projeto, ...)
```

O `_montar_prompt()` injeta as seções dinâmicas (projeto resolvido, aprendizados, ferramentas
disponíveis) no prompt base lido do banco — ou usa o hardcoded se `prompt_db` for `None`.

#### Novos endpoints (`api/routers/admin_agentes.py`)

```
GET    /admin/agentes                    → lista todos os agentes (catálogo)
POST   /admin/agentes                    → cria novo agente
GET    /admin/agentes/{agente_id}        → detalhes + prompt atual
PUT    /admin/agentes/{agente_id}        → atualiza nome, acesso, perfis, prompt, enabled
DELETE /admin/agentes/{agente_id}        → desativa (soft delete — enabled=0, não apaga)
```

Todos os endpoints exigem `acao_admin`. O `PUT` invalida o cache do prompt imediatamente
(remove a entrada de `_prompt_cache`) para que a próxima rodada já use o novo prompt — sem
restart.

**Payload `PUT /admin/agentes/{agente_id}`:**
```json
{
  "nome": "Mapeamento DataStage",
  "descricao": "Explica fluxos DataStage...",
  "acesso": "manual_por_usuario",
  "perfis_elegiveis": ["desenvolvedor"],
  "enabled": true,
  "curador_enabled": false,
  "prompt_sistema": "Você é o agente de mapeamento...",
  "ferramentas_json": null
}
```

#### Catálogo híbrido

O catálogo em `CATALOGO` (hardcoded) continua existindo como **fallback** para agentes que ainda
não migraram para o banco. Na inicialização, `catalogo_do_usuario()` mescla os dois:
banco tem prioridade sobre hardcoded quando `agente_id` coincide.

---

### Frontend (tela Admin)

Nova seção **Admin › Agentes** com duas sub-telas:

#### Lista de agentes

| Campo | Descrição |
|---|---|
| Nome | Nome exibido na tela de Agentes |
| ID | Identificador interno (slug) |
| Acesso | `Manual`, `Tela padrão` ou `Por perfil` |
| Habilitado | Toggle liga/desliga |
| Ações | Editar / Desativar |

Botão **+ Novo Agente** abre o formulário de criação.

#### Formulário de criação / edição

```
┌─────────────────────────────────────────────────────────┐
│ Nome do agente          [________________________]       │
│ ID (slug)               [________________________]       │  ← somente na criação
│ Descrição               [________________________]       │
│                                                         │
│ Controle de acesso                                      │
│  ○ Manual por usuário  (admin libera um a um)           │
│  ○ Tela padrão         (qualquer usuário com a tela)    │
│  ○ Por perfil          [desenvolvedor ▼]                │
│                                                         │
│ Habilitado   [●]    Curador habilitado   [○]            │
│                                                         │
│ Prompt do sistema                                       │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ Você é o agente de mapeamento de processos...       │ │
│ │                                                     │ │
│ │ (textarea editável, fonte monospace, ~20 linhas)    │ │
│ └─────────────────────────────────────────────────────┘ │
│ ℹ️ Alterações no prompt têm efeito imediato (sem restart)│
│                                                         │
│ Ferramentas disponíveis                                 │
│  ☑ resolver_projeto  ☑ base  ☑ dsx_consulta            │
│  ☑ dsjob             ☑ isx_extrair                     │
│                                                         │
│              [Cancelar]  [Salvar alterações]            │
└─────────────────────────────────────────────────────────┘
```

O botão **Salvar** chama `PUT /admin/agentes/{id}` e exibe confirmação inline.
Não requer reload da página.

---

## Regras de acesso ao novo agente criado via Admin

Quando `acesso = 'tela_padrao'`: qualquer usuário que tenha `tela_agentes` na sua permissão
de tela já vê e usa o agente — sem grant individual.

Quando `acesso = 'perfil'`: qualquer usuário com o perfil listado em `perfis_elegiveis` vê e usa
— sem grant individual.

Quando `acesso = 'manual_por_usuario'` (padrão): segue o fluxo atual — admin libera
usuário a usuário pela tela de permissões.

---

## O que NÃO muda

- Autenticação e RBAC por agente: `require_agente()` continua funcionando
- Endpoints existentes de conversa (`POST /agentes/datastage/conversar`) — inalterados
- Agentes hardcoded continuam funcionando enquanto não forem migrados para o banco
- Tabela `etl_app_config`: `agentes_enabled` e `agente_datastage_enabled` continuam
  existindo como interruptores globais; a nova `enabled` por agente é um nível adicional

---

## Arquivos a criar / alterar

| Arquivo | O que muda |
|---|---|
| `migrations/XXXX_etl_agente_config.sql` | DDL da nova tabela + INSERT do agente datastage |
| `api/routers/admin_agentes.py` | Novos endpoints CRUD de agentes |
| `api/services/agentes.py` | `_prompt_sistema()` lê do banco com cache; catálogo híbrido; invalidação de cache no PUT |
| `api/main.py` | Registra o novo router |
| Frontend (Admin › Agentes) | Lista + formulário de criação/edição |

---

## Ordem de implementação sugerida

1. Migration SQL + popular com agente datastage existente
2. Endpoints de leitura (`GET /admin/agentes` e `GET /admin/agentes/{id}`) — sem ainda alterar o catálogo
3. `_prompt_sistema()` com leitura do banco + cache (com fallback hardcoded)
4. Endpoint `PUT` + invalidação de cache — neste ponto já é possível editar o prompt pela API sem restart
5. Endpoint `POST` (criação de novo agente) + catálogo híbrido
6. Frontend: lista → formulário → toggle enabled
7. Endpoint `DELETE` (soft delete)
