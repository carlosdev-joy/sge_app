-- ═══════════════════════════════════════════════════════════════════════════
-- Backlog — Lineage automático via ISX (spec docs/spec-lineage-isx.md §2 OUT,
--   §6 e §8). Itens que NÃO entraram nas fases F1–F5, inclusive os registrados
--   pelas revisões adversariais e auditorias de segurança. Registro versionável
--   para dbo.etl_backlog (aba Admin › Sistema › Backlog). Idempotente por
--   título: rodar de novo não duplica.
-- Uso: sqlcmd -S <srv> -d <db> -b -I -i sql/backlog/lineage_isx.sql
-- ═══════════════════════════════════════════════════════════════════════════
IF OBJECT_ID('dbo.etl_backlog', 'U') IS NULL
BEGIN
    RAISERROR('dbo.etl_backlog não existe: aplique a migration 035 antes.', 16, 1);
    RETURN;
END
GO

DECLARE @itens TABLE (titulo NVARCHAR(200), descricao NVARCHAR(MAX), tipo NVARCHAR(16),
                      area NVARCHAR(24), prioridade NVARCHAR(4), tags NVARCHAR(200));
INSERT INTO @itens VALUES
(N'Lineage ISX: contexto para IA (consulta por job e prompt)',
 N'O banco ficou pronto — SQL completo por stage, colunas com tipo e tamanho, expressões coluna a coluna, APT code, fluxo e parâmetros em etl_ds_job_isx/etl_job_lineage — mas o assistente ficou fora (spec §2 OUT; §9 do documento original). Endpoint que monte o contexto de um job (cabeçalho + stages + filhos) em texto para o assistente, custo de modelo avaliado antes (skill claude-api), sem levar literais sensíveis do design do job (spec §8.14).',
 N'feature', N'backend', N'P2', N'lineage,isx,ia'),
(N'Lineage ISX: extrair os filhos do sequence em cadeia',
 N'Cada filho é extraído por demanda (link + Extrair na aba Job DataStage) ou pelo lote; a sequence não puxa os filhos (spec §2 OUT). Opção "extrair filhos" que percorra children_json recursivamente, respeitando a regra "job só com pipeline" (filho fora do pipeline continua só informado), com teto de profundidade e o mesmo executor e lock por job (409) da extração unitária.',
 N'feature', N'backend', N'P2', N'lineage,isx'),
(N'Lineage ISX: tela no Admin para o mapa de tipos de stage (etl_stage_type_map)',
 N'O cabeçalho da aba avisa "N stage(s) com tipo fora do mapa" (nao_reconhecidos_json), mas incluir o tipo é por SQL (manual §4.8). Tela em Admin › Sistema com a lista, a categoria (banco/arquivo/transformacao/sequence/debug) e o role_hint, mais um "incluir" a partir dos tipos não reconhecidos dos jobs já extraídos. Depende de unificar a grafia da tabela (item próprio).',
 N'feature', N'frontend', N'P2', N'lineage,isx,admin'),
(N'Lineage: unificar a grafia de etl_stage_type_map (stage_type × type_raw)',
 N'sql/schema_prod_dev.sql e sql/deploy_full.sql criam a chave como stage_type (lida por GET /lineage e dags/etl_lineage_query.py); script/alteracoes/20260601_lineage_catalogo_fase2_v1 cria type_raw + description (lida por api/routers/catalogo.py e dags/etl_catalogo_query.py). Qual existe depende de qual script rodou primeiro no ambiente; no DEV é stage_type e as consultas do catálogo falham com "Invalid column name type_raw". A migration 106 e o engine descobrem a coluna em tempo de execução (spec §8.10). Conferir em produção — SELECT COL_LENGTH(''dbo.etl_stage_type_map'',''type_raw''), COL_LENGTH(''dbo.etl_stage_type_map'',''stage_type'') — e migrar para uma grafia só, ajustando os dois leitores.',
 N'debt', N'backend', N'P2', N'lineage,catalogo,dados'),
(N'Lineage ISX: expurgo de cabeçalhos de jobs que sumiram do DataStage',
 N'Remover o job do pipeline apaga o cabeçalho (FK ON DELETE CASCADE da migration 106). Mas um job renomeado ou apagado no DataStage continua mapeado no pipeline: a cada tentativa o cabeçalho fica com status erro "não encontrado no projeto … do DataStage" e o lineage antigo embaixo. Rotina (ou passo do lote) que marque esses cabeçalhos como órfãos, avise na aba e permita expurgar as linhas isx_auto com confirmação.',
 N'debt', N'backend', N'P3', N'lineage,isx,operacao'),
(N'Lineage ISX: agendar o lote (schedule da DAG etl_lineage_extract_isx)',
 N'A DAG só roda por disparo manual — botão "Extrair todos (lote)" ou POST /lineage/isx/lote, ambos só para admin. Um schedule semanal fora do horário dos jobs, com o cache pelo lastModified (só reextrai o que mudou no DataStage), manteria o lineage sempre atual. Exige o usuário de serviço da Connection orquestra_api (spec §8.1) e janela combinada com a operação (risco 4: uma JVM do istool por job).',
 N'feature', N'datastage', N'P3', N'lineage,isx,airflow'),
(N'Lineage: file_path, stage_name e database_name em NVARCHAR',
 N'As colunas são VARCHAR em etl_job_lineage: caminho ou nome com acento fora da collation vira "?" (risco 10, spec §8.7). O parser corta em UTF-16 e registra o caso em nao_reconhecidos_json. Migrar para NVARCHAR mexe no extrator DSX e na sp_etl_job_lineage_upsert — spec própria de lineage.',
 N'debt', N'backend', N'P3', N'lineage,dados'),
(N'Lineage ISX: certificado da API REST do DataStage (sair de DS_API_VERIFY_SSL=false)',
 N'Com false a API avisa a cada arranque e aceita qualquer certificado na porta da API REST (MITM na rede interna, risco 6). DS_API_VERIFY_SSL aceita o caminho de uma CA interna: obter a cadeia com a infra, montar no container da API e trocar o valor no .env (spec §8.3).',
 N'debt', N'infra', N'P2', N'lineage,isx,seguranca,infra'),
(N'Lineage ISX: SQL, APT e BeforeSQL visíveis a qualquer usuário autenticado',
 N'GET /lineage/isx/job e a aba mostram sql_expression, apt_code e as expressões a quem tem a tela Governança; esses campos podem carregar literais do design do job (spec §8.14 — parâmetros Encrypted e nomes de senha já são mascarados). Decidir entre restringir por permissão (ex.: SQL/APT só com acao_editar) e mascarar padrões (senha=, password=) na gravação.',
 N'debt', N'backend', N'P2', N'lineage,isx,seguranca'),
(N'Lineage ISX: resolver valores de Parameter Set (#PSet.X#)',
 N'Caminhos, DSNs e SQL trazem #PSet.Param# como está, com badge e explicação na tela (spec §2 OUT). Ler os valores default do parameter set (has_ParameterDef do job / arquivos do projeto) e mostrar "valor padrão" no badge, sem substituir o texto gravado — o valor real vem do runtime.',
 N'feature', N'backend', N'P3', N'lineage,isx'),
(N'Lineage ISX: server jobs (jobType fora de PARALLEL/SEQUENCE)',
 N'A extração responde 422 para server jobs (spec §8.12): o istool exporta com outra extensão e o XML tem outro esquema de stages. Levantar quantos existem nos pipelines cadastrados antes de decidir se vale o parser.',
 N'feature', N'backend', N'P3', N'lineage,isx'),
(N'Lineage: lineage em nível de coluna a partir do ISX',
 N'A aba Lineage da Governança continua por objeto (tabela/arquivo). O ISX já grava as colunas de entrada e de saída com tipo e as expressões "saída ← expressão (origem)" por stage: dá para seguir uma coluna de ponta a ponta dentro do job e entre jobs pelo objeto. Spec própria (consulta + UI).',
 N'feature', N'frontend', N'P3', N'lineage,isx,ux');

INSERT INTO dbo.etl_backlog (titulo, descricao, tipo, area, prioridade, status, tags, criado_por, ref_pr)
SELECT i.titulo, i.descricao, i.tipo, i.area, i.prioridade, N'ideia', i.tags, N'spec-lineage-isx-f5', N'#369-#371,#373'
FROM @itens i
WHERE NOT EXISTS (SELECT 1 FROM dbo.etl_backlog b WHERE b.titulo = i.titulo);

PRINT '[OK] backlog do lineage ISX registrado (sem duplicar)';
GO
