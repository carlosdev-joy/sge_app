# Workspace de Pipeline — F1

F1 adiciona a fundação .NET do workspace em paralelo ao backend atual. O piloto DEV oferece saúde, readiness e capacidades autenticadas; não oferece edição, publicação ou operação de pipelines. A interface existente continua servida pelo React atual.

## Implementação

- Solução modular .NET 10, SDK 10.0.401 e ASP.NET 10.0.12, com imagens por digest e locks NuGet.
- Contrato v1 de definição, identidade, layout, capacidades e contexto futuro de execução. Campos desconhecidos e omissão/null são preservados; schema ou nó desconhecido torna a definição somente leitura.
- Bearer opaco com SHA-256, relógio SQL, usuário ativo e união perfil/extras. Basic valida identidade no legado e recarrega permissões pelo SQL. Não há bypass pelo nome do perfil nem permissão implícita quando a lista está vazia.
- Consultas SQL parametrizadas, credencial dedicada somente leitura e mensagens de indisponibilidade sem detalhes internos. Apenas ausência da tabela opcional extras é tolerada; acesso negado e schema incorreto retornam indisponibilidade.
- Overlay exclusivamente DEV e DNS runtime no proxy `/orquestra/workspace/`; falha do piloto retorna 503 e preserva os endpoints legados.
- Migration 140 registra a funcionalidade e incrementa a versão menor, zerando patch; no DEV observado antes da entrega, 2.6.0 passa a 2.7.0. Sem tabelas draft nesta fase.

## Validação antes da integração

Em `develop` base `6e711e54e5883fb6d66edf13dfc1fe229df19c45`:

- .NET Release: 38 passaram, nenhum omitido, incluindo SQL Server real em banco sintético separado. Cobertos relógio/expiração/revogação, usuário inativo, fallback consulta, collation, perfil/extras, mudança de permissões, acesso restrito e negação de UPDATE.
- Python: 7.136 passaram, 8 falharam e 51 foram omitidos. As oito falhas são exatamente as registradas no baseline; nenhuma nova.
- TypeScript e build passaram; lint 166 erros/12 avisos, sem assinaturas novas. Build não alterou dist. Bytes NUL somente no arquivo preexistente `ui-react/src/lib/lineageIsx.ts`.
- Proxy HTTP em rede Docker isolada sem egress: início sem workspace, recuperação DNS, query/prefixo/headers, SQL 503 simulado, parada e GET/POST 503, preservando UI/FastAPI/Airflow simulados.
- Revisão adversarial identificou dois defeitos: metadata SQL invisível e deadline HTTP incompleta. Ambos corrigidos e cobertos por regressões; reavaliação aprovada. Revisão independente da infraestrutura não identificou defeito confirmado.
- Distribuição offline: restore locked com cache vazia, testes e publish sem rede; save/load e reconstrução pelo tar sem rede/cache passaram. São 37 testes .NET aprovados nesse ensaio e um omitido por ausência de SQL; o gate SQL separado passou.

## Deploy e limites

Seguir [roteiro DEV](../dev-workspace-dotnet.md), com backup verificado, grants por coluna em sessão/RBAC, migration 140 e publicação seletiva somente de workspace-api/ui-nginx. Conferir SHA e imagem efetivos, login legado, versão pública, capacidades, revogação, parada e recuperação do piloto.

Pacote offline gerado fora do Git, com imagens, feed de 68 pacotes, inventário, SBOM CycloneDX de NuGet, manifesto e checksums. O ensaio cobre Linux/amd64 neste servidor; não comprova o ambiente air-gapped da Caixa nem Information Server real. Componentes Linux das imagens-base exigem SBOM do fornecedor. Não se afirma determinismo binário das imagens reconstruídas.

F2 permanece responsável por persistência de rascunhos. Granularidade própria de publicar deve ser definida antes da F4. A F1 não integra o editor ao novo backend. Main e produção têm autorização separada.
