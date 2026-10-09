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
