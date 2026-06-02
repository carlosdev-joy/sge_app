USE [DMDB41];
GO

/* ORQUESTRA — Lineage Catálogo (Fase 2) v1.0 — SEED (MERGE/UPSERT) */

IF OBJECT_ID('dbo.etl_stage_type_map', 'U') IS NULL
BEGIN
    RAISERROR('Tabela dbo.etl_stage_type_map não existe. Execute 001_create_table_etl_stage_type_map.sql antes.',16,1);
    RETURN;
END
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

