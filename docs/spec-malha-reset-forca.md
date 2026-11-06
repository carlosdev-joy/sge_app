# Spec: Botão "Reset à força" da malha — Orquestra
Data: 2026-08-11 · Status: rascunho

## 1. Visão
Hoje, quando a malha entra no beco sem saída (disparo recusado por "Ciclo em
andamento" + "Data de referência diferente" e o Equalizar recusando por
duplicata), a saída é o script manual `docs/forcar-reset-ciclo-malha.sql`
(PRs #298/#299) rodado no SSMS — poderoso, mas fora do produto: sem RBAC, sem
auditoria própria, e as pré-condições (DagRuns parados, Republicar depois)
ficam por conta da disciplina do operador. Esta feature porta o script para
dentro do Orquestra: um botão **Reset à força** na tela da malha, com
pré-visualização (o dry-run vira o corpo do modal), motivo obrigatório,
confirmação forte, evento de auditoria e as pré-condições transformadas em
verificação automática.

## 2. Escopo
**IN:**
- Endpoint `POST /malhas/{malha_name}/reset-forca` com `dry_run`, modos
  **preservar** (encerra/recarimba/aposenta) e **limpar** (apaga execuções,
  eventos, corridas e telemetria de jobs — paridade com `@limpar=1`).
- Trava de pré-condição: recusa se houver DagRun em voo de membro (consulta
  via proxy Airflow), nomeando quais.
- Modal no front: pré-visualização das listas, escolha do modo com avisos
  (guardiã pode reenviar cards; ODATE anterior exige alvo naquela data),
  motivo obrigatório, confirmação digitando o nome da malha.
- Auditoria: evento `RESET_FORCA` em `etl_dependencia_evento` com quem,
  motivo, modo e contadores por passo.
- Encadeamento pós-reset: CTA "Republicar pipelines" (reusa
  `POST /malhas/{m}/republicar`) no resultado do modal.
- O cabeçalho do script SQL passa a apontar para o botão como caminho
  preferencial (o script vira o plano B de quando a API está fora).

**OUT (explícito):**
- Matar/pausar DagRuns pelo botão (write-back no Airflow) — v2; na v1 a trava
  apenas recusa e aponta a tela de Execuções (backlog).
- Reset em lote de várias malhas; agendamento de reset.
- Apagar histórico ANTERIOR à data-alvo (continua intocável, como no script).
- Tela/relatório sobre `etl_job_execution` além do contador do resultado.
- Permissão nova em tabela de perfis (reusa o catálogo fixo de `api/deps.py`
  — ver §8a).

## 3. Arquitetura proposta
- **Back**: service novo `api/services/malha_reset.py` portando os passos do
  script (transação única pyodbc, placeholders `?` — ⚠️ árvore `api/` usa
  pyodbc, nunca `%s`): 1 encerrar em aberto → 2 recarimbar no recorte da
  trava 2 com sufixo anti-colisão `_forca_<id>` → 3 aposentar (`substituida_em`,
  contrato 078) → 4 cancelar corridas via `mc.fechar_corrida`
  (`api/services/malha_corrida.py`) → 5 rastro (modo preservar) → 6 limpeza
  (modo limpar: eventos, execuções, corridas com cascade do snapshot,
  `etl_job_execution` por `pipeline` + `start_time`). O corte do ciclo reusa
  `_inicio_do_ciclo`/`_virada_global` de `api/routers/malhas.py` (NÃO
  reimplementa: é a mesma régua da trava, com compensação de relógio do
  banco — resolve o skew que o script só documenta).
- **Endpoint**: `POST /malhas/{malha_name}/reset-forca` em
  `api/routers/malhas.py`, body `{data_referencia, modo: "preservar"|"limpar",
  dry_run, motivo, ignorar_dagruns?}`; `dry_run` devolve as listas
  (em_aberto, recarimbar, sufixados, aposentar, corridas, e as 4 listas do
  limpar); execução devolve contadores por passo. Erros no padrão `apiFetch`
  (`err.status` + `detail` legível — contrato já mordeu uma vez).
- **Trava DagRun**: para cada membro com `dag_criada=1`, consulta
  `GET /api/v1/dags/{dag_id}/dagRuns?state=running` pelo cliente do proxy
  `api/routers/airflow.py`. Airflow inacessível → 503 nomeando a causa;
  `ignorar_dagruns=true` (consciente, vai para o evento) prossegue — ver §8b.
- **Front**: botão "Reset à força" na zona administrativa da malha
  (`ui-react/src/pages/Malha.tsx` + `components/malhas/MalhaEditor.tsx`),
  visível só com a permissão; modal novo
  `components/malhas/ResetForcaModal.tsx` no padrão dos modais existentes
  (`AgendamentoInicioModal.tsx`), tokens `canvas/panel/edge/ink` claro+escuro.
- **Auditoria**: evento `RESET_FORCA` (tipo novo, VARCHAR livre — sem
  migration) com `detalhe` = quem/motivo/modo/contadores; âncora fixa no 1º
  membro (lição do rastro rastejante, PR #298).
- **Decisões e alternativas descartadas**:
  - Executar o script .sql pelo backend (sqlcmd) — descartado: a API já tem
    transação e os helpers; port em Python testável no pytest.
  - Migration/trilho 6c para o reset — descartado (discussão 2026-08-11):
    operação parametrizada e repetível não é mudança de schema.
  - Permissão nova por tabela — descartado na v1: catálogo de permissões é
    fixo em `api/deps.py`; criar modelo novo de permissão é feature própria.

## 4. Modelo de dados
**Nenhuma migration.** Tipo de evento `RESET_FORCA` é valor novo em coluna
VARCHAR existente; permissão reusa `PERM_ADMIN` (`acao_admin`, §8a).
Nota: a numeração 088 está reservada pelo rascunho da spec de chamados
(PR #297) — se uma decisão da §8 exigir migration, usar o próximo número
livre no momento da F1 e registrar aqui.

## 5. Fases
### F1 — Service + endpoint em modo leitura (dry-run)
- Entregável: `api/services/malha_reset.py` com TODAS as consultas do
  dry-run (paridade de predicado com o script) + endpoint aceitando apenas
  `dry_run=true` (422 para execução — "chega na F2").
- Inclui: port do corte da virada reusando `_inicio_do_ciclo`; listas
  em_aberto/recarimbar/sufixados/aposentar/corridas/limpar; permissão
  `PERM_ADMIN` já no endpoint.
- Critérios de aceite: dado o cenário QA5 desta sessão recriado no dev,
  quando chamo o dry-run, então as listas batem 1:1 com o dry-run do script
  (mesmos ids); sem permissão → 403; malha inexistente → 404.
- Validação: pytest (cenários de paridade com SQL Server dev, padrão
  `tests/test_dependencias_f6_vivo.py`) + tsc/eslint baseline + build.
- Revisão adversarial multi-agente antes da PR. PR: `feat: reset à força da
  malha — service e pré-visualização (F1)`.

### F2 — Execução: modos preservar e limpar + trava DagRun + auditoria
- Entregável: o endpoint executa de verdade, com tudo-ou-nada.
- Inclui: passos 1–6 na transação (sufixo anti-colisão, guards, idempotência);
  `motivo` obrigatório (padrão do encerrar corrida); trava DagRun em voo via
  proxy `airflow.py` com `ignorar_dagruns` auditado; evento `RESET_FORCA`
  com contadores; 503 nomeado com Airflow fora.
- Critérios de aceite: cenários QA2/QA4/QA5/QA7 desta sessão como testes —
  colisão NULL×NULL sufixa sem 2601, rastro não rasteja, escopo não vaza
  para não-membro, job antigo/vizinho sobrevive, 2ª chamada devolve tudo 0;
  com DagRun de membro rodando → 422 nomeando o run; `ignorar_dagruns=true`
  → prossegue e o evento registra.
- Validação: pytest + tsc/eslint baseline + build + revisão adversarial
  (obrigatória: é o passo que apaga dado de produção). PR: `feat: reset à
  força da malha — execução com auditoria (F2)`.

### F3 — Modal no front
- Entregável: botão + `ResetForcaModal.tsx` completo.
- Inclui: pré-visualização (dry-run) ao abrir; radio preservar/limpar com os
  dois avisos (guardiã reenvia cards; ODATE anterior → alvo naquela data);
  campo motivo; confirmação digitando o nome da malha; resultado com
  contadores por passo; erros via `err.status`/`err.message` do `apiFetch`;
  botão invisível sem `acao_admin`; `dist/` rebuildada e commitada.
- Critérios de aceite: dado usuário sem permissão, então o botão não existe
  e o endpoint nega; dado dry-run com listas vazias, então o modal diz "nada
  a fazer" e desabilita executar; digitar nome errado mantém o botão
  desabilitado; CSS sem os três pecados conhecidos (especificidade/overlay,
  `overflow-hidden`×`sticky`, comentário com `*/`).
- Validação: tsc/eslint baseline + build + revisão adversarial. PR:
  `feat: reset à força da malha — modal com pré-visualização (F3)`.

### F4 — Encadeamento pós-reset + polimento + docs
- Entregável: fluxo fechado de ponta a ponta.
- Inclui: CTA "Republicar pipelines" no resultado (reusa
  `POST /malhas/{m}/republicar`) + lembrete do disparo com a data desejada;
  cabeçalho do script .sql apontando para o botão; `/simplify` no conjunto;
  MANUAL_USUARIO.md se aplicável.
- Critérios de aceite: após reset com sucesso, o CTA republica e o banner
  confirma; o script .sql cita o botão como caminho preferencial.
- Validação: tsc/eslint baseline + build + pytest + revisão adversarial.
  PR: `feat: reset à força da malha — encadeamento e polimento (F4)`.

## 6. Riscos e mitigações
| # | Risco | Impacto | Mitigação |
|---|-------|---------|-----------|
| 1 | Port divergir do script (predicados sutis: corte, sufixo, janelas) | Reset que "passa" mas deixa trava viva, ou apaga a mais | Testes de paridade F1/F2 reproduzindo os cenários QA desta sessão; o service cita o script como referência canônica; revisão adversarial dedicada por fase |
| 2 | DELETE com escopo errado em produção | Perda de histórico de terceiros | Confirmação digitando o nome da malha; dry-run obrigatório no fluxo do modal; testes de não-membro/história antiga; evento com contadores para conferência pós-fato |
| 3 | Trava DagRun depende do Airflow vivo | Reset bloqueado num incidente (exatamente quando é preciso) | 503 nomeando a causa + `ignorar_dagruns` consciente e auditado; o script .sql permanece como plano B documentado |
| 4 | Guardiã reenvia cards do Teams após limpar eventos | Ruído/alarme falso para a operação | Aviso no modal (modo limpar) e no resultado; documentado no manual |
| 5 | Botão destrutivo visível/da permissão errada | Operador sem contexto aperta | `PERM_ADMIN` no endpoint E no front (botão oculto); 403 testado na F1 |

## 7. Smoke pós-deploy
a) Como usuário sem `acao_admin`, abrir a malha → botão não aparece; chamar o
   endpoint à mão → 403.
b) Como admin, abrir o modal numa malha suja → listas da pré-visualização
   coerentes com as telas (mesmos pipelines/datas).
c) Executar modo **preservar** com motivo → contadores > 0, travas do disparo
   zeram (a tela de disparo libera), evento `RESET_FORCA` no painel.
d) Executar modo **limpar** numa malha de teste → Execuções/Gestão de Falhas
   sem os jobs do período; aviso da guardiã exibido; contadores batem.
e) Com um DagRun de membro rodando → recusa nomeando o run; com
   `ignorar_dagruns` → prossegue e o evento registra a escolha.
f) CTA "Republicar pipelines" ao final → republicação confirmada.
g) Disparar a malha na data desejada → parte limpa, dependentes pelo push.
h) Rodar o reset duas vezes seguidas → segunda execução devolve tudo 0, sem
   erro.

## 8. Pendências e decisões em aberto
a) **Permissão**: recomendo `PERM_ADMIN` (`acao_admin`) — apagar dado de
   produção não deveria caber no mesmo `acao_executar` do disparo. Confirmar.
b) **`ignorar_dagruns`**: manter o bypass (com auditoria) ou bloquear sempre
   que o Airflow estiver fora? Recomendo manter — é a saída de emergência,
   mesma filosofia do encerrar corrida que não passa pelo portão.
c) **Matar DagRuns pelo botão** (write-back no Airflow): fica para v2?
   Recomendo sim (OUT nesta spec).
d) **Quando construir**: depois do deploy do trem da malha (mesma fila da
   spec de chamados #297)? Confirmar a ordem entre as duas.
