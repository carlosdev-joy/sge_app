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

## 2026-09-13 — F2 mergeada; F3 implementada

PR409 mergeada com autorização, main8e18e74. F3 em feat/orq-header-f3:
ChangelogModal usa marca/assinatura compartilhadas, diálogo e overlay existente
para Tab/Escape/foco. Perfil foca trigger estável antes de desmontar itemversão.
Consulta autenticada e cacheversão preservados. Documento: docs/branding/orq-header-f3.md.

Build OK, ESLint193 antes/depois, pytest5405/50skip/mesmas8falhas. SmokesF1/F2/F3
e login-altura aprovados; revisão adversarial aprovada. MergeF3/produção
pendentes; F1/F2 já mergeadas. Nenhuma fase funcional adicional nesta spec.

## 2026-09-13 — evolução Navy independente

F3 mergeada PR410, main39555e6. SpecNavy recebida após conclusão F1/F2/F3.
Branch feat/orq-header-navy muda somente fundoHeaderV2 para token--brand-navy.
Docs: branding/orq-header-navy.md e specrecebida. HistóricoF1/F2/F3 preservado.
Build/lint/pytest/smokesF1/F2/F3 e revisão aprovados. Navy fixo nos dois temas,
contraste versão10,30 e controles11,62. Contadorvermelho permanece3,76 (preexistente;
backlog separado, nenhuma perda causada pelo Navy). Merge/produção pendentes.

Complemento Navy solicitado pelo usuário: usar mesmo logo do login e fundoNavy
no dropdown dos dados do usuário. Brand variantewhite (orbitalcolorido+letras
brancas), Perfil fundo tokennavy. Incluído na PR411 aberta, sem novoPR/merge.
Build, lintdoscomponentes e smokeslayout/controles aprovados, revisãoadversarial
aprovada. Substitui restrição anterior de logoheader monocromático.
