# Correção restore F9 — 2026-10-11

Branch fix/workspace-restore-dependencias, base df08be2 (F9/2.17.0). Bug real DEV: snapshot A omitia depends_on, tabela[] removida depois B mas CSV ativo retido; factory bloqueou e preservou gate. Adaptador deriva CSV somente se omitido, NULL para [] sem mutar snapshot. Migration163/2.17.1. Gates:7335PASS/8base/51skip, lint73/73/0novo, build/tsc-b/zeroNULnovo, QA e segurança sem bloqueios. UI/.NET/DAGs idênticos. Backup DEV verificado.

Neste commit: PR/merge/deploy/recuperação nativa e novo smoke pendentes. Não reescrever erro/gate/hash; recuperar draft original por nova revisão e publicação corretiva. Registro final/evidências devem comprovar restore e limpeza das fixtures. Ver docs/release-notes/2.17.1-workspace-restore-dependencias.md e docs/workspace-homologacao-f9.md. Sem autorização para main/produção; ensaios Caixa/DataStage/IA e INP de campo não certificados.
