---
name: orquestra-dependencias-pipelines
updated: 2026-08-02
description: Spec das dependências entre pipelines no modelo Control-M — F1–F9 COMPLETAS e os componentes de malha (F10–F15) também; ✅ TUDO EM PRODUÇÃO desde 2026-08-12 (migrations 067 e 070–076 aplicadas no trem)
metadata: 
  node_type: memory
  type: project
  originSessionId: f530f050-81b0-4c91-a6cc-98cdb214290e
  modified: 2026-08-13T02:42:48.834Z
---

Spec **Dependências entre pipelines (modelo Control-M)** do [[orquestra-sge-app]],
em `docs/spec-dependencias-pipelines.md`. Criada em 2026-07-31.

🏁 **CICLO DA SPEC ENCERRADO NO CÓDIGO (2026-08-03, main 5ab803e) e ✅ EM
PRODUÇÃO desde 2026-08-12** ([[orquestra-deploy-trem-producao]]). Além de
F1–F9, os **componentes de malha F10–F15** foram entregues e aceitos — ver
[[orquestra-malha-componentes]]. O deploy foi **ÚNICO para os dois** (motor +
malha + componentes): ordem consolidada no preâmbulo da spec, migrations
**067 e 070–076**. ⚠️ A 076 (que derruba `FK_dep_evento_pipeline`) era o passo
que, se pulado, deixaria Notificação/Fim mudos com o smoke aparentando sucesso.

🚧 **RETOMADA F2–F6 EM CURSO** (2026-08-02). ✅ **F2 EM MAIN (PR #243)**:
registro em etl_pipeline_execucao — linha nasce no wrapper do check_agenda com
run_id desde o INSERT; FALHA = folha paralela ONE_FAILED espelho do
teams_error; SUCESSO no próprio publish (mesmo task_id/trigger/outlets);
PULADO sem inicio + guarda "não rebaixa terminal" (achado da revisão: Clear de
SUCESSO em dia bloqueado); migration 072 (execution_id 50→250 — run_id de 51+
chars truncaria em silêncio). 7 cenários EXECUTADOS no dev (9 runs = 9 linhas,
0 NULL; anti-verde 3×; Clear FALHA→SUCESSO); diff mecânico do fonte gerado em
16 combinações. Artefatos: docs/retomada-{aceitacao,f2-desenho,harness-dev}.md
(60 itens D01-D60; D09/D53/D56/D58/D60 carimbados). ⚠️ DEPLOY da F2: 072 na 6c
+ dags/ + REGERAR DAGs (force_all). ✅ **F3 EM MAIN (PR #245, 2026-08-02) — O PUSH FUNCIONA**: dia_operacional
separado do ODATE (dia sempre, hora só em cron — D03-D07 mortos); push dentro
do publish pós-commit (folhas intactas); claim serializable (corrida real de
160ms com 1 vencedor no E2); supplement 067 (fio solto D37); sensor/Dataset
removidos com outlets como ponte. 15/15 cenários E executados; 18 itens D
carimbados; 1220 testes. Revisão pegou 2: manual-em-cron julgava o TICK
(PULADO indevido) → manual julga HOJE; CSV órfão viraria cron mudo no
force_all → recusa ruidosa. ⚠️ DEPLOY F3: query de CSV órfão ANTES do
force_all (na PR #245); par de teste primeiro; F4 na sequência imediata.
✅ **F4 EM MAIN (PR #246, 2026-08-02) — NÚCLEO CONTROL-M COMPLETO (F2+F3+F4)**:
guardiã 1-task; datas só do presente (D45 morto por ausência); D44 sem perder
QA5; deadline opt-in só-alerta + NAO_LIBEROU como UNTIL de dia; 15/15 cenários
E (colisão real push×guardiã = D18 completo; 137 min anti-ruído ZERO eventos).
Revisão pegou 3 (DATA_DIVERGENTE falso sob banco UTC → régua do banco via
agora_do_banco; evento NAO_LIBEROU perdido entre commits → transação única;
erro de consulta fechando corrida liberada → sentinel ERRO_CONSULTA adia).
⚠️ DEPLOY F4: só dags/, guardiã NASCE PAUSADA, conferir GETDATE() de produção
antes de despausar. GOTCHA dev: SQL Server em UTC × local -03. ✅ **F5 EM MAIN (PR #247, 2026-08-02)**: register PATCH-parcial (write-only da
causa C morto, estendido aos 5 campos de agenda do wipe do InactivateModal);
edição de dependência aresta a aresta; api/services/dependencias.py com
paridade de SQL; migration 073 dag_config_pendente_em (CARIMBO — TOCTOU morto
por clear condicional); DependenciasModal paginado; 12/12 V-cenários vivos.
Revisão pegou 3 (sla_minutos fora da lista da flag; TOCTOU; wipe) — corrigidos
na raiz. DEPLOY F5: 073 na 6c + api + front, sem regerar DAGs. ✅ **F6 EM MAIN (PR #248, 2026-08-02) — 🏁 RETOMADA F2-F6 COMPLETA NO CÓDIGO**:
manual §3.4 do operador (semântica do DIA OPERACIONAL — revisão corrigiu
"data de referência"); factory zera flag SÓ fora da API (gating do
reconciliador preservado); ssh_conn_id no dump; SMOKE §7 OFICIAL a-f PASS no
dev (cascata em 5s). A spec inteira (F1-F9 + malha) está no código, PRs
#231-#248, TUDO validado por execução. ✅ **DEPLOY DE PRODUÇÃO FEITO em
2026-08-12** — ordem consolidada no preâmbulo da spec (067→073 na 6c; dags/ +
api + front; query CSV órfão ANTES do force_all; force_all; GETDATE do SQL;
TZ da API + docker exec date; guardiã pausada→despausar; smoke §7 produção
com par de teste). Aceitação: 16 itens [ ] restantes são deploy/produção/
gesto humano — nenhum bloqueia. 🔜 antigo F4:
(obsoleto)  (desenho pronto: guardiã 1-task, datas só do presente
— D45 morto por ausência de mecanismo; deadline=alerta, NAO_LIBEROU=UNTIL de
dia; resgate de órfã EXECUTANDO+inicio NULL — cobre a dupla-falha que a
revisão da F3 apontou).

✅ Fix StoredProcOperator EM MAIN (PR #244): proc_params + bind %s/tupla +
Decimal exato; revisão provou EMPIRICAMENTE que DAGs velhas (params=[])
importam sob o utils novo — ordem de deploy livre. 🔜 EM CURSO: desenho da F3
(push; causa-raiz A evento×relógio + contrato reserva-com-run_id + fio solto
da SP D37 + remoção sensor/Dataset).
Método: fase a fase, cenários EXECUTADOS no dev, suíte de aceitação como
contrato. Regra: [[orquestra-dev-testa-producao-manda]].

✅ **F9 EM MAIN (PR #242 MERGEADA 2026-08-02) — TRILHA F7-F9 COMPLETA:**
visão de execução por ODATE no MalhaEditor (modo Montagem|Execução, anel de
status, eventos da guardiã, vazio HONESTO até a retomada) + realocação do
catálogo p/ aba em /governanca + tela Malha SÓ malhas + DependencyGraph morto.
api/services/data_referencia.py = port do canônico de dags/ com paridade
testada. Smoke vivo com dados SEMEADOS 10/10. ⚠️ GOTCHA de TZ achado pela
revisão: container da API rodava em UTC (Airflow tinha TZ) → ODATE default
nascia no dia seguinte 21h-24h BRT; fix = TZ America/Sao_Paulo no compose;
**conferir o TZ do container da API de PRODUÇÃO no deploy** (docker exec
orquestra-api date). Deploy da trilha F7-F9 FEITO no trem de 2026-08-12:
migrations 070+071 na 6c, api + front, recriar container da API (TZ), sem
regerar DAGs.

✅ **F8 EM MAIN (PR #241, 2026-08-02):** MalhaEditor (React Flow, irmão do
FluxoEditor; layoutGrafo.ts extraído como módulo puro) — desenhar aresta grava
na 067 via POST/DELETE /dependencias (helpers da F1 reusados) + espelho CSV na
MESMA transação; PUT layout; ciclo com mensagem literal cliente=servidor.
Revisão achou a MESMA classe da grafia em etl_pipeline_dependencia (aresta
divergente invisível no diagrama) → fechada em 3 pontos: canonização no GET,
canonização no _gravar_dependencias da F1, **migration 071**. Smoke vivo 13/13
×2. Deploy feito no trem (071 na 6c + api + front). GOTCHA React Flow: aresta cujo
source/target não casa com id de nó é DESCARTADA em silêncio.

✅ **F7 EM MAIN (PR #240, 2026-08-02):** entidade Malha (migration 070:
etl_malha + etl_malha_pipeline com layout p/ F8), router /malhas (CRUD +
membros canonizados + degradação com migration_pendente), tela Malha com visão
Malhas default + menu em Construção + Catálogo legado atrás de toggle.
Validada com smoke VIVO no dev (12/12, 2 rodadas). A revisão adversarial
reprovou a 1ª versão com 4 defeitos — o pior: agente de backend DESVIOU do
contrato ({"data"} × malhas/migration_pendente) e a tela inteira ficaria
inoperante; smoke de API não pega desvio de contrato de front — LIÇÃO: smoke de
tela ou checagem de contrato explícita quando front e back são agentes
separados. Deploy feito no trem (070 na 6c + api + front).

🆕 **2026-08-02 (PR #239 MERGEADA): a spec ganhou a MALHA e o ambiente dev
existe.** Malha = entidade que agrupa pipelines (análogo da sequence mestre do
DataStage/SMART Folder Control-M); a tela Malha vira o lugar de MONTAR e exibir
malhas em diagrama (desenhar aresta = gravar dependência na tabela da F1 — uma
fonte de verdade só; dependência é GLOBAL, não por malha). Fases novas: F7
(entidade+lista+menu p/ Construção) e F8 (MalhaEditor irmão do FluxoEditor) —
**independem da retomada F2–F6**; F9 (visão de execução por ODATE + inventário
migra p/ Catálogo & Lineage /governanca) depende de F2–F4. ✅ **Ambiente dev
Airflow+SQL Server DE PÉ nesta VPS** (pré-condição da retomada satisfeita):
Airflow :8082, API :8000, UI :8090, SQL 127.0.0.1:1433, banco orquestra_dev com
schema prod + migrations 002–069; runbook com as armadilhas reais em
docs/ambiente-dev.md (deploy_full defasado, etl_ds_job_log sem guarda na 010,
sqlcmd18 aborta — sequência de 5 passos que funciona). ⚠️ **FIO SOLTO novo
(§10.3): a sp_etl_pipelines_pendentes_criar do repo NÃO devolve depends_on** —
pelo código, o gerador nunca recebe dependências; confirmar no dev antes da F2.
✅ **RESOLVIDO 2026-07-31: EXECUÇÃO REVERTIDA (PR #229, merge 001b44e). A main
está SÃ e no comportamento pré-feature, com a fundação da F1 preservada.**
935 testes, as mesmas 5 falhas pré-existentes.

**O que sobreviveu:** migration 067 (tabelas inertes), ciclo por BFS (fecha o
defeito 3 do QA), FK de existência do predecessor (fecha o defeito 4),
`dags/utils/data_referencia.py` (conceito com testes, sem consumidor),
`deduplicar` + `_rollback_silencioso` (este último corrige um vazamento de
conexão ANTERIOR à feature). **O que voltou:** o `ExternalTaskSensor`, com os
defeitos 1, 2 e 5 do QA — conhecidos e contornáveis pelo modo Dataset.

🚨 **O QUE MOTIVOU A REVERSÃO — a correção B tinha posto `TriggerRule.ALL_DONE`
no `t_exec_fim`, e isso fazia TODO pipeline que falha aparecer VERDE no
Airflow:** com um job falhando, `publish_dataset` fica UPSTREAM_FAILED, mas
`t_exec_fim` (ALL_DONE) roda com sucesso e `t_disparar_dependentes`
(ALL_SUCCESS) também → nenhuma FOLHA em estado de falha → DagRun marcado
SUCCESS. Afetava 100% dos pipelines, com ou sem dependência. **Lição para
qualquer mudança de trigger_rule no dag_factory: o estado do DagRun é decidido
pelas FOLHAS do grafo — mudar a regra de uma task terminal pode esconder falha
do pipeline inteiro.**

**Histórico: F1–F6 (#218–#223) reprovadas na 1ª revisão (21 defeitos). Correções
A–E (#224–#228) fecharam 14 e introduziram ~15 novos. 2ª revisão (5 agentes)
reprovou também.** Os 1053 testes passavam em TODAS as rodadas.

**Defeitos novos mais graves, todos introduzidos pelas correções:**
- **DagRun verde em pipeline que falhou** (acima) — catastrófico.
- **Rerun verde após falha não vira SUCESSO** (guarda `apenas_se_executando`):
  plantonista corrige, dá Clear, DAG fica verde e a linha continua FALHA para
  sempre; a cadeia morre em silêncio. REGRESSÃO — antes funcionava.
- **Guardiã dispara datas PASSADAS**: ao cadastrar uma dependência, o dependente
  roda retroativamente (`_datas_em_aberto` de 48h sem guarda de idade).
- **`somente_dias_uteis` + `hora_virada` REGREDIU o caso que a correção A dizia
  resolver**: com virada 20:00, sexta 23:30 carimba SÁBADO → PULADO.
- **`monthly_days_times` e `dias_semana` continuam sem restrição de dia** — o
  "roda 30x/mês" segue aberto nesses dois tipos.
- **`schedule_dow=0` (domingo) vira segunda** (`int(x or 1)` com x=0).
- **`criado_em NOT NULL DEFAULT GETDATE()` derruba a correção do PULADO**: o
  `COALESCE(inicio, criado_em)` cai no criado_em, então o PULADO continua sendo
  "o mais recente" — e o `_meu` que a correção B adicionou lê PULADO e NÃO
  libera ninguém.
- **`limit=2000` é inerte**: `list_pipelines` clampa em `min(100, ...)`. O aviso
  de teto (`>= 2000`) é código morto. A solução (paginar) já existia em
  `Pipelines.tsx`.
- **Painel diverge do motor**: `/pipelines/dependencias/estado` não recebeu o
  `EXISTS` aplicado em `dependencias.py`.
- **`DATA_DIVERGENTE` falso e `JANELA_ESTOUROU` de fim de semana continuam** —
  as correções não os eliminaram.

⚠️ **PADRÃO DE FALHA DO MEU MÉTODO (registrar para não repetir):** escrevi testes
que confirmavam a hipótese que me levou ao erro. Ex.: `test_predecessor_pulado_nao_ordena`
verificava só a ausência do INSERT, não o evento que a correção prometia
eliminar — passou verde com o defeito intacto. Sem ambiente para EXECUTAR
(Airflow + SQL Server), comportamento distribuído (trigger rules, races, estado
compartilhado) não é verificável por leitura.

**RECOMENDAÇÃO DADA AO USUÁRIO:** reverter F2–F6 + correções A–E (tudo que muda
execução), MANTER a F1 (modelo + ciclo por BFS + FK de existência + data de
referência), que fecha 2 dos 5 defeitos originais do QA sem tocar em execução. A
parte de execução só deve ser refeita com ambiente onde dê para rodar.

**O que cada correção fechou:** A = check_agenda ciente de disparo por evento +
RESTRICAO_DIA (a restrição de dia morava no cron e evaporava com schedule=None)
+ dias úteis/calendário pela data de referência. B = adoção da linha reservada
(execution_id NULL), "existe SUCESSO na data" no lugar de "o mais recente",
reversão da reserva quando o trigger falha, fechamento ALL_DONE com guarda de
estado. C = GET devolve os 3 campos da janela + UPDATE só do que veio no body +
dedup case-insensitive + rollback explícito. D = DATA_DIVERGENTE só com carimbo
recente, varredura das datas em aberto, PULADO não ordena, mensagem coerente,
cron protegido. E = markDagDirty, modal montado só quando aberto, teto de 2000
com aviso, e o painel "aguardando dependência" na Malha (que eu tinha anunciado
na F5 e não entregue).

⚠️ **PADRÃO MEU QUE SE REPETIU 3x NESTA FEATURE:** comentário/docstring que cita
um identificador ("antes era NONE_FAILED_MIN_ONE_SUCCESS", "schedule=None")
entra no código GERADO e quebra assert de substring de testes de
não-regressão. Escrever esses textos sem nomear o identificador.

⛔ **AS 4 CAUSAS-RAIZ (não são 21 bugs independentes):**

**A. Misturei disparo por EVENTO com agenda por RELÓGIO.** O `check_agenda`
raciocina em relógio de parede; ao tornar o dependente `schedule=None` a
premissa quebrou e não revisei quem dependia dela. Duas faces:
 • dependente com `horarios_especificos`/`dias_horarios_mes` → **PULADO em 100%
   dos disparos** (o run_id `dep__*` não começa com 'manual', e o horário do
   trigger nunca bate a lista). E PULADO não libera netos NEM alerta.
 • dependente **semanal/mensal/quinzenal perde a restrição de DIA** (só existia
   no cron; o check_agenda não valida schedule_dom/dow) → **fechamento mensal
   roda 30x/mês**. VERIFICADO gerando a DAG.
 • `somente_dias_uteis`/`calendario` usam o relógio → matam a corrida que
   atravessa a meia-noite, o caso que motivou a spec.

**B. Estado da corrida sem chave estável.** O push insere com `execution_id`
NULL e a DAG atualiza por `ts_nodash` → nunca casam → 2 linhas, a do push presa
em EXECUTANDO. `PULADO` grava `inicio`, então num pipeline 3x/dia o PULADO
mascara o SUCESSO na leitura "mais recente". `EXECUTANDO` é commitado ANTES do
`trigger_dag` → trigger falhou = corrida presa, sem redisparo e sem alerta.
Decisão-raiz com ramo vazio → publish SKIPPED → corrida eterna em EXECUTANDO.

**C. Contrato de leitura/escrita incompleto na API.** `hora_virada`,
`nao_iniciar_antes` e `hora_limite_dependencia` são gravados e NUNCA lidos de
volta → **todo save (e o inativar) zera os três**. `_gravar_dependencias` faz
DELETE+INSERT sem dedup nem atomicidade → CSV legado "A,A,B" perde B e o
pipeline dispara sem esperá-lo (3 revisores acharam isso por caminhos distintos).

**D. Guardiã com premissas divergentes da execução.** Calcula data_ref pela
virada do DEPENDENTE + relógio, enquanto a corrida é carimbada pela virada do
PREDECESSOR → cega na corrida que atravessa meia-noite. `DATA_DIVERGENTE` dispara
**todo dia para todo dependente** (acha o sucesso normal de ontem na janela de
±3 dias). Ordena quando o pai foi PULADO → linha órfã eterna + alerta em fim de
semana. try/except FORA do laço de dependentes → 1 erro cancela os demais.

✅ **O que a revisão APROVOU:** a migration 067 (os 8 vetores refutados com
evidência, inclusive erro 1785 — 1 CASCADE + 1 NO ACTION é aceito); geração das
DAGs compila em 20 combinações; ONE_FAILED correto; degradação sem a 067 correta
(`None` vs `{}`); zero regressão de teste.

⚠️ **GOTCHA DE INFRA descoberto:** `sql/migrate.py` NUNCA lê `cur.messages` → todo
`PRINT` de migration é DESCARTADO. Qualquer relatório impresso por migration não
chega ao operador. Pior: com a F6, um `depends_on` órfão faz o pipeline sair de
`schedule=None` e **passar a rodar sozinho no cron**, em silêncio.

📋 **CONSULTA OBRIGATÓRIA antes de qualquer deploy** (dimensiona o estrago):
`SELECT pipeline_name, schedule_type, horarios_especificos, dias_horarios_mes,
schedule_dom, schedule_dow, somente_dias_uteis, calendario_nome, depends_on
FROM dbo.etl_pipeline WHERE depends_on IS NOT NULL AND active = 1` — linhas com
custom/monthly_days_times caem no defeito "nunca roda"; weekly/monthly/biweekly
caem no "roda todo dia".

🚀 **ORDEM OBRIGATÓRIA DO DEPLOY (a ordem importa, ver PR #220):**
1. migration **067** (etapa 6c, responder `s`)
2. confirmar que a F2 grava: `SELECT TOP 20 * FROM dbo.etl_pipeline_execucao ORDER BY id DESC`
3. **só então REGERAR as DAGs** (`force_all` da factory) — sem isso as DAGs
   antigas seguem com sensor e cron, e NADA muda
4. **despausar** a DAG nova `etl_dependencia_guardia` (5 min)
5. começar por **um par de pipelines de teste**, não pela malha inteira

**PENDÊNCIA REGISTRADA (§10 da spec) para DEPOIS do deploy validado:** remover a
escrita em espelho do CSV `etl_pipeline.depends_on` + a coluna + a
`trigger_por_dependencia` (obsoleta desde a F3, fora da tela desde a F5), numa
migration de limpeza. O CSV foi MANTIDO de propósito: é o fallback do factory
quando a 067 não está aplicada — `_dependencias_da_tabela` devolve `None` (não
`{}`) nesse caso, senão apagaria a dependência de TODAS as DAGs.

**F5** trocou o campo de texto livre por `DependenciasModal` (busca por
nome/projeto, filtro, chips, aviso de pipeline INATIVO escolhido como
dependência); moveu a escolha de "Configurações Avançadas" (passo Notificações)
para o passo **Agendamento**, porque dependência SUBSTITUI o agendamento; janela
e hora-limite só aparecem com dependência e são limpos ao remover a última;
`trigger_por_dependencia` saiu da tela. Endpoint novo
`GET /pipelines/dependencias/estado` devolve, por dependente, o status da corrida
e QUAIS predecessores estão pendentes.

Os **5 defeitos do QA estão todos endereçados**: 1 e 2 pela F3 (sensor removido,
disparo por condição), 3 e 4 pela F1 (BFS + FK), 5 pela F4 (guardiã alerta em
vez de silenciar). DAG nova `etl_dependencia_guardia` (5 min) precisa ser
DESPAUSADA no Airflow; Variables opcionais
`DEPENDENCIA_GUARDIA_INTERVAL_MINUTES` (5) e `DEPENDENCIA_LOTE_NOTIFICACAO` (50).

⚠️ **DEPLOY DA F3 TEM UM PASSO A MAIS E ORDEM OBRIGATÓRIA:** (1) migration 067;
(2) confirmar que a F2 já grava (`SELECT TOP 20 * FROM etl_pipeline_execucao`);
(3) SÓ ENTÃO **regerar as DAGs** (`force_all` da factory ou botão por pipeline)
— o `etl_dag_factory` mudou, mas as DAGs JÁ GERADAS continuam com sensor e cron
até serem regeradas, então nada muda sem esse passo. Regerar com a tabela vazia
deixaria os dependentes sem condição para satisfazer. Começar por um PAR DE
PIPELINES DE TESTE, não pela malha inteira.

F1 fechou os defeitos 3 e 4 (ciclo por BFS + existência por FK) e entregou
`dags/utils/data_referencia.py`. F2 grava `etl_pipeline_execucao` (EXECUTANDO /
SUCESSO / FALHA / PULADO) com a data de referência; **a execução ainda NÃO muda
de comportamento — o ExternalTaskSensor só sai na F3.**

⚠️ **GOTCHA descoberto na F2 (vale para qualquer mudança no `etl_dag_factory`):**
no arquivo GERADO, `consts_str` é emitido ANTES de `helpers_str`. Pôr uma função
dos helpers em `default_args` (ex.: `on_failure_callback`) dá **NameError no
import da DAG** — e o pytest de geração NÃO pega, porque a string compila. Use
task com `trigger_rule=ONE_FAILED` (padrão que o `teams_error` já usa). Há teste
`test_default_args_nao_referencia_helper` guardando isso.
Outro: `ONE_FAILED` só enxerga upstream DIRETO — pendurar no `publish_dataset`
deixa a task cega, porque numa falha o publish nem roda.

**Por que:** o usuário vai migrar dezenas de processos com dependência entre si e
pediu QA do mecanismo atual. Chamou isso de "o coração da ferramenta".

⚠️ **5 DEFEITOS CONFIRMADOS no mecanismo atual (QA de 2026-07-31, cada um
reproduzido, não inferido):**
1. `ExternalTaskSensor` sem `execution_delta`/`execution_date_fn`
   (`dags/etl_dag_factory.py:1366`) → **só funciona se pai e filho tiverem o MESMO
   horário de agendamento**; horários diferentes = logical_date diferente = sensor
   nunca acha o run, espera 1h e falha. A UI ainda induz o erro ao dizer "precisam
   concluir antes deste iniciar".
2. `timeout=3600` fixo → pai que dura mais de 1h reprova o filho (o
   CargaDiaria deles roda 8h).
3. `_check_circular` (`api/routers/pipelines.py:197`) segue **só a primeira**
   dependência (`raw.split(",")[0]`) → ciclo com múltiplas deps passa batido.
   Provado: A→B→A com A tendo "X,B" NÃO é detectado.
4. `depends_on` **não valida existência** do pipeline citado → typo vira sensor
   para DAG inexistente (falha em 1h) ou, no modo Dataset, **nunca dispara, para
   sempre, em silêncio**.
5. Modo Dataset: pai pulado pelo `check_agenda` (ShortCircuit) não publica o
   Dataset → filho não roda e ninguém é avisado.

**Recomendação dada enquanto a spec não é implementada:** marcar "Disparar quando
as dependências concluírem" (modo Dataset) em todo pipeline com dependência —
escapa dos defeitos 1 e 2, que são os fatais.

**DECISÕES do usuário (2026-07-31), todas via AskUserQuestion:**
1. **Data de referência (ODATE)**: hora de **virada configurável** (global +
   override por pipeline) **+ herança na cadeia** — quem é disparado por
   dependência НЕ recalcula, herda a data do pai via `conf` do trigger.
   Regra: virada 00:00 → data do calendário; senão, hora >= virada → dia seguinte.
2. **Disparo**: **push do pai + DAG guardiã** de rede de segurança (não
   scheduler central). Pipeline com dependência vira `schedule=None`.
3. **Quando não libera**: aguarda até `hora_limite_dependencia` e então **alerta
   sem falhar** (fica pendente). Campos `nao_iniciar_antes` + hora-limite.
4. **Granularidade**: só pipeline→pipeline agora, **mas job→job fica no BACKLOG
   GARANTIDO** — por isso `etl_pipeline_dependencia` já nasce com `tipo`,
   `job_origem`, `job_destino` reservados (§9 da spec), para a feature futura não
   exigir migration destrutiva.

**Fatos do levantamento que valem além da spec:**
- **NÃO existe data de referência em nenhum lugar do modelo hoje** —
  `etl_job_execution` (`sql/schema_prod_dev.sql:206`) só tem start_time/end_time.
- **Não existe tabela de execução no nível PIPELINE** — só nível job; o status de
  pipeline do dashboard é derivado por agregação (`api/routers/dashboard.py:170`).
- Airflow **2.9.3**.
- Padrão de disparo de DAG a partir de DAG já existe:
  `airflow.api.client.local_client.Client.trigger_dag`
  (`dags/etl_sequence_import_approve.py:208`).
- Técnica usada no QA: gerar a DAG de verdade com `_generate_dag_source` e
  inspecionar a string — os testes do repo já fazem isso
  (`tests/test_dag_factory_decisao.py`), stubando Airflow via `sys.modules`.
