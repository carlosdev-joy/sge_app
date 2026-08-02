# Desenho técnico — F5: cadastro e visão de dependências (UX/API)

Spec: `docs/spec-dependencias-pipelines.md` §5-F5 · Base: branch `feat/retomada-f4-guardia` (F2+F3 na main; F4 implementada nesta branch) · Escopo: `api/routers/pipelines.py` + `api/routers/malhas.py` + `api/routers/factory.py` + `api/services/dependencias.py` (novo) + **migration 073** + front (`components/pipelines/`, `components/malhas/`, `pages/Dashboard.tsx`) + testes · **Zero mudança em `dags/`** — a F5 não toca o motor · Suíte-contrato: `docs/retomada-aceitacao.md` — itens de F5: **D26–D35**; não-regressão: D24/D25 (F1) e D27 (parcialmente na main)

## 0. Princípios herdados (F2 §0 + F3 §0 + F4 §0 + causa C — regem tudo abaixo)

1. **Todo campo que se grava se lê de volta** (causa C): nenhuma coluna nova entra no `register` sem entrar no GET e no tipo TS do front — o defeito write-only (`hora_virada`/`nao_iniciar_antes`/`hora_limite_dependencia` zerados por QUALQUER save, inclusive o inativar) morre por **contrato de round-trip com teste explícito**, não por promessa.
2. **Chave ausente do body = "não mexa", nunca "apague"**: o `register` vira PATCH-parcial nos campos da 067 — é a única semântica em que um body parcial (inativar, script, import) não destrói configuração alheia ao gesto.
3. **Aresta a aresta, nunca replace-all onde há o que perder** (causa C): a porta de escrita de dependência em EDIÇÃO é a MESMA da F8 (`POST`/`DELETE /dependencias` — canonização + espelho CSV na mesma transação, idempotente). O replace-all do `register` sobrevive só onde é inofensivo por construção (criação: tabela vazia, DELETE no-op).
4. **Um predicado só** (D29/N9): o painel porta `liberado()` de `dags/utils/dependencias.py` com **teste de paridade** — o precedente é `api/services/data_referencia.py` × `dags/` (F9, `tests/test_malhas_f9.py:404-445`). Nenhum `TOP 1 ... ORDER BY COALESCE(inicio, criado_em)` em lugar nenhum da API (foi exatamente o SQL do endpoint da 1ª F5 — D15+D29 juntos).
5. **Placeholder por árvore**: `?` em toda a árvore `api/` (pyodbc), `%s` só em `dags/` — o GOTCHA registrado; o port do predicado troca o placeholder, o teste de paridade normaliza.
6. **Modal montado só quando aberto** (D31, correção E): o `Modal` da casa esconde com `open` mas NÃO desmonta — render condicional no pai é obrigatório.
7. **Degradação nunca é 500 cru**: sem 067 → leitura degrada com flag (`migration_067_pendente`, contrato F8/F9), escrita de dependência dá 503 com instrução (padrão `malhas.py`); sem 073 → tudo funciona como hoje (guard `INFORMATION_SCHEMA`/`COL_LENGTH`, padrão do próprio `pipelines.py`).
8. Validação viva no dev (API + tela) antes do merge, como F7/F8 — a F5 não tem cenário de DAG rodando; a única publicação real no dev é a do D30 (conferir o `schedule=None` gerado).

---

## 1. As duas portas de escrita — a decisão central (responde a pergunta 1)

Hoje existem **duas portas para a MESMA tabela** (registrado no §4b da spec e no desenho da F3): o `register_pipeline` (replace-all via `_gravar_dependencias`, alimentado pelo CSV do form) e os endpoints da F8 (`POST`/`DELETE /dependencias`, aresta a aresta, com canonização e espelho CSV na mesma transação — `api/routers/malhas.py:772-883`). Manter as duas com semânticas diferentes é convite à divergência que a causa C encarna.

**Alternativas pesadas:**

| Opção | Prós | Contras |
|---|---|---|
| (a) Manter tudo no `register` (CSV replace-all) | uma transação com o resto do form; wizard atômico (cancelar não grava) | replace-all continua vivo em EDIÇÃO (a superfície da causa C); duas semânticas de escrita; **body sem `depends_on` APAGA TUDO hoje** (`body.get("depends_on") or ""` → lista vazia → DELETE sem INSERT — a mesma classe do "inativar zerava", ainda aberta na main para este campo) |
| (b) Tudo aresta a aresta, inclusive na criação | uma porta só | **impossível na criação**: a FK da 067 exige o pipeline existir em `etl_pipeline` — não há como POSTar dependência antes do register |
| (c) **Híbrido (escolhida)** | mata o replace-all onde há o que perder; criação continua atômica; uma semântica de aresta (a da F8) | duas portas continuam existindo — mitigado porque a porta do register fica restrita ao caso em que ela é segura por construção |

**Decisão 1 — híbrido por modo:** na **CRIAÇÃO**, as dependências escolhidas no modal viajam no body do `register` como `depends_on` (replace-all sobre pipeline recém-criado = tabela vazia = DELETE no-op, só INSERTs — não existe estado a perder; preserva o wizard: cancelar não grava nada). Na **EDIÇÃO**, o modal grava **aresta a aresta pelos endpoints da F8** e o form **para de enviar `depends_on`** *(evita: o replace-all destrutivo da causa C exatamente onde ele mordia; e o CSV "A,A,B" que deixava pipeline rodando por cron — o caminho nem existe mais na edição)*.

**Decisão 2 — `register` vira PATCH-parcial em `depends_on`:** chave **ausente** do body = não toca na tabela nem no CSV (o UPDATE do espelho sai do bloco incondicional atual, `pipelines.py:705-709`, e passa a ser gateado por `"depends_on" in body`); chave **presente** (mesmo `""`/`null`) = sincroniza para o valor (vazio = remoção explícita de todas). O replace-all que fica (chave presente) mantém dedup + canonização + propagação pós-DELETE + rollback explícito que já estão na main (D27 vira não-regressão testada) *(evita: o wipe silencioso por body parcial — o análogo de `depends_on` do defeito C1; e quebra de compat com import CSV/scripts que enviam a chave de propósito)*.

**Decisão 3 — `trigger_por_dependencia` sai da tela e ganha a MESMA semântica parcial:** o checkbox some (obsoleto desde a F3 — ter dependência JÁ significa ser disparado por ela), o front para de enviar, e o `register` **preserva o valor atual quando a chave está ausente** (hoje `int(body.get(...,0))` zeraria). Motivo de não simplesmente zerar: num deploy API-antes-de-`dags/`, zerar a coluna de um pipeline que em produção depende do modo Dataset faria a próxima regeneração com o factory ANTIGO emitir sensor — os defeitos QA1/QA2 de volta pela porta do deploy. A coluna morre de verdade na migration de limpeza (§10.2 da spec), não aqui *(evita: hazard de ordem de deploy; e o checkbox que prometia comportamento que a F3 já tornou automático)*.

## 2. `DependenciasModal` — anatomia, reuso e busca

### 2.1 O que reusa (respondendo "reusar o quê do MalhaEditor/F7")

- **`ui/Autocomplete`** NÃO é a peça central aqui (ele é um campo de 1 valor; o modal é seleção múltipla com lista rica) — o que se reusa dele é o **padrão de busca server-side** (`/pipelines?limit=…&filter_name=`), e a estrutura visual do modal antigo (`f233da3`: busca + filtro de projeto + lista com projeto/INATIVO + chips), que a revisão aprovou como UX.
- **`criaCiclo` de `components/etapas/layoutGrafo.ts`** (módulo puro extraído na F8) — validação client-side de ciclo, agora sobre o **grafo global**: o modal monta as arestas a partir do endpoint novo (§4 — `data[].predecessores` é literalmente o grafo inteiro) e marca candidato que fecharia ciclo como **desabilitado com a explicação**, em vez de deixar o erro para o Aplicar.
- **Mensagens literais do servidor**: `msgCiclo()`/`MSG_SELF` do MalhaEditor viram módulo compartilhado (`components/malhas/mensagensDependencia.ts`) importado pelos dois — cliente e servidor falam o MESMO texto (aceite da F8, mantido); em erro real de servidor, o `detail` do 422 é exibido **inline no modal** (não só toast), ao lado do candidato/chip que o causou (aceite F5: "o modal mostra por que um pipeline não pode ser escolhido").
- O próprio pipeline **não aparece** na lista (auto-dependência impossível de escolher — como no modal antigo); pipeline INATIVO escolhido → aviso âmbar "enquanto seguir assim, este pipeline não vai ser liberado" (D33, texto do modal antigo).

### 2.2 Fonte dos candidatos — paginação, não teto (D28, responde a pergunta 7)

O clamp do servidor fica **intacto** (`list_pipelines`, `pipelines.py:460`: `limit = min(100, max(1, limit))` — é proteção legítima; o `limit=2000` da correção E era inerte por causa dele). O modal usa o **padrão que já existe em `Pipelines.tsx:46-64`**: loop de agregação `limit=100`/`offset` até `all.length >= total`, guarda de segurança 5000, `staleTime` de 60s. Filtro por nome/projeto aplicado client-side sobre o agregado (mesma escala da página de Pipelines, que já carrega tudo em toda visita). O `allPipes` atual do `PipelineFormModal` (`/pipelines?limit=200`, que o clamp reduz a 100 — **o defeito D28 existe HOJE no datalist**) morre junto com o datalist.

### 2.3 Estado atual das dependências (EDIÇÃO) e aplicação por diff

- Ao abrir em edição, o modal consulta `GET /pipelines/dependencias/estado` e usa a entrada do próprio pipeline: `predecessores[]` = as dependências **da tabela** (verdade, não o CSV), cada uma com o status da última execução na data corrente → o chip ganha o badge de estado do predecessor (entregável da spec: "estado da última execução de cada predecessor"; estilos de `statusExecucao.ts`, F9). Sem 067 → banner âmbar do padrão MalhaEditor + edição de dependências desabilitada (o POST daria 503 de qualquer forma) + chips derivados do CSV espelho, somente-leitura.
- **Confirmar aplica o DIFF, aresta a aresta**: `adicionadas = escolhidas − atuais` via `POST /dependencias`, `removidas = atuais − escolhidas` via `DELETE /dependencias` — o mesmo laço com tratamento por item do `confirmarExclusao` do MalhaEditor (404 = já não existia → segue; 422 = mostra o texto do servidor no item e mantém o modal aberto; sucesso parcial é relatado como "2 de 3 aplicadas"). Cada aresta é atômica no servidor (tabela + espelho CSV na mesma transação — F8); não existe estado "DELETE commitado sem INSERT" por construção.
- Consequência honesta, dita na tela: em edição a dependência é aplicada **na hora**, independente do "Salvar alterações" do wizard (mesma linguagem do MalhaEditor: "dependência é real e global"). Cancelar o wizard depois NÃO desfaz — e o aviso de republicação (§7) já foi disparado pelos endpoints, então nada se perde.
- **D31**: `{depsModalAberto && <DependenciasModal …/>}` no `PipelineFormModal` — montado só quando aberto; "Cancelar" descarta a seleção local; chip removido não ressuscita (o estado nasce do fetch a cada abertura).

### 2.4 Onde mora no wizard

A escolha migra de "Configurações Avançadas" (passo Notificações) para o passo **Agendamento** (decisão da 1ª F5, mantida) — com a semântica **corrigida pela F3**: o texto não diz mais "dependência substitui o agendamento", diz o que o motor faz: *"com dependência, o **horário** deixa de valer (o gatilho é a conclusão dos predecessores); as restrições de **DIA** — semanal, mensal, dias úteis, calendário — continuam valendo"* (D03/D04). Com dependência escolhida: campos de HORA ficam inertes (visíveis, desabilitados, com a explicação), campos de DIA continuam editáveis, e a simulação "Próximas execuções" é substituída por "disparo pelos predecessores: A, B".

## 3. Campos de janela e virada — round-trip completo (D26, D34, D35; responde a pergunta 2)

### 3.1 GET devolve (a metade que faltava)

`list_pipelines` ganha o bloco `janela_cols` da correção C, ressuscitado tal qual (`git show 6e1d15a`): guard por `INFORMATION_SCHEMA.COLUMNS('hora_virada')` → `CONVERT(VARCHAR(5), col, 108)` para os três, senão `NULL AS …` — padrão idêntico aos blocos 013/017/018/024/031 do próprio arquivo. O tipo `Pipeline` (TS) declara `hora_virada`/`nao_iniciar_antes`/`hora_limite_dependencia` como `string | null` — **sem cast** (`as unknown as Record<string,string>` foi o que escondeu o defeito do tsc na 1ª execução; lição gravada).

### 3.2 `register` grava parcial e normalizado

- Só escreve os três quando a **chave veio no body** (princípio 2; UPDATE montado dinamicamente só com as colunas presentes). O `InactivateModal` (body parcial, `PipelineModals.tsx:306-337`) não precisa mudar para os três — a ausência protege; ele **perde a chave `depends_on`** (Decisão 2) e pronto: **inativar não zera NADA** — é o teste de round-trip do D26.
- Normalização `_parse_hora_opcional`: `HH:MM`/`HH:MM:SS` válidos → `HH:MM:SS`; `""`/`null` → `NULL` ("sem regra" ≠ "regra às 00:00", que geraria `JANELA_ESTOUROU` diário — D35 e decisão fechada §8 da spec); inválido → `NULL` **sem recusar o cadastro** (contrato D35), mas com aviso no payload de resposta (`avisos: [...]`) que o front mostra em toast — nunca silêncio.
- **Auditoria**: os três entram em `AUDIT_FIELDS` e no `_read_pipeline_record` (com guard de coluna); `_write_audit` passa a **pular campo ausente de `new_vals`** — sem isso, um body parcial auditaria "valor → vazio" falso.

### 3.3 Forma na tela (a nuance que a 1ª F5 errou)

- **`hora_virada` NÃO é campo de dependente** — é o rótulo ODATE do pipeline, e o caso motivador da spec é um **PAI** com virada 20:00 (que pode nem ter dependência). Ela aparece **sempre** no passo Agendamento ("Hora de virada do dia (ODATE) — opcional"), para qualquer pipeline.
- `nao_iniciar_antes` e `hora_limite_dependencia` são da liberação: **só aparecem com dependência** e são **limpos ao remover a última** (D34) — o form zera os dois no estado e envia `""` (chave presente → NULL no banco; "limpo de verdade", não configuração órfã). Aviso no gesto de remoção: "janela e hora-limite serão limpos".
- **Data de referência CALCULADA ao lado da virada (risco 4 da spec)**: helper TS puro e local (`calcularDataRef(agora, virada)` — 4 linhas, espelho declarado **display-only** da regra canônica; a autoridade continua sendo `dags/`→`api/services`), exibindo duas linhas ao vivo: *"agora ({HH:MM}) → data de referência {D}"* e a fronteira *"início ≥ {virada} conta para o dia seguinte"* — com o exemplo fixo da spec (virada 20:00 · 23:30 → dia seguinte). Divergência aqui seria cosmética por construção: o valor nunca decide nada.
- Junto de `hora_limite_dependencia`, o texto honesto da F4 (Decisão 10): *"ao passar da hora, o Orquestra **alerta e mantém pendente** — não bloqueia nem falha"*. Nenhum campo de UNTIL nasce aqui (§9).

## 4. `GET /pipelines/dependencias/estado` — o painel com o predicado do motor (D29; responde a pergunta 3)

### 4.1 Por que o endpoint da 1ª F5 divergia (o defeito a não repetir)

O endpoint revertido (em `f233da3`) computava pendência por `TOP 1 status ORDER BY COALESCE(e.inicio, e.criado_em) DESC` e `status != 'SUCESSO'` — três pecados de uma vez: "mais recente" em vez de EXISTS (um PULADO mais novo mascarava o SUCESSO do dia — B2/D14), `COALESCE(criado_em)` (a ordenação proibida — D15) e predicado paralelo ao do motor (N9/D29). O motor pergunta uma coisa só: `EXISTS(SUCESSO na data)` por predecessor (`dags/utils/dependencias.py:268-293`).

### 4.2 O port e a paridade

Módulo novo **`api/services/dependencias.py`** (services não importa routers — sem ciclo de import; `malhas.py` importa dele e devolve os helpers hoje inline):

```python
faltantes(cur, pipeline, data_ref) -> list[str]      # port EXATO do SELECT de liberado():
    # NOT EXISTS(... status='SUCESSO' na data) — placeholder ?, semântica idêntica
liberado(cur, pipeline, data_ref) -> tuple[bool, list[str]]
resumo_predecessores(cur, pipeline, data_ref) -> ...  # SÓ exibição — nunca decide (docstring da F4)
mais_recente_da_data(linhas) -> ...                   # a regra F9: (inicio is not None, inicio, execution_id)
virada_global(cur) / tabela_067(cur)                  # extraídos de malhas.py, reusados pelos dois routers
```

**Teste de paridade em dois níveis** (o precedente D29 exige mais que a F9, porque aqui há SQL):
1. **Paridade de predicado**: chama `dags/utils/dependencias.liberado` (carregado por caminho, técnica de `test_malhas_f9.py:410`) e `api/services/dependencias.liberado` contra cursores-dublê que **capturam** `(sql, params)`; normaliza whitespace e placeholder (`%s`→`?`) e exige **texto idêntico** — divergir o SELECT quebra a suíte antes de produção.
2. **Paridade de semântica**: a matriz do D20/D14/D21 (todas SUCESSO / uma falta / FALHA / PULADO intercalado / SUCESSO em outra data / exceção→não liberado) executada contra o dublê de banco estilo F9, nas duas árvores, com o MESMO resultado.

### 4.3 Contrato de resposta

```
GET /pipelines/dependencias/estado?data_referencia=YYYY-MM-DD    (auth: get_current_user)
{
  "data_referencia": "…",              # pedida, ou ODATE corrente (virada GLOBAL — mesma regra/aproximação do F9;
                                       #  pipeline com hora_virada própria usa o seletor de data — documentado)
  "migration_067_pendente": true?,     # degradação F9-style: data []
  "data": [{                           # um item por pipeline ATIVO com ≥1 dependência (tipo PIPELINE)
    "pipeline_name": "C",
    "liberado": bool, "faltantes": ["B"],          # EXCLUSIVAMENTE de services.dependencias (o port)
    "predecessores": [{"nome","status","sucesso_na_data"}],   # exibição (resumo), nunca decide
    "corrida": {status, execution_id, inicio, fim, disparado_por, motivo} | null,  # mais_recente_da_data
    "janela": {"hora_virada","nao_iniciar_antes","hora_limite_dependencia"},
    "eventos": [{tipo, detalhe, detectado_em}]      # etl_dependencia_evento da data
  }]
}
```

Detalhes: param `data_referencia` com 422 no formato ruim (padrão F9, não o 400/`date_ref` do endpoint antigo); rota declarada antes de qualquer futura `GET /pipelines/{nome}` (hoje não há colisão — registrado por teste de rota); **o motivo legível "esperando PIPE_B · data ref 01/08" nasce dos `faltantes`** — resposta direta ao aceite "o dashboard distingue aguardando de não executou, com o motivo".

**Decisão 4 — um único port em `api/services/dependencias.py` servindo TODOS os consumidores da API** (estado, malha §5, dashboard §5) *(evita: N9/D29 — painel × motor com predicados divergentes; D15 pela porta da API; e a proliferação de SQL inline que fez o endpoint da 1ª F5 nascer errado)*.

## 5. Dashboard e Malha — o que falta sobre a F9 (D32; responde a pergunta 4)

A F9 já entrega: nó colorido por status (incl. `AGUARDANDO_DEPENDENCIA` âmbar e `NAO_LIBEROU` roxo — `statusExecucao.ts`), painel de eventos da guardiã, seletor de ODATE. Faltam duas coisas, ambas alimentadas pelo predicado único:

1. **Tooltip com os faltantes na malha**: `get_malha_execucao` (malhas.py) ganha, para membro com corrida `AGUARDANDO_DEPENDENCIA`/`NAO_LIBEROU`, o campo aditivo `faltantes: [...]` (via `services.dependencias.faltantes` — mesmo predicado, custo de um NOT EXISTS por membro aguardando). `statusExecucao.ts` declara o campo opcional; `tituloExecucao` do MalhaEditor anexa *"aguardando: P1, P2"*. Contrato F9 intacto (campo novo opcional — front antigo ignora).
2. **Dashboard principal**: o dashboard deriva status de `etl_job_execution` (nível job — `dashboard.py:27-34`); pipeline aguardando dependência não tem job nenhum e hoje é indistinguível de "não executou". Entra um **painel "Aguardando dependência"** em `Dashboard.tsx`, alimentado por `GET /pipelines/dependencias/estado` (refetch 60s): lista dependentes cuja corrida está `AGUARDANDO_DEPENDENCIA`/`NAO_LIBEROU` — ou que têm `faltantes` sem corrida (pré-guardiã) — cada um com *"esperando {faltantes} · data ref {D}"* e link para a Malha em modo Execução. Painel **some** quando não há dependentes cadastrados ou quando `migration_067_pendente` (degrada sem quebrar — D32); estado vazio com malha saudável mostra "nenhum pipeline aguardando" (distinção explícita, não ausência).

**Decisão 5 — a Malha continua sendo a tela-lar do estado; o dashboard ganha só o resumo com motivo e link** *(evita: E4 — "aguardando dependência" sem consumidor; e o operador abrindo SQL para saber de quem o pipeline espera)*.

## 6. Preview do factory e ViewModal — a divergência registrada na F3 (responde a pergunta 5)

- `factory_preview` já lê a 067 para `depends_on` (fallback CSV com log), mas `_preview_cron` (`factory.py:102-144`) ignora dependência e devolve o cron — o preview promete um agendamento que a DAG gerada (F3 §4.2: `schedule=None`) não terá. Correção espelhando o padrão que o próprio arquivo já usa para `on_demand` (string, não estrutura nova): **com dependência → `"cron": "(sem agendamento — disparo pelos predecessores: A, B)"`**; e `warnings` ganha a linha correspondente. Caso `depends_on` só do CSV com 067 ausente → warning que espelha a recusa ruidosa do factory (F3 Decisão 6): *"dependência cadastrada mas migration 067 ausente — a geração desta DAG será recusada"*. `trigger_por_dependencia` sai do SELECT do preview (não decide nada desde a F3).
- **ViewModal** (`PipelineModals.tsx:28-30`) calcula cron client-side com `buildCron` — mesma mentira. Com `depends_on` preenchido: célula "Expressão CRON" mostra "— (disparo por dependência)" e "Horário" mostra "—" (mesmo tratamento já dado ao `on_demand`); célula "Depende de" mantém os pills. A "Revisão" do wizard remove o sufixo *"dispara por dependência (ignora horário)"* atrelado ao checkbox morto e mostra a linha de dependência com a semântica da F3 (§2.4).
- Teste unitário: preview com dependência em dublê → cron-string de dependente + warning; sem dependência → cron intacto byte a byte.

## 7. `markDagDirty` persistente (D30; responde a pergunta 6)

### 7.1 O buraco atual

O `dagDirtyRef` do `PipelineFormModal` (correção E) só vive **dentro do modal**: oferece "Publicar a DAG agora?" ao salvar — se o operador responde "Agora não", nada mais no produto lembra que a DAG no Airflow roda a configuração velha (badge segue "DAG ✓"). Pior: **dependência criada/excluída pelo MalhaEditor não marca nada** — e é a mudança que troca o `schedule` da DAG do dependente. Enquanto isso, a DAG velha roda por cron **e** é disparada por evento (o defeito E1 literal).

### 7.2 A marca vira estado do banco — migration 073

`sql/migrations/073_dag_config_pendente.sql` (idempotente, `COL_LENGTH`, etapa 6c): `ALTER TABLE dbo.etl_pipeline ADD dag_config_pendente BIT NOT NULL DEFAULT 0` (metadata-only no SQL Server; sem PRINT decisório — `migrate.py` descarta PRINT, D40).

Alternativas descartadas: (a) **reusar `dag_criada=0`** — semanticamente "nunca gerada": esconderia o botão Executar (`PipelineRow.tsx:86`), mentiria "DAG —" para DAG viva, e faria o próximo run global da factory **republicar sozinho** a configuração pendente, sem gesto do operador — publicação implícita é surpresa em produção; (b) **derivar por `updated_at`** — o register bumpa `updated_at` em mudança de cadastro puro (descrição) → falso-pendente crônico; (c) **manter só o ref do front** — morre com o modal e não cobre o MalhaEditor (o buraco do D30).

**Quem liga (=1)** — sempre `WHERE dag_criada = 1` (pipeline nunca publicado não tem versão velha rodando):
- `register_pipeline`: diff servidor `old_record` × valores novos sobre a constante `CAMPOS_QUE_AFETAM_DAG` (enumerada no router com comentário apontando o que o gerador consome: `schedule_*`, `scheduled_time`, `horarios_especificos`, `dias_semana`, `dias_horarios_mes`, `somente_dias_uteis`, `calendario_nome`, os três da janela/virada, `retries/retry_delay/max_active_runs/pool_name`, `envia_msg_*`, `ambiente`, `criticidade`, `dag_start_date`) — o servidor decide, não o ref do front (que continua existindo só para o prompt imediato).
- `POST`/`DELETE /dependencias` (malhas.py): liga para o **dependente** (`pipeline_name`) na mesma transação — o pai NÃO precisa regerar (F3 §2.2: o pai lê a tabela ao vivo; só o filho muda de `schedule`). A resposta ganha `dag_config_pendente: true` e o MalhaEditor/DependenciasModal anexam ao toast: *"a DAG de {X} precisa ser republicada (Pipelines ▸ Publicar nova versão)"*.

**Quem desliga (=0)**: o reconciliador da API (`services/dag_reconcile`) ao concluir a publicação disparada por `gerar-dag` (ele já persiste o `run_id` da factory e acompanha até a DAG ficar pronta — zera a flag no mesmo passo em que notifica). Limitação assumida e documentada: um `force_all` administrativo por fora da API não zera a flag (pendente falso até a próxima publicação via UI); a F6 pode ensinar o factory a zerar (a coluna degrada — anotado como pendência, não bloqueia).

**Onde aparece**: badge âmbar na `PipelineRow` ao lado do "DAG ✓" (*"publicação pendente"*, title explicando que a DAG no Airflow roda a versão anterior); pill no ViewModal; o gesto que regera é o **existente** ("Publicar DAG"/"Publicar nova versão" — GenDagModal), nenhum fluxo novo. Sem a 073, GET devolve `NULL` e o front não renderiza nada (degradação limpa).

**Decisão 6 — pendência de publicação persistida em coluna própria, ligada pelo servidor nas DUAS portas, desligada pelo reconciliador** *(evita: E1/D30 — DAG rodando por cron E por evento sem ninguém saber; a publicação implícita do reuso de `dag_criada`; e a marca que morre com o modal)*.

## 8. Migrations, degradação e riscos

**Migration nova: só a 073** (§7.2). A 067 (colunas de janela, tabelas) e a 071/072 já estão aplicadas no dev; nada mais de DDL.

| Risco | Mitigação |
|---|---|
| Deploy parcial: API F5 sem a 067 | GET degrada os três para NULL (guard); register não grava (chave presente sem coluna → try/except com log, padrão do arquivo); modal trava edição com banner (503 do POST); estado devolve `migration_067_pendente` |
| Deploy parcial: API F5 sem a 073 | Guard de coluna em register/malhas/reconciliador — flag simplesmente não existe; comportamento = hoje |
| API F5 antes de `dags/` F3 em produção | Decisão 3 (não zerar `trigger_por_dependencia`); o resto da F5 é leitura/cadastro — não muda execução |
| Espelho CSV × tabela divergirem | Ambas as portas escrevem tabela+CSV na MESMA transação (F8 e register); o modal em edição lê a TABELA (estado), não o CSV |
| `estado` custoso em malha grande | Uma query de grafo + um NOT EXISTS por dependente (serve-se de `ix_pipe_exec_cond`); refetch 60s no dashboard; sem N+1 (agregação em Python, padrão malhas.py) |
| Paridade "de texto" quebrar por refactor legítimo em `dags/` | O teste falha ruidosamente e obriga a espelhar — é o comportamento desejado (o canônico é `dags/`, docstring do port) |

## 9. O que a F5 NÃO faz

- **Não toca `dags/`** — nenhuma DAG, nenhum factory, nenhuma guardiã; zero cenário de motor. O único gesto de geração é a publicação de validação do D30 no dev.
- **Não aposenta SP/CSV/`trigger_por_dependencia`** (F6 + migration de limpeza §10 da spec) — o espelho CSV continua sendo escrito nas duas portas.
- **Não cria UNTIL de hora** (Decisão 10 da F4 respeitada — a tela diz "alerta, não trava"); não cria OR/expressões nem job→job (§2/§9 da spec); não faz backfill nem reprocesso em massa.
- Não muda o clamp de `list_pipelines` (paginar é o contrato); não redesenha o wizard além do passo Agendamento; não cria canal de Teams nem config nova de guardiã.
- Não decide liberação em lugar nenhum da API — `liberado()` portado é **leitura**; quem dispara continua sendo push/guardiã (comentário do endpoint, herdado do antigo, que nisso estava certo).

## 10. Testes unitários (pytest com dublê de banco estilo `test_malhas_f9.py`; tsc + eslint + build baseline)

1. **Round-trip D26**: register com os 3 → GET devolve os 3; register SÓ com descrição (chaves ausentes) → colunas intactas; body do InactivateModal real (sem as chaves, sem `depends_on`) → janela E tabela de dependências intactas; register com `hora_virada: ""` → NULL; inválida → NULL + `avisos` no payload.
2. **Parcialidade de `depends_on`**: chave ausente → zero DELETE/INSERT na 067 e CSV intacto; presente vazio → remoção explícita; presente com lista → replace-all com dedup/canonização (D27 não-regressão: os testes de `deduplicar`/propagação-pós-DELETE/rollback explícito).
3. **`trigger_por_dependencia`**: ausente do body → valor preservado (anti-hazard da Decisão 3).
4. **Paridade D29** (os dois níveis do §4.2): SQL capturado idêntico módulo-a-módulo (normalizado `%s`→`?`); matriz semântica D14/D20/D21 igual nas duas árvores; **ausência estrutural**: nenhum `COALESCE(inicio, criado_em)` e nenhum `ORDER BY criado_em` no fonte de `api/services/dependencias.py` nem no endpoint (o teste de ausência que o D15 consagrou).
5. **Endpoint estado**: rota registrada; 422 de data; degradação sem 067; `faltantes` com PULADO intercalado + SUCESSO na data → liberado (o caso que o endpoint antigo errava); `corrida` pela regra F9 (empate por `execution_id`); eventos da data; janela devolvida.
6. **Malha/execução**: `faltantes` aditivo só em AGUARDANDO/NAO_LIBEROU; contrato F9 anterior inalterado (testes existentes verdes).
7. **Preview**: dependência → cron-string de dependente + warning; CSV sem 067 → warning de recusa; sem dependência → resposta byte-idêntica ao HEAD.
8. **073/flag**: migration 2× sem erro; register com mudança de agendamento → flag 1 (e mudança só de descrição → 0); POST/DELETE dependência → flag no dependente, nunca no pai; `dag_criada=0` → nunca liga; reconciliador zera; degradação sem a coluna.
9. **Auditoria**: os 3 em AUDIT_FIELDS; `_write_audit` pula chave ausente (sem falso "→ vazio").
10. **tsc**: tipo `Pipeline` com os campos novos SEM cast; build com `dist/` commitada; tokens `canvas/panel/edge/ink` nos dois temas nas peças novas (aceite F5).

## 11. Cenários de validação no dev (API viva :8000 + UI :8090 + banco `orquestra_dev` — smoke de contrato + revisão, como F7/F8; SEM DAG rodando, exceto V9)

| # | Cenário | Prova |
|---|---|---|
| V1 | Criar pipeline novo escolhendo 2 dependências no modal → register cria; `SELECT` na 067 = 2 linhas canonizadas; CSV espelho igual | Decisão 1 (criação), D33 |
| V2 | Editar: adicionar 1 e remover 1 pelo modal → 1 POST + 1 DELETE; tabela E CSV coerentes; toast de republicação | Decisão 1 (edição), §2.3 |
| V3 | Tentar ciclo no modal (grafo global com nó de fora da malha) → candidato desabilitado com a mensagem; forçar via API → 422 com o MESMO texto | D24 não-regressão, aceite F8/F5 |
| V4 | Escolher predecessor INATIVO → aviso âmbar; o próprio pipeline não aparece na lista | D33 |
| V5 | Preencher janela+virada; editar SÓ a descrição; **inativar** pelo diálogo → `SELECT hora_virada, nao_iniciar_antes, hora_limite_dependencia` intactos e 067 intacta | **D26** (o teste-régua da causa C) |
| V6 | Remover a última dependência → janela/limite limpos no banco (NULL); `hora_virada` PERMANECE | D34, §3.3 |
| V7 | Semear `etl_pipeline_execucao` (harness F9): PULADO mais recente + SUCESSO na data → `GET …/estado` mostra liberado, predecessor com status de exibição PULADO — painel e motor contando a mesma história | **D29** vivo |
| V8 | Dashboard e Malha com corrida AGUARDANDO semeada → painel "Aguardando dependência" com "esperando P · data D"; tooltip do nó com faltantes; sem 067 (sp_rename) → tudo degrada sem quebrar | **D32** |
| V9 | Editar dependência → badge "publicação pendente"; "Publicar nova versão" → arquivo gerado com `schedule=None`, badge some | **D30** (a única publicação real) |
| V10 | Modal: abrir → fechar em Cancelar → reabrir: seleção re-hidratada do servidor, nada congelado; chip removido não ressuscita | **D31** |
| V11 | Ambiente com >100 pipelines (semear nomes): o modal lista além do centésimo; busca encontra o 150º | **D28** |
| V12 | Preview e ViewModal de um dependente: "(sem agendamento — disparo pelos predecessores)"; sem dependência: cron de sempre | §6 |

## 12. Mapa decisão → defeito histórico

| Decisão | Defeito que evita |
|---|---|
| 1. Híbrido: criação via register (tabela vazia), edição aresta a aresta pela F8 | C2/D27 — replace-all destrutivo com tela 200; "A,A,B" perdendo o B |
| 2. `depends_on` parcial (ausente = não toca) | o wipe por body parcial — a classe C1 aplicada às dependências (aberta na main HOJE) |
| 3. `trigger_por_dependencia` fora da tela, valor preservado | hazard de deploy API-antes-de-dags ressuscitando o sensor (QA1/QA2) |
| 4. Um port em `api/services/dependencias.py` + paridade de SQL e semântica | N9/D29 painel≠motor; D15 (`COALESCE(criado_em)`) e B2/D14 ("mais recente") na API |
| 5. Malha = tela-lar; dashboard = resumo com faltantes e link | E4/D32 — "aguardando" sem consumidor; operador no SQL |
| 6. `dag_config_pendente` (073) ligado pelo servidor nas duas portas | E1/D30 — DAG velha rodando por cron E evento; marca que morria com o modal; MalhaEditor fora do radar |
| GET devolve os 3 + tipo TS sem cast | C1/D26 — write-only que zerava a virada a cada save |
| Vazio→NULL, inválido→NULL com aviso | D35 — "regra às 00:00" fantasma gerando alerta diário |
| Janela/limite gateados por dependência; `hora_virada` universal | D34 sem matar o caso motivador (PAI com virada 20:00, sem dependência própria) |
| Paginação agregada (padrão Pipelines.tsx), clamp intacto | E3/N8/D28 — `limit=2000` inerte; pipeline nº 101 inescolhível |
| Modal condicional + re-hidratação por fetch | E2/D31 — seleção congelada do primeiro mount |
| Mensagens de ciclo em módulo compartilhado, servidor autoridade | mensagens cliente≠servidor (aceite F8); explicação de ciclo/self no próprio modal (D33) |

**Arquivos tocados na implementação:** `api/routers/pipelines.py`, `api/routers/malhas.py`, `api/routers/factory.py`, `api/services/dependencias.py` (novo), `api/services/dag_reconcile.py`, `sql/migrations/073_dag_config_pendente.sql` (nova), `ui-react/src/components/pipelines/DependenciasModal.tsx` (novo), `PipelineFormModal.tsx`, `PipelineModals.tsx`, `PipelineRow.tsx`, `ui-react/src/components/malhas/{MalhaEditor.tsx, statusExecucao.ts, mensagensDependencia.ts (novo)}`, `ui-react/src/pages/Dashboard.tsx`, `ui-react/src/types/pipeline.ts`, `tests/` (novos + baseline). **Nenhuma mudança em `dags/`.** PR: `feat: cadastro e visão de dependências` (retomada F5). Deploy: 073 na etapa 6c + api + front; **não exige regerar DAGs** (a F5 não muda geração — o preview/flag apenas relatam); revisão adversarial antes da PR, regra da casa.
