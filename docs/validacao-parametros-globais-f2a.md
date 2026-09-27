# Validação F2a — 27/09/2026

Base: origin/main 8cf356b (PR #455 mergeada). Worktree isolada
/root/orquestra-parametros-f2, branch feat/parametros-globais-f2.

## Resultados

- Baseline pytest: 6861 aprovados, 79 saltados, 8 falhas.
- Feature pytest: 6915 aprovados, 51 saltados, mesmas 8 falhas.
- Foram adicionados 26 casos: 25 de importação/API e uma bancada de contrato frontend.
  Outros 28 testes que saltaram na referência executaram na feature.
- Falhas compartilhadas: test_api_v2_4 (4), test_kanban_rodape_card (3), test_smoke (1).
- Checagem dirigida final após correção responsiva: 45 testes aprovados.
- TypeScript por tsc -b e build Vite aprovados.
- ESLint por arquivo/regra/primeira linha/severidade: zero achados novos
  (180 na referência, 178 na feature).
- Playwright com componentes reais e API interceptada: consulta, escolha de origem,
  substituição explícita, envio v2 e origem preservada; nenhum erro de JavaScript.
- Inspeção desktop/mobile em temas claro/escuro, incluindo 320px. Corrigida a grade
  do editor DS que comprimia o nome em telas estreitas. Detector Impeccable: [].
- Revisão adversarial independente: corrigidos truncamento de defaults multilinha
  e divergência na validação dos nomes de origem. Sem defeitos confirmados restantes.

## Evidências e limites

Logs e capturas locais em /root/orquestra-parametros-f2-evidencias.
Tests reproduzíveis: tests/test_pipeline_param_import.py,
tests/test_pipeline_catalogo_front.py e tests/js/pipeline_catalogo_harness.cjs.

Sem conexão a produção, sem deploy e sem gravar em banco do produto.
O serviço DataStage foi exercitado com canais SSH simulados (drenagem de stdout/stderr,
limites, timeout e erros sanitizados), não com execução real de dsjob.
Smoke com a versão DataStage instalada é pendente e está no roteiro de release.

A revisão e os testes desta entrega não certificam F2b nem Valida Arquivo.
