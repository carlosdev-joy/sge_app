# Publicação v1 — F4

Prefixo público DEV `/orquestra/workspace`. Exige flags Enabled, DraftsEnabled e PublicationsEnabled (default false), migration 144 e política do motor ativada no mesmo ambiente. A consulta de versões exige ambas as telas; comandos de publicação/retomada exigem Bearer, `acao_editar` e `acao_publicar`, além de lease vigente, fence e revisão. Experiência/nome de perfil não concedem privilégios.

| Método/caminho | Entrada | Resultado |
|---|---|---|
| POST drafts/{id}/validate | — | revision, valid, diagnostics (nodeId/field/code/message) |
| POST drafts/{id}/publish | operationId UUID, expectedRevision, fence | 202: operação persistida, nunca confirmação antecipada |
| GET drafts/{id}/publications | — | últimas 20 operações, permitindo retomar acompanhamento após reload |
| GET publications/{id} | — | estado/versão/revisão/tentativas/erro sanitizado e timestamps |
| POST publications/{id}/retry | mesmo operationId, revisão atual da operação, fence vigente | mesma operação/versão/run; não duplica publicação |
| GET pipeline-versions?name=... | identidade exata | últimas 100 versões sanitizadas, estado confirmado/importado/não confirmado |
| POST pipeline-restores?name=... | versionId publicado | 201: novo rascunho; não ativa a versão |

A comparação é por campo da definição/layout no cliente, sem cifras. Restore usa a fonte atual para captura de hash base; referências protegidas só podem resolver a localização atual original. Parâmetros removidos não ganham um segredo histórico por restauração.

## Intenção, projeção e confirmação

A intenção captura versão imutável e evento na mesma transação serializable que verifica lease/revisão/hash ativo/reservas. Repetir o mesmo operationId/revisão/fence retorna a mesma operação; colisões são 409. Rascunho importado antes da F4 não possui hash base: preserve suas alterações, descarte/reimporte a base e reaplique antes de publicar.

O .NET não escreve fontes ativas. Adapter FastAPI lê exclusivamente o snapshot persistido, valida novamente permissões/conexões/configuração e projeta a allowlist de oito tabelas em uma transação. Identidades seguem collation SQL; nomes de parâmetros binários permanecem distintos. Cifras são resolvidas apenas na mesma localização, dentro do adapter; fonte/histórico/auditoria só transportam máscara/referência/hash.

Estados persistidos: pendente → projetado → gerando → publicado; erro é terminal e mantém quarentena após efeitos. Claims possuem token/deadline e são conferidos sob lock em cada transição. Factory usa run id determinístico e valida operação/escopo/hash. Arquivo gravado atomicamente e seus marcadores AST, DAG serializada, ausência de import errors e pausa desejada precisam concordar antes de confirmar.

Consulta usa a última versão confirmada ou base importada inicial, jamais a projeção transitória. Nova pipeline permanece rascunho enquanto a DAG não foi confirmada.

## Execução e legado

Triggers bloqueiam alterações legadas dos pipelines geridos (incluindo lineage). Campos runtime, como last_execution/dag_criada/timestamps, não entram no hash de configuração. Reservas EXECUTANDO/RUNNING/QUEUED/AGUARDANDO/AGUARDANDO_DEPENDENCIA compartilham o lock da gestão e são recusadas durante publicação.

A política `config/airflow_local_settings.py` instala gate no pre_execute pelo task_instance_mutation_hook. Usa marcadores da DAG e queued_at confiável do registro Airflow, nunca conf/data lógica. Primeira entrada exige comando posterior à confirmação da versão; comandos anteriores/durante publicação não podem adotar uma DAG recém-parsed. Reabertura mantém versão/hash original e incrementa epoch; reconciliação terminal usa CAS para não apagar reabertura concorrente. Relógios UTC do SQL e Airflow devem estar sincronizados.

## Recuperação

Retomar operação em erro revalida sessão/lease/revisão e mantém o run id. Factory failed ou artefato perdido após success pode ser regenerado pelo reset das tarefas daquele run exato. Não limpa corridas de terceiros.

Erro projetado permite corrigir/salvar o mesmo rascunho e publicar uma nova revisão. Snapshot anterior continua imutável. Intenção corretiva só assume erro do mesmo draft e compara hash atual com a projeção herdada; persistir inherited_projection_hash impede abrir a quarentena mesmo se a correção falhar antes da própria projeção. Descarte fica bloqueado enquanto há projeção não confirmada. Retry da operação antiga não aceita revisão nova.

Erro antes de quaisquer efeitos libera a intenção sem alterar configuração anterior. Dependências temporárias retomam automaticamente após restart; falhas de configuração requerem correção/retomada explícita. Gates fail closed. Operações e versões não são expurgadas nesta fase.
