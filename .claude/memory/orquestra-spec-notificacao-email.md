---
name: orquestra-spec-notificacao-email
description: "Spec do nó de e-mail do Orquestra (Admin › E-mail + nó `email` no pipeline, envio por sendmail via SSH no servidor do DataStage); aprovada 2026-09-10, F1 em PR"
metadata: 
  node_type: memory
  type: project
  originSessionId: 55c7dc0b-089c-4e39-9b3c-c60297f1190c
  modified: 2026-09-11T06:46:35.992Z
---

**Spec:** `docs/spec-notificacao-email.md` no repo Orquestra. **Status: APROVADA 2026-09-10 ("aprovado", decisões assumidas de §8 aceitas). 🔧 F1 = PR #388 ABERTA (`feat/email-f1`, commit `3b45aa1`), aguardando autorização de merge do usuário.** Origem: documento do usuário `2026-09-10-notificacao-email.md` (enviado pelos Utilitários do DEV para `/dados/bi` do container `orquestra-dev-sshd-amostra`), avaliado contra o código.

**Fatos validados em produção (pelo usuário, via DataStage):** relay `smtp.adcorp.intranet` sem autenticação, remetente `orquestra@caixavidaeprevidencia.com.br`, Postfix em `lnxprd021`, `mailx` no PATH, entrega confirmada no domínio interno. O worker do Airflow NÃO foi testado no relay → envio a partir do servidor do DataStage por SSH.

**Correções que a avaliação fez ao documento original:** o nó de notificação Teams JÁ tem tela em Etapas (`pages/Jobs.tsx`) e Fluxos (`PainelNotificacao.tsx`) — só a leitura em runtime falta (o factory embute `grupo_id`/`template_id`/`mensagem` como literais); `etl_app_config` já existe; o nó roda no worker com `SSHHook` (paramiko da API é só do console); a malha tem nós próprios (`malha_nos.py`) — fora da spec; segurança: nada digitado pelo usuário na linha de comando (`sendmail -t -i -f <remetente>` + MIME via stdin), anexo com raízes permitidas.

**Decisão do usuário (2026-09-10):** anexo = diretório entre as raízes parametrizadas + **nome livre** (o arquivo ainda vai ser gerado na corrida): validar existência só na hora; ausente → envia sem anexo com aviso, nunca falha por isso. Placeholders no nome (`relatorio_{odate}.xlsx`).

**Assumidos a confirmar na aprovação (§8):** `sendmail -t -i` + MIME (não `mailx`); nó no padrão do nó de notificação; toda falha de envio falha a task; aba só `acao_admin`; domínios permitidos opcionais.

**F1 — PR #388 (2026-09-11):** migration 111 (5 chaves `email_*`, `etl_pipeline.email_destinatarios`, `etl_email_log`), `services/email_mime.py` ↔ espelho `dags/utils/email_envio.py` com teste anti-drift, `services/email_config.py`, `run_sendmail` em `services/ssh_datastage.py`, `routers/email.py` (status/config/testar/log), aba Admin › E-mail (`EmailTab.tsx` + `lib/emailAdmin.ts`) e bancada seção 9. Validação: 5135 pytest + as 8 falhas pré-existentes, `tsc -b` limpo, eslint 195=195 contra o baseline do HEAD, smoke DEV 12/12 com sendmail de mentira.

**Decisão da revisão adversarial da F1:** o comando virou `sendmail -t -i -f <remetente>`. Sem o `-f` o Postfix assume o usuário do SSH: bounce na caixa errada e relay que policia o MAIL FROM descarta **depois** do rc 0 (falso verde). O remetente é o único argumento de configuração na linha de comando — passa por `EMAIL_RE` e `shlex.quote`. Outros achados aplicados: JSON das listas limitado a 1000 (teto de `config_value`, senão o MERGE dá 500 opaco), `_sem_quebra` por `splitlines()`, `cabecalho_extra` sem cabeçalhos estruturais (um `Bcc` extra seria ENTREGUE pelo `-t`), raiz `/` recusada, banco fora do ar deixou de se disfarçar de "migration pendente".

**Why:** e-mail é o canal que a operação pede; o desenho evita gatilho implícito e segredo em tela, e reaproveita o canal já validado.

**How to apply:** não implementar antes do "aprovada"; ao aprovar, F1 = migration 111 + Admin › E-mail + envio de teste; F2 = nó no pipeline; F3 = notificação Teams em runtime; F4 = docs/smoke (homologação — DEV não tem Postfix nem relay). Relacionado: [[orquestra-spec-maestro-parametros]] (mesmo padrão de leitura em runtime).
