# Spec — Nó "Aguarde" (ponto de encontro entre pernas paralelas)

**Status:** APROVADA e IMPLEMENTADA (F1–F4) — aguardando merge e smoke em produção
**Criada em:** 2026-08-01 · **Aprovada em:** 2026-08-01
**PRs:** F1 #231 · F2 #232 · F3 #233 (empilhadas, mergear em ordem)
**Projeto:** Orquestra (sge_app)
**Arquivo-mãe do motor:** `dags/etl_dag_factory.py`

---

## 1. Problema

Existem fluxos em que duas (ou mais) pernas rodam **em paralelo** e um passo
seguinte só pode acontecer **depois que todas terminarem** — o exemplo do
usuário: dois processos consomem os mesmos arquivos de trabalho, e a remoção
desses arquivos só é segura quando **as duas pernas** já terminaram. Remover
antes corrompe a perna que ainda está lendo.

Hoje o Orquestra não tem um nó que expresse isso. O operador precisa deduzir a
junção ligando arestas manualmente, sem nenhum controle sobre o comportamento
quando uma das pernas falha.

## 2. O que já existe (levantamento, não suposição)

| Fato | Onde | Consequência para a spec |
|---|---|---|
| Modo **explícito** de dependência entre jobs (`depends_on_jobs`) gera `[t_end_A, t_end_B] >> t_start_C >> t_job_C >> t_end_C` | `dags/etl_dag_factory.py:1418-1454` | A junção **já é topologicamente possível**. O que falta é semântica e política de falha. |
| Modo **ondas** (`execution_order`) — jobs de mesma ordem rodam em paralelo | `etl_dag_factory.py:534-543` | Fallback dos pipelines antigos. O Aguarde ativa o modo explícito (ver §5.3). |
| Já existem 3 nós especiais sem `t_start`/`t_end`: `decisao`, `notificacao`, `sql` | `_SPECIAL_NODES`, `etl_dag_factory.py:550` | Há um **padrão pronto** para adicionar um 4º tipo de nó. O Aguarde entra nele. |
| `t_end_<job>` usa `trigger_rule=ALL_DONE` **e o `log_end` dá `raise`** quando o status é FAILED | `etl_dag_factory.py:331` e `:1210-1214` | É o antídoto do gotcha que derrubou a spec de dependências: a task roda para registrar, mas **propaga a falha**. O Aguarde usa o mesmo princípio. |
| `end_tasks >> t_publish_dataset` liga **todos** os `t_end` ao fechamento | `etl_dag_factory.py:1477-1479` | É essa aresta que faz o DagRun ficar vermelho. **O Aguarde nunca a remove** (ver §4, invariante). |
| Detector de ciclo entre jobs (DFS com cores) no backend + espelho client-side | `api/routers/jobs.py:554`, `FluxoEditor.tsx:332` | O Aguarde entra no grafo de ciclo como qualquer nó — sem código novo. |
| Múltiplas arestas de entrada já viram CSV em `depends_on_jobs` | `FluxoEditor.tsx:1341-1358` | A serialização do Aguarde reaproveita esse caminho inteiro. |
| Tipos válidos: `{datastage, shell, python, storedproc, http, decisao, notificacao, sql}` | `api/routers/jobs.py:37` | Ponto único de entrada do tipo novo. |

## 3. Decisões tomadas (usuário, 2026-08-01)

1. **Escopo:** o Aguarde espera **apenas as arestas ligadas a ele** no canvas.
   Sem barreira global implícita — o grafo do Airflow reflete exatamente o que a
   tela mostra. Facilitador: botão "prender as pontas soltas" (§7.4).
2. **Política de falha:** **configurável por nó**, default = *só segue se todas
   derem certo*. A opção *segue assim que todas terminarem, mesmo com falha* é o
   que atende a limpeza de arquivos.
3. **Sem espera por tempo ou evento externo** — o nó é puramente um ponto de
   sincronização. Nada de sleep, horário ou sensor de arquivo.
4. **Condução:** spec aprovada antes de qualquer código; uma PR por fase.

## 4. ⛔ Invariante de segurança (a regra que não pode ser quebrada)

> **Todo `t_end_*` de job real permanece em `all_ends` e ligado ao
> `t_publish_dataset`. O nó Aguarde nunca remove, substitui nem intermedia essa
> aresta.**

**Por quê:** a spec de dependências entre pipelines foi revertida (PR #229)
porque um `TriggerRule.ALL_DONE` numa task **terminal** fez todo pipeline que
falhava aparecer **VERDE** no Airflow — o estado do DagRun é decidido pelas
**folhas** do grafo. O Aguarde usa `ALL_DONE` na política "mesmo com falha", o
que reintroduziria exatamente esse risco **se** ele passasse a ser o caminho
único até o fechamento.

Com o invariante mantido, o comportamento é o correto:

```
t_job_A  FAILED
  └─ t_end_A  (ALL_DONE, mas log_end faz raise) → FAILED
       ├─ t_wait_X (ALL_DONE) → SUCCESS  → t_job_limpeza roda  ✅
       └─ t_publish_dataset → UPSTREAM_FAILED → DagRun FAILED  ✅
```

A limpeza roda **e** o pipeline continua vermelho. Esse cenário vira o
**teste-âncora obrigatório** da F2 (§6.3).

## 5. Desenho técnico

### 5.1 Modelo de dados

Migration **068** — coluna idempotente, no mesmo padrão da 051 (`sql_json`):

```sql
IF COL_LENGTH('dbo.etl_pipeline_job', 'aguarde_json') IS NULL
BEGIN
    ALTER TABLE dbo.etl_pipeline_job ADD aguarde_json NVARCHAR(MAX) NULL;
    PRINT '[OK] etl_pipeline_job.aguarde_json adicionada';
END
ELSE
    PRINT '[SKIP] etl_pipeline_job.aguarde_json já existe';
GO
```

Conteúdo: `{"politica": "todas_sucesso" | "todas_terminarem"}`.
Ausente / inválido → degrada para `"todas_sucesso"` (o conservador).

Nenhuma coluna nova além dessa. As arestas de entrada e saída do Aguarde usam o
`depends_on_jobs` que já existe; a posição no canvas usa o `layout_x/y` da
migration 048.

### 5.2 Tabela de `trigger_rule` do nó gerado

O Aguarde vira `t_wait_<n> = EmptyOperator(...)` — sem `t_start`/`t_end`
próprios, como os outros três nós especiais.

| Política escolhida | Alcançável a partir de uma Decisão? | `trigger_rule` emitida |
|---|---|---|
| `todas_sucesso` (default) | não | `ALL_SUCCESS` |
| `todas_sucesso` | sim | `NONE_FAILED_MIN_ONE_SUCCESS` |
| `todas_terminarem` | qualquer | `ALL_DONE` |

A linha do meio existe porque um ramo não escolhido chega **SKIPPED**, e
`ALL_SUCCESS` travaria a junção para sempre. É o mesmo tratamento que
`branch_reachable` já dá aos `t_start` (`etl_dag_factory.py:327-331`).

### 5.3 Encadeamento

- `_SPECIAL_NODES += ("aguarde",)` → fica fora de `all_ends` (não tem `t_end`).
- `_end_ref(d)` passa a mapear um Aguarde para `t_wait_<d>`, para que um job que
  dependa dele referencie a task certa (sem isso: **NameError no import da DAG**).
- `explicit_deps` passa a incluir `has_aguarde` — um pipeline com Aguarde entra
  no modo explícito mesmo que nenhum job tenha `depends_on_jobs`.
- Aresta de entrada: `{up} >> t_wait_{n}`, onde `up` são os `_end_ref` das
  dependências (idêntico ao que `notificacao`/`sql` já fazem).
- Convergência no fechamento: `t_wait_* >> t_publish_dataset` (+ `t_teams_end`,
  `t_teams_error`, `t_flow_close` quando ativos), espelhando `notif_task_refs` e
  `sql_task_refs`. Cobre o caso do Aguarde ser folha do fluxo.

### 5.4 Contrato da API

- `VALID_JOB_TYPES += {"aguarde"}` (`api/routers/jobs.py:37`).
- `sem_lineage` inclui `aguarde` — o nó não tem origem/destino nem comando.
- `_validar_aguarde(job)` / `_normalizar_aguarde(job)`, no padrão de
  `_validar_sql` / `_normalizar_sql`.
- Persistência e leitura com degrade se `aguarde_json` não existir (padrão
  `_tem_coluna`), tanto no `POST /fluxo` quanto no `GET`.
- ⚠️ **O GET tem que devolver a política.** Na spec de dependências, três campos
  eram gravados e nunca lidos de volta — resultado: **todo save zerava os três**
  (causa-raiz C da reversão). Round-trip é critério de aceite da F1, com teste.

### 5.5 Regras de validação

| Situação | Tratamento |
|---|---|
| Aguarde com **0** arestas de entrada | **Erro** no save (backend 422 + guard no front) — nó órfão que nunca libera |
| Aguarde com **1** aresta de entrada | **Aviso** não bloqueante — é junção de uma perna só, provavelmente esquecimento |
| Aguarde com **0** arestas de saída | **Aviso** não bloqueante — não segura nada; legítimo como marco visual |
| Aguarde → Aguarde | Permitido (barreiras encadeadas) |
| Ciclo envolvendo Aguarde | Já barrado pelo `_graph_has_cycle` + espelho client-side |
| `politica` fora do domínio | Normaliza para `todas_sucesso` |

## 6. Fases

Uma branch e uma PR por fase, mergeáveis em ordem. Nenhuma fase deixa a `main`
num estado quebrado.

### F1 — Fundação: modelo e contrato da API

**Entrega**
- `sql/migrations/068_pipeline_no_aguarde.sql` (idempotente, §5.1)
- `api/routers/jobs.py`: tipo válido, `sem_lineage`, validação, normalização,
  persistência e **leitura** de `aguarde_json` nos dois endpoints do fluxo
- Regras de validação de §5.5 (as que são do backend)

**Critérios de aceite**
- Salvar um fluxo com nó `aguarde` persiste a política escolhida
- **Reabrir o fluxo devolve a política gravada** (round-trip), e um segundo save
  sem tocar no nó **não zera** o campo
- Aguarde sem entrada é rejeitado com mensagem nomeando o nó
- Com a coluna ausente (migration não aplicada), a API não quebra — degrada
- Ciclo com Aguarde continua barrado

**Validação:** pytest — baseline obrigatório (zero falhas **novas** vs `HEAD`,
nunca zero absoluto; hoje são 935 testes com 5 falhas pré-existentes).

### F2 — Motor: geração da DAG

**Entrega**
- `_wait_block(job, cfg, branch_reachable)` em `dags/etl_dag_factory.py`
- `_SPECIAL_NODES`, `_end_ref`, `explicit_deps`, encadeamento e convergência (§5.3)
- Suplemento de leitura de `aguarde_json` no factory, no padrão do
  `depends_on_jobs` (`etl_dag_factory.py:1694-1703`)

**Critérios de aceite**
- As 3 linhas da tabela de `trigger_rule` (§5.2) saem corretas no código gerado
- Job a jusante do Aguarde referencia `t_wait_<n>` e a DAG **importa sem NameError**
- **Teste-âncora do invariante (§4):** num pipeline com Aguarde em
  `todas_terminarem`, o `t_end` de cada perna continua em `all_ends` e ligado ao
  `t_publish_dataset`
- Pipeline **sem** nó Aguarde gera DAG **byte-idêntica** à de hoje
- Aguarde como folha converge no fechamento (não fica pendurado)

**Validação:** geração real da DAG com `_generate_dag_source` + inspeção da
string, com Airflow stubado via `sys.modules` — a técnica que os testes do repo
já usam (`tests/test_dag_factory_decisao.py`). Compilação da string gerada em
pelo menos 12 combinações (com/sem decisão × 2 políticas × com/sem notificação).

⚠️ **Duas armadilhas do factory, já pagas antes:**
1. No arquivo gerado, `consts_str` sai **antes** de `helpers_str` — nunca pôr
   função de helper em `default_args` (NameError no import; o pytest de geração
   não pega, porque a string compila).
2. Comentário/docstring que **cite um identificador** entra no código gerado e
   quebra assert de substring dos testes de não-regressão. Escrever os
   comentários do `_wait_block` sem nomear as regras de trigger.

### F3 — Canvas: o componente

**Entrega**
- `ui-react/src/components/etapas/AguardeNode.tsx` — barra de sincronização
  (linguagem visual de BPMN), múltiplas entradas e uma saída, cor âmbar (as
  outras já usam indigo/teal/violeta), ícone `GitMerge`
- `PainelAguarde.tsx` — seletor da política com o texto explicando a
  consequência de cada opção em linguagem de operador
- Registro em `nodeTypes`, paleta, contadores, cor do minimap, rótulo do painel
- Serialização (`payloadNodes`) e desserialização (`apiNodes → nodes`)
- Guards client-side de §5.5, nomeando o nó com problema (padrão dos guards de
  notificação e decisão)
- Ação **"prender as pontas soltas"** (§7.4)

**Critérios de aceite**
- Arrastar um Aguarde, ligar duas pernas nele e um job de limpeza depois; salvar,
  recarregar a página e o desenho volta idêntico, com a política preservada
- Guards disparam antes do 422 e nomeiam o nó
- Nó aparece corretamente no minimap e nos contadores

**Validação:** `tsc --noEmit` + `eslint` + `build` com baseline vs `HEAD`.

### F4 — Documentação e smoke

**Entrega**
- `docs/MANUAL_USUARIO.md`: seção do nó Aguarde com o exemplo das duas pernas +
  limpeza de arquivos, e a explicação da política de falha
- Release note da versão
- Roteiro de smoke em produção (§8)

**Critérios de aceite:** roteiro executável por outra pessoa, sem contexto desta
conversa.

## 7. Detalhes de UX

### 7.1 Nome e linguagem
Rótulo na paleta: **Aguarde**. Subtítulo no painel: *"segura o fluxo até que
todas as etapas ligadas a ele terminem"*.

### 7.2 O seletor de política, em linguagem de operador
- **Só seguir se todas derem certo** (padrão) — *"se qualquer etapa acima falhar,
  o que vem depois não roda."*
- **Seguir assim que todas terminarem, mesmo com falha** — *"use quando o passo
  seguinte é limpeza. O pipeline continua marcado como falho."*

A segunda opção mostra um aviso permanente no painel dizendo que ela **não**
esconde a falha — para não virar um botão de "deixar verde".

### 7.3 Desenho do nó
Barra horizontal larga e baixa (não um card), que é como se lê "sincronização"
em BPMN/UML. Handles de entrada distribuídos ao longo da barra.

### 7.4 "Prender as pontas soltas"
Botão no painel do Aguarde: liga a ele todos os nós do fluxo que não têm aresta
de saída, exceto ele mesmo e os que já estão a jusante dele. Monta a barreira em
um clique sem introduzir dependência invisível — as arestas ficam **desenhadas**
no canvas.

## 8. Deploy

⚠️ **A ordem importa. O passo 3 é o que a spec anterior descobriu na dor:**

1. Aplicar a migration **068** (etapa 6c do `deploy.sh`, responder `s`)
2. Subir API + front
3. **REGERAR as DAGs** (`force_all` da factory, ou o botão por pipeline) — o
   `etl_dag_factory` mudou, mas **as DAGs já geradas não mudam sozinhas**. Sem
   este passo, nada acontece.
4. Validar em **um pipeline de teste**, não na malha inteira

**Rollback:** remover o nó do fluxo e regerar a DAG. A coluna `aguarde_json`
pode ficar — é inerte para quem não usa o nó.

⚠️ **Gotcha de infra conhecido:** `sql/migrate.py` nunca lê `cur.messages`, então
todo `PRINT` de migration é descartado. Não confiar em saída de migration para
confirmar nada — conferir no banco.

## 8.1 Roteiro de smoke (executável sem contexto desta spec)

Rodar **depois** do deploy completo, incluindo o passo 3 (regerar as DAGs).
Use um pipeline de teste — não a malha real.

**Preparo:** um pipeline de teste com duas etapas que possam rodar em paralelo
(`PernaA`, `PernaB`) e uma terceira que represente a limpeza (`Limpeza` — pode ser
um `shell` com `echo`).

| # | Passo | Resultado esperado |
|---|---|---|
| 1 | No editor de fluxo, arrastar **Aguarde** para o canvas | Nó aparece como barra vertical âmbar, rotulado `todas com sucesso` |
| 2 | Ligar `PernaA` e `PernaB` na entrada dele, e ele em `Limpeza` | Painel mostra "2 etapas ligadas" |
| 3 | Salvar, sair da tela e voltar | Desenho e política voltam idênticos |
| 4 | Publicar (Gerar DAG) e abrir a DAG no Airflow | Aparece a task do Aguarde entre as pernas e a limpeza |
| 5 | Executar o pipeline | `Limpeza` só inicia depois que **as duas** pernas terminam |
| 6 | Fazer `PernaA` falhar de propósito e executar | `Limpeza` **não roda**; pipeline em falha |
| 7 | Trocar a política para **"mesmo com falha"**, salvar e **regerar a DAG** | Card do nó passa a mostrar `mesmo com falha` |
| 8 | Repetir a execução com `PernaA` falhando | ⭐ `Limpeza` **roda**, e o pipeline **continua vermelho** |
| 9 | Criar um Aguarde e tentar salvar sem ligar nada nele | Erro nomeando o nó, antes de chegar ao servidor |

⭐ **O passo 8 é o que precisa ser conferido com atenção.** Ele valida os dois lados
ao mesmo tempo: a limpeza acontece E a falha continua visível. Se o pipeline
aparecer **verde** no passo 8, pare o deploy e reabra a spec — é o modo de falha que
derrubou a spec de dependências.

## 9. Fora de escopo (registrado de propósito)

- Espera por tempo, horário ou arquivo (decisão 3 do usuário)
- Barreira global implícita (decisão 1)
- Aguarde entre **pipelines** diferentes — isso é o território da spec de
  dependências entre pipelines, hoje revertida
- Timeout do Aguarde ("se em 2h não liberar, alerta") — candidato natural a uma
  F5 futura, **não** entra agora

## 10. Riscos

| Risco | Mitigação |
|---|---|
| `ALL_DONE` mascarar falha do pipeline | Invariante §4 + teste-âncora obrigatório na F2 |
| Operador usar "mesmo com falha" achando que conserta o pipeline | Aviso permanente no painel (§7.2) |
| Regressão em pipelines existentes | Critério de aceite de DAG byte-idêntica sem o nó |
| Deploy sem regerar as DAGs → "não mudou nada" | Passo 3 explícito do §8 |
| Comportamento distribuído não verificável por leitura | F2 valida por **geração e compilação real** da DAG; o smoke §8 roda num pipeline de teste antes da malha |
