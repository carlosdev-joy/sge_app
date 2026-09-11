# Spec: E-mail — prévia na tela, modelos institucionais e seletor de anexo — Orquestra
Data: 2026-09-11 · Status: 🏁 **CONCLUÍDA 2026-09-11** — F1 #393 · F2 #394 · F3 #395 · F4 (esta PR)
⏳ Deploy em produção **pendente**: roteiro e conferência em `docs/release-notes/email-modelos.md`.

Continuação de `docs/spec-notificacao-email.md` (concluída, F1–F4 = PRs #388–#391).
Aquela entregou o canal; esta trata de **como as pessoas escrevem o aviso**.

## 1. Visão
Hoje quem monta um nó de e-mail digita HTML às cegas: não vê como fica, não tem
de onde partir, e digita o caminho do anexo de memória. O resultado previsível é
cada fluxo com um aviso diferente, e o layout institucional existindo só no
documento de quem o desenhou. Esta spec dá **prévia na própria tela**, um
**catálogo de modelos** mantido pelo administrador, e **navegação de pastas** no
anexo, igual à dos Utilitários. Quando estiver pronto, o caminho comum é escolher
um modelo, ver o resultado e clicar no arquivo — sem escrever HTML.

## 2. Escopo
**IN:**
- **Prévia do corpo** renderizada na tela, alternando entre os marcadores e
  valores de exemplo. Na F1 ela entra no **painel do nó** (Etapas e Fluxos), que
  é onde existe corpo editável; em Admin › E-mail ela chega na F2, ao lado do
  editor de modelos — hoje aquela tela não tem corpo para pré-visualizar (o
  e-mail de teste é montado pelo servidor).
- **Catálogo de modelos** (`etl_email_modelo`): CRUD em Admin › E-mail, com o
  modelo institucional já semeado pela migration.
- **Vínculo vivo**: o nó referencia o modelo; o corpo é lido no envio. Trocar o
  layout no Admin vale para todos os nós, sem republicar nem reeditar.
- **Padronização por lista (decisão do usuário, 2026-09-11): "exigido com
  escape".** O corpo do nó deixa de ser um campo livre e passa a ser **escolhido
  numa lista** — os modelos ativos do catálogo, mais a opção **Corpo livre**,
  para quem precisar fugir do padrão. A escolha fica visível no nó, então sair do
  padrão é uma decisão consciente, não o caminho de menor esforço.
- **Interruptor de padronização** em Admin › E-mail: *exigir modelo do catálogo*.
  Ligado, ele **remove a opção Corpo livre** da lista — o nível "travado", para
  quando a operação quiser endurecer. Desligado por padrão.
- **Seletor de arquivo do anexo**: navegação pelas pastas liberadas do e-mail,
  reusando o `NavegadorPastas` dos Utilitários, com endpoint próprio.
- **Sugestão de marcador de data**: ao escolher um arquivo cujo nome contenha uma
  data, o campo oferece trocá-la por `{odate}`.
- Manual, release note e smoke.

**OUT (explícito):**
- **Editor visual de HTML** (arrastar blocos, escolher cores). O administrador
  edita o HTML do modelo com a prévia ao lado; quem monta o fluxo escolhe da
  lista. Um construtor de layout é produto próprio.
- **Modelos para o card do Teams**: o catálogo `etl_msg_template` já existe e é
  outra tabela. Unificar os dois é spec própria — e o precedente pesa contra
  (ver §8).
- **Anexar mais de um arquivo** e **anexo por upload do navegador**: o anexo
  continua sendo um arquivo do servidor.
- **Navegador de pastas para as raízes do Admin** (cadastrar raiz navegando).
  Continua textarea.
- **Prévia do e-mail com o anexo renderizado** (miniatura do arquivo).

## 3. Arquitetura proposta

**Prévia — `components/etapas/PreviaEmail.tsx` (novo)**
`<iframe sandbox srcdoc={corpo}>`, sem `allow-scripts` e sem
`allow-same-origin`. Seria o **primeiro iframe do produto** (hoje não há nenhum),
e é a escolha certa por dois motivos: isola o HTML de terceiro do aplicativo, e
impede que o CSS do Orquestra vaze para dentro da prévia — o que a tornaria
mentirosa justamente no que ela promete mostrar.

Alternativas descartadas: `dangerouslySetInnerHTML` (o produto só o usa com
markdown gerado por allowlist, `lib/markdown.ts`, onde `& < >` são escapados na
ENTRADA — o oposto deste caso); biblioteca de sanitização (não há nenhuma no
`package.json`; `dompurify` existe só como dependência transitiva do `jspdf`, e
depender disso é frágil).

**Catálogo — `api/routers/email.py`**
- `GET /email/modelos` (`get_current_user`) — ativos, para o painel do nó.
- `GET/POST /email/admin/modelos`, `PUT/DELETE /email/admin/modelos/{id}`
  (`get_admin_user`), no mesmo molde de `/email/admin/config`.
- **Apagar recusa quando há nó usando** (409 nomeando os pipelines), como as
  raízes dos Utilitários, que se desativam e não se apagam. Desativar é sempre
  permitido e não afeta quem já usa — só some da lista de escolha.

**Vínculo vivo — `dags/utils/email_operator.py`**
O nó passa a guardar `modelo_id` em `notify_json`. No `execute`, o operador lê o
modelo junto com o resto (uma consulta a mais) e usa `corpo`/`html` dele; os
campos do nó (destinatários, anexo, assunto) seguem como estão. Sem `modelo_id`,
usa o corpo do próprio nó, como hoje.

⚠️ **O defeito que NÃO vamos repetir:** no catálogo do Teams, template apagado ou
desativado faz o envio cair em silêncio para a mensagem embutida
(`etl_dag_factory.py`, `WHERE id=%s AND ativo=1` sem tratar o vazio). Aqui, nó que
referencia modelo inexistente **falha com mensagem clara**, e a régua do cadastro
recusa apagar modelo em uso.

**Navegação do anexo**
- `GET /email/anexo/listar?caminho=` em `routers/email.py`, reusando
  `services/ssh_arquivos.preparar_pasta` e `listar_pasta` — os mesmos que os
  Utilitários usam, com toda a defesa contra escape de raiz por symlink
  (`resolver_real` confere nível a nível). O que muda é **de onde vêm as raízes**
  (`email_anexo_raizes` de `etl_app_config`, não `etl_utilitario_raiz`) e **a
  permissão** (quem edita pipeline, não `tela_utilitarios`).
- Front: reusa `components/utilitarios/NavegadorPastas.tsx` (apresentação pura,
  recebe a rede por prop) e o hook `useNavegadorPastas.ts`, passando um
  `listarPasta` que chama o endpoint do e-mail. Sem fork, sem cópia.

**Decisões e alternativas descartadas**
- *Vínculo vivo em vez de cópia*: copiar o HTML para cada nó deixaria dez cópias
  do mesmo layout para manter, e o modelo já ocupa 24% do limite de corpo.
- *Endpoint próprio em vez de parâmetro no dos Utilitários*: acoplar os dois
  misturaria permissões e as duas listas de raízes.
- *Prévia server-side (renderizar no backend e devolver imagem)*: exigiria
  navegador headless no servidor air-gapped.

## 4. Modelo de dados

`sql/migrations/112_email_modelos.sql` (idempotente, etapa 6c do `deploy.sh`):

```sql
CREATE TABLE dbo.etl_email_modelo (
  id          INT IDENTITY PRIMARY KEY,
  nome        NVARCHAR(120)  NOT NULL,     -- "Aviso de fim de carga"
  descricao   NVARCHAR(400)  NULL,         -- quando usar
  assunto     NVARCHAR(500)  NULL,         -- sugestão; o nó pode ter o seu
  corpo       NVARCHAR(MAX)  NOT NULL,     -- o HTML, com marcadores
  html        BIT            NOT NULL DEFAULT 1,
  ativo       BIT            NOT NULL DEFAULT 1,
  padrao      BIT            NOT NULL DEFAULT 0,   -- pré-selecionado no nó novo
  criado_por  NVARCHAR(100)  NULL,
  criado_em   DATETIME2(0)   NOT NULL DEFAULT GETDATE(),
  atualizado_em DATETIME2(0) NULL
);
-- UNIQUE em nome (o catálogo do Teams não tem, e nomes repetidos confundem
-- justamente na lista de escolha)
CREATE UNIQUE INDEX ux_etl_email_modelo_nome ON dbo.etl_email_modelo (nome);
```

Guarda de `padrao`: no máximo um ativo por vez — o `POST`/`PUT` zera os demais na
mesma transação (não há índice filtrado, pelo gotcha de `QUOTED_IDENTIFIER` com
`sqlcmd` já registrado no repo).

Semente na própria migration: o modelo institucional validado em 11/09/2026
(cabeçalho com o gradiente da tela de entrada, tarja laranja, tabela de dados),
com `padrao = 1`.

Chave nova em `etl_app_config`: `email_exigir_modelo` (`'0'` por padrão).
Nada muda em `etl_pipeline_job`: `modelo_id` entra no JSON de `notify_json`.

## 5. Fases

### F1 — Prévia do corpo na tela
- Entregável: ver o e-mail enquanto se escreve, no **painel do nó**. No Admin
  a prévia chega na F2, junto do editor de modelos — ver §2.
- Inclui: `PreviaEmail.tsx` com iframe isolado; `previaEmailDados.ts` com os
  valores de exemplo espelhando o que o operador resolve; alternância marcadores
  × valores; a prévia no `PainelEmail` (dock); aviso de **marcador desconhecido**
  no painel (erro de digitação que hoje só apareceria na caixa de quem recebeu);
  bancada do front para as partes puras.
- Critérios de aceite: dado um corpo com marcadores, quando se liga *valores de
  exemplo*, então a prévia mostra o texto resolvido; dado HTML com `<script>`,
  então ele **não** executa (iframe sem `allow-scripts`); dado corpo vazio, então
  a prévia mostra um estado vazio, não um quadro branco sem explicação.
- Validação: tsc + eslint (baseline HEAD) + build + pytest. Revisão adversarial.
  PR: `feat(email): prévia do corpo na tela (F1)`.
- ✅ **ENTREGUE — PR #393 `35bbe2f`** (2026-09-11).

### F2 — Catálogo de modelos
- Entregável: administrador cadastra modelos; quem monta o fluxo escolhe um.
- Inclui: migration 112 com a semente; CRUD no router; seção **Modelos** em
  Admin › E-mail (lista, criar, editar com a prévia da F1 ao lado, ativar,
  definir padrão, excluir com a trava de uso); `Select` de modelo no painel do
  nó; interruptor *exigir modelo do catálogo*; leitura do modelo no
  `EmailOperator`; testes (régua, trava de exclusão, operador com e sem modelo,
  modelo inexistente → falha clara).
- Critérios de aceite: dado um nó com modelo escolhido, quando o administrador
  edita o HTML do modelo, então a próxima corrida usa o novo **sem republicar**;
  dado um modelo em uso, quando se tenta excluir, então a API recusa nomeando os
  pipelines; dado modelo desativado, quem já o usa continua enviando; dado
  `email_exigir_modelo` ligado, então a opção **Corpo livre** some da lista;
  dado um nó que já existia antes da F2, então ele aparece como **Corpo livre**
  com o corpo intacto e envia exatamente o que enviava.
- Validação: completa. Revisão adversarial.
  PR: `feat(email): catálogo de modelos institucionais (F2)`.
- 🔧 **EM REVISÃO** — implementada; duas rodadas de revisão adversarial (a
  primeira REPROVOU com 6 defeitos + 2 sugestões, a segunda aprovou com
  ressalvas depois de 1 defeito novo corrigido). Decisões que a execução fixou,
  todas vindas da revisão:
  - **A régua do salvar aceita modelo INATIVO** e recusa só o inexistente.
    Desativar é o gesto que a API recomenda no lugar de excluir; se o salvar
    recusasse inativo, desativar tornaria **insalvável** todo fluxo que usa o
    modelo — mexer em qualquer outro nó passaria a devolver 422.
  - **A padronização só vale com catálogo.** A chave `email_exigir_modelo` é
    gravada por MERGE e não depende da tabela: ligada num ambiente sem a 112,
    deixaria o nó novo insalvável **sem gesto possível na tela**, porque o
    painel não mostra a lista quando o catálogo está indisponível.
  - **Nó novo nasce no modelo padrão** (`emailNoNovo`, no ponto de criação);
    com a padronização ligada, a lista abre em *Selecione um modelo…*, nunca em
    Corpo livre — que a API recusaria.
  - **A tela não afirma o que não sabe**: modelo fora da lista de escolha pode
    ter sido desativado (segue enviando) ou removido (a corrida falha), e a
    mensagem diz os dois casos em vez de escolher um.
  - **A semente é guardada pelo catálogo vazio**, não pelo nome: renomeado o
    modelo, a guarda por nome reinseriria a semente e criaria dois `padrao=1`.

### F3 — Seletor de arquivo do anexo
- Entregável: clicar na pastinha, navegar e escolher o arquivo.
- Inclui: `GET /email/anexo/listar` reusando `ssh_arquivos`; fiação do
  `NavegadorPastas` no `PainelEmail`; preenchimento de raiz + nome ao escolher;
  sugestão de troca da data por `{odate}`; testes (raiz fora da lista do e-mail
  → 403; escape por symlink → 403; permissão; o front puro da sugestão de data).
- Critérios de aceite: dado o clique na pastinha, então abre no nível das raízes
  do **e-mail** (não nas dos Utilitários); dado um arquivo escolhido, então raiz
  e nome são preenchidos e a régua aceita; dado `relatorio_20260911.xlsx`, então
  é oferecido `relatorio_{odate}.xlsx` e a escolha é do usuário; dado um caminho
  que sai da raiz por link, então 403 com a mesma mensagem dos Utilitários.
- Validação: completa. Revisão adversarial.
  PR: `feat(email): escolher o arquivo do anexo navegando pelas pastas (F3)`.
- 🔧 **EM REVISÃO** — implementada. O que a execução fixou:
  - **A pasta do anexo passa a ser a raiz liberada OU uma pasta abaixo dela.**
    Sem isso o seletor não alcança o arquivo guardado numa subpasta, que é o
    caso normal. O ENVIO sempre aceitou subpasta (`caminho_do_anexo` mede o
    caminho final contra as raízes) — era só o cadastro que recusava, na tela,
    o que a corrida entregaria sem reclamar.
  - **A régua da pasta vale em três lugares** (API, worker e tela) e há
    **teste cruzado**: os mesmos 20 casos rodam na bancada de node e em
    `pasta_do_anexo`, e o veredito tem de bater. Entre TS e Python não dá para
    comparar o fonte, como o anti-drift faz entre `api/` e `dags/`.
  - **Link de diretório é conferido no ENVIO.** A régua do cadastro é lexical
    (não há SSH no salvar), então `/dados/saida/corrente -> /u02/outra_area`
    passa no texto e o `stat` seguiria o link para fora das pastas liberadas.
    O envio agora pergunta o caminho real ao servidor (`sftp.normalize`) antes
    de ler; servidor sem `realpath` cai na régua lexical, como antes.
  - **Modal aberto não alimenta mais os atalhos do canvas.** O `Modal` da casa
    ganhou a marca `nokey` (do React Flow) e o editor de fluxo consulta a pilha
    de overlays: sem isso o Backspace anunciado como *Subir um nível* abria
    "Excluir nó", e o Esc fechava o painel por baixo do navegador.

### F4 — Manual, release note e smoke
- Manual (§3.5-A e §4.10 revisados, FAQ), `docs/release-notes/email-modelos.md`,
  funcionalidades, spec concluída, smoke §7 em homologação.
- PR: `docs(email): modelos e navegação do anexo (F4)`.
- ✅ **ENTREGUE.** Manual §3.5-A (modelo, prévia e seletor de anexo), §4.10
  (catálogo e padronização), §4.6 (deploy) e §5 (FAQ: cinco perguntas novas);
  `docs/release-notes/email-modelos.md` com roteiro, conferência pós-deploy e
  reversão; `ORQUESTRA_Funcionalidades_e_Beneficios.md`. O smoke da §7 abaixo
  fica para o ambiente real — o que pôde ser provado no DEV está registrado nas
  fases (F2: 22 verificações; F3: 14).

## 6. Riscos e mitigações

| # | Risco | Impacto | Mitigação |
|---|-------|---------|-----------|
| 1 | HTML de terceiro renderizado na tela do administrador | Script executando na sessão de quem tem `acao_admin` | `<iframe sandbox>` **sem** `allow-scripts` nem `allow-same-origin`; teste que prende os atributos do iframe. O produto não tem CSP (conferido em `config/nginx.conf`), então o isolamento é a única defesa — não pode depender de revisão futura |
| 2 | Catálogo que ninguém usa | Trabalho jogado fora | Precedente real: a Supervisão DS **removeu** o `template_id` porque "nunca chegou a ser usado" (migration 063). Aqui o modelo é o **layout**, não o texto, e já nasce semeado e marcado como padrão — o caminho de menor esforço passa a ser usá-lo |
| 3 | Modelo apagado ou desativado quebrando envio em silêncio | Aviso que não chega, task verde | É exatamente o defeito do catálogo do Teams. Aqui: apagar em uso é recusado (409), e modelo inexistente faz a etapa **falhar** com mensagem que nomeia o modelo |
| 4 | A prévia mentir sobre o Outlook | Confiança indevida no que foi visto | A prévia mostra o motor do navegador. O rótulo diz isso, e o manual mantém a regra: a validação final é o e-mail recebido |
| 5 | Vínculo vivo transformando erro de edição em incidente amplo | Um HTML quebrado atinge todos os fluxos de uma vez | A prévia fica ao lado do editor do modelo; e o modelo em edição só passa a valer ao salvar, com a régua de tamanho aplicada |
| 6 | Navegação abrindo pasta que o e-mail não pode anexar | Escolha que a régua depois recusa | O endpoint lista **só** sob as raízes do e-mail; o nível zero mostra exatamente as raízes que o Admin liberou |

## 7. Smoke pós-deploy

⏳ **Pendente**: exige o ambiente real (servidor de e-mail e DataStage). O
roteiro operacional, com o que conferir em cada passo, está em
`docs/release-notes/email-modelos.md` — a lista abaixo é a da spec, mantida
como está para conferência item a item.

a) Admin › E-mail: a seção **Modelos** lista o modelo institucional semeado, marcado como padrão.
b) Editar o modelo, mudar uma palavra do rodapé, salvar; a prévia ao lado acompanha enquanto digita.
c) Num nó de e-mail já existente com modelo escolhido, rodar **sem republicar**: o e-mail chega com a palavra nova.
d) Tentar excluir o modelo em uso: a API recusa nomeando o pipeline. Desativar: quem usa continua enviando, e ele some da lista de escolha.
e) Criar nó novo: o modelo padrão já vem escolhido e a prévia aparece preenchida.
f) Ligar *exigir modelo do catálogo*: o nó novo não oferece corpo livre; os existentes continuam funcionando.
g) No anexo, clicar na pastinha: abre nas raízes do **e-mail**. Descer, escolher um arquivo, conferir que raiz e nome foram preenchidos.
h) Escolher um arquivo com data no nome: a sugestão de `{odate}` aparece; aceitar e rodar numa data diferente para ver o arquivo daquele dia ser anexado.
i) Colar no corpo um `<script>alert(1)</script>` e abrir a prévia: nada executa.
j) Navegar até uma pasta fora das raízes do e-mail pelo caminho digitado: 403.
k) Com o navegador de pastas aberto sobre o canvas, apertar **Backspace**, **Esc** e as **setas**: nenhum deles mexe no fluxo atrás (achado da revisão da F3).
l) Um **link de diretório** dentro de uma pasta liberada, apontando para fora: o navegador recusa entrar, e um nó apontando para ele envia **sem anexo**, com o motivo no registro.

## 8. Pendências e decisões em aberto

1. ✅ **RESOLVIDO (usuário, 2026-09-11): "exigido com escape".** O corpo é
   escolhido numa lista de modelos, com **Corpo livre** como saída explícita. O
   interruptor *exigir modelo* passa a ser o endurecimento opcional (remove o
   Corpo livre da lista), desligado por padrão.
   ⚠️ Consequência para a F2: os nós que **já existem** têm corpo próprio e
   nenhum modelo. Eles entram na lista como **Corpo livre**, mantendo o que
   enviam hoje — a mudança não pode alterar nenhum e-mail já configurado.
2. ✅ **Mantido como proposto** (usuário, 2026-09-11). **O seletor sugere o marcador de data?** A spec propõe que sim, porque
   o anexo típico é o arquivo do dia e o nome livre existe justamente para isso.
   Se preferir que o seletor só preencha o nome exato, é um item a menos.
3. ✅ **Mantido como proposto** (usuário, 2026-09-11). **O modelo define o assunto?** A spec deixa `assunto` no modelo
   como sugestão, preenchida ao escolher, mas o nó continua dono do seu. A
   alternativa é o assunto vir travado do modelo.
4. **Vale um `Content-Security-Policy` no nginx?** Não existe hoje. O iframe
   isolado resolve este caso sem ele, mas o produto renderiza markdown em três
   telas e a defesa é só o escaping na entrada. Fica registrado como backlog
   próprio, fora desta spec.
5. **Precedente a considerar antes de aprovar:** a Supervisão DS removeu o
   catálogo de templates por desuso (migration 063). Vale confirmar que o caso
   aqui é diferente — layout institucional único, não texto por situação.
6. 🆕 **As raízes de anexo do e-mail não passam pela lista de pastas
   proibidas** (achado da F3). `ssh_arquivos.normalizar_raiz` barra `/etc`,
   `/root` e afins nas raízes dos Utilitários; `email_mime.validar_raizes` não
   tem essa lista, então `/etc` pode ser cadastrada em Admin › E-mail. A
   navegação é barrada pela conferência no servidor, mas o **envio** leria o
   arquivo. É anterior a esta spec (veio com a F1 da notificação) e a correção
   mexe na régua de uma config que já pode estar gravada — por isso fica
   registrado aqui em vez de entrar de carona.
7. 🆕 **Excluir o modelo padrão deixa o catálogo sem padrão** (achado da F2). A
   exclusão é recusada quando o modelo está em uso, mas um padrão **sem uso**
   pode ser apagado e o catálogo fica sem nenhum marcado — e aí o nó novo volta
   a nascer em Corpo livre, em silêncio. Três saídas possíveis: (a) recusar a
   exclusão do padrão enquanto houver outro modelo para promover; (b) promover
   automaticamente o mais antigo; (c) deixar como está e avisar na tela. Não
   entra nesta fase.
