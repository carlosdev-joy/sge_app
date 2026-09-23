# Spec: Agentes de IA (tela `/agentes`) — agente de mapeamento DataStage — Orquestra
Data: 2026-09-21 · Status: **✅ ENTREGUE — F0 a F7 implementadas (PRs #419–#429 + F7, 22–23/09/2026)**. Dúvidas ainda abertas que não bloquearam a entrega (padrão conservador aplicado): D-01–D-05, D-07, D-08, D-09 (⚠️), D-19 (⚠️) — ver §8.1 e `docs/release-notes/agentes.md`

> Origem: entrevista de descoberta de 2026-09-21 (skill `entrevista-projeto`), Entendimento do Projeto
> **confirmado pelo usuário**. Esta spec é autossuficiente: quem a lê (inclusive um agente rodando no
> servidor de produção, sem o contexto da conversa) encontra aqui o que foi decidido, o que ainda é
> dúvida e como fechar cada dúvida. **A implementação só começa depois que o usuário aprovar a spec.**
>
> **Validação de produção de 2026-09-21:** D-06 e D-10 a D-15 fechadas por validação; **D-16 e D-17 fechadas por decisão do usuário**; D-09 ⚠️; abertas: D-01 a D-05, D-07, D-08 e D-18 a D-20. Ver §8.1 e §9.
>
> **Validação de produção de 2026-09-22:** **D-20 fechada** (`desenvolvedor` tem `acao_editar`); **D-19 ⚠️ parcial** (DSX ativo em produção, 92 registros `dsx_auto` — detalhe fino ainda aberto, padrão
> conservador aplicado). F0, F1 e F2 implementadas e mergeadas na main.

## 1. Visão

Engenheiros de dados gastam tempo para entender os fluxos DataStage que já existem (jobs, tabelas, campos,
lineage, parâmetros), lendo ISX/DSX ou o Designer na mão, e o que um descobre não fica registrado para o
próximo. A nova tela **Agentes** (`/agentes`) deixa cada usuário conversar com os agentes que lhe foram
liberados. O primeiro agente **consulta o servidor DataStage sem alterá-lo (lê e extrai definições) e a base do Orquestra**, explica o
fluxo e mostra o grafo, e **vai registrando** o que descobre (fatos, inclusive na lineage) e o que aprende sobre como acessar o
servidor, buscar a informação e ler os jobs — para consultar a base antes do servidor e não repetir erro.
Cada usuário é identificado no gateway de IA da Caixa por `cvp-<matrícula>`, e o gateway decide se ele pode usar.

## 2. Escopo

**IN**
- Tela **Agentes**, **habilitada pelo admin** no menu Admin (`tela_agentes`; nasce **só no perfil `admin`**), com **seletor mostrando só os agentes liberados
  para aquele usuário** (RBAC por usuário × agente, **decidido pelo admin**). Primeiro agente: **mapeamento de processos DataStage**.
- **Quem decide é o admin, pelo menu Admin.** O **admin já nasce com a tela e com todos os agentes** (ele sempre tem todos os menus e acessos); **ninguém mais nasce com nada**. O admin habilita a
  tela (`tela_agentes`) e concede **cada agente, usuário a usuário**. O agente DataStage só pode ser concedido a usuário do perfil **`desenvolvedor`** e **nunca por perfil**. Agentes futuros que
  expliquem o **negócio e as tabelas** poderão ter acesso mais amplo, com política própria.
- Chat em texto, **grafo do fluxo** (reaproveita o componente da Governança) e **links** para telas do Orquestra.
- **Consulta ao vivo ao DataStage sem alterá-lo**, pela API do Orquestra (`DS_SSH_*`): leitura por `dsjob` e **extração de definições (ISX) e **consulta aos arquivos DSX** que já existem em `DSX_BASE_DIR`**, com **base primeiro**:
  o servidor só é consultado quando a base não tem o dado ou ele venceu.
- **Gravação no banco para melhorar a lineage** (o que a extração descobre): job **em pipeline** → pelo mesmo caminho do botão da Governança (`etl_ds_job_isx` + linhas `isx_auto`);
  job **fora de pipeline** → `etl_agente_fato` (a regra "lineage só para job num pipeline" segue — **B-19**). Extrair exige que o **usuário** tenha `acao_editar`, como o botão.
- **Fatos** lidos por ferramenta são gravados direto, com origem e evidência. **Interpretações** do modelo viram
  **proposta**: o usuário na conversa aprova ou recusa; sem aprovação ficam só os fatos.
- **Base de aprendizados** (como acessar, buscar, ler jobs, detalhar; erros e correções): fatos comprovados valem
  na hora; **interpretações só depois de aprovação de um curador**. Recuperada por relevância, com semente inicial.
- **Histórico de conversas**: todas salvas por usuário; lista com busca; **retomar conversa de até 30 dias**.
- **Identidade no gateway**: `cvp-<matrícula>` da sessão; aviso na tela quando o usuário não está cadastrado no
  gateway (detectado por uma chamada mínima ao abrir a tela); "gateway indisponível" tratado como caso distinto.
- Interruptores liga/desliga (geral e por agente), **nascem desligados**; config no Admin.
- **Camada de IA compartilhada e desacoplada do módulo Caixa** (**F0**, pré-requisito): o serviço, a config e a aba do Admin deixam de se chamar
  "Caixa" e passam a servir o Maestro, a triagem, os agentes e módulos futuros (o módulo Caixa vai para outra ferramenta em breve).

**OUT (explícito)**
- Executar, reexecutar ou parar jobs; escrever no repositório do DataStage.
- **Alterar o DataStage**: importar, compilar, executar, parar ou apagar jobs e sequências; **extração em lote** (é só do admin, pela DAG `etl_lineage_extract_isx`). O que "for necessário" para
  trazer detalhes **não** é uma lista aberta: cada ferramenta nova entra por PR, na allowlist em código (**B-02**).
- **Logs de execução** (`logsum`/`logdetail`) como ferramenta do agente (podem conter valores de dados) — **B-03**.
- Exportar documentação (Markdown/PDF); outros agentes (entra só a estrutura de catálogo); autenticação nova.
- O Orquestra **cadastrar** o usuário no gateway (ele só avisa).
- Gravar conclusão do modelo sem aprovação.
- **Medir ou limitar tokens** (nenhum contador, cota ou meta de tokens no Orquestra).
- Streaming da resposta; apagar a própria conversa (**B-04**).
- **Ferramenta SFTP** no v1: as raízes ativas existem, mas não têm ISX/DSX úteis ao mapeamento (**D-11 ✅**, B-02b).
- **Remover ou migrar o módulo Caixa** (assistentes Diego/Lari/Léo, PIO, `etl_caixa_chat_log`, `tela_caixa_seguro`): outra entrega; aqui ele só passa a
  depender da camada nova, sem perder função.
- Conceder o agente DataStage **por perfil**, ou a quem **não** é `desenvolvedor` (o admin já o tem por ser admin).
- Alterar a identidade dos outros consumidores do gateway: Caixa Seguro e triagem de chamados **continuam
  com `cvp-orquestra`**.

**Backlog (fora desta spec):** ler o que entra e o que sai das conversas para gerar novas funcionalidades
(como a fila de "pedidos não atendidos" do Maestro). Exige política antes — **B-07**.

## 3. Arquitetura proposta

### Front (`ui-react/`)
- `src/lib/nav.ts`: `NavGroup` ganha `'Agentes'`; `NAV_GROUPS` recebe `'Agentes'` **imediatamente antes de
  `'Administração'`** (não reordena nada existente — regra de não mudar a ordem da tela; **B-01**); item
  `{ to: '/agentes', label: 'Agentes', icon: Bot, group: 'Agentes', perm: 'tela_agentes' }`.
- `src/App.tsx`: `PAGE_ELEMENT['/agentes']`. Sem subrotas: agente e conversa vão em query (`?agente=&conversa=`).
- `src/pages/Agentes.tsx` + `src/components/agentes/` (seletor, chat, aviso de cadastro, histórico, cartão de
  proposta, aba do curador, grafo inline) + `src/lib/agentes.ts` (constantes/tipos/helpers, no estilo de
  `lib/maestro.ts`). O chat segue os padrões de `components/etapas/MaestroChat.tsx` (referência, sem refatorar o Maestro).
- Grafo: reaproveita `components/governanca/isx/GrafoIsx.tsx` / `PainelJobIsx.tsx`, alimentado por
  `GET /lineage/isx/job` (só banco). **C-02** confere as props na F3.
- Admin: `pages/Admin.tsx` — `RBAC_RECURSOS` (linha ~36, a **2ª lista à mão**) ganha `tela_agentes`,
  `agente_datastage`, `agente_curador`; nova aba `components/admin/AgentesTab.tsx` (no molde de `MaestroTab.tsx`).
- Visual: tokens neutros do Orquestra (`canvas/panel/edge/ink`, claro e escuro), sem tema CAIXA. `dist/` recompilada
  em toda fase com front.

### Back (`api/`)
- `api/routers/agentes.py` (novo; registrado nas **duas** listas de `api/main.py`):

  | Método e rota | Guard | Função |
  |---|---|---|
  | `GET /agentes/catalogo` | `require_perm('tela_agentes')` | agentes que o usuário pode usar (catálogo em código ∩ **política do agente** ∩ interruptor) |
  | `GET /agentes/status?agente=` | `tela_agentes` | estado do gateway para o usuário (sonda, com cache) |
  | `POST /agentes/datastage/conversar` | `require_agente('datastage')` (admin passa; senão perfil `desenvolvedor` **e** grant manual) | uma rodada (orquestrada) |
  | `GET /agentes/conversas`, `GET /agentes/conversas/{id}` | `tela_agentes` + dono | histórico (só do próprio usuário; `404` se não for o dono) |
  | `POST /agentes/propostas/{id}/decidir` | dono da conversa | aprovar/recusar proposta |
  | `GET /agentes/aprendizados`, `POST /agentes/aprendizados/{id}/decidir` | `require_agente('datastage', curador=True)` (mesma política) | fila do curador |
  | `GET/POST /agentes/admin/config` | `get_admin_user` | interruptores, campo do gateway, texto de cadastro, teto SSH, validade |

- `api/services/agentes.py` (catálogo em código, prompt, orquestração da rodada, identidade), 
  `api/services/agentes_ferramentas.py` (ferramentas e allowlist), `api/services/agentes_conhecimento.py`
  (fatos, propostas, aprendizados, filtro de segredos). Módulos planos, como `maestro.py`.
- **Duas políticas de acesso, decididas pelo usuário em 21/09, com mecanismos DIFERENTES:**
  1. **A tela (`tela_agentes`)** é um recurso RBAC **normal**, checado por `require_perm('tela_agentes')` — **exatamente como qualquer outra tela** (`tela_jobs`, `tela_pipelines`…): perfil ∪ overrides
     por usuário, sem bypass nem código especial. Semeada (migration 117, MERGE) **só no perfil `admin`** (o mesmo padrão da 060 para uma tela nova e restrita) — é assim que o admin **já nasce com o
     menu**. Se o admin quiser abrir a tela a outro perfil (ex.: `desenvolvedor`), usa a **mesma tela Admin › Perfis que já existe** (`perfil_upsert`) — nenhum mecanismo novo.
  2. **Cada agente** (`agente_datastage`, e `agente_curador`) é **sempre por definição do administrador, usuário a usuário** — nunca por perfil, nem para o `desenvolvedor`. Isso é reforçado com o
     catálogo em código (`perfis_elegiveis=('desenvolvedor',)`, `concessao='manual_por_usuario'`) e com uma dependency própria, **`require_agente`**: **o admin passa sempre** (`PERM_ADMIN`/`acao_admin`,
     como já faz `require_ds_console` — é o que "o admin sempre tem todos os menus e acessos" quer dizer); o **não-admin** só passa se o perfil for **`desenvolvedor`** **e** o recurso estiver em
     `permissoes_extra` — a parte **só de overrides por usuário** que `carregar_usuario` já separa do que vem do perfil (`info["permissoes_extra"]`) — senão 403 `agente_nao_elegivel` ou
     `agente_nao_liberado`. **Defesa em profundidade contra o "por engano":** mesmo que alguém marque `agente_datastage` num perfil pela tela genérica de perfis, `require_agente` **ignora essa origem**
     para não-admin (só olha `permissoes_extra`); e a tela Admin › Agentes (F3) — o único lugar pensado para conceder agente — **não lista `agente_*` na matriz de perfis**, só no grant por usuário.
     `agente_curador` segue a mesma regra (**B-06**). Agentes futuros de negócio/tabelas poderão ter política mais ampla — a trava é deste agente, que toca o servidor DataStage.
- `api/services/ia_provedor.py` (renome de `caixa_ia.py` na **F0**) **estendido, sem quebrar os outros consumidores**: `chat_conversa(..., identidade=None)`,
  `_chat_caixa_gateway(..., identidade)` e `sondar_usuario()`. Sem `identidade` o corpo e os headers ficam
  **idênticos aos de hoje** (Caixa Seguro e triagem intactos). Hoje o código trata 401/403 como "chave recusada" e
  devolve 502; no caminho do agente o recusa vira um tipo próprio (`GatewayRecusou`) para separar *usuário sem
  cadastro* de *chave do app inválida*.
- **Sem tool-calling nativo.** O gateway recebe **uma única mensagem `user`** (`_corpo_gateway`; o histórico vai
  transcrito por `transcrever`), então o "agente" é **orquestrado pelo backend**: o modelo pede uma ferramenta num
  bloco ` ```json ` (mesmo padrão do Maestro), o backend **valida contra a allowlist**, executa, e devolve o
  resultado ao modelo como **dado delimitado**. No máximo 4 rodadas de ferramenta por pergunta (eram 3; ajuste de produção de 23/09/2026 — o fluxo resolver_projeto → isx_extrair → resposta precisava de espaço para uma ferramenta intermediária) e um **orçamento
  de tempo** (não só de quantidade — lição da triagem de chamados): **teto de 240 s** (`ORCAMENTO_AGENTE_S`), abaixo do
  `proxy_read_timeout 300s` da rota `/orquestra/` (D-14 ✅). É um **teto**, não uma meta: o backend controla o prazo por
  relógio (cada chamada ao gateway pode levar até 60 s e cada `dsjob` até 60 s) e o front mostra o andamento.
- **Ferramentas do v1 (allowlist em código; ferramenta nova só por PR):** (1) `base`: lê `etl_ds_job_isx`, `etl_job_lineage` (`isx_auto`) e `etl_agente_fato`;
  (2) `dsjob`: **`ljobs`, `lstages`, `lparams`, `jobinfo`, `report`** via `ssh_datastage.run_dsjob` (nomes por `^[A-Za-z0-9_.]+$`; **fora**: `logsum`, `logdetail`);
  (3) `isx_extrair` (**F2b**): `localizar` + `extrair` + `gravar` de `services/lineage_isx` — as **mesmas funções e o mesmo executor** (2 por processo, teto de 60 s, lock por job,
  cache por `lastModified`) do endpoint `POST /lineage/isx/extrair`, e **exige que o usuário tenha `acao_editar`** (o agente não abre atalho: sem ela, devolve o link da Governança);
  (4) `dsx_consulta` (**F2b**): **somente leitura** dos arquivos `.dsx` que **já existem** em `DSX_BASE_DIR` (`/opt/airflow/dsx`; o `orquestra-api` os monta `:ro`), pelo `DSXEngine` existente
  (`listar_dsx`, `listar_jobs`, `listar_pastas`, `buscar_campo`, `extrair`), importado como já faz `api/routers/lineage.py` (`_import_dsx_engine`); **não toca o servidor DataStage**; a resposta traz o
  **nome e a data do arquivo** (é um retrato, não o estado de agora); SFTP fora do v1 (D-11 ✅). O `istool export` cria um arquivo temporário privado no servidor
  (`DS_ISTOOL_TMP`, `umask 077`) — **é a única escrita no servidor DataStage**, já existente na Governança; nada altera jobs, sequências, projetos nem execuções.
  **Ordem de custo** (o agente tenta nessa ordem, **depois de resolver o projeto**): base → `dsx_consulta` (arquivo local; só se o projeto tem `.dsx`) → `dsjob` ao vivo → `isx_extrair` (uma JVM no servidor).
- **Resolução do projeto (decisão do usuário, 21/09)** — passo do orquestrador, **antes de qualquer consulta ao DataStage**. No começo da análise, se o projeto ainda não é conhecido, o chat **pergunta qual é
  o projeto**. O nome é validado **sem tocar o servidor**, contra: (a) o que a base já conhece (`etl_pipeline.project_name`, `etl_ds_job_isx.ds_project` — se o usuário cita um pipeline ou um job de pipeline,
  o projeto sai daí e **nem se pergunta**); (b) os arquivos `.dsx` de `DSX_BASE_DIR` (`listar_dsx`: o nome do projeto é o nome do arquivo). Resultado:
  - `projeto_com_dsx` → a **hierarquia do DSX** (projeto → pastas → jobs) fica disponível para navegar;
  - `projeto_sem_dsx` (o nome existe na base ou o usuário o confirma, mas não há `.dsx`) → o agente **pula a hierarquia do DSX** e consulta direto **ISX e produção (`dsjob`)** com esse projeto;
  - `projeto_desconhecido` (não bate com nada) → **nenhuma** consulta a ISX/`dsjob` com o nome não validado (é o que geraria várias consultas sem sucesso): o agente lista sugestões (projetos da base e
    dos `.dsx`) e pergunta de novo.
  O backend **impõe** isso: `dsjob`, `isx_extrair` e `dsx_consulta` **recusam** rodar sem projeto resolvido, seja qual for o pedido do modelo. Nome que só difere na **caixa** de um projeto conhecido →
  sugere o nome canônico e pede confirmação (nomes no DataStage são sensíveis à caixa). O projeto fica na conversa (`etl_agente_conversa.projeto`), é lembrado ao **retomar**, e o usuário pode **trocar** (o
  contexto de job recomeça). `dsjob -lprojects` é **candidato** a entrar na allowlist para confirmar o projeto no servidor (uma chamada barata, com cache) — depende da **D-07**.
- **Identidade (D-16 ✅, decisão do usuário):** `identidade_gateway(usuário)` = o **campo do cadastro** `etl_usuario.identidade_gateway` **se preenchido**; senão o **modelo padrão**
  `cvp-` + matrícula em **minúsculas** (`lower()` obrigatório: o banco grava em MAIÚSCULAS, `auth.py:38`). Sempre resolvida no servidor, a partir da **sessão** (`get_current_user`) —
  nunca do corpo. O campo é preenchido só por admin (Admin › Usuários), aceita `^[A-Za-z0-9._@-]{1,100}$` (vai em header: sem espaço nem quebra de linha), é **único** entre usuários
  (conferido ao salvar) e a tela mostra ao lado o valor padrão que valeria. Sem matrícula na sessão ⇒ **não chama o gateway**; e **nunca cai para `cvp-orquestra`** (isso faria todos
  agirem como o app e anularia a autorização por usuário). Para os 4 usuários que não seguem `CVP`+dígitos, um admin preenche o campo com o identificador que o gateway conhece; se
  ninguém preencher, vai o modelo padrão e o gateway responde "sem cadastro" (o aviso normal). O local do identificador na requisição (header ou corpo, nome do campo) é
  **configuração** até o contrato ser validado (**D-01**); sem ela, estado `sem_contrato` (agente desligado, sem chute).
- **Sonda de cadastro** (`GET /agentes/status`): chamada mínima ao gateway com a identidade resolvida (cadastro ou `cvp-<matrícula>`). Se voltar
  401/403, faz **uma chamada de controle com a identidade do app** (`cvp-orquestra`): controle OK ⇒ o usuário
  não está cadastrado; controle também falha ⇒ problema da chave do app/gateway, **não** do usuário.
  Estados: `ok`, `sem_cadastro`, `gateway_indisponivel`, `chave_do_app_invalida`, `sem_contrato`, `desligado`,
  `provedor_incompativel` (o agente exige o provedor `caixa_gateway`), `sem_matricula`. Cache por
  matrícula em memória: `ok` 10 min, `sem_cadastro` 60 s (a pessoa se cadastra e o botão "verificar de novo"
  funciona), `gateway_indisponivel` não é cacheado. Os TTLs finais dependem de **D-03**. O cache do usuário é **invalidado** quando o admin altera o campo `identidade_gateway`.
- Erros no formato `detail: {code, message}` (como `maestro_corpo_invalido`); o front decide pelo `code`, não pelo
  texto — o contrato `err.status` × `err.message` do `apiFetch` já causou bug.
- Purga por **DAG** em `dags/etl_log_cleanup.py` (nova tarefa `limpar_conversas_agentes`, retenção de 30 dias
  espelhada em `services/agentes.RETENCAO_CONVERSAS_DIAS`). Lá o placeholder é `%s` (pymssql); na API é `?` (pyodbc).
  A janela de 30 dias **também é imposta na leitura** (o `SELECT` filtra), então a regra vale mesmo que o `dags/`
  não seja sincronizado. (D-15 ✅: o `etl_log_cleanup.py` de produção já tem `limpar_conversas_maestro`; o deploy da F4 só
  acrescenta `limpar_conversas_agentes`.)

### Dados
Migration `sql/migrations/117_agentes.sql` (§4). Lê `etl_ds_job_isx`, `etl_job_lineage`; reaproveita
`etl_usuario_permissao` (RBAC por usuário) e `etl_app_config` (interruptores, config). Provedor de IA: **`caixa_gateway`**
já configurado em Admin › IA (hoje ainda "Caixa Seguro IA"; renomeada na F0); o modelo é o configurado ali (a spec não fixa modelo nem custo). D-06 ✅: em produção
é `caixa_gateway`, modelo `claude-sonnet-4-6`, `usa_proxy = 1`; o host tem "dev" no nome e **é o que a produção usa** (D-17 ✅: decisão do usuário — a ferramenta é de outra área e será trocada no futuro; o contrato do usuário fica em config para absorver a troca).

### Decisões e alternativas descartadas
- **Catálogo de agentes em código** (registro), não em tabela — descartado `etl_agente`: sem CRUD nem valor hoje.
- **Orquestração no backend** — descartado depender de `tools` do gateway (não confirmado) e descartado delegar a
  leitura ao Airflow (decisão do usuário: API do Orquestra direto, `DS_SSH_*`; síncrono e já existente).
- **RBAC por usuário em `etl_usuario_permissao`** (recursos `agente_*`) — descartada tabela própria agente×usuário:
  reaproveita a UI de grants e a invalidação de sessão. **`agente_*` não é semeado em perfil nenhum** e, para não-admin, só conta se estiver em `permissoes_extra` (por usuário) — mesmo que apareça num perfil por engano, `require_agente` o ignora; a
  concessão é sempre feita pelo admin, usuário a usuário. `tela_agentes` é diferente: é um recurso normal, perfil ∪ overrides, sem essa restrição.
- **Fatos em tabela própria** `etl_agente_fato`, não em `etl_job_lineage` — `etl_ds_job_isx` tem FK para
  `etl_pipeline_job` (o lineage ISX só existe para job que está num pipeline do Orquestra), então job fora de pipeline
  não cabe ali; e misturar dado do agente no lineage contaminaria o grafo da Governança.
- **Corpo de aprendizado de `erro`/`acesso` gerado por código** (modelo `ferramenta + saída-assinatura`), nunca texto
  livre vindo da saída da ferramenta — fecha a injeção persistente. Texto livre só em `interpretacao` (passa pelo curador).
- **Validade do dado:** ISX por `ds_last_modified` (a chave de cache que já existe); `dsjob`/SFTP por **prazo**
  (padrão 7 dias), porque `dsjob` talvez não exponha data de modificação (**D-08**).
- **Retomada de conversa:** reenvia as últimas 12 rodadas (teto do Maestro), sem guardar resumo.
- **Resposta única, sem streaming** (o Maestro também é assim; o gateway não confirmou suporte).

## 4. Modelo de dados

Migrations `117_agentes.sql` (F1), `118_agentes_titulo_redigido.sql` (F4) e `119_agentes_aprendizado_semente.sql` (F6, só dados) — **idempotentes**
(`IF OBJECT_ID(...) IS NULL` / `IF NOT EXISTS`, rodam 2×), aplicadas na **etapa 6c** do `scripts/deploy.sh`
(responder **s**). Sem migration: a tela avisa e nada quebra (padrão da 110).

⚠️ **A 118 zera o `titulo` de toda conversa existente no momento em que roda** — é a limpeza dos títulos gravados
antes da redação (F4). Ela tem de ir na 6c do MESMO deploy que sobe a F4: adiada para um deploy posterior, zeraria
também os títulos já redigidos que a API nova tiver gravado no intervalo (perda cosmética, mas evitável).
Pós-deploy: `SELECT COUNT(*) FROM dbo.etl_agente_conversa WHERE titulo IS NOT NULL` (esperado 0 logo após) e
`SELECT config_value FROM dbo.etl_app_config WHERE config_key = 'agentes_titulo_redigido_em'` (a marca de corte).
Larguras seguem a origem: `matricula VARCHAR(20)` (= `etl_usuario.matricula`), `ds_project NVARCHAR(50)`,
`job_name`/`pipeline_name NVARCHAR(200)`. `NVARCHAR(n)` conta UTF-16: cortar com `cortar_utf16`.

> **Larguras confirmadas em produção (D-13 ✅):** `etl_usuario.matricula = VARCHAR(20)`; `etl_job_lineage.extraction_method = VARCHAR(50)`;
> `etl_app_config`: `config_key VARCHAR(100)`, `config_value VARCHAR(1000)`, `descricao VARCHAR(500)`, `updated_at DATETIME`,
> `updated_by VARCHAR(100)` — os `INSERT` de seed da 117 usam esse esquema (inclusive `descricao`).

| Tabela | Colunas principais | Notas |
|---|---|---|
| `etl_agente_conversa` | `conversa_id VARCHAR(36) PK` (gerado no servidor), `agente VARCHAR(40)`, `matricula VARCHAR(20)`, `titulo NVARCHAR(200)`, `projeto NVARCHAR(50) NULL` (projeto DataStage resolvido na conversa), `criada_em`, `ultima_msg_em DATETIME2(0)` | índice `(matricula, ultima_msg_em DESC)` e `(ultima_msg_em)` p/ purga |
| `etl_agente_mensagem` | `id BIGINT IDENTITY PK`, `conversa_id FK ON DELETE CASCADE`, `papel VARCHAR(10)`, `conteudo NVARCHAR(MAX)` (**já redigido**), `status VARCHAR(20)`, `artefatos_json NVARCHAR(MAX) NULL` (ferramentas executadas [nome, args, exit, ms], grafo, links, ids de proposta), `criada_em` | índice `(conversa_id, criada_em)` |
| `etl_agente_fato` | `id BIGINT IDENTITY PK`, `ds_project`, `job_name`, `pipeline_name NULL`, `tipo VARCHAR(20)` (stage/parametro/tabela/campo/lineage/descricao), `chave NVARCHAR(300)`, `valor_json NVARCHAR(MAX)`, `origem VARCHAR(30)` (dsjob_lstages/dsjob_lparams/dsjob_report/isx/dsx/interpretacao_aprovada; em `dsx`, `ds_last_modified` guarda a data do arquivo), `evidencia NVARCHAR(MAX)` (autocontida, filtrada), `ds_last_modified VARCHAR(40) NULL`, `lido_em`, `lido_por VARCHAR(20)`, `aprovado_por VARCHAR(20) NULL`, `aprovado_em NULL`, `obsoleto_em NULL` | upsert idempotente; índice `(ds_project, job_name, tipo)` |
| `etl_agente_proposta` | `id BIGINT IDENTITY PK`, `conversa_id VARCHAR(36)` (**sem FK**: sobrevive à purga), `agente`, `matricula VARCHAR(20)`, `ds_project`, `job_name`, `tipo`, `chave`, `valor_json`, `evidencia`, `motivo NVARCHAR(600)`, `estado VARCHAR(12)` (pendente/aprovada/recusada/expirada), `criada_em`, `decidida_por`, `decidida_em`, `fato_id NULL` | decisão idempotente (`UPDATE … WHERE estado='pendente'` + rowcount) |
| `etl_agente_aprendizado` | `id`, `agente VARCHAR(40)`, `tipo VARCHAR(20)` (acesso/busca/leitura/detalhamento/erro), `assinatura CHAR(64)` (sha256 da chave normalizada), `titulo NVARCHAR(200)`, `corpo NVARCHAR(2000)`, `evidencia NVARCHAR(MAX)`, `origem VARCHAR(20)` (ferramenta/interpretacao/semente), `estado VARCHAR(12)` (rascunho/validado/obsoleto/rejeitado), `criado_em`, `validado_por`, `validado_em`, `ultimo_uso_em`, `usos INT`, `revalidar_em NULL` | `UNIQUE (agente, assinatura)` dedupa e incrementa `usos`; índice `(agente, estado, tipo)` |
| `etl_usuario` (**ALTER**) | `identidade_gateway VARCHAR(100) NULL`, `identidade_gateway_por VARCHAR(20) NULL`, `identidade_gateway_em DATETIME2(0) NULL` | `IF COL_LENGTH('dbo.etl_usuario','identidade_gateway') IS NULL`; formato `^[A-Za-z0-9._@-]{1,100}$` validado na API; **unicidade conferida na aplicação** (índice único filtrado evitado: gotcha `QUOTED_IDENTIFIER`); só admin grava |

**Sem FK das tabelas derivadas (proposta, fato, aprendizado) para a conversa**, e evidência autocontida (comando +
trecho filtrado da saída): a purga de 30 dias não pode apagar o que precisa durar (aprovações com matrícula e hora,
fatos, aprendizados).

**Seeds da 117** (padrão da 060): `MERGE` de `tela_agentes` em `etl_perfil_permissao` **só para o perfil `admin`** — é como o admin já nasce com a tela; se quiser abri-la a outro perfil (ex.
`desenvolvedor`), o admin usa a **Admin › Perfis já existente** (`perfil_upsert`), como faria com qualquer outra tela. Cada AGENTE (`agente_datastage`) segue política diferente: nunca semeado, e
sempre concedido usuário a usuário, pelo admin (não pela tela de perfis); `etl_app_config`: `agentes_enabled='0'`,
`agente_datastage_enabled='0'` (colunas `config_key, config_value, descricao, updated_by, updated_at`). A 117 também **acrescenta as colunas de identidade em `etl_usuario`** (última linha da tabela acima).
Config sem migration (chaves em `etl_app_config`): `agentes_gateway_campo_usuario` (`header:NOME` | `body:CAMPO`),
`agentes_cadastro_texto`, `agentes_ssh_max` (padrão 10, configurável), `agentes_fato_validade_dias` (padrão 7).

## 5. Fases

Regras: cada fase = **1 PR**, mergeável sozinha, deixa a `main` funcional; **fases de UI em sequência** (a `dist/` é
commitada e gera conflito se duas fases mexerem no front). O merge é **sempre autorizado pelo usuário**. Sem
dependência Python nova prevista (`anthropic`, `httpx`, `paramiko` já existem) — nenhuma wheel nova em `api/wheels/`.

**Validação padrão de toda fase** (citada em cada uma como "padrão"): `cd ui-react && npx tsc -b` (**não** `--noEmit`,
que não checa nada aqui) e eslint **comparados com o HEAD** (zero erros novos) · `npm run build` com a `dist/` commitada ·
`pytest` comparado com o baseline do HEAD (falhas pré-existentes conhecidas; zero novas) · **revisão adversarial
multi-agente antes da PR** (`qa-adversarial`; `security-review` nas F1, F2, F5 e F6) · `/simplify` nas fases finais.

### F0 — Camada de IA compartilhada, desacoplada do módulo Caixa (pré-requisito da F1)
- **Por quê (pedido do usuário, 21/09):** a IA está centralizada no módulo Caixa — `api/services/caixa_ia.py`, chaves `caixa_ia_*` em `etl_app_config`,
  ações `caixa_ia_*` do Admin e a aba "Caixa Seguro IA" — e esse módulo vai para outra ferramenta em breve, ficando só o Orquestra. A IA fica para o
  **Maestro** (`maestro.py`), a **triagem** (`dags/utils/triagem_ia.py`), os **agentes** e módulos futuros. Fazer isto **antes** da F1 evita escrever o
  agente sobre um módulo que vai ser renomeado.
- **Entregável:** a mesma capacidade, com nome e dono neutros; **nenhuma mudança de comportamento** para quem usa; deploy independente do resto.
- **Inclui:**
  1. `api/services/ia_provedor.py` (`git mv` de `caixa_ia.py`) com os provedores `anthropic`, `openai_compat` e `caixa_gateway` — este último nomeia o
     **destino** (o gateway interno da Caixa), não o módulo, e o valor gravado em config **não muda**. Imports atualizados em `admin.py`, `maestro.py` e
     `caixa_chat.py`; sem shim.
  2. **Config** `caixa_ia_{provider,model,base_url,api_key_enc,usa_proxy,ultima_verificacao}` → `ia_*`. **Migration `116_ia_provedor_config.sql`**
     (idempotente, etapa 6c): **copia** cada chave que existir para o nome novo, sem sobrescrever a nova e **sem apagar a antiga**. Leitura **dual**
     (nova → antiga) na API **e** no espelho `dags/utils/triagem_ia.py`; o Admin grava as novas e **espelha nas antigas** durante a transição. A limpeza das
     antigas é uma migration posterior (**F0b**), só depois de confirmado que `dags/` e worker leem as novas.
  3. **`caixa_ia_enabled` não migra:** é o interruptor dos assistentes do Caixa (diz o comentário do próprio `triagem_ia.py`) e fica com o módulo. Cada consumidor
     mantém o seu (`maestro_enabled`, `chamados_triagem_habilitada`, `agentes_enabled`). Sem interruptor global novo (**B-14**).
  4. **Admin:** a aba "Caixa Seguro IA" (`Admin.tsx`, id `caixa-ia`) vira **"IA"** (id `ia`), com textos genéricos; ações `ia_get/ia_set/ia_test/ia_verificar`
     (as `caixa_ia_*` ficam como **aliases por uma versão**, para JS em cache); os textos de `MaestroTab.tsx` e de `Admin.tsx` (~3677) apontam para **Admin › IA**.
  5. **Espelho api × dags:** `dags/utils/triagem_ia.py` muda as mesmas chaves e ganha um **teste de contrato** que prende chaves e dialeto do gateway nos dois
     lados (`api/` e `dags/` não se importam).
  6. **Nada do Caixa sai aqui** (`caixa_chat.py`, `etl_caixa_chat_log`, prompts Diego/Lari/Léo, `tela_caixa_seguro`, `pio.py`): só passam a depender da camada nova.
     As migrations antigas (ex.: a 093, que cita `caixa_ia_enabled`) **não** são editadas.
- **Critérios de aceite:**
  1. Com as chaves só no nome antigo (o banco de hoje) tudo funciona (fallback); com as novas idem; a 116 roda 2× sem erro e não sobrescreve chave nova já existente.
  2. **Não-regressão:** Maestro, triagem e assistentes do Caixa respondem como antes; os corpos e headers de `_chat_caixa_gateway`, `_chat_anthropic` e
     `_chat_openai_compat` saem **idênticos**; os 7 arquivos de teste que citam `caixa_ia` foram ajustados e passam.
  3. Admin › IA grava as chaves novas **e** as antigas; a chave de API segue write-only, mascarada e cifrada com o mesmo Fernet (`ORQUESTRA_CONN_KEY`);
     salvar não apaga a última verificação sem motivo.
  4. **Teste de desacoplamento** (`test_ia_desacoplada.py`): o serviço não importa nem cita `caixa_*`; fora de `caixa_chat.py`/`ui-react/src/caixa/` nada cita
     `caixa_ia` nem "Caixa Seguro IA" (exceto a migration 116, as antigas e os aliases marcados).
  5. As ações antigas `caixa_ia_get/set/test/verificar` ainda respondem (alias).
  6. O teste de espelho api × dags passa.
- **Deploy da F0 (o usuário faz):** 6c **s** (116) · API · `dist/` · `dags/` **s** e **restart do worker** (a triagem lê as chaves e o worker cacheia `dags/utils`) ·
  `config/` **n**. Como há fallback e as chaves antigas ficam, **a ordem não quebra nada**: se `dags/`/worker ficarem para depois, a triagem segue nas antigas
  (que o Admin espelha).
- **Validação:** padrão. **PR:** `refactor(ia): camada de IA compartilhada, desacoplada do módulo Caixa (F0)`.

### F1 — Fundação: migration 117, RBAC por agente e gateway com identidade por usuário
- **Entregável:** backend sem UI nova; interruptores desligados. A `main` segue igual para quem não liga.
- **Inclui:** migration 117; catálogo em código; `ia_provedor` com `identidade`, `GatewayRecusou`, `sondar_usuario`
  (+ controle com a identidade do app); `identidade_gateway()` (cadastro → padrão `cvp-<matrícula>`); coluna `etl_usuario.identidade_gateway` + ação `user_identidade_set` (só admin) + campo no modal de usuário do Admin; `require_agente()` (política de acesso por agente; **admin passa sempre**) e a recusa (422) no `user_perm_set` para perfil não elegível; `GET /agentes/catalogo`, `GET /agentes/status`,
  `GET/POST /agentes/admin/config`; recursos em `RBAC_RECURSOS` (`Admin.tsx`); testes; `dist/` (se a F1 passar de ~500 linhas úteis, o campo de identidade no modal do Admin migra para a F3).
- **Pré-requisito:** **F0 mergeada e em produção**; D-01, D-02 e D-03 fechadas (D-06, D-13, D-16 e D-17 já ✅). Sem D-01 a F1 abre com a sonda em `sem_contrato`.
- **Critérios de aceite:**
  1. A 117 roda 2× sem erro; `tela_agentes` semeada **só no perfil `admin`**; interruptores em `'0'`.
  2. **Tela** (`tela_agentes`, recurso normal): admin a vê por estar seedada no perfil; não-admin sem ela → sem item de menu, 403 na API — e some ao trocar o perfil; conceder via **Admin › Perfis**
     (`perfil_upsert`, já existente) para um perfil inteiro (ex. `desenvolvedor`) funciona **igual a qualquer outra tela** (teste). **Agente** (`agente_datastage`): admin conversa **sem grant nenhum**
     (`acao_admin`, via `require_agente`); não-admin com a tela e sem grant → catálogo vazio; `desenvolvedor` **com** grant em `permissoes_extra` → aparece **depois do relogin**; perfil **não elegível**
     mesmo com o grant → 403 `agente_nao_elegivel`; `desenvolvedor` sem grant → 403 `agente_nao_liberado`; **`agente_datastage` marcado num PERFIL** (via `perfil_upsert`, por engano ou não) → **não** dá
     acesso a não-admin (`require_agente` só olha `permissoes_extra`) — teste específico para essa defesa; a tela Admin › Agentes não lista `agente_*` na matriz de perfis.
  3. `identidade_gateway`: cadastro **vazio** → `identidade_gateway('CVP1234') == 'cvp-cvp1234'`; cadastro **preenchido** → usa o cadastro (sem `cvp-`); valor com espaço, quebra de linha ou mais de
     100 caracteres → 422 ao salvar; valor **duplicado** entre usuários → 409; só admin grava; sem matrícula na sessão → **nenhuma chamada** ao gateway; teste que **falha** se existir fallback
     para `cvp-orquestra`; alterar o campo **invalida** o cache da sonda.
  4. Sonda: 200 ⇒ `ok`; 401/403 do usuário + controle OK ⇒ `sem_cadastro`; 401/403 + controle falha ⇒
     `chave_do_app_invalida`; `ConnectError`/timeout/5xx ⇒ `gateway_indisponivel`; campo não configurado ⇒
     `sem_contrato` **sem** chamar; cache respeitado. (Regras finais conforme D-02/D-03.)
  5. **Não-regressão:** `_chat_caixa_gateway` sem `identidade` gera corpo e headers **idênticos** aos de hoje; testes
     existentes de `caixa_chat`/`ia_provedor`/triagem passam.
  6. Erros no formato `detail: {code, message}`.
- **Validação:** padrão. **PR:** `feat(agentes): fundação — migration 117, RBAC por agente e gateway com identidade por usuário (F1)`.

### F2 — Ferramentas de leitura e orquestração (backend)
- **Entregável:** `POST /agentes/datastage/conversar` funcionando por API, com persistência das mensagens; sem UI.
- **Inclui:** `agentes_ferramentas.py` (`base`, `dsjob` com a allowlist acima); régua do pedido de ferramenta
  (bloco JSON); **resolução do projeto** (pergunta, validação contra a base e os `.dsx`, e a guarda que recusa `dsjob`/ISX/DSX sem projeto resolvido — §3); orquestração (≤3 rodadas, **teto de 240 s** abaixo do `proxy_read_timeout 300s` — D-14 ✅); semáforo de
  sessões SSH com espera limitada; truncagem das saídas (`run_dsjob` devolve até 200 000 caracteres); `redigir()`
  de segredos; saída de ferramenta como **dado delimitado**; prompt gerado do vocabulário das ferramentas; base
  primeiro com validade (ISX por `ds_last_modified`; `dsjob` por prazo).
- **Pré-requisito:** D-04, D-07, D-08 e D-09 fechadas (D-14 já ✅: teto de 240 s).
- **Critérios de aceite:**
  1. Não-admin sem elegibilidade (perfil `desenvolvedor`) **e** grant manual → 403 (o admin passa); interruptor desligado → 503 **sem** chamar gateway nem servidor.
  2. Pedido fora da allowlist (`logdetail`, comando livre, `;` no nome do job) → recusado; teste com SSH dublê que
     **falha se for chamado**.
  3. Job com dado válido na base → **0 chamadas SSH** e a resposta informa a idade do dado; dado vencido → 1 leitura ao vivo.
  4. Valores canário (senha, token, valor de parâmetro Encrypted) **nunca** chegam ao modelo nem às mensagens gravadas.
  5. Com teto de N sessões, a N+1ª espera; passado o limite de espera → erro nomeado "servidor ocupado".
  6. O identificador enviado é o da **sessão**: `matricula` forjada no corpo é ignorada.
  7. Saída de ferramenta com "ignore as instruções…" entra como dado e **não** muda allowlist nem estado.
  8. Gateway lento (dublê) → resposta nomeada dentro do teto de 240 s, não 504 do nginx.
  9. **Sem projeto resolvido, nenhuma ferramenta de servidor roda** (`dsjob`, ISX e DSX): teste com o SSH e o serviço dublês que **falham se chamados**, mesmo que o modelo peça a ferramenta.
  10. Usuário cita um pipeline ou um job de pipeline → o projeto sai da **base** e **nada é perguntado**; cita só o nome de um job → o chat **pergunta o projeto**.
  11. Projeto **com** `.dsx` → `dsx_consulta` disponível; projeto **sem** `.dsx` → a hierarquia do DSX é **pulada** e o agente segue por ISX/`dsjob` (teste: `dsx_consulta` nunca chamada); projeto
      **desconhecido** → **0** chamadas a ISX/`dsjob`, com sugestões na resposta; nome só diferente na caixa → sugere o canônico e pede confirmação.
  12. O projeto é lembrado ao retomar a conversa; trocar de projeto zera o job em foco.
- **Validação:** padrão. **PR:** `feat(agentes): ferramentas de leitura e orquestração do agente DataStage (F2)`.

> **Ajuste de produção de 23/09/2026 (PR #428) — muda o critério 11 da F2.** Pedido do usuário: o agente
> **infere o projeto pelo prefixo do job** (`SsdPrs_*`/`SeqSsdPrs_*` → BI_PRESTAMISTA) e segue **sem pedir
> confirmação**; no caso "quase" (caixa diferente), quando o prefixo confirma, chama `resolver_projeto` de novo com a
> grafia canônica sem perguntar. O que continua valendo: o backend **não resolve sozinho** — o nome inferido passa por
> `resolver_projeto`, que só aceita o que existe na base/DSX (guarda do risco 28). Quando o prefixo não diz nada,
> `resolver_projeto {"listar": true}` lista os projetos conhecidos (base ∪ DSX, até 50) e o agente pede ao usuário
> para escolher — nunca "não encontrado" sem mostrar as opções.

### F2b — Extração ISX e consulta a DSX pelo agente, com a mesma régua do botão da Governança
- **🏁 IMPLEMENTADA 22/09/2026** (branch `feat/agentes-f2b`): `isx_extrair` e `dsx_consulta` em
  `api/services/agentes_ferramentas.py`, reaproveitando 100% de `services.lineage_isx`
  (`localizar/extrair/gravar/cabecalho/conta_linhas/mapa_tipos/config/montar`) e o MESMO executor
  dedicado do router (`routers.lineage_isx._EXECUTOR_ISX`, importado direto — nenhum pool novo,
  confirmado por identidade de objeto em teste) para `isx_extrair`; `dsx_consulta` usa o `DSXEngine`
  existente (mesmo padrão de `api/routers/lineage.py`). `isx_extrair` tem duas portas: `pipeline_name`+
  `job_name` (job em pipeline, GRAVA como o botão, rastreado com `extracted_by = "MATRÍCULA
  (agente:datastage)"`) ou só `job_name` (projeto já resolvido, fora de pipeline — extrai e responde,
  NÃO grava, a persistência em `etl_agente_fato` fica para a F5). Limite de 2 extrações ISX por
  pergunta. 36 testes novos (`test_agentes_f2b_ferramentas.py` + `test_agentes_f2b_orquestracao.py`),
  cobrindo os 11 critérios de aceite; suíte completa sem regressão (baseline de 8 falhas
  pré-existentes inalterado).
- **Decisão do usuário (B-02, 21/09):** o agente pode disparar ISX e DSX e o que for necessário para trazer detalhes dos jobs e, no final, gravar no banco para melhorar a lineage.
  Lida assim: **ferramentas de exportação/leitura que não alteram o DataStage**, numa **allowlist em código** — não uma lista aberta. Quanto ao **DSX**, o usuário informou que os arquivos **já existem
  nas pastas do Airflow para consulta**: o agente os **consulta** (somente leitura); não exporta DSX do servidor.
- **Entregável:** ferramentas `isx_extrair` e `dsx_consulta` no agente; gravação na lineage para jobs em pipeline.
- **Inclui:**
  1. `isx_extrair` sobre `services/lineage_isx` (`localizar` + `extrair` + `gravar`): as **mesmas funções e o mesmo executor** do endpoint `POST /lineage/isx/extrair` (2 extrações simultâneas por
     processo, teto de 60 s, `sp_getapplock` por job, cache pelo `lastModified`; `force` só se o usuário pedir). **Nenhum segundo pool.**
  2. **`isx_extrair` exige que o usuário tenha `acao_editar`** (o mesmo do botão; o perfil `desenvolvedor` a tem no seed da migration 019): sem ela o agente **não extrai** e devolve o link da
     Governança. A permissão `agente_datastage` **não** a substitui.
  3. `dsx_consulta`: lê os `.dsx` de `DSX_BASE_DIR` pelo `DSXEngine` (o `orquestra-api` os monta `:ro`), com as operações `listar_dsx`, `listar_jobs`, `listar_pastas`, `buscar_campo` e `extrair` (o lineage
     de um job **lido do arquivo**). **Somente leitura e sem tocar o servidor DataStage.** Nome de projeto/arquivo validado contra path traversal (como `_safe_project_name` em `api/routers/lineage.py`); o
     parse roda num executor com teto de tempo e a saída é truncada; `redigir()` sobre o conteúdo (um DSX pode trazer usuário/senha de stage); **toda resposta informa o nome e a data do arquivo**.
  4. Job **em pipeline** → `isx_extrair` grava como o botão (cabeçalho em `etl_ds_job_isx` + linhas `isx_auto`, `extracted_by` = matrícula). Job **fora de pipeline** → extrai e responde **sem** gravar em
     `etl_job_lineage`/`etl_ds_job_isx` (a regra do lineage segue — **B-19**); os fatos dele vão para `etl_agente_fato` na F5. O que vem do **DSX** também vai para `etl_agente_fato` (**B-22**), nunca
     direto para `etl_job_lineage`.
  5. No máximo **2 extrações ISX por pergunta**, dentro do teto de 240 s; **nunca lote** (é do admin, pela DAG). Ferramenta nova depois disso entra **por PR** — aprendizado não amplia a allowlist.
  6. Quando a base/`isx_auto` e o DSX têm o mesmo job, a **base prevalece** (a mesma preferência de `GET /lineage`).
  7. Erros do serviço (422, 404, 409, 502, 503, 504) viram mensagens nomeadas ao usuário e alimentam os aprendizados (F6).
- **Pré-requisito:** F2; **D-19** (a pasta DSX de produção: o que há, quão velho, quem atualiza, se a API a enxerga).
- **Critérios de aceite:**
  1. Sem `acao_editar` → o agente **não** extrai por ISX (teste com o serviço dublê que **falha se for chamado**) e devolve o link.
  2. Job em pipeline: o que `isx_extrair` grava é **igual** ao que o `POST /lineage/isx/extrair` gravaria (teste de igualdade); a 2ª pergunta com o mesmo `lastModified` → **0 extração**.
  3. O executor é o mesmo: 3 pedidos simultâneos → 2 rodam e 1 espera (nenhum pool novo).
  4. Job fora de pipeline: **nada** em `etl_job_lineage` nem `etl_ds_job_isx` (teste).
  5. Pedido fora da allowlist (importar, compilar, executar, parar, apagar, lote) → recusado; teste com o SSH e o serviço dublês que **falham se chamados**.
  6. A extração ISX não deixa arquivo além do que o `istool` já cria em `DS_ISTOOL_TMP` (conferido no smoke).
  7. `dsx_consulta` **não** abre SSH nem chama `dsjob` (teste com o SSH dublê que falha se chamado) e **não cria nem altera** arquivo em `DSX_BASE_DIR`; projeto com `..` ou `/` → recusado.
  8. Toda resposta de `dsx_consulta` traz o **nome e a data do arquivo**; base/`isx_auto` prevalece sobre o DSX quando os dois existem.
  9. Valores canário (senha, `{iisenc}`) num DSX de teste **não** chegam ao modelo nem às mensagens gravadas.
  10. Um DSX grande não estoura o teto: parse no executor com prazo; resposta truncada e nomeada.
  11. `dsx_consulta` só roda com projeto **com** `.dsx`; sem ele é recusada (a hierarquia é pulada — §3).
- **Validação:** padrão (+ `security-review`). **PR:** `feat(agentes): extração ISX e consulta a DSX pelo agente, com a mesma régua do botão da Governança (F2b)`.

### F3 — Tela `/agentes` (seletor, chat, aviso de cadastro, grafo, links) e Admin › Agentes
- **Entregável:** a tela visível para quem tem `tela_agentes` (o admin desde o início; os demais, habilitados por ele); agente utilizável pelo admin e por quem tem o grant.
- **Inclui:** `nav.ts`, `App.tsx`, `pages/Agentes.tsx`, componentes, `lib/agentes.ts`; `AgentesTab.tsx` (interruptores,
  campo do gateway, texto de cadastro, teto SSH, validade, e a **visão por agente**: quem tem acesso, com **incluir/remover usuário** — só elegíveis — pelo mesmo `user_perm_set`); grafo inline;
  **indicador do projeto da conversa** (com o selo "tem DSX") e a ação **trocar projeto**; links para a Governança (**C-01**); `dist/`.
- **Pré-requisito:** D-05 fechada (texto do aviso de cadastro).
- **Critérios de aceite:**
  1. Sem grant: a tela abre com estado vazio explicativo (não um 403 em branco); a chamada direta à API dá 403.
  2. Com grant: o seletor mostra **só** os agentes liberados (o admin vê todos); a visão por agente do Admin inclui e remove usuário e recusa quem não é elegível.
  3. `sem_cadastro` mostra o aviso com o texto configurado; `gateway_indisponivel` mostra "gateway indisponível" e
     **nunca** o aviso de cadastro (teste de front por regex + teste de API pelos `code`).
  4. Chat com `aria-live="polite"`, foco gerenciado, contraste dos tokens em claro e escuro, **sem cor fixa**.
  5. O grafo abre reaproveitando `GrafoIsx`; os links levam ao job na Governança.
  6. CSS: sem `overflow-hidden` em ancestral de `sticky`; sem `*/` dentro de comentário CSS; overlays sem
     especificidade que pinte fundo (lições do Caixa Seguro).
- **Validação:** padrão. **PR:** `feat(agentes): tela /agentes com chat, aviso de cadastro, grafo e Admin › Agentes (F3)`.

### F4 — Histórico de conversas (30 dias)
- **Entregável:** lista, busca e retomada; purga.
- **Inclui:** `GET /agentes/conversas` (`?q=`) e `/{id}`; continuar conversa (as últimas 12 rodadas vão ao gateway);
  UI de histórico; tarefa `limpar_conversas_agentes` em `dags/etl_log_cleanup.py` (o arquivo de produção já tem `limpar_conversas_maestro` — D-15 ✅, basta acrescentar); `LIKE` com `ESCAPE` para `%` e `_`;
  título por `cortar_utf16`.
- **Critérios de aceite:**
  1. Com 2 usuários, cada um lista e busca **só** as próprias; conversa alheia → 404 (sem oráculo).
  2. Conversa com 29 dias aparece e retoma; com 31 dias **não aparece, mesmo sem a purga** (filtro na leitura).
  3. Ao retomar, cada resposta antiga mostra a data e o dado passa pela checagem de validade.
  4. A purga apaga a conversa vencida e **não** apaga proposta, fato nem aprendizado (teste).
  5. Segredo canário digitado no chat não aparece em `etl_agente_mensagem`.
- **Validação:** padrão. **PR:** `feat(agentes): histórico de conversas com busca e retomada em até 30 dias (F4)`.

### F5 — Fatos gravados e propostas com aprovação
- **🏁 IMPLEMENTADA 22/09/2026** (branch `feat/agentes-f5`, **sem migration** — as tabelas vieram na 117). Novo
  `api/services/agentes_conhecimento.py`. Como ficou (decisões de implementação, algumas além do texto abaixo):
  - **Fato = retrato por (projeto, job, origem):** chave nova insere; igual renova `lido_em`/`lido_por`; valor mudou →
    a antiga ganha `obsoleto_em` e entra a nova; chave que sumiu → `obsoleto_em`. Retrato **vazio** não obsoleta nada
    (parse vazio ≈ formato inesperado, D-07); retrato **parcial** (stdout no teto de 200 000 de `run_dsjob`) não
    obsoleta o que não apareceu. `sp_getapplock` por job. `ljobs`/`jobinfo` não viram fato (lista do projeto /
    estado de execução). Parâmetro guarda nome, tipo e descrição — **nunca** o valor padrão.
  - **Validade:** `dsjob_*` por `agentes_fato_validade_dias` (padrão 7 — D-08 segue aberta); ISX/DSX pela data do
    job/arquivo em `ds_last_modified`. A `base` devolve os fatos vigentes com `lido_ha_dias`/`vencido`.
  - **Régua da proposta (além de tipo, tamanhos e segredo):** o `job_name` tem de ser um job **lido nesta pergunta**
    por `dsjob`/`isx_extrair`/`dsx_consulta`, e a **evidência** tem de ser trecho **literal** dessa leitura (espaços e
    escapes de JSON normalizados). Mensagens do orquestrador, erros e a própria `base` não contam — senão o modelo
    fabricava a evidência. Máx. 3 por resposta; as recusadas aparecem na tela com o motivo.
  - **Segredo:** além de `redigir()`, valor cifrado `{iisenc}…` é mascarado por FORMATO em fato e evidência (não
    depende de palavra-chave na linha); proposta com ele é recusada.
  - **Decisão** (`POST /agentes/propostas/{id}/decidir`, `{"decisao": "aprovar"|"recusar"}`): `require_agente` +
    dono pela sessão (alheia/inexistente → 404 igual); mesma decisão repetida → 200 `ja_decidida`; oposta → 409
    `proposta_ja_decidida` com a proposta no `detail`; pendente há mais de 30 dias → 409 `proposta_expirada`.
    Aprovar grava `interpretacao_aprovada` na mesma transação, com lock por chave (duas aprovações simultâneas da
    mesma chave deixam UMA vigente — conferido no SQL Server real).
  - **Interpretação aprovada no contexto do modelo:** chave própria no topo da resposta da `base`
    (`interpretacoes_aprovadas_por_usuario_nao_lidas_por_ferramenta`, máx. 5, 600 caracteres cada), **sem a
    matrícula** de quem aprovou; o prompt manda tratá-la como indício, nunca como instrução. Todo `</ferramenta>`
    dentro de dado é escapado antes de montar a tag.
  - Revisão: `qa-adversarial` (2 rodadas) + auditoria de segurança; achados e correções no PR.
  - **Follow-up:** teto de propostas pendentes por usuário (baixo impacto — cada proposta custa uma chamada ao modelo).
- **Entregável:** o agente grava o que a ferramenta leu; interpretações viram proposta aprovável.
- **Inclui:** gravação de fatos em `etl_agente_fato` (origens `dsjob_*`, `isx` — para jobs **fora de pipeline** extraídos na F2b — e `dsx`, sempre com o **nome e a data do arquivo**; origem, evidência, `lido_em`, `ds_last_modified`); obsolescência
  ao detectar mudança; base primeiro usando os fatos; régua de proposta (tipo, chave, tamanhos, segredos);
  `etl_agente_proposta`; cartão "Aprovar / Recusar" **com a evidência ao lado**; `POST /agentes/propostas/{id}/decidir`.
- **Critérios de aceite:**
  1. Fato só é gravado com origem de ferramenta.
  2. Sem decisão, **0** linhas com origem `interpretacao_aprovada` (teste).
  3. Aprovar 2× gera 1 fato; outro usuário decidindo → 403/404; recusar não grava nada.
  4. Proposta com valor Encrypted ou padrão de segredo → rejeitada pela régua.
  5. A aprovação guarda `decidida_por` e `decidida_em` e sobrevive à purga da conversa.
  6. Job fora de pipeline extraído na F2b → fatos em `etl_agente_fato` com origem `isx`; **nada** em `etl_job_lineage`.
  7. Fato vindo do DSX → origem `dsx` com a data do arquivo em `ds_last_modified`; **nunca** em `etl_job_lineage` (B-22).
- **Validação:** padrão. **PR:** `feat(agentes): fatos gravados por ferramenta e propostas com aprovação (F5)`.

### F6 — Base de aprendizados e tela do curador
- **🏁 IMPLEMENTADA 22/09/2026** (branch `feat/agentes-f6`). Novo `api/services/agentes_aprendizado.py` e **migration 119**
  (só dados: as 5 sementes como `rascunho`, B-12). Como ficou (decisões de implementação):
  - **Assinatura do erro = a da CHAMADA** (ferramenta + projeto em que roda + só os argumentos que a ferramenta usa), não
    a do texto do erro: o XML inválido da D-12 muda linha/coluna e continua sendo UM aprendizado (`usos` sobe). A chave
    crua nunca sai do servidor — viaja o hash (`chave_da_chamada`); `redigir()` não é injetivo e fazia chamadas
    diferentes colidirem.
  - **Guarda de reexecução:** falha PERMANENTE não roda de novo na conversa (as das perguntas anteriores voltam por
    `artefatos_json`) e, se virou erro validado e vigente, nem em outra conversa — 0 chamadas, e o motivo vai ao modelo.
    Falha PASSAGEIRA (servidor ocupado, 409/502/504, tempo, `dsjob` com código negativo) pode repetir e não vira
    aprendizado. Uso errado pelo modelo (comando fora da allowlist) só entra na guarda da conversa.
  - **Automáticos, nascem `validado`:** `erro` (título/corpo por CATEGORIA fixa; a mensagem só na evidência —
    critério 2), `acesso` (SSH/ISX não configurado, decidido pela CONFIGURAÇÃO real, não pelo texto; não cita job) e
    `busca` (grafia canônica do projeto). Revalidação: `dsjob` e "não encontrado" 1 dia; demais erros ISX 7.
  - **Recuperação por relevância:** até 5 itens / 2 000 caracteres, só `validado` e vigente, num bloco `<aprendizados>`
    delimitado. Erro de ferramenta fica FORA dela (age pela guarda exata) — o nome de job inventado pelo modelo não
    vai ao prompt de todos.
  - **Sugestões do modelo** (chave `aprendizados` no bloco final, máx. 2) viram `rascunho`.
  - **Curadoria:** aba na tela `/agentes` para quem tem `agente_curador`; validar / rejeitar / marcar obsoleto, com a
    evidência à vista. **Obsoleto** volta a valer se a ferramenta comprovar de novo; **rejeitado** nunca mais. Admin ›
    Agentes ganhou a seção "Curadores" (o curador também precisa do acesso de uso para abrir a tela).
  - Revisão: `qa-adversarial` (2 rodadas) + auditoria de segurança; achados e correções no PR.
  - **Follow-up:** teto de rascunhos por usuário; a curadoria não olha os interruptores do agente.
- **Entregável:** o agente registra e reutiliza aprendizados; curador valida interpretações.
- **Inclui:** registro automático (erro/acesso/busca/leitura) com `assinatura`; corpo gerado por código; interpretação
  entra como `rascunho`; aba do curador (`agente_curador`): aprovar, rejeitar, marcar obsoleto; recuperação por
  relevância (**≤ 5 itens e ≤ 2 000 caracteres**, só `validado`); **guarda de reexecução** (a mesma ferramenta com os
  mesmos argumentos que falhou não roda 2× na conversa); semente inicial (D-12 + o que já se sabe: nome de job é
  case-sensitive, `DS_ISTOOL_AUTHFILE` aceita `~/`, allowlist do `dsjob`, raízes SFTP) e o **erro real de produção** (D-12 ✅):
  "XML da definição do job inválido (reference to invalid character number…)" = caractere inválido no XML do job → informar o
  usuário e **não** tentar reextrair (a `assinatura` normaliza linha e coluna); `revalidar_em`.
- **Critérios de aceite:**
  1. 2ª ocorrência da mesma assinatura → **0 chamadas repetidas** e o aprendizado vai ao contexto (teste).
  2. O corpo de `erro`/`acesso` não contém texto livre da saída além da evidência filtrada (teste com canário de injeção).
  3. `rascunho` **nunca** entra no contexto do agente.
  4. Sem `agente_curador` → 403 nos endpoints de decisão; a aba nem aparece.
  5. Segredo canário não chega a aprendizado.
- **Validação:** padrão. **PR:** `feat(agentes): base de aprendizados, guarda de reexecução e tela do curador (F6)`.

### F7 — Fechamento: documentação, smoke e deploy
- **🏁 IMPLEMENTADA 23/09/2026** (branch `docs/agentes-f7`): `docs/MANUAL_USUARIO.md` §3.12 (usar) e §4.11
  (administrar), item no §4.6 e FAQ; `docs/release-notes/agentes.md` (a entrega inteira, #417–#429);
  `scripts/smoke_agentes.py` (itens automáticos pela API — catálogo, sonda, validação, **progresso chegando aos
  poucos** através do nginx, duração, histórico, régua de decisão, curadoria, usuário sem o agente — e o roteiro
  manual impresso no fim; nada é decidido nem configurado). Provado contra um servidor de teste, inclusive a prova
  reversa: com os eventos retidos até o fim, o smoke acusa o buffer.
- **Entregável:** manual, release note, smoke e roteiro de deploy; memória viva e a cópia em `.claude/memory/`.
- **Inclui:** nova seção em `docs/MANUAL_USUARIO.md`; `docs/release-notes/agentes.md`; `scripts/smoke_agentes.py`
  (no estilo dos `scripts/smoke_*.py`); revisão adversarial geral + `security-review` + `/simplify`.
- **Deploy (o usuário faz):** etapa 6c **s** (117) · `dags/` **s** (a purga; é arquivo de DAG, **não** exige restart do
  worker) · API e `dist/` · `config/` responder **n** (o `nginx.conf` de produção está à frente do repo) · sem `.env` novo,
  sem wheel nova · depois ligar `agentes_enabled` e `agente_datastage_enabled` no Admin; **habilitar `tela_agentes`** para quem for usar (o perfil `desenvolvedor`, ou usuário a usuário — B-21); **preencher `identidade_gateway`** dos 4 usuários fora do padrão `CVP`+dígitos; e conceder `agente_datastage` **só a desenvolvedores, um a um** (tudo pelo menu Admin; quem recebe é decisão sua — B-06). O admin já tem tudo desde a 117.
- **Critérios de aceite:** o smoke do §7 executado e conferido no ambiente real.
- **Validação:** padrão. **PR:** `docs(agentes): manual, release note e smoke de fechamento (F7)`.

## 6. Riscos e mitigações

| # | Risco | Impacto | Mitigação |
|---|-------|---------|-----------|
| 1 | **Falso verde na gravação:** conclusão do modelo vira dado "verdadeiro" no lineage | Decisão errada sobre fluxo em produção | Fato só de ferramenta; interpretação = proposta com aprovação; origem e evidência em toda linha; tabela própria (não toca o grafo da Governança) |
| 2 | **401/403 ambíguo:** o mesmo código serve a "usuário sem cadastro" e a "chave do app inválida" | Aviso de cadastro para quem só bateu numa falha, ou o contrário; chamados falsos | Chamada de **controle** com a identidade do app antes de concluir `sem_cadastro`; códigos separados; **D-02** confirma o que o gateway devolve |
| 3 | **Injeção persistente** via conteúdo de job/ISX/log guardado como aprendizado | Instrução escondida volta em toda conversa | Saída de ferramenta é dado delimitado; corpo de `erro`/`acesso` **gerado por código**; texto livre só passa pelo curador |
| 4 | **Aprendizado errado repetido** | O agente repete a falha para sempre | Evidência + estado + `revalidar_em`; interpretação só com curador; obsoleto/rejeitado saem do contexto |
| 5 | **Dado velho tratado como atual** | Resposta desatualizada sobre um job que mudou | ISX: `ds_last_modified`; `dsjob`: prazo; a resposta mostra a idade; botão "reler ao vivo"; retomada revalida |
| 6 | **Escalada de privilégio:** quem não tem `tela_ds_console` passa a acessar o DataStage pelo agente, e agora **também a extrair definições** | Acesso ao servidor por caminho novo | Grant **manual, usuário a usuário**, e **só para o perfil `desenvolvedor`** (checado no runtime por `require_agente`, que ignora `agente_*` vindo de perfil para não-admin; **só o admin concede**, pela tela
  Admin › Agentes; o admin passa por `acao_admin`, sem seed; a tela `tela_agentes` em si é recurso normal, perfil como qualquer outra); a **extração exige `acao_editar` do próprio usuário** (mesma régua do botão da Governança); allowlist **em código** (ferramenta nova só por PR) e mais estreita que a do Console; toda ferramenta executada fica em `artefatos_json` (auditável) |
| 7 | **Purga de 30 dias apaga o que precisa durar** | Perde aprovação, fato ou aprendizado | Sem FK das derivadas; evidência autocontida; teste na F4 |
| 8 | **Segredo digitado no chat ou lido pelo `dsjob`** (ex.: valor de parâmetro Encrypted) | Vazamento em conversa/log/aprendizado por 30 dias | `redigir()` antes de qualquer gravação e antes de ir ao modelo; canários nos testes; **D-07** mostra o que o `dsjob` realmente devolve |
| 9 | **Sobrecarga do servidor DataStage** (SSH por requisição, compartilhado com Console, Utilitários, lineage e DAGs) | Derrubar o acesso dos outros | Base primeiro; semáforo `agentes_ssh_max`; espera limitada; **D-09** dimensiona o teto |
| 10 | **Timeout de requisição** (D-14 ✅: a rota `/orquestra/` tem `proxy_read_timeout 300 s`, igual no repo e em produção; os 120 s são da `/api/v1/`, do Airflow) | 504 em pergunta com 4 rodadas de ferramenta; espera longa sem retorno | Teto de 240 s controlado por relógio no backend; resposta nomeada; front com indicação de andamento; se houver balanceador/proxy corporativo antes do nginx, o limite efetivo pode ser menor (não verificado) |
| 11 | **Identidade errada:** matrícula gravada em MAIÚSCULAS (`auth.py:38`) × `cvp-…` minúsculo; ou fallback para `cvp-orquestra` | Falha de cadastro falsa, ou autorização anulada | Normalização fixa + teste; **proibido** fallback (teste que falha se existir); **D-01** confirma a caixa |
| 12 | **Permissão nova exige relogin** e `RBAC_RECURSOS` é uma 2ª lista à mão | "Concedi e o agente não aparece" | Recursos na lista do Admin na F1; smoke b) exige o relogin; mensagem no modal de grants |
| 13 | **`dist/` invisível ou em conflito** | PR que "não aparece" em produção | Rebuild em toda fase de UI; UI em sequência |
| 14 | **`dags/` não sincronizado** (a tarefa de purga não roda) | Conversas passam de 30 dias no banco | Janela imposta também na **leitura**; **D-15** verifica o estado do `dags/` em produção; smoke k) |
| 15 | **Aprovação sem leitura** (usuário clica "aprovar" no automático) | Interpretação errada vira fato | Evidência ao lado do botão; a aprovação registra matrícula e hora; a proposta mostra o que será gravado |
| 16 | **Usuários fora do padrão `CVP`+dígitos** (4 de 12 ativos) | O gateway não conhece o identificador padrão desses usuários e eles veem "sem cadastro" | **Resolvido por decisão (D-16 ✅):** campo `identidade_gateway` no cadastro (admin preenche; vale sobre o padrão), com validação de formato, unicidade e invalidação do cache; preencher os 4 antes de conceder o agente |
| 17 | **Contrato validado no gateway "dev"** (D-17 ✅ decisão: é o que a produção usa hoje; a ferramenta é de outra área e será trocada) | Na troca, o formato de identidade e as respostas de "sem cadastro" podem mudar | **Aceito.** O local do identificador e a regra da sonda ficam em **config** (`agentes_gateway_campo_usuario`) e atrás de `ia_provedor`; na troca, repetir D-01 a D-03; "Verificar" no smoke (o último diagnóstico guardado é de 21/08) |
| 18 | **Ordem de deploy API × dags/worker** (a triagem lê as chaves no worker, que cacheia `dags/utils`; o deploy de agosto ficou parcial) | Triagem perde a config ("sem provedor") ou lê chave velha | A migration **copia** (não move); leitura dual nova → antiga na API **e** no espelho; Admin espelha nas antigas; limpeza só depois (F0b); smoke da triagem |
| 19 | **Ação do Admin renomeada com JS em cache** | Aba do Admin quebra até recarregar | Ações `caixa_ia_*` ficam como aliases por uma versão |
| 20 | **Regressão nos consumidores** (Maestro, triagem, assistentes do Caixa) ao mover o módulo | IA quebrada em silêncio em produção | F0 sem mudança de comportamento; teste de igualdade de corpo/headers; 7 arquivos de teste; smoke por consumidor |
| 21 | **Espelho api × dags diverge** (não se importam) | Triagem e API leem coisas diferentes | Teste de contrato que prende chaves e dialeto nos dois lados |
| 22 | **Dependência escondida do Caixa** herdada pela camada nova | A camada quebra quando o módulo Caixa sair | Teste que falha se o serviço importar ou citar `caixa_*`; `caixa_ia_enabled` e `etl_caixa_chat_log` ficam do lado do Caixa |
| 23 | **Extração em excesso** pelo agente (cada `istool export` é uma JVM no servidor DataStage) | Sobrecarga do servidor e dos outros usuários da Governança | Mesmo executor do botão (2 por processo, teto de 60 s, lock por job, cache pelo `lastModified`); no máximo 2 extrações por pergunta; **nunca lote** (é do admin, via DAG); base primeiro |
| 24 | **"O que for necessário" vira lista aberta** de comandos | O agente passa a poder alterar o DataStage | Allowlist **em código**; ferramenta nova só por PR com revisão; aprendizados **não** ampliam a allowlist; importar/compilar/executar/parar/apagar recusados por teste |
| 25 | **Gravar na lineage do job errado** ou apagar linhas boas | Lineage piorada em vez de melhorada | O mesmo `gravar` do botão (só troca as linhas `isx_auto` do job, numa transação, com lock); job fora de pipeline **não** grava em `etl_job_lineage`; interpretações só com aprovação |
| 26 | **Concessão por perfil por engano** (via a Admin › Perfis genérica, que existe para qualquer tela) | Todos os usuários daquele perfil passam a acessar o agente | `require_agente`, para não-admin, só reconhece `agente_*` em `permissoes_extra` (override por usuário) — vir de perfil **não conta**, mesmo que alguém marque; a tela Admin › Agentes nem lista `agente_*` na matriz de perfis; teste dedicado |
| 27 | **DSX é retrato antigo** e pode conter **credenciais** de stages | Resposta desatualizada tratada como atual; vazamento de segredo | A resposta informa **nome e data do arquivo**; base/`isx_auto` prevalece; `redigir()` sobre o conteúdo do DSX + canário; a **D-19** mostra o que o DSX de produção contém (amostra redigida) |
| 28 | **Consultas às cegas** por falta do nome do projeto (o ISX `localizar` e o `dsjob` exigem o projeto) | Várias consultas sem sucesso, carga inútil no servidor e resposta lenta | Resolução do projeto **antes** de qualquer consulta, validada contra a base e os `.dsx`; guarda no backend que recusa a ferramenta sem projeto; nome desconhecido → sugestões, nunca tentativa |

## 7. Smoke pós-deploy

**Da F0 (no deploy da F0, antes de qualquer coisa dos agentes):**

F0-a) **Admin › IA:** a aba abre com o provedor atual; **Verificar** devolve `ok`; salvar sem mudar nada não derruba nada.
F0-b) **Consumidores:** o Maestro responde; a triagem roda um ciclo (ou é acionada) e grava o laudo; um assistente do Caixa responde.
F0-c) **Transição:** trocar o modelo em Admin › IA e conferir que a chave nova **e** a antiga refletem; recarregar sem cache e reabrir a aba.

**Dos agentes (no deploy da F7):**

a0) **Admin:** um admin, sem nenhuma concessão, vê o menu **Agentes**, o agente DataStage no seletor e conversa com ele.
a) **Sem acesso:** (i) usuário **sem** `tela_agentes` → não vê o item de menu e a API dá 403; (ii) com `tela_agentes` e sem grant → abre `/agentes` com estado vazio explicativo, e `POST /agentes/datastage/conversar` direto → 403; (iii) usuário de perfil **`consulta`/`operador`** com o grant forçado no banco → 403 `agente_nao_elegivel`; (iv) o Admin **recusa** conceder `agente_datastage` a esse usuário; (v) o recurso marcado num **perfil** não dá acesso a não-admin.
b) **Concessão:** o admin habilita `tela_agentes` para o usuário X **e** concede `agente_datastage` a X (Admin › Usuários ou Admin › Agentes), **X de perfil `desenvolvedor`**; **X faz logout e login** → o menu e o agente aparecem.
c) **Gateway:** X **sem** cadastro no gateway → aviso com o texto configurado; após o cadastro e "verificar de novo" → `ok`. Para um dos 4 usuários fora do padrão `CVP`+dígitos: sem o campo `identidade_gateway` → "sem cadastro"; com o campo preenchido → `ok`. Derrubar o gateway (ou apontar a URL errada em homologação) → "gateway indisponível" e **não** o aviso de cadastro.
d0) **Projeto:** iniciar uma conversa citando só o nome de um job → o chat **pergunta o projeto**; informar um projeto **com** `.dsx` → a hierarquia do DSX é usada; um projeto **sem** `.dsx` → o agente segue por ISX/`dsjob` sem tentar o DSX; um nome que **não existe** → nenhuma consulta ao servidor e sugestões na resposta; citar um pipeline do Orquestra → o projeto é assumido sem perguntar.
d) **Base primeiro:** perguntar sobre um job **com** ISX na base → resposta sem chamada ao servidor, com a idade do dado; sobre um job **sem** base → leitura ao vivo de `lstages`/`lparams` e o grafo/links quando houver ISX.
d2) **Extração pelo agente:** com um usuário que tenha `acao_editar`, pedir um job de pipeline **sem** ISX → o agente extrai, o grafo aparece e a Governança mostra as mesmas linhas `isx_auto`; repetir a pergunta → **0 extração** (cache pelo `lastModified`). Com um usuário **sem** `acao_editar` → o agente devolve o link e **não** extrai. Um job **fora de pipeline** → responde sem gravar em `etl_job_lineage`. Depois, conferir que o servidor DataStage não ficou com arquivos temporários além dos que a Governança já deixa.
d3) **DSX:** perguntar sobre um job que só existe no DSX → a resposta cita o **arquivo e a data**, e nenhuma conexão SSH nova aparece no servidor DataStage; um job que existe no ISX e no DSX → a resposta usa a base/ISX.
e) **Erro documentado:** pedir um job com o nome em caixa errada → erro nomeado e aprendizado registrado; repetir → o agente **não** repete o mesmo comando e usa o aprendizado.
f) **Proposta:** provocar uma interpretação → cartão com evidência → **Aprovar** grava o fato com `decidida_por`; **Recusar** não grava nada.
g) **Histórico:** buscar um termo de ontem; retomar a conversa e continuar; conferir que conversa com mais de 30 dias não aparece.
h) **Curador:** usuário com `agente_curador` vê a aba e valida um rascunho; usuário sem ele não vê a aba e leva 403 na API.
i) **Interruptor:** desligar `agente_datastage_enabled` → agente some do seletor; API 503; nenhuma chamada ao gateway.
j) **Concorrência:** 3 a 5 abas perguntando ao mesmo tempo sobre jobs sem base → o teto de sessões SSH é respeitado; Console DataStage segue respondendo.
k) **Purga:** no Airflow, `etl_log_cleanup` › `limpar_conversas_agentes` roda e apaga só o que passou de 30 dias.
l) **Segredo:** digitar um valor canário parecido com senha no chat → não aparece em `etl_agente_mensagem`; ver que a resposta também não o repete.
m) **Não-regressão:** Caixa Seguro (assistentes) e a triagem de chamados continuam usando `cvp-orquestra` e funcionando.
n) **Progresso e duração** (#428): `scripts/smoke_agentes.py` com `ORQ_URL` pelo nginx — os eventos chegam aos poucos; cada resposta mostra *respondido em Xs*, também ao retomar.
o) **Histórico** (#429): grupos por dia, título inteiro, lista rolando até o fim; **Curadoria** e **Histórico** nunca ativos juntos.
p) **Filhos de sequence** (#429): a pergunta vai direto ao ISX; na pergunta seguinte, a `base` já traz os filhos (`filho:<job>`).

## 8. Dúvidas em aberto

> **Como fechar a spec:** o usuário entra em produção e pede a um agente (Claude Code no servidor, ou quem ele
> designar) que **valide e documente** cada dúvida abaixo. Quando todas as **bloqueantes** estiverem ✅ e os pontos de
> impacto atualizados, o status da spec passa a **aprovada** e a F1 pode começar.

### 8.0 Protocolo do agente validador
1. **Somente leitura.** Não alterar dados, configuração, DAGs nem arquivos de produção. As únicas chamadas de saída
   permitidas são as **sondas mínimas ao gateway** (D-01 a D-04) e a **leitura de 3 jobs** pelo `dsjob` da allowlist (D-07).
2. **Gateway:** usar a matrícula **do próprio usuário** (cadastrada). Para o caso "não cadastrado" e "chave inválida",
   **avisar o time do gateway antes** — tentativas com identidade inexistente podem virar alerta de segurança. Nunca
   registrar a chave de API.
3. **Redigir tudo** o que for documentado: nada de senha, token, chave, conteúdo de `authfile`, valor de parâmetro
   Encrypted nem matrícula de terceiros. Contagens em vez de listas; exemplos mascarados (`cvp-cvp****`).
4. **Onde registrar:** no campo **Resultado** de cada item, neste arquivo (data, fonte, conclusão, impacto na spec e
   status ⬜ → ✅/❌). Amostras longas (saídas de `dsjob`, respostas do gateway) vão, já redigidas, para
   `docs/agentes-datastage-evidencias.md`, citando o ID.
5. **Ordem sugerida:** D-06, D-13, D-14 (ambiente) → D-01 a D-04 (gateway) → D-07 a D-09 (DataStage) → o resto.
6. **Se não der para validar** (sem acesso, sem resposta do time do gateway): registrar o motivo, manter o
   **padrão assumido** da linha e marcar ⚠️. Nada é chutado: sem contrato do gateway (D-01) os agentes ficam em `sem_contrato`.
7. **Para D-07, D-08 e D-09**, usar o **Console DataStage do Admin** (mesmo caminho e mesmas credenciais que o agente usará) em vez de
   abrir SSH à mão: uma falha de autenticação do validador não prova nada sobre a API (foi o caso do D-09).

### 8.1 Dúvidas a validar em produção

| ID | Dúvida | Bloqueia | Status |
|----|--------|----------|--------|
| D-01 | Onde vai o identificador do usuário e qual o formato exato | F1 | ⬜ |
| D-02 | O que o gateway devolve em cada causa (não cadastrado, chave inválida, ok, falha, 429) | F1 | ⬜ |
| D-03 | A chamada mínima (sonda): custo, limite e tempo para o cadastro valer | F1 | ⬜ |
| D-04 | Limites e latência do gateway (tamanho, timeout, p50/p95) | F2 | ⬜ |
| D-05 | Como o usuário pede o cadastro no gateway | F3 | ⬜ |
| D-06 | Provedor e configuração de IA em produção hoje | F1 | ✅ |
| D-07 | Como o `dsjob` responde de verdade (formato, tamanho, Encrypted, caixa do nome) | F2 | ⬜ |
| D-08 | Como saber que um job mudou (data de modificação) e a que custo | F2 / F5 | ⬜ |
| D-09 | Capacidade de sessões SSH do servidor DataStage | F2 | ⚠️ |
| D-10 | Tamanho da base já mapeada × jobs existentes | — (informa F5) | ✅ |
| D-11 | Raízes SFTP ativas e se valem para o mapeamento | — (decide o v1) | ✅ |
| D-12 | Erros reais de acesso já vistos (semente do aprendizado) | F6 | ✅ |
| D-13 | Esquema real em produção (larguras, colunas, perfis, usuários) | F1 | ✅ |
| D-14 | `proxy_read_timeout` real da rota da API em produção | F2 | ✅ |
| D-15 | Estado do `dags/` em produção (a purga vai funcionar?) | — (informa F4/F7) | ✅ |
| D-16 | Usuários fora do padrão `CVP`+dígitos (4 de 12 ativos): identificador no gateway | F1 | ✅ decisão |
| D-17 | O gateway configurado (`servicosstdev…`) é o de produção? Por que `usa_proxy = 1`? | F1 | ✅ decisão |
| D-18 | Chaves `caixa_ia_*` em produção, quem as usa e se `dags/`/worker estão em dia (base da transição da F0) | F0 | ⬜ |
| D-19 | A **pasta DSX** em produção: o que há, quão velho, quem atualiza, e se a API a enxerga | F2b (DSX) | ⬜ |
| D-20 | O perfil `desenvolvedor` tem `acao_editar` **em produção**? (a extração ISX pelo agente depende dela) | F2b | ⬜ |

**D-01 — Contrato da identidade por usuário no gateway** · Bloqueia: **F1**
- *Dúvida:* em que campo da requisição vai o `cvp-<matrícula>` (header ou corpo, nome exato); se vai **junto com** o
  `x-api-key` ou no lugar dele; formato exato aceito (maiúsculas ou minúsculas — o Orquestra grava a matrícula em
  **MAIÚSCULAS**, `api/routers/auth.py:38`); se toda matrícula real é `cvp` + dígitos ou existem exceções.
- *Como validar:* (1) procurar a documentação do gateway (OpenAPI em `{base_url}/openapi.json` ou `/docs`, se existir; o
  painel `ritm_geresd_ed.html` do repo privado `sge`, pasta `chamado`, mostra como a estação chama hoje) e/ou perguntar ao
  time do gateway; (2) com a matrícula **do próprio usuário**, uma chamada mínima enviando o identificador no campo
  candidato, testando as duas caixas; (3) contagem no banco, **sem listar matrículas**:
  `SELECT COUNT(*) AS total, SUM(CASE WHEN matricula LIKE 'CVP[0-9]%' THEN 1 ELSE 0 END) AS padrao_cvp FROM dbo.etl_usuario WHERE ativo = 1;`
- *Registrar:* campo e nome exatos; junto/no lugar do `x-api-key`; caixa aceita; exemplo mascarado; as duas contagens.
- *Padrão se não der:* agentes ficam em `sem_contrato` (desligados). Nada é chutado.
- *Impacto:* §3 (Identidade), F1 (`agentes_gateway_campo_usuario`), critério F1.3.
- **Resultado:** _(preencher)_

**D-02 — Respostas do gateway por causa** · Bloqueia: **F1**
- *Dúvida:* status, corpo e headers relevantes em cada caso: (a) usuário cadastrado; (b) usuário **não** cadastrado;
  (c) chave do app inválida; (d) gateway inalcançável; (e) 429. Em especial: **(b) e (c) diferem?**
- *Como validar:* uma chamada mínima por caso. (b) exige identidade que o time do gateway confirme como não cadastrada
  (aviso prévio); (c) pode usar uma chave claramente falsa, com autorização do time; (d) URL/porta errada só para ver
  o tipo do erro no cliente.
- *Registrar:* tabela caso × status × corpo (redigido) × headers × tempo.
- *Padrão se não der:* a **chamada de controle** com a identidade do app (já prevista) decide entre `sem_cadastro` e
  `chave_do_app_invalida`. Se (b) e (c) forem idênticos, o controle passa a ser obrigatório, não opcional.
- *Impacto:* §3 (Sonda), F1.4, texto do aviso.
- **Resultado:** _(preencher)_

**D-03 — A chamada mínima (sonda)** · Bloqueia: **F1**
- *Dúvida:* o gateway aceita `max_tokens` baixo? Há custo ou cota por usuário que a sonda consuma? Devolve 429? Depois
  do cadastro do usuário, **quanto tempo** até valer (cache do gateway)?
- *Como validar:* 3 chamadas com `max_tokens` mínimo; perguntar ao time do gateway sobre cota e propagação (ou medir num
  cadastro real que esteja para acontecer).
- *Registrar:* `max_tokens` mínimo aceito; cota; tempo de propagação.
- *Padrão se não der:* TTL de `ok` = 10 min, `sem_cadastro` = 60 s, `gateway_indisponivel` sem cache.
- *Impacto:* TTLs do §3, F1.4.
- **Resultado:** _(preencher)_

**D-04 — Limites e latência do gateway** · Bloqueia: **F2**
- *Dúvida:* tamanho máximo de mensagem; timeout real do gateway (o cliente usa 60 s, `TIMEOUT_S`); latência típica; aceita
  `messages` com vários turnos e `tools`? (informativo — a spec não depende disso).
- *Como validar:* 5 chamadas curtas e 3 com ~10 000 caracteres (uma transcrição de 12 rodadas + contexto); anotar p50/p95 e
  qualquer erro por tamanho.
- *Registrar:* p50/p95 para os dois tamanhos; maior mensagem aceita; suporte a multi-turno e `tools`.
- *Padrão se não der:* teto de 240 s por rodada (D-14 ✅) e 12 rodadas de histórico (o teto do Maestro).
- *Impacto:* `ORCAMENTO_AGENTE_S`, teto de contexto, F2.8.
- **Resultado:** _(preencher)_

**D-05 — Como pedir o cadastro no gateway** · Bloqueia: **F3** (só o texto)
- *Dúvida:* canal (link, e-mail, chamado), quem atende e em quanto tempo.
- *Como validar:* perguntar ao time do gateway; documentar.
- *Registrar:* o texto exato do aviso (vai para `agentes_cadastro_texto`, editável no Admin).
- *Padrão se não der:* aviso genérico "solicite o cadastro no gateway de IA" — **sem inventar link**.
- *Impacto:* F3.3.
- **Resultado:** _(preencher)_

**D-06 — Provedor e configuração de IA em produção** · Bloqueia: **F1**
- *Dúvida:* o provedor configurado é `caixa_gateway`? Modelo? `base_url`? `usa_proxy`? O diagnóstico passa?
- *Como validar:* `SELECT config_key, CASE WHEN config_key LIKE '%api_key%' THEN '<oculto>' ELSE config_value END AS valor FROM dbo.etl_app_config WHERE config_key LIKE 'caixa_ia_%' OR config_key IN ('maestro_enabled','chamados_triagem_habilitada');` e rodar **Admin › Caixa Seguro IA › Verificar**, registrando a frase do diagnóstico.
- *Registrar:* provedor, modelo, se usa proxy, resultado do Verificar (sem a chave).
- *Padrão se não der:* assume `caixa_gateway`; se for outro, o agente fica `provedor_incompativel` (o agente exige identidade por usuário) — decisão **B-10**.
- *Impacto:* §3, F1.
- **Resultado:** ✅ **21/09/2026** (leitura de `etl_app_config` em produção): provedor `caixa_gateway`, modelo `claude-sonnet-4-6`, `usa_proxy = 1` (**o padrão do código é 0** — ver D-17); host `servicosstdev…` (o nome sugere ambiente de DEV). Último diagnóstico guardado: `ok` em **21/08/2026 — desatualizado**; re-rodar *Verificar* (D-17).

**D-07 — O `dsjob` de verdade** · Bloqueia: **F2**
- *Dúvida:* formato, tamanho e tempo da saída de `ljobs`, `lstages`, `lparams`, `jobinfo` e `report` — **e de `dsjob -lprojects`** (candidato a entrar na allowlist para validar o nome do projeto); **o que aparece para
  parâmetro Encrypted**; o comportamento com o nome em **caixa diferente** e com **job inexistente** (a mensagem exata vira aprendizado).
- *Como validar:* pelo Console DataStage (ou `run_dsjob`) para **3 jobs**: um paralelo, uma sequence, e um com parâmetro Encrypted; mais **um `-lprojects`**.
- *Registrar:* por comando: `exit_code`, bytes, duração, 5 a 10 linhas **redigidas**; a linha (mascarada) do parâmetro Encrypted; a mensagem dos dois erros.
- *Padrão se não der:* parser conservador, saída truncada, e tudo que parecer valor de parâmetro é redigido.
- *Impacto:* parser e truncagem da F2, regras de `redigir()`, semente da F6, F2.4.
- *Limitação conhecida de `redigir()` (F2, revisão adversarial 4ª rodada):* a função mascara da keyword sensível (`senha`/`password`/`Encrypted`/etc.) até o **fim da mesma linha** — nunca vaza um campo diferente, mas se o `dsjob` real formatar um parâmetro `Encrypted` "bonito", com a keyword e o valor em **linhas separadas** (ex. `Parameter: DB_PASS\nType: Encrypted\nValue: {iisenc}...\n`), a linha do valor de verdade não tem a keyword e pode escapar sem máscara. **Validar isso especificamente** ao registrar as 5-10 linhas redigidas do D-07: se o `dsjob` de verdade formatar assim, `redigir()` precisa aprender a olhar a PRÓXIMA linha (ou N linhas) depois de uma keyword sozinha numa linha, não só a mesma linha.
- **Resultado:** _(preencher)_

**D-08 — Como saber que um job mudou** · Bloqueia: **F2 / F5**
- *Dúvida:* o `dsjob` (`-jobinfo`, `-report`) expõe data de modificação? A API REST que o lineage ISX usa
  (`ds_last_modified`) responde só metadados, sem exportar ISX? A que custo?
- *Como validar:* olhar a saída do D-07; numa consulta de metadados do mesmo job pela API REST, comparar com
  `etl_ds_job_isx.ds_last_modified`.
- *Registrar:* qual fonte dá a data, se dá para consultá-la sem exportar, e o tempo.
- *Padrão se não der:* **prazo de 7 dias** (`agentes_fato_validade_dias`) para fatos de `dsjob`/SFTP; ISX continua por `ds_last_modified`.
- *Impacto:* validade da base primeiro (§3), F2.3, F5.
- **Resultado:** _(preencher)_

**D-09 — Capacidade de sessões SSH** · Bloqueia: **F2**
- *Dúvida:* `MaxSessions`/`MaxStartups` do `sshd` do servidor DataStage e quantas conexões o Console, Utilitários, lineage e
  DAGs já abrem no pico. Qual teto é seguro para o agente?
- *Como validar:* se houver acesso ao servidor DataStage, `sshd -T | grep -Ei 'maxsessions|maxstartups'` e a contagem de
  conexões SSH estabelecidas no horário de pico; senão, pedir os dois números ao administrador do servidor.
- *Registrar:* os dois parâmetros, a conexão média e a de pico, e o teto recomendado.
- *Padrão se não der:* `agentes_ssh_max = 10` (o pico de usuários informado), configurável, com espera limitada.
- *Impacto:* F2.5, Admin › Agentes.
- **Resultado:** ⚠️ **21/09/2026:** o agente validador **não conseguiu autenticar por SSH** no servidor DataStage (senha ou chave) — o que **não prova nada sobre a API** do Orquestra. Padrão `agentes_ssh_max = 10` mantido. Para fechar: (1) confirmar no **Console DataStage do Admin** que o `dsjob` responde hoje; (2) pedir ao administrador do servidor `MaxSessions`/`MaxStartups`.

**D-10 — Tamanho da base já mapeada** · Não bloqueia (informa F5)
- *Dúvida:* quantos jobs já têm ISX na base × quantos existem no DataStage.
- *Como validar:* `SELECT COUNT(*) AS jobs_isx, COUNT(DISTINCT ds_project) AS projetos FROM dbo.etl_ds_job_isx;` e
  `SELECT COUNT(*) AS linhas_isx_auto FROM dbo.etl_job_lineage WHERE extraction_method = 'isx_auto';`; o total de jobs por
  projeto via `ljobs` (só a contagem).
- *Registrar:* os números e o percentual coberto.
- *Padrão se não der:* assume que a maioria dos jobs está fora de pipeline (por isso `etl_agente_fato` é tabela própria).
- *Impacto:* valor do base-first e peso da F5.
- **Resultado:** ✅ **21/09/2026:** **5 jobs em 2 projetos** em `etl_ds_job_isx`; **8 linhas** `isx_auto` em `etl_job_lineage`. Base muito pequena: a maior parte das respostas virá do `dsjob` ao vivo (confirma a tabela própria `etl_agente_fato`, B-05) e o **grafo só existirá para esses 5 jobs** enquanto o agente não puder disparar extração ISX (B-02).

**D-11 — Raízes SFTP** · Não bloqueia (decide o v1)
- *Dúvida:* quais raízes do servidor `datastage` estão ativas na tela Utilitários e se há ISX/DSX/relatórios úteis ao mapeamento.
- *Como validar:* ver a configuração das raízes ativas (`api/services/ssh_arquivos.py`, `SERVIDORES['datastage']` e a função
  de raízes) e listar (só nomes de pasta) o que há nelas.
- *Registrar:* raízes ativas e o que serve para mapeamento.
- *Padrão se não der:* a ferramenta SFTP fica **fora do v1**.
- *Impacto:* §3 (ferramentas), F2.
- **Resultado:** ✅ **21/09/2026:** raízes ativas `/Projetos/BI_CVP/Scripts` e `/Projetos/BI_CVP`; sem ISX/DSX úteis ao mapeamento → **SFTP fora do v1**.

**D-12 — Erros reais de acesso já vistos** · Bloqueia: **F6** (semente)
- *Dúvida:* quais falhas de acesso/leitura do DataStage mais acontecem hoje.
- *Como validar:* `SELECT TOP 20 erro, COUNT(*) AS n FROM dbo.etl_ds_job_isx WHERE erro IS NOT NULL GROUP BY erro ORDER BY n DESC;`
  e os logs do `orquestra-api` (mensagens de `dsjob`/SSH/ISX).
- *Registrar:* as 10 assinaturas mais frequentes (redigidas) e a correção conhecida de cada uma.
- *Padrão se não der:* a semente inicial usa só o que já é sabido (caixa do nome do job, `~/` no `DS_ISTOOL_AUTHFILE`, allowlist).
- *Impacto:* semente da F6 (**B-12**).
- **Resultado:** ✅ **21/09/2026:** 1 erro em `etl_ds_job_isx.erro`: "XML da definição do job inválido (reference to invalid character number: line 172, column 611)" — job com caractere inválido no XML. Entra na semente da F6, com linha/coluna normalizadas na assinatura.

**D-13 — Esquema real em produção** · Bloqueia: **F1**
- *Dúvida:* larguras reais (`etl_usuario.matricula`, `etl_job_lineage.extraction_method` — a 106 diz `VARCHAR(20)`, o
  `schema_prod_dev.sql` diz `VARCHAR(50)`), colunas de `etl_app_config`, **todos os perfis** de `etl_perfil_permissao`
  (para semear `tela_agentes`) e usuários ativos por perfil.
- *Como validar:* `SELECT TABLE_NAME, COLUMN_NAME, CHARACTER_MAXIMUM_LENGTH FROM INFORMATION_SCHEMA.COLUMNS WHERE (TABLE_NAME='etl_usuario' AND COLUMN_NAME='matricula') OR (TABLE_NAME='etl_job_lineage' AND COLUMN_NAME='extraction_method') OR TABLE_NAME='etl_app_config';`
  e `SELECT perfil_nome, COUNT(*) FROM dbo.etl_usuario WHERE ativo = 1 GROUP BY perfil_nome;` e `SELECT DISTINCT perfil_nome FROM dbo.etl_perfil_permissao;`
- *Registrar:* larguras, colunas e a lista de perfis (só nomes de perfil e contagens).
- *Padrão se não der:* (obsoleto — a `tela_agentes` agora nasce **só no perfil `admin`**.)
- *Impacto:* §4, F1.1.
- **Resultado:** ✅ **21/09/2026:** `etl_usuario.matricula VARCHAR(20)`; `etl_job_lineage.extraction_method VARCHAR(50)`; `etl_app_config`: `config_key VARCHAR(100)`, `config_value VARCHAR(1000)`, `descricao VARCHAR(500)`, `updated_at DATETIME`, `updated_by VARCHAR(100)`. 12 usuários ativos: admin 2, consulta 4, desenvolvedor 6; `operador` existe em `etl_perfil_permissao` sem usuários. **8 de 12 seguem `CVP`+dígito; 4 não** → D-16.

**D-14 — `proxy_read_timeout` de produção** · Bloqueia: **F2**
- *Dúvida:* qual `location` do nginx **de produção** atende `/orquestra/` e qual o seu `proxy_read_timeout` (o de produção
  está à frente do repo; no repo há 120 s numa location e 300 s noutra).
- *Como validar:* ler o `nginx.conf` em uso no servidor (não o do repo).
- *Registrar:* o timeout efetivo da rota da API.
- *Padrão se não der:* (fechada — ver Resultado; o teto adotado é 240 s.)
- *Impacto:* `ORCAMENTO_AGENTE_S`, F2.8.
- **Resultado:** ✅ **21/09/2026:** `proxy_read_timeout 300s` na location `/orquestra/`; os 120 s são da `/api/v1/` (Airflow). O `nginx.conf` do repo tem o mesmo valor (conferido). Teto do agente: **240 s**. Não verificado: balanceador/proxy corporativo antes do nginx.

**D-15 — Estado do `dags/` em produção** · Não bloqueia (informa F4/F7)
- *Dúvida:* o `etl_log_cleanup.py` de produção já tem a tarefa `limpar_conversas_maestro` (do pacote de 10/09)? Se não, o
  `dags/` não é sincronizado desde então e o deploy da F4 vai levar mudanças acumuladas.
- *Como validar:* procurar `limpar_conversas_maestro` no arquivo de produção e comparar com o do repo.
- *Registrar:* sim/não e o que diverge.
- *Padrão se não der:* o deploy da F7 responde **s** em `dags/` e revisa o diff antes.
- *Impacto:* roteiro de deploy da F7, smoke k).
- **Resultado:** ✅ **21/09/2026:** o `etl_log_cleanup.py` de produção já tem `limpar_conversas_maestro` → o `dags/` do pacote de 10/09 foi sincronizado. O deploy da F4 só acrescenta `limpar_conversas_agentes`.

**D-16 — Usuários fora do padrão `CVP`+dígitos** · Bloqueia: **F1** · **✅ decidido pelo usuário em 21/09/2026**
- *Dúvida (histórico):* 4 dos 12 usuários ativos (D-13) não seguem `CVP`+dígitos; o que enviar ao gateway por eles?
- **Decisão:** o identificador enviado ao gateway é o **campo do cadastro** (`etl_usuario.identidade_gateway`) **quando preenchido**; senão o **modelo padrão** `cvp-<matrícula em minúsculas>`. Ver §3 (Identidade), §4, F1 e risco 16.
- *O que resta (operacional, não bloqueia a F1):* saber **qual identificador o gateway conhece** para cada um dos 4 e preenchê-lo em Admin › Usuários **antes de conceder o agente** a eles (deploy da F7). A forma dos 4, sem listar matrículas: `SELECT perfil_nome, LEN(matricula) AS tam, LEFT(matricula, 3) AS prefixo, COUNT(*) AS n FROM dbo.etl_usuario WHERE ativo = 1 AND matricula NOT LIKE 'CVP[0-9]%' GROUP BY perfil_nome, LEN(matricula), LEFT(matricula, 3);`
- **Resultado:** ✅ decisão registrada (21/09/2026).

**D-17 — O gateway configurado é o de produção?** · Bloqueia: **F1** · **✅ decidido pelo usuário em 21/09/2026**
- *Dúvida (histórico):* o host configurado (`servicosstdev…`) tem "dev" no nome; e `usa_proxy = 1` (o padrão do código é 0).
- **Decisão:** manter. O gateway "dev" **é o mais usado pela produção** hoje; a ferramenta é **de outra área e será alterada no futuro**. Seguimos como está, inclusive `usa_proxy = 1`.
- *Consequência:* o contrato validado (D-01 a D-03) vale para esse gateway; **na troca futura, repetir D-01 a D-03**. Por isso o local do identificador e a regra da sonda ficam em config e atrás de `ia_provedor` (§3). O *Verificar agora* do smoke da F0 confirma que a chamada segue funcionando (o último diagnóstico guardado é de 21/08).
- **Resultado:** ✅ decisão registrada (21/09/2026).

**D-18 — Chaves de IA em produção e quem as usa** · Bloqueia: **F0**
- *Dúvida:* quais das 7 chaves `caixa_ia_*` existem hoje em `etl_app_config`; quais consumidores estão **ligados** (`maestro_enabled`, `chamados_triagem_habilitada`,
  `caixa_ia_enabled`); e se o `dags/utils/triagem_ia.py` que roda no **worker** é o do repo (o deploy da triagem foi parcial em 21/08).
- *Como validar:* `SELECT config_key, CASE WHEN config_key LIKE '%api_key%' THEN '<oculto>' ELSE config_value END AS valor, updated_at FROM dbo.etl_app_config WHERE config_key LIKE 'caixa_ia_%' OR config_key IN ('maestro_enabled','chamados_triagem_habilitada') ORDER BY config_key;`
  e comparar (hash) o `dags/utils/triagem_ia.py` do worker com o do repo.
- *Registrar:* chaves presentes, flags, e igual/diferente no arquivo do worker.
- *Padrão se não der:* assume as chaves presentes e a triagem desligada; a migration 116 copia só o que existir.
- *Impacto:* janela de transição e critério F0.1; risco 18.
- **Resultado:** _(preencher)_

**D-19 — A pasta DSX em produção** · Bloqueia: **F2b** (só a parte DSX)
- *Contexto (usuário, 21/09):* os arquivos `.dsx` **já existem nas pastas do Airflow, para consulta**. No código: `DSX_BASE_DIR=/opt/airflow/dsx`; o `orquestra-api` a monta **`:ro`** (`docker-compose.yaml`) e já
  usa o `DSXEngine` em `api/routers/lineage.py`; os arquivos são publicados por `scripts/export_dsx.sh` (`dsexport`/`dscmdexport`/`istool`) — a tela "Impacto por Campo/Tabela/Arquivo" os lê.
- *Dúvida:* quais projetos têm `.dsx` na pasta de **produção**, de que **data** e **tamanho**; quem/como os atualiza (o `export_dsx.sh`, à mão?) e com que frequência; o container `orquestra-api` em
  execução enxerga a pasta; o DSX **cobre** os jobs dos 2 projetos que têm ISX e os dos pipelines; se aparecem **dados sensíveis** (usuário/senha de stage, valores `{iisenc}`) num DSX real; e quanto o `DSXEngine` demora num arquivo grande; e se o **nome de cada arquivo `.dsx` bate** com `etl_pipeline.project_name` e com o nome real do projeto no DataStage (a **resolução do projeto** depende dessa convenção: projeto = nome do arquivo).
- *Como validar (somente leitura):* `docker compose exec orquestra-api ls -la --time-style=long-iso /opt/airflow/dsx` (nomes, tamanhos, datas); conferir que `GET /lineage/dsx-files` (ou a tela de impacto)
  lista os mesmos arquivos; `SELECT extraction_method, COUNT(*) AS n FROM dbo.etl_job_lineage GROUP BY extraction_method;`; num DSX, **procurar** (sem copiar o conteúdo) `Password` e `iisenc` só para
  registrar **se existem** e como aparecem — a amostra vai **redigida**; cronometrar um `listar_jobs` e um `buscar_campo` no maior arquivo.
- *Registrar:* lista `projeto → tamanho → data`; quem atualiza e quando; se a API vê a pasta; cobertura dos projetos; se há segredo no DSX (sim/não e a forma); tempos.
- *Padrão se não der:* `dsx_consulta` com nome e data do arquivo em toda resposta, `redigir()` sobre o conteúdo e teto de tempo no executor; o DSX fica **atrás** da base/`isx_auto` na preferência.
- *Impacto:* F2b, §3 (ferramentas), riscos 24 e 27.
- **Resultado:** ⚠️ **PARCIAL (22/09/2026, usuário rodou em produção):** `SELECT extraction_method, COUNT(*) FROM dbo.etl_job_lineage GROUP BY extraction_method;` devolveu `NULL: 27`, `dsx_auto: 92`,
  `isx_auto: 8`, `manual: 220` — confirma que a extração **DSX está ativa e é a maior fonte automática de lineage em produção** (92 registros, bem mais que `isx_auto`). **Não** confirmado: `ls -la` da
  pasta real (projeto→tamanho→data), se há segredo no conteúdo de um `.dsx` real, se o nome de cada arquivo bate com `project_name`, tempo do `DSXEngine` num arquivo grande. **Decisão:** aplicar
  direto o *padrão se não der* já descrito acima (nome+data do arquivo sempre na resposta, `redigir()` sobre TUDO que `dsx_consulta` devolver, DSX sempre atrás de base/`isx_auto`) — é o comportamento
  conservador que seria implementado de qualquer forma, e os 92 registros confirmam que a ferramenta tem uso real. Segue **aberta só para o detalhe fino** (validar quando houver acesso de shell ao
  container de produção).

**D-20 — `acao_editar` do perfil `desenvolvedor` em produção** · Bloqueia: **F2b**
- *Dúvida:* a extração ISX (`POST /lineage/isx/extrair`) exige `acao_editar`, e o agente só extrai para quem a tem. No seed da migration 019 o `desenvolvedor` a tem, mas o Admin edita as permissões dos perfis:
  em produção ela continua lá? E os 6 desenvolvedores ativos (D-13) a têm de fato?
- *Como validar:* `SELECT perfil_nome FROM dbo.etl_perfil_permissao WHERE recurso = 'acao_editar';` e, para saber se algum desenvolvedor **perdeu** a permissão por override, conferir a tela Admin › Usuários (só contagem).
- *Registrar:* quais perfis têm `acao_editar` hoje.
- *Padrão se não der:* assume que o `desenvolvedor` a tem; quem não a tiver recebe o link da Governança em vez da extração.
- *Impacto:* F2b (critério 1), smoke d2.
- **Resultado:** ✅ **22/09/2026 (usuário rodou em produção):** `SELECT perfil_nome FROM dbo.etl_perfil_permissao WHERE recurso = 'acao_editar';` devolveu `admin`, `desenvolvedor` — confirma que o
  `desenvolvedor` TEM `acao_editar` em produção hoje (nenhum override individual verificado, mas o seed da 019 está intacto no perfil). **D-20 fechada** — a extração ISX pelo agente (crítério 1) pode
  seguir sem o fallback "link da Governança".

### 8.2 Decisões que dependem do usuário (com padrão assumido)

| ID | Decisão | Padrão assumido |
|----|---------|-----------------|
| B-01 | Posição do grupo **Agentes** na sidebar | Imediatamente antes de "Administração" (não reordena os existentes) |
| B-02 | O agente pode **disparar a extração ISX** (e DSX, e o que for necessário para trazer detalhes dos jobs) e **gravar o resultado no banco para melhorar a lineage**? | **Sim — decidido pelo usuário em 21/09/2026**, com estes limites: (a) o **usuário** precisa de `acao_editar`, como no botão da Governança; (b) allowlist **em código** — ferramenta nova só por PR, não uma lista aberta; (c) nunca importar, compilar, executar, parar ou apagar; (d) sem lote (é do admin); (e) DSX = **consulta** aos arquivos que já existem em `DSX_BASE_DIR` (somente leitura), sem exportar do servidor; (f) interpretações continuam só com aprovação |
| B-02b | **Ferramenta SFTP** no v1? | **Não** (D-11 ✅) |
| B-03 | Logs de execução (`logsum`/`logdetail`) como ferramenta? | **Fora** do v1 (podem ter valores de dados) |
| B-04 | O usuário pode **apagar a própria conversa**? | Não; a purga de 30 dias cuida |
| B-05 | Job **fora de pipeline**: fatos em `etl_agente_fato` (tabela nova), sem espelhar em `etl_job_lineage` | Sim, tabela nova; sem espelho |
| B-06 | Quem é o **curador** (`agente_curador`) e **quais desenvolvedores** recebem `agente_datastage` no começo | O **admin decide**, no menu Admin, usuário a usuário; só perfil `desenvolvedor`; ninguém recebe automático (o admin já tem tudo) |
| B-07 | **Política de leitura de conversas de terceiros** (o backlog) e se guardar conversas com matrícula por 30 dias precisa de aval de compliance | Só o dono lê; o backlog não começa sem política |
| B-08 | Os **30 dias** contam desde a última mensagem (A12) ou desde a criação? | Desde a última mensagem |
| B-09 | Linha de base do problema (A1): como o engenheiro entende um fluxo hoje e quanto leva | Sem número; registrar depois (opcional) |
| B-10 | Se o provedor de produção **não** for `caixa_gateway`: aceitar trocar? | Não se aplica: D-06 ✅ confirmou `caixa_gateway` |
| B-11 | Histórico enviado ao gateway na retomada | Últimas 12 rodadas |
| B-12 | Semente de aprendizados: quem aprova a lista inicial | O curador, antes do agente usar |
| B-13 | **Nomes** da camada neutra: `api/services/ia_provedor.py`, chaves `ia_*`, aba **"IA"**, ações `ia_*`; o provedor `caixa_gateway` mantém o nome (é o destino, não o módulo) | Sim |
| B-14 | `caixa_ia_enabled` fica só dos assistentes do Caixa; **sem interruptor global** `ia_enabled` (cada consumidor tem o seu) | Sim |
| B-15 | **Transição:** copiar as chaves, ler nas duas, Admin espelhando nas antigas; **limpeza das antigas só depois** de confirmar `dags/`+worker (F0b) | Sim |
| B-16 | *(informativa — não bloqueia)* **Quando** o módulo Caixa sai do Orquestra? Só serve para ordenar o trabalho: a F0 **não remove** nada do Caixa, só faz o Caixa depender da camada nova de IA | Sem data: o Caixa continua funcionando sobre a camada nova; nada dele é removido aqui |
| B-17 | *(informativa — não bloqueia)* Algum script, workflow n8n ou relatório **fora do repositório** lê direto do banco as chaves de IA antigas (`caixa_ia_*` em `etl_app_config`)? A F0 cria chaves novas (`ia_*`) e **mantém as antigas**, então nada quebra agora; a resposta só decide se podemos **apagar as antigas** depois | Assume que não; as antigas ficam até a F0b, que só roda com a sua confirmação |
| B-18 | Maestro e triagem passarem a enviar a **identidade por usuário** (`cvp-<matrícula>`) no futuro | Fora: a camada já recebe `identidade` como parâmetro; eles continuam com `cvp-orquestra` |
| B-19 | A regra do lineage ("só há lineage para job **num pipeline**", por causa da FK em `etl_ds_job_isx`) **continua valendo**? | Sim: job fora de pipeline é extraído e respondido, mas os fatos vão para `etl_agente_fato`, não para `etl_job_lineage`; o agente sugere incluir o job num pipeline. Mudar a regra exigiria mexer no esquema da lineage (fora desta spec) |
| B-20 | **Admin** também pode usar o agente DataStage? | **Sim:** o admin sempre tem todos os menus e acessos — passa em `require_agente` por `acao_admin`, sem grant nenhum |
| B-21 | Quem vê o item **Agentes** do menu (`tela_agentes`)? | **Decidido em 21/09/2026:** é um recurso normal, **como qualquer outra tela** — semeado só no perfil `admin` (o admin já nasce com ela); para abrir a outros, o admin usa a **Admin › Perfis** já existente (perfil inteiro, ex. `desenvolvedor`) ou o grant por usuário — nenhum mecanismo novo |
| B-22 | O que vem do **DSX** grava em `etl_job_lineage` (`dsx_auto`)? | **Não** no v1: vai para `etl_agente_fato` (origem `dsx`, com a data do arquivo). O `dsx_auto` segue sendo gravado pelo fluxo que já existe (`PUT /lineage/job`, com `acao_editar`) |

### 8.3 Dúvidas que o código já respondeu (a fase confere; não dependem de produção)
- **C-01** `Governanca.tsx` não lê parâmetros de URL (`useSearchParams` sem ocorrência) → a F3 adiciona `?pipeline=&job=` (mudança mínima) ou o link abre a aba sem o job.
- **C-02** Reuso do grafo: `GrafoIsx.tsx`/`PainelJobIsx.tsx` com `GET /lineage/isx/job` (só banco, guard `get_current_user`) → a F3 confirma as props sem duplicar código.
- **C-03** O gateway recebe **uma** mensagem e hoje 401/403 vira 502 "chave recusada" → a F1 estende `ia_provedor` (ex-`caixa_ia`, renomeado na F0) sem mudar Caixa Seguro nem triagem (teste de igualdade do corpo/headers).
- **C-04** `run_dsjob` devolve até 200 000 caracteres de `stdout` → a F2 trunca por ferramenta antes de ir ao modelo.
- **C-05** `api/main.py` registra routers em **duas** listas (~linhas 147 e 207) → a F1 inclui `agentes` nas duas.
- **C-06** Purga em `dags/` usa `%s` (pymssql); a API usa `?` (pyodbc).
- **C-07** `NVARCHAR(n)` conta UTF-16 → `cortar_utf16` em título e corpo.
- **C-08** `auth.py:38` faz `usuario.upper()` → `identidade_gateway()` aplica `lower()` antes de montar `cvp-<matrícula>`.
- **C-09** `etl_app_config.descricao` é `VARCHAR(500)` (D-13 ✅) → os seeds da 117 preenchem `descricao`.
- **C-10** O consumidor de IA da árvore `dags/` (`dags/utils/triagem_ia.py`) **espelha** as chaves `caixa_ia_*` e não importa de `api/` → a F0 muda os dois lados e prende o espelho com teste.
- **C-11** `caixa_ia_enabled` governa só os assistentes do Caixa (comentário do próprio `triagem_ia.py`); Maestro (`maestro_enabled`) e triagem (`chamados_triagem_habilitada`) têm interruptor próprio.
- **C-12** Hoje citam `caixa_ia`: 7 arquivos de teste, `api/routers/{admin,maestro,caixa_chat}.py`, `dags/utils/triagem_ia.py`, `ui-react/src/pages/Admin.tsx`, `MaestroTab.tsx` e 5 docs; a migration `093_chamado_triagem.sql` cita `caixa_ia_enabled` e **não** é editada.

### 8.4 Critério de fechamento da spec
Todas as dúvidas **bloqueantes** (D-18 antes da F0; D-01, D-02 e D-03 antes da F1; D-04, D-07, D-08 e D-09 antes da F2; D-19 e D-20 antes da F2b; D-05 antes da F3) com status ✅ ou ⚠️ justificado; os pontos de **impacto** de cada uma atualizados neste arquivo; as decisões
B-xx confirmadas ou o padrão aceito. Então o status passa a **aprovada**, e o usuário autoriza o início da F1.

## 9. Registro da entrevista (decisões e itens assumidos)

**Decisões do usuário:** agente único de mapeamento DataStage, com outros agentes possíveis depois · todos acessam a tela,
agentes liberados por usuário · usuário logado vai ao gateway como `cvp-<matrícula>` e o gateway autoriza · consulta ao vivo ao DataStage sem alterá-lo (leitura e, desde 21/09, extração de definições), pela API do Orquestra (`DS_SSH_*`) · saída: chat, grafo e links · fatos gravados na hora; interpretação só
com aprovação do usuário na conversa · aprendizado: fatos na hora, interpretação com aprovação do curador · tokens **não**
são controlados · conversas salvas, retomáveis em até 30 dias, com busca; leitura do que entra e sai fica no backlog ·
visual com tokens neutros · até 10 usuários simultâneos, base primeiro · item novo "Agentes" no menu · deploys anteriores
confirmados (migrations 106–115 aplicadas, última em 14/09/2026 08:01; horário do banco é BRT).

**Decisões de 21/09/2026 (após a validação):** identificador no gateway = campo do cadastro se preenchido, senão `cvp-<matrícula>` (D-16) · gateway "dev" mantido, por ser o mais usado pela produção e ser de outra área, com troca futura (D-17) · o agente **pode disparar ISX, DSX e o necessário para trazer detalhes dos jobs e gravar no banco para melhorar a lineage** (B-02), dentro dos limites do B-02 — em especial `acao_editar` do usuário e allowlist em código.

**Decisões de 21/09/2026 (3ª rodada):** o agente DataStage é **só para o perfil `desenvolvedor`** e **só por inclusão manual, usuário a usuário** (nunca por perfil), por ser um agente único que toca o servidor; agentes futuros de **negócio e tabelas** poderão ter acesso mais amplo · o resto fica como está · **DSX**: os arquivos já existem nas pastas do Airflow, para consulta — o agente os consulta em leitura, não exporta do servidor.

**Decisões de 21/09/2026 (4ª rodada):** a tela e os agentes são decididos pelo **admin**, no menu Admin; o **admin já nasce com a tela e com todos os agentes** (sempre tem todos os menus e acessos) e **ninguém mais nasce com nada** · cada agente é concedido **usuário a usuário** · **no início de uma análise o chat pergunta o projeto** e o valida contra os `.dsx` (e a base): com match usa a hierarquia do DSX; **sem match, pula a hierarquia** e vai ao ISX e à produção, em vez de sair tentando nomes que não existem.

**Requisito novo (21/09/2026, durante a validação):** a IA hoje está centralizada no módulo Caixa (`caixa_ia.py`, chaves `caixa_ia_*`, aba "Caixa Seguro IA"), e o módulo Caixa vai para outra ferramenta em breve, ficando só o Orquestra; a camada de IA fica para o Maestro, a triagem, os agentes e outros módulos → **F0** (§5).

**Validação de produção (21/09/2026)** — por um agente validador, com leitura direta de banco, nginx e DAGs: 12 usuários ativos (admin 2, consulta 4, desenvolvedor 6), 8 com padrão `CVP`+dígito e **4 sem** (D-16) · gateway `caixa_gateway`, modelo `claude-sonnet-4-6`, `usa_proxy = 1`, host com "dev" no nome (D-17) · `proxy_read_timeout 300s` na `/orquestra/` (teto do agente 240 s) · base ISX com 5 jobs em 2 projetos e 8 linhas `isx_auto` · SFTP sem ISX/DSX úteis (fora do v1) · `etl_log_cleanup.py` já com `limpar_conversas_maestro` · nenhuma tabela `etl_agente_*` existe (a 117 é a primeira). **Não conseguiu autenticar por SSH no DataStage** (D-09 ⚠️), e por isso D-07 e D-08 continuam abertas.

**ASSUMIDOS:**
- **A1** O processo atual é leitura manual de ISX/DSX/Designer; sem linha de base numérica (B-09).
- **A2** Sonda mínima ao abrir a tela, com cache de sessão (a decisão de "só pela resposta do chat" já foi do usuário).
- **A3** Rota `/agentes`, item "Agentes" no menu.
- **A5** Acessibilidade no padrão do Orquestra.
- **A6** Sem dependência Python nova.
- **A7** Curador é um recurso RBAC novo (`agente_curador`).
- **A8** Validade: ISX por `ds_last_modified`; `dsjob`/SFTP por prazo de 7 dias (a confirmar no D-08).
- **A10** Teto de sessões SSH = 10, configurável (D-09 ⚠️: não verificado).
- **A11** Identificador = campo `identidade_gateway` do cadastro se preenchido, senão `cvp-` + matrícula em minúsculas (a confirmar no D-01; `lower()` obrigatório — C-08).
- **A12** Os 30 dias contam desde a última mensagem (B-08).
- **A13** "O que for necessário" (B-02) foi lido como *ferramentas de exportação/leitura que não alteram o DataStage*, numa allowlist em código — e não como lista aberta; a extração exige `acao_editar` do usuário e não há lote. O **DSX** é consulta aos arquivos que já existem em `DSX_BASE_DIR` (somente leitura).
- **A14** `tela_agentes` é recurso normal (perfil ∪ overrides, sem bypass), semeado só no perfil `admin`, extensível pela Admin › Perfis já existente. Acesso ao **agente** DataStage é diferente: **admin
  passa sempre** (`acao_admin`, via `require_agente`); não-admin = perfil `desenvolvedor` **+** grant em `permissoes_extra`, **sempre por usuário** (nunca por perfil — `require_agente` ignora essa origem
  para não-admin), concedido só pelo admin (menu Admin › Agentes); `agente_curador` segue a mesma política.
- ~~A4~~ (retenção de 180 dias) substituída pelos 30 dias; ~~A9~~ (meta de tokens) removida.
