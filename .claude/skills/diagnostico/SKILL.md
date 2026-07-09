---
description: >
  Runbook de triagem de incidentes do ORQUESTRA — casos REAIS já diagnosticados e
  suas causas confirmadas. Use PRIMEIRO quando o usuário reportar bug, erro,
  comportamento estranho, "não funciona", "não grava", "disparou duas vezes",
  "sumiu", falha em produção ou print/gravação de erro — antes de investigar do zero.
argument-hint: "<sintoma>"
---

# Diagnóstico — ORQUESTRA

Confira se o sintoma bate com um caso conhecido ANTES de investigar do zero.
Cada caso lista assinatura → causa confirmada → verificação → correção.

## Casos conhecidos (base de conhecimento)

### "Recebi os DOIS cards do Teams (sim E não) na mesma execução"
- **Assinatura**: Grid do Airflow com a decisão VERMELHA (failed) em todo run e os dois
  `RESULTADO_*` verdes; notificações penduradas direto no `check_agenda`.
- **Causa**: DAG publicada com `condition_json` SEM os ramos → notificações viraram
  raízes órfãs; a decisão falha porque os alvos do branch não são downstream dela.
- **Verificar**: aba Code da DAG (procure `t_dec_* >> t_notif_*`); `condition_json` da
  decisão no banco (`ramo_verdadeiro`/`ramo_falso`).
- **Corrigir**: religar sim/não no canvas → Salvar (toast VERDE) → re-publicar. O guard
  do factory hoje RECUSA publicar fluxo com nó órfão (ValueError com o nome do nó).

### "Salvar o fluxo apaga links/config da decisão"
- **Causa raiz (corrigida)**: refetch em background do react-query sobrescrevia o canvas
  com o estado salvo antigo. Fix: `staleTime: Infinity` + guard de `dirty` no useEffect.
- **Se voltar**: conferir se o build do front em produção contém o fix; toast vermelho
  "NÃO salvo (N erros)" = 422 → ler `detail.errors` (nomeia nó + motivo).

### "Cadastro de etapa dá 422 e não grava nada"
- **Causa (corrigida)**: caminho de job único do `/pipelines/jobs/register` descartava
  `condition`/`notify`/`sql_node` → "config ausente". Fix: `_single_job_from_body`.
- **Se voltar**: ler o Response do 422 (`detail.errors`) — o array nomeia item e motivo.

### "DAG some/quebra após publicar" (import error)
- **Assinatura**: publicação "OK" mas DAG com erro de import no Airflow.
- **Causa típica**: referência a `t_end_` de nó especial (NameError) — nós especiais
  concluem em `t_notif_`/`t_dec_`/`t_sql_` (função `_end_ref`).
- **Verificar**: `dag_reconcile` marca `estado='ERRO'` com o traceback na tela de
  publicação; ou `docker compose logs airflow-scheduler | grep -i import`.

### "{linhas} vazio no card do Teams"
- **Causa (corrigida)**: parser esperava `Rows=N`; o DataStage real emite
  `Link: <nome>, N rows` / `Stage: <nome>, N rows`. Agregação = MAX, não SUM.
- **Verificar**: `dsjob -report DETAIL` do job vs. `_ROWS_OUT_PATTERNS` no operador.

### "Dashboard mostra N falhas, painel mostra menos"
- **Causa (corrigida)**: JOIN de ack sem escopo de pipeline (`execution_id` =
  `ts_nodash` repete entre pipelines). Toda leitura por execution_id deve incluir
  `AND pipeline = ...`.

### "heartbeat failed / could not translate host name postgres"
- **Causa**: metadado do Airflow (Postgres interno) — NÃO é o job DataStage (segue
  RUNNING) nem o SQL Server. Tratar como infra/rede; distinguir de ABORTED real.

### Preview/consulta pendurando o banco
- **Padrão obrigatório**: `conn.timeout = N` (config em Admin → Configurações de fluxo),
  `READ UNCOMMITTED`, `SELECT TOP 100` wrapper.

## Se não bater com nenhum caso
1. Reproduzir a geração offline: `_generate_dag_source` é pura — monte os dicts e
   inspecione o wiring (padrão dos testes de factory).
2. Console do navegador + aba Network (status e Response do endpoint).
3. `docker compose logs --tail=50 orquestra-api` e logs do scheduler.
4. Delegar ao agent do domínio (`orquestra-backend`/`-frontend`/`-datastage`).
5. **Ao resolver: adicionar o caso novo NESTA skill** (é a memória do time).
