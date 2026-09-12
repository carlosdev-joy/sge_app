# Release note — Resultado do SQL no e-mail e ajustes do nó (F1–F6)

Spec: `docs/spec-email-tabela-sql-e-ajustes.md` · Migration **113**

Esta nota cobre a spec inteira. As fases F2 e F3 têm notas próprias com mais
detalhe — `preview-sql-timeout.md` e `email-header.md`; o que está aqui é o
roteiro **consolidado** de deploy e conferência.

## O que entra

| Fase | O que muda | Onde aparece |
|---|---|---|
| F1 | O campo de destinatários do nó aceita **vários endereços digitados** (antes só colados) | Etapas › nó de e-mail |
| F2 | Prévia de SQL: padrão **60s**, teto **280s**, e o campo mudou para **Sistema › Configurações**. Junto foram o `asyncio.to_thread` da prévia/simulação e a separação entre timeout de login e de execução no wizard de Cópia de Dados | Admin, painel do nó SQL, **Cópia de Dados** |
| F3 | Cabeçalho do modelo institucional **inteiro no Outlook**; `{linhas}` sem valor vira `—` | E-mails enviados |
| F4 | O nó SQL publica a **tabela** do resultado, além do valor de sempre | Runtime (XCom) |
| F5 | **`{tabela}`** e `{tabela:NOME_DO_NO}` no corpo/assunto do e-mail | Etapas › nó de e-mail |
| F6 | Manual, esta nota e o smoke | — |

## Ordem do deploy

1. **Migration 113** na etapa **6c** do `deploy.sh`.
   Antes: `SELECT @@VERSION` (o `HASHBYTES` sobre `NVARCHAR(MAX)` pede 2016+) e
   `SELECT config_value FROM dbo.etl_app_config WHERE config_key='sql_preview_timeout_s'`
   (valor acima de 120 passa a valer 280 sozinho — ver `preview-sql-timeout.md`).
2. **`api/`**.
3. **`dags/`** — e **reiniciar o worker**. `dags/utils/` é cacheado pelo
   processo: sem o restart a etapa fica **verde** enviando com o código antigo,
   e o `{tabela}` chega **literal** no corpo do e-mail (o marcador desconhecido
   sai como está, que é a regra da casa).
4. **`dist/`**.
5. `config/` → **n**.
6. ⚠️ **Republicar os pipelines que têm nó SQL** e devem usar `{tabela}`. A
   publicação da tabela vive no código gerado da DAG: fluxo não republicado
   continua funcionando igual, só não oferece a tabela — e aí o corpo mostra
   **"(sem resultado)"**, não o marcador literal. Os dois sintomas apontam para
   coisas diferentes: `{tabela}` cru = worker sem restart; "(sem resultado)" =
   pipeline não republicado (ou nó SQL que não é vizinho imediato).

Também confira o `proxy_read_timeout` real do bloco `/orquestra/`
(`docker exec airflow-ui grep -A 8 "location /orquestra/" /etc/nginx/nginx.conf`):
o teto de 280s se apoia nos 300s do proxy, e o nginx de produção está à frente
do repo.

## Conferência pós-deploy

⚠️ O botão **"enviar e-mail de teste"** do Admin não serve para conferir nada
disto: ele manda corpo fixo em texto puro, sem modelo. Quem monta a mensagem do
modelo é o **worker** — a conferência é rodando um pipeline de verdade.

**Destinatários (F1)**
a) No painel do nó de e-mail, digitar um endereço, **Enter**, digitar outro: os
   dois têm de ficar em linhas separadas e o card mostrar "2 destinatários".
b) Sair do campo com vírgula sobrando: ela some, sem criar destinatário vazio.

**Prévia de SQL (F2)**
c) **Admin › Sistema › Configurações › Configurações de fluxo**: o campo está lá
   (não mais na aba de Notificações) e aceita até 280.
d) Rodar no nó SQL a consulta que antes estourava em 15s: deve trazer a amostra.
e) Forçar o estouro: a mensagem cita o tempo em vigor **e** o caminho do Admin.
f) Com uma prévia longa em andamento, navegar pelo sistema noutra aba: a UI
   continua respondendo.
f2) **Cópia de Dados** (a F2 mexeu no wizard): apontar para uma conexão com host
   inalcançável e clicar em Pré-visualizar — o erro precisa vir em poucos
   segundos, não depois de minutos. É o timeout de LOGIN, que deixou de
   acompanhar o de execução.

**Cabeçalho e modelo (F3)**
g) Rodar a 113 e ler o log: `[OK] cabecalho … corrigido` — ou `[--] modelo
   EDITADO`, se alguém o tiver editado (aí o roteiro é o de `email-header.md`).
h) Rodar a 113 **de novo**: `[--]`, sem alterar nada.
i) Abrir um e-mail do modelo no **Outlook desktop**: cabeçalho inteiro, sem corte
   e sem faixa de cor diferente à direita. Repetir com o **fundo invertido**.
j) No mesmo e-mail, **"exibir em texto sem formatação"**: sem resto de comentário
   HTML e sem texto de desenvolvedor.
k) Fluxo cujo e-mail não vem depois de etapa DataStage: "Linhas processadas"
   mostra `—`, nunca vazio.

**Tabela do SQL (F4/F5)**
l) Fluxo `SQL → E-mail` **republicado**, com `{tabela}` no corpo: o e-mail chega
   com colunas e linhas. ⚠️ O campo do corpo só aparece com o nó em **Corpo
   livre**; com modelo do catálogo, ou troque para Corpo livre, ou acrescente o
   marcador ao modelo em Admin › E-mail › Modelos (aí vale para todos os fluxos
   que o usam).
m) No log da etapa de e-mail, procurar a linha de sucesso:
   `[EMAIL] tabela de <NO>: N linha(s) publicada(s), M coluna(s)`.
   **Se ela não aparecer, o worker está com `dags/utils/` em cache** — reinicie.
n) SELECT com milhares de linhas: o corpo mostra 50 e o rodapé diz
   *"mostrando 50 de …"*.
o) Abrir o mesmo e-mail em **texto sem formatação**: a tabela sai legível, com
   `|` separando as colunas — nunca com os valores colados.
p) Dois nós SQL antes do e-mail, com `{tabela}` sem nome: o corpo diz
   "(sem resultado)" e o log manda usar `{tabela:NOME_DO_NO}`.
q) `{tabela:NOME_ERRADO}`: sai literal no e-mail, e o log diz quais nós existem.
r) Fluxo `SQL → Decisão → E-mail`: o corpo diz "(sem resultado)" e o log explica
   que só o vizinho imediato é lido.
s) Corpo em **texto** (sem HTML) com `{tabela}`: chega a tabela alinhada, sem
   nenhum `<td style=…>`.
t) Abrir um e-mail com tabela no **Gmail**: mensagens acima de ~102 KB são
   cortadas pelo Gmail ("mensagem truncada") — 50 linhas × 15 colunas chegam
   perto desse limite. Se acontecer, reduza as colunas do SELECT.

## Reversão

- **F1/F2/F5 (tela e API)**: voltar `api/` e `dist/`. O valor de
  `sql_preview_timeout_s` permanece gravado e volta a ser recortado em 120.
- **F4/F5 (runtime)**: voltar `dags/` **com restart do worker**. Fluxos seguem
  rodando; `{tabela}` passa a sair literal no corpo, sem quebrar o envio.
- **F3 (modelo)**: o corpo do modelo **não volta sozinho** — seria preciso
  reexecutar o INSERT da 112 ou editar pela tela. Não há motivo prático: o
  cabeçalho antigo é o que está quebrado.
