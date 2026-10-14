-- Auditoria por tentativa concluída; nenhum transporte/cutover ativado.
IF OBJECT_ID('dbo.etl_alert_attempt','U') IS NOT NULL
BEGIN
    IF COL_LENGTH('dbo.etl_alert_attempt','replay_actor') IS NULL
        ALTER TABLE dbo.etl_alert_attempt ADD replay_actor NVARCHAR(100) NULL;
    IF COL_LENGTH('dbo.etl_alert_attempt','replay_reason') IS NULL
        ALTER TABLE dbo.etl_alert_attempt ADD replay_reason NVARCHAR(500) NULL;
    IF COL_LENGTH('dbo.etl_alert_attempt','replay_at') IS NULL
        ALTER TABLE dbo.etl_alert_attempt ADD replay_at DATETIME2(6) NULL;
END
GO

IF OBJECT_ID('dbo.etl_backlog','U') IS NOT NULL
AND NOT EXISTS (SELECT 1 FROM dbo.etl_backlog WHERE titulo=N'Alertas: validar transporte de teste e cutover sem duplicar legados')
    INSERT dbo.etl_backlog (titulo,descricao,tipo,area,prioridade,status,tags,criado_por)
    VALUES (N'Alertas: validar transporte de teste e cutover sem duplicar legados',
    N'EOC-F10 technical_delivered_activation_pending: adapters internos e reenvio dry-run auditado. Sem destino real de teste autorizado; nenhum envio real validado. Antes de ativar: certificar autoridade F9/Warning/geração Clear, persistir transporte sob claim/fence e impedir emissor legado para o mesmo run/política em cutover transacional. Runs legados preservados, Unknown sem retry cego; aceitação não confirma recebimento. Não liberar capabilities ou remover CHECK dry_run por esta entrega. Credenciais/destinos apenas RAM; fixtures com limpeza.',
    N'spike',N'backend',N'P1',N'refinado',N'EOC-F10,alertas,cutover,activation-gate',N'eoc-f10');
GO
