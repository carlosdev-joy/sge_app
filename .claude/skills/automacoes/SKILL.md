---
name: automacoes
description: Decide ONDE cada automação deve viver (n8n, Airflow/Orquestra, cron do Vercel/Next, GitHub Actions ou agente Claude agendado) e delega a construção à ferramenta certa. Use quando o usuário pedir para criar, agendar, automatizar ou rodar algo recorrente — "automatizar X", "rodar todo dia", "agendar", "cron", "job", "rotina", "webhook", "notificação WhatsApp", "schedule", "recurring task", "scheduled job", "automation". Aplica-se a projetos web (Orquestra, LC Decorações, NexxaFarma), apps e automações de integração (n8n LC Segurança). NÃO use para construir um produto/sistema completo cujo TEMA seja agendamento/reservas — isso é novo-projeto; aqui é tarefa recorrente/integração. Toda automação sai com gatilho, idempotência, log, alerta em falha e kill switch definidos ANTES de construir.
---

# Automações — roteador de onde cada automação vive

## Quando usar
- Qualquer pedido de tarefa recorrente, agendada ou disparada por evento: "todo dia às 9h", "a cada 30 min", "quando chegar um webhook", "avisar no WhatsApp", "sincronizar X com Y".
- Antes de escrever QUALQUER workflow/dag/rota de cron: esta skill decide a plataforma; a construção é delegada (ver Integrações).
- Também ao revisar/migrar automações existentes (ex.: a carga do mart NexxaFarma migrou de GitHub Actions para n8n justamente por decisão deste tipo).

## Processo

1. **Classificar a automação e escolher a plataforma** (tabela de decisão):
   | Natureza | Plataforma | Exemplos reais deste ambiente |
   |---|---|---|
   | Integração entre sistemas, webhooks, notificações WhatsApp/e-mail, ETL leve via API | **n8n (LC Segurança)** | resumo diário NexxaFarma (`3zvOWLgUuMKYd84T`), carga do mart (`4ENn8zabyB4Ydmvm`, 30/30 min, retry 3x) |
   | ETL pesado, cargas SQL Server (milhões de linhas), dependências entre etapas, bcp | **Airflow (Orquestra)** — dag em `/opt/orquestra-dev`, deploy só de `dags/` | módulo Cópia de Dados (139M linhas, bcp_native) |
   | Rotina acoplada ao app Next.js que precisa do código/env do próprio app | **Rota `/api/cron/*` no Vercel** | lembrete-saldo LC Decorações (n8n `ca3tYFUukN04gX6I` chama `/api/cron/lembrete-saldo` às 09:00) |
   | CI/CD: build, lint, testes em PR | **GitHub Actions** | pipelines do sge_app |
   | Tarefa que exige raciocínio de LLM (triagem, resumo com julgamento, revisão) | **Agente Claude agendado** — skill `schedule` (cloud) ou `CronCreate`/`loop` (local) | rotinas de monitoramento/relatório |
   Regra prática: se envolve WhatsApp, webhook ou "ligar sistema A no B" → n8n. Se envolve SQL Server em volume → Airflow. Se precisa do código do app Next → rota de cron chamada pelo n8n (padrão híbrido do lembrete-saldo: lógica no app, agendamento no n8n).

2. **Definir os 5 contratos obrigatórios ANTES de construir** (perguntar ao usuário o que faltar):
   - **Gatilho**: cron (qual horário/fuso), webhook (quem chama, auth) ou manual. Colisão com outras cargas? (o mart roda 30/30 min).
   - **Idempotência**: rodar 2x seguidas não pode duplicar efeito. Padrões: upsert/MERGE, chave de dedupe (data+entidade), checagem "já enviado hoje?" antes de notificar, migrations T-SQL idempotentes no Orquestra.
   - **Observabilidade**: log estruturado em TABELA, não só stdout. Padrões existentes: `notify_runs` (Supabase, resumo diário) e `etl_caixa_chat_log` (Orquestra). Registrar início, fim, status, contagens e erro.
   - **Alerta em falha**: quem fica sabendo e por onde. Padrão: workflow n8n de erro (Error Trigger) → WhatsApp/e-mail; no Airflow, callback de falha; retry com limite (3x como no mart) antes de alertar.
   - **Kill switch**: como desligar em <1 min sem deploy. Padrões: toggle em tabela de config (como `caixa_ia_enabled` no Orquestra), etapa toggleável em UI (como `/admin/notificacoes` no LC Decorações), ou desativar o workflow no n8n. A automação DEVE checar o toggle no início da execução.

3. **Delegar a construção** à skill/plataforma escolhida (nomes exatos na seção Integrações). Não construir workflow n8n "na mão" — sempre via skill `n8n` + pack.

4. **Registrar**: ID do workflow/dag/rota, horário, tabela de log e kill switch na memória persistente (padrão dos arquivos de memória existentes: nexxafarma-resumo-diario.md, lcdecoracoes-lembrete-saldo.md).

5. **Validar em produção com segurança**: execução manual controlada primeiro (no n8n, executar workflow com dados de teste SEM disparar webhook/notificação real), conferir a linha na tabela de log, só então ativar o agendamento.

## Checklist
- [ ] Plataforma escolhida pela tabela de decisão (e justificada em 1 frase para o usuário)
- [ ] Gatilho definido: cron com fuso explícito OU webhook com autenticação
- [ ] Idempotência: rodar 2x não duplica notificação/carga (dedupe testado)
- [ ] Log em tabela (padrão `notify_runs`/`etl_caixa_chat_log`) com status e erro
- [ ] Retry configurado com limite + alerta em falha definido (quem, por onde)
- [ ] Kill switch existe e a automação o consulta no início da execução
- [ ] Nenhum webhook/notificação REAL disparado durante testes
- [ ] ID + horário + tabela de log + kill switch registrados na memória
- [ ] Se substituiu automação antiga, a antiga foi DESLIGADA (não deixar duas rodando)

## Integrações
- **n8n**: invocar a skill local `n8n` e SEMPRE consultar `n8n-mcp-skills:using-n8n-mcp-skills` antes de qualquer tool n8n-mcp; para agendados sem supervisão, `n8n-mcp-skills:n8n-error-handling` é obrigatória; padrões de arquitetura em `n8n-mcp-skills:n8n-workflow-patterns`.
- **Agente Claude agendado**: skill `schedule` para routines na nuvem; ferramenta `CronCreate` (carregar via ToolSearch) ou skill `loop` para recorrência local na sessão.
- **Hooks do harness** ("sempre que eu fizer X no Claude Code"): skill `update-config` — isso é hook em settings.json, não automação de plataforma.
- **Descoberta/planejamento**: se a automação é parte de feature maior, rodar `entrevista-projeto` → `gerador-spec` antes; se toca credenciais, webhooks públicos ou dados pessoais, rodar a skill `seguranca` antes de ativar.
- **Supabase** (LC Decorações/NexxaFarma): tabelas de log e toggles via MCP Supabase (`apply_migration`), nunca SQL manual no dashboard.

## Armadilhas conhecidas deste ambiente
- **n8n LC Segurança é PRODUÇÃO com 33+ workflows ativos**: nunca testar disparando webhook real; instância 2.27.5 em queue-mode; gotcha do alias `redis` na LCNet (serviços novos no swarm podem resolver o alias errado).
- **PAT do GitHub SEM escopo Actions**: não dá para criar/editar/desabilitar workflows de Actions via API — foi por isso que desligar o `etl.yml` do NexxaFarma ficou pendente (exige ação manual do usuário na UI do GitHub). Não prometer automação via Actions sem lembrar disso.
- **Automação migrada ≠ automação antiga desligada**: o mart NexxaFarma roda no n8n mas o `etl.yml` ainda existe no GH — risco de carga dupla. Sempre fechar esse laço.
- **Orquestra tem pip OFFLINE**: dag nova com dependência Python nova exige wheel em `api/wheels/` versionada no git ANTES do deploy; deploy de dag é só `dags/`, mas migration de tabela de log vai em `sql/migrations` (idempotente) e é aplicada na etapa 6c do `deploy.sh`.
- **Rotas `/api/cron` no Vercel precisam de auth**: o padrão lembrete-saldo usa n8n como agendador chamando a rota — a rota deve validar um secret no header, senão qualquer um dispara a notificação.
- **Horário/fuso**: servidores e n8n podem estar em UTC; "09:00" do usuário é horário de Brasília — sempre explicitar o fuso no cron.
- **Notificação sem dedupe** = cliente recebendo WhatsApp duplicado ao reexecutar após falha parcial. Checar "já enviado?" na tabela de log antes de enviar, não depois.

## O que NÃO fazer
- NÃO construir workflow n8n sem passar pelas skills `n8n`/`n8n-mcp-skills` (elas existem exatamente para isso — não duplicar o conhecimento aqui).
- NÃO criar automação sem kill switch e sem log em tabela "porque é simples" — o padrão mínimo vale para tudo.
- NÃO usar GitHub Actions para novo agendamento de negócio (limitação do PAT + histórico do etl.yml); Actions é só CI.
- NÃO agendar agente Claude para algo determinístico que n8n/Airflow fazem melhor e mais barato (LLM só quando há julgamento envolvido).
- NÃO ativar cron sem uma execução manual validada e sem conferir a primeira execução agendada na tabela de log.
- NÃO deixar duas plataformas executando a mesma automação em paralelo durante migração sem janela de corte explícita.
