-- 192: Comunicações e SLA F13; Idempotente — seguro para rodar mais de uma vez.
DECLARE @titulo NVARCHAR(200) = N'Comunicações — políticas, SLA e recuperação';

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
    VALUES (@nova, @titulo, N'## Comunicações e SLA

- Nós SQL/E-mail preservados; política explícita de erro Teams, default legado.
- Resultado agregado original com Warning exato e geração Clear; matrícula/destinos sem retarget.
- Dispatcher operacional de teste sob autorização RAM temporária e fence; dry-run preserva legado.
- SLA com intenção, histórico de tentativas e recuperação administrativa idempotente auditada.
- Teams pessoal: formulário administrativo, readiness e binding aprovado; tenant/destino/recebimento permanecem gates externos.
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


IF OBJECT_ID('dbo.etl_backlog','U') IS NOT NULL
BEGIN
    UPDATE dbo.etl_backlog SET descricao=N'EOC-F9–F13 technical_delivered_external_pending: integrações internas de autoridade original, Warning exato, geração Clear, produtor operacional, transporte fenced, cutover por modo original, reenvio administrativo auditado e formulário Admin entregues tecnicamente em F13. Flags permanecem OFF. Dry-run preserva legado; operational-test exige autorização temporária RAM por destino exato. Gates externos: tenant/app/permissões mínimas/instalação/Connector; destino real de teste explicitamente autorizado, teste de transporte e recibo; piloto humano e Caixa/DataStage. Accepted não significa Received; Unknown não tem retry automático. Não certificar100% humano/externo nem ativar mensagens de negócio.'
    WHERE titulo IN (N'Alertas: certificar autoridade agregada e geração operacional',
                      N'Alertas: validar transporte de teste e cutover sem duplicar legados',
                      N'Teams pessoal: homologar tenant e concluir integração operacional');
    IF NOT EXISTS (SELECT 1 FROM dbo.etl_backlog WHERE titulo=N'Comunicações e SLA: homologação externa e piloto humano')
        INSERT dbo.etl_backlog (titulo,descricao,tipo,area,prioridade,status,tags,criado_por)
        VALUES (N'Comunicações e SLA: homologação externa e piloto humano',
                N'EOC-F13 technical_delivered_external_pending. Código interno e fixtures próprias não comprovam recebimento nem tenant/Caixa. Validar destinos reais somente após autorização específica; piloto humano nos três perfis; provider/instalação e SQL/DataStage Caixa. Transporte operacional sóteste, sem ativação nesta entrega. Preservar coorte/mode originais e histórico por tentativa após restart/Clear.',
                N'spike',N'backend',N'P1',N'refinado',N'EOC-F13,external-gate',N'eoc-f13');
END
GO
