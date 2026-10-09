# Workspace: estrutura do fluxo próxima à referência — 2.12.0

Montagem com biblioteca agrupada, canvas central e propriedades fixas; validação/publicação imediatamente abaixo do canvas. Nós próprios horizontais com ícones e nomes, arestas ortogonais, ramificação/convergência e Organizar por dependências. Campos e condições avançados continuam disponíveis. ReactFlow é o motor de interação.

Operação preserva snapshot por corrida e dados reais. Investigação lateral prioriza etapa, estado, duração e logs; dependências ficam recolhidas. Histórico com posições incompletas usa desenho transitório inteiro, sem gravar ou alterar sua definição. Mobile empilha regiões e mantém navegação por pan/zoom. Nenhuma métrica ilustrativa de SLA/progresso foi criada.

Validação local: Python7201PASS, oito falhas preexistentes e51skip; delta final173PASS. TypeScript passou; lint sem assinaturas novas e delta final separado; build versionado. Navegador sintético16checks,28capturas1440/390 claro/escuro. Revisões independentes de código e segurança aprovadas; parecer visual e documentação em evidências. Migration148 idempotente registra2.12.0.

Entrega via develop/DEV; serviços e imagem backend F5 sem mudanças. Sem dependências novas; pacote offline F5 não é anunciado como pacote2.12.0. Promoção/produção e F6 seguem separadas. Evidências: /root/orquestra-referencia-evidencias. SHA, PR e smoke pós-deploy são registrados na memória de entrega; este arquivo não comprova deploy antes deles.
