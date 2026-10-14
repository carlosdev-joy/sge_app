# EOC-F15 — Malha canvas/localizador

Em desenvolvimento na worktree própria da fase, base DEV2.33.0 b74eb690. Fonte: docs/spec-experiencia-operacao-consolidada.md §F15.

Localizador recebe apenas nós da visão; lista por teclado e propriedades de identidade/execução sem writes. Seleção preservada no rebuild de status após achado e confirmação dirigida independente. Painéis responsivos; causas de bloqueio continuam no painel canônico.

Migration194 de versão 2.34.0; nenhum contrato de API/auth/motor alterado. Revisão independente de fonte APROVADO COM RESSALVAS: capturas/suíte/smoke reais ainda necessários. Evidências locais: /root/orquestra-eoc-evidencias/f15; QA reproduzível scripts/qa/eoc_f15_canvas.py com APIs sintéticas. Não confundir captura sintética com smoke de DEV. Gates humanos/externos anteriores mantidos; main/produção não autorizadas.

QA candidato2: tsc-b/build PASS (Vite8.27s), lint73assinaturas exatas baseline e detector vazio. Suíte final8598total/8539PASS/8FAILexatas/51SKIP;207.51s de parede,202.97s pytest. Revisão dirigida mobile aprovada após escopo/locator corrigidos; confirmação visual/publicação ainda gates. Realce em fluxo normal acima do canvas mobile; desktop mantém painel existente.

Candidato3 corrige achado material947px: realce abaixo barra de ações, que interceptava botão limpar. Confirmação dirigida independente estática aprovada; suíte final e Chromium candidato3 em andamento. Evidência da falha anterior preservada browser-confirm-corrected.log; não ocultar resultados incompletos anteriores.

Candidato5 resolve corte das ações inferiores do realce no canvas de execução intermediário: corpo desktop mínimo480px e rolagem do editor. Gates de geometria completos e cliques de sentido/isolar/limpar em todos os cenários; confirmação dirigida independente estática recebida, execução final pendente. Fonte/gates correntes sempre no estado/handoff, não usar passed dos candidatos anteriores como aceite final.

Candidato final5: tsc-b/buildPASS(Vite9.81s), lint73assinaturas exatas, detector vazio/NUL/authAPI/motorpreservados; suíte8598total8539PASS8FAILexatas51SKIP,206.56s parede/202.05s pytest. Chromium12casos/122.95sPASS, geometria completa e cliques reais; confirmação dirigida independente sem achados remanescentes. PR/deploy/smoke correntes registrados em /root/orquestra-eoc-loop/estado.json e relatório externo de entrega; gates humanos/externosBacklog192 mantidos.
