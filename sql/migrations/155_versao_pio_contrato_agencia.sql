-- 155_versao_pio_contrato_agencia.sql
-- Idempotente — seguro para rodar mais de uma vez.
-- Versão 2.6.14 (sobre a 2.6.13 da migration 154). Só registra a versão e sincroniza
-- app_version/app_release_name: NÃO toca nas tabelas do PIO (AGG/FAT/CTL_ORQ_CARD0N_*
-- são publicadas pela carga no DMDB41 e a aplicação só as lê).
-- ⚠️ Numeração: o `develop` também usa 140+. Ao promover o develop, reconciliar — as
-- migrations têm NOMES distintos, e o migrate.py controla por nome.
SET NOCOUNT ON;

DECLARE @versao NVARCHAR(20)  = N'2.6.14';
DECLARE @titulo NVARCHAR(200) = N'PIO: Cards 1 a 6 no novo contrato de leitura';
IF OBJECT_ID('dbo.etl_versao_ferramenta', 'U') IS NULL
    PRINT '[--] etl_versao_ferramenta ausente (migration 003) — versão não registrada';
ELSE IF EXISTS (SELECT 1 FROM dbo.etl_versao_ferramenta WHERE titulo = @titulo OR versao = @versao)
    PRINT '[SKIP] versão desta entrega já registrada';
ELSE
BEGIN
    INSERT INTO dbo.etl_versao_ferramenta (versao, titulo, descricao_md, criado_por)
    VALUES (@versao, @titulo, N'## PIO: Cards 1 a 6 no novo contrato de leitura

- Cards 1, 2 e 3: o endereço exibido passa a ser o da AGÊNCIA (nome, endereço, cidade/UF e CEP). A região da lista vira Região da agência. O endereço do segurado deixou de vir na extração e não é mais lido.
- Card 4: o código da situação do contrato aparece ao lado da descrição recebida; todas as situações são exibidas (0, 1, 9, E).
- Card 6: a data de venda é rotulada como Data de Venda (quitação), pois a origem passou a derivá-la da quitação.
- Cards 4, 5 e 6: o Resumo do seguro mostra nome e endereço da agência.
- Fotos anteriores à nova extração seguem abrindo; os campos novos aparecem como não informados.

Roteiro: docs/release-notes/pio-contrato-agencia.md.', 'deploy');

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
