-- Migration 071 — normaliza a grafia em etl_pipeline_dependencia.
--
-- Mesma classe do incidente da 069, em outra tabela: o register da F1 gravava
-- depende_de "como digitado" e o seed F da 067 herdou a grafia do CSV legado —
-- a colação CI junta tudo nas queries, mas o diagrama da malha (F8) monta as
-- arestas por id de nó, e uma grafia divergente fazia a dependência REAL sumir
-- do desenho em silêncio. O código foi corrigido para canonizar na leitura e
-- na gravação; esta migration limpa o que já nasceu divergente.
--
-- Idempotente: BIN2 + DATALENGTH (espaço à direita) — segunda execução casa
-- zero linhas. Sem risco de colisão: o índice único é CI e já trata as grafias
-- como a mesma identidade.

IF OBJECT_ID('dbo.etl_pipeline_dependencia', 'U') IS NOT NULL
BEGIN
    UPDATE d SET pipeline_name = p.pipeline_name
    FROM dbo.etl_pipeline_dependencia d
    INNER JOIN dbo.etl_pipeline p ON p.pipeline_name = d.pipeline_name
    WHERE d.pipeline_name COLLATE Latin1_General_BIN2
          <> p.pipeline_name COLLATE Latin1_General_BIN2
       OR DATALENGTH(d.pipeline_name) <> DATALENGTH(p.pipeline_name);
    PRINT '[OK] etl_pipeline_dependencia.pipeline_name: '
        + CAST(@@ROWCOUNT AS VARCHAR(10)) + ' linha(s) normalizada(s)';

    UPDATE d SET depende_de = p.pipeline_name
    FROM dbo.etl_pipeline_dependencia d
    INNER JOIN dbo.etl_pipeline p ON p.pipeline_name = d.depende_de
    WHERE d.depende_de COLLATE Latin1_General_BIN2
          <> p.pipeline_name COLLATE Latin1_General_BIN2
       OR DATALENGTH(d.depende_de) <> DATALENGTH(p.pipeline_name);
    PRINT '[OK] etl_pipeline_dependencia.depende_de: '
        + CAST(@@ROWCOUNT AS VARCHAR(10)) + ' linha(s) normalizada(s)';
END
ELSE
    PRINT '[--] etl_pipeline_dependencia ausente (migration 067 pendente) — nada a normalizar';
GO
