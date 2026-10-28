---
name: orquestra-uso-busca-vendas
description: Monitoramento de uso do módulo Busca & Vendas (/caixa-seguro/*) — tela "Uso do módulo", recurso caixa_seguro_uso, tabelas etl_uso_evento/etl_uso_presenca; branch feat/uso-busca-vendas a partir da main; v2.6.2, migrations 141/142; PR #527 aguarda aprovação de merge
metadata:
  type: project
---

Tela `/caixa-seguro/uso` ("Uso do módulo"): online agora, acessos e usuários por dia/mês/ano, acessos por tela, ranking. Spec: `docs/spec-uso-busca-vendas.md`. Release notes: `docs/release-notes/uso-busca-vendas.md`. Origem: pedido do solicitante do RITM0117336 ("a partir deste primeiro card construiremos monitoramento de usabilidade") + decisões do Carlos em 28/10/2026 (escopo = tudo de `/caixa-seguro/*`; menu dentro do módulo, habilitável por perfil/usuário no Admin; seguir até a PR, **merge só após aprovação dele**).

**Como funciona:** front `UsoTracker` (nas 5 rotas do módulo + a própria tela) → `POST /caixa/uso/acesso` (dedupe 30 min, cliente e servidor) e `/presenca` (a cada 4 min, aba visível); `GET /caixa/uso/resumo` exige `caixa_seguro_uso`. `api/routers/caixa_uso.py` tem o registro FECHADO de rotas (`ROTAS`); `tests/test_caixa_uso_api.py` lê o `App.tsx` e reprova divergência. Matrícula sempre do token. Sem IP/user-agent.

**Why:** a `etl_sessao` só guarda a sessão corrente e `ultimo_login` só o último — não havia como saber quem usa o módulo. A medição começa na publicação; não há histórico anterior.

**How to apply:**
- Branch `feat/uso-busca-vendas` em `/root/orquestra-uso-busca-vendas` (worktree a partir da `main` `6dcf3b5c`), por decisão do Carlos de não levar nada do `develop`. Ver [[orquestra-pio-card1-foto]].
- Versão **2.6.2** (não 2.7.0): o `develop` usa 2.7.0+ e o `etl_versao_ferramenta` ignora registro com versão/título repetido. Migrations 141/142 colidem em número (não em nome) com o `develop`: reconciliar ao promover.
- Permissão nova exige relogin. `caixa_seguro_uso` nasce só no perfil admin.
- Pendências: retenção/expurgo dos eventos (proposta 24 meses, decisão do solicitante); medir ações dentro da tela; deploy em produção só com autorização do Carlos.
- Validado: pytest 7.2 mil passando + as 8 falhas pré-existentes; T-SQL real em banco descartável (migrations 2×, dedupe, MERGE, períodos); front × contrato real no Playwright nos temas claro/escuro e mobile. NÃO validado em produção nem com o login real de produção (SELECT/INSERT nas tabelas novas).
