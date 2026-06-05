# ORQUESTRA — Histórico de Alterações

---

## v2.2.0 — Parâmetros avançados de importação, Changelog e melhorias operacionais

### Import Sequence (wizard)
- Domínio passou de **opcional para obrigatório** no step 1, com validação
- Step 3 expandido com novos campos:
  - **Status inicial** — Ativo ou Inativo ao criar o pipeline
  - **Data de início da DAG** — define quando o agendamento começa (aceita data futura)
  - **Notificações Teams** — checkboxes individuais para início, conclusão e erro
- `etl_sequence_import_approve.py` aplica todos os novos campos no pipeline após aprovação

### Formulário de Pipeline
- Nova seção **"Agendamento avançado"** com campo `Data de início da DAG`
- Campos hora e minuto redesenhados: largura 76px, fonte 15px bold, centralizado — elimina corte de 2 dígitos
- Campo `dag_start_date` enviado ao `etl_pipeline_register` e carregado ao editar

### Última Execução (`last_execution`)
- `log_end` agora executa dois passos ao final de cada job:
  1. Atualiza tabela de log (comportamento existente)
  2. Atualiza `last_execution` em `dbo.etl_pipeline` com data e hora
- O último job do pipeline sempre grava o horário mais recente
- Requer regeneração de DAGs para pipelines existentes

### Data de Início da DAG (`dag_start_date`)
- Nova coluna `dag_start_date DATE` em `dbo.etl_pipeline`
- `etl_dag_factory.py` lê o valor da tabela e usa no `start_date` da DAG gerada
- Sem valor: mantém comportamento padrão (2026-01-01)

### Changelog / Versões
- Badge de versão no header agora abre modal com histórico de versões
- Modal em accordion — versão mais recente aberta por padrão
- Renderizador markdown inline (sem CDN) — headers, bold, listas, código
- Admin: nova aba **"📋 Versões"** com CRUD completo (criar, editar, excluir)
- Ao salvar nova versão, badge no header é atualizado automaticamente
- Novos DAGs: `etl_versao_query` e `etl_versao_register`

### SQL — Migration 003
```
sql/migrations/003_start_date_versoes.sql
```
- `ALTER TABLE dbo.etl_pipeline ADD dag_start_date DATE NULL`
- `CREATE TABLE dbo.etl_versao_ferramenta` (id, versao, titulo, descricao_md, criado_em, criado_por)

---

## v2.1.0 — Validação circular S4, Reexecutar do log e melhorias de UX

### Validação de Dependência Circular (S4)
- **Frontend**: DFS em `window.__pipelines` ao digitar no campo "Depende de" — feedback imediato sem chamar o backend
- **Backend** (`etl_pipeline_register.py`): DFS iterativo no banco, máx. 50 saltos, levanta `ValueError` antes de qualquer escrita
- Auto-loop (pipeline dependendo de si mesmo) validado separadamente em ambas as camadas

### Reexecutar a partir do Log
- Botão "reexecutar" direto em cada linha da tabela de logs — elimina troca de tela
- Chama `reexecutarDoPipelineLog(pipelineName)` que dispara novo `dagRun` manual
- Trata 404 (DAG não existe) e 409 (execução em andamento) com toast informativo

### Ícones SVG inline
- Sistema de ícones SVG sem dependência de CDN (compatível air-gap / Docker)
- 12 ícones a 18px: edit, trash, disable, play, refresh, gear, graph, check, detail, history, link, rerun
- CSS `.act-btn` sem largura fixa, variantes por cor, sem bordas visíveis

### UX da coluna Ações
- `justify-content: flex-start` — ícones alinhados à esquerda
- `min-width: 120px` em `th/td.col-actions`

### Formulário de Agendamento
- Grid CSS `180px + auto` com labels acima de cada campo
- Tags ao lado do Agendamento em grid de 2 colunas

---

## v2.0.0 — Audit Trail (S1) e Dependência entre Pipelines (S4)

### S4 — Dependência entre Pipelines
- Campo "Depende de" no formulário de pipeline com autocomplete (datalist)
- `etl_dag_factory.py` gera `ExternalTaskSensor` como primeira task quando há dependência
  - `mode='reschedule'`, `timeout=7200`, `poke_interval=60`
  - Aguarda status `success` do pipeline pai antes de iniciar
- Nova coluna `depends_on NVARCHAR(200) NULL` em `dbo.etl_pipeline`

### S1 — Audit Trail
- Modal "Histórico de alterações" por pipeline, acessível na coluna Ações
- Registra todos os campos alterados com valor anterior e novo
- Novos registros: audita todos os campos na criação
- DAG `etl_pipeline_audit_query` retorna histórico paginado via XCom
- Nova tabela `dbo.etl_pipeline_audit` com índices em `pipeline_name` e `changed_by`
- `etl_pipeline_register.py`: lê estado antes do upsert, compara e persiste diferenças

### SQL — Migration 002
```
sql/migrations/002_audit_trail_depends_on.sql
```
- Coluna `depends_on` em `dbo.etl_pipeline`
- Tabela `dbo.etl_pipeline_audit`

---

## v1.2.0 — Correções de bugs críticos e ícones

### Correções de bugs
- **`_pipelineToDagId`**: removido `.toLowerCase()` — nome do pipeline é case-sensitive
- **`_resolveAirflowDagRunId`**: substituído filtro server-side (bugs no Airflow) por matching client-side com tolerância de ≤ 10 minutos
- **Badge de falhas vs. logs**: unificado critério de tempo — `_extractFailuresFromDash` aplica o mesmo `cutoffMs` que o badge usa, eliminando divergência de contagem
- **Visualizador de logs**: `font-size:10.5px`, `white-space:pre`, `overflow-x:auto`, `text-align:left`

### Botão "Executar agora"
- Separado em `.act-btn.act-exec` (ícone na tabela) e `.btn-exec` (botão texto), evitando conflito de estilos

---

## Arquivos alterados (acumulado)

| Arquivo | Tipo | Descrição |
|---|---|---|
| `ui/index.html` | Modificado | Todas as mudanças de UI/UX e JS |
| `dags/etl_pipeline_register.py` | Modificado | Audit trail, depends_on, dag_start_date |
| `dags/etl_pipeline_query.py` | Modificado | depends_on, dag_start_date no SELECT |
| `dags/etl_dag_factory.py` | Modificado | ExternalTaskSensor, dag_start_date, last_execution |
| `dags/etl_sequence_import_approve.py` | Modificado | active, dag_start_date, notificações |
| `dags/etl_pipeline_audit_query.py` | Novo | Consulta histórico de audit trail |
| `dags/etl_versao_query.py` | Novo | Consulta versões da ferramenta |
| `dags/etl_versao_register.py` | Novo | CRUD de versões (create/update/delete) |
| `sql/migrations/002_audit_trail_depends_on.sql` | Novo | depends_on + etl_pipeline_audit |
| `sql/migrations/003_start_date_versoes.sql` | Novo | dag_start_date + etl_versao_ferramenta |

---

## Pendente — Aprovado para desenvolvimento futuro

- **S5 — Parâmetros de data para DataStage**: janela de extração (DT_INICIO, DT_FIM) por pipeline, catch-up automático até D-1, injeção via argumento no `run_datastage_job.sh`. *Aguardando validação do usuário.*
- **S6** — Desativação/ativação em massa de pipelines
- **S7** — Histórico de execuções individual por pipeline
- **S8** — Métricas de tempo de execução (média, tendência 30 dias)
- **S9** — Comentários operacionais por pipeline
- **S10** — Aprovação de alterações (4-eyes)
- **S12** — Monitoramento de SLA por pipeline
- **S13** — Alerta de pipeline parado há N dias
- **S14** — Exportar / importar configurações
- **S17** — Busca global com atalho de teclado (Ctrl+K)
