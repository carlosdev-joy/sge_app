# F5 — Execução controlada por validação de arquivos

A fábrica gera Valida Arquivo, guardas antes do início/executor e fechamento rigoroso. Destinos só executam com diagnóstico durável e dependências satisfeitas; retomadas conservam configuração original e não misturam autorizações de tentativas diferentes. Decisão pulada não libera seus ramos. Aguarde protegido executa uma tarefa Python real, pois o scheduler pode concluir EmptyOperator sem executar pre_execute.

## Encerramento

O histórico distingue COM_MOVIMENTO, SEM_MOVIMENTO, SEM_EXECUCAO (ramos pulados por decisão, sem inferir falta de dados) e FALHA. Sem movimento tem histórico obrigatório; liberação e notificação são opções independentes congeladas no snapshot. Política negando liberação grava PULADO técnico e pula o evento Dataset; autorização positiva grava SUCESSO, compatível com os predicados existentes de dependência. Falha no encerramento não publica sucesso.

## Deploy e rollback

Após merges autorizados, aplicar migrations pendentes até **133** pela etapa6c; atualizar API/dags/utils, reiniciar worker e publicar inicialmente as DAGs afetadas. Sem dependências/wheels novas. A133 cria prova durável de guarda e amplia o conjunto de resultados da conclusão; não amplia execution_id, pois072 já o fez. Preservar chave Fernet e snapshots. F2b deve ser implantada junto da correção de identidade SQL contida na F4#459.

Não habilitar cadastro de validadores antes de F6. Rollback após uso requer pausar novas execuções, preservar corridas e histórico e restaurar em conjunto DAGs e runtime compatíveis; não apagar tabelas nem regenerar contratos incompatíveis para uma corrida em falha. Valores/políticas podem mudar para novos runs, topologia/conexão requer nova publicação.

Roteiro local/evidências: `docs/validacao-valida-arquivo-f5.md`. Smoke final DataStage depende da Caixa. Nenhum merge ou deploy nesta entrega.
