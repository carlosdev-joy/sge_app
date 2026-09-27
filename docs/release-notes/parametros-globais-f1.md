# F1 — Contrato do catálogo de parâmetros de pipeline

Esta fase prepara a fundação de `docs/spec-parametros-globais-valida-arquivo.md`.
Não cria o nó Valida Arquivo nem altera o wizard; esses entregáveis pertencem às fases seguintes.

## Contrato

- GET `/pipelines/{pipeline_name}/parametros`: comportamento v1 preservado, apenas parâmetros destinados ao DataStage, segredos mascarados.
- GET da mesma rota com `?parametros_versao=2`: catálogo completo, migration 129 obrigatória (503 se ausente ou parcial).
- POST `/pipelines/register` com `parametros_versao: 2` e `parametros`: substitui o catálogo completo na transação do cadastro. Somente usuários com permissão de edição. A chave `parametros` ausente não altera o catálogo.
- Cliente v1 substitui apenas seus parâmetros DataStage, preserva ORQ e metadados DS invisíveis. Colisão com nome ORQ é recusada com mensagem textual para a interface antiga.
- Campos novos: `param_destino` (`datastage` ou `orquestra`), `param_procedencia` (`manual` ou `datastage`), `param_import_project`, `param_import_job`, `param_descricao`. Destino é diferente da procedência e de `param_source`, que continua definindo o cálculo do valor.
- Metadados de procedência são declarativos nesta fase; importação verificável via SSH virá na F2. Não há chamada SSH ou promessa de sincronização automática na F1.
- Nomes continuam únicos por pipeline e sensíveis à caixa. Um nome não pode representar dois parâmetros simultâneos de destinos diferentes. Parâmetros ORQ não são enviados ao DS nem apresentados como defaults DS na reexecução.
- Encrypted preserva cifragem e sentinela `***`; metadados de importação não armazenam cópia de defaults secretos.

## Segurança e validação

Entrada: catálogo JSON de editor autenticado; leitura exige sessão. Nenhuma nova permissão ampla, tabela de credenciais ou dependência externa. O maior risco do diff é um parâmetro interno ORQ ser enviado ao DS por um consumidor legado. As consultas da API de reexecução e do worker filtram destino; saves antigos preservam linhas ocultas. Migração parcial é erro 503, nunca fallback destrutivo.

SQL usa placeholders, metadados têm limites UTF-16, valores secretos são serializados pela máscara existente e o catálogo é validado antes de DELETE/INSERT. A transação do cadastro faz rollback em falha; a leitura para salvar usa UPDLOCK/HOLDLOCK. Não se oferece ainda controle otimista de edição concorrente nem snapshot de execução; pertencem ao contrato das fases seguintes.

## Deploy

1. Conferir backup/processo existente e numeradores das migrations. Na etapa 6c do `deploy.sh`, aplicar 128 (item futuro de frescor no Backlog) e 129 (colunas e CHECK do catálogo), dependente da 108. Reaplicar é seguro; não há alteração de valores/cifra existentes.
2. Atualizar `dags/utils/ds_params.py` e **reiniciar todos os workers consumidores**. Só depois atualizar/habilitar API com gravação v2. Worker antigo pode enviar parâmetros ORQ como DS; não permitir gravação v2 durante a transição.
3. Atualizar API com `pipeline_params.py`, router e serviço de rerun. Não há frontend novo, wheel ou variável de ambiente nova. Não é necessário regenerar DAGs nesta F1: módulo de runtime mantém assinatura.
4. `config/` de produção: preservar conforme instrução local (responder n). Produção é aplicada/validada pelo operador; validação local não certifica seu ambiente.

## Smoke do operador

a) GET v1 do pipeline existente continua apresentando seus defaults e máscaras.
b) GET v2 apresenta defaults legados com destino datastage e procedência manual.
c) Criar parâmetro ORQ em pipeline de teste pelo contrato v2; confirmar que GET v1 não o mostra e salvar pela interface atual não o apaga.
d) Confirmar prévia de reexecução DS sem parâmetros ORQ e disparo de teste sem ORQ nos argumentos do DS.
e) Salvar Encrypted e reenviar `***`: valor mantido sem aparecer em resposta/log.
f) Usuário sem edição recebe 403; payload inválido não altera catálogo.

## Reversão

Não remover colunas nem reverter API/worker indiscriminadamente depois de cadastrar ORQ. Antes de qualquer rollback de código, exportar de forma protegida a configuração e tratar/remover explicitamente parâmetros ORQ sob autorização do operador; código antigo não sabe isolá-los. Preferir correção adiante ou bloquear temporariamente a edição v2, mantendo o runtime com filtro. Não apagar dados automaticamente para reverter.
