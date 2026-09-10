---
name: gotcha-servicenow-tabela-inacessivel
description: ServiceNow devolve 200 com lista VAZIA (não 403) em tabela sem permissão — integração fica verde coletando nada
metadata: 
  node_type: memory
  type: reference
  originSessionId: 80eeec2c-39eb-4217-a273-e34383d916bf
  modified: 2026-08-28T19:11:17.870Z
---

Na Table API do ServiceNow, consultar uma tabela que a conta **não tem
permissão de ler** devolve **`HTTP 200` com `{"result": []}`** — não 403, não
erro. Uma coleta que depende dessa tabela fica **verde para sempre**, gravando
zero registros, e a tela mostra "nenhum item" — a mesma frase que mostraria se
o registro realmente não tivesse aquele conteúdo.

**Custo real (Orquestra, descoberto 2026-08-28):** `dbo.etl_chamado_nota` viveu
com **0 linhas** desde que o módulo de Chamados existe, porque o motor lia
`sys_journal_field`. O flagrante veio da comparação: a tabela de **anexos**,
preenchida pelo mesmo laço no mesmo DAG, tinha 89 linhas.

**Onde o conteúdo estava:** nos campos `work_notes` e `comments` do próprio
registro, como diário concatenado (`dd/mm/aaaa hh:mm:ss - Autor (Rótulo)`,
entradas separadas por linha em branco, mais recente primeiro).

**Como aplicar:**
- Nunca concluir "não há dados" de uma resposta vazia de integração sem
  **comparar com uma coleta irmã** que funcione. Contagem zero ao lado de
  contagem não-zero é o sinal.
- Ao ler `task`/`incident`/`sc_req_item`/`sc_task`: a tabela-mãe **`task`**
  serve os três e aceita **`sysparm_query=sys_idIN<a,b,c>`** — um lote em vez de
  uma chamada por registro.
- O ServiceNow **espelha** cada anotação entre RITM e SCTASK, com um eco sem
  conteúdo do "Usuário de Integração Interno". Medido: **nenhum** pai ganha nota
  ao juntar as das tarefas — mas sem dedupe o histórico aparece **duplicado**.

Mesma família de [[orquestra-modos-de-falso-verde]] e
[[gotcha-tsc-noemit-nao-checa]]: ferramenta que responde verde sem ter feito o
que se supõe. Ver `docs/spec-chamados-tabela-copiar-notas.md` (§2) no repo
`sge_app`.
