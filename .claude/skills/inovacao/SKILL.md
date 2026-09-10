---
name: inovacao
description: Processo estruturado para elevar um produto existente com melhorias priorizadas — de quick wins a diferenciais de mercado. Use quando o usuário pedir "o que dá pra melhorar?", "traga ideias", "me surpreenda", "como deixar esse produto melhor/mais completo", "brainstorm", "roadmap de melhorias", "innovation", "feature ideas", "improve this product", "what's next". Aplica-se aos projetos web (Orquestra, LC Decorações, NexxaFarma), apps e automações (n8n LC Segurança). Toda ideia sai com valor, esforço, risco e dependências — e só entra no backlog com dono e critério de sucesso.
---

# Inovação — elevar um produto com ideias acionáveis

## Quando usar
- O usuário quer melhorar um produto que JÁ existe e funciona ("o que dá pra melhorar no Orquestra?", "traga ideias pro LC Decorações", "surpreenda").
- Fim de um ciclo de features, antes de definir o próximo backlog.
- NÃO usar para projeto novo do zero — isso é `entrevista-projeto`. NÃO usar para bug/ajuste pontual — isso é trabalho direto.

## Processo
1. **Mapear o que o produto já tem.** Ler o código real, não supor: rotas do front (React Router no Orquestra, app/ no Next.js), endpoints da API, tabelas/migrations, workflows n8n ligados ao produto (`mcp__n8n-mcp__n8n_list_workflows`). Consultar a memória persistente (arquivos em `/root/.claude/projects/-root/memory/`) — ela registra o que está em produção, pendente e em branch. Produzir um inventário de 10-20 linhas: o que existe, o que está meio-feito, o que dói.
2. **Gerar candidatas a partir das fontes deste ambiente** (não de generalidades). Percorrer cada fonte e perguntar "cabe aqui?":
   - **Assistente IA embutido (padrão caixa_chat)**: backend próprio FastAPI→LLM, config e toggle no admin, chave cifrada no banco, log de chamadas em tabela. Já existe no /caixa-seguro do Orquestra e é replicável a qualquer produto (ex.: assistente de orçamento no LC Decorações, explicador de execuções falhas no Orquestra). Consultar `claude-api` para modelo/custo ANTES de propor.
   - **Automação n8n**: rotinas manuais do usuário final que viram workflow (padrões já provados: resumo diário WhatsApp da NexxaFarma, lembrete de saldo do LC Decorações). O swarm LC Segurança já roda 33+ workflows.
   - **Dashboards/KPIs**: telas de dados sem visualização, ou listas que mereciam gráfico/stat tile — propor com `dataviz` como base.
   - **Exportações**: XLSX e jsPDF já são usados nos projetos — relatórios, comprovantes, extratos são melhorias baratas.
   - **Notificações WhatsApp**: padrão NexxaFarma/LC (endpoint /api/... chamado por workflow n8n agendado, log em tabela tipo notify_runs).
   - **Integração entre os sistemas do ambiente** (MCP/API): ex.: evento num sistema dispara ação noutro via n8n.
   - **UX/visual**: telas funcionais mas datadas — candidatas a `design-impactante-corporativo`.
3. **Filtrar para 3-7 melhorias** e classificar em TRÊS faixas:
   - **Rápidas (dias)**: 1 PR, sem migration arriscada, sem dependência externa nova.
   - **Estruturais (semanas)**: mudam arquitetura/modelo de dados, exigem fases F1..Fn.
   - **Diferenciais de mercado**: colocam o produto à frente de concorrentes (IA embutida, automação proativa, integração única).
4. **Para CADA ideia, preencher a ficha** (sem ficha completa a ideia morre aqui):
   - Valor para o usuário FINAL (não para o dev): que dor resolve, em uma frase concreta.
   - Esforço: dias/semanas + o que toca (front, API, migration, workflow n8n, wheel nova).
   - Risco: técnico (ex.: dep nova sem wheel offline) e de produto (ninguém usar).
   - Dependências: outra feature, credencial, acesso, decisão do usuário.
5. **Priorizar COM o usuário via AskUserQuestion**: apresentar a tabela (ideia × faixa × valor × esforço × risco) e perguntar quais entram agora, quais ficam no radar, quais morrem. Nunca decidir sozinho.
6. **Transformar as escolhidas em spec via `gerador-spec`**: cada ideia aprovada vira spec com fases F1..Fn, PR por fase, critérios de aceite. Registrar dono e critério de sucesso mensurável — **ideia sem dono e sem critério de sucesso não entra no backlog**.

## Checklist
- [ ] Inventário do produto feito lendo código real + memória persistente (não de cabeça)
- [ ] Todas as 7 fontes de ideia do ambiente percorridas (IA embutida, n8n, dataviz, exportação, WhatsApp, integração, UX)
- [ ] 3-7 ideias, com pelo menos 1 em cada faixa (rápida / estrutural / diferencial)
- [ ] Ficha completa por ideia: valor p/ usuário final, esforço, risco, dependências
- [ ] Nenhuma ideia duplica algo que já existe ou está em branch (checar memória)
- [ ] Priorização feita com AskUserQuestion — usuário escolheu explicitamente
- [ ] Cada ideia aprovada tem dono e critério de sucesso mensurável
- [ ] Escolhidas viraram spec via `gerador-spec` (docs/spec-<feature>.md)

## Integrações
- **`gerador-spec`**: destino obrigatório das ideias aprovadas (passo 6).
- **`entrevista-projeto`**: se uma ideia "diferencial" for grande/ambígua demais, rodar entrevista antes da spec.
- **`claude-api`**: consultar SEMPRE antes de propor feature com LLM — modelo, preço, limites; nunca estimar custo de memória.
- **`dataviz`**: base de qualquer proposta de dashboard/KPI/gráfico (paleta validada, stat tiles).
- **`ui-ux-pro-max:ui-ux-pro-max`** e **`design-impactante-corporativo`**: propostas de redesign/UX.
- **`n8n` + `n8n-mcp-skills:using-n8n-mcp-skills`**: qualquer ideia de automação — listar workflows existentes antes de propor (não duplicar os 33+ ativos).
- **`seguranca`**: ideias que tocam auth, dados pessoais (LGPD!) ou chaves de API ganham nota de risco vinda desta skill.
- **`performance`**: se o inventário revelar lentidão, "deixar rápido" pode ser uma das ideias rápidas — medir antes.

## Armadilhas conhecidas deste ambiente
- **Wheel offline no Orquestra**: o pip do deploy roda `--no-index --find-links=wheels`. Ideia que exige lib Python nova = baixar wheel p/ `api/wheels/` e versionar no git. Isso É esforço e risco — declarar na ficha.
- **Migrations do Orquestra** são T-SQL idempotentes em `sql/migrations`, aplicadas na etapa 6c do deploy.sh. Ideia estrutural com mudança de schema já nasce com essa dependência.
- **dist/ commitada no Orquestra**: qualquer ideia de front implica rebuild + commit da dist no deploy.
- **Tema escopado**: no Orquestra o padrão são os tokens canvas/panel/edge/ink; o shadcn/Radix da CAIXA vive escopado em `.caixa-theme`. Ideia visual nova deve declarar em qual mundo vive — vazamento de especificidade CSS já causou overlay branco em produção.
- **Padrão caixa_chat de IA**: chave cifrada + toggle no admin + log em tabela NÃO são opcionais ao replicar — são o que torna a feature operável e auditável.
- **WhatsApp**: o padrão comprovado é endpoint no produto + workflow n8n agendado chamando-o, com log (ex.: notify_runs). Não propor envio direto do app sem esse contorno.
- **Memória persistente diz o que já está em branch** (ex.: catálogo do LC Decorações não deployado): propor algo que já existe meio-pronto queima credibilidade — checar antes.

## O que NÃO fazer
- NÃO despejar 20 ideias genéricas ("adicionar testes", "melhorar UX") — cada ideia precisa ser específica do produto e caber numa das 3 faixas.
- NÃO colocar ideia no backlog sem dono e critério de sucesso — regra dura, sem exceção.
- NÃO propor automação que duplique workflow n8n existente — listar antes.
- NÃO estimar custo/modelo de LLM de memória — `claude-api` primeiro.
- NÃO implementar nada nesta skill: o entregável é a tabela priorizada + specs geradas. Código só depois, seguindo o fluxo de fases com PR e revisão adversarial.
- NÃO decidir prioridade pelo usuário — a escolha é dele, via AskUserQuestion.
