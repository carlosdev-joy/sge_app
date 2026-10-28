# Spec: Uso do módulo Busca & Vendas — Orquestra
Data: 2026-10-28 · Status: em execução (F1) · Origem: pedido do solicitante do RITM0117336 ("a partir deste primeiro CARD construiremos monitoramento de usabilidade") + decisões do Carlos em 28/10/2026

## 1. Visão
Hoje o Orquestra não sabe quem usa o módulo `/caixa-seguro/*`, quando e o que abre: `etl_sessao` só guarda a sessão corrente (apagada no logout/expiração/novo login) e `etl_usuario.ultimo_login` guarda só o último. Esta feature registra o uso do módulo e o mostra numa tela nova **dentro do módulo** ("Uso do módulo", item novo do menu), liberada por permissão escolhida na Administração (qualquer perfil ou usuário). Serve para dizer, no futuro, **quais usuários acessam e o que acessam**.

A medição começa no dia da publicação. Não há histórico anterior a recuperar.

## 2. Escopo
**IN**
- Registro de **acesso** a cada tela de `/caixa-seguro/*` (Consulta de Propostas, Monitoramento Tático, Acompanhamento por status, Portabilidades, Painel de IA Operacional e a própria tela de Uso).
- **Presença** ("online agora") por heartbeat enquanto a aba está visível.
- Tela **Uso do módulo**: usuários online agora, acessos e usuários distintos por dia / mês / ano, acessos por tela, ranking de usuários.
- Permissão nova `caixa_seguro_uso`, concedível por perfil e por usuário no Admin; semeada só no perfil `admin`.
- Item novo no menu do módulo (`MenuButton`), visível só com a permissão.

**OUT (explícito)**
- Uso fora do módulo `/caixa-seguro/*` (Dashboard, Pipelines, Admin etc.) e eventos de LOGIN do sistema.
- Ações dentro da tela (cliques em card, buscas, envios): só a abertura de tela é medida. Backlog.
- Exportação (CSV/Excel), alertas, comparação entre períodos, drill-down por usuário.
- Retenção/expurgo automático dos eventos: **sem job nesta entrega** (pendência de decisão, §9).
- Histórico anterior à publicação.
- IP, user-agent ou qualquer dado de dispositivo.

## 3. Telas (brief definido com a skill `impeccable`, modo Operate)

**Tela única: `/caixa-seguro/uso` — "Uso do módulo"**
- **Quem e quando:** gestor/administrador que decide acesso e adoção; abre a tela de tempos em tempos, não a opera o dia todo. Precisa responder em segundos: "quantos usam, quem usa, o que abrem".
- **Autoridade visual:** as telas nativas do módulo (`Monitoramento.tsx`, `PainelIA.tsx`): tokens `canvas/panel/edge/ink` claro+escuro, `Card`, `KpiCard`, `Tabs`, `Table`, `Skeleton`, `Banner`, `Badge` de `components/ui`, e `recharts` com o azul institucional `#1A5FA8` e o tooltip por CSS vars. **Nenhuma cor, fonte ou componente novo.** Cabeçalho igual ao das outras telas do módulo (h1 com ícone + `MenuButton`). Item novo entra no FIM do `MenuButton` (a ordem existente não muda).
- **Hierarquia (de cima para baixo):**
  1. Cabeçalho + seletor de granularidade `Dia | Mês | Ano` (`Tabs`) com navegação ‹ período › (data de referência; não avança além de hoje).
  2. Faixa de KPIs (`KpiCard`): **Online agora** · **Usuários no período** · **Acessos no período** · **Acessos por usuário** (média). "Online agora" é independente do período e leva rótulo "últimos 10 min".
  3. Gráfico de série do período, um nível abaixo da granularidade: Dia → por hora; Mês → por dia; Ano → por mês. Duas séries: acessos e usuários distintos.
  4. Duas colunas em desktop: **Acessos por tela** (tabela com barra proporcional: tela, acessos, usuários) e **Ranking de usuários** (usuário, matrícula, acessos, dias ativos, último acesso, tela mais acessada).
- **Estados:** carregando (`Skeleton` nos KPIs/gráfico/tabelas); vazio ("Nenhum acesso registrado neste período." + nota "O registro começou em DD/MM/AAAA" com a data do primeiro evento); erro (`Banner` com "Tentar novamente"); sem permissão (o `RequirePerm` redireciona; o item de menu nem aparece).
- **Responsivo:** KPIs 4 → 2 → 1 colunas; duas colunas viram uma abaixo de `lg`; tabelas rolam na horizontal **dentro do card**, nunca a página; gráfico em `ResponsiveContainer`.
- **Acessibilidade:** `Tabs` navegável por teclado; o gráfico tem equivalente em tabela (a tabela "Acessos por tela" e o ranking carregam os mesmos números); a cor nunca é o único sinal (séries distintas por rótulo e por traço); foco visível; contraste pelos tokens.
- **Copy (pt-BR):** "Uso do módulo", "Online agora", "Usuários no período", "Acessos no período", "Acessos por usuário", "Acessos por tela", "Ranking de usuários", "Último acesso", "Dias ativos". "Acesso" = abertura de uma tela; a tela explica isso em um `Hint`.
- **Dados que a tela consome** → contrato da §4 (`GET /caixa/uso/resumo`).
- **Fora desta tela:** não reordenar nada das telas existentes; não mexer no visual das demais.

## 4. Arquitetura proposta
**Front (`ui-react/src`)**
- `caixa/pages/Uso.tsx` — a tela.
- `caixa/lib/uso.ts` — tipos do contrato, hooks `useUsoResumo(periodo, referencia)` (TanStack Query + `apiFetch`) e `useRastreioUso()`.
- `caixa/components/UsoTracker.tsx` — componente sem UI: dispara `POST /caixa/uso/acesso` na mudança de rota (`useLocation`) e `POST /caixa/uso/presenca` a cada 4 min com a aba visível (`document.visibilityState`). Falha **silenciosa** (nunca quebra a tela nem mostra toast). Dedupe local por rota na sessão (30 min) além do dedupe do servidor.
- `App.tsx` — rota nova `caixa-seguro/uso` com `RequirePerm perm="caixa_seguro_uso"`; `<UsoTracker />` dentro das 5 rotas do módulo (dentro do `ProfileProvider`).
- `caixa/components/MenuButton.tsx` — item "Uso do módulo" no fim, só com `caixa_seguro_uso`.
- `lib/rbacRecursos.ts` — `['caixa_seguro_uso', 'Caixa Seguro — Uso do módulo']` (Admin governa por perfil e por usuário; fica em `RBAC_RECURSOS_PERFIS`). Não é `tela_*`, então não exige item no NAV (mesmo caso de `caixa_seguro_operacional`).

**Back (`api/`)**
- `routers/caixa_uso.py`, registrado em `main.py` (mesmo padrão de `pio_card1`):
  - `POST /caixa/uso/acesso` `{rota}` — `tela_caixa_seguro`. A **matrícula vem do token**, nunca do corpo. A rota é casada contra um **registro fechado** de rotas (regex → rota canônica, rótulo da tela, `detalhe` opcional, p. ex. o `:status` validado contra a lista de status). Rota desconhecida: ignorada (200, `registrado:false`), não grava lixo. Dedupe no servidor: `INSERT … WHERE NOT EXISTS` (mesma matrícula + rota + detalhe nos últimos 30 min).
  - `POST /caixa/uso/presenca` `{rota}` — `tela_caixa_seguro`. `MERGE` em `etl_uso_presenca` (1 linha por matrícula).
  - `GET /caixa/uso/resumo?periodo=dia|mes|ano&referencia=AAAA-MM-DD` — `caixa_seguro_uso`. Devolve `{online_agora, usuarios_online[], primeiro_registro, periodo:{inicio,fim,granularidade}, kpis:{usuarios, acessos, acessos_por_usuario}, serie:[{rotulo, acessos, usuarios}], por_tela:[{tela, rota, acessos, usuarios}], ranking:[{matricula, nome, acessos, dias_ativos, ultimo_acesso, tela_top}]}`. Erros no shape do `apiFetch` (`err.status` + `err.message`).
- Placeholder `?` (pyodbc), árvore `api/`. Horário do banco é o relógio de Brasília (`GETDATE()`), igual ao resto do Orquestra.
- Decisões descartadas (1 linha cada): LOGIN/LOGOUT no sistema inteiro (fora do escopo pedido); medir por middleware de API (conta requisição, não tela); tabela de resumo diário (volume de dezenas de usuários não justifica; consulta direta com índice); guardar IP/UA (LGPD sem necessidade).

## 5. Modelo de dados
Migration `141_uso_busca_vendas.sql` (idempotente, etapa 6c do `deploy.sh`) + `142_versao_uso_busca_vendas.sql` (padrão da 140). **Versão 2.6.2**, não 2.7.0: o `develop` já usa 2.7.0+ e o `etl_versao_ferramenta` ignora (SKIP) o registro cuja versão ou título já exista — um 2.7.0 aqui faria a promoção do `develop` pular a própria versão. Reconciliar ao promover:
- `dbo.etl_uso_evento`: `id BIGINT IDENTITY PK`, `matricula VARCHAR(20) NOT NULL`, `modulo VARCHAR(30) NOT NULL DEFAULT 'busca_vendas'`, `rota VARCHAR(120) NOT NULL`, `tela VARCHAR(80) NOT NULL`, `detalhe VARCHAR(40) NULL`, `ocorrido_em DATETIME NOT NULL DEFAULT GETDATE()`. Índices `(ocorrido_em)` e `(matricula, ocorrido_em)`. Sem FK para `etl_usuario` (o evento sobrevive à remoção do usuário).
- `dbo.etl_uso_presenca`: `matricula VARCHAR(20) PK`, `rota VARCHAR(120)`, `atualizado_em DATETIME NOT NULL`.
- Recurso `caixa_seguro_uso` semeado no perfil `admin` por `MERGE`.
- ⚠️ Numeração: o `develop` usa 141+ com outros nomes; o `migrate.py` controla por NOME. Reconciliar ao promover o `develop` (mesma nota da 140).

## 6. Fases (uma PR, um commit por fase — a feature é pequena e o solicitante pediu uma PR; cada commit deixa a árvore verde)
### F1 — Front com dados simulados
- Entregável: tela `Uso.tsx`, item de menu, rota, entrada no RBAC e `UsoTracker` apontando para um cliente que, nesta fase, devolve um mock tipado do contrato da §4 atrás do `apiFetch`/camada de `caixa/lib/uso.ts`.
- Aceite: com a permissão, o item aparece e a tela renderiza KPIs, série, por tela e ranking nos temas claro e escuro; sem a permissão o item não aparece e a rota redireciona; estados carregando/vazio/erro; sem rolagem horizontal da página a 360 px.
- Validação: `impeccable` (critique + audit + polish) e Chrome nos dois temas e em mobile; `tsc -b`, eslint comparado ao baseline do HEAD (zero erros novos), build; pytest do anti-drift de RBAC.
- Portão: se o front não passar no `impeccable`, o backend não começa.

### F2 — Backend
- Entregável: migration, `routers/caixa_uso.py`, registro em `main.py`, testes.
- Aceite: acesso grava uma linha e o segundo no mesmo minuto não grava outra; rota desconhecida é ignorada; matrícula do corpo é ignorada; presença atualiza uma única linha; resumo devolve o contrato nas três granularidades; 403 sem `caixa_seguro_uso`; `POST` exige `tela_caixa_seguro`.
- Validação: pytest (novos + suíte), migration rodada **duas vezes** no DEV, revisão de SQL (placeholder `?`).

### F3 — Integração, versão e documentação
- Entregável: troca do mock pelo real, `dist/` recompilado, nota de versão, release notes (`docs/release-notes/`), memória do projeto.
- Aceite: ponta a ponta no DEV (navegar → evento → tela mostra); relogin após conceder a permissão.
- Validação: `tsc -b` + eslint + build + pytest, **revisão adversarial** (agente `qa-adversarial`) antes de abrir a PR; PR `feat: monitoramento de uso do módulo Busca & Vendas`. **Merge só após aprovação do Carlos.**

## 7. Riscos e mitigações
| # | Risco | Impacto | Mitigação |
|---|-------|---------|-----------|
| 1 | Perda de eventos (bloqueador de rede, aba fechada, offline) | Subcontagem | Falha silenciosa e documentada; a tela diz que mede aberturas de tela e não é auditoria |
| 2 | Disparo duplo (StrictMode, navegação rápida) | Acesso inflado | Dedupe no front (30 min por rota) e no servidor (`NOT EXISTS`) |
| 3 | Rota nova no módulo sem registro no servidor | Tela não medida, sem erro | Teste anti-drift lê as rotas `caixa-seguro/*` do `App.tsx` e exige entrada no registro |
| 4 | Permissão nova não aparece para quem já está logado | "Não vejo o menu" | Gotcha conhecido (permissão exige relogin): smoke e nota de versão dizem isso |
| 5 | Segunda lista de RBAC esquecida | Admin não governa a permissão | Entrada em `rbacRecursos.ts` + teste existente |
| 6 | Dados pessoais (matrícula/nome) sem retenção definida | LGPD | Só `caixa_seguro_uso` vê; sem IP/UA; retenção entra como pendência explícita |
| 7 | Colisão de numeração com o `develop` | Confusão na promoção | `migrate.py` controla por nome; nota na migration |
| 8 | `dist/` esquecida | PR invisível em produção | Rebuild no commit da F3 |
| 9 | Consulta lenta com o crescimento | Tela lenta | Índices por `ocorrido_em` e `(matricula, ocorrido_em)`; consultas sempre com janela de datas |

## 8. Smoke pós-deploy
a) Aplicar a migration (etapa 6c, responder **s**) e conferir `etl_uso_evento` e `etl_uso_presenca`.
b) Em Admin, conceder `caixa_seguro_uso` a um perfil de teste; o usuário faz logout/login.
c) Esse usuário vê "Uso do módulo" no menu do módulo; um usuário sem a permissão não vê.
d) Abrir Consulta de Propostas, Monitoramento, Portabilidades: a tela de Uso mostra as aberturas, e recarregar a mesma tela em seguida não duplica.
e) "Online agora" mostra o usuário e deixa de mostrá-lo cerca de 10 min após fechar a aba.
f) Alternar Dia/Mês/Ano; no 1º dia, Mês e Ano mostram só o dia de hoje e a data de início do registro.
g) Tema escuro e celular sem rolagem horizontal da página.

## 9. Pendências e decisões em aberto
- **Retenção** dos eventos (proposta: 24 meses, com expurgo por job) — decisão do Carlos/solicitante; fora desta entrega.
- Se a medição de **ações dentro da tela** (cliques em card, buscas) entra num próximo ciclo.
- Quem, além dos administradores, receberá `caixa_seguro_uso` (decisão de acesso, feita no Admin após o deploy).
