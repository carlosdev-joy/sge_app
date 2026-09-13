# Header ORQ F2 — controles e acessibilidade

F1 mergeada no PR408 (085122b). F2 preserva arquitetura e contratos da
especificação `orq-header-notion-spec.md`; changelog permanece para F3.

Busca/tema têm tipo de botão explícito e busca tem nome acessível. Controles
usam alvos40px no mobile e36px no desktop. Perfil e notificações usam popovers
não modais com role dialog, nome, controles identificados e aria-expanded.
Escape dentro do controle/popover fecha e devolve foco ao trigger, sem capturar
Escape de overlays externos. Conteúdo permanece navegável por Tab normal.

Dropdowns cabem em320px via inset lateral8px e rolam quando a altura é pequena.
Notificações apresentam contador no nome acessível. Itens com ação são botões
nativos, ativáveis por Enter/Espaço; itens estáticos não entram na tabulação.
Confirmação/leitura reposiciona foco no sino antes de um botão desaparecer.
Perfil usa ORQ vX e preserva dados e contrato de logout.

## Segurança — superfície e evidências

Entradas: respostas autenticadas de notificações/comunicados e user do store.
Acesso: shell em PrivateRoute; autorização permanece no backend. Risco do diff:
renderização indevida de texto ou acionamento divergente de confirmação/logout.

- Nenhum endpoint/SQL/dependência/env foi criado ou alterado.
- Textos de feed continuam filhos React (incluindo mensagem com tags); sem
  novo HTML cru. Banner mantém renderMarkdown existente sem alteração.
- Consulta, polling30s, refreshOnWindowFocus, toast e mutações existentes
  preservados. Confirmação ainda só em comunicado não confirmado e ação explícita.
- Logout continua POST best-effort, limpeza do store e redirect para login.
- Nenhum dado pessoal novo em log, URL ou persistência; nome do trigger reutiliza
  nomeCompleto já visível. Bancada usa dados fictícios com domínio .invalid.
- CSRF/auth/limites de backend não mudam nesta refatoração de controles.
- Skill embutida security-review não está disponível no ambiente (busca local
  sem resultado); revisão de código pelo auditor-seguranca conforme CLAUDE.md.

## Validação e deploy

Smoke Chromium `scripts/smoke_orq_header_controls.py`: Escape/foco, Enter/Espaço,
contador, read-all, confirmação, banner, texto tratado como texto, perfil,
Ctrl/Cmd+K, tema persistido, falha de logout500 com limpeza local, dois temas e
320/360/768/1440. Regressão reproduzida antes: Escape não fechava notificações.
Smoke F1 cobre layout/navegação. TypeScript/Vite, ESLint e pytest vs baseline.
Frontend dist apenas. Conferência manual: abrir sino/perfil com teclado, Tab
pelas ações, Escape retorna ao trigger; conferir popovers no celular. F3 seguirá
após merge autorizado deste PR. Nenhuma mudança no login ou RBAC.

Evidência: TypeScript/Vite OK; ESLint193 antes/depois, zero novos; pytest5405
passed/50skipped/mesmas8falhas. Revisões adversarial e auditor-seguranca sem
novos defeitos confirmados. Smoke F1 passou nos20 cenários após ampliar controles.
Smoke F2 final aprovado: teclado/perfil/feed/ARIA, responsividade/temas,
leitura/confirmação/banner/logout. Bancada aguarda foco assíncrono existente
da CommandPalette e montagem do login após logout, evitando corridas de teste.
