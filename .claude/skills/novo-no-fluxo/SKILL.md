---
description: >
  Roteiro OBRIGATÓRIO para adicionar um novo tipo de nó ao canvas de fluxo do ORQUESTRA
  (como decisão, notificação, SQL). Use quando o usuário pedir "novo tipo de nó",
  "novo componente no fluxo", "nova etapa especial", "nó de <coisa> no canvas".
  São 9 pontos de integração — pular qualquer um reproduz bugs que já tivemos.
argument-hint: "<tipo_do_no>"
---

# Novo tipo de nó no fluxo — ORQUESTRA

Um nó novo atravessa TODA a stack. Siga na ordem; cada item lista o bug real que
aconteceu quando foi esquecido. Referências: nó SQL (migration 051) é o exemplo
mais recente e completo para copiar.

## Backend — `api/routers/jobs.py`
1. **`VALID_JOB_TYPES`** (topo do arquivo): adicionar o tipo.
2. **Validador + normalizador puros**: `_validate_<tipo>(cfg, ...)` e `_normalize_<tipo>(cfg)`
   (copie `_validate_sql_node`/`_normalize_sql_node`). Persistir o dict INTEIRO
   (round-trip por presença de chave).
3. **DOIS caminhos de gravação — não esqueça nenhum**:
   - `save_pipeline_fluxo` (canvas): validar, normalizar, gravar coluna `<tipo>_json`
     SÓ quando `j_type == "<tipo>"` (nunca zerar a config de outro tipo).
   - `register_pipeline_jobs` (lista/"Nova Etapa"): idem, E **incluir a chave no
     `_single_job_from_body`** — *bug real: o caminho de job único descartava
     `notify`/`condition`/`sql_node` → 422 "config ausente" em todo cadastro pela lista.*
4. **GET round-trip**: `get_pipeline_fluxo` (SELECT da coluna + parse p/ chave do nó) e
   `get_pipeline_job`. Degradar (NULL) se a coluna não existir.

## Migration — `sql/migrations/`
5. Nova coluna `<tipo>_json NVARCHAR(MAX) NULL` em `etl_pipeline_job` via skill
   `/nova-migration` (idempotente, `COL_LENGTH ... IS NULL`, `GO`).

## Factory — `dags/etl_dag_factory.py`
6. **Bloco do nó**: parse (`<tipo>_nodes` a partir do json, degrada se inválido),
   `_<tipo>_block(...)` com `task_id = nome do nó`. Se o nó NÃO tem lineage
   (`t_start_`/`t_end_` próprios):
   - adicionar em `_SPECIAL_NODES` (fica fora de `end_tasks`);
   - adicionar em **`_end_ref`** — *bug real: job dependendo de notificação gerou
     `NameError: t_end_<notif>` no import do Airflow;*
   - wiring próprio na seção `explicit_deps` + convergência no `publish_dataset`;
   - `trigger_rule=NONE_FAILED_MIN_ONE_SUCCESS` quando `branch_reachable`;
   - conferir o **guard de roteamento** (nó especial órfão com decisão no pipeline →
     ValueError) — *bug real: notificação órfã disparava card em TODO run.*

## Frontend — `ui-react/src/components/etapas/`
7. **Componente do nó** `<Tipo>Node.tsx` (padrão icon+label, cor própria, handles) e em
   `FluxoEditor.tsx`: registrar em `nodeTypes`, item na PALETA, **branch no `onDrop`** —
   *bug real: sem o branch, o nó caía no fallback e virava "datastage";* `buildNodes`
   (`toXConfig`), painel de propriedades, e **serialização no `salvar()` com a MESMA
   chave que o backend lê** — *bug real: front mandava `sql`, backend lia `sql_node` →
   config silenciosamente descartada.*
8. **`Jobs.tsx`**: adicionar em `JOB_TYPES` (form "Nova Etapa") + campos do tipo —
   *bug real: notificação não aparecia na lista de tipos.*

## Testes — `tests/`
9. `tests/test_dag_factory_<tipo>.py` no padrão existente (stubs do Airflow via
   `sys.modules` + `_exec_source` que IMPORTA a DAG gerada — pega NameError de carga)
   e validadores puros em `test_jobs_decisao.py`. Rodar `python -m pytest tests -q`
   (baseline: 5 falhas pré-existentes de auth) e `npm run build` em `ui-react/`.

## Antes de commitar
- [ ] Os 9 pontos acima conferidos?
- [ ] `/seguranca-review` rodada (json embutido via `json.dumps`, validação no register)?
- [ ] `/revisao-pr` rodada?
