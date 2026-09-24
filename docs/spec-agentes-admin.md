# Spec: Agentes pela tela de Admin — prompt editável e criação de agentes

**Data:** 2026-09-23 (rascunho `c7cff0f` da equipe, revisado com as decisões do usuário no mesmo dia)
**Status:** ✅ ENTREGUE — A0–A2 + BK-1 e B1–B4 (PRs #432, #434–#438; release note `docs/release-notes/agentes-admin.md`)
**Base:** `docs/spec-agentes-datastage.md` (F0–F7 entregues, PRs #419–#431)
**Prioridade:** Alta — hoje cada ajuste de prompt exige editar código, `docker cp` e restart da API

---

## 1. Problema

O prompt do agente DataStage e o catálogo de agentes estão em código (`api/services/agentes.py`). Hoje, para ajustar
uma frase do prompt, é preciso:

1. editar o arquivo;
2. copiar para o container;
3. reiniciar a API.

Foi assim que a equipe passou a corrigir o prompt direto em produção (22–23/09), e cada correção teve de ser
portada à mão para o repo. Criar um agente novo exige uma entrega de desenvolvimento inteira.

## 2. Decisões (usuário, 23/09/2026)

| # | Decisão |
|---|---|
| D1 | **Duas fases na mesma spec.** **A:** editar o prompt do DataStage pela tela, com versões e sem deploy (resolve a dor principal). **B:** criar agentes novos. |
| D2 | **Um agente novo pode fazer as duas coisas.** Na criação, o admin escolhe entre **só conversa** (sem ferramenta) e **um subconjunto das ferramentas que já existem**. Ferramenta nova continua **só por PR**: a configuração só restringe a allowlist do código, nunca amplia. |
| D3 | **Acesso dos agentes novos: manual ou por perfil.** Manual = concessão usuário a usuário, como hoje. Por perfil = todo usuário do perfil escolhido. O modo `tela_padrao` do rascunho sai. O **DataStage continua só manual e só para `desenvolvedor`**, como decidido em 21/09. Restrição da revisão de segurança (**confirmada pelo usuário em 23/09**): o acesso **por perfil só vale para agente sem ferramenta que toque servidor** (`dsjob`, `isx_extrair`, `dsx_consulta`) e **nunca** para o perfil `consulta`, que é o perfil dado a quem entra sem cadastro. Agente com essas ferramentas é só manual, pelo mesmo motivo do DataStage (§4.2). |
| D4 | **O admin edita só a parte do domínio do prompt**: instruções, ordem de uso, armadilhas e tom. O **protocolo** é montado pelo código e aparece na tela **só para leitura**. Protocolo = bloco de ferramenta, catálogo e allowlist, trava de projeto, formato de propostas e aprendizados, e regras de segurança. |

Decisões técnicas tomadas junto (resolvem os pontos 5, 6, 8 e 9 do rascunho):

- **T1 — Versões, nunca edição por cima.** Cada gravação cria uma versão nova, com texto, quem gravou, quando e o
  motivo. Restaurar também cria uma versão nova, com o texto antigo. Nada é apagado nem atualizado no lugar.
- **T2 — Sem cache.** O prompt é lido do banco **a cada pergunta**, na mesma conexão curta que já lê a config. Uma
  leitura por índice custa quase nada perto dos segundos da IA, e acaba o problema do cache de 60 s *por processo*:
  a API roda com 2 workers, e o `PUT` só limparia o cache de um deles.
- **T3 — O DataStage não vai para a tabela de agentes.** Ele continua no `CATALOGO` do código, com os interruptores
  que já tem (`agentes_enabled` + `agente_datastage_enabled`). Os agentes do banco têm um `ativo` próprio. Assim
  nenhum agente tem três interruptores (ponto 6 do rascunho), e o kill switch geral `agentes_enabled` continua
  derrubando **todos**.
- **T4 — Migrations 120 (Fase A) e 121 (Fase B)**, idempotentes: toda migration pode rodar 2×.
- **T5 — Tudo entra na `AgentesTab.tsx`** que já existe (interruptores, gateway, limites, "Quem pode usar",
  "Curadores"). Não nasce outra tela.

---

## 3. Fase A — prompt do domínio editável

### 3.1 Separar domínio e protocolo (A0, sem mudança de comportamento)

Hoje `_prompt_sistema()` é um texto único. Ele passa a ser **montado em blocos**:

| Bloco | Origem | Editável |
|---|---|---|
| 1. Contexto da conversa: projeto resolvido ou "pergunte o projeto antes" | código | não |
| 2. Domínio: quem é o agente, ordem de custo, armadilhas, como ler SEQUENCE/PARALLEL, como responder | versão ativa do banco; sem versão, o **padrão do código** (`PROMPT_DOMINIO_PADRAO["datastage"]`) | **sim** |
| 3. Protocolo de ferramentas: formato do bloco JSON, ferramentas do agente com args obrigatórios, **comandos do `dsjob` gerados da allowlist** (anti-drift) | código | não |
| 4. Segurança: o agente nunca altera o DataStage, nunca inventa o que não veio de ferramenta | código | não |
| 5. Propostas e aprendizados: formato, limites, regra da evidência literal, nunca propor senha/token/valor de parâmetro | código | não |
| 6. Aprendizados validados, anexados como hoje | banco (curadoria) | não |

- Os blocos 4 e 5 são os do DataStage. Um agente só-conversa (Fase B) recebe a **variante genérica** do bloco 4:
  - nunca inventar o que não sabe;
  - nunca pedir, repetir nem propor senha, token ou credencial;
  - dizer claramente quando não tem acesso ao dado.

  Ele não recebe os blocos 3 e 5. O formato de resposta ("como responder") é do domínio em todos os agentes.
- O padrão do código é **o texto de hoje** dividido nesses blocos. As únicas mudanças no texto:
  - saem do domínio a linha `Comandos disponíveis: {comandos}`, a seção "Como usar as ferramentas" e o aviso "Chamadas
    que já falharam…", que vão para o protocolo (3), junto com a linha nova "Ferramentas disponíveis: …";
  - vão para os blocos fixos as frases de segurança.
- Ordem de montagem: **1 → 6**, na ordem da tabela.
  - O contexto (1) vem antes do domínio, como no texto único de antes. O domínio manda "resolver_projeto primeiro",
    e o modelo precisa já saber que o projeto está resolvido para não gastar uma rodada à toa (revisão da A0). Ele é
    um fato da conversa, não uma regra, então o domínio não tem o que sobrescrever nele.
  - Os blocos 3–6 vêm **depois** do domínio. Assim, o que o admin escrever não passa por cima do protocolo.
- Como a ordem das seções muda, a A0 é validada **em produção logo depois do deploy** com as perguntas reais da
  sessão de 22/09. O DEV não tem o gateway de IA nem o DataStage. Se alguma resposta piorar: na hora, gravar
  uma versão do domínio que reforce a instrução; definitivo, uma PR na montagem dos blocos. **Não reverter a
  #432** — as fases seguintes dependem dela (ver `docs/release-notes/agentes-admin.md`).
  As perguntas:
  1. filhos de uma sequence;
  2. colunas de um job PARALLEL;
  3. status da última execução;
  4. job com prefixo `SsdPrs_*` sem projeto.

### 3.2 Modelo de dados — migration 120

```sql
IF OBJECT_ID('dbo.etl_agente_prompt', 'U') IS NULL
CREATE TABLE dbo.etl_agente_prompt (
    id            INT IDENTITY PRIMARY KEY,
    agente_id     VARCHAR(40)    NOT NULL,
    versao        INT            NOT NULL,          -- 1, 2, 3… por agente; a ativa é a MAIOR
    texto         NVARCHAR(MAX)  NOT NULL,          -- só o bloco de domínio
    motivo        NVARCHAR(200)  NOT NULL,          -- obrigatório: "por que mudou"
    origem_versao INT            NULL,              -- preenchido quando é uma restauração
    criado_em     DATETIME2(0)   NOT NULL DEFAULT GETDATE(),   -- BRT, como a 117
    criado_por    VARCHAR(20)    NOT NULL,
    CONSTRAINT uq_agente_prompt_versao UNIQUE (agente_id, versao)
)
```

- **Sem linha = versão 0 = padrão do código.** Não se grava semente: o padrão continua vivendo no código e acompanha
  as PRs. Restaurar a versão 0 grava o padrão atual como versão nova.
- O `UNIQUE` barra duas gravações simultâneas com o mesmo número. Quem perde recebe 409.

### 3.3 Backend

- **Leitura por pergunta:** `_preparar_conversa` lê a versão ativa (`SELECT TOP 1 … ORDER BY versao DESC`) na
  mesma conexão da config.
  - Se a leitura falhar (tabela ainda sem a 120, erro de driver), o **DataStage** usa o padrão do código e registra
    log `warning`, e o chat não cai. Um **agente do banco** não tem padrão no código: nesse caso responde 503
    `agente_prompt_indisponivel`.
- **Rastreio:** a resposta grava `{"prompt_versao": n, "prompt_hash": "<12 hex>"}` em `artefatos_json`, ao lado de
  `duracao_ms`. O hash (sha256 do domínio usado) diferencia os "padrão do código" de deploys diferentes, que
  compartilham a versão 0. O `_separar_artefatos` ignora chaves que não conhece.
- **Endpoints** (admin, no mesmo router, sob `/agentes/admin/`):

  ```
  GET  /agentes/admin/agentes/{id}/prompt             → versão ativa, texto, "é o padrão?", parte fixa montada (leitura), limites
  PUT  /agentes/admin/agentes/{id}/prompt             → {texto, motivo, versao_base} → cria a versão seguinte
  GET  /agentes/admin/agentes/{id}/prompt/versoes     → lista (versão, quando, quem, motivo, tamanho, origem)
  GET  /agentes/admin/agentes/{id}/prompt/versoes/{v} → texto de uma versão (v=0: padrão do código)
  POST /agentes/admin/agentes/{id}/prompt/restaurar   → {versao, motivo, versao_base} → cria versão nova com aquele texto
  ```

- **Validação ao gravar** (422 com `code`):
  - `prompt_vazio` / `prompt_grande`: texto entre 1 e 50.000 caracteres depois do `strip` (era 20.000; ampliado por
    decisão do usuário em 23/09);
  - `motivo_obrigatorio`: motivo com 3 a 200 **unidades UTF-16** (`utf16_len`, porque é o que o `NVARCHAR` conta; o
    mesmo vale para nome, descrição e perfis na Fase B);
  - `prompt_com_marcador`: o texto contém marcadores reservados do protocolo (`<ferramenta`, `</ferramenta`,
    `<aprendizados`, `"ferramenta":`, `"propostas":`, `"aprendizados":`). O domínio não pode imitar o protocolo;
  - `prompt_com_segredo`: **valor** com cara de credencial. O prompt vai para o gateway de IA a cada pergunta. A
    regra **não** é o `redigir()`: ele casa `senha`, `token`, `secret` e `Encrypted` em qualquer lugar da linha e
    recusaria texto normal ("nunca peça a senha", "parâmetros Encrypted", o stage `TokenizerTransform`,
    "secretaria"). A regra nova (sem diferenciar maiúsculas) recusa só:
    - **chave = valor:** `(?<![a-z0-9])(senha|password|passwd|pwd|secret|token|api[_-]?key)(?![a-z])`
      seguido de aspas opcionais, `:` ou `=` com espaços opcionais na mesma linha (inclusive o U+00A0 de
      texto colado), aspas opcionais e um valor de **6 ou mais
      caracteres** sem espaço, aspas, `,`, `;` ou `}`, que **tenha dígito ou símbolo**.
      - Como `_` não é letra nem dígito, `DB_PASSWORD=…`, `client_secret=…` e `access_token=…` casam sem um grupo de
        prefixo, e o estilo JSON também casa (`"senha": "…"`). A A1 tirou o grupo `(?:[a-z0-9]+_)*` do rascunho:
        ele deixava a regex quadrática, com ~10 s de CPU para 20.000 caracteres.
      - **Não conta como segredo** um valor que seja referência ou marcador, em forma estrita: `#PS_X.Y#` (com os
        dois `#`), `$PS_X.Y`, `<valor>`, `****` ou o início de um JSON (`{…`, `[…`). `$enha123!` e `#abc123`
        continuam recusados.
    - **formatos conhecidos:**
      - `(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}` (pega `sk-ant-api03-…` e `sk-proj-…`; "risk-" e "disk-" passam);
      - `Bearer` seguido de 20 ou mais caracteres de token;
      - blocos `-----BEGIN … KEY-----`.

    Regra testada em Python em 23/09 (3ª revisão da spec). A A1 prende em teste as mesmas frases, e **o prompt
    padrão inteiro não dispara**:

    | Recusa | Aceita |
    |---|---|
    | `senha=Abc123`, `PWD=Xk2!pz`, `api_key=9f8e7d6c5b` | "nunca peça a senha ao usuário", "Senha: nunca peça" |
    | `DB_PASSWORD=Abc123!`, `client_secret=Xy9zAbcdef`, `access_token=abcdef123456` | "parâmetros do tipo Encrypted", "o stage TokenizerTransform", "secretaria de vendas" |
    | `"senha": "Abc123"`, `password: S3nh@Forte` | `pwd=#PS_ORA.PWD#`, `senha=$PS_BD.senha`, `password: #PS_CONEXAO.password#` |
    | `sk-ant-api03-…`, `sk-proj-…` | `senha=********`, `PWD=<valor>`, `token: {"job_name": "X"}` |
    | `Bearer eyJhbGci…`, `-----BEGIN RSA PRIVATE KEY-----` | "risk-assessment…", "disk-usage", "o token expira em 1 hora" |
  - `agente_desconhecido` (404): id fora do catálogo.
- **Concorrência:** `versao_base` diferente da versão ativa → **409 `prompt_mudou`**, com a versão atual no corpo. A
  tela avisa "outro admin gravou antes de você".
- **Parte fixa na tela:** o `GET` devolve os blocos 1 e 3–5 montados com um projeto de exemplo, só para leitura. O admin
  vê exatamente o que vai junto com o texto dele.

### 3.4 Front (A2)

Na `AgentesTab.tsx`, a seção **"Prompt — {nome do agente}"**:

- Editor monospace de ~20 linhas, com contador de caracteres, campo **Motivo** (obrigatório) e botão **Salvar
  versão**.
- Indicação da versão ativa ("versão 4, por 123456 em 23/09 14:02", ou "padrão do código").
- Aviso: "vale a partir da próxima pergunta, sem reiniciar nada".
- **Parte fixa (montada pelo Orquestra)** recolhida, só leitura.
- **Histórico de versões**: lista com quem, quando e o motivo; "ver texto"; **Restaurar** (pede motivo). Mostra a
  "versão 0 — padrão do código".
- 409 `prompt_mudou`: mensagem e botão para recarregar a versão nova **sem perder** o texto digitado, que fica
  copiável.

### 3.5 Critérios de aceite da Fase A

1. Sem nenhuma versão gravada, o prompt montado tem **todos os trechos obrigatórios** de hoje, cada um no bloco
   certo: regras de sequence, eco tardio, `pipeline_name`, inferência de projeto, formato de propostas e
   aprendizados. Os testes verificam trechos, como `test_agentes_rodadas_sequence.py` já faz, e não uma foto do texto.
2. Gravar uma versão muda a resposta **da próxima pergunta**, nos dois workers, sem restart.
3. Restaurar cria versão nova. Nenhuma linha de `etl_agente_prompt` é apagada nem alterada.
4. Um texto com marcador reservado ou cara de credencial é recusado com 422 e **não** grava.
5. Duas gravações com a mesma `versao_base`: a segunda recebe 409.
6. Com a tabela ausente ou com erro de leitura, o chat funciona com o padrão do código.
7. Só admin lê ou grava (`get_admin_user`). Não-admin recebe 403.
8. Cada resposta registra a `prompt_versao` usada.

---

## 4. Fase B — criar agentes

### 4.1 Modelo de dados — migration 121

```sql
IF OBJECT_ID('dbo.etl_agente', 'U') IS NULL
CREATE TABLE dbo.etl_agente (
    agente_id        VARCHAR(30)   NOT NULL PRIMARY KEY,  -- slug ^[a-z][a-z0-9_]{2,29}$; nunca reaproveitado
    nome             NVARCHAR(100) NOT NULL,
    descricao        NVARCHAR(500) NOT NULL,
    acesso           VARCHAR(10)   NOT NULL
        CONSTRAINT ck_etl_agente_acesso CHECK (acesso IN ('manual', 'perfil')),
    perfis_json      NVARCHAR(200) NOT NULL,              -- ex.: '["desenvolvedor"]' (nunca vazio)
    ferramentas_json NVARCHAR(400) NOT NULL,              -- '[]' = só conversa; senão subconjunto da allowlist
    ativo            BIT           NOT NULL DEFAULT 0,
    criado_em        DATETIME2(0)  NOT NULL DEFAULT GETDATE(),
    criado_por       VARCHAR(20)   NOT NULL,
    atualizado_em    DATETIME2(0)  NOT NULL DEFAULT GETDATE(),
    atualizado_por   VARCHAR(20)   NOT NULL
)
```

- O slug tem no máximo **30** caracteres. Assim `agente_<slug>_curador` (45) cabe no `recurso VARCHAR(50)` e
  mantém o prefixo `agente_`, que o `Admin.tsx` já tira da matriz de perfis.

- **Ids reservados**, recusados na criação:
  - os do `CATALOGO` do código (`datastage`);
  - as palavras das rotas (`admin`, `catalogo`, `status`, `conversas`, `propostas`, `aprendizados`);
  - **`curador` e qualquer id terminado em `_curador`**. Sem isso, o uso do agente `curador` seria o
    `agente_curador` (a curadoria do DataStage), e o uso de `foo_curador` seria igual ao curador de `foo`: um único
    grant daria dois papéis.
  - O `agente_do_recurso` passa a resolver por um mapa **exato** recurso → (agente, papel), montado com todos os
    agentes. Um recurso que aparecer duas vezes é erro de carga, nunca "o primeiro que achar".
- O prompt do agente novo usa a mesma `etl_agente_prompt` da Fase A. Criar exige o texto inicial, que vira a
  versão 1. Agente do banco não tem "padrão do código".
- **Desativar = `ativo = 0`.** Não existe exclusão: conversas, propostas e aprendizados ficam, e o slug não volta a
  ser usado.

### 4.2 Acesso

- Recurso de uso: **`agente_<slug>`**. Recurso de curador: **`agente_<slug>_curador`**, só para agente com
  ferramentas (só agente com ferramentas gera aprendizados). O DataStage mantém o `agente_curador`.
  - Hoje o `agente_do_recurso("agente_curador")` sempre devolve o DataStage. A B1 passa a resolver os dois recursos
    de cada agente, e os perfis elegíveis ao curador são os mesmos do uso.
- **Propostas e curadoria passam a ser por agente.** Hoje as rotas são do DataStage: `POST
  /agentes/propostas/{id}/decidir` exige `agente_datastage`, e `/agentes/aprendizados` lê e decide só a fila do
  DataStage, sem receber o agente.
  - Rotas novas: `POST /agentes/{agente_id}/propostas/{id}/decidir`, `GET /agentes/{agente_id}/aprendizados` e
    `POST /agentes/{agente_id}/aprendizados/{id}/decidir`, com acesso de uso e de curador daquele agente.
  - A proposta e o aprendizado precisam pertencer ao agente da rota; senão, 404.
  - As rotas antigas continuam como apelido do DataStage.
  - A tela chama as rotas com o agente selecionado.
- **Manual:** o admin concede `agente_<slug>` em "Quem pode usar", que já é montado a partir do catálogo. O
  `user_perm_set` só aceita o grant para os perfis de `perfis_json`. Para isso, `agente_do_recurso` e
  `elegivel_por_perfil` passam a enxergar o banco.
- **Por perfil:** quem tem um perfil de `perfis_json` usa o agente sem grant individual. Para ver o menu, o perfil
  também precisa da **`tela_agentes`**. O formulário avisa quando o perfil escolhido não tem a tela, e não a
  concede sozinho.
- **Catálogo híbrido:** todas as funções que hoje leem só o `CATALOGO` passam a enxergar o banco:
  `svc.agente()`, `catalogo_do_usuario`, `agente_do_recurso`, `elegivel_por_perfil`, `agente_ligado` e o catálogo
  do admin. Sem isso, `/agentes/conversas?agente=<slug>` e `/agentes/status` respondem 404 `agente_desconhecido`.
- A checagem de acesso (`require_agente`) vira dinâmica para as rotas com `{agente_id}`: procura o agente no código
  e, se não achar, no banco (um `SELECT` por chave). O DataStage continua com a checagem fixa de hoje.
- **Por perfil só sem ferramenta de servidor e nunca `consulta`** (D3). O `consulta` também fica fora dos perfis
  elegíveis do modo **manual**: não entra em `perfis_json` em nenhum modo. O `POST`/`PUT` recusa com 422
  `acesso_perfil_com_servidor` / `perfil_nao_permitido`.
  - O `require_agente` dinâmico também exige a **`tela_agentes`** do usuário. Hoje as rotas de conversa só olham o
    recurso do agente, e com acesso por perfil a API ficaria aberta a todo o perfil, mesmo sem o menu.
- Interruptor: `agente_ligado(cfg, agente)` passa a aceitar o agente do banco. Ele exige `agentes_enabled = "1"`
  **e** `ativo = 1`. Desligado → 503 `agente_desligado`, como hoje.
- Continua valendo o gotcha: **concessão manual nova exige novo login**. O modo por perfil vale na próxima
  requisição.

### 4.3 Execução

- **Rotas genéricas:**
  - `POST /agentes/{agente_id}/conversar` e `…/conversar/stream`, declaradas **depois** das do DataStage, que
    continuam exatamente como estão;
  - o front já chama `/agentes/${agente.id}/conversar`.
- O `conversar()` recebe a **configuração de execução** do agente: domínio do prompt e conjunto de ferramentas.
- **Só conversa** (`ferramentas = []`):
  - o prompt leva **só o domínio (2) + a variante genérica do bloco 4**. Não leva o bloco 1 (contexto de projeto
    DataStage, que mandaria "pergunte o projeto"), nem o 3, o 5 ou o 6. O formato de resposta é do domínio;
  - uma rodada só;
  - um bloco de ferramenta, proposta ou aprendizado que venha na resposta é **ignorado**: não executa e não grava;
  - não há projeto (o indicador de projeto, o grafo e a curadoria somem da tela desse agente).
- **Com ferramentas:**
  - o conjunto é um subconjunto de `resolver_projeto`, `base`, `dsx_consulta`, `dsjob` e `isx_extrair`;
  - qualquer ferramenta que precise de projeto **inclui `resolver_projeto` sozinha**;
  - o backend recusa, **antes** da allowlist, uma ferramenta fora do conjunto do agente. Ela entra como ferramenta
    falha, e o modelo é informado;
  - trava de projeto, guarda de reexecução, propostas, aprendizados, orçamento de 240 s, `MAX_RODADAS_FERRAMENTA`,
    teto de 2 rodadas por usuário, gateway e sonda: **tudo igual ao DataStage**, gravado com `agente = <slug>`.
- **Os blocos fixos seguem o subconjunto de ferramentas.** O contexto (1) só cita as ferramentas de projeto que o
  agente tem. As propostas (5) só entram se o agente tem ao menos uma ferramenta que lê job (`dsjob`, `isx_extrair`
  ou `dsx_consulta`), e citam só essas. Sem isso, o modelo pediria ferramentas que o backend recusa e gastaria
  rodadas.
- A identidade no gateway é a mesma do usuário, e a sonda é compartilhada entre os agentes.
- **A conversa é presa ao agente.** O `_preparar_conversa` passa a comparar `etl_agente_conversa.agente` com o agente
  da rota. Conversa de outro agente → 404 `conversa_nao_encontrada`, igual a conversa de outro usuário. Sem isso, a
  conversa herdaria projeto, histórico e falhas de outro agente.
- **Pontos com `AGENTE_DATASTAGE` fixo** que a B2 troca pelo agente da rota:
  - `agente_ligado(…)` e o INSERT da conversa em `_preparar_conversa`;
  - o INSERT das propostas em `_rodar_e_gravar_interno`;
  - `_registrar_seguro`, `_erro_conhecido_seguro`, `_recuperar_seguro` e `_rascunhos_pendentes_seguro`.
- **Fatos compartilhados, de propósito.** Os fatos lidos por ferramenta (`etl_agente_fato`) descrevem **jobs**, não
  agentes. O que um agente leu serve a todos, que é o objetivo da base.
  - A interpretação aprovada **mantém `origem = 'interpretacao_aprovada'`**. `origem` é `VARCHAR(30)`, e o código
    compara esse valor exato em `agentes_conhecimento.py` para mostrá-la como indício e não como fato lido.
  - O agente que a propôs vai numa coluna nova, `etl_agente_fato.agente VARCHAR(40) NULL`, que a migration 121
    acrescenta de forma idempotente. Ela é preenchida só na interpretação aprovada.

### 4.4 Endpoints de administração

```
GET    /agentes/admin/agentes            → código (só leitura, exceto o prompt) + banco
POST   /agentes/admin/agentes            → cria (slug, nome, descrição, acesso, perfis, ferramentas, prompt inicial, motivo)
PUT    /agentes/admin/agentes/{id}       → nome, descrição, acesso, perfis, ferramentas, ativo   (409 para agente do código)
```

- Validações: slug (formato, não reservado, não existente → 409 `agente_existe`); `acesso` ∈ {manual, perfil};
  perfis existentes e não vazios; ferramentas ⊆ allowlist; nome e descrição sem marcador de protocolo.
- O `RBAC_RECURSOS` do `Admin.tsx` é a segunda lista escrita à mão. Os rótulos `agente_<slug>` do editor de
  permissões passam a vir do catálogo da API, e não da lista.

### 4.5 Front (B3)

- `AgentesTab.tsx`:
  - **lista de agentes** (nome, id, origem código/tela, acesso, ferramentas ou "só conversa", ativo);
  - **+ Novo agente**: formulário com nome, id (só na criação), descrição, acesso (manual/perfil + perfis),
    ferramentas ("Nenhuma — só conversa" ou checkboxes) e prompt inicial com motivo;
  - editar e desativar;
  - a seção de prompt da Fase A vale para todos.
- `/agentes`: o seletor já lista o catálogo do usuário. Para agentes só de conversa, somem o indicador de projeto, o
  grafo e a aba Curadoria.

### 4.6 Critérios de aceite da Fase B

1. Um agente criado e ativado aparece no seletor de quem tem acesso **sem deploy**. Desativado, some para todos e a
   rota responde 503.
2. `agentes_enabled = 0` derruba o DataStage **e** os agentes do banco.
3. **Manual:** sem grant, 403; com grant de perfil não elegível, `user_perm_set` recusa. **Por perfil:** só os perfis
   listados usam, e só com a `tela_agentes`. Criar agente por perfil com `dsjob`/`isx_extrair`/`dsx_consulta`, ou com
   o perfil `consulta`, é recusado.
4. **Só conversa:** nenhuma ferramenta executa e nenhuma proposta ou aprendizado grava, mesmo que o modelo mande o
   bloco.
5. **Com subconjunto:** pedir uma ferramenta fora do conjunto falha antes de tocar o servidor.
6. O DataStage não muda nada: rotas, acesso manual, curadoria e interruptores. A suíte F0–F7 continua verde.
7. Id reservado ou repetido na criação: 422/409.
8. Conversa, proposta ou aprendizado de outro agente, pela rota de um agente → 404.
9. O curador de um agente não decide a fila de outro.

---

## 5. Riscos

| Risco | Mitigação |
|---|---|
| Prompt ruim publicado piora as respostas | histórico + restaurar em um clique; `prompt_versao` em cada resposta mostra quando piorou |
| Admin apaga uma regra de segurança do texto | as regras de segurança ficam nos blocos fixos (D4), e o backend continua impondo allowlist, projeto e régua de proposta |
| Domínio imitando o protocolo ou com segredo | 422 `prompt_com_marcador` / `prompt_com_segredo` |
| Reordenar o prompt na A0 muda o comportamento do DataStage | contexto do projeto mantido no topo; validação em produção logo depois do deploy, com as perguntas reais; se piorar, versão do domínio na hora e PR na montagem — não reverter a #432 (§3.1) |
| Agente com ferramentas dá acesso a SSH/ISX para mais gente | ferramentas só do código, subconjunto escolhido por admin, mesmos limites e travas; acesso por perfil exige ação explícita do admin |
| Correções direto no container voltarem | com o prompt no banco, ajuste de texto deixa de precisar de container; mudança de código continua por PR |

## 6. Entregas (uma PR cada, QA adversarial antes de abrir)

| Fase | Entrega | Deploy |
|---|---|---|
| **A0** ✅ #432 | separar domínio e protocolo em `_prompt_sistema`; teste do prompt montado — falta a validação em produção depois do deploy | API |
| **A1** ✅ #434 | migration 120 + leitura por pergunta + endpoints + validações + `prompt_versao` | 6c `s` (120) + API |
| **A2** ✅ #435 | editor, parte fixa e histórico/restaurar na `AgentesTab`, + **BK-1** (vigência, duração, respostas e tempo médio por versão) | API + `dist/` |
| **B1** ✅ #436 | migration 121 + CRUD admin + catálogo híbrido (todas as funções da §4.2) + acesso manual/perfil + checagem dinâmica com `tela_agentes` | 6c `s` (121) + API |
| **B2** ✅ #437 | rotas genéricas (conversa, propostas, curadoria) + conversa presa ao agente + execução só-conversa / subconjunto | API |
| **B3** ✅ #438 | admin: lista/criar/editar/desativar; `/agentes` adaptada; rótulos RBAC vindos da API | `dist/` |
| **B4** ✅ | manual (§3.12/§4.11), release notes (`docs/release-notes/agentes-admin.md`), `smoke_agentes.py` estendido | — |

## 7. Fora do escopo

- Ferramenta nova pela tela: continua só por PR.
- Acesso `tela_padrao` (qualquer um com a tela).
- Levar o DataStage para a tabela de agentes.
- Excluir agente de verdade.
- Comparar versões lado a lado (diff). Pode entrar depois, se o histórico pedir.

## 8. Backlog

- **BK-1 — Período de vigência de cada versão do prompt** (pedido do usuário em 23/09, durante a A1) — ✅ **entregue
  junto com a A2**. Fim **derivado**, sem coluna nova: o `criado_em` da versão seguinte é gravado no momento de versionar,
  e a regra T1 (só acrescenta) continua valendo:
  - ao versionar, guardar **início e fim** do período em que cada versão ficou ativa;
  - mostrar **quanto tempo** ela ficou em uso.
  - Para desenhar na hora de implementar:
    - O **início** é o `criado_em` da versão. O **fim** é o `criado_em` da versão seguinte. A versão ativa não tem fim.
      Dá para calcular sem mudar a tabela, mantendo a regra de nunca atualizar (T1). Se for preciso gravar o fim
      numa coluna (`vigente_ate`), vale abrir uma exceção à T1: um único `UPDATE` de NULL para a data, na mesma
      transação que grava a versão seguinte.
    - A **versão 0** (padrão do código) vale desde o deploy até a 1ª versão gravada. O início dela não está no banco.
    - **Uso real:** as respostas já gravam `prompt_versao` e `prompt_hash` em `artefatos_json` (A1). Isso permite
      mostrar, por versão, **quantas respostas** ela deu e o **tempo médio** de resposta (`duracao_ms`), além do
      tempo de calendário.
    - Tela: colunas "vigente de … até …", "duração" e "respostas" no histórico de versões (A2).
