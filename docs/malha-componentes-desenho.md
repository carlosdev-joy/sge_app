# Desenho técnico — Componentes de malha: Início · Aguarde · Notificação · Fim

Spec: `docs/spec-dependencias-pipelines.md` §4b (malha) e §3 (modelo push) · Base: main `5a7c8e9` (retomada F2–F6 completa: push/guardiã/ODATE vivos; malha F7–F9 + orientação 074) · Escopo: migration **075** + `api/routers/malhas.py` + `api/services/` + `ui-react/src/components/malhas/` + `dags/utils/` + `dags/etl_dependencia_guardia.py` (responsabilidade nova) + testes · **Zero mudança em `dags/etl_dag_factory.py`** — nenhuma DAG gerada muda de forma · Fases novas: **F10–F15** na numeração da spec da malha (F7–F9 entregues)

**O pedido (literal do usuário):** *"criar na malha um componente de INÍCIO de malha, um componente de NOTIFICAÇÃO, um componente de AGUARDE, e um componente de FIM, assim conseguimos criar as execuções com configuração na malha no primeiro componente de inicio OU ter a configuração na própria malha e dispara pelo início que agrega vários jobs iniciais em paralelo e depois usando os demais componentes"* — a sequence MESTRE do DataStage (Waits entre ondas de sequences) nativa na malha.

**A restrição inegociável, assumida como premissa de projeto:** os componentes são **açúcar de compilação** sobre os primitivos que já existem — agendamento nas raízes (colunas de `etl_pipeline` + cron do gerador), dependências globais (`etl_pipeline_dependencia`, 067) e observabilidade da guardiã (`etl_dependencia_evento` + cards Teams, F4). **Não nasce um segundo executor.** O modelo "DAG-mestre que dispara e espera" foi exatamente o sensor/DAG-de-DAGs que a spec matou com 36 defeitos em duas revisões adversariais; nada aqui reabre essa porta: em runtime, quem dispara é o scheduler do Airflow (raízes em cron) e o push da F3 (cadeia), e quem observa é a guardiã. A malha **compila o desenho para eles**.

## 0. Princípios herdados (spec §4b + F2–F5 §0 + reversão — regem tudo abaixo)

1. **A malha não executa** (spec §4b): nenhum componente cria task, DAG, sensor ou disparo próprio. Início vira colunas de agendamento nas raízes; Aguarde vira linhas na 067; Notificação/Fim viram eventos da guardiã. Se um componente precisar de algo que os primitivos não dão, a resposta é estender o primitivo na spec dele — nunca criar mecanismo na malha.
2. **Uma fonte de verdade** (F1/F8): a dependência é global na 067. Os nós **assinam** linhas (proveniência), não as duplicam. Nenhuma tabela nova guarda dependência.
3. **O estado do DagRun é decidido pelas folhas** (lição E, PR #229): este desenho não toca `etl_dag_factory` — o conjunto de folhas e trigger_rules de toda DAG gerada permanece byte-idêntico. Não existe superfície para reeditar o "verde escondendo falha".
4. **Contrato EXISTS intocado**: a liberação continua sendo exclusivamente `liberado()` de `dags/utils/dependencias.py`; o claim, a devolução e o ciclo da guardiã não mudam uma linha.
5. **Desenhar É fazer** (F8): gesto no canvas tem efeito real, imediato e consentido — nunca um estado em que o desenho conta uma história e o motor outra. Este princípio decide a estratégia de compilação (§7).
6. **Degradação nunca é 500 cru**: sem a 075, leitura degrada com `migration_075_pendente` e escrita dá 503 com instrução — padrão literal de `malhas.py` (070/067/074).
7. **Placeholder por árvore** (GOTCHA registrado): `?` em `api/`, `%s` em `dags/`. Regra pura canônica em `dags/utils/`, port na API com teste de paridade — o precedente é `api/services/data_referencia.py` e `api/services/dependencias.py`.
8. **Rede não ruidosa** (causa D, D42/N10): todo evento novo é idempotente pela chave `ux_dep_evento`; observador sem upstream não emite nada; card positivo é opt-in.
9. **Republicação por carimbo** (F5/D30): mudar configuração compila carimbo `dag_config_pendente_em` — a regeneração é gesto do operador pelo fluxo que já existe. Nenhuma regeneração implícita, nenhum `force_all` escondido.
10. Nenhuma fase mergeia sem cenários **executados** no dev (regra da retomada; a suíte de aceitação desta feature nasce no §14).

---

## 1. Modelo de dados — migration 075

### 1.1 As duas tabelas novas e as três colunas

```sql
-- (A) Nós especiais — DESENHO por malha (não são orquestração)
CREATE TABLE dbo.etl_malha_no (
    id          INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_malha_no PRIMARY KEY,
    malha_name  NVARCHAR(200) NOT NULL
        CONSTRAINT FK_malha_no_malha REFERENCES dbo.etl_malha (malha_name)
        ON DELETE CASCADE,                     -- nó não vive sem a malha (padrão 070)
    tipo        VARCHAR(20)  NOT NULL,         -- 'inicio' | 'aguarde' | 'notificacao' | 'fim'
    config_json NVARCHAR(MAX) NULL,            -- §5/§6; validado na API (padrão aguarde_json/068)
    layout_x    FLOAT NULL,
    layout_y    FLOAT NULL,
    criado_em   DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
    criado_por  NVARCHAR(100) NULL
);
-- Um Início e um Fim por malha, garantidos no MODELO (índice filtrado), não só na API:
CREATE UNIQUE INDEX ux_malha_no_inicio ON dbo.etl_malha_no (malha_name) WHERE tipo = 'inicio';
CREATE UNIQUE INDEX ux_malha_no_fim    ON dbo.etl_malha_no (malha_name) WHERE tipo = 'fim';
CREATE INDEX ix_malha_no_malha ON dbo.etl_malha_no (malha_name);

-- (B) Arestas do desenho que envolvem nós (aresta pipeline→pipeline NÃO entra aqui — §1.2)
CREATE TABLE dbo.etl_malha_aresta (
    id               INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_malha_aresta PRIMARY KEY,
    malha_name       NVARCHAR(200) NOT NULL
        CONSTRAINT FK_malha_ar_malha REFERENCES dbo.etl_malha (malha_name),  -- NO ACTION (§1.3)
    origem_no        INT NULL CONSTRAINT FK_malha_ar_ono  REFERENCES dbo.etl_malha_no (id),
    origem_pipeline  NVARCHAR(200) NULL
        CONSTRAINT FK_malha_ar_opipe REFERENCES dbo.etl_pipeline (pipeline_name) ON DELETE CASCADE,
    destino_no       INT NULL CONSTRAINT FK_malha_ar_dno  REFERENCES dbo.etl_malha_no (id),
    destino_pipeline NVARCHAR(200) NULL
        CONSTRAINT FK_malha_ar_dpipe REFERENCES dbo.etl_pipeline (pipeline_name),  -- NO ACTION (1785)
    CONSTRAINT CK_malha_ar_origem  CHECK ((origem_no IS NULL)  <> (origem_pipeline IS NULL)),
    CONSTRAINT CK_malha_ar_destino CHECK ((destino_no IS NULL) <> (destino_pipeline IS NULL)),
    -- A tabela declara no próprio modelo que NÃO é tabela de dependência:
    CONSTRAINT CK_malha_ar_tem_no  CHECK (origem_no IS NOT NULL OR destino_no IS NOT NULL)
);
CREATE UNIQUE INDEX ux_malha_aresta ON dbo.etl_malha_aresta
    (malha_name, origem_no, origem_pipeline, destino_no, destino_pipeline);
CREATE INDEX ix_malha_ar_ono ON dbo.etl_malha_aresta (origem_no);
CREATE INDEX ix_malha_ar_dno ON dbo.etl_malha_aresta (destino_no);

-- (C) Assinatura de proveniência na 067: quem compilou esta dependência
ALTER TABLE dbo.etl_pipeline_dependencia ADD origem_no INT NULL
    CONSTRAINT FK_dep_origem_no REFERENCES dbo.etl_malha_no (id);   -- NO ACTION de propósito (§1.4)
CREATE INDEX ix_dep_origem_no ON dbo.etl_pipeline_dependencia (origem_no) WHERE origem_no IS NOT NULL;

-- (D) Assinatura de agendamento na raiz: qual Início agenda este pipeline
ALTER TABLE dbo.etl_pipeline ADD agenda_no INT NULL
    CONSTRAINT FK_pipe_agenda_no REFERENCES dbo.etl_malha_no (id);  -- NO ACTION (§1.4)

-- (E) Agendamento da malha (fonte para compilação — o motor NUNCA lê daqui)
ALTER TABLE dbo.etl_malha ADD agendamento_json NVARCHAR(MAX) NULL;
```

Idempotente (`IF OBJECT_ID`/`COL_LENGTH`), aplicada na etapa 6c do `deploy.sh`. Lembrete de infra: `sql/migrate.py` descarta `PRINT` (D40) — nenhum relatório de migration é confiável; a conferência é por SELECT.

### 1.2 O que mora onde — a decisão estrutural

**Decisão 1 — nós e arestas-de-nó são DESENHO por malha; dependência continua global na 067; a ponte entre os dois mundos é a assinatura `origem_no`** *(evita: a segunda fonte de verdade de orquestração — a classe inteira do DAG-de-DAGs morto pela spec; e o compilador "cego" que não sabe o que é dele na hora de remover)*.

**Decisão 2 — aresta pipeline→pipeline NÃO entra em `etl_malha_aresta`** (o CHECK `CK_malha_ar_tem_no` torna isso impossível no modelo): desenhar aresta direta entre dois pipelines continua sendo o F8 intocado — grava direto na 067 via `POST /dependencias`, aparece em toda malha que contenha as duas pontas *(evita: duas semânticas para a mesma aresta na mesma tela; e a regressão dos aceites da F8, que são contrato validado em produção)*.

Alternativas pesadas para o modelo de arestas:

| Alternativa | Prós | Contras — por que não |
|---|---|---|
| (a) **Escolhida**: `etl_malha_aresta` só com arestas envolvendo nó; diretas seguem na 067 | F8 intocada; o modelo declara a fronteira; compilador simples | GET do detalhe monta o grafo de duas fontes (já monta hoje: membros da 070 + arestas da 067 — é uma terceira leitura, não um padrão novo) |
| (b) `etl_malha_aresta` com TODAS as arestas do desenho; compilador sincroniza a 067 inteira (compile-and-own total) | um lugar só para o desenho | segunda fonte de verdade; quebra "a mesma dependência aparece em toda malha" (F8); duas malhas com os mesmos pipelines brigariam pela posse da MESMA linha global — indecidível |
| (c) Nós como linhas sintéticas em `etl_malha_pipeline` (pipeline fantasma) | zero tabela nova | FK para `etl_pipeline` impede; nome sintético vazaria para push/guardiã/telas — a classe de bug da grafia (PR #236) multiplicada |

### 1.3 FKs e o erro 1785 (lição da 067, aplicada de propósito)

SQL Server recusa dois caminhos de cascade para a mesma tabela. Distribuição consciente, no precedente "1 CASCADE + 1 NO ACTION é aceito":

- `etl_malha_aresta → etl_malha` **NO ACTION** (o CASCADE viria por dois caminhos: direto e via `etl_malha_no`); a exclusão de malha não tem endpoint hoje (inativa-se) — se nascer um, a API apaga arestas→nós→membros→malha na mesma transação, explícito e ruidoso.
- `origem_no`/`destino_no` → `etl_malha_no` **NO ACTION** nos dois (dois cascades para a mesma tabela = 1785): a exclusão de nó é gesto da API que remove as arestas primeiro (§7.3) — um DELETE de nó por SQL direto com arestas penduradas falha alto, nunca leva desenho junto em silêncio.
- `origem_pipeline` **CASCADE** / `destino_pipeline` **NO ACTION**: excluir um pipeline que é perna de entrada limpa a aresta (como o membro some da malha, 070); excluir um pipeline que é saída de Aguarde é bloqueado — coerente com `FK_dep_predecessor` da 067, que já bloqueia excluir predecessor referenciado. Na prática a linha compilada da 067 bloquearia antes; a mensagem da API cita as duas causas.

### 1.4 A assinatura `origem_no` — NO ACTION, nunca SET NULL nem CASCADE

- **CASCADE** apagaria dependências reais como efeito colateral mudo de excluir um nó — a classe exata do "mudança de orquestração em silêncio" que a 067 bloqueou no modelo.
- **SET NULL** transformaria linha compilada em linha "manual" órfã — adoção silenciosa; o desenho da malha esqueceria o que criou.
- **NO ACTION** obriga a descompilação explícita (§7.3) a remover/transferir as linhas na MESMA transação da exclusão do nó — a ordem certa vira obrigatória no modelo, não promessa da API. Idem `agenda_no`.

## 2. Gramática do desenho e validações

### 2.1 Arestas permitidas

| Origem → Destino | Permitida | Significado |
|---|---|---|
| inicio → pipeline | sim | o pipeline é RAIZ da malha: recebe o agendamento compilado (§4) |
| pipeline → aguarde | sim | perna de entrada da junção |
| aguarde → pipeline | sim | o pipeline depende de TODO o upstream do Aguarde (§3) |
| aguarde → aguarde | sim | barreiras encadeadas (upstream transitivo — mesmo espírito do Aguarde das Etapas, §5.5) |
| pipeline/aguarde → notificacao | sim | ponto de escuta (§5) |
| pipeline/aguarde → fim | sim | conclusão da malha (§6) |
| inicio → nó · qualquer → inicio · notificacao/fim → qualquer | **não** (422) | Início só planta agenda em raiz; Notificação e Fim são OBSERVADORES terminais — se tivessem saída, precisariam ser primitivo de runtime, e não existe primitivo para isso (princípio 1) |
| pipeline → pipeline | fora desta tabela | é o F8 de sempre, direto na 067 |

`upstream(nó)` = todos os pipelines alcançáveis para trás através de arestas, **expandindo Aguardes transitivamente** (função pura, §3.2). Multiplicidade: 1 Início e 1 Fim por malha (índice filtrado + 422 com mensagem), N Aguardes e N Notificações.

### 2.2 Validações de desenho — a lição do nó Aguarde das Etapas

A lição registrada (spec do nó Aguarde §5.5 + F3 das Etapas): **ponta solta avisada no momento de consequência, não só num painel que ninguém abre**. Aqui o momento de consequência é o GESTO (a compilação é incremental, §7) — cada aviso sai no retorno do gesto que o cria (toast) **e** fica persistente num banner de avisos do editor enquanto durar:

| Situação | Tratamento |
|---|---|
| Aresta que criaria ciclo no grafo EXPANDIDO (§3.3) | **Erro 422**, mensagem literal única cliente=servidor (regra F8, `mensagensDependencia.ts`) |
| 2º Início ou 2º Fim | **Erro 422** (e o índice filtrado segura por baixo) |
| inicio → pipeline que TEM dependência na 067 | **Erro 422** ("raiz não pode ter dependência — `schedule=None` do motor venceria o cron e o agendamento da malha seria mentira") |
| Notificação/Fim sem entrada | **Aviso forte** + a guardiã NÃO avalia (nunca o "vacuamente verdadeiro" — Decisão 13) |
| Aguarde com saídas e 0 entradas | **Aviso forte**: "nenhuma dependência criada ainda — ligue as entradas" (o gesto é aceito: montar na ordem que quiser é legítimo; o efeito zero é dito, nunca subentendido) |
| Aguarde com 1 entrada | Aviso leve (junção de uma perna — provável esquecimento; Etapas §5.5) |
| Aguarde sem saída | Aviso leve (marco visual legítimo) |
| Início com agendamento e 0 saídas | Aviso forte ("o agendamento da malha não alcança nenhum pipeline") |
| Pipeline terminal da malha não ligado ao Fim | Aviso + botão **"prender as pontas soltas"** no painel do Fim: liga a ele todos os terminais membros (recicla o §7.4 das Etapas — barreira em um clique, arestas DESENHADAS, nada invisível) |
| Raiz assinada (`agenda_no`) que ganhou dependência por OUTRA porta (modal F5) depois | Badge de contradição no nó Início e no pipeline ("o motor obedece a dependência; o agendamento da malha está inerte") — aviso, não bloqueio das outras portas (§8 da coexistência) |

## 3. Aguarde — a junção que compila para N×M

### 3.1 Semântica

O Aguarde é **junção pura**: para cada saída-pipeline `D`, compila `D depende de P` para **cada** `P ∈ upstream(aguarde)` — linhas normais da 067, assinadas com `origem_no`. Cinco entradas × quatro saídas = 20 dependências reais em 9 arestas desenhadas — é exatamente a explosão de arestas manuais que o componente elimina. Depois de compilado, o runtime é 100% o motor existente: `schedule=None` nos dependentes (o gerador já faz isso para quem tem dependência), push do último predecessor que concluir, claim serializable, guardiã ordenando/alertando. **Nada re-avalia "o Aguarde" em runtime — o Aguarde não existe em runtime.**

**Decisão 5 — expansão N×M transitiva através de Aguardes; linha manual pré-existente não é adotada** *(evita: a explosão de arestas manuais; e a troca silenciosa de posse — uma dependência que o operador criou à mão continua sendo dele, o compilador reporta "já existia (manual) — não assinada" e a exclusão do nó não a leva)*.

**Decisão 6 — política única: EXISTS(SUCESSO) — "todas com sucesso na mesma data de referência". A política tolerante ("todas terminarem") fica OUT explícito** *(evita: mexer em `liberado()`/guardiã — o predicado canônico com paridade painel×motor; e a porta de volta do ALL_DONE que motivou a reversão)*. O caminho futuro, com dono: coluna `politica` em `etl_pipeline_dependencia` + extensão de `liberado()` para aceitar `SUCESSO|FALHA` nas arestas marcadas + revisão do `PREDECESSOR_FALHOU` da guardiã (que deixaria de valer para essas arestas) — é decisão de MOTOR, fase própria da spec de dependências, não da malha. Não existe versão barata honesta sem tocar o motor: qualquer simulação no nível da malha seria um segundo avaliador (proibido pela premissa). O painel do nó diz a semântica em linguagem de operador: *"libera quando TODAS as entradas tiverem SUCESSO na mesma data de referência; falha segura a malha e a guardiã alerta"*.

### 3.2 A função de expansão — canônica e pura

`dags/utils/malha_nos.py` (novo, puro — zero banco, zero Airflow):

```python
expandir(nos, arestas) -> dict
# nos = [{id, tipo}], arestas = [{origem_no|origem_pipeline, destino_no|destino_pipeline}]
# devolve, por nó: {"upstream": set[pipeline], "saidas_pipeline": set[pipeline]}
# e o conjunto compilado da malha: {(dependente, predecessor, no_id), ...}
# — upstream expande aguarde→aguarde por BFS; nó fora do grafo = sets vazios.
```

Consumidores: o compilador da API (port `api/services/malha_nos.py`, placeholder `?`, **teste de paridade** — precedente `data_referencia`/`dependencias`) e a guardiã (F14, importa o canônico direto — paridade por identidade de objeto, como a F4 fez). O GET do detalhe da malha devolve o `upstream` calculado por nó — o front nunca reimplementa a expansão (uma autoridade só; a mesma regra que salvou o texto do ciclo na F8).

### 3.3 Ciclo — validado sobre o grafo expandido

**Decisão 15 — o ciclo é validado sobre o conjunto PÓS-expansão do gesto** (067 atual − remoções do gesto ∪ adições do gesto), reusando o BFS da F1 no serviço, com a mensagem literal compartilhada *(evita: o defeito 3 do QA renascendo pela porta da expansão — um `aguarde` inocente pode fechar A→…→A por linhas que o gesto cria aos pares; validar aresta a aresta isolada não pega)*. O espelho client-side (`criaCiclo`) roda sobre o preview expandido que o dry_run devolve (§7.2) — cliente avisa antes, servidor é a autoridade, texto idêntico.

## 4. Início — o agendamento mora na malha; o nó é o plugue

### 4.1 Onde mora a configuração — RECOMENDAÇÃO

**Decisão 8 — o agendamento mora na MALHA (`etl_malha.agendamento_json`), editado pelo caminho da malha; o nó Início é a representação visual e o fio que diz QUEM recebe** *(evita: um segundo schema de agendamento vivo no motor; config órfã se o nó for excluído; e drift entre o form do nó e as validações reais do register)*. Pesado contra a alternativa "config no `config_json` do nó":

- O agendamento é propriedade do **conjunto** (uma malha = um calendário operacional), como `orientacao` (074) — o precedente de preferência por malha via PATCH existe e funciona.
- O motor lê agendamento **das colunas de `etl_pipeline`** — qualquer que fosse o lugar da cópia-mestre, a compilação teria de escrever nas colunas reais. Guardar a mestre na malha mantém o nó livre para ser recriado/movido sem perder configuração.
- JSON, não colunas novas em `etl_malha`: é fonte de compilação (o motor nunca lê daqui — comentário na migration), schema = exatamente o subconjunto de campos do register (`schedule_type/hour/minute/dow/dom`, `horarios_especificos`, `dias_semana`, `dias_horarios_mes`, `somente_dias_uteis`, `calendario_nome`, **`hora_virada`**), validado **pelas mesmas funções da API** (`_build_cron` para o domínio, `_validate_dias_horarios_mes`) — precedente do `aguarde_json` (068).

Na UI, clicar no nó Início abre o painel de agendamento (mesmos componentes do passo Agendamento do wizard) — o nó é a porta; o salvamento é `POST /malhas/{name}/agendamento`.

**Decisão 9 — `hora_virada` faz parte do agendamento da malha e é aplicada a TODAS as raízes** *(evita: o risco 4 da spec pela raiz — viradas divergentes entre predecessores são exatamente o que faz a junção "nunca liberar" e a guardiã gritar `DATA_DIVERGENTE` de configuração; uma malha, uma virada, e a corrida inteira junta no mesmo ODATE por construção)*.

### 4.2 O que a compilação faz — e por que "disparar em paralelo" não precisa de disparador

Compilar o Início = **copiar** os campos do `agendamento_json` para as colunas reais de cada pipeline ligado a ele + assinar `agenda_no` + carimbar `dag_config_pendente_em` (`WHERE dag_criada = 1`, o padrão da 073), numa transação. Todas as raízes ficam com o MESMO cron e a MESMA virada → o scheduler do Airflow dispara todas no mesmo tick, **em paralelo, cada uma na própria DAG** — o efeito "dispara pelo início que agrega vários jobs iniciais em paralelo" sem nenhum disparador novo, nenhuma DAG-mestre, nenhum ponto único de falha. O restante da malha corre pelo push da F3, herdando ODATE/dia operacional.

Regras do gesto (todas com dry_run + confirmação, §7.2):

- **Ligar `inicio → P`**: se a malha tem agendamento, o efeito mostrado é "P: agendamento atual (resumo) → agendamento da malha (resumo) · republicação necessária"; sem agendamento ainda, liga só o fio com aviso ("configure o agendamento no Início").
- **Salvar/alterar o agendamento**: efeito em TODAS as raízes ligadas, listadas uma a uma no diff do gesto.
- **Decisão 10 — desligar uma raiz (excluir a aresta) ou excluir o Início: a raiz vira `on_demand` + carimbo — nunca restauração do agendamento antigo, nunca cron remanescente** *(evita: a classe D40 — pipeline voltando a rodar sozinho em silêncio; `on_demand`→`schedule=None` é o primitivo seguro que já existe: DAG ativa, só manual, visível; restaurar "o que era antes" exigiria guardar história e devolveria um cron que ninguém revisou)*. O efeito é dito no diff do gesto; reagendar é gesto explícito do operador.
- **Decisão 11 — conflito de assinatura: `inicio → P` quando `P.agenda_no` pertence a OUTRA malha → 422 nomeando a malha e o nó donos** *(evita: last-write-wins mudo entre malhas — o desenho da perdedora mentiria para sempre; a regra é a mesma da linha assinada da 067: um dono por vez, transferência é gesto)*. P com agendamento próprio não assinado: pode — o diff mostra a substituição explicitamente (consentida).

## 5. Notificação — a guardiã como motor de observação

Nó observador com upstream `U` (pipelines, através de Aguardes). `config_json`: `{"titulo": str?, "mensagem": str?}`. Condição: **todos os `P ∈ U` com SUCESSO na data** — o mesmo contrato EXISTS, sobre lista explícita.

**Decisão 12 — Notificação e Fim são avaliados pela guardiã, dentro da MESMA task `ciclo`, como responsabilidade 5 (depois do fechamento §6 da F4); nenhum task nova em DAG nenhuma** *(evita: o segundo executor; e a classe da lição E — a guardiã segue com uma folha única, manuscrita, imune por construção)*. Mecânica, item a item com try/except (padrão D51):

1. Universo: `nos_observadores(conn)` — nós `notificacao`/`fim` de malhas **ativas** (`etl_malha.ativo=1`), com arestas; upstream via o canônico `expandir` (§3.2). Upstream vazio → pula com log (Decisão 13).
2. Datas: `D = calcular(agora, virada_comum(U))` e **também `D−1`** — janela fixa de dois rótulos derivada do presente, nunca varredura de histórico (a proibição do D45 é estrutural e continua: nenhuma data sai de `etl_pipeline_execucao`). O `D−1` existe para a cadeia noturna atrasada com virada 00:00: a malha que conclui 00:30 do dia seguinte não perde o aviso — a idempotência pela chave impede duplicata quando o evento já saiu no próprio dia. Viradas divergentes no upstream → pula com log (a face de configuração do `DATA_DIVERGENTE` da F4 já alerta essa doença na ordenação; o observador não adivinha).
3. Condição: `pipelines_todos_sucesso(conn, U, D)` — função nova em `dags/utils/dependencias.py` (contrato do módulo: *"nenhuma consulta paralela — pergunta nova entra AQUI"*), mesmo EXISTS de `liberado()`, sobre nomes explícitos.
4. Satisfeita → `gravar_evento(conn, f"#no:{id}", D, 'MALHA_NOTIFICACAO', detalhe)` — **a infra da F4 intacta**: chave idempotente `ux_dep_evento`, fila `eventos_nao_notificados`, `marcar_notificado` só após 2xx, canal da supervisão, lote com clamp. `detalhe` = título/mensagem do config + malha + a lista de U resumida. Card: `montar_card_dependencia` ganha o tipo no `ESTILO` (tom positivo/informativo — os quatro da F4 são de problema; este é o primeiro de conclusão).

`pipeline_name = "#no:{id}"` na chave do evento: o `id` é IDENTITY global (um nó, uma chave); o prefixo `#` não colide com `dag_id` válido do Airflow; comentário no código registra a convenção. `VARCHAR(30)` do tipo comporta (`MALHA_NOTIFICACAO` = 17). Zero DDL em eventos.

**Decisão 13 — observador sem upstream nunca emite (guarda dupla: aviso forte no desenho + skip em runtime)** *(evita: o "todos com sucesso" vacuamente verdadeiro virando card diário falso — a mesma doença dos 200 cards/dia do D42/N10, pela porta nova)*.

## 6. Fim — a conclusão da malha na data

Mesmo mecanismo da Notificação (responsabilidade 5), tipo **`MALHA_CONCLUIDA`**, upstream = os pipelines ligados ao Fim. A validação de desenho + o botão "prender as pontas soltas" (§2.2) empurram o operador a ligar TODOS os terminais — o desenho é a verdade explícita ("concluída" = o que está ligado concluiu; nada de inferência automática de "terminais da malha", que mudaria de significado a cada membro novo sem ninguém consentir).

**Decisão 14 — o card do Fim é opt-in (`config_json {"notificar_teams": false}` default); o evento e o painel são sempre** *(evita: a inundação diária de "concluída" em N malhas — rede ruidosa é rede ignorada, a lição-mãe da F4; quem quer o card no canal pede)*. `detalhe`: "Malha {nome} concluída na data {D} — {n} pipelines com SUCESSO".

Alimenta a F9: `GET /malhas/{name}/execucao` passa a devolver `malha_concluida: {"em": detectado_em} | null` (lido do evento da data) e os eventos dos nós da malha (hoje o endpoint filtra eventos por membro e descartaria `#no:*` — F14 acrescenta a busca por `#no:{id}` dos nós desta malha). O front mostra o **banner verde "Malha concluída em {D} às {HH:MM}"** no modo Execução. SUCESSO tardio via Clear: o evento sai quando a condição fechar (idempotente); evento emitido é histórico verdadeiro e não se apaga (filosofia F4 §7.2).

## 7. Compilação — quando, como, e o que acontece ao remover

### 7.1 Quando compila — a decisão de cadência

**Decisão 7 — compilação INCREMENTAL, por gesto, com o efeito mostrado ANTES (dry_run) e confirmação; o invariante é "o desenho É o compilado, sempre"** *(evita: o limbo desenho≠motor — a tela que mente, a classe de divergência que a retomada inteira existiu para matar; o TOCTOU de um diff global envelhecido; e duas cadências no mesmo canvas, já que a aresta direta do F8 é imediata por contrato validado)*.

O botão "Aplicar malha" global foi pesado e descartado:

| Alternativa | Por que perdeu |
|---|---|
| "Aplicar malha" com diff global (desenho staged) | cria o estado persistente "desenhado mas não aplicado" — precisa de linguagem visual própria, reconciliação, hash anti-TOCTOU; convive mal com as portas F5/F8 que continuam imediatas (a promessa "nada muda antes do Aplicar" seria falsa); e quebra a frase-mãe da spec §4b: *"desenhar uma aresta É cadastrar a dependência"* |
| Compilar no salvar do desenho inteiro (auto) | efeito composto sem consentimento por gesto — remoção de perna removeria N linhas sem o operador ver a lista |
| **Incremental por gesto (escolhida)** | cada gesto tem diff pequeno e legível (o SEU efeito), consentido no modal; o carimbo `dag_config_pendente_em` absorve o churn de republicação (idempotente — N gestos, uma republicação no fim, pelo fluxo existente); zero estado intermediário |

### 7.2 O contrato do gesto (dry_run)

Todo gesto de efeito composto (`POST/DELETE /malhas/{name}/arestas`, `DELETE /malhas/{name}/nos/{id}`, `POST /malhas/{name}/agendamento`) aceita `"dry_run": true` e devolve o efeito sem gravar:

```
{ "efeito": {
    "dependencias_criar":      [{dependente, predecessor}],
    "dependencias_remover":    [{dependente, predecessor}],
    "dependencias_transferir": [{dependente, predecessor, para_malha, para_no}],   // §7.3
    "ja_existentes_manuais":   [...],          // não serão assinadas
    "agendamentos":            [{pipeline, de, para}],
    "republicar":              [pipeline, ...] // quem recebe carimbo
  },
  "avisos": [...], "erros": [...] }
```

O front mostra o modal de confirmação com essa lista (mesma linguagem do modal de exclusão de aresta do F8: efeito real, dito antes); confirmar re-envia sem `dry_run`. O servidor **recomputa** no write (a autoridade é o estado corrente, não o preview) — se o resultado divergir do previsto (edição concorrente), o toast reporta o que de fato aconteceu, no padrão tolerante do `confirmarExclusao` do F8 (404 = "já não existia, segue"). Limitação assumida e documentada: a janela preview→confirm não é serializada — o write é atômico e honesto, e é isso que importa.

A transação do write (uma só, rollback explícito — padrão `malhas.py`): linhas 067 (INSERT assinado / DELETE por `origem_no`) + **espelho CSV `depends_on` de cada dependente afetado na MESMA transação** (regra viva da F6: o CSV é o fallback do factory pré-067 — o compilador usa o mesmíssimo `_espelho_csv`/serviço das portas F5/F8, nunca uma cópia) + colunas de agenda/assinaturas + carimbos.

### 7.3 Remover — nó, aresta, membro

- **Excluir aresta de nó**: recompila o(s) nó(s) afetado(s); linhas assinadas que a expansão nova não produz entram em `dependencias_remover`. Confirmação obrigatória quando remove ≥1 linha (a mesma barra do F8: "isto apaga dependências REAIS").
- **Excluir nó**: gesto destrutivo com confirmação; a transação remove as linhas assinadas (**ou transfere** — abaixo), as arestas do nó, o nó, e carimba os dependentes afetados. Início: raízes assinadas viram `on_demand` (Decisão 10). A FK NO ACTION da assinatura garante que não existe outra ordem possível (§1.4).
- **Transferência entre malhas (o caso 2-malhas, fechado):** na descompilação, linha assinada que a expansão de OUTRA malha também produz é **re-assinada para o nó da outra malha** em vez de removida, listada como `dependencias_transferir` no diff *(evita: M1 excluir seu Aguarde e derrubar em silêncio uma dependência que o desenho de M2 ainda mostra como viva — a divergência global mais traiçoeira deste modelo)*. Custo: expandir as malhas que compartilham os pares — barato no volume real (malhas são dezenas, não milhares).
- **Remover membro da malha** (`DELETE /malhas/{name}/pipelines/{p}`): hoje não toca a 067 (docstring explícita). Passa a RECUSAR (422) se o pipeline está ligado a nó desta malha ("desligue-o dos componentes primeiro") — remover o membro por baixo do desenho deixaria arestas apontando para um não-membro.

### 7.4 Coexistência — as regras consolidadas (a resposta à pergunta 1)

1. **Aditiva-com-assinatura, não compile-and-own** (**Decisão 3**): dependências criadas fora da malha (modal F5, F8 direto, register na criação) continuam existindo, aparecendo em toda malha que contenha as pontas, e editáveis pelas portas de sempre. A malha só é dona **das linhas que assinou** *(evita: a briga de posse entre 2 malhas sobre a mesma linha global; a morte das portas F5/F8 — contrato em produção; e a ambiguidade destrutiva de "tirei o membro, morrem as dependências dele?")*.
2. **Linha assinada só se mexe pela malha dona** (**Decisão 4**): `DELETE /dependencias` e o replace-all do `register` (chave `depends_on` presente) recusam com 422 nomeando malha e nó ("compilada pelo Aguarde X da malha M — edite lá"); o modal F5 mostra o chip travado com o mesmo texto *(evita: a divergência silenciosa desenho×motor — operador de M2 apagando no diagrama dele uma aresta que o Aguarde de M1 recriaria… ou pior, não recriaria nunca)*.
3. **Renderização**: no GET do detalhe, linha assinada por nó **desta** malha não vira aresta direta (ela é o desenho do nó); linha assinada por nó de **outra** malha vira aresta direta anotada `compilada_por: {malha, no}` — o editor a desenha com cadeado, somente-leitura. Linha manual coincidente com um caminho de Aguarde aparece como aresta direta além do caminho — honesta: ela existe além do nó.

## 8. Execução (F9) — os nós no modo Execução

O modo Execução (F9) já colore pipelines pelo status da data e trava a edição. Os nós ganham camada própria, derivada de dados que o payload já tem (custo zero de API além do §6):

| Nó | Estado exibido | Fonte |
|---|---|---|
| Início | resumo do agendamento + "próxima execução: {texto}" (helper display-only, mesmo estatuto do `calcularDataRef` da F5 — a autoridade é o scheduler) + contagem de raízes | `agendamento_json` + arestas (payload do detalhe) |
| Aguarde | **satisfeito** (todas as entradas SUCESSO em D — anel verde) · **bloqueado** (alguma FALHA/NAO_LIBEROU — anel vermelho, tooltip nomeia) · **aguardando** (anel âmbar, "faltam: X, Y") | derivação client-side de `execucoes[]` × `upstream` (o upstream vem do servidor, §3.2 — nenhuma expansão no front) |
| Notificação | "emitida às HH:MM" (evento `MALHA_NOTIFICACAO` da data) ou "aguardando" | eventos de nó no payload (F14) |
| Fim | "malha concluída às HH:MM" + o **banner** verde no topo; senão "em andamento" | evento `MALHA_CONCLUIDA` + `malha_concluida` (§6) |

Nó sem dado na data fica neutro — a regra F9 de nunca inventar cor.

## 9. Resumo da API

```
POST   /malhas/{name}/nos                      {tipo, config?, layout_x/y} → {id}
PATCH  /malhas/{name}/nos/{id}                 {config, layout}   (config validado por tipo)
DELETE /malhas/{name}/nos/{id}                 (?dry_run — efeito §7.3)
POST   /malhas/{name}/arestas                  {origem:{pipeline|no}, destino:{...}, dry_run?}
DELETE /malhas/{name}/arestas/{id}             (?dry_run)
POST   /malhas/{name}/agendamento              {agendamento, dry_run?}   (§4)
GET    /malhas/{name}        → + nos[] (com upstream), arestas_no[], arestas[].compilada_por
GET    /malhas/{name}/execucao → + eventos de nó (#no:*) + malha_concluida
PUT    /malhas/{name}/layout → aceita entradas "no:{id}" (grava etl_malha_no.layout_*)
```

Permissões: as mesmas da malha (`tela_malha` + `PERM_EDITAR` nas escritas). Degradação sem a 075: GET com `migration_075_pendente` (nós/arestas vazios, resto da malha intacto), escrita de nó/aresta 503 com instrução — o padrão literal das guardas 070/067/074 do arquivo.

## 10. Fases (F10–F15) — cada uma mergeável, com validação executável no dev

### F10 — Modelo e API do desenho (sem efeito)
- **Entrega:** migration 075; CRUD de nós e arestas de nó com a gramática do §2.1, unicidade, 422s; GET do detalhe estendido (nos com upstream via port da expansão + paridade, arestas_no, `compilada_por`); PUT layout aceitando nós; degradação sem 075. `dags/utils/malha_nos.py` (puro) nasce aqui com o port.
- **Aceite:** gramática recusada célula a célula da tabela §2.1; 2º Início = 422 e o índice filtrado segura um INSERT direto; excluir nó sem arestas ok; com arestas, a API remove na ordem (FK provada por tentativa direta); duas malhas com os mesmos pipelines criam nós independentes.
- **Validação:** pytest (paridade da expansão incluída) + smoke de API vivo no dev com SELECTs. Zero linha na 067 nasce desta fase. PR: `feat: malha — nós especiais (modelo e desenho)`.

### F11 — Compilador do Aguarde
- **Entrega:** efeito nos gestos (expansão → 067 assinada + espelho CSV + carimbo, transação única); dry_run; ciclo pós-expansão com mensagem única; descompilação com transferência entre malhas (§7.3); proteção de linha assinada nas TRÊS portas (DELETE /dependencias, `_gravar_dependencias` do register, modal F5 via estado); recusa de remover membro ligado a nó.
- **Aceite:** 3×2 no desenho = 6 linhas assinadas + CSV espelhado + carimbos; remover perna remove só o que a expansão perdeu; linha manual coincidente não é adotada nem removida; caso 2-malhas: exclusão do nó em M1 TRANSFERE para M2 (diff nomeia); ciclo via expansão = 422 com o texto canônico.
- **Validação:** pytest + **cascata REAL no dev**: compilar A,B→W→C,D pelos endpoints, republicar, rodar A e B → C e D partem pelo push com o MESMO ODATE — a prova de que o componente é açúcar sobre o motor, não motor. PR: `feat: malha — compilador do Aguarde`.

### F12 — Canvas: os quatro nós
- **Entrega:** paleta de componentes no MalhaEditor; `InicioNode`/`NotificacaoNode`/`FimNode` (cards) e `AguardeNode` (barra de sincronização — a linguagem BPMN do Aguarde das Etapas); gestos com modal de confirmação alimentado pelo dry_run; banner persistente de avisos + avisos no gesto (§2.2); "prender as pontas soltas" no Fim; cadeado nas arestas `compilada_por` de outra malha; orientação 074 respeitada nos handles.
- **Aceite:** desenhar a malha-exemplo do usuário (ondas + Waits) de ponta a ponta só pela tela; recarregar devolve desenho idêntico (round-trip — a lição write-only da causa C); todos os avisos aparecem no gesto que os cria.
- **Validação:** tsc + eslint + build (baseline HEAD) + smoke de tela vivo (lição F7: front e back de agentes separados exigem smoke de TELA ou checagem de contrato explícita). PR: `feat: malha — componentes no canvas`.

### F13 — Início: agendamento da malha
- **Entrega:** `agendamento_json` + `POST /malhas/{name}/agendamento` (validação reusando as funções do register); cópia às raízes + `agenda_no` + carimbo; conflito de assinatura (422); desligar → `on_demand`; painel do nó com o form de agendamento e o resumo; badge de contradição raiz-com-dependência.
- **Aceite:** salvar agendamento numa malha com 3 raízes → 3 pipelines com colunas idênticas (virada inclusive), 3 carimbos; republicar → crons idênticos na DAG gerada; desligar uma raiz → `on_demand` + carimbo, nunca cron velho; raiz de outra malha → 422 nomeando a dona.
- **Validação:** pytest + cenário vivo: 2 raízes de teste disparando NO MESMO TICK do scheduler no dev e empurrando a cadeia (SELECT em `etl_pipeline_execucao` com o mesmo ODATE). PR: `feat: malha — início e agendamento da malha`.

### F14 — Guardiã: Notificação e Fim
- **Entrega:** responsabilidade 5 no ciclo (após o fechamento §6/F4, try/except por nó); `pipelines_todos_sucesso` + `nos_observadores` em `dags/utils/dependencias.py`; janela {D, D−1}; tipos `MALHA_NOTIFICACAO`/`MALHA_CONCLUIDA` no `ESTILO` do card; endpoint de execução devolvendo eventos `#no:*` e `malha_concluida`; malha inativa ignorada.
- **Aceite:** condição fechada → 1 evento + card na fila; 200 ciclos = zero duplicata (chave); upstream vazio ou virada divergente → skip com log, zero evento; malha saudável incompleta → zero evento (anti-ruído); conclusão pós-meia-noite pega por D−1.
- **Validação:** pytest (banco stubado) + cenários vivos com trigger manual da guardiã (o harness da F4). **Deploy desta fase é só `dags/` — sem regerar DAG nenhuma** (factory intocado, padrão F4). PR: `feat: malha — notificação e fim pela guardiã`.

### F15 — Execução, manual e smoke consolidado
- **Entrega:** camada de execução dos nós (§8) + banner "malha concluída"; `docs/MANUAL_USUARIO.md` (seção "Componentes de malha", com o exemplo ondas+Aguarde e a semântica "todas com sucesso"); release note; roteiro de smoke de produção executável sem contexto.
- **Aceite:** modo Execução mostra Aguarde satisfeito/aguardando/bloqueado coerente com os SELECTs; banner na data concluída; roteiro executável por outra pessoa.
- **Validação:** tsc/eslint/build baseline + smoke vivo consolidado (o §14 inteiro re-executado). PR: `feat: malha — execução dos componentes e manual`.

Revisão adversarial antes de cada PR (regra da casa — o histórico desta spec é o argumento).

## 11. Riscos e mitigações

| # | Risco | Mitigação |
|---|---|---|
| 1 | Deploy parcial: API nova sem a 075 | Guardas por request + `migration_075_pendente` + 503 instrutivo (padrão 070/067/074 do próprio arquivo) |
| 2 | Compilação grava 067 mas o operador não republica → dependente segue no cron velho | O mesmo risco de QUALQUER edição de dependência hoje — coberto pelo carimbo/badge/aviso `msgRepublicar` da F5; o diff do gesto lista `republicar[]` explicitamente |
| 3 | Duas malhas, linha compartilhada, exclusão de nó | Transferência de assinatura no diff (§7.3) — nunca remoção silenciosa |
| 4 | Script/import com `depends_on` esbarra em linha assinada | 422 nomeando malha/nó (Decisão 4) — ruidoso por escolha; o corpo do erro instrui a porta certa |
| 5 | Raízes com viradas herdadas divergentes de outras fontes | Decisão 9 (virada única por malha) elimina para pipelines geridos pelo Início; para os demais, a F4 (`DATA_DIVERGENTE`) segue de guarda |
| 6 | Evento de nó com `pipeline_name` sintético vaza para consumidor que espera pipeline | Convenção `#no:{id}` documentada; o único leitor de eventos por malha é o endpoint da F14, que resolve os ids; o painel exibe tipo/mensagem crus (contrato F9: nunca esconder linha do banco) |
| 7 | Custo da responsabilidade 5 no ciclo de 5 min | Consultas por nó são 2 SELECTs baratos; try/except por nó; teto natural (nós ∝ malhas); se crescer, índice `(status, data_referencia)` já é a pendência registrada da F4 §10 |
| 8 | Editor com dois "tipos de aresta" confunde (direta imediata × de nó com efeito confirmado) | Ambas são imediatas e confirmadas quando destrutivas — a cadência é UMA (Decisão 7); a diferença é só quantas linhas o modal lista |

## 12. O que este desenho NÃO faz

- **Não cria executor**: nenhuma DAG nova (além de zero — a guardiã já existe), nenhuma task nova em DAG nenhuma, nenhum sensor, nenhuma DAG-mestre. Não toca `etl_dag_factory`, `liberado()`, claim, devolução, ordenação, fechamento — o motor F2–F4 é consumido, não editado.
- **Não muda a política de liberação**: "todas terminarem" fica OUT com caminho futuro nomeado (Decisão 6); OR/expressões seguem OUT (spec §2); job→job segue no backlog §9.
- **Não fecha as portas F5/F8**: modal e aresta direta continuam funcionando; a malha só protege o que assinou.
- **Não restaura agendamento antigo** ao desligar raiz (Decisão 10) e **não orquestra backfill** (reprocesso de data segue sendo o gesto manual com `conf` da F2).
- **Não infere o Fim**: "concluída" é o que está LIGADO ao Fim — o desenho é a verdade, a validação e o botão de pontas soltas fecham o vão.
- **Não desfaz compilação ao inativar a malha**: `ativo=0` desliga só os observadores (guardiã); as dependências e agendas compiladas são reais e continuam — desligar orquestração é excluir/desligar nós, com diff. Dito na tela ao inativar.
- **Não escreve SQL na DAG guardiã** (Decisão 15 da F4 mantida): as perguntas novas entram no módulo.

## 13. Testes (pytest; puros sem stub; banco stubado onde há conn; front por tsc/eslint/build + smoke)

1. **`expandir` (puro)**: N×M simples; aguarde→aguarde transitivo; aguarde sem entrada = conjunto vazio; nó isolado; paridade port API × canônico dags (matriz idêntica).
2. **Migration/modelo**: 075 2× sem erro; índices filtrados recusam 2º início/fim; CHECKs de aresta; FK NO ACTION da assinatura bloqueia DELETE de nó com linhas (teste vivo no dev).
3. **Gramática**: cada célula proibida da tabela §2.1 → 422 com a mensagem; ciclo via expansão detectado (o par que só existe expandido); mensagem idêntica à do BFS da F1.
4. **Compilador**: transação única (falha no meio → rollback total, nada de 067 sem CSV); assinatura correta; manual não adotada; remoção só do que a expansão perdeu; transferência 2-malhas; carimbo só com `dag_criada=1`; dry_run não grava (rowcounts zero).
5. **Proteções**: DELETE /dependencias de linha assinada → 422 nomeando; `_gravar_dependencias` com remoção que atinge assinada → 422; remover membro ligado a nó → 422.
6. **Início**: validação do JSON reusando as funções do register (domínio de `schedule_type`, `dias_horarios_mes`); cópia campo a campo inclusive `hora_virada`; conflito de assinatura; desligar → `on_demand` (nunca os valores antigos — teste de ausência); raiz com dependência → 422.
7. **Guardiã/observadores**: `pipelines_todos_sucesso` (todas/uma falta/FALHA/outra data/exceção→não — o espelho da matriz de `liberado`); janela {D, D−1} e SÓ ela (teste de ausência de varredura, como o D45); idempotência (2ª chamada False); upstream vazio → zero evento; malha inativa → zero; `montar_card_dependencia` com os 2 tipos novos; ciclo com 1º nó explodindo → 2º avaliado (D51).
8. **Ausências guardadas**: zero mudança em `etl_dag_factory.py` (diff vazio da árvore no PR das fases 10–13); zero SQL novo no fonte da DAG guardiã; nenhuma ordenação por `criado_em` nas consultas novas (D15).

## 14. Cenários de EXECUÇÃO no dev (Airflow :8082 + `orquestra_dev`, harness da retomada) — SELECT + UI em cada um

| # | Cenário | Prova |
|---|---|---|
| E1 | Desenhar A,B→W1→C,D pela API: 4 linhas assinadas na 067, CSV espelhado, carimbos; republicar; rodar A e B → C e D partem pelo push, mesmo ODATE | compilador = açúcar sobre o motor |
| E2 | Remover a perna B→W1 (dry_run mostra 2 remoções; confirmar): sobram (C,A),(D,A); rodar A sozinho → C e D partem | recompilação incremental |
| E3 | Malha M2 com A e C: aresta A→C aparece com `compilada_por` M1, DELETE → 422 nomeando M1/W1 | Decisão 4 |
| E4 | Excluir W1 em M1 quando M2 tem W2 que produz (C,A): diff mostra transferência; a linha continua, assinada por W2 | §7.3 |
| E5 | Encadeado A→W1→B→W2→C: C depende de B (e do upstream declarado); ciclo proposto C→W1 → 422 texto canônico | §3.2/§3.3 |
| E6 | Início com agendamento (weekly dow=0, virada 20:00) ligado a 2 raízes: colunas idênticas nas duas; republicar; as duas disparam no MESMO tick e a cadeia herda o ODATE | §4.2, Decisão 9 (e D05 de guarda: dow=0=domingo) |
| E7 | Desligar uma raiz: `on_demand` + carimbo; republicar → `schedule=None`; a DAG não roda mais sozinha | Decisão 10 (anti-D40) |
| E8 | `inicio→P` com P assinado por outra malha → 422 nomeando a dona | Decisão 11 |
| E9 | Nó Notificação em W1; rodar A e B → ciclo manual da guardiã → 1 evento `MALHA_NOTIFICACAO` `#no:{id}` + card na fila; 5 ciclos → zero duplicata | §5, D49 |
| E10 | Fim ligado aos terminais; completar a malha → `MALHA_CONCLUIDA`; F9 mostra o banner e o nó "concluída às HH:MM" | §6/§8 |
| E11 | Malha incompleta (falta 1 SUCESSO) + guardiã despausada 1h → ZERO evento de nó | anti-ruído (Decisão 13) |
| E12 | Pai concluindo 00:30 com virada 00:00 (fixture) → ciclo pós-meia-noite emite pela janela D−1 | §5 passo 2 |
| E13 | Notificação sem entrada: aviso forte no gesto; guardiã pula com log | Decisão 13 |
| E14 | Modo Execução: W1 "aguardando (falta B)" → rodar B → "satisfeito"; FALHA em A → "bloqueado" nomeando A | §8 |
| E15 | `sp_rename` na 075 → GET degrada com flag, escrita 503; restaurar → volta | princípio 6 |

## 15. Mapa decisão → defeito/risco que evita

| Decisão | Evita |
|---|---|
| 1. Desenho por malha + assinatura; dependência segue global | segunda fonte de verdade (a classe DAG-de-DAGs, 36 defeitos); compilador sem memória do que é seu |
| 2. Aresta direta fora da tabela de desenho (CHECK no modelo) | duas semânticas de aresta; regressão dos aceites F8 |
| 3. Aditiva-com-assinatura, não compile-and-own | briga de posse entre malhas; morte das portas F5/F8; ambiguidade destrutiva ao remover membro |
| 4. Linha assinada só pela dona (todas as portas recusam nomeando) | divergência silenciosa desenho×motor no caso 2-malhas; replace-all do register desfazendo compilação |
| 5. Expansão N×M transitiva; manual não adotada | explosão de arestas manuais; troca silenciosa de posse |
| 6. Política única EXISTS(SUCESSO); tolerante OUT com dono | tocar `liberado()`/guardiã; a porta de volta do ALL_DONE assassino (PR #229) |
| 7. Compilação incremental por gesto + dry_run + invariante desenho==compilado | o limbo staged (tela que mente, TOCTOU de diff global); duas cadências no canvas |
| 8. Agendamento na malha; nó = plugue; compilar = copiar p/ colunas reais | segundo schema de agendamento; factory intocado; config órfã em nó excluído |
| 9. Uma virada por malha | risco 4 da spec (viradas divergentes = junção que nunca libera) na raiz |
| 10. Desligar raiz = `on_demand`, nunca cron restaurado | D40 — pipeline voltando a rodar sozinho em silêncio |
| 11. Conflito de assinatura = 422 nomeando | last-write-wins mudo entre malhas |
| 12. Observadores pela guardiã, mesma task, janela {D, D−1} do presente | segundo executor; D45 (varredura histórica); perda do aviso pós-meia-noite; lição E preservada (folha única) |
| 13. Sem upstream → nunca emite (desenho + runtime) | o card vacuamente-verdadeiro diário (classe D42/N10) |
| 14. Card do Fim opt-in; painel sempre | inundação de "concluída" — rede ruidosa é rede ignorada |
| 15. Ciclo sobre o grafo expandido, mensagem única | defeito 3 do QA renascendo pela expansão; texto cliente≠servidor |
| 16. Zero mudança no factory e no predicado | regeração em massa desnecessária; a classe inteira da reversão |

**Arquivos tocados na implementação:** `sql/migrations/075_malha_nos.sql` (nova), `api/routers/malhas.py`, `api/routers/pipelines.py` (proteção de assinada), `api/services/malha_nos.py` (novo, port), `api/services/dependencias.py`, `dags/utils/malha_nos.py` (novo, canônico puro), `dags/utils/dependencias.py` (funções §5), `dags/etl_dependencia_guardia.py` (responsabilidade 5), `dags/utils/ds_teams.py` (2 tipos no `ESTILO`), `ui-react/src/components/malhas/` (nós novos + MalhaEditor + statusExecucao), `docs/MANUAL_USUARIO.md`, `tests/`. **`dags/etl_dag_factory.py` não é tocado.** Deploy: 075 na 6c → api + front (F10–F13, sem regerar DAGs — o carimbo/republicação cobre os afetados) → `dags/` na F14 (guardiã, sem force_all) → smoke §14 começando por uma malha de teste, não pela produção inteira.
