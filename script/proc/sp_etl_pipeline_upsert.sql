USE [DMDB41]
GO

/****** Object:  StoredProcedure [dbo].[sp_etl_pipeline_upsert]    Script Date: 30/05/2026 00:58:37 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE PROCEDURE [dbo].[sp_etl_pipeline_upsert]
(
    @pipeline_name    NVARCHAR(200),
    @scheduled_time   TIME(0),
    @active           BIT           = 1,
    @envia_msg_inicio BIT           = 1,
    @envia_msg_fim    BIT           = 1,
    @envia_msg_erro   BIT           = 1,
    @dag_criada       BIT           = 0,
    @project_name     NVARCHAR(50),
    @domain           NVARCHAR(100),
    @tags             NVARCHAR(500) = ''
)
AS
BEGIN
    SET NOCOUNT ON;

    IF EXISTS (
        SELECT 1 FROM dbo.etl_pipeline WHERE pipeline_name = @pipeline_name
    )
    BEGIN
        UPDATE dbo.etl_pipeline
        SET
            scheduled_time   = @scheduled_time,
            active           = @active,
            ENVIA_MSG_INICIO = @envia_msg_inicio,
            ENVIA_MSG_FIM    = @envia_msg_fim,
            ENVIA_MSG_ERRO   = @envia_msg_erro,
            DAG_CRIADA       = @dag_criada,
            project_name     = @project_name,
            domain           = @domain,
            tags             = @tags,
            updated_at       = SYSDATETIME()
        WHERE pipeline_name = @pipeline_name
    END
    ELSE
    BEGIN
        INSERT INTO dbo.etl_pipeline (
            pipeline_name, scheduled_time, active,
            last_execution, created_at, updated_at,
            ENVIA_MSG_INICIO, ENVIA_MSG_FIM, ENVIA_MSG_ERRO, DAG_CRIADA,
            project_name, domain, tags
        )
        VALUES (
            @pipeline_name, @scheduled_time, @active,
            NULL, SYSDATETIME(), SYSDATETIME(),
            @envia_msg_inicio, @envia_msg_fim, @envia_msg_erro, @dag_criada,
            @project_name, @domain, @tags
        )
    END
END
GO


