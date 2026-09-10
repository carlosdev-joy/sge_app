---
name: orquestra-malha-data-unica
description: "Incidente Carga_Vida (2026-08-04): Aguarde liberou com predecessores em datas diferentes. Causa = DAG não republicada rodando por cron. Spec de 5 fases + HOLD ✅ EM PRODUÇÃO desde 2026-08-12 (migrations 081/082); script de reset à força em docs/forcar-reset-ciclo-malha.sql"
metadata: 
  node_type: memory
  type: project
  originSessionId: 80c9c0f8-d96b-4823-bfbd-f3a91475f9ad
  modified: 2026-08-13T02:41:13.747Z
---

Incidente de produção do [[orquestra-sge-app]] (malha `Carga_Vida`,
2026-08-04): o Aguarde deu a condição por satisfeita com **parte dos
predecessores no dia 3 e parte no dia 4**, e os dependentes rodaram com dados
de dois dias. Spec: `docs/spec-malha-data-unica.md`; consultas de diagnóstico:
`docs/diagnostico-liberacao-datas.sql`.

## ⚠️ A CAUSA RAIZ (vale para qualquer malha)
**A data de referência só é calculada por quem roda por AGENDA.** Raiz ligada
ao Início recebe a virada da malha; dependente publicado tem `schedule=None` e
HERDA a data do pai. Quem diverge é o **dependente cuja DAG não foi
republicada depois de a dependência nascer**: ele mantém o cron, roda fora da
ordem e calcula a própria data. É a mesma causa dos "dependentes em verde fora
de ordem". **Republicar os membros corta a fonte** — ver
[[orquestra-republicar-malha]].

E `liberado()` compara **só o ODATE**: sucesso produzido em outro dia real, com
o mesmo carimbo, conta como se fosse da corrida de hoje.

## Decisões do usuário
1. Virada ÚNICA por malha (os membros não podem divergir entre si).
2. Validação ANTES de o Início partir: data divergente → **bloqueia + alerta**.
3. **Equalização automática opcional por malha**: marcada, carimba todos com a
   data da malha e SEGUE, sem parar o operador.
4. ⛔ NÃO remover a data de referência (326 usos em 34 arquivos; é parte do
   índice único `ux_pipe_exec` — seria refazer o motor e reabrir o caso da
   corrida que atravessa a meia-noite).

## Entregue (F1–F5, **PR #272 MERGEADA**, merge b2d3bbd)
- **F1** `POST /malhas/{m}/disparo` recusa (422) com corrida viva ou data
  divergente NO CICLO; dry_run MOSTRA a lista. Banner vermelho na malha para
  "membro com dependência ainda disparando por agenda".
- **F2** migration **081**: `etl_malha.hora_virada` + `equalizar_data`. A
  virada é COMPILADA para todos os membros (o Início só alcançava as raízes);
  só quem diverge é tocado e carimbado.
- **F3** equalização automática: recarimba `data_referencia` do ciclo corrente
  com rastro (`motivo` da linha + evento `DATA_EQUALIZADA`); não roda sob
  corrida viva nem sobre pipeline que já tem linha na data-alvo.
- **F4** o **push** ganhou a trava que só a guardiã tinha (Decisão 5).
- **F5** o **check_agenda** exige malha limpa no gatilho automático (origem
  `agenda` apenas); `dags/utils/malha_ciclo.py` (placeholder `%s`).

✅ **EM PRODUÇÃO desde 2026-08-12** ([[orquestra-deploy-trem-producao]]). A ordem
executada, para referência: migration 081 na 6c → api + front (F1–F3 valem na
hora) → dags/ + **`force_all`**, que a F4 e a F5 exigem.

## 🔒 HOLD do Aguarde e do Início (PRs #272→#273, merge d18bdc7)
Botão **Segurar/Soltar** no diagrama (migration **082**: `retido_em`/
`retido_por` em `etl_malha_no`). **Aguarde** → obedecido pelo PREDICADO (a
consulta traz o id do nó retido na 2ª coluna; push, guardiã e painel herdam);
**Início** → obedecido pelo `check_agenda` (ele não compila linha na 067).
Notificação/Fim recusados (422): não liberam ninguém.
⚠️ **Furo pego no dev**: `malha_do_pipeline` devolvia a PRIMEIRA malha e o
pipeline pertencia a 4 → a trava não pegava. Virou `malhas_do_pipeline`
(lista) e o check percorre TODAS. **Barreira vale no mais restritivo.**
Cascata de fallback **082→078→legado** no predicado: sem ela, banco sem a
coluna viraria "não liberado para todos" (D21) = parada geral.

## 🛠️ Reset à força para corrida de validação (2026-08-11)
Cenário: disparo recusado com "Ciclo em andamento" + "Data de referência
diferente" E o Equalizar da tela recusa ("já existe ciclo na data-alvo —
recarimbar criaria duas"). Beco sem saída pela UI. Script pronto:
`docs/forcar-reset-ciclo-malha.sql` — ✅ **PRs #298 + #299 MERGEADAS** (squash,
2026-08-11), após 3 rodadas de revisão adversarial com 7 achados reais
reproduzidos e corrigidos no SQL Server do dev VPS (os dados SEQSSDVIDA vivem
no ambiente Caixa, fora do meu alcance — o usuário roda o script lá:
`@executar` 0=dry-run/1=força; `@limpar` 0=preserva histórico/1=APAGA).
**Modo @limpar (PR #299)**: passo 6 apaga eventos (data>=@alvo), execuções
(data>=@alvo OU inicio>=@corte), corridas da malha (snapshot cai por FK
CASCADE) e **telemetria por job em etl_job_execution** (start_time>=meia-noite
de @alvo; zero FKs; escopo pela coluna `pipeline` da execução) — é LÁ que a
tela Execuções/Gestão de Falhas lê o "job com falha". Avisos documentados:
FALHA de ODATE anterior só some apontando @alvo p/ aquela data; apagar
eventos apaga a memória de dedup da guardiã → cards do Teams podem ser
REENVIADOS (observar 1–2 ciclos antes do disparo). Para o caso SEQSSDVIDA:
@alvo='2026-08-10', @limpar=1.
Lições T-SQL pagas (valem p/ qualquer script de força):
- NOT EXISTS anti-colisão NÃO vê duas linhas movidas pelo MESMO UPDATE
  (snapshot pré-update) e NULL colide com NULL em índice único → resolver com
  CASE sufixando a chave, truncando o ORIGINAL e nunca o sufixo;
- guarda NOT EXISTS correlacionada DENTRO de `SELECT TOP 1` não "pula quando
  existe" — escolhe o PRÓXIMO sem registro e rasteja 1 insert por rodada;
  fixar a âncora antes da guarda;
- rastro/INSERT de evento sem guarda + XACT_ABORT = o rastro derruba a
  operação (o oficial se protege com try/except; SQL puro não tem);
- TRY_CAST é mais tolerante que o parse do produto (fração de segundo) →
  validar formato ANTES do cast, espelhando o parse real.
Mecânica que o script explora, na ordem:
1. Trava 1 = membros `EXECUTANDO/AGUARDANDO_DEPENDENCIA` em QUALQUER data
   (`substituida_em IS NULL`) → encerrar (status=FALHA + fim + motivo).
2. Trava 2 = execução do ciclo corrente (`inicio >= virada`) com data ≠ alvo —
   **não olha status nem substituida_em** → recarimbar data > alvo p/ o alvo
   (guard NOT EXISTS contra colisão no `ux_pipe_exec`).
3. **`substituida_em` é a chave do redisparo**: o NOT EXISTS do push/claim
   (dags/utils/dependencias.py) ignora ciclo aposentado → aposentar TODOS os
   vivos da data-alvo faz a corrida nova criar ciclo fresco por dependente.
4. Corrida ABERTA em `etl_malha_execucao` → CANCELADA (shape do fechar_corrida).
⚠️ Escrever em `etl_pipeline_execucao` via sqlcmd exige `QUOTED_IDENTIFIER ON`
(índices filtrados da 085; erro 1934) — o script já seta os SET no topo.
⚠️ Antes: parar DagRuns em voo (pai que conclui depois faz push na data velha).
Depois: Republicar pipelines (agenda residual recria a divergência).
O aviso "já rodou (N)" da raiz NÃO filtra substituida_em — segue aparecendo,
é informativo, não trava.

## Lições
- **Trava que existe só na guardiã não protege**: quem dispara na cascata é o
  push, e ele não fazia a checagem. Toda regra de liberação precisa valer nas
  DUAS portas.
- **Erro de consulta na trava do gatilho NÃO pode barrar** (o oposto do
  `liberado()`/D21): ali o risco é disparar cedo, aqui seria parar a produção
  inteira por banco intermitente.
- `from utils import x` num teste com `utils` stubado devolve **MagicMock
  truthy** — a malha parecia suja em toda DAG. Import POR NOME
  (`from utils.x import f`) cai no except quando o módulo não existe, que é o
  comportamento seguro.
- A âncora do fonte gerado (`test_dag_factory_espera`) não é "o fonte não
  muda", é "só muda o que foi DECLARADO" — todo delta novo entra nela.
