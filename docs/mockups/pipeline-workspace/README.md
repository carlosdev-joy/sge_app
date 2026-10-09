# Referências visuais do workspace de Pipeline
Estas quatro imagens registram a direção visual aprovada na conversa de evolução do ORQUESTRA. A implementação deve abrir e inspecionar as imagens antes de definir layout, componentes e comportamento visual. Disponíveis na branch docs/pipeline-workspace-dotnet.

## Telas
- [Pipeline em execução](01-pipeline-execucao.png)
- [Pipeline em montagem](02-pipeline-montagem.png)
- [Malha com rascunho e edição identificada](03-malha-rascunho.png)
- [Criação de pipeline](04-criar-pipeline.png)

## Como aplicar
Preservar hierarquia visual, cabeçalho, navegação, composição de canvas, painéis contextuais e linguagem de estados. Reutilizar React e os tokens semânticos existentes, com modo claro e escuro e acessibilidade.

Mockups são referência visual, não garantia de que todos os comportamentos já existem. Seguir docs/spec-pipeline-workspace-dotnet.md para escopo, contratos e permissões.

Corrigir na implementação as inconsistências ilustrativas: ambiente da lateral deve acompanhar o contexto Desenvolvimento/Produção; parâmetros de execução não são editáveis; percentuais e previsões só aparecem com fonte real; recursos futuros não são habilitados como se já funcionassem.

Os dados, nomes, tempos e versões nas imagens são ilustrativos. Não usá-los como métricas reais.

## Continuidade no servidor
Buscar esta branch sem trocar o checkout servido pelo DEV. Copiar esta pasta para o worktree de implementação ou abrir as imagens diretamente na branch documental. Ler os roteiros de continuidade e início no DEV.
