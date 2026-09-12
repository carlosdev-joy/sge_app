# Spec: Resultado do SQL no e-mail + ajustes do nó — Orquestra
Data: 2026-09-11 · Status: 🏁 **CONCLUÍDA** — F1 #399, F2 #400, F3 #401, F4 #402, F5 #403, F6 (esta) · ⏳ deploy em produção pendente

## 1. Visão

O nó de e-mail entrou em produção sabendo avisar *que* uma carga terminou, mas não
*o que* ela produziu: o corpo só alcança um punhado de marcadores fixos, e o nó SQL
que roda ao lado publica apenas um valor escalar para a Decisão comparar. Quem opera
a malha quer receber o **resultado da consulta** dentro do aviso — a lista de sanções
novas, os registros pendentes, o que a carga trouxe.

Esta spec entrega isso e, no caminho, corrige três defeitos encontrados no uso real:
o campo de destinatários que **não deixa digitar mais de um endereço**, a prévia de SQL
cancelada aos **15 segundos** e o **cabeçalho do modelo institucional quebrado no
Outlook**. Quando estiver pronto, um fluxo poderá terminar com "carga fechou — e aqui
está a tabela do que entrou", num e-mail que chega bem formado no Outlook da Caixa.

## 2. Escopo

**IN:**
- Campo de destinatários do nó aceitando vários endereços digitados (hoje só colados).
- Timeout da prévia/simulação de SQL com default maior e teto maior, regulável no Admin.
- Cabeçalho do modelo "Aviso de fim de carga" refeito para o motor do Word (Outlook
  desktop), inclusive em modo escuro; corpo enviado como documento HTML completo.
- Nó SQL publicando, além do escalar de hoje, a **tabela** do resultado (colunas +
  linhas, truncada na origem).
- Marcadores `{tabela}` e `{tabela:NOME_DO_NO}` no assunto/corpo do e-mail, resolvidos
  em tempo de corrida e renderizados como tabela HTML no corpo.
- Prévia na tela mostrando a tabela de exemplo; painel do nó listando o marcador novo.
- Manual, release note e smoke.

**OUT (explícito):**
- **Anexar o resultado completo** (CSV/Excel) ao e-mail — o módulo de anexo hoje só
  pega arquivo que já existe no servidor; vira spec própria se você quiser.
- Gráfico ou formatação condicional dentro do e-mail (cor por faixa de valor).
- Tabela vinda de qualquer nó que não seja o nó SQL (DataStage, Cópia de Dados).
- Agendar o envio ou reenviar um e-mail já enviado.
- Editor visual de modelos (o Admin continua editando o HTML como texto).
- Rodar a prévia em segundo plano com polling — foi considerado para o timeout e
  descartado nesta spec (fica no backlog se 300 s não bastar).

## 3. Arquitetura proposta

**Front** (`ui-react/src/`):
- `components/etapas/paineis/PainelEmail.tsx` — o campo de destinatários passa a
  guardar o **texto cru** num estado local e só separa os endereços no `onBlur` e no
  salvar, que é o padrão já usado em `components/pipelines/PipelineFormModal.tsx:533`.
- `components/etapas/fluxoTypes.ts` — `EMAIL_PLACEHOLDERS` ganha `tabela`; a régua
  `errosDoEmailNo` não muda.
- `components/etapas/previaEmailDados.ts` — `VALORES_EXEMPLO` ganha uma tabela de
  exemplo para a prévia mostrar o bloco com aparência real.
- `pages/Admin.tsx` (`FlowConfigSection`) — o `max` do campo de timeout acompanha o
  teto novo.

**Back** (`api/`):
- `routers/jobs.py:1143-1150` — `_PREVIEW_TIMEOUT_DEFAULT` 15 → **60**;
  `_PREVIEW_TIMEOUT_MAX` 120 → **280**. O teto para em 280 s de propósito: o nginx
  corta a resposta em 300 s (`config/nginx.conf`, `location /orquestra/`), e a API
  precisa conseguir devolver a mensagem de erro antes disso.
- `services/email_mime.py` — o corpo HTML passa a ser embrulhado num documento
  completo **só quando ainda não for um** (o corpo do modelo começa com `<table`);
  o `<head>` traz `meta charset`, `meta color-scheme` e o bloco
  `<o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch>`, sem o qual o
  Outlook dimensiona formas com o DPI do Windows.
- `services/email_mime.py:43` e `dags/utils/email_envio.py:37` — `PLACEHOLDER_RE`
  passa a aceitar o qualificador: `\{([a-z_]+)(?::([A-Za-z0-9_\-]{1,128}))?\}`.
- `services/email_modelos.py` — sem mudança de contrato; só o corpo semeado muda.

**Orquestração** (`dags/`):
- `etl_dag_factory.py` (`_resolve_e_roda_sql`, ~linha 1439) — além de devolver o
  escalar (contrato atual, que a Decisão `valor_sql` lê pelo `return_value`), publica
  `ti.xcom_push(key="tabela", value={columns, rows, total, truncado})`. **O retorno da
  função não muda**: nenhuma DAG existente muda de comportamento.
- `utils/email_operator.py` — `_mapa` ganha a resolução de `{tabela}`; a busca do nó
  SQL a montante reusa `_jobs_a_montante` (que já tira os prefixos `log_end_`/
  `log_start_`; a task do nó SQL tem `task_id` igual ao nome do nó, `_sql_block:764`).
- `utils/email_envio.py` — função `tabela_html(dados)` que monta o markup, com
  `html.escape` em **toda** célula e cabeçalho.

**Dados:** `sql/migrations/113_email_modelo_header.sql` — atualiza o corpo do modelo
semeado pela 112 **apenas se ninguém o editou** (decisão sua), comparando o corpo atual
com o hash do texto semeado. Editado → não toca e imprime aviso no log da migration.

**Decisões e alternativas descartadas:**
- *Tabela por XCom com key própria, em vez de trocar o retorno do nó SQL* — trocar o
  retorno quebraria toda Decisão `valor_sql` já publicada.
- *Truncar na origem (nó SQL), não na hora de montar o e-mail* — evita carregar
  centenas de milhares de linhas na memória do worker por causa de um aviso.
- *Cabeçalho sólido em vez de VML corrigido* — dá para consertar o VML (altura +
  `mso-fit-shape-to-text`), mas o gradiente continuaria brigando com o modo escuro do
  Outlook, que inverte `bgcolor` e não inverte preenchimento VML. Um cabeçalho de cor
  sólida some com a classe inteira de defeitos.
- *Marcador `{tabela}` sem qualificador quando há um só nó SQL a montante* — evita
  obrigar a digitar o nome no caso comum, mantendo `{tabela:NOME}` para o resto.

## 4. Modelo de dados

Nenhuma tabela nova. A migration **`113_email_modelo_header.sql`** (idempotente,
aplicada na **etapa 6c do `deploy.sh`**) faz:

```
IF EXISTS (SELECT 1 FROM dbo.etl_email_modelo
           WHERE nome = N'Aviso de fim de carga'
             AND HASHBYTES('SHA2_256', CAST(corpo AS NVARCHAR(MAX))) = <hash do corpo da 112>)
    UPDATE ... SET corpo = <corpo novo>, atualizado_em = GETDATE()
ELSE
    PRINT '[--] modelo editado pelo usuario — corpo preservado'
```

Roda 2× sem efeito diferente: depois do primeiro UPDATE o hash deixa de bater e a
segunda execução cai no ramo que preserva. O corpo novo cabe folgado no `NVARCHAR(MAX)`.

⚠️ `HASHBYTES` sobre `NVARCHAR(MAX)` exige `CAST` em pedaços no SQL Server 2014 e
anteriores; o ambiente é 2019 (`orquestra-sqlserver-dev`), que aceita direto — a fase
confirma a versão de produção antes de fechar.

## 5. Fases

### F1 — Destinatários: digitar mais de um endereço
- **Entregável:** o campo aceita Enter e vírgula enquanto se digita.
- **Inclui:**
  - estado local com o texto cru no `PainelEmail.tsx`, separação no `onBlur` +
    no salvar (padrão do `PipelineFormModal`);
  - sincronizar o texto quando o nó muda (trocar de nó no canvas não pode deixar o
    texto do nó anterior na tela);
  - teste de unidade da separação, com os casos que hoje falham (Enter no meio,
    vírgula no fim, espaço sobrando, endereço repetido).
- **Critérios de aceite:**
  - digitar `ana@cvp.com.br`, Enter, `bruno@cvp.com.br` grava **dois** destinatários;
  - colar `a@x.com; b@y.com` continua funcionando;
  - sair do campo com vírgula sobrando não cria destinatário vazio;
  - o rodapé do card mostra "2 destinatários".
- **Validação:** `tsc -b` (nunca `tsc --noEmit`), eslint comparado ao baseline do HEAD,
  build com `dist/` refeita, pytest.
- Revisão adversarial antes da PR. PR: `fix(email): aceitar mais de um destinatário digitado no nó`.

### F2 — Timeout da prévia de SQL
- **Entregável:** prévia com folga de tempo, regulável num lugar que se ache.
- **Inclui:** default 15 → 60 s; teto 120 → 280 s; `max` do campo no Admin; texto de
  ajuda dizendo que cada prévia longa ocupa um worker da API; release note explicando
  como ajustar sem deploy.
- **⛔ O campo está escondido — ✅ mudança autorizada pelo usuário em 2026-09-11:**
  `FlowConfigSection` (`Admin.tsx:2906`) é renderizada dentro de `NotificacoesTab`
  (`Admin.tsx:3102`), ou seja, em **Acessos & Comunicação › Notificações**, no rodapé da
  página dos canais e modelos de card do Teams — ninguém procura configuração de SQL ali.
  A fase **move a seção para Sistema › Configurações**, onde já vive o editor genérico de
  `etl_app_config` (a chave `sql_preview_timeout_s` aparece lá crua, sem rótulo), e a
  mensagem de timeout da prévia passa a dizer onde ajustar.
- **Varredura por outras seções órfãs (pedido do usuário):** feita sobre os títulos de
  seção de `Admin.tsx` — `Congelamento de Ambiente`, `Calendários de Bloqueio` e
  `Janelas de Blackout` (Pipelines › Agendamento), `Canais` e `Modelos de card`
  (Notificações), `Bancos do servidor` (Servidor), `Monitoramento de tabelas` (Monitoramento)
  e `Credencial executora` estão todas na aba a que pertencem. **"Configurações de fluxo"
  é a única órfã** — nada mais a mudar de lugar.
- **Critérios de aceite:**
  - ambiente novo (sem a chave em `etl_app_config`) roda a prévia por 60 s;
  - salvar 280 no Admin persiste; salvar 400 continua sendo recortado para o teto;
  - consulta que estoura devolve a mensagem com o número em vigor, e não erro cru;
  - a resposta de erro chega ao navegador **antes** do corte do nginx.
- **Validação:** pytest (casos de clamp e default) + tsc + eslint + build.
- Revisão adversarial antes da PR. PR: `feat(fluxo): mais tempo para a prévia de SQL`.

### F3 — Cabeçalho do e-mail que não quebra no Outlook
- **Entregável:** o modelo institucional chegando inteiro no Outlook desktop, claro e escuro.
- **Inclui:**
  - corpo enviado como documento HTML completo quando ainda não for um
    (`meta charset`, `color-scheme`, `OfficeDocumentSettings/PixelsPerInch 96`);
  - cabeçalho sem VML: cor sólida, logo em células de tabela (nada de `<div>` com
    `width`/`height`, que o motor do Word ignora), sem `border-radius` no topo;
  - `{linhas}` sem valor vira `—` em vez de deixar a célula vazia;
  - migration 113 com a guarda de hash;
  - a prévia da tela renderizando o mesmo HTML do envio.
- **Critérios de aceite:**
  - e-mail de teste aberto no Outlook desktop mostra o cabeçalho inteiro, sem corte e
    sem faixa de cor diferente à direita;
  - o mesmo e-mail com o fundo invertido (modo escuro) mantém o cabeçalho legível;
  - modelo editado à mão **não** é sobrescrito pela migration;
  - rodar a migration 2× não muda o resultado.
- **Validação:** pytest (guarda do hash, embrulho só quando o corpo não é documento) +
  tsc + eslint + build + envio real de teste pelo Admin.
- Revisão adversarial antes da PR. PR: `fix(email): cabeçalho do modelo institucional no Outlook`.

### F4 — Nó SQL publica a tabela do resultado
- **Entregável:** o resultado da consulta disponível para quem vem depois no fluxo.
- **Inclui:**
  - `xcom_push(key="tabela", ...)` com `{columns, rows, total, truncado}`;
  - truncamento na origem: até **50 linhas × 15 colunas** renderizáveis, lendo no
    máximo 1.000 linhas para saber o total (acima disso o aviso diz "mais de 1.000");
  - valores convertidos para texto de forma segura (data, decimal, `NULL` → `—`),
    reusando a régua de `_json_safe` (`api/routers/jobs.py:1014`) que a prévia já aplica;
  - o retorno escalar **intacto**, com teste provando que a Decisão `valor_sql`
    continua lendo o mesmo valor.
- **Critérios de aceite:**
  - SELECT de 3 linhas publica 3 linhas e `truncado=false`;
  - SELECT de 5.000 linhas publica 50 linhas, `truncado=true` e total "mais de 1.000";
  - SELECT que falha com `on_error=falhar` continua derrubando a task;
  - fluxo com Decisão `valor_sql` a jusante roda igual ao de hoje.
- **Validação:** pytest do factory (bancada de geração) + execução real no DEV.
- Revisão adversarial antes da PR. PR: `feat(sql): publicar a tabela do resultado no XCom`.

### F5 — `{tabela}` no corpo do e-mail
- **Entregável:** o e-mail com a tabela do SQL dentro.
- **Inclui:**
  - `PLACEHOLDER_RE` com qualificador nos **três** espelhos (`api/services/email_mime.py`,
    `dags/utils/email_envio.py`, `previaEmailDados.ts`) + teste anti-drift entre eles;
  - `tabela_html()` com `html.escape` em toda célula, largura fixa, zebra e rodapé
    "mostrando 50 de mais de 1.000 linhas" quando truncado — acima do teto de
    leitura o total é um piso, e o texto nunca afirma um número que não contou;
  - `{tabela}` = único nó SQL a montante; `{tabela:NOME}` = nó nomeado; sem dado, um
    bloco discreto "(sem resultado)" — nunca a chave crua num e-mail institucional;
  - painel do nó listando o marcador com a dica, e a prévia mostrando a tabela exemplo.
- **Critérios de aceite:**
  - fluxo `SQL → E-mail` com `{tabela}` no corpo chega com a tabela preenchida;
  - dois nós SQL a montante e `{tabela}` sem nome → log claro e bloco "(sem resultado)",
    sem adivinhar qual;
  - célula com `<b>` ou `&` chega como texto, não como marcação;
  - `{tabela}` num nó sem SQL a montante não derruba o envio.
- **Validação:** pytest (render, escape, resolução do nó) + tsc + eslint + build +
  corrida real no DEV com o modelo institucional.
- Revisão adversarial antes da PR. PR: `feat(email): marcador {tabela} com o resultado do nó SQL`.

### F6 — Docs, release note e smoke
- **Entregável:** manual atualizado, roteiro de deploy e smoke letrado.
- **Inclui:** manual (§4.10 do e-mail e a seção do nó SQL), `docs/release-notes/`
  com ordem de migration/`dags/`/`api/`/`dist/` e o restart do worker, atualização
  desta spec para "concluída" e da memória do projeto.
- **Critérios de aceite:** o roteiro cita a 113 na 6c, o restart do worker
  (`dags/utils/` é cacheado) e a resposta **n** para `config/`; a seção de reversão
  descreve efeito que de fato ocorre.
- **Validação:** leitura crítica + revisão adversarial focada em "doc que mente".
- PR: `docs(email): manual, release note e smoke da tabela do SQL`.

## 6. Riscos e mitigações

| # | Risco | Impacto | Mitigação |
|---|-------|---------|-----------|
| 1 | A migration 113 sobrescreve um modelo que você ajustou à mão | Perde trabalho manual e o e-mail muda sem aviso | Guarda por hash (F3): só atualiza o corpo idêntico ao semeado; a release note diz como aplicar à mão quem editou |
| 2 | Dado do banco com `<`, `&` ou aspas entra cru no corpo HTML | Layout quebrado no cliente de e-mail; marcação injetada pelo conteúdo da tabela | `html.escape` em toda célula e cabeçalho (F5), com teste de célula maliciosa |
| 3 | Resultado grande vira XCom gigante no metastore | Airflow lento, XCom estourando, worker com pico de memória | Truncar **na origem** (F4): teto de leitura 1.000 linhas, render de 50 × 15 |
| 4 | `PLACEHOLDER_RE` vive em 3 espelhos (API, DAG e TS) | Marcador que funciona na prévia e falha no envio — o falso verde clássico | Teste anti-drift cruzado na F5, no padrão que a F3 do anexo já usa |
| 5 | Timeout de 280 s prende um worker da API por prévia | Poucas prévias pesadas simultâneas deixam a UI lenta para todos | Teto abaixo do corte do nginx, texto de ajuda no Admin e default de 60 s, não o teto |
| 6 | `dags/utils/` é cacheado pelo worker | Task **verde** rodando código velho: e-mail sem a tabela sem ninguém notar | Restart do worker obrigatório no roteiro (F6) e verificação no log da task |
| 7 | `dist/` é commitada | PR "invisível": front antigo em produção | Rebuild da `dist/` em toda fase de front (F1, F2, F3, F5) |
| 8 | O modo escuro do Outlook inverte só parte das cores | Cabeçalho remendado, com dois tons de azul | F3 testa com o fundo invertido antes de fechar, e o cabeçalho deixa de depender de VML |

## 7. Smoke pós-deploy

⚠️ **O botão "enviar e-mail de teste" (Admin › E-mail) NÃO serve para conferir
o cabeçalho nem a tabela**: ele monta corpo fixo em TEXTO PURO, sem `html=True` e
sem passar pelo catálogo de modelos (`api/routers/email.py`). Quem monta a
mensagem do modelo é o **worker** — tudo que envolve HTML se confere rodando um
pipeline de verdade.

a) **Admin › Sistema › Configurações**: o campo mostra 60 em ambiente novo; salvar 280 persiste depois de recarregar.
b) **Prévia de SQL**: rodar no nó SQL a consulta que hoje estoura em 15 s — deve trazer a amostra; uma consulta deliberadamente infinita deve ser cancelada com a mensagem citando o tempo em vigor.
c) **Destinatários**: no painel do nó, digitar dois endereços separados por Enter, salvar, reabrir — os dois continuam lá, e o card mostra "2 destinatários".
d) **Rodar um pipeline com nó de e-mail apontando para o modelo** e abrir a mensagem no Outlook desktop: cabeçalho inteiro, sem corte e sem faixa clara à direita.
e) Repetir (d) com o fundo da mensagem invertido (botão de modo escuro do Outlook): cabeçalho legível.
f) **Fluxo `SQL → E-mail`** no DEV com `{tabela}` no corpo: o e-mail chega com colunas e linhas; o log da task traz `[EMAIL] tabela de <NO>: N linha(s)`.
g) Mesmo fluxo com SELECT de milhares de linhas: o corpo mostra 50 linhas e o rodapé "mostrando 50 de mais de 1.000".
h) Fluxo com Decisão `valor_sql` (já existente, não regerado): continua roteando como antes.
i) Modelo editado à mão: conferir que a 113 **não** mexeu nele (comparar `atualizado_em`).

## 8. Pendências e decisões em aberto

### Descobertas durante a execução (registradas, não resolvidas)

1. **A tela não confere o nome do nó no qualificador.** `{tabela:CONTA}` escrito
   para o nó `CONTA_SANCOES` passa no save e sai literal no e-mail — o painel não
   conhece o grafo a montante. Quem denuncia é o log da etapa, em runtime. Para
   resolver de verdade, o `PropriedadesPanel` precisaria passar ao painel a lista
   de nós SQL a montante; fica como melhoria.
2. **Só o vizinho imediato é lido.** `SQL → Decisão → E-mail` não alcança a
   tabela. Atravessar a decisão exigiria caminhar o grafo para trás no runtime —
   possível, mas muda o contrato de "o que está antes deste nó".
3. **Tamanho da mensagem no Gmail**: 50 linhas × 15 colunas com estilo inline
   chegam perto dos ~102 KB em que o Gmail corta a mensagem. Não afeta o Outlook,
   que é o cliente da casa; se virar problema, o caminho é estilo por classe.
4. **`documento_html` do lado da API não é exercitado em produção.** O módulo
   `api/services/email_mime.py` TEM chamadores — é ele que monta e envia o e-mail
   de teste do Admin (`api/routers/email.py`), além de emprestar as réguas para
   `pipelines.py` e `jobs.py`. O que não roda por lá é o embrulho: o e-mail de
   teste vai com `html=False`. Quem envia mensagem de MODELO é o worker.

### Abertas desde o levantamento



1. **Total exato acima de 1.000 linhas** — para escrever "50 de 1.240" seria preciso ler tudo ou rodar um `COUNT(*)` extra na origem. A spec assume o aviso honesto ("mais de 1.000"); se você preferir o número exato, entra um `COUNT` e o custo de uma segunda consulta.
2. **Colunas acima de 15** — a proposta é cortar as excedentes e avisar no rodapé. A alternativa é quebrar a tabela em duas, que fica ruim de ler no Outlook.
3. **Versão do SQL Server em produção** — o `HASHBYTES` direto sobre `NVARCHAR(MAX)` exige 2016+. A F3 confirma antes de fechar a migration.
4. ~~Para onde vai o campo de timeout~~ — **resolvido em 2026-09-11:** vai para
   Sistema › Configurações, junto com qualquer outra seção órfã (a varredura achou só esta).
5. **Anexar o resultado completo** ficou de fora (escopo OUT). Se for virar prioridade, a fase do anexo mexe em `resolver_anexo`, que hoje só lê arquivo já existente no servidor.
