# Spec — triagem de chamados com o gateway de IA da empresa

Status: **F1 em execução** · demais fases aguardando
Origem: painel `ritm_geresd_ed.html` (repo `sge`, pasta `chamado`), que hoje roda
na estação e produz o que a tela `/chamados` ainda não tem.

## 1. Visão

A tela `/chamados` já espelha o ServiceNow e mostra kanban, aging, tipo × estado,
fluxo de 14 dias e carga por responsável. O painel da estação foi além e resolve
outra pergunta: **este chamado tem informação suficiente para começar?** Ele
classifica cada RITM em `PODE INICIAR` × `RETORNAR AO SOLICITANTE`, lista as
lacunas, sugere as perguntas a devolver ao solicitante e propõe um responsável
pelo histórico de quem atendeu o quê.

Esta spec traz essa lógica para dentro do produto e, no caminho, dá ao Orquestra
um provedor de IA que funciona **dentro da rede da Caixa**: o gateway interno
`servicosstdev.caixavidaeprevidencia.intranet/api/claude/…`.

### O que o painel faz e a tela não

| Capacidade do painel | Existe em `/chamados`? |
|---|---|
| Kanban por estado, aging, carga | ✅ já existe |
| Veredito de suficiência (`PODE INICIAR` × `RETORNAR`) | ❌ |
| Lacunas identificadas e perguntas sugeridas | ❌ |
| Resumo de uma linha (`Tipo · Objeto · Pedido`) | ❌ |
| Tipo de demanda derivado do título/catálogo | ❌ |
| Categoria "dia a dia" extraída das work notes | ❌ |
| Objetos técnicos citados (DMDB, DM_, TB_, VW_, PRC_) | ❌ |
| Sugestão de responsável por histórico/especialidade | ❌ |
| Histórico de resolvidos dos últimos 10 dias | ❌ |
| Contadores por veredito e por tipo | ❌ |

### O que falta no espelho

`dbo.etl_chamado` (migration 088) guarda número, título, estado, prioridade,
responsável, grupo e datas. **Não guarda** `descricao`, `work_notes`, `catalogo`,
`demandante`, `prazo`/`due_date` nem `sla_vencido` — e sem descrição e work notes
não há triagem possível, nem por IA nem por heurística. Por isso a F2 vem antes
da F3/F4.

## 2. O gateway de IA da empresa

Extraído de `gerar_painel.py` (a implementação que já funciona na estação):

| Item | Valor |
|---|---|
| Endpoint | `http://servicosstdev.caixavidaeprevidencia.intranet/api/claude/chat/completions` |
| Autenticação | header **`x-api-key`** (não `Authorization: Bearer`) |
| Corpo | `{"model", "messages":[{"role","content"}], "max_tokens"}` |
| Resposta | **`content[0].text`** — formato Anthropic, apesar da URL `chat/completions` |
| Modelo em uso | `claude-sonnet-4-6` |
| Proxy | **nenhum** — host interno; o painel usa `CLAUDE_PROXIES = {}` |
| TLS | `http://` simples, `verify=False` no painel |

Nenhum dos dois provedores de `services/caixa_ia.py` atende isso: `anthropic` usa
o SDK oficial contra a API pública, e `openai_compat` manda `Authorization:
Bearer` e lê `choices[0].message.content`. Daí a F1.

⚠️ **O proxy é a armadilha desta integração.** O container `orquestra-api` recebe
`HTTPS_PROXY`/`HTTP_PROXY` do ambiente e o httpx, com `trust_env` (padrão), os
respeita. O gateway é intranet: sem `NO_PROXY` cobrindo `.intranet`, ou sem
desligar o `trust_env` na chamada, o pedido sai para o proxy corporativo e volta
como `ConnectError` — o mesmo sintoma de gateway fora do ar. É a repetição
exata do gotcha da PR #311 (ServiceNow) e do proxy que existia no
`orquestra-api` mas não no worker.

## 3. Fases

### F1 — O provedor do gateway e a prova de que ele conecta

- **Entregável:** provedor `caixa_gateway` em `services/caixa_ia.py` +
  configuração e **verificação visível** em Admin > Caixa Seguro IA.
- **Inclui:**
  - novo provedor com `x-api-key`, corpo `messages` e leitura de
    `content[0].text`, **com fallback** para `choices[0].message.content` (se o
    gateway mudar de dialeto, a resposta continua sendo lida);
  - `trust_env` desligado por padrão para este provedor — a rota é interna e o
    proxy corporativo não deve ser usado; um interruptor na config permite o
    contrário quando o gateway estiver atrás de proxy;
  - o `system_prompt` viaja como primeira mensagem `user` quando o gateway não
    aceitar campo `system` (é como o painel faz hoje);
  - **painel de verificação** na aba do Admin, substituindo o toast atual: mostra
    veredito, latência, modelo que respondeu, endpoint efetivo, se houve proxy no
    caminho e o trecho da resposta. Em falha, nomeia a causa (DNS, proxy,
    401 de chave, timeout, resposta em formato inesperado) — cada uma com o que
    fazer;
  - o resultado da última verificação fica **na tela**, com data e hora: um toast
    some, e a pergunta "isso está conectando?" precisa de resposta permanente.
- **Critérios de aceite:**
  - dado o gateway configurado e acessível, quando clico em Verificar conexão,
    então o painel mostra `conectado`, a latência, o modelo e o texto devolvido;
  - dado o gateway inacessível, então o painel diz **qual** camada falhou e não
    exibe "erro genérico";
  - dado que o ambiente tem `HTTPS_PROXY`, então a chamada ao gateway **não**
    passa pelo proxy, e o painel informa isso explicitamente;
  - dado um gateway que responde `choices[0].message.content`, então a resposta
    ainda é lida.
- **Validação:** pytest (provedor e sonda com mock de httpx) + tsc/eslint/build.
  ⚠️ O gateway só existe dentro da rede da Caixa: a verificação real contra ele
  é **smoke do usuário**, não automatizável aqui.
- PR: `feat: provedor do gateway de IA da Caixa e verificação de conexão`

### F2 — O espelho aprende o que a triagem precisa ler

- **Entregável:** migration 091 + campos novos na DAG de sync.
- **Inclui:** `descricao`, `work_notes`, `catalogo`, `demandante`, `prazo`
  (`estimated_delivery`), `due_date`, `sla_vencido` (`u_sla_expired`).
  `NVARCHAR` com truncamento explícito, como o `titulo` da 088 (o incidente
  NUM_CPF_CNPJ e o título com acento já ensinaram a lição).
- **Cuidado:** work notes carregam nome de pessoa e conteúdo de negócio — o
  espelho passa a guardar dado sensível que hoje não guarda. Decidir retenção e
  quem vê, antes de subir.
- **Critérios de aceite:** um chamado com descrição e work notes chega completo
  ao espelho; campo ausente na origem vira `NULL`, nunca string `"None"`.

### F3 — Agregação e contadores do painel na tela

- **Entregável:** derivações + contadores em `/chamados` e nos indicadores.
- **Inclui:**
  - **tipo de demanda** pelo título/catálogo (o `tipo_map` do painel: inclusão de
    coluna, ajuste em tabela, enriquecimento, extração, análise, consulta,
    auditoria, estruturante, relatório, dúvida, parametrização, restauração,
    processamento de arquivo, BUCC);
  - **categoria "dia a dia"** extraída das work notes (`dia a dia - <categoria>`,
    e `geral` quando vem sem categoria);
  - **objetos técnicos** citados na descrição (`DMDB…`, `DM_…`, `TB_`, `VW_`,
    `PRC_`), até 3 por chamado;
  - **histórico de resolvidos dos últimos 10 dias** como aba/rodapé, hoje
    invisível na tela (o kanban só mostra a fila viva);
  - contadores novos: por tipo de demanda, por categoria dia-a-dia, e
    ativos × resolvidos-10d — cada um com o denominador ao lado, regra da casa.
- **Onde a conta é feita:** no SQL, como já faz `/chamados/indicadores` — não na
  tela. As derivações de texto (tipo, categoria, objetos) são calculadas na
  **ingestão** e gravadas, não a cada request: regex por linha em toda leitura
  é desperdício e faz a tela variar conforme a versão do código.
- **Critérios de aceite:** a soma dos contadores por tipo bate com o total de
  ativos; tipo não reconhecido cai em "Demanda técnica" e **aparece**, em vez de
  sumir; dia sem resolvidos mostra zero explícito.

### F4 — A triagem propriamente dita

- **Entregável:** veredito, lacunas, perguntas e resumo por chamado, com
  fallback heurístico.
- **Inclui:**
  - o prompt do painel (JSON estrito, veredito binário, critérios de lacuna)
    disparado pelo provedor da F1, em lote na DAG — **não** no request da tela;
  - **fallback heurístico** (`_suficiencia_heuristica` do painel) quando a IA não
    responde: a tela nunca fica sem veredito por causa do gateway;
  - a tela **diz qual dos dois produziu** o veredito. Heurística apresentada
    como análise de IA é engano do operador;
  - sugestão de responsável por especialidade/histórico, marcada como sugestão;
  - interruptor próprio: a triagem não pode depender do `caixa_ia_enabled`, que
    hoje governa a visibilidade dos assistentes do Caixa Seguro.
- **Critérios de aceite:** gateway fora do ar → todos os chamados continuam com
  veredito, marcados como heurísticos; veredito da IA em formato inesperado →
  cai na heurística e registra o motivo, sem derrubar o lote.

## 4. Decisões

- **Uma configuração de provedor, vários consumidores.** As chaves `caixa_ia_*`
  passam a valer para todo o sistema, e não só para os assistentes do Caixa
  Seguro. O interruptor `caixa_ia_enabled` continua governando **apenas** a
  visibilidade dos assistentes — a triagem terá o seu (F4). Misturar os dois
  faria desligar o Diego desligar a triagem de chamados, sem que ninguém pedisse.
- **A triagem roda em lote, na ingestão.** Uma chamada de IA por chamado dentro
  do request tornaria a tela refém do gateway.
- **Sem escrita no ServiceNow.** As perguntas sugeridas são para copiar e colar,
  como no painel. Devolver chamado pela automação é decisão de outra spec.

## 5. Fora de escopo

Escrita no ServiceNow; substituir o painel da estação (ele continua útil como
bancada); e mover a análise para dentro do Airflow como DAG própria (a F4 usa a
DAG de sync que já existe).
