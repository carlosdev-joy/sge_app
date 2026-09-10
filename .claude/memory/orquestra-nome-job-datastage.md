---
name: orquestra-nome-job-datastage
description: "⚠️ INCIDENTE + FIX (PR #269): DataStage é case-SENSITIVE em nome de job, SQL Server é case-INSENSITIVE — a divergência quebrou pipeline em produção E impedia o conserto; agora tem rename de caixa, conferência com sugestão no cadastro e erro que nomeia a causa"
metadata: 
  node_type: memory
  type: project
  originSessionId: f83b731c-0876-4438-b369-1dd4f50c0621
  modified: 2026-08-04T01:49:46.239Z
---

Incidente real em 2026-08-03 no [[orquestra-sge-app]]: task de produção
falhou com `(DSOpenJob) Cannot find job SsdVidaCobranca01BaixaProcessamento
Cobranca / Status code = -1004`. O job existe — chama-se **`SSDVida…`**.

⚖️ **A REGRA QUE EXPLICA TUDO: o DataStage é case-SENSITIVE em nome de job;
o SQL Server (colação `SQL_Latin1_General_CP1_CI_AS`) é case-INSENSITIVE.**
Essa divergência (a) criou o erro, (b) escondeu a causa no log e (c)
**impedia o conserto pela tela**.

**Como diagnosticar erro de task DataStage** (o traceback longo engana):
- traceback que termina em `raise AirflowException` no `datastage_operator.py`
  = exceção DELIBERADA do operator, **não é bug de Python**;
- `rc=255` + texto do `dsjob` = resposta do **DataStage**;
- `(DSOpenJob) Cannot find job` = o **projeto abriu** e o job não está nele
  (se o projeto não abrisse, a mensagem seria sobre o projeto);
- 2 conexões SSH antes do erro = `_jobinfo()` (que já recebeu o mesmo erro e
  era ignorado) + `_trigger_run()`.
- Conferir no servidor: `dsjob -ljobs <PROJETO> | grep -i <nome>` e
  `for p in $(dsjob -lprojects); do dsjob -ljobs $p | grep -i <nome>; done`.
- O factory manda `project=PROJECT_NAME` (o projeto do PIPELINE no Orquestra)
  e `job_name` = **o nome da etapa, sem tradução** (`task_id` == `job_name`).

✅ **CORRIGIDO NA PR #269 (main 7dfd907, 2026-08-03)** — três frentes:
1. **Rename de caixa** (`api/routers/jobs.py`): eram DOIS bloqueios
   independentes — a guarda de unicidade perguntava ao banco (CI) e achava a
   PRÓPRIA linha (422 "já existe"), e a guarda "igual ao atual" era avaliada
   ANTES de canonizar a grafia (`SSD→SSD` = "igual ao atual"). Agora compara
   em Python e usa **UPDATE in-place** (a estratégia de cópia estouraria a PK
   sob CI). Bônus achado junto: `_rename_in_dep_csv`/`_rename_in_condition`
   eram case-sensitive → referência com grafia divergente **sobrevivia ao
   rename apontando para job inexistente**.
   ⚠️ **WORKAROUND histórico (antes da #269)**: renomear em 2 passos por um
   nome intermediário.
2. **Conferência no cadastro** (`GET /datastage/jobs` + front nos 2 lugares de
   cadastro): autocompletar sobre os nomes reais + 4 estados (caixa divergente
   com correção em 1 clique e salvar em alerta / inexistente com parecidos
   clicáveis / exato com visto / indisponível com aviso neutro).
   **Indisponibilidade NUNCA bloqueia o cadastro** (200 com motivo).
3. **Erro que diz a verdade** (`dags/utils/datastage_operator.py`): falha já no
   `_jobinfo()` (onde o operator JÁ sabia), nomeando o projeto, avisando do
   case-sensitive e listando parecidos (busca só no caminho de erro).
   **Importado em RUNTIME ⇒ vale sem regerar DAGs.**

⚠️ **Defeito que só a PROVA VISUAL achou** (3ª vez seguida nesta base): os
"nomes parecidos" nunca apareciam quando o erro está no MEIO do nome
(`SSDVidaCobranca09X` × `SSDVidaCobranca01Y` não é prefixo nem substring um do
outro) → a faixa saía SEM sugestão, justo o que ela existe para dar. Passou a
ranquear por **maior prefixo comum**, no front e no operator.

🔴 **2º INCIDENTE (mesmo dia, natureza DIFERENTE) — PR #271 (main 2ff21eb)**:
```
[DS] trigger rc=255 | Error running job
Status code = -99 DSJE_REPERROR      (job SsdVidaDimePessoa02Ftp, pipeline TESTE_DS)
```
**O job EXISTE e foi aberto** — não é `Cannot find job`. `DSJE_REPERROR` (−99) é
o **balde genérico** de erro de repositório do DataStage: não diz o motivo.
Hipóteses vivas (nenhuma tem marcador textual, por isso são hipóteses):
**job não compilado**, **`-param` que o job não declara**, **`-queue`
inexistente**, job travado/permissão. ⚠️ O factory gera `queue_name=DS_QUEUE`
mas **NÃO** passa `execution_date_param` — em pipeline gerado hoje as
hipóteses vivas são **fila** e **compilação**.
Diagnóstico no servidor: `dsjob -logsum <PROJ> <JOB>` (o motivo real),
`-jobinfo` (compilado/runnable), `-lparams` (parâmetros que o job aceita).
✅ Fix: o operator **buscava o log do job só quando o job ABORTAVA**, nunca
quando o disparo era RECUSADO — agora anexa o `-logsum` ao erro de disparo
(best-effort: falha do diagnóstico NUNCA substitui o erro real), **registra o
comando executado** (revela `-queue`/`-param`; sem credencial — auth é do SSH),
cria categoria própria p/ o −99 (afirma só o que o marcador garante + hipóteses
com os valores que só o Orquestra conhece) e cobre os 2 caminhos que mandavam
"consulte os logs" sem trazer log. Bônus achado na leitura: o ramo ABORTED
buscava o log **desprotegido** — queda de SSH no diagnóstico trocaria "job
abortou" por erro de rede.

📌 **Limite declarado**: o dev **não tem DataStage**. A prova visual usou
DUBLÊ da lista de jobs; o caminho feliz (lista real, veredito contra jobs de
verdade) **só será verificável em produção**.

📌 **Fio solto registrado (não é da #269)**: `GET /pipelines/jobs/{pipeline}/
{job}` devolve **500** no dev — `Invalid column name 'active'` em
`api/routers/jobs.py:2044`; `etl_pipeline_job` do dev não tem a coluna
(divergência de schema do ambiente, família das pendências de
`docs/ambiente-dev.md`). Efeito: "Editar Etapa" não carrega deps/params.
