---
name: orquestra-spec-utilitarios-arquivos
description: "Spec Utilitários de arquivos no servidor do DataStage (Orquestra) — tela /utilitarios com Ver arquivo, Criar/editar e navegador de pastas via SFTP pela API; raízes e extensões cadastradas no Admin; docs/spec-utilitarios-arquivos.md; 🏁 SPEC CONCLUÍDA — F1–F7 MERGEADAS (PRs #356–#363, 2026-09-03); ✅ EM PRODUÇÃO (usuário confirmou o deploy concluído em 2026-09-07); extensão download/upload vem em spec própria [[orquestra-spec-utilitarios-transferencia]]"
  modified: 2026-09-07T00:00:00.000Z
metadata: 
  node_type: memory
  type: project
  originSessionId: 97a32f84-3b42-4486-82ed-a61083d760aa
  modified: 2026-09-03T14:00:00.000Z
---

Pedido do usuário em 2026-09-02/03 ("funcionalidade utilitário"): (1) **ver o conteúdo de
um arquivo** do servidor escolhendo a pasta e o nome, com modal de execução e botão
Copiar; (2) **criar/editar arquivo** num editor, escolhendo extensão e pasta. Hoje só no
**servidor do DataStage** (o `DS_SSH_HOST` que o Console DataStage já usa), com caminho
aberto para mais servidores depois.

**Spec:** `docs/spec-utilitarios-arquivos.md` no [[orquestra-sge-app]] — **APROVADA pelo
usuário em 2026-09-03** ("aprovada, pode começar a F1"). 7 fases, uma PR cada:
F1 backend leitura + migration 105 + CRUD admin + harness → F2 Admin › aba Utilitários →
F3 tela + aba Ver arquivo → F4 backend gravação → F5 aba Criar/editar → F6 navegador de
pastas → F7 manual + smoke.

## Estado

- ✅ **F1 MERGEADA — PR #356, squash `7825a02` na main (2026-09-03, autorizado pelo
  usuário)**. 158 testes em `tests/test_utilitarios_arquivos.py`; suíte sem falha nova;
  migration 105 aplicada 2× no DEV; prova viva por curl contra o `sshd-amostra`.
- ⏳ **Deploy da F1 em produção PENDENTE**: migration 105 na 6c (responder **s**); sem
  `dags/`, sem `dist/`, sem wheel nova; `docker-compose.yaml` só ganha
  `DS_SSH_KNOWN_HOSTS` (default vazio — definir em prod depois, com o known_hosts do DS).
  Pode ir junto com as fases seguintes (nenhuma tela chama os endpoints ainda).
- ✅ **F2 MERGEADA — PR #357, squash `6d709eb` (2026-09-03, autorizado pelo usuário)**:
  Admin › Sistema › Utilitários (raízes com
  Testar/Desativar/Reativar, extensões com confirmação e alerta para `sh`, limites), só
  front + `dist/`. 22 testes em `tests/test_utilitarios_admin_front.py` (bancada
  `tests/js/utilitarios_admin_harness.cjs` no minireact + anti-drift front×back das
  constantes). Revisão adversarial: 4 ressalvas baixas, corrigidas. O DEV em :8090 já
  serve o build (prova visual é do usuário).
- ✅ **F3 MERGEADA — PR #358, squash `46085ac` (2026-09-03, autorizado pelo usuário)**:
  tela `/utilitarios` (Operação,
  após Console DataStage, `tela_utilitarios` nos 4 lugares), aba Ver arquivo
  (`components/utilitarios/FormVerArquivo` + `ModalConteudoArquivo`, lógica em
  `lib/utilitariosArquivo.ts`), Copiar via `lib/copiar.ts` com a opção nova `bruto`
  (sem trim — conteúdo de arquivo não pode perder o `\n` final). 15 testes em
  `tests/test_utilitarios_tela_front.py` (bancada `tests/js/utilitarios_tela_harness.cjs`).
  Revisão adversarial: 2 médias + 3 baixas, corrigidas (resposta atrasada de pedido
  fechado → callbacks por chamada + número de série; trim; 502 do nginx; aria-live; vazio).
  ⚠️ Permissão nova exige relogin ([[orquestra-permissao-nova-exige-relogin]]).
- ✅ **F4 MERGEADA — PR #359, squash `48d8ed1` (2026-09-03, autorizado pelo usuário)**:
  `POST /utilitarios/arquivo/gravar`
  (tela + `acao_editar`; extensão da lista; CRLF→LF; UTF-8/Latin-1 com recusa nomeando
  linha/posição; 409 com `detail={mensagem, existente}`; tmp na mesma pasta + **chmod
  preservando o modo** + `posix_rename`; backup `.bak-<ts>-<ms>`; link para dentro grava
  no ALVO). 210 testes. Revisões: 1 grave (permissões perdidas) + 3 médios corrigidos.
  ⚠️ Decisão de produção pendente (spec §8.9): raízes não devem alcançar `.param` de
  credencial, ou entra `permite_gravar` por raiz.
- ✅ **Editar caminho da raiz MERGEADO — PR #360, squash `72582f9`** (pedido do usuário ao
  testar no DEV; ele cadastrou `/opt/totalseg-pw` com erro de digitação): PATCH aceita
  `{ativo?, caminho?}` com 409 para duplicidade e auditoria `acao='raiz'`; lápis na linha
  com Enter/Esc; lápis desligado durante Testar (o resultado seria do caminho antigo).
  Também: **DEV_SSHD_PASTA_EXTRA** no `.env.dev` monta uma pasta real da VPS no
  `sshd-amostra` (hoje `/opt/totalseg-pwa`, só leitura) — sem isso o Testar dizia "não
  existe", porque o servidor de arquivos do DEV é o container.
- ✅ **F5 MERGEADA — PR #361, squash `cd8a3ba` (2026-09-03, autorizado pelo usuário)**: aba
  "Criar/editar arquivo" (`lib/utilitariosGravacao.ts`, `FormEditarArquivo`,
  `ModalGravacaoArquivo`; guarda de troca de aba; Carregar existente; 409 → Sobrescrever
  reenvia com `sobrescrever: true`; Ver arquivo pelo caminho DIGITADO). Revisão adversarial
  reprovou a 1ª versão com 8 achados, todos corrigidos — o grave: `sujo` espelhado no
  formulário (`useState` + `useEffect`) dessincronizava após a 1ª gravação (bail-out por
  `Object.is`) e a guarda morria → **estado de texto-não-gravado é da PÁGINA (prop)**; a
  bancada simula a página com um container. Outros: Enter em campo submetia o form e
  gravava arquivo vazio (Gravar virou `type=button`); refetch do config que falha não
  derruba mais a página; `txt` é a extensão padrão; extensão derivada da lista.
  **Achado do usuário no DEV**: gravar em `/opt/totalseg-pwa` (montagem `:ro`) dizia
  "detalhe registrado no log" → o SFTP esconde o errno (`OSError('Failure')`); a API
  pergunta ao OpenSSH por `statvfs@openssh.com` (via `sftp._request(200, …)`, o paramiko
  3.5 não expõe) e diz "sistema de arquivos montado somente leitura" / "sem espaço".
  Provado ao vivo. 226 testes de serviço + 20 do editor.
- ✅ **F6 MERGEADA — PR #362, squash `c9c5b14` (2026-09-03, "Merge aprovado" do usuário)**;
  árvore principal em `feat/utilitarios-f7-fecho` (= main, sem trabalho ainda):
  `GET /utilitarios/pasta/listar` (nível zero = raízes sem SSH; resposta LEXICAL
  `caminho/raiz/pai` + `caminho_real` informativo; ocultos; links com `alvo` só para dentro,
  200 resolvidos na ordem da tela, resto `desconhecido`; 20 mil brutas / 2 mil na
  resposta; auditoria `listar`), `NavegadorPastas` + hook `useNavegadorPastas` DENTRO de
  cada formulário (a página passa só `onListar`), `CampoPasta` com Navegar…. Revisão
  adversarial reprovou a 1ª versão (6) e a auditoria de segurança achou 2 médios — todos
  corrigidos e provados ao vivo. API e dist de DEV já com tudo.
  ⚠️ Gotchas pagos na F6: (1) o **Modal da casa renderiza inline, DENTRO do `<form>`** que
  o abriu — botão sem `type="button"` submete o form (Fechar disparava Iniciar); o X do
  `Modal.tsx` ganhou `type="button"`; (2) **o minireact não descarta o estado de um
  componente desmontado** — estado que precisa morrer ao fechar vai para o hook do pai;
  (3) **o SFTP esconde o errno** (EROFS/ENOSPC chegam como `Failure`): `statvfs@openssh.com`
  via `sftp._request(200, …)` conta a causa; (4) **régua de raiz proibida tem de valer no
  caminho REAL** — raiz cadastrada e ausente + `ln -s /etc` virava leitor de `/etc`;
  (5) resposta de navegador tem de ser LEXICAL, porque `ler`/`gravar` conferem assim.

- ✅ **F7 MERGEADA — PR #363, squash `7d8ffa2` (2026-09-03, "Abrir PR e Merge autorizado")**:
  manual §2.5/§3.7/§4.7 + FAQ, `docs/release-notes/utilitarios-arquivos.md`,
  `scripts/smoke_utilitarios.sh` (itens a–p do §7 pela API; 38 ok no DEV; sem acesso ao
  servidor de arquivos 25 ok + aviso das sobras; só mexe em extensão que está na lista e
  repõe por trap), `sql/backlog/utilitarios_arquivos.sql` (8 itens do §8 em etl_backlog,
  idempotente), simplificação `0c291e7`, spec com status concluída. Revisão de fecho:
  código aprovado; 7 ressalvas de docs/smoke corrigidas (coluna `executado_em`, botão
  "Ver o fim do arquivo", known_hosts dentro do container, `bat` não é script na lista).
- 🏁 **SPEC CONCLUÍDA.** Árvore principal em `chore/utilitarios-pos-f7` (= main).
- ✅ **EM PRODUÇÃO** — o usuário confirmou em 2026-09-07 que o deploy foi finalizado
  ("o deploy dos utilitarios ja foi finalizado podemos encerrar ele"). O checklist abaixo
  fica como registro histórico; não há mais pendência de deploy desta spec. A extensão
  download/upload (pedida em 2026-09-07) é spec própria: [[orquestra-spec-utilitarios-transferencia]].
- ~~⏭️ DEPLOY EM PRODUÇÃO PENDENTE~~ — checklist usado: (1) migration 105 na 6c → `s`; `config/`
  → `n`; sem dags/wheel; vai `api/` + `dist/`; (2) `.env`: `DS_SSH_*` do Console + 
  **`DS_SSH_KNOWN_HOSTS=/opt/airflow/dsx/known_hosts`** com o arquivo gerado por
  `ssh-keyscan` em `dsx/` (o compose só monta dags/ e dsx/; caminho do host = 503 em toda a
  tela); (3) relogin pela permissão `tela_utilitarios`; (4) Admin › Sistema › Utilitários:
  cadastrar raízes que NÃO alcancem `.param` de credencial (§8.9) e Testar cada uma;
  (5) `sql/backlog/utilitarios_arquivos.sql` uma vez; (6) `scripts/smoke_utilitarios.sh`
  com ORQ_URL/ORQ_USER/ORQ_PASS/RAIZ/PASTA/ARQ/LATIN1 (i/o e a limpeza exigem acesso ao
  servidor; sem ele o script diz o que apagar à mão); (7) itens UI a, b, f, n do §7.

## ⚠️ Gotchas da bancada de front (F2)

- **Re-achar os nós antes de cada gesto**: o `onSubmit`/`onClick` de um render antigo
  fecha sobre o estado antigo (campo vazio) — capturar `form` uma vez e reusar submete
  "nada" e a bancada mente. Usar funções (`form()`, `campo()`).
- **Handler `async`**: o minireact re-renderiza no `clicar`/`disparar`, mas o `await`
  do handler resolve depois — ceder `setImmediate` ×2 e chamar `tela.sincronizar()`.
- O shim de `react` precisa de `forwardRef` (Input/Switch) e `useId` (Input/Select),
  que o minireact não tem; `useEffect` é no-op (Modal renderiza inline, sem portal).
- `eslint src` na main tem 196 problemas pré-existentes (Admin.tsx+ui = 52): régua é
  zero NOVOS, contando por arquivo. `tsc -b` na main é 0.
- **`setTimeout` dentro do componente segura o Node**: o aviso "copiado" some por timer
  de 2,5 s; ele dispara depois que a bancada descartou a árvore e o setState quebra
  (exit 1 com o JSON já escrito). Encerrar com `process.stdout.write(json, () =>
  process.exit(0))`.
- **Regra do aceite da malha vale para TODO o front**: `grep -rn "chega na F"
  ui-react/src` tem de voltar vazio, inclusive em COMENTÁRIO
  (`tests/test_malhas_f11_aceite.py`). Escrever "é de uma fase posterior".
- **Anti-drift por regex no `.tsx` precisa tirar comentários antes** — o cabeçalho que
  explica "não use `navigator.clipboard`" contém `navigator.clipboard`.
- ⚠️ **`npm run build` em background com cwd errado falha em silêncio** (`npm error
  enoent`, exit 0 no wrapper): a dist ficou VELHA e foi commitada — sempre conferir com
  um rebuild + `git status ui-react/dist` vazio antes da PR. Aconteceu na F3 (pego antes
  do push).

## Decisões de desenho (aprovadas com a spec)

- Tela própria **Utilitários** no grupo Operação (não aba do Console DataStage, não nó do
  editor de fluxo). Operador lê; desenvolvedor e admin gravam (`tela_utilitarios` +
  `acao_editar`). Menu "Utilitários".
- **SFTP síncrono na API**, nunca `cat`/`ls` por shell. Executor **dedicado** de 4 threads
  com teto de 90 s (504) — o Console chama o paramiko dentro de `async def` e trava a
  API; não repetir.
- Raízes e extensões em **tabelas** (`etl_utilitario_raiz` com `ativo`, raiz se desativa;
  `etl_utilitario_extensao`, semente só com a tabela vazia, `sh` fora). Auditoria em
  `etl_utilitario_arquivo_log` sem conteúdo. Extensões valem para GRAVAR; leitura só
  pelas raízes + teste de texto. Raízes de sistema (`/etc`, `/usr`, `/dev`…) recusadas.
- Política de caminho: lexical antes do SSH (403 sem revelar existência) e `realpath`
  **de cima para baixo** no servidor (raiz → pasta → arquivo), raízes também resolvidas
  (raiz-symlink vale).
- Gravação (F4): 409 sem `sobrescrever`, backup `.bak-<ts>`, tmp+rename, CRLF→LF,
  codificação UTF-8 | Latin-1 escolhida. Copiar via `lib/copiar.ts` (produção é HTTP).
- `DS_SSH_KNOWN_HOSTS` opcional (RejectPolicy); em produção definir. Levar ao Console =
  backlog. Expurgo do log = backlog (§8).

## ⚠️ Gotchas pagos nesta F1 (reutilizáveis)

- **NVARCHAR conta unidades UTF-16, não code points** — ver [[gotcha-nvarchar-utf16]].
  Corte `[:1000]` deixava 600 emojis estourarem a coluna e a auditoria da tentativa sumia.
- **`posixpath.normpath("//x")` devolve `//x`** (POSIX preserva duas barras): raiz `//`
  passava pela guarda "não pode ser /" e casava com o servidor inteiro. Colapsar barras
  iniciais ANTES do normpath.
- **Chave única de índice = 1.700 bytes** (nonclustered): `NVARCHAR(50)+NVARCHAR(1000)`
  cria com aviso e falha no INSERT (Msg 1946). O teste de idempotência é regex, não pega.
- **`realpath` do OpenSSH tolera o ÚLTIMO componente ausente** (devolve o caminho);
  só componente intermediário dá ENOENT. Fake de teste que lança ENOENT em tudo esconde
  o defeito.
- **`paramiko.open_sftp()` não tem timeout no handshake** — abrir o canal à mão
  (`open_session(timeout)` + `settimeout` + `invoke_subsystem("sftp")`).
- **`pytest -p no:logging` quebra `caplog`** e inventa 6 ERRORs na suíte do Orquestra —
  rodar a suíte sem esse flag; o baseline honesto é `origin/main` num worktree COM
  `ui-react/node_modules` (senão 400+ testes viram SKIP e o kanban muda de estado).
- `test_kanban_rodape_card::test_o_prazo_aparece_no_card` é bomba de data (fixture com
  prazo 02/09/2026): falha na main desde 2026-09-03 — não é regressão de ninguém.
- **DEV não tem servidor DataStage**: `sshd-amostra` (compose dev, porta 2222, só na rede
  do compose) + `.env.dev` com `DS_SSH_*` apontando para ele; árvore gerada no arranque
  por `dev/sshd-amostra/10-amostra.sh`. A imagem da API de DEV é BUILDADA (sem bind mount
  de `api/`): mudar código exige `compose build orquestra-api` + `up -d --no-deps`.
- Aplicar migration no DEV: `docker cp sql orquestra-api:/tmp/sql` + `migrate.py` (registra
  em `etl_schema_version.migration_name`); 2ª execução por `sqlcmd -b -I -i`.

Ver [[orquestra-fluxo-etapas]] (levantamento do editor feito na mesma sessão),
[[orquestra-rbac-recursos-lista-dupla]] (os 4 lugares da tela na F3) e
[[orquestra-dev-testa-producao-manda]].
