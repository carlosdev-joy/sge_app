---
name: orquestra-spec-email-tabela-sql
description: "🏁 Spec CONCLUÍDA 2026-09-11 (F1–F6, PRs #398–#403): {tabela} leva o resultado do nó SQL para o corpo do e-mail, mais 3 correções (destinatários, timeout da prévia SQL, cabeçalho do modelo no Outlook); deploy em produção pendente"
metadata: 
  node_type: memory
  type: project
  modified: 2026-09-12T01:07:49.323Z
  originSessionId: 402b71ba-966f-4b04-993d-364218f8ad21
---

**Spec:** `docs/spec-email-tabela-sql-e-ajustes.md` (🏁 **CONCLUÍDA**). Continuação de [[orquestra-spec-email-modelos-navegacao]].
Nasceu de problemas que o usuário encontrou usando o nó de e-mail no DEV em 2026-09-11.

**Os 3 defeitos, todos diagnosticados no código (não são hipóteses):**

1. **⛔ O campo de destinatários do nó só aceita UM endereço digitado.**
   `PainelEmail.tsx:147-151` guarda o ARRAY e reescreve o texto a cada tecla
   (`cfg.destinatarios.join('\n')`), enquanto o `onChange` faz o split e descarta o
   separador vazio com `.filter(Boolean)` — o Enter e a vírgula morrem no instante em
   que são digitados, e o 2º endereço COLA no 1º (`ana@x.combruno@y.com`). Simulado:
   `["ana@cvp.com.brbruno@cvp.com.br"]`. **Colar os dois de uma vez funciona** (o split
   recebe o texto inteiro) — é o workaround enquanto não sai a correção. O campo do
   FLUXO (`PipelineFormModal.tsx:533`) faz certo: guarda texto cru, separa no salvar.

2. **Prévia de SQL cancelada aos 15 s.** Não é limite fixo: `sql_preview_timeout_s` em
   `etl_app_config` (`api/routers/jobs.py:1143-1150`, default 15, clamp 1..120) é
   editável sem deploy — mas **o campo está ESCONDIDO**: `FlowConfigSection`
   (`Admin.tsx:2906`) é renderizada dentro de `NotificacoesTab` (`Admin.tsx:3102`), no
   rodapé de **Acessos & Comunicação › Notificações**, junto dos canais do Teams. O
   usuário procurou e não achou. A F2 move para Sistema › Configurações (⚠️ mudança de
   tela = precisa de aval, [[regra-nao-mudar-ordem-da-tela]]). A spec sobe default→60 e teto→**280** (o nginx corta em 300 s no
   `location /orquestra/`, e a API precisa responder o erro ANTES disso).

3. **⛔ Cabeçalho do modelo institucional quebrado no Outlook** (imagem em
   `/dados/bi/orquestra_email.png` DENTRO do container `orquestra-dev-sshd-amostra`).
   Três causas somadas:
   - o corpo é enviado CRU (`email_mime.py:286`, `add_alternative`), **sem `<head>`** —
     logo sem `<o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch>`, e o
     motor do Word dimensiona o VML com o DPI do Windows (tela em 125% → forma menor
     que a célula = **faixa clara sobrando à direita**);
   - `<v:textbox>` sem `mso-fit-shape-to-text:true` e `v:rect` sem `height`
     (migration 112, linhas 87-89) → o Word **clipa** o conteúdo = texto "ORQUESTRA ·
     Gestão de Pipelines" cortado ao meio;
   - o **modo escuro do Outlook inverte `bgcolor`, mas não inverte preenchimento VML** —
     dois azuis diferentes no mesmo cabeçalho.
   Correção escolhida: cabeçalho SÓLIDO sem VML, logo em células (o Word ignora
   `width`/`height` em `<div>`), e embrulho do corpo em documento HTML completo.

**A melhoria (o pedido central): `{tabela}` no corpo do e-mail.** Hoje o nó SQL
publica só o ESCALAR (`row[0]`, `_resolve_e_roda_sql` no `etl_dag_factory.py:1439`) no
XCom default, que a Decisão `valor_sql` lê. A spec adiciona `xcom_push(key="tabela")`
**sem tocar no retorno** (trocá-lo quebraria toda Decisão já publicada), e o e-mail
ganha `{tabela}` (único nó SQL a montante) e `{tabela:NOME}`.

**Decisões do usuário (2026-09-11):** tabela **no corpo** (anexo CSV ficou OUT);
truncar com aviso (50 linhas × 15 colunas, leitura até 1.000); a migration 113 só
corrige o modelo **se ninguém o editou** (guarda por hash do corpo semeado).

**⚠️ Armadilhas que a spec carrega:**
- `PLACEHOLDER_RE` (`\{([a-z_]+)\}`) vive em **3 espelhos** — `api/services/email_mime.py:43`,
  `dags/utils/email_envio.py:37` e o TS da prévia. Não aceita `:` nem maiúsculas, então
  `{tabela:NOME_DO_NO}` exige mudar os três com teste anti-drift.
- **Não há escape de HTML em lugar nenhum** hoje (`interpolar` injeta cru) — aceitável
  para número e data, inaceitável para dado vindo de SELECT. `html.escape` por célula.
- `{linhas}` vazio deixa a célula EM BRANCO no e-mail (visível na captura do usuário):
  vira `—`.

**Fases:** F1 destinatários · F2 timeout · F3 cabeçalho + migration 113 · F4 nó SQL
publica a tabela · F5 `{tabela}` no corpo · F6 docs/smoke.

**Estado:** 🏁 **CONCLUÍDA 2026-09-11** — #398 `239ec2f` (spec), #399 `0179374` (F1),
#400 `6cfcb4b` (F2), #401 `fb1bdd4` (F3), #402 `b4bb5c6` (F4), #403 `b4d872c` (F5), F6 (docs).
⏳ **deploy em produção PENDENTE**: `docs/release-notes/email-tabela-sql.md` (113 na 6c,
`api/`, `dags/` **com restart do worker**, `dist/`, `config/` → n) + ⚠️ **republicar os
pipelines com nó SQL** que forem usar `{tabela}`.

**⚠️ O que a F5/F6 ensinaram:**
- **O `text/plain` de corpo HTML é gerado por regex e COLAVA as células**
  (`ProdutoQtdACIDO A3DIPIRONA1`): `html_para_texto` transforma fronteira de célula em
  `" | "` ANTES do strip.
- **Teste cruzado TS×Python prova PARIDADE, não correção** — "1 coluna não cabem" passou
  verde porque os dois lados erravam igual.
- **Aviso de tela dentro de ramo condicional mente**: o aviso de marcador vivia no ramo
  "Corpo livre" e o campo do anexo aparece SEMPRE — com modelo do catálogo (o padrão do
  nó novo) `relatorio_{tabela}.xlsx` passava calado.
- **Doc que manda usar o botão "enviar e-mail de teste" do Admin é falso verde**: ele
  manda corpo fixo em TEXTO PURO, sem modelo (`api/routers/email.py`). Errei isso duas
  vezes na mesma spec — a segunda ficou na §7 da própria spec depois de eu ter corrigido
  a release note.

**⚠️ O que a F3 ensinou (cabeçalho de e-mail no Outlook):**
- **O `text/plain` do e-mail é `re.sub(r"<[^>]+>", "", corpo)`** — casa até o PRIMEIRO
  `>`. Um comentário HTML que CITA uma tag (`<!-- … em <div> -->`) deixa o resto do
  comentário VISÍVEL para quem lê em texto puro. Foi defeito real desta fase, pego na
  revisão: a 1ª linha legível virou `, e os quadrados sumiam. -->`. **Comentário em
  corpo de e-mail não pode conter `<` nem `>`.**
- **Sem `<head>` o Outlook desktop dimensiona VML pelo DPI do Windows** (tela a 125% =
  cabeçalho menor que a mensagem). O que conserta é
  `<o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch>`.
- **O botão "enviar e-mail de teste" do Admin NÃO exercita modelo nem HTML** — manda
  corpo fixo em texto puro (`api/routers/email.py`). Conferir cabeçalho por ele é falso
  verde; só o WORKER monta a mensagem do modelo.
- A régua "já é documento" tem de ser a mesma do front (`/<(html|body)\b/i`): olhar só
  `<html` embrulha um corpo que abre em `<body>` e o cliente descarta os atributos do 2º.

**⚠️ O que a F4 ensinou (nó SQL → tabela):**
- **`test_dag_factory_espera` é uma ÂNCORA do fonte gerado**: compara com um commit base
  e exige que toda mudança no gerador seja DECLARADA numa lista de deltas/trocas. Mudou
  `etl_dag_factory.py`? Declare, ou os 4 cenários falham.
- **O escalar do nó SQL não pode passar por conversão** — a Decisão `valor_sql` compara
  com régua tipada; data virando texto ISO muda o roteamento em silêncio.

**⚠️ O que a F2 revelou (vale para qualquer timeout deste repo):**
- **`sql_preview_timeout_s` NÃO é só da prévia**: `copias.py` (3 pontos) usava o mesmo
  valor como 3º argumento de `abrir_conexao_nativa`, que cai em
  `pyodbc.connect(timeout=…)` — isso é **LOGIN**, não execução. Host inalcançável
  penduraria a requisição pelo tempo da CONSULTA. Agora há `_CONNECT_TIMEOUT_S = 5`
  em `jobs.py` para o login, e `conn.timeout` para a execução.
- **`/jobs/sql-preview` e `/jobs/decisao/simular` são `async def` e rodavam pyodbc NO
  EVENT LOOP** — a API tem **2 workers uvicorn** (`api/Dockerfile`), então duas
  consultas pesadas paravam TUDO (login, dashboard, os laços do lifespan). Corrigido
  com `asyncio.to_thread`, padrão que `utilitarios.py` e `lineage_isx.py` já usavam.
  ⚠️ Vale varrer outros `async def` que chamem pyodbc direto.
- **Teste que lê o fonte procurando string mente**: tirar o `f` de um f-string deixa
  `{_PREVIEW_TIMEOUT_MAX}` cru na cara do operador e o teste segue verde. Conferir a
  mensagem RENDERIZADA (extrair a função que a monta).
- ⚠️ **O teto 280 depende do `proxy_read_timeout` de produção**, e o `config/nginx.conf`
  de lá está à frente do repo — conferir com
  `docker exec airflow-ui grep -A8 "location /orquestra/" /etc/nginx/nginx.conf`.

**⚠️ O que a F1 ensinou (vale para qualquer campo de lista):**
- **Sincronizar "prop mudou" NÃO pode ser `useEffect([lista])`** — a lista é array novo a
  cada tecla e o efeito redesenharia o campo enquanto se digita, trazendo o defeito de
  volta. Também não pode ser `ref`: o lint da casa proíbe LER ref no render
  (`Cannot access refs during render`) — o jeito aceito é ajustar estado no render com um
  espelho em `useState`, comparando TEXTO.
- **A bancada do front RENDERIZA componente real** (`tests/js/minireact.cjs` + shims de
  react-query/lucide/react-dom no `ds_params_harness.cjs`): dá para montar um painel com
  um "palco" que imita o FluxoEditor e digitar tecla a tecla. ⚠️ **O minireact NÃO roda
  `useEffect`** — bug que dependa de efeito passa despercebido; cobrir com trava estrutural.
- **Teste de ciclo simulado é tautológico**: se o roteiro não toca o componente, ele passa
  com o bug de volta. O jeito de saber: reverter o código, rodar, e exigir que FALHE.
- `git add -u` **não** pega os assets novos da `dist/` (nomes com hash): sem `git add -A
  ui-react/dist`, o `index.html` aponta para arquivo que não existe no repo — front 404.
