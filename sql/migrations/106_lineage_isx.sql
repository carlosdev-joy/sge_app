-- sql/migrations/106_lineage_isx.sql
-- Lineage automático via ISX (spec docs/spec-lineage-isx.md, F1).
--
-- O Orquestra passa a exportar o job do DataStage por conta própria (istool,
-- formato ISX) e a gravar por stage o SQL completo, colunas, expressões, APT
-- code e fluxo. O que esta migration cria:
--
--   1. dbo.etl_ds_job_isx          — CABEÇALHO por job (pasta no DataStage, tipo,
--                                    lastModified que serve de chave de cache,
--                                    descrição, parâmetros, fluxo, filhos de
--                                    sequence, hash do .isx, status da extração).
--                                    Um por (pipeline_name, job_name): lineage ISX
--                                    só existe para job que está num pipeline do
--                                    Orquestra (regra do usuário) — a FK garante.
--   2. dbo.etl_job_lineage         — colunas novas por stage (colunas de entrada,
--                                    APT code, expressões, id interno do stage) e
--                                    índice por (pipeline, job, método). As linhas
--                                    ISX usam extraction_method = 'isx_auto' (cabe
--                                    no VARCHAR(20)); manual/dsx_auto ficam.
--   3. dbo.etl_stage_type_map      — tipos PX que faltavam (MERGE: não sobrescreve
--                                    o que o admin editou; só INSERE ausentes).
-- Idempotente (roda 2×). Aplicada pela etapa 6c do deploy.sh.

-- ═══════════════════════════════════════════════════════════════════════════
-- 1. Cabeçalho por job
-- ═══════════════════════════════════════════════════════════════════════════
IF OBJECT_ID('dbo.etl_ds_job_isx', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_ds_job_isx (
        id                     INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_ds_job_isx PRIMARY KEY,
        pipeline_name          NVARCHAR(200)  NOT NULL,
        job_name               NVARCHAR(200)  NOT NULL,
        ds_project             NVARCHAR(50)   NOT NULL,   -- etl_pipeline.project_name
        ds_folder_path         NVARCHAR(500)  NULL,       -- '\Jobs\SsdVida\_Dime', como a API REST devolve
        ds_job_type            VARCHAR(20)    NULL,       -- 'PARALLEL' | 'SEQUENCE'
        ds_last_modified       VARCHAR(40)    NULL,       -- texto ISO da API REST (chave de cache; comparação textual)
        job_description        NVARCHAR(2000) NULL,       -- shortDescription
        job_long_description   NVARCHAR(MAX)  NULL,       -- longDescription
        parameters_json        NVARCHAR(MAX)  NULL,       -- [{name, type, default, description}]
        flow_json              NVARCHAR(MAX)  NULL,       -- [{from, from_type, link, to, to_type}]
        children_json          NVARCHAR(MAX)  NULL,       -- sequence: [{job_name, activity}]
        nao_reconhecidos_json  NVARCHAR(MAX)  NULL,       -- o que o parser viu e não classificou
        isx_sha256             CHAR(64)       NULL,
        isx_bytes              INT            NULL,
        status                 VARCHAR(20)    NOT NULL CONSTRAINT DF_etl_ds_job_isx_status DEFAULT 'ok', -- 'ok' | 'erro'
        erro                   NVARCHAR(500)  NULL,       -- frase pública do último erro
        extracted_at           DATETIME2(0)   NOT NULL CONSTRAINT DF_etl_ds_job_isx_em DEFAULT GETDATE(),
        extracted_by           NVARCHAR(100)  NULL,       -- matrícula ou 'dag:etl_lineage_extract_isx'
        duracao_ms             INT            NULL,
        -- (200 + 200) x 2 = 800 bytes: dentro do teto de 1.700 de uma chave de índice.
        CONSTRAINT UQ_etl_ds_job_isx UNIQUE (pipeline_name, job_name),
        -- ON DELETE CASCADE como a etl_pipeline_job_param (026): remover/renomear o
        -- job no pipeline e apagar o pipeline (jobs.py, sp_etl_pipeline_delete) não
        -- apagam esta tabela à mão — sem cascade, passariam a falhar com erro 547.
        CONSTRAINT FK_etl_ds_job_isx_job FOREIGN KEY (pipeline_name, job_name)
            REFERENCES dbo.etl_pipeline_job (pipeline_name, job_name) ON DELETE CASCADE
    );
    PRINT '[OK] Tabela dbo.etl_ds_job_isx criada';
END
ELSE
    PRINT '[SKIP] dbo.etl_ds_job_isx ja existe';
GO

-- Ambiente que criou a tabela pela primeira versão desta migration (sem cascade):
-- recria a FK com ON DELETE CASCADE. delete_referential_action 0 = NO_ACTION.
IF EXISTS (SELECT 1 FROM sys.foreign_keys
           WHERE name = 'FK_etl_ds_job_isx_job' AND parent_object_id = OBJECT_ID('dbo.etl_ds_job_isx')
             AND delete_referential_action = 0)
BEGIN
    ALTER TABLE dbo.etl_ds_job_isx DROP CONSTRAINT FK_etl_ds_job_isx_job;
    ALTER TABLE dbo.etl_ds_job_isx ADD CONSTRAINT FK_etl_ds_job_isx_job FOREIGN KEY (pipeline_name, job_name)
        REFERENCES dbo.etl_pipeline_job (pipeline_name, job_name) ON DELETE CASCADE;
    PRINT '[OK] FK_etl_ds_job_isx_job recriada com ON DELETE CASCADE';
END
ELSE
    PRINT '[SKIP] FK_etl_ds_job_isx_job ja tem ON DELETE CASCADE';
GO

-- ═══════════════════════════════════════════════════════════════════════════
-- 2. Colunas novas por stage em etl_job_lineage
-- ═══════════════════════════════════════════════════════════════════════════
IF COL_LENGTH('dbo.etl_job_lineage', 'input_columns_json') IS NULL
BEGIN
    ALTER TABLE dbo.etl_job_lineage ADD input_columns_json NVARCHAR(MAX) NULL;
    PRINT '[OK] etl_job_lineage.input_columns_json';
END
ELSE PRINT '[SKIP] etl_job_lineage.input_columns_json ja existe';
GO
IF COL_LENGTH('dbo.etl_job_lineage', 'apt_code') IS NULL
BEGIN
    ALTER TABLE dbo.etl_job_lineage ADD apt_code NVARCHAR(MAX) NULL;
    PRINT '[OK] etl_job_lineage.apt_code';
END
ELSE PRINT '[SKIP] etl_job_lineage.apt_code ja existe';
GO
IF COL_LENGTH('dbo.etl_job_lineage', 'expressions_json') IS NULL
BEGIN
    ALTER TABLE dbo.etl_job_lineage ADD expressions_json NVARCHAR(MAX) NULL;
    PRINT '[OK] etl_job_lineage.expressions_json';
END
ELSE PRINT '[SKIP] etl_job_lineage.expressions_json ja existe';
GO
IF COL_LENGTH('dbo.etl_job_lineage', 'stage_internal_id') IS NULL
BEGIN
    ALTER TABLE dbo.etl_job_lineage ADD stage_internal_id VARCHAR(20) NULL;
    PRINT '[OK] etl_job_lineage.stage_internal_id';
END
ELSE PRINT '[SKIP] etl_job_lineage.stage_internal_id ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'IX_etl_job_lineage_job_metodo' AND object_id = OBJECT_ID('dbo.etl_job_lineage'))
BEGIN
    CREATE INDEX IX_etl_job_lineage_job_metodo
        ON dbo.etl_job_lineage (pipeline_name, job_name, extraction_method);
    PRINT '[OK] Indice IX_etl_job_lineage_job_metodo criado';
END
ELSE
    PRINT '[SKIP] IX_etl_job_lineage_job_metodo ja existe';
GO

-- ═══════════════════════════════════════════════════════════════════════════
-- 3. Tipos PX no mapa de stages (só INSERE o que falta: o admin pode ter editado)
-- ═══════════════════════════════════════════════════════════════════════════
-- A tabela tem DUAS grafias no repo: `stage_type` (sql/schema_prod_dev.sql,
-- deploy_full.sql; lida por /lineage) e `type_raw` + `description`
-- (script/alteracoes/20260601_lineage_catalogo_fase2_v1; lida pelo catálogo).
-- Qual existe depende de qual script rodou primeiro no ambiente. O seed abaixo
-- descobre a coluna-chave em tempo de execução e insere só o que falta.
IF OBJECT_ID('dbo.etl_stage_type_map', 'U') IS NOT NULL
BEGIN
    IF OBJECT_ID('tempdb..#src_isx') IS NOT NULL DROP TABLE #src_isx;
    SELECT * INTO #src_isx FROM (VALUES
            ('PxCopy',                'Cópia',                       'transformacao', 'transformacao', 'Copia o fluxo para uma ou mais saídas'),
            ('PxLookup',              'Lookup',                      'transformacao', 'transformacao', 'Enriquecimento por chave'),
            ('PxJoin',                'Join',                        'transformacao', 'transformacao', NULL),
            ('PxMerge',               'Merge',                       'transformacao', 'transformacao', NULL),
            ('PxSort',                'Ordenação',                   'transformacao', 'transformacao', NULL),
            ('PxSortWithGroupBy',     'Ordenação com agrupamento',   'transformacao', 'transformacao', NULL),
            ('PxRemDup',              'Remover duplicados',          'transformacao', 'transformacao', NULL),
            ('PxFunnel',              'Funnel (união de fluxos)',    'transformacao', 'transformacao', NULL),
            ('PxAggregator',          'Agregação',                   'transformacao', 'transformacao', NULL),
            ('PxFilter',              'Filtro',                      'transformacao', 'transformacao', NULL),
            ('PxModify',              'Modify',                      'transformacao', 'transformacao', NULL),
            ('PxHead',                'Head (primeiras linhas)',     'debug',         'transformacao', NULL),
            ('PxTail',                'Tail (últimas linhas)',       'debug',         'transformacao', NULL),
            ('PxSample',              'Amostragem',                  'debug',         'transformacao', NULL),
            ('CJobActivity',          'Job (atividade de sequence)', 'sequence',      'transformacao', 'Chama outro job dentro de um sequence'),
            ('CNotificationActivity', 'Notificação (sequence)',      'sequence',      'transformacao', NULL),
            ('CExceptionHandler',     'Tratador de exceção (sequence)', 'sequence',   'transformacao', NULL),
            ('CExecCommandActivity',  'Comando (sequence)',          'sequence',      'transformacao', 'Executa comando do sistema dentro de um sequence'),
            ('CRoutineActivity',      'Rotina (sequence)',           'sequence',      'transformacao', NULL),
            ('CSequencerActivity',    'Sequenciador',                'sequence',      'transformacao', NULL),
            ('CWaitForFileActivity',  'Aguardar arquivo (sequence)', 'sequence',      'transformacao', NULL),
            ('CStartLoopActivity',    'Início de laço (sequence)',   'sequence',      'transformacao', NULL),
            ('CEndLoopActivity',      'Fim de laço (sequence)',      'sequence',      'transformacao', NULL),
            ('CUserVariablesActivity','Variáveis do usuário (sequence)', 'sequence',  'transformacao', NULL),
            ('PxFileSet',             'FileSet (arquivo FS)',        'arquivo',       'ambos',         'PX FileSet'),
            ('PxLookupFileSet',       'Lookup FileSet',              'arquivo',       'origem',        NULL),
            ('PxExternalSource',      'Fonte externa (comando)',     'arquivo',       'origem',        NULL),
            ('PxExternalTarget',      'Destino externo (comando)',   'arquivo',       'destino',       NULL)
        ) AS v(type_raw, type_label, type_category, role_hint, description);

    DECLARE @chave sysname = CASE
        WHEN COL_LENGTH('dbo.etl_stage_type_map', 'type_raw')   IS NOT NULL THEN N'type_raw'
        WHEN COL_LENGTH('dbo.etl_stage_type_map', 'stage_type') IS NOT NULL THEN N'stage_type'
    END;
    IF @chave IS NULL
        PRINT '[SKIP] etl_stage_type_map sem coluna type_raw nem stage_type — seed nao aplicado';
    ELSE
    BEGIN
        DECLARE @tem_desc BIT = CASE WHEN COL_LENGTH('dbo.etl_stage_type_map', 'description') IS NOT NULL THEN 1 ELSE 0 END;
        DECLARE @sql NVARCHAR(MAX) = N'
            MERGE dbo.etl_stage_type_map AS tgt
            USING #src_isx AS src ON tgt.' + QUOTENAME(@chave) + N' = src.type_raw
            WHEN NOT MATCHED THEN
                INSERT (' + QUOTENAME(@chave) + N', type_label, type_category, role_hint'
                          + CASE WHEN @tem_desc = 1 THEN N', description' ELSE N'' END + N')
                VALUES (src.type_raw, src.type_label, src.type_category, src.role_hint'
                          + CASE WHEN @tem_desc = 1 THEN N', src.description' ELSE N'' END + N');';
        EXEC sp_executesql @sql;
        PRINT '[OK] etl_stage_type_map (chave ' + @chave + '): tipos PX/sequence conferidos — ' + CAST(@@ROWCOUNT AS VARCHAR(10)) + ' inseridos';
    END
    IF OBJECT_ID('tempdb..#src_isx') IS NOT NULL DROP TABLE #src_isx;
END
ELSE
    PRINT '[SKIP] dbo.etl_stage_type_map nao existe (script/alteracoes/20260601_lineage_catalogo_fase2_v1) — o engine usa o mapa embutido';
GO
