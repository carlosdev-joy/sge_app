# Spec: RITM × SCTASK — um card por trabalho
Projeto: Orquestra (`carlosdev-joy/sge_app`) · Data: 2026-08-21 · Status: **rascunho**

Origem: documento `spec_089_ritm_sctask.html` (bancada do usuário). O documento
foi escrito contra um **snapshot antigo** do repositório; a §0 registra o que
dele já está entregue, o que mudou de nome e o que estava errado. O escopo
executável desta spec é o que sobrou — que não é pouco, e é justamente a parte
que ninguém fez.

---

## 0. O que o documento de origem propunha × o repositório de hoje

| O documento dizia | Hoje na `main` | Consequência para esta spec |
|---|---|---|
| Criar migration **089** com `parent_sys_id` | A 089 é `089_servicenow_proxy.sql`. O parentesco entrou na **090** (`090_chamado_parentesco.sql`, PR #312) como **`pai_sys_id` + `pai_numero`** — e ainda `estado_cru` | **Nenhuma migration nova em F1/F2.** A camada de dados está pronta e é mais rica que a proposta (guarda o número, não só o sys_id) |
| Índice **filtrado** `WHERE parent_sys_id IS NOT NULL` | `IX_etl_chamado_pai` **sem filtro**, deliberadamente | O documento reproduziria um defeito já pago: índice filtrado exige `QUOTED_IDENTIFIER ON` em todo DML, e o `sqlcmd` das migrations roda com **OFF** — mediu-se `Msg 1934` no dev, com a migration parando no meio e todo DML posterior na tabela quebrando (enquanto o `pymssql` da DAG seguiria verde) |
| Editar `dags/etl_servicenow_sync.py`, função `_fetch_tabela`, campo `request_item` | A normalização mudou de casa: está em **`dags/utils/servicenow_sync.py`**, com `CAMPOS` já pedindo `parent,request_item` e a função `_pai()` resolvendo a precedência (`request_item` manda sobre `parent`) | **Nada a fazer na DAG** para o parentesco. Os testes de `tests/test_servicenow_sync.py` §8 já cobrem |
| MERGE editado à mão em dois ramos | O MERGE é **gerado** a partir da tupla `CAMPOS_UPSERT` (uma fonte só para UPDATE, INSERT e params), e `pai_sys_id`/`pai_numero` já estão lá | O alerta do documento ("alinhar as duas listas") deixou de existir por construção |
| Endpoint `GET /chamados/{sys_id}/tasks` | Não existe | **Descartado**: a fila inteira já viaja numa resposta só (dezenas de itens). Uma ida ao servidor por card seria N+1 sem ganho — o agrupamento sai de graça no mesmo `SELECT` |
| Backlog B3: alerta de frescor 6h × ciclo de 3h | Resolvido: `FRESCOR_ALERTA_MINUTOS = 60` para cadência de 15 min, com `tests/test_servicenow_cadencia.py` recusando a combinação incoerente | Fora do backlog |
| Backlog B1: desativação por `sync_em < -10min` | Já é `sync_em < inicio` (carimbo do ciclo) **e** restrita a `tipos_ok` | Atenuado; permanece no backlog em versão corrigida |

**O que sobrou de verdade:** o parentesco está no banco desde a #312 e
**nada acima do banco o usa**. A API não devolve as colunas, a fila desenha
dois cards para o mesmo trabalho e os indicadores contam os dois.

Existe ainda a branch preservada **`feat/chamados-card-unico` (`c665335`)**, da
PR **#315 fechada a pedido**: ela resolvia isto, mas contra a tela anterior às
derivações (091/092) e à triagem (093). O código dela é insumo — não merge.

---

## 1. Visão

No ServiceNow todo RITM do catálogo gera uma `sc_task` filha. O espelho traz as
duas como linhas irmãs e a tela desenha **dois cards para o mesmo trabalho**:
medido em produção, **113 itens na fila para ~60 trabalhos** — 49 de 49 tasks
ativas com o pai também na fila.

Quem olha a tela não consegue responder "quantos pedidos estão abertos?" sem
dividir de cabeça, e a aba Indicadores repete o mesmo inchaço em todo gráfico.

Quando esta spec estiver pronta, **o card é o trabalho**: o pedido (RITM) é o
card, a execução (SCTASK) é uma linha dentro dele, a contagem para de dobrar e
a aba Indicadores diz o mesmo número que a aba Fila.

---

## 2. Escopo

**IN**
- `GET /chamados` devolve `pai_sys_id`, `pai_numero`, `estado_cru` e **agrupa** o filho dentro do pai, com `registros` (o denominador honesto) ao lado de `total`.
- Tela `/chamados`: a tarefa vira linha `↳` dentro do card do pedido; busca, filtros e as opções dos selects passam a enxergar o filho; o cabeçalho diz "N na fila" com "M registros" ao lado.
- Task **órfã** (com `pai_sys_id` que não está no espelho) continua sendo card próprio, **sem marca visual** (decisão do usuário: a regra da instância garante que toda `sc_task` tem o RITM pai na mesma fila, então órfã não deveria existir). O código não a esconde mesmo assim: se ela aparecer, é **sintoma** de defeito no filtro de grupo — e sumir com o sintoma seria falso verde.
- `GET /chamados/indicadores` e `GET /chamados/historico` aplicam o **mesmo recorte** em SQL — **todos** os indicadores passam a contar trabalhos, inclusive a carga por responsável — com teste de paridade contra a fila e teste anti-drift que recusa agregação nova sem o predicado.

**OUT (explícito)**
- **Escrever no ServiceNow** — a v1 é somente leitura (decisão da spec 088); nada aqui muda isso.
- **Botão "Sincronizar agora"** (`POST /chamados/sincronizar`) — retirado do escopo por decisão do usuário (2026-08-21): mexe em `dags/` e em migration, e a janela de deploy de `dags/` já deve a triagem (#324) e a F0 do ciclo fechado (#303). Volta ao backlog com o resto de `c665335`.
- **Janela de histórico no `sysparm_query` + guarda `pertence_ao_grupo`** — o filtro só-por-grupo traz ~3.376 registros por ciclo (medido) para uma fila ativa de 113. É problema de **volume do sync**, não de hierarquia; o código existe em `c665335` e merece spec própria.
- **Paginação no `GET /chamados`** (B2 do documento de origem) — com o agrupamento a fila encolhe ~45%; segue no backlog.
- **Hierarquia de mais de um nível** (task de task): `_agrupar_por_pai` é de um nível só, por decisão. Um segundo nível aninhado esconde trabalho dentro de trabalho.
- **Drag-and-drop no kanban** — continua fora, pela mesma razão de sempre: prometeria uma escrita que não existe.
- **Endpoint por card** (`/chamados/{sys_id}/tasks`) — descartado na §0.

---

## 3. Arquitetura proposta

**Back** — `api/routers/chamados.py` (árvore `api/`, placeholder pyodbc `?`):
- `_agrupar_por_pai(chamados)` em Python, para a **fila**: a tela precisa dos dois registros (o pai para o card, o filho para a linha), então o recorte não pode ser um `WHERE` — seria jogar fora o que a tela vai mostrar.
- `_so_trabalhos(entre_ativos)` em SQL, para as **agregações**: elas só contam, nunca mostram o filho. Fazer o agrupamento em Python aqui significaria trazer a tabela inteira para contar linha.
- As duas regras dizem a mesma coisa por caminhos diferentes — e é exatamente por isso que a F2 traz um **teste de paridade**: sem ele, a aba Indicadores pode dizer 113 enquanto a Fila diz 60, e as duas "estarem certas".

**Front** — `ui-react/src/pages/Chamados.tsx`: sem componente novo e sem
biblioteca nova. `CardChamado` ganha o bloco de filhos; `casaBusca`, `opcoes` e
`filtrados` passam a considerar `[pai, ...filhos]`. Tokens da casa
(`canvas/panel/edge/ink/dim`) nos dois temas; o `dist/` é versionado e o
rebuild entra na mesma PR.

**Dados** — **nenhuma migration nesta spec**: a 090 já entregou tudo que as duas
fases usam. Nada a aplicar na etapa 6c do `deploy.sh`.

**Orquestração** — **nada em `dags/`**. As duas fases vivem em `api/` e
`ui-react/`, o que mantém esta entrega fora da janela de restart do worker que
a triagem e o ciclo fechado ainda devem.

**Decisões e alternativas descartadas**
- *Agrupar no front, deixando a API plana* — descartado: os indicadores são agregados em SQL de qualquer forma, e a regra ficaria escrita em três lugares (front, SQL, e o `historico`) em vez de dois com teste de paridade.
- *Flag `?agrupar=1` para separar a fase da API da fase da tela* — descartado: enquanto a flag estivesse desligada nada mudaria, e ligada ela nunca mais sairia. F1 entrega os dois lados juntos porque é **um contrato só**.
- *Esconder a task órfã* — descartado: perderia trabalho de vista, o oposto do que a mudança existe para fazer.
- *`WHERE tipo <> 'task'` como recorte* — descartado: mata a task órfã e a task de incidente junto.

---

## 4. Modelo de dados

**Nenhuma alteração de schema em toda a spec.** As duas fases usam o que a
migration 090 já criou:

| Coluna | Tipo | Origem |
|---|---|---|
| `pai_sys_id` | `VARCHAR(32) NULL` | `sc_task.request_item.value` (fallback `parent`) |
| `pai_numero` | `VARCHAR(20) NULL` | o mesmo campo, `display_value` (`RITM0096880`) |
| `estado_cru` | `VARCHAR(20) NULL` | `state.value` — o número, ao lado do rótulo |

Índice `IX_etl_chamado_pai` sobre `pai_sys_id`, **não filtrado** (§0).

---

## 5. Fases

### F1 — Um card por trabalho (API + tela)

- **Entregável:** a fila mostra o pedido e a execução num card só, com o denominador visível.
- **Inclui:**
  - `chamados.py`: `pai_sys_id`, `pai_numero`, `estado_cru` no `SELECT` e no dict de cada linha; `_agrupar_por_pai()`; `registros` na resposta.
  - As três colunas entram no **bloco degradável** (o mesmo `try` de duas tentativas que hoje protege as 091/092), não no `base`. Num ambiente sem a 090 a fila continua plana e servida, em vez de virar "sistema em atualização".
  - `Chamados.tsx`: `pai_sys_id`/`pai_numero`/`estado_cru`/`filhos` na interface `Chamado`; bloco de filhos em `CardChamado` (número com link para a origem, badge do tipo, estado da tarefa **sempre** — é ele que responde "o pedido está aberto, mas alguém já pegou?" — e o responsável **só quando diferir** do pai); `casaBusca`, `opcoes` e `filtrados` passando a olhar `[pai, ...filhos]`; badge do cabeçalho com "M registros" quando `registros > total`.
  - Rebuild do `dist/`.
- **Critérios de aceite:**
  - Dado um RITM ativo com uma `sc_task` ativa apontando para ele, quando a fila carrega, então aparece **um** card, com a task como linha `↳` dentro dele.
  - Dada uma task cujo `pai_sys_id` não está no espelho (órfã), então ela continua como card próprio na coluna do seu estado — sem selo especial, mas **presente**.
  - Dado um registro com `pai_sys_id == sys_id` (auto-referente), então ele aparece na fila como raiz — nunca some.
  - Dado o número de uma SCTASK digitado na busca, então o card do RITM que a contém é encontrado.
  - Dado o filtro Tipo = "Tarefa", então os cards cujos **filhos** são tarefas continuam visíveis (e "Tarefa" continua na lista de opções).
  - Dada a fila com 113 registros e 60 trabalhos, então o cabeçalho diz `60 na fila` e `113 registros`.
  - Dado um ambiente sem a migration 090, então a fila aparece plana, sem erro e sem "sistema em atualização".
  - A ordem das raízes e a dos filhos dentro de cada card seguem a da query (`aberto_em DESC`).
- **Validação:** `pytest` (baseline do HEAD — zero falhas **novas**; hoje há 5 pré-existentes), `tsc` + `eslint` comparados com o HEAD, `npm run build`.
- Revisão adversarial multi-agente antes da PR. PR: `feat: um card por trabalho na fila de chamados`.

### F2 — Indicadores e histórico contam a mesma coisa que a fila

- **Entregável:** nenhuma superfície do produto conta o mesmo trabalho duas vezes.
- **Inclui:**
  - `_so_trabalhos(entre_ativos)` e sua aplicação nas agregações de `/chamados/indicadores`: aging, tipo × estado, fluxo de entradas × saídas (com `entre_ativos=False` — o pai pode já ter saído da fila), carga por responsável, `total_ativos`, `por_tipo_demanda`, `por_categoria` + `sem_categoria`, `resolvidos_periodo`, `triagem` (veredito × origem) e os dois contadores de erro de triagem.
  - `/chamados/historico`: mesmo recorte, com `entre_ativos=False`.
  - **Teste de paridade:** o `total_ativos` dos indicadores é igual ao `total` da fila, sobre o mesmo conjunto de linhas.
  - **Teste anti-drift:** varre as execuções de `SELECT … FROM dbo.etl_chamado` do módulo e exige o predicado em toda agregação — agregação nova sem ele **reprova** (o mesmo remédio que `RBAC_RECURSOS` e o inventário de DAGs usam).
  - **Carga por responsável entra no mesmo recorte, sem tratamento especial** (decisão do usuário: na instância deles o responsável da task e o do RITM são sempre o mesmo). A premissa fica dita no comentário do código, junto do que acontece se ela quebrar: o trabalho passaria a contar para o dono do RITM. O sintoma é visível na F1 — a linha `↳` mostra o responsável do filho justamente quando ele **difere** do pai.
  - `ChamadosIndicadores.tsx`: o subtítulo diz que a contagem é de trabalhos, não de registros.
- **Critérios de aceite:**
  - Dada a fila com 60 trabalhos, então `total_ativos` dos indicadores é 60 — não 113.
  - Dada uma task órfã ativa, então ela **conta** nos indicadores (é trabalho real).
  - Dado um RITM e sua task com responsáveis diferentes, então a carga conta **1**, para o responsável do RITM — e o card da fila mostra o nome divergente na linha `↳`, que é como a premissa quebrada aparece.
  - Dado um RITM já encerrado com task encerrada na janela, então o fluxo de saídas conta 1, não 2.
  - Dada uma agregação nova sem o predicado, então o teste anti-drift falha nomeando a query.
  - O histórico de resolvidos não lista o pedido e a tarefa como duas entregas.
- **Validação:** idem F1.
- Revisão adversarial multi-agente antes da PR. PR: `feat: os indicadores de chamados contam trabalhos, nao registros`.

> **Duas fases, e só.** O "Sincronizar agora" era a F3 e saiu do escopo por
> decisão do usuário (§2 OUT). Com isso a spec inteira fica sem migration e sem
> `dags/` — nada aqui depende da janela de restart do worker.

---

## 6. Riscos e mitigações

| # | Risco | Impacto | Mitigação |
|---|---|---|---|
| 1 | **Agrupamento esconde chamado.** Auto-referência (`pai_sys_id == sys_id`) ou par mutuamente apontado faria o card sumir da fila **sem erro nenhum** | Alto — trabalho invisível é pior que trabalho duplicado | Guarda `pai is not c`; só o **filho** entra no pai (nunca o contrário); órfã permanece raiz; critério de aceite dedicado a cada caso |
| 2 | **Fila e Indicadores discordarem.** A regra existe em Python (fila) e em SQL (agregação); as duas podem divergir e ambas parecerem certas | Alto — número de gestão errado sem sintoma | Teste de **paridade** entre `total` e `total_ativos` + teste **anti-drift** que reprova agregação nova sem o predicado |
| 3 | **Ambiente sem a migration 090** (dev recém-criado, ou 6c pulada) | Médio — fila inteira viraria "sistema em atualização" | As colunas novas entram no bloco degradável; sem elas a fila é servida plana, como hoje |
| 4 | **A premissa "mesmo responsável" quebrar.** A carga passa a contar pelo trabalho porque, na instância, task e RITM têm sempre o mesmo dono. Se um dia divergirem, o trabalho conta para o dono do RITM | Médio — gráfico de distribuição atribui a quem não executou | Premissa **escrita no comentário** da query, com o efeito de quebrá-la; a linha `↳` da F1 mostra o responsável do filho exatamente quando ele difere — o sintoma fica visível na tela antes de virar dúvida no gráfico |
| 5 | **`dist/` esquecida** na PR de front | Médio — PR "invisível" em produção | Rebuild no diff da F1; conferência do `dist/` no checklist da revisão adversarial |
| 6 | **Órfã aparecer** apesar da regra da instância | Baixo — um card a mais, e é informação | O código nunca a esconde (risco #1); se aparecer, é sinal de filtro de grupo trazendo task sem o RITM — investigar o `sysparm_query`, não a tela |

---

## 7. Smoke pós-deploy

a) Abrir `/chamados`. **Esperado:** cards de RITM com linha `↳ SCTASK…` dentro; nenhum card solto de SCTASK cujo RITM esteja na mesma tela.

b) Conferir o cabeçalho. **Esperado:** "N na fila" com "M registros" ao lado, `M > N`; passar o mouse mostra a explicação do agrupamento.

c) Rodar no banco: `SELECT COUNT(*) FROM dbo.etl_chamado WHERE ativo=1` e `… AND (pai_sys_id IS NULL OR pai_sys_id = '' OR pai_sys_id NOT IN (SELECT sys_id FROM dbo.etl_chamado WHERE ativo=1))`. **Esperado:** os dois números batem com "M registros" e "N na fila" da tela.

d) Digitar na busca o número de uma SCTASK visível numa linha `↳`. **Esperado:** o card do RITM aparece; a busca não volta vazia.

e) Filtrar Tipo = "Tarefa". **Esperado:** a opção existe e os cards com tarefa dentro continuam visíveis.

f) Abrir a aba Indicadores. **Esperado:** o total bate com o "N na fila" da aba anterior.

g) Rodar `SELECT COUNT(*) FROM dbo.etl_chamado WHERE ativo=1 AND tipo='task' AND pai_sys_id NOT IN (SELECT sys_id FROM dbo.etl_chamado)`. **Esperado:** zero — é o que a regra da instância garante. Se vier maior que zero, essas tasks aparecem como cards próprios na tela (correto) e o `sysparm_query` do sync merece investigação.

h) Conferir um responsável no gráfico de carga contra a fila filtrada por ele. **Esperado:** o número do gráfico é igual à contagem de cards da fila com aquele responsável.

i) Alternar tema claro/escuro na tela de chamados. **Esperado:** a linha `↳`, a borda do bloco de filhos e o texto do responsável divergente legíveis nos dois.

---

## 8. Decisões tomadas e backlog

**Decididas pelo usuário em 2026-08-21** (fechadas — estão aplicadas no texto acima):

1. **Carga por responsável** → segue o trabalho, sem tratamento especial: na instância, o responsável da task e o do RITM são sempre o mesmo, e **todos** os indicadores passam ao nível de trabalho. A premissa e o efeito de quebrá-la ficam ditos no código (risco #4).
2. **Task órfã** → sem marca visual: a regra da instância garante que a `sc_task` tem o RITM na mesma fila. O código continua não a escondendo, porque órfã que aparece é sintoma, não estado normal (risco #6, smoke g).
3. **"Sincronizar agora"** → **fora do escopo**, para não empilhar `dags/` e migration na janela que já deve a #324 e a F0 da #303. Com isso a spec fica sem migration e sem `dags/`.

**Ainda em aberto**

- Nenhuma. A spec está pronta para aprovação e execução.

**Backlog** (registrar, não executar):

- **`POST /chamados/sincronizar` + `disparado_por`** — pronto em `c665335` (as três recusas: integração desligada, credencial incompleta e **DAG pausada**, que é a traiçoeira: o Airflow aceita a run, devolve 200 e ela fica parada para sempre). Precisaria da migration `094` em `dbo.etl_chamado_sync` e de uma janela de `dags/`.

- **Herdado do documento de origem:**
   - **B1** — desativação por `sync_em < inicio`: um upsert que falhe no meio do ciclo deixa a linha com carimbo antigo e ela é desativada. Já é melhor que os `-10min` do documento (e restrita a `tipos_ok`), mas o recorte exato seria `sys_id NOT IN (ids do ciclo)`.
   - **B2** — paginação no `GET /chamados`.
   - **Volume do sync** — janela de histórico no `sysparm_query` + guarda `pertence_ao_grupo` (~3.376 registros/ciclo medidos); código pronto em `c665335`.
