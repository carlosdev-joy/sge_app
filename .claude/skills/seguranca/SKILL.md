---
name: seguranca
description: Processo de segurança para features e projetos — threat model rápido, checklist OWASP prático (authn/authz, injeção, XSS, CSRF, secrets, rate limiting, validação de entrada), LGPD e supply chain. Use quando o usuário pedir para revisar segurança, fazer security review, threat model, auditoria, hardening, pentest de mesa, "isso é seguro?", proteger endpoint/API/credencial, ou antes do PR de qualquer feature que toque autenticação, dados pessoais, secrets ou entrada de usuário. Palavras-chave: segurança, vulnerabilidade, OWASP, LGPD, security, threat model, auth, injection, secrets, hardening. Aplica-se a projetos web (Orquestra FastAPI+React, LC Decorações/NexxaFarma Next.js+Supabase), apps e automações (n8n).
---

## Quando usar

- Antes de abrir PR de feature que toque: auth, permissões, entrada de usuário, secrets, dados pessoais, novo endpoint, nova dependência.
- Quando o usuário pedir revisão de segurança, auditoria, ou perguntar "isso é seguro?".
- Ao integrar serviço externo (API, webhook, credencial n8n, chave de IA).
- NÃO substitui a revisão adversarial multi-agente pré-PR — complementa com foco exclusivo em segurança.

## Processo

1. **Threat model rápido (5 min, sempre primeiro)** — responda por escrito:
   - **Entradas**: quais dados entram e de onde (form, query param, body JSON, webhook, arquivo, coluna de banco de origem)?
   - **Quem acessa**: qual perfil/permissão consegue chamar cada endpoint/tela? Anônimo alcança algo?
   - **O que vaza se falhar**: pior cenário concreto (conversas de clientes, connection strings, CPF/CNPJ, chaves de IA).
2. **Mapear a superfície do diff**: liste endpoints novos/alterados, queries SQL, campos de formulário, variáveis de ambiente, tabelas novas. É contra ESSA lista que o checklist roda.
3. **Rodar o checklist OWASP prático** (abaixo) item a item contra a superfície mapeada. Marcar cada item com evidência (arquivo:linha), não de memória.
4. **LGPD**: identificar dados pessoais (nome, CPF/CNPJ, telefone, e-mail, conteúdo de conversas) em: logs, tabelas de log/auditoria, respostas de API, mensagens de erro. Ex. real: `etl_caixa_chat_log` guarda conversas inteiras — precisa de política de retenção e acesso restrito por permissão.
5. **Supply chain**: dependência nova?
   - Orquestra: pip é OFFLINE (`--no-index --find-links=wheels`) — toda dep entra como wheel em `api/wheels/` versionado no git. Isso é um vetor CONTROLADO: revise o wheel adicionado (nome, versão, hash, procedência do download) no diff do PR.
   - Front/Next.js: `npm audit` no lockfile; desconfiar de pacote novo com poucas semanas/downloads.
6. **Invocar a skill embutida `security-review`** no diff da branch para varredura automatizada e cruzar com os achados manuais.
7. **Relatar**: achados ordenados por severidade, cada um com arquivo:linha, cenário de exploração concreto e correção proposta. Corrigir só com autorização do usuário (fluxo padrão: fases F1..Fn, usuário autoriza merge).

## Checklist

- [ ] **Authn/Authz**: todo endpoint novo do Orquestra tem `require_perm(...)` com a permissão certa (padrão RBAC via perfis + `etl_usuario_permissao`)? Testou acesso com usuário SEM a permissão (espera 403, não 500 nem dados)?
- [ ] **Injeção SQL**: todo pyodbc usa placeholders `?` — zero f-string/`.format()`/concatenação com valor de usuário em SQL. Nomes de tabela/coluna dinâmicos (que placeholder não cobre) validados contra whitelist/regex `^[A-Za-z0-9_]+$`.
- [ ] **XSS**: nada de `dangerouslySetInnerHTML`/`innerHTML` com dado de usuário; se inevitável, sanitizar. Conteúdo vindo de IA/chat renderizado como texto, não HTML.
- [ ] **CSRF**: endpoints mutadores exigem token de sessão em header (não só cookie); webhooks n8n com auth (header secret), nunca URL "secreta" sozinha.
- [ ] **Secrets**: credenciais cifradas com Fernet/`ORQUESTRA_CONN_KEY`; chaves de API são write-only — respostas GET retornam mascarado (`sk-***`, padrão do caixa_ia), nunca o valor. Nenhum secret em código, log, mensagem de erro ou commit.
- [ ] **Validação de entrada**: todo campo de body validado com `isinstance(x, str)` ANTES de `.strip()`/`.lower()` (bug real do caixa_chat: body com int/None → 500). Limites de tamanho e tipo em tudo que entra.
- [ ] **Rate limiting**: endpoints caros ou de auth (login, OTP, chamadas de IA) têm limite por usuário/IP? OTP do LC Decorações tem expiração + máximo de tentativas?
- [ ] **Erros**: `HTTPException` para usuário final NUNCA carrega `detail` com internals (traceback, connection string, path). Erro de configuração/infra vira 503 genérico ("serviço indisponível"); detalhe real só em log servidor.
- [ ] **LGPD**: dados pessoais em log/tabela de auditoria justificados, com acesso restrito por permissão e retenção definida; logs de aplicação não imprimem CPF/telefone/conteúdo de conversa.
- [ ] **Supabase (LC Decorações/NexxaFarma)**: RLS habilitado em tabela nova; policy testada com anon key; rodar `get_advisors` do MCP Supabase após migration.
- [ ] **Colunas de banco**: tamanho de VARCHAR comporta o valor real — token cifrado com Fernet é ~1.4x maior que o claro + overhead base64 (bug real: coluna estourou com token cifrado). Testar com o MAIOR valor plausível.

## Integrações

- **`security-review`** (skill embutida): SEMPRE invocar no passo 6, sobre o diff da branch, antes do PR.
- **`code-review`** / revisão adversarial multi-agente: roda em paralelo para bugs gerais; esta skill cobre o eixo segurança que ela não aprofunda.
- **n8n + n8n-mcp-skills**: para credenciais e webhooks do n8n LC Segurança, usar o pack `n8n-mcp-skills` (em especial `n8n-mcp-skills:n8n-mcp-tools-expert` para `n8n_manage_credentials` e `n8n_audit_instance`) — nunca manipular credencial n8n "na mão".
- **MCP Supabase** (`get_advisors`, `list_tables`): auditoria de RLS e advisors de segurança nos projetos LC Decorações e NexxaFarma.
- **`verify`**: exercitar de fato o caminho negativo (usuário sem permissão, body malformado) — teste de segurança que só passa no caminho feliz não vale.

## Armadilhas conhecidas deste ambiente

- **`detail` de HTTPException vazando internals** (bug real corrigido): erro de configuração do provedor de IA retornava 500 com detalhe interno para usuário não-admin. Padrão correto: log completo no servidor, resposta 503 com mensagem genérica. Revisar TODO `raise HTTPException` novo com esse olhar.
- **`isinstance` antes de `.strip()`** (bug real do caixa_chat): JSON aceita qualquer tipo no campo; `payload["msg"].strip()` com int → AttributeError → 500. Validar tipo primeiro, sempre.
- **VARCHAR estourando com valor cifrado** (bug real): coluna dimensionada para o token em claro não coube o cifrado. Dimensionar para o pós-Fernet/base64 e a migration T-SQL deve ser IDEMPOTENTE (padrão `sql/migrations`, aplicada na etapa 6c do deploy.sh).
- **Nunca logar chave/token**: nem em `print`, nem em log de erro, nem em payload de retry do Airflow. Se precisa depurar, logue só os 4 primeiros caracteres mascarados.
- **Chaves write-only**: seguir o padrão do caixa_ia — endpoint aceita a chave no POST/PUT, GET devolve máscara. Qualquer GET que devolva secret em claro é achado crítico.
- **Wheels offline ≠ imunes**: o diff que adiciona `api/wheels/*.whl` é código de terceiro entrando em produção — conferir versão contra PyPI e origem do download no PR.

## O que NÃO fazer

- Não "corrigir" achados de segurança sem apresentar ao usuário primeiro — o usuário sempre autoriza merge e mudanças de comportamento.
- Não aprovar com base em "parece seguro" — cada item do checklist exige evidência arquivo:linha ou teste executado.
- Não duplicar o que `security-review`, `code-review` ou o pack n8n-mcp-skills já fazem — invocá-los e consolidar.
- Não montar SQL com f-string "só desta vez porque é nome de coluna" sem whitelist explícita.
- Não criar tabela de log com dado pessoal sem responder: quem lê, por quanto tempo, protegido por qual permissão.
- Não devolver mensagens de erro detalhadas ao cliente para "facilitar o debug" — detalhe vai para o log do servidor.
