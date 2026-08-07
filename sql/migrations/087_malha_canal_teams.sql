-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 087 — O CANAL do Teams por MALHA (e a mensagem do nó Notificação)
--
--   Hoje todo aviso de malha sai pelo canal que a supervisão DataStage usa —
--   um só, global, escolhido por "o grupo ativo com mais jobs de supervisão".
--   Quem opera duas frentes (a malha da madrugada e a de fechamento, por
--   exemplo) recebe as duas no mesmo lugar, e o alarme que importa se perde no
--   meio do que não importa.
--
--   `etl_malha.grupo_id` aponta para um canal JÁ CADASTRADO (`etl_msg_grupo`,
--   migration 049) — o mesmo catálogo que o nó de Notificação das Etapas usa.
--   Nenhuma tabela nova: canal, webhook e modelos de mensagem já existem, com
--   tela de cadastro e API próprias.
--
--   Por que na MALHA e não no nó Notificação: os sete alarmes do ciclo
--   (MALHA_FALHOU, MALHA_ATRASADA, MALHA_EXPIRADA…) existem mesmo em malha que
--   NÃO tem nó Notificação desenhado — e são justamente eles que acordam
--   alguém. Pendurar o canal no nó deixaria a maioria das malhas sem escolha.
--   O nó continua podendo ter canal próprio no `config_json` dele (chave
--   `grupo_id`), e aí ele vence para o aviso DELE.
--
--   SEM FK, pela mesma razão da Decisão 5 da 085: apagar um canal não pode
--   tornar a malha ineditável, e o `ON DELETE` certo aqui é "vira NULL", que
--   `_canal_da_malha` já trata degradando para o canal global.
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF OBJECT_ID('dbo.etl_malha', 'U') IS NOT NULL
   AND COL_LENGTH('dbo.etl_malha', 'grupo_id') IS NULL
BEGIN
    ALTER TABLE dbo.etl_malha ADD grupo_id INT NULL;
    PRINT '[OK] Coluna dbo.etl_malha.grupo_id criada';
END
ELSE
    PRINT '[--] dbo.etl_malha.grupo_id nao criada (ja existe ou tabela ausente)';
GO

-- O índice serve à leitura "quais malhas usam este canal", que a tela de
-- cadastro faz antes de deixar alguém inativar um grupo. FILTRADO porque a
-- esmagadora maioria das malhas segue no canal global (NULL) — e um índice
-- que indexa NULL aqui seria quase todo ele lixo.
IF OBJECT_ID('dbo.etl_malha', 'U') IS NOT NULL
   AND COL_LENGTH('dbo.etl_malha', 'grupo_id') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_malha_grupo')
BEGIN
    CREATE NONCLUSTERED INDEX ix_malha_grupo
        ON dbo.etl_malha (grupo_id)
        WHERE grupo_id IS NOT NULL;
    PRINT '[OK] Indice ix_malha_grupo criado';
END
ELSE
    PRINT '[--] Indice ix_malha_grupo nao criado (ja existe, coluna ou tabela ausente)';
GO
