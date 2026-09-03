# Spec: Utilitários de arquivos no servidor — Orquestra
Data: 2026-09-03 · Status: rascunho (aguarda aprovação do usuário)

## 1. Visão

Quem desenvolve e opera as cargas precisa, várias vezes por dia, olhar o conteúdo de um
arquivo no servidor Unix do DataStage (log de job, arquivo sequencial, arquivo de
parâmetros, script) e, com menos frequência, criar ou ajustar um desses arquivos. Hoje isso
exige terminal SSH fora do Orquestra, credencial pessoal no servidor e nenhum rastro de quem
leu ou alterou o quê.

Quando estiver pronto, a tela **Utilitários** (grupo Operação) terá duas ferramentas:
**Ver arquivo** (informa diretório e nome, clica em Iniciar, um modal busca e mostra o
conteúdo inteiro com botão Copiar) e **Criar/editar arquivo** (escreve num editor, escolhe
extensão e diretório, grava no servidor). Tudo passa pela API do Orquestra, dentro de
diretórios liberados pelo admin, com auditoria de cada leitura e gravação. O servidor de
hoje é o do DataStage; o desenho deixa a porta aberta para outros servidores sem retrabalho.

## 2. Escopo

**IN:**
- Tela `/utilitarios` no grupo **Operação**, atrás da permissão nova `tela_utilitarios`
  (semeada para `admin` e `desenvolvedor`; o admin concede a outros perfis pela tela de
  Perfis).
- Campo **Servidor** desde a primeira versão, com uma única opção hoje: o servidor do
  DataStage, o mesmo `DS_SSH_HOST` que o Console DataStage já usa.
- **Ver arquivo**: diretório + nome → modal de execução (conectando → lendo → conteúdo),
  conteúdo inteiro em bloco mono, botão **Copiar conteúdo**, rodapé com tamanho, linhas,
  codificação detectada e tempo. Arquivo maior que o teto: opção **últimas N linhas**.
- **Criar/editar arquivo**: editor de texto (mono), diretório, nome, **extensão** escolhida
  de uma lista liberada, codificação (UTF-8 ou Latin-1), botão **Carregar existente** para
  editar um arquivo que já está lá, gravação via SFTP, confirmação explícita para
  sobrescrever, cópia de segurança do arquivo anterior.
- Guardrails: **diretórios-raiz liberados** e **extensões graváveis** configuráveis no Admin
  (chaves de `etl_app_config`, mesmo padrão da rota do ServiceNow), teto de tamanho, só
  texto, caminho resolvido no servidor (`realpath`) contra `..` e symlink.
- **Auditoria** de toda leitura e gravação em tabela própria (quem, quando, servidor,
  caminho, bytes, hash, resultado). O conteúdo **não** é guardado no banco.
- **Harness de DEV**: a VPS não tem servidor DataStage. Um container `sshd` com arquivos de
  amostra entra no `docker-compose.dev.yaml` para provar a mecânica antes de produção.

**OUT (explícito):**
- **Outros servidores** (os das conexões SSH do Airflow). A API não tem essas senhas (o REST
  do Airflow não as devolve). Entra depois como fase própria: estender `dbo.etl_conexao`
  para tipo `ssh` (senha cifrada com Fernet, padrão das conexões nativas) **ou** RPC via DAG
  no worker (padrão da introspecção da Cópia de Dados). O contrato `servidor` desta spec já
  aceita o id novo sem mudar tela nem endpoints. Registrado no §8.
- **Listar arquivos de um diretório** / navegador de pastas. Útil, mas amplia a superfície
  exposta (nome de todo arquivo da pasta). Fica no §8 para o usuário decidir se entra como
  fase F6 ou vai ao backlog.
- Arquivos binários, download para o PC, upload do PC, executar o arquivo (`chmod +x`,
  rodar), apagar, renomear, mover.
- Editor com realce de sintaxe, diff entre versões, histórico além da cópia de segurança.
- Nó de pipeline "escrever arquivo" no editor de fluxo. É outra feature (etapa de DAG); o
  backend desta spec pode ser reaproveitado por ela.
- Leitura pelo worker do Airflow. Tudo aqui é síncrono, na API, como o Console DataStage.

## 3. Arquitetura proposta

### Front (`ui-react/`)
- **Nova página** `src/pages/Utilitarios.tsx`: cabeçalho + `Tabs` (`components/ui/Tabs`) com
  as abas **Ver arquivo** e **Criar/editar arquivo**. Aba lembrada em `localStorage`
  (`orq.utilitarios.aba`, com `try/catch` — janela privada lança).
- **Componentes novos** em `src/components/utilitarios/`:
  - `FormVerArquivo.tsx` — Servidor (`Select`), Diretório (`Input`), Nome do arquivo
    (`Input`), "Últimas N linhas" (opcional), botão **Iniciar**.
  - `ModalConteudoArquivo.tsx` — o modal de execução: estados `conectando` → `lendo` →
    `pronto` | `erro`; bloco mono escuro igual ao `rawOutput` do `DsConsole.tsx` (exceção
    de fundo fixo já aceita na seção 4 de `docs/ui-temas-cores.md`); botão **Copiar
    conteúdo** com `lib/copiar.ts` (`copiarTexto` + `AVISO_COPIA` — a API de clipboard do
    navegador só existe em HTTPS e a produção é servida por HTTP); rodapé com tamanho,
    linhas, codificação, `truncado`, tempo.
  - `FormEditarArquivo.tsx` — Servidor, Diretório, Nome (sem extensão), Extensão (`Select`
    da lista liberada), Codificação (`Select`: UTF-8 | Latin-1), `Textarea` mono com
    contador de linhas/bytes, botões **Carregar existente** e **Gravar**.
  - `ModalGravacaoArquivo.tsx` — estados `gravando` → `pronto` | `existe` (409: mostra
    tamanho e data do arquivo atual e pede a confirmação **Sobrescrever**, que envia de
    novo com `sobrescrever: true`) | `erro`; resultado com caminho final, bytes, hash,
    cópia de segurança criada, e atalho **Ver arquivo**.
  - `erros.ts` — mapa `status → mensagem` (422/403/404/409/413/415/502/503). Contrato:
    `apiFetch` lança `Error` com `status` e `message`; a tela nunca mostra `[object Object]`.
- **Registro da tela nos QUATRO lugares** (gotcha registrado — teste anti-drift
  `tests/test_rbac_recursos_admin.py` prende os dois primeiros):
  1. `src/lib/nav.ts` — `{ to: '/utilitarios', label: 'Utilitários', icon: Wrench, group:
     'Operação', perm: 'tela_utilitarios' }`, logo após Console DataStage;
  2. `src/App.tsx` — rota `'/utilitarios': <Utilitarios />`;
  3. `src/pages/Admin.tsx` — `['tela_utilitarios', 'Utilitários']` em `RBAC_RECURSOS`;
  4. migration semeando `etl_perfil_permissao` (§4).
- Cores só por token (`bg-panel`/`text-ink`/`text-dim`/`border-edge`), par claro+escuro.
  `dist/` é versionada: toda fase de front termina com `npm run build` commitado.

### Back (`api/`)
- **Novo serviço** `api/services/ssh_arquivos.py` — separado de `ssh_datastage.py` (que é
  do `dsjob` e diz "nunca há comando livre"; aqui não há comando nenhum: é SFTP).
  - `SERVIDORES` — registro `{id: resolver}`. Hoje só `datastage`, cujas credenciais vêm
    das mesmas variáveis do Console (`DS_SSH_HOST/PORT/USER/PASSWORD/KEY_FILE`).
    Adicionar servidor = adicionar uma entrada; nenhum endpoint muda.
  - Funções **puras** (testáveis sem SSH): `normalizar_diretorio`, `validar_nome`
    (sem `/`, sem `\0`, sem `..`, tamanho ≤ 255), `montar_caminho`, `dentro_das_raizes
    (caminho_real, raizes)`, `decidir_codificacao(bytes, pedida)` (UTF-8 estrito → fallback
    Latin-1, devolve qual valeu), `eh_texto(bytes)` (rejeita `\0` e proporção alta de
    bytes de controle), `ultimas_linhas(bytes, n)`, `nome_backup(caminho, agora)`,
    `normalizar_conteudo(texto)` (CRLF → LF, garante `\n` final).
  - Cliente SFTP **injetável** (`abrir_sftp(servidor)` devolve um objeto com `stat`,
    `normalize`, `open`, `rename`, `close`); nos testes entra um fake em memória — o
    `paramiko` não está no ambiente de teste (`tests/test_ds_console.py` documenta isso).
  - Leitura: `stat` primeiro (tamanho, mtime; 404 se não existe; 422 se for diretório) →
    `normalize` (realpath **no servidor**) → `dentro_das_raizes` (senão 403, auditado
    como `negado`) → tamanho > teto sem `ultimas_linhas` → 413; com `ultimas_linhas`,
    `seek` no fim e lê só um bloco → decodifica → devolve.
  - Gravação: mesmas validações + extensão na lista liberada (422) + tamanho do conteúdo
    ≤ teto (413) → `stat` do destino: existe e `sobrescrever=false` → 409 com
    `{existente: {tamanho_bytes, modificado_em}}`; existe e `sobrescrever=true` →
    cópia de segurança `<nome>.<ext>.bak-<AAAAMMDDHHMMSS>` no mesmo diretório (se a chave
    de backup estiver ligada) → **escrita atômica**: grava em `.<nome>.<ext>.tmp-<pid>` e
    `rename` por cima (um job que leia o arquivo no meio nunca vê metade) → `sha256` →
    auditoria.
  - **Fora do event loop**: todo acesso SSH roda em `await asyncio.to_thread(...)`
    (padrão de `services/monitor_capture.py` e `dag_reconcile.py`). O Console chama o
    `paramiko` direto dentro de `async def` e segura a API inteira por até 120 s; não
    repetir.
  - Timeouts: conexão 10 s (como o Console), leitura/gravação 60 s.
- **Novo router** `api/routers/utilitarios.py` (registrar em `api/main.py`: import + lista):

  | Método | Rota | Permissão | Body → Resposta |
  |---|---|---|---|
  | GET | `/utilitarios/config` | `require_tela_utilitarios` | → `{servidores: [{id, label, configurado}], raizes: [...], extensoes: [...], tamanho_max_kb, backup_ao_sobrescrever, pode_gravar}` |
  | POST | `/utilitarios/arquivo/ler` | `require_tela_utilitarios` | `{servidor, diretorio, nome, ultimas_linhas?, codificacao?}` → `{caminho, tamanho_bytes, linhas, codificacao, truncado, modificado_em, conteudo, duracao_ms}` |
  | POST | `/utilitarios/arquivo/gravar` | `require_tela_utilitarios` **+** `PERM_EDITAR` | `{servidor, diretorio, nome, extensao, conteudo, codificacao, sobrescrever}` → `{caminho, tamanho_bytes, linhas, sha256, criado, backup, duracao_ms}` |

  Erros: 422 validação (mensagem em pt-BR, campo nomeado), 403 fora das raízes ou sem
  permissão, 404 não existe, 409 já existe, 413 acima do teto, 415 não é texto, 502 falha
  SSH, 503 servidor não configurado (`DS_SSH_HOST` vazio — mesma degradação do Console).
- **Dependência de permissão** `require_tela_utilitarios` em `api/deps.py`, cópia do
  padrão `require_ds_console` (admin **ou** recurso `tela_utilitarios`). A autoridade é a
  API: o menu escondido não protege nada.
- **Leitura da configuração**: chaves em `dbo.etl_app_config`, lidas a cada chamada (sem
  cache de processo — trocar no Admin vale na hora, sem restart). Raízes vazias = **tudo
  bloqueado** e a tela explica onde configurar.

### Dados
- `dbo.etl_app_config` — 4 chaves novas (§4).
- `dbo.etl_perfil_permissao` — recurso `tela_utilitarios`.
- `dbo.etl_utilitario_arquivo_log` — auditoria (§4).
- Nenhuma tabela existente muda.

### Orquestração
- Nenhuma DAG. O deploy não toca em `dags/` nem no worker.

### Decisões e alternativas descartadas
- **Tela própria, não aba no Console DataStage** — o Console gira em torno de projeto/job e
  já tem 8 abas; "Utilitários" é o lar da segunda ferramenta e das próximas.
- **SFTP, não `cat` por shell** — zero interpolação de entrada do usuário em comando.
- **Síncrono na API, não RPC via DAG** — o servidor de hoje já está configurado na API;
  resposta em segundos, sem latência de scheduler, sem teto de XCom, sem deploy de `dags/`.
- **Raízes liberadas com default vazio** — o admin de produção decide o que expõe; a spec
  não adivinha caminhos da Caixa.
- **Conteúdo fora do banco** — auditoria guarda caminho e hash; arquivos de dados podem ter
  dado pessoal (LGPD) e volume.
- **Backup no mesmo diretório** (`.bak-<ts>`) — simples e visível; alternativa de subpasta
  `.orquestra_bak/` fica em aberto no §8.
- **`AutoAddPolicy` mantida** (paridade com o Console) — `known_hosts` fixo é melhoria
  transversal aos dois, registrada no §8.

## 4. Modelo de dados

Migration **`sql/migrations/105_utilitarios_arquivos.sql`** — idempotente (roda 2× sem
erro; `tests/test_migrations_idempotentes.py` cobre), blocos com `GO`, aplicada pela etapa
**6c** do `deploy.sh` (responder **s**).

```sql
-- 1) Auditoria (o conteúdo NUNCA entra aqui)
IF OBJECT_ID('dbo.etl_utilitario_arquivo_log','U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_utilitario_arquivo_log (
        id            BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_utilitario_arquivo_log PRIMARY KEY,
        executado_em  DATETIME2(0)  NOT NULL CONSTRAINT DF_util_arq_log_em DEFAULT GETDATE(),
        usuario       NVARCHAR(100) NOT NULL,      -- matrícula (get_current_user)
        servidor      NVARCHAR(50)  NOT NULL,      -- 'datastage' hoje
        acao          VARCHAR(10)   NOT NULL,      -- 'ler' | 'gravar'
        caminho       NVARCHAR(1000) NOT NULL,     -- caminho REAL (pós realpath), ou o pedido se negado
        tamanho_bytes BIGINT        NULL,
        sha256        CHAR(64)      NULL,          -- só em 'gravar'
        resultado     VARCHAR(20)   NOT NULL,      -- 'ok' | 'negado' | 'erro'
        detalhe       NVARCHAR(500) NULL,          -- motivo do negado/erro, backup criado, truncado…
        duracao_ms    INT           NULL
    );
    CREATE INDEX IX_util_arq_log_em      ON dbo.etl_utilitario_arquivo_log (executado_em);
    CREATE INDEX IX_util_arq_log_usuario ON dbo.etl_utilitario_arquivo_log (usuario, executado_em);
END
GO

-- 2) Configuração (MERGE: não sobrescreve valor já editado no Admin)
--   utilitarios_arquivo_raizes     : ''  (vazio = bloqueado; separar por ';' — ex.: /opt/IBM/InformationServer/Server/Projects;/dados/bi)
--   utilitarios_arquivo_extensoes  : 'txt,sh,sql,csv,dat,log,param,prm,cfg,conf,ini,properties,json,xml,yaml,yml'
--   utilitarios_arquivo_max_kb     : '2048'
--   utilitarios_arquivo_backup     : '1'  (cópia .bak-<ts> antes de sobrescrever)

-- 3) RBAC (MERGE em etl_perfil_permissao, com o mesmo guard da 088 para a tabela existir)
--   ('admin', 'tela_utilitarios'), ('desenvolvedor', 'tela_utilitarios')
```

Larguras: `caminho` NVARCHAR(1000) cobre PATH_MAX (4096 bytes) só parcialmente; a API
recusa caminho > 1000 caracteres com 422 antes de tocar o servidor. `usuario` segue o
NVARCHAR(100) de `etl_pipeline_audit.changed_by`.

Degradação: sem a 105, a API responde 503 "migration 105 pendente" no `/config`, a tela
mostra o aviso e nada quebra no resto do Orquestra.

## 5. Fases

### F1 — Fundação + leitura (backend) + harness de DEV
- Entregável: `POST /utilitarios/arquivo/ler` e `GET /utilitarios/config` funcionando contra
  o servidor do DataStage, auditados, com a permissão e a configuração no banco; no DEV, um
  `sshd` de amostra para provar ao vivo.
- Inclui:
  - migration 105 (§4);
  - `api/deps.py`: `require_tela_utilitarios`;
  - `api/services/ssh_arquivos.py`: registro de servidores, funções puras, cliente SFTP
    injetável, leitura com `to_thread`;
  - `api/routers/utilitarios.py` (`/config`, `/arquivo/ler`) + registro em `main.py`;
  - auditoria em `etl_utilitario_arquivo_log` (ok / negado / erro);
  - **harness**: serviço `sshd-amostra` em `docker-compose.dev.yaml` (imagem já em uso na
    VPS ou `linuxserver/openssh-server`, sem porta publicada — só na rede do compose),
    volume `dev/sshd-amostra/` com arquivos: texto UTF-8, texto Latin-1 com acentos,
    arquivo > teto, binário, symlink apontando para fora da raiz, diretório; `.env.dev`
    ganha `DS_SSH_*` apontando para ele (o Console DataStage do DEV continua degradado,
    porque não há `dsjob` lá — esperado); `docs/ambiente-dev.md` ganha a seção;
  - testes `tests/test_utilitarios_arquivos.py`: funções puras (traversal `..`, nome com
    `/`, symlink fora da raiz, Latin-1, binário, `ultimas_linhas` em borda de linha,
    normalização de diretório com `//` e `/./`), router com fake SFTP (200/403/404/413/
    415/503, auditoria gravada em cada saída), permissão (consulta → 403; admin sem
    recurso → 200).
- Critérios de aceite:
  - dado `raizes = /dados`, quando pedir `/dados/../etc/passwd`, então 403 e linha
    `negado` na auditoria com o caminho pedido;
  - dado symlink `/dados/link → /etc`, quando pedir `/dados/link/passwd`, então 403
    (o `realpath` sai da raiz);
  - dado arquivo Latin-1 com "ação", quando ler sem `codificacao`, então `conteudo`
    exibe "ação" e `codificacao = 'latin-1'`;
  - dado arquivo de 5 MB e teto de 2 MB, quando ler sem `ultimas_linhas`, então 413; com
    `ultimas_linhas = 200`, então 200, `truncado = true`, 200 linhas inteiras;
  - dado `DS_SSH_HOST` vazio, quando chamar `/config`, então `servidores[0].configurado =
    false` e `/arquivo/ler` responde 503;
  - migration 105 roda 2× no SQL Server do DEV sem erro;
  - no DEV, `curl` autenticado lê o arquivo de amostra pelo `sshd-amostra`.
- Validação: `python -m pytest tests -q` contra baseline do HEAD (zero falhas novas; as 5
  pré-existentes ficam) + migration 2× no DEV + prova viva por `curl`. Sem front nesta
  fase.
- Revisão adversarial multi-agente antes da PR. PR: `feat(utilitarios): F1 — ler arquivo do servidor do DataStage pela API, com auditoria e harness de dev`.

### F2 — Tela Utilitários + aba Ver arquivo
- Entregável: menu **Utilitários** visível para quem tem o recurso, aba **Ver arquivo**
  completa, modal de execução com Copiar.
- Inclui: os 4 lugares da tela (nav, rota, `RBAC_RECURSOS`; a migration já veio na F1);
  `pages/Utilitarios.tsx`, `FormVerArquivo`, `ModalConteudoArquivo`, `erros.ts`; aba
  Criar/editar visível como "em breve" desabilitada **ou** ausente (decidir na revisão:
  ausente é mais honesto); banner quando `raizes` está vazio ("Nenhum diretório liberado —
  Admin › Configurações › utilitarios_arquivo_raizes") e quando o servidor não está
  configurado; botão Copiar com os três desfechos do `copiarTexto`; `npm run build`
  commitado.
- Critérios de aceite:
  - perfil `consulta` não vê o item no menu e recebe 403 ao abrir `/utilitarios` direto;
  - dado diretório e nome válidos, quando clicar Iniciar, então o modal abre já em
    "conectando", passa por "lendo" e mostra o conteúdo inteiro com rolagem interna (o
    corpo da página não rola na horizontal);
  - clicar em Copiar conteúdo em HTTP (DEV pelo IP) copia pelo caminho legado e o botão
    diz "copiado"; falhando, diz "selecionado — use Ctrl+C";
  - 413 mostra "arquivo de X MB acima do teto de Y MB" e oferece o campo "últimas N
    linhas" sem fechar o modal;
  - modo escuro: bloco de conteúdo legível (fundo fixo escuro é a exceção documentada),
    resto da tela só com tokens;
  - Esc fecha o modal; foco volta ao botão Iniciar.
- Validação: `npx tsc -b` (⚠️ `tsc --noEmit` não checa nada neste template) + `eslint`
  contra baseline + `npm run build` + `pytest` (o anti-drift do RBAC passa a exigir a
  entrada nova) + prova visual no DEV (`dist/` é volume: aparece na hora).
- Revisão adversarial multi-agente antes da PR (inclui CSS: especificidade, `overflow`,
  comentário com `*/`). PR: `feat(utilitarios): F2 — tela Utilitários com a aba Ver arquivo e o modal de conteúdo`.

### F3 — Gravação (backend)
- Entregável: `POST /utilitarios/arquivo/gravar` com todas as guardas.
- Inclui: extensões liberadas, teto, 409 sem `sobrescrever`, backup `.bak-<ts>`, escrita
  atômica (tmp + rename), `sha256`, normalização CRLF→LF e `\n` final, codificação pedida
  (UTF-8 | Latin-1; caractere fora do Latin-1 → 422 nomeando a posição), auditoria com
  hash; permissão `tela_utilitarios` + `PERM_EDITAR`; testes com fake SFTP (criação,
  sobrescrita com e sem backup, 409, extensão fora da lista, `.tmp` limpo em falha de
  `rename`, diretório inexistente → 404 sem criar pasta).
- Critérios de aceite:
  - dado `extensoes = txt,sql`, quando gravar `x.sh`, então 422 "extensão sh não liberada";
  - dado arquivo existente, quando gravar sem `sobrescrever`, então 409 com tamanho e data
    do atual e nada muda no servidor;
  - com `sobrescrever = true` e backup ligado, então existe `x.txt.bak-<ts>` byte-idêntico
    ao anterior e `x.txt` tem o conteúdo novo;
  - falha no `rename` deixa o arquivo original intacto e nenhum `.tmp` para trás;
  - usuário com `tela_utilitarios` mas sem `acao_editar` → 403.
- Validação: `pytest` contra baseline + prova viva no DEV pelo `curl` (arquivo aparece no
  volume do `sshd-amostra` com LF e `\n` final).
- Revisão adversarial multi-agente antes da PR. PR: `feat(utilitarios): F3 — gravar arquivo no servidor com confirmação, backup e escrita atômica`.

### F4 — Aba Criar/editar arquivo (UI)
- Entregável: a segunda aba completa, com o modal de gravação.
- Inclui: `FormEditarArquivo` (editor mono com contador, extensão da lista do `/config`,
  codificação), **Carregar existente** (reusa `/arquivo/ler` com o nome+extensão do
  formulário e ajusta a codificação para a detectada), `ModalGravacaoArquivo` com o fluxo
  do 409 (confirmação Sobrescrever mostrando o que será substituído), resultado com atalho
  Ver arquivo (abre o `ModalConteudoArquivo` do que acabou de gravar), aviso de
  "alterações não gravadas" ao trocar de aba; botão Gravar só para quem tem `pode_gravar`
  (o `/config` diz); `npm run build` commitado.
- Critérios de aceite:
  - dado texto com CRLF colado do Windows, quando gravar, então o arquivo no servidor tem
    LF (verificado por `od -c` no DEV);
  - Carregar existente de arquivo Latin-1 preenche o editor com acentos corretos e a
    codificação muda sozinha para Latin-1; gravar de volta mantém os bytes dos acentos;
  - quem não tem `acao_editar` vê a aba com o editor desabilitado e a explicação, não um
    403 surpresa;
  - Ctrl+Enter grava (mesmo gesto do editor de fluxo); Esc fecha o modal sem gravar.
- Validação: `tsc -b` + `eslint` baseline + `npm run build` + `pytest` + prova visual no
  DEV nos dois temas.
- Revisão adversarial multi-agente antes da PR. PR: `feat(utilitarios): F4 — aba Criar/editar arquivo com carregar, confirmar sobrescrita e resultado`.

### F5 — Polimento, manual e smoke
- Entregável: feature fechada e documentada.
- Inclui: seção "Utilitários" em `docs/MANUAL_USUARIO.md` (perfil Desenvolvedor e
  Operador), release note em `docs/release-notes/utilitarios-arquivos.md`, `/simplify` nos
  arquivos novos, revisão de acessibilidade (rótulos, foco, contraste dos estados do modal),
  registro no backlog (`.claude/skills/backlog`) dos itens do §8 que não entraram, e o
  roteiro de smoke do §7 executado no DEV com o resultado colado na PR.
- Critérios de aceite: manual descreve os dois fluxos com as mensagens de erro reais;
  smoke a–m do §7 com resultado registrado (DEV) e pronto para produção.
- Validação: suíte completa + build + `/code-review` do conjunto F1–F4.
- Revisão adversarial única de fecho (além das por fase). PR: `docs(utilitarios): F5 — manual, release note e smoke`.

## 6. Riscos e mitigações

| # | Risco | Impacto | Mitigação |
|---|-------|---------|-----------|
| 1 | Exposição de arquivo sensível (senha em `.param`/`.cfg`, chave, dado pessoal em arquivo de carga) | Vazamento; LGPD | Raízes liberadas com default **vazio** (nada abre até o admin decidir), permissão própria, auditoria com caminho real e usuário, sem listagem de diretório, conteúdo nunca vai ao banco |
| 2 | Escape de caminho por `..`, `//`, symlink ou nome com `/` | Leitura fora da raiz | Validação pura antes do SSH + `realpath` **no servidor** (`sftp.normalize`) conferido contra as raízes; testes com symlink para fora e com `..` codificado |
| 3 | Sobrescrever script que um job shell está usando (F3) | Job quebra ou roda meia versão | 409 sem `sobrescrever`, backup `.bak-<ts>`, escrita atômica por `rename` (o leitor vê o antigo ou o novo, nunca metade), extensão `.sh` só se o admin liberar |
| 4 | Arquivo grande trava a API (paramiko é bloqueante) | Orquestra inteiro lento | `stat` antes do `read`, teto por config, `ultimas_linhas` lê só o fim, `asyncio.to_thread`, timeouts de canal |
| 5 | Codificação: servidor em Latin-1, tela em UTF-8 | Acento quebrado ao ler; arquivo corrompido ao gravar | Detecção UTF-8 estrito → Latin-1 na leitura, codificação exibida; na gravação a codificação é escolhida e o "Carregar existente" a herda; caractere fora do Latin-1 é recusado com posição |
| 6 | Botão Copiar não funciona em produção (HTTP) | Usuário cola conteúdo velho e manda para alguém | `lib/copiar.ts` com caminho legado e os três desfechos visíveis no botão |
| 7 | DEV sem servidor DataStage: mecânica provada, mas caminhos e codificação reais só em produção | Smoke de prod pode achar diferença | Harness `sshd-amostra` reproduz Latin-1, symlink, binário e teto; smoke §7 tem itens marcados "só prod" |
| 8 | Permissão nova não aparece (relogin) ou não tem interruptor (RBAC_RECURSOS) | Tela invisível para quem deveria ver | Migration semeia admin+desenvolvedor; smoke começa por relogin; teste anti-drift prende `NAV` × `RBAC_RECURSOS` |
| 9 | Deploy: migration 105 na 6c; `config/` do nginx de prod está à frente do repo | Tela sem permissão no banco; nginx regredido | Responder **s** na 6c e **n** em `config/`; sem `dags/` nesta spec; sem dependência Python nova (paramiko já está em `api/wheels/`) |
| 10 | `AutoAddPolicy` aceita qualquer host key (paridade com o Console) | MITM na rede interna | Registrado como melhoria transversal no §8 (`known_hosts` fixo para Console e Utilitários) |

## 7. Smoke pós-deploy

a) Sair e entrar de novo (permissão vive no `localStorage`). Com `admin` e `desenvolvedor`, o
   menu Operação mostra **Utilitários**; com `consulta`, não mostra e `/utilitarios` direto
   dá "sem permissão".
b) Admin › Perfis e Permissões: o checkbox **Utilitários** existe e está marcado para admin
   e desenvolvedor.
c) Admin › Configurações: definir `utilitarios_arquivo_raizes` com os diretórios de
   produção (decisão do §8), conferir extensões e teto. Antes de definir, a tela mostra o
   banner "nenhum diretório liberado".
d) Ver arquivo: um arquivo pequeno conhecido (ex.: um `.param` de projeto) → o modal passa
   por conectando/lendo e o conteúdo é idêntico ao `cat` no servidor (conferir linhas e
   tamanho do rodapé com `wc -lc`).
e) Copiar conteúdo → colar no Bloco de Notas: texto inteiro, sem perda de acento. O botão
   disse "copiado".
f) Arquivo com acento gravado em Latin-1 (só prod) → acentos corretos e rodapé
   "codificação: latin-1".
g) Caminho fora das raízes (ex.: `/etc/passwd` e `<raiz>/../etc/passwd`) → "fora dos
   diretórios liberados"; `SELECT TOP 5 * FROM dbo.etl_utilitario_arquivo_log ORDER BY id
   DESC` mostra `negado` com o caminho pedido e a matrícula.
h) Arquivo maior que o teto (um log grande) → mensagem com os tamanhos e o campo "últimas N
   linhas"; com 200, mostra as 200 últimas linhas inteiras e `truncado`.
i) Criar arquivo novo `smoke_orquestra.txt` num diretório liberado → resultado com caminho,
   bytes e hash; no servidor, `cat` mostra o conteúdo, `od -c | tail` termina em `\n`, sem
   `\r`.
j) Gravar de novo no mesmo nome sem marcar Sobrescrever → 409 com tamanho e data do atual;
   marcar Sobrescrever → `smoke_orquestra.txt.bak-<ts>` existe com o conteúdo anterior e o
   arquivo tem o novo. Apagar os dois no servidor ao final.
k) Extensão fora da lista (ex.: `.exe`) → recusa nomeando a extensão. Perfil com a tela mas
   sem `acao_editar` → editor desabilitado com explicação.
l) Carregar existente do arquivo Latin-1 do item f, alterar uma linha sem acento, gravar →
   os acentos das outras linhas continuam corretos no `cat` (só prod).
m) Auditoria: as leituras e gravações do smoke aparecem em `etl_utilitario_arquivo_log` com
   `ok`, `negado` e os hashes; nenhuma linha contém conteúdo de arquivo.

## 8. Pendências e decisões em aberto

1. **Raízes de produção**: quais diretórios do servidor do DataStage podem ser lidos e
   gravados? (Só quem conhece a Caixa decide; o default vazio bloqueia tudo até lá.)
2. **Extensões graváveis**: a lista default do §4 serve? `.sh` entra? Gravar script que
   roda em pipeline é o caso de maior risco (risco 3).
3. **Quem grava**: `tela_utilitarios` + `acao_editar` (hoje = desenvolvedor e admin). Operador
   só lê. Confirmar.
4. **Backup ao sobrescrever**: `.bak-<ts>` no mesmo diretório (visível, pode acumular) ou
   subpasta `.orquestra_bak/` (limpo, invisível)? Proposta: mesmo diretório, com a chave
   `utilitarios_arquivo_backup` para desligar.
5. **Listar arquivos do diretório**: entra como **F6** (botão "Listar" no formulário, mesmo
   guard de raízes, mostra nome/tamanho/data, clique preenche o nome) ou fica no backlog?
6. **Mais servidores (futuro)**: quando chegar, qual caminho — `etl_conexao` tipo `ssh`
   (senha cifrada, lida pela API e pelo worker) ou RPC via DAG? A primeira é mais simples
   e reaproveita a aba Conexões do Admin. Decidir só quando o pedido vier.
7. **`known_hosts`** fixo para Console e Utilitários (risco 10): backlog transversal.
8. Nome do item de menu: **Utilitários** (proposta) ou **Ferramentas**?
