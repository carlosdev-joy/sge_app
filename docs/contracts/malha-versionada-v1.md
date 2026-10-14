# Malha versionada v1 — EOC-F16

Estado: modelo revisado pelo Codex principal e revisor independente, com
confirmação dirigida das lacunas de identidade/travas/hashes. Aprovação do
modelo antes de DDL; schema, implementação e ativação ainda não validados.
Base: DEV `f4a6ba1c250a2b1ac05ee9f7738aaeb0c64acacd` (2.34.0/schema194).
Não representa funcionalidade já entregue nem autorização para alterar produção.

## Autoridades existentes

`etl_malha`/`etl_malha_pipeline`/`etl_malha_no` e dependências globais
continuam sendo a projeção operacional. `etl_malha_execucao` identifica a
corrida; `etl_malha_execucao_membro` congela membros, ativo, raiz e participação
no fim, mas não registra definição ou versão do pipeline. Não reconstruir
histórico a partir do cadastro atual.

`etl_workspace_versao` contém definições imutáveis dos pipelines.
`etl_workspace_pipeline` e `etl_workspace_publicacao` determinam a versão
efetivamente publicada, com operação pendente e hash da projeção. Versão
importada não equivale a publicada. `sp_workspace_guard_run` exige versão
atual e rejeita reexecução divergente; F16 conserva essa guarda. Um vínculo
histórico não permite executar uma versão antiga pela DAG atual.

## Objetos candidatos

| Objeto | Conteúdo e invariantes |
|---|---|
| `etl_malha_versao` | UUID, nome NVARCHAR(200), número positivo único por nome, schema 1, definição JSON, layout JSON, hash SHA256, autor NVARCHAR(100), UTC. UPDATE/DELETE proibidos, sem cascata para cadastro. |
| `etl_malha_versao_membro` | PK(versão da malha, pipeline_name), FK para versão imutável da malha e UUID exato de `etl_workspace_versao`, hash dessa versão. Identidade do pipeline deve coincidir com a versão referenciada pela collation da origem. Sem referência `latest`. |
| `etl_malha_rascunho` | UUID, nome, base_version_id opcional, definição/layout JSON, revisão positiva, estado ativo/descartado/publicado, autor/responsável/UTC. Um ativo por nome. Escrita com revisão esperada, conflito 409; restore cria novo draft, nunca altera versão nem corrida. |
| `etl_malha_versionamento` | UUID estável PK, nome NVARCHAR(200) UNIQUE com collation da origem, versão efetiva opcional, revisão positiva, estado compatibilidade/gerido. Registro criado apenas por importação opt-in explícita. Ausência significa legado. |
| `etl_malha_corrida_versao` | corrida_id PK/FK sem cascata, versão imutável da malha FK, hash, capturada_em UTC. Inserção no mesmo commit da abertura e snapshot; nenhuma atualização. A corrida é a chave, ODATE não substitui a corrida. |

Versões e drafts carregam também o UUID estável do registro de versionamento.
A FK de versão efetiva precisa comprovar esse mesmo UUID, não apenas existir.
Rename e exclusão de malha que possua registro de versionamento são recusados
com 409 nesta entrega, inclusive rename case-only e transferência de nomes;
suporte futuro exigirá contrato próprio de identidade. Malhas legadas mantêm
rename existente. Não remover cadastro e recriar para contornar a guarda.

Membros históricos referenciam a relação imutável da versão da malha, sem
duplicar o conteúdo do pipeline. Corridas legadas não recebem vínculo por
backfill. Ao consultar corrida sem vínculo, apresentar `legacy_unversioned`
e referências indisponíveis, nunca a versão efetiva atual.

Definição inclui membros, nós canônicos e dependências com origem/autoria,
configurações de fechamento e agenda próprias da malha. Layout tem hash
separado e não muda ordem executável. Dependências globais continuam
autoridade de execução; divergência entre projeção e definição impede
ativação, não é corrigida silenciosamente.

Hashes não são intercambiáveis: `definition_hash` cobre JSON canônico da
definição da malha (UTF-8, chaves ordenadas, separadores compactos, sem NaN),
`layout_hash` cobre somente apresentação pelo mesmo algoritmo. `content_hash`
do membro é copiado exatamente da versão workspace, cujo algoritmo inclui
definição e layout; `projection_hash` é o valor de `sp_workspace_active_hash`
confirmado pela operação publicada e revalidado no protocolo workspace.
Não recalcular hashes workspace pelo algoritmo da malha. Vínculo da corrida
conserva `definition_hash`; layout pode ser exibido da versão escolhida e não
prova configuração de execução. DTOs identificam cada hash pelo seu nome.

## Opt-in e leitura de compatibilidade

Leitura legada continua disponível usando permissões existentes da Malha.
A API de versões responde capability indisponível/503 com migration nominal
quando schema falta. Modo compatibilidade é somente leitura nesta superfície:
não importa automaticamente, não resolve pipeline legado por aproximação,
não cria versões ao consultar. Rotas legadas conservam sua semântica.

Importação explícita cria draft com retrato atual para revisão. Membro sem
versão workspace publicada é impedimento nominal; sua definição legada não
é convertida em uma versão supostamente histórica. O usuário deve publicar
esse pipeline pelo workspace antes de publicar a definição da malha.
Nenhuma importação executa pipeline, republica DAG ou envia comunicação.

## Publicação e concorrência

Publicação exige permissão existente de edição de Malha e `acao_publicar`,
revisão esperada e UUIDs explícitos de membros. Não reutiliza autorização de
leitura. Autor vem da sessão, nunca do payload. Ausência ou UUID de outro
pipeline retorna erro nominal; nenhum fallback para última versão.

Uma transação adquire primeiro o recurso global existente
`orquestra.workspace.dependencies`, depois os recursos
`orquestra.malha.versionamento.<UUID canônico>` em ordem de UUID, depois
linhas workspace dos membros em ordem determinística pela collation SQL,
antes de ler projeção. Todos usam `sp_getapplock` Exclusive, proprietário
Transaction, timeout limitado e retorno negativo tratado como conflito.
Não derivar recurso de nome: applock compara bytes enquanto nomes SQL podem
equivaler por case/acento/espaços. Opt-in trava primeiro o recurso global e
resolve/cria UUID sob UNIQUE e UPDLOCK/HOLDLOCK, consultando o nome com a
collation da coluna; por isso aliases equivalentes não criam duas identidades.
Todos os caminhos de abertura
(API, DAG, guardiã) e publicação/opt-in participam da mesma trava. Rollback
desfaz abertura, vínculo e snapshot juntos. A adesão a corrida já existente
somente lê seu vínculo; não insere membros ou versões novos nessa corrida.

No instante da publicação, cada referência deve ser a versão efetiva
confirmada, sem operação pendente, e ter hash válido. O publicador workspace
usa as mesmas linhas com UPDLOCK/HOLDLOCK; a captura de todos os membros
ocorre sob uma única transação, nunca consultas independentes por conexão.
Deadlock implica rollback/retry limitado da operação inteira.

No instante de abertura, revalidar versão, hash de projeção e dependências
contra definição efetiva antes de inserir snapshot. Divergência ou schema
ausente em malha gerida falha fechada: não abrir corrida legada por fallback.
Uma corrida nova pode escolher somente a definição efetiva confirmada.
Captura e execução continuam protegidas pelas guardas workspace existentes.

Durante corrida aberta, publicação de nova definição da malha é recusada
com 409. Mudança posterior de pipeline não reescreve versões da corrida;
antes de executar/reexecutar um membro, discrepância com a referência
capturada impede execução e informa criação de nova corrida. Não prometer
execução de DAG histórica: esse recurso exigiria outro contrato/motor.

Não basta travar o novo publicador: antes de ativar modo gerido, todas as
escritas legadas de membros, nós, agenda e dependências que atingem a malha
precisam de guarda transacional compartilhada, inclusive dependências
globais de pipeline que pertença a várias malhas. Malhas afetadas são
travadas em ordem de UUID após o recurso global, antes das linhas workspace;
alteração gerida fora do protocolo é
recusada. Projeção publicada exige intenção servidor identificada e auditada.
Enquanto essa cobertura não existir, a capability de autoria/ativação
permanece indisponível; contrato e leitura podem ser entregues separados.

## Restore

Restore recebe UUID de versão da própria malha e revisão esperada. Cria
draft com base nessa versão e suas referências exatas. Draft ativo existente
causa 409; não descartá-lo implicitamente. Referência histórica indisponível
é erro visível, nunca substituição. A publicação futura revalida as guardas;
restore não muda projeção, versão efetiva, agenda, corrida ou DAG.

## Sequência e evidências exigidas

1. Revisão principal do modelo e revisão adversarial independente antes DDL.
2. Contrato/leitura com schema aditivo inerte, sem migração automática.
3. Autoria/opt-in somente com cobertura comprovada de todas as guardas.
4. QA: duas corridas/mesmo ODATE; publicação concorrente à abertura;
   corrida antiga sem vínculo; versão ausente/outro pipeline/importada;
   restore com draft ativo/stale; schema faltante; permissões negativas;
   publicação workspace concorrente; caminhos API/DAG/guardiã em paridade.
5. Suíte final por candidato contra baseline pinada, revisão independente,
   PR develop, backup DEV, migrations idempotentes e smoke com fixtures limpas.

Incremento contrato/leitura: migrations 195 (schema inerte) e 196 (versão);
GET `/malhas/{nome}/versionamento`, `/malhas/{nome}/versoes/{UUID}` e
`/malhas/{nome}/corridas/{id}/definicao`. Autenticação segue os GETs legados.
Nenhuma superfície de autoria ou ativação é exposta neste incremento.
IDs de corrida aceitam somente BIGINT positivo; `latest` não é um UUID.
Schema/fixtures de QA SQL foram revertidos; publicação DEV ainda pendente.
F16 permanece em desenvolvimento até critérios técnicos comprovados; gates
humanos/externos permanecem registrados no Backlog existente.
