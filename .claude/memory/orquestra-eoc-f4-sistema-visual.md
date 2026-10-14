---
name: EOC-F4 sistema visual comum
description: Base de componentes, densidade local, temas e evidências do candidato2.23.0
type: project
---

SPEC consolidada EOC-F4, referências design-global41ac369, base developa322eb7c. Codex implementa diretamente; Claude permanece parado por decisão do usuário. Fonte Inter local/OFL, controles/tokens/densidade de apresentação no perfil, amostra Vite sem rota/API. Contrato e limites em docs/eoc-f4-sistema-visual.md; deploy em docs/release-notes/2.23.0-sistema-visual-comum.md. F5 expande shell/Pipeline; F21 gerencia preferências por contexto.

Why: padronizar controles e preservar operações/canvas. Não introduzir nova stack, remover funcionalidades ou tratar leitura de comunicação como resolução do resultado do job.

How to apply: uma revisão independente; correções em lote; dois conjuntos de inspeção visual. `color-scheme` deve herdar de html; foco branco do header precisa reset em overlays de panel. Icon buttons têm minwidth e minheight por toque. O Chromium pode adicionar tab-stop a containers roláveis e normalizar pointer após fullPage screenshot: medir interação/retângulos antes da captura e não presumir que próximo Tab é sempre botão. Bench loading mede aria-busy em vez do glifo antigo. `relative` dos invólucros sr-only preservado.

Candidato: suíte7914PASS/mesmas8falhas/51SKIP; lint176semnovas; build/TypeScript e202dirigidos;20casos amostra; nativo DEV próprio conserva canvas630×584 e3nós sem criar run. Roteiro versiona174/2.23.0. Estado vivo de PR/merge/DEV e SHA deve ser confirmado no GitHub/registro compartilhado/evidência pós-deploy; esta nota não prova deploy antecipado.
