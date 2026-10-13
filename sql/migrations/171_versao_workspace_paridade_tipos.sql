-- 171_versao_workspace_paridade_tipos.sql
-- Idempotente — seguro para rodar mais de uma vez.
-- Correção: incrementa somente o patch.
-- Título estável evita duplicação; sincroniza a versão e o nome da aplicação.
SET NOCOUNT ON;

DECLARE @titulo NVARCHAR(200) = N'Publicação de Python, DataStage e Aguarde com as regras do cadastro';

IF OBJECT_ID('dbo.etl_versao_ferramenta', 'U') IS NULL
    PRINT '[--] etl_versao_ferramenta ausente (migration 003) — versão não registrada';
ELSE IF EXISTS (SELECT 1 FROM dbo.etl_versao_ferramenta WHERE titulo = @titulo)
    PRINT '[SKIP] versão desta entrega já registrada';
ELSE
BEGIN
    DECLARE @maior INT, @menor INT, @patch INT, @nova NVARCHAR(20);

    -- Só versões numéricas de 1 a 4 partes ("3", "2.2", "2.4.1", "2.4.1.7"),
    -- completadas para 4 partes; o resto é ignorado.
    ;WITH v AS (
        SELECT versao + REPLICATE('.0', 3 - (LEN(versao) - LEN(REPLACE(versao, '.', '')))) AS v4
          FROM dbo.etl_versao_ferramenta
         WHERE versao NOT LIKE '%[^0-9.]%' AND versao NOT LIKE '%..%'
           AND versao NOT LIKE '.%' AND versao NOT LIKE '%.' AND versao <> ''
           AND LEN(versao) - LEN(REPLACE(versao, '.', '')) BETWEEN 0 AND 3
    ), n AS (
        SELECT TRY_CONVERT(INT, PARSENAME(v4, 4)) AS a, TRY_CONVERT(INT, PARSENAME(v4, 3)) AS b,
               TRY_CONVERT(INT, PARSENAME(v4, 2)) AS c, TRY_CONVERT(INT, PARSENAME(v4, 1)) AS d
          FROM v
    )
    SELECT TOP 1 @maior = a, @menor = b, @patch = c
      FROM n
     WHERE a IS NOT NULL AND b IS NOT NULL AND c IS NOT NULL AND d IS NOT NULL
     ORDER BY a DESC, b DESC, c DESC, d DESC;

    -- Versão fora do padrão (sufixo "-hotfix", 5+ partes, espaço) é ignorada aqui,
    -- mas o cabeçalho a compara com parseInt: avisa no log do deploy, para o admin
    -- conferir o número em Admin › Versões.
    IF EXISTS (SELECT 1 FROM dbo.etl_versao_ferramenta
                WHERE versao LIKE '%[^0-9.]%' OR versao LIKE '%..%' OR versao LIKE '.%' OR versao LIKE '%.'
                   OR LEN(versao) - LEN(REPLACE(versao, '.', '')) > 3)
        PRINT '[ATENÇÃO] há versões fora do padrão em etl_versao_ferramenta (ignoradas no cálculo) — confira o número em Admin › Versões';

    IF @maior IS NULL
        SELECT @maior = 2, @menor = 2, @patch = 0;
    SET @nova = CONCAT(@maior, '.', @menor, '.', @patch + 1);

    INSERT INTO dbo.etl_versao_ferramenta (versao, titulo, descricao_md, criado_por)
    VALUES (@nova, @titulo, N'## Publicação de Python, DataStage e Aguarde com as regras do cadastro

- Ao publicar pela Montagem, a etapa Python que usa um parâmetro do pipeline no caminho do script ou no diretório de publicação passa pela mesma conferência do cadastro: parâmetro inexistente ou com grafia diferente, parâmetro que não é texto/caminho fixo ou referência no campo de outro modo é apontado na etapa, antes de publicar. Antes, a publicação passava e a etapa falhava na execução.
- Ao publicar pela Montagem, a etapa DataStage que usa um parâmetro do pipeline passa pela mesma conferência do cadastro: parâmetro inexistente ou com grafia diferente, parâmetro exclusivo do Orquestra ou nome de destino inválido é apontado na etapa, antes de publicar. O valor informado direto na etapa continua com prioridade sobre o parâmetro do pipeline de mesmo nome.
- Nas etapas dos demais tipos (Shell, SQL, procedure, HTTP, decisão, Aguarde, notificação, e-mail e Valida Arquivo), um uso de parâmetro do pipeline que tenha sobrado, por exemplo de uma etapa que era DataStage, é apontado na etapa antes de publicar, com a mesma mensagem do cadastro. Vale o tipo atual da etapa.
- A etapa Python no modo módulo, que roda no próprio motor, publica sem servidor SSH, como no cadastro. Os modos script no servidor e código embutido continuam exigindo o servidor SSH, e uma conexão informada que não existe continua recusada.
- Um Aguarde sem nenhuma etapa ligada a ele é recusado na publicação, com a mesma mensagem do cadastro.
', 'deploy');

    -- O mesmo que o "Nova Versão" da aba faz.
    IF OBJECT_ID('dbo.etl_app_config', 'U') IS NOT NULL
    BEGIN
        UPDATE dbo.etl_app_config SET config_value = @nova WHERE config_key = 'app_version';
        IF @@ROWCOUNT = 0
            INSERT INTO dbo.etl_app_config (config_key, config_value) VALUES ('app_version', @nova);
        UPDATE dbo.etl_app_config SET config_value = @titulo WHERE config_key = 'app_release_name';
        IF @@ROWCOUNT = 0
            INSERT INTO dbo.etl_app_config (config_key, config_value) VALUES ('app_release_name', @titulo);
    END

    PRINT CONCAT('[OK] versão ', @nova, ' registrada: ', @titulo);
END

GO
