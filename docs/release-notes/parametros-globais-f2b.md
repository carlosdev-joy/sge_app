# Parâmetros de pipeline — F2b

Data: 27/09/2026. Implementação preparada; sem merge/deploy. Depende da F2a (#456).

## Mudanças na tela

No formulário de etapa e no painel do canvas, DataStage permite vincular um nome declarado pelo job a um parâmetro DS do pipeline. Parâmetros exclusivos Orquestra não são enviados ao DataStage. Python permite selecionar String/Pathname fixo para o caminho do script ou diretório de publicação do modo ativo. O campo direto continua tendo prioridade e a interface informa quando sobrepõe a referência. Segredos permanecem protegidos e não são opções de caminho Python.

Ao ativar referências, a corrida guarda a configuração antes dos consumidores. Retomadas usam a original, mostram parâmetros sem edição e rejeitam novos overrides. Para usar alterações do cadastro, inicie outra execução. Corrida antiga sem snapshot não é reconstruída com valores atuais. Pipelines que nunca ativaram vínculos preservam o fluxo legado de overrides.

Não inclui ainda o nó Valida Arquivo (F3–F6). Não habilita interpolação de outros campos Python ou dos demais tipos de nó.

## Implantação

1. Integrar F2a antes desta fase; aplicar migrations 128/129 pendentes e 130 pelo fluxo 6c do deploy.
2. Publicar API, `dags/` e `ui-react/dist/` juntos. Reutiliza `ORQUESTRA_CONN_KEY`; não adiciona dependências Python/wheels.
3. Reiniciar workers do Airflow (cache de `dags/utils/`). Preservar a chave existente; perder a chave impede retomar snapshots cifrados.
4. Publicar inicialmente as DAGs dos pipelines que ativarem referências. Alterar apenas valores de parâmetros não exige nova DAG. Remover a última referência mantém o suporte ao histórico.
5. Mudanças de estrutura/projeto/servidor incompatíveis são recusadas enquanto houver corrida retomável. Reexecução de corrida concluída também confere compatibilidade. O DataStage preserva a conexão efetiva do pipeline; Python usa a conexão do nó.

Não aplicar DDL diretamente em produção por esta PR. Ausência da migration 130 mantém a seleção desabilitada; falha de leitura não apaga referências preenchidas.

## Smoke e rollback

Testar em DEV: configurar referência, disparar, editar parâmetro, retomar e conferir original; disparar nova corrida e conferir novo valor; tentar alterar servidor/estrutura; testar entrada por Logs (execution_id) e canvas (dag_run_id). Conferir segredos fora de logs/tela/XCom. Certificar DataStage com dsjob real na versão instalada antes de declarar validação operacional.

Para rollback, impedir novas execuções dos pipelines que ativaram a feature e drenar/concluir as corridas antes de reverter API/DAG/UI. Não remover tabelas nem chave: os snapshots são necessários ao histórico. Reverter somente a UI não remove o contrato de execução já ativado.
