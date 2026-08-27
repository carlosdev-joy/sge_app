# SDD ledger — plan: docs/superpowers/plans/2026-08-22-servicenow-inteligencia-operacional-a.md

## Contexto
- Ambiente: produção /opt/airflow (sem git — atualizaremos sge_app ao final)
- Spec: docs/superpowers/specs/2026-08-22-servicenow-inteligencia-operacional-a.md
- Início: 2026-08-23

## Pre-flight scan

| Par de tasks | Arquivo compartilhado | Verificação |
|---|---|---|
| T1→T2 | tabelas DB | T1 cria tabelas; T2 lê via hook — OK, sequencial |
| T1→T3 | etl_chamado_ciclo | T1 cria; T3 insere — OK |
| T2→T3 | servicenow_sync.py | T2 adiciona funções; T3 importa — OK |
| T3→T4 | etl_chamado_ciclo | T3 insere modo='delta'; T4 insere modo='full' — OK |
| T2→T4 | servicenow_sync.py | T4 usa mesmas funções da T2 — OK |
| T5 | chamados.py | T5 modifica FRESCOR e adiciona endpoints; T9 confirma valor=8 — sem conflito |
| T6→T7 | AdminServiceNow.tsx | T6 cria; T7 não toca — OK |
| T8 | rotas | T8 adiciona rota indicadores; T6 adiciona rota admin — paths distintos, OK |
| T9 | chamados.py | T9 confirma FRESCOR=8 já feito em T5 — idempotente |

**Scan limpo — nenhum conflito encontrado.**

---

## Progresso das Tasks

### Task 10: complete
- 92/92 testes Python PASS
- 9/9 tabelas + tem_anexo confirmadas no banco
- etl_servicenow_delta e etl_servicenow_full registradas no scheduler
- Build frontend passou após correções; deploy para /opt/airflow/ui-react/dist/
- Endpoints 401 confirmados (/chamados/indicadores/historico, /admin/servicenow/config)
- Ruling: rota /chamados/indicadores/historico movida antes de /{sys_id}/ — bug de ordering FastAPI, sem custo
- Ruling: Vite 5.x (downgrade de 8.x) — Node 20.18 incompatível com Vite 8; upgrade futuro requer Node 20.19+
- Parked (minor): bundle JS 705 KB — code-splitting a considerar em sprint futura

### Task 9: complete
- FRESCOR_ALERTA_MINUTOS=8 confirmado em chamados.py
- test_servicenow_cadencia.py não existe (não criado — spec futura)
- isINCAtivo criado em ui-react/src/lib/chamado.ts
- 92/92 testes Python PASS, tsc: 0 erros

### Task 8: complete
- ChamadosIndicadoresHistorico.tsx criado com 4 gráficos Recharts v3.8.1
- App.tsx e nav.ts atualizados (rota + link adminOnly)
- tsc --noEmit: 0 erros

### Task 7: complete
- ChamadoDetalheModal.tsx e ChamadoKanbanCard.tsx criados em ui-react/src/components/
- tsc --noEmit: 0 erros
- Ruling: kanban ainda está na UI legada (não React) — ChamadoKanbanCard criado como standalone pronto para integração futura. Modal é independente e pode ser usado em qualquer contexto React. Custo se errado: nenhum, é código novo não conectado a nada quebrado.

### Task 6: complete
- AdminServiceNow.tsx criado em /opt/git/sge_app/ui-react/src/pages/
- Admin.tsx e App.tsx modificados (aba ServiceNow + rota admin/servicenow)
- tsc --noEmit: 0 erros
- Ruling: frontend source está em /opt/git/sge_app/ui-react/ (não /opt/airflow/ui-react/ que é só o dist compilado). Build+deploy para /opt/airflow/ui-react/dist/ será feito na Task 10.
- Ruling: apiFetch (fetch nativo) em vez de axios — padrão real do projeto

### Task 5: complete
- 12 endpoints adicionados a chamados.py (detalhe, proxy anexos, indicadores, admin completo)
- FRESCOR_ALERTA_MINUTOS=8 confirmado
- 33 novos testes, 92/92 PASS (zero regressões)
- Ruling: httpx em vez de requests para disparar-delta (requests não instalado no container)

### Task 4: complete
- dags/etl_servicenow_full.py criada, registrada no scheduler
- Schedule 0 2,14, max_active_runs=1, dagrun_timeout=25min, 3 tasks confirmadas
- Ruling: proxy= (singular) em vez de proxies= — padrão httpx 0.28+ já em uso no projeto

### Task 3: complete
- dags/etl_servicenow_delta.py criada, registrada no scheduler
- Schedule */5, max_active_runs=1, dagrun_timeout=8min, 4 tasks confirmadas
- Ruling: decrypt_password via _decifrar() local (padrão das DAGs existentes, api/services não está no sys.path do scheduler)

### Task 2: complete
- 10 funções adicionadas a servicenow_sync.py
- 12 testes novos PASS + 60/60 suite completa (zero regressões)
- proxy_da_config já existia no arquivo — sem impacto na Task 3
- Ruling: ordem do fixture snapshot ajustada (SELECT antes do INSERT) — custo zero se errado, testes confirmam

### Task 1: complete
- 5 migrations criadas e aplicadas em DMDB41
- 9/9 tabelas + coluna tem_anexo confirmadas
- Ruling: VARCHAR(32) nas FKs de sys_id_nota/sys_id_chamado/sys_id_anexo (etl_chamado.sys_id é VARCHAR, não NVARCHAR) — baixo risco, apenas afeta novas tabelas criadas agora

