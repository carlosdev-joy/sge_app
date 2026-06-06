-- =============================================================================
-- export-prod-schema.sql
-- =============================================================================
-- Execute este script no SSMS conectado ao banco de PRODUÇÃO.
-- Ele gera o DDL completo (tabelas, índices, procedures, views) do schema dbo.
--
-- Como usar:
--   1. Abra o SSMS e conecte no banco de produção
--   2. Abra este script e execute (F5)
--   3. Clique com botão direito no resultado → "Save Results As..." → schema_prod.sql
--   4. Copie o arquivo schema_prod.sql para a VPS de dev
-- =============================================================================

SET NOCOUNT ON;
DECLARE @sql NVARCHAR(MAX) = '';
DECLARE @crlf NCHAR(2) = CHAR(13) + CHAR(10);

-- =============================================================================
-- CABEÇALHO
-- =============================================================================
PRINT '-- ============================================================';
PRINT '-- Schema exportado de: ' + @@SERVERNAME + ' / ' + DB_NAME();
PRINT '-- Data: ' + CONVERT(VARCHAR, GETDATE(), 120);
PRINT '-- ============================================================';
PRINT 'USE [orquestra_dev];';
PRINT 'GO';
PRINT '';

-- =============================================================================
-- 1. TABELAS
-- =============================================================================
PRINT '-- ------------------------------------------------------------';
PRINT '-- TABELAS';
PRINT '-- ------------------------------------------------------------';

DECLARE @tname NVARCHAR(128);
DECLARE cur_tables CURSOR FOR
    SELECT t.name
    FROM sys.tables t
    WHERE t.schema_id = SCHEMA_ID('dbo')
      AND t.is_ms_shipped = 0
    ORDER BY t.name;

OPEN cur_tables;
FETCH NEXT FROM cur_tables INTO @tname;

WHILE @@FETCH_STATUS = 0
BEGIN
    SET @sql = 'IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = ''' + @tname + ''' AND schema_id = SCHEMA_ID(''dbo''))' + @crlf;
    SET @sql += 'CREATE TABLE [dbo].[' + @tname + '] (' + @crlf;

    -- Colunas
    DECLARE @col_sql NVARCHAR(MAX) = '';
    SELECT @col_sql += '    ['  + c.name + '] '
        + tp.name
        + CASE
            WHEN tp.name IN ('varchar','nvarchar','char','nchar')
                THEN '(' + CASE WHEN c.max_length = -1 THEN 'MAX'
                                WHEN tp.name IN ('nvarchar','nchar') THEN CAST(c.max_length/2 AS VARCHAR)
                                ELSE CAST(c.max_length AS VARCHAR) END + ')'
            WHEN tp.name IN ('decimal','numeric')
                THEN '(' + CAST(c.precision AS VARCHAR) + ',' + CAST(c.scale AS VARCHAR) + ')'
            ELSE ''
          END
        + CASE WHEN c.is_identity = 1 THEN ' IDENTITY(' +
                CAST(IDENT_SEED('[dbo].[' + @tname + ']') AS VARCHAR) + ',' +
                CAST(IDENT_INCR('[dbo].[' + @tname + ']') AS VARCHAR) + ')' ELSE '' END
        + CASE WHEN c.is_nullable = 0 THEN ' NOT NULL' ELSE ' NULL' END
        + CASE WHEN c.default_object_id <> 0
               THEN ' DEFAULT ' + OBJECT_DEFINITION(c.default_object_id)
               ELSE '' END
        + ',' + @crlf
    FROM sys.columns c
    JOIN sys.types tp ON tp.user_type_id = c.user_type_id
    WHERE c.object_id = OBJECT_ID('[dbo].[' + @tname + ']')
    ORDER BY c.column_id;

    -- Remove última vírgula antes do fechamento
    SET @col_sql = LEFT(@col_sql, LEN(@col_sql) - 3);

    -- Primary key
    DECLARE @pk NVARCHAR(MAX) = '';
    SELECT @pk = '    CONSTRAINT [' + i.name + '] PRIMARY KEY ' +
        CASE WHEN i.type = 1 THEN 'CLUSTERED' ELSE 'NONCLUSTERED' END + ' (' +
        STUFF((
            SELECT ', [' + c2.name + ']' + CASE WHEN ic.is_descending_key = 1 THEN ' DESC' ELSE ' ASC' END
            FROM sys.index_columns ic
            JOIN sys.columns c2 ON c2.object_id = ic.object_id AND c2.column_id = ic.column_id
            WHERE ic.object_id = i.object_id AND ic.index_id = i.index_id
            ORDER BY ic.key_ordinal
            FOR XML PATH('')
        ), 1, 2, '') + ')'
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID('[dbo].[' + @tname + ']')
      AND i.is_primary_key = 1;

    IF @pk <> ''
        SET @col_sql += ',' + @crlf + @pk;

    SET @sql += @col_sql + @crlf + ');' + @crlf + 'GO' + @crlf;

    PRINT @sql;

    -- Índices não-PK
    SELECT
        'IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = ''' + i.name + ''' AND object_id = OBJECT_ID(''[dbo].[' + @tname + ']''))' + @crlf +
        'CREATE ' + CASE WHEN i.is_unique = 1 THEN 'UNIQUE ' ELSE '' END +
        'NONCLUSTERED INDEX [' + i.name + '] ON [dbo].[' + @tname + '] (' +
        STUFF((
            SELECT ', [' + c2.name + ']' + CASE WHEN ic.is_descending_key = 1 THEN ' DESC' ELSE ' ASC' END
            FROM sys.index_columns ic
            JOIN sys.columns c2 ON c2.object_id = ic.object_id AND c2.column_id = ic.column_id
            WHERE ic.object_id = i.object_id AND ic.index_id = i.index_id AND ic.is_included_column = 0
            ORDER BY ic.key_ordinal
            FOR XML PATH('')
        ), 1, 2, '') + ');' + @crlf + 'GO' + @crlf
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID('[dbo].[' + @tname + ']')
      AND i.is_primary_key = 0
      AND i.is_unique_constraint = 0
      AND i.type > 0
      AND i.name IS NOT NULL;

    FETCH NEXT FROM cur_tables INTO @tname;
END;

CLOSE cur_tables;
DEALLOCATE cur_tables;

-- =============================================================================
-- 2. STORED PROCEDURES
-- =============================================================================
PRINT '';
PRINT '-- ------------------------------------------------------------';
PRINT '-- STORED PROCEDURES';
PRINT '-- ------------------------------------------------------------';

DECLARE @pname NVARCHAR(128);
DECLARE cur_procs CURSOR FOR
    SELECT o.name
    FROM sys.objects o
    WHERE o.type = 'P'
      AND o.schema_id = SCHEMA_ID('dbo')
      AND o.is_ms_shipped = 0
    ORDER BY o.name;

OPEN cur_procs;
FETCH NEXT FROM cur_procs INTO @pname;

WHILE @@FETCH_STATUS = 0
BEGIN
    PRINT 'IF OBJECT_ID(''[dbo].[' + @pname + ']'', ''P'') IS NOT NULL DROP PROCEDURE [dbo].[' + @pname + '];';
    PRINT 'GO';
    PRINT OBJECT_DEFINITION(OBJECT_ID('[dbo].[' + @pname + ']'));
    PRINT 'GO';
    PRINT '';
    FETCH NEXT FROM cur_procs INTO @pname;
END;

CLOSE cur_procs;
DEALLOCATE cur_procs;

-- =============================================================================
-- 3. VIEWS
-- =============================================================================
PRINT '';
PRINT '-- ------------------------------------------------------------';
PRINT '-- VIEWS';
PRINT '-- ------------------------------------------------------------';

DECLARE @vname NVARCHAR(128);
DECLARE cur_views CURSOR FOR
    SELECT o.name
    FROM sys.objects o
    WHERE o.type = 'V'
      AND o.schema_id = SCHEMA_ID('dbo')
      AND o.is_ms_shipped = 0
    ORDER BY o.name;

OPEN cur_views;
FETCH NEXT FROM cur_views INTO @vname;

WHILE @@FETCH_STATUS = 0
BEGIN
    PRINT 'IF OBJECT_ID(''[dbo].[' + @vname + ']'', ''V'') IS NOT NULL DROP VIEW [dbo].[' + @vname + '];';
    PRINT 'GO';
    PRINT OBJECT_DEFINITION(OBJECT_ID('[dbo].[' + @vname + ']'));
    PRINT 'GO';
    PRINT '';
    FETCH NEXT FROM cur_views INTO @vname;
END;

CLOSE cur_views;
DEALLOCATE cur_views;

-- =============================================================================
-- 4. FOREIGN KEYS
-- =============================================================================
PRINT '';
PRINT '-- ------------------------------------------------------------';
PRINT '-- FOREIGN KEYS';
PRINT '-- ------------------------------------------------------------';

SELECT
    'IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = ''' + fk.name + ''')' + CHAR(13)+CHAR(10) +
    'ALTER TABLE [dbo].[' + tp.name + '] ADD CONSTRAINT [' + fk.name + '] FOREIGN KEY ([' +
    cp.name + ']) REFERENCES [dbo].[' + tr.name + '] ([' + cr.name + ']);' + CHAR(13)+CHAR(10) + 'GO' + CHAR(13)+CHAR(10)
FROM sys.foreign_keys fk
JOIN sys.tables tp ON tp.object_id = fk.parent_object_id
JOIN sys.tables tr ON tr.object_id = fk.referenced_object_id
JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
JOIN sys.columns cp ON cp.object_id = fk.parent_object_id AND cp.column_id = fkc.parent_column_id
JOIN sys.columns cr ON cr.object_id = fk.referenced_object_id AND cr.column_id = fkc.referenced_column_id
WHERE tp.schema_id = SCHEMA_ID('dbo')
ORDER BY tp.name, fk.name;

PRINT '';
PRINT '-- FIM DO SCHEMA';
