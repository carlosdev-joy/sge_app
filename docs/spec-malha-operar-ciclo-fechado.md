# Spec: Operar o ciclo da malha depois de fechado — Orquestra

Data: 2026-08-13 · Status: **rascunho** (aguardando aprovação do usuário)

## 1. Visão

Hoje o desfecho de um ciclo de malha é **irrevogável e prematuro**: a guardiã
sentencia assim que a malha para, e nada no produto revisa esse veredito quando
o operador conserta a falha e o trabalho termina. O resultado é um dia que
concluiu de verdade mas fica vermelho para sempre — e um operador sem nenhum
gesto na tela da Malha para corrigir isso.

Esta spec dá ao operador a capacidade de **reavaliar** um ciclo fechado (o
gesto principal, que não inventa verde: apenas manda a guardiã reler o que está
no banco), corrige o falso verde que hoje existe no anúncio do nó Fim, e ataca a
causa raiz do fecho prematuro. O carimbo manual de conclusão existe, mas como
**exceção nomeada e mais cara**, não como caminho principal.

### O caso que motivou (Carga_Vida, ciclo #4 de 2026-08-12)

Linha do tempo real, extraída do banco de produção:

| Hora | Fato |
|---|---|
| 01:10 | ciclo #4 abre (`aberta_em`), `teto_em = 13/08 01:10` |
| 04:30 | `SEQSSDVIDA3RECEBIMENTO` e `SEQSSDVIDA6SINISTRO` partem |
| 04:45 | ambos **falham** → `PREDECESSOR_FALHOU` em `SEQSSDVIDA7PEPS` e `SEQSSDVIDA10COBERTURA` |
| **07:13** | **guardiã fecha `FALHA`** — motivo: "2 pipeline(s) sem concluir: COBERTURA (nao_partiu), PEPS (nao_partiu)" |
| 09:52 | `6SINISTRO` conclui **SUCESSO** (linha 143, `malha_execucao_id = 4`) |
| 11:10 | `3RECEBIMENTO` conclui **SUCESSO** (linha 140, `malha_execucao_id = 4`) |
| 11:10→11:22 | `COBERTURA` conclui **SUCESSO** (linha 138, `malha_execucao_id = **NULL**`) |
| 11:10→11:22 | `PEPS` falha (linha 144, `malha_execucao_id = **NULL**`) |
| 22:51→22:57 | `PEPS` conclui **SUCESSO** (linha 155, `malha_execucao_id = **NULL**`) |
| 23:00 | observador do nó Fim emite **"ciclo concluído"** sobre um ciclo fechado em FALHA |

Os quatro pipelines terminaram em `SUCESSO`, nenhum com `substituida_em`. **O
verde já existe no banco, em linhas reais com horários reais.** O que ficou
errado é só o veredito — e o vínculo de três dessas linhas com o ciclo.

### Por que nenhum caminho existente resolve

| Porta | Por que não cobre |
|---|---|
| **Finalização Manual** (`api/routers/finalizacao.py`) | Só alcança linha **em andamento** (`WHERE status='EXECUTANDO'`, `:151`; `RUNNING` no GET `:195`; **404** sem alvo `:304-307`). Pipeline em FALHA não é alvo. E ela declaradamente não fecha corrida: *"Fechar é da guardiã, sempre (Decisão 19)"* (`:80-84`) |
| **`POST /malhas/{m}/corridas/{id}/encerrar`** (`api/routers/malhas.py:4939`) | Desfecho **fixo `CANCELADA`** (`:5021`), fora de `REABREM`, e significa "desisti". Além disso **recusa com 422 ciclo já fechado** (`:5006-5018`) |
| **Rerun com cascata** (`api/routers/execucoes.py:1257`) | Único caminho que reabre ciclo (`_efeito_na_corrida` → `mc.reabrir_corrida`, `:761`), mas atrás de `if cascata:` **e** `if n > 0:` (`:1196-1216`). `n = marcar_substituidas(info["com_corrida"])`, e dependente que **não rodou** não tem corrida a aposentar (`api/services/rerun.py`, docstring de `afetados`). **No caso Carga_Vida os dois pendentes eram exatamente `nao_partiu` → `n = 0` → o efeito nunca roda.** O front até desabilita a opção (`ModalRerunEtapa.tsx:409-412`) |
| **`docs/forcar-reset-ciclo-malha.sql`** | Fecha como `CANCELADA` ou, com `@limpar=1`, **apaga** o ciclo. Fora do RBAC e da auditoria do produto |

Consequência estrutural: `mc.fechar_corrida(..., 'CONCLUIDA')` tem **um único
chamador de produção** — a guardiã (`dags/etl_dependencia_guardia.py:1329`) — e
`SQL_FECHAR` termina em `WHERE id = ? AND fechada_em IS NULL`
(`api/services/malha_corrida.py:1011`): **não existe transição terminal →
terminal no produto**. Esta spec preserva isso: reavaliar passa por `ABERTA`.

### A causa raiz do fecho prematuro

`_quiescencia_liberada` (`guardia.py`) adia o fechamento **somente** quando
existe linha `AGUARDANDO_DEPENDENCIA` que `liberado()` aprova — ou seja, que vai
partir **agora**. Às 07:13, `COBERTURA` e `PEPS` aguardavam com os pais em
`FALHA`: `liberado()` = `False`, nada a adiar, ciclo sentenciado.

**A guardiã distingue "vai partir" de "não vai partir", mas não conhece "pode
partir se alguém consertar".** Falha de predecessor é o estado mais reexecutável
que existe, e é tratado como definitivo.

## 2. Escopo

**IN:**
- Correção do falso verde do observador do nó Fim (anúncio de conclusão sobre
  ciclo fechado com desfecho ruim) e do fechamento em `FALHA` que hoje é mudo.
- Portão do §11.1 que **fala** quando recusa, em vez de `log.info` + `continue`.
- Gesto **Reavaliar ciclo** na tela da Malha: reabre, estende o teto, deixa a
  guardiã julgar o que está no banco. RBAC `acao_executar`.
- Prévia honesta antes do clique (o que vai acontecer, linha a linha).
- Adoção das linhas órfãs (`malha_execucao_id IS NULL`) nascidas depois do fecho.
- Carência da guardiã para falha reexecutável — a causa raiz.
- Gesto **Concluir manualmente** como exceção, com desfecho próprio, motivo
  obrigatório e autoria do token.

**OUT (explícito):**
- **Carimbar `SUCESSO` em linha de pipeline** (`etl_pipeline_execucao`). Fica de
  fora por decisão de risco: `liberado()` (`dependencias.py:757-761`) e
  `pipelines_todos_sucesso` (`:1861-1868`) só olham status/`substituida_em`/data,
  e `_rede_seguranca` (`guardia.py:579-688`) dispara os filhos `AGUARDANDO` no
  tick seguinte **sem olhar corrida** — carimbar **é** soltar a cadeia, com o
  ODATE de ontem e proveniência apontando para o robô. Backlog, se um dia for
  pedido, exige pergunta explícita e registrada sobre a existência da saída.
- Reprocesso automático de quem consumiu dado pré-correção. O modal **informa**
  (reusando `fecho_dependentes`, `rerun.py:112-149`), mas não age.
- Unificação com a spec **#301 (Reset à força)** — ver §9.
- Expurgo/retenção de `etl_malha_execucao` e `etl_job_execution_tentativa`.
- Correção do `GET /audit` sem autenticação (`api/routers/infra.py:199-203`) —
  achado colateral, vai para trilha de segurança própria.

## 3. Arquitetura proposta

- **Front:** `ui-react/src/components/malhas/CabecalhoCorrida.tsx` (ações do
  ciclo), `MalhaEditor.tsx` (modo Execução), modal novo
  `ModalOperarCiclo.tsx` reusando o padrão de confirmação da #301. Tokens
  `canvas/panel/edge/ink` claro+escuro. **`dist/` é commitada** — toda fase de
  front rebuilda.
- **Back:** `api/routers/malhas.py` (rotas novas ao lado de `encerrar_corrida`,
  `:4939`), `api/services/malha_corrida.py` (port canônico).
- **Motor:** `dags/etl_dependencia_guardia.py` (observador do Fim, critério de
  quiescência), `dags/utils/malha_corrida.py` (gêmeo do port).
- **⚠️ Invariante 12 — paridade das duas árvores:** `dags/utils/malha_corrida.py`
  e `api/services/malha_corrida.py` são cópias com paridade testada
  (`tests/test_malha_corrida_paridade.py`). Toda mudança entra **no mesmo
  commit** nas duas. Lembrar do gotcha de placeholder: `dags/` usa `%s`
  (pymssql), `api/` usa `?` (pyodbc).
- **Dados:** `etl_malha_execucao` (085), `etl_pipeline_execucao` (067),
  `etl_dependencia_evento`, `etl_pipeline_audit`.

**Decisões e alternativas descartadas:**
- *Reavaliar via reabertura, não via transição terminal→terminal* — preserva a
  autoridade única da guardiã sobre `CONCLUIDA` e evita ser a primeira transição
  desse tipo no produto.
- *Desfecho próprio para o carimbo manual, não `CONCLUIDA` reusado* —
  `fechada_por LIKE 'manual:%'` **não serve** de discriminador: `EXPIRADA`
  (`malhas.py:5789`) e `ABORTADA` (`:5918`) já gravam esse prefixo em
  fechamentos automáticos.
- *`acao_executar`, não `acao_admin`* — decisão do usuário: reavaliar não
  inventa verde, só manda reler o banco; exigir admin obrigaria a acordar
  alguém às 3h. Precisa ficar coerente com a #301 (§9).

## 4. Modelo de dados

**Migration `088_malha_desfecho_manual.sql`** (idempotente, etapa 6c do
`deploy.sh`):

| Objeto | Mudança |
|---|---|
| `etl_malha_execucao.status` | `CK_mexec_status` ganha o 8º valor `CONCLUIDA_MANUAL` (drop + recreate do CHECK, com guarda `IF EXISTS`) |
| `etl_malha_execucao.teto_em` | sem DDL — passa a ser **reescrito** na reabertura (F2) |
| `etl_malha_execucao.reavaliada_em` / `reavaliada_por` | colunas novas (`IF COL_LENGTH(...) IS NULL`) — `tentativas` já existe mas conta reaberturas de rerun também; a distinção importa para a métrica |

⚠️ **`CONCLUIDA_MANUAL` toca sete lugares** e esquecer um reproduz o defeito já
catalogado com `ABORTADA` (*"não casava filtro nenhum, não tinha contador, ficava
invisível às 8h"*, `corridasDaLista.ts:318-325`):
`DESFECHOS`/`REABREM` nas **duas** árvores · `STATUS_CORRIDA` ·
`casaEstado`/`ESTADOS_CORRIDA` · `TEM_PROBLEMA`/`PESO_CORRIDA` ·
`_DESFECHOS_RUINS` (`malhas.py:2755`) · `ds_teams.ESTILO`.
O teste é de **paridade entre as listas**, não de existência de cada uma.

⚠️ **Não criar status novo em `etl_pipeline_execucao`**: a 067 **não tem CHECK**
(`067:36-37`) — um status novo entraria em silêncio e todo leitor que compara
`status='SUCESSO'` ignoraria a linha, deixando o membro eternamente pendente.

## 5. Fases

### F0 — O falso verde do nó Fim, o desfecho mudo e o portão calado

Pré-requisito de merge das demais: sem ele, um botão novo **agrava** a
contradição — passariam a existir dois "concluído" na mesma coluna, um humano e
um do Fim, indistinguíveis, e o gesto manual teria mais autoridade visual que o
veredito da máquina, que hoje se cala.

- **Entregável:** três correções independentes no motor + uma na API.
- **Inclui:**
  - guarda do observador: a verificação "não anunciar com membro vivo" está
    inteira dentro de `if aberta is not None:` (`guardia.py:1496`) — com o ciclo
    fechado ela não roda. Passa a ler o desfecho da corrida da data e **não
    emite** sobre ciclo fechado com desfecho ruim;
  - texto do evento afirma só o verificado: *"os N pipelines que alimentam o Fim
    concluíram"*, reservando "ciclo concluído" para o desfecho;
  - fechamento em `FALHA` emite **sempre** evento de desfecho, distinto do
    alerta de detecção (hoje `so_se_primeira_falha=True`, `guardia.py:1075`,
    engole o evento quando o alerta já saiu — foi por isso que o caso Carga_Vida
    não tem evento de fecho na linha do tempo);
  - portão do §11.1 passa a **responder**: `MOTIVO_INTERRUPTOR`,
    `MOTIVO_SEM_085`, `MOTIVO_GUARDIA_AUSENTE` já existem
    (`malhas.py:5443-5445`); hoje a recusa é `log.info` + `continue`
    (`execucoes.py:744-751`) e o operador vê rerun verde com ciclo em FALHA.
- **Critérios de aceite:**
  - dado ciclo fechado como `FALHA`, quando o observador do Fim roda, então
    **nenhum** `MALHA_CONCLUIDA` é emitido (teste por ausência, no molde de
    `_nao_diz_concluida`, `tests/test_malhas_f9_aceite.py:357-369`);
  - dado fechamento em `FALHA` com alerta de detecção já emitido, então o evento
    de desfecho sai assim mesmo, com tipo distinto;
  - dado portão recusando por qualquer das 4 razões, então a resposta do rerun
    traz o motivo nomeado.
- **Validação:** pytest (baseline HEAD, zero falhas novas) + tsc/eslint/build.
- Revisão adversarial multi-agente. PR: `fix: o nó Fim para de anunciar conclusão sobre ciclo que falhou`

### F1 — Reavaliar o ciclo (o gesto principal)

- **Entregável:** `POST /malhas/{malha}/corridas/{id}/reavaliar` + botão no
  cabeçalho do ciclo, no modo Execução.
- **Inclui:**
  - reusa `reabrir_corrida` + `descartar_desfecho`
    (`api/services/malha_corrida.py:1089`), que já fazem o trabalho pesado:
    `ABERTA`, `fechada_em=NULL`, `tentativas+1`, desfecho anulado concatenado no
    `motivo`, e descarte dos eventos de desfecho (**obrigatório**: sem ele
    `ux_dep_evento_corrida` engole a próxima conclusão);
  - **extensão do teto** (decisão do usuário): `SQL_REABRIR` hoje **não toca
    `teto_em`**. No caso Carga_Vida o teto (`13/08 01:10`) já venceu, e reabrir
    sem estender deixaria a guardiã fechar `EXPIRADA` no tick seguinte — que
    **não está em `REABREM`** e é fim de linha irreversível. Passa a recalcular
    `teto_em` a partir de agora;
  - **janela** (decisão do usuário): até a virada do ciclo seguinte. Depois
    disso, **recusa nominal** (nunca silenciosa) com o motivo exato — "o ciclo
    de 13/08 já está aberto" ou "as linhas dos dependentes já foram encerradas
    como `NAO_LIBEROU`" (terminal, `dependencias.py:1302-1304`);
  - `descartar_desfecho` **degrada em silêncio** (`malha_corrida.py:1153-1158`:
    exceção → `log.warning`, `return 0`) — reabriria sem descartar e o card da
    reconclusão nunca sairia. Aqui a falha do descarte **aborta** a reavaliação;
  - RBAC `acao_executar`; autoria **sempre do token**, nunca do corpo (o padrão
    de `resolve_failure`, `execucoes.py:2513`, aceita matrícula do corpo — não
    copiar).
- **Critérios de aceite:**
  - dado o ciclo #4 da Carga_Vida com os 4 pipelines em `SUCESSO`, quando
    reavaliado, então ele volta a `ABERTA` com `teto_em` futuro e a guardiã o
    fecha `CONCLUIDA` no tick seguinte — **sem nenhum carimbo de status**;
  - dado ciclo com membro do `conta_para_fim` ainda pendente, quando reavaliado,
    então ele reabre e **permanece** aberto (a guardiã não inventa verde);
  - dado o ciclo do dia seguinte já aberto, então 422 nomeando a causa;
  - dado desfecho fora de `REABREM` (`EXPIRADA`/`ABORTADA`/`CANCELADA`/
    `SEM_TRABALHO`), então 422 dizendo que aquele desfecho é fim de linha.
- **Validação:** pytest + tsc/eslint/build + **cenário executado no dev**.
- Revisão adversarial. PR: `feat: reavaliar o ciclo da malha depois de fechado`

### F2 — A prévia honesta e a adoção das linhas órfãs

- **Entregável:** modal com dry-run + carimbo de vínculo das linhas nascidas
  depois do fecho.
- **Inclui:**
  - **prévia:** os **três** contadores lado a lado (membros do snapshot,
    `conta_para_fim`, linhas do pipeline), porque eles divergem e o operador
    precisa ver isso antes de clicar. ⚠️ Os contadores **não podem ser usados
    como evidência**: `SQL_ESTADO` de ciclo fechado tem
    `AND (malha_execucao_id = ? OR COALESCE(inicio,criado_em) >= ?)` **sem teto
    superior** (`malha_corrida.py:1454-1457`), enquanto a lista de execuções do
    mesmo painel tem `_ESCOPO_PAINEL_FECHADA` com `<= fechada_em`
    (`malhas.py:3286-3301`) — o cabeçalho tende a exibir "13 de 13" sob chip
    vermelho. A prévia **lista linha a linha** (`id`, `inicio`,
    `malha_execucao_id`) o que sustenta o fechamento;
  - **adoção das órfãs:** linhas nascidas depois do fecho ficam com
    `malha_execucao_id IS NULL` porque `_dona_do_odate` só aceita dono de ciclo
    **ABERTO** (`dags/utils/malha_corrida.py:661-674`). No caso Carga_Vida são 3
    das 5 linhas. A reavaliação carimba o vínculo das linhas do ODATE dentro da
    janela do ciclo;
  - informação (não ação) sobre quem consumiu dado pré-correção, reusando
    `fecho_dependentes` (`rerun.py:112-149`);
  - componente de confirmação **compartilhado com a #301** (motivo obrigatório,
    confirmação digitando o nome da malha, trava de DagRun em voo).
- **Critérios de aceite:** dado ciclo com linhas órfãs, quando reavaliado, então
  todas passam a apontar para o ciclo; dado dry-run, então nenhuma escrita
  ocorre e a resposta lista as linhas nominalmente.
- **Validação:** pytest + tsc/eslint/build + cenário no dev.
- Revisão adversarial. PR: `feat: prévia da reavaliação e adoção das linhas órfãs do ciclo`

### F3 — A causa raiz: carência para falha reexecutável

- **Entregável:** a guardiã deixa de sentenciar o dia enquanto a falha ainda é
  consertável.
- **Inclui:**
  - hoje `_quiescencia_liberada` adia o fecho **só** quando `liberado()` aprova
    alguma linha `AGUARDANDO` — isto é, quando ela vai partir **agora**. Passa a
    reconhecer o estado intermediário: membro pendente cuja causa é predecessor
    em `FALHA` (classe `nao_partiu` derivada de falha, não de ausência) segura o
    desfecho por uma **carência configurável por malha**, dentro do teto;
  - o alerta de detecção continua saindo cedo (o plantão precisa dele) — o que
    muda é só o **desfecho**, que passa a esperar;
  - default conservador: carência que preserve o comportamento atual para quem
    não configurar, e a decisão de qual valor sai do histórico real das malhas.
- **Critérios de aceite:** dado o cenário Carga_Vida replicado no dev (pais
  falham 04:45, conserto às 09:52/11:10), quando a carência está ativa, então o
  ciclo **não** é fechado às 07:13 e conclui `CONCLUIDA` sozinho; dado membro
  pendente por ausência (nunca teve linha), então o comportamento não muda.
- **⚠️ Fase de risco:** mexe no motor que decide o desfecho de toda malha.
  Exige cenários executados no dev e teste-âncora comparando o comportamento com
  o de `main` nos casos não cobertos pela carência.
- **Validação:** pytest + cenários vivos no dev.
- Revisão adversarial reforçada. PR: `fix: o ciclo deixa de ser sentenciado enquanto a falha ainda é consertável`

### F4 — Concluir manualmente (a exceção)

- **Entregável:** o segundo gesto, para quando o trabalho foi feito por fora e
  não há o que reavaliar.
- **Inclui:**
  - migration `088` com `CONCLUIDA_MANUAL` e os **sete** pontos de leitura;
  - motivo obrigatório com 422 didático (molde de `encerrar_corrida`,
    `malhas.py:4939-5046`); autoria do token;
  - **recusa** `CONCLUIDA_MANUAL` enquanto houver membro do snapshot em `FALHA`
    **fora** do `conta_para_fim` — a lista `fora_do_fim` já é calculada
    (`malha_corrida.py:1570`). Sem isso, declarar sucesso nos 2 alimentadores do
    Fim fecharia o ciclo com 11 membros em falha;
  - **não escreve `duration_seconds`** de relógio. A Finalização Manual já grava
    `DATEDIFF(SECOND, start_time, GETDATE())` (`finalizacao.py:313`), que entra
    em `_SQL_TIPICOS` (`malhas.py:2230-2253`), em `/execucoes/duracao-media` e no
    `sla-report` — o produto **já sabe** que isso é errado (a reconciliação usa o
    `end_time` real do Airflow "para não contaminar o P90"). O veneno é diferido:
    distorce as madrugadas dos próximos 90 dias;
  - **rastro em três camadas**: coluna estrutural · evento de **tipo próprio**,
    fora de `EVENTOS_DO_DESFECHO` (senão `descartar_desfecho` apaga o carimbo
    humano no próximo rerun com cascata) · linha em `etl_pipeline_audit`, que o
    reset da #301 não toca;
  - **discriminante visual obrigatório** na tela: hoje toda proveniência vive
    dentro do `title` do nó (`MalhaEditor.tsx:413`) e num `line-clamp-2`
    (`CabecalhoCorrida.tsx:300-302`), e `_classe_da_linha` lê **apenas** o status.
- **Critérios de aceite:** dado ciclo com membro em falha fora do
  `conta_para_fim`, então 422; dado ciclo concluído manualmente, então ele
  aparece visualmente distinto em todas as sete superfícies e **não** sai do
  numerador de "falhou N das últimas 7".
- **Validação:** pytest + tsc/eslint/build + cenário no dev + conferência da
  migration por `SELECT` (§12.1: `migrate.py` descarta `PRINT`).
- Revisão adversarial. PR: `feat: concluir o ciclo manualmente, com desfecho próprio e rastro`

### F5 — Fecho: manual, smoke e aceitação

- **Entregável:** MANUAL do operador atualizado, roteiro de smoke executado no
  dev, matriz de aceitação.
- **Inclui:** quando usar reavaliar × concluir manualmente; o que cada um faz
  com a cadeia; a janela e o que acontece depois dela.
- **Validação:** roteiro **executado** no dev antes de virar guia de produção.
- PR: `docs: manual e aceitação da operação de ciclo fechado`

## 6. Riscos e mitigações

| # | Risco | Impacto | Mitigação |
|---|---|---|---|
| 1 | `EXPIRADA` irreversível ao reabrir ciclo com teto vencido | ciclo perdido para sempre | F1 estende `teto_em` na reabertura; teste com teto vencido |
| 2 | Divergência entre `dags/utils/` e `api/services/` (invariante 12) | comportamento diferente no motor e na API, invisível | mudanças no mesmo commit + `test_malha_corrida_paridade` |
| 3 | `CONCLUIDA_MANUAL` esquecido em 1 dos 7 pontos | desfecho invisível às 8h (defeito já vivido com `ABORTADA`) | teste de **paridade entre listas**, não de existência |
| 4 | F3 muda o desfecho de toda malha | regressão ampla no motor | carência opt-in, default preservando o atual, teste-âncora contra `main` |
| 5 | `descartar_desfecho` falha em silêncio | reabre e a reconclusão nunca é anunciada | F1 aborta a reavaliação se o descarte falhar |
| 6 | Métrica de confiabilidade descaracterizada | "falhou N das últimas 7" vira decoração em 3 semanas | decisão escrita + teste por ausência sobre `_DESFECHOS_RUINS` |
| 7 | `dist/` não rebuildada | PR "invisível" em produção | checklist de cada fase de front |
| 8 | Supervisão DataStage em ABORTOU ao lado do painel de Malha verde, na mesma tela (`Dashboard.tsx:1083`/`:1094`) | operador vê dois vereditos contraditórios | decidir na F5: exigir resolução na DS como pré-condição, ou escrever a reconciliação na tela |

## 7. Smoke pós-deploy

a) Abrir uma malha com ciclo fechado em `FALHA` cujo trabalho concluiu → botão
   **Reavaliar** presente e habilitado.
b) Clicar → prévia lista **linha a linha** o que sustenta o fechamento, com os
   três contadores e suas divergências visíveis.
c) Confirmar → ciclo volta a `ABERTA` com `teto_em` futuro; conferir no banco
   `tentativas`, `reaberta_em`, `motivo` com o desfecho anulado.
d) Aguardar 1 tick da guardiã (5 min) → ciclo fecha `CONCLUIDA` **sem carimbo**;
   evento de conclusão sai **uma vez**.
e) Conferir que as linhas órfãs do ODATE passaram a apontar para o ciclo.
f) Repetir com ciclo cujo `conta_para_fim` ainda tem pendente → reabre e
   **permanece** aberto (a guardiã não inventa verde).
g) Tentar reavaliar com o ciclo do dia seguinte aberto → 422 nomeando a causa.
h) Tentar reavaliar ciclo `CANCELADA` → 422 dizendo que é fim de linha.
i) **F0:** provocar fechamento em `FALHA` com alerta já emitido → evento de
   desfecho sai assim mesmo; observador do Fim **não** emite conclusão.
j) **F0:** desligar o interruptor e mandar rerun → a recusa do portão **aparece
   na resposta**, com motivo.
k) **F4:** concluir manualmente um ciclo → aparece distinto nas sete superfícies;
   conferir que não entrou em `_SQL_TIPICOS` nem no `sla-report`.

## 8. Pendências e decisões em aberto

**Decididas pelo usuário em 2026-08-13:**
1. Investigar o fecho prematuro da guardiã — **sim**, entra como F3.
2. Permissão — **`acao_executar`** para os dois gestos (mesmo nível de disparar).
3. Janela — **até a virada do ciclo seguinte**, com recusa nominal depois.
4. Teto vencido — **estender na reabertura**.

**Em aberto:**
5. Valor default da carência da F3 — sair do histórico real das malhas, não de
   palpite.
6. `CONCLUIDA_MANUAL` entra em `DESFECHOS_RUINS`, ou a frase da confiabilidade
   ganha um terceiro número ("falhou 2 · fechado após correção 1 de 7")?
   ⚠️ **A F0 aumentou o peso desta pendência.** `DESFECHOS_RUINS` deixou de ser
   só "o numerador de falhou N das últimas 7" e virou também **a mordaça do nó
   Fim**: um desfecho fora da tupla faz o observador anunciar *"os N pipelines
   que alimentam o Fim concluíram"* sobre um ciclo fechado à mão. A escolha da
   F4 decide, portanto, **duas** coisas — a métrica e o anúncio —, e é preciso
   dizer explicitamente qual comportamento se quer em cada uma.
7. Pré-condição de falha **Resolvida** com `snow_ticket` em `etl_failure_ack`
   para o gesto da F4 — costura com a spec **#297** e é a única prova externa
   disponível. O campo já existe.
8. Reconciliação com a Supervisão DataStage (risco 8).

**A confirmar no banco de produção** (decide detalhe da F1/F2, não o desenho):
- `SELECT origem_pipeline, origem_no FROM dbo.etl_malha_aresta WHERE destino_no = <id do Fim da Carga_Vida>` — quais são os alimentadores diretos do Fim.
- `SELECT pipeline_name FROM dbo.etl_malha_execucao_membro WHERE malha_execucao_id = 4 AND conta_para_fim = 1` — o `conta_para_fim` congelado do ciclo #4.
- O nó Fim tem `notificar_teams: true`? Decide se o card ✅ falso do dia 12 já foi ao canal de plantão.
- Valor de `dependencia_modo_sequencia` em produção — em `'1'` o predicado exige `ISNULL(fim, inicio) >= corte`, o que muda o sentido do gesto.

## 9. Relação com a spec #301 (Reset à força)

**Specs separadas, com contrato compartilhado travado antes, e a #301 primeiro.**

*Por que não fundir:* os efeitos são opostos (a #301 **anula** o dia para rodar
de novo; esta **sela** o dia) e os custos são de outra ordem — a #301 não tem
migration e só toca `api/`, enquanto esta exige migration no `CK_mexec_status`,
paridade nas duas árvores, sete pontos no front e mudança no motor (F3). Fundir
amarraria um gesto de emergência já rascunhado a um trem mais longo.

*Por que não ignorar:* colidem em quatro pontos.
1. **RBAC** — a #301 §8a deixa em aberto e recomenda `acao_admin`; aqui o
   usuário decidiu `acao_executar`. **As duas precisam de resposta coerente**,
   senão a tela de Malha passa a ter dois gestos humanos com critérios
   diferentes e ninguém consegue explicar por quê. *Esta é a pendência mais
   urgente entre as duas specs.*
2. **Modal, trava e auditoria** — dry-run como pré-visualização, motivo
   obrigatório, confirmação digitando o nome, trava de DagRun em voo: 1:1
   reaproveitável, nasce como componente único.
3. **Rastro à prova de reset** — o `@limpar=1` **não apaga** o evento do ciclo
   (o passo 6a filtra por nome de pipeline membro,
   `forcar-reset-ciclo-malha.sql:312-318`, e `#corrida:{id}` não está em
   `etl_malha_pipeline`). O que ele apaga é a linha de `etl_malha_execucao`
   (`:326-328`), o que **desvincula** o evento: a tela não o mostra mais e o card
   nunca sai. Requisito para as duas: o dry-run da #301 **lista os ciclos
   fechados manualmente que o reset vai desvincular**, e o fechamento manual
   grava em `etl_pipeline_audit`, que o reset não toca.
4. **Fila** — a #301 §8d já pergunta a ordem versus a #297. Agora são três
   coisas disputando a mesma tela.

*Ordem recomendada:* **F0 desta spec** (é correção de defeito vivo, não feature)
→ #301 → F1–F5 desta spec.
