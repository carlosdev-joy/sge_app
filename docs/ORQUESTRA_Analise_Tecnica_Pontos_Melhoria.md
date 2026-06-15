# ORQUESTRA — Análise Técnica e Pontos de Melhoria

> Versão analisada: v2.3.0 · Data: 2026-06-15
> Complementa e atualiza `AUDITORIA_TECNICA.md` (2026-06-12) com novos achados pós-migração React.

---

## 1. Estado atual (resumo executivo)

| Camada | Situação |
|---|---|
| Frontend React | 10 páginas, TypeScript, Tailwind, TanStack Query; `dist/` commitado no Git (correto para air-gap) |
| Frontend legado | `ui/index.html` ainda serve como fallback; login redireciona ao React |
| API | FastAPI 0.115; 16 routers, 43+ endpoints; `from __future__ import annotations` em todos os arquivos |
| Banco | SQL Server; 23 migrations manuais; 20+ tabelas `etl_*`; sem FK constraints nas tabelas críticas |
| Orquestração | Airflow 2.11.2 CeleryExecutor; factory gera DAGs em `dags/generated/` |
| Testes | Zero testes automatizados |
| Autenticação | Credenciais validadas contra Airflow; senha já não persiste em localStorage (resolvido em v2.3) |

---

## 2. Gaps críticos de segurança

### S1 — Endpoints sem autenticação (novos achados)

Além dos endpoints de escrita (`/pipelines/register`, `/admin/*`) já documentados na auditoria anterior, foram identificados endpoints de **leitura** que também não exigem autenticação:

| Endpoint | Situação |
|---|---|
| `GET /datastage/log/{ds_job}` | Sem `Depends(require_perm(...))` — qualquer host da rede lê logs |
| `GET /factory/runs` | Sem autenticação — histórico de geração de DAGs exposto |
| `GET /airflow/proxy/*` | Proxy sem validação de token — permite navegar no Airflow sem login |
| `GET /catalogo/*` | Endpoints de catálogo de dados sem proteção |

**Risco**: qualquer máquina da rede corporativa pode consultar logs de jobs (que podem conter dados sensíveis), histórico de DAGs e estrutura interna do catálogo.

**Correção**: aplicar `Depends(require_perm(PERM_LEITURA))` nesses endpoints. A infraestrutura de autenticação já existe — só não foi aplicada a todos os routers.

### S2 — Endpoint `/auth/airflow-header` expõe credencial de serviço

O endpoint retorna o header `Authorization` codificado da conta de serviço do Airflow. Qualquer usuário autenticado pode obtê-lo e usar a conta de serviço diretamente.

**Correção**: remover o endpoint ou restringir a `require_perm(PERM_ADMIN)`. O frontend não precisa desse header — as chamadas ao Airflow devem ser proxiadas pela própria API.

### S3 — SQL injection em stored procedure legada

Em `sp_etl_pipeline_delete` (migration 007 ou 008), há concatenação direta de `@pipeline_name` em SQL dinâmico dentro da procedure:

```sql
-- Padrão inseguro encontrado:
SET @sql = 'DELETE FROM etl_pipeline WHERE pipeline_name = ''' + @pipeline_name + ''''
EXEC(@sql)
```

**Risco**: baixo em produção (apenas administradores chamam delete), mas viola o princípio de "SQL sempre parametrizado" que é um ponto forte documentado da plataforma.

**Correção**: reescrever com `sp_executesql` e parâmetros, ou substituir por DELETE direto sem SQL dinâmico.

### S4 — CORS `allow_origins=["*"]` ainda ativo

Confirmado nos routers principais. Combinado com a ausência de autenticação em alguns endpoints, permite chamadas cross-origin de qualquer página interna.

**Correção**: restringir à origem do nginx (ex.: `http://localhost` ou o hostname corporativo). Já documentado na auditoria anterior, ainda não corrigido.

---

## 3. Gaps de integridade de dados

### D1 — Ausência de FK constraints nas tabelas principais

As tabelas `etl_pipeline_job`, `etl_job_lineage`, `etl_job_execution` e `etl_sla_alert` **não possuem FK constraints** para `etl_pipeline`. Isso significa:

- Um pipeline pode ser deletado deixando jobs, execuções e lineage órfãos.
- Orphans já ocorreram em produção (bug de deleção de job corrigido em v2.3.0 via soft-delete na API).
- Consultas de governança podem retornar dados de pipelines inexistentes.

**Correção**: adicionar `FOREIGN KEY ... ON DELETE CASCADE` ou `ON DELETE SET NULL` nas migrations. Como o SQL Server está no `DMDB41` compartilhado, coordenar com DBA antes de alterar constraints.

### D2 — `pool_name` cadastrado mas não aplicado no factory

O wizard permite cadastrar um pool do Airflow para o pipeline (`pool_name`), e o valor é salvo no banco. Porém o `etl_dag_factory.py` **não lê nem aplica** esse campo ao gerar o DAG — todos os jobs usam o pool `default_pool` implicitamente.

**Impacto**: limitação de concorrência via pool não funciona, mesmo que o administrador configure.

**Correção**: no factory, ler `pool_name` e passá-lo para cada operador:
```python
op = SSHOperator(..., pool=pipeline.get('pool_name') or 'default_pool')
```

### D3 — `tipo_agendamento = 'hourly_n'` colapsa para `'custom'` no banco

O wizard exibe "De hora em hora" como opção de agendamento (`hourly_n`), mas ao salvar, o backend normaliza para `'custom'` com `horarios_especificos` calculados. Ao recarregar o pipeline para edição, o tipo original `hourly_n` é perdido — o wizard exibe "Horários específicos" em vez de "De hora em hora".

**Impacto**: UX de edição confusa; desenvolvedores não reconhecem o agendamento original.

**Correção**: preservar `tipo_agendamento = 'hourly_n'` no banco e tratar no factory; ou mapear de volta ao detectar o padrão de horários.

### D4 — Schema divergente em `sp_etl_pipeline_delete` audit trail

A stored procedure de deleção registra auditoria em `etl_pipeline_audit`, mas o schema esperado pela procedure difere da migration que criou a tabela (campo `deleted_by` vs `usuario` dependendo da versão). Em ambientes onde as migrations não foram aplicadas em ordem, a procedure falha silenciosamente sem registrar a auditoria.

**Correção**: unificar e testar a procedure contra o schema atual; adicionar teste de smoke no CI (quando CI existir).

### D5 — Duas versões divergentes de `sp_etl_seq_import_approve`

Foram encontradas duas versões da stored procedure de aprovação de import de sequence DataStage — uma em `sql/migrations/` e uma em `sql/` (raiz). As versões têm lógica diferente para tratamento de jobs duplicados.

**Risco**: dependendo de qual foi aplicada no servidor, o comportamento do import DSX pode ser inconsistente.

**Correção**: manter apenas uma versão, na migration numerada correta. Arquivos soltos em `sql/` (raiz) devem ser removidos ou movidos.

---

## 4. Gaps de arquitetura e qualidade

### A1 — Gerenciamento de conexão inconsistente (16 routers, 1 padrão correto)

Apenas o router `admin.py` usa o context manager `managed_conn` para abrir/fechar conexões com o SQL Server. Os outros 15 routers abrem conexão manualmente com `pyodbc.connect(...)` e fecham no `finally` — sem pooling, sem tratamento de reconexão automática, sem timeout configurado.

**Impacto**: em picos de carga, conexões podem ficar abertas por erro de programação ou exception não tratada; sem pool, cada request cria uma nova conexão (custo alto no SQL Server).

**Correção**: extrair `get_db_conn()` como dependency do FastAPI com `yield` (context manager), aplicar em todos os routers. Exemplo:
```python
# db.py
from contextlib import contextmanager
@contextmanager
def get_conn():
    conn = pyodbc.connect(CONN_STR, timeout=30)
    try:
        yield conn
        conn.commit()
    except:
        conn.rollback()
        raise
    finally:
        conn.close()
```

### A2 — DDL em handler de request (`_ensure_resolve_columns`)

A função `_ensure_resolve_columns` em `routers/lineage.py` executa `ALTER TABLE ... ADD COLUMN` durante um request HTTP normal. Se duas requests simultâneas chegarem antes da coluna existir, ambas tentam criar a mesma coluna — falha com erro de duplicidade.

**Correção**: mover o DDL para uma migration numerada; remover a criação dinâmica de coluna do runtime.

### A3 — `from __future__ import annotations` em todos os routers

Essa diretiva torna todas as anotações de tipo lazy strings (avaliadas apenas quando necessário). O FastAPI depende da introspecção de tipos em tempo de execução para resolver parâmetros de endpoints. Isso causou o bug da 422 no `POST /pipelines/projects` (corrigido em v2.3.0 com o padrão `body: dict = Body(default={})`), mas o risco persiste em qualquer endpoint novo que use tipos complexos.

**Correção**: remover `from __future__ import annotations` de todos os routers da API; usar `from typing import Optional` diretamente onde necessário.

### A4 — Ordenação de criticidade quebrada no Dashboard

O backend ordena execuções por criticidade com `ORDER BY CASE criticidade WHEN 'ALTA' THEN 1 ...` mas os valores armazenados no banco são `'Alta'`, `'Media'`, `'Baixa'` (primeira letra maiúscula). O CASE é case-sensitive no SQL Server — a ordenação não funciona.

**Correção**: padronizar os valores no banco (migration) ou usar `UPPER(criticidade)` no ORDER BY.

### A5 — Página Pipelines.tsx com 2230+ linhas

A página de Pipelines concentra o wizard (6 etapas), a listagem, os cards, as ações (executar, editar, excluir, gerar DAG) e os filtros — tudo em um arquivo. Mudanças em uma etapa do wizard arriscam quebrar a listagem.

**Correção (Fase A)**: extrair componentes:
- `PipelineWizard.tsx` (wizard de 6 etapas)
- `PipelineCard.tsx` (card de listagem)
- `PipelineFilters.tsx` (filtros e busca)
- `PipelineActions.tsx` (botões de ação)

### A6 — URL do Airflow hardcoded no frontend

`AIRFLOW_UI = 'http://localhost:8080'` está hardcoded em `Pipelines.tsx` e outros arquivos. Em ambientes onde o Airflow roda em host diferente, os links do frontend apontam para lugar errado.

**Correção**: expor via endpoint `GET /config/airflow-ui-url` ou ler de variável de ambiente injetada no build (`import.meta.env.VITE_AIRFLOW_URL`).

### A7 — Filtro de domínio na Malha age apenas na página corrente

O filtro de "domínio" na aba Malha filtra somente os cards já carregados na página atual da paginação. Pipelines em outras páginas com o domínio selecionado não aparecem.

**Correção**: passar o filtro de domínio como query param para a API (`GET /malha?dominio=...`) em vez de filtrar no frontend.

---

## 5. Gaps de processo e operação

### P1 — Zero testes automatizados

Toda regressão é descoberta em produção pelo usuário. O bug de `pipelineToDagId` (lowercase vs original case) que causava "DAG not found" é um exemplo direto: um teste de smoke teria capturado antes do deploy.

**Correção mínima viável** (sem CI, sem internet):
```bash
# Vendorizar wheels do pytest no Git
wheels/pytest-8.x.x-py3-none-any.whl
# Smoke tests básicos:
# - Importar todos os routers sem erro
# - Compilar todos os DAGs gerados: python -m py_compile dags/generated/*.py
# - 3-5 testes de endpoint crítico com sqlite em memória
```

### P2 — Sem tabela de controle de migrations

Não há `etl_schema_version` ou similar. Em ambientes distintos (dev, hom, prod), não é possível saber quais migrations já foram aplicadas sem inspecionar o banco manualmente.

**Correção**: criar `etl_schema_version (migration_id, applied_at, applied_by)` e um script `sql/migrate.py` que registra cada migration aplicada (já descrito na auditoria anterior).

### P3 — Arquivos legados na raiz do projeto

Arquivos `versao_*.html`, pastas `script/` e `scripts/` (duplicatas), e arquivos `.sql` na raiz (fora de `sql/migrations/`) confundem novos membros do time sobre o que é código ativo.

**Correção**: mover ou deletar durante o próximo ciclo de limpeza; nunca comprometer arquivos legados junto com código novo.

### P4 — `nginx:latest` sem versão fixada

Já documentado na auditoria anterior. Em rebuild offline, a imagem `latest` pré-carregada pode divergir da esperada.

**Correção**: `nginx:1.27-alpine` pinado.

### P5 — Redis sem senha e Postgres com credenciais padrão

Já documentado. Válido repetir: qualquer host da rede pode conectar no Redis e ler/escrever na fila de tarefas do Celery; o Postgres do Airflow usa `airflow:airflow`.

---

## 6. Oportunidades de melhoria de produto (UX/funcional)

| # | Oportunidade | Valor |
|---|---|---|
| U1 | **Notificação de sucesso por pipeline**: além dos alertas de falha/SLA, enviar card no Teams quando pipeline crítico conclui com sucesso | Confirma entrega de dados sem que o time precise verificar manualmente |
| U2 | **Filtro cross-página funcional na Malha** (ver A7) | Usuários com muitos pipelines não conseguem filtrar efetivamente hoje |
| U3 | **Histórico de edições de pipeline**: registrar em `etl_pipeline_audit` o que mudou, quem mudou e quando | Auditoria e rastreabilidade de configuração |
| U4 | **Dependências visuais entre pipelines no diagrama da Malha** | Hoje as dependências por Dataset aparecem em texto; um grafo visual facilitaria planejamento |
| U5 | **Busca global** (Ctrl+K / barra de comando): buscar pipelines, jobs, tabelas do catálogo em qualquer tela | Produtividade para times com centenas de pipelines |
| U6 | **Relatório de aderência ao SLA por período**: exportar PDF/Excel com % de entregas no prazo por pipeline | Insumo para reuniões de gestão e negociação de capacidade |
| U7 | **Dry-run de DAG**: simular a geração sem gravar em disco | Valida o factory antes do deploy real |

---

## 7. Roadmap sugerido (atualizado)

### Fase 1 — Fechar gaps de segurança (prioridade máxima)
1. Aplicar `require_perm(PERM_LEITURA)` nos endpoints expostos (S1).
2. Remover ou proteger `/auth/airflow-header` (S2).
3. Corrigir `sp_etl_pipeline_delete` (S3).
4. Restringir CORS à origem do nginx (S4).
5. Remover `from __future__ import annotations` dos routers (A3).

### Fase 2 — Integridade e confiabilidade de dados
6. Adicionar FK constraints nas tabelas `etl_*` (D1) — coordenar com DBA.
7. Aplicar `pool_name` no factory (D2).
8. Preservar `tipo_agendamento = 'hourly_n'` (D3).
9. Corrigir ordenação por criticidade no Dashboard (A4) — 1 linha de SQL.
10. Unificar `sp_etl_seq_import_approve` (D5).
11. Criar `etl_schema_version` + `sql/migrate.py` (P2).

### Fase 3 — Qualidade de código
12. Extrair `get_db_conn()` como dependency compartilhado (A1).
13. Mover DDL de `_ensure_resolve_columns` para migration (A2).
14. Dividir `Pipelines.tsx` em componentes (A5).
15. Externalizar URL do Airflow (A6).
16. Adicionar smoke tests + `py_compile` dos DAGs gerados (P1).

### Fase 4 — Melhorias de produto
17. Filtro cross-página na Malha via API (A7 / U2).
18. Notificações de sucesso para pipelines críticos (U1).
19. Histórico de edições de pipeline (U3).
20. Relatório de aderência ao SLA (U6).

---

## 8. Matriz de priorização

| Gap | Severidade | Esforço | Prioridade |
|---|---|---|---|
| S1 — Endpoints sem auth | CRÍTICO | Baixo (1-2h) | **Imediato** |
| S2 — Airflow-header exposto | CRÍTICO | Baixo (30min) | **Imediato** |
| A4 — Criticidade sem ordenação | ALTO | Baixíssimo (5min SQL) | **Imediato** |
| D2 — pool_name ignorado | ALTO | Baixo (1h) | Sprint atual |
| D3 — hourly_n colapsa | ALTO | Médio (3h) | Sprint atual |
| S3 — SQL injection em SP | ALTO | Médio (2h) | Sprint atual |
| A1 — Gerenciamento de conexão | ALTO | Alto (1-2 dias) | Próxima sprint |
| D1 — Sem FK constraints | ALTO | Médio (DBA) | Próxima sprint |
| A5 — Pipelines.tsx 2k linhas | MÉDIO | Alto (2-3 dias) | Backlog |
| P1 — Zero testes | MÉDIO | Alto (3-5 dias) | Backlog |
| U1-U7 — Melhorias UX | BAIXO-MÉDIO | Variado | Roadmap |
