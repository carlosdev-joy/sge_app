# Spec: Lineage ISX — jobs fora de `Jobs/` (busca pela raiz do projeto e pasta informada) — Orquestra
Data: 2026-09-08 · Status: rascunho (aguarda aprovação do usuário)

Consolida, no formato da casa, o documento "Lineage ISX — BFS com Raiz Alternativa e
Pasta Pré-configurada" (Equipe BI CVP, 2026-09-08), levantado no primeiro uso em
produção da spec `docs/spec-lineage-isx.md` (F1–F5 = PRs #369, #370, #371, #373, #374;
#375). O documento foi **validado contra o código** antes desta spec — ver §8, onde
estão as diferenças que ele não viu (a maior: a pasta é obrigada a começar por `Jobs`
em três lugares, não só na busca).

## 1. Visão

No projeto BI_CVP os jobs não moram só em `Jobs/`: a raiz do projeto tem mais de uma
dezena de pastas irmãs de `Jobs/` (`BU02 - …`, `UIC_…`, …) e o primeiro job pedido em
produção estava numa delas. A busca em largura do engine começa **fixa em `Jobs/`** e
nunca sai de lá, então a extração responde "não encontrado". Quando esta spec estiver
pronta, a busca parte da **raiz do projeto** (com `Jobs/` na frente da fila, para o caso
comum continuar rápido), o usuário pode **informar a pasta** na tela para pular a busca,
a pasta achada fica gravada **mesmo quando o export falha**, e os tetos de tempo da
extração acomodam um projeto com muitas raízes.

## 2. Escopo

**IN:**
- `validar_pasta` deixa de exigir `Jobs` como primeiro componente (vale para a busca, o
  path rápido pela pasta conhecida e o caminho `-datastage` do istool). Lista branca de
  caracteres e `..` continuam; teto de 500 caracteres (largura de `ds_folder_path`).
- `localizar_job` começa na raiz do projeto (`folders/<engine>\<projeto>/contents`):
  enfileira `Jobs` primeiro e depois as outras pastas de primeiro nível na ordem da API;
  jobs soltos na raiz também contam. Raiz vazia ou não listável → fila só com `Jobs/`
  (comportamento de hoje). Parâmetro `pasta_inicial` restringe a busca a uma subárvore.
- **Pasta informada** (`ds_folder_path` no corpo de `POST /lineage/isx/extrair` e na
  query de `GET /lineage/isx/localizar`): validada por `validar_pasta`; confere direto o
  `jobdesigns/…`; se a API não acha ali, busca em largura **só na subárvore do primeiro
  componente** da pasta informada; não achou → 404 dizendo onde procurou e sugerindo
  deixar a pasta em branco para varrer o projeto inteiro.
- Persistência da pasta: a pasta que a busca achou entra no cabeçalho também quando o
  export falha (já acontece pelo `e.meta` para `ISXError`; passa a valer para o 504 do
  executor, que hoje perde o `meta`). Assim a segunda tentativa nunca repete a busca.
- Tetos encadeados: `LOCALIZAR_MAX_S` 30 → 60 s; `/localizar` 35 → 65 s; `/extrair`
  ganha teto **por situação** — 65 s com pasta conhecida/informada (como hoje), 125 s
  quando precisa buscar (busca 60 + export 60 + margem); DAG `TIMEOUT_JOB_S` 90 → 150 s;
  frases do front e do 504 sem o "60 s" fixo.
- Tela (aba Job DataStage): campo opcional **Pasta no DataStage** no painel do job
  selecionado, visível só enquanto o cabeçalho não tem `ds_folder_path`; some quando a
  pasta fica gravada. `\` ou `/` como separador; espaços e acentos aceitos.
- Harness de DEV: a API REST de amostra ganha a listagem da raiz do projeto `BI_VIDA`
  (`Jobs` + uma pasta irmã com espaço e hífen no nome) e um job PARALLEL fora de
  `Jobs/`, com `.isx` sintético e mapeado no `PIPE_VIDA`; smoke cobre o caso.
- Manual §3.9/§4.8, release note (seção de correções) e spec original §8 atualizados.

**OUT (explícito):**
- Cache da árvore de pastas entre chamadas (memória ou tabela): a pasta gravada por job
  já elimina a repetição; um cache global fica para quando houver medição de produção.
- Status novo no cabeçalho (`localizado`/`pendente`): o modelo continua `ok` | `erro`.
  O "workaround por SQL" do documento (§6) **não funciona hoje** — ver §8.3.
- Busca paralela (várias pastas ao mesmo tempo) na API REST do DataStage.
- Editar a pasta de um job já extraído pela tela (a pasta conhecida é conferida e, se o
  job saiu de lá, a busca refaz sozinha — comportamento de hoje).
- Tela para o mapa de tipos, filhos em cadeia e o resto do backlog da spec original.

## 3. Arquitetura proposta

### Engine (`dags/utils/isx_engine.py`)
- `validar_pasta(folder_path, *, max_len=500)`: sem a checagem `partes[0] != "Jobs"`;
  recusa string acima de `max_len` (422). Docstrings de `caminhos_istool`/`validar_pasta`
  deixam de prometer `Jobs`.
- `caminho_raiz(engine, projeto)` → `folders/<eng>%5C<proj>/contents`.
- `localizar_job(rest, engine, projeto, job, *, pasta_inicial=None, max_nos, teto_s,
  relogio)`:
  - sem `pasta_inicial`: `rest(caminho_raiz)`; filhos `jobdesigns/` da raiz são conferidos
    na hora; filhos `folders/` viram a fila com `Jobs` **primeiro** (se existir) e os
    demais na ordem da API; raiz sem resposta ou sem pastas → fila `[Jobs]`;
  - com `pasta_inicial` (lista de componentes já validada): fila
    `[caminho_pastas(eng, proj, partes)]`;
  - o laço continua igual (tetos de nós e tempo, `_caminho_api_valido` em `$ref`/`id`).
- Constantes: `LOCALIZAR_MAX_S = 60.0`.

### Serviço (`api/services/lineage_isx.py`)
- `localizar(cfg, projeto, job, pasta_conhecida, pasta_informada=None)`:
  1. `pasta_conhecida` (cabeçalho) → `api_id_de` + `checar_modificado`; 404/422 → segue;
  2. `pasta_informada` → mesmo path rápido; 404/422 → `localizar_job(pasta_inicial=
     [primeiro componente])`; não achou → `ISXError(404, "Job X não encontrado abaixo de
     \\<pasta>… — deixe a pasta em branco para varrer o projeto inteiro.")`;
  3. sem nada → `localizar_job()` pela raiz; não achou → 404 (frase atual, sem "de Jobs").
- `extrair(...)` recebe `pasta_informada` e repassa; `resultado="nao_encontrado"` mantido.
- `precisa_buscar(cab, pasta_informada) -> bool` (puro): sem `ds_folder_path` no
  cabeçalho e sem pasta informada → o router escolhe o teto maior.

### Router (`api/routers/lineage_isx.py`)
- `POST /lineage/isx/extrair`: lê `ds_folder_path` do corpo (string; vazio = ausente),
  valida com `E.validar_pasta` → 422 com a frase do engine; passa ao serviço; teto
  `_TETO_EXTRAIR_S` (65) ou `_TETO_EXTRAIR_BUSCA_S` (125) conforme `precisa_buscar`.
- `GET /lineage/isx/localizar`: query `ds_folder_path` opcional, mesma validação; teto 65.
- 504 do executor: a busca roda em etapa própria antes do export (duas chamadas ao
  executor: `localizar` e depois `exportar+parse`), e o `meta` da primeira é persistido
  pelo `_registrar_erro` quando a segunda estoura — é o que fecha o "ovo e galinha" sem
  campo novo no banco.
- Mensagem do 504: "A extração não terminou em {teto:g} s" (o teto que valeu).

### DAG (`dags/etl_lineage_extract_isx.py`)
- `TIMEOUT_JOB_S = 150` (a API pode levar 125 s no primeiro job de cada pasta nova).
  Sem outra mudança: a DAG chama a API, não o engine (não exige restart do worker por
  causa desta spec, mas a DAG na raiz de `dags/` recarrega sozinha).

### Front (`ui-react/src/components/governanca/isx/`)
- `PainelJobIsx`: estado `pastaInformada`; bloco `data-pasta-informada` no topo da coluna
  direita quando `jobAtual` é job DataStage e `!jobAtual.isx?.ds_folder_path`: rótulo
  "Pasta no DataStage (opcional)", input (`data-campo="pasta"`, placeholder genérico
  `Pasta\Subpasta` com a dica "use \ ou /; só se o job não estiver em Jobs"), botão
  **Extrair com esta pasta** (`data-acao="extrair-com-pasta"`, `acao_editar`). A mutation
  `extrair` ganha `pasta?: string` → `ds_folder_path` no corpo. O campo zera ao trocar de
  job/pipeline. Spinner: "até 1 min; até 2 min quando a pasta ainda não é conhecida".
- `lib/lineageIsx.ts`: `POR_STATUS[504]` sem "(60 s)"; `EstadoJobIsx.ds_folder_path` já
  existe no contrato de `GET /lineage/isx/pipeline` (nada muda no back para a lista).
- `CabecalhoJobIsx`: a linha "Pasta" já mostra `ds_folder_path`.
- Bancada `tests/js/lineage_isx_harness.cjs`: o bloco aparece só sem pasta conhecida,
  envia `ds_folder_path`, some com pasta gravada.

### Harness de DEV
- `dev/ds-api-amostra/rotas.json`: rota `folders/AMOSTRA.DEV%5CBI_VIDA/contents` com
  `Jobs`, `BU02 - Base Amostra` (espaço e hífen, como as pastas reais) e um job solto
  `JobNaRaiz`; subárvore `BU02 - Base Amostra\Sub` com o job PARALLEL `JobForaDeJobs`
  (`jobdesigns/…` com `folderPath`). `.isx` sintético `JobForaDeJobs.isx` gerado do mesmo
  template dos testes (`tests/test_lineage_isx_engine.py::isx`) e subido para
  `/dados/bi/isx/` do `sshd-amostra` (o istool falso acha pelo nome do job, em qualquer
  pasta). `JobForaDeJobs` mapeado como 4º job do `PIPE_VIDA` (SQL idempotente em
  `docs/ambiente-dev.md`).
- `scripts/smoke_lineage_isx.sh`: item **n)** `JOB_FORA` (opcional): localizar sem pasta
  → `encontrado: true` com `folder_path` fora de `\Jobs`; extrair com `force` → 200;
  localizar com `ds_folder_path` errada → 404 com "abaixo de"; `ds_folder_path` com `..`
  → 422.

### Decisões e alternativas descartadas
- **`Jobs` primeiro na fila, não "raiz em ordem da API"**: a maioria dos jobs está em
  `Jobs/`; a busca continua custando o de hoje para eles e só paga as pastas irmãs quando
  precisa.
- **Sem status novo no cabeçalho**: persistir a pasta no cabeçalho de erro (que já
  existe) resolve a repetição da busca sem mexer no modelo, no front da lista nem no
  `GET /pipeline`.
- **Busca com pasta informada fica na subárvore**: previsível e limitada; o usuário que
  errou a pasta recebe uma frase dizendo onde se procurou e como varrer tudo.
- **Teto por situação em vez de subir tudo para 125 s**: uma extração com pasta
  conhecida continua respondendo em até 65 s; só a primeira busca de um job novo paga
  mais.
- **`ui/js/app.js` do documento não existe**: o front é a aba React
  (`components/governanca/isx/*`); o campo entra em `PainelJobIsx`.

## 4. Modelo de dados

Sem migration. `etl_ds_job_isx.ds_folder_path NVARCHAR(500)` já guarda pastas fora de
`Jobs` (a barra inicial `\` continua: `\BU02 - Base\Sub`). O corte por `_c` em 500
permanece; a validação do corpo recusa antes de chegar aqui.

## 5. Fases

### F1 — Engine, API, DAG, harness e smoke
- Entregável: extração de job fora de `Jobs/` funcionando pela API, com pasta informada
  ou pela busca na raiz, pasta persistida em falha, tetos coerentes.
- Inclui: `validar_pasta` sem `Jobs`; `caminho_raiz`; `localizar_job` pela raiz com
  `pasta_inicial`; `localizar`/`extrair` do serviço com `pasta_informada` e
  `precisa_buscar`; router com `ds_folder_path` (corpo e query), teto por situação e
  persistência do `meta` no 504; DAG `TIMEOUT_JOB_S = 150`; `rotas.json` + `.isx`
  sintético + SQL do 4º job em `docs/ambiente-dev.md`; smoke item n); testes:
  engine (`validar_pasta` aceita `BU02 - Base\Sub` e recusa `..`/501 caracteres;
  `caminhos_istool` fora de `Jobs` com espaço escapado; `localizar_job` raiz com `Jobs`
  primeiro, job solto na raiz, raiz 404 → fallback `Jobs`, `pasta_inicial`, tetos),
  API (corpo com pasta → sem chamada a `folders/…contents`; pasta inválida → 422; pasta
  errada → busca só na subárvore → 404 "abaixo de"; sem pasta → acha fora de `Jobs` e
  grava `ds_folder_path`; export falha depois da busca → cabeçalho `erro` **com** a
  pasta; 504 do executor no export → idem; teto 125 só quando precisa buscar), DAG
  (constante), docs (release note cita a correção).
- Critérios de aceite:
  - Dado `JobForaDeJobs` mapeado no `PIPE_VIDA` sem cabeçalho, `POST /extrair` sem pasta
    → 200 com `ds_folder_path = \BU02 - Base Amostra\Sub` e 5 stages; segunda chamada →
    `cache_hit: true` sem nenhuma chamada a `folders/`.
  - `POST /extrair` com `ds_folder_path: "BU02 - Base Amostra/Sub"` num job sem cabeçalho
    → 200 e nenhuma chamada a `folders/…/contents`.
  - `ds_folder_path: "Outra\Pasta"` → 404 com "abaixo de \Outra"; `"../x"` → 422.
  - Job em `Jobs/` (os dois de hoje) continua com a mesma sequência de chamadas
    (raiz → `Jobs` → …) e o smoke c–i + k segue verde.
- Validação: pytest (engine 48+, API 50+, DAG, docs) + `bash -n` + smoke no DEV.
- Revisão adversarial (`qa-adversarial` + `auditor-seguranca`: a pasta informada chega
  ao shell do istool e à URL da API REST) antes da PR. PR: `fix(lineage): busca pela
  raiz do projeto e pasta informada para jobs fora de Jobs/ (F1)`.

### F2 — Tela, textos e documentação
- Entregável: campo **Pasta no DataStage** na aba, spinner e 504 sem "60 s" fixo, manual
  e release note.
- Inclui: `PainelJobIsx` (bloco, estado, mutation com `pasta`), `lineageIsx.ts`
  (`POR_STATUS[504]`), bancada + `tests/test_lineage_isx_front.py` (bloco só sem pasta;
  envia `ds_folder_path`; some com pasta; `type="button"`; pares claro/escuro), manual
  §3.9 (passo "se o job não está em Jobs") e §4.8 (tetos), release note (seção
  "Correções" com #375 e esta), spec original §8 (item novo), `dist/` rebuildada, prova
  com Chromium headless no DEV (claro e escuro).
- Critérios de aceite: com `JobForaDeJobs` sem cabeçalho, o bloco aparece; preencher
  `BU02 - Base Amostra\Sub` e clicar **Extrair com esta pasta** → cabeçalho com a pasta e
  o bloco some; com `SsdVidaDimePessoa02Ftp` (pasta conhecida) o bloco não aparece.
- Validação: `tsc -b` 0 + eslint (baseline) + `npm run build` + pytest.
- Revisão adversarial antes da PR. PR: `feat(lineage): campo Pasta no DataStage na aba
  Job DataStage e textos dos tetos (F2)`.

## 6. Riscos e mitigações

| # | Risco | Impacto | Mitigação |
|---|-------|---------|-----------|
| 1 | A listagem da raiz (`folders/<eng>\<proj>/contents`) na API real tem outra forma ou responde 404 | Busca cai no fallback `Jobs/` e o job fora de `Jobs` continua "não encontrado" | Fallback explícito + log com o status da raiz; o campo de pasta cobre enquanto se ajusta; item do smoke pede o `curl` da raiz em produção |
| 2 | Busca pela raiz em projeto grande passa dos 60 s | 504 na primeira extração de um job de pasta nova | `Jobs` primeiro na fila; pasta informada pula a busca; pasta achada persiste mesmo em 504 do export; teto de nós 5.000 |
| 3 | Pasta informada vai ao shell (`-datastage`) e à URL da API | Injeção | Mesma lista branca de `validar_pasta` (sem `..`, `;`, `$`, aspas), `shlex.quote` + espaço escapado (já existentes), `_quote_ds` percent-encoded; teste com `../x`, `a;b`, `$(id)`, 501 caracteres |
| 4 | `TIMEOUT_JOB_S` maior segura o lote por mais tempo num job travado | Lote mais lento | Só o primeiro job de pasta nova paga; 4 threads; o resumo mostra os 504 |
| 5 | Pasta gravada errada (o job foi movido no DataStage) | Path rápido responde 404 | Já cai na busca (comportamento de hoje, teste `pasta_conhecida_desatualizada`) |

## 7. Smoke pós-deploy

> `scripts/smoke_lineage_isx.sh` cobre c–i, k e **n** (com `JOB_FORA`, um job fora de
> `Jobs/` mapeado num pipeline). a, b, j, l, m continuam manuais.

a) `curl -k -u … "$DS_API_URL/folders/<engine>%5C<projeto>/contents"` de dentro do
   container da API responde 200 com `children` (a raiz lista `Jobs` e as irmãs).
b) `POST /lineage/isx/extrair` do job que motivou a spec, sem pasta → 200 em até ~2 min
   com `ds_folder_path` fora de `\Jobs`; log da API mostra a busca (quantas pastas, tempo).
c) Mesmo job de novo → `cache_hit: true` em < 1 s.
d) Job de `Jobs/` já extraído → nada muda (cache); um novo em `Jobs/` → busca passa pela
   raiz e acha em tempo parecido com o de antes.
e) Tela: job sem cabeçalho mostra **Pasta no DataStage**; informar a pasta e extrair → 200
   e o bloco some; pasta errada → frase "abaixo de …".
f) Lote de um pipeline com jobs fora de `Jobs/` → run verde, `erros[]` sem 404 de pasta.

## 8. Pendências e decisões em aberto

1. **Diferença do documento (não vista lá)**: `validar_pasta` obriga `Jobs` como primeiro
   componente e é usada pelo path rápido (`api_id_de`), pelo istool (`caminhos_istool`)
   e pela pasta conhecida. Só mudar o BFS deixaria a extração em 422 "Pasta do job
   precisa começar por 'Jobs'" logo depois de achar o job.
2. **Tetos encadeados** (não vistos): subir `LOCALIZAR_MAX_S` sem mexer em
   `_TETO_LOCALIZAR_S` (35) e `_TETO_EXTRAIR_S` (60) faria o router responder 504 antes
   do engine, e a DAG (90 s) antes da API.
3. **O "workaround imediato" do documento (§6) não funciona hoje**: `UPDATE`/`INSERT` de
   `ds_folder_path` fora de `Jobs` cai no mesmo 422 do item 1 no path rápido; e o status
   `pendente` está fora do domínio `ok | erro` (a lista mostraria "erro"). Não há atalho
   por SQL — é código.
4. **`ui/js/app.js`** citado no documento não existe; o front é a aba React da F4.
5. **Forma da listagem da raiz na API real**: assumida igual à das pastas
   (`children[]` com `$ref`/`name`/`children: true`); confirmar com o `curl` do smoke a)
   antes de fechar a F1 — se diferir, ajustar `localizar_job` na própria F1.
6. **Job que motivou a spec**: depois do deploy da F1, extrair pela API (ou com a pasta
   informada pela tela na F2) e conferir o `ds_folder_path` gravado.
