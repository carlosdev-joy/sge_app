---
name: orquestra-eoc-f10-adapters
description: "EOC-F10: adapters internos E-mail/Teams e replay dry-run auditado"
type: project
---

Candidato F10 baseado em DEV ed62aef3/2.28.0. Contrato em docs/eoc-f10-adapters.md;
release notes2.29.0, migrations182/183. Codex executor único; ClaudeOFF.
QA independente encontrou exit_code SSH -1 tratado Failed; regressão reproduzida,
corrigida Unknown e confirmação dirigida APROVADA. Gates de transporte
real e integração interna/cutover registrados no Backlog pela migration182; autoridadeF9 permanece.
Why: entregar adapters sem inferir autoridade, ativar clientes ou duplicar legados.
How to apply: não conectar dispatcher nem liberar capabilities por esta fase;
confira SHA/PR/DEV e evidências no handoff antes de alegar entrega publicada.

Revisão principal corrigiu vazamento de assinatura via log INFO HTTPX e
rejeição do host atual Workflows. HTTPSConnection com TLS/hostname, debug0,
query opaca, sem redirect/proxy e sem alterar outros loggers. Revisão dirigida
independente aprovada; 49 testes dirigidos passaram. Envio real não realizado.
