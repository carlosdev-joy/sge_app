# EOC-F10 — Adapters internos de E-mail e canal Teams

Entrega técnica independente dos gates de autoridade da F9. Não há rota nova,
worker de envio, alteração de job, de nós customizados ou de emissores legados.
`enqueue_result` continua 503; dispatcher continua fixture-only/dry-run/OFF.
Assim nenhum run pode emitir pelo legado e por estes adapters nesta entrega.

`alert_channels.resolve` lê exclusivamente a versão vinculada à corrida,
compara a revisão e a referência da intenção e verifica o evento selecionado.
E-mail gera um destino por referência de destinatário; canal consulta apenas o
ID ativo selecionado em `etl_msg_grupo`, sem fallback. Webhook fica somente em
RAM, fora de repr, erro, tentativa e respostas públicas. Usa a configuração,
validação MIME e `ssh_datastage.run_sendmail` existentes. O POST de canal segue
`ds_teams.enviar_card`, usando HTTPSConnection da biblioteca padrão, com validação TLS/hostname e
debug desativado por conexão. Não segue redirects, usa proxies do ambiente
ou imprime URL assinada em logs HTTPX. Aceita hosts específicos do Teams
legado e do Workflows (*.environment.api.powerplatform.com); preserva a query
assinada exatamente. A Microsoft documenta a troca de URLs do gatilho:
[alterações do HTTP/Teams Webhook](https://github.com/MicrosoftDocs/SupportArticles-docs/blob/main/support/power-platform/power-automate/flow-run-issues/triggers-troubleshoot.md).

`deliver` é harness interno: dry-run por padrão. Envio real requer opt-in e
fingerprint SHA-256 exata do canal/destino de teste explicitamente autorizado,
passada pelo operador em RAM. Não executamos envio real nesta fase. Não aceitar
fingerprint em future body HTTP como se representasse autorização do operador.
202/2xx ou rc0 = Accepted, nunca Received. Falha de rede ou exceção inesperada
= Unknown, sem retry. Erros guardam apenas código fechado; não copiam stderr,
URL, host SSH, destinatário ou corpo. Templates/anexos customizados permanecem
nos seus emissores próprios. A tentativa durável continua responsabilidade do
chamador: estes adapters ainda não são conectados ao dispatcher.

Reenvio interno exclusivamente dry-run: `replay_dry_run` aceita apenas fixtures
F9 em Failed/DryRun, com sequência esperada, ator confiável e motivo limitado
em UTF-16. Lock da intenção, atualização da tentativa encerrada com
replay_actor/replay_reason/replay_at e retorno a Pending usam o mesmo commit.
Accepted, Unknown, Leased e limite de quatro tentativas
não permitem reenvio. Histórico não é apagado; concorrência retorna 409.
O dry-run não estabelece autorização de reenvio real.

## Gates de ativação e cutover

Antes de ativar em clientes: certificar resultado agregado/Warning/geração de
Clear da F9; persistir transporte sob claim/fence; impedir o emissor legado para
o mesmo run/política em transação de publicação; manter runs legados inalterados;
validar reprocesso sem trocar snapshot; autorizar destino real de teste e provar
recebimento quando houver recibo. Unknown requer reconciliação auditada, nunca
reenvio cego. Não habilitar capability enquanto estes gates estiverem abertos.
F10 fica `technical_delivered_activation_pending`, sem aceite humano inventado.
A integração do adapter com a tentativa durável e o cutover são pendências
internas de código; autorização de destino e comprovação de recebimento são
validações externas distintas.

## Validação

Unitários para snapshot, grupo inexistente/inativo, destinos inválidos, ausência
de autorização, MIME/sendmail, 2xx/302/429/500/timeout, proteção de credencial (inclusive logs das bibliotecas),
audit/replay e conflitos. SQL Server isolado prova idempotência da migration182,
claim/replay concorrente, histórico e rollback. DEV mantém authority503/flagOFF;
smoke publicado usa fixtures próprias e transportes substituídos, sem envio.
Migration183 registra versão2.29.0. API restart somente, sem DAG/worker/UI.
