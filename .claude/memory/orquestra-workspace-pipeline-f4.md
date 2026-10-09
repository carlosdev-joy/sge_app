# Workspace Pipeline — F4

Autorização do usuário: seguir até o final da F4. Branch feat/pipeline-workspace-f4, base develop a21de862. Código e testes em /root/orquestra-workspace-f4; evidências /root/orquestra-f4-evidencias. Publicação/validação/versões/compare/restore e policy de motor implementados. Integração/deploy DEV e smoke ainda são gates pendentes neste snapshot pré-PR; não afirma entrega.

SQL144: intenção/registry/execução, source hash, guards legados/reservas, queued_at vs confirmação; 145: release minor. .NET não escreve legado. Claim token/deadline e epoch/CAS corrigem retomada e reabertura. Recovery corretivo persiste inherited_projection_hash; nunca liberar gate por erro pré-projeção que herdou efeitos.

Consulte docs/contracts/workspace-publications-v1.md, docs/release-notes/workspace-pipeline-f4.md e docs/workspace-f4-ameacas.md. Main/produção separadas; F5/F6 fora desta fase. Registro final compartilhado terá PR/SHA/DEV/validações confirmadas.

## Verificação final antes do PR

.NET64PASS0FAIL0SKIP em SQL isolado; Python7169PASS/8falhas preexistentes/51SKIP, zero novas falhas. TS/build passam; lint166erros12avisos sem novas assinaturas. Navegador sintético13checks aprovado; revisões independentes adversarial/segurança e impeccable aprovadas. Pacote offline-ship68NuGet/127checksums, consumidor sem rede/cache61PASS3SQLSKIP; SQL coberto separadamente. Imagem sha256:06c0bd25b8fe5c0489910feee9a547f09ede4fa11763bdcefbc1d22a75259772. PR/merge/deploy/smoke DEV ainda são passos seguintes; esta nota não afirma entrega.
