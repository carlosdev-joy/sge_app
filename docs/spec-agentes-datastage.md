# Spec: Agentes de IA (tela `/agentes`) — agente de mapeamento DataStage — Orquestra
Data: 2026-09-21 · Status: **rascunho — aguardando a validação das dúvidas do §8 em produção**

> Origem: entrevista de descoberta de 2026-09-21 (skill `entrevista-projeto`), Entendimento do Projeto
> **confirmado pelo usuário**. Esta spec é autossuficiente: quem a lê (inclusive um agente rodando no
> servidor de produção, sem o contexto da conversa) encontra aqui o que foi decidido, o que ainda é
> dúvida e como fechar cada dúvida. **A implementação só começa depois que o usuário aprovar a spec.**

## 1. Visão

Engenheiros de dados gastam tempo para entender os fluxos DataStage que já existem (jobs, tabelas, campos,
lineage, parâmetros), lendo ISX/DSX ou o Designer na mão, e o que um descobre não fica registrado para o
próximo. A nova tela **Agentes** (`/agentes`) deixa cada usuário conversar com os agentes que lhe foram
liberados. O primeiro agente **lê o servidor DataStage (somente leitura) e a base do Orquestra**, explica o
fluxo e mostra o grafo, e **vai registrando** o que descobre (fatos) e o que aprende sobre como acessar o
servidor, buscar a informação e ler os jobs — para consultar a base antes do servidor e não repetir erro.
Cada usuário é identificado no gateway de IA da Caixa por `cvp-<matrícula>`, e o gateway decide se ele pode usar.

## 2. Escopo

**IN**
- Tela **Agentes** aberta a todo usuário logado (`tela_agentes`), com **seletor mostrando só os agentes liberados
  para aquele usuário** (RBAC por usuário × agente). Primeiro agente: **mapeamento de processos DataStage**.
- Chat em texto, **grafo do fluxo** (reaproveita o componente da Governança) e **links** para telas do Orquestra.
- **Leitura ao vivo somente leitura** no DataStage, pela API do Orquestra (`DS_SSH_*`), com **base primeiro**:
  o servidor só é consultado quando a base não tem o dado ou ele venceu.
- **Fatos** lidos por ferramenta são gravados direto, com origem e evidência. **Interpretações** do modelo viram
  **proposta**: o usuário na conversa aprova ou recusa; sem aprovação ficam só os fatos.
- **Base de aprendizados** (como acessar, buscar, ler jobs, detalhar; erros e correções): fatos comprovados valem
  na hora; **interpretações só depois de aprovação de um curador**. Recuperada por relevância, com semente inicial.
- **Histórico de conversas**: todas salvas por usuário; lista com busca; **retomar conversa de até 30 dias**.
- **Identidade no gateway**: `cvp-<matrícula>` da sessão; aviso na tela quando o usuário não está cadastrado no
  gateway (detectado por uma chamada mínima ao abrir a tela); "gateway indisponível" tratado como caso distinto.
- Interruptores liga/desliga (geral e por agente), **nascem desligados**; config no Admin.

**OUT (explícito)**
- Executar, reexecutar ou parar jobs; escrever no repositório do DataStage.
- **Extração ISX disparada pelo agente** (ela cria arquivo temporário no servidor). No v1 o agente aponta o link
  da Governança para o usuário extrair — decisão **B-02**.
- **Logs de execução** (`logsum`/`logdetail`) como ferramenta do agente (podem conter valores de dados) — **B-03**.
- Exportar documentação (Markdown/PDF); outros agentes (entra só a estrutura de catálogo); autenticação nova.
- O Orquestra **cadastrar** o usuário no gateway (ele só avisa).
- Gravar conclusão do modelo sem aprovação.
- **Medir ou limitar tokens** (nenhum contador, cota ou meta de tokens no Orquestra).
- Streaming da resposta; apagar a própria conversa (**B-04**).
- Alterar a identidade dos outros consumidores do gateway: Caixa Seguro e triagem de chamados **continuam
  com `cvp-orquestra`**.

**Backlog (fora desta spec):** ler o que entra e o que sai das conversas para gerar novas funcionalidades
(como a fila de "pedidos não atendidos" do Maestro). Exige política antes — **B-07**.

## 3. Arquitetura proposta

### Front (`ui-react/`)
- `src/lib/nav.ts`: `NavGroup` ganha `'Agentes'`; `NAV_GROUPS` recebe `'Agentes'` **imediatamente antes de
  `'Administração'`** (não reordena nada existente — regra de não mudar a ordem da tela; **B-01**); item
  `{ to: '/agentes', label: 'Agentes', icon: Bot, group: 'Agentes', perm: 'tela_agentes' }`.
- `src/App.tsx`: `PAGE_ELEMENT['/agentes']`. Sem subrotas: agente e conversa vão em query (`?agente=&conversa=`).
- `src/pages/Agentes.tsx` + `src/components/agentes/` (seletor, chat, aviso de cadastro, histórico, cartão de
  proposta, aba do curador, grafo inline) + `src/lib/agentes.ts` (constantes/tipos/helpers, no estilo de
  `lib/maestro.ts`). O chat segue os padrões de `components/etapas/MaestroChat.tsx` (referência, sem refatorar o Maestro).
- Grafo: reaproveita `components/governanca/isx/GrafoIsx.tsx` / `PainelJobIsx.tsx`, alimentado por
  `GET /lineage/isx/job` (só banco). **C-02** confere as props na F3.
- Admin: `pages/Admin.tsx` — `RBAC_RECURSOS` (linha ~36, a **2ª lista à mão**) ganha `tela_agentes`,
  `agente_datastage`, `agente_curador`; nova aba `components/admin/AgentesTab.tsx` (no molde de `MaestroTab.tsx`).
- Visual: tokens neutros do Orquestra (`canvas/panel/edge/ink`, claro e escuro), sem tema CAIXA. `dist/` recompilada
  em toda fase com front.

### Back (`api/`)
- `api/routers/agentes.py` (novo; registrado nas **duas** listas de `api/main.py`):

  | Método e rota | Guard | Função |
  |---|---|---|
  | `GET /agentes/catalogo` | `require_perm('tela_agentes')` | agentes que o usuário pode usar (catálogo em código ∩ permissões do usuário ∩ interruptor) |
  | `GET /agentes/status?agente=` | `tela_agentes` | estado do gateway para o usuário (sonda, com cache) |
  | `POST /agentes/datastage/conversar` | `require_perm('agente_datastage')` | uma rodada (orquestrada) |
  | `GET /agentes/conversas`, `GET /agentes/conversas/{id}` | `tela_agentes` + dono | histórico (só do próprio usuário; `404` se não for o dono) |
  | `POST /agentes/propostas/{id}/decidir` | dono da conversa | aprovar/recusar proposta |
  | `GET /agentes/aprendizados`, `POST /agentes/aprendizados/{id}/decidir` | `require_perm('agente_curador')` | fila do curador |
  | `GET/POST /agentes/admin/config` | `get_admin_user` | interruptores, campo do gateway, texto de cadastro, teto SSH, validade |

- `api/services/agentes.py` (catálogo em código, prompt, orquestração da rodada, identidade), 
  `api/services/agentes_ferramentas.py` (ferramentas e allowlist), `api/services/agentes_conhecimento.py`
  (fatos, propostas, aprendizados, filtro de segredos). Módulos planos, como `maestro.py`.
- `api/services/caixa_ia.py` **estendido, sem quebrar os outros consumidores**: `chat_conversa(..., identidade=None)`,
  `_chat_caixa_gateway(..., identidade)` e `sondar_usuario()`. Sem `identidade` o corpo e os headers ficam
  **idênticos aos de hoje** (Caixa Seguro e triagem intactos). Hoje o código trata 401/403 como "chave recusada" e
  devolve 502; no caminho do agente o recusa vira um tipo próprio (`GatewayRecusou`) para separar *usuário sem
  cadastro* de *chave do app inválida*.
- **Sem tool-calling nativo.** O gateway recebe **uma única mensagem `user`** (`_corpo_gateway`; o histórico vai
  transcrito por `transcrever`), então o "agente" é **orquestrado pelo backend**: o modelo pede uma ferramenta num
  bloco ` ```json ` (mesmo padrão do Maestro), o backend **valida contra a allowlist**, executa, e devolve o
  resultado ao modelo como **dado delimitado**. No máximo 3 rodadas de ferramenta por pergunta e um **orçamento
  de tempo** (não só de quantidade — lição da triagem de chamados).
- **Ferramentas do v1:** (1) `base`: lê `etl_ds_job_isx` (cabeçalho, parâmetros, fluxo, filhos), `etl_job_lineage`
  (`isx_auto`) e `etl_agente_fato`; (2) `dsjob`: **`ljobs`, `lstages`, `lparams`, `jobinfo`, `report`** via
  `ssh_datastage.run_dsjob` (nomes validados por `^[A-Za-z0-9_.]+$`; **fora**: `logsum`, `logdetail`); (3) SFTP de leitura
  (`ssh_arquivos`) **só se D-11 justificar** (padrão: fora do v1).
- **Identidade:** `identidade_gateway(matricula)` = `cvp-` + matrícula em minúsculas, **sempre da sessão**
  (`get_current_user`), nunca do corpo. Matrícula ausente ou fora do padrão ⇒ **não chama o gateway** e **nunca
  cai para `cvp-orquestra`** (isso faria todos agirem como o app e anularia a autorização por usuário).
  O local do identificador na requisição (header ou corpo, nome do campo) é **configuração** até o contrato
  ser validado (**D-01**); sem ela, estado `sem_contrato` (agente desligado, sem chute).
- **Sonda de cadastro** (`GET /agentes/status`): chamada mínima ao gateway com o `cvp-<matrícula>`. Se voltar
  401/403, faz **uma chamada de controle com a identidade do app** (`cvp-orquestra`): controle OK ⇒ o usuário
  não está cadastrado; controle também falha ⇒ problema da chave do app/gateway, **não** do usuário.
  Estados: `ok`, `sem_cadastro`, `gateway_indisponivel`, `chave_do_app_invalida`, `sem_contrato`, `desligado`,
  `provedor_incompativel` (o agente exige o provedor `caixa_gateway`), `matricula_fora_do_padrao`. Cache por
  matrícula em memória: `ok` 10 min, `sem_cadastro` 60 s (a pessoa se cadastra e o botão "verificar de novo"
  funciona), `gateway_indisponivel` não é cacheado. Os TTLs finais dependem de **D-03**.
- Erros no formato `detail: {code, message}` (como `maestro_corpo_invalido`); o front decide pelo `code`, não pelo
  texto — o contrato `err.status` × `err.message` do `apiFetch` já causou bug.
- Purga por **DAG** em `dags/etl_log_cleanup.py` (nova tarefa `limpar_conversas_agentes`, retenção de 30 dias
  espelhada em `services/agentes.RETENCAO_CONVERSAS_DIAS`). Lá o placeholder é `%s` (pymssql); na API é `?` (pyodbc).
  A janela de 30 dias **também é imposta na leitura** (o `SELECT` filtra), então a regra vale mesmo que o `dags/`
  não seja sincronizado.

### Dados
Migration `sql/migrations/116_agentes.sql` (§4). Lê `etl_ds_job_isx`, `etl_job_lineage`; reaproveita
`etl_usuario_permissao` (RBAC por usuário) e `etl_app_config` (interruptores, config). Provedor de IA: **`caixa_gateway`**
já configurado em Admin › Caixa Seguro IA; o modelo é o configurado ali (a spec não fixa modelo nem custo).

### Decisões e alternativas descartadas
- **Catálogo de agentes em código** (registro), não em tabela — descartado `etl_agente`: sem CRUD nem valor hoje.
- **Orquestração no backend** — descartado depender de `tools` do gateway (não confirmado) e descartado delegar a
  leitura ao Airflow (decisão do usuário: API do Orquestra direto, `DS_SSH_*`; síncrono e já existente).
- **RBAC por usuário em `etl_usuario_permissao`** (recursos `agente_*`) — descartada tabela própria agente×usuário:
  reaproveita a UI de grants e a invalidação de sessão. **Nenhum `agente_*` é semeado em perfil nenhum, nem no admin**:
  só concessão explícita por usuário.
- **Fatos em tabela própria** `etl_agente_fato`, não em `etl_job_lineage` — `etl_ds_job_isx` tem FK para
  `etl_pipeline_job` (o lineage ISX só existe para job que está num pipeline do Orquestra), então job fora de pipeline
  não cabe ali; e misturar dado do agente no lineage contaminaria o grafo da Governança.
- **Corpo de aprendizado de `erro`/`acesso` gerado por código** (modelo `ferramenta + saída-assinatura`), nunca texto
  livre vindo da saída da ferramenta — fecha a injeção persistente. Texto livre só em `interpretacao` (passa pelo curador).
- **Validade do dado:** ISX por `ds_last_modified` (a chave de cache que já existe); `dsjob`/SFTP por **prazo**
  (padrão 7 dias), porque `dsjob` talvez não exponha data de modificação (**D-08**).
- **Retomada de conversa:** reenvia as últimas 12 rodadas (teto do Maestro), sem guardar resumo.
- **Resposta única, sem streaming** (o Maestro também é assim; o gateway não confirmou suporte).

## 4. Modelo de dados

Migration `116_agentes.sql` — **idempotente** (`IF OBJECT_ID(...) IS NULL` / `IF NOT EXISTS`, roda 2×), aplicada na
**etapa 6c** do `scripts/deploy.sh` (responder **s**). Sem migration: a tela avisa e nada quebra (padrão da 110).
Larguras seguem a origem: `matricula VARCHAR(20)` (= `etl_usuario.matricula`), `ds_project NVARCHAR(50)`,
`job_name`/`pipeline_name NVARCHAR(200)`. `NVARCHAR(n)` conta UTF-16: cortar com `cortar_utf16`.

| Tabela | Colunas principais | Notas |
|---|---|---|
| `etl_agente_conversa` | `conversa_id VARCHAR(36) PK` (gerado no servidor), `agente VARCHAR(40)`, `matricula VARCHAR(20)`, `titulo NVARCHAR(200)`, `criada_em`, `ultima_msg_em DATETIME2(0)` | índice `(matricula, ultima_msg_em DESC)` e `(ultima_msg_em)` p/ purga |
| `etl_agente_mensagem` | `id BIGINT IDENTITY PK`, `conversa_id FK ON DELETE CASCADE`, `papel VARCHAR(10)`, `conteudo NVARCHAR(MAX)` (**já redigido**), `status VARCHAR(20)`, `artefatos_json NVARCHAR(MAX) NULL` (ferramentas executadas [nome, args, exit, ms], grafo, links, ids de proposta), `criada_em` | índice `(conversa_id, criada_em)` |
| `etl_agente_fato` | `id BIGINT IDENTITY PK`, `ds_project`, `job_name`, `pipeline_name NULL`, `tipo VARCHAR(20)` (stage/parametro/tabela/campo/lineage/descricao), `chave NVARCHAR(300)`, `valor_json NVARCHAR(MAX)`, `origem VARCHAR(30)` (dsjob_lstages/dsjob_lparams/dsjob_report/sftp/interpretacao_aprovada), `evidencia NVARCHAR(MAX)` (autocontida, filtrada), `ds_last_modified VARCHAR(40) NULL`, `lido_em`, `lido_por VARCHAR(20)`, `aprovado_por VARCHAR(20) NULL`, `aprovado_em NULL`, `obsoleto_em NULL` | upsert idempotente; índice `(ds_project, job_name, tipo)` |
| `etl_agente_proposta` | `id BIGINT IDENTITY PK`, `conversa_id VARCHAR(36)` (**sem FK**: sobrevive à purga), `agente`, `matricula VARCHAR(20)`, `ds_project`, `job_name`, `tipo`, `chave`, `valor_json`, `evidencia`, `motivo NVARCHAR(600)`, `estado VARCHAR(12)` (pendente/aprovada/recusada/expirada), `criada_em`, `decidida_por`, `decidida_em`, `fato_id NULL` | decisão idempotente (`UPDATE … WHERE estado='pendente'` + rowcount) |
| `etl_agente_aprendizado` | `id`, `agente VARCHAR(40)`, `tipo VARCHAR(20)` (acesso/busca/leitura/detalhamento/erro), `assinatura CHAR(64)` (sha256 da chave normalizada), `titulo NVARCHAR(200)`, `corpo NVARCHAR(2000)`, `evidencia NVARCHAR(MAX)`, `origem VARCHAR(20)` (ferramenta/interpretacao/semente), `estado VARCHAR(12)` (rascunho/validado/obsoleto/rejeitado), `criado_em`, `validado_por`, `validado_em`, `ultimo_uso_em`, `usos INT`, `revalidar_em NULL` | `UNIQUE (agente, assinatura)` dedupa e incrementa `usos`; índice `(agente, estado, tipo)` |

**Sem FK das tabelas derivadas (proposta, fato, aprendizado) para a conversa**, e evidência autocontida (comando +
trecho filtrado da saída): a purga de 30 dias não pode apagar o que precisa durar (aprovações com matrícula e hora,
fatos, aprendizados).

**Seeds da 116** (padrão da 060/110): `MERGE` de `tela_agentes` em `etl_perfil_permissao` para **todos os perfis
existentes** (conferir quais são em produção — **D-13**); `etl_app_config`: `agentes_enabled='0'`,
`agente_datastage_enabled='0'` (colunas `config_key, config_value, descricao, updated_by, updated_at`).
Config sem migration (chaves em `etl_app_config`): `agentes_gateway_campo_usuario` (`header:NOME` | `body:CAMPO`),
`agentes_cadastro_texto`, `agentes_ssh_max` (padrão 10, configurável), `agentes_fato_validade_dias` (padrão 7).

## 5. Fases

Regras: cada fase = **1 PR**, mergeável sozinha, deixa a `main` funcional; **fases de UI em sequência** (a `dist/` é
commitada e gera conflito se duas fases mexerem no front). O merge é **sempre autorizado pelo usuário**. Sem
dependência Python nova prevista (`anthropic`, `httpx`, `paramiko` já existem) — nenhuma wheel nova em `api/wheels/`.

**Validação padrão de toda fase** (citada em cada uma como "padrão"): `cd ui-react && npx tsc -b` (**não** `--noEmit`,
que não checa nada aqui) e eslint **comparados com o HEAD** (zero erros novos) · `npm run build` com a `dist/` commitada ·
`pytest` comparado com o baseline do HEAD (falhas pré-existentes conhecidas; zero novas) · **revisão adversarial
multi-agente antes da PR** (`qa-adversarial`; `security-review` nas F1, F2, F5 e F6) · `/simplify` nas fases finais.

### F1 — Fundação: migration 116, RBAC por agente e gateway com identidade por usuário
- **Entregável:** backend sem UI nova; interruptores desligados. A `main` segue igual para quem não liga.
- **Inclui:** migration 116; catálogo em código; `caixa_ia` com `identidade`, `GatewayRecusou`, `sondar_usuario`
  (+ controle com a identidade do app); `identidade_gateway()`; `GET /agentes/catalogo`, `GET /agentes/status`,
  `GET/POST /agentes/admin/config`; recursos em `RBAC_RECURSOS` (`Admin.tsx`); testes; `dist/`.
- **Pré-requisito:** D-01, D-02, D-03, D-06, D-13 fechadas. Sem elas a F1 abre com a sonda em `sem_contrato`.
- **Critérios de aceite:**
  1. A 116 roda 2× sem erro; `tela_agentes` semeada em todos os perfis existentes; interruptores em `'0'`.
  2. Sem `tela_agentes` → 403; com a tela e sem `agente_datastage` → catálogo vazio; com grant por usuário
     (`user_perm_set`) → o agente aparece **depois do relogin**.
  3. `identidade_gateway('CVP1234') == 'cvp-cvp1234'`; matrícula vazia ou fora do padrão → **nenhuma chamada**
     ao gateway; teste que **falha** se existir fallback para `cvp-orquestra`.
  4. Sonda: 200 ⇒ `ok`; 401/403 do usuário + controle OK ⇒ `sem_cadastro`; 401/403 + controle falha ⇒
     `chave_do_app_invalida`; `ConnectError`/timeout/5xx ⇒ `gateway_indisponivel`; campo não configurado ⇒
     `sem_contrato` **sem** chamar; cache respeitado. (Regras finais conforme D-02/D-03.)
  5. **Não-regressão:** `_chat_caixa_gateway` sem `identidade` gera corpo e headers **idênticos** aos de hoje; testes
     existentes de `caixa_chat`/`caixa_ia`/triagem passam.
  6. Erros no formato `detail: {code, message}`.
- **Validação:** padrão. **PR:** `feat(agentes): fundação — migration 116, RBAC por agente e gateway com identidade por usuário (F1)`.

### F2 — Ferramentas de leitura e orquestração (backend)
- **Entregável:** `POST /agentes/datastage/conversar` funcionando por API, com persistência das mensagens; sem UI.
- **Inclui:** `agentes_ferramentas.py` (`base`, `dsjob` com a allowlist acima); régua do pedido de ferramenta
  (bloco JSON); orquestração (≤3 rodadas, orçamento de tempo abaixo do `proxy_read_timeout` — **D-14**); semáforo de
  sessões SSH com espera limitada; truncagem das saídas (`run_dsjob` devolve até 200 000 caracteres); `redigir()`
  de segredos; saída de ferramenta como **dado delimitado**; prompt gerado do vocabulário das ferramentas; base
  primeiro com validade (ISX por `ds_last_modified`; `dsjob` por prazo).
- **Pré-requisito:** D-04, D-07, D-08, D-09, D-14 fechadas.
- **Critérios de aceite:**
  1. Sem `agente_datastage` → 403; interruptor desligado → 503 **sem** chamar gateway nem servidor.
  2. Pedido fora da allowlist (`logdetail`, comando livre, `;` no nome do job) → recusado; teste com SSH dublê que
     **falha se for chamado**.
  3. Job com dado válido na base → **0 chamadas SSH** e a resposta informa a idade do dado; dado vencido → 1 leitura ao vivo.
  4. Valores canário (senha, token, valor de parâmetro Encrypted) **nunca** chegam ao modelo nem às mensagens gravadas.
  5. Com teto de N sessões, a N+1ª espera; passado o limite de espera → erro nomeado "servidor ocupado".
  6. O identificador enviado é o da **sessão**: `matricula` forjada no corpo é ignorada.
  7. Saída de ferramenta com "ignore as instruções…" entra como dado e **não** muda allowlist nem estado.
  8. Gateway lento (dublê) → resposta nomeada dentro do orçamento, não 504 do nginx.
- **Validação:** padrão. **PR:** `feat(agentes): ferramentas de leitura e orquestração do agente DataStage (F2)`.

### F3 — Tela `/agentes` (seletor, chat, aviso de cadastro, grafo, links) e Admin › Agentes
- **Entregável:** a tela visível para quem tem `tela_agentes`; agente utilizável para quem tem o grant.
- **Inclui:** `nav.ts`, `App.tsx`, `pages/Agentes.tsx`, componentes, `lib/agentes.ts`; `AgentesTab.tsx` (interruptores,
  campo do gateway, texto de cadastro, teto SSH, validade); grafo inline; links para a Governança (**C-01**); `dist/`.
- **Critérios de aceite:**
  1. Sem grant: a tela abre com estado vazio explicativo (não um 403 em branco); a chamada direta à API dá 403.
  2. Com grant: o seletor mostra **só** os agentes liberados.
  3. `sem_cadastro` mostra o aviso com o texto configurado; `gateway_indisponivel` mostra "gateway indisponível" e
     **nunca** o aviso de cadastro (teste de front por regex + teste de API pelos `code`).
  4. Chat com `aria-live="polite"`, foco gerenciado, contraste dos tokens em claro e escuro, **sem cor fixa**.
  5. O grafo abre reaproveitando `GrafoIsx`; os links levam ao job na Governança.
  6. CSS: sem `overflow-hidden` em ancestral de `sticky`; sem `*/` dentro de comentário CSS; overlays sem
     especificidade que pinte fundo (lições do Caixa Seguro).
- **Validação:** padrão. **PR:** `feat(agentes): tela /agentes com chat, aviso de cadastro, grafo e Admin › Agentes (F3)`.

### F4 — Histórico de conversas (30 dias)
- **Entregável:** lista, busca e retomada; purga.
- **Inclui:** `GET /agentes/conversas` (`?q=`) e `/{id}`; continuar conversa (as últimas 12 rodadas vão ao gateway);
  UI de histórico; tarefa `limpar_conversas_agentes` em `dags/etl_log_cleanup.py`; `LIKE` com `ESCAPE` para `%` e `_`;
  título por `cortar_utf16`.
- **Critérios de aceite:**
  1. Com 2 usuários, cada um lista e busca **só** as próprias; conversa alheia → 404 (sem oráculo).
  2. Conversa com 29 dias aparece e retoma; com 31 dias **não aparece, mesmo sem a purga** (filtro na leitura).
  3. Ao retomar, cada resposta antiga mostra a data e o dado passa pela checagem de validade.
  4. A purga apaga a conversa vencida e **não** apaga proposta, fato nem aprendizado (teste).
  5. Segredo canário digitado no chat não aparece em `etl_agente_mensagem`.
- **Validação:** padrão. **PR:** `feat(agentes): histórico de conversas com busca e retomada em até 30 dias (F4)`.

### F5 — Fatos gravados e propostas com aprovação
- **Entregável:** o agente grava o que a ferramenta leu; interpretações viram proposta aprovável.
- **Inclui:** gravação de fatos em `etl_agente_fato` (origem, evidência, `lido_em`, `ds_last_modified`); obsolescência
  ao detectar mudança; base primeiro usando os fatos; régua de proposta (tipo, chave, tamanhos, segredos);
  `etl_agente_proposta`; cartão "Aprovar / Recusar" **com a evidência ao lado**; `POST /agentes/propostas/{id}/decidir`.
- **Critérios de aceite:**
  1. Fato só é gravado com origem de ferramenta.
  2. Sem decisão, **0** linhas com origem `interpretacao_aprovada` (teste).
  3. Aprovar 2× gera 1 fato; outro usuário decidindo → 403/404; recusar não grava nada.
  4. Proposta com valor Encrypted ou padrão de segredo → rejeitada pela régua.
  5. A aprovação guarda `decidida_por` e `decidida_em` e sobrevive à purga da conversa.
- **Validação:** padrão. **PR:** `feat(agentes): fatos gravados por ferramenta e propostas com aprovação (F5)`.

### F6 — Base de aprendizados e tela do curador
- **Entregável:** o agente registra e reutiliza aprendizados; curador valida interpretações.
- **Inclui:** registro automático (erro/acesso/busca/leitura) com `assinatura`; corpo gerado por código; interpretação
  entra como `rascunho`; aba do curador (`agente_curador`): aprovar, rejeitar, marcar obsoleto; recuperação por
  relevância (**≤ 5 itens e ≤ 2 000 caracteres**, só `validado`); **guarda de reexecução** (a mesma ferramenta com os
  mesmos argumentos que falhou não roda 2× na conversa); semente inicial (D-12 + o que já se sabe: nome de job é
  case-sensitive, `DS_ISTOOL_AUTHFILE` aceita `~/`, allowlist do `dsjob`, raízes SFTP); `revalidar_em`.
- **Critérios de aceite:**
  1. 2ª ocorrência da mesma assinatura → **0 chamadas repetidas** e o aprendizado vai ao contexto (teste).
  2. O corpo de `erro`/`acesso` não contém texto livre da saída além da evidência filtrada (teste com canário de injeção).
  3. `rascunho` **nunca** entra no contexto do agente.
  4. Sem `agente_curador` → 403 nos endpoints de decisão; a aba nem aparece.
  5. Segredo canário não chega a aprendizado.
- **Validação:** padrão. **PR:** `feat(agentes): base de aprendizados, guarda de reexecução e tela do curador (F6)`.

### F7 — Fechamento: documentação, smoke e deploy
- **Entregável:** manual, release note, smoke e roteiro de deploy; memória viva e a cópia em `.claude/memory/`.
- **Inclui:** nova seção em `docs/MANUAL_USUARIO.md`; `docs/release-notes/agentes.md`; `scripts/smoke_agentes.py`
  (no estilo dos `scripts/smoke_*.py`); revisão adversarial geral + `security-review` + `/simplify`.
- **Deploy (o usuário faz):** etapa 6c **s** (116) · `dags/` **s** (a purga; é arquivo de DAG, **não** exige restart do
  worker) · API e `dist/` · `config/` responder **n** (o `nginx.conf` de produção está à frente do repo) · sem `.env` novo,
  sem wheel nova · depois ligar `agentes_enabled` e `agente_datastage_enabled` no Admin e conceder o grant aos usuários.
- **Critérios de aceite:** o smoke do §7 executado e conferido no ambiente real.
- **Validação:** padrão. **PR:** `docs(agentes): manual, release note e smoke de fechamento (F7)`.

## 6. Riscos e mitigações

| # | Risco | Impacto | Mitigação |
|---|-------|---------|-----------|
| 1 | **Falso verde na gravação:** conclusão do modelo vira dado "verdadeiro" no lineage | Decisão errada sobre fluxo em produção | Fato só de ferramenta; interpretação = proposta com aprovação; origem e evidência em toda linha; tabela própria (não toca o grafo da Governança) |
| 2 | **401/403 ambíguo:** o mesmo código serve a "usuário sem cadastro" e a "chave do app inválida" | Aviso de cadastro para quem só bateu numa falha, ou o contrário; chamados falsos | Chamada de **controle** com a identidade do app antes de concluir `sem_cadastro`; códigos separados; **D-02** confirma o que o gateway devolve |
| 3 | **Injeção persistente** via conteúdo de job/ISX/log guardado como aprendizado | Instrução escondida volta em toda conversa | Saída de ferramenta é dado delimitado; corpo de `erro`/`acesso` **gerado por código**; texto livre só passa pelo curador |
| 4 | **Aprendizado errado repetido** | O agente repete a falha para sempre | Evidência + estado + `revalidar_em`; interpretação só com curador; obsoleto/rejeitado saem do contexto |
| 5 | **Dado velho tratado como atual** | Resposta desatualizada sobre um job que mudou | ISX: `ds_last_modified`; `dsjob`: prazo; a resposta mostra a idade; botão "reler ao vivo"; retomada revalida |
| 6 | **Escalada de privilégio:** quem não tem `tela_ds_console` passa a ler o DataStage pelo agente | Acesso ao servidor por caminho novo | Grant **explícito por usuário** (nenhum `agente_*` semeado, nem no admin); allowlist mais estreita que a do Console; toda ferramenta executada fica em `artefatos_json` (auditável) |
| 7 | **Purga de 30 dias apaga o que precisa durar** | Perde aprovação, fato ou aprendizado | Sem FK das derivadas; evidência autocontida; teste na F4 |
| 8 | **Segredo digitado no chat ou lido pelo `dsjob`** (ex.: valor de parâmetro Encrypted) | Vazamento em conversa/log/aprendizado por 30 dias | `redigir()` antes de qualquer gravação e antes de ir ao modelo; canários nos testes; **D-07** mostra o que o `dsjob` realmente devolve |
| 9 | **Sobrecarga do servidor DataStage** (SSH por requisição, compartilhado com Console, Utilitários, lineage e DAGs) | Derrubar o acesso dos outros | Base primeiro; semáforo `agentes_ssh_max`; espera limitada; **D-09** dimensiona o teto |
| 10 | **Timeout de requisição** (nginx `proxy_read_timeout`; o repo tem 120 s numa location e 300 s noutra) | 504 em pergunta com 3 rodadas de ferramenta | Orçamento de tempo abaixo do timeout **de produção**; resposta nomeada; **D-14** |
| 11 | **Identidade errada:** matrícula gravada em MAIÚSCULAS (`auth.py:38`) × `cvp-…` minúsculo; ou fallback para `cvp-orquestra` | Falha de cadastro falsa, ou autorização anulada | Normalização fixa + teste; **proibido** fallback (teste que falha se existir); **D-01** confirma a caixa |
| 12 | **Permissão nova exige relogin** e `RBAC_RECURSOS` é uma 2ª lista à mão | "Concedi e o agente não aparece" | Recursos na lista do Admin na F1; smoke b) exige o relogin; mensagem no modal de grants |
| 13 | **`dist/` invisível ou em conflito** | PR que "não aparece" em produção | Rebuild em toda fase de UI; UI em sequência |
| 14 | **`dags/` não sincronizado** (a tarefa de purga não roda) | Conversas passam de 30 dias no banco | Janela imposta também na **leitura**; **D-15** verifica o estado do `dags/` em produção; smoke k) |
| 15 | **Aprovação sem leitura** (usuário clica "aprovar" no automático) | Interpretação errada vira fato | Evidência ao lado do botão; a aprovação registra matrícula e hora; a proposta mostra o que será gravado |

## 7. Smoke pós-deploy

a) **Sem grant:** usuário com `tela_agentes` e sem `agente_datastage` abre `/agentes` → estado vazio explicativo; `POST /agentes/datastage/conversar` direto → 403.
b) **Concessão:** admin concede `agente_datastage` ao usuário X (Admin › Usuários); **X faz logout e login** → o agente aparece no seletor.
c) **Gateway:** X **sem** cadastro no gateway → aviso com o texto configurado; após o cadastro e "verificar de novo" → `ok`. Derrubar o gateway (ou apontar a URL errada em homologação) → "gateway indisponível" e **não** o aviso de cadastro.
d) **Base primeiro:** perguntar sobre um job **com** ISX na base → resposta sem chamada ao servidor, com a idade do dado; sobre um job **sem** base → leitura ao vivo de `lstages`/`lparams` e o grafo/links quando houver ISX.
e) **Erro documentado:** pedir um job com o nome em caixa errada → erro nomeado e aprendizado registrado; repetir → o agente **não** repete o mesmo comando e usa o aprendizado.
f) **Proposta:** provocar uma interpretação → cartão com evidência → **Aprovar** grava o fato com `decidida_por`; **Recusar** não grava nada.
g) **Histórico:** buscar um termo de ontem; retomar a conversa e continuar; conferir que conversa com mais de 30 dias não aparece.
h) **Curador:** usuário com `agente_curador` vê a aba e valida um rascunho; usuário sem ele não vê a aba e leva 403 na API.
i) **Interruptor:** desligar `agente_datastage_enabled` → agente some do seletor; API 503; nenhuma chamada ao gateway.
j) **Concorrência:** 3 a 5 abas perguntando ao mesmo tempo sobre jobs sem base → o teto de sessões SSH é respeitado; Console DataStage segue respondendo.
k) **Purga:** no Airflow, `etl_log_cleanup` › `limpar_conversas_agentes` roda e apaga só o que passou de 30 dias.
l) **Segredo:** digitar um valor canário parecido com senha no chat → não aparece em `etl_agente_mensagem`; ver que a resposta também não o repete.
m) **Não-regressão:** Caixa Seguro (assistentes) e a triagem de chamados continuam usando `cvp-orquestra` e funcionando.

## 8. Dúvidas em aberto

> **Como fechar a spec:** o usuário entra em produção e pede a um agente (Claude Code no servidor, ou quem ele
> designar) que **valide e documente** cada dúvida abaixo. Quando todas as **bloqueantes** estiverem ✅ e os pontos de
> impacto atualizados, o status da spec passa a **aprovada** e a F1 pode começar.

### 8.0 Protocolo do agente validador
1. **Somente leitura.** Não alterar dados, configuração, DAGs nem arquivos de produção. As únicas chamadas de saída
   permitidas são as **sondas mínimas ao gateway** (D-01 a D-04) e a **leitura de 3 jobs** pelo `dsjob` da allowlist (D-07).
2. **Gateway:** usar a matrícula **do próprio usuário** (cadastrada). Para o caso "não cadastrado" e "chave inválida",
   **avisar o time do gateway antes** — tentativas com identidade inexistente podem virar alerta de segurança. Nunca
   registrar a chave de API.
3. **Redigir tudo** o que for documentado: nada de senha, token, chave, conteúdo de `authfile`, valor de parâmetro
   Encrypted nem matrícula de terceiros. Contagens em vez de listas; exemplos mascarados (`cvp-cvp****`).
4. **Onde registrar:** no campo **Resultado** de cada item, neste arquivo (data, fonte, conclusão, impacto na spec e
   status ⬜ → ✅/❌). Amostras longas (saídas de `dsjob`, respostas do gateway) vão, já redigidas, para
   `docs/agentes-datastage-evidencias.md`, citando o ID.
5. **Ordem sugerida:** D-06, D-13, D-14 (ambiente) → D-01 a D-04 (gateway) → D-07 a D-09 (DataStage) → o resto.
6. **Se não der para validar** (sem acesso, sem resposta do time do gateway): registrar o motivo, manter o
   **padrão assumido** da linha e marcar ⚠️. Nada é chutado: sem contrato do gateway (D-01) os agentes ficam em `sem_contrato`.

### 8.1 Dúvidas a validar em produção

| ID | Dúvida | Bloqueia | Status |
|----|--------|----------|--------|
| D-01 | Onde vai o identificador do usuário e qual o formato exato | F1 | ⬜ |
| D-02 | O que o gateway devolve em cada causa (não cadastrado, chave inválida, ok, falha, 429) | F1 | ⬜ |
| D-03 | A chamada mínima (sonda): custo, limite e tempo para o cadastro valer | F1 | ⬜ |
| D-04 | Limites e latência do gateway (tamanho, timeout, p50/p95) | F2 | ⬜ |
| D-05 | Como o usuário pede o cadastro no gateway | F3 | ⬜ |
| D-06 | Provedor e configuração de IA em produção hoje | F1 | ⬜ |
| D-07 | Como o `dsjob` responde de verdade (formato, tamanho, Encrypted, caixa do nome) | F2 | ⬜ |
| D-08 | Como saber que um job mudou (data de modificação) e a que custo | F2 / F5 | ⬜ |
| D-09 | Capacidade de sessões SSH do servidor DataStage | F2 | ⬜ |
| D-10 | Tamanho da base já mapeada × jobs existentes | — (informa F5) | ⬜ |
| D-11 | Raízes SFTP ativas e se valem para o mapeamento | — (decide o v1) | ⬜ |
| D-12 | Erros reais de acesso já vistos (semente do aprendizado) | F6 | ⬜ |
| D-13 | Esquema real em produção (larguras, colunas, perfis, usuários) | F1 | ⬜ |
| D-14 | `proxy_read_timeout` real da rota da API em produção | F2 | ⬜ |
| D-15 | Estado do `dags/` em produção (a purga vai funcionar?) | — (informa F4/F7) | ⬜ |

**D-01 — Contrato da identidade por usuário no gateway** · Bloqueia: **F1**
- *Dúvida:* em que campo da requisição vai o `cvp-<matrícula>` (header ou corpo, nome exato); se vai **junto com** o
  `x-api-key` ou no lugar dele; formato exato aceito (maiúsculas ou minúsculas — o Orquestra grava a matrícula em
  **MAIÚSCULAS**, `api/routers/auth.py:38`); se toda matrícula real é `cvp` + dígitos ou existem exceções.
- *Como validar:* (1) procurar a documentação do gateway (OpenAPI em `{base_url}/openapi.json` ou `/docs`, se existir; o
  painel `ritm_geresd_ed.html` do repo privado `sge`, pasta `chamado`, mostra como a estação chama hoje) e/ou perguntar ao
  time do gateway; (2) com a matrícula **do próprio usuário**, uma chamada mínima enviando o identificador no campo
  candidato, testando as duas caixas; (3) contagem no banco, **sem listar matrículas**:
  `SELECT COUNT(*) AS total, SUM(CASE WHEN matricula LIKE 'CVP[0-9]%' THEN 1 ELSE 0 END) AS padrao_cvp FROM dbo.etl_usuario WHERE ativo = 1;`
- *Registrar:* campo e nome exatos; junto/no lugar do `x-api-key`; caixa aceita; exemplo mascarado; as duas contagens.
- *Padrão se não der:* agentes ficam em `sem_contrato` (desligados). Nada é chutado.
- *Impacto:* §3 (Identidade), F1 (`agentes_gateway_campo_usuario`), critério F1.3.
- **Resultado:** _(preencher)_

**D-02 — Respostas do gateway por causa** · Bloqueia: **F1**
- *Dúvida:* status, corpo e headers relevantes em cada caso: (a) usuário cadastrado; (b) usuário **não** cadastrado;
  (c) chave do app inválida; (d) gateway inalcançável; (e) 429. Em especial: **(b) e (c) diferem?**
- *Como validar:* uma chamada mínima por caso. (b) exige identidade que o time do gateway confirme como não cadastrada
  (aviso prévio); (c) pode usar uma chave claramente falsa, com autorização do time; (d) URL/porta errada só para ver
  o tipo do erro no cliente.
- *Registrar:* tabela caso × status × corpo (redigido) × headers × tempo.
- *Padrão se não der:* a **chamada de controle** com a identidade do app (já prevista) decide entre `sem_cadastro` e
  `chave_do_app_invalida`. Se (b) e (c) forem idênticos, o controle passa a ser obrigatório, não opcional.
- *Impacto:* §3 (Sonda), F1.4, texto do aviso.
- **Resultado:** _(preencher)_

**D-03 — A chamada mínima (sonda)** · Bloqueia: **F1**
- *Dúvida:* o gateway aceita `max_tokens` baixo? Há custo ou cota por usuário que a sonda consuma? Devolve 429? Depois
  do cadastro do usuário, **quanto tempo** até valer (cache do gateway)?
- *Como validar:* 3 chamadas com `max_tokens` mínimo; perguntar ao time do gateway sobre cota e propagação (ou medir num
  cadastro real que esteja para acontecer).
- *Registrar:* `max_tokens` mínimo aceito; cota; tempo de propagação.
- *Padrão se não der:* TTL de `ok` = 10 min, `sem_cadastro` = 60 s, `gateway_indisponivel` sem cache.
- *Impacto:* TTLs do §3, F1.4.
- **Resultado:** _(preencher)_

**D-04 — Limites e latência do gateway** · Bloqueia: **F2**
- *Dúvida:* tamanho máximo de mensagem; timeout real do gateway (o cliente usa 60 s, `TIMEOUT_S`); latência típica; aceita
  `messages` com vários turnos e `tools`? (informativo — a spec não depende disso).
- *Como validar:* 5 chamadas curtas e 3 com ~10 000 caracteres (uma transcrição de 12 rodadas + contexto); anotar p50/p95 e
  qualquer erro por tamanho.
- *Registrar:* p50/p95 para os dois tamanhos; maior mensagem aceita; suporte a multi-turno e `tools`.
- *Padrão se não der:* orçamento de tempo da rodada de 90 s e 12 rodadas de histórico (o teto do Maestro).
- *Impacto:* `ORCAMENTO_AGENTE_S`, teto de contexto, F2.8.
- **Resultado:** _(preencher)_

**D-05 — Como pedir o cadastro no gateway** · Bloqueia: **F3** (só o texto)
- *Dúvida:* canal (link, e-mail, chamado), quem atende e em quanto tempo.
- *Como validar:* perguntar ao time do gateway; documentar.
- *Registrar:* o texto exato do aviso (vai para `agentes_cadastro_texto`, editável no Admin).
- *Padrão se não der:* aviso genérico "solicite o cadastro no gateway de IA" — **sem inventar link**.
- *Impacto:* F3.3.
- **Resultado:** _(preencher)_

**D-06 — Provedor e configuração de IA em produção** · Bloqueia: **F1**
- *Dúvida:* o provedor configurado é `caixa_gateway`? Modelo? `base_url`? `usa_proxy`? O diagnóstico passa?
- *Como validar:* `SELECT config_key, CASE WHEN config_key LIKE '%api_key%' THEN '<oculto>' ELSE config_value END AS valor FROM dbo.etl_app_config WHERE config_key LIKE 'caixa_ia_%' OR config_key IN ('maestro_enabled','chamados_triagem_habilitada');` e rodar **Admin › Caixa Seguro IA › Verificar**, registrando a frase do diagnóstico.
- *Registrar:* provedor, modelo, se usa proxy, resultado do Verificar (sem a chave).
- *Padrão se não der:* assume `caixa_gateway`; se for outro, o agente fica `provedor_incompativel` (o agente exige identidade por usuário) — decisão **B-10**.
- *Impacto:* §3, F1.
- **Resultado:** _(preencher)_

**D-07 — O `dsjob` de verdade** · Bloqueia: **F2**
- *Dúvida:* formato, tamanho e tempo da saída de `ljobs`, `lstages`, `lparams`, `jobinfo` e `report`; **o que aparece para
  parâmetro Encrypted**; o comportamento com o nome em **caixa diferente** e com **job inexistente** (a mensagem exata vira aprendizado).
- *Como validar:* pelo Console DataStage (ou `run_dsjob`) para **3 jobs**: um paralelo, uma sequence, e um com parâmetro Encrypted.
- *Registrar:* por comando: `exit_code`, bytes, duração, 5 a 10 linhas **redigidas**; a linha (mascarada) do parâmetro Encrypted; a mensagem dos dois erros.
- *Padrão se não der:* parser conservador, saída truncada, e tudo que parecer valor de parâmetro é redigido.
- *Impacto:* parser e truncagem da F2, regras de `redigir()`, semente da F6, F2.4.
- **Resultado:** _(preencher)_

**D-08 — Como saber que um job mudou** · Bloqueia: **F2 / F5**
- *Dúvida:* o `dsjob` (`-jobinfo`, `-report`) expõe data de modificação? A API REST que o lineage ISX usa
  (`ds_last_modified`) responde só metadados, sem exportar ISX? A que custo?
- *Como validar:* olhar a saída do D-07; numa consulta de metadados do mesmo job pela API REST, comparar com
  `etl_ds_job_isx.ds_last_modified`.
- *Registrar:* qual fonte dá a data, se dá para consultá-la sem exportar, e o tempo.
- *Padrão se não der:* **prazo de 7 dias** (`agentes_fato_validade_dias`) para fatos de `dsjob`/SFTP; ISX continua por `ds_last_modified`.
- *Impacto:* validade da base primeiro (§3), F2.3, F5.
- **Resultado:** _(preencher)_

**D-09 — Capacidade de sessões SSH** · Bloqueia: **F2**
- *Dúvida:* `MaxSessions`/`MaxStartups` do `sshd` do servidor DataStage e quantas conexões o Console, Utilitários, lineage e
  DAGs já abrem no pico. Qual teto é seguro para o agente?
- *Como validar:* se houver acesso ao servidor DataStage, `sshd -T | grep -Ei 'maxsessions|maxstartups'` e a contagem de
  conexões SSH estabelecidas no horário de pico; senão, pedir os dois números ao administrador do servidor.
- *Registrar:* os dois parâmetros, a conexão média e a de pico, e o teto recomendado.
- *Padrão se não der:* `agentes_ssh_max = 10` (o pico de usuários informado), configurável, com espera limitada.
- *Impacto:* F2.5, Admin › Agentes.
- **Resultado:** _(preencher)_

**D-10 — Tamanho da base já mapeada** · Não bloqueia (informa F5)
- *Dúvida:* quantos jobs já têm ISX na base × quantos existem no DataStage.
- *Como validar:* `SELECT COUNT(*) AS jobs_isx, COUNT(DISTINCT ds_project) AS projetos FROM dbo.etl_ds_job_isx;` e
  `SELECT COUNT(*) AS linhas_isx_auto FROM dbo.etl_job_lineage WHERE extraction_method = 'isx_auto';`; o total de jobs por
  projeto via `ljobs` (só a contagem).
- *Registrar:* os números e o percentual coberto.
- *Padrão se não der:* assume que a maioria dos jobs está fora de pipeline (por isso `etl_agente_fato` é tabela própria).
- *Impacto:* valor do base-first e peso da F5.
- **Resultado:** _(preencher)_

**D-11 — Raízes SFTP** · Não bloqueia (decide o v1)
- *Dúvida:* quais raízes do servidor `datastage` estão ativas na tela Utilitários e se há ISX/DSX/relatórios úteis ao mapeamento.
- *Como validar:* ver a configuração das raízes ativas (`api/services/ssh_arquivos.py`, `SERVIDORES['datastage']` e a função
  de raízes) e listar (só nomes de pasta) o que há nelas.
- *Registrar:* raízes ativas e o que serve para mapeamento.
- *Padrão se não der:* a ferramenta SFTP fica **fora do v1**.
- *Impacto:* §3 (ferramentas), F2.
- **Resultado:** _(preencher)_

**D-12 — Erros reais de acesso já vistos** · Bloqueia: **F6** (semente)
- *Dúvida:* quais falhas de acesso/leitura do DataStage mais acontecem hoje.
- *Como validar:* `SELECT TOP 20 erro, COUNT(*) AS n FROM dbo.etl_ds_job_isx WHERE erro IS NOT NULL GROUP BY erro ORDER BY n DESC;`
  e os logs do `orquestra-api` (mensagens de `dsjob`/SSH/ISX).
- *Registrar:* as 10 assinaturas mais frequentes (redigidas) e a correção conhecida de cada uma.
- *Padrão se não der:* a semente inicial usa só o que já é sabido (caixa do nome do job, `~/` no `DS_ISTOOL_AUTHFILE`, allowlist).
- *Impacto:* semente da F6 (**B-12**).
- **Resultado:** _(preencher)_

**D-13 — Esquema real em produção** · Bloqueia: **F1**
- *Dúvida:* larguras reais (`etl_usuario.matricula`, `etl_job_lineage.extraction_method` — a 106 diz `VARCHAR(20)`, o
  `schema_prod_dev.sql` diz `VARCHAR(50)`), colunas de `etl_app_config`, **todos os perfis** de `etl_perfil_permissao`
  (para semear `tela_agentes`) e usuários ativos por perfil.
- *Como validar:* `SELECT TABLE_NAME, COLUMN_NAME, CHARACTER_MAXIMUM_LENGTH FROM INFORMATION_SCHEMA.COLUMNS WHERE (TABLE_NAME='etl_usuario' AND COLUMN_NAME='matricula') OR (TABLE_NAME='etl_job_lineage' AND COLUMN_NAME='extraction_method') OR TABLE_NAME='etl_app_config';`
  e `SELECT perfil_nome, COUNT(*) FROM dbo.etl_usuario WHERE ativo = 1 GROUP BY perfil_nome;` e `SELECT DISTINCT perfil_nome FROM dbo.etl_perfil_permissao;`
- *Registrar:* larguras, colunas e a lista de perfis (só nomes de perfil e contagens).
- *Padrão se não der:* a 116 usa `MERGE` sobre **todos os perfis que existirem** no momento da migration.
- *Impacto:* §4, F1.1.
- **Resultado:** _(preencher)_

**D-14 — `proxy_read_timeout` de produção** · Bloqueia: **F2**
- *Dúvida:* qual `location` do nginx **de produção** atende `/orquestra/` e qual o seu `proxy_read_timeout` (o de produção
  está à frente do repo; no repo há 120 s numa location e 300 s noutra).
- *Como validar:* ler o `nginx.conf` em uso no servidor (não o do repo).
- *Registrar:* o timeout efetivo da rota da API.
- *Padrão se não der:* 120 s ⇒ orçamento de tempo da rodada de 90 s.
- *Impacto:* `ORCAMENTO_AGENTE_S`, F2.8.
- **Resultado:** _(preencher)_

**D-15 — Estado do `dags/` em produção** · Não bloqueia (informa F4/F7)
- *Dúvida:* o `etl_log_cleanup.py` de produção já tem a tarefa `limpar_conversas_maestro` (do pacote de 10/09)? Se não, o
  `dags/` não é sincronizado desde então e o deploy da F4 vai levar mudanças acumuladas.
- *Como validar:* procurar `limpar_conversas_maestro` no arquivo de produção e comparar com o do repo.
- *Registrar:* sim/não e o que diverge.
- *Padrão se não der:* o deploy da F7 responde **s** em `dags/` e revisa o diff antes.
- *Impacto:* roteiro de deploy da F7, smoke k).
- **Resultado:** _(preencher)_

### 8.2 Decisões que dependem do usuário (com padrão assumido)

| ID | Decisão | Padrão assumido |
|----|---------|-----------------|
| B-01 | Posição do grupo **Agentes** na sidebar | Imediatamente antes de "Administração" (não reordena os existentes) |
| B-02 | O agente pode **disparar a extração ISX**? (cria arquivo temporário no servidor DataStage, como o lineage já faz) | **Não** no v1: o agente aponta o link da Governança |
| B-03 | Logs de execução (`logsum`/`logdetail`) como ferramenta? | **Fora** do v1 (podem ter valores de dados) |
| B-04 | O usuário pode **apagar a própria conversa**? | Não; a purga de 30 dias cuida |
| B-05 | Job **fora de pipeline**: fatos em `etl_agente_fato` (tabela nova), sem espelhar em `etl_job_lineage` | Sim, tabela nova; sem espelho |
| B-06 | Quem é o **curador** (`agente_curador`) e quem recebe `agente_datastage` no começo | A definir; ninguém recebe automático |
| B-07 | **Política de leitura de conversas de terceiros** (o backlog) e se guardar conversas com matrícula por 30 dias precisa de aval de compliance | Só o dono lê; o backlog não começa sem política |
| B-08 | Os **30 dias** contam desde a última mensagem (A12) ou desde a criação? | Desde a última mensagem |
| B-09 | Linha de base do problema (A1): como o engenheiro entende um fluxo hoje e quanto leva | Sem número; registrar depois (opcional) |
| B-10 | Se o provedor de produção **não** for `caixa_gateway`: aceitar trocar? | O agente fica `provedor_incompativel` até trocar |
| B-11 | Histórico enviado ao gateway na retomada | Últimas 12 rodadas |
| B-12 | Semente de aprendizados: quem aprova a lista inicial | O curador, antes do agente usar |

### 8.3 Dúvidas que o código já respondeu (a fase confere; não dependem de produção)
- **C-01** `Governanca.tsx` não lê parâmetros de URL (`useSearchParams` sem ocorrência) → a F3 adiciona `?pipeline=&job=` (mudança mínima) ou o link abre a aba sem o job.
- **C-02** Reuso do grafo: `GrafoIsx.tsx`/`PainelJobIsx.tsx` com `GET /lineage/isx/job` (só banco, guard `get_current_user`) → a F3 confirma as props sem duplicar código.
- **C-03** O gateway recebe **uma** mensagem e hoje 401/403 vira 502 "chave recusada" → a F1 estende `caixa_ia` sem mudar Caixa Seguro nem triagem (teste de igualdade do corpo/headers).
- **C-04** `run_dsjob` devolve até 200 000 caracteres de `stdout` → a F2 trunca por ferramenta antes de ir ao modelo.
- **C-05** `api/main.py` registra routers em **duas** listas (~linhas 147 e 207) → a F1 inclui `agentes` nas duas.
- **C-06** Purga em `dags/` usa `%s` (pymssql); a API usa `?` (pyodbc).
- **C-07** `NVARCHAR(n)` conta UTF-16 → `cortar_utf16` em título e corpo.

### 8.4 Critério de fechamento da spec
Todas as dúvidas **bloqueantes** (D-01, D-02, D-03, D-04, D-06, D-07, D-08, D-09, D-13, D-14; D-05 e D-12 antes das F3 e F6
respectivamente) com status ✅ ou ⚠️ justificado; os pontos de **impacto** de cada uma atualizados neste arquivo; as decisões
B-xx confirmadas ou o padrão aceito. Então o status passa a **aprovada**, e o usuário autoriza o início da F1.

## 9. Registro da entrevista (decisões e itens assumidos)

**Decisões do usuário:** agente único de mapeamento DataStage, com outros agentes possíveis depois · todos acessam a tela,
agentes liberados por usuário · usuário logado vai ao gateway como `cvp-<matrícula>` e o gateway autoriza · leitura ao vivo
somente leitura, pela API do Orquestra (`DS_SSH_*`) · saída: chat, grafo e links · fatos gravados na hora; interpretação só
com aprovação do usuário na conversa · aprendizado: fatos na hora, interpretação com aprovação do curador · tokens **não**
são controlados · conversas salvas, retomáveis em até 30 dias, com busca; leitura do que entra e sai fica no backlog ·
visual com tokens neutros · até 10 usuários simultâneos, base primeiro · item novo "Agentes" no menu · deploys anteriores
confirmados (migrations 106–115 aplicadas, última em 14/09/2026 08:01; horário do banco é BRT).

**ASSUMIDOS:**
- **A1** O processo atual é leitura manual de ISX/DSX/Designer; sem linha de base numérica (B-09).
- **A2** Sonda mínima ao abrir a tela, com cache de sessão (a decisão de "só pela resposta do chat" já foi do usuário).
- **A3** Rota `/agentes`, item "Agentes" no menu.
- **A5** Acessibilidade no padrão do Orquestra.
- **A6** Sem dependência Python nova.
- **A7** Curador é um recurso RBAC novo (`agente_curador`).
- **A8** Validade: ISX por `ds_last_modified`; `dsjob`/SFTP por prazo de 7 dias (a confirmar no D-08).
- **A10** Teto de sessões SSH = 10, configurável.
- **A11** Identificador = `cvp-` + matrícula em minúsculas (a confirmar no D-01).
- **A12** Os 30 dias contam desde a última mensagem (B-08).
- ~~A4~~ (retenção de 180 dias) substituída pelos 30 dias; ~~A9~~ (meta de tokens) removida.
