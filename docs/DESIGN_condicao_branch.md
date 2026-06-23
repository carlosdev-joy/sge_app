# Design — Ramificação condicional em pipelines (nó de "Decisão")

Status: **proposta para avaliação** (Fase 1 / MVP). Decisões já tomadas:
modelo = **nó de Decisão** (nativo do Airflow); condições do MVP = **contagem de
registros (>N)** e **valor de uma query**.

## 1. Objetivo

Permitir que um pipeline desvie o fluxo com base em um dado de runtime:

- **Por contagem**: "se a tabela `X` tiver mais de 10.000 registros, roda o ramo A;
  senão, o ramo B".
- **Por valor de query**: "se `SELECT ... ` retornar `1`, segue pelo caminho X;
  senão, pelo caminho Y".

## 2. Modelo escolhido — nó de Decisão

A condição mora em um **vértice explícito** (não na aresta), espelhando o padrão
nativo do Airflow (`@task.branch`) — auditável, versionável e alinhado à *factory*
que gera a DAG a partir da config no banco.

```
              ┌──────────────┐  verdadeiro → [JobA, JobB]
   ... ──▶──  │  Decisão (?)  │ ─┐
              └──────────────┘  └ falso     → [JobC]
                                   (o ramo não escolhido vira `skipped`)
```

Alternativa descartada: "condição na aresta" (DataStage/SSIS) — exigiria um modelo
de grafo bem mais rico e fugiria do padrão Airflow, sem ganho prático aqui.

## 3. Modelo de dados (migration `043_*`, idempotente)

Um job de decisão é uma linha em `dbo.etl_pipeline_job` com
`job_type = 'decisao'` e um novo campo `condition_json NVARCHAR(MAX)`:

```jsonc
{
  "tipo": "contagem" | "query",
  // tipo = contagem:
  "tabela": "dbo.FatoVendas",      // valida identificador (regex), opcional 3 partes p/ cross-db
  "database": "BI_DW",             // opcional (reusa o padrão de mssql_database)
  // tipo = query:
  "sql": "SELECT MAX(flag) FROM dbo.Controle WHERE ...",  // somente SELECT (read-only)
  "mssql_conn_id": "mssql_default",// reusa a conexão já existente do job
  // comum:
  "operador": "=" | "<>" | ">" | ">=" | "<" | "<=",
  "valor": 10000,
  "ramo_verdadeiro": ["JobA", "JobB"],   // jobs do MESMO pipeline a rodar se condição verdadeira
  "ramo_falso": ["JobC"]                 // jobs a rodar se falsa (pode ser vazio = encerra o ramo)
}
```

- **Fonte da verdade das arestas do branch**: `ramo_verdadeiro`/`ramo_falso`. A
  *factory* cria as arestas `Decisão → (t_start dos jobs do ramo)`; os jobs do ramo
  não precisam duplicar isso no `depends_on_jobs`.
- Degrada graciosamente: se a coluna não existir, a *factory* ignora decisões
  (padrão já usado no projeto).
- Tabela-filha `etl_pipeline_job_param` (026) é o molde caso prefira normalizar; no
  MVP, `condition_json` numa coluna é suficiente e mais simples.

## 4. Avaliação em runtime (infra já existe)

- **Contagem**: `SELECT COUNT_BIG(*) FROM [tabela]` (ou `dm_db_partition_stats` p/
  tabelas grandes), reaproveitando `api/services/monitor_capture.qi/_measure`
  (identificador validado por regex `^[A-Za-z0-9_]+$`, anti-injeção).
- **Valor de query**: roda o `SELECT` via `MsSqlHook`/`SqlOperator`
  (`dags/utils/job_operators.py`) e pega a 1ª célula. **Restrição de segurança**:
  o SQL deve ser read-only (começar com `SELECT`, sem `;`/DML) — validar no backend
  e no operador.
- **Comparação**: `valor_obtido <operador> valor_limite` → `True`/`False`.

## 5. Geração da DAG (factory)

Em `dags/etl_dag_factory.py` (emissão de arestas do modo grafo explícito, ~`:810-829`):

- Para um job `decisao`, em vez do operador normal, emitir um **`BranchPythonOperator`**
  (`t_dec_<job>`) cujo callable:
  1. avalia a condição (contagem/query);
  2. loga a escolha (valor obtido + ramo) na telemetria já existente
     (`etl_job_execution` / XCom);
  3. retorna `["t_start_<j>" for j in (ramo_verdadeiro if cond else ramo_falso)]`.
- Arestas: `up >> t_dec_<job>`; e `t_dec_<job> >> t_start_<j>` para cada `j` dos dois
  ramos. O ramo não escolhido fica `skipped` e propaga.

### A pegadinha nº 1 do Airflow (tratar no gerador)

O `skipped` de um ramo **contamina** as tasks de convergência: uma task de junção
com `trigger_rule` padrão (`all_success`) é **pulada por engano**. Correção canônica:

> Toda task **alcançável a partir de um branch** deve usar
> `trigger_rule = "none_failed_min_one_success"` (terminou tudo, nada falhou, ao
> menos um upstream com sucesso).

A *factory* precisa: (a) computar os jobs alcançáveis a jusante de qualquer decisão;
(b) setar esse `trigger_rule` nos `t_start_*` desses jobs e nas tasks finais
(`publish_dataset`, `teams_end`). Hoje a *factory* só usa `ALL_DONE`/`ONE_FAILED`.

## 6. UI (PipelineFormModal)

- Novo tipo de job **"Decisão"** no wizard (junto de datastage/shell/python/sql).
- Form da decisão: **tipo** (contagem | valor de query), **tabela**/**SQL**,
  **operador**, **valor**, e os dois **ramos** (multiselect dos demais jobs do
  pipeline → verdadeiro / falso).
- Conviver com: validador de ciclo (`jobsHaveCycle`) — incluindo as arestas do
  branch; propagação de *rename* de job (atualizar `ramo_*` e `condition_json`).
- Persistência via `api/routers/jobs.py` (grava `condition_json`, degrada se a coluna
  não existir).
- (Opcional) expor o tipo `sql` no `JOB_TYPES` da UI, já suportado pela factory.

## 7. Telemetria e validação

- **Logar a decisão**: valor avaliado + ramo escolhido (no log do job e/ou
  `etl_job_execution`), para auditoria e debug.
- **Validar**: ramos referenciam jobs existentes do pipeline; sem ciclo; SQL
  read-only; identificador de tabela válido; `valor` numérico p/ contagem.

## 8. Fases

- **Fase 1 (MVP, aprovada)**: tipo **contagem (>N)** e **valor de query**
  (operadores `=,<>,>,>=,<,<=`) → ramo verdadeiro/falso. Migration + factory
  (branch + `trigger_rule` nas junções) + backend (persistência + avaliação) + UI.
- **Fase 2**: condição por **retorno/status do job anterior** (XCom) e **Switch**
  (múltiplos casos/ramos).

## 9. Riscos / pontos de atenção

- **Geração da DAG**: a *factory* gera código-fonte `.py` validado por `ast.parse`;
  a lógica do branch e o `trigger_rule` das junções são a parte delicada — testar a
  DAG gerada (compilação + cenários verdadeiro/falso) antes do deploy.
- **SQL livre da condição**: mesmo perfil de risco do tipo de job `sql` existente;
  mitigar com read-only + perfis confiáveis (mesma diretriz de `docs/SEGURANCA`).
- **Skip propagation**: documentado na seção 5 — é a causa nº 1 de bug em branching
  no Airflow.
