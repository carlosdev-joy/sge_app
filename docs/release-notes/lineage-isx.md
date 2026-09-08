# 🧬 Lineage automático via ISX — o Orquestra exporta o job do DataStage por conta própria

**Compatibilidade:** Apache Airflow 2.x | SQL Server | IBM InfoSphere Information Server 11.7 (DataStage) com `istool` no servidor do engine e a API REST do DataStage (`/ibm/iis/ds/api`) | acesso SSH ao servidor do DataStage (o mesmo do Console e dos Utilitários)
**Migration:** **106** (`106_lineage_isx.sql`, deploy.sh etapa 6c — responder **s**)
**Spec:** `docs/spec-lineage-isx.md` (F1–F5; F1 = #369, F2 = #370, F3 = #371, F4 = #373, F5 = PR de fecho)
**Manual:** `docs/MANUAL_USUARIO.md` §1.4 (o que é), §3.9 (extrair, grafo, painel, mensagens), §4.8 (configuração e lote), §5 (FAQ)
**Depende de:** as variáveis `DS_SSH_*` do Console DataStage (já em uso) e de um **arquivo de credencial do istool no servidor do DataStage** (`-authfile`) — ver Deploy

---

## 📋 Resumo

O lineage dos jobs DataStage vinha de um `.dsx` exportado à mão e copiado para
`dsx/`: meses defasado do job em produção e pobre (só nomes de tabela, colunas
raras, nenhuma transformação). Agora o Orquestra **exporta o job sozinho** com o
`istool` do Information Server (formato ISX) via SSH, lê a definição do job e
grava por stage o **SQL completo**, o DSN, o caminho do arquivo, as **colunas com
tipo e tamanho**, as **expressões coluna a coluna**, o **código APT** do
Transformer e o **fluxo** entre stages. Só reextrai quando o job mudou no
DataStage. Regra do usuário: **só para job que já está num pipeline do
Orquestra**. A Governança ganha a aba **Job DataStage** com grafo e painel por
stage; o admin extrai um pipeline inteiro em lote pela DAG
`etl_lineage_extract_isx`. O banco fica pronto para uma IA consultar — a IA em si
é spec própria (backlog).

```
Governança › Job DataStage
┌───────────────────────────────────────────────────────────────────────────┐
│ Pipeline [PIPE_VIDA        ▾] [Carregar]   Projeto BI_VIDA · 3 job(s)     │
│                                            · 2 com lineage ISX  [Extrair todos (lote)] │
│ ┌ jobs ─────────────────┐ ┌ SsdVidaDimePessoa02Ftp  PARALLEL  extraído agora ┐ │
│ │ SsdVida… ● extraído   │ │ Projeto BI_VIDA · Pasta \Jobs\… · Modificado … │ │
│ │          [Atualizar]  │ │                                                 │ │
│ │ SeqSsd…  ● extraído   │ │  (DM_119_INFO)──LnkOrig──▶(TrfNlist)──▶(DST_FTP) │ │
│ │          [Atualizar]  │ │   origem            transformação    destino    │ │
│ │ JobRaiz  ● erro       │ │                                                 │ │
│ │  não encontrado…      │ │ stage      direção  tipo        resumo   colunas│ │
│ │          [Extrair]    │ │ DM_119_INFO origem  PxOdbc      select … 1      │ │
│ └───────────────────────┘ └─────────────────────────────────────────────────┘ │
│   painel do stage ▸ SQL completo · banco/DSN · arquivo · colunas · expressões │
│                     saída ← expressão (origem) · APT (recolhido) · #PSet.X#  │
└───────────────────────────────────────────────────────────────────────────┘
```

> **Impacto para a engenharia ETL:** o lineage de um job passa a ser o do
> DataStage de agora, com o SQL que o job roda de verdade — um clique, sem
> `.dsx`, sem WinSCP, sem cadastro à mão. O que foi cadastrado à mão ou pelo DSX
> continua no banco; a aba Lineage prefere o ISX quando ele existe.
>
> **Impacto para a operação:** nada muda nos jobs. A extração é uma JVM do
> `istool` por chamada (3–5 s) no servidor do DataStage; o lote é só do admin,
> por pipeline, com 4 extrações simultâneas e cache pelo `lastModified`.
>
> **Impacto para a segurança:** a credencial do `istool` fica num arquivo do
> servidor do DataStage (`-authfile`, permissão 600), **nunca** na linha de
> comando; a da API REST vem do `.env` da API; a DAG chama a API com um usuário
> de serviço do Orquestra que vem pelo ambiente do worker (não pelo banco do
> Airflow). `GET /lineage`, que era aberto, **passa a exigir o token** da sessão.
> Nenhuma permissão nova: extrair pede `acao_editar`; lote pede admin.

---

## 🚚 O que entra

| Fase | Entrega |
|---|---|
| **F1** | Migration **106**: `dbo.etl_ds_job_isx` (cabeçalho por job — pasta, tipo, `lastModified` que serve de chave de cache, descrição, parâmetros, fluxo, filhos da sequence, hash do `.isx`, status/erro), colunas novas em `etl_job_lineage` (colunas de entrada, APT, expressões, id do stage) com `extraction_method = 'isx_auto'`, tipos PX/sequence que faltavam em `etl_stage_type_map` (MERGE, não sobrescreve o que o admin editou). Engine `dags/utils/isx_engine.py`: localizar o job na árvore de pastas pela API REST, montar o `istool export` (`-authfile`, pasta temporária privada, `umask 077`), abrir o ZIP e **parser puro** do XML (stages com direção, SQL, DSN, arquivo, colunas, expressões, APT, fluxo, filhos; DOCTYPE/ENTITY recusados, teto de tamanho, parâmetros `Encrypted` mascarados). Harness de DEV (istool de mentira + API REST de amostra) |
| **F2** | Endpoints: `GET /lineage/isx/localizar`, `POST /lineage/isx/extrair` (`acao_editar`; cache pelo `lastModified` × API REST; `force`; executor dedicado, 60 s → 504; `sp_getapplock` por job → 409; grava cabeçalho + linhas numa transação apagando só as `isx_auto` do job), `GET /lineage/isx/job`, `GET /lineage/isx/pipeline` (estado ISX de cada job). **`GET /lineage` passa a exigir autenticação** e a preferir `isx_auto` quando existe |
| **F3** | DAG `etl_lineage_extract_isx` (a DAG orquestra, a API extrai): lista os jobs `datastage` dos pipelines com projeto (um pipeline ou todos; `CopyOf*` e pipelines inativos de fora por padrão), chama a API com 4 threads e timeout por job; erro individual não aborta; resumo `{total, extraidos, cache, erros[]}` no XCom. `POST /lineage/isx/lote` (admin; despausa a DAG antes de disparar) e `GET /lineage/isx/lote/{run_id}`; o disparo genérico de DAG da API passa a exigir admin para esta DAG |
| **F4** | Aba **Job DataStage** em Catálogo & Lineage: seletor de pipeline, lista de jobs com o estado ISX, **Extrair / Atualizar** (só com `acao_editar`), cabeçalho (cache × extraído agora, tipos fora do mapa, erro da última tentativa sem esconder o lineage bom), grafo `@xyflow/react` colorido por direção, tabela de stages, painel lateral (SQL, banco, arquivo, colunas, expressões, APT recolhido, `#PSet.X#` em badge), sequence com os filhos (link + Extrair só para quem está no pipeline), **Extrair todos (lote)** para admin com acompanhamento a cada 5 s. Tema claro e escuro |
| **F5** | Manual (§1.4, §3.9, §4.8, FAQ), esta release note, `scripts/smoke_lineage_isx.sh` fechado (c–i e k pela API, roteiro impresso para a, b, j, l, m), `sql/backlog/lineage_isx.sql` (12 itens em `etl_backlog`, idempotente), spec concluída |

## ⚙️ Como funciona

1. **Localizar**: com o projeto do pipeline (`etl_pipeline.project_name`), a API
   REST do DataStage responde a pasta, o tipo (PARALLEL/SEQUENCE) e o
   `lastModified` do job. A pasta fica gravada no cabeçalho — a busca em largura
   na árvore só acontece na primeira vez.
2. **Cache**: se o `lastModified` é o mesmo do cabeçalho e não veio `force`, a
   resposta é o que está no banco (`cache_hit: true`, < 1 s).
3. **Exportar**: por SSH, `istool export … -authfile <arquivo no servidor>
   -archive <pasta privada>/orq_<job>_<uuid>.isx -datastage '<engine>/<projeto>/Jobs/…/<job>.pjb'`
   (sequence: `.qjb`, depois `.sjb`); o `.isx` desce por SFTP e é apagado no
   servidor. Teto de 60 s no canal e de 20 MB no arquivo.
4. **Ler e gravar**: o parser lê o `DSJobDefSDO` do ZIP e a API grava, numa
   transação com trava por job, o cabeçalho em `etl_ds_job_isx` e uma linha por
   stage em `etl_job_lineage` com `extraction_method = 'isx_auto'` (as linhas
   `manual` e `dsx_auto` do job ficam). Falha vira `status = 'erro'` com a frase
   no cabeçalho — o lineage anterior continua visível.
5. **Lote**: a DAG lê os jobs dos pipelines no SQL Server e chama
   `POST /lineage/isx/extrair` por job com a Connection `orquestra_api`
   (usuário de serviço com `acao_editar`); a run termina **verde mesmo com erros
   individuais** (ficam em `erros[]`, a tela mostra "ver erros" — inclusive quando o
   istool/SSH falha em todos) e só falha quando nenhum job chega à API (API fora,
   credencial de serviço recusada, ISX não configurado) ou quando o filtro não acha
   job DataStage (pipeline inativo, só `CopyOf*`, só nós que não são DataStage).

## 🔒 Como a segurança funciona

- **Nenhuma credencial no repo nem na linha de comando**: `istool` sempre com
  `-authfile` (a senha nunca aparece no `ps` nem no log); API REST com
  `DS_API_USER`/`DS_API_PASSWORD` do `.env` (uma `DS_API_URL` com
  `usuario:senha@` é recusada com 503); SSH com as `DS_SSH_*` do Console.
  Testes anti-drift proíbem literal de senha e host real no engine, na API, no
  smoke e nos documentos.
- **Nomes viram linha de shell**: projeto, pasta e job passam por lista branca e
  `shlex.quote`, e vêm do banco (pipeline) e da API REST do DataStage, nunca de
  texto livre; `;`, `$(`, `..` → 422 antes do SSH. Caminhos da API REST são
  validados pelo engine (só `folders/…` e `jobdesigns/…`).
- **O `.isx` traz credenciais de conexão do job**: nasce numa pasta privada do
  usuário SSH (`DS_ISTOOL_TMP`, padrão `~/.orquestra/tmp`, `umask 077`), não em
  `/tmp`; é apagado no servidor depois da leitura; parâmetros `Encrypted` (e
  nomes como senha/password) são mascarados antes de gravar. Defina
  `DS_SSH_KNOWN_HOSTS`: sem ele o SSH aceita qualquer host key (a API avisa no
  arranque).
- **XML hostil**: DOCTYPE/ENTITY em qualquer codificação recusados, teto no
  `.isx` e no membro descomprimido (bomba ZIP), raiz obrigatória `DSJobDefSDO`.
- **RBAC**: consultar = ter a tela Governança; extrair = `acao_editar`; lote =
  admin (também pelo proxy genérico de DAGs da API). `GET /lineage` exige token.
- **A DAG não guarda segredo no banco do Airflow**: `AIRFLOW_CONN_ORQUESTRA_API`
  vem pelo ambiente do worker (um role Op do Airflow não a vê nem edita; não
  depende de Fernet); a sessão da DAG e o cliente REST da API ignoram o proxy
  corporativo (`trust_env=False`) — o Basic nunca sai para o proxy.
- **Limitação conhecida**: `sql_expression`, `apt_code` e `BeforeSQL` podem
  carregar literais do design do job e são lidos por qualquer usuário
  autenticado com a tela (backlog: restringir ou mascarar).

## 🚀 Deploy

Ordem sugerida — os passos 2 e 3 são **antes** de liberar a tela, senão a
extração responde 503 "não configurado" (nada quebra, mas ninguém extrai).

1. **Migration 106** (etapa 6c, responder **s**). Idempotente; cria
   `etl_ds_job_isx`, as colunas novas de `etl_job_lineage` e completa
   `etl_stage_type_map`. Antes, conferir a grafia do mapa em produção — a tabela
   existe com duas chaves possíveis no repo (spec §8.10):
   ```sql
   SELECT COL_LENGTH('dbo.etl_stage_type_map','type_raw') AS type_raw,
          COL_LENGTH('dbo.etl_stage_type_map','stage_type') AS stage_type;
   ```
   A migration e o engine descobrem a coluna sozinhos; o resultado decide se vale
   unificar (item do backlog).
2. **`.env` da API** (bloco "Lineage ISX" — modelo em `.env.dev.example`):
   `DS_ENGINE` (FQDN do engine, como o istool exige no `-datastage`),
   `DS_API_URL` (`https://<host>:<porta>/ibm/iis/ds/api`), `DS_API_USER`,
   `DS_API_PASSWORD`, `DS_API_VERIFY_SSL` (`true`, caminho da CA interna ou `false`
   com aviso a cada arranque), `DS_ISTOOL_HOME` (padrão `/opt/IBM/InformationServer`),
   `DS_ISTOOL_LAUNCHER` (JAR do launcher, relativo ao home — o padrão é o da 11.7),
   `DS_ISTOOL_DOMAIN` (`host:porta` dos serviços), `DS_ISTOOL_AUTHFILE` (caminho **no
   servidor do DataStage**), `DS_ISTOOL_TMP` e `DS_ISTOOL_CFG` (pastas privadas do
   usuário SSH; padrão `~/.orquestra/…`), `DS_SSH_KNOWN_HOSTS`. Depois `docker compose
   up -d --no-deps orquestra-api` (a imagem muda de qualquer forma: `api/` mudou).
   **No servidor do DataStage**, criar o `-authfile` do istool na pasta do usuário
   SSH do Orquestra: duas linhas `user=<usuário do istool>` e `password=<senha>`
   (grafia chave=valor; `-user`/`-password` em linhas o istool 11.7 recusa com
   *user name not found*), permissão **600**, e o **caminho absoluto** em
   `DS_ISTOOL_AUTHFILE` (a API não expande `~`). Sem a variável, a extração responde
   503 "Lineage ISX não configurado nesta instância da API — defina DS_ISTOOL_AUTHFILE";
   com a variável apontando para um arquivo que não existe no servidor, o istool falha
   (502, motivo no log da API) — **não há** fallback para senha na linha de comando.
3. **`.env` do Airflow**: `AIRFLOW_CONN_ORQUESTRA_API=http://<usuario>:<senha>@orquestra-api:8000/http`
   com um usuário de serviço do Orquestra que tenha `acao_editar` (o compose
   repassa; vazio = a DAG procura a Connection no banco do Airflow). Recriar
   worker e scheduler (`up -d airflow-worker airflow-scheduler`) — variável de
   ambiente só entra recriando.
4. **`dags/`** (etapa 5, responder **s**): a DAG `etl_lineage_extract_isx.py` na raiz
   recarrega sozinha; `dags/utils/isx_engine.py` é módulo em subpasta → o
   `deploy.sh` pergunta pelo **restart do `airflow-worker`** (5b) — responder **s**
   numa janela sem jobs, senão o worker fica com o módulo antigo em cache. A DAG
   nasce pausada; o `POST /lineage/isx/lote` despausa antes do primeiro disparo.
5. `ui-react/dist` (automático) e `api/`. **Sem relogin** (nenhuma permissão
   nova). `config/` do nginx: responder **n** (nada muda ali).
6. **Rede**: de dentro do container da API, `curl -k -u "$DS_API_USER:$DS_API_PASSWORD"
   "$DS_API_URL/engines"` → 200 (chamada direta, sem proxy — se a rede exigir proxy
   para esse host é decisão a tomar); de dentro do worker,
   `python3 -c "import requests; print(requests.get('http://orquestra-api:8000/health', timeout=5).status_code)"`
   → 200 (`NO_PROXY`, gotcha conhecido: sonda passa e DAG morre).
7. **Consumidores de `GET /lineage`**: o endpoint exige token agora. Nenhum
   script externo (n8n, relatório) pode lê-lo sem autenticação — conferir antes de
   liberar.
8. **Smoke**: `scripts/smoke_lineage_isx.sh` (c–i com um desenvolvedor; k com um
   admin dispara o lote e espera a DAG) e o roteiro impresso para a, b, j, l e m.
   Durante o item d, no servidor do DataStage, `ps -ef | grep istool` mostra
   `-authfile`, nunca a senha. Backlog: `sql/backlog/lineage_isx.sql` (idempotente,
   pode rodar 2×).

## ⚠️ Limites conhecidos (backlog)

- **IA fora**: o banco está pronto (SQL, colunas, expressões, APT, fluxo), o
  assistente é spec própria.
- Os filhos de uma sequence **não** são extraídos em cadeia — cada um por demanda
  (link + Extrair) ou pelo lote.
- `#PSet.X#` fica como está (badge com explicação), sem resolver o valor.
- Só PARALLEL e SEQUENCE; **server jobs** respondem 422.
- Tipos de stage fora do mapa ficam em `nao_reconhecidos_json` e no aviso do
  cabeçalho; incluir no mapa é por SQL (`etl_stage_type_map`, manual §4.8) — sem
  tela.
- `file_path`, `stage_name` e `database_name` são `VARCHAR`: acento fora da
  collation vira `?` (o caso fica anotado).
- O lote só roda por disparo manual (botão ou `POST /lineage/isx/lote`); sem
  agendamento.
- Job renomeado ou apagado no DataStage mantém o cabeçalho com `status = 'erro'`
  até ser removido do pipeline (a FK apaga em cascata); sem expurgo automático.
- `DS_API_VERIFY_SSL=false` funciona, mas avisa a cada arranque — o certo é a CA
  interna.
- O extrator DSX e o preview "Comparar XML × Atual" continuam existindo; a
  consulta prefere ISX.
