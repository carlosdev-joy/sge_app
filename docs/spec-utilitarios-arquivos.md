# Spec: Utilitários de arquivos no servidor — Orquestra
Data: 2026-09-03 · Status: rascunho v2 (respostas do usuário incorporadas; aguarda aprovação)

## 1. Visão

Quem desenvolve e opera as cargas precisa, várias vezes por dia, olhar o conteúdo de um
arquivo no servidor Unix do DataStage (log de job, arquivo sequencial, arquivo de
parâmetros, script) e, com menos frequência, criar ou ajustar um desses arquivos. Hoje isso
exige terminal SSH fora do Orquestra, credencial pessoal no servidor e nenhum rastro de quem
leu ou alterou o quê.

Quando estiver pronto, a tela **Utilitários** (grupo Operação) terá duas ferramentas:
**Ver arquivo** (escolhe a pasta, informa o nome, clica em Iniciar; um modal busca e mostra
o conteúdo inteiro com botão Copiar) e **Criar/editar arquivo** (escreve num editor, escolhe
extensão e pasta, grava no servidor). O admin cadastra **um ou mais diretórios-raiz** e
**quais extensões podem ser usadas**; abaixo de cada raiz o usuário **navega pelas pastas**
até a desejada. Tudo passa pela API do Orquestra, com auditoria de cada leitura e gravação.
O servidor de hoje é o do DataStage; o desenho deixa a porta aberta para outros servidores
sem retrabalho.

## 2. Escopo

**IN:**
- Tela `/utilitarios` no grupo **Operação**, atrás da permissão nova `tela_utilitarios`,
  semeada para `admin`, `desenvolvedor` e `operador`. **Ler** = ter a tela. **Gravar** = ter
  a tela **e** `acao_editar` (hoje só desenvolvedor e admin; operador só lê). O admin ajusta
  pela tela de Perfis.
- Campo **Servidor** desde a primeira versão, com uma única opção hoje: o servidor do
  DataStage, o mesmo `DS_SSH_HOST` que o Console DataStage já usa.
- **Admin › aba Utilitários** (grupo Sistema do Admin): cadastro de **diretórios-raiz**
  (vários, por servidor; incluir, desativar, reativar) e de **extensões** (incluir e
  excluir), além do teto de tamanho e da opção de backup.
- **Ver arquivo**: pasta + nome → modal de execução (conectando → lendo → conteúdo),
  conteúdo inteiro em bloco mono, botão **Copiar conteúdo**, rodapé com tamanho, linhas,
  codificação detectada e tempo. Arquivo maior que o teto: opção **últimas N linhas**.
- **Criar/editar arquivo**: editor de texto (mono), pasta, nome, **extensão** escolhida da
  lista cadastrada, codificação (UTF-8 ou Latin-1), botão **Carregar existente** para editar
  um arquivo que já está lá, gravação via SFTP, confirmação explícita para sobrescrever,
  cópia de segurança do arquivo anterior.
- **Navegador de pastas** (F6): a partir das raízes cadastradas, desce pasta a pasta, mostra
  subpastas e arquivos (nome, tamanho, data), "Usar esta pasta" preenche o formulário e o
  clique num arquivo preenche o nome. Vale nas duas abas. A pasta digitada continua aceita.
- Guardrails: tudo abaixo de uma raiz cadastrada é alcançável, nada fora dela; caminho
  resolvido no servidor (`realpath`) contra `..` e symlink; teto de tamanho; só texto.
- **Auditoria** de toda leitura, listagem e gravação em tabela própria (quem, quando,
  servidor, caminho, bytes, hash, resultado). O conteúdo **não** é guardado no banco.
- **Harness de DEV**: a VPS não tem servidor DataStage. Um container `sshd` com arquivos de
  amostra entra no `docker-compose.dev.yaml` para provar a mecânica antes de produção.

**OUT (explícito):**
- **Outros servidores** (os das conexões SSH do Airflow). A API não tem essas senhas (o REST
  do Airflow não as devolve). Entra depois como fase própria: estender `dbo.etl_conexao`
  para tipo `ssh` (senha cifrada com Fernet, padrão das conexões nativas) **ou** RPC via DAG
  no worker (padrão da introspecção da Cópia de Dados). O contrato `servidor` desta spec e a
  coluna `servidor` das raízes já aceitam o id novo sem mudar tela nem endpoints.
- Arquivos binários, download para o PC, upload do PC, executar o arquivo (`chmod +x`,
  rodar), apagar, renomear, mover, criar pasta.
- Editor com realce de sintaxe, diff entre versões, histórico além da cópia de segurança.
- Nó de pipeline "escrever arquivo" no editor de fluxo. É outra feature (etapa de DAG); o
  backend desta spec pode ser reaproveitado por ela.
- Leitura pelo worker do Airflow. Tudo aqui é síncrono, na API, como o Console DataStage.
- Busca de arquivo por nome dentro da raiz (`find`). Fica para depois do navegador.

## 3. Arquitetura proposta

### Front (`ui-react/`)
- **Nova página** `src/pages/Utilitarios.tsx`: cabeçalho + `Tabs` (`components/ui/Tabs`) com
  as abas **Ver arquivo** e **Criar/editar arquivo**. Aba lembrada em `localStorage`
  (`orq.utilitarios.aba`, com `try/catch` — janela privada lança).
- **Componentes novos** em `src/components/utilitarios/`:
  - `CampoPasta.tsx` — o campo Pasta compartilhado pelas duas abas: `Input` de caminho +
    botão **Navegar…** (F6) que abre o `NavegadorPastas`; mostra a raiz a que o caminho
    pertence (ou "fora das raízes" em vermelho antes mesmo de chamar a API, comparando por
    prefixo — a autoridade continua sendo o `realpath` no servidor).
  - `FormVerArquivo.tsx` — Servidor (`Select`), Pasta (`CampoPasta`), Nome do arquivo
    (`Input`), "Últimas N linhas" (opcional), botão **Iniciar**.
  - `ModalConteudoArquivo.tsx` — o modal de execução: estados `conectando` → `lendo` →
    `pronto` | `erro`; bloco mono escuro igual ao `rawOutput` do `DsConsole.tsx` (exceção
    de fundo fixo já aceita na seção 4 de `docs/ui-temas-cores.md`); botão **Copiar
    conteúdo** com `lib/copiar.ts` (`copiarTexto` + `AVISO_COPIA` — a API de clipboard do
    navegador só existe em HTTPS e a produção é servida por HTTP); rodapé com tamanho,
    linhas, codificação, `truncado`, tempo.
  - `FormEditarArquivo.tsx` — Servidor, Pasta (`CampoPasta`), Nome (sem extensão),
    Extensão (`Select` da lista cadastrada), Codificação (`Select`: UTF-8 | Latin-1),
    `Textarea` mono com contador de linhas/bytes, botões **Carregar existente** e **Gravar**.
  - `ModalGravacaoArquivo.tsx` — estados `gravando` → `pronto` | `existe` (409: mostra
    tamanho e data do arquivo atual e pede a confirmação **Sobrescrever**, que envia de
    novo com `sobrescrever: true`) | `erro`; resultado com caminho final, bytes, hash,
    cópia de segurança criada, e atalho **Ver arquivo**.
  - `NavegadorPastas.tsx` (F6) — modal: se há mais de uma raiz, começa pela lista de
    raízes; depois breadcrumb desde a raiz, lista com pastas primeiro e arquivos depois
    (nome, tamanho, data), duplo clique ou Enter desce, Backspace sobe (nunca acima da
    raiz), **Usar esta pasta**, clique em arquivo devolve nome (e extensão, na aba de
    edição). Ocultos (`.`) escondidos por padrão, com interruptor "mostrar ocultos".
  - `erros.ts` — mapa `status → mensagem` (422/403/404/409/413/415/502/503). Contrato:
    `apiFetch` lança `Error` com `status` e `message`; a tela nunca mostra `[object Object]`.
- **Admin › aba Utilitários** em `src/pages/Admin.tsx` (grupo `sistema`, ao lado de
  Conexões de Dados; padrão visual do `ConexoesTab`): dois cards.
  - **Diretórios-raiz**: tabela (servidor, caminho, ativo, cadastrado por/em), formulário
    incluir (servidor + caminho absoluto), ação **Desativar/Reativar** (não apaga: o log
    de auditoria referencia caminhos que estavam abaixo dela). Botão **Testar** faz `stat`
    no servidor e diz se a pasta existe e é legível pelo usuário SSH.
  - **Extensões**: lista de chips (`txt`, `sql`, …), campo incluir (sem ponto, minúsculas,
    `^[a-z0-9]{1,15}$`), **Excluir** em cada chip (apaga de fato: extensão não tem
    dependente). Vazio = nada pode ser gravado; a tela de edição avisa.
  - Teto de tamanho (KB) e "cópia de segurança ao sobrescrever" (interruptor), gravados
    nas chaves de `etl_app_config` do §4.
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
    (caminho_real, raizes)` (prefixo por componente: `/dados2` **não** está abaixo de
    `/dados`), `decidir_codificacao(bytes, pedida)` (UTF-8 estrito → fallback Latin-1,
    devolve qual valeu), `eh_texto(bytes)` (rejeita `\0` e proporção alta de bytes de
    controle), `ultimas_linhas(bytes, n)`, `nome_backup(caminho, agora)`,
    `normalizar_conteudo(texto)` (CRLF → LF, garante `\n` final), `extensao_de(nome)`,
    `ordenar_entradas(lista)` (pastas primeiro, depois nome, sem diferenciar caixa).
  - Cliente SFTP **injetável** (`abrir_sftp(servidor)` devolve um objeto com `stat`,
    `lstat`, `normalize`, `listdir_attr`, `open`, `rename`, `close`); nos testes entra um
    fake em memória — o `paramiko` não está no ambiente de teste
    (`tests/test_ds_console.py` documenta isso).
  - Leitura: `stat` primeiro (tamanho, mtime; 404 se não existe; 422 se for diretório) →
    `normalize` (realpath **no servidor**) → `dentro_das_raizes` das raízes **ativas**
    (senão 403, auditado como `negado`) → tamanho > teto sem `ultimas_linhas` → 413; com
    `ultimas_linhas`, `seek` no fim e lê só um bloco → decodifica → devolve.
  - Listagem (F6): `normalize` + guarda das raízes → `listdir_attr` → filtra ocultos (se
    pedido) → ordena → limita a 2.000 entradas com `truncado` → tipo por `lstat` (`pasta`
    | `arquivo` | `link`; link é mostrado mas só é seguido se o `realpath` ficar dentro de
    uma raiz). Sem `caminho`, devolve as raízes ativas do servidor como nível zero.
  - Gravação: mesmas validações + extensão na lista cadastrada (422) + tamanho do conteúdo
    ≤ teto (413) → destino por `lstat`: **link para dentro das raízes grava no ALVO** (é o
    que `ler` mostra e o que um job usa), link para fora → 403, link quebrado é substituído
    por arquivo; `stat` do alvo: existe e `sobrescrever=false` → 409 com
    `{existente: {tamanho_bytes, modificado_em}}`; existe e `sobrescrever=true` →
    cópia de segurança `<nome>.<ext>.bak-<AAAAMMDDHHMMSS>-<ms>` no mesmo diretório (se a
    chave de backup estiver ligada) → **escrita atômica**: grava em
    `.<nome>.<ext>.tmp-<marca única>`, **preserva as permissões** do arquivo anterior
    (`chmod` no tmp — sem isto um `.param` 0775 do grupo sairia 0644 e o job que escreve
    nele quebraria) e `posix_rename` por cima (um job que leia o arquivo no meio vê o
    antigo ou o novo, nunca metade) → `sha256` → auditoria. Falha no meio: o original volta
    ao lugar e o `.tmp` some.
  - **Erro de gravação com causa na tela**: o SFTP esconde o errno de quase tudo — pasta
    somente leitura, disco cheio e cota chegam como um `Failure` sem número. Quando isso
    acontece, a API pergunta ao OpenSSH (extensão `statvfs@openssh.com`, melhor esforço)
    e responde "O servidor recusou gravar em X: o sistema de arquivos está montado somente
    leitura" / "não há espaço livre no disco"; servidor sem a extensão recebe a frase com as
    causas comuns. `EACCES` diz "sem permissão para gravar em X". Nada de "detalhe no log"
    para quem está na tela (achado do teste em DEV com a montagem `:ro` de
    `DEV_SSHD_PASTA_EXTRA`).
  - ⚠️ Dois efeitos que a tela e o manual dizem: (1) o **dono** do arquivo sobrescrito
    passa a ser o usuário SSH da API (SFTP não muda dono; as permissões são preservadas);
    (2) com backup ligado, entre mover o original para `.bak` e pôr o novo no lugar há um
    instante em que o caminho **não existe** — nunca "metade", mas um `open` nesse
    instante recebe "não encontrado". Backup desligado = um único `posix_rename`, sem
    janela.
  - Nome final (`<nome>.<ext>`) limitado a 215 bytes: o `.tmp` e o `.bak` precisam caber
    nos 255 do NAME_MAX. Criar arquivo NOVO não é exclusivo sob corrida (o SFTP não tem
    `O_EXCL`): duas criações simultâneas do mesmo nome terminam com o último a renomear.
  - **Fora do event loop**: todo acesso SSH roda em `await asyncio.to_thread(...)`
    (padrão de `services/monitor_capture.py` e `dag_reconcile.py`). O Console chama o
    `paramiko` direto dentro de `async def` e segura a API inteira por até 120 s; não
    repetir.
  - Timeouts: conexão 10 s (como o Console), leitura/gravação/listagem 60 s.
- **Novo router** `api/routers/utilitarios.py` (registrar em `api/main.py`: import + lista):

  | Método | Rota | Permissão | Body → Resposta |
  |---|---|---|---|
  | GET | `/utilitarios/config` | `require_tela_utilitarios` | → `{servidores: [{id, label, configurado}], raizes: [{id, servidor, caminho}] (só ativas), extensoes: [...], tamanho_max_kb, backup_ao_sobrescrever, pode_gravar}` |
  | POST | `/utilitarios/arquivo/ler` | `require_tela_utilitarios` | `{servidor, diretorio, nome, ultimas_linhas?, codificacao?}` → `{caminho, tamanho_bytes, linhas, codificacao, truncado, modificado_em, conteudo, duracao_ms}` |
  | GET | `/utilitarios/pasta/listar` (F6) | `require_tela_utilitarios` | `?servidor&caminho?&mostrar_ocultos?` → `{caminho_real, raiz, pai, entradas: [{nome, tipo, tamanho_bytes, modificado_em}], ocultos_omitidos, truncado}` |
  | POST | `/utilitarios/arquivo/gravar` | `require_tela_utilitarios` **+** `PERM_EDITAR` | `{servidor, diretorio, nome, extensao, conteudo, codificacao, sobrescrever}` → `{caminho, tamanho_bytes, linhas, sha256, criado, backup, duracao_ms}` |
  | GET | `/utilitarios/admin/raizes` | `get_admin_user` | → `[{id, servidor, caminho, ativo, criado_por, criado_em}]` (inclui inativas) |
  | POST | `/utilitarios/admin/raizes` | `get_admin_user` | `{servidor, caminho}` → `{id}`; 422 se não for absoluto/normalizado; 409 se já existe |
  | PATCH | `/utilitarios/admin/raizes/{id}` | `get_admin_user` | `{ativo?, caminho?}` → `{ok, id, servidor, caminho, ativo}`; caminho novo passa pela régua do cadastro, 409 se repetir outra raiz, e a troca é auditada (`acao='raiz'`) |
  | POST | `/utilitarios/admin/raizes/{id}/testar` | `get_admin_user` | → `{existe, legivel, caminho_real}` (faz `stat` no servidor) |
  | GET | `/utilitarios/admin/extensoes` | `get_admin_user` | → `[{extensao, criado_por, criado_em}]` |
  | POST | `/utilitarios/admin/extensoes` | `get_admin_user` | `{extensao}` → `{ok}`; 422 fora de `^[a-z0-9]{1,15}$`; 409 repetida |
  | DELETE | `/utilitarios/admin/extensoes/{extensao}` | `get_admin_user` | → `{ok}` |
  | PUT | `/utilitarios/admin/config` | `get_admin_user` | `{tamanho_max_kb, backup_ao_sobrescrever}` → `{ok}` (MERGE nas chaves do §4) |

  Erros: 422 validação (mensagem em pt-BR, campo nomeado), 403 fora das raízes ou sem
  permissão, 404 não existe, 409 já existe, 413 acima do teto, 415 não é texto, 502 falha
  SSH, 503 servidor não configurado (`DS_SSH_HOST` vazio — mesma degradação do Console).
- **Dependência de permissão** `require_tela_utilitarios` em `api/deps.py`, cópia do
  padrão `require_ds_console` (admin **ou** recurso `tela_utilitarios`). A autoridade é a
  API: o menu escondido não protege nada.
- **Leitura da configuração**: raízes e extensões lidas das tabelas a cada chamada (sem
  cache de processo — cadastrar no Admin vale na hora, sem restart). Sem raiz ativa =
  **tudo bloqueado** e a tela explica onde cadastrar.

### Dados
- `dbo.etl_utilitario_raiz` — diretórios-raiz por servidor (§4).
- `dbo.etl_utilitario_extensao` — extensões permitidas (§4).
- `dbo.etl_utilitario_arquivo_log` — auditoria (§4).
- `dbo.etl_app_config` — 2 chaves (teto, backup).
- `dbo.etl_perfil_permissao` — recurso `tela_utilitarios`.
- Nenhuma tabela existente muda.

### Orquestração
- Nenhuma DAG. O deploy não toca em `dags/` nem no worker.

### Decisões e alternativas descartadas
- **Tela própria, não aba no Console DataStage** — o Console gira em torno de projeto/job e
  já tem 8 abas; "Utilitários" é o lar da segunda ferramenta e das próximas.
- **SFTP, não `cat`/`ls` por shell** — zero interpolação de entrada do usuário em comando.
- **Síncrono na API, não RPC via DAG** — o servidor de hoje já está configurado na API;
  resposta em segundos, sem latência de scheduler, sem teto de XCom, sem deploy de `dags/`.
- **Raízes e extensões em tabelas, não em chave de texto** — o admin inclui/exclui pela
  tela com validação, rastro de quem cadastrou, e a raiz pode ser desativada sem sumir do
  histórico. Teto e backup ficam em `etl_app_config` porque são valores únicos.
- **Raiz se desativa, não se apaga** — o log de auditoria referencia caminhos abaixo dela.
- **Extensões valem para GRAVAR** — a leitura é limitada pelas raízes e pelo teste de texto,
  porque muito arquivo Unix não tem extensão (assunção registrada no §8).
- **Ocultos escondidos por padrão no navegador** — `.ssh`, `.bash_history` e afins não
  devem aparecer por acidente; o interruptor existe para quem precisa.
- **Conteúdo fora do banco** — auditoria guarda caminho e hash; arquivos de dados podem ter
  dado pessoal (LGPD) e volume.
- **Backup no mesmo diretório** (`.bak-<ts>`) — simples e visível; alternativa de subpasta
  `.orquestra_bak/` fica em aberto no §8.
- **`known_hosts` opcional desde a F1** — `DS_SSH_KNOWN_HOSTS` definida = host key
  desconhecida é recusada (`RejectPolicy`); vazia = `AutoAddPolicy`, paridade com o
  Console. Levar ao Console é melhoria transversal (§8).
- **Raízes de sistema recusadas** (`/etc`, `/root`, `/proc`, `/sys`, `/dev`, `/boot`,
  `/bin`, `/sbin`, `/lib*`, `/usr`, `/run`) — o resto é decisão do admin.
- **`realpath` de cima para baixo** (raiz → cada pasta → arquivo), e não só do caminho
  inteiro: um symlink que sai da raiz é barrado no nível dele, sem revelar se o que vem
  depois existe (403 × 404 seria um oráculo). Raízes também são resolvidas no servidor:
  raiz que é symlink continua valendo.
- **Executor dedicado** (4 threads) com teto de 90 s para o SSH — N leituras presas não
  esgotam o `to_thread` que reconciliação, monitor e execuções compartilham.

## 4. Modelo de dados

Migration **`sql/migrations/105_utilitarios_arquivos.sql`** — idempotente (roda 2× sem
erro; `tests/test_migrations_idempotentes.py` cobre), blocos com `GO`, aplicada pela etapa
**6c** do `deploy.sh` (responder **s**).

```sql
-- 1) Diretórios-raiz (por servidor; desativa, não apaga)
IF OBJECT_ID('dbo.etl_utilitario_raiz','U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_utilitario_raiz (
        id          INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_utilitario_raiz PRIMARY KEY,
        servidor    NVARCHAR(50)   NOT NULL,     -- 'datastage' hoje
        caminho     NVARCHAR(800)  NOT NULL,     -- absoluto, normalizado, sem barra final
                                                 -- (800: (50+800)×2 = 1.700 bytes, o teto da chave única)
        ativo       BIT            NOT NULL CONSTRAINT DF_util_raiz_ativo DEFAULT 1,
        criado_por  NVARCHAR(100)  NOT NULL,
        criado_em   DATETIME2(0)   NOT NULL CONSTRAINT DF_util_raiz_em DEFAULT GETDATE(),
        CONSTRAINT UQ_etl_utilitario_raiz UNIQUE (servidor, caminho)
    );
END
GO

-- 2) Extensões permitidas para gravar (apaga de fato; sem dependentes)
IF OBJECT_ID('dbo.etl_utilitario_extensao','U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_utilitario_extensao (
        extensao    VARCHAR(15)   NOT NULL CONSTRAINT PK_etl_utilitario_extensao PRIMARY KEY, -- minúsculas, sem ponto
        criado_por  NVARCHAR(100) NOT NULL,
        criado_em   DATETIME2(0)  NOT NULL CONSTRAINT DF_util_ext_em DEFAULT GETDATE()
    );
END
GO
-- Semente SÓ quando a tabela está vazia: reexecutar a migration não ressuscita
-- extensão que o admin excluiu.
IF NOT EXISTS (SELECT 1 FROM dbo.etl_utilitario_extensao)
    INSERT INTO dbo.etl_utilitario_extensao (extensao, criado_por) VALUES
        ('txt','migration_105'), ('sql','migration_105'), ('csv','migration_105'),
        ('dat','migration_105'), ('log','migration_105'), ('param','migration_105'),
        ('prm','migration_105'), ('cfg','migration_105'), ('conf','migration_105'),
        ('ini','migration_105'), ('properties','migration_105'), ('json','migration_105'),
        ('xml','migration_105'), ('yaml','migration_105'), ('yml','migration_105');
GO
-- (⚠️ 'sh' fica FORA da semente: gravar script que roda em pipeline é o caso de maior risco —
--  o admin inclui pela tela se quiser. Ver §8.)

-- 3) Auditoria (o conteúdo NUNCA entra aqui)
IF OBJECT_ID('dbo.etl_utilitario_arquivo_log','U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_utilitario_arquivo_log (
        id            BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_utilitario_arquivo_log PRIMARY KEY,
        executado_em  DATETIME2(0)   NOT NULL CONSTRAINT DF_util_arq_log_em DEFAULT GETDATE(),
        usuario       NVARCHAR(100)  NOT NULL,   -- matrícula (get_current_user)
        servidor      NVARCHAR(50)   NOT NULL,
        acao          VARCHAR(10)    NOT NULL,   -- 'ler' | 'listar' | 'gravar'
        caminho       NVARCHAR(1000) NOT NULL,   -- caminho REAL (pós realpath), ou o pedido se negado
        tamanho_bytes BIGINT         NULL,
        sha256        CHAR(64)       NULL,       -- só em 'gravar'
        resultado     VARCHAR(20)    NOT NULL,   -- 'ok' | 'negado' | 'erro'
        detalhe       NVARCHAR(500)  NULL,       -- motivo do negado/erro, backup criado, truncado…
        duracao_ms    INT            NULL
    );
    CREATE INDEX IX_util_arq_log_em      ON dbo.etl_utilitario_arquivo_log (executado_em);
    CREATE INDEX IX_util_arq_log_usuario ON dbo.etl_utilitario_arquivo_log (usuario, executado_em);
END
GO

-- 4) Configuração (MERGE: não sobrescreve valor já editado no Admin)
--   utilitarios_arquivo_max_kb : '2048'
--   utilitarios_arquivo_backup : '1'  (cópia .bak-<ts> antes de sobrescrever)

-- 5) RBAC (MERGE em etl_perfil_permissao, com o mesmo guard da 088 para a tabela existir)
--   ('admin','tela_utilitarios'), ('desenvolvedor','tela_utilitarios'), ('operador','tela_utilitarios')
--   Gravar exige também 'acao_editar' (019: desenvolvedor e admin; operador NÃO tem).
```

Larguras: `caminho` do log NVARCHAR(1000) cobre PATH_MAX (4096 bytes) só parcialmente; a
API recusa caminho > 1000 **unidades UTF-16** (o que NVARCHAR conta — 600 emojis são 610
caracteres Python e 1.210 unidades) com 422 antes de tocar o servidor, e corta o que
audita na mesma medida. A raiz fica em 800 por causa da chave única (1.700 bytes).
`usuario` segue o NVARCHAR(100) de `etl_pipeline_audit.changed_by`. `UQ_etl_utilitario_raiz` usa a colação
padrão (CI) do banco: `/Dados` e `/dados` colidem no cadastro, de propósito — no servidor
são pastas diferentes, mas a API normaliza e o `realpath` decide; duas raízes que só diferem
na caixa seriam armadilha.

Degradação: sem a 105, a API responde 503 "migration 105 pendente" no `/config`, a tela
mostra o aviso e nada quebra no resto do Orquestra.

## 5. Fases

### F1 — Fundação (backend): migration, leitura, cadastro admin e harness de DEV
- Entregável: `GET /utilitarios/config`, `POST /utilitarios/arquivo/ler` e os endpoints
  `/utilitarios/admin/*` funcionando contra o servidor do DataStage, auditados, com a
  permissão e as tabelas no banco; no DEV, um `sshd` de amostra para provar ao vivo.
- Inclui:
  - migration 105 (§4);
  - `api/deps.py`: `require_tela_utilitarios`;
  - `api/services/ssh_arquivos.py`: registro de servidores, funções puras, cliente SFTP
    injetável, leitura com `to_thread`;
  - `api/routers/utilitarios.py` (`/config`, `/arquivo/ler`, `/admin/raizes` CRUD + testar,
    `/admin/extensoes`, `/admin/config`) + registro em `main.py`;
  - auditoria em `etl_utilitario_arquivo_log` (ok / negado / erro);
  - **harness**: serviço `sshd-amostra` em `docker-compose.dev.yaml` (imagem
    `linuxserver/openssh-server` ou equivalente já presente na VPS, sem porta publicada —
    só na rede do compose), volume `dev/sshd-amostra/` com: duas raízes (`/dados/bi` e
    `/dados/param`) com subpastas, texto UTF-8, texto Latin-1 com acentos, arquivo > teto,
    binário, arquivo oculto, symlink apontando para fora da raiz, e uma pasta fora das
    raízes; `.env.dev` ganha `DS_SSH_*` apontando para ele (o Console DataStage do DEV
    continua degradado, porque não há `dsjob` lá — esperado); `docs/ambiente-dev.md`
    ganha a seção;
  - testes `tests/test_utilitarios_arquivos.py`: funções puras (traversal `..`, nome com
    `/`, symlink fora da raiz, prefixo `/dados2` × `/dados`, Latin-1, binário,
    `ultimas_linhas` em borda de linha, normalização de diretório com `//` e `/./`), router
    com fake SFTP (200/403/404/413/415/503, auditoria gravada em cada saída, raiz inativa
    não libera), CRUD admin (422 caminho relativo, 409 repetido, extensão fora da regex,
    perfil não-admin → 403), permissão da tela (consulta → 403; operador → 200 em ler).
- Critérios de aceite:
  - dado raiz ativa `/dados/bi`, quando pedir `/dados/bi/../../etc/passwd`, então 403 e
    linha `negado` na auditoria com o caminho pedido;
  - dado symlink `/dados/bi/link → /etc`, quando pedir `/dados/bi/link/passwd`, então 403
    (o `realpath` sai da raiz);
  - dado raiz `/dados/bi` **desativada**, quando ler um arquivo dela, então 403;
  - dado arquivo Latin-1 com "ação", quando ler sem `codificacao`, então `conteudo`
    exibe "ação" e `codificacao = 'latin-1'`;
  - dado arquivo de 5 MB e teto de 2 MB, quando ler sem `ultimas_linhas`, então 413; com
    `ultimas_linhas = 200`, então 200, `truncado = true`, 200 linhas inteiras;
  - dado `DS_SSH_HOST` vazio, quando chamar `/config`, então `servidores[0].configurado =
    false` e `/arquivo/ler` responde 503;
  - migration 105 roda 2× no SQL Server do DEV sem erro e, na 2ª vez, não recria as
    extensões apagadas;
  - no DEV, `curl` autenticado cadastra uma raiz, testa (`existe = true`) e lê o arquivo de
    amostra pelo `sshd-amostra`.
- Validação: `python -m pytest tests -q` contra baseline do HEAD (zero falhas novas; as 5
  pré-existentes ficam) + migration 2× no DEV + prova viva por `curl`. Sem front nesta
  fase.
- Revisão adversarial multi-agente antes da PR. PR: `feat(utilitarios): F1 — ler arquivo do servidor do DataStage pela API, cadastro de raízes e extensões, auditoria e harness de dev`.

### F2 — Admin › aba Utilitários
- Entregável: o admin cadastra raízes e extensões pela tela, sem SQL.
- Inclui: aba `Utilitários` no grupo Sistema do `Admin.tsx` (padrão do `ConexoesTab`),
  card Diretórios-raiz (tabela, incluir, desativar/reativar, testar), card Extensões
  (chips, incluir, excluir com confirmação), teto e backup; queries TanStack
  `['utilitarios-admin-raizes']`, `['utilitarios-admin-extensoes']`; `npm run build`
  commitado.
- Critérios de aceite:
  - incluir `/dados/bi` e `/dados/param` no servidor `datastage` → aparecem na tabela com
    quem/quando; **Testar** diz "existe e é legível" no DEV;
  - incluir `dados/x` (relativo) → 422 com mensagem no campo; repetido → 409 "já cadastrada";
  - desativar uma raiz → ela fica cinza na tabela e some do `/config`;
  - excluir a extensão `csv` → some dos chips e do `/config`; incluir `SH` → é gravada como
    `sh`; incluir `a.b` → 422;
  - tudo legível nos dois temas.
- Validação: `npx tsc -b` (⚠️ `tsc --noEmit` não checa nada neste template) + `eslint`
  contra baseline + `npm run build` + `pytest` + prova visual no DEV (`dist/` é volume:
  aparece na hora).
- Revisão adversarial multi-agente antes da PR. PR: `feat(utilitarios): F2 — aba Utilitários no Admin para cadastrar diretórios-raiz e extensões`.

### F3 — Tela Utilitários + aba Ver arquivo
- Entregável: menu **Utilitários** visível para quem tem o recurso, aba **Ver arquivo**
  completa, modal de execução com Copiar.
- Inclui: os 4 lugares da tela (nav, rota, `RBAC_RECURSOS`; a migration já veio na F1);
  `pages/Utilitarios.tsx`, `CampoPasta` (ainda sem Navegar…, que é F6), `FormVerArquivo`,
  `ModalConteudoArquivo`, `erros.ts`; a aba Criar/editar **ausente** até a F5 (mais honesto
  que "em breve"); banner quando não há raiz ativa ("Nenhum diretório liberado — Admin ›
  Utilitários") e quando o servidor não está configurado; botão Copiar com os três
  desfechos do `copiarTexto`; `npm run build` commitado.
- Critérios de aceite:
  - perfil `consulta` não vê o item no menu e recebe 403 ao abrir `/utilitarios` direto;
    `operador` vê e lê;
  - dado pasta e nome válidos, quando clicar Iniciar, então o modal abre já em
    "conectando", passa por "lendo" e mostra o conteúdo inteiro com rolagem interna (o
    corpo da página não rola na horizontal);
  - pasta digitada fora das raízes → o `CampoPasta` já avisa em vermelho antes do clique, e
    a API confirma com 403 se insistir;
  - clicar em Copiar conteúdo em HTTP (DEV pelo IP) copia pelo caminho legado e o botão
    diz "copiado"; falhando, diz "selecionado — use Ctrl+C";
  - 413 mostra "arquivo de X MB acima do teto de Y MB" e oferece o campo "últimas N
    linhas" sem fechar o modal;
  - modo escuro: bloco de conteúdo legível (fundo fixo escuro é a exceção documentada),
    resto da tela só com tokens;
  - Esc fecha o modal; foco volta ao botão Iniciar.
- Validação: `tsc -b` + `eslint` baseline + `npm run build` + `pytest` (o anti-drift do
  RBAC passa a exigir a entrada nova) + prova visual no DEV.
- Revisão adversarial multi-agente antes da PR (inclui CSS: especificidade, `overflow`,
  comentário com `*/`). PR: `feat(utilitarios): F3 — tela Utilitários com a aba Ver arquivo e o modal de conteúdo`.

### F4 — Gravação (backend)
- Entregável: `POST /utilitarios/arquivo/gravar` com todas as guardas.
- Inclui: extensão na lista cadastrada, teto, 409 sem `sobrescrever`, backup `.bak-<ts>`,
  escrita atômica (tmp + rename), `sha256`, normalização CRLF→LF e `\n` final, codificação
  pedida (UTF-8 | Latin-1; caractere fora do Latin-1 → 422 nomeando a posição), auditoria
  com hash; permissão `tela_utilitarios` + `PERM_EDITAR`; testes com fake SFTP (criação,
  sobrescrita com e sem backup, 409, extensão fora da lista, `.tmp` limpo em falha de
  `rename`, diretório inexistente → 404 sem criar pasta, gravar fora da raiz → 403).
- Critérios de aceite:
  - dado extensões `txt,sql`, quando gravar `x.sh`, então 422 "extensão sh não liberada";
  - dado arquivo existente, quando gravar sem `sobrescrever`, então 409 com tamanho e data
    do atual e nada muda no servidor;
  - com `sobrescrever = true` e backup ligado, então existe `x.txt.bak-<ts>` byte-idêntico
    ao anterior e `x.txt` tem o conteúdo novo;
  - falha no `rename` deixa o arquivo original intacto e nenhum `.tmp` para trás;
  - operador (tem a tela, não tem `acao_editar`) → 403.
- Validação: `pytest` contra baseline + prova viva no DEV pelo `curl` (arquivo aparece no
  volume do `sshd-amostra` com LF e `\n` final).
- Revisão adversarial multi-agente antes da PR. PR: `feat(utilitarios): F4 — gravar arquivo no servidor com confirmação, backup e escrita atômica`.

### F5 — Aba Criar/editar arquivo (UI)
- Entregável: a segunda aba completa, com o modal de gravação.
- Inclui: `FormEditarArquivo` (editor mono com contador, extensão da lista do `/config`,
  codificação), **Carregar existente** (reusa `/arquivo/ler` com o nome+extensão do
  formulário e ajusta a codificação para a detectada), `ModalGravacaoArquivo` com o fluxo
  do 409 (confirmação Sobrescrever mostrando o que será substituído), resultado com atalho
  Ver arquivo (abre o `ModalConteudoArquivo` do que acabou de gravar), aviso de
  "alterações não gravadas" ao trocar de aba; para quem não tem `pode_gravar` (operador),
  a aba mostra o editor desabilitado com a explicação; lista de extensões vazia → aviso
  apontando o Admin; `npm run build` commitado.
- Critérios de aceite:
  - dado texto com CRLF colado do Windows, quando gravar, então o arquivo no servidor tem
    LF (verificado por `od -c` no DEV);
  - Carregar existente de arquivo Latin-1 preenche o editor com acentos corretos e a
    codificação muda sozinha para Latin-1; gravar de volta mantém os bytes dos acentos;
  - operador vê a aba com o editor desabilitado e a explicação, não um 403 surpresa;
  - Ctrl+Enter grava (mesmo gesto do editor de fluxo); Esc fecha o modal sem gravar.
- Validação: `tsc -b` + `eslint` baseline + `npm run build` + `pytest` + prova visual no
  DEV nos dois temas.
- Revisão adversarial multi-agente antes da PR. PR: `feat(utilitarios): F5 — aba Criar/editar arquivo com carregar, confirmar sobrescrita e resultado`.

### F6 — Navegador de pastas
- Entregável: botão **Navegar…** nas duas abas, descendo das raízes até a pasta desejada.
- Inclui: `GET /utilitarios/pasta/listar` (guarda das raízes, ocultos, limite de 2.000,
  links só seguidos dentro da raiz, auditoria `listar`), `NavegadorPastas.tsx` (lista de
  raízes quando há mais de uma, breadcrumb, pastas primeiro, tamanho e data, teclado:
  Enter desce, Backspace sobe, nunca acima da raiz, **Usar esta pasta**, clique em arquivo
  preenche nome e, na aba de edição, extensão), `CampoPasta` ganha o botão; testes de
  listagem (ordem, ocultos, truncado, raiz inativa, symlink para fora aparece como `link`
  mas não desce); `npm run build` commitado.
- Como ficou: o navegador vive DENTRO de cada formulário (hook
  `components/utilitarios/useNavegadorPastas.ts`: abrir, descer, subir, ocultos, número
  de série contra resposta atrasada, pasta digitada inválida → erro na tela + volta às
  raízes); a página só passa `onListar` (o `apiFetch` de `GET /utilitarios/pasta/listar`).
  Assim os formulários continuam apresentação pura e a bancada de node prova o fluxo
  inteiro (Navegar… → raiz → pasta → arquivo → campos preenchidos) sem rede. Links só
  ganham `alvo` (e só descem) quando apontam para dentro das raízes; o servidor resolve
  no máximo 200 links por listagem, na ordem da tela (os demais ficam "não verificados" e
  o clique tenta); no máximo 20 mil entradas brutas são lidas (`truncado`).
- **A resposta da listagem é LEXICAL**: `caminho`, `raiz` e `pai` são o que o usuário
  pediu (normalizado), e é por eles que o navegador desce, sobe e preenche os campos —
  o `ler`/`gravar` conferem lexicalmente, e com raiz que é symlink o caminho real cairia
  fora (403 falso, achado das duas revisões da F6). `caminho_real` vai junto, como nota
  ("→ /u01/…") na trilha. O Modal da casa renderiza DENTRO do `<form>` do formulário:
  todo botão do navegador é `type="button"` e Enter no filtro é prevenido — senão Fechar
  disparava uma leitura (Iniciar) na aba Ver arquivo.
- Critérios de aceite:
  - dado duas raízes ativas, quando abrir Navegar…, então a primeira tela lista as duas e
    nada mais; com uma só, abre direto nela;
  - dentro de `/dados/bi/2026`, Backspace volta a `/dados/bi`; em `/dados/bi`, Backspace
    não faz nada (não sobe para `/dados`);
  - arquivo oculto não aparece; com "mostrar ocultos" aparece; o symlink para `/etc`
    aparece como `link` e o clique nele responde 403;
  - pasta com 3.000 entradas mostra 2.000 e o aviso "lista truncada";
  - clique em `carga.txt` na aba de edição preenche nome `carga` e extensão `txt`;
    extensão não cadastrada preenche o nome e avisa que não poderá gravar com ela.
- Validação: `tsc -b` + `eslint` baseline + `npm run build` + `pytest` + prova visual no
  DEV com as duas raízes do harness.
- Revisão adversarial multi-agente antes da PR. PR: `feat(utilitarios): F6 — navegador de pastas abaixo das raízes cadastradas`.

### F7 — Polimento, manual e smoke
- Entregável: feature fechada e documentada.
- Inclui: seção "Utilitários" em `docs/MANUAL_USUARIO.md` (perfis Operador, Desenvolvedor e
  Administrador — este com o cadastro de raízes e extensões), release note em
  `docs/release-notes/utilitarios-arquivos.md`, `/simplify` nos arquivos novos, revisão de
  acessibilidade (rótulos, foco, contraste dos estados do modal, teclado do navegador),
  registro no backlog (`.claude/skills/backlog`) dos itens do §8 que não entraram, e o
  roteiro de smoke do §7 executado no DEV com o resultado colado na PR.
- Critérios de aceite: manual descreve os fluxos com as mensagens de erro reais; smoke
  a–p do §7 com resultado registrado (DEV) e pronto para produção.
- Validação: suíte completa + build + `/code-review` do conjunto F1–F6.
- Revisão adversarial única de fecho (além das por fase). PR: `docs(utilitarios): F7 — manual, release note e smoke`.

## 6. Riscos e mitigações

| # | Risco | Impacto | Mitigação |
|---|-------|---------|-----------|
| 1 | Exposição de arquivo sensível (senha em `.param`/`.cfg`, chave, dado pessoal em arquivo de carga) abaixo de uma raiz larga demais | Vazamento; LGPD | Nenhuma raiz vem de fábrica; o admin cadastra e o botão Testar mostra o que abriu; auditoria com caminho real e usuário; ocultos escondidos por padrão; conteúdo nunca vai ao banco |
| 2 | Escape de caminho por `..`, `//`, symlink, nome com `/` ou prefixo enganoso (`/dados2` sob `/dados`) | Leitura ou gravação fora da raiz | Validação pura antes do SSH + `realpath` **no servidor** (`sftp.normalize`) conferido por componente contra as raízes ativas; navegador segue link só se o destino ficar dentro; testes para cada forma |
| 3 | Sobrescrever script que um job shell está usando (F4) | Job quebra ou roda meia versão | 409 sem `sobrescrever`, backup `.bak-<ts>`, escrita atômica por `rename`, `sh` fora da semente de extensões (o admin liga conscientemente) |
| 4 | Arquivo grande ou pasta gigante trava a API (paramiko é bloqueante) | Orquestra inteiro lento | `stat` antes do `read`, teto por config, `ultimas_linhas` lê só o fim, listagem limitada a 2.000, `asyncio.to_thread`, timeouts de canal |
| 5 | Codificação: servidor em Latin-1, tela em UTF-8 | Acento quebrado ao ler; arquivo corrompido ao gravar | Detecção UTF-8 estrito → Latin-1 na leitura, codificação exibida; na gravação a codificação é escolhida e o "Carregar existente" a herda; caractere fora do Latin-1 é recusado com posição |
| 6 | Botão Copiar não funciona em produção (HTTP) | Usuário cola conteúdo velho e manda para alguém | `lib/copiar.ts` com caminho legado e os três desfechos visíveis no botão |
| 7 | DEV sem servidor DataStage: mecânica provada, mas caminhos, permissões do usuário SSH e codificação reais só em produção | Smoke de prod pode achar diferença | Harness `sshd-amostra` reproduz duas raízes, Latin-1, symlink, oculto, binário e teto; smoke §7 tem itens marcados "só prod" |
| 8 | Reexecução da migration ressuscita extensão excluída pelo admin | Extensão perigosa volta sem ninguém pedir | Semente só quando a tabela está vazia (critério de aceite da F1 testa a 2ª execução) |
| 9 | Permissão nova não aparece (relogin) ou não tem interruptor (RBAC_RECURSOS) | Tela invisível para quem deveria ver | Migration semeia admin+desenvolvedor+operador; smoke começa por relogin; teste anti-drift prende `NAV` × `RBAC_RECURSOS` |
| 10 | Deploy: migration 105 na 6c; `config/` do nginx de prod está à frente do repo | Tela sem permissão no banco; nginx regredido | Responder **s** na 6c e **n** em `config/`; sem `dags/` nesta spec; sem dependência Python nova (paramiko já está em `api/wheels/`) |
| 11 | `AutoAddPolicy` aceita qualquer host key (paridade com o Console) | MITM na rede interna | Registrado como melhoria transversal no §8 (`known_hosts` fixo para Console e Utilitários) |

## 7. Smoke pós-deploy

> **Script**: `scripts/smoke_utilitarios.sh` executa pela API tudo que não exige o
> navegador (c, d, e, g, h, i, j, k, l, m, o, p) e compara com o servidor quando tem
> acesso a ele (`wc -lc`, `cat`, `od`, `.bak`). Uso em produção: `ORQ_URL`, `ORQ_USER`,
> `ORQ_PASS`, `RAIZ`, `PASTA`, `ARQ`, `LATIN1` no ambiente. **Resultado no DEV
> (2026-09-03, F7): 37 conferências ok, 0 falhas**; a, b, f, n e a parte visual de j são
> manuais (marcados "UI" na saída).

a) Sair e entrar de novo (permissão vive no `localStorage`). Com `admin`, `desenvolvedor` e
   `operador`, o menu Operação mostra **Utilitários**; com `consulta`, não mostra e
   `/utilitarios` direto dá "sem permissão".
b) Admin › Perfis e Permissões: o checkbox **Utilitários** existe e está marcado para os
   três perfis.
c) Admin › Utilitários: antes de cadastrar, a tela Utilitários mostra "nenhum diretório
   liberado". Cadastrar as raízes de produção (decisão do §8) e clicar **Testar** em cada
   uma → "existe e é legível". Cadastrar uma raiz relativa → recusada.
d) Admin › Utilitários › Extensões: excluir `yml`, incluir de volta; conferir que `sh` não
   está na lista (e decidir se entra).
e) Ver arquivo: um arquivo pequeno conhecido (ex.: um `.param` de projeto) → o modal passa
   por conectando/lendo e o conteúdo é idêntico ao `cat` no servidor (conferir linhas e
   tamanho do rodapé com `wc -lc`).
f) Copiar conteúdo → colar no Bloco de Notas: texto inteiro, sem perda de acento. O botão
   disse "copiado".
g) Arquivo com acento gravado em Latin-1 (só prod) → acentos corretos e rodapé
   "codificação: latin-1".
h) Caminho fora das raízes (ex.: `/etc/passwd` e `<raiz>/../etc/passwd`) → o campo Pasta
   avisa em vermelho e, insistindo, "fora dos diretórios liberados"; `SELECT TOP 5 * FROM
   dbo.etl_utilitario_arquivo_log ORDER BY id DESC` mostra `negado` com o caminho pedido e a
   matrícula.
i) Arquivo maior que o teto (um log grande) → mensagem com os tamanhos e o campo "últimas N
   linhas"; com 200, mostra as 200 últimas linhas inteiras e `truncado`.
j) Navegar…: com duas raízes, a primeira tela lista as duas; descer três níveis, Backspace
   sobe, na raiz não sobe mais; ocultos não aparecem; "Usar esta pasta" preenche o campo;
   clique num arquivo preenche o nome.
k) Criar arquivo novo `smoke_orquestra.txt` numa pasta abaixo da raiz → resultado com
   caminho, bytes e hash; no servidor, `cat` mostra o conteúdo, `od -c | tail` termina em
   `\n`, sem `\r`.
l) Gravar de novo no mesmo nome sem marcar Sobrescrever → 409 com tamanho e data do atual;
   marcar Sobrescrever → `smoke_orquestra.txt.bak-<ts>` existe com o conteúdo anterior e o
   arquivo tem o novo. Apagar os dois no servidor ao final.
m) Extensão fora da lista (ex.: `exe`) nem aparece no select; excluir `txt` no Admin e tentar
   gravar `.txt` pela API → recusa nomeando a extensão. Incluir `txt` de volta.
n) Com `operador`: lê e navega; a aba Criar/editar mostra o editor desabilitado com a
   explicação; `POST /utilitarios/arquivo/gravar` direto → 403.
o) Carregar existente do arquivo Latin-1 do item g, alterar uma linha sem acento, gravar →
   os acentos das outras linhas continuam corretos no `cat` (só prod).
p) Auditoria: as leituras, listagens e gravações do smoke aparecem em
   `etl_utilitario_arquivo_log` com `ok`, `negado` e os hashes; nenhuma linha contém
   conteúdo de arquivo.

## 8. Pendências e decisões em aberto

Resolvidas pelo usuário em 2026-09-03: raízes múltiplas cadastradas pelo admin com
navegação abaixo delas; extensões cadastradas no Admin com incluir/excluir; operador lê,
desenvolvedor e admin gravam; navegador de pastas entra como fase (F6); menu **Utilitários**.

Ainda em aberto:
1. **Raízes de produção**: quais diretórios do servidor do DataStage entram no cadastro
   inicial? Podem ser cadastrados pelo admin depois do deploy (item c do smoke); a spec não
   precisa saber.
2. **`sh` na lista de extensões?** A semente deixa de fora; o admin inclui pela tela se
   quiser gravar scripts. Confirmar que é assim que prefere.
3. **Extensões valem só para gravar** (assunção desta spec). Se quiser que a leitura também
   respeite a lista, arquivos sem extensão (comuns no Unix) deixam de abrir. Inverter é uma
   linha no serviço.
4. **Backup ao sobrescrever**: `.bak-<ts>` no mesmo diretório (visível, pode acumular) ou
   subpasta `.orquestra_bak/` (limpo, invisível)? Proposta: mesmo diretório, com o
   interruptor no Admin para desligar.
5. **Mais servidores (futuro)**: quando chegar, qual caminho — `etl_conexao` tipo `ssh`
   (senha cifrada, lida pela API e pelo worker) ou RPC via DAG? A primeira é mais simples e
   reaproveita a aba Conexões do Admin. Decidir só quando o pedido vier.
6. **`known_hosts`**: nos Utilitários já existe (`DS_SSH_KNOWN_HOSTS`, opcional); levar ao
   Console DataStage é backlog transversal. Em produção, **definir** a variável (fecha o
   MITM na intranet com a senha da conta de serviço).
7. **Expurgo de `etl_utilitario_arquivo_log`** (achado da auditoria de segurança da F1):
   nada apaga o log; o `etl_log_cleanup` só cuida de `.log` em disco. Propor purga por
   idade (ex.: 365 dias) numa fase de polimento ou como item do backlog.
8. **Retenção do que a F1 ainda não cobre**, registrado pela revisão adversarial: o
   `open` no caminho real ainda segue symlink criado ENTRE o `realpath` e o `open`
   (TOCTOU) — exige shell no servidor, sem ganho de privilégio; residual aceito. Na
   gravação (F4) o mesmo residual tem impacto maior (escrita), com a mesma barreira.
9. **Raiz de leitura × raiz de escrita** (auditoria de segurança da F4): hoje toda raiz
   ativa vale para ler E gravar, e a semente de extensões inclui `param`/`cfg`/`conf`/
   `properties` — quem tem `acao_editar` pode sobrescrever um `.param` de projeto DataStage
   (credencial de banco) se a raiz o alcançar. **Decisão operacional para produção: não
   cadastrar diretórios de projeto com `.param` de credencial como raiz**, ou tratá-los só
   em leitura. Separar raiz de leitura e de escrita (uma coluna `permite_gravar` +
   interruptor no Admin) fica como melhoria — barata, decidir antes ou depois da F5.
10. **`.bak` sem expurgo no servidor** (F4): cada sobrescrita com backup deixa um
    `.bak-<ts>-<ms>` que nada apaga — disco do DS e cópias de dado pessoal acumulando.
    Purga por idade (ou subpasta `.orquestra_bak/` com limpeza) antes de liberar a gravação
    em volume. Junto com o item 7.
11. **413 cedo**: o teto é aplicado depois de ler o corpo inteiro (o nginx aceita 64 MB); um
    `Content-Length` acima do teto poderia ser recusado antes de ler. Backlog.
12. **Fila do executor sem teto** (auditoria da F6): as 4 threads dos Utilitários (por
    worker) atendem ler/gravar/listar/testar; 8 listagens de 50 mil entradas em paralelo
    fizeram uma listagem pequena esperar ~10 s (o resto da API não sofre — o executor é
    dedicado). Teto na fila com 503 "ocupado" ou semáforo por usuário. Backlog; o corte de
    20 mil entradas brutas (`LISTAGEM_BRUTA_MAX`) já limita o pior caso.
13. **Oráculo residual para quem PLANTA o link** (auditoria da F6): link para
    `/naoexiste/x` responde 404 e link para `/etc/naoexiste` responde 403, porque o
    `realpath` do OpenSSH tolera só o último componente ausente — revela se a pasta-mãe do
    alvo existe. Só quem cria o link (shell no servidor) escolhe o alvo, e esse já lê o
    servidor direto. Fechável mapeando o 404 num componente-link para 403 (um `lstat` por
    nível); não vale o custo agora.
14. **Nomes que o editor não representa** (revisão da F6): a aba Criar/editar só sabe pedir
    `nome.extensão` em minúscula (a lista de extensões é minúscula e o servidor distingue
    caixa). `RELATORIO.TXT`, `README` (sem extensão) e nomes com espaço nas pontas não podem
    ser carregados nem gravados por ela — o navegador preenche só a pasta e avisa; a aba Ver
    arquivo lê qualquer nome. Suportar nome completo no editor (campo único + extensão
    inferida) fica como melhoria.
15. **Raiz cadastrada que aponta para pasta do sistema** (auditoria da F6, corrigido): a
    régua `RAIZES_PROIBIDAS` vale para o caminho REAL — raiz que no servidor é link para
    `/etc` não lista, não lê, não grava, e o Testar do Admin diz "pasta do sistema — esta
    raiz NÃO vale". Quem escreve na pasta-mãe de uma raiz (ou uma raiz cadastrada e ausente
    no servidor) não transforma mais a conta SSH da API em leitor de `/etc`.
