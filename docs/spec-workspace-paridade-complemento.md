# Complemento executável: paridade do workspace — Orquestra
Data: 2026-10-11 · Status: autorizada, F7A/F7B/F7C/F7D/F8/F9 entregues em DEV2.17.1; aceites externos separados

## 1. Visão
Completar os requisitos de paridade de docs/spec-pipeline-workspace-dotnet.md, confrontados em docs/workspace-paridade-f6.md. Autorização explícita do usuário: seguir até encerrar os pontos listados, preservando a spec existente e a referência visual. Não substitui arquitetura, contratos ou escopo da spec original.

## 2. Escopo
**IN:** formulários das 11 categorias, parâmetros de etapa/pipeline, prévias SQL/decisão/arquivo, lineage no draft, aplicação do Maestro existente no draft, cadastro rico já existente, importação/ordenação guiada, comparação completa com legado, desempenho e homologação DEV. Decisão posterior confirmada em PR490 prevalece sobre a opção de lista da spec original: editar somente pelo Fluxo. Guiar operações comuns sem exigir JSON. Aproximação estrutural aos mockups01/02, com padrões de ferramentas empresariais como direção de qualidade, sem inventar funcionalidades de outros produtos.

**OUT:** novas Malhas, monitores estratégicos, novo assistente por linguagem natural, Academy/comunidade, migração completa FastAPI ou motor, cancelamento remoto geral, novas conexões/conectores, main/produção. Verificação em DataStage/InformationServer da Caixa exige acesso real e deve ser declarada separadamente, nunca substituída por fixture ou chamada de homologação integral em produção.

## 3. Arquitetura
- React: PipelineWorkspace/WorkspaceEditor/NodeProperties; componentes compartilhados JobTypeFields, JobParamsEditor e paineis especializados. Adaptadores puros transformam configuration/legacyJob e tabelas relacionadas sem descartar campos.
- .NET mantém draft/revision/lease/version/publication. FastAPI conserva consultas e motor legado; previews de draft usam contratos exclusivos, validados pelo servidor, sem gravar cadastro publicado. Lineage/segredos adicionais exigem contrato e projeção explícitos.
- Biblioteca/canvas/propriedades permanecem dominantes. Configuração extensa usa área expandida compartilhada; controles leves e resumo no inspector. DS claro/escuro, foco, cancelamento e feedback da aplicação.
- Nenhum editor legado de gravação ativa será ligado ao draft sem mapear todas as chamadas. Mutação local exige posse atual; salvar/publicar continuam autoridades do servidor.

## 4. Modelo de dados
Definition/layout e nós existentes são a base. JobTypeFields usa legacyJob, etl_pipeline_job_param e JSON tipados existentes. Lineage e eventual armazenamento de segredo do rascunho requerem migrations próprias idempotentes, tipos/larguras conferidos no código/banco. Segredo não entra em definition_json, logs, IA ou evidências; somente referência. Cada entrega tem migration de versão numerada pelo próximo número livre de develop, aplicada pelo runner do projeto/etapa6c. Não reservar números para fases futuras.

## 5. Fases e aceite
### F7A — formulários compartilhados e parâmetros de etapa
Reusar controles DataStage/Shell/Python/Stored Procedure/HTTP, conexões e bancos catalogados, preview de parâmetros e modos Python. Aplicar mudanças apenas ao nó do draft; campos desconhecidos e referências protegidas conservados. Leitura/lease expirada não podem aplicar alterações nem propostas atrasadas. Parâmetros existentes protegidos não viram input de segredo comum. PR própria; versão funcional minor.
### F7B — configurações especializadas e prévias
SQL/decisão/notificação/e-mail/aguarde/valida-arquivo: controles equivalentes, erros guiados, ramos e prévias sobre a revisão selecionada, sem execução/gravação ativa involuntária. Respostas obsoletas não descrevem revisão nova. Serviços reais ausentes aparecem como indisponíveis, sem resultados fictícios.
### F7C — parâmetros/cadastro/importação/ordenação
CRUD tipos/origens/offset/âncora/formato/destino/vínculos e catálogo/importação guiados; cadastro rico/política sem movimento; ordenação executável distinta do layout. Segredos novos ou alterações somente por contrato seguro e referência, mantendo integridade de publicação. Concluir parâmetros/propostas e herança do pipeline no draft.
### F7D — lineage e Maestro
Consulta/manutenção de lineage vinculada à definição, importação e publicação completas e hash consistente. Maestro existente recebe contexto de draft, propostas revisáveis aplicadas ao draft; jamais execução/publicação automática ou exposição de segredo. Edição preserva histórico publicado.
### F8 — desempenho
Medir antes/depois com mesmos cenários50/100/300nós. Meta APIp95<500ms, interação canvasp95<200ms, rota nova<300KBgzip, INP<200ms/CLS<0,1 quando mensuráveis no DEV. Hipótese e alteração isoladas, sem degradação de capabilities/permissões. Não chamar uma medição sintética de INP em campo.
### F9 — homologação e fechamento da matriz
Confrontar cada linha da matriz F6 com novo destino/cenário. Testar desenvolvimento/consulta/sustentação, negativas, publicação/restore/reload e projeção/reconciliação em fixture própria DEV, limites offline e rollback. Encerrar somente requisitos comprovados; marcar ensaios externos sem acesso como pendentes, sem declarar100% desses ambientes.

Todas as fases: uma PR para develop, QA adversarial antes da PR, segurança quando tocar entrada/auth/dados; pytest comparado com base, tsc-b, lint por assinatura zero NEW, dist final commitado, fontes sem NUL novos, backup verificado, migrations idempotentes, DEV saúde/versão/assets/smoke. Revisão independente visual e documentação DS conforme skill Impeccable. Autorização deste escopo já inclui continuidade e deploy DEV; não pedir nova aprovação da mesma execução.

## 6. Riscos
| Risco | Impacto | Mitigação |
|---|---|---|
| Reusar form que grava ativo | Violação de isolamento | Adaptadores puros e auditoria de chamadas, nenhum save legado |
| Proposta/import assíncrono em nó/revisão antiga | Perda de edição | Guardas atuais de identidade/lease/revision e cancelamento |
| Cifra no JSON/provedor | Vazamento | Ref imutável, contrato seguro, testes sentinela, ausência de segredo em evidências |
| Projeção/lineage sem hash | Publicação divergente | Expandir contrato/import/hash/projeção juntos e testar SQL real |
| Form extenso quebra referência | Uso confuso | Canvas central, editor expandido guiado, claro/escuro390/947/1440 |

## 7. Smoke pós-deploy
(a) entrar por novo/antigo link e editar no Fluxo; (b) configurar cada tipo, salvar/recarregar, comparar publicado intacto; (c) parâmetros/policy/import/preview e draft contextual; (d) negar ações sem permissão/lease e respostas atrasadas; (e) publicar/reconciliar versão/testSQL e restaurar; (f) medir cenário300nós e confirmar metas; (g) descartar fixtures e confirmar ausência de comandos/rascunhos ativos; (h) registrar limites de serviços externos.

## 8. Decisões
Spec original continua autoridade. PR490 removeu Etapas/lista e atualizou rótulos; não reintroduzir. Autorização explícita de 11/10/2026 cobre pontos listados, continuidade e referência/qualidade empresarial. Produção/main e funcionalidades futuras da seção9 original continuam fora. Estado de fechamento e evidências por fase no registro compartilhado e memória.

### Contrato da prévia estática F7B

A prévia de Valida Arquivo no editor recebe o grafo/configuração e somente diretórios String/Pathname fixos do rascunho local. POST /workspace-adapter/valida-arquivo/preview exige acao_editar, tela_pipelines, tela_jobs e workspace habilitado; não consulta cadastro publicado, banco, SSH, existência de arquivos nem secrets. É cálculo estático, não operação sobre uma identidade de rascunho no servidor. Guardas atuais de definição/lease/revisão/fence rejeitam aplicação e respostas antigas na UI. O save versionado e a publicação mantêm seus próprios contratos/autorização.

### Contrato seguro F7C — desenho de implementação

Valores Encrypted novos/alterados serão enviados apenas a endpoint write-only autenticado do adaptador com draftId, expectedRevision, fence, nome do parâmetro e escopo pipeline/etapa. O servidor confere sessão nativa atual, revisão, estado editável, ausência de publicação pendente e lease/fence dentro de transação com locks na mesma ordem do repositório. O segredo é cifrado por ORQUESTRA_CONN_KEY em tabela exclusiva; resposta contém somente referência UUID imutável com pipeline/job/parâmetro. Definition/layout, versões, auditoria, prévias, IA e evidências nunca contêm o valor/cifra. Cancelar não aplica referência ao draft; registros pendentes não são publicados. Referências registradas são validadas pelo .NET ao salvar e pelo adaptador ao projetar; valores históricos permanecem resolvíveis para restore. A projeção ativa recebe apenas a cifra no campo legado Encrypted. Nenhum GET resolve segredo. Referências antigas preservam o contrato anterior. Endpoint não grava tabela ativa nem muda revisão/definição.

Parâmetros de pipeline usam o editor compartilhado em staging e preservam campos adicionais por identidade; referências protegidas são consultáveis e removíveis com confirmação. Tipos comuns não podem capturar valores protegidos. Importação DataStage permanece consulta de declarações, aplicação explícita à revisão atual, sem executar jobs. Cadastro rico e ordem executável terão campos guiados; layout Organizar não modifica execution_order.

Referências legadas sem UUID recebem baseline imutável por versão. Captura inicial só ocorre quando o hash ativo comprova o snapshot corrente/base, em transação SERIALIZABLE; novas importações capturam no mesmo txn. Publicações seguintes copiam baseline histórico à nova versão. Restore sem baseline comprovado fica em consulta com motivo. Não inferir cifras históricas de versões antigas a partir do valor atual. A chave de cifra deve ser conservada; autenticidade HMAC é verificada sem decifrar na projeção. Não há GC nesta entrega, para preservar versões e restores.


### Contrato F7D — lineage e Maestro no rascunho

Importações e criações novas recebem `metadata.workspaceLineageVersion=1` e uma lista explícita `configuration.etl_job_lineage` em cada nó, inclusive vazia. Ausência significa captura histórica desconhecida. A marca é controlada pelo servidor e imutável no save; rascunhos ativos anteriores continuam editáveis no contrato anterior, preservando lineage ativo. Restaurar uma versão histórica sem captura comprovada gera rascunho somente para consulta com motivo persistido. Não reconstruir lineage histórico a partir do cadastro atual.

Importação lê lineage, definição e hash base na mesma transação SERIALIZABLE. As linhas preservam campos conhecidos e adicionais; associação órfã torna a importação somente para consulta. Publicação do contrato1 substitui todas as linhas do pipeline atomicamente com as demais tabelas, incluindo a lista vazia. Identidades técnicas e timestamps não são configuração. A projeção preserva duplicatas e não usa chave textual presumida para atualizar linhas sem chave funcional.

A migration de hash mantém o resultado anterior byte a byte no contrato0 e acrescenta lineage somente no contrato1. O procedimento recebe override explícito para captura base/publicação .NET; sem override, escolhe a versão da operação pendente primeiro (inclusive quarentena de erro), depois a versão confirmada. Ordenação de lineage usa representação canônica de todos os campos projetáveis, sem id/timestamps, independente da ordem de edição ou de reinserção. Expected/projection/inherited hashes devem permanecer no mesmo contrato; correção entre contratos é recusada. Não reescrever snapshots, hashes existentes ou operações pendentes anteriores.

Lineage tem consulta e formulário de origens/destinos/transformações no editor expandido, aplicado apenas à definição local. Importações dos extratores existentes retornam prévia e exigem aplicar explicitamente. Rotas legadas que gravam cadastro/header/cache não podem ser chamadas pelo draft. Indisponibilidade de DataStage/InformationServer é exibida como tal; nenhum resultado fictício. Metadados protegidos/defaults Encrypted não entram em JSON ou IA.

Maestro usa o provedor/catálogo existente por contrato específico de draft, com autenticação nativa, permissões, revisão e lease/fence conferidos no servidor. Declarações/defaults/contexto vêm do draft fornecido validado e da identidade salva, sem substituir por catálogo ativo. Propostas são revisáveis, nunca salvam/publicam/executam automaticamente. Contexto e saída são saneados, referências protegidas excluídas; resultado antigo não pode ser aplicado após mudança de nó, configuração, revisão ou posse. Conversas de draft têm namespace próprio.

Gates adicionais: marker falsificado/removido e lineage em posição alternativa recusados; histórico desconhecido em consulta; arrays vazios conhecidos publicados; reordenação sem mudança de hash, mudança de qualquer campo com conflito; captura/transação sem perda de linhas; divergência após projeção mantém gate; operação anterior continua retomável após migration; propostas atrasadas e segredos nunca chegam ao provedor/aplicação.


### Plano de medição F8 — 2026-10-11, antes das alterações
Base develop555af58a/DEV2.16.0. Cenários iguais50/100/300nós,25seleções e dois requestAnimationFrame até pintura,30amostras por endpoint através do proxy DEV; Chromium desktop sem throttle. Essa interação é proxy de laboratório, não INP de campo. APIp95 observado10,9–25,9ms, sem hipótese de mudança SQL. Canvasp95 antes72,0/133,0/216,0ms; CLS0,0010–0,0018. Main838238bytesgzip na medição determinística, acima do orçamento307200; medir também soma dos scripts efetivamente carregados pela rota para não esconder custo em chunks.

Hipótese1: imports síncronos de páginas alheias ao Fluxo trazem bibliotecas não usadas à rota inicial. Isolar carregamento por rota com lazy/Suspense da casa, mantendo login e casca síncronos, permissões/URLs e guardas idênticos. Medir bytes realmente carregados antes/depois e testar rotas diretas, erro, temas e entradas legadas. Um commit perf por hipótese.

Hipótese2 (condicionada ao perfil de execução): seleção reconstrói data de todos os nós, fazendo trabalho proporcional ao grafo. Usar identidade estável somente se perfil/medição confirmar trabalho no mapeamento/renderer; não virtualizar ocultando etapas nem reduzir capabilities para cumprir meta. Medir os mesmos50/100/300nós, preservando seleção, drag, Delete, ligação, decisão e save. Sem nova dependência.

Entrega F8 precisa revisão adversarial, gates da base, dist final e migration de versão; medir API novamente após DEV e comparar metodologias. INP de campo/Caixa permanecem externos quando não houver amostras reais. F7D smoke DEV concluído; registro final confirma três publicações e histórico em consulta, sem ensaio externo Caixa.

F8 hipótese1 refinada por medição: divisão de páginas reduziu main a187416bytesgzip, mas soma efetiva da rotaFluxo335151bytes ainda excede307200. Import estático de WorkspaceParameters traz JobTypeFields/catalog/importadores mesmo na abaFluxo; Operations/Versions também entram sem uso. Estender a mesma hipótese de carregamento sob demanda às abas, preservando casca/Fluxo/Dashboard/login síncronos e defaults/guardas. Sem hipótese nova ou reestruturação visual.

Resultado H1: scripts efetivamente carregados antes879418bytesgzip e depois239022bytesgzip, abaixo307200. Mesma rota fria, fixture e build de produção. Testes estáticos de registro Agentes/Utilitários aceitam ligação lazy equivalente; âncora sandbox de e-mail agora inspeciona também chunks da prévia para não omitir proteção após split (49focadosPASS). Perfil CPU300antes localizou WorkspaceFlowNode(tS) com28amostras e Handle(o_)24, autorizando isolamento de data/memo no renderer na H2.

Resultado H2: comparação isolada buildsH1/H2,50/100/300p95antes85,7/494,0/361,2ms e depois55,0/79,4/193,5ms; CLS0,00142. Todos abaixo200ms/.1 nessa rodada. BaselineF7D original72/133/216 mostra variância do host compartilhado; amostras brutas preservadas e números não são INP de campo. Definição/layout e número de nós/arestas preservados ao salvar. Gates finais Python7326PASS8conhecidas51skip; lint73/73/0NEW; build3PASS.

Confirmação H2 (fixture com arrayslineage explícitos em todos os nós):50/100/300p95antes83,7/158,2/273,3ms e depois65,6/99,9/113,3ms; CLSmáximo0,00181. Rodada inicial preservada em arquivospass1, ambas depoispassam<200. Nenhuma edição de UI entre as rodadas; confirmação resolve variância e contrato da fixture. Revisão visual independente F8ship,15capturas válidas; documenter preserva sistema incumbente.


### Plano F9 — antes da homologação final
Base developc71337dd/DEV2.16.1. Confrontar as19linhas do inventárioF6 e os11tipos com destinos atuais, separando prova de fonte, harness isolado e DEV real. Retestar capacidades/negativas e três experiências, salvar/recarregar próprio draft, versões/restore e projeção. Não executar serviços externos nem jobs por inferência; reutilizar provas SQL/offline quando fontes comprovadamente idênticas. Correções locais confirmadas nesta rodada entram na F9 com testes relevantes. Registrar política de restore/rollback sem destruir dados; preservar snapshots históricos. QA adversarial obrigatório antes da PR. Sem declarar paridade integral para campos ainda desconhecidos ou ensaios Caixa. Fechamento exige matriz explícita de comprovado/restrição/externo/pendente.


Achados F9 confirmados antes da correção: importação JSON alternativa cria nó sem arraylineage no contrato1; inicializar explicitamente no mesmo contrato. Cadastro precisa seleção de predecessores e janelas não-iniciar/limite existentes; staging deve alterar tabela relacionada e CSV juntos, preservar campos/linhas assinadas por malha, nunca chamar POST/DELETEdependencias no editor draft. Catálogo paginado/ciclo/indisponibilidade seguem controles existentes; validar servidor antes de projeção. Conferência DataStage deve usar projeto do draft e comando configurado, nunca projeto ativo; catálogo GET indisponível é aviso, não bloqueio nem execução. Aplicar sugestões somente com posse/identidade atual. Sem novaMalha ou novaexecução.


### Falha de restore confirmada no DEV F9 e correção pontual
PR496/DEVdf08be2a2.17.0 entregues, mas smoke nativo revelou que restaurar snapshot cuja tabela de dependências é vazia e CSV omitido removia linhas sem limpar o CSV ativo. Factory recusou divergência, preservando arquivo anterior/gate; não se declara F9 encerrada antes da recuperação. Derivar CSV somente quando ausente, incluindoNULL para tabela vazia, na projeção do snapshot. Valores explícitos divergentes continuam sujeitos à validação. Não reescrever snapshots/erro/gate nem alterar DAGs/.NET; corrigir pelo fluxo autorizado de nova revisão e operação corretiva, confirmando histórico, CSV/tabela/hash, restore e ausência de execuções. Branchfix/workspace-restore-dependencias; migration patch seguinte disponível163.


## Fechamento DEV — 2026-10-11

F9 encerrada no escopo DEV em2.17.1, fonte funcional22045507efde12118d19ba5aac03bf455ce7c7b4 (PR497), após PR496/2.17.0. A homologação revelou restore que removia tabela de dependências mas conservava CSV omitido pelo snapshot; factory recusou e preservou DAG/gate. A correção deriva o CSV ausente da tabela, incluindoNULL para lista vazia, sem mutar snapshot ou aceitar divergência explícita.

Recuperação real pelo rascunho original, nova revisão e publicação corretiva confirmou CSVNULL/tabela[]/gate liberado, com erro original e snapshots históricos preservados. Um ciclo independente confirmou cinco publicações: fonte sob demanda, filho vazio, filho com predecessor/janelas, restore do filho vazio, fonte inativada. UI salvou09:00/10:00 e recarregou sem diálogos Chrome ou erros JS; tentativa de assinatura compilada forjada recusada422. Fixtures próprias antigas e novas terminaram inativas/pausadas, sem execuções, drafts ativos ou comandos.

Fix7335PASS/8mesmas falhas/51skip/zeroNEW; lint73/73/0NEW; tsc-b/buildPASS com dist idêntico, zeroNULnovo (lineageIsx.ts preexistente preservado). QA adversarial e segurança manual sem bloqueios confirmados. Saúde/versão/assets15PASS;163migrations sem pendências; migration163 reexecutada duas vezes sem duplicação. BackupCOPY_ONLY/CHECKSUM/VERIFYONLY verificado. Somente API reiniciada. .NET/DAG/worker/offline inalterados, com provas de identidade do artefatoF7D. UI idêntica mantém revisãoF9SHIP/10capturas e negativas4/experiências16. Rota fria239973bytesgzip e APIp95máximo37,8ms medidos em2.17.0 são evidências anteriores reutilizadas para superfícies/contratos de leitura inalterados, não novas medições em2.17.1.

Evidências /root/orquestra-f9-restore-evidencias/{health-dev.json,recovery-dev.json,smoke-dev.json,migration-idempotence-dev.json,validation-summary.json,reuse-proofs.json}; conjunto inicialF9 em /root/orquestra-f9-evidencias. Fechamento documental não muda código executável nem versão; registrar seu SHA publicado separadamente da fonte funcional. Caixa/DataStage/InformationServer, IA real, INP de campo e planos SQL/IO permanecem ensaios externos. Não certificar100% desses ambientes nem promovermain/produção sem autorização.
