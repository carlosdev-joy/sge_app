-- 154_versao_agente_terminal.sql
-- Idempotente — seguro para rodar mais de uma vez.
-- Versão 2.6.13 (sobre a 2.6.12 da migration 152). Só registra a versão e sincroniza
-- app_version/app_release_name. A tabela do Terminal vem na 153_agente_terminal.
-- ⚠️ Numeração: na `develop` o mesmo Terminal está em 197 (auditoria) + 198–201 (versões).
-- Ao promover o develop, reconciliar — as migrations têm NOMES distintos e o migrate.py
-- controla por nome (a 153 e a 197 criam a MESMA tabela, ambas com guarda IF OBJECT_ID).
SET NOCOUNT ON;

DECLARE @versao NVARCHAR(20)  = N'2.6.13';
DECLARE @titulo NVARCHAR(200) = N'Agente Terminal em /agentes';
IF OBJECT_ID('dbo.etl_versao_ferramenta', 'U') IS NULL
    PRINT '[--] etl_versao_ferramenta ausente (migration 003) — versão não registrada';
ELSE IF EXISTS (SELECT 1 FROM dbo.etl_versao_ferramenta WHERE titulo = @titulo OR versao = @versao)
    PRINT '[SKIP] versão desta entrega já registrada';
ELSE
BEGIN
    INSERT INTO dbo.etl_versao_ferramenta (versao, titulo, descricao_md, criado_por)
    VALUES (@versao, @titulo, N'## Agente Terminal em /agentes

- Novo agente **Terminal** dentro de /agentes: chat em formato de terminal que consulta, em linguagem livre, o DataStage e o servidor do Orquestra/Airflow com os acessos do Orquestra.
- Leitura livre; comando que altera algo só roda depois de confirmação explícita no card (comando inteiro visível, uso único, prazo de 2 minutos).
- Comandos de segredo, sudo, desligar servidor e parar containers do Orquestra são bloqueados.
- Herda o RBAC: recursos agente_terminal (uso) e agente_terminal_escrita (escrita); nasce DESLIGADO.
- Admin › IA › Agentes › Terminal: bancos liberados (só SELECT) e auditoria completa, com retenção de 180 dias.

Roteiro: docs/release-notes/agente-terminal-main.md.', 'deploy');

    -- O mesmo que o "Nova Versão" da aba faz.
    IF OBJECT_ID('dbo.etl_app_config', 'U') IS NOT NULL
    BEGIN
        UPDATE dbo.etl_app_config SET config_value = @versao WHERE config_key = 'app_version';
        IF @@ROWCOUNT = 0
            INSERT INTO dbo.etl_app_config (config_key, config_value) VALUES ('app_version', @versao);
        UPDATE dbo.etl_app_config SET config_value = @titulo WHERE config_key = 'app_release_name';
        IF @@ROWCOUNT = 0
            INSERT INTO dbo.etl_app_config (config_key, config_value) VALUES ('app_release_name', @titulo);
    END

    PRINT CONCAT('[OK] versão ', @versao, ' registrada: ', @titulo);
END

GO
