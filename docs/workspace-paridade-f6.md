# F6 — revisão adversarial da paridade funcional atual

Data2026-10-09; candidato funcional 211289ff774053ee1ad1ba7816a483fe564e4c69. Somente leitura do código/plano/inventário, sem alteração de fontes, serviços, produção ou dados privados. Relatório é a única gravação. Não houve delegação.

## Conclusão

PARIDADE INCOMPLETA. O novo workspace entrega criação básica, lease/revisão, canvas, publicação/versionamento, execução e investigação contextual. Preservar JSON das11categorias não equivale a manter os formulários e ferramentas do pipeline antigo. Links Ferramentas dão acesso ao legado, mas suas gravações em pipelines geridos são deliberadamente recusadas; portanto não são substitutos funcionais da edição no draft.

A spec docs/spec-pipeline-workspace-dotnet.md:5,123,136,166 exige destinos/permissões equivalentes antes da retirada de menus para o grupo habilitado. As lacunas abaixo são requisitos anteriores ainda incompletos, não funcionalidades novas fora do escopo. F6:168-171 e plano2026-10-09-pipeline-workspace-f6 mandam testar/documentar consolidação; o plano F6 atual expressamente não autoriza implementar as diferenças nesta rodada. Aprovar testes da operação existente pode encerrar a rodada de evidências, mas não comprova paridade integral.

## Inventário F1 confrontado com destinos reais

| Função | Destino implementado | Estado/risco e evidência |
|---|---|---|
| Lista/cadastro pipeline | Pipelines, PipelineCreate, Visão geral, DraftTools | Parcial: criação/contexto existem, cadastro rico viraJSON. PipelineFormModal.tsx:623-682 tem projeto catálogo, descrição, criticidade, ambiente, SLA, motivo de inativação; :1086-1095 pool/runbook/destinatários. DraftTools.tsx:18 só projeto/domínio/tipoagenda/horário +JSON. Risco: operação comum exige conhecer campos internos. |
| Criar/editar etapa | Biblioteca11tipos, NodeProperties, configuração avançada | Parcial: WorkspaceEditor.tsx:90 adiciona tipos; NodeProperties.tsx:18-25 oferece nome/comando/ordem/conexões/valor de parâmetros existentes. JobTypeFields.tsx e painéis especializados não são usados. Risco de parâmetros/configurações incompletos e maior esforço de montagem. |
| Remover etapa | Propriedades → remover rascunho | Implementado, publicado preservado até publicação; WorkspaceEditor.tsx:95. Não equivale a inativar. |
| Inativação | JSON de metadata/legacyJob | Parcial. Status importado preservado, sem ação dedicada comparável; inativação de etapa já era lacuna do inventárioF1, logo não inventar regressão de um botão que não existia. Inativação de pipeline tinha motivo no cadastro antigo. |
| Ordenar | Campo ordem + Organizar desenho | Parcial. NodeProperties.tsx:21 altera execution_order; Organizar sólayout. Jobs.tsx:808,1019 oferece reorder e FluxoEditor antigo recompõe ordem/dependências. Não há equivalente guiado em lote; não chamar arranjo visual de ordenação executável. |
| Renomear | Renomear identificador no draft | Implementado com limites: helper atualiza referências/arestas/layout e recusa parâmetros protegidos. Jobs.tsx:246-266 rename legado atualiza também lineage/histórico; versão draft não deve alterar histórico, mas lineage não possui percurso de edição correspondente. |
| Abrir/salvar fluxo | WorkspaceEditor/Canvas + lease/revision | Implementado; decisões/ramos em workspaceDecision, leitura não grava. Configuração completa JSON continua alternativa técnica. |
| Publicação | WorkspacePublication/Versions | Implementado e melhora isolamento/versionamento; não substitui disparo. |
| Parâmetros pipeline/importação | Aba Parâmetros + metadataJSON | Parcial forte: WorkspaceEditor.tsx:89 adiciona somente String e edita valor existente; sem remover/renomear/tipo/destino/origem/offset/âncora/formato/vínculo/preview/importação guiados. PipelineFormModal.tsx:1034 e ParametrosGlobais/ParametrosPipeline têm catálogo e importação. |
| Configuração por tipo | NodeProperties genérico +JSON | Parcial forte:11tipos preservados, mas controles especializados ausentes; detalhamento abaixo. |
| Lineage | Ferramentas → legado; consultas GET | Consulta legada acessível, edição sem destino draft. workspace_publication.py:58,64 admite somente tabelas/configs enumeradas, não etl_job_lineage; legado PUT/extração que grava com pipeline é recusado. Risco: pipeline gerido não consegue manter lineage pelo novo fluxo. |
| Importação em lote | DraftTools listaJSON | Parcial: :14 recusa depends_on_jobs e condition_json não vazios, adiciona jobs sem grafo; antigo Jobs.tsx:611 permite colar lista com conferência. Risco: formato/montagem e configs relacionados exigem passos/manipulaçãoJSON adicionais. |
| Execução | WorkspaceOperations RunRequest, APIworkspace/runs | Implementado para configuração publicada, confJSON/data lógica/runid, com reserva/gates. Não há cancelamento geral oferecido; UI informa. |
| Reprocessar | FluxoEditor runtime modais preservados | Implementado com prévia/seleção/params. Política gerida recusa corrida antiga/desconhecida e cascata; limite explícito, menor alcance que reprocessamento legado. Não tratar essa restrição de integridade como bug por si só. |
| Pausas | Header runtime + ModalPausaEtapa | Implementado para marcar/liberar/cancelar pausa de etapa. Não é pausaDAG/cancelamento remoto geral. |
| Estado/logs | Execuções + Logs + painel lateral | Implementado parcialmente: fonte/tentativa/run/histórico e logAirflow; RunProperties.tsx:9 só início/duração/tentativa/params/link. Antigo painel traz configuração especializada, conferênciaDataStage e cronologia/contexto adicional. LogsAirflow não provam paridade com todos logs específicosDataStage/falhas/resolução do módulo global Logs. |
| Política sem movimento | metadataJSON | Sem formulário draft. PainelPipeline legado monta editor específico; escrita publicada é bloqueada. Risco: política crítica menos descobrível e sem controles equivalentes. |
| Prévias SQL/decisão/arquivo | Ferramentas → editor legado | Parcial: SQL/decisão com payload sem identidade podem consultar por contrato próprio; não são preview do draft contextual. ValidaArquivo POST contém pipeline no path e é barrado em pipeline gerido (PainelValidaArquivo.tsx:40; guard:42-49). Não declarar as três ferramentas igualmente acessíveis. |
| Maestro | Ferramentas → legado | Conversa/histórico permanecem no contrato legado; aplicação da proposta ocorre no estado legado e salvar ativo é recusado. Workspace não oferece aplicação da proposta ao draft. Risco: usuário vê ajuda mas não consegue concluir percurso sugerido. |

## Lacunas de formulários por tipo (sem confundir JSON com controle)

- DataStage: JobTypeFields.tsx:270-565 oferece criar/remover parâmetros, tipos, origemfixo/data/run, offsets/âncoras/formato, previewservidor e máscara; :629-807 importa parâmetrosISX. NodeProperties.tsx:23 edita apenas valor dos jáexistentes e oculta segredo, sem criar parâmetros da etapa. VinculosParametros, seleção/conferência de job e ISX ficam no legado. Novos params/vínculos sóJSON; novos secretos não são criados por inserir uma secretReference, que exige origem existente.
- Python/PySpark: JobTypeFields.tsx:154-205 valida modos módulo/script/PySpark e configuração específica (paths/destino/opções); workspace sócomando/conexão +JSON python_json. Preservação não oferece os mesmos seletores.
- Storedproc/shell/http: campos simples existem parcialmente, mas seleção de conexões/bancos por catálogo, parâmetrosstoredproc tipados/criar/remover e controles específicos são substituídos por identificadores livres/JSON.
- SQL: PainelSql.tsx:45-66 consulta bancos e preview amostra; workspace propriedade SQL mostra comando/genérico, enquanto sql_json tem consulta e opções internas. Campo comando não é editor guiado do sql_node.
- Decisão: workspace conecta/remove ramos e conserva condição; não oferece formulários de tipo, operador, valor, fonte SQL/linhas, edição/reordenação de casos e simulação como PainelDecisao.tsx:93-126,221-310,450. Configurarcondition_json ainda é tarefaJSON.
- Aguarde/notificação/email: paineis PainelAguarde/PainelNotificacao/PainelEmail oferecem configuração específica, grupos/modelos/canais/conteúdo/origens. Workspace sóJSON além do formulário genérico. Tipoemail aparece no catálogo sem equivalência de seleção/modelagem.
- ValidaArquivo: tabelas/configurações importadas preservadas, mas entradas, destinos, políticas, diretórios/vínculos e prévia impacto têm painel específico antigo. Novo NodeProperties sóJSON; nova criação exige montar arrays etl_valida_arquivo_no/config manualmente. Prévia legada do pipeline gerido é bloqueada.

## Gaps confirmados de capacidade além do formulário

1. Agenda hourly_n e biweekly: PipelineFormModal.tsx:843-916,1143-1161 suporta modos e campos; validate_projection em workspace_publication.py:108 rejeita esses schedule_type. Preservar metadata importado ou usarJSON NÃO torna publicável. Pipeline desse tipo pode ser importado, mas não concluir publicação do draft sem modificar agenda. Gap de motor/adaptador e requisito de preservação/paridade, prioridade alta.
2. Lineage: sem armazenamento/projeção de atualização no draft. Link não contorna autoridade. Gap de capacidade, não só aparências, prioridade alta.
3. PréviaValidaArquivo: leitura computada porPOST recebe identidade e é recusada pelo guard geral de configuração. Ferramentas em PipelineWorkspace.tsx:38 afirma prévias acessíveis, mas este percurso falha409 em pipelinegerido. Prioridade média/alta pelo risco de publicarsemprévia.
4. Catálogo/secretos: preservação de referências e mascaramento protegem dados existentes; não equivalem ao fluxo antigo de criar/rotacionar secreto. API exige origem compatível; UX não oferece destino gerido explícito para fazê-lo. Limite de capacidade importante a registrar antes do piloto.

## Autoridade e links legados

api/services/workspace_legacy_guard.py:12 permite GET/HEAD/OPTIONS; :16-32 coleta identidade path/query/body; :42 classifica runtime; :47-49 recusa escrita de cadastro gerido e runtime durante pending. Routersjobs e lineage instalam guard (jobs.py:35, lineage.py:19). Legado=1 em PipelineWorkspace.tsx:38 sóevita redirect, não contorna SQL/HTTP. Assim formulários podem abrir e permitir manipulação local, porém Save/rename/reorder/import/lineage/policy/gerarDAG encontram bloqueio. Isso é isolamento correto F4, mas reduz o valor do link como destino de paridade se não existir alternativa draft equivalente.

SQL/decisão previews em painéis enviam consultas/conexões sem pipeline; guard sem names retorna, então não afirme bloqueio geral de toda préviaPOST. Maestro router não usa o mesmo guard; conversar é distinto de gravar fluxo. Capacidade deve ser atribuída ação por ação.

## Fora de escopo e limites honestos

F6 atual não autoriza implementar essas lacunas: documentá-las para decisão de ajustes após rodada. DataStage real/InformationServer/Caixa, produção/main, novaMalha, novos componentes de qualidade/modelos/progressos fictícios, cancelamento remoto geral não comprovado e ampliação de telemetria/retensão não devem ser acrescentados por inferência. SLA/runbook já presentes no cadastro antigo são paridade de interface/consulta; não confundir isso com implementar novo algoritmoSLA/previsão.

Esta revisão não reexecutou testes/DEV/performance/offline. SQL76PASS foi informado pelo responsável; não prova formulários inexistentes nem equivalência de toda operação. Aceite funcional precisa separar destinos implementados, JSONparcial, indisponíveis no gerido e restrições assumidas. Não há corrupção nova confirmada nesta auditoria de paridade; o problema é ausência/alcance funcional e descoberta. Nenhum arquivo de configuração secreta, logcliente ou dado real foi lido.
