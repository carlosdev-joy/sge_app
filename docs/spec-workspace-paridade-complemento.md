# Complemento executável: paridade do workspace — Orquestra
Data: 2026-10-11 · Status: autorizada, F7A/F7B entregues em DEV; execução F7C

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
