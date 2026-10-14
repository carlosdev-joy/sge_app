-- Transporte operacional de TESTE opt-in. Fixtures continuam dry_run=1;
-- produtor captura modo na matrícula original. Sem backfill/ativação.
DECLARE @constraint SYSNAME;
SELECT @constraint=name FROM sys.check_constraints
WHERE parent_object_id=OBJECT_ID('dbo.etl_alert_event')
AND parent_column_id=COLUMNPROPERTY(OBJECT_ID('dbo.etl_alert_event'),'dry_run','ColumnId');
IF @constraint IS NOT NULL
BEGIN
    DECLARE @sql NVARCHAR(MAX)=N'ALTER TABLE dbo.etl_alert_event DROP CONSTRAINT '+QUOTENAME(@constraint);
    EXEC sys.sp_executesql @sql;
END
GO
