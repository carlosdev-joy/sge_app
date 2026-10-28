-- 140_versao_pio_card1_foto.sql
-- Idempotente — seguro para rodar mais de uma vez.
-- Correção/ajuste de entrega: versão 2.6.1 (decisão do usuário em 28/10/2026), sobre a
-- 2.6.0 da migration 138. Só registra a versão e sincroniza app_version/app_release_name:
-- NÃO toca nas tabelas do PIO (AGG/FAT/CTL_ORQ_CARD01_* já existem em produção e a
-- aplicação só as lê).
-- ⚠️ Numeração: o `develop` também usa 140+ (workspace de pipeline etc.). Ao promover o
-- develop, reconciliar a numeração — as duas migrations têm NOMES distintos, e o
-- migrate.py controla por nome.
SET NOCOUNT ON;

DECLARE @versao NVARCHAR(20)  = N'2.6.1';
DECLARE @titulo NVARCHAR(200) = N'Card 1 do PIO lê a foto diária';

IF OBJECT_ID('dbo.etl_versao_ferramenta', 'U') IS NULL
    PRINT '[--] etl_versao_ferramenta ausente (migration 003) — versão não registrada';
ELSE IF EXISTS (SELECT 1 FROM dbo.etl_versao_ferramenta WHERE titulo = @titulo OR versao = @versao)
    PRINT '[SKIP] versão desta entrega já registrada';
ELSE
BEGIN
    INSERT INTO dbo.etl_versao_ferramenta (versao, titulo, descricao_md, criado_por)
    VALUES (@versao, @titulo, N'## Card 1 do PIO lê a foto diária

- O card "Pendentes de Assinatura" mostra o prêmio em destaque e, abaixo, a quantidade de contratos, lidos da foto diária publicada pelo Fabric.
- A lista ao clicar no card, o Resumo do Seguro e o botão Enviar usam a mesma foto (mesma data e lote); a tela informa a data da foto e avisa quando ela não é de hoje.
- Enviar mostra "Contato não informado" e não habilita destino ausente.
- No Resumo do Seguro do Card 1, "Usuário" e o rodapé saem; o Histórico mostra o estado da foto.
- Os outros sete cards e a busca por proposta não mudam.

Roteiro: docs/release-notes/pio-card1-foto.md.', 'deploy');

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
