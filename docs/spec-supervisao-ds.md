# Spec: Supervisão de Jobs DataStage — Orquestra

Data: 2026-07-29 · Status: rascunho (aguardando aprovação)

## 1. Visão

Jobs críticos do DataStage falham ou simplesmente não rodam, e hoje isso só é
descoberto quando alguém abre o **Console DataStage** e consulta job por job,
manualmente. Não existe registro histórico de quando cada job iniciou e terminou
em cada dia.

Esta feature cadastra um conjunto de **jobs supervisionados**, coleta o resumo de
runs desses jobs a cada 15 minutos, classifica o estado do dia (abortou, não
executou, iniciou com atraso, falha de estrutura), mostra o resultado numa área
nova do **Dashboard** — respeitando o seletor de data que já existe — e notifica
o canal do **Teams** escolhido entre os grupos já cadastrados.

Quando estiver pronto: falha ou atraso de job supervisionado é detectado em até
15 minutos sem ninguém olhando a tela, e o histórico de horários de início e
término acumula para embasar o SLA desses jobs no futuro.

## 2. Escopo

**IN:**

- Cadastro de jobs supervisionados em aba nova do **Console DataStage**: projeto,
  job, janela de início esperada (de/até), tolerância, dias da semana em que
  vale, **data de início da vigência**, **limite de linhas do logsum**, canal do
  Teams, template da mensagem, quais alertas ligar e ativo/inativo.
- **Vigência**: o monitoramento só avalia dias a partir da data escolhida. Nada
  antes disso vira evento, mesmo que o log ainda tenha o run.
- **Card de situação inicial**: quando um job entra em vigência, o primeiro ciclo
  envia ao Teams o cenário do dia (executou e terminou às X, abortou, ainda não
  executou, ou janela ainda não chegou), para o usuário validar a configuração
  assim que ligar o monitoramento. Sai **uma vez por job**, mesmo quando está tudo certo.
- A lista de jobs é **dinâmica**: entra e sai pela tela, sem carga inicial fixa.
  Tirar um job de supervisão **preserva** o histórico já coletado.
- **DAG de coleta a cada 15 min**: uma conexão SSH reaproveitada roda
  `dsjob -logsum` de cada job supervisionado ativo, segmenta os runs dos últimos
  7 dias e classifica o estado do dia corrente.
- Quatro categorias de alerta: **ABORTOU**, **NAO_EXECUTOU**, **ATRASO** (passou
  o fim da janela + tolerância sem iniciar) e **ESTRUTURA** (o próprio `dsjob`
  não conseguiu ler o job — projeto/job inexistente, renomeado, SSH fora).
- **Área no Dashboard** com badge por job, ligada ao seletor de data existente
  (`ui-react/src/pages/Dashboard.tsx:474`): trocar o dia mostra o histórico
  daquele dia.
- Gravação, por dia, de **início e término de cada run observado** — base
  histórica para a futura sugestão de SLA.
- **Notificação no Teams** 1x por ocorrência, no canal de `dbo.etl_msg_grupo`,
  com card montado a partir de `dbo.etl_msg_template`.
- Expurgo automático de registros com mais de 1 ano.

**OUT (explícito):**

- **Sugestão automática de SLA** e alerta de "demorou mais que o normal" — esta
  entrega só acumula a base. Vira fase futura quando houver semanas de dado real.
- **Janela de conclusão** (prazo de término) como gatilho de alerta — fica no
  backlog junto com a sugestão de SLA.
- Qualquer **ação sobre o job** (rerun, reset, parar). O Console DS permanece
  somente leitura, com a allowlist de subcomandos de `api/services/ssh_datastage.py:33`.
- Alerta por **e-mail, WhatsApp** ou qualquer canal fora do Teams.
- Supervisão de **pipelines do próprio Orquestra** — já coberta por
  `dags/orquestra_sla_monitor.py`.
- **Editor de mensagem próprio**: o texto do card sai do catálogo já existente
  (Admin → catálogo de mensagens), sem tela nova de edição.
- Alerta de **warning** do DataStage (não foi marcado como gatilho na entrevista).

## 3. Arquitetura proposta

### Front

| Arquivo | Mudança |
|---|---|
| `ui-react/src/pages/DsConsole.tsx` | Aba nova `supervisao` no array `TABS` (linha 1009). CRUD dos jobs supervisionados. |
| `ui-react/src/components/dsconsole/SupervisaoTab.tsx` *(novo)* | Tabela + formulário do cadastro, isolando o CRUD do arquivo de 1281 linhas. |
| `ui-react/src/pages/Dashboard.tsx` | Seção nova consumindo `/dashboard/supervisao`, passando o `date` já existente. |
| `ui-react/src/components/dashboard/SupervisaoCard.tsx` *(novo)* | Lista de jobs supervisionados com badge de estado do dia. |

Chamadas via `apiFetch` (`ui-react/src/lib/api.ts:7`), tokens semânticos
`canvas/panel/edge/ink` em claro e escuro — **sem** tema `.caixa-theme`.

### Back

Router novo `api/routers/ds_supervisao.py`, registrado em `api/main.py`:

| Método | Rota | Guard |
|---|---|---|
| GET | `/admin/ds/supervisao` | `require_ds_console` |
| POST | `/admin/ds/supervisao` | `require_ds_console` |
| PATCH | `/admin/ds/supervisao/{sid}` | `require_ds_console` |
| DELETE | `/admin/ds/supervisao/{sid}` | `require_ds_console` |
| GET | `/dashboard/supervisao?date_ref=YYYY-MM-DD` | `get_current_user` |

`require_ds_console` (`api/deps.py:215`) já libera admin **ou** perfil com o
recurso `tela_ds_console` — não é preciso criar permissão nova. O painel do
Dashboard é leitura para qualquer usuário logado, conforme decidido.

O `webhook_url` **nunca** é devolvido cru: as leituras de grupo continuam saindo
por `api/routers/mensagens.py`, que expõe apenas `has_webhook`.

Contrato de erro: `apiFetch` propaga `err.status` e `err.message` — o front trata
422 (validação de janela/nome) e 403 (sem `tela_ds_console`) separadamente.

### Dados

Três tabelas novas na **migration 062** (detalhe na seção 4). Reuso sem
alteração de `dbo.etl_msg_grupo` e `dbo.etl_msg_template` (migrations 049/050).

### Orquestração

DAG nova `dags/etl_ds_supervisao_monitor.py`, `schedule` a cada 15 min, timezone
`America/Sao_Paulo`, `retries: 0` (o próximo ciclo é a retentativa natural):

1. Lê os jobs supervisionados ativos cujo dia da semana bate com hoje.
2. Abre **uma** conexão SSH e roda `dsjob -logsum -max N <projeto> <job>` em
   sequência — mesmo padrão de `dags/etl_ds_monitor_centralizado.py`.
3. Segmenta a saída em runs com o parser novo (`dags/utils/ds_logsum.py`).
4. Faz upsert dos runs observados dos últimos 7 dias e classifica o dia corrente.
5. Grava os eventos com chave de deduplicação e envia ao Teams o que ainda não
   foi notificado.
6. Uma vez por dia, expurga registros com mais de 1 ano.

Parser em módulo **puro** (sem SSH, sem banco) para ser testável por pytest,
como `tests/test_datastage_rows_parser.py`.

### Decisões e alternativas descartadas

- **SSH ao vivo no request do Dashboard** — descartado: 1 conexão por job com
  timeout de 120s trava a tela e não alerta sem ninguém olhando.
- **Ler só de `dbo.etl_ds_job_log`** — descartado: só enxerga jobs disparados
  pelo Orquestra; jobs agendados no próprio DataStage ficariam invisíveis.
  Continua servindo como **fonte de conferência** contra falso "não executou".
- **Permissão nova para o painel** — descartada: o objetivo é a falha ser vista
  o quanto antes.
- **Card fixo no código** — descartado: o catálogo de templates permite mudar o
  texto sem deploy.
- **Reaproveitar o `parseLogsum` do TS via porta automática** — descartado:
  reescrita manual em Python com fixtures reais, validada por teste.
- **Exclusão física do cadastro** — descartada: como o job entra e sai de
  supervisão conforme a prioridade do momento, remover apagaria o histórico que
  sustenta o SLA futuro. A remoção é **lógica** (`ativo = 0`): o job some do
  painel do dia corrente e deixa de ser coletado, mas os dias já coletados
  continuam aparecendo ao navegar para trás. Exclusão física fica disponível
  apenas para cadastro que nunca coletou nada.
- **Card de situação inicial consolidado** (um card listando todos os jobs que
  entraram em vigência no ciclo) — descartado: o objetivo é validar **job a
  job**. Cadastro em lote gera um card por job; como a validação começa no canal
  de homologação, o volume fica contido.

## 4. Modelo de dados

Arquivo: `sql/migrations/062_ds_supervisao.sql` — idempotente
(`IF OBJECT_ID(...) IS NULL`, `IF COL_LENGTH(...) IS NULL`), aplicada na
**etapa 6c do `scripts/deploy.sh`** (migrate.py dentro do container da API).

### `dbo.etl_ds_supervisao_job` — cadastro

| Coluna | Tipo | Nota |
|---|---|---|
| `id` | INT IDENTITY PK | |
| `project` | VARCHAR(128) NOT NULL | allowlist `^[A-Za-z0-9_.]+$` |
| `job_name` | VARCHAR(255) NOT NULL | idem |
| `descricao` | VARCHAR(400) NULL | |
| `janela_inicio` | TIME(0) NOT NULL | ex.: `02:00:00` |
| `janela_fim` | TIME(0) NOT NULL | ex.: `03:00:00` |
| `tolerancia_min` | INT NOT NULL DEFAULT 0 | minutos após `janela_fim` antes de acusar atraso |
| `dias_semana` | VARCHAR(20) NOT NULL DEFAULT `'1,2,3,4,5'` | CSV ISO — 1=seg … 7=dom |
| `vigencia_inicio` | DATE NOT NULL DEFAULT CAST(GETDATE() AS DATE) | nada antes desta data é avaliado |
| `max_linhas` | INT NOT NULL DEFAULT 200 | `-max` do logsum, por job; limitado a 1..2000 |
| `grupo_id` | INT NULL | ref. lógica a `etl_msg_grupo.id` |
| `template_id` | INT NULL | ref. lógica a `etl_msg_template.id` |
| `alerta_abortou` | BIT NOT NULL DEFAULT 1 | |
| `alerta_nao_executou` | BIT NOT NULL DEFAULT 1 | |
| `alerta_atraso` | BIT NOT NULL DEFAULT 1 | |
| `alerta_estrutura` | BIT NOT NULL DEFAULT 1 | |
| `ativo` | BIT NOT NULL DEFAULT 1 | |
| `created_by` | VARCHAR(20) NULL | matrícula |
| `created_at` / `updated_at` | DATETIME NOT NULL DEFAULT GETDATE() | |

`CREATE UNIQUE INDEX ux_ds_superv_job ON (project, job_name)` — o mesmo job não
é cadastrado duas vezes. Reativar um job já cadastrado é `ativo = 1` + nova
`vigencia_inicio`, não um registro novo — o histórico anterior continua ligado
ao mesmo `supervisao_id`.

**Remoção é lógica**: `DELETE` na API vira `ativo = 0`. Cadastro sem nenhum run
ou evento associado pode ser apagado de fato (o registro nunca produziu histórico).

**Janela que cruza a meia-noite** (`janela_fim < janela_inicio`, ex.: 23:00→01:00):
a `data_ref` é sempre o dia em que a janela **começa**. Regra documentada no
formulário e coberta por teste.

### `dbo.etl_ds_supervisao_run` — runs observados (base de SLA)

| Coluna | Tipo | Nota |
|---|---|---|
| `id` | INT IDENTITY PK | |
| `supervisao_id` | INT NOT NULL | |
| `data_ref` | DATE NOT NULL | dia da janela |
| `run_inicio` | DATETIME NOT NULL | normalizado em BRT |
| `run_fim` | DATETIME NULL | nulo enquanto executa |
| `duracao_seg` | INT NULL | |
| `resultado` | VARCHAR(20) NOT NULL | `ok` \| `aborted` \| `running` \| `indefinido` |
| `jobs_filhos` | INT NULL | quantidade de jobs da sequence no run |
| `coletado_em` | DATETIME NOT NULL DEFAULT GETDATE() | |

`CREATE UNIQUE INDEX ux_ds_superv_run ON (supervisao_id, run_inicio)` — o mesmo
run revisto a cada 15 min faz **upsert**, não duplica.
`CREATE INDEX ix_ds_superv_run_data ON (data_ref, supervisao_id)` — leitura do painel.

### `dbo.etl_ds_supervisao_evento` — alertas

| Coluna | Tipo | Nota |
|---|---|---|
| `id` | INT IDENTITY PK | |
| `supervisao_id` | INT NOT NULL | |
| `data_ref` | DATE NOT NULL | |
| `tipo` | VARCHAR(20) NOT NULL | `ABORTOU` \| `NAO_EXECUTOU` \| `ATRASO` \| `ESTRUTURA` \| `SITUACAO_INICIAL` |
| `chave_ocorrencia` | VARCHAR(64) NOT NULL | horário do run para `ABORTOU`; `''` para os demais |
| `detalhe` | NVARCHAR(1000) NULL | mensagem do dsjob / resumo |
| `run_inicio` | DATETIME NULL | |
| `detectado_em` | DATETIME NOT NULL DEFAULT GETDATE() | |
| `notificado_em` | DATETIME NULL | preenchido no envio ao Teams |

`CREATE UNIQUE INDEX ux_ds_superv_evento ON (supervisao_id, data_ref, tipo, chave_ocorrencia)`
— mesmo espírito de `UX_etl_sla_alert` (`sql/migrations/013_operacao_fase2.sql:28`).
É isso que garante **1 card por ocorrência**: dois abortos distintos no mesmo dia
geram dois eventos (chaves diferentes); o mesmo aborto revisto em 8 ciclos gera um.

`SITUACAO_INICIAL` usa `data_ref = vigencia_inicio` e `chave_ocorrencia = ''`,
então o índice único já garante que ele sai **uma única vez por vigência** — e
volta a sair se o job for reativado com vigência nova.

Expurgo: `DELETE` em `run`/`evento` com `data_ref < DATEADD(YEAR,-1,GETDATE())`.
O **cadastro nunca é expurgado**.

## 5. Fases

### F1 — Modelo de dados e cadastro

- **Entregável:** migration 062 aplicada, CRUD na API e aba "Supervisão"
  funcional no Console DataStage.
- **Inclui:**
  - `sql/migrations/062_ds_supervisao.sql` idempotente com as três tabelas.
  - `api/routers/ds_supervisao.py` (GET/POST/PATCH/DELETE) + registro em `api/main.py`.
  - Validação de entrada: allowlist de projeto/job, `janela_inicio`/`janela_fim`
    obrigatórias, `dias_semana` não vazio, `grupo_id` existente e ativo,
    `max_linhas` entre 1 e 2000 (mesmo cap de `build_dsjob_command`).
  - `vigencia_inicio` no formulário, com hoje como valor sugerido e aviso de que
    a partir dela o job passa a ser avaliado e a gerar o card de validação.
  - `DELETE` implementado como desativação lógica; exclusão física só quando não
    houver run nem evento ligado ao cadastro.
  - `SupervisaoTab.tsx` + entrada no `TABS` de `DsConsole.tsx`.
  - Seleção de canal e template lendo `/msg/grupos` e `/msg/templates`.
  - Rebuild da `ui-react/dist` (é commitada).
- **Critérios de aceite:**
  - Cadastrar projeto `X` + job `Y` com janela 02:00–03:00 e dias seg–sex grava e
    reaparece na lista após recarregar.
  - Cadastrar o mesmo (projeto, job) duas vezes retorna 409/422 com mensagem clara,
    não erro 500.
  - Nome de job com espaço ou `;` é recusado com 422 antes de qualquer uso.
  - `max_linhas` fora de 1..2000 é recusado com 422.
  - Remover um job que já tem histórico o marca como inativo e mantém os
    registros de `run`/`evento`; remover um cadastro recém-criado sem histórico
    apaga o registro.
  - Usuário sem `tela_ds_console` nem admin recebe 403 nas quatro rotas de escrita.
  - O select de canal lista os grupos ativos sem expor `webhook_url` no payload.
  - Rodar a migration duas vezes seguidas não gera erro.
- **Validação:** `tsc` + `eslint` (baseline HEAD, zero erros novos) + `build` + `pytest`.
- Revisão adversarial multi-agente antes da PR. PR: `feat: cadastro de jobs DataStage supervisionados`.

### F2 — Coleta e classificação

- **Entregável:** DAG rodando a cada 15 min, gravando runs e eventos. Sem Teams ainda.
- **Inclui:**
  - `dags/utils/ds_logsum.py`: parser puro que segmenta a saída do `-logsum` em
    runs (início, fim, resultado, jobs filhos), com filtro de janela de 7 dias.
  - `tests/test_ds_logsum_parser.py` com fixtures de saída **real** capturada do
    Console DS (run ok, run abortado, run em execução, saída vazia, log truncado).
  - `dags/etl_ds_supervisao_monitor.py`: conexão SSH única, upsert dos runs,
    classificação do dia, gravação dos eventos, expurgo diário de 1 ano.
  - Regras de classificação, incluindo janela que cruza a meia-noite, o dia da
    semana do cadastro e o corte por `vigencia_inicio`.
  - `-max` do logsum lido de `max_linhas` do próprio job.
  - Geração do evento `SITUACAO_INICIAL` no primeiro ciclo em que o job entra em
    vigência, descrevendo o cenário do dia mesmo quando não há problema algum.
  - Conferência contra `dbo.etl_ds_job_log` antes de acusar `NAO_EXECUTOU`.
- **Critérios de aceite:**
  - Dado um job com janela 02:00–03:00 e nenhum run até 03:00 + tolerância,
    o ciclo seguinte grava evento `ATRASO` daquele `data_ref`.
  - Dado um job que abortou, grava `ABORTOU` com `run_inicio` preenchido; oito
    ciclos seguidos com o mesmo aborto mantêm **um** evento.
  - Projeto inexistente gera `ESTRUTURA`, não `ABORTOU`, e a DAG conclui com sucesso.
  - SSH indisponível gera `ESTRUTURA` para todos os jobs do ciclo sem a task falhar.
  - Job com dias seg–sex não gera nenhum evento no sábado.
  - Job cadastrado hoje com vigência hoje gera `SITUACAO_INICIAL` no ciclo
    seguinte, com o estado real do dia (executou às X, abortou, ainda não
    executou, ou janela ainda não chegou) — e apenas um, por mais ciclos que rodem.
  - Job com vigência futura não gera nenhum evento até a data chegar; run
    anterior à vigência não vira evento retroativo.
  - Job desativado deixa de ser coletado, mas seus dias anteriores continuam
    consultáveis.
  - O parser, alimentado pelas fixtures, devolve a mesma segmentação que a tela
    mostra hoje (teste compara contra o esperado escrito à mão a partir da tela).
  - Ciclo com 30 jobs cadastrados conclui em menos de 15 min.
- **Validação:** `pytest` (baseline HEAD) + execução manual da DAG em `dags/` no ambiente.
- Revisão adversarial + `/security-review` (interpolação no comando SSH).
  PR: `feat: coleta e classificação dos jobs DataStage supervisionados`.

### F3 — Painel no Dashboard

- **Entregável:** área de supervisão visível no Dashboard, ligada ao seletor de data.
- **Inclui:**
  - `GET /dashboard/supervisao?date_ref=` em `api/routers/ds_supervisao.py`,
    devolvendo, por job: estado do dia, horários de início/término observados e
    eventos abertos.
  - `SupervisaoCard.tsx` + integração no `Dashboard.tsx` reusando o estado `date`.
  - Badges com **texto além da cor** (abortado, atrasado, não executou, sem
    verificação, ok), tokens em claro e escuro.
  - Estado vazio ("nenhum job supervisionado cadastrado") com link para a aba do
    Console DS.
  - Rebuild da `ui-react/dist`.
- **Critérios de aceite:**
  - Com a data em hoje, job atrasado aparece com badge de atraso; ao trocar para
    ontem, aparecem os eventos e horários de ontem, lidos do banco.
  - `date_ref` inválido retorna 400 com mensagem, como `/dashboard` já faz.
  - Data sem nenhum dado coletado mostra estado vazio, não spinner infinito.
  - Nenhuma chamada SSH é disparada no carregamento do Dashboard (conferido no log da API).
  - Área legível em tema claro e escuro; nenhum badge depende só de cor.
- **Validação:** `tsc` + `eslint` (baseline HEAD) + `build`.
- Revisão adversarial antes da PR. PR: `feat: painel de supervisão DataStage no dashboard`.

### F4 — Alerta no Teams

- **Entregável:** evento novo vira card no canal configurado, uma vez por ocorrência.
- **Inclui:**
  - Resolução de canal/template na DAG: `grupo_id` → `etl_msg_grupo.webhook_url`;
    `template_id` → título/corpo/`facts`/cor/botão, com fallback para card
    padrão quando não houver template.
  - Card Adaptive no padrão de `dags/orquestra_sla_monitor.py:29`.
  - Placeholders interpolados: `{projeto} {job} {tipo} {data} {inicio} {fim}`.
  - Card de `SITUACAO_INICIAL` com cor neutra e texto de validação ("monitoramento
    iniciado — situação de hoje: ..."), distinto visualmente dos alertas.
  - Marcação de `notificado_em` **após** resposta do webhook; falha de envio não
    marca (o próximo ciclo tenta de novo) e nunca derruba a task.
- **Critérios de aceite:**
  - Job abortado gera exatamente um card no canal escolhido, com projeto, job,
    tipo e horário.
  - Job que entra em vigência gera um card de situação inicial no canal escolhido,
    inclusive quando o cenário do dia está normal.
  - Ciclos seguintes com o mesmo evento não reenviam.
  - Grupo sem `webhook_url` ou inativo: evento fica gravado, log registra a
    ausência do canal, DAG conclui com sucesso.
  - Webhook devolvendo 500: `notificado_em` permanece nulo e o ciclo seguinte reenvia.
  - Nenhuma URL de webhook aparece em log ou em resposta de API.
- **Validação:** `pytest` + teste manual com webhook de canal de homologação.
- Revisão adversarial + `/security-review` (segredo em log).
  PR: `feat: alerta de supervisão DataStage no Teams`.

## 6. Riscos e mitigações

| # | Risco | Impacto | Mitigação |
|---|---|---|---|
| 1 | Parser Python diverge do `parseLogsum` do TS e classifica run errado | Alerta falso ou falha silenciosa | Fixtures de saída real em `tests/`, parser puro, comparação com o que a tela exibe hoje (critério de aceite da F2) |
| 2 | Janela cruzando a meia-noite classifica no dia errado | Alerta no dia errado, histórico furado | `data_ref` = dia de início da janela, regra documentada no form e coberta por teste |
| 3 | `logsum` traz hora do servidor Unix; janela é cadastrada em BRT | Atraso calculado errado | Normalizar em `America/Sao_Paulo` na coleta (convenção de `ui-react/src/lib/dsTime.ts`) e gravar `data_ref` já resolvida |
| 4 | Rotação/truncamento do log do DataStage esconde run antigo | Falso `NAO_EXECUTOU` | Cruzar com `dbo.etl_ds_job_log` antes de acusar; `-max` dimensionado para cobrir 7 dias |
| 5 | 30 jobs × SSH estourando o ciclo de 15 min | Coleta atrasada, alerta tardio | Conexão única reaproveitada, timeout por job, corte do ciclo com log do que ficou de fora |
| 6 | **`dags/` só é sincronizado com confirmação no deploy (etapa 5)** | DAG nova não sobe e a feature fica muda em produção | Smoke `(a)` confirma a DAG listada no Airflow antes de qualquer outro passo |
| 7 | `ui-react/dist` é commitada | PR "invisível" em produção | F1 e F3 sequenciais, cada uma com rebuild da dist no diff |
| 8 | Webhook do Teams vazando em log ou API | Exposição de segredo | Reuso do mascaramento de `mensagens.py`; `/security-review` na F4 |
| 9 | Cadastro em lote gera um card de situação inicial por job no mesmo ciclo | Canal poluído logo na estreia | O card inicial é intencional e sai uma vez por vigência; a validação começa no canal de **homologação**, e só depois o job é apontado para o canal oficial |
| 10 | `max_linhas` baixo demais em job verboso não cobre o dia | Falso `NAO_EXECUTOU` | Configurável por job (default 200, teto 2000); o card de situação inicial expõe o problema logo na estreia do monitoramento |
| 11 | Job removido da supervisão levando junto o histórico de SLA | Perda da base que justifica a feature | Remoção lógica (`ativo=0`); exclusão física só em cadastro sem histórico |

## 7. Smoke pós-deploy

a) No Airflow, confirmar que `etl_ds_supervisao_monitor` aparece na lista e está
   despausada — se não aparecer, a etapa 5 do `deploy.sh` não foi confirmada.
b) Console DataStage → aba **Supervisão**: cadastrar um job real de janela
   conhecida, apontar para o **grupo de homologação** já existente, deixar a
   vigência em **hoje** e salvar. Recarregar e conferir que persistiu.
b1) Após o primeiro ciclo, conferir no canal de homologação o card de **situação
   inicial** daquele job, com o cenário do dia — é ele que valida se janela,
   dias e `max_linhas` foram configurados certo.
b2) Rodar mais dois ciclos e confirmar que o card inicial **não** se repete.
c) Tentar cadastrar o mesmo job de novo → mensagem de duplicidade, sem erro 500.
d) Entrar com usuário sem `tela_ds_console` → aba não disponível / 403 na escrita.
e) Disparar a DAG manualmente e conferir no log: quantos jobs lidos, quantos runs
   gravados, tempo total do ciclo.
f) `SELECT` em `etl_ds_supervisao_run` do job cadastrado: início e término batem
   com o que o Console DS mostra para o mesmo job.
g) Dashboard: o job aparece na área de supervisão com o estado do dia.
h) Trocar a data do Dashboard para o dia anterior → histórico daquele dia
   (ou estado vazio, se ainda não havia coleta).
i) Cadastrar propositalmente um job **inexistente** → após um ciclo, evento
   `ESTRUTURA` no painel e card no canal de homologação.
j) Conferir no canal do Teams: exatamente **um** card por ocorrência após três
   ciclos consecutivos.
k) `SELECT` em `etl_ds_supervisao_evento` → `notificado_em` preenchido só nos
   eventos efetivamente enviados.
l) Remover o job de teste e confirmar que ele sai do painel do dia corrente, que
   os dias anteriores continuam consultáveis e que nenhum evento órfão quebra a tela.
m) Cadastrar um job com vigência **amanhã** e confirmar que nada é avaliado nem
   notificado hoje.
n) Depois de validado em homologação, trocar o canal do job para o **grupo
   oficial** e confirmar que o próximo alerta chega lá.

## 8. Decisões fechadas (2026-07-29)

1. **Canal de homologação**: já existe um grupo em `etl_msg_grupo` dedicado a
   homologar ações novas. A spec **não cria** canal nenhum — o usuário aponta o
   job para o grupo de homologação, valida, e depois troca para o oficial.
   Nenhum seed de grupo entra na migration.
2. **Lista de jobs**: sem carga inicial. Tudo é cadastrado pela tela e é
   dinâmico — job priorizado hoje pode sair amanhã. Por isso a remoção é lógica
   e o histórico sobrevive ao descadastro.
3. **`-max` do logsum**: configurável **por job** (`max_linhas`, default 200,
   teto 2000), não parâmetro global da DAG.
4. **Vigência em vez de ativo/inativo na estreia**: o usuário define a data em
   que o monitoramento passa a valer. Com vigência em hoje, o primeiro ciclo já
   busca a execução do dia e envia o **card de situação inicial**, para ele
   validar a configuração de imediato.
5. **Subida da versão**: o usuário decide quando cada fase vai a produção — o
   deploy não é acionado por mim, como já é a regra em todo o projeto.

Nenhuma pendência aberta bloqueando a F1.
