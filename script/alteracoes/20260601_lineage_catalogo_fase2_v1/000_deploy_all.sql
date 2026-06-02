USE [DMDB41];
GO

/* ============================================================
   ORQUESTRA — Lineage Catálogo (Fase 2) v1.0
   Deploy único (produção): cria/atualiza tudo de forma idempotente.

   Inclui:
   1) dbo.etl_stage_type_map (CREATE + seed MERGE)
   2) dbo.etl_job_lineage: direction NVARCHAR(30) + coluna file_path
   3) dbo.sp_etl_job_lineage_upsert: direction + file_path + validação
   ============================================================ */

/* 1) etl_stage_type_map */
IF OBJECT_ID('dbo.etl_stage_type_map', 'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[etl_stage_type_map] (
        [id]            INT IDENTITY(1,1) NOT NULL,
        [type_raw]      VARCHAR(100) NOT NULL,
        [type_label]    VARCHAR(100) NOT NULL,
        [type_category] VARCHAR(30)  NOT NULL,
        [role_hint]     VARCHAR(20)  NOT NULL,
        [description]   VARCHAR(500) NULL,
        [created_at]    DATETIME     NOT NULL CONSTRAINT [DF_etl_stage_type_map_created_at] DEFAULT (GETDATE()),
        CONSTRAINT [PK_etl_stage_type_map] PRIMARY KEY CLUSTERED ([id] ASC),
        CONSTRAINT [UQ_etl_stage_type_map_type_raw] UNIQUE ([type_raw])
    );
    PRINT 'OK: dbo.etl_stage_type_map criada';
END
ELSE
    PRINT 'JA EXISTE: dbo.etl_stage_type_map';
GO

;WITH src AS (
    SELECT *
    FROM (VALUES
        -- BANCO
        ('Banco de Dados (ODBC)', 'Banco de Dados ODBC', 'banco', 'ambos', 'Stage ODBC padrão DataStage — leitura ou escrita em banco via ODBC'),
        ('ODBCConnector', 'Banco de Dados ODBC', 'banco', 'ambos', 'Conector ODBC nativo'),
        ('ODBCConnectorPX', 'Banco de Dados ODBC', 'banco', 'ambos', 'Conector ODBC PX (Parallel)'),
        ('SQLServerConnector', 'SQL Server', 'banco', 'ambos', NULL),
        ('OracleConnector', 'Oracle', 'banco', 'ambos', NULL),
        ('DB2Connector', 'IBM DB2', 'banco', 'ambos', NULL),
        ('TeradataConnector', 'Teradata', 'banco', 'ambos', NULL),
        ('JDBCConnector', 'JDBC genérico', 'banco', 'ambos', NULL),
        ('SybaseConnector', 'Sybase', 'banco', 'ambos', NULL),
        ('InformixConnector', 'Informix', 'banco', 'ambos', NULL),
        ('DRSStage', 'Dynamic DBMS (DRS)', 'banco', 'ambos', 'Suporta Oracle, SQL Server, DB2, Informix, Sybase'),
        ('StoredProcedureStage', 'Stored Procedure', 'banco', 'ambos', 'Chamada a stored procedure no banco'),
        ('MS_OLEDB', 'MS OLE DB', 'banco', 'ambos', NULL),

        -- ARQUIVO
        ('Arquivo DataSet (.ds/.dx)', 'DataSet (arquivo DS)', 'arquivo', 'ambos', 'Arquivo DataStage nativo — controle .ds + dados binários'),
        ('DataSetStage', 'DataSet (arquivo DS)', 'arquivo', 'ambos', NULL),
        ('PxDataSet', 'DataSet (arquivo DS)', 'arquivo', 'ambos', 'PX DataSet'),
        ('SequentialFile', 'Arquivo sequencial', 'arquivo', 'ambos', 'Leitura/escrita em arquivos flat'),
        ('FileConnector', 'Arquivo sequencial', 'arquivo', 'ambos', NULL),
        ('PxSequentialFile', 'Arquivo sequencial', 'arquivo', 'ambos', 'PX Sequential File'),
        ('FileSetStage', 'FileSet (arquivo FS)', 'arquivo', 'ambos', 'Particionado — extensão .fs'),
        ('XmlOutputFileStage', 'Arquivo XML', 'arquivo', 'destino', NULL),
        ('XmlInputFileStage', 'Arquivo XML (entrada)', 'arquivo', 'origem', NULL),
        ('UnstructuredDataStage', 'Dados não estruturados', 'arquivo', 'ambos', NULL),
        ('LookupFileSet', 'FileSet de lookup', 'arquivo', 'origem', NULL),

        -- TRANSFORMAÇÃO
        ('PxSort', 'Ordenação', 'transformacao', 'transformacao', 'Ordena registros por colunas especificadas'),
        ('PxSortWithGroupBy', 'Ordenação com grupo', 'transformacao', 'transformacao', NULL),
        ('PxRemDup', 'Remover duplicatas', 'transformacao', 'transformacao', NULL),
        ('PxFunnel', 'Funil (consolidação)', 'transformacao', 'transformacao', 'Combina múltiplos streams em um'),
        ('PxLookup', 'Lookup (enriquecimento)', 'transformacao', 'transformacao', 'Enriquece stream com dados de referência'),
        ('PxAggregator', 'Agregador', 'transformacao', 'transformacao', 'Sum/Count/Min/Max/Avg por grupo'),
        ('PxJoin', 'Join', 'transformacao', 'transformacao', 'Inner/Left/Right/Full Outer Join'),
        ('PxMerge', 'Merge', 'transformacao', 'transformacao', 'Master + update inputs — inputs devem estar ordenados'),
        ('PxFilter', 'Filtro', 'transformacao', 'transformacao', 'Filtra registros por condição'),
        ('PxModify', 'Modificar registro', 'transformacao', 'transformacao', 'Renomeia colunas, converte tipos, trata nulos'),
        ('CTransformerStage', 'Transformação customizada', 'transformacao', 'transformacao', 'Lógica derivada customizada'),
        ('TransformerStage', 'Transformação', 'transformacao', 'transformacao', 'Stage genérico de transformação'),
        ('PxSwitch', 'Desvio condicional', 'transformacao', 'transformacao', 'Distribui registros por valor de campo'),
        ('PxPivot', 'Pivotamento', 'transformacao', 'transformacao', NULL),
        ('PxSurrogateKeyGen', 'Gerador chave surrogate', 'transformacao', 'transformacao', NULL),
        ('PxChangeCapture', 'Captura de alterações', 'transformacao', 'transformacao', NULL),
        ('PxChangeApply', 'Aplicar alterações', 'transformacao', 'transformacao', NULL),
        ('PxDifference', 'Diferença de conjuntos', 'transformacao', 'transformacao', NULL),
        ('PxChecksum', 'Checksum', 'transformacao', 'transformacao', NULL),
        ('PxColumnExport', 'Exportar colunas', 'transformacao', 'transformacao', NULL),
        ('PxColumnImport', 'Importar colunas', 'transformacao', 'transformacao', NULL),
        ('PxNormalize', 'Normalização', 'transformacao', 'transformacao', NULL),
        ('PxDenormalize', 'Desnormalização', 'transformacao', 'transformacao', NULL),
        ('PxMakeSubrec', 'Criar sub-registro', 'transformacao', 'transformacao', NULL),
        ('PxSplitSubrec', 'Dividir sub-registro', 'transformacao', 'transformacao', NULL),
        ('PxRowMerge', 'Merge de linhas', 'transformacao', 'transformacao', NULL),
        ('PxEncode', 'Codificar (gzip)', 'transformacao', 'transformacao', NULL),
        ('PxDecode', 'Decodificar', 'transformacao', 'transformacao', NULL),
        ('PxSharedContainer', 'Container compartilhado', 'transformacao', 'transformacao', NULL),
        ('LocalContainerStage', 'Container local', 'transformacao', 'transformacao', NULL),

        -- DEBUG
        ('PxPeek', 'Peek (debug)', 'debug', 'transformacao', 'Imprime valores no log — uso em desenvolvimento'),
        ('RowGenerator', 'Gerador de linhas (teste)', 'debug', 'origem', 'Gera dados de teste'),
        ('ColumnGenerator', 'Gerador de colunas (teste)', 'debug', 'transformacao', NULL)
    ) AS v(type_raw, type_label, type_category, role_hint, description)
)
MERGE dbo.etl_stage_type_map AS tgt
USING src
ON tgt.type_raw = src.type_raw
WHEN MATCHED THEN UPDATE SET
    type_label = src.type_label,
    type_category = src.type_category,
    role_hint = src.role_hint,
    description = src.description
WHEN NOT MATCHED THEN
    INSERT (type_raw, type_label, type_category, role_hint, description)
    VALUES (src.type_raw, src.type_label, src.type_category, src.role_hint, src.description);
GO

PRINT 'OK: seed dbo.etl_stage_type_map';
GO

/* 2) etl_job_lineage: direction e file_path */
IF COL_LENGTH('dbo.etl_job_lineage', 'file_path') IS NULL
BEGIN
    ALTER TABLE dbo.etl_job_lineage ADD file_path VARCHAR(500) NULL;
    PRINT 'OK: coluna dbo.etl_job_lineage.file_path';
END
GO

IF EXISTS (
    SELECT 1
    FROM sys.columns c
    JOIN sys.types t ON t.user_type_id = c.user_type_id
    WHERE c.object_id = OBJECT_ID('dbo.etl_job_lineage')
      AND c.name = 'direction'
      AND t.name IN ('nvarchar', 'varchar')
      AND c.max_length < 60  -- nvarchar(30) = 60 bytes
)
BEGIN
    ALTER TABLE dbo.etl_job_lineage ALTER COLUMN direction NVARCHAR(30) NOT NULL;
    PRINT 'OK: dbo.etl_job_lineage.direction NVARCHAR(30)';
END
GO

/* 3) sp_etl_job_lineage_upsert */
CREATE OR ALTER PROCEDURE [dbo].[sp_etl_job_lineage_upsert]
(
    @pipeline_name NVARCHAR(200),
    @job_name      NVARCHAR(200),
    @direction     NVARCHAR(30), -- origem | destino | transformacao
    @object_type   NVARCHAR(20),
    @object_name   NVARCHAR(500),

    @stage_name        VARCHAR(200)   = NULL,
    @stage_type_raw    VARCHAR(100)   = NULL,
    @database_name     VARCHAR(200)   = NULL,
    @sql_expression    NVARCHAR(MAX)  = NULL,
    @file_path         VARCHAR(500)   = NULL,
    @dsx_source_file   VARCHAR(500)   = NULL,
    @extracted_at      DATETIME2      = NULL,
    @extraction_method VARCHAR(20)    = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        IF @direction NOT IN ('origem','destino','transformacao')
            RAISERROR ('direction inválido: %s', 16, 1, @direction);

        IF EXISTS (
            SELECT 1
            FROM dbo.etl_job_lineage
            WHERE pipeline_name = @pipeline_name
              AND job_name      = @job_name
              AND direction     = @direction
              AND object_name   = @object_name
        )
        BEGIN
            UPDATE dbo.etl_job_lineage
            SET
                object_type = @object_type,
                stage_name = COALESCE(@stage_name, stage_name),
                stage_type_raw = COALESCE(@stage_type_raw, stage_type_raw),
                database_name = COALESCE(@database_name, database_name),
                sql_expression = COALESCE(@sql_expression, sql_expression),
                file_path = COALESCE(@file_path, file_path),
                dsx_source_file = COALESCE(@dsx_source_file, dsx_source_file),
                extracted_at = COALESCE(@extracted_at, extracted_at),
                extraction_method = COALESCE(@extraction_method, extraction_method),
                updated_at  = SYSDATETIME()
            WHERE pipeline_name = @pipeline_name
              AND job_name      = @job_name
              AND direction     = @direction
              AND object_name   = @object_name;
        END
        ELSE
        BEGIN
            INSERT INTO dbo.etl_job_lineage
            (
                pipeline_name, job_name, direction, object_type, object_name,
                stage_name, stage_type_raw, database_name, sql_expression, file_path,
                dsx_source_file, extracted_at, extraction_method,
                created_at, updated_at
            )
            VALUES
            (
                @pipeline_name, @job_name, @direction, @object_type, @object_name,
                @stage_name, @stage_type_raw, @database_name, @sql_expression, @file_path,
                @dsx_source_file, @extracted_at, @extraction_method,
                SYSDATETIME(), SYSDATETIME()
            );
        END
    END TRY
    BEGIN CATCH
        DECLARE @ErrorMessage  NVARCHAR(4000) = ERROR_MESSAGE();
        DECLARE @ErrorSeverity INT            = ERROR_SEVERITY();
        RAISERROR (@ErrorMessage, @ErrorSeverity, 1);
    END CATCH
END
GO

PRINT 'OK: sp_etl_job_lineage_upsert (Fase 2)';
GO

