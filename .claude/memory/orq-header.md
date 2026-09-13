---
name: Header ORQ — especificação final
description: Fases da consolidação do header após PR407
type: project
---

## 2026-09-13 — F1 implementada

Fonte: docs/spec-orq-header.md e docs/branding/orq-header-notion-spec.md.
Baseline exigido e usado: e09fc76 (PR407). Branch feat/orq-header-f1.

F1: Brand usa Link SPA com nome acessível e divisor CAIXA | ORQ; CAIXA somente
md+, versão sm+, título lg+, busca xl+, nome do perfil md+. Gradiente com tokens
cvp existentes, corpo52/filete4 preservados. Login/Logo/Nav/RBAC intocados.

Why: header anterior recarregava o documento ao clicar na marca e disputava
espaço em telas estreitas. How to apply: manter breakpoints e fonte NAV; não
reabrir escopo do login nem trocar versão autenticada pela versão pública.

F2 pendente após merge autorizado F1: ARIA/tipos, alvos dos controles,
Escape/foco, feed acionável e perfil ORQ. F3 pendente: changelog e regressão
integrada. Um PR por fase conforme CLAUDE.md. Nenhum merge desta fase autorizado.
Deploy: frontend dist apenas; produção pendente, sem migrations/dependências.

Validação F1: tsc/Vite OK, ESLint193 antes/depois, pytest5405/50skip/mesmas8falhas,
smoke20 combinações claro/escuro OK, revisão adversarial aprovada após corrigir
mock de /utilitarios/config (precisa raizes e servidores). Capturas em
/tmp/orq-header-f1-{light,dark}-{1440,768,360,320}.png no ambiente de execução.

## 2026-09-13 — F1 mergeada; F2 implementada

PR408 mergeada com autorização, main085122b. F2 em feat/orq-header-f2:
triggers40/36px, ARIA/dialog não modal, Escape com retorno de foco, feed com
botões nativos e foco preservado após confirmação/read-all, popoversmobile,
perfil ORQ. Contratos de leitura/confirmação/polling/logout intactos.

Spec/evidência: docs/branding/orq-header-f2.md. Revisões adversarial e segurança
aprovadas. Build OK, ESLint193 antes/depois; pytest5405/50skip/mesmas8falhas.
F3 changelog segue pendente após autorização de merge F2. Sem novo asset,
backend, dependência, migration ou mudança no login/RBAC. Produção pendente.
