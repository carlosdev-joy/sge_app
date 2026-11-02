-- 150_versao_pio_fluxo_resumo.sql
-- Idempotente — seguro para rodar mais de uma vez.
-- Versão 2.6.10 (sobre a 2.6.9 da migration 149). Só registra a versão e sincroniza
-- app_version/app_release_name: NÃO toca nas tabelas do PIO (AGG/FAT/CTL_ORQ_CARD0N_*
-- são publicadas pelo Fabric e a aplicação só as lê).
-- ⚠️ Numeração: o `develop` também usa 140+. Ao promover o develop, reconciliar — as
-- migrations têm NOMES distintos, e o migrate.py controla por nome.
SET NOCOUNT ON;

DECLARE @versao NVARCHAR(20)  = N'2.6.10';
DECLARE @titulo NVARCHAR(200) = N'Resumo do Seguro mostra o fluxo da proposta';
IF OBJECT_ID('dbo.etl_versao_ferramenta', 'U') IS NULL
    PRINT '[--] etl_versao_ferramenta ausente (migration 003) — versão não registrada';
ELSE IF EXISTS (SELECT 1 FROM dbo.etl_versao_ferramenta WHERE titulo = @titulo OR versao = @versao)
    PRINT '[SKIP] versão desta entrega já registrada';
ELSE
BEGIN
    INSERT INTO dbo.etl_versao_ferramenta (versao, titulo, descricao_md, criado_por)
    VALUES (@versao, @titulo, N'## Resumo do Seguro mostra o fluxo da proposta

- A linha do tempo do Resumo do Seguro mostra todas as etapas até a do card em que a proposta está: as anteriores como concluídas (verde, com check) e a atual em destaque.
- Exemplo: no card Em Análise aparecem Pendente de Assinatura, Pendente de Pagamento e Assinada e Paga concluídas, e Em Análise como etapa atual.
- A etapa atual mostra o estado real (por exemplo Cancelada, Devolução em Andamento, último movimento da sensibilização). A rejeitada não passa por Emitida; a devolução vem depois da rejeição.
- No celular o fluxo longo abre na etapa atual e rola na horizontal.

Roteiro: docs/release-notes/pio-fluxo-resumo.md.', 'deploy');

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
