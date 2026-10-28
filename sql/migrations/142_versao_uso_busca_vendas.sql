-- 142_versao_uso_busca_vendas.sql
-- Idempotente — seguro para rodar mais de uma vez.
-- Versão 2.6.2 (decisão de numeração: o `develop` já usa 2.7.0+; o registro cuja versão
-- ou título já exista é ignorado, então um 2.7.0 aqui faria a promoção do develop pular
-- a própria versão — reconciliar ao promover). Só registra a versão e sincroniza
-- app_version/app_release_name: as tabelas são da migration 141.
SET NOCOUNT ON;

DECLARE @versao NVARCHAR(20)  = N'2.6.2';
DECLARE @titulo NVARCHAR(200) = N'Uso do módulo Busca & Vendas';

IF OBJECT_ID('dbo.etl_versao_ferramenta', 'U') IS NULL
    PRINT '[--] etl_versao_ferramenta ausente (migration 003) — versão não registrada';
ELSE IF EXISTS (SELECT 1 FROM dbo.etl_versao_ferramenta WHERE titulo = @titulo OR versao = @versao)
    PRINT '[SKIP] versão desta entrega já registrada';
ELSE
BEGIN
    INSERT INTO dbo.etl_versao_ferramenta (versao, titulo, descricao_md, criado_por)
    VALUES (@versao, @titulo, N'## Uso do módulo Busca & Vendas

- Nova tela **Uso do módulo** no menu de Busca & Vendas: usuários online agora, acessos e usuários por dia, mês e ano, acessos por tela e ranking de usuários.
- "Acesso" é a abertura de uma tela do módulo; o mesmo usuário na mesma tela conta uma vez a cada 30 minutos. Não mede cliques dentro da tela.
- A tela é liberada pela permissão **Caixa Seguro — Uso do módulo** (Admin › Perfis e Permissões, ou por usuário). Quem recebe a permissão precisa sair e entrar de novo.
- A medição começa na publicação: não há histórico anterior.

Roteiro: docs/release-notes/uso-busca-vendas.md.', 'deploy');

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
