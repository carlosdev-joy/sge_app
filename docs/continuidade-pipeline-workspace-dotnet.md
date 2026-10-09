# Continuidade do workspace de Pipeline no DEV
Data: 2026-10-09

## Resultado pretendido
Criar a nova experiência de Pipeline e depois Malha, conforme mockups da conversa. Consolidar Etapas e Fluxos no Pipeline. Manter frontend React, migrar a gestão para .NET e preservar Airflow, DataStage, SQL e jobs Python/PySpark.

## Artefatos preparados
- docs/spec-pipeline-workspace-dotnet.md: especificação atualizada com direção e continuidade autorizadas.
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
O usuário autorizou atualizar a documentação e iniciar os próximos passos em 2026-10-09. Preservar essa autorização: inspecionar DEV, conferir divergências e detalhar o plano F1. Não pedir novamente autorização para a direção geral; apresentar para revisão o plano concreto antes de implementação conforme o processo do projeto.
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
Estamos iniciando a evolução do ORQUESTRA conforme docs/spec-pipeline-workspace-dotnet.md. Leia CLAUDE.md e docs/fluxo-desenvolvimento.md, confira o estado do checkout e revise a especificação antes de implementar. A direção aprovada é manter React, criar o espaço de trabalho de Pipeline, incorporar os menus Etapas/Fluxos, migrar gestão para .NET e manter Airflow e jobs Python/PySpark. Trabalhe por fases em branches de origin/develop, com testes, revisão adversarial e validação DEV. Preserve dados e serviços compartilhados, não faça deploy de produção e não exponha segredos. A continuidade foi autorizada. Considere três experiências (desenvolvimento, consulta e sustentação), monitores estratégico/operacional, capacidade por horário e Academy como evoluções documentadas. Comece pela inspeção e plano F1; apresente divergências e o plano concreto antes de implementar, sem reabrir decisões já aprovadas.

## Próxima entrega imediata
Usar docs/inicio-dev-pipeline-workspace-dotnet.md para inspeção segura e evidências. Acesso SSH não foi fornecido nesta sessão. Nenhuma conexão ou validação no servidor foi realizada.

## Referências visuais versionadas
Os quatro mockups aprovados estão em docs/mockups/pipeline-workspace/ na branch docs/pipeline-workspace-dotnet. Ler o README e abrir os PNGs antes de implementar a interface. Transportar essa pasta para o worktree de feature junto com a documentação. As imagens definem a direção visual; os contratos e permissões desta especificação definem o comportamento.
