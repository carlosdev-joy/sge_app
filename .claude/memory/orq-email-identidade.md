---
name: Identidade ORQ nos e-mails
description: Modelo institucional Navy e logo CID no nó de e-mail
type: project
---

2026-09-13 — branch `feat/email-identidade-orq`, base main `0bedbe0`.
Pedido: reestruturar e-mails do nó conforme o novo header e logo do login.
Implementação em `docs/spec-email-identidade-orq.md`; HTML em
`docs/branding/orq-email-modelo.html`.

Migration 114 atualiza apenas o corpo original da 113 (guarda SHA256), preserva
modelos personalizados e todas as configurações. DEV tinha apenas id 1,
Aviso de fim de carga, exatamente original. Logo PNG 360×144 exportado do login,
incorporado via CID fixo na API/worker e resolvido localmente na prévia sandbox.
Nenhum envio real realizado ou autorizado. Sem novas dependências.

Validação: testes MIME/preview, suíte completa comparada às oito falhas existentes,
TypeScript/build, ESLint sem novos achados. Prévia Chromium 800/360 px sem overflow;
EML offline. Revisões adversarial e segurança aprovadas; corrigida diferença de
maiúsculas no esquema CID. Outlook desktop ainda exige validação no cliente real.

Deploy: atualizar API + assets, dags/utils + assets, dist; reiniciar worker/scheduler
antes de aplicar 114. Conferir estado pós-deploy e registrar PR abaixo.
Merge desta PR depende de autorização específica do usuário.

DEV atualizado em 2026-09-13: API reconstruída/recriada, worker/scheduler reiniciados,
nginx recarregado. Migration 114 validada com rollback e idempotência e aplicada
apenas ao id 1; novo SHA256 UTF16LE 9e5d3db5d8fc847879b1d10a7aa6df4cd0559975108dff9419cc702d0fee5739.
HTTP login, health e logo 200; bytes do logo publicado conferidos. API MIME OK.
Suíte final: 5421 aprovados, 8 falhas preexistentes, 50 ignorados.
