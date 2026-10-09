# Workspace Pipeline — F3 (DEV 2.9.0)

Criação simples abre um rascunho vazio. A identidade técnica é preservada exatamente, separada do nome de exibição. O workspace reúne visão geral, fluxo, etapas, parâmetros e contexto de execuções. Desenvolvimento permite editar somente com capacidades e lease; consulta e sustentação permanecem somente leitura.

O editor é independente do cadastro publicado. Propriedades comuns e configuração avançada preservam campos adicionais de todos os onze tipos suportados; parâmetros cifrados permanecem mascarados e por referência. Erros de lease/revisão congelam edição sem apagar alterações mantidas na memória da aba. A configuração completa não é armazenada no navegador.

## Deploy em DEV

- Migration idempotente `143_versao_workspace_pipeline_f3.sql`: incremento funcional, esperado 2.9.0 após 2.8.0.
- Atualizar imagem workspace-api pelo pacote offline e variável `Workspace__EnvironmentLabel=Desenvolvimento` do compose.
- Atualizar FastAPI e reiniciar somente API para carregar o alias de consulta contextual por query; carregar a dist commitada.
- Usar os três arquivos compose de DEV e `.env.dev`; preservar SQL, volumes e Airflow.
- Backup COPY_ONLY/CHECKSUM e VERIFYONLY antes da integração/deploy.

## Smoke

Conferir readiness, login, versão, migration sem pendências, criação vazia, edição com revision/fence, consulta por outra sessão, bloqueio de revisão obsoleta, leitura de contexto publicado e execuções com as três permissões. Verificar que nenhuma identidade foi criada no cadastro publicado. Conferir temas claro/escuro e desktop/mobile. Dados sintéticos não substituem a validação DataStage na Caixa.

## Limites

Publicação, validação funcional completa e ações operacionais seguem para F4/F5. Menus e rotas de compatibilidade continuam disponíveis em F3. Mudanças somente em develop/DEV; main e produção exigem autorização separada.
