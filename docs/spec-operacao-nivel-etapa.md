# Spec — Operação no nível de etapa

Data: 2026-08-03 · Status: **APROVADA — as 4 decisões do §7 foram tomadas pelo
usuário em 2026-08-03; implementação por fases (§8) autorizada.**

> **Decisão arquitetural já tomada (usuário, 2026-08-03): não construir
> executor próprio — seguir com o Airflow.** A dúvida levantada foi "como
> gerenciar a questão de DAGs toda hora com essas alterações?". A resposta que
> orienta esta spec: **a DAG é a planta, não o estado**. Pausar, liberar e
> reexecutar são **estado em tabela** — nenhum deles republica DAG. O grafo só
> muda quando o **desenho** muda (etapa nova no canvas), que é o caminho já
> existente do carimbo `dag_config_pendente_em`.

## 1. O problema

Hoje a operação enxerga a malha (pipelines) e a execução agregada, mas quando
um pipeline falha o operador não consegue, **no mesmo lugar**, descer até a
etapa que quebrou, entender o que já rodou e retomar dali. Ele reprocessa o
pipeline inteiro — caro e, em cadeia, arriscado. Também não há como segurar o
processo num ponto para conferir um número antes de deixar seguir: hoje a
alternativa é despausar/pausar DAG na mão ou deixar quebrar de propósito.

## 2. O que JÁ existe (levantado no código, não suposto)

| Peça | Onde | Situação |
|---|---|---|
| Cada etapa **já é uma task** (`task_id` = `job_name`), com `log_start_<job>` e `log_end_<job>` em volta | `dags/etl_dag_factory.py:289-445` | ✅ pronto |
| Horário de início/fim/duração/status **por etapa** | `dbo.etl_job_execution` (`start_time`, `end_time`, `duration_seconds`, `status`) | ✅ pronto |
| **Reexecução a partir de uma etapa** (`clearTaskInstances` com `include_downstream`) | `POST /execucoes/rerun` (`api/routers/execucoes.py:570-638`) | ⚠️ existe, mas só aparece no modal de Logs/Dashboard e **só quando a etapa está FAILED** |
| Drill-down execução → etapa com horários | `LogDetailModal` (`components/execucao/ExecucaoDetailModal.tsx`) | ⚠️ existe **em lista**, não em diagrama, e fora da malha |
| Travessia de grafo no front (DFS de sucessores; mapa de predecessores) | `components/etapas/layoutGrafo.ts` (`criaCiclo`, `liveLayout`) | ✅ reusável |
| Canvas do pipeline (nós = etapas, arestas = `depends_on_jobs`) | `components/etapas/FluxoEditor.tsx` | ✅ pronto (modo edição) |
| Espera por **aprovação humana** no meio do run | — | ❌ **não existe nada**. Sensores foram removidos do gerador (D01); o único "aprovar" é de importação de cadastro; a Finalização Manual conserta registro órfão, não pausa |

**Armadilha central descoberta:** as duas tabelas de execução usam chaves
diferentes — `etl_job_execution.execution_id` é o `ts_nodash` (timestamp
lógico) e `etl_pipeline_execucao.execution_id` é o `run_id` do Airflow. Já
existe conversão nos dois lados (`_iso_to_ts_nodash` na API, `toNodash` no
front), mas **todo drill-down malha → etapa passa por essa ponte** e ela
precisa ser explícita, não improvisada em cada tela.

## 3. Bloco A — Descer da malha até a etapa (diagrama, com horários)

**Gesto:** no modo Execução da malha, clicar num pipeline abre o **mesmo canvas
de Etapas, em modo Execução** — read-only, com cada etapa mostrando status,
início, fim e duração, e o caminho realmente percorrido em destaque (ramos de
decisão não tomados ficam apagados).

**Como:** é a composição de duas coisas prontas. O `FluxoEditor` já desenha o
grafo do pipeline; o `LogDetailModal` já busca os dados por etapa
(`GET /execucoes?detail_mode=true`). A fase entrega o **modo Execução do canvas
de etapas** (espelho do que a malha já faz: anel de status, sem edição) e a
ponte de identidade `run_id ↔ ts_nodash` num único lugar.

**Regras de honestidade** (herdadas da malha): etapa sem linha de execução =
neutra, nunca verde; etapa `SKIPPED` por ramo não tomado tem cor própria e não
conta como sucesso nem falha.

## 4. Bloco B — Reexecutar a partir de uma etapa

**O que muda em relação ao que existe:** o `POST /execucoes/rerun` já faz o
certo (clear da task com downstream). Falta (a) **estar onde o operador está**
— dentro do drill-down da malha, não só no modal de Logs; (b) **não depender
de FAILED** — retomar a partir de uma etapa `SUCCESS` é legítimo (o operador
corrigiu o dado de origem e quer refazer dali para frente); (c) uma
**confirmação honesta**, no padrão da malha: "vai reexecutar estas N etapas"
com a lista, antes de rodar.

**Duas questões que a fase precisa resolver (viraram decisões, §7):**

1. **Cascata na malha.** Reexecutar um pipeline no meio de uma malha faz o
   `publish_dataset` rodar de novo ao final, e o push tenta disparar os
   dependentes — mas o *claim* de corrida (`reservar_corrida`) impede uma
   segunda corrida do dependente na mesma data. Ou seja, **hoje o
   comportamento de fato é "sem cascata"**, por efeito colateral e não por
   escolha. Control-M trata isso como opção explícita do gesto.
2. **Histórico da tentativa.** O `clear` mantém o mesmo `ts_nodash`, e a SP de
   telemetria faz `IF NOT EXISTS INSERT ELSE UPDATE` — então a reexecução
   **sobrescreve** a linha da tentativa anterior. Perde-se "falhou 10:12,
   reexecutado 11:03, passou". A coluna `attempt` existe na tabela e **nunca é
   preenchida** — o conserto natural é gravar a tentativa e passar a
   acumular (migration + ajuste da SP), o que também dá base para medir
   retrabalho.

## 5. Bloco C — Etapa em espera (pausa até o OK do usuário)

Não existe nada disso hoje; é a parte que exige construção de verdade. Duas
formas, e elas não são excludentes:

**C1 — Pausa declarada no desenho** (mais simples): no canvas de Etapas, marcar
uma etapa como *"exige liberação"*. Vira um portão no grafo na próxima
publicação. Previsível e sem surpresa, mas só serve para pausas que você sabe
de antemão que quer.

**C2 — Pausa em runtime, em qualquer etapa** (o que você descreveu): durante a
execução, marcar uma etapa que **ainda não começou** como "em espera"; o
processo para ali e continua assim que você liberar.

**Como fazer C2 sem mexer no grafo em voo** — o portão já existe fisicamente:
toda etapa tem um `log_start_<job>` antes dela. A proposta é esse `log_start`
passar a consultar uma tabela de pausas e, quando houver uma pendente para
`(execução, etapa)`, ficar **aguardando em `reschedule`** (o padrão do Airflow
que devolve o worker entre as verificações — não é polling que segura recurso)
até a liberação. Nenhuma task nova, nenhum nó a mais no desenho, e a pausa vale
para qualquer etapa sem republicar nada.

**Limite honesto que precisa aparecer na tela:** só dá para pausar etapa que
**ainda não iniciou**. Se ela já está rodando, a pausa vale para as seguintes.

**Ponto de atenção declarado:** o repo removeu sensores de propósito (o
`ExternalTaskSensor` esperava run de outra DAG, com timeout de 1h que reprovava
o filho). O caso aqui é diferente — a condição é local (uma linha em tabela) e
o modo `reschedule` não ocupa worker — mas a fase precisa entregar **teto de
espera configurável com alerta**, para que uma pausa esquecida não vire
pipeline pendurado em silêncio (a mesma disciplina da guardiã).

**Liberação:** botão na tela (com auditoria de quem liberou e quando), evento
visível no painel da malha, e — para o operador que desistiu — a opção de
**cancelar a execução** em vez de liberar.

## 6. Bloco D — Realce de dependências no canvas

**Gesto:** clicar num nó (ou numa linha) acende toda a cadeia ligada a ele;
botões **"dependências para trás"** e **"para frente"** isolam um dos sentidos.
Vale nos **dois** canvas — etapas (dentro do pipeline) e malha (entre
pipelines).

**Como:** `layoutGrafo.ts` já tem a travessia por sucessores (usada para
detectar ciclo) e o mapa de predecessores (usado no layout). A fase extrai
`upstreamDe`/`downstreamDe` como funções puras e as usa para o realce: cadeia
acesa em cor forte, o resto esmaecido, com contador ("7 etapas dependem desta").

É a fase de **menor risco e maior valor imediato** para mapeamento de processo
— não toca em execução nenhuma.

## 7. Decisões — TOMADAS pelo usuário em 2026-08-03

1. **Cascata no rerun: SEMPRE PERGUNTAR.** O modal oferece as duas opções —
   *"só este pipeline"* ou *"este e os dependentes (cascata)"* — mostrando
   quais pipelines seriam afetados em cada caso. Nunca decidir em silêncio,
   nos dois sentidos: nem reprocessar cadeia inteira sem aviso, nem deixar
   dependentes com dado velho achando que o rerun resolveu.
2. **Histórico de tentativas: ACUMULAR.** `etl_job_execution` passa a guardar
   cada tentativa (coluna `attempt`, hoje existente e nunca preenchida), com
   migration e ajuste da SP de telemetria. O drill-down mostra a linha do
   tempo real do dia, e fica a base para medir retrabalho.
3. **Pausa: RUNTIME primeiro** (C2 — marcar em execução qualquer etapa que
   ainda não iniciou). A pausa declarada no desenho (C1) e demais variações
   vão para o **backlog**, a reavaliar depois que o uso real mostrar
   necessidade.
4. **Realce: DESTACAR por padrão, com botão de "isolar"** para grafos grandes
   (esconder o que não pertence à cadeia sob demanda, nunca automaticamente).

## 8. Fases propostas

| Fase | Entrega | Depende de |
|---|---|---|
| **F1** | Realce de dependências (para trás/para frente) nos dois canvas | — |
| **F2** | Ponte de identidade `run_id ↔ ts_nodash` num único lugar + endpoint de execução por etapa consumível pela malha | — |
| **F3** | Modo Execução do canvas de Etapas (status, horários, caminho percorrido) e o gesto de descer da malha até ele | F2 |
| **F4** | Rerun a partir da etapa dentro do drill-down, com confirmação e a decisão de cascata; tentativas acumuladas | F3, decisões 1 e 2 |
| **F5** | Etapa em espera: tabela de pausa, portão no `log_start`, teto com alerta, liberação/cancelamento com auditoria | F3, decisão 3 |
| **F6** | Fecho: manual do usuário, roteiro de smoke e aceitação com cenários executados no dev | F1–F5 |

Cada fase segue o rito da casa: cenários **executados** no ambiente dev,
revisão adversarial antes da PR e merge só com autorização.

## 9. Riscos conhecidos

- **F5 é a fase de risco real**: mexe no `log_start`, que hoje existe em toda
  etapa de toda DAG — uma regressão ali afeta 100% dos pipelines. Mitigação:
  o portão só muda de comportamento quando existe pausa pedida; sem linha na
  tabela, o caminho é byte-idêntico ao atual, com teste de não-regressão do
  fonte gerado.
- **Republicação geral**: F5 exige regerar as DAGs para o portão valer
  (`force_all`), com a consulta de dimensionamento antes — o mesmo cuidado já
  documentado no deploy da spec de dependências.
- **Pausa esquecida** vira pipeline pendurado: teto + alerta são parte da
  entrega, não melhoria futura.
- **Rerun com cascata** pode reprocessar volume grande: o modal precisa dizer
  quantos pipelines e quais, antes de confirmar.
