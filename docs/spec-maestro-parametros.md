# Spec: Maestro — assistente conversacional de parâmetros DataStage — Orquestra
Data: 2026-09-10 · Status: aprovada 2026-09-10 · em execução (F3; F1 = #382, F2 = #383)

## 1. Visão
Cadastrar parâmetro DataStage exige conhecer um vocabulário (origem, meses, âncora,
dias, formato, tipos) que a maioria dos usuários de Etapas não domina. O **Maestro**
é um avatar de chat na seção *Parâmetros do job* (Etapas **e** Fluxos, mesmo
componente): a pessoa descreve o cenário ("carga mensal do mês anterior, com data
inicial e final") e o Maestro responde **como preencher cada campo**, com um botão
*Aplicar no editor* que preenche as linhas para conferência antes de salvar. Se o
cenário não existe no catálogo de cenários atendidos, o Maestro diz isso com clareza,
orienta a **procurar o administrador** e registra o pedido para o administrador ver
a demanda. Resultado: o uso dos parâmetros da spec anterior acelera sem o usuário
precisar ler o §3.10 do manual.

## 2. Escopo
**IN:**
- Chat multi-rodada com o Maestro dentro da seção *Parâmetros do job* do
  `JobTypeFields` em modo datastage (Etapas › modal e Fluxos › painel da etapa).
- Conhecimento do Maestro = **vocabulário real** de `services/job_params.py` +
  **catálogo de cenários** mantido pelo administrador (tabela nova, com semente
  dos cenários mais comuns) + os parâmetros que o job **declara** no lineage ISX
  (quando extraído) + os defaults do pipeline (para não duplicar).
- Resposta sempre em duas partes: explicação em prosa (campo a campo) e uma
  **proposta estruturada** validada no servidor pelas réguas que já existem
  (`normalizar_lista` + `resolver_preview`). Só proposta válida chega ao botão
  *Aplicar no editor*; a prévia com a data de referência acompanha.
- Cenário não atendido → mensagem padrão "procure o administrador", pedido gravado
  com `atendido = 0` e visível no Admin.
- Ligar/desligar o Maestro no Admin (chave própria em `etl_app_config`), reusando o
  **provedor de IA já configurado** (`caixa_ia_*`: anthropic, OpenAI-compatível ou
  gateway da Caixa) — sem segunda chave de API.
- Admin: CRUD do catálogo de cenários + lista de pedidos não atendidos.
- Log de conversas (tabela própria), sem nenhum valor Encrypted.
- Manual do usuário, release note, smoke.

**OUT (explícito):**
- O Maestro **não salva** nada: aplica no editor; quem salva é o usuário pelo botão
  de sempre da etapa. Não cria etapa, não muda tipo, não mexe em pipeline.
- Não sobrepõe parâmetros no rerun (F5 da spec anterior) nem edita defaults do
  pipeline — só orienta e, se for o caso, diz "isso é default do pipeline".
- Não executa `dsjob -lparams` nem consulta o DataStage: a lista de parâmetros
  declarados vem do lineage ISX já extraído; sem ISX, o Maestro pede o nome ao
  usuário e avisa que a conferência acontece no disparo.
- Não amplia o vocabulário (dias úteis, feriados, valor vindo de tabela): quem
  pede isso recebe "procure o administrador" — backlog na spec de parâmetros §8.
- Não usa tool-use/function calling do provedor: o gateway da Caixa é texto puro.
  A proposta vem num bloco JSON no fim da resposta e o servidor a valida.
- Não guarda memória entre conversas (cada abertura do chat começa do zero; o
  histórico das últimas conversas do usuário fica consultável, como no Caixa).
- Sem streaming (o gateway da Caixa não suporta; o padrão do repo é resposta única).
- Sem avatar animado/voz. O avatar é uma ilustração estática (SVG inline).

## 3. Arquitetura proposta

**Front (`ui-react/src/`)**
- `components/etapas/MaestroChat.tsx` (novo): botão com o avatar ao lado de
  *Importar do DataStage* na linha de cabeçalho da seção
  (`JobTypeFields.tsx:649-683`, `data-secao-params-ds`) — **acrescido à direita
  do botão existente, sem reordenar o que já está lá** — abre um painel flutuante
  (`fixed bottom-6 right-6`, portal no `document.body`, `z-[60]`: acima do
  `Modal` (`z-50`) e abaixo do `Toast` (`z-[100]`)). Visual nativo (tokens
  `panel/edge/ink/canvas`, claro+escuro), no molde do
  `caixa/components/ChatAssistant.tsx` mas sem PDF e sem cor da Caixa.
- `lib/maestro.ts` (novo, puro, sem React): montagem do contexto enviado ao
  servidor (`contextoDoEditor`: linhas atuais **sem valor Encrypted**, defaults do
  pipeline, nome do pipeline/job), conversão da proposta da API em `JobParam[]`
  do editor (`propostaParaEditor`), mescla com as linhas atuais
  (`aplicarProposta`: substitui pelo nome exato, mantém as demais) e as mensagens
  fixas (boas-vindas, "procure o administrador"). Bancada em
  `tests/js/ds_params_harness.cjs` (mesma infra: sucrase + minireact).
- Markdown da resposta desenhado por blocos com o **parser puro**
  `parseMarkdown` de `caixa/lib/markdown.ts` (o mesmo dos assistentes do Caixa,
  sem HTML por string — o texto vem de um LLM); só o parser é reusado, nenhum
  componente da seção Caixa.
- `JobTypeFields.tsx`: recebe `pipeline`/`jobName` (já recebe desde a F6) e passa
  ao `MaestroChat` junto com `value.params`, `defaultsPipeline` e um
  `onAplicar(params)` que faz `onChange({ params })` lendo a lista atual via
  `paramsRef` (mesma proteção do import: o usuário pode editar enquanto a
  resposta está em voo).
- `pages/Admin.tsx` › aba nova **Maestro** dentro de *Acessos & Comunicação* (ao
  lado de *Caixa Seguro IA*): interruptor, catálogo de cenários (tabela + modal
  de edição), pedidos não atendidos. Componentes em `components/admin/Maestro*.tsx`
  (padrão dos `Utilitarios*.tsx`).
- Gate de exibição: `GET /maestro/status` → `{enabled}` via `useQuery` (5 min),
  como `useAssistentesIA`. Desligado ou sem resposta = botão oculto.

**Back (`api/`)**
- `services/maestro.py` (novo): `SYSTEM_PROMPT` montado a partir do vocabulário
  **importado** de `job_params` (tipos, origens, âncoras, formato permitido,
  limites, ordem meses → âncora → dias → formato, exemplos) — nunca digitado à mão,
  para não divergir; `montar_contexto(cur, pipeline, job, editor)` (catálogo,
  parâmetros declarados no ISX via `services.lineage_isx.montar`, defaults do
  pipeline via `etl_pipeline_param`); `extrair_proposta(texto)` (último bloco
  ```json da resposta) → `validar_proposta(proposta, referencia)` reusando
  `normalizar_lista` + `resolver_preview`; `classificar(resposta)`:
  `atendido | nao_atendido | pergunta` (o modelo é instruído a responder
  `{"status": "nao_atendido", "motivo": ...}` quando não há cenário; a régua do
  servidor é a **fonte da verdade**: proposta que não valida vira `nao_atendido`
  com o erro, mesmo que o modelo tenha dito que atende).
- `services/caixa_ia.py`: nova função `chat_conversa(cfg, system, mensagens)`
  (lista `[{role, content}]`): anthropic e openai_compat mandam a lista; o gateway
  da Caixa recebe o transcrito concatenado numa única mensagem (mesmo motivo do
  `_corpo_gateway`). `chat()` atual continua igual (Caixa Seguro não muda).
- `routers/maestro.py` (novo), tudo atrás de `require_perm("tela_jobs")` (a mesma
  permissão de Etapas e Fluxos no `nav.ts`):
  - `GET  /maestro/status` → `{enabled}`.
  - `POST /maestro/conversar` body `{conversa_id, mensagens[], contexto{pipeline_name,
    job_name, params[], referencia}}` → `{resposta, status, proposta|null,
    previa|null, erros[]}`; grava um registro por rodada em `etl_maestro_conversa`.
  - `GET  /maestro/historico` → últimas 20 conversas do usuário (agrupadas por
    `conversa_id`).
  - `GET/POST /maestro/cenarios` e `POST /maestro/cenarios/{id}/excluir` (admin,
    `get_admin_user`); `GET /maestro/pedidos` (admin): não atendidos, com marcação
    `tratado_em`.
- `routers/admin.py`: nada novo além de reusar `caixa_ia.load_config` — o
  interruptor `maestro_enabled` fica no router do Maestro para não inflar o
  `admin.py` (1.300+ linhas).
- Erros: 503 `maestro_desligado`, 503 `ia_indisponivel` (config do provedor
  ausente → o usuário não vê internals; o admin vê o laudo em *Caixa Seguro IA ›
  Verificar*), 422 estruturado nas entradas, 429/402 repassados como no Caixa.

**Dados:** §4.

**Orquestração/automação:** nenhuma. O Maestro só conversa com o provedor a partir
do `orquestra-api` (mesma rede/proxy dos assistentes do Caixa — o worker não entra).

**Decisões e alternativas descartadas**
- *Catálogo de cenários + vocabulário* (escolhido) × *só vocabulário, IA livre*:
  "o cenário não existe" precisa de um universo definido; o catálogo dá ao
  administrador o controle do que o Maestro promete e mostra a demanda reprimida.
- *Reusar o provedor do Caixa* (escolhido) × *segunda configuração de IA*: uma
  chave, um gateway, um laudo de conexão. Só o interruptor é próprio.
- *Proposta em bloco JSON validado no servidor* (escolhido) × *tool-use*: o gateway
  da Caixa não tem tool-use; a validação pelo `job_params` é a mesma régua do
  salvar, então nada que o Maestro proponha pode dar 422 depois.
- *Painel flutuante em portal* (escolhido) × *coluna dentro do modal*: o modal de
  Etapas já é denso e o dock do Fluxo é baixo; o flutuante serve aos dois sem
  mudar a ordem dos objetos das telas.
- *Tabela própria de log* (escolhido) × *reusar `etl_caixa_chat_log`*: o Maestro
  precisa de `pipeline_name/job_name/status/proposta_json`, e misturar domínios
  no log do Caixa confundiria o histórico daquela tela.
- *Estado da conversa no front* (escolhido, como o Caixa) × *sessão no servidor*:
  o servidor fica sem estado; o front manda as últimas 12 mensagens por rodada.

## 4. Modelo de dados
Migration **`110_maestro.sql`** (idempotente; próximo número livre após a 109):

```sql
-- Catálogo de cenários atendidos (mantido pelo administrador)
dbo.etl_maestro_cenario (
  id            INT IDENTITY PRIMARY KEY,
  codigo        VARCHAR(40)   NOT NULL UNIQUE,      -- ex.: mensal_anterior
  titulo        NVARCHAR(120) NOT NULL,             -- "Carga mensal do mês anterior"
  descricao     NVARCHAR(600) NOT NULL,             -- quando usar (o Maestro lê)
  receita_json  NVARCHAR(MAX) NOT NULL,             -- parâmetros-modelo (§4.1)
  ativo         BIT NOT NULL DEFAULT 1,
  criado_em DATETIME2(0)/criado_por/atualizado_em/atualizado_por
)
-- Uma linha por rodada de conversa
dbo.etl_maestro_conversa (
  id            INT IDENTITY PRIMARY KEY,
  conversa_id   VARCHAR(36)   NOT NULL,             -- uuid gerado no front
  matricula     VARCHAR(20)   NOT NULL,             -- largura de etl_usuario
  pipeline_name NVARCHAR(200) NULL,                 -- larguras da 109
  job_name      NVARCHAR(200) NULL,
  mensagem      NVARCHAR(MAX) NOT NULL,
  resposta      NVARCHAR(MAX) NULL,
  status        VARCHAR(20)   NOT NULL,             -- atendido | nao_atendido | pergunta | erro
  cenario_codigo VARCHAR(40)  NULL,
  proposta_json NVARCHAR(MAX) NULL,                 -- sem valor Encrypted, nunca
  motivo        NVARCHAR(600) NULL,                 -- por que não atendeu
  modelo        VARCHAR(100)  NULL,
  duracao_ms    INT NULL,
  tratado_em    DATETIME2(0) NULL, tratado_por VARCHAR(20) NULL,  -- admin viu o pedido
  criado_em     DATETIME2(0) NOT NULL DEFAULT GETDATE()
)
-- índices: (conversa_id), (matricula, criado_em DESC), (status, tratado_em)
-- chave nova em etl_app_config: maestro_enabled ('0' padrão)
```

Larguras: `pipeline_name`/`job_name` NVARCHAR(200) como a 109 e `matricula`
VARCHAR(20) como `etl_usuario`; `resposta` NVARCHAR(MAX) porque a resposta
carrega markdown + JSON; `motivo`/`descricao` medidos em UTF-16 (gotcha do repo)
com `cortar_utf16`. **Semente** (na própria migration, `IF NOT EXISTS` por
`codigo`, 10 cenários): `mensal_anterior` (pDataIni = −1 mês, início; pDataFim =
−1 mês, fim), `mes_corrente` (início do mês até a referência), `diario_d1`
(referência −1 dia), `diario_referencia` (referência tal qual),
`semanal_anterior` (segunda/domingo, depois −7 dias), `trimestre_anterior`,
`ano_anterior`, `competencia_aaaamm` (formato `%Y%m`), `rastreio_run_id`,
`caminho_fixo` (Pathname absoluto). Nomes de parâmetro na semente são
**placeholders** (`<DATA_INICIAL>`): o Maestro troca pelos nomes que o job
declara ou que o usuário informar.

### 4.1 Contrato da proposta (o bloco JSON que o modelo devolve)
```json
{"status": "atendido", "cenario": "mensal_anterior",
 "params": [
   {"param_name": "pDataIni", "param_type": "Date", "param_source": "data_referencia",
    "param_offset_meses": -1, "param_ancora": "inicio_mes", "param_offset_dias": 0,
    "param_formato": "%Y-%m-%d"},
   {"param_name": "pDataFim", "param_type": "Date", "param_source": "data_referencia",
    "param_offset_meses": -1, "param_ancora": "fim_mes", "param_offset_dias": 0,
    "param_formato": "%Y-%m-%d"}
 ]}
{"status": "nao_atendido", "motivo": "último dia útil exige calendário de feriados, que o cálculo de data não tem"}
{"status": "pergunta"}   -- o Maestro ainda precisa de uma informação do usuário
```
O servidor valida `params` com `normalizar_lista` (mesma régua do save) e calcula
a prévia com `resolver_preview(referencia, itens)`; `param_type = Encrypted` é
aceito **sem valor** (o usuário digita no editor). Nome que não está entre os
declarados no ISX (quando o ISX existe) vira aviso na resposta, não bloqueio.

## 5. Fases

### F1 — Fundação: migration, serviço e endpoint de conversa
- Entregável: `POST /maestro/conversar` funcionando via API, com catálogo semeado.
- Inclui: `sql/migrations/110_maestro.sql` (tabelas, índices, semente, chave
  `maestro_enabled`); `services/caixa_ia.chat_conversa`; `services/maestro.py`
  (system prompt gerado do vocabulário, contexto, extração/validação/classificação
  da proposta, log); `routers/maestro.py` com `status`, `conversar`, `historico`;
  registro do router no `main.py`; testes: prompt contém todo o vocabulário
  (anti-drift contra `job_params`), proposta válida → `atendido` + prévia,
  proposta inválida → `nao_atendido` com o erro da régua, JSON ausente →
  `pergunta`, Encrypted nunca no log, gateway recebe transcrito concatenado,
  desligado → 503 `maestro_desligado`, sem permissão → 403; migration roda 2×.
- Critérios de aceite: dado o catálogo semeado e o provedor configurado, quando o
  usuário manda "mensal do mês anterior com data inicial e final" com o job que
  declara `pDataIni`/`pDataFim` no ISX, então a resposta traz `status=atendido`,
  os dois itens com `-1 mês` + `inicio_mes`/`fim_mes` e a prévia correta para a
  referência informada; quando manda "último dia útil do mês", então
  `nao_atendido` com motivo, registro com `atendido=0`; com `maestro_enabled=0`,
  503 e nada é gravado.
- Validação: pytest completo contra o baseline (8 falhas pré-existentes); os SQLs
  da 110 reexecutados no DEV desta VPS (0 erros).
- Revisão adversarial (`qa-adversarial`) antes da PR. PR: `feat(maestro): fundação —
  migration 110, serviço e endpoint de conversa (F1)`.

### F2 — Tela: avatar e chat em Etapas e Fluxos, com "Aplicar no editor"
- Entregável: o Maestro na seção *Parâmetros do job* (Etapas › modal e Fluxos ›
  painel), conversa, proposta com prévia e botão *Aplicar no editor*.
- Inclui: `lib/maestro.ts` (puro) + `MaestroChat.tsx` (portal, `z-[60]`, tokens
  nativos, boas-vindas com 4 sugestões vindas do catálogo, bolhas com markdown,
  cartão da proposta com a prévia e o botão *Aplicar no editor*, mensagem fixa de
  "procure o administrador" com o motivo), `JobTypeFields.tsx` (botão à direita de
  *Importar do DataStage*, `paramsRef` no aplicar), gate `useMaestroAtivo`,
  histórico do usuário; bancada `ds_params_harness.cjs`: contexto sem Encrypted,
  aplicar substitui pelo nome e preserva as demais linhas, botão só em datastage e
  só com o Maestro ligado; `dist/` recompilada por último.
- Critérios de aceite: dado um job datastage no modal de Etapas ou no painel do
  Fluxo, quando o Maestro está ligado, então o avatar aparece ao lado de *Importar
  do DataStage* (e não aparece em storedproc/shell/python); dada uma proposta
  `atendido`, quando o usuário clica *Aplicar no editor*, então as linhas entram
  no editor com origem/meses/âncora/dias/formato preenchidos, a prévia da seção
  bate com a do Maestro e nada foi salvo; dada uma resposta `nao_atendido`, então
  o cartão mostra o motivo e a orientação de procurar o administrador, sem botão
  de aplicar; no tema escuro nada fica branco; o painel não é coberto pelo modal
  nem cobre os toasts; sem `overflow-hidden` matando o scroll das bolhas.
- Validação: `tsc -b` + eslint por (arquivo, regra) contra o baseline (zero novos)
  + build + pytest (bancada do front).
- Revisão adversarial antes da PR. PR: `feat(maestro): avatar e chat em Etapas e
  Fluxos com "Aplicar no editor" (F2)`.

### F3 — Admin: interruptor, catálogo de cenários e pedidos não atendidos
- Entregável: aba **Maestro** em *Acessos & Comunicação*.
- Inclui: endpoints admin (`cenarios` GET/POST/excluir com validação da
  `receita_json` pela mesma régua; `pedidos` GET + marcar tratado); interruptor
  `maestro_enabled` (exige provedor configurado com chave, como o Caixa);
  componentes `components/admin/Maestro*.tsx`; o catálogo alimenta as sugestões
  de abertura do chat; retenção de 180 dias das conversas na limpeza de logs;
  testes de rota e da validação da receita; `dist/`.
- Critérios de aceite: dado um cenário novo salvo no Admin, quando o usuário abre
  o Maestro, então o cenário aparece nas sugestões e é atendido; dada uma receita
  inválida (âncora inexistente), então 422 com o erro da régua; dado um pedido
  `nao_atendido`, então ele aparece na lista com pipeline/job/matrícula/motivo e
  some ao marcar tratado; interruptor desligado → botão some das telas em até 5
  min (ou no F5).
- Validação: tsc + eslint (baseline) + build + pytest.
- Revisão adversarial antes da PR. PR: `feat(maestro): admin — interruptor,
  catálogo de cenários e pedidos não atendidos (F3)`.

### F4 — Polimento: manual, release note, smoke no DEV e fecho
- Entregável: documentação e conferência real.
- Inclui: `docs/MANUAL_USUARIO.md` §3.11 *Maestro* (+ nota no §3.10, §4 admin,
  FAQ); `docs/release-notes/maestro.md` (deploy: 110 na 6c, `dist/`, provedor de
  IA já configurado, `config/` → n); `docs/ORQUESTRA_Funcionalidades_e_Beneficios.md`;
  smoke §7 no DEV com o provedor anthropic desta VPS (o gateway da Caixa só em
  produção); ajustes de prompt que o smoke pedir (com teste para cada ajuste);
  status da spec → concluída.
- Critérios de aceite: os cinco cenários da semente atendidos no DEV com prévia
  correta; três pedidos fora do vocabulário (dia útil, feriado, valor de tabela)
  → "procure o administrador" e listados no Admin; nenhum valor Encrypted em
  `etl_maestro_conversa` nem no log da API.
- Validação: completa (tsc + eslint + build + pytest) e `/simplify` opcional.
- Revisão adversarial antes da PR. PR: `docs(maestro): manual, release note e
  smoke (F4)`.

## 6. Riscos e mitigações
| # | Risco | Impacto | Mitigação |
|---|-------|---------|-----------|
| 1 | O modelo "inventa" origem/âncora que o vocabulário não tem (falso verde) | Proposta aplicada dá 422 no salvar ou, pior, comportamento inesperado | O servidor valida com `normalizar_lista` **antes** de devolver a proposta; inválida vira `nao_atendido` com o erro; teste anti-drift garante que o prompt lista o vocabulário do `job_params` |
| 2 | Segredo vazando para o provedor ou para o log | Senha do DataStage num gateway externo / tabela | Contexto do editor nunca leva valor Encrypted (bancada prova); prompt instrui a nunca pedir senha; `proposta_json` gravada sem valor de Encrypted; `_PADROES_SEGREDO` do admin cobre `maestro` |
| 3 | Gateway da Caixa: proxy/CA/formatos (incidente já vivido nos assistentes) | "Maestro indisponível" em produção sem dizer por quê | Reuso integral de `caixa_ia` (trust_env, `_verificacao_tls`, `extrai_texto`); laudo em *Caixa Seguro IA › Verificar* vale para o Maestro; erro 503 ao usuário com "contate o administrador" |
| 4 | Permissão: usuário de consulta usando IA à vontade / custo | Gasto no provedor; ruído no log | Gate `tela_jobs` (quem pode ver Etapas/Fluxos); limite de 4.000 chars por mensagem e 12 mensagens de histórico; interruptor do admin; `duracao_ms`/`modelo` no log para acompanhar |
| 5 | Painel flutuante × modal/dock: z-index, tema escuro, sticky/overflow | Chat escondido atrás do modal ou branco no escuro | Portal em `document.body` com `z-[60]` (Modal `z-50`, Toast `z-[100]`); só tokens semânticos; revisão adversarial com o checklist de CSS do repo |
| 6 | Deploy: migration 110 esquecida ou Maestro ligado sem provedor | 500 na rota / 503 permanente | Rota degrada com "Invalid object name" → 503 `maestro_indisponivel` com a dica da 110; interruptor recusa ligar sem chave (mesma regra do Caixa); release note com a 6c |
| 7 | Semente do catálogo com nomes de parâmetro que não existem no job | Usuário aplica e a etapa falha no disparo por "não declarado" | Semente usa placeholders; o Maestro só sugere nomes do ISX quando há ISX e avisa "confira o nome no Designer" quando não há; a conferência real continua no `-lparams` do disparo |
| 8 | O usuário confunde "aplicado" com "salvo" | Fecha o modal e perde a proposta | Toast "aplicado no editor — confira e salve a etapa"; badge de contagem da seção já muda na hora |

## 7. Smoke pós-deploy
a) Admin › *Acessos & Comunicação* › **Maestro**: interruptor ligado com o provedor
   já verificado em *Caixa Seguro IA*; catálogo mostra os 10 cenários da semente.
b) Etapas › editar uma etapa DataStage com ISX extraído: o avatar aparece ao lado
   de *Importar do DataStage*; em etapa storedproc não aparece.
c) Conversa: "carga mensal do mês anterior, data inicial e final" → resposta explica
   campo a campo, cartão com `pDataIni`/`pDataFim` (nomes do ISX), prévia para a
   referência de hoje = 1º e último dia do mês passado; *Aplicar no editor* → as
   duas linhas entram no editor; salvar a etapa → `GET /pipelines/{p}/fluxo`
   devolve o cálculo.
d) Fluxos › mesmo job no painel da etapa: o avatar e o aplicar funcionam no dock.
e) Conversa: "último dia útil do mês anterior" → "não atendido" com o motivo e a
   orientação de procurar o administrador; Admin › Maestro › *Pedidos* lista o
   pedido com pipeline/job/matrícula; marcar tratado remove da lista.
f) Conversa que envolve senha: "o job precisa da senha do banco" → o Maestro propõe
   `Encrypted` **sem valor** e diz para digitar no editor; `SELECT proposta_json
   FROM dbo.etl_maestro_conversa` sem nenhum valor; log da API sem o valor.
g) Desligar o Maestro no Admin → o avatar some (após o cache de 5 min ou F5); a
   API responde 503 `maestro_desligado`.
h) Provedor com chave errada → usuário vê "Maestro indisponível — contate o
   administrador"; *Caixa Seguro IA › Verificar* mostra a etapa que falhou.
i) Tema escuro: painel, bolhas e cartão da proposta legíveis; o painel fica acima
   do modal e abaixo dos toasts.
j) **Gateway da Caixa com histórico** (só em produção): conversa de 2+ rodadas e
   inspeção da resposta crua — o transcrito "Usuário:/Assistente:" numa mensagem
   só não pode levar o modelo a responder prefixando "Assistente:" nem a
   continuar o transcrito. Se acontecer, ajuste do `transcrever`.
k) **Anthropic com adaptive thinking**: conversa de 2+ rodadas (turnos assistant
   anteriores sem blocos de thinking) aceita pelo provedor no DEV.
l) **Resposta longa**: depois de uma resposta do Maestro acima de 4.000
   caracteres, a rodada seguinte continua funcionando (o histórico é truncado
   no servidor, nunca recusado).

## 8. Decisões tomadas (aprovação de 2026-09-10) e pendências
- **Desenho aprovado** pelo usuário: catálogo de cenários (admin) + vocabulário,
  reuso do provedor do Caixa com interruptor próprio, painel flutuante, proposta
  validada no servidor.
- **Avatar** (pedido do usuário: "um avatar que faça sentido com o contexto da
  aplicação"): ilustração SVG inline própria, desenhada na F2, derivada da marca do
  Orquestra (`components/layout/Logo.tsx`: três linhas diagonais com nós, ciano
  `#06B6D4` / azul `#1E40AF` / azul-escuro `#0B1A30`) — um **regente** cujo braço
  e batuta conduzem as três linhas do pipeline (as "partituras" que o Orquestra
  já usa como símbolo), com estados "ouvindo" (parado) e "pensando" (pulso). Sem
  imagem raster; funciona nos temas claro e escuro pelos tokens.
- **Posição do botão**: à direita de *Importar do DataStage*, na linha de cabeçalho
  da seção, sem reordenar o que já existe.
- **Permissão**: `tela_jobs` (a mesma de Etapas/Fluxos), porque o Maestro não grava
  nada.
- **Retenção** de `etl_maestro_conversa`: 180 dias, na limpeza da F3.
- Modelo: o configurado no provedor; se em produção o gateway expuser um modelo
  mais barato, o admin pode trocar só ali (vale para o Caixa também).
- Números de migration (110) confirmados na abertura da F1.
