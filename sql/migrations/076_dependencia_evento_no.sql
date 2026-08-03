-- ============================================================================
-- Migration 076 — Eventos de nó da malha: derruba a FK de pipeline do evento
-- (F14 do desenho docs/malha-componentes-desenho.md §5/§6)
--
-- A guardiã passa a gravar eventos de OBSERVADOR de malha (MALHA_NOTIFICACAO /
-- MALHA_CONCLUIDA) em etl_dependencia_evento com pipeline_name = '#no:{id}'
-- — o marcador da convenção do §5 (o id é o IDENTITY de etl_malha_no; o
-- prefixo '#' não colide com dag_id válido do Airflow).
--
-- A FK FK_dep_evento_pipeline (criada na 067) impedia o marcador: ela exigia
-- que TODO evento apontasse para uma linha de etl_pipeline. O desenho declarou
-- "zero DDL em eventos", mas essa afirmação não sobrevivia à FK — este é o
-- ajuste MÍNIMO, registrado como desvio consciente:
--
--   • derrubar SÓ a FK (nenhuma coluna nova, nenhum índice novo — a chave
--     idempotente ux_dep_evento continua intacta e passa a valer também para
--     os marcadores '#no:{id}');
--   • o ON DELETE CASCADE que a FK carregava apagava a HISTÓRIA do evento
--     quando um pipeline era excluído — contra a filosofia da F4 §7.2
--     ("evento emitido é histórico verdadeiro e não se apaga"). Sem a FK,
--     evento de pipeline excluído permanece na tabela. Os leitores filtram:
--     o painel da malha / endpoint de execução por membro ou por nó da
--     malha, e a FILA do Teams (eventos_nao_notificados, que também lê esta
--     tabela) passou a exigir a EXISTÊNCIA do alvo — pipeline em
--     etl_pipeline para evento comum, nó em etl_malha_no para marcador
--     '#no:{id}' — para nunca enviar card órfão (achado 2 da revisão
--     adversarial da F14).
--
-- Idempotente: roda 2x sem erro (etapa 6c do deploy.sh). Conferência por
-- SELECT — sql/migrate.py descarta PRINT (D40).
-- ============================================================================

IF EXISTS (SELECT 1 FROM sys.foreign_keys
           WHERE name = 'FK_dep_evento_pipeline'
             AND parent_object_id = OBJECT_ID('dbo.etl_dependencia_evento'))
BEGIN
    ALTER TABLE dbo.etl_dependencia_evento
        DROP CONSTRAINT FK_dep_evento_pipeline;
    PRINT '[OK] FK_dep_evento_pipeline derrubada (eventos de no #no:{id} liberados)';
END
ELSE
    PRINT '[--] FK_dep_evento_pipeline ja nao existe';
GO
