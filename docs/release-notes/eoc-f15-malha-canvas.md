# EOC-F15 — Canvas e diagnóstico da Malha

O localizador pesquisa nome, tipo ou identificador dos nós presentes na visão exibida. A lista oferece seleção por teclado e centraliza o alvo; propriedades mostram identidade e diagnóstico de execução disponível. Localizar não grava posições nem dependências. A seleção resiste às atualizações de status da corrida.

Montagem e painéis Agora/Travando/Eventos passam a ocupar a largura disponível em telas pequenas, com rolagem para alcançar o canvas. O realce ocupa uma faixa acima do canvas no celular e fica abaixo da barra de ações nas larguras maiores. Autoria, membros, componentes, ações, permissões e causas fornecidas pelo motor permanecem nos caminhos existentes.

Deploy DEV: backup SQL COPY_ONLY/CHECKSUM e VERIFYONLY; migration 194 idempotente de versão (2.34.0 sobre DEV2.33.0), dist atualizada. Sem alteração de auth, API, service, DAG ou dependência. Não executar pipeline para validar esta entrega. Produção exige autorização própria.

QA reproduzível da interface compilada, com APIs inteiramente sintéticas e sem backend: `python3 scripts/qa/eoc_f15_canvas.py --output /tmp/eoc-f15-qa`. Requer Playwright/Chromium no ambiente de QA, não no runtime. Cobre ambos os temas, três larguras, nome longo, busca vazia, seleção por teclado, polling, ausência de writes e realce mobile acima do canvas com sentidos/isolar.

Gates humanos e externos existentes continuam no Backlog; esta fase não certifica DataStage/Caixa nem substitui o piloto humano. O canvas histórico preexistente não ganhou contrato novo de snapshots.
