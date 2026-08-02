# Desenho técnico — F4: DAG guardiã (`etl_dependencia_guardia`)

Spec: `docs/spec-dependencias-pipelines.md` §3 (guardiã) e §5-F4 · Base: branch `feat/retomada-f3-push` (F3 desenhada **e implementada**: `dags/utils/dependencias.py` + factory) · Escopo: `dags/etl_dependencia_guardia.py` (novo, manuscrito) + funções novas em `dags/utils/dependencias.py` + card novo em `dags/utils/ds_teams.py` + testes · **Zero migration nova** · Suíte-contrato: `docs/retomada-aceitacao.md` — itens de F4: **D18, D41–D52** + as metades que a F3 deixou: **D16** (redisparo pela guardiã) e **D22** (guardiã dispara às 08:00)

## 0. Princípios herdados (F2 §0 + F3 §0 + reversão — regem tudo abaixo)

1. **O estado do DagRun é decidido pelas FOLHAS** (lição E, PR #229) — a guardiã não toca o `etl_dag_factory`, nenhuma DAG gerada, nenhuma trigger_rule. Ver §1.3 para por que a própria guardiã é imune à lição.
2. **Chave estável desde o nascimento** (causa B): toda linha que a guardiã cria nasce com `execution_id` preenchido (`guardia__*` via `novo_run_id`); reserva com NULL é proibida por contrato (F2 §1).
3. **Contrato de leitura EXISTS**: a única pergunta de liberação é `liberado()` de `utils/dependencias.py` — a guardiã **importa a mesma função** que o push usa; nenhum predicado paralelo (é o contrato gravado na docstring do módulo: *"se a guardiã precisar de outra pergunta, ela entra AQUI"*).
4. **A rede de segurança não pode ser ruidosa** (causa D — *"rede que ninguém lê"*): todo evento é idempotente pelo índice `ux_dep_evento (pipeline, data_ref, tipo)` e todo alerta nasce de uma linha que EXISTE, nunca de uma data calculada por premissa própria.
5. Registro/alerta é observabilidade: **o ciclo nunca lança exceção por causa de UM pipeline** (try/except por item, D51) — mas o ciclo INTEIRO falhando falha a task, visível (a guardiã vermelha é informação, não vergonha).
6. Placeholder `%s` em toda a árvore `dags/` (pymssql — GOTCHA registrado).
7. Nenhum helper em `default_args`; DAG manuscrita não passa pelo `consts_str`/`helpers_str` da factory, mas o princípio vale.
8. Nenhum item mergeia sem os cenários de EXECUÇÃO no dev (regra de merge da suíte).

---

## 1. A DAG: forma, schedule e a lição E

### 1.1 Cabeçalho

```python
DAG(dag_id="etl_dependencia_guardia",
    schedule=f"*/{_intervalo()} * * * *",   # _intervalo(): Variable com clamp, §10
    start_date=pendulum.datetime(2026, 8, 1, tz=LOCAL_TZ),
    catchup=False, max_active_runs=1,        # ciclos nunca se atropelam (claims/eventos)
    tags=["dependencias", "guardia", "monitoramento"])
```

`_intervalo()` = `DEPENDENCIA_GUARDIA_INTERVAL_MINUTES` com **clamp 1..59 e default 5**; Variable ausente, `0`, `60` ou lixo **não derrubam o import** (try/except devolvendo 5) — D47, mesmo padrão do `etl_ds_monitor_centralizado` (`_get_interval`, l.325–329), com o teto 59 que lá falta (`*/60` é cron inválido). `execution_timeout = max(1, intervalo − 1)` minutos na task, para um ciclo travado não segurar o seguinte.

### 1.2 Estrutura de tasks: **UMA task (`ciclo`), as 4 responsabilidades em sequência dentro dela**

Espelho deliberado do `etl_ds_supervisao_monitor` (uma task `coletar`). Uma task por responsabilidade foi considerada e descartada:

- As responsabilidades têm **ordem obrigatória com estado compartilhado**: ordenar (1) cria as linhas que a rede (2) vai varrer; a rede dispara ANTES de o deadline (3) julgar (senão o ciclo alerta a corrida que ele mesmo ia disparar); divergência (4) lê o que sobrou. Em tasks separadas, cada fronteira vira latência de scheduler + snapshot divergente entre tasks — exatamente a classe de corrida que a retomada existe para não criar.
- Uma conexão pymssql por ciclo, transações curtas por operação (o claim exige commit imediato — docstring do módulo).
- Envio ao Teams **no fim do ciclo**, depois de toda a detecção, para o lote sair de uma vez e em ordem (padrão da supervisão, l.815–820).

### 1.3 Por que a lição E não a alcança (justificando as folhas)

A guardiã é **DAG utilitária manuscrita**: não tem `publish_dataset`, não tem dependentes, não publica Dataset, não é gerada pela factory (zero exposição ao gotcha consts-antes-de-helpers, D56). Seu grafo tem **uma task, que é a única folha** — não existe trigger_rule que possa rebaixar a folha portadora de falha, porque a folha É o ciclo: ciclo estourou exceção → task failed → DagRun FAILED, honesto e visível na UI. O `max_active_runs=1` + `catchup=False` garantem que a falha de um ciclo não represa ciclos (o próximo horário roda normalmente). Falha de UM pipeline dentro do ciclo não falha a task (princípio 5/D51) — a task só falha por quebra estrutural (banco fora o ciclo inteiro, bug), que é quando ficar vermelho é a resposta certa.

**Decisão 1 — uma task única, manuscrita, única folha, envio no fim** *(evita: corridas entre responsabilidades; a classe da lição E por construção — nenhuma folha para esconder; o try/except-fora-do-laço que na 1ª execução cancelava os demais dependentes, D51)*.

## 2. O relógio da guardiã: datas só do presente

### 2.1 Relógio de parede, não momento lógico — e por quê isso não fere o D10

A guardiã usa `agora = pendulum.now(LOCAL_TZ)` em tudo. O princípio D10 (momento lógico) vale para quem **carimba a própria corrida** — atraso de fila não pode mudar o rótulo de uma execução. A guardiã não tem corrida de negócio: é um **monitor do presente** (como a supervisão, que usa `datetime.now()`). Um ciclo atrasado 10 min deve agir sobre o mundo de AGORA — janela e deadline são de relógio por definição (F3 §3.4), e a data que ela deriva (§2.2) fica correta justamente por olhar o presente.

### 2.2 De onde vêm as datas — e a guarda de idade (D45)

**Proibição estrutural: a guardiã NÃO deriva datas varrendo o histórico de `etl_pipeline_execucao`.** Foi o `_datas_em_aberto` de 48h sem guarda de idade que fez a 1ª guardiã disparar datas passadas no instante em que uma dependência era cadastrada (N3/D45). Aqui, toda data de ordenação nasce de **um único cálculo**: `calcular(agora, virada_efetiva(predecessor))` — o mesmo `utils/data_referencia.calcular` da F2, com a virada do **PREDECESSOR** (coluna `hora_virada` ?? config global ?? 00:00). Por construção esse cálculo só produz **hoje ou amanhã** (virada 20:00 às 23:30 → amanhã), nunca uma data passada — a guarda de idade é a ausência do mecanismo que produzia passado, travada por teste de ausência (§12.9).

**"Corrente" fica definido assim**: a data corrente de uma corrida é a que a virada do predecessor produz sobre o agora. É a resposta ao D43 pela outra ponta — a guardiã não "calcula pela virada do dependente + relógio" (a cegueira da causa D): a virada do dependente é **irrelevante** sob herança (F3 §7); e as "datas em aberto que os predecessores realmente carimbaram" são as **linhas `AGUARDANDO_DEPENDENCIA` que existem** (criadas por New Day, push §3.4 ou devolução D16) — a rede (§4) opera sobre elas, não sobre datas imaginadas.

### 2.3 O dia operacional na guardiã: candidatos

Regras de DIA julgam o `dia_operacional` (F3 §1.1). Para uma corrida de virada `v > 00:00`, o dia de origem é ambíguo no corredor pós-meia-noite (o pai pode ter rodado ontem 23:30 ou hoje 01:00). A guardiã resolve com o helper **puro** novo:

```
candidatos_dia_operacional(agora, virada) -> list[date]
  virada == 00:00            → [hoje]
  agora.time() >= virada     → [hoje]              # corrida de amanhã, ordenada hoje
  senão                      → [hoje - 1, hoje]    # corredor pós-meia-noite
```

Um dependente é julgado `dia_permitido` se **algum** candidato passa; o candidato que passa (preferindo o mais antigo, que é o dia de origem provável) é o `dia_operacional` que vai no conf do disparo. Verificação contra o par D06/D07: virada 20:00, C `somente_dias_uteis` — sexta 21:00 (`D=sábado`, candidatos `[sexta]`) → ordena com dia_op sexta ✔; sábado 00:15 (`D=sábado`, candidatos `[sexta, sábado]`) → sexta passa → dispara com dia_op sexta, **o mesmo que o push do pai enviaria** ✔. Sábado 21:00 (`D=domingo`, candidatos `[sábado]`) → não ordena ✔.

**Decisão 2 — datas só de `calcular(agora, virada do predecessor)`; proibida varredura histórica para ordenar** *(evita: N3/D45 — disparo retroativo ao cadastrar dependência; a causa D — guardiã calculando por premissa própria e cega à corrida da meia-noite, D43)*.
**Decisão 3 — dia operacional por candidatos, preferindo o dia de origem** *(evita: reabrir D06/D07 pela mão da guardiã — o sweep pós-meia-noite com `dia_op=hoje` pularia a corrida de dias úteis que o push teria disparado certo)*.

## 3. Responsabilidade 1 — New Day: ordenar o dia (e fechar o anterior)

### 3.1 Universo: quem é "previsto"

```
dependentes = pipelines ATIVOS com ≥1 linha em etl_pipeline_dependencia (tipo='PIPELINE')
```

Para cada dependente C (try/except por item, D51):

1. **Dia do próprio C**: `dia_permitido(regras_dia de C, candidato)` para algum candidato (§2.3) — reusa `config_dependente` + `dia_permitido` já implementados (paridade por construção com o check_agenda do filho, espírito do D29). Reprovou → C não é previsto hoje; nada é criado. **É isso que mata o `JANELA_ESTOUROU` de fim de semana na raiz: sem linha, não há o que alertar (§5).**
2. **Data-alvo**: `D_p = calcular(agora, virada_efetiva(P))` para cada predecessor P. Se os `D_p` **divergem** entre si (viradas mal configuradas — risco 4 da spec), C **não é ordenado** e nasce evento `DATA_DIVERGENTE` (face de configuração, §7.1) com os pares `(P, D_p)` no detalhe, chaveado em `min(D_p)` (determinístico entre ciclos → idempotente). Convergiram → `D = D_p` comum.
3. **Expectativa dos predecessores (D44)**: P conta como *esperado em D* se `dia_permitido(regras de P, candidato)` para algum candidato **ou** P já tem linha em D com status `SUCESSO|EXECUTANDO|FALHA` (rodou/está rodando apesar da agenda — ex.: manual). `PULADO` sozinho **não** conta. Se **qualquer** P não é esperado, C não é ordenado (a condição não pode fechar em D — ordenar criaria a linha órfã eterna do D3/N11) — log `[GUARDIA] C não ordenado em D: P fora do dia`. Assim, sábado com pai `somente_dias_uteis` (que tem linha PULADO do cron, ou linha nenhuma): não ordena, não alerta — **D44 fechado**; pai pulado por **blackout** (dia permitido, linha PULADO): ordena, e o dia acaba em alerta — **QA5/D41 preservado**.
4. **Ordena**: `ordenar_corrida(conn, C, D, novo_run_id('guardia', D, C), 'guardia')` — linha `AGUARDANDO_DEPENDENCIA` **nasce com run_id `guardia__*`** (contrato linha-nasce-com-run_id; se o push adotar depois, o caminho (a) do claim dispara com esse mesmo run_id e atualiza `disparado_por` para o pai). `ordenar_corrida` é idempotente (NOT EXISTS não-PULADO) e **devolve bool**: `False` = já havia corrida (AGUARDANDO/EXECUTANDO/SUCESSO/FALHA) — a guardiã **não assume ordenação** e não escreve nada em cima (D48: violação/corrida existente não pode virar `JANELA_ESTOUROU` sobre corrida rodando).

### 3.2 Fechar o dia anterior — ver §6 (NAO_LIBEROU)

O fechamento roda **no início do ciclo, antes de ordenar** — New Day do Control-M: abre o dia novo fechando o velho.

**Decisão 4 — previsto = dia do dependente E expectativa de TODOS os predecessores** *(evita: D44/D3/N11 — linha órfã de fim de semana + alerta que ensina a operação a ignorar a guardiã; sem perder QA5/D41 — pai pulado por blackout/inativo/falho em dia devido continua terminando em alerta)*.
**Decisão 5 — viradas divergentes entre predecessores bloqueiam a ordenação e viram `DATA_DIVERGENTE`** *(evita: ordenar uma corrida que NUNCA fecharia numa data só — o "dependência nunca libera" do risco 4, agora com nome e card em vez de espera muda)*.

## 4. Responsabilidade 2 — rede de segurança do push

### 4.1 Varredura

Fonte: **as linhas `AGUARDANDO_DEPENDENCIA` existentes** (`corridas_aguardando(conn)` — função nova no módulo). Não há recorte de idade na LIBERAÇÃO: uma linha só existe se foi ordenada de propósito (New Day de hoje; push §3.4 na janela; devolução D16; reprocesso de data passada via push do pai re-rodado — F3 §7), e o fechamento do §6 limita quanto tempo ela pode viver. Para cada linha (try/except por item):

1. `lib, faltantes = liberado(conn, C, D)` — **a mesma função do push**, contrato EXISTS (D14/D20/D21: erro → não liberado). Não liberou → nada (o deadline §5 e a divergência §7 cuidam do resto do diagnóstico).
2. **Janela** `nao_iniciar_antes` (relógio de parede, F3 §3.4): `agora.time() < janela` → não dispara; a linha fica — é literalmente o "a guardiã dispara às 08:00" prometido no D22.
3. **Filho pausado no Airflow** (`DagModel.get_dagmodel(C).is_paused`): não dispara, log `[GUARDIA] C pausado — não disparado`; a linha permanece AGUARDANDO e o deadline (se configurado) alerta — fecha metade do risco "F3 sem F4: filho pausado sem alerta" (F3 §8) sem criar run `queued` eterno.
4. **Claim**: `reservar_corrida(conn, C, D, novo_run_id('guardia', D, C), 'guardia')` + commit imediato. O caminho (a) adota a linha AGUARDANDO e devolve **o run_id que a linha já tinha** — é exatamente a arbitragem push×guardiã do D18: os dois disputam a transição `AGUARDANDO→EXECUTANDO` sob UPDLOCK/HOLDLOCK e **exatamente um** vence (F3 §3.2, já implementado — a F4 não escreve SQL de claim, só chama). `None` → outra ponta venceu → nada, sem segundo disparo.
5. **Trigger**: `Client(None, None).trigger_dag(dag_id=C, run_id=<vencedor>, conf=montar_conf(D, dia_op_escolhido, 'guardia'))` — `dia_op_escolhido` pela Decisão 3. Exceção → `devolver_reserva(...)` com a guarda `inicio IS NULL` (F3 §3.3) + commit + log — e o ciclo **seguinte** re-tenta pela mesma varredura: é a metade F4 do **D16** ("a guardiã redispara no ciclo seguinte"), fechada sem código novo de retry — a varredura É o retry.

### 4.2 Resgate de reserva órfã (o buraco que a devolução não cobre)

`devolver_reserva` só roda quando o trigger LEVANTA. Worker morto (kill −9) **entre o commit do claim e o trigger** deixa `EXECUTANDO + inicio IS NULL` para sempre — invisível ao deadline (não é AGUARDANDO) e ao push (claim bloqueado). Resgate no ciclo: linhas `EXECUTANDO AND inicio IS NULL` com `atualizado_em` mais velho que `max(10 min, 2×intervalo)` **e sem DagRun correspondente no Airflow** (`DagRun.find(dag_id, run_id)` vazio) → `UPDATE ... SET status='AGUARDANDO_DEPENDENCIA'` com a MESMA guarda `status='EXECUTANDO' AND inicio IS NULL` (não reverte corrida adotada — eco da Decisão 5 da F3). DagRun existe (ex.: `queued` de filho pausado depois do trigger) → não mexe (a corrida é do Airflow; risco residual documentado em §10). A guarda de idade elimina o falso resgate na janela de milissegundos entre claim e trigger.

**Decisão 6 — a rede opera SÓ sobre linhas existentes e reusa claim/devolução da F3 intocados** *(evita: D18 — execução dupla; D50 — push perdido vira disparo no ciclo seguinte; e o retorno do disparo retroativo — a rede não inventa datas)*.
**Decisão 7 — resgate de reserva órfã com tripla guarda (inicio NULL + idade + DagRun inexistente)** *(evita: corrida presa em EXECUTANDO sem alerta — B3/D16 no único corner que a devolução da F3 não alcança; e o falso resgate de corrida viva)*.
**Decisão 8 — filho pausado não é disparado** *(evita: run `queued` eterno com linha EXECUTANDO órfã — troca um estado mudo por uma linha AGUARDANDO que o deadline sabe alertar)*.

## 5. Responsabilidade 3 — deadline (`hora_limite_dependencia`)

### 5.1 O instante do deadline tem âncora de DATA, não só de hora

`hora_limite` sozinha alertaria na hora errada para corrida de virada (linha de D=sábado criada sexta 21:00 com limite 02:00 NÃO pode alertar sexta 21:05). Helper **puro** novo:

```
instante_deadline(data_ref, hora_limite, virada) -> datetime
  virada == 00:00                → combine(data_ref, hora_limite)
  hora_limite >= virada          → combine(data_ref - 1, hora_limite)   # trecho pré-meia-noite do dia operacional
  senão                          → combine(data_ref, hora_limite)       # trecho pós-meia-noite
```

(o único instante com aquela hora dentro do dia operacional `[(D−1)@virada, D@virada)`). `virada` = a efetiva dos predecessores (a mesma que carimbou D).

### 5.2 A regra

Para cada linha `AGUARDANDO_DEPENDENCIA` cujo pipeline tem `hora_limite_dependencia NOT NULL` (**opt-in — decisão fechada §8 da spec: NULL = a guardiã NUNCA gera `JANELA_ESTOUROU` para ele**): se `agora >= instante_deadline(...)` **e** o instante cai no dia operacional corrente (deadline no passado — linha de reprocesso de data antiga — não alerta; log apenas): grava evento `JANELA_ESTOUROU` + card. **O pipeline fica PENDENTE — a linha continua `AGUARDANDO_DEPENDENCIA`, nada falha, nada é fechado aqui** (spec §3.3; aceite F4; o fechamento é do §6, em outro momento e por outra regra). Idempotente por `(C, D, 'JANELA_ESTOUROU')`: os 200 ciclos seguintes do dia não duplicam nem reenviam (D49).

**Detalhe do evento com as três mensagens do D46**, nesta ordem de teste (a ordem errada era o defeito D4 — o ramo "nenhum executou" saía quando todos tinham executado):

1. `liberado()` == True → `"liberado mas sem disparo — verifique DAG/scheduler"` (só alcançável se o disparo está falhando repetidamente);
2. algum predecessor tem linha em D → `"aguardando: P1, P2"` (os `faltantes` de `liberado`);
3. nenhum predecessor tem linha em D → `"nenhum predecessor executou em {D}"`.

### 5.3 Fim de semana (o D-histórico), fechado em duas camadas

O deadline **só avalia linhas que existem** — e a linha só existe se `dia_permitido` do dependente passou E os predecessores eram esperados (§3.1). Sábado sem malha prevista = zero linhas = zero `JANELA_ESTOUROU`, por construção. Não há segunda via: o deadline não calcula "quem deveria ter linha" (proibição do §2.2). D42/D44 cobertos sem nenhum `if fim_de_semana` ad-hoc.

### 5.4 A decisão adiada da F3 §9: deadline vira UNTIL?

A F3 registrou: *"deadline não bloqueia push — se quiser UNTIL à la Control-M, é decisão explícita na F4"*. **Proposta desta F4, com recomendação: o deadline CONTINUA só alerta; o UNTIL fino (bloquear disparo após a hora) NÃO entra.** Trade-off honesto:

- **Por não bloquear**: o caso que motivou a spec é a cadeia que atravessa a madrugada ATRASADA — um UNTIL na hora estrangularia exatamente ela, em silêncio operacional (o pior desfecho possível, F3 §9 já nomeava); o operador alertado pelo `JANELA_ESTOUROU` pode intervir (pausar o filho, não dar Clear no pai); e adicionar UNTIL depois é aditivo (flag opt-in por pipeline), enquanto removê-lo depois de adotado é quebra.
- **Por bloquear**: janela determinística de negócio ("depois das 9h o fechamento não pode mais rodar") — legítimo, mas raro e configurável no futuro.
- **O que a F4 entrega de UNTIL, de graça e na granularidade certa**: o fechamento `NAO_LIBEROU` do §6 é um UNTIL de **dia operacional** — depois que o dia fecha, a corrida não dispara mais automaticamente. Se o usuário precisar do UNTIL de hora, é decisão explícita futura com dono (coluna/flag nova + UI na F5), registrada no backlog.

**Decisão 9 — deadline ancorado em `instante_deadline`, opt-in, alerta-sem-falhar, idempotente** *(evita: D49; alerta na hora errada em corrida de virada; e o `JANELA_ESTOUROU` diário de pipeline sem deadline — "sem regra" ≠ "regra às 00:00", D35)*.
**Decisão 10 — deadline não vira UNTIL; o UNTIL de dia é o fechamento do §6** *(evita: estrangular a cadeia atrasada em silêncio — a decisão adiada da F3 §9 resolvida a favor do caso motivador da spec)*.

## 6. `NAO_LIBEROU` — o fim do ciclo de vida (contrato com a F9)

**Quando fecha**: uma linha `AGUARDANDO_DEPENDENCIA` fecha como `NAO_LIBEROU` quando **um dia operacional INTEIRO se passou desde a criação** — operacionalmente: no início de cada ciclo, fecham-se as linhas com `criado_em` anterior à **virada ANTERIOR** (a linha atravessou um New Day completo sem liberar) **e** que continuam não liberadas (`liberado()` == False) **e** sem predecessor `EXECUTANDO` na data. As três guardas têm dono:

- **Idade de um dia completo, não "meia-noite"**: fechar na virada mataria a cadeia noturna meramente LENTA (pai começa 23:00, termina 02:00 — a corrida que motivou a spec); com a folga de um dia operacional, o push das 02:00 adota a linha ainda AGUARDANDO pelo caminho (a) e a malha fecha sozinha.
- **`liberado()` == False**: linha velha porém LIBERADA não é fechada — é **disparada** pela rede (§4; rodar atrasado é o propósito da feature; o `JANELA_ESTOUROU` já alertou o atraso). "Não liberou" só pode significar literalmente que a condição nunca fechou.
- **Sem predecessor EXECUTANDO**: pai de 30h rodando não derruba o filho que o espera.

O fechamento grava `motivo` (os mesmos três diagnósticos do §5.2) e **evento `tipo='NAO_LIBEROU'`** + card — é o que fecha a parte "pulado/inativo" do **D41** quando não há deadline configurado (sem isso, pipeline sem `hora_limite` morreria mudo — o QA5 de volta). `JANELA_ESTOUROU` continua exclusivo do deadline opt-in (decisão fechada §8 respeitada). O tipo novo não exige DDL: `tipo` é VARCHAR(30) sem CHECK; o comentário da 067 lista três tipos e este desenho estende o domínio para quatro — registrado aqui e em comentário no código; a F9 já renderiza o **status** `NAO_LIBEROU` (roxo em `statusExecucao.ts`) e exibe eventos com `tipo` cru, então **painel e motor contam a mesma história sem mudança de front**.

**Consequências honestas, documentadas**: (i) linha `NAO_LIBEROU` **bloqueia claim futuro** naquela data (`status <> 'PULADO'` no NOT EXISTS) — SUCESSO tardio do pai (Clear dois dias depois) não redispara o filho automaticamente; reprocesso do dia fechado é gesto explícito do operador (trigger manual com `conf {"data_referencia": ...}`, que a F2 já aceita) — o mesmo comportamento do New Day do Control-M, que remove o job não rodado. (ii) `NAO_LIBEROU` é terminal para a guardiã: nenhum código a reabre.

**Decisão 11 — fechamento por idade de um dia operacional completo, com escape de liberação e evento próprio** *(evita: AGUARDANDO acumulando para sempre (o painel da F9 viraria mentira); a morte da cadeia noturna lenta que um fechamento na virada causaria; e o D41-sem-deadline mudo — nenhuma cascata morre sem aviso)*.

## 7. Responsabilidade 4 — `DATA_DIVERGENTE` (e `PREDECESSOR_FALHOU`)

### 7.1 `DATA_DIVERGENTE`: definição EXATA, nas duas únicas faces reais

O falso histórico (D1/N10: 200 dependentes = 200 cards/dia) vinha de procurar SUCESSO "em outra data" numa janela de ±3 dias — **o sucesso normal de ontem sempre está lá**. A definição que elimina o falso: divergência é quando o predecessor **trabalhou no dia operacional corrente** e ainda assim as datas não casam.

- **Face de configuração (na ordenação, §3.1-2)**: predecessores da MESMA corrida com viradas efetivas produzindo `D_p` distintos AGORA. Detalhe: `"viradas divergentes: P1→D1, P2→D2"`.
- **Face de execução (neste passo)**: dependente C com linha `AGUARDANDO` em D, e existe predecessor P **sem** SUCESSO em D mas **com** SUCESSO cujo `fim >= início do dia operacional corrente` (= a virada mais recente; carimbo em `fim`, nunca `criado_em` — D15) e `data_referencia <> D`. Ou seja: P rodou HOJE e carimbou outra data — virada errada em P ou disparo manual com data trocada. Detalhe **cita as duas datas** (aceite F4): `"aguarda {D}; {P} concluiu hoje com data_referencia={D'}"`. O SUCESSO de ontem tem `fim` anterior à virada corrente → **não dispara nada** (D42).

**Anti-reenvio e "reset entre dias"**: o índice `ux_dep_evento (pipeline, data_ref, tipo)` limita a **um evento/card por dependente por data de referência** — ciclos repetidos no mesmo dia não duplicam nem reenviam (D49); no dia seguinte a data muda e, se a causa persistir (virada continua errada), sai **um** novo card — que é o comportamento desejado de um problema ainda aberto, não ruído. Nenhum "reset" ativo é necessário: a chave natural o faz.

### 7.2 `PREDECESSOR_FALHOU`: o alerta que não pode esperar deadline

Dependente C `AGUARDANDO` em D com predecessor P que tem `FALHA` em D **e não tem** `SUCESSO` em D → evento `PREDECESSOR_FALHOU` + card, **imediato** (o deadline é opt-in; a FALHA é fato consumado e o dependente comprovadamente bloqueado — esperar seria reeditar o silêncio do QA5). Detalhe nomeia os predecessores falhados. Idempotente pela chave; se o plantonista der Clear e P virar SUCESSO, o push segue normal (D17) — o evento fica como histórico verdadeiro do dia. Diagnóstico usa a função nova `resumo_predecessores` (status por predecessor na data), que é **só para mensagens** — a decisão de liberação continua sendo exclusivamente `liberado()` (proteção do D29 gravada na docstring).

**Decisão 12 — divergência exige carimbo dentro do dia operacional corrente** *(evita: D42/D1/N10 — o card diário do sucesso normal de ontem, o defeito que tornou a 1ª guardiã ilegível)*.
**Decisão 13 — `PREDECESSOR_FALHOU` imediato, sem depender de deadline** *(evita: QA5 renascendo no pipeline sem `hora_limite`; e não espera o fim do dia para dizer o que já é certo)*.

## 8. Alertas Teams

- **Canal — decisão fechada §8 da spec ("reusa o canal da supervisão, sem grupo novo") materializada assim**: `SELECT TOP 1 g.id, g.webhook_url, g.nome FROM dbo.etl_msg_grupo g WHERE g.ativo=1 AND LTRIM(RTRIM(COALESCE(g.webhook_url,''))) <> '' AND EXISTS (SELECT 1 FROM dbo.etl_ds_supervisao_job s WHERE s.grupo_id=g.id AND s.ativo=1) ORDER BY (nº de jobs ativos que o usam) DESC, g.id` — o grupo que a supervisão **de fato** usa; empate resolvido deterministicamente. Sem grupo elegível → eventos ficam gravados (`notificado_em` NULL), card não sai, log `[GUARDIA] sem canal do Teams — eventos só no painel` uma vez por ciclo. **É a degradação que o harness previu**: no dev não há webhook real em `etl_msg_grupo` (regra do runbook §9) — o caminho degradado é o exercitado nos cenários. Canal dedicado próprio fica como decisão futura (F5/backlog), não desta fase.
- **Card**: função **pura** nova `montar_card_dependencia(evento) -> dict` em `utils/ds_teams.py` (mesmo Adaptive Card do canal; `ESTILO` ganha os tipos novos — `JANELA_ESTOUROU` ⏰ Warning, `DATA_DIVERGENTE` ⚠️ Warning, `PREDECESSOR_FALHOU` 🚨 Attention, `NAO_LIBEROU` 🚨 Attention). Corpo = `detalhe` do evento (a mensagem é renderizada na DETECÇÃO, com o contexto em mãos — padrão da supervisão) + FactSet: Pipeline, Data de referência, Detectado em. Transporte: `enviar_card` **intocado** — herda os dois contratos já pagos: `notificado_em` só após 2xx e **URL do webhook jamais em log** (D49).
- **Lote e fila**: eventos com `notificado_em IS NULL AND detectado_em >= DATEADD(day,-2,GETDATE())`, ordem `detectado_em`, `TOP (DEPENDENCIA_LOTE_NOTIFICACAO)` (default 50, clamp ≥1, lida por ciclo). A janela de 2 dias é constante comentada (mesma razão da supervisão: consertar um webhook não pode despejar semanas de alertas velhos; não criamos Variable além das duas da spec). Lote cheio → log explícito "restante sai no próximo ciclo" (corte silencioso passaria a impressão de que tudo saiu). Falha de envio não marca — o próximo ciclo re-tenta.

**Decisão 14 — canal derivado da supervisão + card puro + transporte reusado** *(evita: grupo novo que a decisão fechada proibiu; vazamento de URL; "avisei" no lugar de "tentei avisar"; e a inundação pós-conserto de webhook)*.

## 9. Paridade painel×motor e a API do módulo

**A guardiã importa as MESMAS funções que o push** — `dependentes_de`, `liberado`, `config_dependente`, `dia_permitido`, `reservar_corrida`, `ordenar_corrida`, `devolver_reserva`, `novo_run_id`, `montar_conf` — paridade **por identidade de objeto**, mais forte que port+teste. O que a F4 acrescenta entra **no mesmo módulo** (contrato da docstring: *"nenhuma consulta paralela"*), com docstrings no mesmo padrão:

```python
# puras
candidatos_dia_operacional(agora, virada) -> list[date]          # §2.3
instante_deadline(data_ref, hora_limite, virada) -> datetime     # §5.1

# banco (conn pymssql, %s; chamador dono da transação)
dependentes_com_dependencia(conn) -> list[str]                   # universo do New Day (§3.1)
predecessores_de(conn, pipeline) -> list[str]
virada_efetiva(conn, pipeline) -> time                           # hora_virada ?? config global ?? 00:00
corridas_aguardando(conn) -> list[(pipeline, data_ref, run_id, criado_em)]
resumo_predecessores(conn, pipeline, data_ref) -> dict[str, set[str]]  # SÓ diagnóstico/mensagem — nunca decide liberação (D29)
reservas_orfas(conn, idade_min) -> list[...]                     # §4.2
resgatar_reserva(conn, pipeline, data_ref, run_id) -> bool       # guarda EXECUTANDO + inicio IS NULL
fechar_nao_liberou(conn, pipeline, data_ref, run_id, motivo) -> bool   # guarda status='AGUARDANDO_DEPENDENCIA'
gravar_evento(conn, pipeline, data_ref, tipo, detalhe) -> bool   # INSERT WHERE NOT EXISTS na chave do ux_dep_evento
eventos_nao_notificados(conn, limite, janela_dias) -> list[...]
marcar_notificado(conn, evento_id) -> None
```

`config_dependente` ganha a chave `'hora_limite'` no dict (aditivo — o push a ignora; teste de não-regressão da F3 continua verde). **Contrato com a F5/D29 reafirmado**: quando o endpoint `/pipelines/dependencias/estado` nascer, porta `liberado` com **teste de paridade** (o precedente é `api/services/data_referencia.py` × `dags/`, F9). Teste estrutural nesta F4: `dags/etl_dependencia_guardia.py` **não contém SQL** sobre `etl_pipeline_execucao`/`etl_pipeline_dependencia`/`etl_dependencia_evento` (assert de ausência sobre o fonte) — toda pergunta mora no módulo.

**Decisão 15 — zero SQL na DAG; tudo em `utils/dependencias.py`, com as puras separadas** *(evita: N9/D29 — o painel/motor com predicados divergentes; e repete a arquitetura que fez F2/F3 serem testáveis sem Airflow)*.

## 10. Migrations, Variables, degradação e riscos

**Migrations novas: NENHUMA.** Conferido item a item: `etl_dependencia_evento` + `ux_dep_evento` (067-D) cobrem eventos e anti-reenvio; `NAO_LIBEROU` já é status documentado na 067 e renderizado pela F9; o tipo de evento novo cabe no VARCHAR(30) sem CHECK; `hora_limite_dependencia`/`nao_iniciar_antes`/`hora_virada` (067-C) e a config global (067-E) existem; a 072 (run_id 250) cobre `guardia__*` (~100 chars). Duas pendências registradas, **sem bloquear**: (i) expurgo/retenção de `etl_pipeline_execucao` e `etl_dependencia_evento` não existe — volume baixo (linhas ∝ corridas/dia), decisão de retenção fica para depois do deploy validado (§10 da spec já acumula a limpeza do CSV); (ii) a varredura por `status='AGUARDANDO_DEPENDENCIA'` não tem índice dedicado (o `ix_pipe_exec_cond` abre por pipeline) — scan barato no volume atual; índice `(status, data_referencia)` só se a tabela crescer.

**Variables (todas com default; nenhuma derruba import — D47):**

| Variable | Default | Clamp | Lida |
|---|---|---|---|
| `DEPENDENCIA_GUARDIA_INTERVAL_MINUTES` | 5 | 1..59 | no parse (schedule) |
| `DEPENDENCIA_LOTE_NOTIFICACAO` | 50 | ≥1 | por ciclo |
| `DEPENDENCIA_MSSQL_CONN_ID` | `SQL14_DMDB41` | — | por ciclo (mesmo padrão `DS_MONITOR_MSSQL_CONN_ID`; no dev já aponta para `orquestra_dev` via compose) |

**Degradação sem a 067 (D52)**: primeiro passo do ciclo = `OBJECT_ID` das três tabelas (`etl_pipeline_dependencia`, `etl_pipeline_execucao`, `etl_dependencia_evento`); qualquer ausência → `[GUARDIA] migration 067 ausente — ciclo encerrado` e **retorno limpo** (task verde, log explícito — o contrato F2 §6; nunca o except mudo do GOTCHA do placeholder).

| Risco | Mitigação |
|---|---|
| Guardiã fora do ar | O push (F3) é o caminho principal e independe dela; ao voltar, New Day/varredura recuperam o dia corrente (datas só do presente — nada retroativo) |
| Guardiã fora do ar durante TODO o corredor `[virada, meia-noite)` de uma corrida de virada, com pai também morto | Janela estreita (ciclos de 5 min); os candidatos do §2.3 ordenam no pós-meia-noite quando as regras de dia do filho permitem; limitação residual documentada |
| Contenção HOLDLOCK claim×push | Transações mínimas + commit imediato (contrato do módulo); perdedor loga e segue (D18) |
| Filho pausado APÓS o trigger (run `queued`, linha EXECUTANDO `inicio` NULL com DagRun existente) | Fora do resgate §4.2 de propósito (a corrida é do Airflow); visível como EXECUTANDO no painel; residual documentado |
| Evento correto, card perdido (webhook fora) | `notificado_em` NULL → re-tenta a cada ciclo por 2 dias; painel F9 mostra o evento desde o 1º ciclo |
| Mudar `hora_virada` com linha aberta | Linha antiga fecha `NAO_LIBEROU` no prazo do §6; `DATA_DIVERGENTE` §7.1 aponta a causa (mesma limitação assumida na F2 §5) |

## 11. O que a F4 NÃO faz

- **Não toca o `etl_dag_factory` nem nenhuma DAG gerada** — deploy da F4 **não exige regerar DAGs** (as mudanças em `utils/dependencias.py` são aditivas; teste de não-regressão da F3 prova).
- Não cria UI nem endpoint (F5/F9 — a F9 já lê `etl_pipeline_execucao`/`etl_dependencia_evento` e renderiza `NAO_LIBEROU`); não aposenta SP/CSV/`trigger_por_dependencia` (F6 + migration de limpeza §10 da spec).
- Não bloqueia push por deadline (Decisão 10 — UNTIL de hora é backlog com dono); não redispara FALHA (Clear é do plantonista — D17); não reabre `NAO_LIBEROU`; não faz backfill nem reprocesso em massa (OUT da spec §2); não trata OR/job→job (§2/§9 da spec).
- Não julga hora de agendamento de ninguém (a hora de evento morreu na F3; o piso é `nao_iniciar_antes`); não decide liberação por nada além de `liberado()`.
- Não expurga histórico (pendência registrada §10) e não cria canal/config de Teams próprios (decisão fechada §8).

## 12. Testes unitários (pytest; banco stubado — aceite F4; puras sem stub)

1. `candidatos_dia_operacional`: matriz virada 00:00/20:00 × antes/depois da virada × pós-meia-noite (§2.3, casos D06/D07 numerados).
2. `instante_deadline`: limite ≥ virada / < virada / virada 00:00; âncora nunca no dia errado (§5.1).
3. **New Day**: universo (ativo+dependência); C fora do dia não ordena; predecessor não-esperado bloqueia (D44); PULADO não conta como esperado; viradas divergentes → não ordena + evento (Decisão 5); `ordenar_corrida` False → nenhum efeito colateral (D48); run_id `guardia__*` ≤250.
4. **Guarda de idade (D45)**: ausência estrutural — nenhuma função da guardiã seleciona datas de `etl_pipeline_execucao` para ORDENAR (teste de ausência no fonte, como o D15 fez com `criado_em`); dependência recém-cadastrada com histórico velho → ciclo stubado não produz INSERT nem trigger para data < corrente.
5. **Rede**: liberado→claim→trigger na ordem; janela segura (D22); pausado não dispara; trigger levanta → `devolver_reserva` com os args certos; perdedor do claim não dispara (D18); try/except por item — 1º explode, 2º dispara (D51).
6. **Resgate**: só com `inicio IS NULL` + idade + DagRun ausente; DagRun existente não resgata.
7. **Deadline**: NULL nunca alerta; pendente-não-falha (nenhum UPDATE de status no caminho do deadline); as **três mensagens alcançáveis** cada uma no seu cenário (D46, com o anti-teste do D4: todas executadas ≠ "nenhum executou"); deadline no passado não alerta.
8. **NAO_LIBEROU**: fecha só com idade + não-liberada + sem EXECUTANDO; liberada velha vai para disparo, não fechamento; terminal.
9. **Eventos**: `gravar_evento` idempotente (2ª chamada False); `DATA_DIVERGENTE` exige `fim >= virada corrente` (sucesso de ontem NÃO gera — D42) e detalhe com as duas datas; `PREDECESSOR_FALHOU` só com FALHA sem SUCESSO na data.
10. **Teams**: `montar_card_dependencia` pura com os 4 tipos; lote corta e loga; `notificado_em` só após 2xx; motivo de erro sem URL; sem canal → nada enviado, eventos intactos.
11. **DAG**: import com Variable ausente/lixo/0/60 → intervalo 5 (D47); `max_active_runs=1`, `catchup=False`, uma task; **zero SQL no fonte da DAG** (Decisão 15); sem 067 → ciclo limpo (D52).
12. **Não-regressão F3**: suíte existente verde (utils aditivo; `config_dependente` com chave nova não quebra o push).

## 13. Cenários de EXECUÇÃO no dev (Airflow :8082 + `orquestra_dev`, runbook `docs/retomada-harness-dev.md`) — SELECT + UI do Airflow em cada um

**Modo de execução — decidido**: a guardiã nasce PAUSADA no dev (`DAGS_ARE_PAUSED_AT_CREATION`); os cenários determinísticos usam **trigger manual da guardiã via REST** (um ciclo por assert, sem corrida com o relógio dos SELECTs — mesmo fluxo do §5 do runbook); os dois cenários de **corrida/ruído** (E5, E9) rodam com a guardiã **DESPAUSADA e `DEPENDENCIA_GUARDIA_INTERVAL_MINUTES=1`**, porque disputa e silêncio prolongado só se provam com o ciclo de verdade. Sem webhook real (regra §9 do runbook): os asserts de Teams são sobre `notificado_em`/log degradado.

| # | Cenário | Prova |
|---|---|---|
| E1 | Malha HARNESS A→C prevista; ciclo manual → linha `AGUARDANDO_DEPENDENCIA` com run_id `guardia__*`; 2º ciclo não duplica | New Day, D48 |
| E2 | Pai `somente_dias_uteis` num sábado (simulado por `dias_semana` do dia errado): ciclo NÃO ordena C, zero evento | **D44** |
| E3 | Cadastrar dependência nova com SUCESSOs velhos na tabela → ciclo → ZERO linha/disparo retroativo | **D45** |
| E4 | Pai conclui com push sabotado (filho sem DAG no disco → devolução F3); restaurar o arquivo; ciclo seguinte da guardiã dispara C | **D16** (metade F4), **D50** |
| E5 | Pai terminando no instante do ciclo (guardiã despausada, intervalo 1): UMA execução de C, um vencedor no claim | **D18** |
| E6 | `nao_iniciar_antes` = agora+3 min, condição fecha antes: push segura (F3), ciclos seguram, primeiro ciclo após a hora dispara | **D22** |
| E7 | Predecessor não roda; `hora_limite` = agora+2 min → evento `JANELA_ESTOUROU`, C segue AGUARDANDO (**não falha**), ciclos repetidos = 1 evento e 0 duplicata | **D41, D49** |
| E8 | Viradas divergentes entre P1 e P2 → `DATA_DIVERGENTE` citando as duas datas; corrigir a virada → dia seguinte sem evento | **D43-face, D42** |
| E9 | Malha saudável, guardiã despausada por ≥1h de ciclos → ZERO evento/linha falsa (`SELECT COUNT(*)` antes/depois) | **D42** (anti-ruído) |
| E10 | `sp_rename` na 067 → ciclo VERDE com log da migration; restaurar → ciclo volta ao normal | **D52** |
| E11 | Linha AGUARDANDO com `criado_em` retrodatado (UPDATE de fixture) além da virada anterior → fecha `NAO_LIBEROU` + evento; F9 (`/malhas/.../execucao`) mostra o roxo; pai com SUCESSO tardio NÃO redispara | §6, contrato F9 |
| E12 | Pai FALHA (`sp_harness_falha`) → `PREDECESSOR_FALHOU` imediato; Clear do pai → push dispara C (evento fica como histórico) | **D41**-falhou, D17 |
| E13 | Reserva órfã fabricada (UPDATE p/ EXECUTANDO `inicio` NULL retrodatado, sem DagRun) → resgate → AGUARDANDO → dispara | §4.2 |
| E14 | Filho pausado: ciclo NÃO dispara (log), linha fica AGUARDANDO; despausar → próximo ciclo dispara | Decisão 8 |
| E15 | Virada 20:00: ciclo às 21h ordena D=amanhã (dia_op hoje); ciclo pós-meia-noite não duplica; filho `somente_dias_uteis` disparado pelo sweep no sábado 00:15 RODA (dia_op sexta) | §2.3, D06/D07 na mão da guardiã |

## 14. Mapa decisão → defeito histórico

| Decisão | Defeito que evita |
|---|---|
| 1. Task única manuscrita, única folha | lição E (nenhuma folha a esconder); try/except-fora-do-laço (D51); latência/snapshot entre responsabilidades |
| 2. Datas só de `calcular(agora, virada do predecessor)`; sem varredura histórica | N3/D45 (disparo de datas passadas ao cadastrar); causa D (premissas próprias de data; cegueira à meia-noite — D43) |
| 3. Dia operacional por candidatos | reabertura de D06/D07 pelo sweep pós-meia-noite |
| 4. Previsto = dia do dependente E expectativa de todos os predecessores | D44/D3/N11 (linha órfã + alerta de fim de semana) sem perder QA5/D41 |
| 5. Viradas divergentes bloqueiam ordenação + evento | risco 4 ("nunca libera") mudo |
| 6. Rede só sobre linhas existentes; claim/devolução da F3 intocados | D18 (execução dupla); D50 (push perdido); redisparo retroativo |
| 7. Resgate de órfã com tripla guarda | B3/D16 (corrida presa em EXECUTANDO sem alerta) |
| 8. Filho pausado não dispara | run queued eterno + EXECUTANDO órfão |
| 9. Deadline ancorado, opt-in, pendente-não-falha, idempotente | D49; alerta na hora errada em corrida de virada; alerta diário de "regra às 00:00" |
| 10. Deadline ≠ UNTIL; UNTIL de dia = fechamento §6 | cadeia atrasada estrangulada em silêncio (decisão adiada F3 §9, resolvida) |
| 11. NAO_LIBEROU por dia operacional completo, com escapes | painel mentiroso por AGUARDANDO eterno; morte da cadeia noturna lenta; D41 mudo sem deadline |
| 12. Divergência exige carimbo do dia corrente | D42/D1/N10 (o card diário falso — 200/dia) |
| 13. PREDECESSOR_FALHOU imediato | QA5 renascendo em pipeline sem deadline |
| 14. Canal derivado da supervisão; card puro; transporte reusado | grupo novo proibido; URL em log; inundação pós-conserto |
| 15. Zero SQL na DAG; tudo em utils | N9/D29 (painel × motor divergentes) |

**Arquivos tocados na implementação:** `dags/etl_dependencia_guardia.py` (novo), `dags/utils/dependencias.py` (funções novas §9), `dags/utils/ds_teams.py` (`montar_card_dependencia` + `ESTILO`), `tests/` (novos + baseline). **Nenhuma migration.** PR: `feat: guardiã de dependências com janela e alerta` (retomada F4). Deploy: 067+072 aplicadas → F2/F3 no ar (DAGs já regeradas) → subir `dags/` → **despausar `etl_dependencia_guardia`** (nasce pausada) → acompanhar 1 dia com o par de pipelines de teste antes da malha inteira — sem `force_all` nesta fase (factory intocado).
