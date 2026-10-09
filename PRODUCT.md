# ORQUESTRA

<!-- impeccable:product-schema 1 -->

## Platform
web

## Users
Equipes de desenvolvimento, consulta e sustentação de pipelines ETL. Os três percursos estão definidos na spec aprovada docs/spec-pipeline-workspace-dotnet.md; experiência não concede permissões.

## Product Purpose
Construir, consultar e operar pipelines de dados com governança sobre o motor Airflow/DataStage existente.

## Operating Context
Aplicação corporativa em português do Brasil, React e FastAPI com SQL Server. Workspace .NET piloto em DEV; rascunhos persistidos separados da configuração publicada. Produção/Caixa possui autorização e validação próprias.

## Capabilities and Constraints
F1/F2 entregues: contratos, autenticação/RBAC, rascunhos, importação, revisão, lease e auditoria. F3 adiciona interface e criação. F4 adiciona validação funcional, publicação durável com confirmação no Airflow, histórico imutável, comparação e restauração para rascunho. Publicar exige permissão própria; execução operacional unificada pelo workspace pertence à F5. Preservar identidade técnica, todos os campos de configuração e segredos somente por referência. Mostrar apenas estados/métricas sustentados pela API.

## Brand Commitments
Preservar marca ORQUESTRA, idioma e tokens semânticos claros/escuros existentes. Referências aprovadas: docs/mockups/pipeline-workspace; dados dessas imagens são ilustrativos.

## Evidence on Hand
Spec aprovada e quatro mockups. Componentes/tokens atuais, docs/ui-temas-cores.md e docs/DESIGN_navegacao_regroup.md são autoridade da interface existente. Nenhum novo estilo global solicitado.

## Accessibility & Inclusion
Navegação por teclado, foco visível, rótulos associados, estados além de cor e composição responsiva, conforme spec aprovada.
