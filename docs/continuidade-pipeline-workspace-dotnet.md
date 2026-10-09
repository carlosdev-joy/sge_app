# Continuidade do workspace de Pipeline no DEV
Data: 2026-10-09

## Resultado pretendido
Criar a nova experiência de Pipeline e depois Malha, conforme mockups da conversa. Consolidar Etapas e Fluxos no Pipeline. Manter frontend React, migrar a gestão para .NET e preservar Airflow, DataStage, SQL e jobs Python/PySpark.

## Artefatos preparados
- docs/spec-pipeline-workspace-dotnet.md: especificação em rascunho para revisão.
- Branch documental docs/pipeline-workspace-dotnet, criada de develop 6e711e54e5883fb6d66edf13dfc1fe229df19c45.
- Quatro mockups ilustrativos: workspace em execução, montagem, malha com edição bloqueada e criação.
- Nenhum código de produto, migration, runtime ou configuração de servidor foi alterado nesta sessão.

## Onde continuar
O repositório documenta /opt/orquestra-dev como checkout do DEV. Confirmar host, caminho, branch, mudanças locais, serviços e acesso antes de usar. A memória do servidor é histórica, não prova seu estado atual.
A UI e API usam bind mounts: um build ou restart no checkout servido pode alterar o DEV. Desenvolver em checkout isolado e publicar somente candidatos identificados por SHA.

## Leitura inicial
1. CLAUDE.md e docs/fluxo-desenvolvimento.md.
2. docs/spec-pipeline-workspace-dotnet.md.
3. .claude/skills/gerador-spec/SKILL.md.
4. .claude/memory/vps-ambiente-dev-orquestra.md e docs/ambiente-dev.md.
5. Instruções locais AGENTS.md, se presentes no servidor.

## Estado e limites
O usuário aprovou a direção geral e pediu início. A especificação escrita ainda precisa de revisão explícita antes do plano detalhado e da implementação, conforme o processo do projeto.
A próxima etapa é revisar esta spec, conferir os contratos reais e preparar o plano de F1. Não apresentar a documentação como implementação concluída.
Não promover main nem implantar produção. Fases são PRs para develop, com revisão adversarial e validação no DEV.
Não reproduzir credenciais de memórias/documentos, não imprimir .env e não incluir segredos nos prompts.

## Inspeção inicial do servidor
- Conferir alterações locais, HEAD, remoto, origin/develop e diferenças.
- Conferir SDK/runtime .NET, Node e Docker, sem instalar nada automaticamente.
- Conferir recursos disponíveis e serviços do DEV sem alterar serviços compartilhados.
- Capturar baseline de build/lint/testes antes de alterar o produto.
- Preservar bancos/volumes; não executar bootstrap destrutivo nem compose up global.
- Escolher pipeline de teste e registrar limitações dos simuladores DataStage.

## Prompt para iniciar a próxima sessão
Estamos iniciando a evolução do ORQUESTRA conforme docs/spec-pipeline-workspace-dotnet.md. Leia CLAUDE.md e docs/fluxo-desenvolvimento.md, confira o estado do checkout e revise a especificação antes de implementar. A direção aprovada é manter React, criar o espaço de trabalho de Pipeline, incorporar os menus Etapas/Fluxos, migrar gestão para .NET e manter Airflow e jobs Python/PySpark. Trabalhe por fases em branches de origin/develop, com testes, revisão adversarial e validação DEV. Preserve dados e serviços compartilhados, não faça deploy de produção e não exponha segredos. A spec ainda está em rascunho: apresente divergências e solicite sua aprovação antes do plano de implementação.
