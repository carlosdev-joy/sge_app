-- F7D: hash versionado sem reescrever snapshots ou operações anteriores.
SET NOCOUNT ON;
IF OBJECT_ID('dbo.etl_workspace_publicacao','U') IS NULL THROW 50159,'Aplique migration 144 antes da 159.',1;
GO
CREATE OR ALTER PROCEDURE dbo.sp_workspace_active_hash @name NVARCHAR(200), @include_lineage BIT=NULL AS
BEGIN
 SET NOCOUNT ON;
 -- Operação pendente tem precedência, inclusive erro com gate mantido.
 IF @include_lineage IS NULL
 BEGIN
  SELECT @include_lineage=CASE WHEN JSON_VALUE(v.definition_json,'$.metadata.workspaceLineageVersion')='1' THEN 1 ELSE 0 END
  FROM dbo.etl_workspace_pipeline p
  LEFT JOIN dbo.etl_workspace_publicacao o ON o.operation_id=p.pending_operation_id
  LEFT JOIN dbo.etl_workspace_versao v ON v.version_id=CASE WHEN p.pending_operation_id IS NOT NULL THEN o.version_id ELSE p.version_id END
  WHERE p.pipeline_name=@name;
  SET @include_lineage=COALESCE(@include_lineage,0);
 END;
 -- Somente hash sai do SQL; cifras nunca são transportadas ao .NET.
 DECLARE @payload NVARCHAR(MAX)=N'',@table sysname,@cols NVARCHAR(MAX),@query NVARCHAR(MAX),@rows NVARCHAR(MAX),@order NVARCHAR(MAX);
 IF NOT EXISTS(SELECT 1 FROM dbo.etl_pipeline WHERE pipeline_name=@name) BEGIN SELECT CAST(NULL AS CHAR(64)) AS active_hash; RETURN; END;
 DECLARE tables CURSOR LOCAL FAST_FORWARD FOR SELECT name FROM (VALUES
 ('etl_pipeline'),('etl_pipeline_job'),('etl_pipeline_param'),('etl_pipeline_job_param'),('etl_valida_arquivo_no'),('etl_valida_arquivo_config'),('etl_pipeline_dependencia'),('etl_pipeline_owner'),('etl_job_lineage')) t(name) WHERE name<>'etl_job_lineage' OR @include_lineage=1 ORDER BY name;
 OPEN tables; FETCH NEXT FROM tables INTO @table;
 WHILE @@FETCH_STATUS=0
 BEGIN
  IF OBJECT_ID('dbo.'+@table,'U') IS NOT NULL
  BEGIN
   SELECT @cols=STRING_AGG(CAST(QUOTENAME(name) AS NVARCHAR(MAX)),',') WITHIN GROUP(ORDER BY column_id)
    FROM sys.columns WHERE object_id=OBJECT_ID('dbo.'+@table) AND NOT(@table='etl_job_lineage' AND (is_identity=1 OR is_computed=1 OR name='extracted_at')) AND name NOT IN('dag_criada','last_execution','updated_at','created_at','atualizado_em','criado_em','dag_config_pendente_em');
   SET @order=CASE @table WHEN 'etl_pipeline_job' THEN '[job_name]' WHEN 'etl_pipeline_param' THEN '[param_name]' WHEN 'etl_pipeline_job_param' THEN '[job_name],[param_name]' WHEN 'etl_valida_arquivo_no' THEN '[task_id]' WHEN 'etl_valida_arquivo_config' THEN '[task_id],[entrada_id]' WHEN 'etl_pipeline_dependencia' THEN '[depende_de]' ELSE '[pipeline_name]' END;
   SET @query=N'SELECT @rows=(SELECT '+@cols+' FROM dbo.'+QUOTENAME(@table)+' WHERE pipeline_name=@name ORDER BY '+@order+' FOR JSON PATH,INCLUDE_NULL_VALUES)';
   IF @table='etl_job_lineage'
   BEGIN
    -- JSON completo + collation binária preserva duplicatas e ordena MAX sem truncar.
    SET @query=N'DECLARE @lineage_rows TABLE(row_json NVARCHAR(MAX)); INSERT @lineage_rows SELECT (SELECT '+@cols+' FOR JSON PATH,INCLUDE_NULL_VALUES,WITHOUT_ARRAY_WRAPPER) FROM dbo.'+QUOTENAME(@table)+' s WHERE s.pipeline_name=@name; SELECT @rows=N''[''+COALESCE(STUFF((SELECT N'',''+row_json FROM @lineage_rows ORDER BY row_json COLLATE Latin1_General_100_BIN2 FOR XML PATH(''''),TYPE).value(''.'', ''NVARCHAR(MAX)''),1,1,N''''),N'''')+N'']''';
   END;
   EXEC sp_executesql @query,N'@name NVARCHAR(200),@rows NVARCHAR(MAX) OUTPUT',@name,@rows OUTPUT;
   SET @payload=@payload+@table+CHAR(10)+COALESCE(@rows,N'[]')+CHAR(10);
  END;
  FETCH NEXT FROM tables INTO @table;
 END;
 CLOSE tables; DEALLOCATE tables;
 SELECT LOWER(CONVERT(CHAR(64),HASHBYTES('SHA2_256',@payload),2)) AS active_hash;
END;
GO
