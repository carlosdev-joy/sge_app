# ⚙️ Parâmetros de execução dos jobs DataStage — o `-param` chega ao DataStage

**Compatibilidade:** Apache Airflow 2.x | SQL Server | IBM InfoSphere DataStage 11.7 (`dsjob -run -param` e `dsjob -lparams` via SSH, o mesmo acesso do operador de hoje)
**Migrations:** **107** (`107_job_param_datastage.sql`, F1), **108** (`108_pipeline_param.sql`, F4) e **109** (`109_job_param_override.sql`, F5) — deploy.sh etapa 6c, responder **s**
**Spec:** `docs/spec-parametros-job-datastage.md` (F1 = #376 · F2 = #377 · F3 = #378 · F4 = #379 · F5 = #380 · F6 = esta PR)
**Manual:** `docs/MANUAL_USUARIO.md` §3.10 (parâmetros: origem, cálculo, importar do DataStage, Encrypted, defaults, rastro), §3.1 (defaults no wizard), §3.2 (Etapas), §2.2 (sobreposição na reexecução), §4.6 (deploy) e §5 (FAQ)
**Depende de:** `ORQUESTRA_CONN_KEY` no **worker do Airflow** (a mesma que o `orquestra-api` já usa nas conexões cifradas da 054) — só para parâmetros do tipo Encrypted

---

## 📋 Resumo

Até aqui o Orquestra disparava todo job DataStage **sem nenhum `-param`**: o job
rodava com os defaults do design e do Parameter Set, e não havia onde dizer "passe
a data de referência" ou "use este caminho". Com a F1 (modelo e API) e a F2 (esta
PR, runtime), a etapa DataStage passa a ter **parâmetros cadastrados no Orquestra**
que o operador resolve **a cada execução** e envia no `dsjob -run`:

- **valor fixo** (String, Integer, Float, Date, Time, Timestamp, Pathname, List);
- **valor calculado** a partir de uma data — **referência da corrida** (ODATE),
  data lógica do Airflow ou data da execução — com o cálculo em ordem fixa
  **meses → âncora → dias → formato**. O caso mensal: `pDataIni` = referência
  −1 mês, início do mês; `pDataFim` = referência −1 mês, fim do mês;
- **run_id** da corrida (rastreabilidade);
- **Encrypted**: cifrado no banco com a chave Fernet das conexões, decifrado só
  no disparo, **nunca** em log.

O que foi enviado fica registrado em três lugares, sempre com o mesmo texto:
a linha `[DS] parâmetros:` no log da task, a coluna `params_json` de
`etl_ds_job_log` e (F3) o modal de detalhe da execução.

```
[DS] parâmetros: pDataIni=2026-08-01 (etapa · referência 2026-09-09 → -1 mês → início do mês → 2026-08-01)
                 · pDataFim=2026-08-31 (etapa · referência 2026-09-09 → -1 mês → fim do mês → 2026-08-31)
                 · pSenha=*** (etapa · fixo (Encrypted))
[DS] trigger rc=0 | Job started
```

> **Sem parâmetro cadastrado, nada muda:** o comando é byte a byte o de sempre e
> nenhuma chamada extra é feita. Até a F3 não há tela para cadastrar — só a API.

> ⚠️ **Encrypted e o log do DataStage.** O Orquestra mascara o valor do lado dele
> (comando no log, mensagens de erro, `params_json`). Mas o **DataStage** grava os
> parâmetros recebidos na entrada "Starting Job" do log do job — e só os
> mascara com asteriscos quando o parâmetro **do job** é do tipo Encrypted no
> Designer. Um valor Encrypted no Orquestra enviado a um parâmetro String no job
> aparece em claro no `dsjob -logsum` (que vai para o log da task e para
> `etl_ds_job_log.log_summary`). Regra: **Encrypted no Orquestra só para
> parâmetro Encrypted no job.** O `-lparams` devolve só nomes, então o operador
> não tem como conferir o tipo por você.

## 🔍 Como o operador decide (F2)

1. Lê os parâmetros da etapa em `etl_pipeline_job_param` **em runtime** (não
   ficam embutidos na DAG: trocar um valor não exige "Publicar nova versão").
   Sem banco → a etapa **falha antes do disparo** (nunca roda "sem os parâmetros").
2. Com parâmetro cadastrado, chama `dsjob -lparams` e confere: nome que o job
   **não declara** → falha antes do disparo, listando o que o job declara
   (o DataStage distingue maiúsculas de minúsculas).
3. A data de referência vem da linha desta corrida em `etl_pipeline_execucao`
   (nasce no `check_agenda`); fallback `conf['data_referencia']`; sem os dois →
   falha antes do disparo. Nunca "a data de hoje".
4. Monta `-param nome=valor` (quotado para o shell quando precisa) e dispara.
   O comando só vai para o log **mascarado** (`***` no Encrypted).

## 🧩 Defaults no nível do pipeline (F4)

Um Parameter Set vale para todos os jobs — e agora o **pipeline** guarda defaults
com o mesmo vocabulário da etapa (Construção › Pipelines › passo Notificações /
Execução, seção **Parâmetros DataStage do pipeline**). O operador aplica cada
default **só à etapa cujo job declara o nome** (conferido no `dsjob -lparams`);
job que não declara ignora, e o nome ignorado sai na linha `[DS] parâmetros:`.
A etapa pode sobrepor pelo mesmo nome — o painel da etapa mostra
"Defaults do pipeline: … · sobreposto pela etapa". Tabela nova
`etl_pipeline_param` (migration **108**); sem ela, a seção não aparece e nada
muda.

## 🔁 Sobreposição na reexecução (F5)

No modal **Reexecutar a partir de…** (painel da etapa no Fluxo), a seção
**Parâmetros desta reexecução** lista, por etapa DataStage que vai rodar de
novo, cada parâmetro com o **valor que iria ao DataStage** na data de
referência da corrida (defaults do pipeline marcados "se o job declarar"). O
operador digita um valor novo que vale **só nesta corrida** — a agendada
seguinte volta ao cadastro. Encrypted não se sobrepõe. A sobreposição é gravada
em `etl_job_param_override` (migration **109**) **antes** do clear e desfeita se
o Airflow recusar; o operador carimba `consumido_em` quando a usa, e ela
aparece no `[DS] parâmetros:` com fonte `rerun` e no `params_json`. A auditoria
do rerun registra os nomes sobrepostos (nunca valores).

## 📥 Importar do DataStage (F6)

No editor de parâmetros da etapa, o botão **Importar do DataStage** lê os
parâmetros que o job **declara** no lineage ISX já extraído (Governança › Job
DataStage) e acrescenta os que faltam — nome, tipo do DataStage e o default como
valor fixo (Encrypted vem sem valor; o default ofuscado nunca vira valor). Um
Parameter Set aparece no ISX só como conjunto: os membros são cadastrados como
`PSet.Param`; nomes fora da régua do Orquestra (`$APT_…`) são ignorados com
aviso. Sem lineage extraído, o botão orienta a extrair primeiro; extração com
erro → aviso para reextrair, sem importar. Nada é salvo até o usuário salvar a
etapa.

## 🚀 Deploy

| Passo | O quê |
|---|---|
| 6c | Migrations **107** (F1), **108** (F4) e **109** (F5) → **s**. Sem a 107: nenhum parâmetro é enviado, com aviso no log da task; sem a 108: sem defaults de pipeline, seção oculta; sem a 109: a sobreposição no rerun é recusada com mensagem clara |
| `dags/` | `dags/utils/datastage_operator.py`, `dags/utils/ds_params.py` (novo) e `dags/etl_dag_factory.py` → **sim** para `dags/` |
| worker | ⚠️ **Reiniciar o worker do Airflow** — ele cacheia `dags/utils/` (task verde com código antigo sem o restart) |
| `.env` | `ORQUESTRA_CONN_KEY` no `x-airflow-common` (worker), igual à do `orquestra-api` — exigida só ao disparar etapa com parâmetro Encrypted |
| DAGs | Republicar as DAGs dos pipelines que vão usar parâmetro (o bloco ganha `pipeline_name=PIPELINE_NAME`; sem republicar, o operador cai no `dag_id`, que é igual — funciona, mas republique para ficar explícito) |
| `config/` | **n** (nginx de produção está à frente do repo) |

## ✅ Conferência pós-deploy

a) Etapa DataStage **sem** parâmetro, `verbose_log` ligado: log da task com `[DS] comando:` idêntico ao de antes, sem `-lparams`.
b) Via API (`POST /pipelines/jobs/register` com `params`), cadastrar `pTeste` String fixo num job que declara `pTeste`: rodar; log com `[DS] parâmetros: pTeste=…`; `dsjob -logsum` mostra o valor na entrada "Starting Job".
c) `pDataIni`/`pDataFim` (−1 mês, início/fim do mês): log com as duas descrições; `SELECT params_json FROM dbo.etl_ds_job_log` do run com os dois itens.
d) `pNaoExiste`: a etapa falha **antes** do disparo com a lista do `-lparams`; `dsjob -jobinfo` confirma que o job não rodou.
e) Encrypted: log com `pSenha=***`; nenhuma ocorrência do valor no log; `ORQUESTRA_CONN_KEY` presente no container do worker.
f) Worker reiniciado depois do deploy de `dags/utils/`.
