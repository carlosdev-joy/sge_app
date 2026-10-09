# Workspace Pipeline — F4

Validação funcional por etapa, publicação persistente com confirmação de versão/hash no Airflow, histórico imutável, comparação e restauração para rascunho. Versão da entrega incrementada pela migration 145 (DEV a partir de 2.9.0 → 2.10.0).

## Deploy DEV

1. Backup COPY_ONLY/CHECKSUM e RESTORE VERIFYONLY; guardar configuração DEV por canal protegido.
2. Integrar somente o candidato revisado em develop; usar os três arquivos Compose e `.env.dev`, projeto orquestra-dev. Sem up global, down, recriação SQL ou volumes.
3. Aplicar migrations 144 e 145 idempotentes. Grants do usuário .NET: SELECT/INSERT/UPDATE nas tabelas de publicação/gestão, SELECT em telemetria/reservas; EXEC em sp_workspace_active_hash. Preservar DENY INSERT/UPDATE/DELETE nas oito fontes legadas e versão UPDATE/DELETE.
4. Definir WORKSPACE_PUBLICATIONS_ENABLED=true somente com todos os componentes prontos. Overlay aplica flag ao .NET/FastAPI e quatro serviços Airflow; inclui /opt/airflow/config no PYTHONPATH. O hook exige procedure 144; sem ela, recusa tarefas quando habilitado.
5. Publicar imagem .NET do pacote offline verificado, dist final e código FastAPI/factory/config. Recriar seletivamente workspace-api, orquestra-api e quatro serviços Airflow para aplicar env/política; worker reiniciado obrigatoriamente. Verificar nginx -t. Nenhum dado de clientes usado no smoke.
6. Validar SHA/imageid/readiness/login/release/migrations, publicação sintética sob demanda, confirmação real DAG/hash, idempotência/restart, guards legado/motor, recuperação e histórico/restore.

## Operação e limites

Recurso `acao_publicar` é concedido inicialmente ao perfil admin pela migration, e configurável na matriz de permissões. Publicar exige Bearer/edição/lease/fence/revisão, sem bypass por perfil.

Não desligar a política do motor em um ambiente que já possui pipelines geridos para contornar erro. Quarentena após projeção permanece até correção publicada/confirmada. Rotina de rollback de infraestrutura deve preservar migrations/histórico/gate e usar versão revisada compatível; retirar a gestão/volumes não é recuperação de publicação.

F5 contém ações operacionais unificadas e redirects/menus. Main/produção/Caixa exigem autorização própria; piloto DataStage/dataset real e medição de desempenho pertencem à F6. Pacote offline cobre .NET/NuGet; Python/factory/política são código do repositório completo, sem dependência Python nova. SBOM de OS/bases depende do fornecedor.

Contrato: docs/contracts/workspace-publications-v1.md. Ameaças: docs/workspace-f4-ameacas.md. Evidências e SHA final ficam no registro de entrega da fase.

## Conferência no DEV e ajuste corretivo

PR479 foi integrado em develop e migrations144/145 aplicadas com backup verificado. O smoke real detectou que a consulta de hash da factory reutilizava o cursor fechado após a leitura do lote; a consulta passou a usar conexão própria por `hook.get_first`, mantendo binding e recusa em divergência. A F4 só encerra após retomada da operação em quarentena e smoke real completo. O backend/offline permanecem com fontes idênticas; este ajuste altera apenas o adaptador do motor.

No DEV, o factory precisa estar ativo para executar a intenção. A conexão do motor SQL14_DMDB41 vinha exclusivamente do ambiente e não aparecia no catálogo REST: seu identificador/tipo foi registrado no catálogo Airflow sem copiar credenciais. Após recriar API/webserver, o nginx exige reload para resolver novos IPs.

O aceite real também confirmou UUIDs representados diferentemente por pyodbc e pymssql. Adaptador e factory agora usam UUID canônico minúsculo nos marcadores, mantendo comparação estrita de hash/versão. Dois testes de regressão cobrem a fronteira entre drivers.

A factory real gerou a DAG e terminou SUCCESS na mesma corrida retomada. O Airflow2.11 devolve parâmetros REST como objetos Param serializados; a conferência agora extrai exclusivamente o value do wrapper reconhecido, preservando recusa para marcadores ausentes/diferentes e para classes desconhecidas. Compatível também com respostas escalares.
