# Rascunhos v1 — F2

Prefixo público DEV `/orquestra/workspace`; backend interno `/workspace`. Consulte capabilities antes de habilitar edição. `Workspace:Enabled` controla o módulo; `Workspace:DraftsEnabled` controla somente mutações, padrão false. Lease dura 120 segundos, ajustável por `Workspace:LeaseSeconds` entre 30 e 600. Cliente renova a cada 30 segundos (ou menos de metade da duração configurada).

GET capabilities mantém schemaVersion1 e os mesmos campos. editDraft exige ambas as telas, acao_editar, Bearer, flag e schema. administer acrescenta acao_admin. publish/execute/cancel/reprocess permanecem false. Basic é aceito apenas nas consultas.

| Método e caminho | Entrada | Resultado |
|---|---|---|
| GET pipelines/{name} | Nome exato, codificado na URL | pipelineName canônico, draftsAvailable, published (definition/layout/readOnlyReasons), draft ativo |
| POST pipelines | definition, layout | 201: identidade somente no workspace, revision1 |
| POST pipelines/{name}/drafts | Sem corpo | 201: snapshot consistente do publicado e versão base importada |
| GET drafts/{guid} | — | Conteúdo persistido, revisão, motivos somente leitura, lease |
| PUT drafts/{guid} | expectedRevision, fence, definition, layout | Conteúdo atualizado e revision+1 |
| POST drafts/{guid}/lease | `{}` adquirir ou `{ "fence": 1 }` renovar | holderUser, fence, expiresAt UTC, heldBySession |
| DELETE drafts/{guid}/lease | expectedRevision, fence | 204, encerra lease preservando fence |
| POST drafts/{guid}/transfer | expectedRevision, fence atual (0 se ausente) | Admin assume edição na própria sessão, fence+1 |
| DELETE drafts/{guid} | expectedRevision, fence | 204, descarte lógico auditado, revision+1 |

Consulta de contexto sem tela_jobs devolve apenas identidade e disponibilidade. Conteúdo do rascunho exige tela_pipelines+tela_jobs. Todos os comandos exigem essas telas+acao_editar e sessão Bearer vigente; transferência exige acao_admin. Sem privilégios pelo nome do perfil.

Identidade é NVARCHAR(200), com case/Unicode/espaços preservados; unicidade segue a collation SQL legada. Um rascunho ativo por pipeline. Dados salvos não expiram com lease, logout ou reinício. Descartados permanecem consultáveis por leitores autorizados. Leases em configurações somente leitura permitem liberar/transferir/descartar; salvar permanece bloqueado, impedindo rascunhos órfãos.

Importação preserva o contrato legado em metadata.legacyPipeline, metadata.legacyTables e configuration.legacyJob mais as tabelas de parâmetros/valida_arquivo por nó. Campos `_json` e dependências originais permanecem intactos. Arestas/posições são também projetadas para o contrato visual. O adapter de publicação futuro deverá interpretar essa representação antes de permitir publicar. Nenhum endpoint F2 projeta configuração no legado.

Parâmetros encrypted usam `param_value="***"`, `tem_valor` e `secretReference` (pipelineName/jobName/parameterName); nunca transportar cifra/valor. Referências não podem ser criadas/alteradas pelo save. Credenciais detectadas em outras configurações são redigidas e tornam a importação somente leitura. Conexões permanecem por ID. Tipos futuros e dependências inconsistentes também deixam o fluxo somente leitura com motivo explícito.

Erros JSON: detail em português e code estável. 401 sessão/Bearer; 403 permissão; 409 draft_conflict, revision_conflict, lease_held, lease_conflict, draft_read_only; 422 draft_invalid/body_too_large; 503 draft_schema_unavailable (migration141), drafts_disabled/dependency_unavailable. Corpo máximo1MiB, 1.000nós/10.000arestas, posições finitas. Campos desconhecidos do contrato de definição/layout permanecem preservados.

Eventos contêm apenas identidade do rascunho, ator, ação, revisão, operation_id e relógio UTC; nenhum JSON de configuração, credencial ou session hash. Retenção vinculada à vida do rascunho; expurgo futuro exige política explícita. Versão base é imutável e origem importada, sem afirmar versionamento de execuções anteriores.
