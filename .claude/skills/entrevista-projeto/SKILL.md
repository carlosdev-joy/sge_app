---
name: entrevista-projeto
description: Entrevista estruturada de descoberta ANTES de qualquer projeto ou feature novo. Use quando o usuário pedir para criar, iniciar, planejar ou tirar do papel um novo projeto, feature, app, site, automação, dashboard, MVP ou POC — ou disser "quero fazer X" sem spec definida. Palavras-chave: entrevista, descoberta, levantamento de requisitos, briefing, kickoff, escopo, discovery, requirements, scoping, definition of ready. Cobre projetos web, app mobile, automação (n8n) e dashboard/BI.
---

## Quando usar
- Antes de QUALQUER projeto/feature novo — web (Orquestra, LC Decorações, NexxaFarma), app mobile, automação n8n ou dashboard/BI.
- Quando o pedido chega vago ("quero uma tela de X", "automatiza Y") sem problema, escopo ou critérios definidos.
- NÃO usar para bugfix, ajuste pontual em feature existente ou tarefa já especificada — vá direto ao trabalho.
- A saída desta skill alimenta a skill **gerador-spec**; nunca pule direto para a spec sem o Definition of Ready.

## Processo
1. **Situar o contexto**: identifique o projeto-alvo antes de perguntar qualquer coisa — Orquestra (/opt/orquestra-dev: React 19 + Tailwind 3.4 tokens canvas/panel/edge/ink, FastAPI + SQL Server, Airflow), LC Decorações/NexxaFarma (Next.js + Supabase cloud), n8n LC Segurança, ou projeto novo. As restrições mudam radicalmente entre eles.
2. **Perguntar em blocos curtos**: máx. 3-4 perguntas por turno. Use **AskUserQuestion** sempre que houver opções fechadas (ex.: marca institucional CAIXA vs neutra; PWA vs nativo; webhook vs cron). Perguntas abertas vão em texto corrido.
3. **Ordem dos blocos**: (a) problema + usuário-alvo + resultado de negócio → (b) escopo IN/OUT → (c) dados e integrações → (d) não-funcionais (segurança, performance, acessibilidade) → (e) restrições (prazo, stack, marca/identidade visual) → (f) critérios de aceite mensuráveis → (g) riscos.
4. **Registrar e repetir de volta**: ao fim de cada bloco, resuma em 2-3 linhas ("Entendi que…") e deixe o usuário corrigir ANTES de avançar. Não acumule 7 blocos para validar só no final.
5. **Usar o banco de perguntas** (abaixo) filtrado pelo tipo. Pule o que o ambiente já responde ou o que o usuário já disse — repetir pergunta respondida queima a entrevista.
6. **Atalho consciente**: se o usuário quiser encurtar, tudo que não foi respondido vira item **ASSUMIDO: <premissa>** explícito no output — nunca lacuna silenciosa.
7. **Encerrar** somente com o Definition of Ready completo (checklist abaixo). Então emita o bloco "Entendimento do Projeto" e ofereça seguir para **gerador-spec**.

## Banco de perguntas por tipo
**Web (Orquestra / LC / Nexxa)**
- Nova rota/módulo ou evolução de tela existente? Qual URL/menu?
- Quem acessa? Precisa de RBAC (no Orquestra: `etl_usuario_permissao` + guard de rota, como no /caixa-seguro)?
- Tema: tokens semânticos neutros (canvas/panel/edge/ink, claro+escuro) ou tema escopado tipo `.caixa-theme`? Precisa de dark mode?
- Dados: quais tabelas/views SQL Server (Orquestra) ou tabelas Supabase (LC/Nexxa)? Exige migration nova?
- Volumetria e concorrência esperadas? Há endpoint FastAPI novo ou reuso?

**App mobile**
- PWA sobre a stack web atual ou app nativo (loja)? Offline-first? Push?
- Autenticação: reusa OTP/e-mail (padrão LC Decorações) ou outra?
- Qual o dispositivo/contexto real de uso (campo, balcão, gestor)?

**Automação n8n**
- Trigger: webhook, cron ou evento? Frequência e volume por execução?
- Já existe workflow parecido entre os 33+ ativos? (verificar com `n8n_list_workflows` ANTES de escopar um novo)
- Falha silenciosa é aceitável? Quem é notificado e por onde? Precisa ser idempotente/reexecutável?
- Credenciais/integrações já existem na instância ou são novas?

**Dashboard/BI**
- Quais KPIs, exatamente, e qual decisão cada um sustenta? Quem é a audiência?
- Fonte e frequência de atualização dos dados (tempo real, 30/30 min como o mart NexxaFarma, diário)?
- Precisa de drill-down/filtros ou é visão executiva estática? Paleta da marca ou neutra?

## Saída: bloco "Entendimento do Projeto"
Emitir em Markdown, nesta ordem — é o contrato de entrada da skill **gerador-spec**:
- **Problema** (1-2 frases, sem solução embutida) · **Usuário-alvo** · **Resultado de negócio**
- **Escopo IN** (bullets) · **Escopo OUT** (bullets — mínimo 3)
- **Dados & integrações** (tabelas, APIs, credenciais, migrations previstas)
- **Não-funcionais** (segurança, performance, acessibilidade — ou N/A justificado)
- **Restrições** (prazo, stack imposta, marca — ex.: institucional CAIXA vs neutro)
- **Critérios de aceite** (cada um mensurável/testável)
- **Riscos** (com mitigação) · **Fases propostas** (F1..Fn, 1 PR por fase) · **Itens ASSUMIDOS**

## Checklist (Definition of Ready)
- [ ] Problema descrito sem solução embutida ("relatório demora 40 min", não "precisamos de cache")
- [ ] Usuário-alvo e resultado de negócio nomeados
- [ ] Escopo OUT explícito com pelo menos 3 exclusões
- [ ] Fontes de dados mapeadas (tabelas/views/APIs) e necessidade de migration decidida
- [ ] Marca/identidade decidida quando há UI (CAIXA escopado vs tokens neutros)
- [ ] Não-funcionais respondidos ou marcados N/A com motivo
- [ ] Todo critério de aceite é verificável (número, comportamento observável ou teste)
- [ ] Riscos listados com mitigação
- [ ] Fases F1..Fn esboçadas, cada uma fechável em 1 PR
- [ ] Entendimento repetido de volta e CONFIRMADO pelo usuário (ou ASSUMIDOs registrados)

## Integrações
- **gerador-spec**: destino obrigatório do bloco "Entendimento do Projeto".
- **AskUserQuestion**: toda pergunta com opções fechadas (marca, trigger, plataforma, prioridade).
- **ui-ux-pro-max:ui-ux-pro-max** e **ui-ux-pro-max:brand**: consulte DURANTE o bloco de restrições visuais para oferecer opções reais de estilo/paleta/tipografia em vez de perguntar no vácuo.
- **dataviz**: em dashboards/BI, use para propor formas de gráfico e validar paleta já na entrevista.
- **n8n** + **n8n-mcp-skills:using-n8n-mcp-skills**: em automações, liste workflows existentes antes de escopar — nunca duplicar os 33+ da LC Segurança.
- **claude-api**: se a feature envolver IA/LLM (ex.: assistentes do /caixa-seguro), consulte para custo/modelo antes de prometer escopo.
- **security-review**, **/code-review**, **verify**, **/simplify**: cite no plano de fases — a revisão adversarial multi-agente antes de cada PR é parte do fluxo padrão, não opcional.
- **update-config**: se a entrevista revelar necessidade de automação do harness (hooks, permissões).

## Armadilhas conhecidas deste ambiente
- **Orquestra tem pip OFFLINE**: dependência Python nova exige wheel em `api/wheels/` commitada. Pergunte sobre deps novas NA ENTREVISTA — descobrir no deploy é tarde.
- **Migrations T-SQL devem ser idempotentes** e entram na etapa 6c do deploy.sh. Mudança de schema decidida cedo evita retrabalho (já houve deploy sem migration aplicada antes do PR #164).
- **dist/ do front é commitada**: fases paralelas mexendo no front geram conflito de merge; sequencie as fases de UI.
- **Marca é decisão, não default**: o tema CAIXA é ESCOPADO em `.caixa-theme`; assumir institucional vs neutro sem perguntar já gerou retrabalho. Sempre feche isso no bloco de restrições.
- **Prioridades mudam**: o usuário traz demandas novas que reordenam o backlog (ex.: 2026-07-08). Pergunte onde o projeto entra em relação ao backlog vigente — inclusive smokes pendentes.
- **O usuário SEMPRE autoriza o merge**: nenhum plano de fases pode prometer merge automático.
- **Baseline de validação**: tsc/eslint comparados com o HEAD (zero erros NOVOS). Se a feature toca código legado com erros pré-existentes, registre isso em Restrições.
- **LC/Nexxa usam Supabase cloud via MCP**: migrations por `apply_migration`, não por arquivo local — o "como" de dados muda por projeto.

## O que NÃO fazer
- Não despejar 10+ perguntas de uma vez — máx. 3-4 por bloco, sempre.
- Não começar a codar, criar branch ou gerar spec antes do DoR completo (ou ASSUMIDOs registrados).
- Não perguntar o que o ambiente já responde (stack do Orquestra, fluxo F1..Fn com PR por fase, commits convencionais pt-BR).
- Não aceitar critérios vagos ("rápido", "bonito", "fácil de usar") — converta em mensuráveis ou devolva a pergunta.
- Não duplicar skills instaladas: automação → n8n/n8n-mcp-skills; design → ui-ux-pro-max; gráficos → dataviz.
- Não pular a repetição do entendimento por bloco — é onde os mal-entendidos morrem baratos.
- Não inflar escopo: se o usuário pedir "só um MVP", o Escopo OUT cresce, não encolhe.
