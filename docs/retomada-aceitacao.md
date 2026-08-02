# Suíte de aceitação — Retomada F2–F6 (dependências entre pipelines)

Data: 2026-08-02 · Base: `main 5c85655` · Spec: `docs/spec-dependencias-pipelines.md` · Ambiente: dev desta VPS (Airflow :8082, API :8000, UI :8090, banco `orquestra_dev` — runbook `docs/ambiente-dev.md`)

> ## ✅ RETOMADA CONCLUÍDA NO CÓDIGO em 2026-08-02 — itens restantes são de deploy/produção
>
> F2–F6 mergeadas (PRs #243–#248, todas de 2026-08-02). O **smoke §7 oficial da
> spec foi EXECUTADO no dev na F6** (marcas "(smoke§7 2026-08-02 F6)"), com
> evidência dupla (Airflow + banco), harness padrão e limpeza §7 completa:
> **a)** C←A,B pela porta do modal, texto livre → 422 citando o nome ·
> **b)** ciclo → 422 com mensagem clara · **c)** B (o segundo) concluiu 21:53:58
> e C iniciou 21:54:03 (**5 s**), mesma data de referência, `disparado_por=B` ·
> **d)** hora-limite vencida sem B → `JANELA_ESTOUROU` ("aguardando:
> HARNESS_PIPE_B") e C **AGUARDANDO_DEPENDENCIA**, nunca FALHA · **e)** virada
> 20:00, 23:30 simulado por conf (registrado: relógio real 18:5x) → pai carimba
> o dia seguinte e o filho **herda** a mesma data via conf do push ·
> **f)** dependente sem `ExternalTaskSensor`, `schedule=None` ("Never, external
> triggers only"), importErrors 0. E o ajuste F6 do factory foi provado VIVO:
> pendência de publicação ligada pela API (21:56:10) → regeneração fora da API →
> `dag_config_pendente_em = NULL`.
>
> **O que resta em [ ] e SÓ produção (ou gesto humano na tela) fecha:**
> - o **smoke §7 EM PRODUÇÃO** — o portão final, na ordem consolidada dos
>   lembretes "Fora da suíte" (e do preâmbulo da spec): 067/070–073 na 6c →
>   `dags/` → consulta de CSV órfão ANTES → `force_all` → conferir `GETDATE()` →
>   despausar a guardiã → smokes;
> - **D31** — comportamento de desmontagem do modal: gesto de UI, smoke humano;
> - **D54** — invariante PERMANENTE de processo (a matriz de folhas foi
>   executada na retomada — D53/D55 —, mas o item não "fecha": re-prova a cada
>   mudança de `trigger_rule`);
> - **D57** — a fiação está no unitário e a falha real gravou FALHA (D53); o
>   cenário completo "falha em cada ramo de decisão" fica para produção.
>
> Os demais [ ] são de **teste unitário com cobertura JÁ presente na suíte**
> (nomes conferidos um a um na F6, suíte verde): D08, D10, D11, D15
> (`test_predicado_sem_ordenacao_nem_criado_em`), D21
> (`test_liberado_excecao_nao_vira_pode_disparar`), D23
> (`test_d23_d16_trigger_que_levanta_devolve_e_o_pai_segue`), D27 (parcial —
> dedup/canonização em `test_depends_on_presente_replace_all_com_dedup_e_canonizacao`),
> D46 (parcial — 2 das 3 mensagens nomeadas), D47, D48 (idempotência da
> ordenação), D51 (`test_um_pipeline_quebrado_nao_cancela_os_demais`), D52 e
> D59. O fechamento formal fica com as fases donas; **nenhum bloqueia o deploy**.

> ## ⛔ REGRA DE MERGE
> **Nenhuma fase mergeia sem os itens dela marcados como EXECUÇÃO terem sido EXECUTADOS no ambiente dev** — DAG rodando de verdade, efeito observado no Airflow (estado do DagRun, das tasks) **e** no banco (`etl_pipeline_execucao`, `etl_dependencia_evento`). Teste que compila a string da DAG ou verifica a ausência de um INSERT **não conta** como execução: foi exatamente esse método que deixou 1053 testes verdes com um defeito catastrófico na main (PR #229).

**Por que esta suíte existe.** A 1ª execução (PRs #218–#223) foi reprovada por 2 revisões adversariais: 21 defeitos; as correções A–E (PRs #224–#228) fecharam 14 e **introduziram ~15 novos** — o pior fazia todo pipeline que falha aparecer VERDE no Airflow. Tudo revertido na PR #229 (só a F1 sobrevive). Esta suíte é a união deduplicada dos 21 + ~15 + 5 defeitos do QA + aceites do §5 da spec, agrupada pelas 5 causas-raiz.

**Legenda.**
- Fase: F2 registro de execução · F3 disparo por condição · F4 guardiã · F5 UI/API de cadastro · F6 geração pela tabela. Itens `F1✔` já estão fechados na main e entram como **não-regressão**.
- Verificação: **EXECUÇÃO no dev** (obrigatória p/ comportamento distribuído: trigger rules, corridas, estado compartilhado, UI viva) · **teste unitário** (funções puras/contratos; deve EXECUTAR o código gerado, não caçar substring) · **leitura** (inspeção/documento).
- Origem entre colchetes: `QAn` = §3 da spec; `An..En` = defeitos da 1ª revisão fechados pelas correções A–E (PRs #224–#228); `Nn` = defeitos NOVOS da 2ª revisão (memória do projeto); `aceite Fn` = §5; `smoke §7x` = §7.

---

## A — Evento × relógio (agenda, ODATE, virada)

*Causa-raiz: o `check_agenda` raciocina em relógio de parede; disparo por dependência é evento. Misturar os dois gerou PULADO em 100% dos disparos e fechamento mensal rodando 30x/mês.*

- [x] (E-dev 2026-08-02 F3) **D01** (F3 · EXECUÇÃO no dev) — A DAG gerada de um pipeline com dependência não contém `ExternalTaskSensor` e tem `schedule=None`, visível na UI do Airflow do dev; código morto dos sensores removido; o outlet Dataset permanece só como ponte para DAGs antigas não regeradas. [QA1 · aceite F3 · smoke §7f]
- [x] (E-dev 2026-08-02 F3 — pai de 41 min de relógio; sensor removido = sem polling/timeout por construção) **D02** (F3 · EXECUÇÃO no dev) — Predecessor que dura mais de 1h não reprova o dependente: no modelo por push não existe timeout de polling. Simular pai lento no dev e conferir que o filho dispara ao final. [QA2]
- [x] (E-dev 2026-08-02 F3) **D03** (F3 · EXECUÇÃO no dev) — Dependente com `horarios_especificos`/`dias_horarios_mes` disparado por evento (`dep__`/`guardia__`) NÃO é PULADO: regras de relógio só se aplicam a disparo por cron. Na 1ª execução ele era pulado em 100% dos disparos e a cascata morria em silêncio. [A1]
- [x] (E-dev 2026-08-02 F3 — weekly+monthly em execução; os 5 tipos no unitário) **D04** (F3 · teste unitário + EXECUÇÃO no dev) — A restrição de DIA sobrevive ao `schedule=None` para TODOS os tipos: weekly, monthly, biweekly **e também `monthly_days_times` e `dias_semana`** (os dois que a correção A esqueceu). Fechamento mensal dia 5 com dependência roda só no dia 5, nunca 30x/mês. [A2 · N5]
- [x] (E-dev 2026-08-02 F3) **D05** (F3 · teste unitário) — `schedule_dow=0` (domingo) é tratado como domingo: o padrão `int(x or 1)` transformava domingo em segunda. [N6]
- [x] (E-dev 2026-08-02 F3) **D06** (F3 · EXECUÇÃO no dev) — `somente_dias_uteis` e `calendario` avaliam a **data de referência**, não o relógio: pai sexta 23:30 → filho sábado 00:10 na mesma corrida LIBERA (o caso que motivou a spec). [A3]
- [x] (E-dev 2026-08-02 F3) **D07** (F3 · EXECUÇÃO no dev) — Combinação `somente_dias_uteis` + `hora_virada`: com virada 20:00, disparo de sexta 23:30 carimba SÁBADO — a regra de dia útil não pode PULAR essa corrida (regressão que a correção A introduziu no próprio caso que dizia resolver). [N4]
- [ ] **D08** (F3 · teste unitário) — Blackout continua medindo o RELÓGIO, de propósito (freeze operacional é sobre "agora"): não regride com as mudanças de D03–D07. [correção A]
- [x] (E-dev 2026-08-02) **D09** (F2 · EXECUÇÃO no dev) — Toda execução de pipeline gera **exatamente uma** linha em `etl_pipeline_execucao` por `execution_id`, com `data_referencia` preenchida e status final coerente (SUCESSO/FALHA/PULADO). [aceite F2]
- [ ] **D10** (F2 · teste unitário) — O instante do cálculo da data de referência é o horário AGENDADO (`data_interval_end`/`logical_date`), não o relógio: atraso de fila que empurra a execução para depois da meia-noite não muda a data. [PR #219]
- [ ] **D11** (F2 · teste unitário) — `conf['data_referencia']` prevalece sobre o cálculo pela virada; sem conf, a cadeia é coluna do pipeline → config global → default 00:00. [aceite F2]
- [x] (E-dev 2026-08-02 F3) **D12** (F3 · EXECUÇÃO no dev) — Herança ponta a ponta: pipeline com `hora_virada=20:00` disparado 23:30 carimba o dia seguinte E o dependente disparado por ele herda a MESMA data via conf, sem recalcular. [aceite F1/F3 · smoke §7e]

## B — Corrida sem chave estável (estado em `etl_pipeline_execucao`)

*Causa-raiz: reserva com `execution_id NULL` que nunca casava com o UPDATE da DAG, PULADO mascarando SUCESSO, EXECUTANDO commitado antes do trigger. Tudo terminava em corrida presa e dependente que nunca libera — em silêncio.*

- [x] (E-dev 2026-08-02 F3) **D13** (F3 · EXECUÇÃO no dev) — A DAG **adota** a linha-reserva criada pelo push/guardiã (carimba o `execution_id` na linha NULL) em vez de inserir uma segunda linha; ao fim do dia não existe reserva órfã presa em EXECUTANDO/AGUARDANDO. [B1]
- [x] (E-dev 2026-08-02 F3) **D14** (F3 · teste unitário + EXECUÇÃO no dev) — A liberação pergunta "**existe SUCESSO nesta data de referência?**", não "o mais recente é SUCESSO": pipeline 3x/dia com PULADOs intercalados aos SUCESSOs libera o dependente (semântica da condição OUT do Control-M). [B2]
- [ ] **D15** (F3 · teste unitário) — O mascaramento do PULADO não volta pela porta dos fundos: `criado_em NOT NULL DEFAULT GETDATE()` fazia `COALESCE(inicio, criado_em)` eleger o PULADO como "mais recente", e a leitura do próprio estado (`_meu`) lia PULADO e recusava liberar. Nenhuma ordenação por `criado_em` pode reintroduzir o defeito. [N7]
- [x] (E-dev 2026-08-02 F3 + E-dev 2026-08-02 F4 — E4: push sabotado devolveu a reserva e o ciclo seguinte da guardiã ordenou e disparou C) **D16** (F3 · EXECUÇÃO no dev) — Trigger que falha (DAG não serializada, worker morto) **devolve a reserva** (`WHERE execution_id IS NULL` — corrida já adotada não é revertida) e a guardiã redispara no ciclo seguinte; nenhuma corrida fica presa em EXECUTANDO sem alerta. [B3]
- [x] (E-dev 2026-08-02 F3) **D17** (F3 · EXECUÇÃO no dev) — Rerun após falha: plantonista corrige, dá Clear, a DAG re-roda verde → a linha da corrida vira SUCESSO e **libera a cadeia**. A guarda `apenas_se_executando` da correção B deixava a linha FALHA para sempre — REGRESSÃO (antes da feature funcionava). [N2]
- [x] (E-dev 2026-08-02 F4 — E5: colisão real provocada; push do pai perdeu o claim às 14:32:06 ("ja tem corrida — sem novo disparo") e a guardiã disparou às 14:32:08 adotando a linha; UMA execução de C) **D18** (F4 · EXECUÇÃO no dev) — Push do pai e guardiã avaliando o mesmo dependente no mesmo instante produzem **uma única** execução: só quem vira a linha `AGUARDANDO_DEPENDENCIA→EXECUTANDO` dispara. Provocar a corrida no dev (guardiã em intervalo curto + conclusão simultânea). [risco §6.5]
- [x] (E-dev 2026-08-02 F3) **D19** (F3 · EXECUÇÃO no dev) — C depende de A e B: A conclui e B não → C NÃO dispara; B conclui → C dispara em menos de 1 min com a mesma data de referência (quem completa a condição por último dispara). [aceite F3 · smoke §7c]
- [x] (E-dev 2026-08-02 F3) **D20** (F3 · teste unitário + EXECUÇÃO no dev) — Só SUCESSO libera: FALHA, EXECUTANDO, PULADO e ausência de execução na data NÃO liberam; SUCESSO em OUTRA data de referência também não. [F3 PR #220]
- [ ] **D21** (F3 · teste unitário) — Erro de consulta na avaliação (lista de predecessores vazia por exceção) não vira "pode disparar". [F3 PR #220]
- [x] (E-dev 2026-08-02 F3 + E-dev 2026-08-02 F4 — E6: push segurou na janela; ciclos da guardiã antes da hora seguraram; o PRIMEIRO ciclo após a hora disparou adotando o run_id do push) **D22** (F3+F4 · EXECUÇÃO no dev) — `nao_iniciar_antes=08:00` com liberação 07:10: o push segura e a guardiã dispara às 08:00 — nem antes, nem nunca. [aceite F3]
- [ ] **D23** (F3 · teste unitário) — O disparo de dependentes tem try/except POR ITEM (um dependente com erro não cancela a avaliação dos demais) e uma falha no disparo nunca derruba o pipeline pai. [B bônus · F3 PR #220]

## C — Contrato de API, cadastro e geração

*Causa-raiz: campos write-only, replace-all sem dedup/atomicidade, teto silencioso na lista, painel divergindo do motor, geração lendo espelho.*

- [x] (E-dev 2026-08-02 F3) **D24** (F1✔ · teste unitário — não-regressão) — Ciclo detectado por BFS sobre TODAS as dependências: A depende de "X,B" e B depende de A → 422 (fechado na F1, guarda permanente). [QA3]
- [x] (E-dev 2026-08-02 F3) **D25** (F1✔ · teste unitário — não-regressão) — Predecessor inexistente → 422 citando o nome + FK no banco; nunca grava (fechado na F1, guarda permanente). [QA4]
- [x] (V-dev 2026-08-02 F5) **D26** (F5 · teste unitário + EXECUÇÃO no dev) — `hora_virada`, `nao_iniciar_antes` e `hora_limite_dependencia` são devolvidos pelo GET e o UPDATE só grava o que veio no body: editar a descrição (ou inativar, que monta body parcial) NÃO zera os três. Smoke: editar no dev e conferir as colunas no banco. [C1]
- [ ] **D27** (F5 · teste unitário — parcialmente na main) — Replace-all de dependências com dedup case-insensitive (collation CI: 'A,a' viola índice) e atomicidade: falha depois do DELETE propaga (sem estado parcial que apague dependência com tela 200); rollback explícito nos caminhos de erro. `deduplicar`/`_rollback_silencioso` sobreviveram ao revert — não regredir. [C2]
- [x] (V-dev 2026-08-02 F5) **D28** (F5 · EXECUÇÃO no dev + leitura) — O modal de dependências alcança TODOS os pipelines: sem teto silencioso. O fix `limit=2000` era INERTE (`list_pipelines` clampa em `min(100,...)` — conferir o clamp por leitura); a solução é paginar, padrão que já existe em `Pipelines.tsx`. [E3 · N8]
- [x] (V-dev 2026-08-02 F5 — semântica viva no V7: PULADO mais recente + SUCESSO na data → liberado no /estado; a paridade de SQL corre na suíte da PR) **D29** (F5 · teste unitário) — O painel usa o MESMO predicado do motor: `GET /pipelines/dependencias/estado` não pode divergir de `dags/utils/dependencias.py` (na 1ª execução o `EXISTS` foi aplicado só no motor). Exigir teste de paridade entre os dois, como o da F9 (`api/services/data_referencia.py` × `dags/`). [N9]
- [x] (V-dev 2026-08-02 F5 — publicação REAL no dev: editar agendamento e dependência ligou `dag_config_pendente=1` nas duas portas; gerar-dag + reconciliador zeraram; .py regerado com `schedule=None` de dependente) **D30** (F5 · EXECUÇÃO no dev) — Mudar dependência marca a DAG como suja e oferece publicar (`markDagDirty`): sem isso a DAG segue com o cron antigo e roda por horário E por evento. Conferir no dev que a DAG regerada mudou de schedule. [E1]
- [ ] **D31** (F5 · EXECUÇÃO no dev) — O modal desmonta ao fechar (montado só quando aberto): "Cancelar" descarta a seleção e um chip removido não ressuscita na próxima confirmação. [E2]
- [x] (V-dev 2026-08-02 F5 — API/contrato: `/estado` e `/malhas/{m}/execucao` com `faltantes` e degradação sem 067 provadas vivas; o RENDER do painel/tooltip conferido só por bundle — gesto visual fica p/ o smoke humano) **D32** (F5 · EXECUÇÃO no dev) — "Aguardando dependência" tem consumidor: o card da Malha/dashboard mostra o estado e **quais** predecessores faltam ("esperando PIPE_B, PIPE_C"); o dashboard distingue "aguardando dependência" de "não executou". Sem a 067 a tela degrada sem quebrar. [E4 · aceite F5]
- [x] (smoke§7 2026-08-02 F6 — a/b pela PORTA do modal, `POST /dependencias`: texto livre → 422 citando o nome; ciclo → 422 "Dependência circular … fecha um ciclo"; a explicação/aviso de inativo no RENDER conferida por leitura — o gesto visual fica p/ o smoke humano) **D33** (F5 · EXECUÇÃO no dev) — Impossível salvar dependência por texto livre; o modal explica por que um pipeline não pode ser escolhido (ciclo/ele mesmo) e avisa quando o escolhido está INATIVO (dependente de inativo nunca libera). [aceite F5 · smoke §7a/§7b]
- [x] (V-dev 2026-08-02 F5 — banco provado vivo no V6: remover a última dependência + register com `""` → NULL nos dois e `hora_virada` permanece; o "só aparecem com dependência" é do form — smoke humano) **D34** (F5 · teste unitário + EXECUÇÃO no dev) — Janela e hora-limite só aparecem com dependência e são LIMPOS ao remover a última — sem configuração órfã no banco. [F5 PR #222]
- [x] (V-dev 2026-08-02 F5 — vivo: `20:00`→`20:00:00`; `""`→NULL; `99:99`/`07:x0`→NULL com 2 `avisos` no payload e cadastro aceito) **D35** (F5 · teste unitário) — Normalização `HH:MM`→`HH:MM:SS`; vazio vira NULL ("sem regra" ≠ "regra às 00:00", que geraria alerta diário); hora inválida vira NULL sem recusar o cadastro inteiro. [F5 PR #222]
- [x] (unitário entregue na F3, conferido 2026-08-02 F6 — `test_dag_factory_dependencias_f3.py::test_contrato_none_x_dict_do_supplement`) **D36** (F6 · teste unitário) — `_dependencias_da_tabela` devolve **`None`** quando a tabela não existe (chamador preserva o que a proc trouxe) e **`{}`** quando existe e está vazia (sobrescreve): deploy de `dags/` sem a 067 NÃO apaga a dependência de todas as DAGs. [F6 PR #223]
- [x] (smoke§7 2026-08-02 F6 — EXECUÇÃO estrita: dependência inserida SÓ na tabela, `depends_on` NULL; a factory gerou HARNESS_PIPE_Q com o `schedule=None` do RAMO DEPENDENTE ("o gatilho e o disparo dos predecessores", não o "sob demanda") e 0 sensor — a SP não precisou mudar, o supplement da 067 é a fonte) **D37** (F6 · EXECUÇÃO no dev) — Fio solto §10.3 CONFIRMADO no dev: a `sp_etl_pipelines_pendentes_criar` NÃO devolve `depends_on` — a F6 cobre a SP (ou o supplement de colunas) explicitamente, e a DAG gerada no dev reflete dependência gravada SÓ na tabela. [§10.3]
- [x] (smoke§7 2026-08-02 F6 — dependentes C/F/Q gerados com `schedule=None` e 0 `ExternalTaskSensor`, importErrors 0; o "cron intacto" fica no unitário byte-a-byte da F3 (`test_folhas_byte_identicas_a_f2`, `test_sem_067_sem_csv_compila_no_cron`) — a regra do harness PROÍBE cadastrar cron no dev) **D38** (F6 · teste unitário + EXECUÇÃO no dev) — Dependência vinda da tabela vira `schedule=None` na DAG gerada; pipeline sem dependência mantém o cron intacto (comparar as duas DAGs geradas no dev). [F6 PR #223 · correção A]
- [x] (leitura 2026-08-02 F6 — §3.4 reescrito em linguagem de operador: as duas portas de cadastro, hora não vale × DIA continua valendo, janela/hora-limite, ODATE com o exemplo da virada 20:00, os 4 eventos da guardiã e onde vê-los, reprocesso — Clear empurra a cadeia / NAO_LIBEROU exige trigger com data —, badge "publicação pendente") **D39** (F6 · leitura) — `MANUAL_USUARIO.md` §3.4 atualizado: escolher da lista, o horário deixa de valer, janela/limite e data de referência com o exemplo da virada 20:00. [F6 PR #223]
- [x] (2026-08-02 F6 — a metade de código no unitário da F3: órfão/sem-067 → recusa RUIDOSA da geração, nunca regressão a cron em silêncio (`test_sem_067_com_csv_recusa_ruidosamente`, `test_tabela_vazia_com_csv_e_orfao_e_recusa`); a metade operacional virou passo da ordem de deploy no preâmbulo da spec — consulta de órfãos ANTES do force_all, porque `migrate.py` descarta PRINT) **D40** (F6 · leitura + teste unitário) — `sql/migrate.py` DESCARTA `PRINT` (`cur.messages` nunca é lido): relatório de órfãos do `depends_on` precisa chegar ao operador por outra via; e um `depends_on` órfão NÃO pode fazer o pipeline sair de `schedule=None` e voltar a rodar sozinho no cron, em silêncio. [gotcha infra 1ª execução]

## D — Guardiã (premissas alinhadas com a execução)

*Causa-raiz: guardiã calculando datas por premissas próprias, alertando o estado normal da malha e ordenando corridas que nunca resolvem. Rede de segurança ruidosa = rede que ninguém lê.*

- [x] (E-dev 2026-08-02 F4 — E7: JANELA_ESTOUROU no 1º ciclo pós-limite; E12: PREDECESSOR_FALHOU imediato no mesmo ciclo da ordenação; E11: NAO_LIBEROU + evento no fechamento sem deadline) **D41** (F4 · EXECUÇÃO no dev) — O silêncio do defeito original vira ALERTA: predecessor que não rodou o dia inteiro (pulado/inativo/falhou) → dependente ganha evento e card; nenhuma cascata morre sem aviso. [QA5 · F4 PR #221 · risco §6.2]
- [x] (E-dev 2026-08-02 F4 — E9: 137 min de ciclos a cada 1 min sobre malha saudável = ZERO evento/linha falsa (janela reduzida vs "dia inteiro", anotada); E3: SUCESSOs velhos não geraram DATA_DIVERGENTE; E8: corrigida a virada, ciclo seguinte sem evento novo) **D42** (F4 · EXECUÇÃO no dev) — `DATA_DIVERGENTE` só com carimbo RECENTE em outra data: o sucesso normal de ontem NÃO alerta. Teste de ruído: malha com vários dependentes atravessa um dia inteiro no dev com ZERO card falso (na 1ª versão: 200 dependentes = 200 cards/dia). [D1 · N10]
- [x] (E-dev 2026-08-02 F4 — E6/E5: a rede varreu e adotou a linha que o PUSH carimbou (dep__*) na data do pai; E15: virada 20h→amanhã com dia_op de origem e corredor pós-meia-noite pelos candidatos) **D43** (F4 · EXECUÇÃO no dev) — A guardiã examina as datas EM ABERTO que os predecessores realmente carimbaram (não só a calculada pela virada do DEPENDENTE): cobre a corrida que atravessa a meia-noite — justamente a que ela existe para proteger. [D2]
- [x] (E-dev 2026-08-02 F4 — E2: DOMINGO real com pai somente_dias_uteis → "não ordenado: HARNESS_PAI_A fora do dia", zero linha órfã, zero evento) **D44** (F4 · EXECUÇÃO no dev) — Predecessor PULADO não ordena corrida: sábado com pai pulado por dias úteis NÃO gera linha `AGUARDANDO` órfã nem `JANELA_ESTOUROU` de fim de semana. [D3 · N11]
- [x] (E-dev 2026-08-02 F4 — E3: dependência recém-cadastrada com 3 SUCESSOs de datas passadas → ciclo criou SÓ a linha do dia corrente, ZERO disparo/linha retroativa) **D45** (F4 · EXECUÇÃO no dev) — Cadastrar uma dependência nova NÃO dispara datas passadas: a varredura de datas em aberto tem guarda de idade (na 1ª versão, `_datas_em_aberto` de 48h rodava o dependente retroativamente). [N3]
- [ ] **D46** (F4 · teste unitário) — As três mensagens corretas e alcançáveis: "sem execução nenhuma" / "aguardando fulano" / "liberado mas sem disparo" — o ramo "nenhum predecessor executou" saía quando TODOS tinham executado. [D4]
- [ ] **D47** (F4 · teste unitário) — `DEPENDENCIA_GUARDIA_INTERVAL_MINUTES` com 0, 60 ou lixo não derruba o import da DAG: clamp 1..59, padrão do `etl_ds_monitor_centralizado`. [D5]
- [ ] **D48** (F4 · teste unitário) — `_ordenar` informa se criou de fato: violação de índice não faz o ciclo assumir ordenação e gravar `JANELA_ESTOUROU` sobre corrida que já está rodando. [D bônus]
- [x] (E-dev 2026-08-02 F4 — parte EXECUÇÃO: E7 evento+PENDENTE (nunca FALHA), ciclos repetidos sem duplicata/reenvio, notificado_em NULL sem 2xx (degradação sem webhook), log sem URL; E8 detalhe cita as duas datas; unitários da F4 correm na PR) **D49** (F4 · EXECUÇÃO no dev + teste unitário) — Deadline: passou de `hora_limite_dependencia` sem liberar → evento `JANELA_ESTOUROU` + card Teams e o pipeline fica **PENDENTE, nunca FALHA**; `DATA_DIVERGENTE` cita as DUAS datas; eventos idempotentes por `(pipeline, data, tipo)` — ciclo repetido não duplica nem reenvia; `notificado_em` só após 2xx; URL do webhook fora do log. [aceite F4 · smoke §7d]
- [x] (E-dev 2026-08-02 F4 — E4: pai concluiu com filho sem DAG no disco → devolução F3 ("reserva devolvida"); restaurado o arquivo, o ciclo seguinte da guardiã ordenou E disparou C) **D50** (F4 · EXECUÇÃO no dev) — Push perdido: predecessor morre entre o fim e o trigger (matar/pausar no dev) → a guardiã dispara o dependente no ciclo seguinte. [F4 PR #221]
- [ ] **D51** (F4 · teste unitário) — Um pipeline com cadastro problemático não interrompe a varredura dos demais (try/except por pipeline, dentro do laço). [F4 PR #221]
- [ ] **D52** (F4 · teste unitário) — Sem a migration 067 o ciclo da guardiã termina limpo (degradação sem exceção). [F4 PR #221]

## E — Trigger rules e folhas do grafo

*Causa-raiz: o estado do DagRun é decidido pelas FOLHAS do grafo — mudar a trigger rule de uma task terminal pode esconder a falha do pipeline inteiro. Foi o defeito catastrófico que motivou o revert.*

- [x] (E-dev 2026-08-02) **D53** (F2 · EXECUÇÃO no dev) — **O item mais importante da suíte.** Pipeline com job falhando → DagRun **FAILED** no Airflow, linha `FALHA` em `etl_pipeline_execucao` e card de erro — executado no dev com falha REAL. Na main revertida, `t_exec_fim` (ALL_DONE) + `t_disparar_dependentes` (ALL_SUCCESS) deixavam nenhuma folha em falha → DagRun VERDE em 100% dos pipelines que falhavam. [N1]
- [ ] **D54** (F2 · leitura + EXECUÇÃO no dev) — Invariante das folhas: para TODA mudança de `trigger_rule` no `etl_dag_factory`, enumerar as folhas do grafo gerado e provar por EXECUÇÃO que existe folha em estado de falha quando qualquer job falha. Matriz mínima no dev: sucesso total · falha no meio · decisão com ramo vazio · corrida pulada. [lição-mãe PR #229]
- [x] (E-dev 2026-08-02 F3) **D55** (F3 · EXECUÇÃO no dev) — A tensão B4×N1 resolvida SIMULTANEAMENTE: decisão-raiz com ramo vazio (publish SKIPPED) → a corrida FECHA (não fica eterna em EXECUTANDO) **e** a falha continua visível no DagRun. As duas propriedades verificadas na MESMA matriz de execução — a correção B consertou uma quebrando a outra. [B4 × N1]
- [x] (E-dev 2026-08-02) **D56** (F2 · teste unitário + EXECUÇÃO no dev) — Nenhuma função de helper referenciada em `default_args`: no arquivo gerado as consts saem ANTES dos helpers → `on_failure_callback` ali = NameError no import (que o pytest de geração não pega). Manter `test_default_args_nao_referencia_helper` + conferir `airflow dags list-import-errors` limpo no dev. [gotcha F2]
- [ ] **D57** (F2 · EXECUÇÃO no dev) — `ONE_FAILED` só enxerga upstream DIRETO: `registrar_falha` pendura nos MESMOS fins de ramo do `teams_error` (nunca no `publish_dataset`, que numa falha nem roda); falha em qualquer ramo grava `FALHA`. [gotcha F2 · PR #219]
- [x] (E-dev 2026-08-02) **D58** (F2 · teste unitário + EXECUÇÃO no dev) — `PULADO` gravado por WRAPPER do `check_agenda` cobre os 5 caminhos de saída (horários, dia+hora do mês, blackout, dia útil, calendário): corrida pulada nunca fica sem registro — indistinguível de "nunca ordenada" é o que a guardiã não pode ter. [F2 PR #219]
- [ ] **D59** (F2 · teste unitário) — O registro de execução NUNCA derruba o pipeline: sem a 067, loga e segue — carga que rodou bem não falha por observabilidade. [F2 PR #219 · risco §6.3]
- [x] (E-dev 2026-08-02) **D60** (F2 · EXECUÇÃO no dev) — `registrar_inicio` fica DEPOIS do `check_agenda` (corrida pulada não vira EXECUTANDO eterno) e ANTES do primeiro job (falha logo no começo já encontra a linha) — sem reabrir o gotcha do factory_log órfão. [F2 PR #219]

---

## Resumo

| Grupo | Itens | EXECUÇÃO no dev | teste unitário | leitura |
|---|---|---|---|---|
| A — evento × relógio | D01–D12 | 8 | 5 | — |
| B — corrida sem chave | D13–D23 | 8 | 4 | — |
| C — contrato API/geração | D24–D40 | 8 | 12 | 3 |
| D — guardiã | D41–D52 | 7 | 6 | — |
| E — trigger rules/folhas | D53–D60 | 7 | 4 | 1 |

(Itens com verificação dupla contam nas duas colunas.)

Cobertura por fase: **F2** D09–D11, D53–D60 · **F3** D01–D08, D12–D17, D19–D23, D55 · **F4** D18, D22, D41–D52 · **F5** D26–D35 · **F6** D36–D40 · **não-regressão F1** D24–D25.

## Fora da suíte (lembretes de deploy — não são aceites)

1. Ordem obrigatória em produção: migration 067 → confirmar F2 gravando (`SELECT TOP 20 * FROM dbo.etl_pipeline_execucao ORDER BY id DESC`) → **regerar as DAGs** (`force_all`; sem isso NADA muda — o `deploy.sh` exclui `generated/`) → despausar `etl_dependencia_guardia` → começar por um PAR de pipelines de teste.
2. Consulta de dimensionamento antes do deploy: pipelines ativos com `depends_on` preenchido, por `schedule_type` (ver memória do projeto).
3. Pendências §10 pós-deploy validado: aposentar o CSV `depends_on` + `trigger_por_dependencia` numa migration de limpeza.
