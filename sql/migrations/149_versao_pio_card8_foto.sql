-- 149_versao_pio_card8_foto.sql
-- Idempotente — seguro para rodar mais de uma vez.
-- Versão 2.6.9 (sobre a 2.6.8 da migration 148). Só registra a versão e sincroniza
-- app_version/app_release_name: NÃO toca nas tabelas do PIO (AGG/FAT/CTL_ORQ_CARD08_*
-- são publicadas pelo Fabric e a aplicação só as lê).
-- ⚠️ Numeração: o `develop` também usa 140+. Ao promover o develop, reconciliar — as
-- migrations têm NOMES distintos, e o migrate.py controla por nome.
SET NOCOUNT ON;

DECLARE @versao NVARCHAR(20)  = N'2.6.9';
DECLARE @titulo NVARCHAR(200) = N'Card 8 do PIO lê a foto diária';
IF OBJECT_ID('dbo.etl_versao_ferramenta', 'U') IS NULL
    PRINT '[--] etl_versao_ferramenta ausente (migration 003) — versão não registrada';
ELSE IF EXISTS (SELECT 1 FROM dbo.etl_versao_ferramenta WHERE titulo = @titulo OR versao = @versao)
    PRINT '[SKIP] versão desta entrega já registrada';
ELSE
BEGIN
    INSERT INTO dbo.etl_versao_ferramenta (versao, titulo, descricao_md, criado_por)
    VALUES (@versao, @titulo, N'## Card 8 do PIO lê a foto diária

- O card "Sensibilizações" mostra o valor sensibilizado em destaque e, abaixo, a quantidade de identificações, lidos da foto diária publicada pelo Fabric.
- A lista mostra o último movimento de cada identificação, sem a contagem em dias, com o botão "Sensibilizar" (habilitado quando a situação da proposta difere do último movimento encaminhado).
- O Resumo do Seguro mostra valor do prêmio, movimento encaminhado e data de envio do movimento, e o Workflow traz os dois estados reais (movimento e proposta).
- Os demais cards e a busca por proposta não mudam.

Roteiro: docs/release-notes/pio-card8-foto.md.', 'deploy');

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
