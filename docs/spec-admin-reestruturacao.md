# Spec: Reestruturação do Admin — Orquestra
Data: 2026-09-24 · Status: concluída (F1–F6; ver §10 Execução)

## 1. Visão
O Admin (`/admin`) cresceu por acréscimo até chegar a **24 abas em 4 grupos**, quase todas num único
`pages/Admin.tsx` de 4.255 linhas. Hoje:
- "Sistema" sozinho tem 12 abas.
- A aba Configurações é uma tabela crua com 36 chaves de 8 assuntos diferentes.
- Um mesmo assunto aparece em várias abas: IA em 5 lugares, mensageria em 4, bancos em 3.
- A aba escolhida não fica no endereço: o F5 volta para Configurações e não dá para linkar uma aba.

O admin gasta tempo **procurando** onde as coisas estão. Com a entrega pronta:
- O Admin passa a ter um **sub-menu lateral com 6 grupos por assunto** e **busca de configuração**.
- **Cada aba ganha endereço próprio** (`/admin/<grupo>/<aba>`).
- Cada parâmetro aparece na aba do seu assunto.
- O que não é administração sai do Admin.

## 2. Escopo
**IN:**
- **Casca nova do Admin.**
  - Sub-menu lateral secundário com 6 grupos, com busca.
  - Link por aba (`/admin/<grupo>/<aba>`), com redirecionamento dos ids antigos.
  - Carregamento sob demanda de cada aba (`React.lazy`).
- **Extração mecânica** das abas de `Admin.tsx` para `components/admin/abas/*.tsx`, sem mudança visual.
- **Novos grupos:**

  | Grupo | Abas |
  |---|---|
  | **Acesso** | Usuários · Perfis e Permissões · Roles do Airflow (hoje as três ficam numa aba só) |
  | **Inteligência Artificial** | Provedor (atual "IA") · Maestro · Agentes · Triagem de chamados (sai da aba ServiceNow) |
  | **Comunicação** | Teams (atual "Notificações", mais o "Testar Webhook" que hoje fica em Configurações) · E-mail · Comunicados |
  | **Integrações & Dados** | Conexões de Dados · ServiceNow (credencial + **Diagnóstico**, que é a antiga "Sonda de descoberta") · Servidor DataStage (SFTP) (atual "Utilitários") · Bancos & Monitoramento (junta "Servidor" e "Monitoramento") |
  | **Pipelines & Ambiente** | Publicar DAGs · Excluir Pipeline · Calendários & Blackout (atual "Agendamento") · Projetos · Tipos de Job · DAGs do sistema (atual "Inventário de DAGs") |
  | **Sistema** | Parâmetros avançados · Versões · Backlog (**fica**: é o repositório oficial das pendências do produto) |

- **Saídas do Admin:**
  - **Fluxo DS** é removida: duplica a aba "Fluxo (XML)" do `/ds-console`, com o mesmo endpoint e o mesmo componente.
  - **Relatório SLA** vai para `/performance`.
  - **Guia de acessos do Power BI** vai para `/powerbi`.
- **Parâmetros avançados** mostra só as chaves **órfãs** (sem aba própria), agrupadas por prefixo. O backend passa a
  recusar a gravação, por esse editor genérico, de chave que tem aba dona. Isso fecha o desvio da validação 422 das abas.
- **⌘K** (CommandPalette) ganha um grupo "Administração" com as abas.
- **Migalhas de texto** que citam "Admin › X" em outras telas passam a ser links reais para o endereço da aba.
  Hoje são 5 arquivos com grafias divergentes. O MANUAL também é atualizado.

**OUT (explícito):**
- **Conteúdo interno das abas.** Formulários, tabelas e ordem dos blocos dentro de cada aba **não mudam**
  (regra de não reordenar tela). Só se move o que está listado acima.
- **Unificar a concessão de agentes.** Hoje ela acontece em dois lugares, Usuários › Permissões extras e Agentes › Acesso.
  Fica para o Backlog.
- **RBAC por aba.** Quem tem `tela_admin` sem `acao_admin` continua vendo todas as abas, e o 403 vem da API.
  Fica para o Backlog: esconder as abas que exigem `acao_admin`.
- **Reescrever o visual das abas** (tipografia, cores). A casca usa os tokens e componentes existentes.
- Mudança no menu principal (`lib/nav.ts`), exceto o que a saída do SLA exigir em `/performance`.
- Backend das abas existentes, exceto a trava de chave com dono (F5).

## 3. Telas (definidas com a skill `impeccable`, modo Operate)

> Contexto do impeccable: o projeto não tem PRODUCT.md/DESIGN.md. A decisão foi tratar a entrega como **refinamento
> dentro do mundo visual já estabelecido**: tokens `canvas/panel/edge/ink` e `components/ui`. Não é mundo novo.
> O modo **Operate** dá o critério: familiaridade merecida, densidade e a mesma linguagem de componentes em toda a casca.

### 3.1 Casca do Admin (`/admin/<grupo>/<aba>`)

**Trabalho:** o admin chega com uma tarefa ("trocar o webhook do Teams", "liberar agente para o fulano") e precisa
**achar a aba em até 1 clique ou 1 busca** e voltar a ela por link ou F5.

**Layout (desktop ≥ 1024 px):**
```
┌ sidebar principal ┐┌──────────────────────── conteúdo ─────────────────────────────┐
│ …                 ││ Administração                                                   │
│                   ││ ┌── sub-menu (240px, sticky) ──┐ ┌─────────────────────────────┐ │
│                   ││ │ [🔎 Buscar no admin…   ⌘/]    │ │ Comunicação › E-mail        │ │
│                   ││ │                              │ │ Remetente, modelos e teste… │ │
│                   ││ │ ACESSO                       │ │ ─────────────────────────── │ │
│                   ││ │   Usuários                   │ │ [conteúdo da aba, intacto]  │ │
│                   ││ │   Perfis e Permissões        │ │                             │ │
│                   ││ │   Roles do Airflow           │ │                             │ │
│                   ││ │ INTELIGÊNCIA ARTIFICIAL      │ │                             │ │
│                   ││ │   Provedor · Maestro · …     │ │                             │ │
│                   ││ │ COMUNICAÇÃO                  │ │                             │ │
│                   ││ │ ▌ E-mail          (ativo)    │ │                             │ │
│                   ││ │ …                            │ │                             │ │
│                   ││ └──────────────────────────────┘ └─────────────────────────────┘ │
└───────────────────┘└────────────────────────────────────────────────────────────────┘
```

**Sub-menu:**
- Coluna de 240 px, `sticky` com rolagem própria.
- Cabeçalhos de grupo usam o mesmo estilo da sidebar principal (caixa alta, `text-dim`, 11 px).
- Itens de 32 px de altura.
- O ativo tem barra lateral de 3 px + fundo `panel`, na cor de destaque do app (`#1A5FA8`).
- **Não** usa ícone por item, para não competir com a sidebar principal e não criar ruído com 22 itens.
- Os grupos ficam sempre abertos: são 22 itens e rolar é mais barato que expandir.

**Cabeçalho da aba:**
- Migalha `Grupo › Aba` (o grupo não é link).
- **Uma frase** dizendo para que serve a aba. A copy fica no registro central.
- Botão "Copiar link" discreto.

**Busca:**
- Filtra no cliente, sem API. Procura em rótulo, grupo, descrição, **palavras-chave** e **chaves de configuração**
  que a aba possui. Exemplo: digitar `teams_webhook` leva à aba Teams.
- Enquanto se digita, o sub-menu vira lista de resultados com o trecho que casou destacado.
- ↑/↓ navegam e Enter abre. Esc limpa a busca e volta ao menu.
- `/` foca a busca quando o foco não está num campo.

**Endereço:**
- `/admin` abre a **última aba visitada** (localStorage, com try/catch). Sem histórico, abre **Acesso › Usuários**.
- Endereço de aba inexistente mostra o estado "Aba não encontrada".
- Os ids antigos (`config`, `sla`, `fluxo_ds`, …) são redirecionados para o endereço novo, ou para a tela nova no caso
  do SLA.

**Registro central** (`lib/adminNav.ts`), uma entrada por aba:
`{ grupo, id, rotulo, descricao, palavrasChave[], chavesConfig[] (prefixos), componente: lazy(() => import(...)) }`.
É a fonte única do sub-menu, da busca, do ⌘K, do redirecionamento e do filtro de chaves órfãs.

**Estados:**
| Estado | Comportamento |
|---|---|
| Carregando a aba (chunk) | Skeleton no painel de conteúdo; o sub-menu e o cabeçalho já aparecem |
| Falha ao carregar o chunk (deploy novo) | Banner "Esta aba foi atualizada. Recarregue a página." + botão Recarregar (ErrorBoundary por aba) |
| Aba não encontrada | "Não encontramos esta aba do admin. Ela pode ter mudado de lugar." + link para a busca |
| Busca sem resultado | "Nada encontrado para "xyz". Tente o nome de um parâmetro, como `email_remetente`, ou de um assunto, como e-mail ou agentes." |
| Sem permissão (`tela_admin` ausente) | Continua como hoje: o guard de rota redireciona. As abas não ganham RBAC nesta entrega (ver OUT) |
| Erro dentro da aba | Continua o tratamento de cada aba. O ErrorBoundary por aba impede que uma aba derrube a casca |

**Responsivo (< 1024 px):**
- O sub-menu vira um **botão seletor** no topo do conteúdo ("Comunicação › E-mail ▾").
- O botão abre um `Sheet` (componente existente) com a busca e a mesma lista.
- Não pode haver rolagem horizontal da página.

**Acessibilidade:**
- Sub-menu com `<nav aria-label="Seções do admin">` e cabeçalhos de grupo como `<h2>`.
- Item ativo com `aria-current="page"`.
- Busca com `role="combobox"`, `aria-expanded` e `aria-activedescendant`. A contagem de resultados vai para uma região
  `aria-live="polite"`.
- Ao trocar de aba, o foco vai para o título da aba.
- Foco visível em todos os itens.
- Contraste AA nos dois temas.

**Copy (rótulos finais):**
- Os rótulos da tabela da §2.
- "Parâmetros avançados" tem o subtítulo: "Chaves sem tela própria. Para as demais, use a busca."

### 3.2 `/performance` ganha "Aderência ao SLA"
O componente atual vai inteiro para o fim da tela, numa seção nova, sem reordenar o que já existe acima. A posição exata
fica para confirmar (ver §9).

### 3.3 `/powerbi` ganha "Como liberar acessos"
O guia atual é texto fixo. Ele entra como **seção recolhível, fechada por padrão**, no fim da tela.

### 3.4 Parâmetros avançados
- A tabela atual é mantida, agrupada por prefixo com cabeçalhos: `app_`, `dependencia_`/`malha_`/`espera_`, `powerbi_`, …
- Mostra só as chaves que nenhuma aba possui.
- A seção "Configurações de fluxo" (FlowConfigSection) continua no fim, como decidido em 2026-09-11.
- Chave com dono que já exista no banco não aparece aqui. A busca por ela leva à aba dona.

## 4. Arquitetura proposta
- **Front:**
  - **Novos arquivos:**
    - `ui-react/src/lib/adminNav.ts`: registro, busca e mapa de redirecionamento.
    - `ui-react/src/components/admin/AdminShell.tsx`: sub-menu, busca, cabeçalho e ErrorBoundary por aba.
    - `components/admin/abas/*.tsx`: uma aba por arquivo, extraída de `pages/Admin.tsx`.
  - **Arquivos alterados:**
    - `pages/Admin.tsx` vira uma casca fina que lê `useParams`.
    - `App.tsx` passa a importar o Admin com `lazy()`. Hoje ele entra no bundle principal.
    - `components/ui/CommandPalette.tsx` ganha o grupo "Administração".
    - `pages/Performance.tsx` e `pages/PowerBI.tsx` recebem o SLA e o guia.
  - **Rota:** `/admin/*` já é curinga em `App.tsx:103`, então o roteador não muda.
- **Back:** `api/routers/admin.py`. As ações `config_upsert` e `config_delete` passam a recusar, com 422 e o nome da aba,
  as chaves cujo prefixo tem dono. A lista de prefixos com dono fica em Python, espelhando `chavesConfig` do registro,
  e é presa por teste (mesmo padrão de `tests/test_rbac_recursos_admin.py`).
- **Dados:** nenhuma tabela nova. Uma migration de versão, conforme a regra de versão automática.
- **Decisões descartadas:**
  - Abas em 2 níveis: o usuário escolheu o sub-menu.
  - Página índice de cards: custa um clique a mais.
  - Filtrar as chaves órfãs no backend: o `config_list` continua devolvendo tudo, e o filtro de exibição é do front.
    O que o backend precisa garantir é a trava na **escrita**.

## 5. Modelo de dados
Sem tabela nova. Migration `NNN_versao_admin_reestruturado.sql` (próximo número livre, hoje o 126), idempotente e aplicada
na etapa 6c do `deploy.sh`. Ela registra a versão da entrega.

## 6. Fases (com tela: front primeiro, validado com impeccable + Chrome antes do backend)

### F1 — Extração mecânica das abas (sem mudança visual)
- **Entregável:** cada aba de `Admin.tsx` num arquivo próprio em `components/admin/abas/`. `Admin.tsx` só importa e
  renderiza, com a mesma navegação de hoje.
- **Inclui:**
  - Mover componentes e helpers compartilhados (`adminPost`, `ConfirmModal`, `Markdown`) para `components/admin/comum.ts(x)`.
  - Mover `RBAC_RECURSOS` para `lib/rbacRecursos.ts`, atualizando o teste que prende as duas listas.
- **Critérios de aceite:**
  - Screenshot de cada uma das 24 abas no DEV, antes e depois, sem diferença visual.
  - `Admin.tsx` com menos de 150 linhas.
  - `tests/test_rbac_recursos_admin.py` verde.
- **Validação:** `tsc -b` + eslint (baseline do HEAD, zero erros novos) + `npm run build` (com `dist/`) + pytest.
- **QA:** `qa-adversarial`.
- **PR:** `refactor(admin): uma aba por arquivo — extração sem mudança visual`.

### F2 — Casca nova: sub-menu, busca e link por aba (FRONT; portão do impeccable)
- **Entregável:** `adminNav.ts` + `AdminShell` + lazy por aba + redirecionamento dos ids antigos + última aba visitada +
  responsivo com Sheet. As abas entram **já nos 6 grupos novos**, com os rótulos novos, e o conteúdo interno fica intacto.
  Nesta fase, "Usuários & Perfis" ainda é uma aba só e ServiceNow ainda contém a triagem.
- **Critérios de aceite:**
  - Dado `/admin/comunicacao/email`, quando der F5, então continua na aba E-mail.
  - Busca por `teams_webhook` → aba Teams.
  - Busca por `xyz` → estado "nada encontrado".
  - `/admin/sistema/config` redireciona para Parâmetros avançados.
  - Em 390 px, nenhuma rolagem horizontal e seletor com Sheet funcionando.
  - Teclado: `/`, ↑/↓, Enter e Esc.
  - Leitor de tela: `aria-current` e combobox.
  - Temas claro e escuro.
- **Validação:** o bloco padrão + `impeccable` (critique + audit + polish) + detector `impeccable detect` + Chrome em
  desktop e mobile. **A F5 não começa sem este portão.**
- **Armadilhas:**
  - `overflow-hidden` num ancestral mata o `sticky` do sub-menu.
  - Nada de `*/` dentro de comentário CSS.
- **PR:** `feat(admin): sub-menu lateral com busca e link por aba`.

### F3 — Remanejamentos de conteúdo entre abas
- **Entregável:**
  - `UsuariosTab` dividida em 3 abas (Usuários · Perfis e Permissões · Roles do Airflow).
  - Triagem de chamados sai de ServiceNow para IA.
  - A Sonda vira seção "Diagnóstico" dentro de ServiceNow, depois da credencial.
  - "Testar Webhook" sai de Configurações para Teams.
  - Servidor e Monitoramento juntos em "Bancos & Monitoramento", com Servidor em cima e Monitoramento embaixo.
- **Critérios de aceite:**
  - Cada bloco movido funciona igual no destino: grava, testa e lista.
  - Nenhum bloco some.
  - Cada movimento tem um comentário no código com a posição anterior.
- **Validação e QA:** bloco padrão + Chrome + `qa-adversarial`.
- **PR:** `feat(admin): cada assunto num lugar só — IA, Teams, Acesso, Bancos`.

### F4 — Saídas do Admin e links reais
- **Entregável:**
  - Fluxo DS removida.
  - SLA em `/performance`.
  - Guia Power BI em `/powerbi` (recolhível).
  - As migalhas "Admin › X" em outras telas (`PainelEmail.tsx`, `PainelNotificacao.tsx`, `Utilitarios.tsx`,
    `Agentes.tsx`, `MaestroTab.tsx`, `fluxoTypes.ts`) viram `<Link>` para o endereço da aba.
  - MANUAL §4.9–4.11 atualizado.
- **Critérios de aceite:**
  - O SLA gera o mesmo relatório que gerava no Admin.
  - `/admin/.../sla` antigo redireciona para `/performance`.
  - Nenhuma migalha de texto sobra (grep).
- **Validação e QA:** bloco padrão + Chrome + `qa-adversarial`.
- **PR:** `feat(admin): SLA, Power BI e Fluxo DS fora do admin; migalhas viram links`.

### F5 — Parâmetros avançados: só as chaves órfãs + trava no backend
- **Entregável:**
  - **Front:** tabela filtrada e agrupada por prefixo.
  - **Back:** `config_upsert` e `config_delete` recusam, com 422, a chave com dono (`{"detail": "A chave email_remetente é gerida em Comunicação › E-mail."}`), e o front mostra o `detail`.
  - Teste pytest prendendo a lista de prefixos com dono ao registro do front.
- **Critérios de aceite:**
  - `email_remetente` não aparece na tabela.
  - O POST direto `config_upsert` com essa chave devolve 422.
  - `app_base_url` continua editável.
  - As abas donas continuam gravando pelas rotas próprias.
- **Validação e QA:** bloco padrão + `qa-adversarial` + `security-review` (trava de escrita).
- **PR:** `feat(admin): parâmetros avançados só com chaves sem dono`.

### F6 — ⌘K, polimento e fechamento
- **Entregável:**
  - Grupo "Administração" no ⌘K.
  - `/simplify` + `impeccable polish` final.
  - Migration de versão.
  - Release note.
  - Smoke em `scripts/`.
  - Memória atualizada (viva + `.claude/memory/`).
  - Pendências do OUT registradas no **Backlog de produção via migration idempotente**
    (`INSERT … WHERE NOT EXISTS` por `titulo` em `dbo.etl_backlog`, tag `admin-reestruturacao`), aplicada na etapa 6c.
- **Critérios de aceite:**
  - ⌘K "e-mail" → aba E-mail.
  - A migration roda 2× sem erro.
- **PR:** `feat(admin): atalho ⌘K para as abas do admin + fechamento`.

## 7. Riscos e mitigações
| # | Risco | Impacto | Mitigação |
|---|-------|---------|-----------|
| 1 | A extração da F1 é um diff enorme em `Admin.tsx` e conflita com qualquer branch em voo que mexa no Admin | Merge doloroso | Hoje nenhuma branch em voo toca `Admin.tsx`/`components/admin` (conferido em 24/09). A F1 sai rápida e sozinha. As próximas specs que tocarem o Admin esperam a F1 |
| 2 | Lazy por aba e deploy novo: chunk antigo some e a aba quebra | Tela branca no meio do uso | ErrorBoundary por aba com "Recarregar" (estado previsto na §3.1) |
| 3 | A trava de chave com dono quebra algum fluxo que hoje grava pelo editor genérico (script, DAG, runbook) | Operação para de conseguir gravar | Antes da F5, grep por `config_upsert` em `dags/`, `scripts/` e docs. A trava vale só para a action genérica, nunca para as rotas das abas |
| 4 | Link antigo ou hábito ("Configurações" como aba inicial) | Admin desorientado no 1º dia | Redirecionamento dos ids antigos, última aba lembrada e release note com "onde foi parar cada aba" |
| 5 | Mover blocos (Testar Webhook, Triagem, Sonda) perde estado ou query compartilhada | Botão que não faz nada no destino | Critério da F3: exercitar cada bloco movido no Chrome contra o DEV, não só renderizar |
| 6 | `powerbi_client_secret` e outras chaves sensíveis continuam visíveis em claro em Parâmetros avançados | Vazamento de segredo | Na F5, mascarar chaves `*_secret`, `*_senha*`, `*_key`, `*_enc`, `*webhook*` com "•••• — preencha para trocar", no mesmo padrão da aba IA |

## 8. Smoke pós-deploy
- **a)** Abrir `/admin`: cai em Acesso › Usuários, ou na última aba visitada.
- **b)** Clicar em Comunicação › E-mail e dar F5: continua em E-mail. Copiar o link, abrir em outra aba: mesma tela.
- **c)** Buscar `teams_webhook_url`: leva a Teams, onde o "Testar Webhook" funciona.
- **d)** Buscar `xyz123`: aparece a mensagem de nada encontrado.
- **e)** IA › Triagem de chamados: liga e desliga, e o valor persiste.
- **f)** ServiceNow › Diagnóstico: roda a sonda e mostra as tabelas.
- **g)** `/performance`: gera a Aderência ao SLA do mês.
- **h)** `/powerbi`: a seção "Como liberar acessos" abre.
- **i)** Sistema › Parâmetros avançados: não lista `email_*` nem `teams_*`, mas lista `app_base_url`.
- **j)** ⌘K "agentes": aparece IA › Agentes.
- **k)** Celular (390 px): o seletor abre o Sheet e navega.

## 9. Decisões (fechadas em 2026-09-24)
1. **Aba inicial sem histórico:** Acesso › Usuários; depois vale a última aba visitada.
2. **SLA em `/performance`:** seção no fim da tela, sem reordenar nada.
3. **FlowConfigSection:** fica no fim de Parâmetros avançados (mantém decisão de 11/09).
4. **Pendências → Backlog de PRODUÇÃO via migration** idempotente (não mais na memória). Vale para toda pendência identificada daqui em diante no Orquestra.

## 10. Execução
| Fase | PR | Entrega |
|---|---|---|
| F1 | #449 | Extração mecânica: `Admin.tsx` de 4.255 para 129 linhas, uma aba por arquivo |
| F2 | #450 | `lib/adminNav.ts` + `AdminShell`: sub-menu, busca, link por aba, lazy, última aba, Sheet < 1024 px |
| F3 | #451 | Acesso em 3 abas, Triagem em IA, Diagnóstico em ServiceNow, webhook padrão em Teams, Bancos & Monitoramento |
| F4 | #452 | SLA em `/performance`, guia em `/powerbi`, Fluxo DS removida, migalhas viram `<LinkAdmin>`, MANUAL |
| F5 | #453 | Parâmetros avançados só com órfãs + trava 422 de chave com dono no backend |
| F6 | F6 (esta PR) | ⌘K "Administração", migrations 126 (versão 2.4.0) e 127 (backlog), `scripts/smoke_admin.sh`, release note `docs/release-notes/admin-reestruturacao.md` |

**Achados de QA/segurança, por fase (todos corrigidos na própria PR):**
- **F1:** nenhum defeito; 24 abas com `innerText` e nº de elementos idênticos antes/depois no DEV.
- **F2 (2 rodadas):** a troca div × Fragment ao cruzar 1024 px desmontava a aba e apagava o digitado; `/admin` → última
  aba devolvia `null` e desmontava a casca; chaves avulsas (`servicenow_admin_perfis`) não eram achadas; prefixo da
  família abria Parâmetros avançados em vez da aba dona; redirect roubava o foco.
- **F3:** textos em outras telas, na DAG de sync e nas notificações ainda citavam "Admin > Configurações"/"Admin >
  ServiceNow"; o Chrome oferecia a senha de login nos campos do webhook.
- **F4:** mensagens da API e do worker com o caminho velho ("Admin › Utilitários") — normalizadas e presas por teste,
  com exceção de `etl_dag_factory.py`/`dags/generated` (exige republicar → Backlog d).
- **F5 (QA + auditoria de segurança, 2 rodadas):** chave *fullwidth*/BOM/NUL contornava a trava (casava no SQL Server
  CI_AS) → só ASCII; `GET /config` público devolvia `servicenow_senha_enc` e `ia_api_key_enc` → padrões de segredo
  em fonte única; o proxy de dagRuns deixava qualquer executor disparar `etl_admin_manage` como admin → só admin;
  `config_upsert` ecoava o valor; `config_key` não-string dava 500.
- **F6:** ⌘K reusa a busca do registro (`atalhosDaPaleta`), sem lógica duplicada; migrations aplicadas 2× no DEV sem
  duplicar (versão 2.4.0; 10 itens de backlog).

**Pendências → Backlog de produção** (migration `127_backlog_admin_reestruturacao.sql`, tag `admin-reestruturacao`):
- a. [bug/backend/P2] `servicenow.url_valida` aceita outro host via `#`/`?` e a senha vai por Basic auth.
- b. [debt/backend/P2] `/admin/test-webhook`: allowlist de hosts do Teams/Power Automate; sem `url_usada` (`sig`) nem traceback.
- c. [bug/backend/P2] DAG `etl_admin_manage` confia em `conf.requested_by` (rerun por `clearTaskInstances`, role Op).
- d. [debt/datastage/P3] DAGs geradas citam "Admin > Acessos e Comunicacao > Notificacoes" — republicar e tirar a exceção do teste.
- e. [feature/frontend/P3] RBAC por aba (OUT §2).
- f. [debt/frontend/P3] Concessão de agente em dois lugares via `user_perm_set` (OUT §2).
- g. [bug/frontend/P3] Clicar "Admin" na sidebar dentro de uma aba empilha entrada no histórico.
- h. [bug/frontend/P3] Chunk do Admin removido por deploy cai no ErrorBoundary global com erro cru.
- i. [bug/frontend/P3] Badge "Canal padrão: não configurado" ignora a env `TEAMS_WEBHOOK_URL_CVP`.
- j. [debt/backend/P3] `servicenow_proxy` em claro e aceitando `usuário:senha@`.
