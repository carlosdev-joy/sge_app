# Spec: corrida de MALHA (`etl_malha_execucao`)

Data: 2026-08-04 · Status: 📝 **RASCUNHO — aguardando aprovação do usuário.**
⚠️ Custo de deploy já no topo: **de oito fases, só a F5 exige `force_all`.**
F1, F2, F3, F4, F6, F7 e F8 são migration + `api/` + `dags/utils/` + guardiã +
front — nenhuma toca o fonte gerado das DAGs. E o trem inteiro sobe **desligado**
por um interruptor em `etl_app_config` (`malha_corrida_ativa`, default `0`):
nenhuma fase muda o comportamento de produção no dia em que é mergeada.
Origem: três sintomas do mesmo buraco — (a) o card da malha diz "sucesso" com um
membro em FALHA (defeito relatado pelo usuário); (b) a janela do modo SEQUÊNCIA
(PR #274/#275) é um chute calibrado em horas; (c) o incidente de produção da
malha `Carga_Vida` (2026-08-04), em que **cada pipeline calculou o próprio
ODATE** e o Aguarde liberou por cima da divergência.

---

## 1. O problema (diagnóstico, não hipótese)

O Orquestra tem corrida de **PIPELINE** (`etl_pipeline_execucao`, chave
`ux_pipe_exec` = `pipeline_name + data_referencia + execution_id`) e **não tem
corrida de MALHA**. O ciclo da malha não é um registro: é uma **inferência**, e
hoje ele é inferido por **quatro réguas incompatíveis** — quatro respostas
diferentes para a mesma pergunta "onde começa e onde termina este ciclo?".

| Régua | Onde | O que ela responde | Onde erra |
|---|---|---|---|
| execução **mais recente** entre os membros | `api/routers/malhas.py:1541` e o laço de composição em `:1813-1830` | o status do card da lista | um membro que conclui bem **sobrepõe** um membro em FALHA |
| janela **desde a virada** corrente | `api/routers/malhas.py:2598` (`_datas_divergentes`), `:2619` (`_inicio_do_ciclo`), `dags/utils/malha_ciclo.py` | o bloqueio do disparo (F1/F5 da 081) | a virada é uma régua de calendário, não do ciclo; malha 23h→01h atravessa a fronteira |
| **últimas N horas** | `dependencia_janela_sequencia_horas` (migration 084) | o corte do modo SEQUÊNCIA | 12h é um chute: menor que o intervalo entre execuções e maior que a duração — calibrado à mão, malha a malha |
| evento `MALHA_CONCLUIDA` por `(nó, data_referencia)` | guardiã (`_observadores_malha`, `dags/etl_dependencia_guardia.py:691`) lido em `api/routers/malhas.py:2280-2286` | o banner "malha concluída" do painel | é chaveado por `(pipeline, data, tipo)` em `ux_dep_evento`: **a segunda conclusão do mesmo dia some em silêncio** |

### 1.1 Sintoma (a) — o card que mente

`_ultima_execucao_por_pipeline` (`api/routers/malhas.py:1541`) devolve, por
pipeline membro, a corrida **mais recente**. A composição por malha é este laço
(`api/routers/malhas.py:1819-1828`):

```python
atual = melhor.get(malha)
if atual is None or (u[0], u[2].casefold()) > (atual[0], atual[2].casefold()):
    melhor[malha] = u
```

A chave de comparação é `(momento_de_início, nome_do_pipeline)`. Ou seja: **o
status exibido no card é o status de UM pipeline — o que começou por último, com
desempate alfabético.** `CARGA_A` falha às 03:00, `CARGA_B` conclui às 03:40, e
o card da malha diz **sucesso**. Não é um bug de renderização: é a definição.

Isso é a família de defeitos mais cara do projeto — o **campo agregado que
mente**: o `ALL_DONE` verde com pipeline falho (PR #229), o "sucesso falso
recursivo" do DataStage, o observador vacuamente verdadeiro sem upstream. O card
da malha é o último membro vivo dessa família.

E há um terceiro estado que hoje simplesmente **não existe**: "em andamento". O
card só sabe pintar o verde/vermelho de um pipeline; uma malha de 40 membros com
4 concluídos e 36 correndo não tem como se dizer.

### 1.2 Sintoma (b) — a janela em horas é um chute

A migration 084 documenta a própria fragilidade no cabeçalho: *"Use um valor
MENOR que o intervalo entre execuções da malha e MAIOR que a duração dela"*. É
uma régua que o operador calibra por malha, sem ter os dois números. Errou para
menos, o predecessor legítimo cai fora e o Aguarde não solta; errou para mais, o
sucesso de ontem libera a rodada de hoje.

A pergunta que a janela tenta responder — *"este SUCESSO é desta rodada?"* — tem
uma resposta exata e barata que hoje não existe: **este sucesso aconteceu depois
que a corrida da malha começou?**

### 1.3 Sintoma (c) — o ODATE por pipeline (o incidente `Carga_Vida`)

`_data_referencia` é emitido **dentro do fonte gerado** de cada DAG
(`dags/etl_dag_factory.py:1553-1594`) e tem hoje dois degraus: herança pelo
`conf` e cálculo pela virada **do pipeline**. Quem não herda, calcula. Numa malha
que roda em torno do corte — a `Carga_Vida` começa 01:10 — pipelines separados
por minutos caem em dias diferentes, e a liberação
(`dags/utils/dependencias.py:336`) compara **só o ODATE**: metade dos membros no
dia 3, metade no dia 4, e o Aguarde liberou.

A spec `docs/spec-malha-data-unica.md` (migration 081) atacou isso em cinco
frentes — bloqueio no disparo, virada única por malha, equalização, trava no
push, trava no `check_agenda`. **Todas partem do pressuposto de que existe um
"ciclo" identificável**, e as cinco o reconstroem por janela de virada, que é
justamente a régua que não sabe onde o ciclo começou. A F5 chegou a implementar
isso literalmente (`dags/etl_dag_factory.py:1919-1921`): calcula `_dref`, calcula
`_desde` pela virada e pergunta o estado. É um ciclo **presumido**, não um ciclo
**registrado**.

**Causa raiz das três, uma só:** o ciclo da malha não tem identidade. Sem uma
linha que diga "este ciclo começou aqui, com este ODATE, e ainda não terminou",
cada consumidor inventa a sua régua, e réguas diferentes discordam exatamente nas
bordas — meia-noite, dois ciclos no mesmo dia, membro que roda por fora.

**Consultas de confirmação:** `docs/diagnostico-liberacao-datas.sql` (o ODATE
divergente) e, para o card, a query do §12.1 desta spec.

---

## 2. O que JÁ existe (levantado no código, não suposto)

| Peça | Onde | Situação |
|---|---|---|
| corrida de **pipeline** com claim serializable | `dags/utils/dependencias.py:436` (`reservar_corrida`) | ✅ pronta — chaveada em `(pipeline, data_referencia)`, **não se toca** (§3) |
| nós de malha (Início, Fim, Aguarde, Notificação) e expansão N×M | `dags/utils/malha_nos.py:32` + port `api/services/malha_nos.py:21` | ✅ pronta, com paridade — é de onde sai `conta_para_fim` |
| guardiã com ciclo de 5 min, `max_active_runs=1` e 9 responsabilidades ordenadas | `dags/etl_dependencia_guardia.py:832` | ✅ pronta — é o fechador natural (§6.3) |
| evento de malha por nó (`#no:{id}`) e o observador do Fim | `dags/etl_dependencia_guardia.py:691`, `dags/utils/ds_teams.py:25-48` | ⚠️ existe, mas o evento é chaveado por `(pipeline, data, tipo)` — a 2ª conclusão do dia some |
| bloqueio "malha suja" no disparo | `api/routers/malhas.py:2576` (`_STATUS_EM_ABERTO`), `:2582` (`_corridas_em_aberto`) | ⚠️ existe, mas por **execução viva de membro**, não por ciclo — não sabe dizer "este ciclo ainda está aberto" |
| virada única por malha | `etl_malha.hora_virada` (migration 081) | ✅ é o **insumo** do ODATE do ciclo; o que muda é quem a lê (§7) |
| hold do Aguarde e do Início | `etl_malha_no.retido_em/retido_por` (migration 082) | ✅ pronto — a corrida **lê**, nunca espelha (§6.7) |
| modo SEQUÊNCIA e sua janela | configs `dependencia_modo_sequencia` (083), `dependencia_janela_sequencia_horas` (084) | ⚠️ o interruptor fica; o **corte** muda (§8) |
| cascata de degradação por marca de migration | `dags/utils/dependencias.py:301` (`_MARCA_078`), `:615` (`_MARCA_082`) | ✅ o padrão a repetir — é a diferença entre degradar e parar a produção |
| `CAPACIDADES` lido por AST do bind mount | `dags/utils/dependencias.py:317`, leitor em `api/services/rerun.py:251` | ✅ é como a API pergunta ao motor "você entende isso?" |
| sonda do fonte **gerado** por marca sintática | `api/services/espera.py:160` (`MARCA_PORTAO`), `:214` (`portao_no_arquivo`), com o 3º valor `PORTAO_DESCONHECIDO` | ✅ é a ferramenta certa para provar o `force_all` da F5 |
| corrida de **malha** | — | ❌ **não existe nada** |

**Armadilha central descoberta:** `CAPACIDADES` responde *"o motor importado em
runtime entende o carimbo?"* — e o `deploy.sh` sincroniza `dags/` na etapa 5 mas
**nunca toca `generated/`** (`--exclude=generated/`, linhas 106 e 113). Declarar
`malha_corrida_085` em `CAPACIDADES` no commit que mexe no **fonte gerado**
seria declarar capacidade que não existe — o defeito que a própria docstring de
`CAPACIDADES` nomeia. A marca entra em `CAPACIDADES` na **F2** (guardiã, código
importado) e o fonte gerado é provado por **sonda de arquivo**, nunca por
`CAPACIDADES` (§12.2).

---

## 3. O que NÃO vamos fazer

**Trocar a chave de `etl_pipeline_execucao` por `(corrida, pipeline)`.**
`ux_pipe_exec` (`pipeline_name, data_referencia, execution_id`) aparece em **326
pontos de 34 arquivos** — claim, liberação, guardiã, visão de execução, eventos,
pausa de etapa (custo já medido em `docs/spec-malha-data-unica.md:40-46`).
Reescrevê-la é refazer o motor. A corrida de malha **acrescenta um vínculo**
(uma coluna `NULL`) e um estado; não substitui identidade nenhuma.

**Tocar o claim serializable.** `reservar_corrida`, `ordenar_corrida` e
`devolver_reserva` continuam chaveados em `(pipeline, data_referencia)`. A
corrida viaja como **atributo**, nunca como cláusula de porta — e a regra do
módulo é explícita: cláusula nova entra nas **três** portas ou em nenhuma.

**Exigir o nó Fim para a corrida existir.** 3 de 4 malhas do dev não têm Fim, e
toda malha criada antes da F14 não tem. Exigi-lo faria 75% delas nunca fecharem
— o card voltaria a mentir por outro caminho. Malha sem Fim fecha por
**quiescência** (§6.5), derivada do desenho, nunca configurada à mão.

**Backfill de corridas retroativas.** Toda linha do legado nasce com
`malha_execucao_id NULL`, e `NULL` significa literalmente *"rodou fora de
corrida"* — que é a verdade. **Inventar corrida retroativa é inventar verde
retroativo**, a mesma classe do card vacuamente verdadeiro que esta spec existe
para matar.

**Remover a janela em horas (084) nem trocar o default do modo SEQUÊNCIA
(083).** Dependência criada à mão pelo `POST /dependencias` tem `origem_no IS
NULL`: não pertence a malha nenhuma e não tem corrida a que se referir. A janela
vira o que sempre deveria ter sido — o **fallback de quem não tem corrida**. E
"sequência vira o padrão" é backlog: duas mudanças de comportamento no mesmo
deploy é uma a mais do que se consegue diagnosticar às 3h.

**Remover `hora_virada` (081) nem a equalização.** A virada continua sendo o
insumo que decide **qual** ODATE a corrida nasce carimbando; o que morre é ela
ser lida por **cada membro**. Migration aplicada não se altera.

**Nenhuma DAG nova, nenhuma task nova, nenhum sensor.** Quem fecha é a guardiã,
de fora (§6.3).

**Nenhuma tela nova.** A corrida entra nas telas que existem: lista de malhas,
painel de execução e canvas.

---

## 4. Decisões do usuário (2026-08-04)

1. **O nó INÍCIO abre a corrida da malha; o nó FIM a encerra.** O ciclo passa a
   ser delimitado pelos componentes do desenho, não por janela de calendário.
2. **Enquanto não passar pelo Fim, o ciclo está ABERTO.** Corrida aberta é o
   estado de primeira classe que hoje não existe.
3. **O card da malha só pode dizer "concluída" depois do Fim.** O status do card
   é da CORRIDA, nunca do membro que começou por último.
4. **O ODATE é carimbado UMA VEZ para a corrida inteira**, no lugar de cada
   pipeline calcular o seu.
5. **A janela do modo SEQUÊNCIA passa a ser "desde que ESTA corrida começou"** —
   exata e imune à meia-noite, no lugar das N horas calibradas.

**Leitura explícita da decisão 4 (o único ponto que a formulação deixou em
aberto):** o ODATE é carimbado **na ABERTURA**, não ao passar pelo Fim. Carimbar
no Fim seria tarde por definição — o ODATE é o dado que **todo membro precisa
antes de rodar**, é ele que entra na chave `ux_pipe_exec` da primeira linha. O
Fim **encerra** o ciclo e sela o desfecho; a abertura **carimba** o dia. Se essa
leitura não for a intenção, é o único item desta spec que muda de forma.

**Consequência que o usuário mesmo enxergou e está no escopo:** o incidente
`Carga_Vida` deixa de ser possível **por construção** dentro de uma corrida —
não porque uma trava o detecta, mas porque não há mais duas datas a divergir.

---

## 5. Modelo

### 5.1 Por que **duas** tabelas e **uma** coluna — e não uma coisa só

São duas perguntas diferentes, e respondê-las com a mesma estrutura produz o beco
do pipeline membro de N malhas:

| Pergunta | Cardinalidade | Onde mora | Quem escreve |
|---|---|---|---|
| *"De onde veio o ODATE desta linha de execução?"* | **1:N** — uma linha nasce de **uma** corrida (ou de nenhuma) | coluna `etl_pipeline_execucao.malha_execucao_id` | `_registrar_execucao` (caminho quente, fonte gerado) |
| *"Quem esta corrida está esperando para fechar?"* | **N:N**, e precisa ser **congelado** | tabela `etl_malha_execucao_membro` | a abertura da corrida, **uma vez** |

**Decisão 1 — a coluna é PROVENIÊNCIA, não participação** *(evita: escolher em
silêncio uma entre N malhas do pipeline, que é a mesma classe de defeito que
esta spec existe para matar)*. O ODATE tem exatamente uma origem — não há
ambiguidade a resolver. Já "quem conta para o fechamento" é do desenho, é N:N e
muda quando alguém edita a malha; por isso é snapshot em tabela própria, escrito
**fora** do caminho quente.

**Decisão 2 — a PROVA de que um membro concluiu é da linha no intervalo, nunca
da proveniência** *(evita: o pipeline `P`, membro de A e de B com as duas
abertas, carimbar a corrida de A e ficar **pendente para sempre** em B — B iria
a `FALHA` ou arrastaria até o teto, e a corrida perdedora congelaria a malha)*.
O predicado do §6.4 aceita a linha por `malha_execucao_id = @corrida` **ou** por
recorte de tempo. Sem isto, a corrida **piora** o compartilhamento: hoje
`_ultima_execucao_por_pipeline` ao menos enxerga a linha.

Alternativas descartadas:

| Alternativa | Por que não |
|---|---|
| **Só a coluna** em `etl_pipeline_execucao` | Membro de 2 malhas com 2 corridas abertas: a corrida perdedora nunca vê a linha (Decisão 2 é a correção, mas sem o snapshot não há denominador estável) |
| **Só a tabela de ligação** (`corrida × execution_id`) | Uma escrita a mais por run no fonte gerado, e o ODATE fica sem dono — que é a causa raiz (c) |
| **Nada — inferir por `(malha, data_referencia)`** | É o que existe hoje. Duas corridas no mesmo ODATE colidem, e a heurística de data **é** o defeito |

### 5.2 O que se materializa e o que não

**Decisão 3 — campo DERIVADO não se materializa; campo que existe para não
repetir um efeito colateral, sim** *(evita: o agregado guardado que só é
reescrito pela guardiã a cada 5 min mais 15 de carência — a tela mostraria "4 de
7" sem dizer que o número tem 20 minutos, e o operador ficaria batendo F5 num
valor congelado achando que é o de agora)*.

| Fato | Materializado? | Por quê |
|---|---|---|
| `membros_ok` / `membros_total` / `pendentes[]` / saúde | **não** — derivados em **uma** consulta agregada por corrida (§9.1), servindo card e painel | são a resposta a *"isso é verdade AGORA?"*; e um `GROUP BY` único não é o N+1 que `api/routers/malhas.py:1529-1530` se proíbe em comentário |
| `retido_desde` (hold) | **não** — é `MIN(retido_em)` dos nós da malha, lido na avaliação | espelho dessincroniza: com dois Aguardes segurados, soltar **um** limparia o espelho e o teto voltaria a correr com a malha ainda travada |
| `falha_vista_em`, `atraso_visto_em` | **sim** | existem só para **não repetir** o evento/card. É memória de efeito colateral, não estado |
| `teto_creditado_min` | **sim** | é fato acumulado e imutável ("quanto tempo já foi creditado por hold"); "está retido" é fato do agora e não se guarda |
| `status`, `data_referencia`, `aberta_em`, `fechada_em` | **sim** | são a corrida. É o registro que substitui as quatro réguas |

### 5.3 DDL — migration **085** (idempotente, blocos terminando em `GO`)

```sql
-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 085 — CORRIDA DE MALHA
--   O ciclo da malha deixa de ser inferido por quatro reguas incompativeis e
--   passa a ser UM REGISTRO: aberto pelo Inicio (ou pelo disparo), fechado
--   pelo Fim (ou por quiescencia/teto), carregando o ODATE do ciclo, o
--   instante de abertura e o desfecho.
--   Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

-- ── 1. A corrida ───────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.etl_malha_execucao', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_malha_execucao (
        id                  BIGINT IDENTITY(1,1) NOT NULL,
        malha_name          NVARCHAR(200) NOT NULL,  -- SEM FK: ver Decisao 5
        data_referencia     DATE          NOT NULL,  -- o ODATE, carimbado UMA vez
        sequencia           INT           NOT NULL,  -- rotulo humano: "2a corrida de 04/08"
        status              VARCHAR(20)   NOT NULL,
        aberta_em           DATETIME2     NOT NULL CONSTRAINT DF_mexec_ab DEFAULT SYSDATETIME(),
        fechada_em          DATETIME2     NULL,      -- NULL <=> ABERTA (CK abaixo)
        fechada_por         NVARCHAR(200) NULL,      -- 'guardia' | 'manual:C123456'
        origem              VARCHAR(20)   NOT NULL,  -- inicio|manual|implicita
        aberta_por          NVARCHAR(200) NULL,      -- 'inicio:#12' | 'manual:C123456'
        ancora_pipeline     NVARCHAR(200) NULL,      -- a raiz cuja linha ancorou a abertura
        ancora_execution_id NVARCHAR(250) NULL,
        no_inicio           INT           NULL,
        no_fim              INT           NULL,
        modo_fechamento     VARCHAR(20)   NOT NULL,  -- fim | quiescencia (§6.5)
        teto_em             DATETIME2     NULL,      -- aberta_em + teto_horas (§6.6)
        teto_creditado_min  INT           NOT NULL CONSTRAINT DF_mexec_cred DEFAULT 0,
        falha_vista_em      DATETIME2     NULL,      -- memoria do evento, nao estado
        atraso_visto_em     DATETIME2     NULL,
        tentativas          INT           NOT NULL CONSTRAINT DF_mexec_tent DEFAULT 1,
        reaberta_em         DATETIME2     NULL,
        reaberta_por        NVARCHAR(200) NULL,
        motivo              NVARCHAR(500) NULL,
        criado_em           DATETIME2     NOT NULL CONSTRAINT DF_mexec_cri DEFAULT SYSDATETIME(),
        atualizado_em       DATETIME2     NOT NULL CONSTRAINT DF_mexec_atu DEFAULT SYSDATETIME(),
        CONSTRAINT PK_etl_malha_execucao PRIMARY KEY CLUSTERED (id),
        CONSTRAINT CK_mexec_status CHECK (status IN
            ('ABERTA','CONCLUIDA','FALHA','SEM_TRABALHO','EXPIRADA',
             'ABORTADA','CANCELADA')),
        -- A invariante em forma de CHECK: "aberta" e "sem fechada_em" sao a
        -- MESMA coisa. Sem ela, o indice filtrado abaixo e o status poderiam
        -- discordar — a trava de disparo leria um e a tela leria o outro.
        CONSTRAINT CK_mexec_coerente CHECK (
            (status =  'ABERTA' AND fechada_em IS     NULL) OR
            (status <> 'ABERTA' AND fechada_em IS NOT NULL)),
        CONSTRAINT CK_mexec_modo   CHECK (modo_fechamento IN ('fim','quiescencia')),
        CONSTRAINT CK_mexec_origem CHECK (origem IN ('inicio','manual','implicita'))
    );
    PRINT '[OK] Tabela dbo.etl_malha_execucao criada';
END
GO

-- A INVARIANTE "um ciclo aberto por malha" mora no MODELO, nao na API.
IF OBJECT_ID('dbo.etl_malha_execucao', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'ux_malha_exec_aberta'
                     AND object_id = OBJECT_ID('dbo.etl_malha_execucao'))
BEGIN
    CREATE UNIQUE NONCLUSTERED INDEX ux_malha_exec_aberta
        ON dbo.etl_malha_execucao (malha_name) WHERE fechada_em IS NULL;
    PRINT '[OK] Indice ux_malha_exec_aberta criado';
END
GO

-- Card da lista: um SEEK por malha (a composicao em Python some).
IF OBJECT_ID('dbo.etl_malha_execucao', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'ix_malha_exec_malha'
                     AND object_id = OBJECT_ID('dbo.etl_malha_execucao'))
BEGIN
    CREATE NONCLUSTERED INDEX ix_malha_exec_malha
        ON dbo.etl_malha_execucao (malha_name, aberta_em DESC)
        INCLUDE (id, status, data_referencia, fechada_em, sequencia);
    PRINT '[OK] Indice ix_malha_exec_malha criado';
END
GO

-- Lente por data do painel + o rotulo humano da N-esima corrida do dia.
IF OBJECT_ID('dbo.etl_malha_execucao', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'ux_malha_exec_seq'
                     AND object_id = OBJECT_ID('dbo.etl_malha_execucao'))
BEGIN
    CREATE UNIQUE NONCLUSTERED INDEX ux_malha_exec_seq
        ON dbo.etl_malha_execucao (malha_name, data_referencia, sequencia);
    PRINT '[OK] Indice ux_malha_exec_seq criado';
END
GO

-- ── 2. O snapshot do denominador ───────────────────────────────────────────
IF OBJECT_ID('dbo.etl_malha_execucao_membro', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_malha_execucao_membro (
        malha_execucao_id BIGINT        NOT NULL,
        pipeline_name     NVARCHAR(200) NOT NULL,
        conta_para_fim    BIT           NOT NULL,  -- upstream expandido do no Fim
        ativo_na_abertura BIT           NOT NULL,  -- etl_pipeline.active na abertura
        eh_raiz           BIT           NOT NULL,  -- sem predecessor DENTRO da malha
        CONSTRAINT PK_etl_malha_exec_membro
            PRIMARY KEY CLUSTERED (malha_execucao_id, pipeline_name),
        CONSTRAINT FK_mexec_membro_corrida FOREIGN KEY (malha_execucao_id)
            REFERENCES dbo.etl_malha_execucao (id) ON DELETE CASCADE
    );
    CREATE NONCLUSTERED INDEX ix_mexec_membro_pipe
        ON dbo.etl_malha_execucao_membro (pipeline_name, malha_execucao_id);
    PRINT '[OK] Tabela dbo.etl_malha_execucao_membro criada';
END
GO

-- ── 3. O vinculo na corrida de PIPELINE ────────────────────────────────────
IF OBJECT_ID('dbo.etl_pipeline_execucao', 'U') IS NOT NULL
   AND COL_LENGTH('dbo.etl_pipeline_execucao', 'malha_execucao_id') IS NULL
BEGIN
    ALTER TABLE dbo.etl_pipeline_execucao ADD malha_execucao_id BIGINT NULL;
    PRINT '[OK] Coluna dbo.etl_pipeline_execucao.malha_execucao_id criada';
END
GO

-- FILTRADO de proposito: todo o legado e NULL, entao o indice nasce VAZIO e
-- cresce so com o que a feature produz. Um indice nao-filtrado aqui indexaria
-- a historia inteira por um valor nulo.
IF OBJECT_ID('dbo.etl_pipeline_execucao', 'U') IS NOT NULL
   AND COL_LENGTH('dbo.etl_pipeline_execucao', 'malha_execucao_id') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'ix_pipe_exec_malha'
                     AND object_id = OBJECT_ID('dbo.etl_pipeline_execucao'))
BEGIN
    CREATE NONCLUSTERED INDEX ix_pipe_exec_malha
        ON dbo.etl_pipeline_execucao (malha_execucao_id)
        INCLUDE (pipeline_name, status, data_referencia, inicio, fim,
                 substituida_em)
        WHERE malha_execucao_id IS NOT NULL;
    PRINT '[OK] Indice ix_pipe_exec_malha criado';
END
GO

-- ── 4. Idempotencia do evento POR CORRIDA ──────────────────────────────────
IF OBJECT_ID('dbo.etl_dependencia_evento', 'U') IS NOT NULL
   AND COL_LENGTH('dbo.etl_dependencia_evento', 'malha_execucao_id') IS NULL
BEGIN
    ALTER TABLE dbo.etl_dependencia_evento ADD malha_execucao_id BIGINT NULL;
    PRINT '[OK] Coluna dbo.etl_dependencia_evento.malha_execucao_id criada';
END
GO

-- O indice NOVO nasce ANTES de o velho sair: nunca existe instante sem
-- protecao. Em SQL Server os NULLs sao IGUAIS num indice unico, entao com
-- toda a historia em NULL o indice estendido e EXATAMENTE tao estrito quanto
-- o atual — nao ha de-dup a fazer, e a retrocompatibilidade e por construcao,
-- nao por sorte. (A ordem inversa — dropar e recriar — abriria uma janela em
-- que a guardia, que roda a cada 5 min, poderia inserir a duplicata que faz
-- o CREATE UNIQUE falhar e abortar o deploy na 6c.)
IF OBJECT_ID('dbo.etl_dependencia_evento', 'U') IS NOT NULL
   AND COL_LENGTH('dbo.etl_dependencia_evento', 'malha_execucao_id') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'ux_dep_evento_corrida'
                     AND object_id = OBJECT_ID('dbo.etl_dependencia_evento'))
BEGIN
    CREATE UNIQUE NONCLUSTERED INDEX ux_dep_evento_corrida
        ON dbo.etl_dependencia_evento
           (pipeline_name, data_referencia, tipo, malha_execucao_id);
    PRINT '[OK] Indice ux_dep_evento_corrida criado';
END
GO

IF OBJECT_ID('dbo.etl_dependencia_evento', 'U') IS NOT NULL
   AND EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'ux_dep_evento_corrida'
                 AND object_id = OBJECT_ID('dbo.etl_dependencia_evento'))
   AND EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'ux_dep_evento'
                 AND object_id = OBJECT_ID('dbo.etl_dependencia_evento'))
BEGIN
    DROP INDEX ux_dep_evento ON dbo.etl_dependencia_evento;
    PRINT '[OK] Indice ux_dep_evento substituido por ux_dep_evento_corrida';
END
GO

-- ── 5. Teto por malha ──────────────────────────────────────────────────────
IF OBJECT_ID('dbo.etl_malha', 'U') IS NOT NULL
   AND COL_LENGTH('dbo.etl_malha', 'teto_horas') IS NULL
BEGIN
    ALTER TABLE dbo.etl_malha ADD teto_horas INT NULL;   -- NULL = padrao global
    PRINT '[OK] Coluna dbo.etl_malha.teto_horas criada';
END
GO

-- ── 6. Configs (uma por bloco, todas idempotentes) ─────────────────────────
-- malha_corrida_ativa .......... 0 = KILL SWITCH: nada abre, nada fecha, o
--                                card usa o fallback e o ODATE fica no degrau
--                                de hoje. Ligado so depois do smoke.
-- malha_teto_horas_padrao ...... 24 (dominio 1..168)
-- malha_quiescencia_minutos .... 15 (dominio 5..240) = 3 ciclos da guardia
-- malha_carencia_partida_min ... 15 (dominio 1..240) piso para ABORTADA
IF OBJECT_ID('dbo.etl_app_config', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM dbo.etl_app_config
                   WHERE config_key = 'malha_corrida_ativa')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao)
    VALUES ('malha_corrida_ativa', '0',
            'Liga a corrida de malha (0/1). Com 0 nada abre nem fecha, o card usa o fallback e a data de referencia segue a regra anterior. Ligue somente apos o smoke.');
    PRINT '[OK] etl_app_config.malha_corrida_ativa criada (DESLIGADA)';
END
GO
-- (blocos analogos para malha_teto_horas_padrao = 24,
--  malha_quiescencia_minutos = 15 e malha_carencia_partida_min = 15)
GO
```

**Custo da migration, medido e honesto:**

| Operação | Custo |
|---|---|
| 2 `CREATE TABLE` vazias + 5 índices sobre elas | ~0 |
| 3 `ALTER TABLE ... ADD <col> NULL` **sem default** | **metadata-only** no SQL Server — instantâneo por definição, não por a tabela ser pequena |
| `ix_pipe_exec_malha` filtrado | nasce **vazio**, mas o SQL Server **varre a tabela inteira** para avaliar o predicado, sob `Sch-M`, dentro da transação do `migrate.py`, com a API antiga e o Airflow no ar. **É a única operação da 085 que bloqueia escrita do motor** — ver §11.3 (dimensionamento obrigatório antes do deploy) |
| `CREATE ux_dep_evento_corrida` + `DROP ux_dep_evento` | rebuild de uma tabela de histórico **de eventos** (um por `pipeline+data+tipo`, ordens de grandeza menor que `etl_pipeline_execucao`), na ordem segura descrita no DDL |
| **Backfill** | **NENHUM** (§3) |

### 5.4 Decisões de modelo

**Decisão 4 — o vínculo nasce `NULL`, e `NULL` significa "fora de corrida", que
é literalmente verdade para todo o legado** *(evita: backfill que inventa corrida
retroativa)*.

**Decisão 5 — `etl_malha_execucao` NÃO tem FK para `etl_malha`, e
`etl_pipeline_execucao.malha_execucao_id` NÃO tem FK para a corrida** *(evita:
(i) o erro 1785 de dois caminhos de cascade — `etl_malha → corrida → pipe_exec`
colidindo com o `CASCADE` que a 067 já tem; (ii) tornar a malha indeletável)*.
Precedente literal na casa: a migration **076 derrubou** a FK de
`etl_dependencia_evento` justamente para que histórico não morra com cadastro. A
integridade fica no código, como o marcador `#no:{id}` já faz. A FK que **fica**
é `membro → corrida` com `ON DELETE CASCADE`: o snapshot pertence à corrida e
morre com ela.

**Decisão 6 — `sequencia` sai de dentro do próprio `INSERT ... SELECT`, com
`WITH (UPDLOCK, HOLDLOCK)` sobre `(malha_name, data_referencia)`** *(evita: dois
redisparos simultâneos calcularem `MAX(sequencia)+1 = 2` e um deles violar
`ux_malha_exec_seq` — um índice **diferente** do de abertura, cujo tratamento é
oposto)*. É o padrão que `reservar_corrida`/`ordenar_corrida` já usam.

**Decisão 7 — o handler de violação distingue os índices PELO NOME na mensagem
de erro** *(evita: o handler genérico "2601 significa adere" aderir à corrida
errada — ou pior, a uma corrida FECHADA, deixando linhas carimbadas com id de
ciclo encerrado, invisíveis para o ciclo vivo)*. Só `ux_malha_exec_aberta`
significa "outra ponta abriu primeiro"; `ux_malha_exec_seq` significa "recalcule
a sequência e tente de novo". O repo já faz parsing de mensagem em
`_exec_com_fallback_078` e no fallback do `_MARCA_082`. E a releitura de adesão é
sempre `WHERE malha_name = ? AND fechada_em IS NULL`, **jamais** por
`(malha, data)`.

**Decisão 8 — toda transição da corrida é `UPDATE ... WHERE id = ? AND <estado
esperado>` com `rowcount` como árbitro** *(evita: duplo clique ou retry HTTP
incrementarem `tentativas` duas vezes, e duas pontas fecharem a mesma corrida
com desfechos diferentes)*. `rowcount = 0` não é erro: é "outra ponta chegou
primeiro" — `_rollback` e segue. É a regra do módulo inteiro
(`reservar_corrida`, `fechar_nao_liberou`, `fechar_orfa_em_execucao`).

**Decisão 9 — o carimbo do vínculo é WRITE-ONCE:
`malha_execucao_id = COALESCE(malha_execucao_id, %s)` no `UPDATE`, valor direto
só no `INSERT`** *(evita: reescrever o passado — o `UPDATE` de
`_registrar_execucao` roda a cada estado, e o Clear do rerun **reusa o mesmo
`run_id`**; sem o `COALESCE`, uma linha da corrida #12 reexecutada no dia
seguinte passaria a pertencer à #13)*.

**Decisão 10 — todo relógio da corrida é o do BANCO** *(evita: o desvio real
medido no dev — worker e API em `-03`, SQL Server em UTC, três horas à frente —
transformar teto de 24h em 27h, impedir a carência de quiescência de ser
satisfeita antes de 3h, e fazer `teto_em += (agora − retido_desde)` nascer
**negativo**, de modo que soltar um hold de 1h EXPIRARIA a corrida na hora)*. Não
existe aritmética de relógio da corrida em Python: `teto_em < SYSDATETIME()`,
`DATEDIFF(MINUTE, ..., SYSDATETIME()) >= @carencia`,
`teto_em = DATEADD(SECOND, DATEDIFF(SECOND, @retido_desde, SYSDATETIME()), teto_em)`.
Quando Python for inevitável, via `dep.agora_do_banco(conn)` + `desvio_banco`,
como `_divergencias_e_falhas` já faz (a lição está escrita em
`dags/utils/dependencias.py:830`).

---

## 6. Ciclo de vida

### 6.1 Dois eixos: CICLO e SAÚDE

```
 ciclo:   ABERTA ──┬──► CONCLUIDA      (passou pelo Fim / quiesceu com OK)
                   ├──► FALHA          (parou tudo e sobrou pendencia)
                   ├──► SEM_TRABALHO   (nada era esperado hoje — sabado)
                   ├──► EXPIRADA       (teto estourou E nada vivo)
                   ├──► ABORTADA       (zero linhas apos a carencia de partida)
                   └──► CANCELADA      (operador / malha excluida)

 saude (so faz sentido com ciclo = ABERTA, e e DERIVADA, nunca guardada):
          OK · COM_FALHA · ATRASADA · SEM_PROGRESSO
```

**Decisão 11 — o eixo de SAÚDE existe separado do eixo de CICLO** *(evita: o
defeito relatado mudar de rótulo em vez de desaparecer — numa malha de 40
membros, `CARGA_A` falha às 01:12 e os outros 38 seguem até 05:00; com um eixo
só, o card diria "em andamento desde 01:10 · 4 de 40", **em azul, por quase
quatro horas**, sem nada que informe que a corrida já está perdida. Descobrir às
05:00 é depois do SLA)*. O card mostra os dois:
*"em andamento desde 01:10 · 4 de 40 · **1 falha: CARGA_A às 01:12**"*, em
vermelho.

**Decisão 12 — `MALHA_FALHOU` é emitido na DETECÇÃO da primeira falha, não no
fechamento** *(evita: o Teams só tocar depois que tudo parou — que é tarde por
definição)*. `falha_vista_em` é a memória que impede repetir o card a cada ciclo
de 5 min.

**Reabertura:** devolve `fechada_em = NULL`, `status = 'ABERTA'`,
`tentativas += 1`, `reaberta_em/por` carimbados. **Só `CONCLUIDA` e `FALHA`
reabrem** — e só quando **não há outra corrida aberta da malha** (§6.9/#3).
`SEM_TRABALHO`, `EXPIRADA`, `ABORTADA` e `CANCELADA` são fim de linha.

### 6.2 Quem ABRE — três portas, uma invariante, e a coluna que faltava

**Decisão 13 — a abertura mora na GUARDIÃ e na API; o fonte gerado NUNCA abre
corrida** *(evita: quatro coisas de uma vez — (i) a inversão de ordem em que as
portas automáticas só existiriam na fase do `force_all`, deixando as fases
anteriores sem nada para exercitar e o card vazio para a maioria das malhas;
(ii) um abridor sem fechador, se `dags/` subir parcial: a guardiã é a mesma
árvore, então quem abre e quem fecha deployam juntos; (iii) caminhar o grafo
(`malha_nos.expandir`) **dentro do caminho quente** de toda raiz, com o import
pesado e o ponto de falha novo quando o grafo está quebrado; (iv) pagar
`force_all` a cada ajuste da regra de abertura)*. O custo é latência de até um
ciclo (5 min) entre a raiz partir e a corrida existir — coberto pelo recorte de
tempo da Decisão 2, e `aberta_em` **recua** para o instante da linha âncora, de
modo que a corrida nunca "perde" o trabalho que a originou.

| # | Porta | `origem` | Onde | O que faz **quando já existe corrida aberta** |
|---|---|---|---|---|
| 1 | `POST /malhas/{m}/disparo` | `manual` | `api/routers/malhas.py:2297`, na **mesma transação** dos bloqueios, **antes** dos triggers | **recusa 422** nomeando a corrida (é o bloqueio de hoje, com granularidade melhor), com a frase de ação e o botão de encerrar (§6.9/#14) |
| 2 | guardiã, ao ver uma **raiz assinada pelo Início** partir | `inicio` | `_abrir_corridas_malha`, responsabilidade nova | **adere** se o ODATE bater; **recusa e alerta** se divergir |
| 3 | guardiã, ao ver uma **raiz sem predecessor interno** partir em malha **SEM** Início | `implicita` | idem | idem |

**Decisão 14 — abertura é INSERT-first, nunca SELECT-then-INSERT** *(evita: a
corrida entre o clique no botão e o ciclo da guardiã, que hoje é uma janela real
porque as duas pontas consultam e decidem separadamente)*. Violação de
`ux_malha_exec_aberta` **não é erro**: relê e adere. É o padrão de
`reservar_corrida` (`dags/utils/dependencias.py:436-505`): claim, não check.

**Decisão 15 — a adesão CONFERE o ODATE; divergiu, RECUSA** *(evita: reintroduzir
o `Carga_Vida` por dentro do mecanismo criado para matá-lo — corrida de terça
travada, quarta 01:00 o cron parte, adere à corrida de terça e carimba **terça**
em toda a carga de quarta, e para o motor está tudo coerente porque é uma corrida
só)*. Divergiu → `PULADO` com motivo nominal
(`CORRIDA_ABERTA_DE_OUTRO_ODATE: corrida #12 de 2026-08-03 ainda aberta`) +
evento `DATA_DIVERGENTE`. É a mesma política da Decisão 24. Hoje o caminho
automático **já recusa** nesse caso (`dags/etl_dag_factory.py:1932`:
`return False, f'malha {_malha} nao esta limpa — {_res}'`); trocar recusa
explícita por adesão silenciosa seria uma regressão.

**Decisão 16 — a porta implícita é restrita às RAÍZES** *(evita: numa malha sem
Início, um membro do meio da cadeia abrir a corrida com `aberta_em` **depois** de
metade dos membros já ter concluído — o recorte de tempo não veria essas linhas,
elas virariam "pendentes" e a corrida iria a **`FALHA`** numa malha que rodou
perfeitamente: o card vermelho mentiroso, mesma família do defeito (a))*. Raiz =
membro sem predecessor **dentro** da malha, computável por
`etl_pipeline_dependencia ∩ etl_malha_pipeline`, sem tocar `malha_nos`. Membro
não-raiz que registra `EXECUTANDO` sem corrida aberta **não abre**: adere se
houver, e fica `NULL` se não houver.

**Decisão 17 — malha COM nó Início não abre por porta 3** *(evita: o membro com
cron próprio "sequestrar" o ciclo e o Início virar decoração)*. Nesse caso a
linha nasce com `malha_execucao_id NULL`, o painel diz nominalmente **"rodou
FORA da corrida"** e a própria linha carimba isso no `motivo`, na origem
*(porque de plantão se chega pelo pipeline, não pela malha — o diagnóstico tem de
viajar com a execução)*. É exatamente o alarme que faltou no `Carga_Vida`.

**Decisão 18 — o ODATE da abertura sai de UMA função canônica,
`malha_corrida.odate_da_abertura(conn, malha, momento)` =
`calcular(momento, COALESCE(etl_malha.hora_virada, config global))`, chamada
pelas três portas** *(evita: três fórmulas — a API usa a virada **global**, com a
divergência painel×disparo confessada em `api/routers/malhas.py:2377-2384`; o
`check_agenda` usa a virada do **pipeline**; a 081 introduziu a virada da
**malha**. Com `INSERT-first`, quem vence o índice carimbaria o ODATE de toda a
corrida, e disparar às 02:00 pela tela e pelo cron no mesmo minuto produziria
ciclos com dias diferentes conforme quem chega primeiro: não-determinismo puro)*.
A virada do **pipeline** nunca abre corrida de malha — continua valendo só para
pipeline fora de malha. Teste de paridade `dags/` × `api/` obrigatório.

**No ato da abertura** (uma transação): calcula o ODATE (Decisão 18), grava a
corrida com `aberta_em` recuado para `COALESCE(inicio, criado_em)` da linha
âncora (portas 2 e 3) ou `SYSDATETIME()` (porta 1), **congela o snapshot**
(`INSERT ... SELECT` de `etl_malha_pipeline`, com `conta_para_fim` de
`malha_nos.expandir()`, `ativo_na_abertura` de `etl_pipeline.active` e `eh_raiz`)
e calcula `teto_em` **em SQL**. Se a linha âncora tiver carimbado um ODATE
diferente do canônico — o caso que a virada única (081) existe para eliminar —
a corrida nasce com o canônico, registra no `motivo` e emite `DATA_DIVERGENTE`;
a linha entra classificada como `fora_do_odate` (§6.4). Divergência visível é o
oposto de divergência silenciosa.

### 6.3 Quem FECHA — **a guardiã, sempre**

**Decisão 19 — nenhuma DAG fecha corrida de malha** *(evita: a corrida que
precisa fechar justamente porque NADA está rodando — quiescência, teto, aborto —
nunca ser fechada)*. Precedente literal: `_resgatar_em_execucao`, *"a rede de
segurança tem de ser de fora"*.

`ciclo()` (`dags/etl_dependencia_guardia.py:832`) ganha **duas**
responsabilidades: `_abrir_corridas_malha` **antes** de `_observadores_malha` e
`_fechar_corridas_malha` **depois** dele e **antes** de `_notificar` — o card sai
no mesmo lote.

Um só predicado, dois consumidores (o padrão de `liberado()`: push, guardiã e
painel leem o mesmo): `malha_corrida.estado(conn, corrida)` devolve
`{vivos[], pendentes[], ok[], dispensados[], fora_do_fim[], fora_do_odate[]}`. O
observador emite o evento do nó; o fechador carimba o estado. **Nenhum dos dois
deriva do outro** — se o observador for pulado (malha inativa, `notificar_teams`
desligado), o fechamento acontece do mesmo jeito.

**Decisão 20 — evento e fechamento na MESMA transação, commit único** *(evita: a
lição já paga e escrita em `dags/etl_dependencia_guardia.py:299` — "a antiga
ordem fechar→commit→evento perdia o card PARA SEMPRE se a falha caísse entre os
dois commits, porque a detecção consome a própria fonte e nada re-tenta o
evento". A corrida tem exatamente essa forma: a detecção é `fechada_em IS NULL`,
e é ela que o fechamento consome)*. O `UPDATE` é condicional
(`WHERE id = ? AND fechada_em IS NULL`) com `rowcount` de árbitro, idêntico a
`fechar_nao_liberou`.

### 6.4 A classificação de cada membro do snapshot (`ativo_na_abertura = 1`)

| Situação da linha do membro no escopo da corrida | Classe |
|---|---|
| `SUCESSO` vivo (`substituida_em IS NULL`) | **OK** |
| `PULADO` | **dispensado** — terminal legítimo, é o que já vale hoje |
| sem linha **e** `dia_permitido(regras_dia, dia_operacional) == False` | **dispensado** — reusa o julgamento de `_predecessor_esperado` (`dags/etl_dependencia_guardia.py:326`), não duplica |
| `FALHA` | **pendente**, classe `falhou` |
| `NAO_LIBEROU` | **pendente**, classe `nao_liberou` |
| sem linha, com dia permitido | **pendente**, classe `nao_partiu` |
| `EXECUTANDO` **com evento `EXECUCAO_ORFA` aberto** | **pendente**, classe `orfa` — ver Decisão 22 |
| `EXECUTANDO` / `AGUARDANDO_DEPENDENCIA` | **vivo** → a corrida segue `ABERTA` |
| linha com `malha_execucao_id = @corrida` mas `data_referencia <> @odate` | **fora_do_odate** — aparece nominalmente e **nunca** conta como OK |

**Decisão 21 — `pendentes[]` carrega a CLASSE, não só o nome** *(evita: o painel
dizer "pendentes: CARGA_A, CARGA_B, CARGA_C" e obrigar o plantonista a abrir as
três telas para descobrir que são três problemas com três donos: rodar o job de
novo, soltar/investigar a dependência, descobrir por que a DAG nunca partiu)*. O
painel já sabe fazer isso por membro — é o `faltantes` da F5/D32
(`api/routers/malhas.py:2232`). Formato:
`{pipeline, classe, desde, faltante}`.

**Decisão 22 — linha `EXECUTANDO` com órfã já alertada sai de "vivo" e vira
"pendente"** *(evita: o caso órfão mais comum do sistema — DagRun terminou
`success` e a linha ficou `EXECUTANDO`, em que a guardiã corretamente se recusa a
inventar verde e só alerta (`dags/etl_dependencia_guardia.py:430`) — virar N
horas de **malha bloqueada** em vez de um alerta. A corrida fecha como `FALHA`
nomeando a linha órfã, que é a verdade, em vez de esperar 24h para dizer
`EXPIRADA`)*. E a Finalização Manual, ao fechar a linha, **reavalia a corrida no
mesmo gesto**.

**O escopo de "linha do membro nesta corrida"** — o SQL que resolve, de uma vez,
o membro compartilhado (Decisão 2), a transição entre fases (Decisão 23) e o
reprocesso de outro dia (§6.9/#15):

```sql
e.data_referencia = @odate
AND (   e.malha_execucao_id = @corrida
     OR COALESCE(e.inicio, e.criado_em) >= @aberta_em)
AND e.substituida_em IS NULL
```

**Decisão 23 — o predicado aceita a linha por proveniência OU por recorte de
tempo, e exige o ODATE nos DOIS ramos** *(evita: (i) subir o fechamento antes do
carimbo e nenhuma corrida fechar nunca — toda malha congelaria; (ii) ignorar
permanentemente o membro que rodou por fora com o ODATE certo; (iii) o cenário
real de plantão em que às 3h o operador reprocessa `CARGA_B` **para o dia 03**
enquanto a corrida do dia 04 está aberta: sem a exigência do ODATE no ramo do
vínculo, esse SUCESSO contaria como OK para o dia 04, e se fosse o último
pendente a corrida fecharia **CONCLUIDA sobre trabalho que não foi feito**)*. O
recorte por `>= aberta_em` é o que impede duas corridas do mesmo ODATE de se
confundirem.

### 6.5 Os desfechos

| Condição | Desfecho | Evento |
|---|---|---|
| `modo_fechamento='fim'`: nenhum **vivo**, nenhum **pendente** entre os `conta_para_fim=1`, **nenhum membro do snapshot vivo**, e **≥1 OK** | `CONCLUIDA` | `MALHA_CONCLUIDA` |
| `modo_fechamento='quiescencia'`: nenhum **vivo**, nenhum **pendente**, **≥1 OK** | `CONCLUIDA` | `MALHA_CONCLUIDA` |
| nenhum vivo, **≥1 pendente** | **`FALHA`** | `MALHA_FALHOU` (já emitido na detecção, Decisão 12) |
| nenhum vivo e **zero OK** porque **todos** são dispensados | **`SEM_TRABALHO`**, imediato | `MALHA_SEM_TRABALHO` (informativo, **fora** do lote de notificação) |
| `teto_em < SYSDATETIME()` **e ≥1 vivo** | **continua `ABERTA`**, saúde `ATRASADA` | `MALHA_ATRASADA` |
| `teto_em < SYSDATETIME()` **e nenhum vivo** | `EXPIRADA` | `MALHA_EXPIRADA` |
| **zero linhas** vinculadas, nenhum vivo, **e** `aberta_em < agora − carência_partida` | `ABORTADA` | `MALHA_ABORTADA` |
| operador encerrou / malha excluída | `CANCELADA` | `MALHA_CANCELADA` |

**Decisão 24 — `EXPIRADA`, `ABORTADA`, `FALHA`, `SEM_TRABALHO` e `CANCELADA`
JAMAIS emitem `MALHA_CONCLUIDA`** *(evita: a família inteira do campo agregado
que mente)*. É o espelho literal de *"a guardiã não inventa verde"*, e o teste é
de **ausência**, não de presença.

**Decisão 25 — o teto NUNCA fecha corrida com membro vivo** *(evita: fechamento
mensal com 26h de carga legítima e teto padrão de 24h — às 24h a corrida sairia
`EXPIRADA`, `fechada_em` desbloquearia o disparo, e o cron da madrugada seguinte
partiria a corrida #13 **por cima de 8 pipelines ainda `EXECUTANDO`**, que é
exatamente o que a F1/081 existe para impedir, agora com carimbo de aprovação do
modelo. Pior: as linhas que terminassem depois carregariam id de corrida fechada,
e o card ficaria `EXPIRADA` para sempre com 7/7 verdes embaixo — mentira estável
que nenhum refresh corrige)*. Teto com vivo é **alarme** (`MALHA_ATRASADA`), não
desfecho; o disparo segue bloqueado.

**Decisão 26 — "tudo dispensado" é desfecho terminal IMEDIATO (`SEM_TRABALHO`),
não espera de teto** *(evita: o sábado de uma malha `somente_dias_uteis` bloquear
a malha o dia inteiro — hoje `PULADO` é terminal e não segura nada
(`api/routers/malhas.py:2576`) — recusar todo disparo manual do sábado, e mandar
um `MALHA_ORFA` no domingo por um sábado que funcionou como projetado. Na
primeira semana o operador aprende a ignorar esse alarme, e aí ele deixa de
servir para o caso real. E com `teto_horas = 48` a corrida de sábado ainda
estaria aberta na segunda 01:00 → o `check_agenda` da segunda seria `PULADO` →
**dia útil perdido em silêncio**)*.

**Decisão 27 — `MALHA_ORFA` é dividido em `MALHA_SEM_TRABALHO` e
`MALHA_EXPIRADA`** *(evita: um evento só para dois fatos opostos, com card
idêntico e ação oposta)*.

**Decisão 28 — `ABORTADA` tem piso absoluto por `aberta_em`** *(evita: o disparo
manual fecha o banco **antes** de chamar o Airflow (`api/routers/malhas.py:2477`)
e commita a corrida; entre o commit e o primeiro `EXECUTANDO` há latência de
scheduler, pool saturado, DAG pausada, `nao_iniciar_antes`. Se a guardiã passar
nessa janela, `ABORTADA` — e as raízes registrariam `EXECUTANDO` apontando para
uma corrida abortada, o card voltaria a mentir e o próximo disparo seria liberado
**por cima da malha rodando**. A carência de quiescência não cobre isso: ela é
ancorada no último `atualizado_em` de **algum membro**, e aqui não há membro)*.

**Três guardas antes de declarar quiescência:**

1. **Nenhuma linha `AGUARDANDO_DEPENDENCIA` que `liberado()` aprove** — senão a
   `_rede_seguranca` (`dags/etl_dependencia_guardia.py:524`) ainda vai disparar e
   a corrida teria fechado no meio de si mesma.
2. **Carência** `malha_quiescencia_minutos` (default 15 = 3 ciclos) desde
   `GREATEST(aberta_em, MAX(fim/atualizado_em dos membros desta corrida))` — e
   **nunca só o `atualizado_em`**, que `malha_ciclo.equalizar` e
   `rerun.marcar_substituidas` bumpam por **gesto administrativo**, resetando o
   relógio de quiescência sem que nada tenha rodado. A janela é real:
   `_registrar_sucesso` commita o SUCESSO e **só então** chama
   `_disparar_dependentes` (`dags/etl_dag_factory.py:1693`) — segundos no caminho
   feliz, minutos quando o push falha e a rede assume.
3. **Nenhum nó da malha retido** (§6.7).

### 6.6 O teto é obrigatório, e é avaliado NA PORTA

`teto_em = DATEADD(HOUR, COALESCE(etl_malha.teto_horas, <config>), aberta_em)`,
em SQL (Decisão 10).

Justificativa: corrida `ABERTA` **bloqueia o disparo**. Uma corrida sem teto
seria estritamente pior que o estado de hoje — congelaria a malha para sempre,
sem tela para destravar. É a classe do `factory_log` órfão em `RUNNING`, elevada
da geração para o ciclo.

**Decisão 29 — expiração PREGUIÇOSA na porta: antes de recusar por "corrida
aberta", a abertura avalia o teto e expira ali mesmo, na mesma transação
(`UPDATE ... WHERE id=? AND fechada_em IS NULL AND teto_em < SYSDATETIME()`, com
rowcount de árbitro), e prossegue** *(evita: `teto_horas = 24` numa malha diária
fazer a corrida de 01:00 expirar às 01:00 do dia seguinte, com a guardiã rodando
a cada 5 min — se a raiz roda às 01:00:00 e a guardiã só expira às 01:03, a malha
**pula o dia inteiro**, e no dia seguinte a mesma moeda é jogada de novo)*.
Nunca depender de outro processo ter passado.

### 6.7 HOLD suspende os relógios — e isso corrige um defeito que já existe

**Decisão 30 — enquanto houver nó da malha retido (`MIN(etl_malha_no.retido_em)`,
lido na avaliação), o teto não corre, a quiescência não avalia e
`_fechar_dia_anterior` pula os membros da corrida** *(evita: um defeito que já
existe HOJE e que o teto pioraria — um Aguarde segurado faz `liberado()` devolver
`False` para o dependente, o que é literalmente "nenhum vivo, nenhum liberado", e
a quiescência fecharia a corrida como **`FALHA` por causa da trava que o próprio
operador pôs**; e `_fechar_dia_anterior` (`dags/etl_dependencia_guardia.py:259`)
já mata hoje a linha do dependente como `NAO_LIBEROU` depois de 24h de hold, sem
que ninguém tenha soltado nada)*.

A guarda é barata e já está pronta: o predicado **devolve o id do Aguarde retido
na 2ª coluna** (`_faltante`, `dags/utils/dependencias.py:760`) —
`_fechar_dia_anterior` pula quando o faltante é retenção, exatamente como já pula
quando começa com `ERRO_CONSULTA`.

Ao soltar o **último** nó retido: `teto_creditado_min += DATEDIFF(MINUTE,
retido_desde, SYSDATETIME())` e `teto_em` é reprojetado a partir de `aberta_em` +
crédito. Nunca se guarda "está retido".

**Decisão 31 — `_fechar_dia_anterior` pula QUALQUER linha cujo
`malha_execucao_id` aponte para corrida `ABERTA`, não só as retidas** *(evita: o
mesmo defeito no caso geral — a função corta por `criado_em < virada_anterior`,
régua derivada da **virada**; uma malha com teto de 48h, ou uma corrida que
atravessa a virada seguinte (cadeia noturna longa + rerun), teria seus
`AGUARDANDO_DEPENDENCIA` fechados como `NAO_LIBEROU` **enquanto a corrida ainda é
válida** — e esses membros virariam "pendentes", levando a corrida a `FALHA` por
ação da própria guardiã)*. A corrida passa a ser a autoridade sobre "este ciclo
ainda não acabou", e isso tem de valer nesta função também.

Hold do **Início** não para corrida aberta (está certo: ele segura a *partida*) —
mas a tela passa a dizer *"Início segurado: a próxima corrida não parte; a corrida
#N em andamento segue"*, que hoje o botão não explica.

### 6.8 A porta de saída do operador

**Decisão 32 — existe `POST /malhas/{m}/corridas/{id}/encerrar`, com motivo
obrigatório e `PERM_EXECUTAR`, gravando `CANCELADA` + `fechada_por`** *(evita: a
única saída para uma corrida travada às 3h ser **esperar 24h do teto** ou
**apagar a malha** — hoje o operador tem mais saída que isso, porque mexe nas
linhas de execução e o `_fechar_dia_anterior` fecha em um dia operacional. Teto
de 24h não é ferramenta de plantão, é espera)*. O botão vive no banner do painel,
e a mensagem de recusa do disparo (422) aponta para ele.

### 6.9 As bordas, uma a uma

| # | Borda | Resposta desta spec |
|---|---|---|
| 1 | Malha **sem** nó Fim (3 de 4 no dev) | `modo_fechamento='quiescencia'`, derivado do desenho na abertura, nunca configurado à mão. `_avisos_desenho` ganha aviso **leve**: "esta malha fecha por quiescência" — leve, não forte, porque é o desenho legítimo da maioria |
| 2 | Fim com entradas que não alcançam todos os membros | Fecha por `conta_para_fim=1`, **mas não fecha com nenhum membro do snapshot vivo**, e o painel lista nominalmente os `fora_do_fim`. Sem a segunda cláusula é o defeito (a) com outra roupa |
| 3 | **Rerun com cascata** | Reabre a **mesma** corrida (`tentativas += 1`) **somente se não houver outra corrida aberta da malha** — senão o `UPDATE` que zera `fechada_em` violaria `ux_malha_exec_aberta` (2601) dentro da transação que carimba `substituida_em` (`api/services/rerun.py:368`), e ou o rerun inteiro rola de volta, ou a corrida não reabre e ninguém percebe. Havendo outra aberta: **não reabre**, a linha preserva o `malha_execucao_id` original (Decisão 9) e grava-se `MALHA_REPROCESSO` na corrida antiga |
| 4 | Disparo manual da malha | Abre na transação dos bloqueios; **`dry_run` NÃO abre**; se **todas** as raízes falharem no trigger (o banco já fechou, `api/routers/malhas.py:2484`), a corrida é `ABORTADA` **numa segunda conexão, na mesma resposta** — senão o primeiro Airflow fora do ar congela a malha |
| 5 | Disparo avulso de UM pipeline (`api/routers/airflow.py:100`) | **Nunca abre, nunca reabre.** Se há corrida aberta **com o mesmo ODATE**, vincula-se a ela (senão card e camada de FLUXO mentem por omissão) e a tela avisa antes: *"este pipeline é membro da malha X, corrida #N aberta — esta execução será contada nela"*. Com ODATE informado **diferente** do da corrida: **não vincula**, e a tela diz que a execução ficará fora do ciclo |
| 6 | Membro de N malhas | Snapshot em N corridas (a tabela é N:N); a **coluna** aponta para a corrida que carimbou o ODATE; a **prova de conclusão** é lida por qualquer uma (Decisão 2). Duas corridas abertas com ODATEs divergentes para o mesmo pipeline → recusa (Decisões 15 e 34) |
| 7 | Duas corridas no mesmo dia | Identidade é **id**, nunca `(malha, data)`. `sequencia` é rótulo humano, derivado sob `UPDLOCK` (Decisão 6) |
| 8 | Malha inativa | **Não abre** corrida nova; corrida já aberta **segue até fechar** (órfã eterna é o pior resultado). Bônus: o *"ruído único ACEITO"* de hoje (reativar emite card retroativo pela janela `{D-1, D}`) **desaparece sozinho** — não há corrida aberta para observar |
| 9 | Membro inativo | `ativo_na_abertura = 0` sai do denominador; o painel diz *"N membro(s) inativo(s), fora desta corrida"* — nunca some em silêncio |
| 10 | Meia-noite | `aberta_em` é exato e imune à fronteira do dia por construção |
| 11 | Órfã | Quiescência (normal) + teto (rede, sem matar vivo) + `ABORTADA` com piso |
| 12 | HOLD | §6.7 |
| 13 | **Malha renomeada com corrida aberta** | `PATCH /malhas/{m}` com `novo_nome` (`api/routers/malhas.py:3130-3181`) faz `INSERT` do novo + `DELETE` do antigo. Sem tratamento, a corrida aberta ficaria **órfã sob o nome antigo**, ocupando o slot de `ux_malha_exec_aberta` para sempre, e o nome novo nasceria sem corrida → **dupla abertura por construção**. O rename passa a carimbar: `UPDATE etl_malha_execucao SET malha_name = ? WHERE malha_name = ? AND fechada_em IS NULL`, na mesma transação. ⚠️ **Achado colateral, pré-existente, a reportar ao dono:** `FK_malha_no_malha ... ON DELETE CASCADE` (`sql/migrations/075_malha_nos.sql:56-57`) e o rename **não** atualiza `etl_malha_no`/`etl_malha_aresta` — renomear uma malha hoje **apaga Início, Fim, Aguarde e Notificação** pelo cascade. Anterior a esta spec; é a prova de que `malha_name` não é identidade |
| 14 | Malha excluída com corrida aberta | `DELETE` **cancela** a corrida na mesma transação — senão a corrida órfã presa no índice filtrado impediria recriar uma malha com o mesmo nome |
| 15 | Reprocesso de outro ODATE durante a corrida | `fora_do_odate` (Decisão 23): aparece nominalmente, nunca conta como OK |
| 16 | Desenho editado com corrida aberta | O **snapshot congela** membros, `conta_para_fim` e `modo_fechamento` na abertura. Edição vale **da próxima corrida em diante**, e a tela diz isso. Mesmo princípio do corte anti-retroativo do observador, aplicado ao ciclo inteiro |
| 17 | Republicar com corrida aberta | Aviso no `dry_run` do `POST /republicar` — hoje ele não tem como saber que há ciclo em voo, e metade dos membros ficaria com código novo no meio do ciclo |

---

## 7. Quem carimba o ODATE

Precedência nova de `_data_referencia(context)` no fonte gerado
(`dags/etl_dag_factory.py:1553-1594`) — **a mudança que resolve a causa raiz
(c)**:

| # | Fonte | Quem cai aqui |
|---|---|---|
| 1 | `conf['malha_execucao_id']` → `SELECT data_referencia FROM etl_malha_execucao WHERE id = %s AND fechada_em IS NULL` **e** a corrida é de uma malha deste pipeline | a fonte única: cascata por push dentro da corrida |
| 2 | `conf['data_referencia']` | herança de hoje: push fora de malha, rerun, disparo manual com data |
| 3 | **corrida ABERTA de alguma malha deste pipeline** (`malha_corrida.corrida_aberta_do_pipeline`) | ⚠️ **o membro com cron próprio, DAG não republicada — é o `Carga_Vida` invertido**: em vez de calcular a própria data, ele **adere** ao ODATE do ciclo em voo |
| 4 | cálculo pela virada (o de hoje, byte a byte) | pipeline fora de malha, ou malha sem corrida aberta |

**Decisão 33 — o degrau 3 conserta o caso do incidente SEM exigir republicação do
dependente** *(evita: a proteção existir só para quem já foi republicado — que é
exatamente por que a F1–F5 da 081 não fecharam o caso)*.

**Decisão 34 — dois ODATEs abertos para o mesmo pipeline = RECUSA, nunca
escolha** *(evita: reintroduzir a doença com rótulo novo)*. `PULADO` com motivo
`MALHA_ODATE_AMBIGUO` + evento. Precedente: `malhas_do_pipeline`, *"barreira vale
no mais restritivo"*.

**Decisão 35 — a recusa por ODATE ambíguo vale também na porta do PUSH, e o
caminho `ganho is None` grava evento quando o filho é membro de corrida aberta
diferente da do pai** *(evita: a checagem morar na porta errada — o bloco de
malha do `check_agenda` roda **só** `if _origem == 'agenda'`
(`dags/etl_dag_factory.py:1893`, com o comentário explícito "quem vem por evento
já passou pelas travas do push"), e o pipeline compartilhado por duas malhas é,
quase por definição, um **dependente**: chega por `_disparar_dependentes` →
`reservar_corrida` → trigger. A recusa nunca dispararia. E o que acontece hoje é
pior: a malha A empurra e ganha o claim, a malha B empurra, recebe
`ganho is None`, imprime *"já tem corrida — sem novo disparo"* e segue — **silêncio
total**, nenhuma marca de que a corrida B ficou sem o membro)*. É a regra da
casa: cláusula nova entra nas três portas ou em nenhuma.

**Decisão 36 — `_data_referencia` é função PURA do run, memoizada por `run_id`**
*(evita: um defeito **fabricado pela cura**. A função é chamada 4 vezes por run
(`dags/etl_dag_factory.py:1619`, `:1739`, `:1918`, mais o registro de
sucesso/falha); hoje todos os degraus são estáveis, mas o degrau 3 lê estado
**mutável**. Cenário: pipeline longo, sem conf; 01:10 o `check_agenda` resolve
degrau 3 → ODATE `D`, grava a linha `(P, D, run_id)`; 04:50 a corrida fecha;
04:52 o `_registrar_sucesso` chama de novo → degrau 3 não acha nada → degrau 4
calcula `D-1` → o `UPDATE ... WHERE pipeline_name=%s AND data_referencia=%s AND
execution_id=%s` **erra a chave**, `rowcount == 0`, e o INSERT cria uma **segunda
linha** `(P, D-1, run_id)` com status SUCESSO. O run passa a existir em dois
ODATEs: a doença desta spec, produzida por ela)*. A memoização também elimina as
3 idas extras ao banco por run — o degrau 3 custa 1–2 consultas e
`_disparar_dependentes` as multiplicaria por dependente. **É entregável da fase,
não detalhe de implementação.**

**Decisão 37 — `conf['malha_execucao_id']` é OTIMIZAÇÃO de herança, não
identidade, e é VALIDADA** *(evita: amarrar a identidade a uma string frágil —
`POST /airflow/dags/{dag_id}/dagRuns` (`api/routers/airflow.py:100`) repassa o
`conf` **cru**, então qualquer conf com id arbitrário seria obedecido)*. Conf que
aponta corrida já fechada, ou de malha que não contém este pipeline, é tratado
como **ausente** (cai para o degrau 3/4) com log.

**O que acontece com as travas existentes:**

| Peça | Destino |
|---|---|
| `datas_divergentes` / F4 no push (`dags/etl_dag_factory.py:1761-1777`) | **FICA**, com curto-circuito: se o pai carrega `malha_execucao_id`, a checagem é redundante dentro da corrida e é pulada. Continua sendo a única proteção de cadeias **entre** malhas e fora de malha — não se remove código que ainda protege alguém |
| `equalizar_data` / `malha_ciclo.equalizar` (F3, 081) | **legado documentado**: conserto de um sintoma que a corrida elimina na origem. Não é removida — a 081 já foi aplicada em ambiente |
| `etl_malha.hora_virada` (F2, 081) | **continua necessária** — é o insumo que decide **qual** ODATE a corrida nasce carimbando. O que morre é ela ser lida por cada membro; passa a ser lida **uma vez, na abertura** |
| `_inicio_do_ciclo` (`api/routers/malhas.py:2619`), `malha_ciclo.inicio_do_ciclo` | **saem do caminho corrente** — o começo do ciclo é `aberta_em`, exato. Ficam como fallback sem a 085 |
| `_datas_divergentes` (`api/routers/malhas.py:2598`) | deixa de ser classe de problema **dentro** da corrida; vira o diagnóstico *"membro rodou fora da corrida"* (`malha_execucao_id IS NULL`) |

---

## 8. A janela do modo SEQUÊNCIA vira a corrida

**Decisão 38 — o corte deixa de ser um parâmetro global e passa a ser resolvido
POR LINHA de dependência** *(evita: um corte só para dependências de naturezas
diferentes — dependência de malha tem corrida, dependência avulsa não tem)*.
Ordem de resolução:

1. **a corrida da própria linha do dependente** (`malha_execucao_id`), passada
   como parâmetro;
2. **a corrida aberta da malha que ASSINOU a dependência** — a dependência já é
   assinada pelo nó (`etl_pipeline_dependencia.origem_no`, migration 075), então
   a malha é **determinada** e a ambiguidade do membro compartilhado não aparece
   aqui;
3. **a janela em horas** (084) — o fallback de quem não tem corrida.

**Decisão 39 — a assinatura vira
`liberado(conn, pipeline, data_ref, corrida=None)`, e a mudança entra nas TRÊS
portas (push, guardiã, `api/services/dependencias.py`) + paridade, no mesmo
commit** *(evita: o corte ser "a corrida aberta no instante da avaliação" em vez
de "a corrida da linha avaliada" — se a corrida fechar entre duas avaliações, uma
subconsulta correlacionada cairia no fallback de 12h **em silêncio** e o corte
mudaria de significado no meio do ciclo)*. A subconsulta por `origem_no` é o 2º
degrau, com `ORDER BY` explícito no `TOP 1` (regra da casa D15).

```sql
-- SQL_LIBERADO_SEQ_085 (trecho): o corte, em tres degraus
AND NOT EXISTS (
  SELECT 1 FROM dbo.etl_pipeline_execucao e
  WHERE e.pipeline_name = dd.depende_de
    AND e.status = 'SUCESSO' AND e.substituida_em IS NULL
    AND ISNULL(e.fim, e.inicio) >= COALESCE(
          (SELECT me.aberta_em FROM dbo.etl_malha_execucao me
            WHERE me.id = %s),                       -- 1) corrida da LINHA
          (SELECT TOP 1 me2.aberta_em
             FROM dbo.etl_malha_no n3
             JOIN dbo.etl_malha_execucao me2
               ON me2.malha_name = n3.malha_name AND me2.fechada_em IS NULL
            WHERE n3.id = dd.origem_no
            ORDER BY me2.aberta_em DESC, me2.id DESC),-- 2) corrida da MALHA
          %s))                                        -- 3) janela em horas
```

**A janela em horas continua existindo e NÃO é depreciada.** Dependência criada à
mão pelo `POST /dependencias` tem `origem_no IS NULL`; removê-la quebraria
**toda** dependência avulsa. `dependencia_janela_sequencia_horas` e
`inicio_do_ciclo_corrente` (`dags/utils/dependencias.py:722`) ficam, com o
docstring reescrito.

⚠️ **Cascata de degradação — obrigatória, e a razão está escrita em
`dags/utils/dependencias.py:63-65`:** `_MARCA_085 = "malha_execucao_id"` (e
`"etl_malha_execucao"`), com `_exec_liberado` virando
**SEQ_085 → SEQ_084 → 082 → 078 → legado**. Sem esse degrau, um deploy parcial
faz `liberado()` devolver **não-liberado para o banco inteiro** — a trava nova
pararia a produção em vez de segurar um Aguarde.

---

## 9. O card, o painel e os eventos

### 9.1 O card da lista — como "concluída" deixa de mentir

`_ultima_execucao_por_pipeline` (`api/routers/malhas.py:1541`) **sai do caminho
corrente** e vira fallback. Entram **duas** consultas, nenhuma por malha:

```sql
-- (1) a corrida corrente de cada malha: um SEEK por malha em ix_malha_exec_malha
SELECT m.malha_name, c.id, c.sequencia, c.status, c.data_referencia,
       c.aberta_em, c.fechada_em, c.origem, c.aberta_por, c.tentativas,
       c.modo_fechamento, c.teto_em
FROM dbo.etl_malha m
CROSS APPLY (SELECT TOP 1 me.* FROM dbo.etl_malha_execucao me
              WHERE me.malha_name = m.malha_name
              ORDER BY me.aberta_em DESC, me.id DESC) c;

-- (2) o denominador de TODAS elas de uma vez (GROUP BY unico sobre o indice
--     filtrado novo) — ok/total/falhas, derivados na leitura, com o instante
--     de apuracao vindo do MESMO relogio da consulta.
SELECT SYSDATETIME() AS apurado_em, ... GROUP BY mm.malha_execucao_id;
```

**O laço `melhor[malha] = max((momento, pipeline))` de
`api/routers/malhas.py:1819-1828` some — e com ele o defeito**, porque a chave de
comparação que hoje decide o status ("mais recente, desempate alfabético") deixa
de existir.

O "concluída" deixa de mentir por **quatro** mecanismos, não um:

1. o status é da **CORRIDA**, não do membro que começou por último;
2. **`FALHA` passa a ser desfecho possível** — hoje um membro em falha apenas
   impede o evento `MALHA_CONCLUIDA` de sair, e o card fica com o verde do
   vizinho;
3. existe o terceiro estado que hoje não existe: **`ABERTA`** — *"em andamento
   desde 01:10 · 4 de 7"*;
4. existe o eixo de **saúde** (Decisão 11): "em andamento" com falha já detectada
   é **vermelho**, não azul.

Payload:
`corrida: {id, sequencia, status, saude, data_referencia, aberta_em, fechada_em,
origem, aberta_por, tentativas, modo_fechamento, teto_em, membros_ok,
membros_total, falhas[], pendentes[], apurado_em}`.

**Decisão 40 — todo campo derivado exibido carrega o instante em que foi apurado,
ou é derivado na leitura** *(evita: a tela responder "isso era verdade há pouco"
quando o operador perguntou "isso é verdade agora?" — batendo F5 num número
congelado sem saber que está congelado)*. Aqui os derivados são calculados na
leitura e o payload traz `apurado_em` do relógio do banco; o front exibe
*"· atualizado agora"*.

**Decisão 41 — a degradação é POR MALHA (`corrida` ausente), nunca por flag de
migration** *(evita: o front novo contra a API velha — o `deploy.sh` publica o
`dist/` na etapa 3, **automático e sem pergunta**, e a API só é reconstruída na
etapa 7; nesse intervalo o front novo conversa com a API velha, que não manda
`corrida` **nem** `migration_085_pendente`. Sem flag, o front concluiria "está
tudo certo" e renderizaria `corrida` indefinida. E se o operador responder `n` na
6c, o intervalo é permanente)*. Regra: `if (!m.corrida)` → texto de hoje com o
sufixo **"(membro mais recente)"** e **jamais** a palavra "concluída". A flag
`migration_085_pendente` fica só como texto explicativo do tooltip.

### 9.2 A visão de execução

| Hoje | Com a corrida |
|---|---|
| lente = `?data_referencia=YYYY-MM-DD` (`api/routers/malhas.py:2146`) | lente = `?corrida={id}`; a data continua como **atalho** |
| sem data → `dref.calcular(_agora(), _virada_global(cur))`, virada **GLOBAL**, com a divergência painel×disparo confessada em `:2377-2384` | sem parâmetro → **a corrida ABERTA**; sem corrida aberta, a última fechada. **A divergência some**: painel e disparo leem o mesmo registro |
| `WHERE data_referencia = ?` sobre o banco inteiro, filtro de membro em Python (`:2205-2210`) | o predicado do §6.4 — recorte exato |
| `malha_concluida` varre `eventos_no` procurando `MALHA_CONCLUIDA` do nó Fim (`:2280-2286`) | lê `status`/`fechada_em` da corrida. **O evento vira rastro, não fonte de verdade** |
| navegação ◀ ▶ por **dia** (`MalhaEditor.tsx:1976-1993`) | navegação por **corrida**, alimentada por `GET /malhas/{m}/corridas?limite=N` (Decisão 42) |
| banner verde "Malha concluída em…" (`MalhaEditor.tsx:2214`) | ganha os pares honestos: *"ciclo #12 ABERTO desde 01:10 — 4 de 7 · 1 falha"*, *"ciclo #12 falhou: CARGA_A"*, e a linha de diagnóstico da Decisão 43 |
| `bloqueios.em_aberto` + `datas_divergentes`, duas listas (`:2849-2872`) | **uma linha**: *"a corrida #12, aberta em 04/08 às 01:10, ainda não passou pelo Fim"* — mantendo a **frase de ação** que a mensagem de hoje tem (*"…resolvido por Republicar pipelines"*, `MalhaEditor.tsx:2872`), agora apontando para o botão de encerrar |

**Decisão 42 — existe `GET /malhas/{m}/corridas?limite=N`** *(evita: navegar "por
corrida" no escuro, sem saber quantas corridas existiram na madrugada nem poder
pular para a #10; e o atalho por data resolver para "a de maior `sequencia`",
**escondendo as anteriores do mesmo dia** — exatamente o caso que a `sequencia`
existe para preservar)*.

**Decisão 43 — o banner expõe os campos de diagnóstico em uma linha** *(evita:
gravar seis campos e não mostrar nenhum — as três primeiras perguntas às 3h são
"quem começou isso?", "é a primeira tentativa ou já mexeram aqui?" e "por que
essa malha fecha sem passar pelo Fim?", todas respondíveis pelo banco e nenhuma
pela tela)*: *"corrida #12 · 2ª tentativa · aberta por **agendamento do Início**
(CARGA_RAIZ) às 01:10 · fecha por quiescência"*. `aberta_por` é traduzido na API
(`'inicio:#12'` é formato de máquina).

**Decisão 44 — corrida com `origem='implicita'` DIZ isso na tela** *(evita: nas
3 de 4 malhas sem Início, o ODATE ser "o que o primeiro membro achou" e a tela
apresentar isso como "o ODATE da corrida", com uma autoridade que ele não tem)*:
*"data de referência definida pela primeira raiz a partir (CARGA_C, 01:03) —
esta malha não tem nó Início"*, e o aviso leve do desenho diz isso também.

**Decisão 45 — a carência de quiescência é explicada na tela** *(evita: o último
pipeline ficar verde às 04:02, o card continuar "em andamento" até 04:17, e o
operador reportar bug ou — pior — disparar coisa na mão)*: *"aguardando 15 min de
estabilidade antes de fechar (até 04:17)"*.

**Decisão 46 — `statusExecucao.ts` ganha um mapa PARALELO `STATUS_CORRIDA`, não
reusa `STATUS_EXECUCAO`** *(evita: mentira de domínio — reusar faria `ABERTA`
herdar o estilo de `EXECUTANDO`, e `EXPIRADA`/`SEM_TRABALHO` caírem no
`default`)*. Tokens `canvas/panel/edge/ink` nos **dois** temas, pt-BR.
`MalhaComponenteNodes.tsx`: o nó Fim ganha o estado que hoje não tem — hoje é
verde (`concluidaEm`) ou apagado; passa a ter **"ciclo aberto"**.

### 9.3 Os eventos e o Teams

**Decisão 47 — os sete tipos novos entram em `ESTILO`
(`dags/utils/ds_teams.py:25-48`) e em `estiloEvento`
(`ui-react/src/components/malhas/statusExecucao.ts:142`) no MESMO PR que os
emite** *(evita: cair no `_PADRAO = {"rotulo": "Alerta", "icone": "🔔", "cor":
"Warning"}` — o que chegaria no celular às 3h seria um **card amarelo genérico
"🔔 Alerta" com subtítulo `#no:12`**, sem nomear a malha nem o pipeline que
quebrou, e com a cor "atenção" para o evento mais grave do produto; no painel, o
neutro cinza pelo mesmo motivo)*.

| Tipo | Ícone/cor | Notifica? |
|---|---|---|
| `MALHA_FALHOU`, `MALHA_EXPIRADA`, `MALHA_ABORTADA` | 🚨 Attention | **sempre** |
| `MALHA_ATRASADA` | ⏰ Warning | **sempre** |
| `MALHA_CANCELADA`, `MALHA_REPROCESSO` | ⚠️ Warning | sempre |
| `MALHA_CONCLUIDA` | ✅ Good | **opt-in** (`notificar_teams`, como hoje) |
| `MALHA_SEM_TRABALHO` | 💤 Good | **não vira card** |

**Decisão 48 — falha notifica SEMPRE; sucesso é que é opt-in** *(evita: o
`MALHA_FALHOU` herdar o opt-in de hoje e a malha falhar **em silêncio** para quem
nunca ligou a config — que é a maioria)*. O `detalhe` do evento **nomeia malha,
corrida (#N) e os pendentes com a classe** — é o corpo do card e é a única coisa
que se lê no celular.

**Decisão 49 — o evento da corrida é gravado com o marcador `#corrida:{id}`, e o
resolvedor do `GET /execucao` é estendido no MESMO PR** *(evita: em malha **sem
nó Fim** — 3 de 4 — o evento não ter onde morar: o painel só exibe evento cuja
chave resolve para um nó **desta** malha ou para um membro, e qualquer outra
chave é `continue` silencioso (`api/routers/malhas.py:2255-2270`). O evento mais
grave não apareceria exatamente na tela onde se olha às 3h)*.

**Decisão 50 — `malha_execucao_id` é PARÂMETRO EXPLÍCITO de `gravar_evento`
(`dags/utils/dependencias.py:1033`), default `None`, o `NOT EXISTS` inclui a
coluna, e a spec declara nominalmente que SÓ os tipos `MALHA_*` carregam corrida**
*(evita: dois defeitos gêmeos — (i) reconstruir o índice não muda o
`WHERE NOT EXISTS (pipeline_name, data_referencia, tipo)` que é feito **em
Python**, então o 2º `MALHA_CONCLUIDA` do rerun continuaria sumindo e o aceite da
fase falharia; (ii) se **alguns** escritores passarem a coluna e outros não, o
mesmo `(pipeline, data, tipo)` vira duas linhas — `NULL` e `12` — e o operador
recebe **dois cards para o mesmo fato**, quebrando a anti-duplicação de 200
ciclos/dia)*.

---

## 10. Fases

Cada fase é mergeável sozinha, com PR própria. **Revisão adversarial antes de
cada PR (regra da casa — o histórico desta spec é o argumento).** Merge só com
autorização do usuário.

### F1 — O modelo, e os módulos gêmeos que ninguém ainda usa
- **Entregável:** migration **085** completa (incluindo o kill switch
  `malha_corrida_ativa = 0`); `dags/utils/malha_corrida.py` (canônico, puro,
  `%s`) + `api/services/malha_corrida.py` (port `?`/pyodbc) com **teste de
  paridade** (matriz idêntica, precedente `tests/test_dependencias_f5_paridade.py`).
  Nenhum leitor, nenhum escritor no motor.
- **Deploy:** migration na 6c. **Não** exige `force_all`.
- **Aceite:**
  - o arquivo `.sql` roda **duas vezes seguidas, direto no banco** (não pelo
    `migrate.py`, que pula a 2ª pelo nome) sem erro, sem duplicar linha, coluna
    ou índice — os três `CREATE INDEX` da corrida com guarda por `sys.indexes` e
    **um `GO` por índice**, porque erro no primeiro aborta o batch e o índice
    seguinte nunca é criado, em silêncio;
  - dada uma corrida `ABERTA` da malha `M`, um `INSERT` **direto no banco** de
    uma segunda falha com violação de `ux_malha_exec_aberta` — **a invariante é
    do MODELO, não da API**;
  - dado `status='CONCLUIDA'` com `fechada_em NULL`, `CK_mexec_coerente` recusa;
  - `etl_dependencia_evento` com duas linhas de mesmo
    `(pipeline_name, data_referencia, tipo)` e `malha_execucao_id NULL` → a
    segunda é recusada (**o comportamento de hoje, byte a byte**); a mesma chave
    com corrida `10` é aceita;
  - em nenhum instante da migration a tabela de eventos fica **sem** índice único
    (o novo nasce antes de o velho sair);
  - as sete `SET options` exigidas por índice filtrado conferidas na conexão real
    do `dags/` — **são os primeiros índices filtrados de `etl_pipeline_execucao`
    no projeto**, e isso vira aceitação, não pressuposto;
  - paridade `dags/` × `api/` passa.
- **PR:** `feat: modelo da corrida de malha (migration 085)`

### F2 — A guardiã abre e fecha a corrida
- **Entregável:** responsabilidades novas em `ciclo()` —
  `_abrir_corridas_malha` (portas 2 e 3, com raiz, âncora, snapshot e ODATE
  canônico) e `_fechar_corridas_malha` (os sete desfechos, as três guardas, o
  predicado `estado`, evento e fechamento na mesma transação);
  `_observadores_malha` escopado pela corrida aberta (a janela `{D-1, D}` vira
  fallback); `gravar_evento` com `malha_execucao_id` explícito; os sete tipos em
  `ds_teams.ESTILO`; heartbeat `malha_corrida_guardia_visto_em`;
  `CAPACIDADES += ("malha_corrida_085",)`. Tudo atrás de `malha_corrida_ativa`.
- **Deploy:** `dags/` (etapa 5) — a guardiã é DAG própria, bind mount, recarrega
  sozinha; **não** exige `force_all` e **não** exige a etapa 8b.
- **Aceite:**
  - com o interruptor em `0`: **nada** abre, **nada** fecha, e o log da guardiã
    não muda de tamanho;
  - com `1`, raiz da malha parte por cron → **uma** linha `ABERTA` no ciclo
    seguinte, com o ODATE canônico da malha, `aberta_em` **recuado** para o
    início da linha âncora, e o snapshot congelado;
  - malha **com** Início: membro **não-raiz** que roda sozinho → **não** abre
    corrida, e a linha fica `malha_execucao_id NULL` com o `motivo` carimbado;
  - `CARGA_A` em `FALHA` e todos os outros em `SUCESSO` → corrida vai a
    **`FALHA`**, e **`MALHA_CONCLUIDA` NÃO é emitido** (teste de **ausência**);
  - `MALHA_FALHOU` sai no ciclo da **detecção** (01:12), não no fechamento
    (05:00), e **uma vez só** em 200 ciclos;
  - sábado com tudo `PULADO` → **`SEM_TRABALHO` imediato**, sem alarme, sem
    bloquear disparo — e **não** espera o teto;
  - membro em `EXECUTANDO` → corrida segue `ABERTA` mesmo com todos os outros
    verdes;
  - corrida com zero linhas recém-aberta → **não** vira `ABORTADA` antes da
    carência de partida;
  - malha **sem** nó Fim → o evento aparece no painel (marcador `#corrida:{id}`
    resolvido);
  - relógio do banco deslocado 3h do worker (o caso **medido** no dev) → o teto e
    a carência se comportam igual: nenhuma aritmética em Python;
  - sem a 085 (tabela renomeada com `sp_rename`) → a guardiã loga **uma vez por
    ciclo**, com prefixo `[GUARDIA]`, "085 ausente" e o ciclo inteiro segue.
- **PR:** `feat: a guardia abre e fecha a corrida de malha`

### F3 — O disparo manual abre; o operador encerra
- **Entregável:** `POST /malhas/{m}/disparo` abre na transação dos bloqueios
  (`dry_run` **não** abre), com expiração preguiçosa (Decisão 29) e **aborta em
  segunda conexão** se todas as raízes falharem; `POST
  /malhas/{m}/corridas/{id}/encerrar` (motivo obrigatório, `PERM_EXECUTAR`);
  `GET /malhas/{m}/corridas`; `DELETE /malhas/{m}` cancela a corrida aberta;
  `PATCH` com `novo_nome` **carimba** a corrida aberta (§6.9/#13); a API só abre
  se `capacidade_dags()` declarar `malha_corrida_085` **e** o heartbeat da
  guardiã for recente.
- **Deploy:** `api/` (etapa 7, automática). **Não** exige `force_all`.
- **Aceite:**
  - disparar pela tela → uma linha `ABERTA` com o ODATE do disparo e o snapshot
    congelado; `dry_run` → **nenhuma** linha;
  - Airflow derrubado, disparo de 2 raízes falha nas 2 → a resposta traz as
    falhas **e** a corrida sai `ABORTADA`; o próximo disparo **não** é bloqueado;
  - corrida presa com o teto vencido → o disparo **expira na porta e prossegue**,
    sem depender de a guardiã ter passado;
  - encerrar corrida #12 com motivo → `CANCELADA` + `fechada_por`; disparo volta
    a funcionar **na hora**;
  - renomear malha com corrida aberta → a corrida acompanha o nome novo; o nome
    antigo fica livre e **não** sobra corrida órfã no índice filtrado;
  - motor antigo (sem `malha_corrida_085` em `CAPACIDADES`) com a 085 aplicada →
    a API **não abre** corrida e o disparo responde **exatamente como hoje**;
  - o 422 do disparo mantém a **frase de ação** e nomeia a corrida.
- **PR:** `feat: disparo abre a corrida e o operador pode encerra-la`

### F4 — O card e o painel deixam de mentir
- **Entregável:** `_ultima_corrida_por_malha` + o `GROUP BY` único do
  denominador; payload `corrida` com saúde, `pendentes[]` classificado e
  `apurado_em`; `GET /malhas/{m}/execucao` com lente `?corrida=`; front
  (`Malha.tsx`, `MalhaEditor.tsx`, `statusExecucao.ts`,
  `MalhaComponenteNodes.tsx`, `fluxoExecucao.ts`, `types/index.ts`).
- **Deploy:** `api/` + front (`dist/` commitada). **Não** exige `force_all`.
- **Aceite:**
  - **o defeito relatado, reproduzido no dev**: `CARGA_A` FALHA às 03:00 e
    `CARGA_B` SUCESSO às 03:40 → o card diz **"falhou"** e nomeia `CARGA_A`;
    hoje diz "sucesso · CARGA_B";
  - corrida em voo sem falha → *"em andamento desde 01:10 · 4 de 7"*, azul;
  - corrida em voo **com** `CARGA_A` em falha e 38 membros correndo → o card é
    **vermelho** e nomeia a falha, sem esperar o fechamento;
  - `pendentes[]` distingue `falhou` / `nao_liberou` / `nao_partiu` / `orfa`;
  - duas corridas no mesmo ODATE → ◀ ▶ navega entre elas sem sobrepor, e
    `GET /corridas` lista as duas;
  - lista com 40 malhas → **duas** consultas no total (medido), nunca N+1;
  - **front novo contra API velha** (payload sem `corrida`) → card renderiza o
    texto de hoje com "(membro mais recente)", sem exceção no console —
    degradação **por ausência do campo**, não por flag;
  - **sem a 085** → card **e painel** degradam juntos: o banner verde some junto
    com o card verde, e a palavra "concluída" não aparece em nenhum dos dois;
  - tsc + eslint com **baseline HEAD** (zero NOVOS) e build com `dist/`.
- **PR:** `feat: card e painel da malha passam a ler a corrida`

### F5 — A corrida carimba o ODATE ⚠️ **`force_all`**
- **Entregável:** fonte gerado — `_data_referencia` com a precedência do §7,
  **memoizada por `run_id`**; `_registrar_execucao` grava
  `malha_execucao_id` write-once; `montar_conf`
  (`dags/utils/dependencias.py:133`) propaga a chave; o bloco de malha do
  `check_agenda` (`dags/etl_dag_factory.py:1893-1938`) troca 5 chamadas +
  heurística de janela por **uma** chamada a `malha_corrida`; a recusa por ODATE
  ambíguo entra também na porta do **push**, e `ganho is None` grava evento.
  Marca sintática `_corrida.odate(` emitida pela factory.
- **Deploy:** ⚠️ **`force_all` obrigatório, e é a ÚNICA fase que exige.** O gesto
  **não está no `deploy.sh`**: é um trigger de `etl_dag_factory` com
  `conf={"force_all": true}` — a instrução literal está em
  `dags/etl_admin_manage.py:202`. Prova por pipeline no §12.2.
- **Aceite:**
  - **o `Carga_Vida` invertido**: membro com cron próprio (DAG **não**
    republicada), malha com corrida aberta em D → ele carimba **D**, não a data
    que calcularia sozinho;
  - raiz parte por cron → todas as linhas da cascata trazem o mesmo
    `malha_execucao_id`;
  - **`_data_referencia` chamada 4× no mesmo run devolve o MESMO valor mesmo que
    a corrida feche no meio** — e a 2ª a 4ª chamadas **não** vão ao banco (o
    teste que prova que a cura não fabrica a doença);
  - rerun que reusa o `run_id` **preserva** o `malha_execucao_id` original;
  - conf com `malha_execucao_id` de corrida **fechada** ou de outra malha → é
    ignorado e o degrau 3/4 resolve, com log;
  - duas corridas abertas com ODATEs diferentes para o mesmo pipeline →
    `PULADO` com motivo `MALHA_ODATE_AMBIGUO` **na agenda e no push**, nunca
    escolha silenciosa;
  - **sem a 085**: `_data_referencia` produz a data de hoje **byte a byte** e
    `_registrar_execucao` grava sem a coluna (fallback por `_MARCA_085`) — a
    carga **nunca** cai;
  - a API **avisa** (não recusa) no disparo quando há membro cuja DAG publicada
    não tem a marca, usando a sonda de arquivo do §12.2 — e o terceiro valor
    `DESCONHECIDO` **não** é tratado como ausência.
- **PR:** `feat: a corrida da malha carimba a data de referencia`

### F6 — A janela do modo SEQUÊNCIA vira a corrida
- **Entregável:** `SQL_LIBERADO_SEQ_085` com os três degraus;
  `liberado(conn, pipeline, data_ref, corrida=None)` nas **três** portas;
  cascata SEQ_085 → SEQ_084 → 082 → 078 → legado; port em
  `api/services/dependencias.py` + paridade.
- **Deploy:** `dags/utils/` é importado em runtime — **não** exige `force_all`.
- **Aceite:**
  - dependência assinada por Aguarde de malha com corrida aberta às 01:10 e pai
    que concluiu às 22:00 do dia anterior (dentro das 12h da janela) → **NÃO
    libera** — o corte é `aberta_em`;
  - dependência com `origem_no IS NULL` → janela de 12h **inalterada**;
  - malha 23h→01h → o filho às 01:00 enxerga o pai das 23h30;
  - corrida fecha entre duas avaliações → o corte **não** muda de significado
    (a corrida vem da linha, não de subconsulta viva);
  - **sem a 085** (tabela ausente) → a cascata cai na SEQ_084 e `liberado()`
    **não** devolve `False` para o banco inteiro — o teste que prova a catástrofe
    evitada;
  - paridade `dags/` × `api/` do SQL capturado passa.
- **PR:** `feat: modo sequencia usa o inicio da corrida da malha`

### F7 — Os relógios: hold, teto e atraso
- **Entregável:** hold **derivado** de `MIN(etl_malha_no.retido_em)`;
  `teto_creditado_min` creditado ao soltar o **último** nó;
  `_fechar_dia_anterior` pula membros de **qualquer** corrida `ABERTA` (não só
  retida); `MALHA_ATRASADA` (teto com vivo) × `MALHA_EXPIRADA` (teto sem vivo);
  `etl_malha.teto_horas` na tela; textos das Decisões 43–45.
- **Deploy:** `api/` + `dags/` + front. **Não** exige `force_all`.
- **Aceite:**
  - Aguarde segurado por 30h → `_fechar_dia_anterior` **NÃO** fecha o dependente
    como `NAO_LIBEROU` (**é a correção de um defeito que já existe hoje**) e a
    quiescência **não** fecha a corrida como `FALHA`;
  - **dois** Aguardes segurados, solta-se **um** → os relógios **continuam
    parados** (o teste que o espelho materializado reprovaria);
  - nó segurado ontem, corrida abre hoje → nasce com os relógios parados;
  - soltar após 6h de hold numa malha com teto de 4h → `teto_em` empurrado 6h; a
    corrida **não** expirou;
  - teto vencido com 8 membros `EXECUTANDO` → corrida **continua `ABERTA`**,
    saúde `ATRASADA`, `MALHA_ATRASADA` emitido **uma vez**, e o disparo segue
    **bloqueado** (o teste que prova que o teto não mata trabalho vivo);
  - corrida parada além do teto sem vivo → `EXPIRADA` + `MALHA_EXPIRADA`, e
    **`MALHA_CONCLUIDA` não sai** (ausência);
  - hold do Início com corrida aberta → toast diz *"a próxima corrida não parte;
    a corrida #N segue"*.
- **PR:** `feat: teto, atraso e hold da corrida de malha`

### F8 — Rerun, desenho editado e os avisos que faltavam
- **Entregável:** rerun com cascata (`marcar_substituidas` com `rowcount > 0`)
  reabre a corrida na mesma transação **quando não há outra aberta**; senão
  grava `MALHA_REPROCESSO` e não reabre; `PATCH ativo=0` avisa e deixa a corrida
  fechar; `add_membro`/`remove_membro`/`POST /republicar` **avisam** ("vale da
  próxima corrida" / "há ciclo #N em voo") sem recusar; disparo avulso de um
  pipeline avisa que será contado na corrida; Finalização Manual reavalia a
  corrida ao fechar a linha órfã.
- **Deploy:** `api/` + front. **Não** exige `force_all`.
- **Aceite:**
  - malha `CONCLUIDA` sem outra aberta, rerun com cascata → corrida volta a
    `ABERTA` com `tentativas=2`; quando o rerun conclui, **a segunda
    `MALHA_CONCLUIDA` É GRAVADA** (hoje some em silêncio por `ux_dep_evento`);
  - malha `CONCLUIDA` do dia 03 **com** a corrida do dia 04 aberta, rerun de um
    membro do dia 03 → o rerun **conclui sem erro**, a corrida #12 **não**
    reabre, `MALHA_REPROCESSO` é gravado e a #13 não é afetada (o teste que
    prova que o desenho não passa por cima do próprio índice);
  - rerun de pipeline **sem** dependentes aposentados → **não** reabre nada;
  - `add_membro` com corrida aberta → entra no cadastro, **não** entra no
    snapshot, e a resposta diz isso;
  - `DELETE` da malha com corrida aberta → `CANCELADA`, e o nome pode ser
    recriado;
  - Finalização Manual fecha linha órfã → a corrida é reavaliada **no mesmo
    gesto**, sem esperar 5 min.
- **PR:** `feat: rerun reabre a corrida e o desenho editado vale do proximo ciclo`

---

## 11. Degradação, deploy parcial e o interruptor

### 11.1 A matriz que o `deploy.sh` produz de verdade

A etapa 3 (front) e a 7 (`api/`) são **automáticas, sem pergunta**; a 5 (`dags/`)
e a 6c (migrations) são **padrão-NÃO**. Logo há quatro combinações reais, e as
quatro precisam de resposta:

| `dags/` | 085 | O que acontece | Coberto por |
|---|---|---|---|
| novo | aplicada | caminho feliz (com o interruptor ainda em `0`) | — |
| novo | **não** | `liberado()` devolveria não-liberado para o **banco inteiro** e a produção pararia | cascata `_MARCA_085` (F6) + a guardiã logando "085 ausente" (F2) |
| **antigo** | **aplicada** | **a célula mais provável** — a API nova sobe sem pergunta e o `dags/` só com `s`. A API abriria corrida, o motor antigo não vincularia nem fecharia: **toda corrida ficaria órfã até o teto e, enquanto isso, bloquearia o disparo** — a API paralisando a malha com uma trava que o motor deployado não sabe destravar (o espelho exato do "078 sim / dags não") | a API pergunta a `capacidade_dags()` **e** ao heartbeat da guardiã antes de abrir (F3); e o interruptor |
| antigo | não | nada muda | — |

### 11.2 O interruptor

**Decisão 51 — `malha_corrida_ativa` nasce em `0` e o trem inteiro sobe
desligado** *(evita: (i) não haver gesto de rollback — todas as mudanças recentes
de comportamento do motor entraram atrás de uma chave em `etl_app_config`
(`dependencia_modo_sequencia`, `dependencia_janela_sequencia_horas`), e sem ela o
rollback da F2 seria "reverter o merge e refazer o ciclo de deploy", às 3h; (ii)
cada uma das oito fases mudar o comportamento de produção no dia em que é
mergeada, ao longo de várias janelas de deploy)*. Com `0`: nada abre, nada fecha,
`_fechar_corridas_malha` sai no primeiro `if`, o card usa o fallback e
`_data_referencia` fica no degrau de hoje. **Liga-se depois da F7**, porque o
teto é a rede obrigatória.

### 11.3 O que o operador precisa saber

- **Ordem real do deploy** (e não a que se costuma escrever): etapa 3 front
  (automática) → 4 `config/` → 5 `dags/` (padrão-NÃO, responder `s`) → **6c
  migration 085** (padrão-NÃO, responder `s`; **nunca `migrate.py --baseline`**)
  → 7 `api/` (automática) → 8b containers Airflow: **responder `n` em todas as
  oito fases** (`dags/` é bind mount e recarrega sozinho; a 8b interrompe jobs em
  execução).
- **Dimensionamento ANTES**, por causa do `ix_pipe_exec_malha`:
  `SELECT COUNT(*), MIN(criado_em), MAX(criado_em) FROM dbo.etl_pipeline_execucao`
  — acima de um limiar a ser fixado com o dono, a 085 sai da 6c e roda em janela
  própria. `ONLINE = ON` só existe em Enterprise; a edição do SQL Server da Caixa
  precisa ser declarada.
- **A 085 fecha na F1.** `migrate.py` registra por **nome** em
  `etl_schema_version` e o checksum nunca é revalidado: editar a 085 depois de
  aplicada é **no-op silencioso** em todo ambiente que já a rodou. Correção vira
  **086**. É **intencional** que a F1 entregue colunas que só a F7 usa
  (`teto_creditado_min`, `teto_em`, `teto_horas`).
- **`sql/deploy_full.sql` não recebe a 085** — está congelado num schema antigo
  (861 linhas, sem `etl_malha*` nem `etl_dependencia_evento`).
- Se as fases forem em janelas separadas e uma for pulada, o `deploy.sh` pede que
  o operador **reconheça os nomes** das migrations pendentes: o nome é
  `085_malha_corrida.sql` e a resposta é sempre `s`.
- **F7 sem F2** (hold sem corrida): o hold continua funcionando exatamente como
  hoje — o predicado é a autoridade, a corrida só suspende relógios que ainda não
  existem.
- **Janela normal entre o deploy e a primeira madrugada:** banco com a 085,
  interruptor ligado, nenhuma corrida ainda aberta → **toda** malha cai no
  fallback por ausência do campo (Decisão 41), com "(membro mais recente)". O
  operador não chega na manhã seguinte com 100% das malhas "sem informação".

---

## 12. As consultas que não mentem

### 12.1 Pré-requisito da 085 (roteiro de smoke, §0)

`sql/migrate.py` **descarta `PRINT`** (D40): a conferência é `SELECT`, com o
valor esperado em comentário por linha. E a prova é de **objeto**, nunca
`COUNT(*) FROM etl_schema_version` — `--baseline` deixaria a contagem igual.

```sql
SELECT OBJECT_ID('dbo.etl_malha_execucao','U')                      AS t_corrida,   -- NOT NULL
       OBJECT_ID('dbo.etl_malha_execucao_membro','U')               AS t_membro,    -- NOT NULL
       COL_LENGTH('dbo.etl_pipeline_execucao','malha_execucao_id')  AS vinculo,     -- NOT NULL
       COL_LENGTH('dbo.etl_dependencia_evento','malha_execucao_id') AS ev_corrida,  -- NOT NULL
       COL_LENGTH('dbo.etl_malha','teto_horas')                     AS teto,        -- NOT NULL
       (SELECT COUNT(*) FROM sys.indexes
         WHERE object_id = OBJECT_ID('dbo.etl_malha_execucao'))     AS idx_corrida, -- = 4
       (SELECT COUNT(*) FROM sys.index_columns ic
           JOIN sys.indexes i ON i.object_id = ic.object_id AND i.index_id = ic.index_id
           JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
          WHERE i.name = 'ux_dep_evento_corrida'
            AND c.name = 'malha_execucao_id')                       AS ev_na_chave, -- = 1
       (SELECT COUNT(*) FROM dbo.etl_app_config
         WHERE config_key IN ('malha_corrida_ativa','malha_teto_horas_padrao',
                              'malha_quiescencia_minutos',
                              'malha_carencia_partida_min'))        AS cfgs;        -- = 4
```

`ev_na_chave = 0` é **a linha traiçoeira**: as tabelas existem, a tela funciona,
tudo parece verde — e o 2º `MALHA_CONCLUIDA` do rerun (F8) some em silêncio,
que é exatamente o defeito que a F8 diz corrigir.

E o relógio, porque a Decisão 10 depende dele:
`SELECT GETDATE()` no banco **conferido contra** `docker exec orquestra-api date`
e o `date` do worker. **No dev medido hoje o desvio é de 3 horas** (worker/API em
`-03`, SQL Server em UTC) — isto é passo obrigatório do smoke, não conselho.

### 12.2 A prova do `force_all` da F5 — por pipeline, em duas colunas

**Não** se usa `grep -rl "malha_execucao_id" generated/ | wc -l` contra
`COUNT(*) FROM etl_pipeline WHERE active = 1`: (i) `generated/` guarda o fonte de
pipelines **inativos** também — o deploy nunca limpa a pasta — então o total do
grep é legitimamente **≥** o `COUNT`, a igualdade quebra sem nada estar errado, e
a partir daí a conferência não confere mais nada; (ii) a string casaria em
comentário e em código morto.

A prova é uma **marca sintática única emitida por concatenação pela factory** —
`_corrida.odate(` — sondada pipeline a pipeline pelo mesmo mecanismo de
`api/services/espera.py:214`, com os **três** valores (`OK`, `AUSENTE`,
`DESCONHECIDO`, porque *"não saber montar o caminho não é prova de nada"*), e o
resultado exibido em **duas colunas** — `pipeline_name` e sonda — para o operador
ver **quem** ficou para trás e republicar só aquele. `dag_config_pendente_em`
**não** serve aqui: ele responde "a configuração mudou desde a publicação", não
"o fonte publicado tem o carimbo".

---

## 13. Impacto por consumidor

| Arquivo | O que muda |
|---|---|
| `sql/migrations/085_malha_corrida.sql` | **novo** — todo o §5.3 |
| `dags/utils/malha_corrida.py` | **novo** — canônico e puro: `odate_da_abertura`, `abrir`, `estado`, `fechar`, `corrida_aberta_do_pipeline`, `expirar_na_porta` |
| `api/services/malha_corrida.py` | **novo** — port `?`/pyodbc, com teste de paridade |
| `dags/etl_dependencia_guardia.py` | responsabilidades `_abrir_corridas_malha` e `_fechar_corridas_malha` no `ciclo()` (`:832`); `_observadores_malha` escopado pela corrida; `_fechar_dia_anterior` (`:259`) pula membros de corrida `ABERTA` |
| `dags/utils/dependencias.py` | `SQL_LIBERADO_SEQ_085` e a cascata `_MARCA_085`; `liberado(..., corrida=None)`; `gravar_evento(..., malha_execucao_id=None)` (`:1033`); `montar_conf` (`:133`); `CAPACIDADES` (`:317`) na **F2** |
| **`dags/etl_dag_factory.py`** | ⚠️ **FONTE GERADO — só a F5**: `_data_referencia` (`:1553-1594`) com 4 degraus e memoização; `_registrar_execucao` (`:1595`) grava write-once; bloco de malha do `check_agenda` (`:1893-1938`) encolhe para uma chamada; recusa por ODATE ambíguo no push (`:1761-1777`) |
| `dags/utils/malha_ciclo.py` | encolhe: `inicio_do_ciclo`/`estado_do_ciclo` saem do caminho corrente e viram fallback sem a 085 |
| `dags/utils/ds_teams.py` | 7 tipos novos em `ESTILO` (`:25-48`) + a política "falha notifica sempre" |
| `api/routers/malhas.py` | lista (`:1541`, `:1813-1830` — **o laço do defeito some**); execução (`:2140-2290`, lente por corrida, resolvedor de `#corrida:`); disparo (`:2297`, abre + expira na porta); bloqueios (`:2576-2650`, uma linha em vez de duas listas); `PATCH` rename (`:3130-3181`, carimba a corrida); `DELETE` cancela; membros e `POST /republicar` avisam; endpoints novos `/corridas` e `/corridas/{id}/encerrar` |
| `api/services/dependencias.py` | port do predicado com corrida + paridade |
| `api/services/rerun.py` | reabertura condicionada (`marcar_substituidas`, `:368`); `MALHA_REPROCESSO`; write-once preservado |
| `api/routers/airflow.py` | disparo avulso vincula-se à corrida aberta de mesmo ODATE e avisa antes (`:100`) |
| `api/services/espera.py` | molde reusado para a `MARCA_CORRIDA` da sonda do fonte gerado (`:160`, `:214`) |
| `ui-react/src/pages/Malha.tsx` | card com status da corrida, saúde, `4 de 7`, `apurado_em` e o fallback "(membro mais recente)" |
| `ui-react/src/components/malhas/MalhaEditor.tsx` | banner de ciclo aberto/falhou/atrasado; linha de diagnóstico; seletor de corridas; textos das Decisões 43–45; 422 com frase de ação |
| `ui-react/src/components/malhas/statusExecucao.ts` | `STATUS_CORRIDA` **paralelo** a `STATUS_EXECUCAO` (`:66`); `estiloEvento` (`:142`) com os 7 tipos |
| `ui-react/src/components/malhas/MalhaComponenteNodes.tsx` | nó Fim ganha o estado "ciclo aberto" |
| `ui-react/src/components/malhas/fluxoExecucao.ts`, `types/index.ts` | camada de FLUXO e contrato do payload |
| **testes novos** | `tests/test_malha_corrida.py`, `test_malha_corrida_paridade.py`, `test_malhas_corrida_card.py`, `test_dependencia_guardia_corrida.py`, `test_malha_corrida_relogio.py` |
| **testes existentes a rever** | `test_malhas_data_unica.py`, `test_malha_ciclo.py`, `test_malhas_aguarde_retido.py`, `test_dependencias_f5_paridade.py`, `test_utils_dependencias.py`, `test_dependencia_guardia_dag.py`, `test_dag_factory_dependencias_f3.py`, `test_malhas_f14.py`, `test_malhas_f15.py`, `test_malhas_republicar.py`, `test_rerun_etapa_f4.py` |
| **não tocados, de propósito** | `dags/utils/malha_nos.py` e o port · `dags/utils/data_referencia.py` · compilador do Aguarde (`_diff_compilacao`, `_aplicar_compilacao`) · agendamento do Início (F13) e `proximaExecucao.ts` (é **gatilho**, não ciclo) · `AgendamentoInicioModal.tsx` · `componenteMeta.ts` · `MalhaPipelineNode.tsx` · regras de agenda do `check_agenda` (horários, dias do mês, blackout, calendário) · rede de segurança/deadline da guardiã · espelho CSV `depends_on` |

---

## 14. Riscos e mitigações

| # | Risco | Impacto | Mitigação (já é entrega de uma fase) |
|---|---|---|---|
| 1 | Deploy parcial: `dags/` novo, banco sem a 085 | `liberado()` devolve não-liberado para o **banco inteiro** — a produção para | Cascata `_MARCA_085` (F6), com o teste do degrau (forma do 078/082) |
| 2 | Deploy parcial inverso: 085 + API nova, `dags/` antigo | corridas abertas que nada fecha, bloqueando o disparo de toda malha | A API pergunta a `CAPACIDADES` **e** ao heartbeat antes de abrir (F3) + interruptor (F1) |
| 3 | Fechamento antes do carimbo do ODATE (F2 antes da F5) | nenhuma corrida fecharia e toda malha congelaria | O ramo por **recorte de tempo** do predicado (Decisão 23), entregue **na F2** |
| 4 | Corrida aberta que nunca fecha | congela a malha para sempre, sem tela para destravar (classe do `factory_log` órfão em RUNNING) | Teto **obrigatório** com expiração na porta (F3/F7) + quiescência (F2) + `ABORTADA` com piso (F2) + **porta de encerramento do operador** (F3). Invariante testada: **toda corrida aberta fecha** |
| 5 | Quiescência fecha no meio de si mesma | corrida vai a `FALHA` entre o SUCESSO do pai e o push do filho | As três guardas do §6.5, com a carência ancorada em `GREATEST(aberta_em, MAX(...))` |
| 6 | Teto mata trabalho vivo | segunda corrida parte por cima da primeira — o defeito que a F1/081 existe para impedir | Decisão 25: teto com vivo é `ATRASADA`, não desfecho (F7) |
| 7 | HOLD longo mata o dependente / estoura o teto | o operador segura de propósito e o motor destrói a corrida | Decisões 30 e 31 (F7) — e isso **corrige um defeito que já existe hoje** |
| 8 | Relógio do banco ≠ relógio do worker (**3h medidas no dev**) | teto de 24h vira 27h; a quiescência nunca é satisfeita; soltar um hold **expira** a corrida | Decisão 10: nenhuma aritmética de relógio em Python; invariante 9 do §16, com teste de relógio deslocado, e passo obrigatório do smoke |
| 9 | F5 sem `force_all` completo | metade das DAGs carimba, metade calcula sozinha — a doença com aparência de cura | Sonda por pipeline em duas colunas (§12.2) + aviso da API no disparo |
| 10 | Membro compartilhado por duas malhas | a corrida perdedora espera para sempre e vai a `FALHA` | Decisão 2 (a prova é da linha no intervalo) + Decisão 35 (a recusa vale no push) |
| 11 | `_data_referencia` lendo estado mutável | o run existe em **dois** ODATEs — a doença fabricada pela cura | Decisão 36: memoização por `run_id` como **entregável** da F5 |
| 12 | Rerun colidindo com `ux_malha_exec_aberta` | o rerun inteiro rola de volta, ou a corrida não reabre e ninguém percebe | §6.9/#3 + o aceite explícito da F8 |
| 13 | `malha_name` não é chave estável (rename) | corrida órfã ocupando o slot do nome antigo + dupla abertura | Carimbo do rename (F3) + a borda #13, que também **reporta** o cascade pré-existente que apaga os nós |
| 14 | Alarme falso semanal (sábado) | o operador aprende a ignorar o alarme, e ele deixa de servir para o caso real | `SEM_TRABALHO` imediato e sem card (Decisões 26 e 27, F2) |
| 15 | Rebuild do índice de eventos na 6c | duplicata inserida na janela sem unicidade faz o `CREATE UNIQUE` falhar e **aborta o deploy** com front e `dags/` já novos | O índice novo nasce **antes** de o velho sair (§5.3, bloco 4) |
| 16 | `ix_pipe_exec_malha` varrendo `etl_pipeline_execucao` em produção | bloqueio de escrita do motor na 6c com o app no ar | Dimensionamento **antes** (§11.3) e, acima do limiar, janela própria |
| 17 | `sql/migrate.py` descarta `PRINT` (D40) | a conferência "parece ter rodado" | §12.1 — `SELECT` de **objeto** com o valor esperado por linha |

---

## 15. Smoke pós-deploy

Roteiro executável **sem contexto desta spec**, em `docs/smoke-malha-execucao.md`
(precedente: `docs/smoke-malha-componentes.md`), sempre numa **malha de teste**,
nunca na de produção. Estrutura: §0 pré-requisitos (§12.1 + o relógio) · §1
interruptor em `0` prova que nada mudou · §2 ligar e abrir uma corrida pelo
disparo · §3 o defeito relatado (card com membro em falha) · §4 fechar pelo Fim ·
§5 fechar por quiescência (malha sem Fim) · §6 sábado = `SEM_TRABALHO` · §7 hold
e teto · §8 rerun e a segunda conclusão · §9 encerrar corrida pela tela. Cada
passo com o `SELECT` de conferência e um "⚠️ **pare**" quando o valor vier
errado.

---

## 16. Invariantes a declarar e testar

1. **No máximo uma corrida `ABERTA` por malha** — `ux_malha_exec_aberta`, provada
   com `INSERT` direto no banco.
2. **`status='ABERTA' ⟺ fechada_em IS NULL`** — `CK_mexec_coerente`.
3. **Toda corrida aberta fecha** — por Fim, quiescência, `SEM_TRABALHO`, teto,
   aborto, cancelamento ou pela porta do operador. Nenhum caminho a deixa aberta
   indefinidamente, porque corrida aberta bloqueia disparo.
4. **Nunca inventar verde** — `EXPIRADA`/`ABORTADA`/`FALHA`/`SEM_TRABALHO`/
   `CANCELADA` jamais emitem `MALHA_CONCLUIDA`. Teste de **ausência**.
5. **O teto nunca fecha corrida com membro vivo.**
6. **Corrida sem membros = `ABORTADA` após a carência, nunca `CONCLUIDA`.**
7. **`_data_referencia` é função pura do run** — nenhum degrau lê estado que muda
   durante a execução.
8. **O vínculo é write-once** — uma linha nunca troca de corrida.
9. **Todo relógio da corrida é o do banco** — testado com relógio deslocado.
10. **Toda leitura degrada** — sem a 085 (ou com o interruptor em `0`) a tela
    volta ao comportamento de hoje **com rótulo honesto**, e o motor não muda de
    comportamento em ponto nenhum.
11. **A corrida não é dona do pipeline** — a relação é N:N e a barreira vale no
    mais restritivo (o que `malha_ciclo.malhas_do_pipeline` já implementa).
12. **Paridade `dags/utils/` × `api/services/`** — matriz idêntica, SQL capturado
    igual, no mesmo commit.

---

## 17. Backlog garantido (o modelo já nasce preparado)

1. **Modo SEQUÊNCIA como padrão** — muda o interruptor 083, não o corte.
2. **SLA por corrida** — `teto_em` já existe; falta o alvo de conclusão e o
   `MALHA_SLA_ESTOURADO`.
3. **Tela de histórico de corridas** com duração, tentativas e comparação entre
   dias — `GET /corridas` (F4) já é a fonte.
4. **Expurgo de `etl_pipeline_execucao` guiado por corrida fechada** — hoje não há
   critério; `fechada_em` é um.
5. **Corrida de malha como predecessor de outra malha** (dependência entre
   malhas) — a corrida é a identidade que faltava; nada disso é escopo agora.

## 18. Pendências desta spec (depois do deploy validado)

1. Ligar `malha_corrida_ativa` em produção, malha a malha, depois do smoke.
2. Fixar com o dono o **limiar de linhas** de `etl_pipeline_execucao` acima do
   qual a 085 sai da 6c, e a **edição** do SQL Server da Caixa.
3. Reportar o **achado colateral pré-existente** da borda #13: o rename de malha
   apaga Início/Fim/Aguarde/Notificação pelo `ON DELETE CASCADE` de
   `sql/migrations/075_malha_nos.sql:56-57`. É anterior a esta spec e merece PR
   própria.
4. Reescrever os docstrings de `dependencia_janela_sequencia_horas` e
   `inicio_do_ciclo_corrente` para dizerem que agora são **fallback de quem não
   tem corrida**.
5. Confirmar com o usuário a leitura da decisão 4 (§4): o ODATE é carimbado na
   **abertura**, não ao passar pelo Fim.

---

**Ordem de deploy, numa frase:** etapa 5 (`dags/`, responder `s`) → etapa 6c
(migration **085**, prompt padrão-NÃO, responder `s`, **nunca** `--baseline`) →
`api/` + front (automáticos) → etapa 8b **`n`** em todas as fases — e **só na F5**
com `force_all` disparado à parte, confirmado pela sonda por pipeline do §12.2;
o interruptor `malha_corrida_ativa` só vai a `1` depois da F7 e do smoke.
