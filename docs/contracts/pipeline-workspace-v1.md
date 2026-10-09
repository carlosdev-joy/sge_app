# Contrato do workspace de Pipeline v1

Este contrato de transporte usa JSON com nomes camelCase e `schemaVersion: 1`.
A F1 disponibiliza somente capacidades e infraestrutura; `IFlowAccess.ReadPublishedAsync`
é uma porta definida para leitura futura, sem endpoint de fluxo ou implementação de gravação.
Nenhum documento deste contrato autoriza salvar, publicar ou alterar o cadastro ativo.

## Definição publicada

`PipelineDefinition` contém `identity`, `nodes` e `edges`; `metadata`, `schedule` e
`parameters` preservam JSON legado sem converter campos específicos de tipos. `identity.pipelineName`
é a identidade original, com caixa e Unicode preservados. `displayName` é opcional e nullable.
IDs não são normalizados, decodificados como URL nem renomeados durante o transporte.
Limites de cadastro legado são 200 unidades UTF-16 para pipeline/job; `maxLength` JSON Schema
conta caracteres Unicode e portanto não substitui essa validação de cadastro.

Cada nó contém `id`, `type` e `configuration`. Tipos conhecidos: datastage, shell,
python, storedproc, http, decisao, notificacao, sql, aguarde, email e valida_arquivo.
Configuração, vínculos de parâmetros, dependências e condições permanecem na representação
de origem, sem assumir que valores vazios, omitidos e null sejam equivalentes. Arestas
contêm `source`, `target` e `branch` opcional/nullable; condições adicionais são preservadas.

Propriedades desconhecidas são preservadas por extension data na definição, identidade,
nó, aresta, layout e posição. Um tipo desconhecido ou schemaVersion diferente de 1 torna
a definição somente leitura (`IsReadOnly` interno; `FlowReadResult.readOnlyReasons` comunica
os motivos). Não descartar nós desconhecidos. A F1 inteira permanece sem escrita mesmo
para documentos reconhecidos. O schema v1 descreve documentos v1; versões futuras podem
ser transportadas pelo DTO sem serem aceitas como documentos v1 pelo validador.

Omissão de metadata/schedule/parameters/displayName/branch continua omissão; null explícito
continua null. Os campos obrigatórios e coleções estruturais devem ser fornecidos pelo produtor.
A ordem de propriedades e a formatação JSON não são garantidas; o round-trip garante valores
e presença de propriedades, não igualdade de bytes. Não usar o JSON serializado como hash
canônico: canonicalização, conteúdo versus layout e regras de publicação pertencem às próximas fases.

## Layout e leitura

`FlowReadResult` agrupa `definition`, `layout` e `readOnlyReasons`. `FlowLayout` é um documento
separado com schemaVersion e `nodes`, mapa do ID original para coordenadas finitas `x`/`y`.
O layout não altera o conteúdo semântico do fluxo nem define a ordem de execução.

## Capacidades F1

`GET /workspace/capabilities` autenticado retorna `schemaVersion`, `enabled`, `actions` e
`knownNodeTypes`. `consultDefinition` exige tela_pipelines; `consultStages` exige também
tela_jobs; `consultLogs` exige também tela_logs. Com piloto desligado ou recursos ausentes,
as capacidades respectivas são false. Perfil/experiência não concede permissão e admin
não ganha bypass pelo nome do perfil. `editDraft`, `publish`, `execute`, `cancel`, `reprocess`
e `administer` são sempre false na F1, mesmo quando o usuário tem permissões legadas.

O catálogo de capacidades não é autorização para executar ações no backend. Recursos
de publicação independentes serão definidos antes da F4; as ações legadas agrupadas em
acao_executar não são apresentadas como novas permissões disponíveis.

## Segurança e execução futura

Produtores devem remover segredos antes de construir estes DTOs: referências de conexão
podem aparecer; senha, token, connection string e ciphertext Encrypted não podem aparecer.
Parâmetros secretos devem ter representação mascarada. O DTO genérico e o schema não
redigem conteúdo automaticamente; fixtures são estritamente sintéticas.

`ExecutionContext` reserva correlationId, publishedVersionId, engine, pool, queue,
executor, attemptId e timestamps expectedAt/dependenciesReleasedAt/queuedAt/startedAt/completedAt,
com `sources` por campo. Datas usam ISO 8601 com offset. Null indica ausência de dado na
fonte; não estimar timestamps ou capacidade. Não há coleta nova ou endpoint de execução .NET na F1.

Schema normativo: [pipeline-workspace-v1.schema.json](pipeline-workspace-v1.schema.json).
Testes: `backend-dotnet/Orquestra.Tests/ContractTests.cs` e fixtures SQL/Python/DataStage.
