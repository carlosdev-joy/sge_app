# Spec: Utilitários — transferência de arquivos (download e upload) — Orquestra
Data: 2026-09-07 · Status: **concluída** — F1 = PR #364, F2 = PR #365, F3 = PR #366, F4 = PR #367 mergeadas (2026-09-07); F5 (manual, release note, smoke, backlog) na PR de fecho

Extensão da spec `docs/spec-utilitarios-arquivos.md` (F1–F7 em produção). Aquela spec
deixou **explicitamente fora** "download para o PC" e "upload do PC" (§2, OUT). Esta spec
traz os dois para dentro, sobre a mesma tela, as mesmas raízes, a mesma auditoria e as
mesmas permissões.

## 1. Visão

Levar um arquivo da máquina de quem desenvolve ao servidor Unix do DataStage (um `.dsx`
exportado, uma planilha de parâmetros, um script) ou trazer um de lá (um log inteiro, um
arquivo sequencial, um binário que o **Ver arquivo** recusa) exige hoje um cliente SFTP à
parte, com credencial pessoal no servidor e sem rastro de quem levou ou trouxe o quê.

Quando estiver pronto, a tela **Utilitários** terá **Baixar** ao lado de Copiar no modal de
conteúdo, em cada arquivo do navegador de pastas e como saída quando o Ver arquivo recusa
("não é texto", "acima do teto"); e uma terceira aba, **Enviar arquivo**, com raiz, pasta,
seletor de arquivo local e nome. Qualquer arquivo dentro das raízes pode ser baixado,
inclusive binário; o envio respeita a lista de extensões do Admin, o 409 com confirmação, a
cópia de segurança e a escrita atômica que a gravação já tem. Teto de **50 MB** por
transferência nos dois sentidos. Toda transferência fica na auditoria, sem conteúdo.

## 2. Escopo

**IN:**
- **Download** de um arquivo por vez, abaixo de uma raiz ativa, **sem** o teste de texto
  (binário passa), até 50 MB. Permissão: ter a tela (`tela_utilitarios`), a mesma da
  leitura. Três lugares na tela: botão **Baixar** no modal de conteúdo (ao lado de Copiar),
  ícone **Baixar** em cada arquivo do navegador de pastas, e botão **Baixar o arquivo** no
  bloco de erro do modal quando a leitura devolve 413 ou 415.
- **Upload** de um arquivo por vez, até 50 MB, só com **extensão da lista do Admin**
  (comparada em minúsculas; o nome é mantido como está, maiúsculas e espaços inclusive).
  Permissão: a tela **e** `acao_editar`, a mesma da gravação. Aba nova **Enviar arquivo**
  com Servidor, Pasta (com Navegar…), seletor de arquivo, Nome (pré-preenchido com o nome
  local, editável), **Enviar** e **Cancelar** durante o envio; barra de progresso.
- **Sobrescrita** no upload igual à gravação: 409 com tamanho e data do existente na
  primeira tentativa, botão **Sobrescrever** que reenvia o mesmo arquivo, cópia
  `.bak-<ts>-<ms>` (respeitando o interruptor do Admin), `.tmp` na mesma pasta + rename
  atômico, modo do arquivo preservado.
- **413 cedo**: o upload é recusado pelo `Content-Length` antes de ler um byte do corpo; o
  download faz `stat` e recusa antes de abrir o arquivo. Fecha o item 5 do backlog da spec
  anterior para as transferências.
- **Vagas de transferência**: no máximo 2 transferências simultâneas por worker da API; a
  3ª recebe 503 "ocupado" na hora, em vez de esperar na fila do executor. Timeout próprio de
  240 s (a leitura de texto continua com 90 s).
- **Auditoria** em `etl_utilitario_arquivo_log` com as ações novas `baixar` e `enviar`
  (tamanho, sha256, resultado `ok`/`negado`/`erro`, detalhe, duração). Sem conteúdo.
- `GET /utilitarios/config` passa a devolver `transferencia_max_kb` (51200) para a tela
  recusar arquivo grande **antes** de enviar e mostrar o teto.
- Progresso nos dois sentidos com região `aria-live`; um sentido por vez (o botão que
  iniciou fica desabilitado até terminar).

**OUT (explícito):**
- Vários arquivos por operação, seleção múltipla, download de pasta como `.zip`.
  Backlog: "Utilitários: lote e pasta como zip".
- Apagar, renomear, mover, criar pasta, `chmod`, executar.
- Teto de transferência configurável no Admin (fica a constante de 50 MB no serviço).
  Backlog: "Utilitários: teto de transferência no Admin".
- Download por link direto (ticket assinado, `<a href>` nativo com progresso do navegador).
  O token vive no `localStorage`, então o download vai por `fetch` autenticado + Blob, o
  mesmo padrão dos CSVs do app. Backlog: "Utilitários: download por ticket assinado".
- Mais servidores além do DataStage (mesma pendência §8.5 da spec anterior).
- Raiz só de leitura (`permite_gravar`): continua o item 1 do backlog anterior e ganha peso
  com o upload — ver riscos.
- Mudar `config/nginx.conf`: o de produção está à frente do repo e o atual já basta
  (`client_max_body_size 64M`, `proxy_*_timeout 300s`).
- Dependência Python nova: o upload vai como corpo binário cru, sem `python-multipart`
  (o build da API é `pip --no-index`; uma wheel nova é custo que não se paga aqui).

## 3. Arquitetura proposta

### Front (`ui-react/src`)
- `lib/api.ts`: nova `apiFetchBruto(path, opts): Promise<Response>` com a MESMA injeção de
  `Authorization`, o MESMO redirect no 401 e o MESMO shape de erro (`err.status`,
  `err.detail`, `message` do `detail` string) — mas **sem** `Content-Type` padrão e sem
  `res.json()`. `apiFetch` passa a ser `apiFetchBruto` + `Content-Type: application/json` +
  `.json()`, comportamento idêntico ao de hoje (teste anti-drift garante os dois pontos).
- `lib/utilitariosTransferencia.ts` (puro, testável em node): `urlBaixar(pedido)`,
  `nomeDoContentDisposition(header, fallback)` (lê `filename*=UTF-8''…` e `filename="…"`),
  `erroTransferencia(err)` (mapa por status: 403, 404, 411, 413 "acima do teto de
  transferência", 422, 502/503 "ocupado" ou API fora, 504), `formatarProgresso(feito,
  total)`, `extensaoDe(nome)`, `avisoEnvio(nome, tamanho, extensoes, tetoKb)`.
- `lib/utilitariosDownload.ts`: `baixarArquivo(pedido, amb, onProgresso)`, onde `amb` traz
  `fetch`, `criarUrl`, `revogarUrl` e `abrirLink` (como `copiarTexto(texto, amb)` faz com o
  clipboard) — a bancada de node injeta fakes; o navegador recebe os reais. Lê o corpo por
  `ReadableStream` contando bytes contra o `Content-Length`, monta o Blob, dispara
  `<a download>` e revoga a URL.
- `lib/utilitariosEnvio.ts`: `enviarArquivo(pedido, arquivo, amb, onProgresso)` por
  `XMLHttpRequest` (o `fetch` não expõe progresso de envio) com `PUT`, corpo = `File`,
  `Content-Type: application/octet-stream`, `Authorization` do token; devolve
  `{cancelar}`; resposta JSON tratada com o mesmo shape de erro do `apiFetch`
  (`status`/`detail`), 401 com o mesmo redirect.
- `components/utilitarios/ModalConteudoArquivo.tsx`: props novas `onBaixar?` e
  `transferencia` (estado do download em curso); botão **Baixar** em `BlocoConteudo` ao
  lado de Copiar; botão **Baixar o arquivo** em `BlocoErro` quando `erro.status` é 413 ou
  415. Todo botão `type="button"`.
- `components/utilitarios/NavegadorPastas.tsx`: prop nova `onBaixar?(pasta, nome)`; ícone
  de download por linha de arquivo (segundo botão, `type="button"`, `aria-label`), só
  quando a prop existe. `useNavegadorPastas` não muda.
- `components/utilitarios/FormVerArquivo.tsx` e `FormEditarArquivo.tsx`: prop `onBaixar?`
  repassada ao navegador.
- `components/utilitarios/FormEnviarArquivo.tsx` (novo): Servidor, `CampoPasta` com
  Navegar…, seletor de arquivo (`<input type="file">` escondido + botão "Escolher
  arquivo…" + nome/tamanho escolhido), Nome, Enviar (`type="button"`, como o Gravar do
  editor: Enter num campo não pode disparar envio), Cancelar durante o envio, barra de
  progresso. Desabilitado com explicação quando `podeGravar` é falso. Avisos antes da API:
  extensão fora da lista, arquivo acima do teto, nome inválido, pasta fora das raízes.
- `components/utilitarios/ModalEnvioArquivo.tsx` (novo): estados `enviando` (progresso +
  Cancelar) → `existe` (409: tamanho/data do atual + Sobrescrever) → `pronto` (caminho real,
  bytes, sha256, backup) → `erro`.
- `components/utilitarios/BarraTransferencia.tsx` (novo): faixa fixa no rodapé da página
  com o download em curso ("Baixando carga.bin… 12 MB de 40 MB"), o resultado ("Baixado
  carga.bin, 40 MB") ou o erro; `aria-live="polite"` sempre presente, só o texto muda.
- `pages/Utilitarios.tsx`: aba `enviar` em `TABS` (3ª, depois de Criar/editar); estado do
  download (`transferencia`) e do envio (`pedidoE`/`resultadoE`/`erroE`/`progressoE`) na
  página, com número de série contra resposta atrasada; `sobrescreverEnvio` reenvia o mesmo
  `File` com `sobrescrever=true`; a chave `orq.utilitarios.aba` aceita `enviar`.
- `InfoBanner` da tela ganha uma frase sobre Baixar e Enviar (nova `storageKey`
  `utilitarios_ver_v3`, para o banner reaparecer uma vez).
- Tokens da casa (`canvas/panel/edge/ink`, claro + escuro); nenhum tema novo. `dist/`
  rebuildada e commitada em toda fase de front.

### Back (`api/`)
- `services/ssh_arquivos.py`:
  - `TRANSFERENCIA_MAX_BYTES = 50 * 1024 * 1024`, `BLOCO_TRANSFERENCIA = 256 * 1024`.
  - `baixar_arquivo(sftp, caminho, raizes, *, teto_bytes, destino) -> dict`: `resolver_real`
    (mesma política de cima para baixo) → `stat` → pasta = 422 → `st_size > teto` = 413
    **sem abrir** → lê exatamente `st_size` bytes em blocos (com `prefetch`) para `destino`
    (file-like), calculando sha256; EOF antes de `st_size` = 502 "o arquivo mudou durante a
    leitura". Devolve `{caminho, tamanho_bytes, sha256, modificado_em}`. Sem `eh_texto`.
  - `preparar_envio(diretorio, nome, raizes, extensoes) -> (caminho, raiz)`: `validar_nome`
    do nome completo, extensão = o que vem depois do último ponto, comparada em minúsculas
    com a lista (sem ponto = 422 "arquivo sem extensão"; fora da lista = 422 nomeando a
    extensão), `RESERVA_SUFIXOS_BYTES` (215 bytes úteis, como na gravação), raiz lexical
    (403 `negado` sem SSH).
  - `gravar_arquivo` refatorada: o miolo (409, `.tmp`, chmod, backup, rename, rollback)
    vira `_gravar_de(sftp, caminho, raizes, origem, tamanho, ...)` que lê `origem` em blocos
    e calcula sha256 no caminho; `gravar_arquivo(dados: bytes)` embrulha em `BytesIO` e
    chama o miolo (contrato e testes atuais intactos); `enviar_arquivo(sftp, caminho, raizes,
    origem, tamanho, *, sobrescrever, backup, marca)` chama o mesmo miolo. Arquivo novo
    nasce com o modo do `umask` do usuário SSH (sem `+x`); sobrescrita preserva o modo do
    existente, como hoje.
- `routers/utilitarios.py`:
  - `_no_servidor(fn, *args, timeout=_TIMEOUT_S)`; `_TIMEOUT_TRANSFERENCIA_S = 240`.
  - `_VAGAS_TRANSFERENCIA = threading.BoundedSemaphore(2)`: `acquire(blocking=False)` no
    início dos dois endpoints; sem vaga = 503 "há transferências em andamento — tente em
    instantes" (auditado como `erro`).
  - `GET /utilitarios/arquivo/baixar?servidor=&diretorio=&nome=`
    (`require_tela_utilitarios`): valida como o `ler` (`servidor_valido`,
    `preparar_leitura`), roda `baixar_arquivo` no executor gravando num
    `tempfile.SpooledTemporaryFile(max_size=8 MB)`, e responde `StreamingResponse` a partir
    do spool com `Content-Type: application/octet-stream`, `Content-Length`,
    `Content-Disposition: attachment; filename="<ascii>"; filename*=UTF-8''<nome>`,
    `Cache-Control: no-store`, `X-Orquestra-Sha256`. Audita `baixar` com `ok` quando o
    arquivo foi lido do servidor (a entrega ao navegador pode ainda falhar; documentado).
    Erros seguem em JSON `{detail}` como o resto da API.
  - `PUT /utilitarios/arquivo/enviar?servidor=&diretorio=&nome=&sobrescrever=`
    (`require_tela_utilitarios` + `PERM_EDITAR` no corpo do handler, 403 `negado`): exige
    `Content-Length` (411 sem ele); `Content-Length > teto` = 413 **antes** de tocar o
    corpo; `request.stream()` para um `SpooledTemporaryFile` contando bytes (passou do teto
    = 413 "o corpo passou do tamanho declarado"; acabou antes = 400 "corpo incompleto");
    corpo vazio é aceito (cria arquivo de 0 bytes, como a gravação de texto vazio); depois
    `enviar_arquivo` no executor. Resposta `{caminho, tamanho_bytes, sha256, criado, backup,
    duracao_ms}`; 409 com `detail={mensagem, existente}` igual ao `gravar`.
  - `_carregar_config` devolve `transferencia_max_kb`.
- `deps.py`: nada muda (sem permissão nova).

### Dados
- Sem migration. `etl_utilitario_arquivo_log.acao` é `VARCHAR(10)` sem CHECK;
  `baixar` e `enviar` cabem. O comentário da migration 105 lista as ações antigas; a
  documentação da coluna passa a viver no manual (§4.7) e no release note.
- Nenhuma tabela nova, nenhuma chave nova em `etl_app_config`.

### Orquestração/automação
- Nenhuma DAG, nenhum workflow.

### Decisões e alternativas descartadas
- Corpo cru (`application/octet-stream`) em vez de `multipart/form-data`: evita
  `python-multipart` (wheel offline) e dá o `Content-Length` exato do arquivo para o 413
  cedo. O nome vai na query, percent-encoded pelo `URLSearchParams`.
- Spool em arquivo temporário do container em vez de `bytes` em memória: 2 vagas × 2
  workers × 50 MB seriam até 200 MB de RAM num container sem limite; o spool segura 8 MB em
  memória e o resto em disco, apagado no `close()`.
- Download inteiro no spool antes de responder, em vez de gerador assíncrono chunk a chunk
  a partir da thread SSH: o `proxy_buffering` do nginx bufferizaria de qualquer forma; o
  spool mantém `Content-Length` exato, sha256 pronto para a auditoria e libera a vaga SSH
  cedo.
- `fetch` + Blob em vez de `<a href>` com ticket: o app não tem cookie de sessão; o
  precedente de anexos de chamados (`ChamadoDetalheModal.tsx`) usa `<a href>` sem
  `Authorization` e sem o prefixo `/orquestra` — não é padrão para reusar. Ticket assinado
  fica no backlog.
- `XMLHttpRequest` no envio: única forma de progresso de upload no navegador. O download
  usa `fetch` com `ReadableStream`.
- Semáforo de 2 vagas em vez de teto na fila do executor: pequeno, local aos dois endpoints
  novos, sem tocar a leitura/listagem; o item 4 do backlog anterior (fila com teto) segue
  aberto para o resto.

## 4. Modelo de dados

Sem migration. Valores novos na coluna existente:

| tabela | coluna | valor novo | observação |
|---|---|---|---|
| `dbo.etl_utilitario_arquivo_log` | `acao VARCHAR(10)` | `'baixar'` | tamanho e sha256 do arquivo lido |
| `dbo.etl_utilitario_arquivo_log` | `acao VARCHAR(10)` | `'enviar'` | tamanho e sha256 do arquivo gravado; `detalhe` diz "criado"/"sobrescrito; backup …" |

## 5. Fases

### F1 — Backend do download
- Entregável: `GET /utilitarios/arquivo/baixar` funcional pela API, com teto, vagas,
  auditoria e `transferencia_max_kb` no config. Nenhuma tela chama ainda.
- Inclui:
  - `TRANSFERENCIA_MAX_BYTES`, `BLOCO_TRANSFERENCIA`, `baixar_arquivo` em `ssh_arquivos.py`.
  - `_no_servidor(..., timeout=)`, `_TIMEOUT_TRANSFERENCIA_S`, `_VAGAS_TRANSFERENCIA`,
    endpoint `baixar`, `transferencia_max_kb` em `_carregar_config`.
  - `Content-Disposition` com `filename` ASCII (não-ASCII vira `_`) e `filename*` RFC 5987.
  - Testes em `tests/test_utilitarios_transferencia.py` (serviço com `FakeSftp`: binário
    íntegro, pasta 422, acima do teto 413 sem `open` [contador no fake], arquivo que
    encolheu 502, link para fora 403; endpoint: cabeçalhos, nome com acento, 403 `negado`
    sem chamar `conexao_sftp`, 404, 503 sem vaga, auditoria `baixar`, 401/permissão).
  - `scripts/smoke_utilitarios_transferencia.sh` nasce aqui com os itens b, c, e, f, m e n
    do §7 pela API (`curl -o` + `sha256sum`), provado no DEV contra o `sshd-amostra`.
- Critérios de aceite:
  - Dado um `.bin` de 40 MB abaixo da raiz, `GET …/baixar` devolve 200, `Content-Length`
    = 40 MB, sha256 do corpo = sha256 do arquivo no servidor = `X-Orquestra-Sha256`.
  - Dado um arquivo de 50 MB + 1 byte, devolve 413 nomeando os dois tamanhos e o fake
    registra zero `open`.
  - Dado `diretorio=/etc`, devolve 403 e `conexao_sftp` não é chamada; a auditoria tem
    `baixar`/`negado` com o caminho pedido.
  - Dado nome `relatório ção.txt`, o `Content-Disposition` traz `filename*=UTF-8''…` e um
    `filename` ASCII.
  - Com as 2 vagas ocupadas, a 3ª chamada devolve 503 em menos de 1 s.
  - `GET /utilitarios/config` traz `transferencia_max_kb: 51200`.
  - `TestGravarArquivo`, `TestLerArquivo` e todo `tests/test_utilitarios_arquivos.py`
    passam sem alteração.
- Validação: pytest (baseline `origin/main`, zero falhas novas; a bomba de data de
  `test_kanban_rodape_card` não conta) + `tsc -b` + eslint + build (front intocado, só
  para provar o baseline).
- Revisão adversarial multi-agente (`qa-adversarial` + `/code-review` +
  `security-review`, foco em política de caminho, teto e vazamento de nome no cabeçalho)
  antes da PR. PR: `feat(utilitarios): F1 — baixar arquivo do servidor pela API (streaming,
  teto de 50 MB, vagas e auditoria)`. A spec entra nesta PR.

### F2 — Front do download
- Entregável: botão Baixar no modal, no navegador e na recusa do Ver arquivo; barra de
  transferência com progresso.
- Inclui:
  - `apiFetchBruto` + refatoração de `apiFetch` (comportamento idêntico).
  - `lib/utilitariosTransferencia.ts`, `lib/utilitariosDownload.ts`.
  - `ModalConteudoArquivo` (Baixar e Baixar o arquivo), `NavegadorPastas` (`onBaixar` por
    linha), `FormVerArquivo`/`FormEditarArquivo` (repasse), `BarraTransferencia`,
    `pages/Utilitarios.tsx` (estado, série, `onBaixar`), InfoBanner v3.
  - Bancada `tests/js/utilitarios_transferencia_harness.cjs` +
    `tests/test_utilitarios_transferencia_front.py` (Baixar no modal chama o `amb.fetch`
    com a URL certa e cria/revoga o link; progresso atualiza o texto `aria-live`; Baixar
    aparece no erro 415 e 413 e não no 403; ícone por linha só em arquivo e só com
    `onBaixar`; erro de rede vira frase em pt-BR). Anti-drift: `apiFetch` ainda injeta
    `Content-Type: application/json`; `apiFetchBruto` não injeta; todo `<button>` novo em
    modal/navegador tem `type="button"`; `grep "chega na F"` vazio.
- Critérios de aceite:
  - Dado o modal de conteúdo aberto, clicar Baixar dispara um `GET …/baixar` com
    `Authorization` e o navegador recebe um arquivo com o nome do servidor.
  - Dado um arquivo que o Ver arquivo recusa com 415, o bloco de erro mostra "Baixar o
    arquivo" e o download funciona; com 403, não mostra.
  - Dado o navegador de pastas, cada linha de arquivo tem o ícone Baixar; clicar nele NÃO
    preenche o formulário nem fecha o navegador.
  - Durante o download, a barra mostra "Baixando <nome>… X de Y" e o botão que iniciou fica
    desabilitado; ao fim, "Baixado <nome>, Y"; em 413, a frase nomeia o teto.
  - `git status ui-react/dist` vazio após rebuild; a tela no DEV (:8090) reflete o build.
- Validação: `tsc -b` 0 + eslint (zero novos por arquivo) + `npm run build` + pytest
  (bancadas + anti-drift + suíte inteira).
- Revisão adversarial multi-agente antes da PR (foco: resposta atrasada de download
  fechado, `type="button"`, Blob revogado, 401 no meio do download). PR:
  `feat(utilitarios): F2 — Baixar no modal de conteúdo, no navegador de pastas e na recusa
  do Ver arquivo`.

### F3 — Backend do upload
- Entregável: `PUT /utilitarios/arquivo/enviar` funcional pela API, com 413 cedo, extensão
  da lista, 409/backup/atômico, vagas e auditoria.
- Inclui:
  - `preparar_envio`, `_gravar_de` (miolo compartilhado), `enviar_arquivo`,
    `gravar_arquivo` reescrita sobre o miolo.
  - Endpoint `enviar` com 411/413/400 pelo `Content-Length` e pela contagem, spool, 409 com
    `existente`, auditoria `enviar`.
  - Testes (serviço: stream em blocos com sha256 igual ao de `hashlib` do original, 409,
    backup, chmod preservado, rollback em falha do rename, somente-leitura via
    `statvfs`; endpoint: 411 sem `Content-Length`, 413 antes de ler [asserção de que
    `request.stream()` não foi consumido e `conexao_sftp` não foi chamada], 413 por corpo
    maior que o declarado, 400 por corpo menor, 403 operador, 422 `.SH` fora da lista,
    422 sem extensão, `Relatorio.TXT` com `txt` na lista mantém o nome, 409 e depois
    `sobrescrever=true`, 503 sem vaga, auditoria `enviar` com sha256).
  - `smoke_utilitarios_transferencia.sh` ganha g, h, i, j, l e m.
- Critérios de aceite:
  - Dado `PUT …/enviar?nome=Relatorio.TXT` com 3 MB e `txt` na lista, o arquivo aparece no
    servidor com esse nome, sha256 igual, modo sem `+x`, auditoria `enviar`/`ok`.
  - Dado `Content-Length: 52428801`, a resposta é 413 e nenhum byte do corpo foi lido.
  - Dado arquivo existente 0664, enviar por cima com `sobrescrever=true` cria o `.bak`, o
    novo continua 0664 e a resposta traz `backup`.
  - Dado `.sh` fora da lista, 422 nomeando `sh`; dado `README` (sem extensão), 422.
  - Dado operador (sem `acao_editar`), 403 `negado` antes de ler o corpo.
  - `tests/test_utilitarios_arquivos.py` passa sem alteração após a refatoração de
    `gravar_arquivo`.
- Validação: pytest baseline + `tsc -b` + eslint + build (front intocado).
- Revisão adversarial multi-agente (`qa-adversarial` + `/code-review` +
  `security-review`, foco em: 413 realmente cedo, corpo que mente o tamanho, nome com
  `..`/`/` na query, extensão dupla `x.txt.sh`, `+x` herdado) antes da PR. PR:
  `feat(utilitarios): F3 — enviar arquivo ao servidor pela API (corpo cru, 413 cedo,
  409, backup e escrita atômica)`.

### F4 — Front da aba Enviar arquivo
- Entregável: aba **Enviar arquivo** completa, com progresso, Cancelar, 409 → Sobrescrever
  e modal de resultado.
- Inclui:
  - `lib/utilitariosEnvio.ts` (XHR com `amb` injetável), `avisoEnvio`.
  - `FormEnviarArquivo`, `ModalEnvioArquivo`, `TABS` com `enviar`, estado na página,
    `sobrescreverEnvio` (mesmo `File`), `podeGravar` desabilitando a aba com explicação.
  - Bancada `tests/js/utilitarios_enviar_harness.cjs` + `tests/test_utilitarios_enviar_front.py`
    (escolher arquivo preenche o nome; extensão fora da lista, arquivo acima do teto e
    pasta fora das raízes bloqueiam ANTES do XHR; Enviar abre `PUT` com a query certa e
    `application/octet-stream`; `progress` atualiza a barra; 409 mostra Sobrescrever e o
    reenvio leva `sobrescrever=true` com o mesmo `File`; Cancelar chama `abort` e o modal
    diz "cancelado"; sem `podeGravar` o formulário está desabilitado; resposta atrasada de
    pedido fechado não reabre o modal).
- Critérios de aceite:
  - Dado um `.txt` de 3 MB escolhido, o Nome vem preenchido, Enviar mostra a barra subindo
    e o modal termina em "pronto" com caminho, bytes e sha256.
  - Dado um `.exe` escolhido, o formulário avisa "extensão exe não está na lista" e Enviar
    fica desabilitado; nenhum pedido sai.
  - Dado um arquivo de 60 MB, o aviso nomeia o teto de 50 MB antes de enviar.
  - Dado destino existente, o modal mostra tamanho e data do atual e o botão Sobrescrever;
    confirmar cria o `.bak` (visível no resultado).
  - Dado Cancelar no meio, o modal diz "envio cancelado" e o servidor não tem o arquivo nem
    `.tmp` (conferido no DEV).
  - Com operador, a aba mostra o formulário desabilitado e a explicação.
  - Enter em qualquer campo do formulário NÃO envia.
  - `git status ui-react/dist` vazio após rebuild.
- Validação: `tsc -b` 0 + eslint (zero novos) + `npm run build` + pytest.
- Revisão adversarial multi-agente antes da PR (foco: estado do `File` entre 409 e
  Sobrescrever, `type="button"`, XHR abortado tarde, 401 no meio do envio, foco/`aria`).
  PR: `feat(utilitarios): F4 — aba Enviar arquivo com progresso, cancelar e sobrescrever`.

### F5 — Fecho: manual, release note, smoke e backlog
- Entregável: documentação e smoke completos; spec com status concluída.
- Inclui:
  - `docs/MANUAL_USUARIO.md`: §2.5 ganha "Baixar", §3.7 ganha a aba "Enviar arquivo"
    (ou §3.8 nova), §4.7 documenta as ações `baixar`/`enviar` na auditoria e o teto.
  - `docs/release-notes/utilitarios-transferencia.md`.
  - `scripts/smoke_utilitarios_transferencia.sh` fechado (itens do §7 pela API; sem acesso
    ao servidor de arquivos, avisa o que apagar à mão; traps de limpeza; nunca imprime
    credencial).
  - `sql/backlog/utilitarios_transferencia.sql` (idempotente, `etl_backlog`): lote/zip,
    teto no Admin, download por ticket, semáforo de transferência por usuário, expurgo de
    spool órfão (se algum dia a API cair no meio).
  - `/simplify` nas fases F1–F4 já mergeadas; spec com status concluída.
- Critérios de aceite: smoke no DEV com 0 falhas; manual e release note revisados; backlog
  aplicado 2× sem duplicar.
- Validação: pytest + `tsc -b` + eslint + build (nada de código novo; prova o baseline).
- Revisão de fecho (docs/smoke) antes da PR. PR: `docs(utilitarios): F5 — manual, release
  note, smoke e backlog da transferência de arquivos`.

## 6. Riscos e mitigações

| # | Risco | Impacto | Mitigação |
|---|-------|---------|-----------|
| 1 | Upload sobre um script existente com `+x` preserva o `+x` (mesma regra da gravação); quem tem `acao_editar` troca o conteúdo de um executável | Execução de conteúdo trocado pelo job que o chama | Arquivo novo nunca nasce `+x`; sobrescrita exige 409 + confirmação + `.bak`; decisão operacional das raízes (sem `.param`/scripts de credencial) mantida; backlog `permite_gravar` sobe de prioridade. Registrado no manual §4.7. |
| 2 | Transferência segura a thread SSH por até 240 s; 4 threads/worker; a leitura de texto passaria a esperar atrás de downloads | Ver arquivo "lento" sem explicação | Semáforo de 2 vagas por worker só para transferências (503 "ocupado" na hora); sobram 2 threads para ler/listar/gravar. |
| 3 | `Content-Length` mentiroso (maior corpo que o declarado) ou ausente | Disco do container ocupado, teto furado | 411 sem cabeçalho; contagem durante o `stream()` com 413 ao passar do teto e 400 se acabar antes; spool apagado no `close()` em `finally`. |
| 4 | Nome de arquivo vindo do PC (`..`, `/`, controle, > 255 bytes, `x.txt.sh`) | Escape da raiz ou extensão enganosa | `validar_nome` + `preparar_envio` (lexical antes do SSH) + `resolver_real` de cima para baixo; extensão é só a última; teste de cada caso na F3. |
| 5 | `Content-Disposition` com nome não-ASCII | Nome trocado ou download quebrado | `filename` ASCII de resgate + `filename*` RFC 5987; parser no front com fallback para o nome pedido. |
| 6 | Refatoração de `apiFetch` (usado em todo o app) | Regressão silenciosa em outras telas | `apiFetch` = `apiFetchBruto` + JSON, sem mudança de contrato; anti-drift confere o `Content-Type` e o `.json()`; suíte de front inteira roda na F2. |
| 7 | `proxy_buffering` ligado no nginx: o download só começa no navegador depois de a API terminar de responder | Sensação de "travou" em 50 MB | Barra "Conectando ao servidor e lendo…" antes do progresso de bytes; teto de 50 MB; `config/` de produção não muda (está à frente do repo). |
| 8 | Blob de 50 MB em memória no navegador | Aba pesada em máquina fraca | Teto de 50 MB; `URL.revokeObjectURL` logo após o clique; download por ticket no backlog. |
| 9 | Download amplia o que se lê: binários e arquivos que o teste de texto barrava | Exposição de conteúdo antes "protegido" só pelo 415 | O 415 nunca foi controle de acesso (um `.param` já sai como texto); o controle é a raiz. Documentar; auditoria `baixar` com sha256 dá rastro. |
| 10 | `dist/` esquecida numa fase de front | PR invisível em produção | Rebuild + `git status ui-react/dist` vazio como critério de aceite de F2 e F4; DEV em :8090 serve o build por volume. |

## 7. Smoke pós-deploy

> **Script**: `scripts/smoke_utilitarios_transferencia.sh` (mesmas variáveis do smoke
> anterior: `ORQ_URL`, `ORQ_USER`, `ORQ_PASS`, `RAIZ`, `PASTA`; mais `BIN` = um arquivo
> binário conhecido abaixo da raiz) cobre b, c, e, f, g, h, i, j, k, k2, m e n pela API
> com `curl` e `sha256sum`. Com acesso ao servidor de arquivos, confere modo (`stat`),
> `.bak`, ausência de `.tmp` e o rollback de verdade (k2: subpasta `1777` de outro dono);
> sem ele, avisa o que apagar à mão. j e k só direto na API (atrás do nginx o proxy
> bufferiza o corpo). a, d, k3 e l são "UI" com o roteiro impresso. Nunca imprime
> credenciais. **Resultado no DEV (2026-09-07, F5): 54 conferências ok, 0 falhas.**

a) Sem relogin (não há permissão nova): com `desenvolvedor`, a tela Utilitários mostra a
   3ª aba **Enviar arquivo**; com `operador`, a aba aparece desabilitada com a explicação.
b) Ver arquivo de um `.param` pequeno → no modal, **Baixar** → arquivo salvo no PC com o
   mesmo nome; `sha256sum` local = `sha256sum` no servidor.
c) Ver arquivo de um binário (`BIN`) → o modal recusa com "não é texto" e mostra **Baixar o
   arquivo** → download íntegro (sha256 igual).
d) Navegar… → ícone Baixar numa linha de arquivo → download; o formulário não foi
   preenchido e o navegador continuou aberto.
e) Arquivo maior que 50 MB (gerar com `dd` no servidor) → Baixar responde 413 nomeando os
   tamanhos; nada é salvo.
f) Caminho fora das raízes por `curl` direto → 403; `SELECT TOP 5 * FROM
   dbo.etl_utilitario_arquivo_log ORDER BY id DESC` mostra `baixar`/`negado`.
g) Enviar arquivo: escolher `smoke_transfer.txt` (3 MB, gerado localmente) → Nome
   preenchido → barra de progresso → modal "pronto" com caminho, bytes e sha256; no
   servidor, `sha256sum` igual e `ls -l` sem `x`.
h) Enviar de novo o mesmo nome → 409 com tamanho e data → **Sobrescrever** → `.bak-<ts>`
   existe com o conteúdo anterior; `ls -l` mantém o modo antigo.
i) Escolher `qualquer.exe` → aviso "extensão exe não está na lista" e Enviar desabilitado;
   pela API, `.SH` → 422 nomeando `sh`; `RELATORIO.TXT` → aceito com esse nome.
j) Arquivo de 60 MB → a tela avisa o teto antes de enviar; por `curl` com
   `Content-Length: 62914560` → 413 em menos de 1 s.
k) Enviar um arquivo de ~40 MB e clicar **Cancelar** no meio → modal "envio cancelado";
   no servidor, nem o arquivo nem `.tmp-*` existem.
l) Com `operador`: `PUT …/enviar` direto → 403 `negado`; a auditoria registra.
m) Três downloads do `BIN` em paralelo (`curl &` ×3) → dois 200 e um 503 "ocupado".
n) Auditoria: as linhas `baixar` e `enviar` do smoke têm `tamanho_bytes` e `sha256`
   preenchidos e nenhuma contém conteúdo.
o) Limpeza: apagar `smoke_transfer.txt`, o `.bak` e o arquivo de 50 MB+ do servidor.

## 8. Pendências e decisões em aberto

Resolvidas pelo usuário em 2026-09-07: download de qualquer arquivo (binário incluído);
upload só com extensão da lista; teto de 50 MB; sobrescrita com 409 + confirmação +
backup; permissão do upload = `acao_editar`; Baixar no modal e no navegador + aba
"Enviar arquivo"; um arquivo por vez; deploy dos Utilitários já concluído, esta spec é
trabalho novo.

1. **Extensão dupla** (`x.txt.sh`): a extensão é só a última (`sh`, recusada). Confirmar
   se algum arquivo legítimo do DataStage precisa de outra regra.
2. **Arquivo local sem extensão** (`README`, `Makefile`): recusado. Se aparecer caso real,
   a saída é o backlog "editor/envio com nome completo" (item 6 do backlog anterior).
3. **Teto de 50 MB**: constante. Se produção pedir mais, entra a chave no Admin (backlog) e
   o `client_max_body_size` do nginx (64 MB hoje) vira o limite prático.
4. **Auditoria do download**: `ok` significa "a API leu o arquivo do servidor"; a entrega
   ao navegador não é confirmável pelo servidor. Aceito.
5. **Semáforo por worker, não global**: com 2 workers do uvicorn são até 4 transferências
   simultâneas na instância. Aceito para o volume esperado; semáforo por usuário fica no
   backlog.
6. **`permite_gravar` por raiz**: o upload aumenta o alcance de quem tem `acao_editar`.
   Recomendação: subir o item 1 do backlog anterior para logo depois desta spec.

Registrado pelas revisões da F1 (adversarial + auditoria de segurança, 2026-09-07):

7. **Raízes de produção × binários**: o download entrega o que o teste de texto barrava
   (hashed files do DataStage, `RT_CONFIG*`, `RT_LOG*`, dumps) e o teto de 50 MB não segue
   o `tamanho_max_kb` da leitura. `RAIZES_PROIBIDAS` não cobre a instalação do
   InformationServer. **Antes do deploy**: `SELECT servidor, caminho FROM
   dbo.etl_utilitario_raiz WHERE ativo = 1` e confirmar que nenhuma raiz cobre instalação
   ou projeto do DS. O manual do admin (F5) diz isso.
8. **`/tmp` gravável no container da API**: o spool acima de 8 MB vai para
   `tempfile.TemporaryFile` (sem nome no Linux, sem órfão). Deploy com `read_only`/`tmpfs`
   precisaria de `/tmp` montado. Item do checklist de deploy.
9. **A vaga limita o SFTP, não respostas em voo**: a vaga é devolvida antes de servir o
   spool. Com `proxy_buffering` o nginx drena os 50 MB em menos de 1 s e o custo migra
   para o `proxy_temp` dele (cliente lento segura 50 MB por conexão, como já acontecia
   com o `ler` de 16 MB). Sem rate limit; aceito. Endurecimento possível: segundo
   semáforo de "spools vivos" e `proxy_max_temp_file_size 64m` + `send_timeout` no
   nginx de produção (que está à frente do repo).
10. **Caminho no access log**: por ser `GET`, `diretorio` e `nome` aparecem no access log
    do uvicorn e do nginx (o `ler`, `POST`, não deixava). Vira dado pessoal só se nomes
    sob as raízes carregarem CPF/matrícula. A confirmar com as raízes de produção.
11. **Janela após 504**: a vaga volta na hora, mas a thread presa ocupa o executor por até
    60 s (timeout de canal). Dois 504 seguidos + duas transferências = 4 threads e o
    `ler`/`listar` esperam. Aceito (risco 2).
12. **Ambiente de teste ≠ wheels de produção**: os testes locais rodam com starlette/
    fastapi mais novos que as wheels (`api/wheels/`: starlette 0.41.3, fastapi 0.115.5,
    uvicorn 0.32.1). A revisão conferiu `StreamingResponse`, `Content-Length` explícito e
    desconexão do cliente na fonte das wheels. Regra: mudança que dependa de comportamento
    do framework se confere na wheel, não no `pip` local.

Registrado pelas revisões da F3 (adversarial + auditoria de segurança, 2026-09-07):

13. **Porta 8000 publicada em todas as interfaces** (`docker-compose.yaml`): quem alcança a
    API sem o nginx fala com o uvicorn, que não tem timeout de leitura de corpo. A F3 tomou
    duas medidas (vaga só depois do corpo inteiro no spool; 408 se nenhum pedaço chega em
    60 s), mas o **checklist de deploy** deve conferir se a 8000 é alcançável na rede de
    produção e, se for, publicar `127.0.0.1:8000:8000` (o nginx fala pela rede do compose).
14. **Resposta com corpo pendente vira 502 HTML do nginx** (provado com a imagem de
    produção + nginx 1.27): a F3 é o primeiro endpoint do repo que responde antes de ler o
    corpo. Solução: erros que cabem no teto **drenam** o corpo antes de responder; o 413
    acima do teto e o 411 sem tamanho saem na hora (corrida documentada — a F4 pré-checa o
    tamanho pelo `transferencia_max_kb`, então o 413 só vem de `curl`). A F4 precisa
    tolerar `detail` não-JSON (502/413 HTML do nginx acima de 64 MB).
15. **Cancelar na F4 depois de o corpo chegar ao nginx**: com `proxy_request_buffering`
    o nginx já reenviou tudo; a API grava o arquivo e audita `ok` enquanto o modal diz
    "cancelado". O Cancelar só vale durante o envio ao nginx. A F4 deve dizer isso no
    modal ("cancelado antes de chegar ao servidor" × "o envio já tinha chegado: confira na
    pasta") e o smoke §7 k passa a provar "nenhuma escrita parcial", não rollback.
16. **Lista de extensões é uma só para editar texto e enviar binário**: com a semente
    (só texto, sem `sh`) o upload não abre exposição nova de execução — mas um admin que
    inclua `jar`/`so`/`class`/`zip` libera binários executáveis sob as raízes, e a
    sobrescrita preserva `+x`. **Decisão do usuário**: (a) manter uma lista só e documentar
    no manual do admin; (b) `permite_envio` por extensão; (c) denylist fixa no upload para o
    que o Unix/DataStage executa (`sh ksh bash csh pl py rb jar class so o exe dll`).
    Backlog na F5 com as três opções.
17. **Disco do servidor sem cota**: 50 MB por pedido, `.bak` a cada sobrescrita nunca
    expurgado (backlog anterior). Um usuário com `acao_editar` enche o disco em minutos,
    totalmente auditado. Backlog: cota diária por usuário lida da própria auditoria
    (`SUM(tamanho_bytes)` de `enviar`/`ok` nas 24 h) — sem migration.
18. **Desfecho tardio após 504**: a thread SSH pode concluir a troca depois de a API
    responder 504 (tela diz que falhou, arquivo foi gravado). A F3 registra o desfecho na
    auditoria (`concluído após o 504 — o arquivo FOI gravado` / `falhou após o 504`) via
    `tardio` no `_no_servidor`; para as outras operações fica no log. A F4 deve dizer, no
    504, "confira na pasta antes de reenviar".
19. **`.tmp` órfão quando o canal SSH morre no meio** (queda de rede, 60 s do canal): o
    `_apagar_tmp` usa o mesmo canal morto e engole a falha → fica `.<nome>.tmp-<pid>-<hex>`
    oculto na pasta. Pré-existente na gravação; a F3 multiplica a exposição. Backlog:
    varredura de `.tmp-` antigos na listagem do navegador ou no expurgo dos `.bak`.
20. **Janela sem o destino com backup ligado** (`rename(real→bak)` + `posix_rename`): já
    documentada na spec anterior; `hardlink@openssh.com` (`link` + `posix_rename`) fecharia
    pelo mesmo `_request` do `statvfs`. Backlog, se algum job tropeçar.
21. **`.tmp` com `O_EXCL`**: o `_gravar_de` passou a abrir o `.tmp` com `wxb`
    (`SFTP_FLAG_EXCL`), para um link plantado com o nome do `.tmp` não desviar a escrita.
    Vale também para a gravação de texto.
