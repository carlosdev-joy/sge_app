-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 074 — etl_malha.orientacao: orientação do diagrama de montagem
--
-- O diagrama da malha (MalhaEditor, F8) ganha orientação configurável POR
-- MALHA: 'horizontal' (esquerda → direita, o comportamento de sempre e o
-- default) ou 'vertical' (cima → baixo). É uma PREFERÊNCIA DE VISÃO que viaja
-- com o layout persistido: as posições layout_x/layout_y de etl_malha_pipeline
-- já são por malha (migration 070), e a orientação acompanha na linha-mãe —
-- todos os operadores abrem o MESMO desenho, na mesma direção.
--
-- Sem CHECK constraint de propósito (padrão da casa — cf. criticidade da 007):
-- os valores 'horizontal' | 'vertical' são validados na API (PATCH
-- /malhas/{name} recusa qualquer outro com 422) e a leitura normaliza valor
-- inesperado para 'horizontal' — um dado legado estranho nunca quebra a tela.
--
-- Sem a coluna (deploy parcial), a API degrada no padrão suave das colunas
-- opcionais (mesma regra da 073): GET devolve 'horizontal' e o PATCH responde
-- migration_074_pendente=True com log — nunca 500/503 por uma preferência de
-- visão. O 503 fica reservado às TABELAS (070/067), sem as quais o recurso
-- inteiro não existe.
--
-- Idempotente (COL_LENGTH) — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF COL_LENGTH('dbo.etl_malha', 'orientacao') IS NULL
BEGIN
    -- NOT NULL + default nomeada: as malhas existentes nascem 'horizontal'
    -- (o comportamento que elas sempre tiveram) sem passo de backfill.
    ALTER TABLE dbo.etl_malha
        ADD orientacao VARCHAR(12) NOT NULL
            CONSTRAINT DF_malha_orientacao DEFAULT 'horizontal';
    PRINT '[OK] etl_malha.orientacao criada (default ''horizontal'')';
END
ELSE
    PRINT '[--] etl_malha.orientacao ja existe';
GO
