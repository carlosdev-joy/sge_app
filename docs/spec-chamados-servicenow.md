# Spec: Chamados da Engenharia (ServiceNow) — Orquestra
Data: 2026-08-09 · Status: rascunho

## 1. Visão
A fila de chamados do ServiceNow mistura a empresa inteira; a engenharia não tem
visão própria, kanban nem indicadores — triagem e acompanhamento diário são
manuais e dispersos. Esta feature cria a tela **/chamados** no Orquestra: um
espelho somente-leitura dos chamados do(s) grupo(s) da engenharia (incidentes,
RITMs/tarefas e mudanças), sincronizado a cada 3h por DAG, com kanban por
estado, filtros e a visão de indicadores para a gestão. Quando pronta, a daily
e a priorização passam a partir da mesma foto, e chamado velho não passa
despercebido.

## 2. Escopo
**IN:**
- DAG `etl_servicenow_sync` (a cada 3h): Table API do ServiceNow → espelho no
  SQL Server, filtrado por `assignment_group`, cobrindo `incident`,
  `sc_req_item`, `sc_task` e `change_request`.
- Tela `/chamados` (permissão nova `tela_chamados`): kanban somente-leitura com
  colunas fixas espelhando os estados (Novo · Em andamento · Aguardando ·
  Resolvido · Outros), card com número, título, tipo, responsável, prioridade e
  idade; link abre o chamado no ServiceNow.
- Filtros: tipo, estado, responsável, prioridade e busca por texto/número.
- Aba "Indicadores" (gestão): aging, abertos por tipo × estado, entradas ×
  saídas da semana, carga por responsável.
- Configuração no Admin: URL da instância, grupo(s), credencial (mascarada na
  listagem como as `caixa_ia_*`), "testar conexão" e "sincronizar agora".
- Carimbo de frescor na tela (padrão da casa): "sincronizado há Xh"; atraso de
  sync > 2 ciclos vira aviso âmbar.

**OUT (explícito):**
- Escrita no ServiceNow (mudar estado, atribuir, comentar) — v1 é espelho.
- Tempo real/webhooks — cadência fixa de 3h (configurável por Variable depois).
- Fluxo de colunas próprio da equipe (v2, sobre os dados que a v1 acumular).
- Outros grupos/equipes; anexos; histórico completo/worklog do chamado.
- Notificação proativa (Teams) sobre chamados — backlog, depende da v1 rodar.

## 3. Arquitetura proposta
- **Front**: página nova `ui-react/src/pages/Chamados.tsx` + registro em
  `ui-react/src/App.tsx` (import + rota `/chamados`, menu por permissão, padrão
  da `/inventario`). Componentes existentes: `components/ui/Badge`, `Tabs`,
  `Input/Select`, tokens `canvas/panel/edge/ink` (claro+escuro). Kanban SEM
  drag-and-drop (somente leitura) — colunas são `<div>` com lista de cards,
  nenhuma lib nova.
- **Back**: router novo `api/routers/chamados.py` — `GET /chamados` (espelho +
  frescor + flags de degradação), `GET /chamados/indicadores` (agregados),
  ações de Admin no `api/routers/admin.py` (`servicenow_test`,
  `servicenow_sync_now` via trigger da DAG, padrão do `get_airflow_client`).
- **Dados**: tabelas novas `etl_chamado` e `etl_chamado_sync` (migration 088).
  Config em `dbo.etl_app_config` (`servicenow_url`, `servicenow_grupos`,
  `servicenow_usuario`, `servicenow_senha` — a última mascarada no
  `config_list`, mesmo tratamento das `caixa_ia_*`).
- **Orquestração**: DAG `dags/etl_servicenow_sync.py`, `schedule="0 */3 * * *"`,
  `max_active_runs=1`, gravação via pymssql (placeholders `%s` — árvore
  `dags/`), upsert por `sys_id`, log de cada ciclo em `etl_chamado_sync`.
- **Decisões e alternativas descartadas**:
  - Painel fora do Orquestra (app próprio na intranet) — descartado: infra nova
    na empresa sem necessidade; o Orquestra já tem login, RBAC e deploy.
  - Visual Task Board nativo do ServiceNow — descartado como solução final
    (não unifica os 3 tipos nem dá indicadores); continua disponível como
    paliativo manual até o deploy.
  - Front consultar a API do ServiceNow direto — descartado: credencial iria ao
    navegador e cada usuário geraria carga na API; o espelho serve todos com
    uma credencial só, no servidor.
  - Credencial em Airflow Connection — descartado em favor do `etl_app_config`
    cifrado/mascarado: a tela de Admin já edita e mascara esses valores, e a
    DAG já lê config do banco (um lugar só).

## 4. Modelo de dados
Migration **`sql/migrations/088_chamados_servicenow.sql`** (idempotente:
`IF NOT EXISTS` em tabela, coluna e permissão; RBAC via MERGE, padrão da 055):

**`dbo.etl_chamado`** — o espelho:
| coluna | tipo | obs |
|---|---|---|
| id | INT IDENTITY PK | |
| sys_id | VARCHAR(32) NOT NULL UNIQUE | chave natural do ServiceNow |
| numero | VARCHAR(20) NOT NULL | INC/RITM/SCTASK/CHG + dígitos |
| tipo | VARCHAR(20) NOT NULL | incident · ritm · task · change |
| titulo | **NVARCHAR(400)** | short_description; truncar COM sufixo "…" (larguras da origem já estouraram VARCHAR — PR #161) |
| estado_origem | VARCHAR(60) | valor cru devolvido pela API (display) |
| estado_kanban | VARCHAR(20) NOT NULL | novo · andamento · aguardando · resolvido · outros |
| prioridade | VARCHAR(20) | display value |
| atribuido_a | NVARCHAR(120) | display value |
| grupo | NVARCHAR(120) | assignment_group display |
| aberto_em / atualizado_em | DATETIME | opened_at / sys_updated_on |
| encerrado_em | DATETIME NULL | closed_at/resolved_at |
| ativo | BIT NOT NULL | active da origem |
| url | NVARCHAR(500) | link direto para o registro no portal |
| sync_em | DATETIME NOT NULL | carimbo do ciclo que gravou |

Índices: UNIQUE (sys_id); IX (estado_kanban, ativo); IX (atribuido_a).

**`dbo.etl_chamado_sync`** — um registro por ciclo da DAG: id, iniciado_em,
terminado_em, status (OK/ERRO), qtd_incident, qtd_ritm, qtd_task, qtd_change,
qtd_desativados, erro NVARCHAR(1000). É a fonte do carimbo de frescor e do
alerta "0 chamados" (grupo errado parece fila vazia — o log DIZ a diferença).

**Mapeamento estado→coluna** (dict único em `dags/etl_servicenow_sync.py`,
documentado na própria migration como comentário): incident 1→novo, 2→andamento,
3→aguardando, 6→resolvido, 7/8→(sai do kanban, `ativo=0`); sc_req_item/sc_task
e change_request com tabelas próprias no mesmo dict; **valor não mapeado cai em
`outros` e aparece — nunca some em silêncio**. Valores exatos serão conferidos
na instância real (Pendência #3) antes do deploy da F1.

**RBAC**: recurso `tela_chamados` para `admin`, `desenvolvedor` e `operador`
(MERGE em `etl_perfil_permissao`, padrão da migration 055). Config seeds em
`etl_app_config` com valores vazios (a tela de Admin preenche).

## 5. Fases
### F1 — Fundação: migration + DAG de sync
- Entregável: espelho populando no banco a cada 3h (ou vazio com erro DITO).
- Inclui: migration 088; `dags/etl_servicenow_sync.py` (cliente HTTP isolado em
  função para stub, paginação `sysparm_offset`, upsert por sys_id, desativação
  do que sumiu da fila, log em `etl_chamado_sync`); config seeds; testes de
  contrato (query strings, mapeamento de estado, truncamento de título) com
  HTTP stubado — **o dev não alcança o ServiceNow da empresa; a prova real é o
  smoke §7**.
- Critérios de aceite: rodada da DAG com stub grava N chamados e 1 linha de
  sync OK; credencial ausente/errada → sync ERRO com mensagem que nomeia a
  causa, espelho intacto; estado desconhecido vira `outros`; rodada com 0
  chamados grava sync OK com qtds zeradas (e é distinguível de erro).
- Validação: pytest (baseline: zero falhas novas). Revisão adversarial
  multi-agente antes da PR. PR: `feat: espelho de chamados do ServiceNow (DAG + migration 088)`.

### F2 — Tela /chamados com o kanban
- Entregável: kanban somente-leitura navegável no menu.
- Inclui: `GET /chamados` em `api/routers/chamados.py` (espelho + frescor via
  `etl_chamado_sync` + flag de migration ausente — degradação dita, padrão
  malha); `pages/Chamados.tsx` (colunas fixas, card com número/título/tipo/
  responsável/prioridade/idade, link ServiceNow `target=_blank`); rota + menu
  por `tela_chamados` em `App.tsx`; carimbo "sincronizado há Xh" com âmbar
  quando > 6h. Estado nunca só por cor (rótulo textual no card).
- Critérios de aceite: usuário sem `tela_chamados` não vê menu nem rota; com o
  espelho vazio a tela diz "nenhum chamado sincronizado" + quando foi o último
  sync; migration ausente → aviso "sistema em atualização" (não tela branca);
  erro de `apiFetch` exibe `err.message` (contrato de erro já documentado).
- Validação: tsc + eslint (baseline HEAD, zero erros novos) + build (dist/
  commitada) + pytest. Revisão adversarial antes da PR.
  PR: `feat: tela de chamados da engenharia com kanban`.

### F3 — Filtros e aging no card
- Entregável: fila de ~50 filtrável em 2 cliques.
- Inclui: filtros por tipo/estado/responsável/prioridade + busca por
  texto/número (client-side — volume ≤ centenas); idade no card com destaque
  progressivo (>3d âmbar, >7d vermelho — com rótulo, não só cor); contadores
  por coluna.
- Critérios de aceite: filtro combinado (tipo=incident + responsável=X) reduz
  as colunas na hora; busca por "RITM00" acha por prefixo; card de 8 dias
  exibe "8d" em vermelho E com o rótulo "parado há 8 dias" no title.
- Validação: tsc + eslint (baseline) + build + pytest. Revisão adversarial.
  PR: `feat: filtros e idade dos chamados no kanban`.

### F4 — Indicadores da gestão
- Entregável: aba "Indicadores" na mesma tela.
- Inclui: `GET /chamados/indicadores` (agregados no SQL: aging por faixa,
  abertos por tipo × estado, entradas × saídas por dia dos últimos 14 dias a
  partir de `aberto_em`/`encerrado_em`, carga por responsável); gráficos no
  padrão da casa (SVG simples como o Gantt do Dashboard/Sparkbars do Admin —
  nenhuma lib nova; **consultar a skill dataviz para forma e paleta antes de
  desenhar**).
- Critérios de aceite: cada número da aba bate com uma query manual no espelho;
  semana sem encerramento mostra 0 dito (não célula vazia); nenhuma superfície
  usa "%" sem o `x de y` ao lado (regra da casa).
- Validação: tsc + eslint (baseline) + build + pytest. Revisão adversarial.
  PR: `feat: indicadores de chamados para a gestão`.

### F5 — Admin, teste de conexão e polimento
- Entregável: operação sem tocar em banco/DAG na mão.
- Inclui: aba "ServiceNow" no Admin (grupo Sistema): URL/grupos/credencial
  (senha mascarada na listagem, mesmo tratamento das `caixa_ia_*`), botão
  "Testar conexão" (chama a API com a credencial salva e devolve qtd visível)
  e "Sincronizar agora" (trigger da DAG via `get_airflow_client`); `/simplify`
  no conjunto; atualização do smoke; doc de operação curto no próprio Admin.
- Critérios de aceite: trocar o grupo no Admin muda a fila no ciclo seguinte
  (sem redeploy); "Testar conexão" com senha errada nomeia a causa (401 ≠ DNS
  ≠ timeout); "Sincronizar agora" reflete na tela em < 1 min.
- Validação: tsc + eslint (baseline) + build + pytest. Revisão adversarial.
  PR: `feat: configuracao do ServiceNow no Admin`.

## 6. Riscos e mitigações
| # | Risco | Impacto | Mitigação |
|---|-------|---------|-----------|
| 1 | Dev não alcança o ServiceNow da empresa — a integração real só é testável em produção | Bug de integração descoberto tarde | Cliente HTTP isolado + testes com stub (F1); "Testar conexão" no Admin (F5); smoke §7 é o aceite real; F1 vai primeiro justamente para validar cedo no deploy |
| 2 | Credencial de integração: liberação, escopo (ACL por tabela) e política da empresa | Sync parcial ou negado (403 numa tabela, 200 noutra) | Sync por tabela independente: falha numa não derruba as outras; log nomeia a tabela negada; Pendência #2 |
| 3 | Estados/valores diferentes entre `incident`, `sc_req_item`/`sc_task` e `change_request` (e por instância) | Chamado na coluna errada ou invisível | Dict de mapeamento único e documentado; não mapeado cai em `outros` VISÍVEL; `estado_origem` preservado no card (title) |
| 4 | Grupo renomeado no ServiceNow (filtro para de casar) | Fila vazia com cara de "tudo resolvido" — falso verde | Grupo é config do Admin (sem redeploy); ciclo com 0 chamados grava log distinguível e a tela alerta "0 chamados — confira o grupo" quando antes havia >0 |
| 5 | Títulos com acento/emoji e larguras da origem | Truncamento silencioso ou erro de gravação (bug real: VARCHAR estourado, PR #161) | NVARCHAR no espelho; truncate explícito com "…" e teste de contrato cobrindo |
| 6 | Permissão `tela_chamados` esquecida no deploy | Tela nova não aparece no menu (gotcha conhecido da 6c) | RBAC dentro da migration 088 (F1); critério de aceite da F2 cobre; deploy responde `s` na 6c |

## 7. Smoke pós-deploy
a) Admin → ServiceNow: preencher URL, grupo(s) e credencial; **Testar conexão**
   → deve responder com a quantidade de chamados visíveis (≠ erro).
b) **Sincronizar agora** → em < 1 min, `SELECT COUNT(*) FROM etl_chamado` > 0 e
   1 linha OK em `etl_chamado_sync` com qtds por tipo.
c) Abrir `/chamados` com usuário SEM `tela_chamados` → menu não mostra e a rota
   nega; com admin → kanban carrega com os chamados reais do grupo.
d) Conferir 3 chamados contra o portal do ServiceNow: mesmo estado, mesmo
   responsável; clicar no card abre o registro certo no portal.
e) Filtrar por responsável + buscar por um número RITM real → acha.
f) Aba Indicadores: "abertos por tipo × estado" bate com a lista do portal
   filtrada à mão (tolerância = janela de 3h do sync).
g) Esperar um ciclo agendado (3h) → novo registro em `etl_chamado_sync` sem
   intervenção; carimbo de frescor da tela atualiza.
h) Negativo: trocar a senha no Admin por uma errada e Sincronizar agora → sync
   ERRO nomeando 401, tela continua servindo o espelho anterior com aviso.

## 8. Pendências e decisões em aberto
1. **URL da instância: `https://cvpsnprod.service-now.com`** (informada em
   2026-08-10; alcançável da VPS — API responde 401 sem credencial, sem
   bloqueio por IP). **Nome exato do(s) grupo(s) de atribuição**: a coletar
   pela sonda de diagnóstico (branch `feat/sonda-servicenow`, aba
   ServiceNow (sonda) no Admin do dev).
2. **Tipo de autenticação da API** (Basic com usuário de integração é o
   assumido; se for OAuth, a F1 ganha o fluxo de token).
3. **Valores reais de estado** das 4 tabelas na instância da empresa (conferir
   com 1 GET de exemplo por tabela antes de fechar o dict da F1).
4. "Aberto" = `active=true` (ASSUMIDO — confirmar se a equipe quer ver
   resolvidos-não-fechados no kanban ou só até "resolvido").
