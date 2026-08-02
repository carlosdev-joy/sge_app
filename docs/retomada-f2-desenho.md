# Desenho técnico — F2: registro de execução por data de referência
Spec: `docs/spec-dependencias-pipelines.md` §5-F2 · Base: main `5c85655` · Escopo: **só** `dags/etl_dag_factory.py` (+1 migration nova) · Zero mudança de comportamento de disparo

## 0. Princípios herdados da reversão (regem todas as decisões abaixo)

1. **O estado do DagRun é decidido pelas FOLHAS do grafo** (lição E, PR #229): nenhuma task nova pode ficar downstream de `t_publish_dataset`, e nenhuma trigger_rule de task existente muda.
2. **Chave estável desde o nascimento** (causa-raiz B): a linha nasce com `execution_id` preenchido; linha com `execution_id NULL` é proibida para estados de execução.
3. **Helpers não entram em `default_args`** (GOTCHA F2 antiga: `consts_str` sai antes de `helpers_str` → NameError no import; guardado por `test_default_args_nao_referencia_helper`).
4. **`ONE_FAILED` só enxerga upstream direto** — fiação idêntica à do `teams_error`, nunca pendurada só no `publish_dataset`.
5. Registro é observabilidade: **nunca derruba a carga** (try/except com log explícito).
6. Comentários no código GERADO não citam identificadores de trigger_rule/schedule (quebra asserts de substring de testes de não-regressão — padrão que se repetiu 3x).

---

## 1. Onde nasce a linha e com que chave

**Nasce dentro do `check_agenda`** (callable do `ShortCircuitOperator` já existente, único nó raiz de toda DAG gerada), refatorado em duas camadas:

```
_check_agenda_regras(context) -> (bool, motivo)   # as 5 regras atuais, intactas
check_agenda(context):                            # wrapper: decide E registra
    ok, motivo = _check_agenda_regras(...)
    _registrar_execucao('EXECUTANDO' if ok else 'PULADO', context, motivo=motivo)
    return ok
```

- **Nenhuma task nova para o início.** A alternativa da 1ª execução (task `registrar_inicio` entre `check_agenda` e as raízes) funcionava, mas reescreve o `root_anchor` em 5 pontos de fiação distintos (deps explícitas, ondas, sensores, teams_start, decisão-raiz) — superfície de grafo desnecessária. No wrapper, o nascimento da linha tem **um único ponto**, e o writer é único (múltiplas raízes paralelas com `log_start` disputariam o INSERT da mesma chave — ruído de chave duplicada, eco da causa B).
- **Chave: `execution_id = context['run_id']` DESDE O INSERT.** Nunca `ts_nodash` (a DAG antiga atualizava por `ts_nodash` e o push inseria com NULL → nunca casavam → 2 linhas, defeito B1). Nunca reserva com NULL — além do órfão eterno em EXECUTANDO, o índice único `ux_pipe_exec` trata dois NULL como duplicados no SQL Server: duas linhas NULL na mesma `(pipeline, data)` são fisicamente impossíveis, ou seja, o modelo de reserva NULL já era incompatível com o próprio índice da 067.
- Upsert por chave completa: `UPDATE ... WHERE pipeline_name=%s AND data_referencia=%s AND execution_id=%s`; `rowcount==0` → `INSERT`. Placeholder `%s` (pymssql — árvore `dags/`, GOTCHA registrado).
- `EXECUTANDO` grava `inicio=GETDATE()`, `fim=NULL` (re-tentativa de run inteiro limpo reseta a janela); `disparado_por` = `conf['disparado_por']` > `'manual'` (run_id começa com `manual`) > `'dataset'` (começa com `dataset_triggered`) > `'agenda'`.
- **Contrato para a F3 (documentado no helper e na spec):** quem quiser criar linha antes do run (push/guardiã) deve calcular o `run_id` primeiro, inserir JÁ com ele e passar o mesmo valor ao `trigger_dag(run_id=...)`. Reserva com NULL fica proibida por contrato.

**Defeitos evitados:** B1 (duas linhas por corrida; reserva presa em EXECUTANDO), colisão de NULLs no índice único, corrida de INSERT entre raízes paralelas.

## 2. Como FALHA é gravada

**`on_failure_callback` de NADA.** Callback em `default_args` = NameError no import (princípio 3); callback por task é invisível no grafo e não tem garantia de ordem. Em vez disso:

- Task nova `t_reg_falha` (`task_id="registrar_falha"`, `trigger_rule=ONE_FAILED`), **incondicional** (existe mesmo com `envia_msg_erro=0` — o registro não é notificação).
- Fiação **espelho exato do `teams_error`**: `end_tasks >> t_reg_falha` + cada `t_notif_* >> t_reg_falha` + cada `t_sql_* >> t_reg_falha` + cada `t_wait_* >> t_reg_falha`. Nunca no `publish_dataset` (numa falha ele nem roda — a task ficaria cega, princípio 4).
- Por que isso **não** vira folha perigosa nem muda folha existente: `t_reg_falha` é folha nova **paralela** ao `publish_dataset`, que continua sendo a folha que carrega a falha (`upstream_failed` → DagRun FAILED). Sem falha, `ONE_FAILED` deixa `t_reg_falha` SKIPPED — folha skipped não altera o estado do run. É o mesmo padrão do `teams_error`, já provado em produção. O erro da reversão foi o oposto: pendurar o fechamento **depois** do `publish_dataset` com ALL_DONE, rebaixando a folha que carregava a falha a nó interno.
- Escreve `FALHA` por upsert na mesma chave (a linha EXECUTANDO já existe; se não existir — degradação anterior — insere). `fim=GETDATE()`, `motivo` lista as tasks em estado failed via `dag_run.get_task_instances()` (clipado a 500).
- Cobertura: falha de job (`log_end` levanta), falha de `log_start` (propaga ao `t_end` que levanta), falha de decisão/notificação/sql/aguarde — todos chegam por upstream direto de `t_reg_falha`.

**E o SUCESSO** (mesma pergunta pelo avesso): **nenhuma task nova.** `t_publish_dataset` deixa de ser `EmptyOperator` e vira `PythonOperator` com o MESMO `task_id`, MESMA trigger_rule (inclusive a condicional de decisão), MESMOS `outlets` e MESMA posição — o callable grava `SUCESSO` (degradado, nunca levanta) e o Dataset continua publicado no sucesso da task. Grafo topologicamente idêntico; a folha que carrega falha segue sendo ela.
Caso-borda herdado da correção B (decisão-raiz com ramo vazio → publish SKIPPED → linha presa em EXECUTANDO): resolvido no **`t_flow_close`**, que já existe exatamente quando há decisão, já é ALL_DONE, já é folha paralela segura e já lê os estados do run — ganha um passo: se nenhuma task failed/upstream_failed e o publish foi skipped, fecha a linha como `PULADO` com motivo `'decisao pulou todos os jobs'`. Se houve falha, não escreve nada (é do `t_reg_falha`).

**Defeitos evitados:** DagRun VERDE em pipeline que falhou (o catastrófico da reversão), NameError de helper em default_args, cegueira do ONE_FAILED, corrida presa em EXECUTANDO no ramo vazio.

## 3. Como PULADO é gravado

- No ramo False do `check_agenda` (item 1): **uma única escrita**, `status='PULADO'`, **`inicio=NULL` e `fim=NULL`** — pulado não começou nem terminou. É a correção do defeito do `COALESCE(inicio, criado_em)`: com `criado_em NOT NULL DEFAULT GETDATE()`, qualquer leitura "mais recente" via COALESCE recaía no criado_em e o PULADO voltava a ser o mais novo, mascarando o SUCESSO do dia.
- **Sem mascarar SUCESSO anterior por construção:** o PULADO carrega o `run_id` do próprio run pulado → é **outra linha**, nunca UPDATE sobre a linha SUCESSO de um run anterior (chaves diferentes). E o contrato de leitura gravado na tabela/spec para a F3 é **`EXISTS (status='SUCESSO' AND data_referencia=D)`** — nunca "a linha mais recente". As duas camadas juntas fecham o defeito; a primeira sozinha já impede a escrita destrutiva.
- `motivo` específico por regra (horário fora da lista / dia+hora do mês / blackout / fim de semana / calendário) — `_check_agenda_regras` devolve `(False, motivo)` em cada saída, mantendo o ponto único de escrita da correção A sem perder a causa (que a versão revertida generalizava numa string só).
- Nunca grava EXECUTANDO antes de decidir: a escrita acontece **depois** da avaliação das regras, uma vez só.

**Defeitos evitados:** COALESCE(criado_em) mascarando SUCESSO; PULADO "mais recente" em pipeline N×/dia; EXECUTANDO fantasma de corrida pulada.

## 4. Herança de `conf['data_referencia']`

Helper gerado `_data_referencia(context)`, usado por **todos** os writers (check_agenda, publish, reg_falha, flow_close):

1. **Herança:** `dag_run.conf.get('data_referencia')` — se presente e parseável, prevalece (é o carimbo do ODATE do predecessor, decisão nº1 do usuário). Valor inválido → log `[EXEC] data_referencia herdada invalida ... recalculando` e cai no cálculo (nunca aborta).
2. **Cálculo:** `utils.data_referencia.calcular(momento_logico, virada)`, onde:
   - `momento_logico` = `data_interval_end or logical_date` convertido a `LOCAL_TZ` — **nunca relógio de parede**: atraso de fila ou rerun no dia seguinte não pode mudar a data (é também o que faz o item 5 funcionar). Fallback `pendulum.now(LOCAL_TZ)` só se o contexto não tiver nenhum dos dois.
   - `virada` = `SELECT COALESCE(CONVERT(VARCHAR(8), p.hora_virada, 108), c.config_value) FROM etl_pipeline p LEFT JOIN etl_app_config c ON c.config_key='dependencia_hora_virada' WHERE p.pipeline_name=%s`; qualquer erro (coluna inexistente sem a 067, banco fora) → `parse_virada(None)` = 00:00 = comportamento de hoje.

Na F2 a herança já é exercível **sem F3**: `Trigger DAG w/ config` com `{"data_referencia": "AAAA-MM-DD"}` — é o entregável "disparo manual aceita a data" da spec.

**Defeitos evitados:** corrida que atravessa a meia-noite com datas divergentes entre pai e filho (motivador da spec); parte da causa D (guardiã e execução com premissas de data diferentes — a F4 passará a usar este mesmo helper como canônico).

## 5. Rerun após Clear (FALHA → SUCESSO)

A regressão do `apenas_se_executando` (plantonista corrige, dá Clear, DAG verde, linha FALHA para sempre, cadeia morta em silêncio) morre por **remoção da guarda**, que deixa de ser necessária:

- Clear preserva o `run_id` → o rerun bate na **mesma linha** (chave `pipeline + data_ref + run_id`); a `data_referencia` recomputada é idêntica porque vem do momento lógico, não do relógio.
- Clear do job falhado limpa também o downstream: `t_reg_falha` é reavaliado (agora sem upstream failed → SKIPPED, não regrava FALHA) e `t_publish_dataset` roda no fim → UPDATE da mesma linha para `SUCESSO`. Ordem garantida pelo grafo, não por guarda de estado.
- Clear do run inteiro: `check_agenda` reescreve `EXECUTANDO` (reseta `inicio`, `fim=NULL`) e o ciclo se repete.
- Transições indevidas que a guarda antiga tentava impedir são impossíveis por estrutura: SUCESSO-sobre-PULADO não ocorre porque o ShortCircuit pula TODO o downstream (inclusive ALL_DONE — comportamento documentado no próprio factory); SUCESSO-e-FALHA no mesmo attempt são mutuamente exclusivos (`ONE_FAILED` × folha de sucesso).
- Limitação documentada: mudar `hora_virada` entre a falha e o Clear muda a data recomputada → linha FALHA órfã na data antiga + linha nova. Aceito; é a F4 (`DATA_DIVERGENTE`) que enxerga isso.

**Defeitos evitados:** a regressão nº2 da 2ª revisão (rerun verde que não vira SUCESSO); e o motivo original da guarda deixa de existir sem reintroduzir o ALL_DONE na folha.

## 6. Degradação se a 067 não existir (deploy parcial de `dags/`)

- `_registrar_execucao` checa `SELECT OBJECT_ID('dbo.etl_pipeline_execucao','U')` antes de escrever (padrão da supervisão DS citado no risco 3 da spec): tabela ausente → `print('[EXEC] migration 067 ausente — execucao nao registrada')` e retorna. Distinto do erro genérico.
- Blindagem dupla: todo o corpo em try/except com `print('[EXEC] Aviso: execucao nao registrada (migration 067 aplicada?): {e}')` — nunca propaga; a decisão do `check_agenda` (True/False) é calculada **antes** e devolvida independentemente do registro.
- A consulta da virada degrada sozinha para 00:00 (item 4) — sem a 067 não existe `hora_virada` nem a config, e o cálculo vira "data do calendário", o comportamento de sempre.
- Consequência honesta: DAG verde, pipeline normal, tabela vazia, avisos no log — mesmo contrato aprovado na revisão da F1 (degradação `None` vs `{}`). Sem `except` que esconde gravação zero com task verde (GOTCHA do placeholder registrado: por isso o log é obrigatório e testado).

**Defeitos evitados:** risco 3 da spec (gravação em tabela inexistente com except mudo); análogo do factory_log órfão (falha silenciosa que vira "timeout" para o operador).

## 7. O que a F2 NÃO faz

- **Não dispara ninguém**: sem `t_disparar_dependentes`, sem `trigger_dag`, sem leitura de `etl_pipeline_dependencia` em runtime (F3).
- Não muda `schedule` de nenhum pipeline; `ExternalTaskSensor` e modo Dataset **permanecem** como estão (removê-los é F3).
- Não mexe nas REGRAS do `check_agenda` (a causa-raiz A — agenda por relógio × disparo por evento — só pode ser tratada quando existir disparo por evento, na F3).
- Não cria estados `AGUARDANDO_DEPENDENCIA`/`NAO_LIBEROU` (F3/F4), não cria guardiã (F4), não toca API/UI/dashboard (F5/F9), não toca `etl_job_execution` (o `ts_nodash` do nível job continua como está — semânticas de `execution_id` distintas entre as duas tabelas, documentado no helper).
- Não altera trigger_rule de nenhuma task existente e não adiciona nada downstream de `t_publish_dataset`.
- Vale para TODOS os pipelines (com e sem dependência) e só passa a existir **após regerar as DAGs** (`force_all`) — ordem de deploy já registrada.

## 8. ACHADO NOVO desta análise — `execution_id VARCHAR(50)` trunca `run_id`: migration 072 obrigatória

O `run_id` do Airflow tem até 250 chars. `dataset_triggered__<iso com microssegundos>` = **51 chars** (modo Dataset está ATIVO em produção como contorno recomendado) e o futuro `dep__<pai até 200>__<data>` da F3 chega a ~217. Com `VARCHAR(50)`, o INSERT estoura "string would be truncated" → cai no except de degradação → **buraco sistemático e silencioso** exatamente nos runs disparados por dependência. Truncar no código (`[:50]`) colidiria prefixos no índice único — inaceitável.

**Migration `072_execution_id_250.sql`** (idempotente, etapa 6c): se `sys.columns.max_length < 250` → `DROP INDEX ux_pipe_exec` → `ALTER COLUMN execution_id VARCHAR(250) NULL` → recria `ux_pipe_exec`. Chave do índice ≈ 653 bytes < limite de 1700. Pré-requisito da F2, aplicada no dev antes dos cenários.

## 9. Contrato de leitura (gravado agora, consumido na F3)

Comentário na tabela + docstring do helper + spec: a condição de liberação é `EXISTS(pipeline=P AND data_referencia=D AND status='SUCESSO')` — **nunca** "linha mais recente", **nunca** `COALESCE(inicio, criado_em)`. PULADO/FALHA não negam um SUCESSO existente da mesma data; N execuções no dia = N linhas.

## 10. Testes unitários (pytest, DAG gerada via `_generate_dag_source` com Airflow stubado — técnica já usada em `tests/test_dag_factory_decisao.py`)

1. **Compilação** da DAG gerada (`compile()`) nas combinações: simples, decisão binária/switch, notificação+sql, aguarde, sensores (depends_on CSV), modo Dataset, horários específicos — baseline: zero falhas novas vs HEAD.
2. **Chave**: o bloco de registro usa `context['run_id']`; `ts_nodash` ausente do registro de pipeline (regressão B1); nenhum `[:50]`.
3. **Folhas** (guarda estática da lição E): parser das `dep_lines` do fonte gerado computa o conjunto de folhas; asserts: `t_publish_dataset` continua folha; folha nova = só `registrar_falha`; nada downstream de `publish_dataset`; trigger_rules de `publish_dataset`/`teams_*`/`t_end_*` byte-idênticas ao HEAD.
4. **Fiação da falha**: `registrar_falha` presente mesmo com `envia_msg_erro=0`; recebe `end_tasks` + todos `t_notif_/t_sql_/t_wait_`; não recebe `t_publish_dataset`.
5. **publish**: mesmo `task_id`, `outlets=[Dataset(DATASET_URI)]` preservado, agora `PythonOperator` com callable de sucesso.
6. **check_agenda**: ramo False grava PULADO com `inicio` NULL e motivo específico por regra (5 saídas); ramo True grava EXECUTANDO; decisão retorna correta mesmo com hook explodindo (exec do helper com stub que levanta).
7. **Herança**: exec do `_data_referencia` com contexto stubado — conf válida prevalece; inválida recalcula; sem conf usa `data_interval_end` (não relógio: congelar `pendulum.now` e provar).
8. **Degradação**: `OBJECT_ID` None → nenhuma escrita + log citando a 067; exceção nunca propaga.
9. **flow_close**: com decisão, fonte contém o fechamento de linha para publish skipped sem falha; sem decisão, não contém.
10. `test_default_args_nao_referencia_helper` segue verde (nenhum helper em default_args).
11. Módulo puro `data_referencia`: casos da spec (00:00/20:00 × 23:30/00:40) — já existem, mantêm.

## 11. Cenários de EXECUÇÃO no dev (Airflow :8082 + orquestra_dev, runbook `docs/ambiente-dev.md`) — cada um com o SELECT e o estado do DagRun conferidos (a lição-mãe: **olhar a UI do Airflow, não só a tabela**)

| # | Cenário | Prova |
|---|---|---|
| E1 | Pipeline simples roda ok | 1 linha, `execution_id` = run_id da UI, EXECUTANDO→SUCESSO, `inicio/fim`, data_ref = hoje |
| E2 | Job falha → **DagRun VERMELHO** + linha FALHA; Clear do job → DagRun verde + **MESMA linha** vira SUCESSO | itens 2 e 5 (anti-teste da reversão + regressão `apenas_se_executando`) |
| E3 | Blackout ativo (e depois horário fora da lista) → linha PULADO com `inicio` NULL; rodar de novo com sucesso no mesmo dia → `EXISTS SUCESSO na data` = 1 e a linha PULADO intacta | item 3 |
| E4 | Trigger manual com conf `{"data_referencia":"2026-08-05"}` → linha em 05/08, `disparado_por='manual'`; sem conf → data calculada | item 4 |
| E5 | `hora_virada=20:00`, disparo após a virada → data_ref = dia seguinte | item 4 / caso motivador |
| E6 | `sp_rename` na tabela → rodar pipeline → DAG **verde**, log com aviso citando a 067, zero exceção; restaurar e rodar → volta a gravar | item 6 |
| E7 | Decisão-raiz com ramo vazio → publish SKIPPED → flow_close fecha a linha (nada preso em EXECUTANDO); decisão com ramo normal → SUCESSO | item 2 (caso-borda B) |
| E8 | Pipeline em modo Dataset (run_id `dataset_triggered__…` com 51 chars) → linha gravada íntegra, sem truncar | item 8 / migration 072 |
| E9 | Horários específicos 2×/dia → 2 linhas na mesma data, run_ids distintos, sem violação de `ux_pipe_exec` | risco 6 da spec |
| E10 | Clear do run inteiro APÓS a meia-noite → data_ref NÃO muda (momento lógico), mesma linha atualizada | itens 4 e 5 |
| E11 | Migration 072 aplicada 2× → sem erro, índice presente | idempotência |

## 12. Mapa decisão → defeito histórico

| Decisão | Defeito que evita |
|---|---|
| `execution_id = run_id` no INSERT, nunca NULL/`ts_nodash` | B1: duas linhas por corrida; reserva órfã em EXECUTANDO; colisão de NULLs no índice único |
| Nascimento único no `check_agenda` | corrida de INSERT entre raízes; EXECUTANDO fantasma de run pulado |
| FALHA por task ONE_FAILED espelhando `teams_error`, sem callback | NameError de helper em default_args; ONE_FAILED cego no publish |
| SUCESSO dentro do próprio `publish_dataset` (mesma folha) | DagRun VERDE em pipeline que falhou (ALL_DONE em folha — o motivo da reversão) |
| flow_close fecha o ramo-vazio | linha eterna em EXECUTANDO (motivo original do ALL_DONE da correção B) |
| PULADO sem `inicio` + linha própria + contrato EXISTS | COALESCE(criado_em) mascarando SUCESSO; PULADO "mais recente" |
| Sem guarda `apenas_se_executando`; chave estável + momento lógico | rerun verde que não vira SUCESSO (regressão da 2ª revisão) |
| Degradação com OBJECT_ID + log nomeando a 067 | risco 3 (deploy parcial mudo); padrão factory_log órfão |
| Migration 072 (VARCHAR 250) | truncagem silenciosa de `dataset_triggered__*` hoje e `dep__*` na F3 |
| Momento lógico (não relógio) na data_ref | data que muda com atraso de fila/rerun — quebra da corrida |

**Arquivos tocados na implementação:** `dags/etl_dag_factory.py`, `sql/migrations/072_execution_id_250.sql`, `tests/` (novos + ajustes de baseline). PR: `feat: execução de pipeline registrada por data de referência` (retomada F2).
