# F9 — homologação e destinos do Fluxo

Base c71337dd/DEV2.16.1. Candidato2.17.0; entrega DEV desta fase ainda pendente. Esta matriz confronta as19linhas de [paridade F6](workspace-paridade-f6.md), preservando aquela auditoria como evidência histórica. Fluxo permanece a entrada de desenvolvimento conforme PR490; URLs antigas redirecionam sem reintroduzir Etapas.

| # | Função F6 | Destino atual e evidência local | Alcance |
|---|---|---|---|
|1|Lista/cadastro|Pipelines/PipelineCreate; WorkspaceDraftTools, Catalog/Schedule/GovernanceFields; projeto/domínio, agenda/cadastro rico e seleção de predecessores|Guiado no draft; janelas e predecessores corrigidos F9; staging/cancelamento/paginação testados|
|2|Criar/editar etapa|Biblioteca11tipos, NodeProperties, SharedJobConfiguration e SpecializedConfiguration|Controles por tipo, sem exigir JSON para operação comum; aplicação depende de posse atual|
|3|Remover etapa|Propriedades/seleção e Delete com modal da aplicação|Publicado preservado; não é inativação|
|4|Inativação|Governança ativo/motivo do pipeline|Inativação de etapa não existia no inventário original; não inventar botão ou requisito|
|5|Ordenar|WorkspaceFlowTools e reorderWorkspaceExecution|Ordem executável guiada; Organizar muda sólayout|
|6|Renomear|Identificador no inspector e renameWorkspaceNode|Referências/grafo/layout atualizados no draft; histórico imutável|
|7|Abrir/salvar fluxo|WorkspaceEditor/Canvas|Revisão/lease/fence, modo consulta sem escrita; falha de save preserva alterações locais|
|8|Publicação|WorkspacePublication/Versions, reconciliador persistente|Validação separada, intenção idempotente, hash e projeção; SQL real F7D/contratos preservados|
|9|Parâmetros pipeline/importação|WorkspaceParameters/CatalogEditor, ImportarParametros|CRUD tipos/origens/data/destinos/descrição e prévias; referências protegidas por endpoint write-only|
|10|Configuração por tipo|JobTypeFields/JobParamsEditor/VinculosParametros e seis painéis especializados|11tipos; configuração desconhecida não descartada; conferência de grafia DS adicionadaF9|
|11|Lineage|WorkspaceLineage, adaptação DSX/ISX, marker1/hash/projeção|Linhas versionadas, inclusive vazias/duplicadas; header/cache externo não vira autoridade histórica|
|12|Importação em lote|WorkspaceFlowTools/importWorkspaceRows; alternativa JSON em DraftTools|Guiada com conexões/ramos; JSON inicializa lineage explícito no contrato1 após correçãoF9|
|13|Execução|WorkspaceOperations/RunRequest|Configuração publicada e comando explícito; conferência de backend/SQL em F6, replay isolado atual; não cancela remotamente|
|14|Reprocessar|FluxoEditor runtime/modais|Versão vinculada; corrida antiga/desconhecida e cascata permanecem restrições de integridade|
|15|Pausas|Barra de execução/ModalPausaEtapa|Marcar/liberar/cancelar pausa de etapa; não equivale a pausaDAG ou encerramento remoto|
|16|Estado/logs|Execuções/Logs contextual, WorkspaceRunProperties; módulos globais Logs/Falhas/Console|Run/tentativa/histórico preservados; configuração atual consultada no Fluxo. Resumo runtime não replica todos painéis globais ou editor especializado histórico|
|17|Política sem movimento|WorkspaceGovernanceFields|Controles dos dois campos existentes; versão da política preservada pelo adaptador|
|18|Prévias SQL/decisão/arquivo|SpecializedConfiguration/paineis existentes e preview estático exclusivo|Não gravam publicado; revisão obsoleta/cancelamento recusados. Arquivo estático não certifica arquivo/SSH real|
|19|Maestro|MaestroChat no editor da etapa/pipeline, adaptador contextual nativo|Proposta revisável aplicada sóao draft; sem autoexecução/publicação, segredos excluídos; provedor real não exercitado|

## Onze componentes

DataStage, Shell, Python/PySpark, Stored Procedure e HTTP usam controles/catálogos compartilhados e patches conservativos. SQL, Decisão, Aguarde, Notificação, E-mail e Valida Arquivo usam painéis especializados com transformação local; decisão atualiza configuração/arestas conjuntamente. Declarações ISX importadas por GET do cache são uma fonte explícita para revisão, não prova de declaração histórica do draft. Quando a declaração não foi capturada, o Maestro informa desconhecido em vez de inventá-la.

## Correções desta rodada

O importador JSON alternativo criava nó sem arraylineage e era recusado no save do contrato1. Agora inicializa lista explícita vazia sem alterar o marker. O cadastro oferecia JSON para predecessores e janelas; agora o seletor paginado retorna staging, conserva linhas extras/assinadas, mantém tabela e CSV juntos e limpa janelas ao remover todos os predecessores. O modo draft do modal nunca usa POST/DELETEdependencias ativos. A conferência DataStage utiliza o projeto capturado no draft e consulta explícita, com aviso honesto de indisponibilidade e aplicação protegida de grafia.

Servidor valida predecessores ausentes/inativos/self, tipo canônico, CSV/tabela, ciclo e assinatura de malha. Grafo além do teto é recusado por análise inconclusiva. Publicações com mudança de dependência adquirem applock transacional antes dos locks por operação/hash e revalidam grafo sob locks antes de escrever. Não amplia Malha nem permite transferir propriedade compilada.

## Validação e limites

Gates locais: pytest7332PASS8preexistentes51skip/zeroNEW; lint73/73/zeroNEW; tsc-b/Vitebuild2PASS; migrations167PASS. Novos testes cobrem ciclo com caixa diferente/mais500nós, mirror divergente, inativo/ausente/self, tipo minúsculo forjado e assinatura removida/transferida. BrowserF9 seis cenários,10capturas finais1440/947/390claro/escuro; QA de paridade identificou e exigiu os três ajustes; security manual confirmou correções; finishSHIP/documenter preservam DS. Rota fria239973bytesgzip<307200; medições pareadas50/100/300 e APIF8 seguem evidência, não INP de campo.

Negativas browser4PASS; experiências/aliases/corrida histórica/tentativas/log escapado16PASS, com contratos de catálogo e menu atual adaptados desde o harnessF6. SQL vivo: duas conexões confirmam applock, timeout, rollback e reaquisição em recurso temporário próprio sem gravar dados. DEV final desta fase ainda pendente. Evidências anteriores de execução SQL/reprocessamento/reconciliação e offline só são reutilizadas onde fonte/contrato não mudaram; não chamar reutilização de nova rodada de execução real.

## Recuperação e rollback

Antes de aplicar em DEV: backupCOPY_ONLY/CHECKSUM verificado, commit exato, migrations e serviços alterados conferidos. Somente API requer restart nesta fase; imagem .NET/DAG/worker não mudaram. Falha de publicação conserva intenção/gate e exige consultar operationId/erro antes de retry; não criar intenção substituta nem limpar tabelas. Restore de versão publicada conhecida cria novo draft, nunca reescreve histórico ou presume cifra/lineage antigo desconhecido. Rollback de UI/API usa SHA anterior e mesmas configurações; migration de versão permanece auditável, não fazer downgrade destrutivo nem restaurar banco compartilhado para teste. Ensaios de restore lógico com fixtures próprias são distintos de recovery físico de desastre ou rollback em produção.

Caixa/DataStage/InformationServer, serviço real de IA, INP de campo, planos SQL/IO e dimensionamento cliente continuam ensaios externos pendentes. Main/produção não autorizados. Não há declaração de100% desses ambientes nem de novos cancelamentos/conectores/telemetria. Próximas evidências devem ser registradas nesta matriz e release após DEV.
