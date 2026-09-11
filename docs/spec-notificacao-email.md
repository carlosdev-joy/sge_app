# Spec: Notificação por e-mail — nó `email` e configuração no Admin — Orquestra
Data: 2026-09-10 · Status: aprovada 2026-09-10 · em execução (F2; F1 mergeada na PR #388)

Origem: documento do usuário `2026-09-10-notificacao-email.md` (enviado pelos
Utilitários do DEV), avaliado contra o código em 2026-09-10. Esta spec mantém o
desenho aprovado ali — remetente único, nó explícito, nada automático,
destinatários lidos em runtime, envio pelo servidor do DataStage — e corrige as
premissas que o código desmentia (§8).

## 1. Visão
O canal de e-mail foi validado em produção pelo próprio servidor do DataStage
(`lnxprd021`, Postfix, relay `smtp.adcorp.intranet` sem autenticação, remetente
`orquestra@caixavidaeprevidencia.com.br`). O Orquestra passa a ter um **nó
`email`** que o usuário insere no fluxo e configura em tela (assunto, corpo,
destinatários, anexo), enviado a partir daquele servidor pela conexão SSH que o
operador DataStage já usa. Remetente, limite de anexo, raízes permitidas para
anexo e o interruptor ficam no **Admin › E-mail**. Nenhum e-mail sai sem o
usuário ter colocado o nó no fluxo.

## 2. Escopo
**IN:**
- Admin › Acessos & Comunicação › **E-mail**: remetente único, interruptor,
  limite de anexo (MB), raízes permitidas para anexos, domínios permitidos
  (opcional), botão **Testar** (envia ao próprio usuário).
- Módulo de envio no worker: mensagem MIME montada no Python (texto e HTML
  simples, anexo) e entregue ao `sendmail -t -i` do Postfix **via stdin da
  sessão SSH** — sem `mailx`, sem arquivo temporário nos dois lados.
- Nó `job_type = "email"` no pipeline (Etapas e Fluxos, no mesmo padrão do nó
  de notificação Teams): assunto, corpo, destinatários da etapa, "incluir
  destinatários do pipeline", anexo, ativo.
- Lista de destinatários do **pipeline** (wizard), herdada pelos nós `email`
  (união com a lista da etapa; a etapa pode não herdar).
- Placeholders no assunto, corpo e **nome do anexo**: os cinco que o nó de
  notificação já tem (`{pipeline} {job} {linhas} {status} {data}`) mais
  `{odate} {execution_id} {inicio} {duracao}`.
- **Leitura em runtime**: a DAG só carrega o `job_name`; assunto, corpo,
  destinatários e anexo são lidos do banco no disparo.
- Log de envios (`etl_email_log`), rastro no log da task e no detalhe da execução.
- Correção do nó de **notificação Teams** para o mesmo padrão (runtime read) —
  hoje o factory embute `grupo_id`/`template_id`/`mensagem` como literais.
- Manual, release note, smoke em homologação.

**OUT (explícito):**
- **Malha**: o canvas de malhas tem nós próprios (`dags/utils/malha_nos.py`,
  `components/malhas/`), separados dos tipos de job; um nó `email` da malha e
  a lista de destinatários da malha são spec seguinte.
- E-mail automático por falha, conclusão, SLA ou fim de corrida (F2–F4 do
  documento original) e relatório programado sem pipeline (F5): specs próprias.
- Remetente por nó; autenticação SMTP (o relay não exige); envio direto do
  worker pela rede (o relay foi validado só a partir de `lnxprd021`).
- Formulário novo para o nó de notificação: **já existe** em Etapas
  (`pages/Jobs.tsx`) e em Fluxos (`PainelNotificacao.tsx`) — só a leitura em
  runtime entra.
- Editor HTML rico: corpo em texto simples com HTML básico opcional.

## 3. Arquitetura proposta

**Envio (`dags/utils/email_envio.py`, novo, puro onde dá)**
- `montar_mensagem(remetente, destinatarios, assunto, corpo_texto, corpo_html=None,
  anexo=None) -> bytes`: `email.message.EmailMessage` da stdlib, `Content-Type`
  correto, anexo com nome e tipo pelo `mimetypes`. Nada de `mailx`: a variante
  instalada muda o significado de `-a`, e a mensagem MIME resolve HTML e anexo
  sem depender dela.
- `enviar(client, mensagem: bytes, remetente: str) -> dict`:
  `client.exec_command("/usr/sbin/sendmail -t -i -f <remetente>")` num
  `SSHClient` do paramiko já conectado (o do SSHHook no worker, o de
  `services/ssh_datastage` na API), escreve a mensagem no stdin, fecha, lê
  rc/stderr. **Nenhum campo digitado pelo usuário vai para a linha de
  comando**: o binário é fixo (env `EMAIL_SENDMAIL_BIN` do servidor) e o único
  argumento vindo de configuração é o remetente do Admin, que passa pela
  allowlist `EMAIL_RE` e ainda vai citado com `shlex.quote`. Destinatários,
  assunto e corpo vivem nos cabeçalhos MIME (quebras de linha recusadas na
  validação). O `-f` fixa o **envelope-from**: sem ele o Postfix assume o
  usuário do SSH, os bounces vão para a caixa errada e um relay que policia o
  MAIL FROM descarta a mensagem **depois** de o sendmail já ter devolvido 0.
- `validar_destinatarios(lista, dominios_permitidos) -> (validos, erros)`: regex de
  e-mail, sem duplicata, domínio na lista quando ela estiver configurada.
- `resolver_anexo(sftp, caminho, raizes, limite_mb, mapa) -> (bytes|None, aviso)`:
  resolve os placeholders no **nome**, confere de novo que o caminho resolvido
  está sob uma raiz permitida (o placeholder não pode inserir `..`), `stat` via
  SFTP (`hook.get_conn().open_sftp()`, como o `PythonScriptOperator` já faz),
  tamanho ≤ limite, lê os bytes. Ausente ou grande → `None` + aviso.
- Placeholders: `_notif_interpola` do factory ganha `{odate}`, `{execution_id}`,
  `{inicio}` e `{duracao}`; placeholder desconhecido fica intacto (regra do nó
  de notificação).

**Operador (`dags/utils/email_operator.py`, novo)**: `EmailOperator(BaseOperator)`
com `pipeline_name`, `job_name`, `ssh_conn_id`. No `execute`: lê `etl_app_config`
(interruptor, remetente, limite, raízes, domínios) e o nó (`etl_pipeline_job.notify_json`)
+ a lista do pipeline (`etl_pipeline.email_destinatarios`) pelo `MsSqlHook` — em
runtime, placeholders `%s`; canal desligado → `AirflowSkipException`; sem
destinatário → falha; monta, envia, grava `etl_email_log` e a linha
`[EMAIL] enviado para: … (anexo: …)` no log da task. Erro de SSH ou rc ≠ 0 do
`sendmail` → falha da task (decisão §8).

**Factory (`dags/etl_dag_factory.py`)**: bloco `_email_block` no molde do
`_notify_block` (sem lineage, `trigger_rule` tolerante quando alcançável de um
branch), emitindo só `job_name`/`PIPELINE_NAME`. `_notify_block` deixa de emitir
os literais: `_resolve_e_envia_notificacao(job, pipeline, up_jobs, exec_id, context)`
lê `notify_json` do banco como primeiro passo (o `notificacao_nodes` do factory
passa a servir só para saber que o nó existe).

**API**
- `routers/jobs.py`: `"email"` em `VALID_JOB_TYPES`; `_validate_email`/
  `_normalize_email` (assunto ≤ 500, corpo ≤ 20.000, destinatários válidos, anexo:
  diretório sob uma raiz permitida **e nome livre** — sem `/`, sem `..`, sem
  quebra de linha; placeholders permitidos no nome), gravado em `notify_json`
  como o nó de notificação; `GET .../fluxo` e `GET /pipelines/jobs/{p}/{j}`
  devolvem a config.
- `routers/pipelines.py`: `email_destinatarios` no register/GET (lista validada).
- `routers/email.py` (novo): `GET/POST /email/admin/config` (`get_admin_user`),
  `POST /email/admin/testar` (executa o mesmo `montar_mensagem` e um
  `sendmail -t -i -f <remetente>` via paramiko — helper novo em
  `services/ssh_datastage.py` que aceita stdin e nenhum argumento digitado pelo
  usuário), `GET /email/status` (`{enabled, limite_mb, raizes}`
  para a tela), `GET /email/log?pipeline=…` (últimos envios).
- `services/email_config.py`: leitura/gravação das chaves em `etl_app_config`
  (MERGE, como `caixa_ia_*`), com degradação sem as chaves.

**Front**
- `components/etapas/EmailNode.tsx` + `paineis/PainelEmail.tsx` (Fluxos) e a
  seção condicional em `pages/Jobs.tsx` (Etapas) — o mesmo par que o nó de
  notificação tem hoje: assunto, corpo (textarea com o *Variáveis disponíveis*
  do `PlaceholderPicker`), destinatários (chips, um por linha ou vírgula),
  "incluir destinatários do pipeline", anexo (raiz permitida num `Select` +
  nome livre; texto de ajuda "o arquivo pode ainda não existir — se não existir
  na hora, o e-mail sai sem anexo"), ativo. `types.ts`: `EmailType` em
  `TYPE_META`; ícone `Mail`.
- `components/pipelines/PipelineFormModal.tsx`: campo "Destinatários de e-mail
  do pipeline" no passo Notificações.
- Admin › **E-mail**: `components/admin/EmailTab.tsx` (remetente, interruptor,
  limite, raízes, domínios, *Testar* com o laudo na tela como o *Verificar* da IA).
- `components/execucao/ExecucaoDetailModal.tsx`: bloco **E-mails enviados**
  (de `etl_email_log`) na execução.

**Dados**: §4.

**Decisões e alternativas descartadas**
- *`sendmail -t` com MIME do Python* (escolhido) × *`mailx -a`*: portável entre
  variantes, HTML e anexo sem gambiarra, nenhum argumento do usuário no shell.
- *Nó no padrão do nó de notificação* (escolhido) × *tipo de etapa comum com
  `JobTypeFields`*: o e-mail é um nó de fluxo (sem comando, sem conexão de
  banco), e o padrão já existe nas duas telas.
- *Anexo: raiz permitida + nome livre validado só na hora* (decisão do usuário):
  o arquivo costuma nascer na corrida; validar existência no cadastro impediria
  o caso real. Ausente → sem anexo, com aviso; nunca falha por isso.
- *Envio a partir de `lnxprd021` por SSH* (documento original) × *SMTP do
  worker*: só o servidor do DataStage foi validado no relay; o worker não.
- *Toda falha de envio falha a task* (recomendação) × *só falta de destinatário
  e SSH*: e-mail que não sai em silêncio é o pior modo de falha; o retry da
  etapa cobre o transitório. Confirmar em §8.

## 4. Modelo de dados
Migration **`111_email.sql`** (idempotente; próximo número após a 110):

```sql
-- chaves em dbo.etl_app_config (MERGE por chave, sem tabela nova):
--   email_habilitado ('0'), email_remetente (''), email_limite_anexo_mb ('5'),
--   email_anexo_raizes ('[]' JSON), email_dominios_permitidos ('[]' JSON)
ALTER TABLE dbo.etl_pipeline ADD email_destinatarios NVARCHAR(MAX) NULL;   -- JSON ["a@x","b@x"]
CREATE TABLE dbo.etl_email_log (
  id            INT IDENTITY PRIMARY KEY,
  pipeline_name NVARCHAR(200) NOT NULL,
  job_name      NVARCHAR(200) NOT NULL,
  dag_run_id    NVARCHAR(250) NULL,               -- run_id do Airflow (como a 109)
  execution_id  NVARCHAR(100) NULL,               -- ts_nodash (como etl_job_execution)
  remetente     NVARCHAR(200) NOT NULL,
  destinatarios NVARCHAR(MAX) NOT NULL,           -- JSON
  assunto       NVARCHAR(500) NOT NULL,
  anexo_path    NVARCHAR(500) NULL,               -- caminho RESOLVIDO
  anexo_bytes   INT NULL,
  status        VARCHAR(20)   NOT NULL,           -- enviado | sem_anexo | falhou | pulado
  erro          NVARCHAR(1000) NULL,
  duracao_ms    INT NULL,
  criado_por    NVARCHAR(100) NULL,               -- matrícula (só no teste do Admin)
  criado_em     DATETIME2(0) NOT NULL DEFAULT GETDATE()
);
-- índice (pipeline_name, criado_em DESC) e (dag_run_id)
```
Nó (em `etl_pipeline_job.notify_json`, coluna da 049, como o nó de notificação):
```json
{"email_assunto": "Carga {pipeline} concluída - {data}",
 "email_corpo": "A carga {pipeline} foi concluída em {data}.\nLinhas: {linhas}",
 "email_html": false,
 "email_destinatarios": ["a@caixavidaeprevidencia.com.br"],
 "email_incluir_pipeline": true,
 "email_anexo_raiz": "/opt/IBM/dados/saida",
 "email_anexo_nome": "relatorio_{odate}.xlsx",
 "email_ativo": true}
```
Larguras: `assunto` medido em UTF-16 (`utf16_len`), `erro` cortado com
`cortar_utf16`; `destinatarios` JSON; `email_corpo` até 20.000 caracteres.

## 5. Fases

### F1 — Fundação: migration, configuração no Admin e o envio de teste
- Entregável: Admin › E-mail funcional, com *Testar* entregando um e-mail real.
- Inclui: `sql/migrations/111_email.sql`; `services/email_config.py`;
  `dags/utils/email_envio.py` (puro: `montar_mensagem`, `validar_destinatarios`,
  regras do anexo — sem SSH) e o espelho mínimo usado pela API (`services/email_mime.py`,
  com teste anti-drift, porque `api/` e `dags/` não se importam); helper de
  `sendmail` via paramiko com stdin em `services/ssh_datastage.py`;
  `routers/email.py` (`config`, `testar`, `status`, `log`); `components/admin/EmailTab.tsx`;
  testes: MIME (cabeçalhos, HTML, anexo, quebras de linha recusadas), régua de
  destinatários/domínios/anexo (raiz + nome), config MERGE, rotas admin (AST +
  403), `sendmail` chamado sem argumento do usuário; migration 2×.
- Critérios de aceite: dado o remetente e o interruptor ligado, quando o admin
  clica *Testar*, então o e-mail chega ao próprio endereço e o laudo na tela
  diz host, rc e duração; dado um assunto com quebra de linha, então 422 antes
  de qualquer SSH; sem a 111 a aba nomeia a migration.
- Validação: pytest vs baseline; tsc + eslint (baseline) + build; `dist/`.
- Revisão adversarial antes da PR. PR: `feat(email): fundação — migration 111,
  Admin › E-mail e envio de teste (F1)`.

### F2 — O nó `email` no pipeline (Etapas e Fluxos)
- Entregável: nó configurável nas duas telas, lista do pipeline no wizard,
  envio na corrida com anexo, log e rastro.
- Inclui: `VALID_JOB_TYPES` + `_validate_email`/`_normalize_email`; `email_destinatarios`
  do pipeline; `EmailOperator` + `_email_block` no factory (runtime read);
  placeholders novos em `_notif_interpola`; `EmailNode`/`PainelEmail`/seção em
  `Jobs.tsx`/`types.ts`; campo no wizard; bloco na execução; testes (factory
  emite só o nome, operador lê o banco, união de listas, skip quando desligado,
  anexo ausente → sem anexo com aviso, anexo fora da raiz resolvida → recusado,
  falha de `sendmail` → task falha, log gravado, régua do nó; bancada do front).
- Critérios de aceite: dado um nó `email` após a carga, quando a corrida chega
  nele, então o e-mail sai para a união das listas com o assunto interpolado e
  o anexo `relatorio_{odate}.xlsx` daquela data; dado o arquivo ausente, então o
  e-mail sai sem anexo, o log da task avisa e `etl_email_log.status = 'sem_anexo'`;
  dado o canal desligado, então a task fica `skipped`; mudar destinatários na
  tela vale na próxima corrida sem republicar.
- Validação: completa. Revisão adversarial. PR: `feat(email): nó email no
  pipeline com listas, anexo e log (F2)`.

### F3 — Nó de notificação Teams lendo em runtime
- Entregável: `grupo_id`/`template_id`/`mensagem` deixam de ser literais na DAG.
- Inclui: `_notify_block` e `_resolve_e_envia_notificacao` (leitura por
  `pipeline_name`/`job_name` com `%s`); teste do factory (a DAG gerada não
  contém os valores; o runtime lê); nota no manual: **regerar as DAGs** dos
  pipelines com nó de notificação uma vez (Admin › Publicar DAGs).
- Critérios de aceite: dada uma DAG regerada, quando o admin troca o template
  do nó na tela, então a próxima corrida usa o novo sem republicar.
- Revisão adversarial. PR: `refactor(notificacao): grupo/template/mensagem
  lidos em runtime (F3)`.

### F4 — Manual, release note e smoke
- Manual (§3.x nó de e-mail, §4.x Admin › E-mail, §4.6 deploy, FAQ), release
  note `docs/release-notes/email.md`, funcionalidades, spec concluída, smoke §7
  em homologação (o DEV não tem Postfix nem relay).
- PR: `docs(email): manual, release note e smoke (F4)`.

## 6. Riscos e mitigações
| # | Risco | Impacto | Mitigação |
|---|-------|---------|-----------|
| 1 | Injeção de shell por assunto, corpo, destinatário ou anexo | Comando arbitrário no servidor do DataStage | Nenhum campo digitado pelo usuário na linha de comando: `sendmail -t -i -f <remetente>` com binário fixo do ambiente, tudo em MIME via stdin; o remetente (única configuração no comando) passa por `EMAIL_RE` e `shlex.quote`; quebras de linha recusadas nos cabeçalhos; testes prendem o comando exato |
| 1b | Envelope-from errado (sem `-f`) | rc 0, mas o relay descarta ou manda o bounce para a conta do SSH — falso verde | `-f <remetente do Admin>` em ambos os espelhos; smoke confere o `Return-Path` no que chegou |
| 2 | Anexo lê arquivo indevido do servidor | Vazamento de arquivo do host | Diretório só entre as raízes do Admin; nome sem `/` e `..`; caminho **resolvido** conferido de novo contra as raízes; limite de MB checado no `stat` antes de baixar |
| 3 | `sendmail` aceita e o relay descarta (domínio externo, cota) | E-mail "enviado" que não chega | Domínios permitidos opcionais no Admin; *Testar* com laudo; log com rc/stderr; smoke com domínio externo para saber a política do relay |
| 4 | Worker sem acesso SSH/`lnxprd021` fora do ar | Nó falha | Falha alta e clara (é infraestrutura); retry da etapa; skip só quando o admin desliga |
| 5 | HTML mal formado / encoding | E-mail ilegível | `EmailMessage` com `text/plain` sempre e `text/html` como alternativa só quando marcado; UTF-8 |
| 6 | Regerar DAGs esquecido na F3 | Nó de notificação segue com literais (funciona igual) | Nota no manual e na release note; sem quebra |
| 7 | Deploy: migration 111 e `dags/utils/` novos | Worker sem os módulos | 6c → s; `dags/` + **restart do worker** (arquivos em `dags/utils/`); `config/` n |
| 8 | Spam interno por nó mal configurado num pipeline diário | Caixa lotada | O nó é explícito e por fluxo; `email_ativo` desliga sem apagar; interruptor global |

## 7. Smoke pós-deploy (homologação/produção)
a) Admin › E-mail: remetente, interruptor, limite 5 MB, uma raiz permitida; *Testar* → e-mail no próprio endereço; laudo com rc 0. No e-mail recebido, conferir o **Return-Path** (envelope-from, o `-f`): tem de ser o remetente do Admin, não o usuário do SSH.
b) Assunto com quebra de linha no nó → 422 no salvar; destinatário fora do domínio permitido → 422.
c) Pipeline de teste com nó `email` após uma etapa DataStage: assunto `Carga {pipeline} concluída - {data}`, corpo com `{linhas}`, anexo `raiz/relatorio_{odate}.xlsx` existente → e-mail com anexo; `etl_email_log.status = 'enviado'`; detalhe da execução mostra o envio.
d) Mesmo nó com o arquivo apagado → e-mail sem anexo, aviso no log, `sem_anexo`.
e) Lista do pipeline + lista da etapa → destinatários = união sem duplicata; "incluir destinatários do pipeline" desmarcado → só a etapa.
f) Interruptor desligado → task `skipped`; sem destinatário em lugar nenhum → task falha com mensagem clara.
g) Corpo HTML marcado → renderiza no Outlook; desmarcado → texto simples.
h) Destinatário de domínio externo (se permitido) → chega ou o relay recusa? (define a política).
i) F3: regerar as DAGs com nó de notificação; trocar o template na tela → próxima corrida usa o novo.

## 8. Pendências e decisões em aberto (confirmar na aprovação)
- **Decisão do usuário (2026-09-10):** anexo com diretório entre as raízes
  parametrizadas e **nome livre**, validado só na hora do envio (o arquivo
  ainda vai ser gerado) — incorporado em §3/§4/§5.
- **Desvios de implementação da F2 (2026-09-11), decididos pelo precedente do
  código:**
  1. O nó vive **só no canvas** (Etapas › Fluxo), não na tela Lista. A §3 previa
     "seção condicional em `pages/Jobs.tsx`", mas os dois nós especiais mais
     recentes — `sql` (051) e `aguarde` (068) — também **não** estão lá: a lista
     `JOB_TYPES` daquela tela nunca os ganhou. Seguir a spec ao pé da letra
     criaria um terceiro formulário completo (destinatários, anexo, assunto,
     corpo) num lugar onde ninguém monta nó de fluxo. O que entrou em
     `pages/Jobs.tsx` foi a **cor do rótulo** do tipo, que faltava para `email`
     e também para `sql`, `aguarde`, `decisao` e `notificacao` — todos caíam no
     cinza genérico ao serem listados.
  2. A DAG `dags/etl_pipeline_job_register.py` tem uma **segunda** lista
     `VALID_JOB_TYPES`, defasada desde antes desta spec (só datastage, shell,
     python, storedproc — sem http, decisao, notificacao, sql, aguarde). Ela
     **não** foi tocada: além do tipo, aquele caminho exige origem/destino de
     lineage, que nó especial nenhum tem — consertá-la é replicar o
     `sem_lineage` da API num caminho que a F2 não usa. Fio solto registrado.
- **Achados da revisão adversarial da F2 (2026-09-11), todos corrigidos:**
  1. **Decisão com nó especial no ramo gerava `task_id` inexistente.** O
     `_decision_block` só conhecia as notificações: qualquer outro membro do
     ramo virava `log_start_<nome>`, task que nó sem `t_start` não tem, e o
     `BranchPythonOperator` levantava "'branch_task_ids' must contain only
     valid task_ids" — a DECISÃO falhava e derrubava o pipeline. Valia também
     para `sql` e `aguarde` (defeito pré-existente), corrigido para os quatro.
     Âncora: `test_ancora_decisao_roteia_nos_especiais_pelo_proprio_task_id`.
  2. **`{linhas}` saía sempre vazio.** O factory liga o e-mail ao `t_end_*`,
     cujo `task_id` é `log_end_<job>`, e o `rows_out` está no XCom de `<job>`.
     O operador passou a tirar o prefixo e a cair para `etl_ds_job_log`, como o
     nó Teams já fazia.
  3. **`{odate}` usava `ds_nodash`**, que é o INÍCIO do intervalo — em pipeline
     diário, o dia anterior. Passou a ler a data de referência da corrida
     (`etl_pipeline_execucao`, a mesma fonte do `-param` do DataStage), com o
     fim do intervalo como reserva.
  4. **O 503 "aplique a migration 111" era engolido** por um `except
     Exception: pass` — e, pior, abortava a gravação dos campos da 017 em TODO
     save, porque a tela manda a chave sempre. A gravação saiu de dentro
     daquele `try`.
  5. **A lista do FLUXO não passava pela allowlist de domínios**: entrava no
     cadastro e fazia a task falhar em toda corrida, já que os nós a herdam por
     padrão.
  6. **`{status}` era a string fixa "concluído"** — com um Aguarde de política
     "todas_terminarem", o e-mail afirmaria sucesso depois de uma etapa que
     falhou. Passou a ler o estado agregado do banco, como o card de fim.
  Menores, também corrigidos: auditoria da lista do fluxo; falha de SSH ao
  BUSCAR o anexo passou a gravar o log antes de falhar; nome de anexo vazio
  deixou de sumir em silêncio; lista de pastas vazia por falha de rede não
  trava mais o save; duração negativa; `anexo_path` truncado para a coluna.
  O bloco **E-mails enviados** na tela de execução (§3 Front), que faltava,
  entrou.
- **Decisão da revisão adversarial da F1 (2026-09-11):** o comando ganhou
  `-f <remetente>` (envelope-from). Sem ele o Postfix assume o usuário do SSH
  e a falha aparece só depois do rc 0 (bounce na caixa errada, ou descarte por
  política do relay). O remetente é o único argumento vindo de configuração:
  allowlist `EMAIL_RE` + `shlex.quote`.
- **Assumido, confirmar:** `sendmail -t -i` com MIME do Python em vez de `mailx`;
  nó no padrão do nó de notificação (Etapas + Fluxos), não um tipo de etapa
  com comando; malha fora desta spec; **toda** falha de envio falha a task
  (não só SSH/sem destinatário); aba do Admin só para `acao_admin`, sem
  mascarar remetente; domínios permitidos como lista opcional.
- Nome/rótulo do nó na tela: "E-mail" (ícone `Mail`).
- Placeholders `{inicio}` e `{duracao}`: início da corrida pelo `dag_run.start_date`
  no fuso America/Sao_Paulo — confirmar o fuso desejado.
- Números de migration (111) confirmados na abertura da F1.
