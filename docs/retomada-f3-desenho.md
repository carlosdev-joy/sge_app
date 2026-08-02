# Desenho técnico — F3: liberação por condição e disparo imediato (push)

Spec: `docs/spec-dependencias-pipelines.md` §3 e §5-F3 · Base: main `1cde745` (F2 + fix StoredProc) · Escopo: `dags/etl_dag_factory.py` + `dags/utils/dependencias.py` (novo) + testes · **Zero migration nova** (a 072 já na main é pré-requisito) · Suíte-contrato: `docs/retomada-aceitacao.md` — itens de F3: D01–D08, D12–D17, D19–D23, D55 (+ antecipação parcial de D36–D38)

## 0. Princípios herdados (F2 §0 + reversão, regem tudo abaixo)

1. **O estado do DagRun é decidido pelas FOLHAS** (lição E, PR #229): a F3 não muda trigger_rule de NENHUMA task, não cria folha nova e não pendura nada downstream de `t_publish_dataset`. O conjunto de folhas da DAG gerada é **byte-idêntico ao da F2**.
2. **Chave estável desde o nascimento** (causa B): linha em `etl_pipeline_execucao` nasce com `execution_id` preenchido; reserva com NULL é proibida (o índice `ux_pipe_exec` nem a comporta — dois NULL na mesma chave colidem no SQL Server).
3. **Contrato de leitura EXISTS** (F2 §9): liberação é `EXISTS(pipeline=P AND data_referencia=D AND status='SUCESSO')` — nunca "linha mais recente", nunca `COALESCE(inicio, criado_em)` (D14, D15).
4. Helpers não entram em `default_args` (`test_default_args_nao_referencia_helper` segue verde).
5. Disparo é orquestração, mas **falha no disparo nunca derruba o pai** (D23) e **degradação nunca é silêncio de gravação com task verde** (GOTCHA do placeholder): tudo logado com prefixo `[DEP]`.
6. Placeholder `%s` em toda a árvore `dags/` (pymssql — GOTCHA registrado).
7. Comentário no código GERADO não cita identificador de trigger_rule/schedule (quebra assert de substring — padrão que se repetiu 3×).
8. Nenhum item mergeia sem os cenários de EXECUÇÃO no dev (regra de merge da suíte).

---

## 1. Causa-raiz A — a decisão de produto central: evento × relógio

### 1.1 Três conceitos, três papéis

| Conceito | O que é | Quem define |
|---|---|---|
| `data_referencia` (ODATE) | **Rótulo de junção** da corrida — a chave que une pai e filhos. NÃO é "o dia em que a malha roda" | `_data_referencia` da F2 (herança > cálculo pela virada) |
| **`dia_operacional`** (novo) | O dia de calendário em que a corrida foi **ordenada na origem** — o dia contra o qual regras de DIA são julgadas | Origem cron: `date(data_interval_end em LOCAL_TZ)`; disparo por evento: **herdado via conf**; manual: conf > momento lógico |
| Origem do disparo | Taxonomia explícita: `agenda` (scheduled) · `manual` · `dep` (`dep__*`) · `guardia` (`guardia__*`, F4) · `dataset` (legado) | Helper gerado `_origem_disparo(context)` — substitui o sniffing `run_id.startswith('manual')` |

**Por que `dia_operacional` existe (a decisão nº 1 deste desenho).** D06 e D07 são incompatíveis se a regra de dia julgar uma coisa só:

- D06 (pai sexta 23:30, filho sábado 00:10, mesma corrida → LIBERA): julgar o **relógio** do filho (sábado) pula — errado. Com virada 00:00, julgar a `data_referencia` herdada (sexta) libera — certo.
- D07/N4 (virada 20:00, disparo sexta 23:30 carimba SÁBADO → não pode pular): julgar a `data_referencia` (sábado) pula — foi exatamente a regressão que a correção A introduziu no caso que dizia resolver.

O invariante que satisfaz os dois: **regras de DIA falam do dia em que a malha RODA, não do rótulo ODATE**. A virada é um artifício de junção (decisão nº 1 do usuário: herança para costurar a corrida que cruza a meia-noite), não uma re-rotulação do dia de negócio. Logo: o julgamento de dia acontece contra o `dia_operacional`, que a origem calcula UMA vez (momento lógico, nunca relógio de parede — imune a atraso de fila, princípio do D10) e a cadeia **herda** junto com o ODATE. Em D06 (virada 00:00) `dia_operacional == data_referencia` — o texto do item é satisfeito literalmente no cenário dele; em D07 eles divergem e é o `dia_operacional` (sexta) que decide. Este refinamento fica registrado aqui para o executor da suíte ler D06 como "a data da corrida, não o relógio".

### 1.2 A semântica: dependência + agenda = **AND no DIA; a HORA não se aplica a evento**

Pipeline com dependência tem `schedule=None` (spec). O push marca a elegibilidade da corrida; o `check_agenda` do filho continua julgando o **DIA** (restrições de dia sobrevivem — D04) e **deixa de julgar a HORA** em disparo por evento (evento é "quando liberou", não "que horas são" — D03). O piso de horário de um dependente é `nao_iniciar_antes` (é para isso que a coluna existe); a lista de horários/hora do agendamento vira configuração inerte para quem tem dependência — coerente com a F5, que já tratava dependência como substituta do agendamento no passo Agendamento.

### 1.3 Mapa regra a regra do `_check_agenda_regras` (fonte atual: l.1492–1544 do factory)

| Regra (hoje) | Hoje mede | Sob `agenda` (cron) | Sob `dep`/`guardia` | Sob `manual` | Fecha |
|---|---|---|---|---|---|
| `HORARIOS_ESPECIFICOS` (l.1498, isenta `manual*`) | hora do momento lógico | igual hoje | **não se aplica** (regra de relógio é só de cron) | isenta (igual hoje) | **D03** — era PULADO em 100% dos disparos; `dep__*` não começa com `manual` e caía na regra |
| `DIAS_HORARIOS_MES` — parte HORA (l.1507) | hora do momento lógico | igual hoje | **não se aplica** | isenta | **D03** |
| `DIAS_HORARIOS_MES` — parte DIA | dia (implícito no cron) | julga `dia_operacional ∈ dias` | julga `dia_operacional ∈ dias` | julga | **D04** (um dos 2 tipos que a correção A esqueceu) |
| **`RESTRICAO_DIA` (novo)** — weekly `schedule_dow`, monthly `schedule_dom`, biweekly `d,d+15`, `dias_semana` CSV | hoje só existe no cron (evapora com `schedule=None`) | julga `dia_operacional` (redundante com o cron, inofensivo e uniforme) | **julga `dia_operacional`** | julga | **D04** (fechamento mensal dia 5 roda SÓ dia 5, nunca 30×/mês; `dias_semana` incluído — o outro tipo esquecido) · **D05** (derivação com `is not None`, nunca `int(x or 1)`: dow=0 é domingo; conversão cron-dow 0/7=domingo → weekday() 6 explícita e testada) |
| `SOMENTE_DIAS_UTEIS` (l.1529, `pendulum.now`) | **relógio de parede** | julga `dia_operacional` (= data do momento lógico; atraso de fila que vira a meia-noite deixa de pular — melhoria deliberada, princípio D10) | julga `dia_operacional` **herdado** | julga (conf > hoje) | **D06** (sexta→sábado 00:10 LIBERA) · **D07** (virada 20:00 sexta 23:30 NÃO pula) |
| `CALENDARIO_NOME` (l.1532, `GETDATE()`) | relógio | consulta `etl_calendario` com `data = dia_operacional` (parametrizada, não `CAST(GETDATE())`) | idem | idem | **D06** |
| Blackout (l.1518, `GETDATE()`) | relógio | **relógio, sem mudança** — freeze operacional é sobre "agora", em qualquer origem | relógio | relógio | **D08** (de propósito, não regride) |
| `nao_iniciar_antes` | (não existe no check) | n/a | **é gate do PUSH, não do check** (§3.4) | não bloqueia manual | D22 (parcial; completa na F4) |

Ordem no `_check_agenda_regras` gerado: hora (só `agenda`) → `RESTRICAO_DIA`/dia (puro, sem banco) → blackout → dias úteis → calendário — cada saída com `motivo` próprio (padrão F2, D58 não regride). D09–D11 (F2) não são tocados; D12 fecha pela herança do §7.

**Decisão 1** — dia_operacional herdado + regras de dia sempre / regras de hora só em cron *(evita D03, D04, D05, D06, D07 simultaneamente — o cemitério da 1ª execução)*.
**Decisão 2** — taxonomia explícita `_origem_disparo` no lugar de `startswith('manual')` *(evita a pergunta "dep__ cai onde?" virar comportamento acidental; `dataset` legado só existe em DAG antiga não regerada, que mantém o código antigo)*.

## 2. O disparo: onde vive e como avalia

### 2.1 Onde vive: **dentro do callable do `publish_dataset`, sem task nova**

`_registrar_sucesso` (l.1486–1490) passa a: (1) gravar `SUCESSO` (como hoje, commit próprio); (2) chamar `_disparar_dependentes(context)` — corpo inteiro em try/except que **nunca levanta**, e try/except POR candidato dentro (D23).

Por quê, respondendo à pergunta da lição E ("como disparar só em sucesso sem virar o ALL_DONE assassino?"):

- O gate de sucesso **já existe**: é a própria trigger rule do `publish_dataset` (default, ou `NONE_FAILED_MIN_ONE_SUCCESS` com decisão — intocada). Falha → publish `upstream_failed` → sem push. Decisão-ramo-vazio → publish `skipped` → sem push e a corrida fecha `PULADO` no `flow_close` (D55 revalidado na mesma matriz). Nenhuma trigger rule nova, nenhuma folha nova: os testes de folha da F2 (parser de `dep_lines`) permanecem válidos sem emenda — a F3 é invisível para D53/D54 por construção.
- **Ordem garantida sem corrida**: o `SUCESSO` do pai precisa estar COMMITADO antes da avaliação do EXISTS (o candidato tem o próprio pai entre as deps). No mesmo callable, "commit → avaliar" é sequência, não corrida. Uma task paralela `t_disparar_dependentes` disputaria com o write do publish e perderia disparos de forma intermitente.
- Alternativas descartadas: (a) task downstream do publish — rebaixa a folha que carrega a falha a nó interno e quebra o teste "nada downstream de publish" da F2; (b) task paralela — a corrida de leitura acima; (c) engolir tudo numa task com ALL_DONE — o assassino da reversão.

Sequência interna por candidato: pré-filtro de dia → condição EXISTS → janela → reserva (claim) → `trigger_dag` → devolução em exceção. `_disparar_dependentes` roda mesmo que o write de SUCESSO tenha degradado (a avaliação é autocontida; sem o próprio SUCESSO no banco, a condição não fecha e nada dispara — sem mentira). Sem a 067, primeiro passo `OBJECT_ID` → log `[DEP] migration 067 ausente` e retorno (padrão F2 §6).

**Decisão 3** — push dentro do publish, depois do commit do SUCESSO *(evita: DagRun verde escondendo falha — nenhuma mudança de folha/trigger; corrida SUCESSO×EXISTS; e o "pai vermelho por bug do disparo" — D23)*.

### 2.2 Como lê `ix_dep_predecessor` e avalia a condição

```sql
-- candidatos (seek em ix_dep_predecessor, 067 l.132-140):
SELECT d.pipeline_name FROM dbo.etl_pipeline_dependencia d
JOIN dbo.etl_pipeline p ON p.pipeline_name = d.pipeline_name
WHERE d.depende_de = %s AND d.tipo = 'PIPELINE' AND p.active = 1

-- condição de C na data D (contrato §9 da F2; serve-se de ix_pipe_exec_cond):
SELECT dd.depende_de FROM dbo.etl_pipeline_dependencia dd
WHERE dd.pipeline_name = %s AND dd.tipo = 'PIPELINE'
  AND NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao e
                  WHERE e.pipeline_name = dd.depende_de
                    AND e.data_referencia = %s AND e.status = 'SUCESSO')
```

Lista vazia → **todas** satisfeitas → liberado; lista não vazia → log `[DEP] {C} aguardando: {faltantes}` e nada (quem completar por último dispara — D19). `tipo='JOB'` ignorado (spec §9). Grafia: a 071 canonizou a tabela — o `pipeline_name` lido É o `dag_id` real; `DagNotFound` no trigger vira devolução + log, nunca exceção do pai.

- Qualquer exceção na consulta → candidato tratado como NÃO liberado (D21: erro nunca vira "pode disparar").
- FALHA, EXECUTANDO, PULADO, ausência e SUCESSO em outra data não liberam (D20); PULADO intercalado não mascara (D14); nenhuma ordenação por `criado_em` em lugar nenhum da F3 (D15 — guardado por teste de ausência).
- O pai **não tem lista de filhos no código gerado** — lê a tabela ao vivo: cadastrar dependente novo passa a valer no próximo fim do pai SEM regerar o pai (só o filho precisa de regeração, pelo `schedule=None`).
- O pré-filtro de dia usa o MESMO predicado puro `dia_permitido` que o `check_agenda` do filho executa (§6) com o MESMO `dia_operacional` que irá no conf — paridade por construção (espírito do D29). O filho re-julga de qualquer forma (defesa em profundidade: pusher errado → PULADO honesto, nunca execução indevida). Blackout NÃO é pré-filtrado (é sobre o "agora" do filho, e a corrida devida merece linha PULADO visível).

## 3. Reserva e corrida: o protocolo de claim

### 3.1 Por que o índice único NÃO é o árbitro

`ux_pipe_exec` = `(pipeline, data_referencia, execution_id)`. Dois pais terminando juntos calculariam run_ids DIFERENTES — dois INSERTs não colidem no índice. O árbitro tem de ser uma condição sobre `(pipeline, data_referencia)` sozinha, e ela não é única por design (N linhas/dia é legítimo). Logo: **lock otimista por rowcount, com anti-corrida serializable**, numa função única de `dags/utils/dependencias.py` usada por push e (F4) guardiã.

### 3.2 `reservar_corrida(conn, filho, data_ref, novo_run_id, origem) -> run_id | None`

Transação curta e dedicada (fora da tx do SUCESSO):

```sql
BEGIN TRAN
-- (a) adotar linha ordenada, se existir (F4 New Day; ou janela §3.4):
UPDATE e SET e.status='EXECUTANDO', e.disparado_por=%s, e.atualizado_em=GETDATE()
OUTPUT inserted.execution_id
FROM dbo.etl_pipeline_execucao e WITH (UPDLOCK, HOLDLOCK)
WHERE e.pipeline_name=%s AND e.data_referencia=%s
  AND e.status='AGUARDANDO_DEPENDENCIA';
-- rowcount 1 → venci; run_id do trigger = execution_id QUE A LINHA JÁ TINHA

-- (b) senão, criar a reserva já com run_id (contrato F2 §1):
INSERT INTO dbo.etl_pipeline_execucao
      (pipeline_name, data_referencia, execution_id, status, disparado_por)
SELECT %s, %s, %s, 'EXECUTANDO', %s
WHERE NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao WITH (UPDLOCK, HOLDLOCK)
                  WHERE pipeline_name=%s AND data_referencia=%s
                    AND status <> 'PULADO');
-- rowcount 1 → venci; 0 → corrida já existe (EXECUTANDO/SUCESSO/FALHA/AGUARD.) → não disparo
COMMIT
```

- **Quem ganha a corrida de dois pais juntos:** cada um avalia DEPOIS do próprio commit de SUCESSO, então pelo menos o último a commitar vê a condição completa; se ambos veem, o `HOLDLOCK` (range lock) serializa o `NOT EXISTS`+INSERT — exatamente um rowcount=1. Idem push×guardiã no mesmo instante, disputando a transição `AGUARDANDO_DEPENDENCIA→EXECUTANDO` do caminho (a) — é literalmente a arbitragem que o D18 exige.
- **INSERT direto em `EXECUTANDO`, não AGUARDANDO:** no caminho quente o trigger sai na sequência; `AGUARDANDO` nasce só quando se ordena SEM disparar (§3.4 janela; F4 New Day). Reserva claimada distingue-se de corrida adotada por `inicio IS NULL` (o `check_agenda` do filho, ao adotar pela MESMA chave, carimba `inicio=GETDATE()` — F2 l.1420-1422).
- **`PULADO` não bloqueia claim** (`status <> 'PULADO'` no NOT EXISTS): um PULADO de blackout/dia não pode matar a corrida para sempre — eco do D15. Consequência elegante: filho pulado por blackout consome a reserva virando PULADO na MESMA linha, e um re-push posterior (Clear do pai) pode reclamar com run_id novo.
- **Uma corrida de dependente por ODATE via push** (decisão de produto): pai 3×/dia dispara o filho UMA vez por `data_referencia` (D14: o 2º/3º SUCESSO encontra a corrida existente e não redispara). É a semântica de condição consumida do Control-M e a barreira final contra qualquer "30×/mês". FALHA do filho também bloqueia re-push: rerun de filho falhado é decisão do plantonista via Clear (D17: Clear re-roda a MESMA linha, vira SUCESSO e o publish do filho empurra a cadeia adiante), nunca automatismo.
- **Ciclo é impossível também em runtime:** mesmo que um ciclo escapasse do BFS da F1 (D24 guarda), A→B→A morre no claim — quando o push voltasse a A, (A, D) já tem linha não-PULADO.

### 3.3 run_id calculado ANTES + trigger + devolução

- Formato: `dep__{data_ref AAAA-MM-DD}__{pai[:60]}__{AAAAMMDDTHHMMSSffffff}` (~100 chars; cabe no VARCHAR(250) da 072 — a migration existe exatamente para isso; teste garante ≤250 e ausência de `[:50]`). Prefixo `dep__` é o marcador da taxonomia §1; `guardia__` fica reservado para a F4.
- Trigger: `airflow.api.client.local_client.Client(None, None).trigger_dag(dag_id=filho, run_id=<o run_id da reserva>, conf={...§7})` — padrão de produção provado em `dags/etl_sequence_import_approve.py:206-212`, no mesmo worker.
- **Devolução (D16):** só quando `trigger_dag` LEVANTA (DAG não serializada, DagNotFound, banco do Airflow fora). Caminho (b): `DELETE ... WHERE execution_id=%s AND status='EXECUTANDO' AND inicio IS NULL`; caminho (a): `UPDATE ... SET status='AGUARDANDO_DEPENDENCIA' ...` com a mesma guarda. `inicio IS NULL AND status='EXECUTANDO'` é a tradução de "corrida já adotada não é revertida" para o modelo com run_id (o texto original do D16 falava `execution_id IS NULL` porque vinha do modelo NULL, morto pelo contrato da F2). Se o run foi criado apesar da exceção e o filho rodar depois do DELETE, o upsert da F2 recria a linha pela própria chave — converge para UMA linha (D13).
- **Adoção (D13):** automática por construção — o wrapper `check_agenda` do filho faz upsert pela MESMA chave `(filho, data_ref, run_id)`; não existe "carimbar linha NULL".

**Decisão 4** — claim por transição de status com rowcount + INSERT serializable *(evita: execução dupla de dois pais/guardiã — D18, risco §6.5; reserva NULL presa em EXECUTANDO — B1/D13; redisparo infinito — a praga 30×/mês pela porta do push)*.
**Decisão 5** — devolução guardada por `inicio IS NULL` *(evita: corrida presa sem alerta — B3/D16; e reversão de corrida adotada)*.

### 3.4 `nao_iniciar_antes` (D22, parcial em F3)

Condição satisfeita antes da janela (relógio de parede — janela É de relógio, por definição): o pusher **não dispara**; grava a ordem via INSERT condicional com `status='AGUARDANDO_DEPENDENCIA'` (mesmo NOT EXISTS do §3.2b, run_id já calculado — contrato linha-nasce-com-run_id). Se OUTRO pai completar depois da janela, o caminho (a) adota essa linha e dispara — F3 sozinha já cobre esse caso; o caso "ninguém mais termina" é da guardiã às 08:00 (F4 adota pelo mesmo caminho (a)). Limitação F3-sem-F4 documentada em §8. Essa linha AGUARDANDO é intencional — nunca sofre devolução.

## 4. `schedule` do dependente e a geração (D37, D38)

### 4.1 Como a geração SABE quem tem dependência

Hoje `pipeline["depends_on"]` chega **sempre None**: a `sp_etl_pipelines_pendentes_criar` versionada (migration 026 l.95–150) não devolve a coluna e o supplement avançado (factory l.2156–2206) não a seleciona — D37, confirmado no dev. Decisão: **supplement novo no factory lendo a 067 direto**, no padrão-casa dos 8 supplements existentes, com o contrato `None`×`{}` que a D36 já especificou para a F6:

- `_dependencias_da_tabela(cursor) -> dict[chave_ci, list[str]] | None`: `None` = tabela ausente (067 não aplicada — preserva o que houver); `{}`/dict = tabela é a verdade (vazio sobrescreve: dependência removida É remoção).
- `depends_on` (CSV) entra no SELECT do supplement avançado como **fallback informativo** quando a tabela não existe.
- **A SP não muda.** Motivos: (i) o fio solto provou que a SP de produção pode divergir do repo — `CREATE OR ALTER` clobberaria estado desconhecido; (ii) o factory teria de tolerar SP velha de qualquer jeito (= o mesmo código do supplement, com mais peças móveis); (iii) o supplement versiona JUNTO do código que o consome, uma unidade de deploy. A F6 continua dona de aposentar SP/CSV (§10.1-2 da spec); o aceite do D37 se resolve como "supplement cobre — DAG gerada no dev reflete dependência gravada SÓ na tabela".

### 4.2 O que a geração emite

- Dependência presente (tabela) → **`schedule=None`** (linha l.1880-1883 já existente do on_demand — DAG ativa, só sem gatilho) + consts de dia (`RESTRICAO_DIA`, derivado de `schedule_type`/`schedule_dow`/`schedule_dom`/`dias_semana`/dias do `dias_horarios_mes`, com `is not None` — D05). A restrição de DIA não some com o cron (D04): semanal/mensal/quinzenal/monthly_days_times/dias_semana viram julgamento no check (§1.3). Sem dependência → cron intacto, byte-a-byte (D38; diff mecânico como na F2).
- **Sem a 067, pipeline COM dependência (via CSV) não é gerado**: erro de primeira classe no `steps_log` da factory ("dependência cadastrada mas migration 067 ausente — DAG não gerada"), arquivo antigo preservado. Nem `schedule=None` sem mecanismo de disparo (nunca roda, mudo), nem regressão a cron (roda sozinho, mudo — a classe do D40). Recusar ruidosamente é a única saída honesta; o fluxo de erro visível da factory (PR #234) já existe para isso.
- Regras de dia são CONSTANTES geradas (mesmo padrão de `HORARIOS_ESPECIFICOS`/`SOMENTE_DIAS_UTEIS` hoje, l.822–825): editar agendamento/dependência exige regerar o FILHO — dívida igual à de hoje com o cron, coberta por D30 (markDagDirty, F5) e documentada em §8.

**Decisão 6** — supplement 067 com contrato None×{} e recusa ruidosa sem migration *(evita: D36 — deploy parcial apagando dependência de todas as DAGs; D37 — geração cega; D40 — pipeline voltando ao cron em silêncio)*.

## 5. Remoção do `ExternalTaskSensor` e do modo Dataset

**Sai do gerador** (D01): bloco S4 completo (l.1670–1695 — `dep_list`, sensores, import do `ExternalTaskSensor`), ancoragem `t_check_agenda >> [sensores]` e `root_anchor`/`up` por sensor (l.1701–1704, 1717, 1788–1789), `use_dataset_schedule` + `schedule=[Dataset(...)]` (l.1672–1676, 1876–1879), leitura de `trigger_por_dependencia` (l.587; a coluna morre na migration de limpeza §10.2 da spec, não aqui), const `DEPENDS_ON_DAG_ID` (l.833–834, já sem consumidor).

**Fica**: `outlets=[Dataset(DATASET_URI)]` no publish + import do Dataset — é a **ponte** para DAGs antigas não regeradas (D01): filho velho em modo Dataset continua disparando quando o pai regerado publica. Fica também o `t_check_agenda` como raiz única (o grafo até simplifica: âncora sempre `t_check_agenda`).

**DAGs antigas até regerar**: seguem exatamente como estão (sensor continua pokando o DagRun do pai; Dataset continua fluindo pela ponte). O par perigoso é **pai velho + filho novo**: o pai sem código de push nunca dispara o filho `schedule=None` — por isso a regeração é `force_all`, na ordem de deploy já registrada (067/072 → F2 gravando → force_all → par de teste). **Downgrade path**: reverter `dags/` + `force_all` com o factory antigo — sensores/Dataset voltam; linhas da 067 e reservas restantes ficam inertes (observabilidade, nada as consome); nenhum dado precisa de rollback.

**Decisão 7** — outlet mantido como ponte, remoção só do consumo *(evita: quebrar a frota mista no deploy; e o defeito 5 do QA morre porque filho NOVO não depende mais de Dataset — pai pulado deixa rastro PULADO + F4 alerta, em vez de silêncio)*.

## 6. `dags/utils/dependencias.py` — API do módulo

Mesmo desenho do `data_referencia.py`: o que é regra é puro; o que é estado recebe `conn` (pymssql, `%s`; o chamador é dono da transação). Docstrings carregam o contrato com a F4.

```python
# ── puro (sem banco, sem Airflow) ──────────────────────────────────────────
dia_permitido(regras: dict, dia: date) -> tuple[bool, str | None]
    # regras = {somente_dias_uteis, schedule_type, schedule_dow, schedule_dom,
    #           dias_semana, dias_horarios_mes_dias} — julga SÓ dia; dow=0=domingo,
    #           conversão cron-dow→weekday explícita (D05)
montar_conf(data_ref: date, dia_operacional: date, pai: str) -> dict   # §7, o schema num lugar só

# ── banco ──────────────────────────────────────────────────────────────────
dependentes_de(conn, pai) -> list[str]                     # seek em ix_dep_predecessor, tipo PIPELINE, active=1
liberado(conn, pipeline, data_ref) -> tuple[bool, list[str]]   # (todas SUCESSO na data?, faltantes) — contrato EXISTS §9/F2
calendario_bloqueia(conn, calendario_nome, dia) -> bool
reservar_corrida(conn, filho, data_ref, novo_run_id, origem) -> str | None   # §3.2; None = perdi/há corrida
ordenar_corrida(conn, filho, data_ref, run_id, origem) -> bool               # AGUARDANDO sem disparo (§3.4; F4 New Day)
devolver_reserva(conn, filho, data_ref, run_id, veio_de_adocao: bool) -> None  # §3.3, guarda inicio IS NULL
```

- **Contrato com a F4 (guardiã reusa, gravado nas docstrings):** `dependentes_de` + `liberado` + `reservar_corrida` com `origem='guardia'` e run_id `guardia__*`; a adoção de linhas `AGUARDANDO_DEPENDENCIA` é o caminho (a) do claim; `ordenar_corrida` é o New Day. Nenhuma consulta paralela: se a guardiã precisar de outra pergunta, ela entra AQUI.
- **Contrato com F5/D29:** o predicado de `liberado` é a referência canônica; o endpoint `/pipelines/dependencias/estado` deverá portá-lo com teste de paridade, como `api/services/data_referencia.py` fez com o canônico de `dags/` na F9.
- O código GERADO chama o módulo (import `utils.dependencias`), não duplica SQL — uma fonte por predicado.

## 7. Herança do ODATE no trigger (integração com o `_data_referencia` da F2)

Conf do `trigger_dag`, montado por `montar_conf`:

```python
{"data_referencia": "AAAA-MM-DD",   # a data DA CORRIDA DO PAI — filho NÃO recalcula (decisão nº1 do usuário)
 "dia_operacional": "AAAA-MM-DD",   # §1.1 — o dia contra o qual regras de DIA julgam
 "disparado_por": "<pai>"}          # consumido pelo _disparado_por da F2 (l.1336-1342), já pronto
```

- `data_referencia`: o `_data_referencia` da F2 (l.1350–1390) já a consome com precedência sobre o cálculo — **zero mudança**; virada do FILHO é irrelevante sob push (herança); viradas divergentes entre predecessores são domínio do `DATA_DIVERGENTE` da F4 (risco §8).
- `dia_operacional`: helper gerado novo `_dia_operacional(context)`, espelho do `_data_referencia`: conf válido > `conf['data_referencia']` (aproximação com log — cobre trigger manual que só passou a data) > `date(momento lógico em LOCAL_TZ)`. Nunca relógio de parede.
- **Cascata**: o push do filho para os netos repassa `_data_referencia(context)` e `_dia_operacional(context)` do próprio run — o rótulo e o dia da RAIZ atravessam a cadeia inteira sem recálculo (D12 ponta a ponta; datas coerentes mesmo cruzando a meia-noite — o caso que motivou a spec).
- Pai re-rodado manualmente para data passada (conf com `data_referencia`): o push avalia NAQUELA data — filho que já tem SUCESSO lá é bloqueado pelo claim; filho faltante dispara. Reprocesso pontual coerente de graça; backfill em massa segue OUT (spec §2).

**Decisão 8** — herança dupla (rótulo + dia) no conf *(evita: D12; recálculo na virada — causa D da guardiã cega; e o par D06/D07 sem o qual a herança mataria a própria corrida que costura)*.

## 8. Migrations, riscos e limitações assumidas

**Migrations novas: NENHUMA.** A 072 (`execution_id` 250) já está na main e é pré-requisito (o run_id `dep__*` ~100 chars truncaria no VARCHAR(50) original — era o item 8 do desenho da F2). Índices: `ix_dep_predecessor` serve `dependentes_de`; `ix_pipe_exec_cond` serve EXISTS e claim. Status usados já documentados na 067 (`AGUARDANDO_DEPENDENCIA`, `EXECUTANDO`; `NAO_LIBEROU` continua reservado à F4). `disparado_por` NVARCHAR(200) comporta o nome do pai.

| Risco | Mitigação |
|---|---|
| Frota mista: pai velho não empurra filho novo | Ordem de deploy obrigatória com `force_all` + começar por par de teste (já registrada); ponte Dataset cobre o sentido inverso |
| F3 sem F4: trigger devolvido, filho pausado no Airflow, `nao_iniciar_antes` sem outro pai, blackout no filho — corrida não roda e **ninguém alerta** | Janela assumida e curta: logs `[DEP]` altos no publish do pai; linha AGUARDANDO/PULADO visível no banco; D16/D22/D41/D50 fecham na F4 — é a razão de F4 vir na sequência imediata |
| Predecessores com viradas divergentes → filho nunca libera | Risco 4 da spec: F4 alerta `DATA_DIVERGENTE`; F5 mostra a data calculada no cadastro |
| Consts de dia defasadas (editou agendamento sem regerar) | Mesma dívida do cron hoje; filho é fonte da verdade (PULADO honesto no pior caso); D30 (F5) marca a DAG suja |
| Deadlock/latência no claim serializable | Transação mínima (1 UPDATE + 1 INSERT), fora da tx do SUCESSO, por candidato; exceção → candidato pulado com log (D21/D23), F4 re-cobre |
| `trigger_dag` local_client no worker | Padrão já em produção no mesmo repo (`etl_sequence_import_approve.py:206`) |

## 9. O que a F3 NÃO faz

- **Não ordena o dia nem alerta**: sem guardiã, sem `etl_dependencia_evento`, sem `JANELA_ESTOUROU`/`DATA_DIVERGENTE`/`PREDECESSOR_FALHOU`, sem Teams (F4). `hora_limite_dependencia` não é lida — e, decidido aqui: **deadline não bloqueia push** (é alerta, não trava; bloquear estrangularia a cadeia atrasada em silêncio — se o usuário quiser UNTIL à la Control-M, é decisão explícita na F4).
- Não toca API/UI/dashboard (F5/F9), não aposenta SP/CSV/`trigger_por_dependencia` (F6 + migration de limpeza §10).
- Não redispara FALHA (Clear é do plantonista — D17), não re-roda dependente N×/dia por ODATE (§3.2), não bloqueia disparo manual (operador manda), não faz backfill em massa, não trata OR/job→job (§2/§9 da spec).
- Não muda trigger_rule, folha, `t_reg_falha`, `flow_close`, `_registrar_execucao` nem o nível job (`etl_job_execution`/`ts_nodash` intactos).
- Não julga HORA em evento e não re-julga dependência dentro do filho (o gate é do pusher; filho julga só agenda de dia — uma responsabilidade por lugar).

## 10. Testes unitários (pytest, DAG via `_generate_dag_source` com Airflow stubado — técnica de `tests/test_dag_factory_decisao.py`)

1. **Compilação** nas combinações da F2 + novas (com dependência simples/múltipla, dependência+decisão, dependência+aguarde, dependência+monthly/weekly/dias_semana/monthly_days_times, sem 067): baseline zero falhas novas vs HEAD; diff mecânico do fonte gerado nas 16 combinações da F2 (sem dependência ⇒ mudanças só nos helpers previstos).
2. **Folhas intactas** (lição E): parser de `dep_lines` — conjunto de folhas IDÊNTICO ao da F2; nada downstream de `publish_dataset`; trigger_rules byte-idênticas ao HEAD.
3. **Geração**: com tabela → `schedule=None`, zero `ExternalTaskSensor`/`DEPENDS_ON_DAG_ID`/schedule-por-Dataset no fonte; sem dependência → cron byte-idêntico (D38); contrato `None`×`{}` do supplement (D36); sem 067 + CSV → erro de 1ª classe, arquivo não sobrescrito; `outlets` preservados (ponte D01).
4. **Taxonomia/agenda** (exec do código gerado com contexto stubado): `dep__`/`guardia__` isentos de hora e sujeitos a dia (D03); manual isento de hora (não regride); `agenda` julga hora no momento lógico; `RESTRICAO_DIA` nos 5 tipos com dow=0=domingo e conversão cron→weekday (D04, D05); dias úteis/calendário pelo `dia_operacional` com `pendulum.now` congelado provando independência do relógio (D06/D07); blackout continua GETDATE (D08); os 5+1 motivos de PULADO (D58 não regride).
5. **`_dia_operacional`**: conf válido > data_referencia (log) > momento lógico; inválido recalcula sem abortar.
6. **`dependencias.py` puro**: matriz `dia_permitido`; `montar_conf` com datas serializadas.
7. **`dependencias.py` banco** (conn stubada): `liberado` — todas/uma falta/FALHA/PULADO/EXECUTANDO/outra data/exceção→não libera (D14, D20, D21); claim — vitória por UPDATE, vitória por INSERT, derrota, PULADO não bloqueia, run_id devolvido correto em cada caminho; devolução — DELETE vs volta-a-AGUARDANDO, guarda `inicio IS NULL`; `ordenar_corrida` idempotente.
8. **Push**: try/except por item — 1º candidato explode, 2º dispara, pai nunca levanta (D23); conf com as 3 chaves; run_id `dep__*` ≤250 e sem `[:50]`; sem 067 → log e retorno; commit do SUCESSO antes da avaliação (ordem no fonte).
9. **Ausências guardadas**: nenhum `criado_em` em ordenação (D15); nenhum helper em `default_args` (teste existente segue verde); comentários gerados sem identificadores proibidos (princípio 7).

## 11. Cenários de EXECUÇÃO no dev (Airflow :8082 + `orquestra_dev`, runbook `docs/ambiente-dev.md`) — SELECT + UI do Airflow em cada um (lição-mãe)

| # | Cenário | Prova |
|---|---|---|
| E1 | A e B → C: A conclui (C não dispara, log "aguardando B"); B conclui → C parte em <1 min, run_id `dep__*`, UMA linha adotada (`inicio` carimbado), mesma `data_referencia` | D19, D13, D02-caminho |
| E2 | A e B terminando juntos (jobs sincronizados) → UMA execução de C, um vencedor no claim | D18 (parte F3), §3.2 |
| E3 | Pai falha → DagRun do pai VERMELHO, C não dispara; Clear do pai → SUCESSO → C dispara | matriz D53/D54 re-provada com o código F3 |
| E4 | C mensal dia 5 (`schedule=None`): push no dia certo roda; no dia errado nem trigger nem linha; `schedule_dow=0` num segundo C semanal-domingo | D04, D05 |
| E5 | C com `horarios_especificos` disparado por `dep__` → RODA (hora não se aplica a evento) | D03 — o assassino nº1 da 1ª execução |
| E6 | Virada 20:00 no pai, disparo sexta 23:30 → pai carimba SÁBADO e RODA (dias úteis não pula); filho `somente_dias_uteis` disparado 00:10 herda a MESMA data e RODA | D06 + D07 + D12 juntos |
| E7 | Pai com job de >1h → filho dispara ao final, sem timeout | D02 (QA2 morto por construção) |
| E8 | Trigger falha (filho com DAG removida do disco) → devolução, log `[DEP]`, pai VERDE, nada preso em EXECUTANDO | D16 (parte F3), D23 |
| E9 | Pai 3×/dia com PULADO intercalado → EXISTS libera o filho, filho roda UMA vez na data | D14, §3.2 |
| E10 | Blackout no filho: push → linha adotada vira PULADO (mesma chave); fim do blackout + Clear do pai → novo claim dispara (PULADO não bloqueou) | D15, D20, §3.2 |
| E11 | UI do Airflow: DAG do dependente com `schedule=None` e sem sensor; DAG antiga NÃO regerada segue disparando pela ponte Dataset | D01 |
| E12 | Decisão-raiz com ramo vazio no pai → corrida fecha PULADO, publish skipped, NENHUM push, falha visível quando há falha | D55 (B4×N1 revalidado) |
| E13 | `nao_iniciar_antes=08:00`, liberação 07:10 → linha AGUARDANDO sem disparo; segundo pai concluindo 08:05 adota e dispara | D22 (parte F3) |
| E14 | Cascata de 3 níveis A→C→N: neto herda `data_referencia`/`dia_operacional` da RAIZ via conf, sem recálculo | D12, §7 |
| E15 | Tentativa de ciclo no cadastro → 422 (não-regressão F1) | D24/D25 |

## 12. Mapa decisão → defeito histórico

| Decisão | Defeito que evita |
|---|---|
| Dia operacional herdado; dia sempre, hora só em cron | D03 (PULADO em 100% dos disparos), D04/N5 (30×/mês), D05 (domingo→segunda), D06/A3, D07/N4 (a regressão da virada 20:00) |
| Taxonomia `_origem_disparo` explícita | `dep__*` caindo na regra de horário por não começar com `manual` |
| Push dentro do publish, pós-commit | DagRun verde com falha (folhas intactas — motivo da reversão); corrida SUCESSO×EXISTS; D23 |
| Claim por rowcount + serializable; índice único NÃO arbitra | D18 execução dupla; B1/D13 reserva NULL; redisparo N×/ODATE |
| PULADO não bloqueia claim | D15 pela porta do claim (corrida morta para sempre por um blackout) |
| Devolução guardada por `inicio IS NULL` | B3/D16 corrida presa; reversão de corrida adotada |
| Contrato EXISTS em `liberado` + zero `criado_em` | B2/D14, D15, D20, D21 |
| Supplement 067 `None`×`{}` + recusa ruidosa sem migration | D36 (apagar dependências no deploy parcial), D37 (geração cega), D40 (volta muda ao cron) |
| Outlet Dataset mantido como ponte; remoção só do consumo | frota mista quebrada; QA5 (pai pulado silencia filho — agora rastro + F4) |
| Herança dupla no conf, cascata sem recálculo | D12; causa D (datas divergentes na corrida que cruza a meia-noite) |
| Uma corrida por ODATE via push; FALHA não redispara | D17 preservado (Clear libera a cadeia) sem automatismo perigoso |
| Deadline não bloqueia push (explícito) | cadeia atrasada estrangulada em silêncio — decisão adiada com dono (F4) |

**Arquivos tocados na implementação:** `dags/etl_dag_factory.py`, `dags/utils/dependencias.py` (novo), `tests/` (novos + baseline). Nenhuma migration. PR: `feat: disparo imediato do pipeline dependente` (retomada F3). Deploy: 067+072 já aplicadas → confirmar F2 gravando → `force_all` → par de pipelines de teste (ordem registrada na memória; guardiã só na F4).
