# Workspace .NET — DEV F1

O piloto é exclusivamente DEV, somente leitura e sem porta publicada. A API antiga, React, Airflow e banco permanecem nos serviços existentes. Nenhum comando deste roteiro autoriza promoção para main ou produção. `WORKSPACE_ENABLED=false` é o padrão; autenticação continua obrigatória mesmo com o piloto desligado.

## Artefato e configuração

`backend-dotnet/global.json` fixa o SDK; `packages.lock.json` fixa NuGet. O Dockerfile usa SDK 10.0.401 noble e ASP.NET 10.0.12 noble pelos digests inspecionados nas imagens locais:

- SDK: `sha256:e70cdb7f80b0348f5cb85f19a8f670fca061f033d57eed12fa003d58b0e06317`.
- Runtime: `sha256:222759b391a1aaf241166672c8f99b2d4ada452e7b5319f3c6e8f265a37b5ad4`.

O processo roda como usuário não root, filesystem somente leitura e sem capabilities Linux. A rede é a rede Compose DEV; `expose: 8080` não publica porta no host. Limites iniciais: 512 MiB e 1 CPU, sem representar dimensionamento de produção.

Configurar no canal local seguro (`.env.dev`, ignorado), sem valores no Git ou linha de comando:

| Nome | Uso |
|---|---|
| `WORKSPACE_SQL_USER` / `WORKSPACE_SQL_PASSWORD` | Credencial dedicada com SELECT nas tabelas de sessão/RBAC necessárias; ambos obrigatórios no overlay |
| `WORKSPACE_SQL_DATABASE` | Banco DEV; padrão `orquestra_dev` |
| `WORKSPACE_ENABLED` | Habilitação explícita; padrão false |
| `WORKSPACE_IMAGE_TAG` | Tag do SHA validado; padrão f1 apenas para bancada |

`Workspace__Sql__Server=sqlserver-dev,1433` e `Workspace__LegacyApiUrl=http://orquestra-api:8000/` são internos. `TrustServerCertificate=true` é específico DEV. Não reaproveitar SA para a aplicação. Criar a credencial/grants exige procedimento operacional separado; não criar usuário nem executar DDL automaticamente no arranque da API.

## Roteamento e falhas

Somente o overlay troca o mount de `/etc/nginx/nginx.conf` por `config/nginx.workspace.dev.conf`. A configuração padrão de produção não muda.

`/orquestra/workspace` responde 308 relativo para `/orquestra/workspace/`, preservando query. O prefixo `/orquestra/workspace/` remove apenas `/orquestra`, mantendo `/workspace/` no backend, inclusive query. `/orquestra/workspaceXYZ`, `/orquestra/health`, `/orquestra/me`, `/orquestra/pipelines` e `/api/v1/` continuam no legado. Nenhuma escrita usa fallback FastAPI.

Nginx resolve `workspace-api` pelo DNS Docker em runtime (validade 5 s, timeout 2 s). Ausência de DNS/conexão e timeout respondem 503 JSON estável, com `Cache-Control: no-store`; o proxy inicia mesmo sem o serviço workspace. O backend conserva seus 401/403/503. Authorization é encaminhado sem logar headers; a correlação usa `$request_id` gerado no proxy, descartando o ID recebido do cliente.

Saúde pública do piloto: `/orquestra/workspace/health/live` e `/orquestra/workspace/health/ready`. Live não prova SQL. Ready verifica dependências necessárias, sem DDL; exige schema F2 quando WORKSPACE_DRAFTS_ENABLED=true. `/orquestra/health` permanece legado.

## Rascunhos F2

Aplicar migrations141/142 antes de habilitar `WORKSPACE_DRAFTS_ENABLED=true`; consultar [contratos](contracts/workspace-drafts-v1.md). A conta dedicada permanece sem escrita no legado. Conceder SELECT nas fontes de configuração explicitadas em LegacyFlowReader e SELECT/INSERT/UPDATE em rascunho/lease, SELECT/INSERT em versão/evento; não conceder DELETE nem roles amplas. Ausência de tabela opcional é tolerada; falta de permissão retorna503. Backup, migrations e grants fazem parte do deploy, nunca de requests.

## Instalação offline

O Dockerfile faz restore em build, portanto imagens-base isoladamente **não** provam build offline. Para runtime offline, gerar imagem final no ambiente de build, exportar por `docker save`, preparar SHA-256/manifesto/SBOM e transportar por canal autorizado. No alvo, conferir checksums e plataforma antes de `docker load`; usar `--no-build --pull never`. O alvo não precisa instalar SDK.

Para reconstrução offline, transportar também feed NuGet com todas as dependências transitivas, locks e SDK fixado; apontar NuGet.Config ao feed e executar restore locked sem egress. A disponibilidade das imagens não substitui esse ensaio. Referenciar o manifesto/evidência de bancada produzido na entrega, sem registrar segredos ou conteúdo privado do banco.

`scripts/package_workspace_offline.py --output <pasta-vazia>` prepara o feed dos locks, inventário/licenças, SBOM NuGet, manifesto, tar das imagens e fontes, checksums e executa restore/test/publish com `--network none --pull=false --no-cache`. O pacote inclui `REBUILD.md` para consumo a partir do tar. A imagem gerada tem tag `orquestra-workspace-f1:offline`; antes de servir, validar o ID do manifesto e marcar a mesma imagem como `orquestra-workspace:<tag-do-SHA-validado>`, usada por `WORKSPACE_IMAGE_TAG`.

Ensaio de 09/10/2026: 107 checksums conferidos, 68 pacotes; build, save/load e rebuild consumidor sem rede/cache passaram. SQL é omitido na bancada offline, mas a integração SQL separada passou. Evidências locais fora do Git: `/root/orquestra-f1-evidencias/offline/` e `offline-validation.json`. Ver [release F1](release-notes/workspace-pipeline-f1.md) para resultados e limites.

## Publicação seletiva no DEV

Aplicar somente ao SHA aprovado/validado na develop e depois do backup prescrito em `docs/fluxo-desenvolvimento.md`. Nunca executar `up` global, `down -v`, bootstrap ou recriação de banco/volumes.

```bash
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml -f docker-compose.workspace.dev.yaml --env-file .env.dev build workspace-api
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml -f docker-compose.workspace.dev.yaml --env-file .env.dev up -d --no-deps workspace-api
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml -f docker-compose.workspace.dev.yaml --env-file .env.dev up -d --no-deps --force-recreate ui-nginx
```

O mount do arquivo Nginx muda: recriação seletiva é necessária para trocar o arquivo/inode montado. Validar `nginx -t` e rotas antes de concluir. Não despejar `docker compose config` ou `docker inspect` completo de containers com environment secreto em logs; validação silenciosa `config -q` basta.

## Verificação e recuperação

```bash
python3 -m pytest tests/test_workspace_proxy_config.py -q
python3 scripts/smoke_workspace_proxy_isolated.py
```

O smoke cria rede Docker `--internal`, containers temporários de imagens locais e cliente HTTP dentro da rede. Não publica portas, não tem egress e remove exclusivamente seus recursos no finally. Prova proxy com upstream ausente, criado após Nginx, parado, resposta SQL 503 simulada, prefixo/barra/query, headers e rotas legadas/UI/Airflow. Não substitui testes reais de SQL/autenticação .NET nem valida Information Server/Caixa.

Após publicação: conferir SHA/tag, ready, release SQL/Admin e autenticação/capabilities de perfis sintéticos. Bearer inválido/expirado/revogado deve retornar 401, usuário inativo 403, dependência SQL indisponível 503 sem detalhe interno. Confirmar FastAPI/UI/Airflow saudáveis com workspace parado somente na janela de smoke autorizada.

Para desabilitar o piloto, definir `WORKSPACE_ENABLED=false` e recriar somente workspace-api. Para remover o roteamento, recriar somente ui-nginx com os dois arquivos originais Compose (base + DEV), **sem o overlay**, restaurando o mount padrão. Depois parar/remover apenas workspace-api se necessário; não tocar banco/volumes. Readiness e migrações/versão permanecem parte do gate global da entrega.


## Interface F3

`/pipelines/novo` cria rascunho vazio. `/pipelines/:nome/*` usa nome codificado uma vez; abas visão geral, fluxo, etapas, parâmetros e execuções. `experiencia=desenvolvimento|consulta|sustentacao` muda o contexto, sem ampliar permissões. `fonte=rascunho` permite consultar um rascunho de pipeline já publicado. `data=AAAA-MM-DD` conserva a data operacional no workspace e na abertura dos logs.

Consulta básica (`tela_pipelines`) recebe resumo sem nós. Fluxo exige também `tela_jobs`; execuções exigem adicionalmente `tela_logs`. Edição exige Bearer e `acao_editar`, transferência `acao_admin`. A API continua autoridade de revisão/lease/fence. O editor não usa o FluxoEditor legado e todas as mutações vão para `/workspace`.

Aliases query `/workspace/pipeline-context?name=...`, `/workspace/pipeline-drafts?name=...` e `/workspace/executions?name=...&date=...` preservam identidades com slash, percentual, Unicode e espaços. O último encaminha leitura GET ao FastAPI `/pipeline-execution?pipeline_name=...`, com RBAC em ambos os serviços, timeout de 5 segundos, limite de 2 MiB e erros sanitizados. Nenhum endpoint aceita URL de destino do cliente.

Dados locais sujos são mantidos somente na memória da aba e limpos na troca de sessão; recarregar a página perde esse conteúdo e há aviso de saída. Consulta não persiste posição/zoom nem faz renovação de lease. O ambiente mostrado vem da configuração do servidor, nunca de inferência da URL.

## Publicação F4

Habilitação integrada por `WORKSPACE_PUBLICATIONS_ENABLED=true`, migrations144/145 e política de motor carregada nos quatro serviços Airflow. Workspace consult-only continua sem comandos para Basic; publicação possui recurso `acao_publicar` separado. Ver [contrato](contracts/workspace-publications-v1.md) e [roteiro DEV](release-notes/workspace-pipeline-f4.md).

O SQL .NET continua sem escrita ativa; add grants somente nas tabelas de intenção/gestão e leitura de reservas/EXEC hash. Não habilitar flag apenas no frontend/backend nem desligar o gate para desbloquear uma projeção incompleta. Confirmação é por artefato/DAG/hash, com relógios UTC sincronizados. Menus legados serão tratados na F5; servidor já recusa alterações em pipelines geridos.
