-- 166_versao_pipeline_ux_inspector.sql
-- Idempotente — seguro para rodar mais de uma vez.
-- Funcionalidade: incrementa o minor e zera o patch.
-- Título estável evita duplicação; sincroniza a versão e o nome da aplicação.
SET NOCOUNT ON;

DECLARE @titulo NVARCHAR(200) = N'Inspector do Pipeline em subseções com desfazer e refazer';

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
    SET @nova = CONCAT(@maior, '.', @menor + 1, '.0');

    INSERT INTO dbo.etl_versao_ferramenta (versao, titulo, descricao_md, criado_por)
    VALUES (@nova, @titulo, N'## Inspector do Pipeline em subseções com desfazer e refazer

- Ao selecionar uma etapa, o inspector mostra os campos principais do formulário de cada um dos 11 tipos, sem abrir janela: Configuração, Etapa, Lineage e Avançado ficam na mesma área.
- Alterações no inspector são aplicadas à etapa por Aplicar; Salvar rascunho e Publicar continuam ações separadas. O que ainda não foi aplicado continua no formulário ao trocar de subseção, recolher o painel, ir à Configuração ou salvar.
- Aplicar grava só os campos alterados e recusa, com aviso, quando a etapa mudou nos mesmos campos, foi removida ou renomeada.
- Trocar de etapa com alterações não aplicadas pede confirmação.
- Desfazer e Refazer na barra do canvas (Ctrl+Z, Ctrl+Shift+Z ou Ctrl+Y) para os últimos 50 passos locais desde o último salvamento; um arraste é um passo. Não desfazem salvamento, publicação nem valores protegidos.
- Modo focado expande o inspector sobre a área do canvas para campos longos; Esc ou Voltar ao canvas retornam com zoom e seleção.
- Um diagnóstico da validação abre a subseção correspondente da etapa e mostra a mensagem.', 'deploy');

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
