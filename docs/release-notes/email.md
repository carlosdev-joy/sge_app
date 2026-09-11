# ✉️ Notificação por e-mail — nó `email`, Admin › E-mail e card do Teams em runtime

**Compatibilidade:** Apache Airflow 2.x | SQL Server | servidor de e-mail do próprio DataStage (`lnxprd021`, Postfix → relay interno) — nenhuma conta de e-mail nova
**Migrations:** **111** (`111_email.sql`, F1) — deploy.sh etapa 6c, responder **s**
**Spec:** `docs/spec-notificacao-email.md` (F1 = #388 · F2 = #389 · F3 = #390 · F4 = esta PR)
**Manual:** `docs/MANUAL_USUARIO.md` §3.5-A (nó de e-mail), §3.5-B (card do Teams em runtime), §4.10 (Admin: canal, remetente, pastas, teste), §4.6 (deploy) e §5 (FAQ)
**Depende de:** a conexão SSH do console DataStage já configurada (`DS_SSH_*` no `.env` da API e a conexão do worker)

---

## 📋 Resumo

O Orquestra passa a **avisar por e-mail** quando um fluxo termina. Não há
servidor de e-mail novo: a mensagem é montada no Orquestra e entregue ao
servidor que o DataStage já usa, pela mesma conexão do console.

Quem monta o fluxo arrasta o nó **E-mail** da paleta, liga depois da carga e
escreve assunto e corpo. Quem administra decide, em Admin › E-mail, se o canal
está ligado, qual é o remetente, quanto pode pesar um anexo e **de quais pastas**
ele pode sair.

Nada sai sozinho: sem o nó no desenho, nenhum e-mail é enviado.

> **A decisão que atravessa as três fases:** a DAG gerada **não guarda** a
> configuração. Assunto, corpo, destinatários e anexo são lidos do banco no
> disparo. Mudar quem recebe vale na próxima corrida, sem republicar. O card do
> Teams, que fazia o contrário desde sempre, passou a funcionar do mesmo jeito.

## 🔍 Como funciona

1. **Admin › E-mail** guarda o canal em `etl_app_config` (chaves `email_*`).
   Desligado, os nós ficam salvos e a corrida **pula** o envio.
2. O nó `email` do desenho guarda a configuração em `etl_pipeline_job.notify_json`
   — a mesma coluna do nó de notificação Teams; o tipo do job distingue os dois.
3. Na corrida, o `EmailOperator` (`dags/utils/email_operator.py`) lê o canal, o
   nó e a lista do fluxo, resolve os marcadores, busca o anexo por SFTP, monta a
   mensagem e a entrega ao `sendmail -t -i -f <remetente>` pelo stdin da sessão
   SSH. Cada envio vira uma linha em `etl_email_log`, visível no detalhe da
   execução.
4. **Duas listas se somam**: a do nó e a do fluxo
   (`etl_pipeline.email_destinatarios`, cadastrada no wizard). Endereço repetido
   chega uma vez só.

> **Segurança do desenho.** Nada digitado pelo usuário chega a uma linha de
> comando: assunto, corpo e destinatários vivem nos cabeçalhos da mensagem, que
> entra pelo stdin. O único argumento de linha de comando vindo de configuração
> é o remetente, validado por lista de formato e citado. Quebra de linha é
> recusada onde viraria cabeçalho novo. O anexo só sai de uma pasta liberada, e
> o caminho é reconferido **depois** de resolver os marcadores do nome.

## 🚀 Deploy

1. `git pull` na `main`.
2. **Migration 111** na etapa 6c do `deploy.sh` → responder **s**.
   Cria as 5 chaves `email_*`, a coluna `etl_pipeline.email_destinatarios` e a
   tabela `etl_email_log`. É idempotente: rodar duas vezes não quebra nada.
3. `api/` → **sim**. `dist/` → **sim**. `config/` → **n**.
4. `dags/` → **sim**, e **reiniciar o worker do Airflow**. São dois arquivos
   novos em `dags/utils/`, que o worker mantém em cache: sem o restart, a etapa
   de e-mail falha dizendo que não encontra o operador.
5. Opcional no `.env` do host: `EMAIL_SENDMAIL_BIN` (padrão `/usr/sbin/sendmail`;
   em alguns servidores o Postfix instala como `/usr/sbin/sendmail.postfix`). O
   compose a repassa para **os dois** containers que precisam dela — a API (botão
   *Testar*) e o **worker** (as corridas). Se mudar o valor, confira com
   `docker compose exec orquestra-api env | grep EMAIL` e o mesmo no
   `airflow-worker`: com ela só na API, o teste fica verde e **toda corrida
   falha**.
6. **Republicar uma vez** os pipelines que já tinham nó de **notificação Teams**
   (Admin › Publicar DAGs). Até lá eles seguem mandando o texto gravado na
   geração anterior — sem erro, só desatualizado.
7. **Republicar também os pipelines que já tenham nó de e-mail**, se algum foi
   publicado antes desta versão. A correção que impede o canal desligado de
   arrastar o resto do fluxo (ver abaixo) está na fiação da DAG, então só vale
   depois de regerar.

## ✅ Conferência pós-deploy

Na ordem; cada item de pé por conta própria.

**a) Canal e teste.** Admin › Acessos & Comunicação › **E-mail** abre sem falar
em migration. Preencha o remetente, ligue o canal, cadastre ao menos uma raiz permitida para
anexos e **salve** — o botão *Testar* só habilita sem alteração pendente. Então
clique **Testar**: o laudo tem de dizer *Enviado ao sendmail*.

**b) O e-mail chegou.** Confira a caixa. **No e-mail recebido, olhe o
`Return-Path`** (nos detalhes da mensagem): ele tem de ser o remetente
configurado, não o usuário técnico da conexão. É isso que separa "entregue" de
"aceito e descartado depois" — sem ele, devolução de mensagem vai para a caixa
errada e um relay que confere o remetente do envelope pode recusar em silêncio.

**c) Um fluxo de verdade.** Num pipeline de teste, arraste o nó **E-mail**
depois de uma etapa, escreva `Carga {pipeline} — {status}` no assunto e
`{linhas} linhas em {duracao}` no corpo, salve e **publique**. Rode. O e-mail
tem de chegar com os marcadores resolvidos, e o bloco *E-mails enviados* tem de
aparecer no detalhe da execução.

**d) Anexo do dia.** No mesmo nó, marque *Anexar*, escolha a pasta e use
`relatorio_{odate}.xlsx` (ou o nome que a corrida gera). Rode com o arquivo
presente: ele chega junto. Apague o arquivo e rode de novo: **o e-mail sai
assim mesmo, sem anexo**, e o registro do envio diz onde procurou.

**e) A promessa central.** Com a DAG já publicada, mude o destinatário ou o
texto na tela e rode de novo **sem republicar**. A corrida tem de usar o valor
novo. Se não usar, a DAG é anterior a esta versão: republique uma vez.

**f) Lista do fluxo.** Cadastre um endereço em *Destinatários de e-mail do
fluxo* e confirme que ele recebe junto com a lista do nó, sem duplicar quem
está nas duas.

**g) Interruptor.** Desligue o canal no Admin e rode: a etapa de e-mail tem de
ficar **pulada**, não vermelha, e **o resto do fluxo tem de seguir** — a
publicação da corrida e os pipelines que dependem dela não podem ser arrastados
pelo pulo. Religue depois.

**h) Card do Teams.** Num pipeline com nó de notificação **já republicado**,
troque o texto do card na tela e rode sem republicar: o card tem de chegar com
o texto novo.

**i) Canal do Teams ausente.** Desative o grupo do nó em Admin › Acessos & Comunicação › Notificações e
rode. O card **não** pode chegar no canal padrão do sistema: ele não é enviado,
a corrida segue, e o log da etapa traz `[NOTIF] card NAO enviado` com o motivo.

## ⚠️ O que muda para quem já usava

- **Card do Teams em canal apagado ou desativado deixa de ser enviado.** Antes
  ia para o endereço padrão do sistema, com a etapa verde: chegava no canal
  errado e quem devia receber não recebia. Agora o log diz qual canal falta.
- **Texto do card só passa a ser dinâmico depois de republicar uma vez.**
- **Canal de e-mail desligado não arrasta mais o fluxo.** Antes, o pulo da
  etapa de e-mail descia por tudo que vinha depois dela, inclusive pela tarefa
  que registra o sucesso da corrida: os pipelines dependentes não disparavam, e
  todas as tarefas ficavam verdes ou puladas. Vale depois de regerar a DAG.
- **O comportamento** de pipeline sem nó de e-mail e sem nó de notificação não
  muda. O *arquivo* da DAG muda: o trecho que lê a configuração do card é
  escrito em toda DAG, mesmo onde nunca será chamado. O teste-âncora do repo
  compara byte a byte depois de descontar exatamente esse trecho, que a fase
  declarou.

## 🧯 Se algo der errado

| Sintoma | Onde olhar |
|---|---|
| A aba diz "migration 111 pendente" | A etapa 6c não rodou, ou rodou em outro banco |
| *Não chegou ao servidor do DataStage* no teste | Mesma conexão do console DataStage: confira `DS_SSH_*` no `.env` da API |
| A etapa falha com "não encontra o operador" | O worker não foi reiniciado depois do deploy de `dags/` |
| E-mail sai sem anexo sempre | Pasta não liberada em Admin, arquivo ausente na hora, ou nome com marcador que não resolve — o registro do envio diz qual dos três |
| *O sendmail recusou* | O erro do servidor vem no laudo; daí para a frente é com quem cuida do relay |
| Teste verde e **toda corrida** falhando no envio | `EMAIL_SENDMAIL_BIN` chegou à API mas não ao worker — confira o `env` dos dois containers |

## 📦 O que entrou

| Fase | PR | Entrega |
|---|---|---|
| F1 | #388 | Migration 111, Admin › E-mail, envio de teste com laudo, registro de envios |
| F2 | #389 | Nó `email` no desenho, operador no worker, lista do fluxo, anexo, bloco na execução |
| F3 | #390 | Card do Teams lendo canal, modelo e mensagem no disparo |
| F4 | esta | Manual (§3.5-A, §3.5-B, §4.10, §4.6, FAQ), esta release note, spec concluída |
