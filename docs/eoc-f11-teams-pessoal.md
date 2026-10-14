# F11 — Provider Teams pessoal e readiness

Contrato técnico interno, com identidade e conversa resolvidas no snapshot da
corrida; `teamsPersonal` conserva sua própria intenção, separada de `email` e
`teamsChannel`. Rotas administrativas exigem admin existente; dispatcher e envio permanecem desligados.

Escolha técnica: mensagens proativas por app/bot instalado em escopo pessoal,
por Connector REST autenticado para tenant/app aprovados (sem dependência SDK nova). Graph é
usado somente para resolução GET: usuários por mail/UPN exatos, instalação no
escopo pessoal e conversa dessa instalação. Não criar chat comum nem usar
Graph app-only para postar mensagens; nenhuma permissão de migração.

`Configuration` é construída a partir da configuração cifrada administrada; tokens permanecem em RAM.
Readiness exige tenant/app UUID, aprovação administrativa, permissões e gateway
verificados. Default fechado. Estes flags são atestados administrativos, não
prova automática de consentimento ou de autenticação. O transporte concreto `AuthenticatedTransport` obtém OAuth client_credentials
no endpoint TLS fixo do tenant aprovado, com escopos separados Graph e
Bot Connector. Token opaco recebido diretamente da Microsoft, sem assumir
decode JWT como validação de assinatura. Segredo e tokens apenas RAM, sem
cache, proxy, redirect, retry ou logging. Gateway Graph usa GET autenticado.
Nenhuma credencial/configuração real existe nesta entrega e os testes não abrem rede. ID catálogo Teams é distinto do ID bot/Entra e do ID instalação.

A instalação expande teamsApp/teamsAppDefinition; a consulta do bot da definição
instalada deve retornar o app_id aprovado antes da leitura da conversa. Resposta
paginada incompleta falha fechada como provider indisponível, sem declarar usuário
inexistente ou app ausente. Não segue nextLink externo. Resolução exata detecta
ambiguidade e inexistência; ausência de instalação e vínculo incorreto são erros
fechados. 403/429 de OAuth ou Connector têm diagnóstico explícito, sem tentativa de
mensagem quando OAuth recusa. Não copiam corpo remoto, não fazem fallback/retry.

`deliver_target` encapsula o provider proativo; dry-run default não envia.
Envio de teste requer fingerprint exata tenant/app/user/conversation/channel,
fornecida em RAM por operador autorizado. Aceitação 2xx é Accepted, não Received.
Timeout/5xx/status desconhecido vira Unknown, sem retry. Nenhum teste real foi
feito; callback substituído não comprova tenant, consentimento ou recebimento.

## Gates e pendências

F11: validar tenant/app/manifest, permissões mínimas, instalação e destinatário
real antes de certificar operação. Transporte autenticado concreto usa stdlib,
sem dependência nova/offline. `ConnectorProvider` requer referência pessoal
explicitamente vinculada ao target/fingerprint; não presume que o chat ID Graph
é o conversation ID Connector. serviceUrl pública Teams fica em lista fechada
e deve vir de atividade verificada ou configuração administrativa aprovada.
Nenhum endpoint de bootstrap não autenticado foi criado.
Readiness de identidade não habilita o dispatcher. Autoridade agregada/ciclo,
claim/fence/tentativa durável e cutover F9/F10 continuam gates internos até F13.
Configuração administrativa reconciliada com etl_app_config e auth existente, sem auth paralela.

## Fontes primárias conferidas em 14/10/2026

- [Teams proativo](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/conversations/send-proactive-messages?tabs=python): instalação pessoal e identidade, sem envio direto por e-mail/UPN.
- [Listar usuários](https://learn.microsoft.com/en-us/graph/api/user-list?view=graph-rest-1.0): consultas Graph e permissões de diretório.
- [Apps instalados](https://learn.microsoft.com/en-us/graph/api/userteamwork-list-installedapps?view=graph-rest-1.0): GET pessoal; menor permissão application TeamsAppInstallation.ReadForUser.All.
- [Conversa instalada](https://github.com/MicrosoftDocs/msteams-docs/blob/main/msteams-platform/graph-api/proactive-bots-and-messages/send-personal-welcome-message.md): GET chat da instalação, não criação de chat.
- [Bot da definição](https://learn.microsoft.com/en-us/graph/api/teamworkbot-get?view=graph-rest-1.0): vínculo entre definição Teams e bot; consentimento administrativo deve incluir somente acesso necessário.

Fontes primárias adicionais (14/10/2026):
- [OAuth Graph](https://learn.microsoft.com/en-us/graph/auth-v2-service?tabs=http): client_credentials tenant-bound, Graph .default.
- [Autenticação Connector](https://learn.microsoft.com/en-us/azure/bot-service/rest-api/bot-framework-rest-connector-authentication?view=azure-bot-service-4.0): OAuth single-tenant e escopo api.botframework.com/.default.
- [Connector REST](https://learn.microsoft.com/azure/bot-service/rest-api/bot-framework-rest-connector-api-reference): serviceUrl confiável e POST v3/conversations/{conversationId}/activities.

## Administração cifrada

GET/POST `/teams-personal/admin/config` exigem `get_admin_user` existente.
POST recebe configuração completa: tenant_id, app_id, catalog_app_id,
client_secret e os booleanos admin_approved, permissions_verified,
gateway_verified. Ator vem da matrícula autenticada. GET devolve somente
configured/readiness/delivery_enabled; a credencial não volta ao cliente.
Os gates são declarações administrativas, não prova de validação no tenant.
`delivery_enabled` permanece false inclusive com readiness ready.

Payload cifrado Fernet em `teams_personal_config_enc`, etl_app_config existente;
limite VARCHAR(1000) medido depois da cifra. Payload excessivo é recusado antes
MERGE. Editor genérico recusa prefixo teams_personal_; listagem mascara `_enc`
e configuração pública omite a chave. Falha de chave/banco/cifra é sanitizada.
`teams_config.directory` constrói GraphDirectoryGateway autenticado sem chamada
externa durante bootstrap. POST `/teams-personal/admin/reference` exige referência completa e atestado
reference_verified=true do administrador sobre origem/conversa pessoal. Não
trata esse atestado como validação automática de atividade externa. Referência
cifrada em etl_teams_personal_binding (migration184), com ator de sessão e
fingerprint tenant/app/user/chat; user UUID normalizado como no Graph.
VARCHAR(MAX) comporta os limites pós-Fernet. Conteúdo não volta ao cliente.
POST `/teams-personal/admin/lookup` recebe somente email, consulta Graph após
gates administrativos e retorna readiness/fingerprint, sem IDs ou e-mail.
Referência ausente fecha como connector_reference_missing. Bootstrap valida
novamente conteúdo/fingerprint antes de construir provider; nunca envia.
Migration185 registra versão2.30.0 esperada sobre DEV2.29.0.
Este marco não habilita dispatcher. Dados pessoais da referência têm acesso
somente administrativo, cifra Fernet e uma linha por snapshot aprovado;
nenhuma retenção de atividades ou conteúdo de mensagem é introduzida.

Proteção de HTTP debug: set_debuglevel(0) em cada conexão impede que debug
global exponha o segredo OAuth ou Bearer; TLS/hostname permanecem obrigatórios.
Configuração e referência são administradas por API nesta fase; não foi criado
formulário visual adicional no Admin. A UI mantém somente o espelho de dono
da chave para impedir edição genérica. Evolução desse formulário deve acompanhar
a integração dos alertas antes do aceite operacional completo.
