-- 172_workspace_reserva_publicacao_esperada.sql
-- Idempotente — seguro para rodar mais de uma vez.
-- Correção (incrementa somente o patch): a reserva da execução contextual confere,
-- sob o mesmo bloqueio da 146, a publicação confirmada que a tela exibia quando o
-- pedido foi aberto (par versão + hash do conteúdo).
-- Substitui só dbo.sp_workspace_reserve_run (CREATE OR ALTER). A 146 não é alterada;
-- a trigger de publicação e dbo.sp_workspace_guard_run seguem como estão.
--
-- Política:
--   * execução (@reprocess=0) de pipeline gerenciado exige o par; sem ele, recusa
--     (cliente anterior a esta versão não tem caminho sem conferência);
--   * par diferente da publicação corrente, ou publicação pendente/não confirmada,
--     recusa ANTES de qualquer replay, inserção ou reativação de comando;
--   * replay (comando ativo ou inativo) também exige o mesmo par gravado no comando;
--   * replay de comando encerrado em 'erro' (sem corrida achada no Airflow) é
--     recusado sem reativar: o pedido precisa de uma nova corrida. Nos demais
--     replays, a API só responde sucesso depois de confirmar a corrida exata no Airflow;
--   * pipeline fora do workspace com par informado é recusado (a tela viu uma
--     publicação que não existe);
--   * reprocessamento mantém a regra da 146 (corrida da versão publicada atual);
--     com par informado, confere também.
-- Erro 51172: recusa por publicação (a API responde 409 marcada). 51146 continua
-- para comando/execução concorrente, identidade reutilizada ou comando encerrado
-- sem confirmação.
SET NOCOUNT ON;
SET XACT_ABORT ON;
IF OBJECT_ID('dbo.etl_workspace_comando','U') IS NULL THROW 50172,'Aplique migration 146 antes da 172.',1;
GO
CREATE OR ALTER PROCEDURE dbo.sp_workspace_reserve_run
 @name NVARCHAR(200),@run_id NVARCHAR(300),@request_hash CHAR(64),@actor NVARCHAR(100),@reprocess BIT=0,
 @expected_version UNIQUEIDENTIFIER=NULL,@expected_hash VARCHAR(128)=NULL
AS
BEGIN
 SET NOCOUNT ON; SET XACT_ABORT ON;
 -- Os dois ou nenhum; hash com 64 hexadecimais exatos. O parâmetro é mais largo
 -- que a coluna para que um valor longo não seja truncado em silêncio e aceito.
 IF (@expected_version IS NULL AND @expected_hash IS NOT NULL)
 OR (@expected_version IS NOT NULL AND (@expected_hash IS NULL OR DATALENGTH(@expected_hash)<>64 OR @expected_hash COLLATE Latin1_General_BIN LIKE '%[^0-9A-Fa-f]%'))
  THROW 51172,'Publicacao esperada incompleta ou malformada.',1;
 BEGIN TRANSACTION;
 DECLARE @version UNIQUEIDENTIFIER,@pending UNIQUEIDENTIFIER,@hash CHAR(64),@active CHAR(64),@managed BIT=0,@token UNIQUEIDENTIFIER;
 SELECT @managed=1,@version=p.version_id,@pending=p.pending_operation_id,@active=p.active_hash,@hash=v.content_hash
 FROM dbo.etl_workspace_pipeline p WITH(UPDLOCK,HOLDLOCK) LEFT JOIN dbo.etl_workspace_versao v ON v.version_id=p.version_id WHERE p.pipeline_name=@name;
 IF @managed=0
 BEGIN
  IF @expected_version IS NOT NULL BEGIN ROLLBACK; THROW 51172,'Pipeline sem publicacao do workspace.',1; END;
  COMMIT; SELECT CAST(NULL AS UNIQUEIDENTIFIER) AS command_token,0 AS existing; RETURN;
 END;
 IF @pending IS NOT NULL OR @version IS NULL OR @hash IS NULL OR @active IS NULL
 BEGIN ROLLBACK; THROW 51172,'Publicacao nao confirmada.',1; END;
 IF @reprocess=0 AND @expected_version IS NULL
 BEGIN ROLLBACK; THROW 51172,'Execucao exige a publicacao confirmada exibida.',1; END;
 -- Sob o bloqueio da linha do pipeline e antes de replay, inserção ou reativação.
 IF @expected_version IS NOT NULL AND (@expected_version<>@version OR LOWER(@expected_hash) COLLATE Latin1_General_BIN<>LOWER(@hash) COLLATE Latin1_General_BIN)
 BEGIN ROLLBACK; THROW 51172,'Publicacao alterada desde a exibicao.',1; END;
 -- Daqui em diante, com par informado, @version/@hash são o par esperado.
 IF EXISTS(SELECT 1 FROM dbo.etl_workspace_comando WITH(UPDLOCK,HOLDLOCK) WHERE pipeline_name=@name AND run_id=@run_id AND ativa=1)
 BEGIN
  IF @reprocess=1 OR NOT EXISTS(SELECT 1 FROM dbo.etl_workspace_comando WHERE pipeline_name=@name AND run_id=@run_id AND request_hash=@request_hash AND ator=@actor AND tipo='execute' AND version_id=@version AND content_hash=@hash)
  BEGIN ROLLBACK; THROW 51146,'Comando concorrente ou identidade reutilizada.',1; END;
  SELECT @token=command_token FROM dbo.etl_workspace_comando WHERE pipeline_name=@name AND run_id=@run_id;
  COMMIT; SELECT @token AS command_token,1 AS existing; RETURN;
 END;
 IF EXISTS(SELECT 1 FROM dbo.etl_workspace_comando WITH(UPDLOCK,HOLDLOCK) WHERE pipeline_name=@name AND ativa=1)
 OR EXISTS(SELECT 1 FROM dbo.etl_workspace_execucao WITH(UPDLOCK,HOLDLOCK) WHERE pipeline_name=@name AND ativa=1)
 OR EXISTS(SELECT 1 FROM dbo.etl_pipeline_execucao WITH(UPDLOCK,HOLDLOCK) WHERE pipeline_name=@name AND status IN('EXECUTANDO','RUNNING','QUEUED','AGUARDANDO','AGUARDANDO_DEPENDENCIA'))
 BEGIN ROLLBACK; THROW 51146,'Execucao ou comando ativo.',1; END;
 IF @reprocess=1 AND EXISTS(SELECT 1 FROM dbo.etl_workspace_comando WHERE pipeline_name=@name AND run_id=@run_id AND estado='erro')
 BEGIN ROLLBACK; THROW 51146,'Comando sem confirmacao: crie uma nova corrida.',1; END;
 IF @reprocess=1 AND NOT EXISTS(SELECT 1 FROM dbo.etl_workspace_execucao WHERE pipeline_name=@name AND run_id=@run_id AND version_id=@version AND content_hash=@hash)
 BEGIN ROLLBACK; THROW 51146,'Corrida sem vinculo com a versao atual.',1; END;
 IF @reprocess=0 AND EXISTS(SELECT 1 FROM dbo.etl_workspace_comando WHERE pipeline_name=@name AND run_id=@run_id)
 BEGIN
  -- Replay inativo: mesmo pedido, mesmo ator e o mesmo par gravado no comando.
  IF NOT EXISTS(SELECT 1 FROM dbo.etl_workspace_comando WHERE pipeline_name=@name AND run_id=@run_id AND request_hash=@request_hash AND ator=@actor AND tipo='execute' AND version_id=@version AND content_hash=@hash)
  BEGIN ROLLBACK; THROW 51146,'Identidade de comando reutilizada.',1; END;
  -- Encerrado em 'erro' (a reconciliação não achou a corrida): nada a repetir nem reativar.
  IF EXISTS(SELECT 1 FROM dbo.etl_workspace_comando WITH(UPDLOCK,HOLDLOCK) WHERE pipeline_name=@name AND run_id=@run_id AND estado='erro')
  BEGIN ROLLBACK; THROW 51146,'Comando encerrado sem confirmacao: crie uma nova corrida.',1; END;
  SELECT @token=command_token FROM dbo.etl_workspace_comando WHERE pipeline_name=@name AND run_id=@run_id;
  COMMIT; SELECT @token AS command_token,1 AS existing; RETURN;
 END;
 SET @token=NEWID();
 IF EXISTS(SELECT 1 FROM dbo.etl_workspace_comando WHERE pipeline_name=@name AND run_id=@run_id)
  UPDATE dbo.etl_workspace_comando SET command_token=@token,version_id=@version,content_hash=@hash,active_hash=@active,request_hash=@request_hash,tipo='reprocess',ator=@actor,estado='reservado',ativa=1,solicitada_em=SYSUTCDATETIME(),atualizada_em=SYSUTCDATETIME() WHERE pipeline_name=@name AND run_id=@run_id;
 ELSE
  INSERT dbo.etl_workspace_comando(pipeline_name,run_id,command_token,version_id,content_hash,active_hash,request_hash,tipo,ator,estado,ativa)
  VALUES(@name,@run_id,@token,@version,@hash,@active,@request_hash,IIF(@reprocess=1,'reprocess','execute'),@actor,'reservado',1);
 COMMIT; SELECT @token AS command_token,0 AS existing;
END;
GO

DECLARE @titulo NVARCHAR(200) = N'Execução confere a publicação confirmada exibida antes de reservar';

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
    VALUES (@nova, @titulo, N'## Execução confere a publicação confirmada exibida antes de reservar

- Ao confirmar a execução na aba Execução do pipeline, o pedido leva a publicação confirmada que a tela exibia quando a solicitação foi aberta. Se a publicação mudou ou ficou pendente nesse intervalo, a execução é recusada antes de reservar ou enviar qualquer coisa ao Airflow; abra a solicitação novamente para executar a publicação atual.
- Se a tela passar a exibir outra publicação com a solicitação aberta, o diálogo avisa e não envia.
- Repetir o envio usa o mesmo identificador e a mesma publicação. O mesmo identificador com outra publicação ou outros parâmetros é recusado, sem criar corrida nova.
- Repetir o envio nunca reenvia ao Airflow: só informa sucesso quando o Airflow mostra a corrida com esse identificador. Sem essa confirmação, responde erro e a solicitação segue reservada para conferência; se a conferência não achar a corrida, a solicitação não é repetida e é preciso abrir uma nova.
- Em pipeline publicado pelo workspace, a execução contextual sem a publicação informada é recusada (por exemplo, numa tela aberta antes da atualização): recarregue a tela. A identificação da publicação não é enviada ao Airflow nem entra nos parâmetros da corrida.
- O reprocessamento não muda: continua exigindo que a corrida seja da versão publicada atual.
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
