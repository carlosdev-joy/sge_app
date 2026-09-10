---
name: orquestra-spec-utilitarios-transferencia
description: "Spec transferência de arquivos (download do servidor → PC, upload do PC → servidor do DataStage) nos Utilitários do Orquestra; docs/spec-utilitarios-transferencia.md; 🏁 CONCLUÍDA 2026-09-07 — F1–F5 MERGEADAS (PRs #364–#368); ✅ EM PRODUÇÃO (deploy confirmado pelo usuário em 2026-09-07); pendências: decisão sobre lista de extensões (backlog) e conferências pós-deploy da release note não confirmadas item a item"
metadata:
  type: project
  originSessionId: 627a18b0-5a47-44d0-b15e-ca31a4caf9a1
  modified: 2026-09-07T22:56:46.854Z
---

Pedido do usuário em 2026-09-07: "download do arquivo direto do servidor para minha
máquina local, ou upload de um arquivo local para o servidor do datastage", sobre a tela
Utilitários ([[orquestra-spec-utilitarios-arquivos]], já em produção). Aquela spec deixava
download/upload explicitamente OUT.

**Spec:** `docs/spec-utilitarios-transferencia.md` no [[orquestra-sge-app]], **APROVADA
pelo usuário em 2026-09-07** ("aprovada, pode começar a F1"). Branch
`feat/utilitarios-transferencia-f1` a partir da main (a spec entra na PR da F1, padrão da
spec anterior).

## Estado

- ✅ **F1 MERGEADA — PR #364, squash `2420dca` na main (2026-09-07, "autorizado" do
  usuário)**: `GET /utilitarios/arquivo/baixar` (`svc.baixar_arquivo`,
  `svc.content_disposition`, `_VAGAS_TRANSFERENCIA`, `_TIMEOUT_TRANSFERENCIA_S=240`,
  spool 8 MB, `transferencia_max_kb` no config). 53 testes em
  `tests/test_utilitarios_transferencia.py` (importa FakeSftp/fixtures de
  `tests/test_utilitarios_arquivos.py`); suíte inteira sem falha nova (baseline
  origin/main em worktree: as mesmas 8 falhas pré-existentes — `test_api_v2_4` ×4,
  `test_smoke`, kanban ×3). Smoke `scripts/smoke_utilitarios_transferencia.sh`: 27 ok no
  DEV (6 paralelos de 20 MB → 4 ok + 2 ocupado). Revisão adversarial + auditoria de
  segurança: aprovadas com 8 ressalvas baixas, TODAS corrigidas no commit de fix
  (`detail=e.detail` nos negar pré-SSH, Cf em `validar_nome`, erro local do spool ≠ erro
  do servidor, bytes exatos no 413, nosniff, teste que prova o rollover, smoke).
- ✅ **F2 (front do download) MERGEADA — PR #365, squash `4369181` na main (2026-09-07,
  "merge autorizado" do usuário)**; branches remotas f1/f2 apagadas.
- ✅ **F3 (backend do upload) MERGEADA — PR #366, squash `8c058f3` na main (2026-09-07,
  "merge autorizado" do usuário)**; branch remota apagada.
- ✅ **F4 (front da aba Enviar arquivo) MERGEADA — PR #367, squash `29c3a78` na main
  (2026-09-07, "merge autorizado")**; revisão adversarial "aprovado com ressalvas" (1 médio:
  X/Esc/backdrop abortavam depois que o corpo subiu → agora não fazem nada nessa fase; 2
  baixos: status cru "500" → régua "<status> " + mapa; a11y aria-live no modal) — todos
  corrigidos antes do merge. ⚠️ No DEV, `/opt/totalseg-pwa` é montagem `:ro` no
  sshd-amostra (de propósito): upload lá dá "somente leitura" — testar em `/dados/bi`;
  o usuário pode pedir `:rw` (decisão dele, escreve numa pasta real da VPS).
- ✅ **F5 MERGEADA — PR #368, squash `7ccfd43` na main (2026-09-07, "autorizado")**.
- 🏁 **SPEC CONCLUÍDA (2026-09-07)**: F1 #364 `2420dca`, F2 #365 `4369181`, F3 #366
  `8c058f3`, F4 #367 `29c3a78`, F5 #368 `7ccfd43`. Árvore local em
  `chore/transferencia-pos-f5` (= main). Branches locais das fases ficaram (squash: só
  `-D` apaga); as remotas foram apagadas.
- ✅ **EM PRODUÇÃO** — o usuário confirmou em 2026-09-07 ("deploy realizado com sucesso").
  Os itens do checklist abaixo NÃO foram confirmados um a um (raízes ativas × binários,
  porta 8000, `/tmp`, gzip, backlog SQL, smoke) — perguntar se precisar depender deles.
  Checklist usado (release note §Deploy): (1) sem migration, sem `dags/`, sem wheel, `config/` → **n**; vai `api/` + `dist/`;
  sem relogin; (2) ANTES de liberar: `SELECT servidor, caminho FROM dbo.etl_utilitario_raiz
  WHERE ativo = 1` — nenhuma raiz cobrindo instalação/projeto do DataStage (o download
  entrega binários); (3) porta 8000: se alcançável sem o nginx, publicar `127.0.0.1:8000:8000`;
  (4) `/tmp` gravável no container da API; (5) `curl -sI -H 'Accept-Encoding: gzip'` no
  endpoint de download sem `Content-Encoding`; (6) `sql/backlog/utilitarios_transferencia.sql`
  uma vez; (7) `scripts/smoke_utilitarios_transferencia.sh` + itens de UI a, d, k3, l.
- 📌 Decisão pendente do usuário (spec §8.16 / backlog): lista de extensões única para
  editar e enviar × `permite_envio` × denylist de executáveis.
- 📌 `/simplify` nas fases F1–F4 não foi rodado (dito na PR #368); PR à parte se pedido. Manual §2.5/§3.8/§4.7/FAQ; `docs/release-notes/
  utilitarios-transferencia.md`; `sql/backlog/utilitarios_transferencia.sql` (8 itens,
  aplicado 2× no DEV = 8 linhas); smoke 54 ok; spec "concluída". `/simplify` NÃO foi
  rodado (as 4 fases passaram por revisão adversarial; dizer isso na PR).
  Conteúdo da F4: `lib/utilitariosEnvio.ts` (XHR cru, progresso, abort, 401
  → `expirarSessao` extraído de `api.ts`), puras do envio em `utilitariosTransferencia.ts`,
  `FormEnviarArquivo` (input file `sr-only` + botão; nome pré-preenchido; avisos antes da
  API; `type=button`), `ModalEnvioArquivo` (enviando/existe/pronto/cancelado/erro; Cancelar
  some quando o corpo subiu inteiro; fechar em curso = cancelar), página com `File`
  guardado entre 409 e Sobrescrever, `serieE`, `ABAS_LEMBRADAS`, banner v4. 16 testes
  novos; réguas antigas ajustadas (3 formulários; banner ≥ v3); tsc 0; eslint 0; dist
  rebuildada (DEV :8090 já serve). `PUT /utilitarios/arquivo/enviar` (corpo cru;
  ordem: permissão → lexical → Content-Length (411/422/413 sem ler) → spool contando
  (400/413/408) → VAGA só com o corpo inteiro → SSH 240 s com `tardio`); erros que cabem
  no teto DRENAM o corpo antes de responder (senão o nginx devolve 502 HTML);
  `ClientDisconnect` = 400 auditado sem traceback; `svc.preparar_envio`/
  `extensao_para_envio` (nome mantido, última extensão em minúsculas); `gravar_arquivo`
  virou embrulho de `_gravar_de(origem, tamanho)` compartilhado com `enviar_arquivo`,
  `.tmp` com `wxb` (EXCL). Revisões: adversarial "aprovado com ressalvas" (2 médios + 3
  baixos) + segurança "aprovado com ressalvas" (1 médio + 3 baixos) — todos os de código
  corrigidos; decisões/backlog em spec §8.13–21. 101 testes no arquivo; 246 antigos
  intactos; suíte inteira = 8 falhas da baseline; smoke 54 ok no DEV (k2 prova rollback
  com subpasta 1777). A revisão adversarial REPROVOU a 1ª versão com
  1 grave (faixa `z-40` atrás do Modal `z-50`: os 3 botões de Baixar vivem dentro de um
  modal aberto) + 1 baixo (foco solto quando o ícone vira disabled) + a11y (live region
  aninhada e inundada) — todos corrigidos: `z-[60]` + `data-modal-exempt`, `baixando` nas
  deps do efeito de foco, `anuncioTransferencia` em marcos numa região `sr-only`.
  Refutados com evidência: regressão do `apiFetch`, gzip × Content-Length (nginx do repo
  sem `gzip`; conferir o de PRODUÇÃO, que está à frente), Blob/reader, série. Conteúdo:
  `apiFetchBruto` + `apiFetch` por cima (idêntica); `lib/utilitariosTransferencia.ts`
  (puro), `lib/utilitariosDownload.ts` (fetch + ReadableStream + Blob + `<a download>`,
  `amb` injetável); Baixar no modal (ao lado de Copiar e no erro 415/413), ícone por linha
  no `NavegadorPastas` (li virou flex com 2 botões), `BarraTransferencia` (faixa fixa,
  aria-live sempre presente); página dona do download (um por vez, `serieT`). Bancada
  `tests/js/utilitarios_transferencia_harness.cjs` + 16 testes; bancadas antigas intactas;
  tsc 0; eslint 0 novos; dist rebuildada (DEV :8090 já serve — Ctrl+Shift+R). ⚠️ Não usar `git checkout main` neste clone: um
  worktree antigo de outra sessão (`/tmp/claude-0/-root/d72d0d73…/scratchpad/wt-chat`)
  segura a `main` local com alterações NÃO commitadas (chamados, PR #340) — não apagar sem
  o usuário; criar branches direto de `origin/main`.

## ⚠️ Gotchas pagos na F1

- **Ambiente de teste ≠ wheels de produção**: o `pip` local tem starlette/fastapi mais
  novos que `api/wheels/` (starlette 0.41.3, fastapi 0.115.5, uvicorn 0.32.1). Conferir
  comportamento de framework NA WHEEL, não no local.
- **`curl -w '%{http_code}'` não quebra linha**: em paralelo, N status colam numa linha e
  o `grep -c` vê 0. Sempre `{ curl …; echo; } > arquivo`.
- **One-liner Python dentro de `$(...)` com aspas aninhadas sai vazio em silêncio**: usar
  `python3 - "$arg" <<'PY' … PY` dentro do `$(...)`.
- **`SpooledTemporaryFile` fechado por baixo da thread presa (504)**: o `write` seguinte
  levanta `ValueError` e a thread morre limpa — é o comportamento desejado, não bug.
- **Erro LOCAL dentro do `try` do servidor**: `destino.write` (spool) dentro do mesmo
  `except OSError` que traduz erros do SFTP virava "sem espaço no servidor" (507).
- **Unicode `Cf` (U+202E) passa por `ord(c) < 32`** e inverte a leitura do nome no
  download — recusar por `unicodedata.category`.

## ⚠️ Gotchas pagos na F2 (front)

- **Camada nova fixa na tela × Modal da casa**: o `Modal.tsx` é `z-50` com backdrop
  `bg-black/70` e renderiza INLINE (sem portal); qualquer faixa/toast próprio disparado de
  dentro de um modal precisa de `z-[60]`+ E `data-modal-exempt` (senão o `onFocusIn` do
  `useOverlay` puxa o foco de volta). Toast é `z-[100]`. A bancada não tem CSS: essa
  classe de bug só a revisão adversarial pega — pedir explicitamente "z-index × Modal".
- **Botão que vira `disabled` no clique solta o foco no `<body>`** (Chrome/Firefox): atalhos
  de teclado do painel (Backspace do navegador) morrem até um novo clique — efeito de
  refoco precisa depender do flag que desliga o botão.
- **`aria-live` externa + `role="status"` interna = anúncio duplo**; texto que muda a cada
  bloco de 256 KB inunda o leitor — região `sr-only` separada da visual, só em marcos.
- **Regex `\b` não casa depois de `]`** (`z-[60]` seguido de espaço): usar `(^|\s)…(\s|$)`.
- **Foto de arrays na bancada**: guardar `chamadas.x` por referência e clicar depois muda a
  "foto"; sempre `.slice()`.

## ⚠️ Gotchas pagos na F3 (upload)

- **Responder ANTES de ler o corpo = 502 HTML do nginx** (corrida, não determinística): o
  uvicorn fecha o socket com bytes não lidos → RST → nginx `writev() failed (104)`. Todo
  endpoint que recusa com corpo pendente precisa drenar o corpo primeiro (quando cabe no
  teto). É a 1ª rota do repo que lê o corpo por `request.stream()`; as outras usam
  `Body(...)`, que lê tudo antes do handler.
- **`recebidos > Content-Length` e "corpo incompleto" são inalcançáveis no HTTP/1.1 real**
  (h11/httptools enquadram pelo Content-Length; cliente que mente vê 400 do próprio servidor
  HTTP ou vira `ClientDisconnect`). Só o transporte ASGI do TestClient os aciona — testes
  anotados como cinto.
- **`ClientDisconnect` é `Exception`**, cai no `except Exception` genérico com traceback
  ERROR — tratar à parte em qualquer rota que leia stream.
- **Vaga/semáforo tomado antes de ler a rede = DoS por cliente lento** (uvicorn sem timeout
  de leitura de corpo); tomar depois do spool e pôr `wait_for` por pedaço.
- **`asyncio.wait_for` cancela o future do executor**: o resultado tardio da thread some em
  silêncio; `asyncio.shield(fut)` + `add_done_callback` registra o desfecho após o 504.
- **Sticky bit não prova rollback na pasta do próprio usuário**: o dono da pasta renomeia
  qualquer arquivo nela; a prova é subpasta `1777` de outro dono (como `/tmp`).
- **Backticks em `git commit -m "…"`** executam comando e apagam a palavra; usar `-F -` com
  heredoc `<<'MSG'`.
- **Monkeypatch de `svc.conexao_sftp` pela fixture `sftp_falso` não se desfaz com
  `svc.__dict__[...]`** (o dict já está patchado): teste que precisa da conexão real fica
  sem a fixture.

## Decisões fechadas na entrevista (2026-09-07)

- Download: qualquer arquivo dentro das raízes, binário incluído (sem `eh_texto`), até
  50 MB; permissão = ter a tela. Botão Baixar no modal (ao lado de Copiar), ícone por linha
  no navegador de pastas, e "Baixar o arquivo" no erro 413/415 do Ver arquivo.
- Upload: só extensão da lista do Admin (comparada em minúsculas, nome mantido como está),
  até 50 MB, permissão = `acao_editar` (sem permissão nova, sem relogin). Aba nova
  "Enviar arquivo" com progresso (XHR) e Cancelar. Sobrescrita = mesma política da
  gravação (409 → Sobrescrever → `.bak` → tmp+rename, modo preservado).
- Um arquivo por vez. Teto constante de 50 MB (`TRANSFERENCIA_MAX_BYTES`), exposto como
  `transferencia_max_kb` no `/utilitarios/config`.
- Sem migration (`acao VARCHAR(10)` sem CHECK: `baixar`/`enviar` cabem). Sem mexer em
  `config/nginx.conf` (64M e 300s já bastam; prod está à frente do repo). Sem
  `python-multipart`: upload como corpo cru `application/octet-stream` com nome/pasta na
  query (pip offline, wheel evitada).
- Backend: spool em `SpooledTemporaryFile` (8 MB em RAM, resto em disco), 413 pelo
  `Content-Length` antes de ler o corpo, 411 sem ele, semáforo de 2 vagas por worker
  (503 "ocupado"), timeout próprio de 240 s. `gravar_arquivo` refatorada sobre um miolo
  `_gravar_de(origem, tamanho)` compartilhado com `enviar_arquivo`.
- Front: `apiFetchBruto` (sem Content-Type padrão, devolve `Response`) e `apiFetch`
  reescrita por cima com comportamento idêntico; download por `fetch` + Blob (token no
  localStorage inviabiliza `<a href>`); `amb` injetável nas libs para a bancada de node.

## Fases (uma PR cada, merge sempre autorizado pelo usuário)

F1 backend download → F2 front download → F3 backend upload → F4 front aba Enviar →
F5 manual/release note/smoke/backlog. Smoke em `scripts/smoke_utilitarios_transferencia.sh`.

## Riscos que a spec destaca

`+x` preservado na sobrescrita (mesma regra da gravação; `permite_gravar` por raiz sobe de
prioridade no backlog); nome vindo do PC (`validar_nome` + lexical + realpath);
`Content-Length` mentiroso; refatoração de `apiFetch` (anti-drift); `proxy_buffering` do
nginx atrasa o início do download; Blob de 50 MB no navegador.

Ver também [[orquestra-dev-testa-producao-manda]] e [[gotcha-nvarchar-utf16]].
