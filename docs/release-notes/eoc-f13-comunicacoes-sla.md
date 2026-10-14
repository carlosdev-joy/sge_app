# EOC-F13 — Comunicações, tentativas e SLA

Entrega técnica DEV2.32.0; publicação e smoke devem ser registrados após execução.

Relatórios customizados conservam SQL, templates, colunas e anexos. E-mail obrigatório continua falhando a task e integra o resultado agregado do processamento. Teams customizado conserva o comportamento legado por padrão e oferece política explícita continuar/falhar, sem retry automático de mensagens incertas. Transporte principal permanece independente do resultado e não gera recursão.

Matrícula captura versão, política, inventário e fontes Warning da corrida original. Warning exige prova XCom da task/tentativa/mapIndex e instantes exatos; Clear reserva e confirma geração sob o mesmo lock do produtor. Polling não matricula corridas antigas nem retargeta publicação atual. Snapshot dry-run conserva comunicação principal legada. O modo original operational-test permite cutover por corrida; perda de autorização pausa a entrega e não reativa legado que poderia duplicar mensagens.

Produtor e dispatcher têm loops persistentes. Transporte operacional de teste exige `EOC_ALERT_OPERATIONAL_TEST=1`, matrícula opt-in `EOC_ALERT_ENROLLMENT_ENABLED=true` e autorização Admin temporária por fingerprints exatas. Todas permanecem OFF nesta entrega. O grant dura no máximo3600s, vive somente RAM no processo, expira/revoga e desaparece após restart. Multiplosworkers exigem afinidade ao processo autorizado; nenhum grant é distribuído implicitamente. Fixture dry-run mantém as flags internas existentes. Resolução e envio respeitam fence de lease; resultado incerto fica Unknown, sem retry cego. Fingerprint fora da autorização não recebe mensagem. A autorização de teste não habilita mensagens de negócio.

SLA mantém RISK/BREACH/PREDICT no registro existente com intenção persistente; Pending sobrevive restart. Claim e tentativa são atômicos; expiração encerra Unknown com histórico preservado. Recuperação administrativa por ID exige request UUID, estado esperado, motivo limitado e ator da sessão. Unknown exige confirmação explícita de possível duplicação. Repetição do pedido é no-op mesmo após worker consumir a fila; mudança de identidade409. Payload/destino original nunca são editados pela recuperação. Reenvio principal também conserva sequência e histórico, limitado a quatro tentativas.

Admin → Comunicação → Teams pessoal permite cadastro write-only, referência Connector aprovada e lookup de destinatário, com readiness explícita e sem alegar consentimento ou recebimento. Provider/configuração cifrada vieram F11 e continuam protegidos. Accepted não significa Received.

## Deploy DEV

Backup SQL COPY_ONLY/CHECKSUM e VERIFYONLY antes do merge publicado. Aplicar188 geração Clear,189 intenção SLA,190 histórico/recuperação,191 transporte de teste e192 versão/Backlog, idempotentes. A191 remove a cerca antiga exclusiva dry_run apenas para permitir modo de teste gated; não altera eventos existentes. Atualizar API/UI/dist, DAG factory/SLA/utils e reiniciar worker que cacheia utils. Não regenerar nem executar pipelines de clientes. Prova de factory usa DAG própria fora do DagBag/scheduler. Compose DEV utiliza env-file e arquivos existentes, restart apenas serviços afetados, sem up global/banco/volumes. Nenhuma promoção main/produção.

## Gates externos no Backlog

Tenant/app/permissões mínimas/instalação/referência Microsoft, destino real de teste especificamente autorizado e seu recibo; piloto humano nos três perfis; Caixa/DataStage e benchmark upstream para5s. São distintos dos contratos internos implementados. Fixtures nativas e mocks não certificam100% desses critérios. Estado final técnico deve ser technical_delivered_external_pending até confirmação humana/externa.
