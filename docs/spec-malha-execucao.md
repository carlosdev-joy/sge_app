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
| 14 | Malha excluída com corrida aberta | ⚠️ **BORDA INEXISTENTE, verificada na F3 (2026-08-05):** não há `@router.delete("/malhas/{m}")` no código, nem `deleteMalha` no front — o único `DELETE FROM dbo.etl_malha` é o do rename (borda 13, que já carimba a corrida). Malha não se exclui neste produto; ela se **inativa** (`PATCH ativo=0`, tratado na F8). Se um dia existir exclusão, ela precisa cancelar a corrida na mesma transação, senão a corrida órfã presa no índice filtrado impede recriar uma malha com o mesmo nome |
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
| 0 | **o ODATE já gravado na linha deste `run_id`** (`malha_corrida.odate`, `SQL_ODATE_DO_RUN`) | a Decisão 36 tornada durável — ver a nota abaixo da própria Decisão 36 |
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

> **Como ficou, na execução da F5 (2026-08-05):** a memoização é de **duas
> camadas**, e a segunda é o **degrau 0** da tabela acima. Um dicionário por
> `run_id` no fonte gerado resolve as chamadas do MESMO processo; mas o cenário
> literal da Decisão 36 é entre **tasks diferentes** — `check_agenda` às 01:10 e
> `_registrar_sucesso` às 04:52 rodam em processos distintos, e cache em memória
> não os atravessa. Por isso o degrau 0 lê o ODATE **já gravado na linha deste
> `run_id`**: o run tem um ODATE, ele nasce na primeira chamada e nenhuma
> chamada posterior o redecide. De quebra, é ele que faz "rerun que reusa o
> `run_id` preserva o `malha_execucao_id`" valer sem nenhuma regra especial de
> rerun.
>
> ⚠️ O degrau 0 decide a **data**, e só ela: a **proveniência** continua sendo
> procurada enquanto a linha não tem dono, limitada a corrida do MESMO ODATE.
> Sem essa ressalva, o dependente — cuja linha nasce no claim do pai
> (`reservar_corrida`), sem `malha_execucao_id` — ficaria para sempre sem
> vínculo mesmo tendo recebido a corrida no conf. Foi **medido no dev**:
> `DEV_F10_D` concluiu em `2026-08-02` com `malha_execucao_id` NULL, isto é,
> toda a cascata fora do ciclo a que pertence e o "4 de 7" contando errado.

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

## 9. O card, o painel e os eventos — a camada de visibilidade da corrida

Com a corrida existindo como **registro**, a tela pode responder o que hoje ela
não tem como responder: *está rodando?*, *em que pé está?*, *o que está
travando?*. Esta seção é o desenho dessa camada — e ela vale uma regra só, a
mesma da casa: **campo agregado que não responde "isso é verdade AGORA?" não
entra.** Um número derivado sem denominador, sem instante de apuração e sem
degradação declarada é o card que mente com roupa nova.

### 9.0 As quatro perguntas, na ordem em que são feitas

| # | Pergunta | Onde ela é feita | O que responde |
|---|---|---|---|
| **0** | **onde está o incêndio?** | celular (Teams), Dashboard | *qual* malha abrir |
| 1 | está rodando? | card da lista, faixa do painel | estado + saúde |
| 2 | em que pé está? | barra + `x de y` + relógio | progresso e tempo |
| 3 | o que está travando, e **posso esperar**? | abas do painel | culpado, dono e duração típica |

**A hierarquia é uma só e vale nas duas superfícies: estado → progresso → tempo
→ culpado.** O culpado só ocupa espaço quando existe. Nada de KPI cards, nada de
grade de números: a malha é tela de **acompanhamento**, não dashboard.

A pergunta 0 decide se as outras três chegam a ser feitas. Às 3h ninguém abre
`/malha` por vontade própria: chega-se pelo card do Teams (que hoje **não tem
botão de link** — `dags/utils/ds_teams.py:montar_card` não emite `Action.OpenUrl`,
ao contrário do gerador de DAG em `dags/etl_dag_factory.py:1049`) ou pelo
Dashboard (cujo link de dependência faz `navigate('/malha')` **sem malha e sem
modo**, `ui-react/src/pages/Dashboard.tsx:499`). Uma camada de visibilidade sem
§9.8 é uma tela para o horário comercial.

### 9.1 O card da lista — como "concluída" deixa de mentir

`_ultima_execucao_por_pipeline` (`api/routers/malhas.py:1541`) **sai do caminho
corrente** e vira fallback. Entram **duas** consultas, nenhuma por malha:

```sql
-- (1) a corrida corrente de cada malha: um SEEK por malha em ix_malha_exec_malha
SELECT m.malha_name, c.id, c.sequencia, c.status, c.data_referencia,
       c.aberta_em, c.fechada_em, c.fechada_por, c.motivo, c.origem,
       c.aberta_por, c.tentativas, c.reaberta_por, c.modo_fechamento,
       c.teto_em, c.teto_creditado_min
FROM dbo.etl_malha m
CROSS APPLY (SELECT TOP 1 me.* FROM dbo.etl_malha_execucao me
              WHERE me.malha_name = m.malha_name
              ORDER BY me.aberta_em DESC, me.id DESC) c;

-- (2) o denominador de TODAS elas de uma vez (GROUP BY unico sobre o indice
--     filtrado novo) — ok/total/vivos/dispensados/travados, derivados na
--     leitura, com o instante de apuracao vindo do MESMO relogio da consulta.
--     A clausula substituida_em IS NULL e OBRIGATORIA no numerador (Decisao 55).
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

**Payload** (tudo sai do mesmo `GROUP BY` ou do `SELECT` que já roda — o custo
por refetch **cai**, porque `_ultima_execucao_por_pipeline` sai do caminho):

```
corrida: {
  id, sequencia, status, saude, data_referencia,
  aberta_em, fechada_em, fechada_por, motivo, origem, aberta_por,
  tentativas, reaberta_em, reaberta_por, modo_fechamento,
  teto_em, teto_configurado, teto_creditado_min,
  membros_total, membros_ok, membros_vivos, membros_dispensados,
  membros_travados, membros_fora_do_odate,
  qtd_cadastro, inativos_fora,
  ultimo_movimento_em, quiescencia_ate,
  falhas[], pendentes[], vivos[],
  notificado_em, notificacao_pendente_desde,
  apurado_em
}
corrida_esperada: { previsto_para, atrasada_desde } | null      -- Decisao 58
```

| Campo aditivo | Como sai | Custo |
|---|---|---|
| `membros_vivos`, `membros_dispensados`, `membros_travados` | `SUM(CASE WHEN classe=… THEN 1 END)` no mesmo `GROUP BY` | 0 |
| `qtd_cadastro`, `inativos_fora` | já contados hoje para `⚙ N pipelines (N ativos)` | 0 |
| `ultimo_movimento_em` | `MAX(COALESCE(e.fim, e.inicio))` | 0 |
| `quiescencia_ate` | `DATEADD(MINUTE, @quiescencia, ultimo_movimento)` **em SQL**, nunca em Python (Decisão 10) | 0 |
| `teto_configurado` | `etl_malha.teto_horas IS NOT NULL` — separa SLA de anti-travamento (Decisão 61) | 0 |
| `notificado_em`, `notificacao_pendente_desde` | coluna que já existe (`067:189`) e **nunca foi lida** | 0 (uma coluna a mais no SELECT) |
| `vivos[]: {pipeline, desde}`, `pendentes[]` classificado | derivados de `execucoes[]`, **só** em `GET /execucao` | 0 |

**Decisão 40 — todo campo derivado exibido carrega o instante em que foi apurado,
ou é derivado na leitura** *(evita: a tela responder "isso era verdade há pouco"
quando o operador perguntou "isso é verdade agora?" — batendo F5 num número
congelado sem saber que está congelado)*. Aqui os derivados são calculados na
leitura e o payload traz `apurado_em` do relógio do banco. **Como esse instante
vira texto na tela é a Decisão 60** — e não é subtraindo `apurado_em` de
`Date.now()`, que é exatamente a armadilha do §14/risco 8.

**Decisão 41 — a degradação é POR MALHA (`corrida` ausente), nunca por flag de
migration** *(evita: o front novo contra a API velha — o `deploy.sh` publica o
`dist/` na etapa 3, **automático e sem pergunta**, e a API só é reconstruída na
etapa 7; nesse intervalo o front novo conversa com a API velha, que não manda
`corrida` **nem** `migration_085_pendente`. Sem flag, o front concluiria "está
tudo certo" e renderizaria `corrida` indefinida. E se o operador responder `n` na
6c, o intervalo é permanente)*. Regra: `if (!m.corrida)` → texto de hoje com o
sufixo **"(membro mais recente)"** e **jamais** a palavra "concluída".

**Aditivo à Decisão 41:** a degradação também é **dita**. O card degradado ganha
a linha `⚠ sem dados de corrida — sistema em atualização`, igual em todos os
cards afetados *(evita: quem não é técnico ler o card degradado como um card
diferente, e não como uma tela sem parte da informação)*. A flag
`migration_085_pendente` fica só como texto explicativo do tooltip.

### 9.2 O progresso — o denominador, e as travas do número

**Decisão 52 — o denominador é `membros_total` do snapshot
(`ativo_na_abertura = 1`), e ele NÃO ENCOLHE durante a corrida** *(evita: o
progresso subir quando a situação piora. `dispensado` inclui `PULADO`, que é
carimbado **durante** a corrida — regra de dia, barragem do `check_agenda` e a
Decisão 15, `CORRIDA_ABERTA_DE_OUTRO_ODATE`. Com `esperados = total −
dispensados`, o cenário real é: 02:00 o card diz `2 de 7`; 02:40 a guardiã marca
3 membros `PULADO` por divergência de ODATE — o incidente `Carga_Vida`; 02:41 o
card diz **`2 de 4`**. O olho lê "avançou", e o que aconteceu foi três pipelines
serem barrados. É o card que mente com matemática nova, e um texto numa terceira
linha não desfaz a leitura de 2 segundos que a barra já entregou)*.

Os outros dois candidatos a denominador, e por que não:

- **etapas (`etl_pipeline_job` / `etl_job_execution`)** — parece o mais fino, e
  é o mais caro. Para os run_ids `dep__…` — exatamente o caso de cascata de
  malha — a ponte entre `etl_pipeline_execucao.execution_id` (run_id) e
  `etl_job_execution.execution_id` (ts_nodash) é **leitura do Airflow**
  (`api/services/execucao_identidade.py:179-188,300`;
  `api/routers/execucoes.py:1707-1723`). Uma chamada HTTP por membro a cada
  refetch é proibitiva. **Fica em backlog**, com o caminho barato já identificado
  e a justificativa correta: um rollup por `pipeline IN membros AND start_time >=
  aberta_em` sobre `IX_etl_job_execution_pipeline_status_start` é **uma** consulta
  de conjunto, sem Airflow — o que ele não é é **identidade de run**; é recorte de
  tempo, e isso precisa estar escrito para a próxima pessoa não ler "proibitivo" e
  nunca mais voltar.
- **peso por duração histórica** — transformaria progresso em **previsão**. O §3
  proíbe backfill: no dia 1 o histórico é **zero**, e uma barra ponderada por
  média inexistente é número inventado com aparência de precisão.

**Decisão 53 — a subtração aparece SEMPRE, na linha imediatamente abaixo da
barra, e é ancorada no cadastro** *(evita: dois denominadores no mesmo card —
`⚙ 7 pipelines (7 ativos)` na terceira linha e `4 de 6` na barra, com a explicação
numa quarta linha que só existe "se houver problema"; e o caso pior do membro
inativado: alguém inativa 5 dos 7 na sexta, `ativo_na_abertura = 0` os tira do
snapshot, e sábado o card diz **`2 de 2 · concluída`, verde** — a família "card
que mente" com um número dando autoridade)*.

```
membros_total (denominador)  =  COUNT(snapshot WHERE ativo_na_abertura = 1)
linha de baixo, obrigatoria  =  "N membros nesta corrida"
                              + ", K nao rodam hoje (regra de dia)"   se dispensados > 0
                              + ", J inativos fora desta corrida"     se membros_total < qtd_cadastro
```

`membros_total < qtd_cadastro` é **fato visível**, nunca nota de rodapé.

**Decisão 54 — o TRAVADO não entra na barra: vira chip vermelho ao lado**
*(evita: a leitura periférica errada. `████▓▓▓▒▒░░ 3 de 6` pinta 5/6 da barra e,
a 1,5 m, lê-se "quase pronto". "Vermelho é lastro, ocupa o lugar que ocuparia se
tivesse dado certo" é teoria de layout correta e prática noturna ruim: em
varredura de 40 cards o operador lê comprimento, não cor)*. A casa já tem a
linguagem certa — os chips de `PainelExecucaoEtapas.tsx:253-266`
(`3 sucesso · 1 falha · 2 executando`). **A barra responde uma coisa só: quanto
já ficou pronto.** O chip é clicável e leva à aba `Travando`.

Composição final da barra, ordem **fixa** (nunca reordena entre refreshes):

```
[ verde: ok ][ azul: vivo ][ trilho hachurado neutro: dispensado ][ trilho vazio: o resto ]
```

| Classe (§6.4) | Entra no denominador? | Conta como ok? | Onde aparece |
|---|---|---|---|
| `OK` (SUCESSO vivo, `substituida_em IS NULL`) | sim | **sim** | segmento verde |
| `vivo` (EXECUTANDO / AGUARDANDO_DEPENDENCIA) | sim | não | segmento **azul**, o único animado |
| `dispensado` (`PULADO` / sem dia permitido) | **sim** | não | **trilho hachurado neutro**, dentro da barra |
| pendente `falhou` | sim | **nunca** | trilho vazio + **chip vermelho** fora da barra |
| pendente `nao_liberou` / `orfa` | sim | nunca | trilho vazio + chip |
| pendente `nao_partiu` | sim | nunca | trilho vazio |
| `fora_do_odate` | não | **nunca** | banner âmbar na faixa (Decisão 66), nominal |

O card usa **duas** cores preenchidas (verde e azul) mais dois tratamentos de
trilho; as classes de pendência ficam nos chips. A legenda de quatro cores vive
no painel, onde cabe legenda — no card, quem nomeia é a linha 3.

**Decisão 55 — `substituida_em IS NULL` é cláusula obrigatória do numerador E do
`GET /malhas/{m}/execucao`, na MESMA PR** *(evita: dois números discordando na
mesma tela. Hoje o painel monta `execucoes[]` filtrando só `data_referencia`
(`api/routers/malhas.py:2203-2210`, desempate por `mais_recente_da_data`) e não lê
essa coluna, enquanto o motor filtra por ela em 12 pontos
(`dags/utils/dependencias.py:471,493,531,624,645,1286`). Depois de um rerun às 3h:
a **faixa** diz `3 de 6` e o **nó no canvas** fica verde com a linha que o motor
já aposentou. Corrigir só a barra é trocar o defeito de lugar)*.

**Decisão 56 — não existe `%` em superfície nenhuma; "concluída" e barra cheia só
em corrida terminal verde** *(evita: quatro coisas — (i) o arredondamento
`99,6 → 100` que é o defeito clássico; (ii) `4/6 = 66,67` virar `67%` (o próprio
rascunho desta camada escreveu `67%` em dois mockups, com a regra do `Math.floor`
escrita três parágrafos acima — se o mockup arredonda, o código arredonda);
(iii) com 6 membros o percentual só assume 7 valores, e `(67%)` sugere medição
contínua de uma contagem de 6; (iv) o pior: é **% de pipelines** apresentado como
progresso de **trabalho** — numa malha de 6 em que o último leva 3h e os cinco
primeiros 5 min cada, aos 25 minutos o painel diria `83%` faltando 87% do
tempo)*. O rótulo é sempre `x de y`, e o substantivo é **pipelines**, nunca
"progresso": *"4 de 7 pipelines concluídos"*.

⚠️ **Isto contrariava a letra do pedido original ("% de execução"). RESOLVIDO
pela Decisão 56b abaixo, decidida com o usuário em 2026-08-04: o `%` volta — mas
medindo TEMPO, não contagem de pipelines.**

**Decisão 56b — existe UM percentual, e ele é do TEMPO ESTIMADO, nunca de
pipelines: `≈ 60% do tempo típico`** *(evita, de uma vez, o defeito que a 56
descreve e a lacuna que ela abria. O pedido do usuário — "dentro de cada malha %
de execução" — é a pergunta "em que pé está?", e a resposta honesta a ela é o
tempo, não a contagem: numa malha de 6 em que o último leva 3h e os cinco
primeiros 5 min, `5 de 6` é 83% dos pipelines e 12% do trabalho. O percentual
ponderado dá 12%, que é a verdade)*.

Regras que o tornam honesto — todas obrigatórias, e a ausência de qualquer uma
tira o número da tela:
- **Numerador e denominador são MINUTOS**, vindos da duração típica por membro
  (Decisão 64): soma das durações típicas dos membros já concluídos, sobre a soma
  de todos os membros do snapshot. Membro em execução entra pelo tempo já
  decorrido, limitado à própria duração típica — nunca ultrapassa a própria fatia.
- **Só aparece com `n ≥ 5` em TODOS os membros do snapshot.** Faltando histórico
  em um só, o percentual some (não é estimado, não é "aproximado com ressalva"):
  fica só o `x de y` e a duração típica dos vivos. É a mesma regra do `n` visível
  da Decisão 64 — número sem lastro não entra.
- **Prefixo `≈` e sufixo `do tempo típico`, sempre.** Nunca `60%` solto, nunca
  "concluído": o rótulo é `≈ 60% do tempo típico`. O `≈` é parte do dado, não
  enfeite — remove a promessa de precisão que a 56(iii) denuncia.
- **`Math.floor`, teto em 99** enquanto a corrida não for terminal (a 56(i)), e
  **sem percentual nenhum** em corrida terminal: lá o estado já diz tudo.
- **Ele nunca substitui o `x de y`**, que continua sendo o número primário e o
  primeiro a ser lido. O percentual é o SEGUNDO, entre parênteses, e some antes
  dele em qualquer aperto de espaço (card estreito, mobile).
- **Corrida `ATRASADA` mostra o percentual mesmo passando de 100% do típico** —
  aí ele vira `≈ 140% do tempo típico`, que é exatamente o sinal de atraso, e
  **não** é truncado em 100: truncar esconderia o que o operador precisa ver.

Rótulo final da faixa, com histórico suficiente:

> `4 de 7 pipelines · ≈ 38% do tempo típico · 2 rodando há 12 min`

E sem histórico suficiente (o caso do primeiro mês de uma malha nova):

> `4 de 7 pipelines · 2 rodando há 12 min`

Com `status = 'ABERTA'` e `ok === membros_total − dispensados`, a barra fica
cheia e o rótulo é:

> `7 de 7 · fechando — fecha 15 min após o último movimento; se nada mais mexer,
> por volta de 04:17`

Nunca "concluída", nunca barra terminal. Isto implementa a Decisão 45 sem
reintroduzir o defeito que ela existe para evitar: **o relógio de quiescência
reinicia a cada movimento**, então um horário exato ("até 04:17") faria o operador
reportar bug às 04:18 quando um pipeline se mexeu às 04:16. A frase diz a regra
antes de dizer a hora.

**Decisão 57 — `SEM_TRABALHO` não tem barra; desfecho interrompido tem barra
CONGELADA** *(evita: 0% ler como "falhou tudo" e 100% ler como "rodou tudo", nos
dois casos em que nenhum dos dois é verdade)*.

- **`SEM_TRABALHO`**: a barra **desaparece**. No lugar, traço neutro e a frase
  *"nada previsto para 09/08 — os 7 membros não rodam hoje (regra de dia)"*. Sem
  alarme, sem vermelho (Decisões 26/27: alarme falso semanal treina o operador a
  ignorar o alarme). A exceção é a Decisão 68 (sábado legítimo × terça suspeita).
- **`EXPIRADA` / `ABORTADA` / `CANCELADA`**: a barra **congela** no valor apurado
  no fechamento, ganha `opacity-60`, e o rótulo muda de *"4 de 7"* para **"parou
  em 4 de 7"**. A palavra "concluído" não aparece em nenhuma das três
  (invariante 4 do §16: nunca inventar verde).

**Decisão 58 — a corrida que NÃO ABRIU é um estado da tela, e ela ordena
primeiro** *(evita: o pior modo de falha ficar mudo. O Início não disparou às
01:00 — DAG pausada, Airflow fora, agendamento quebrado. Às 8h o card mostra a
corrida de **ontem**, `concluída`, verde, com carimbo de frescor recente. Toda
esta camada pressupõe "a corrida existe"; a única peça que sabe o que **deveria**
ter acontecido é `proximaExecucao.ts`, listada na §13 como não tocada por ser
"gatilho, não ciclo" — e é exatamente por isso que ela é a peça que falta)*.

`corrida_esperada` é calculada **na API**, não no front: comparar a hora agendada
do gatilho com "agora" no relógio do navegador é a armadilha do §14/risco 8 numa
casa em que o desvio medido é de 3h. Usa-se `dep.agora_do_banco(conn)` +
`desvio_banco`, como `_divergencias_e_falhas` já faz. Condição: existe gatilho com
horário previsto para o ODATE corrente, esse horário já passou com folga
configurável, e **não existe corrida com aquele `data_referencia`**. Resultado:
estado `não abriu`, âmbar, contador próprio na stats bar, e ordenação no topo da
lista. §13 passa a ter uma exceção nominal — `proximaExecucao.ts` é tocada, e a
razão é esta.

### 9.3 Os estados, a saúde e a cor

**Decisão 46 — `statusExecucao.ts` ganha um mapa PARALELO `STATUS_CORRIDA`, não
reusa `STATUS_EXECUCAO`** *(evita: mentira de domínio — reusar faria `ABERTA`
herdar o estilo de `EXECUTANDO`, e `EXPIRADA`/`SEM_TRABALHO` caírem no
`default` cinza)*. Tokens `canvas/panel/edge/ink/dim` nos **dois** temas, pt-BR.
`MalhaComponenteNodes.tsx`: o nó Fim ganha o estado que hoje não tem — hoje é
verde (`concluidaEm`, `:176-177`) ou apagado; passa a ter **"ciclo aberto"**,
como **anel azul discreto e `title`, sem texto no nó** (o número já está na faixa
a 3 cm de distância, e a regra de não empilhar informação no nó vale igual aqui).

| Status | Rótulo pt-BR | Ícone (lucide) | Claro | Escuro | Nó Fim |
|---|---|---|---|---|---|
| `ABERTA` | **em andamento** | `Activity` | `bg-blue-100 text-blue-700 border-blue-300` | `dark:bg-blue-900/60 dark:text-blue-300 dark:border-blue-700` | anel azul animado |
| `CONCLUIDA` | **concluída** | `CheckCircle2` | `bg-green-100 text-green-700 border-green-300` | `dark:bg-green-900/60 dark:text-green-300 dark:border-green-700` | anel verde |
| `FALHA` | **falhou** | `XCircle` | `bg-red-100 text-red-700 border-red-300` | `dark:bg-red-900/60 dark:text-red-300 dark:border-red-700` | anel vermelho |
| `EXPIRADA` | **encerrada sem terminar** | `TimerOff` | `bg-red-100 text-red-700 border-red-300` | `dark:bg-red-900/60 …` | anel vermelho |
| `ABORTADA` | **não chegou a começar** | `CircleSlash` | `bg-red-100 text-red-700 border-red-300` | `dark:bg-red-900/60 …` | anel vermelho |
| `SEM_TRABALHO` | **sem trabalho hoje** | `Moon` | `bg-slate-100 text-slate-600 border-slate-300` | `dark:bg-slate-800 dark:text-slate-300 dark:border-slate-600` | apagado |
| `CANCELADA` | **encerrada por C123456** | `Ban` | `bg-amber-50 text-amber-700 border-amber-300` (contorno) | `dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-800` | apagado |
| *(derivado)* `nao_abriu` | **não abriu** | `CalendarX` | `bg-amber-50 text-amber-700 border-amber-300` | `dark:bg-amber-900/30 …` | apagado |

**Decisão 59 — a partição de cor é "isso me chama às 3h?", o preenchimento separa
"acabou mal" de "ainda pode virar", e o cinza é só para "não havia trabalho"**
*(evita: três defeitos de varredura medidos na leitura desta camada — (i) três
cinzas competindo (`SEM_TRABALHO`, `CANCELADA` e a malha inativa que já é slate
em `Malha.tsx:158-165`), o que ensina "cinza = não preciso olhar" e esconde um
cancelamento humano que é item de auditoria; (ii) quatro vermelhos indistintos —
`FALHA`, `EXPIRADA`, `ABORTADA` e `ABERTA·com falha` — fazendo o gestor reportar
"4 incidentes" quando três já acabaram e um ainda pode fechar verde; (iii)
`SEM_PROGRESSO` em slate, que é a decisão de cor mais perigosa possível, porque
"nada se moveu há 40 min" com membro vivo é o sintoma nº 1 da execução órfã
(`dags/etl_dependencia_guardia.py:430`), a classe de defeito mais cara do
produto)*.

```
vermelho CHEIO     = acabou mal, acao agora      (FALHA, EXPIRADA, ABORTADA)
vermelho CONTORNO  = falha dentro de corrida VIVA, com a palavra "ainda rodando"
ambar              = prazo/atipico/humano        (ATRASADA, SEM_PROGRESSO, CANCELADA, nao_abriu)
slate              = nao havia trabalho          (SEM_TRABALHO)  — e so ele
```

E a regra da casa continua valendo: **cor nunca é o único canal**
(`SupervisaoCard.tsx:64-65`) — os três vermelhos têm ícone e rótulo distintos,
legíveis por quem não distingue vermelho de âmbar.

**A saúde manda na cor quando o status é `ABERTA`** (Decisão 11):

| Saúde | Rótulo composto | Cor | Ícone |
|---|---|---|---|
| `OK` | `em andamento` | azul | `Activity` |
| `COM_FALHA` | `em andamento · com falha (ainda rodando)` | **vermelho contornado** | `AlertTriangle` |
| `ATRASADA` | `em andamento · fora do prazo` | **âmbar** | `Clock` |
| `SEM_PROGRESSO` | `em andamento · sem sinal há 40 min` | **âmbar** | `Hourglass` |

`SEM_PROGRESSO` e `ATRASADA` são **os dois âmbar**, e o desempate é por ícone e
por texto, não por cor. A objeção "dois âmbares se apagam" resolve estética
criando risco operacional, e a própria Decisão 59 diz que ícone+rótulo separam
dentro da cor.

No **canvas**, a corrida não pinta nós — pinta o **nó Fim** (o único que fala de
ciclo) e a faixa. Os nós continuam com `STATUS_EXECUCAO`. A legenda do rodapé
(`MalhaEditor.tsx:2542-2576`) ganha **só** o traço tracejado âmbar de `esperando`
(§9.9): oito estados de corrida na legenda seria o ruído que a Decisão 75 proíbe.

### 9.4 O tempo — três relógios diferentes, e nenhum deles é o mesmo

**Decisão 60 — o DECORRIDO é do banco; o FRESCOR é do navegador consigo mesmo; e
nenhum dos dois mistura os dois relógios** *(evita: o defeito que o próprio
rascunho desta camada cometeu ao proteger o decorrido e esquecer o frescor. Com
`apurado_em` do banco e `Date.now()` do navegador e o desvio de 3h medido no dev,
`· atualizado há 8s` viraria "atualizado há -3h", ou "agora" eternamente, e o
alarme de dado velho **nunca dispararia** — um carimbo de frescor que mente sobre
o próprio frescor)*.

```
decorridoBase = apurado_em − aberta_em      -- os DOIS do banco, subtraidos no servidor
decorrido     = decorridoBase + (Date.now() − instanteLocalDaResposta)
frescor       = Date.now() − instanteLocalDaResposta      -- so relogio local
```

Módulo novo `malhas/tempoCorrida.ts`, puro (sem React, regra do
`react-refresh/only-export-components`, como `componenteMeta.ts`), com
`useDecorrido()` à parte, testado com relógio deslocado. `apurado_em` alimenta
apenas o **texto absoluto do tooltip**.

Aditivos de forma, que custam zero e evitam desconfiança:

- **granularidade grossa** no frescor (`agora` / `há menos de 1 min` / `há 3 min`)
  — precisão de segundo em polling de 15–20 s sugere tempo real; e dois cards com
  `há 8s` e `há 31s` na mesma tela fazem duvidar dos dois;
- **um carimbo por página**, no cabeçalho da lista, não um por card;
- acima de 90 s sem sucesso de refetch: `⚠ dado de HH:MM:SS`, em âmbar;
- **um formato de tempo por posição**: relativo enquanto a corrida está aberta
  (`há 42 min`), absoluto quando fechada (`01:10 → 04:02 · 2h52`). Nunca os três
  formatos no mesmo card.

**Decisão 61 — o prazo que aparece por padrão é o PRÓXIMO GATILHO da própria
malha, não o teto; e a barra de teto só existe quando `etl_malha.teto_horas` foi
configurado para aquela malha** *(evita: três coisas — (i) o teto ser lido como
SLA quando ele é **anti-travamento**: `teto_horas` é `NULL` por padrão e cai no
global de 24h (§6.6), então uma barra em 80% às 20h numa malha que sempre fecha em
3h faria escalar por nada; (ii) a barra **andar para trás**, porque
`teto_creditado_min` empurra `teto_em` quando um hold é solto (§6.7) — às 03:00 a
barra em 80%, alguém solta um hold de 6h, a barra cai para 55% sozinha, e uma
barra de prazo que recua destrói a confiança em todas as outras; (iii) às 04:00
"faltam 21h de teto" ser irrelevante enquanto o fato que importa é que a próxima
corrida parte às 01:00 e a corrida aberta **bloqueia** essa partida)*.

O prazo por padrão, custo zero, com as duas peças já prontas (`proximaExecucao.ts`
+ `gatilho` do payload do card):

> *"a próxima corrida parte em 2h50 (01:00) — enquanto esta não fechar, ela não
> abre"*

Essa é a frase de consequência do índice `ux_malha_exec_aberta` (§5.3), e é o
gatilho real do escalonamento: a hora em que o incidente deixa de ser "um dia" e
vira "dois dias empilhados". Com `teto_configurado = true`, aparece **também** a
barra de teto; e o crédito de hold nunca é silencioso: vira evento nomeado na aba
`Eventos` — *"+6h creditados por retenção às 03:05"*.

### 9.5 Quem está rodando AGORA, o que está travando, e se dá para esperar

Três superfícies, três níveis de detalhe, **uma única fonte** — o agregado do
§9.1. Nenhuma delas conta linha de `execucoes[]` no cliente.

| Superfície | Detalhe | Custo |
|---|---|---|
| **Card da lista** | `2 rodando (mais antigo há 12 min)`, dot azul `animate-pulse`, só com `membros_vivos > 0` | 0 — mesmo `GROUP BY` |
| **Faixa do painel** | segmento azul animado + `2 rodando` clicável (abre a aba `Agora`) | 0 |
| **Aba `Agora (2)`** | `CARGA_B · há 12 min · típico 18 min (n=23)` · `▶ etapas` | `vivos[]` sai de `execucoes[]` que já vem |
| **Aba `Travando (2)`** | classe, dono, raio de alcance e ação por classe | `pendentes[]` agregado |
| **Canvas** | anel azul pulsante (já existe) | 0 |

O contador de vivos **carrega a idade do mais antigo** *(evita: `1 rodando` numa
corrida atrasada há 25h tranquilizar o operador quando aquele `EXECUTANDO` não se
mexe há 20h e não é `orfa` porque o evento `EXECUCAO_ORFA` nunca saiu)*. Acima do
limiar, a palavra muda: `1 sem sinal há 20h`.

**Decisão 62 — a aba ativa é derivada da SAÚDE, e `Encerrar corrida…` existe em
TODA corrida `ABERTA`** *(evita: (i) enterrar a única pergunta aberta — quando o
operador abre o painel às 3h, as perguntas 1 e 2 já foram respondidas pelo card ou
pelo alarme, e obrigar um clique em `Travando` é um clique a mais na única coisa
que ele veio fazer; (ii) o botão de encerrar nascer só depois do teto vencido,
que reintroduz o problema que a Decisão 32 existe para matar — os casos em que
mais se precisa encerrar são `ABERTA · SEM_PROGRESSO` (DagRun morto) e
`ABERTA · COM_FALHA` quando já se decidiu que a madrugada acabou)*.

```
COM_FALHA | ATRASADA | SEM_PROGRESSO  -> abre em  Travando
OK                                     -> abre em  Agora
corrida fechada                        -> abre em  Eventos
```

O que muda por estado é o **texto da confirmação** do encerramento, nunca a
presença do botão. E a confirmação diz a consequência, não só a permissão:
*"encerrar libera o disparo da próxima corrida; os 2 pipelines em execução
continuam rodando"*.

**Um clique até o problema.** Cada linha das abas `Agora` e `Travando` tem:

- **clique na linha** → acende o realce no canvas (reusa
  `components/etapas/PainelRealce.tsx`, já montado no editor em
  `MalhaEditor.tsx:2400-2416`) e centraliza o nó;
- **botão `▶ etapas`** → abre o drill-down do pipeline, o mesmo caminho do chip do
  nó (`MalhaPipelineNode.tsx:123-135`), sem exigir que o operador ache o nó no
  desenho.

Isto resolve o buraco que hoje é estrutural: descobrir o que está rodando é
**varrer o canvas com o olho** procurando anel azul, e o painel lateral fica
**vazio justamente durante a corrida saudável**, porque ele é de *eventos da
guardiã* (`MalhaEditor.tsx:2225-2262`) e corrida saudável não gera evento.

**Decisão 63 — cada travado carrega RAIO DE ALCANCE e CRITICIDADE** *(evita:
`↳ falhou: CARGA_A` não dizer se atrás dela há 1 ou 17 pipelines parados, nem se
algum é `ALTA` — que é exatamente o que decide acordar alguém)*. Custo zero e
client-side puro: `useRealceDependencias`/`cadeiaRealce` já calculam a cadeia à
frente e `criticidade` já vem no payload. A linha vira:

```
▲ CARGA_A [ALTA] · falhou 03:07 · 4 pipelines parados atrás   [▶ etapas] [↻ reexecutar]
◐ CARGA_C          esperando CARGA_A desde 03:07              [🔍 realçar]
```

E as classes **nunca** viram "3 pendentes" — são três problemas com três donos
(Decisão 21), e a ação por classe é: `falhou` → `▶ etapas` / `↻ reexecutar`;
`nao_liberou` → realçar a dependência / soltar hold; `nao_partiu` → ver a DAG;
`orfa` → Finalização Manual.

**Decisão 64 — a duração típica POR MEMBRO é o número que decide "posso
esperar", e ela vem com `n` visível e piso de `n ≥ 5`** *(evita: `4 de 7 · 2
rodando · há 12 min` não dizer se os dois vivos são de 5 min ou de 3h — e, pior,
`4 de 7` com os dois mais pesados restantes parecer "quase lá" e mandar o operador
dormir)*.

O argumento "sem histórico no dia 1" vale para a **corrida**, não para o
**membro**: `etl_job_execution` tem o histórico de sempre, e o molde já existe em
`GET /execucoes/duracao-media` (`api/routers/execucoes.py:2504`, `PERCENTILE_CONT`
com `COUNT(*)`, sem tocar o Airflow) — só que hoje ele é **por `job_name` dentro
de um pipeline**. O agregado desta camada é o irmão dele, **por pipeline**, sobre
os membros do snapshot, numa consulta de conjunto por painel aberto. Forma na
tela, com a mesma honestidade da própria fonte:

```
CARGA_B · há 12 min · típico 18 min (n=23)          -- normal
CARGA_D · há 41 min · típico 18 min (n=23)  ⚠ 2x    -- ambar acima de 2x o p50
CARGA_E · há  3 min                                  -- n<5: SO o decorrido, sem tipico
```

Sem `n ≥ 5` não se exibe nada — e o `n` aparece **sempre** ao lado do número.
Isto **não** é ETA de conclusão da corrida (Decisão 75/#3): é a duração típica de
um membro, medida, com amostra declarada.

**Decisão 65 — `↻ reexecutar` só existe com a frase do efeito na corrida em voo;
sem a frase, o botão não existe** *(evita: o gesto mais delicado do modelo virar
um clique de 3h no escuro. §6.9/#3: rerun com cascata só reabre a corrida se não
houver outra aberta; e `rerun.marcar_substituidas` bumpa `atualizado_em`, que a
guarda 2 da quiescência explicitamente **não** usa como âncora. Sem o texto, o
operador aperta e o painel muda de estado por baixo dele)*. O botão abre a prévia
que já existe (`GET /pipelines/{p}/rerun/previa`,
`api/routers/execucoes.py:724`) com uma linha nova: *"esta reexecução entra na
corrida de 04/08 (em andamento); o relógio de fechamento não reinicia por este
gesto"*. Se essa frase não puder ser escrita com certeza na fase, o botão sai e
fica só `▶ etapas`.

### 9.6 A visão de execução

| Hoje | Com a corrida |
|---|---|
| lente = `?data_referencia=YYYY-MM-DD` (`api/routers/malhas.py:2146`) | lente = `?corrida={id}`; a data continua como **atalho** |
| sem data → `dref.calcular(_agora(), _virada_global(cur))`, virada **GLOBAL**, com a divergência painel×disparo confessada em `:2377-2384` | sem parâmetro → **a corrida ABERTA**; sem corrida aberta, a última fechada. **A divergência some**: painel e disparo leem o mesmo registro |
| `WHERE data_referencia = ?` sobre o banco inteiro, filtro de membro em Python (`:2205-2210`), **sem** `substituida_em` | o predicado do §6.4 — recorte exato, sobre `ix_pipe_exec_malha`, com `substituida_em IS NULL` (Decisão 55) |
| `deps_svc.liberado()` **por membro esperando** (`:2231`, 2 round-trips × membro) | `pendentes[]` do agregado, calculado **uma vez por corrida** no servidor — o N+1 sai do caminho corrente |
| `malha_concluida` varre `eventos_no` procurando `MALHA_CONCLUIDA` do nó Fim (`:2280-2286`) | lê `status`/`fechada_em` da corrida. **O evento vira rastro, não fonte de verdade** |
| navegação ◀ ▶ por **dia** (`MalhaEditor.tsx:1976-1993`) | navegação por **corrida** (Decisão 42), com a faixa das últimas N |
| banner verde "Malha concluída em…" (`MalhaEditor.tsx:2214`) | a **faixa de corrida** do §9.13, com os pares honestos e a linha de diagnóstico da Decisão 43 |
| `bloqueios.em_aberto` + `datas_divergentes`, duas listas (`:2849-2872`) | **uma linha**: *"a corrida de 04/08, aberta às 01:10, ainda não passou pelo Fim"* — mantendo a **frase de ação** que a mensagem de hoje tem (`MalhaEditor.tsx:2872`), agora apontando para o botão de encerrar |
| `Segurar/Soltar` só no modo **Montagem** (`:2461-2486`) | existe **também** na Execução — hoje destravar exige sair da lente de acompanhamento no meio do incidente |
| painel lateral "EVENTOS DA GUARDIÃ" (`:2225-2262`), vazio na corrida saudável | **abas** `Agora · Travando · Eventos` com contador, reusando `ui/Tabs.tsx` |

**Decisão 42 — existe `GET /malhas/{m}/corridas?limite=N`** *(evita: navegar "por
corrida" no escuro, sem saber quantas corridas existiram na madrugada nem poder
pular para a anterior; e o atalho por data resolver para "a de maior `sequencia`",
**escondendo as anteriores do mesmo dia** — exatamente o caso que a `sequencia`
existe para preservar)*. A navegação é **uma só**: a **faixa das últimas N**,
clicável, com `title` por bloco; o `input[type=date]` vira um item do menu ("ir
para uma data…"). Não há `◀ ▶` **e** dropdown **e** faixa **e** calendário — às 3h
usa-se um, e quatro mecanismos de navegação temporal na mesma barra é decisão
adiada, não flexibilidade.

**Decisão 43 — o banner expõe os campos de diagnóstico em uma linha** *(evita:
gravar seis campos e não mostrar nenhum — as três primeiras perguntas às 3h são
"quem começou isso?", "é a primeira tentativa ou já mexeram aqui?" e "por que essa
malha fecha sem passar pelo Fim?", todas respondíveis pelo banco e nenhuma pela
tela)*: *"corrida de 04/08 · reaberta 1x por C123456 · aberta pelo **agendamento
do Início** (CARGA_RAIZ) às 01:10 · fecha sozinha 15 min após o último
movimento"*. `aberta_por` é traduzido na API (`'inicio:#12'` é formato de
máquina), e **nenhum dos rótulos técnicos** da §9.11 sobrevive à tradução.

**Decisão 44 — corrida com `origem='implicita'` DIZ isso na tela, e também no
card** *(evita: nas 3 de 4 malhas sem Início, o ODATE ser "o que o primeiro membro
achou" e a tela apresentar isso como "o ODATE da corrida", com uma autoridade que
ele não tem — e, na lista, essa corrida ser indistinguível de uma agendada)*: no
painel, *"data de referência definida pela primeira raiz a partir (CARGA_C,
01:03) — esta malha não tem nó Início"*; no card, a marca discreta
`início manual (C123456)` / `sem nó Início`.

**Decisão 45 — a carência de quiescência é explicada na tela, dizendo a REGRA
antes da hora** *(evita: o último pipeline ficar verde às 04:02, o card continuar
"em andamento" até 04:17, e o operador reportar bug ou — pior — disparar coisa na
mão; **e** o defeito espelho, de anunciar "até 04:17" como horário exato quando o
relógio reinicia a cada movimento, produzindo o mesmo chamado falso pela forma do
texto)*: *"fecha 15 min após o último movimento — se nada mais mexer, por volta
de 04:17"*.

**Decisão 66 — os três fatos que hoje não têm onde aparecer viram BANNER na
faixa, não item de aba** *(evita: enterrar numa aba o que decide a próxima ação)*:

| Banner | Quando | Por que na faixa |
|---|---|---|
| âmbar · `2 pipelines de outra data de referência: CARGA_X, CARGA_Y` | `membros_fora_do_odate > 0` | é o incidente que **originou esta spec**; é o único caso em que a barra está certa e o **dia** está errado. Mesmo patamar do banner de virada divergente que o editor já tem (`MalhaEditor.tsx:2028+`) |
| âmbar · `2 nós segurados desde 02:40 (por C123456) — a corrida não avança` + `Soltar` | `retido_em` em algum nó | hoje o cadeado existe só no nó, sem banner nem contador; `retido_em`/`retido_por` já vêm em `nos[]` e a ação já tem endpoint |
| vermelho · `aviso ao Teams na fila desde 03:07 — ninguém foi avisado ainda` | `notificacao_pendente_desde` | é o **pior** cenário de plantão: webhook com 401 por URL rotacionada, a guardiã loga e segue (`dags/etl_dependencia_guardia.py:822`), a malha falha em silêncio para todo mundo e o operador é o único que sabe |

**Decisão 67 — quem encerrou, por quê e por qual porta aparece na TELA, não só no
banco** *(evita: gravar `fechada_por`, `motivo`, `reaberta_por`, `origem` e
`tentativas` — a Decisão 32 até **exige** motivo no encerramento manual — e
apresentar tudo isso como o rótulo mudo "encerrada pelo operador"; fechar o mês
com 3 corridas canceladas e não conseguir explicar nenhuma sem abrir o banco)*.
Card e faixa: `encerrada por C123456 às 05:20 — motivo: "…"`. A lista de corridas
(Decisão 42) traz a coluna. `origem` e `tentativas` idem, com as palavras da
§9.11 (`reaberta 1x`, nunca `1ª tentativa`).

### 9.7 O histórico factual — e a fronteira com previsão

**Decisão 68 — contar desfechos PASSADOS não é previsão e entra; prever DURAÇÃO
sem histórico é adivinhação e fica fora** *(evita: usar a proibição de backfill do
§3 para bloquear **toda** informação histórica, que passa do ponto. A proibição é
contra **inventar corrida retroativa**; ler as corridas que de fato existiram é
fato registrado, disponível a partir do dia 2, e sai do índice
`ix_malha_exec_malha` que esta camada já usa)*.

Três leituras, todas factuais, todas com o `n` visível:

| Onde | Frase | Por que importa |
|---|---|---|
| card | `falhou 2 das últimas 7 corridas` | responde "está pior que antes?" sem abrir malha por malha |
| faixa | `corrida anterior: 03/08 · concluída · 01:10 → 04:02` | exige `n = 1`, não `n ≥ 5`: é fato, não mediana, e é a resposta mais direta a *"está pior que ontem?"* |
| faixa das últimas N | `title` do bloco = `04/08 · concluída · 2h41 · travou: CARGA_A` | 3 madrugadas seguidas travando em `CARGA_A` = crônico, espera o horário comercial; 9 verdes e essa vermelha = novidade, escala |

E o caso que só o histórico enxerga: **`SEM_TRABALHO` num dia atípico**. Alguém
inativa membros numa terça; o card diz `sem trabalho hoje`, cinza, sem alarme —
indistinguível de um sábado legítimo. Regra: se as últimas 4 ocorrências do mesmo
dia da semana **tiveram** trabalho, o estado sobe para âmbar com a frase *"as
últimas 4 terças tiveram trabalho"*. Sábado legítimo continua cinza e mudo
(Decisão 26).

**Backlog nomeado, porque o dado passa a existir:** quantas vezes esta malha
atrasou ou falhou em 30 dias — a pergunta da reunião mensal. Fica no §17.

### 9.8 Onde a corrida chega ANTES da tela de Malha

**Decisão 69 — os cards de malha no Teams levam BOTÃO para a corrida** *(evita:
a camada mais cara desta spec ter taxa de uso perto de zero exatamente no horário
para o qual foi feita. Às 3h chega um card no celular e, a partir dali: destravar
o telefone, abrir o notebook, VPN, `/malha`, achar a malha na lista, trocar o
modo, escolher a data)*. `montar_card` (`dags/utils/ds_teams.py:57`) ganha
`actions: [{"type": "Action.OpenUrl", …}]` para os tipos `MALHA_*`, apontando para
`/malha?malha={m}&modo=execucao&corrida={id}` — **a URL que a própria §9.9 está
criando**. O molde literal já existe no gerador de DAG
(`dags/etl_dag_factory.py:1049-1051`). Base em `etl_app_config.app_base_url`
(config nova); **sem ela configurada, o card sai exatamente como hoje, sem
botão** — degradação por ausência, nunca URL inventada.

**Decisão 70 — o Dashboard ganha a corrida na forma mínima, e o link quebrado que
já existe é consertado junto** *(evita: manter cega a tela em que o plantonista
de fato cai. O Dashboard já tem "Rodando agora" e "Aguardando dependência" com
refetch de 60 s, e o link de dependência faz `navigate('/malha')` sem malha e sem
modo (`Dashboard.tsx:499`), despejando o operador na lista)*. Forma mínima: uma
linha por corrida `ABERTA`/`FALHA`, com `CorridaBadge` + `x de y` + link direto —
mesmo payload da lista, **zero consulta nova**.

⚠️ **Defeito pré-existente que esta camada não pode herdar em silêncio:** a barra
de "Rodando agora" (`Dashboard.tsx:438`, `pct = jobs_ok / total_jobs`) está em
**0% desde sempre**. O backend monta a CTE com `WHERE status='RUNNING'` e, dentro
dela, `SUM(CASE WHEN status='SUCCESS' …) AS jobs_ok` sobre um conjunto onde toda
linha é `RUNNING` (`api/routers/dashboard.py:202-210`): `jobs_ok` é sempre 0 e
`total_jobs == jobs_running`. A tela mais vista do produto exibe `0/3 ok` para um
pipeline com 2 jobs concluídos — card que mente, já em produção. **A correção da
agregação (rollup pelo `execution_id` inteiro, sem o filtro de status dentro do
CTE) sai na mesma PR que extrai `ui/Progress`**, porque é o molde que esta camada
ia copiar.

### 9.9 Componentes — arquivo, props, estados

**Decisão 71 — só se promove para `ui/` o que tem CHAMADOR PROVADO, e não se
inventa estado sem chamador** *(evita: os dois erros opostos — deixar em
`MalhaEditor.tsx` a décima cópia literal das mesmas classes de banner, e criar um
componente genérico com modos que ninguém usa)*.

#### Novos em `ui/` — **novos, com justificativa medida**

`ui-react/src/components/ui/Progress.tsx` — **novo**

```ts
export interface SegmentoProgresso {
  chave: string          // 'ok' | 'vivo' | 'dispensado' — usado em key e no aria-label
  valor: number
  cor: string            // classe Tailwind, par claro+escuro obrigatorio
  rotulo: string         // pt-BR, entra no title e no aria-label
  animado?: boolean
  hachurado?: boolean    // so 'dispensado'
}
export interface ProgressProps {
  segmentos: SegmentoProgresso[]
  total: number                    // sempre membros_total (Decisao 52)
  altura?: 'xs' | 'sm'             // xs = card (h-1.5), sm = painel (h-2.5)
  ariaLabel: string                // obrigatorio
}
```

*Por que criar:* existem **4 barras ad-hoc** (`CopiaProgressoModal.tsx:125`,
`Dashboard.tsx:448`, `PlanosAjuste.tsx:36`, `Admin.tsx:2064`), **nenhuma** com
`role="progressbar"`/`aria-valuenow`, e **nenhuma** segmentada. Trilho canônico
mantido: `bg-edge/60 rounded-full overflow-hidden` + preenchimento com
`transition-all`. **Sem** modo `indeterminado` e **sem** modo `total === 0`: nesta
camada a barra só existe com `corrida`, que sempre traz `membros_total`, e
`SEM_TRABALHO` não renderiza barra nenhuma (Decisão 57) — modo sem chamador é
código que nasce sem teste.

`ui-react/src/components/ui/Banner.tsx` — **novo (promoção)**

```ts
{ tom: 'info' | 'alerta' | 'erro' | 'sucesso'; icone?: ReactNode; acao?: ReactNode; children }
```

Extrai o `Banner` de `components/etapas/PainelExecucaoEtapas.tsx:252-268` e
acrescenta o tom `sucesso`. *Por que criar:* o `MalhaEditor` tem **nove** cópias
literais das mesmas classes (`:2037`, `:2074`, `:2104`, `:2116`, `:2130`, `:2177`,
`:2191`, `:2200`, `:2214`) e esta camada acrescentaria mais três. Nove cópias é o
ponto em que a duplicação vira risco de regressão de tema.

`ui-react/src/components/ui/Tabs.tsx` — **alterado**: ganha
`badgeTom?: 'neutro' | 'alerta'`. Hoje **todo** badge é vermelho
(`Tabs.tsx:26-28`: `bg-red-100 text-red-700`), então `Agora (2)` — dois pipelines
saudáveis rodando — sairia gritando "2 problemas". `Agora` é neutro, `Travando` é
alerta.

#### Novos em `components/malhas/`

| Arquivo (todos **novos**) | Props | Estados |
|---|---|---|
| `CorridaBadge.tsx` | `{ corrida: CorridaApi \| null; esperada?: CorridaEsperadaApi \| null; tamanho?: 'sm'\|'md' }` | 7 status × 4 saúdes + `nao_abriu` (§9.3); **degradado**: `corrida = null` e `esperada = null` → não renderiza (o fallback é do chamador) |
| `CorridaProgresso.tsx` | `{ corrida: CorridaApi; variante: 'card'\|'painel' }` | **normal** · **fechando** (D56) · **congelado** (`opacity-60` + "parou em") · **sem trabalho** (sem barra, traço + frase) · **snapshot vazio** (`membros_total === 0` → "a corrida abriu sem membros ativos", âmbar) |
| `CabecalhoCorrida.tsx` | `{ corrida, esperada, malha, onEncerrar, onAbrirAba }` | **carregando** (`ui/Skeleton` de 1 linha, altura fixa — a faixa não pode saltar) · **normal** · **ausente** (`!corrida` → faixa neutra + explicação) · **degradado** (Decisão 41) |
| `PainelCorridaLateral.tsx` | `{ corrida, execucoes, tipicos, eventos, eventosNo, onFocar, onAbrirEtapas }` | 3 abas com default por saúde (D62), cada uma com **vazio explícito**: *"nenhum pipeline em execução agora"* · *"nada travando — os pendentes estão em dia"* · *"nenhum evento nesta corrida"* |
| `RelogioCorrida.tsx` | `{ aberta_em, fechada_em, apurado_em, teto_em, teto_configurado, quiescencia_ate, ultimo_movimento_em, proximoGatilho }` | **em voo** · **fora do prazo** · **fechando** (D45) · **fechada** (`01:10 → 04:02 · 2h52`) · **sem teto configurado** (só o próximo gatilho, D61) |
| `SeletorCorrida.tsx` | `{ malha, corridaId, onTrocar }` | faixa das últimas N clicável + menu (`ir para uma data…`); **1 corrida** → faixa de um bloco, sem controles mortos; **erro** → cai no seletor de data de hoje |
| `tempoCorrida.ts` | módulo puro + `useDecorrido(...)` à parte | Decisão 60; testado com relógio deslocado |

#### Alterados

| Arquivo | Alteração |
|---|---|
| `malhas/statusExecucao.ts` | `STATUS_CORRIDA` **paralelo** (D46) + `SAUDE_CORRIDA` + `estiloCorrida(status, saude)` + `ORDEM_LEGENDA_CORRIDA`; `estiloEvento` (`:142`) ganha os tipos `MALHA_*` (D47); interfaces `CorridaApi` / `CorridaEsperadaApi` no contrato |
| `malhas/fluxoExecucao.ts` | novo estado **`'esperando'`** (âmbar tracejado) para `AGUARDANDO_DEPENDENCIA` — hoje `estadoDoPipeline` devolve `null` (`:29-35`) e a linha fica **idêntica a "não rodou"**; e `ROTULO_FLUXO` (`:127`), hoje **declarado e nunca consumido em lugar nenhum do front** (verificado), passa a alimentar o `title` da aresta e a legenda |
| `malhas/MalhaComponenteNodes.tsx` | nó **Fim** ganha o terceiro estado "ciclo aberto" (hoje `:176-177` é verde ou nada): **anel azul + `title`**, sem texto no nó |
| `malhas/MalhaEditor.tsx` | `CabecalhoCorrida`; painel lateral → `PainelCorridaLateral`; `SeletorCorrida` no lugar do navegador de data; `Segurar/Soltar` **também** no modo Execução (`:2461-2486`); banners da D66; texto de fase antiga removido (`:2205-2206`) |
| `pages/Malha.tsx` | bloco de corrida no card (substitui a linha `▶ última execução`, `:187-201`); `Acompanhar` como ação; filtro por estado de corrida; contadores na stats bar (`:670`+); polling condicional; textos "chega na F8" removidos (`:450`, `:707`) |
| `pages/Dashboard.tsx` + `api/routers/dashboard.py` | linha de corrida; link de dependência com malha e modo (`:499`); **correção do `jobs_ok`** (§9.8) |
| `components/malhas/proximaExecucao.ts` | **exceção nominal à §13**: passa a alimentar `corrida_esperada` (D58) e o prazo do próximo gatilho (D61) |
| `dags/utils/ds_teams.py` | `Action.OpenUrl` nos `MALHA_*` (D69) |
| `types/index.ts` | `CorridaApi`, `CorridaEsperadaApi` no `ApiMalha` e no `MalhaExecucaoApi` |

#### Intocados, de propósito

`MalhaPipelineNode.tsx` — a §13 já o lista, e a razão fica registrada aqui: ele
já carrega dot, nome, `CritBadge`, agenda, chip republicar, badge de status e
badge de contradição; **duração e classe por membro vivem no painel lateral**.
`componenteMeta.ts`, `AgendamentoInicioModal.tsx`, `CritBadge.tsx`,
`layoutGrafo.ts`.

**Decisão 72 — `Acompanhar` existe SEMPRE, e as posições dos botões do card são
FIXAS** *(evita: dois defeitos de bancada — (i) o interruptor `malha_corrida_ativa`
nasce em `0` (§11.2), então no dia do deploy **nenhuma** malha tem `corrida` e um
botão que só existe com corrida deixa a fase **não testável**; e às 8h, quando não
há corrida aberta nenhuma, o primário voltaria a ser `Diagrama`, que é a tela de
**montagem**; (ii) botões que mudam de posição entre estados — clicar "Diagrama" no
card 1 e acertar "Membros" no card 2)*. `Acompanhar` leva à lente de execução da
data corrente, que **já funciona hoje**; com corrida, acrescenta `&corrida=N` e o
destaque de primário. Posição fixa, desabilitar em vez de remover ou reordenar.

### 9.10 Cadência e frescor

**Decisão 73 — o polling é CONDICIONAL, e o painel só sobe de frequência DEPOIS
que o N+1 sai** *(evita: dobrar a frequência de um endpoint que ainda faz
`deps_svc.liberado()` por membro esperando (`api/routers/malhas.py:2231`, 2
round-trips × membro) — numa malha de 40 membros, durante um incidente, é o pior
ordenamento possível)*.

| Superfície | Hoje | Decisão |
|---|---|---|
| Lista `/malha` | **sem polling** (`Malha.tsx:560-563`) | `refetchInterval` condicional: `20_000` se alguma malha **visível** tem corrida `ABERTA` ou está `nao_abriu`; senão `false` |
| Painel `/execucao` | `30_000` fixo (`MalhaEditor.tsx:695`) | **continua 30 s** até o `pendentes[]` agregado entrar; **com ele**, `15_000` com corrida `ABERTA` e `60_000` com corrida fechada (histórico não muda) |
| Frescor | só o spinner de `isFetching` | `· atualizado agora / há 3 min`, **um por página** (Decisão 60) |

**O que a corrida também corrige de custo:** a lente deixa de ser
`WHERE data_referencia = ?` (`malhas.py:2203`, **sem índice**, varredura do
histórico inteiro a cada 30 s por painel aberto — hoje invisível porque a tabela
tem 0 linhas no dev) e passa a ser `malha_execucao_id` sobre o `ix_pipe_exec_malha`
filtrado.

### 9.11 O vocabulário, e a acessibilidade que cabe agora

**Decisão 74 — uma palavra por conceito, em português, e nenhum nome de máquina
na interface** *(evita: o relatório da reunião herdar o vocabulário do motor —
"a malha expirou por quiescência com 2 membros dispensados" não é uma frase que
alguém leve para uma reunião, e "corrida" no painel com "ciclo" no nó Fim e
"Corridas" no menu são três palavras para a mesma coisa na mesma tela)*.

| Está no modelo | **Escrever na tela** |
|---|---|
| corrida / ciclo (as duas) | **corrida** — uma só, em todo lugar |
| `#12` / `sequencia` / `id` | `corrida de 04/08`; e **só se `sequencia > 1`**, `2ª corrida de 04/08`. **`#` não aparece na interface** — hoje três numerações diferentes disputam essa notação (`id`, `sequencia`, `aberta_por='inicio:#12'`), e `#12` numa malha diária lê-se como "12ª tentativa hoje" |
| quiescência | *"fecha 15 min após o último movimento"* |
| teto / `teto_em` | *"limite de segurança (24h)"* |
| guardiã | *"o monitor automático"* |
| dispensado / `PULADO` | *"não roda hoje (regra de dia)"* |
| `nao_liberou` | *"esperando outro pipeline"* |
| `nao_partiu` | *"não chegou a iniciar"* |
| `orfa` | *"terminou sem registrar o fim"* |
| `fora_do_odate` | *"de outra data de referência"* |
| `ABORTADA` | *"não chegou a começar"* |
| `EXPIRADA` | *"encerrada sem terminar"* |
| `tentativas = 1` | *"não foi reaberta"* / `reaberta 1x por C123456` |
| `MALHA_ATRASADA` | *"aviso de atraso enviado ao Teams às 01:12"* |
| `modo_fechamento = quiescencia` | *"fecha sozinha, sem nó Fim (normal nesta malha)"* |
| membro | *"pipeline da malha"* |
| ATRASADA (saúde) × EXPIRADA (ciclo) | eixo de prazo em pt-BR: **`no prazo` / `fora do prazo`** (saúde) e **`encerrada sem terminar`** (desfecho). ⚠️ A ambiguidade é real e vaza para o Teams: `ATRASADA` aparece como **estado** no pedido do usuário e como **saúde** no §6.1. Esta é a resolução, e ela vale nas duas superfícies e no card do celular |

Aceite verificável: `grep -nE 'quiesc|ODATE|dispensad|teto|guardiã|órfã|#[0-9]'`
nos `.tsx` da malha não casa **texto exibido** (casar em comentário e em nome de
variável é esperado).

**Decisão 75 — a acessibilidade que entra é a barata e correta; a região viva
fica em backlog nomeado** *(evita: escrever uma máquina de estados de `aria-live`
— com trava de re-render por `status`/`saude`/`membros_ok` para o leitor não falar
a cada 15 s — sendo que o front **não tem um único `aria-live`** hoje e o plantão
da Caixa não usa leitor de tela: seria a peça mais sujeita a bug servindo a
ninguém no dia 1)*.

Entra agora:

- `Progress` com `role="progressbar" aria-valuenow aria-valuemin=0 aria-valuemax`
  + `aria-label` em pt-BR — **as 4 barras existentes não têm nenhum dos dois**;
- todo contador clicável é `<button>` com `aria-pressed` quando age como filtro
  (molde de `PainelRealce.tsx:100,120`);
- `SeletorCorrida` com `aria-label` nos controles — o navegador de data da malha
  **não tem**, e o gêmeo de `PainelExecucaoEtapas.tsx:133` tem;
- `animate-pulse` continua **semântico e escasso**: só o segmento `vivo` da barra,
  o dot de `ABERTA` e a aresta ativa que já existe. Nada mais.

Fica em backlog (§17): região `aria-live="polite"` anunciando **mudança de fato**
(`status`, `saude` ou o inteiro `membros_ok`), nunca tique de relógio.

### 9.12 ASCII — o card da lista

Legenda dos blocos: `█` feito · `▒` rodando (azul, animado) · `▨` não roda hoje
(trilho hachurado neutro) · `░` ainda não feito.

**Em andamento, saúde OK**

```
┌────────────────────────────────────────────────────────┐
│ ● CARGA_DIARIA_SEGUROS                 [ALTA]  ● Ativa │
│ Consolidação diária das apólices e sinistros           │
│ ⚙ 7 pipelines (7 ativos) · 41 etapas                   │
│ 🕒 gatilho: todo dia 01:00 (nó Início)                 │
│ ┌────────────────────────────────────────────────────┐ │
│ │ ◉ em andamento · corrida de 04/08 · há 42 min      │ │
│ │ ████████████▒▒▒▒▒▒░░░░░░▨▨▨▨          4 de 7       │ │
│ │ 7 membros nesta corrida · 1 não roda hoje          │ │
│ │ ↳ 2 rodando (mais antigo há 12 min)                │ │
│ └────────────────────────────────────────────────────┘ │
│ 📅 criada em 12/06/2026                                │
│ [ ▶ Acompanhar ] [ Diagrama ] [ Membros ] [ ⋯ ]        │
└────────────────────────────────────────────────────────┘
   ◉ = dot azul animate-pulse. Sem "%", sem "#12".
```

**Concluída**

```
│ ┌────────────────────────────────────────────────────┐ │
│ │ ✔ concluída · corrida de 04/08 · 01:10 → 04:02     │ │
│ │ ██████████████████████████████▨▨▨▨    6 de 7       │ │
│ │ 7 membros nesta corrida · 1 não roda hoje          │ │
│ │ ↳ falhou 2 das últimas 7 corridas                  │ │
│ └────────────────────────────────────────────────────┘ │
   Duração absoluta (fechada) · "concluída" so com status do banco.
```

**Com falha, corrida ainda aberta — o defeito relatado, corrigido**

```
│ ┌────────────────────────────────────────────────────┐ │
│ │ ▲ em andamento · com falha (ainda rodando)         │ │
│ │   corrida de 04/08 · há 42 min                     │ │
│ │ ████████▒▒▒▒▒▒░░░░░░░░░░░░░░  3 de 7   ▲ 1 travado │ │
│ │ 7 membros nesta corrida                            │ │
│ │ ↳ falhou: CARGA_A [ALTA] · 4 pipelines parados     │ │
│ └────────────────────────────────────────────────────┘ │
   O travado NAO engorda a barra: chip vermelho ao lado (D54).
   Hoje esta mesma corrida diz "● sucesso · CARGA_B".
```

**Fora do prazo (limite vencido, ainda com trabalho vivo)**

```
│ ┌────────────────────────────────────────────────────┐ │
│ │ ⏰ em andamento · fora do prazo · corrida de 03/08 │ │
│ │   há 25h 14min                                     │ │
│ │ ████████▒▒▒▒░░░░░░░░░░░░░░░░  3 de 7   ▲ 2 travados│ │
│ │ ↳ a próxima corrida parte em 2h50 (01:00) —        │ │
│ │   enquanto esta não fechar, ela não abre           │ │
│ └────────────────────────────────────────────────────┘ │
   Limite vencido COM trabalho vivo e alarme, nao desfecho (D25).
   O prazo exibido e o PROXIMO GATILHO, nao o limite tecnico (D61).
```

**Sem trabalho hoje (sábado legítimo)**

```
│ ┌────────────────────────────────────────────────────┐ │
│ │ ☾ sem trabalho hoje · corrida de 09/08             │ │
│ │ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─    nada previsto         │ │
│ │ os 7 membros não rodam hoje (regra de dia)         │ │
│ └────────────────────────────────────────────────────┘ │
   Sem barra. Nem 0, nem 7 de 7 (D57). Cinza e mudo.
```

**Sem trabalho num dia ATÍPICO (D68) — o mesmo estado, outra cor**

```
│ ┌────────────────────────────────────────────────────┐ │
│ │ ⚠ sem trabalho hoje · corrida de 05/08 (terça)     │ │
│ │ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─    nada previsto         │ │
│ │ ↳ as últimas 4 terças tiveram trabalho             │ │
│ └────────────────────────────────────────────────────┘ │
   Ambar: e o unico jeito de a tela pegar membros inativados por engano.
```

**Encerrada pelo operador (auditoria, D67)**

```
│ ┌────────────────────────────────────────────────────┐ │
│ │ ⊘ encerrada por C123456 às 05:20                   │ │
│ │ ▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░  parou em 4 de 7        │ │
│ │ motivo: "carga do dia 03 remarcada para a tarde"   │ │
│ └────────────────────────────────────────────────────┘ │
   Ambar de contorno, nao cinza: e acao humana, e ela precisa
   ser explicavel no fechamento do mes. Barra congelada, opacity-60.
```

**Não abriu (D58) — a pior notícia da manhã, e o card que hoje não existe**

```
│ ┌────────────────────────────────────────────────────┐ │
│ │ ⏰ não abriu · previsto para 01:00 · já são 08:12  │ │
│ │ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   nenhuma corrida de 04/08     │ │
│ │ ↳ anterior: 03/08 · concluída · 01:10 → 04:02      │ │
│ └────────────────────────────────────────────────────┘ │
   Ordena PRIMEIRO na lista. Sem isto, o card mostraria a
   corrida de ONTEM, verde, com carimbo de frescor recente.
```

**Degradado — API velha ou 085 ausente (D41)**

```
│ ┌────────────────────────────────────────────────────┐ │
│ │ ▶ última execução: 03/08 13:47  ● sucesso          │ │
│ │   (membro mais recente — CARGA_B)                  │ │
│ │ ⚠ sem dados de corrida — sistema em atualização    │ │
│ └────────────────────────────────────────────────────┘ │
   Sem barra, sem data de corrida, e a palavra "concluída"
   nao aparece. A degradacao e DITA, nao so silenciosa.
```

### 9.13 ASCII — o cabeçalho do painel de execução

Zonas, ordem fixa: **identidade/estado · progresso · relógio/prazo · travas**.

**Em andamento**

```
┌ Montagem │ ▓EXECUÇÃO▓ ───────────────────────────────────────────────────────────┐
│ faixa das últimas corridas:  ▉▉ ▉▉ ▉▉ ▉▉ ▉▉ ▉▉ ▉▉ ▉▉ ▉▉ [▉▉]      ⌄ ir para…     │
├──────────────────────────────────────────────────────────────────────────────────┤
│ ◉ EM ANDAMENTO            ████████████▒▒▒▒▒▒░░░░▨▨    4 de 7 pipelines concluídos│
│ corrida de 04/08          7 membros nesta corrida · 1 não roda hoje              │
│ aberta pelo agendamento   aberta 01:10 · há 42 min                               │
│ do Início (CARGA_RAIZ)    a próxima corrida parte em 2h50 (01:00) —              │
│ às 01:10 · não foi        enquanto esta não fechar, ela não abre                 │
│ reaberta · fecha sozinha  2 rodando · 1 não chegou a iniciar    [ Encerrar… ]    │
│ 15 min após o último mov.                                                        │
└───────────────────────────────────────────────────── · atualizado agora ─────────┘
┌───────────────┬──────────────────────────────────────────────────────────────────┐
│ Agora (2) │ Travando │ Eventos (3)          [ canvas ]                           │
├───────────────┤                                                                  │
│ ◉ CARGA_B     │   (Início)──▶(CARGA_A ✔)──▶(CARGA_B ◉)──▶(Aguarde)──▶(Fim ◐)     │
│   há 12 min   │                  │                                               │
│   típico 18   │             (CARGA_D ◉)                                          │
│   min (n=23)  │                                                                  │
│   [▶ etapas]  │   Fim com anel azul = corrida aberta (sem texto no nó)           │
│ ◉ CARGA_D     │                                                                  │
│   há 3 min    │                                                                  │
│   [▶ etapas]  │                                                                  │
└───────────────┴──────────────────────────────────────────────────────────────────┘
   Aba default = Agora, porque a saúde é OK (D62).
```

**Com falha — aba default vira `Travando`**

```
│ ▲ COM FALHA (ainda      █████████▒▒▒▒░░░░░░░░░  3 de 7 pipelines concluídos     │
│   rodando)              7 membros nesta corrida            ▲ 2 travados         │
│ corrida de 04/08        aberta 01:10 · há 3h50                                  │
│ aberta pelo agendamento a próxima corrida parte em 2h50 (01:00)                 │
│ do Início às 01:10      aviso de falha enviado ao Teams às 03:12                │
│                         2 rodando · 2 travados              [ Encerrar… ]       │
└──────────────────────────────────────────────────── · atualizado há 1 min ──────┘
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Agora (2) │ ▓Travando (2)▓ │ Eventos (5)        ← ABERTA AQUI (D62)             │
├─────────────────────────────────────────────────────────────────────────────────┤
│ ▲ CARGA_A [ALTA]   falhou 03:07 · 4 pipelines parados atrás                     │
│                    [▶ etapas]  [↻ reexecutar]  [🔍 realçar cadeia]              │
│ ◐ CARGA_C          esperando CARGA_A desde 03:07                                │
│                    [🔍 realçar]                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
   "3 pendentes" NUNCA aparece: sao problemas com donos diferentes (D21/D63).
   [↻ reexecutar] abre a previa dizendo o efeito na corrida em voo (D65).
```

**Concluída**

```
│ ✔ CONCLUÍDA             ██████████████████████████▨▨  6 de 7 concluídos         │
│ corrida de 04/08        7 membros nesta corrida · 1 não roda hoje               │
│ aberta pelo agendamento 01:10 → 04:02 · 2h52                                    │
│ do Início · fechada     dentro do limite de segurança (24h)                     │
│ pelo nó Fim             corrida anterior: 03/08 · concluída · 01:10 → 04:02     │
└──────────────────────────────────────────────────── · atualizado há 1 min ──────┘
   Aba default = Eventos (corrida fechada). Nada anima.
```

**Sem trabalho hoje**

```
│ ☾ SEM TRABALHO HOJE     ─ ─ ─ ─ ─ ─ ─ ─ ─ ─    nada previsto                    │
│ corrida de 09/08        os 7 membros não rodam hoje (regra de dia)              │
│ aberta pelo agendamento 01:00 → 01:02 · 2 min                                   │
│ do Início às 01:00      fechada de imediato pelo monitor automático             │
│                         sem aviso — não é incidente                             │
└──────────────────────────────────────────────────── · atualizado há 2 min ──────┘
```

**Fora do prazo, com banner de data divergente (D66)**

```
│ ⚠ 2 pipelines de outra data de referência: CARGA_X, CARGA_Y                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│ ⏰ FORA DO PRAZO        ████████▒▒▒░░░░░░░░░░░  3 de 7 concluídos               │
│ corrida de 03/08        7 membros nesta corrida             ▲ 2 travados        │
│ aberta 03/08 às 01:10   há 25h 14min                                            │
│ · não foi reaberta      limite ▉▉▉▉▉▉▉▉▉▉▉▉▉▉▉▉▉▉▉█ vencido (24h configuradas)  │
│                         a próxima corrida parte em 2h50 (01:00) —               │
│                         enquanto esta não fechar, ela não abre                  │
│                         1 rodando · 2 travados              [ Encerrar… ]       │
└──────────────────────────────────────────────────── · atualizado agora ─────────┘
   A barra de limite so aparece porque etl_malha.teto_horas foi
   configurado NESTA malha (D61). Sem isso, so a linha do gatilho.
```

**Não abriu (D58) — a faixa quando não há corrida**

```
│ ⏰ NÃO ABRIU            ─ ─ ─ ─ ─ ─ ─ ─ ─    nenhuma corrida de 04/08           │
│ previsto para 01:00     já são 08:12 · 7h12 de atraso                           │
│ (nó Início)             corrida anterior: 03/08 · concluída · 01:10 → 04:02     │
│                         [ Disparar malha… ]   [ ver a DAG do Início ]           │
└──────────────────────────────────────────────────── · atualizado agora ─────────┘
```

### 9.14 Os eventos e o Teams

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

A partição de cor do Teams e a do painel são **a mesma** (Decisão 59): o painel
não pode discordar do celular.

**Decisão 48 — falha notifica SEMPRE; sucesso é que é opt-in** *(evita: o
`MALHA_FALHOU` herdar o opt-in de hoje e a malha falhar **em silêncio** para quem
nunca ligou a config — que é a maioria)*. O `detalhe` do evento **nomeia malha,
corrida (pela data) e os pendentes com a classe** — é o corpo do card e é a única
coisa que se lê no celular. E, com a Decisão 69, o card leva o **botão** para a
tela desta corrida.

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

E a coluna `notificado_em` (`067:189`), que **existe e nunca foi lida**, passa a
alimentar duas coisas: a linha `avisados às 03:12 · Teams` na aba `Eventos`, e o
banner vermelho da Decisão 66 quando a notificação está presa na fila.

### 9.15 O que NÃO fazer

**Decisão 75 (continuação) — a lista de proibições desta camada**, cada uma com o
defeito que ela evita:

1. **Nada de donut, gauge ou anel de progresso circular** — a legenda inteira da
   malha é baseada em `dot` circular; um anel de progresso colidiria com
   "bolinha = status". A linguagem da casa é **barra + dot + texto**.
2. **Não introduzir `recharts`** (está no `package.json`, usado **só** na POC
   Caixa Seguro). Numa tela 100% CSS/React Flow custa bundle e cria um segundo
   dialeto visual. A faixa de histórico é bloco colorido em CSS.
3. **Não prometer ETA de conclusão da corrida.** Não há coluna de duração
   esperada e o §3 proíbe backfill. O que entra é a **duração típica por membro**,
   medida, com `n` (Decisão 64) — que é outra coisa.
4. **Não exibir `%`** (Decisão 56). E nunca `x de y` sem a linha da subtração
   logo abaixo (Decisão 53).
5. **Não derivar progresso no cliente a partir de `execucoes[]`** — é o caminho
   para card e painel discordarem na mesma tela. Um agregado, uma fonte.
6. **Não contar como OK linha com `substituida_em IS NOT NULL`** (Decisão 55).
7. **Não calcular decorrido com `Date.now() − aberta_em`**, nem frescor com
   `Date.now() − apurado_em` (Decisão 60). 3 h de desvio medidas no dev.
8. **Não buscar % de etapas no refetch** — 1 HTTP por pipeline + Airflow por
   run_id `dep__` a cada 15 s derruba o painel exatamente quando a malha é grande
   e o incidente é real.
9. **Não ligar polling incondicional na lista** (Decisão 73).
10. **Não somar estados distintos para "simplificar"** — `falhou`,
    `nao_liberou`, `nao_partiu` e `orfa` **nunca** viram "3 pendentes": são três
    donos diferentes (Decisão 21). Precedente literal:
    `PainelExecucaoEtapas.tsx:104-107` mantém "em espera" e "pausa marcada"
    separados de propósito.
11. **Não acrescentar badge ao `MalhaPipelineNode`** nem texto ao nó Fim — o
    número já está na faixa a 3 cm.
12. **Não pôr os estados de corrida na legenda do rodapé** — estado de corrida é
    **escrito por extenso** na faixa.
13. **Não animar mais nada** além do segmento `vivo`, do dot de `ABERTA` e da
    aresta ativa que já existe (`fluxoExecucao.ts:102`: *"animação em tudo viraria
    ruído e o olho perderia a frente da corrida"*).
14. **Não usar `bg-{hue}-900/20` ou `text-{hue}-300` como classe base**
    (`docs/ui-temas-cores.md:63-82`). Todo par claro+escuro, tokens
    `canvas/panel/edge/ink/dim` para superfície.
15. **Não escrever "concluída" sem `status = 'CONCLUIDA'` vindo do banco**
    (Decisão 41).
16. **Não usar hachura para dois significados.** Hachura é **uma** coisa nesta
    camada: `não roda hoje`. Corrida congelada usa `opacity-60` + a palavra
    "parou em".
17. **Não criar quatro mecanismos de navegação temporal** (Decisão 42).
18. **Não criar botão que cicla entre os vivos** — com 2 vira toggle sem estado
    visível, com 8 perde-se a conta. A aba `Agora` já centraliza.

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
  `GET /malhas/{m}/corridas`; (o `DELETE /malhas/{m}` da borda 14 **não existe** —
  verificado na execução da F3; malha se inativa, não se exclui);
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
  - ~~`DELETE` da malha com corrida aberta~~ — **removido do aceite**: não há
    rota de exclusão de malha (verificado na F3). O gesto equivalente é o
    `PATCH ativo=0`, que já está no aceite acima;
  - Finalização Manual fecha linha órfã → a corrida é reavaliada **no mesmo
    gesto**, sem esperar 5 min.
- **PR:** `feat: rerun reabre a corrida e o desenho editado vale do proximo ciclo`

### F4+ — Os quatro aditivos de VERACIDADE (entram na PR da F4; não são fase nova)

Não é uma fase: são quatro itens do §9 que **não podem esperar** a camada de
visibilidade, porque sem eles a camada nasce mentindo — e porque três deles são
correções de consultas que a própria F4 escreve. Se a F4 já tiver sido mergeada
quando esta seção for executada, viram a primeira PR da F9.

- **Entregável:**
  1. `substituida_em IS NULL` no numerador **e** no `SELECT` de
     `GET /malhas/{m}/execucao` (`api/routers/malhas.py:2203-2210`) — Decisão 55;
  2. denominador = `membros_total` do snapshot, que **não encolhe**, com
     `membros_dispensados` como classe separada no payload — Decisão 52;
  3. `membros_travados` como campo próprio, **fora** do que a barra preenche —
     Decisão 54;
  4. frescor derivado do **relógio local** (Decisão 60), com `apurado_em`
     restrito ao texto absoluto do tooltip.
- **Deploy:** `api/` + front. **Não** exige `force_all`.
- **Aceite:**
  - rerun às 3h de um membro já concluído → a faixa e o **nó no canvas** contam a
    MESMA linha; sem a cláusula, o nó fica verde com a linha aposentada e a faixa
    diz outro número (o teste é a comparação dos dois na mesma tela);
  - corrida de 7 membros, 2 concluídos; a guardiã marca 3 `PULADO` no ciclo
    seguinte → o card continua dizendo **`2 de 7`** (nunca `2 de 4`), e a linha de
    baixo passa a dizer `3 não rodam hoje`;
  - `CARGA_A` em falha numa malha de 7 com 3 OK → a barra preenche **3/7**, e o
    travado aparece como **chip fora da barra**;
  - relógio do banco deslocado 3 h do navegador → o carimbo de frescor diz
    `agora`, nunca `há -3h`, e o alarme de dado velho dispara aos 90 s (teste com
    relógio deslocado, mesmo molde de `test_malha_corrida_relogio.py`).
- **PR:** `fix: a corrida conta a linha viva e o denominador nao encolhe`

### F9 — O card responde "em que pé está" (e a corrida que NÃO abriu)

- **Entregável:** `ui/Progress` (**novo**, com `role="progressbar"`) e `ui/Banner`
  (**novo**, promoção de `PainelExecucaoEtapas.tsx:252-268`); `ui/Tabs` com
  `badgeTom`; `STATUS_CORRIDA` + `SAUDE_CORRIDA` + `estiloCorrida` em
  `statusExecucao.ts`; `CorridaBadge.tsx`, `CorridaProgresso.tsx`,
  `tempoCorrida.ts` (**novos**); o bloco de corrida no card de `Malha.tsx`
  (substitui a linha `▶ última execução`, `:187-201`); aditivos de payload do
  §9.1 (mesmo `GROUP BY`); `corrida_esperada` calculada **na API** com
  `agora_do_banco` (Decisão 58); nó Fim com anel de "ciclo aberto" (sem texto);
  `Acompanhar` presente sempre (Decisão 72); e a **correção do `jobs_ok` do
  Dashboard** (`api/routers/dashboard.py:202-210`) na mesma PR que extrai
  `ui/Progress`, porque é o molde que esta camada copiaria.
- **Deploy:** `api/` + front (`dist/` commitada). **Não** exige `force_all`.
- **Aceite:**
  - sábado com todos os membros dispensados → **nenhuma barra**, texto "nada
    previsto", e a palavra "concluída" **ausente** (teste de ausência);
  - corrida `ABERTA` com `ok === total − dispensados` → barra cheia, rótulo
    `7 de 7 · fechando — fecha 15 min após o último movimento; se nada mais mexer,
    por volta de 04:17`, e **nem "100%" nem "concluída"** em lugar nenhum;
  - `grep -rn '%' ` nos componentes de corrida não casa nenhum percentual
    **exibido** (Decisão 56), e `grep -nE '#[0-9]'` não casa texto de interface
    (Decisão 74);
  - `EXPIRADA` e `CANCELADA` → barra congelada com `opacity-60` e o rótulo
    **"parou em 4 de 7"**; `CANCELADA` mostra **quem** encerrou e o **motivo**
    (Decisão 67);
  - DAG do Início pausada, horário previsto vencido, nenhuma corrida com o ODATE
    do dia → card **`não abriu`**, âmbar, **primeiro** na ordenação da lista; com
    o relógio do banco deslocado 3 h, o atraso exibido continua correto (o cálculo
    é da API, Decisão 58);
  - **front novo × API velha** (payload sem `corrida`) → card com "(membro mais
    recente)" **e** a linha `⚠ sem dados de corrida — sistema em atualização`,
    zero exceção no console;
  - com o interruptor `malha_corrida_ativa = 0` (o estado do dia do deploy) →
    `Acompanhar` **existe e funciona**, levando à lente de execução da data
    corrente — a fase é testável sem nenhuma corrida no banco;
  - Dashboard: pipeline com 2 de 3 jobs concluídos deixa de exibir `0/3 ok`;
  - `axe`/inspeção manual: a barra tem `role="progressbar"`, `aria-valuenow`,
    `aria-valuemax` e `aria-label` em pt-BR — as 4 barras existentes não têm
    nenhum dos dois;
  - tsc + eslint com **baseline HEAD** (zero NOVOS) e build com `dist/`.
- **PR:** `feat: o card da malha mostra o progresso da corrida`

### F10 — A faixa de corrida e o painel que responde "o que está travando"

- **Entregável:** `CabecalhoCorrida.tsx`, `RelogioCorrida.tsx`,
  `PainelCorridaLateral.tsx` (3 abas, default por saúde — Decisão 62),
  `SeletorCorrida.tsx` (**novos**); `pendentes[]` **agregado no servidor**,
  tirando o `deps_svc.liberado()` por membro do caminho corrente
  (`api/routers/malhas.py:2231`); `Encerrar corrida…` em toda corrida `ABERTA`,
  com a consequência escrita na confirmação; os três banners da Decisão 66
  (`fora_do_odate`, hold com contador e `Soltar`, notificação presa);
  `Segurar/Soltar` também no modo Execução; raio de alcance + criticidade por
  travado (Decisão 63); `↻ reexecutar` com a frase do efeito (Decisão 65);
  `fluxoExecucao.ts` com o estado `esperando` e `ROTULO_FLUXO` **ligado** no
  `title` da aresta e na legenda; `estiloEvento` com os tipos `MALHA_*`;
  `refetchInterval` do painel só então em `15_000` (Decisão 73).
- **Deploy:** `api/` + front. **Não** exige `force_all`.
- **Aceite:**
  - painel de uma malha com 40 membros, 12 esperando → **uma** consulta de
    conjunto para os pendentes (medida no log de SQL), nunca 24 round-trips;
  - o `refetchInterval` só vai a `15_000` na mesma PR do agregado — teste de
    ordenamento: com o N+1 ainda no caminho, o intervalo continua `30_000`;
  - corrida com saúde `COM_FALHA` → o painel **abre em `Travando`**; saúde `OK` →
    abre em `Agora`; corrida fechada → abre em `Eventos`;
  - `Agora (2)` com dois pipelines saudáveis → badge **neutro**, não vermelho
    (hoje `Tabs.tsx:26-28` pinta todo badge de vermelho);
  - `Encerrar corrida…` está presente e habilitado em `ABERTA · OK`,
    `ABERTA · COM_FALHA` e `ABERTA · SEM_PROGRESSO` — **não** só depois do limite
    vencido; a confirmação diz que os pipelines em execução continuam rodando;
  - malha **sem** `etl_malha.teto_horas` configurado → **nenhuma barra de limite**,
    só a linha do próximo gatilho; malha **com** `teto_horas` → barra, e soltar um
    hold de 6 h **não** faz a barra recuar em silêncio: aparece o evento
    `+6h creditados por retenção` (Decisão 61);
  - duas corridas no mesmo ODATE → a faixa mostra **dois** blocos e trocar entre
    elas não sobrepõe (Decisão 42); e existe **um** mecanismo de navegação
    temporal, não quatro;
  - malha **sem nó Fim** → o evento `#corrida:{id}` aparece na aba `Eventos`
    (Decisão 49);
  - clicar numa linha de `Travando` acende a cadeia no canvas e centraliza o nó,
    sem sair da lente de execução; soltar um hold também não exige sair;
  - `↻ reexecutar` mostra a prévia com a frase do efeito na corrida em voo — ou o
    botão **não existe** (Decisão 65);
  - aresta de `AGUARDANDO_DEPENDENCIA` deixa de ser idêntica a "não rodou": traço
    âmbar tracejado com `title` vindo de `ROTULO_FLUXO`.
- **PR:** `feat: a faixa de corrida e o painel de quem esta travando`

### F11 — Onde a corrida chega ANTES da tela de Malha

- **Entregável:** `Action.OpenUrl` nos cards `MALHA_*` de
  `dags/utils/ds_teams.py:montar_card`, apontando para
  `/malha?malha={m}&modo=execucao&corrida={id}` (molde literal em
  `dags/etl_dag_factory.py:1049-1051`), com base em
  `etl_app_config.app_base_url` (**config nova**, idempotente, na migration da
  fase); linha de corrida no Dashboard (`CorridaBadge` + `x de y` + link direto,
  **sem consulta nova**) e o link de dependência passando a levar malha **e**
  modo (`Dashboard.tsx:499`); filtro por estado de corrida na lista
  (`Todas · Rodando agora · Com falha · Fora do prazo · Não abriram · Concluídas`)
  ao lado do filtro Ativas/Inativas; contadores clicáveis na stats bar
  (`Malha.tsx:670`+) **com a régua declarada no rótulo**; polling condicional da
  lista (Decisão 73); remoção dos textos de fase antiga (`Malha.tsx:450`, `:707`;
  `MalhaEditor.tsx:2205-2206`).
- **Deploy:** `dags/` (etapa 5) + `api/` + front + 1 config na 6c. **Não** exige
  `force_all` — `ds_teams` é importado em runtime pela guardiã, não é fonte
  gerado.
- **Aceite:**
  - card de `MALHA_FALHOU` no Teams → botão que abre
    `?malha=X&modo=execucao&corrida=N` e cai **direto** na corrida certa, no
    celular;
  - `app_base_url` **ausente** → o card sai exatamente como hoje, **sem** botão e
    sem erro no ciclo da guardiã (degradação por ausência, nunca URL inventada);
  - contador da stats bar declara a régua: `12 concluídas na madrugada (referência
    03/08)` — às 08:00 de 04/08 ele **não** mostra `0` por filtrar ODATE = hoje,
    nem um número que não bate com nenhum relatório por ODATE;
  - filtro `Rodando agora` responde da lista, sem abrir malha por malha — hoje é
    **impossível** saber qual malha está rodando sem abrir uma a uma e trocar o
    modo;
  - lista com 40 malhas → **duas** consultas por refetch (medido); **sem** corrida
    aberta nem `não abriu` visível → **zero** refetch;
  - `grep -rn "chega na F8" ui-react/src` volta vazio.
- **PR:** `feat: a corrida chega ao Teams, ao Dashboard e ao filtro da lista`

### F12 — O que decide "posso esperar": duração típica, prazo real e histórico

- **Entregável:** agregado novo de **duração típica por pipeline** sobre
  `etl_job_execution` (irmão de `GET /execucoes/duracao-media`,
  `api/routers/execucoes.py:2504` — `PERCENTILE_CONT` + `COUNT(*)`, **sem tocar o
  Airflow**), escopado aos membros do snapshot, com piso `n ≥ 5` e o `n` no
  payload (Decisão 64); o próximo gatilho como prazo padrão na faixa e no card
  (Decisão 61, reusando `proximaExecucao.ts`); histórico factual da Decisão 68 —
  `falhou 2 das últimas 7 corridas` no card, `corrida anterior: …` na faixa,
  `title` dos blocos da faixa com o membro que travou, e `SEM_TRABALHO` em dia
  atípico virando âmbar; `notificado_em` na aba `Eventos` e no banner de fila
  presa; auditoria completa na tela (Decisão 67: `fechada_por`, `motivo`,
  `origem`, `reaberta_por`) no card, na faixa e na lista de corridas.
- **Deploy:** `api/` + front. **Não** exige `force_all`.
- **Aceite:**
  - membro com 23 execuções históricas → `há 12 min · típico 18 min (n=23)`;
    membro com **3** execuções → **só** o decorrido, sem "típico" e sem `n`
    (o piso é duro, e o `n` nunca aparece sem o número ao lado);
  - membro rodando há 41 min com `p50 = 18 min` → marca âmbar `⚠ 2x`, e a marca
    **não** vira alarme no Teams (é leitura de tela, não evento);
  - o número de duração **não** é chamado de ETA nem de previsão de conclusão da
    corrida em nenhum texto da interface;
  - malha que rodou nas últimas 4 terças e hoje (terça) sai `SEM_TRABALHO` →
    card **âmbar** com *"as últimas 4 terças tiveram trabalho"*; no sábado, a
    mesma malha continua **cinza e muda**;
  - corrida `CANCELADA` → card e faixa dizem `encerrada por C123456 às 05:20 —
    motivo: "…"`, e a lista de `GET /corridas` traz a coluna (o fechamento do mês
    é explicável **sem abrir o banco**);
  - malha `origem = implicita` → o card diz `sem nó Início` e a faixa diz de qual
    raiz veio a data de referência (Decisão 44);
  - webhook do Teams com 401 → banner **vermelho** na faixa,
    `aviso ao Teams na fila desde 03:07`, e não uma linha escondida numa aba;
  - histórico com **zero** corridas fechadas (dia 1) → nenhuma das frases desta
    fase é renderizada, e nada quebra — `n = 0` é ausência, nunca `0%`.
- **PR:** `feat: duracao tipica por membro, prazo real e historico da corrida`

**Ordem de entrega, e por quê:** F4+ antes de tudo (são correções de veracidade —
sem elas a camada nasce mentindo); F9 antes de F10 (o card é a superfície de
varredura, e é o que o gestor abre às 8h); F11 antes de F12 (uma tela ótima que
ninguém alcança às 3h vale menos que uma tela boa com caminho até ela); F12 por
último porque é a única que depende de **corrida real gravada** — antes do smoke
da F9 o histórico é literalmente zero, e um número sem amostra é o que esta spec
inteira existe para não fazer.

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
  `085_malha_execucao.sql` e a resposta é sempre `s`.
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
| `sql/migrations/085_malha_execucao.sql` | **novo** — todo o §5.3 |
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
6. **Progresso por ETAPA dentro de cada membro** (§9.2) — o caminho barato está
   identificado e é **uma** consulta de conjunto: rollup por
   `pipeline IN membros AND start_time >= aberta_em` sobre
   `IX_etl_job_execution_pipeline_status_start`, **sem tocar o Airflow**. A
   ressalva que precisa viajar junto: isso é **recorte de tempo, não identidade
   de run** — quem ler "proibitivo" e parar aí nunca mais volta ao assunto.
7. **Métrica do mês por malha** (§9.7) — quantas vezes esta malha atrasou ou
   falhou em 30 dias. É a pergunta da reunião mensal, o dado passa a existir a
   partir da F9, e sai do `ix_malha_exec_malha`.
8. **Região `aria-live="polite"` na faixa de corrida** (§9.11) — anunciando
   **mudança de fato** (`status`, `saude` ou o inteiro `membros_ok`), nunca tique
   de relógio. Fica fora do dia 1 porque o front não tem nenhum `aria-live` e a
   trava de re-render é a peça mais sujeita a bug desta camada inteira.
9. **Gantt da corrida** (reuso de `GanttChart`, `Dashboard.tsx:236-374`, escopado
   a `aberta_em → fechada_em`) — mostra caminho crítico e paralelismo real, "quem
   atrasou quem". Depende de ≥1 corrida real gravada; entra depois do smoke da
   F10.

## 18. Pendências desta spec (depois do deploy validado)

1. Ligar `malha_corrida_ativa` em produção, malha a malha, depois do smoke.
2. Fixar com o dono o **limiar de linhas** de `etl_pipeline_execucao` acima do
   qual a 085 sai da 6c, e a **edição** do SQL Server da Caixa.
3. Reportar o **achado colateral pré-existente** da borda #13: o rename de malha
   apaga Início/Fim/Aguarde/Notificação pelo `ON DELETE CASCADE` de
   `sql/migrations/075_malha_nos.sql:56-57`. É anterior a esta spec e merece PR
   própria.
4. ✅ **RESOLVIDA na F6.** Os docstrings de `janela_sequencia_horas`
   (`dependencia_janela_sequencia_horas`) e `inicio_do_ciclo_corrente` dizem, nas
   duas árvores, que agora são o **3º degrau** do corte — o fallback de quem não
   tem corrida — e que a janela **não** está depreciada, porque dependência
   avulsa (`origem_no IS NULL`) nunca terá corrida nenhuma.
5. ✅ **CONFIRMADO pelo usuário (2026-08-04): o ODATE é carimbado na ABERTURA**,
   não ao passar pelo Fim — a leitura da Decisão 4 registrada no §4 é a correta,
   e nenhuma fase muda de forma por causa dela.
6. ✅ **RESOLVIDO (2026-08-04, com o usuário): o `%` existe, medindo TEMPO.** A
   Decisão 56 continua valendo para o que ela de fato ataca — não há percentual
   de **contagem de pipelines** em superfície nenhuma, porque `4 de 7` lido como
   `57%` é % de trabalho que não existe. Mas o pedido original (*"dentro de cada
   malha % de execução"*) é legítimo e foi atendido pela **Decisão 56b**: um
   percentual do **tempo típico**, ponderado pela duração histórica de cada
   membro, com `≈`, sufixo `do tempo típico`, piso de `n ≥ 5` em todos os
   membros e sumiço total quando falta histórico. Ele é sempre o SEGUNDO número
   da faixa — o `x de y` continua primário.
7. Resolver com o dono o eixo de prazo (§9.11): `ATRASADA` aparece como
   **estado** no pedido do usuário e como **saúde** no §6.1. A resolução escrita
   é `no prazo` / `fora do prazo` (saúde) × `encerrada sem terminar` (desfecho), e
   ela **vaza para o card do Teams** — precisa estar fechada antes da F9.
8. Fixar o **limiar de "sem sinal"** (§9.5, `1 sem sinal há 20h`) e a **folga do
   `nao_abriu`** (§9.2, Decisão 58): quantos minutos depois do horário previsto o
   card vira âmbar. Os dois são config, não constante no front.
9. Configurar `etl_app_config.app_base_url` (Decisão 69) — sem ela, o card do
   Teams sai sem botão, que é a degradação correta, mas também é a camada de §9.8
   inteira sem efeito.
10. **A janela de fallback do observador ainda usa o relógio do WORKER**
    (`dags/etl_dependencia_guardia.py`, `data_corrente = calcular(_agora(), …)`).
    É pré-existente da F14 e sobreviveu de propósito à F2 — o aceite manda o
    observador continuar sendo "o de antes" quando o interruptor está desligado.
    Mas ele agora **convive** com o caminho novo, que lê o relógio do banco: com
    os 3 h de desvio medidos no dev e virada 00:00, das 21:00 às 24:00 do worker
    a janela `{D-1, D}` fica um dia atrás do banco e a conclusão do "hoje" do
    banco fica invisível. Em produção o desvio é presumido zero — **presumido, não
    medido**. Medir antes de ligar o interruptor, e converter para o relógio do
    banco numa PR própria se houver desvio.
11. **O card de `MALHA_CONCLUIDA` do nó Fim ainda publica o marcador interno**
    (`dags/utils/ds_teams.py`): sai com sujeito `#no:38` e fato `Pipeline: #no:38`,
    contrariando a Decisão 74 (nome de máquina não vai ao celular). É
    pré-existente na `main` e o roteamento que o mantém no card genérico é
    deliberado (Fim e Notificação são componentes do desenho, não a corrida).
    Resolver na **F11**, que é a fase que reabre `montar_card` — a fila precisa
    passar a trazer a malha do NÓ, e não só a da corrida, que é o que ela ganhou
    na F2.
12b. **A F10 tem de consumir `corridas_no_dia`.** Quando o operador navega por
    data e aquele dia teve **mais de uma** corrida, a API passou (na F4) a
    OMITIR o bloco `corrida` e a devolver `corridas_no_dia: N` — porque
    descrever uma corrida sobre a lista do dia inteiro é a mesma mentira que a
    fase inteira mata. Hoje o front só deixa de mostrar a faixa; o certo é
    dizer *"este dia teve N corridas — escolha uma"* e oferecer o
    `SeletorCorrida`, que é entregável da F10. Enquanto isso não existe, o
    operador vê o canvas do dia sem faixa, que é honesto mas mudo.
14. **A guardiã é uma QUARTA porta de disparo e não propaga a corrida.**
    `dags/etl_dependencia_guardia.py` chama `montar_conf(data_ref, dia_op,
    "guardia")` — sem `malha_execucao_id`. A **data** não sofre (o degrau 0 lê a
    linha que a própria guardiã acabou de criar) e a proveniência costuma ser
    recuperada pelo degrau 3; mas ela se perde exatamente quando o pipeline é
    membro de **duas corridas do mesmo ODATE**, que é o caso que a F5 existe
    para tratar. A recusa por ambiguidade também não roda nessa porta. Se "as
    três portas" da Decisão 35 incluem a guardiã, falta esta — resolver na F7,
    que já mexe na guardiã.
15. **Um blip de banco na primeira pergunta do run ainda pode gravar a linha
    com a data do cálculo.** A F5 fechou metade: resposta dada com o banco mudo
    não vira memória, então a próxima task refaz a pergunta (teste
    `test_banco_mudo_na_1a_chamada_nao_vira_a_data_oficial_do_run`). O que
    **não** existe é reconciliação: se a linha já nasceu com a data errada, o
    degrau 0 a lê e a fixa. Fechar isso exige mover linha entre ODATEs, que é
    mais arriscado que o defeito — decidir com o dono depois do smoke.
16. **`Clear` de um run recusado por ODATE ambíguo reencontra a linha `PULADO`**
    pelo degrau 0 e roda com a data do cálculo. A mensagem manda "dispare de
    novo" (run novo), que escapa — mas `Clear` é o gesto de plantão mais comum.
17. **Uma conexão a mais por task enquanto o interruptor está em `0`.** Medido:
    `_odate_do_run` num processo novo abre 1 conexão + 1 `SELECT config_value`
    mesmo desligado; do 2º run em diante a consulta some, a conexão não. Como o
    interruptor só liga depois da F7, esse é o estado permanente até lá.
18. **A sonda do §12.2 responde `DESCONHECIDO` para pipeline nunca publicado**
    (sem arquivo em `generated/`), mandando o operador conferir um arquivo que
    nunca existiu. Seguro pela regra ("desconhecido nunca é ausência"), mas o
    texto podia distinguir os dois.
19. **N+1 na sonda do disparo:** `carimbo_corrida_dos_pipelines` consulta o
    cadastro **por membro** antes de ler cada arquivo — numa malha de 40 são 40
    consultas + 40 `stat` a cada disparo, inclusive `dry_run`. O cache é por
    arquivo; o do cadastro não existe.
13. **`_fechar_dia_anterior` ainda fecha como `NAO_LIBEROU` linhas de corrida
    `ABERTA`** que atravessem o dia operacional (teto > 24 h, ou cadeia longa com
    rerun) — virando pendentes e levando a corrida a `FALHA` por ação da própria
    guardiã. É entregável da **F7** (Decisão 31) e o interruptor só vai a `1`
    depois dela, então está coberto pela ordem de deploy; registrado aqui para
    não escapar se a ordem mudar.
20. **A varredura de `corridas_aguardando` da guardiã pergunta `liberado()` sem
    a corrida da linha** (F6). Três das quatro chamadas da guardiã —
    `_rede_seguranca`, `_fechar_dia_anterior` e o `_diagnostico` do deadline —
    iteram `dep.corridas_aguardando(conn)`, que devolve
    `(pipeline, data, run_id, criado_em)`: o `malha_execucao_id` da linha existe
    na tabela desde a F5, mas trazê-lo mudaria a **aridade** de uma leitura que
    quatro responsabilidades consomem e ~30 dublês de teste espelham. Sem o
    degrau 1, o corte cai no degrau 2 (a corrida **aberta** da malha que assinou
    a dependência), que é a resposta certa em todo ciclo **em voo**; a diferença
    aparece só depois que a corrida da linha fechou, e aí decide a janela — que é
    **exatamente o comportamento de hoje**, não uma regressão. A quarta chamada
    (`_quiescencia_liberada`) já passa a corrida, porque a tem em mãos. Fechar o
    resto é da **F7**, que reabre esta varredura (e é a mesma família da
    pendência 14).

---

**Ordem de deploy, numa frase:** etapa 5 (`dags/`, responder `s`) → etapa 6c
(migration **085**, prompt padrão-NÃO, responder `s`, **nunca** `--baseline`) →
`api/` + front (automáticos) → etapa 8b **`n`** em todas as fases — e **só na F5**
com `force_all` disparado à parte, confirmado pela sonda por pipeline do §12.2;
o interruptor `malha_corrida_ativa` só vai a `1` depois da F7 e do smoke.
