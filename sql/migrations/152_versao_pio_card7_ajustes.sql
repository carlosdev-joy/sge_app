-- 152_versao_pio_card7_ajustes.sql
-- Idempotente — seguro para rodar mais de uma vez.
-- Versão 2.6.12 (sobre a 2.6.11 da migration 151). Só registra a versão e sincroniza
-- app_version/app_release_name: NÃO toca nas tabelas do PIO (AGG/FAT/CTL_ORQ_CARD0N_*
-- são publicadas pelo Fabric e a aplicação só as lê).
-- ⚠️ Numeração: o `develop` também usa 140+. Ao promover o develop, reconciliar — as
-- migrations têm NOMES distintos, e o migrate.py controla por nome.
SET NOCOUNT ON;

DECLARE @versao NVARCHAR(20)  = N'2.6.12';
DECLARE @titulo NVARCHAR(200) = N'Ajustes do Card 7 e do Workflow';
IF OBJECT_ID('dbo.etl_versao_ferramenta', 'U') IS NULL
    PRINT '[--] etl_versao_ferramenta ausente (migration 003) — versão não registrada';
ELSE IF EXISTS (SELECT 1 FROM dbo.etl_versao_ferramenta WHERE titulo = @titulo OR versao = @versao)
    PRINT '[SKIP] versão desta entrega já registrada';
ELSE
BEGIN
    INSERT INTO dbo.etl_versao_ferramenta (versao, titulo, descricao_md, criado_por)
    VALUES (@versao, @titulo, N'## Ajustes do Card 7 e do Workflow

- Card 7: os sub-cards verde (Devolução Realizada) e laranja (Devolução em Andamento) deixam de mostrar o botão Gerenciar Devolução nos registros; ele continua no vermelho (Pendente).
- Na tela de gerenciamento de devolução, o botão Programar Devolução passa a se chamar Salvar Dados Bancários.
- O Workflow da tela principal abre por padrão, já mostrando os 8 cards.

Roteiro: docs/release-notes/pio-card7-ajustes.md.', 'deploy');

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
