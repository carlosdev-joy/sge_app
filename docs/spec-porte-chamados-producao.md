# Spec — Porte do módulo ServiceNow desenvolvido em produção

> **Status:** RASCUNHO, aguardando aprovação.
> **Origem:** foto de produção — `18046a8` (código) e `fe1376b` (schema completo,
> migrations, nginx e compose). Preservadas na tag local `foto-producao-20260827`
> e no bundle `/root/backups-orquestra/foto-producao-20260827.bundle`.
> A branch pública `backup/producao-20260827` foi **removida do GitHub** em 2026-08-27
> (levava `dump_prod.sql`, `producao_base.rpt` e `prod_info` para um repositório público).

## 1. O que aconteceu

Um módulo ServiceNow bem mais completo que o do repositório foi desenvolvido **direto no
servidor**. Ele não passou por PR, não tem migration no git e existe em um lugar só.

A foto trazida não é um branch de trabalho: seu commit pai é de **14/06**, e ela está
**806 commits atrás da `main`**. Contém, num commit único, três coisas misturadas — o
repositório como estava em junho, o que os deploys levaram depois, e o desenvolvimento
novo. Mesclá-la apagaria 495 arquivos que existem hoje na `main` (153 do front, 72
migrations, a suíte de testes).

Por isso o trabalho é **porte**, não merge.

## 2. Como o material foi separado do resíduo

Cada um dos 129 arquivos de `api/`, `dags/` e `ui-react/src` da foto teve seu conteúdo
comparado com **todas** as versões daquele caminho no histórico:

| Balde | Qtd | O que é | Destino |
|---|---|---|---|
| Idêntico à `main` | 64 | já temos | descartar |
| Bate com versão anterior | 42 | veio de deploy antigo, é defasagem de junho | descartar |
| **Não existe em versão nenhuma** | **23** | **feito à mão no servidor** | **portar** |

São **5.138 linhas**. O critério é objetivo: se o conteúdo exato já esteve no repositório
alguma vez, não é trabalho novo — é uma cópia velha que o `rsync` do deploy não atualizou.

## 3. O material

### API — `api/routers/chamados.py` (1.407 linhas, contra 554 na `main`)

**22 rotas contra as 4 de hoje.** As novas:

| Rota | O que entrega |
|---|---|
| `GET /chamados/dashboard` | painel em 4 visões: `geral`, `proprio` (pelo e-mail de quem está logado — usa a migration 093), `diaadia` e `iniciativa` |
| `GET /chamados/indicadores/historico` | série histórica por período (hoje / 30d / histórico) |
| `GET /chamados/{sys_id}/tasks` | as SCTASKs de um RITM |
| `GET /chamados/{sys_id}/detalhe` | conteúdo completo do chamado |
| `GET /chamados/{sys_id}/anexos/{id}` | proxy de anexo (o arquivo não passa pelo navegador do usuário direto) |
| `GET /chamados/categorias` | catálogo de categorias |
| `POST` / `DELETE /admin/servicenow/categorias` | CRUD de categoria |
| `GET` / `PUT /admin/servicenow/config` | configuração da integração |
| `POST /admin/servicenow/testar` | teste de conexão |
| `GET` / `POST` / `PUT /admin/servicenow/grupos` | CRUD de grupos |
| `GET /admin/servicenow/ciclos` | ciclos de sincronização |
| `POST /admin/servicenow/disparar-delta` | dispara o delta sob demanda |
| `GET` / `PUT /admin/servicenow/perfis-acesso` | perfis de acesso do módulo |

### DAGs — o motor de sincronização

- `dags/utils/servicenow_sync.py` (567 l.) — evolução da versão que temos
- `dags/utils/chamado_derivacoes.py` (164 l.) — idem
- `dags/etl_servicenow_full.py` (266 l.) — carga completa
- `dags/etl_servicenow_delta.py` (236 l.) — carga incremental
- `dags/etl_log_cleanup.py` (51 l.) — faxina de log
- `dags/.airflowignore`

### Testes — 11 arquivos, 1.417 linhas

Em `dags/tests/`, rodados à mão dentro do container. **Não são coletados pela suíte**:
o `pytest.ini` tem `testpaths = tests`. E **quatro colidem por nome** com testes que já
existem em `tests/` com conteúdo diferente (`test_chamados_api.py`,
`test_admin_servicenow.py`, `test_chamado_derivacoes.py`, `test_servicenow_sync.py`).

### Front — 3 arquivos aproveitáveis

- `ui-react/src/pages/Chamados.tsx` (691 l., contra 554 na `main`)
- `ui-react/src/components/ChamadoDetalheModal.tsx` (146 l.)
- `ui-react/src/lib/chamado.ts` (79 l.)

`App.tsx` e `nav.ts` da foto **não entram**: são a versão de junho adaptada para um
ambiente sem UI legada (`basename` removido, rotas próprias). A `main` já resolveu isso
por outro caminho, e seu `src` tem 182 arquivos contra os 34 da foto.

## 4. O banco — resolvido na segunda foto (`fe1376b`)

O código usa 9 tabelas que não tinham migration em lugar nenhum:

`etl_chamado_anexo` · `etl_chamado_ciclo` · `etl_chamado_nota` · `etl_indicador_meta` ·
`etl_indicador_snapshot` · `etl_indicador_snapshot_analista` ·
`etl_indicador_snapshot_grupo` · `etl_servicenow_grupo` · `etl_sn_categoria`

A segunda foto trouxe **`sql/migrations/000_schema_completo.sql`** — o schema real de
produção, 81 tabelas em DDL idempotente. **As 9 estão todas lá.** A F0 deixa de estar
bloqueada.

Vieram também 7 migrations da linhagem de produção: `089_chamados_parent`,
`093_chamados_atribuido_email`, `094_chamados_nota_anexo`, `095_chamados_anexo`,
`096_chamado_ciclo`, `097_indicador_snapshot`, `098_sn_grupo_gatilho`.

### 4.1 ⚠️ Duas linhagens de migration, com números que colidem

| Nº | Na `main` | Em produção |
|---|---|---|
| 089 | `089_servicenow_proxy.sql` | `089_chamados_parent.sql` |
| 093 | `093_chamado_triagem.sql` | `093_chamados_atribuido_email.sql` |

Os números batem, o conteúdo não. No porte, as de produção **entram renumeradas a partir
da 094** — a `main` já vai até a 093. E `dbo.etl_schema_version` rastreia por **nome**, o
que significa que produção terá as duas listas registradas: as da `main`, aplicadas pelo
deploy, e as da linhagem local.

### 4.2 A `089_chamados_parent` é migration morta — não portar

Ela adiciona `parent_sys_id` a `etl_chamado`. **Essa coluna não existe no schema de
produção** (zero ocorrências no `000_schema_completo.sql`): o banco real usa
`pai_sys_id` / `pai_numero` / `estado_cru`, que são as colunas da **`090` da `main`**.

Ou seja: as duas linhas resolveram o parentesco de formas diferentes, e a que sobreviveu
no banco foi a nossa. Portar a `089` de produção criaria uma segunda coluna para o mesmo
fato, com um índice a mais e nenhum leitor — a próxima pessoa que abrir a tabela teria
que descobrir sozinha qual das duas vale.


### 4.3 🔴 A `main` tem um defeito que produção já corrigiu — mapa de estados

Terceira foto (`7b95dd5`). Em `dags/utils/servicenow_sync.py`, tabela `sc_req_item`,
estado cru `"3"`:

| | Mapeia `"3"` para | Efeito na tela |
|---|---|---|
| `main` (hoje) | `aguardando` | RITM **concluído** fica parado na coluna Aguardando, para sempre |
| produção | `encerrado` | sai da fila (`ativo=0`) e continua no espelho para os indicadores |

No ServiceNow, `sc_req_item` state `3` é **Closed Complete**. O comentário de produção
registra a apuração: *"Confirmado em 2026-08-21: RITMs encerrados caíam em 'outros' e
desapareciam da tela em vez de aparecer na coluna Resolvido."*

**Produção está certa e a `main` está errada.** O porte traz essa correção — e ao trazer,
revisar também o `"4"` (Closed Incomplete), que a `main` e a produção mapeiam para
`aguardando`: pelo padrão do ServiceNow ele também é estado final.

### 4.4 O seed da configuração — e o que não pode ir para o repositório público

A terceira foto trouxe `099_servicenow_config_seed.sql` (MERGE idempotente, `WHEN NOT
MATCHED` apenas — não sobrescreve config existente) e um `.env.example`. **O desenho da
credencial está correto:** a senha não fica em env nem em migration; vai cifrada com
Fernet (`ORQUESTRA_CONN_KEY`) em `dbo.etl_app_config`, gravada pela tela
Admin > ServiceNow. As chaves são `servicenow_url`, `servicenow_usuario`,
`servicenow_senha_enc`, `servicenow_habilitado`, `servicenow_proxy` e
`servicenow_grupos`.

⚠️ Mas os dois arquivos levam **valores reais de infraestrutura** para um repositório
**público**: host e base do SQL Server, usuário do banco, a conta de serviço do
ServiceNow, o endereço do **proxy corporativo interno** e o nome do grupo. Não há senha
em lugar nenhum — o que existe é o mapa que torna uma senha útil.

**No porte, o seed entra com valores vazios**; os reais chegam pela tela Admin (que é o
próprio desenho documentado) ou pelo `.env` do servidor, que é gitignored.

### 4.5 `spec/spec_089_ritm_sctask.md` — documento superado

A terceira foto trouxe também a spec que originou a `089_chamados_parent`. Ela propõe
`parent_sys_id` e um endpoint `/chamados/{sys_id}/tasks` lendo por essa coluna. O que
venceu no banco foi `pai_sys_id` (nossa `090`), e o endpoint de produção lê por ele.
Fica como registro histórico: **não é backlog**.



### 4.6 A rota de salvar config descarta `proxy` e `grupos` em silêncio

`PUT /admin/servicenow/config` (produção) filtra o payload por uma lista fixa:

```python
_campos_validos = {"servicenow_url", "servicenow_usuario",
                   "servicenow_habilitado", "servicenow_senha_enc"}
for campo, valor in payload.items():
    if campo not in _campos_validos:
        continue          # ← servicenow_proxy e servicenow_grupos caem aqui
```

Quem editar o proxy ou o grupo de atribuição nessa tela recebe `{"ok": true}` e **nada
muda no banco**. Os dois campos são justamente os que mais mudam entre ambientes: o proxy
é obrigatório dentro da Caixa e precisa ser vazio fora dela; o grupo define a fila
inteira.

A `main` não tem esse defeito — ela grava por `servicenow_set`, que passa pelos dois
(`proxy_valido()` aceita vazio como rota direta, e `parse_grupos()` trata a lista). **No
porte, prevalece o caminho da `main`.**

### 4.7 A instância responde de fora da rede corporativa

Verificado em 2026-08-28 a partir da VPS: `cvpsnprod.service-now.com` resolve, o TLS sobe,
`GET /api/now/table/sc_req_item` devolve **401** sem credencial e a conta de serviço
**autentica com sucesso** pela sonda. Ou seja, **não há ACL por IP** na instância.

Duas consequências:

1. O ambiente dev consegue sincronizar contra a instância real, o que permite validar o
   porte com dado de verdade antes de qualquer coisa ir para produção — com
   `servicenow_proxy` **vazio**, porque `webproxycvp.adcorp.intranet` não resolve fora da
   rede da Caixa.
2. É mais uma razão para os dados de infraestrutura não circularem em repositório
   público (§4.4): a instância é alcançável da internet, e o que faltava ao conjunto
   publicado era só a senha.


## 5. Fases

### F0 — As 9 tabelas viram migrations `094`+ ✅ **destravada**

Fonte: `000_schema_completo.sql` da segunda foto (§4), conferido contra as 5 migrations
de produção que descrevem as mesmas tabelas (`094`–`098`). Uma migration idempotente por
assunto, renumerada a partir da `094`, rastreada em `dbo.etl_schema_version`.

- **Não portar a `089_chamados_parent`** (§4.2): `parent_sys_id` não existe no banco.
- **Aceite:** `migrate.py --dry-run` num banco limpo aplica tudo sem erro; reaplicar não
  altera nada; `sql/tests` cobre a criação.
- **Atenção:** índice filtrado (`CREATE INDEX ... WHERE`) falha no `sqlcmd` por
  `QUOTED_IDENTIFIER` e, se criado assim, quebra todo DML da tabela pelo `sqlcmd`
  enquanto o `pymssql` da DAG segue verde. A `089` de produção usa exatamente esse
  padrão — ao renumerar as outras, conferir uma a uma.

### F1 — O motor de sincronização

`servicenow_sync.py`, `chamado_derivacoes.py`, `etl_servicenow_full.py`,
`etl_servicenow_delta.py`, `etl_log_cleanup.py`, `.airflowignore`.

- **Traz a correção do mapa de estados (§4.3)** — é defeito vivo na `main`.
- Placeholders `%s` (pymssql) — `dags/` e `api/` usam dialetos diferentes, e trocar dá
  "Incorrect syntax near '?'" com a task **verde**, porque o `try/except` engole.
- Os 11 testes migram para `tests/`, em pt-BR, **mesclados** com os 4 homônimos que já
  existem — nunca sobrescritos.
- **Aceite:** suíte sem falha nova contra o baseline; as DAGs carregam sem Broken DAG.
- **Deploy:** mexe em `dags/utils/` ⇒ **exige restart do worker**, senão a task roda
  verde com o código antigo.

### F2 — A API de leitura

`dashboard`, `indicadores/historico`, `tasks`, `detalhe`, `anexos`, `categorias`.

- Placeholders `?` (pyodbc).
- Colunas novas entram no **bloco degradável** do `SELECT`, como as 091/092 já fazem:
  ambiente sem a migration serve a versão reduzida em vez de virar "sistema em
  atualização".
- **Aceite:** cada rota com teste; o teste de degradação prova que a ausência da tabela
  não derruba a tela.

### F3 — O bloco Admin ServiceNow — **com a permissão que hoje não existe**

As 10 rotas `/admin/servicenow/*` da foto exigem **apenas autenticação**
(`Depends(get_current_user)`). Qualquer usuário logado pode hoje, em produção: ler e
**gravar a configuração da integração**, criar e editar grupos, salvar os perfis de
acesso do módulo e disparar o delta.

O padrão do repositório para isso é `Depends(get_admin_user)` (`api/deps.py`,
`PERM_ADMIN = "acao_admin"`), como em `admin.py` e `datastage.py`.

- **Aceite:** teste que chama cada rota admin com usuário **sem** `acao_admin` e exige
  **403**. Sem esse teste a proteção volta a cair em silêncio no próximo refactor.
- **Corrigir o descarte silencioso (§4.6):** `proxy` e `grupos` precisam persistir, e o
  teste tem de conferir o valor **no banco** depois do `{"ok": true}` — um teste que só
  olha o código de resposta passa verde com o defeito intacto.
- ⚠️ Enquanto a F3 não subir, a exposição continua **viva em produção**.

### F4 — O front

`Chamados.tsx`, `ChamadoDetalheModal.tsx`, `lib/chamado.ts`, adaptados aos componentes
atuais (a tela da foto foi escrita contra a base de junho).

**A tela ganha a 3ª aba, Dashboard** (a `main` tem só Fila e Indicadores) — e ela precisa
ser corrigida ao entrar: o componente lê `d.backlog` como número, mas a rota devolve
`{label, cor, total, chamados}`. Objeto como filho não renderiza. A API já entrega **10
blocos com a lista de chamados dentro** (backlog, abertas, resolvidas_hoje, andamento,
pendentes, sem_analista, resolvidas, vencem_hoje, vencem_semana, vencidas) e **4 visões**
(`geral`, `proprio`, `diaadia`, `iniciativa`); a tela consome 4 números de uma visão só.
Confirmado que é essa versão que está no ar: as strings do fonte estão no bundle que o
`index.html` de produção referencia.

- `RBAC_RECURSOS` é uma segunda lista à mão: tela que entra só no NAV vira permissão
  **sem interruptor** no cadastro de perfis (aconteceu com `tela_chamados`).
- Permissão nova **exige relogin** — as permissões vivem no `localStorage` e só atualizam
  no login.
- `dist/` rebuildada e commitada.
- **Aceite:** `tsc` 0 erros, `eslint` idêntico ao baseline, build ok.

### F5 — Alinhar o recorte dos indicadores ao da fila

**Verificado no código de produção: o card duplicado já está resolvido**, por um caminho
diferente do que as #327/#328 propunham — e o resultado na fila é o mesmo.

`Chamados.tsx`, linha 474:

```ts
(resp?.chamados ?? []).filter(c => !(c.tipo === 'task' && c.pai_sys_id))
```

Esconde a task **que tem pai**; a task **órfã continua card**. É exatamente o
comportamento que a #327 defendia. O RITM mostra suas tasks dentro do card, buscadas em
`/chamados/{sys_id}/tasks`. Os contadores da tela (total e colunas do kanban) são
recalculados sobre esse mesmo recorte, então fila e kanban concordam entre si.

**O que resta é uma divergência silenciosa entre a tela e as contas:**

| Onde | Recorte | Órfã |
|---|---|---|
| Fila e kanban (front) | `NOT (tipo='task' AND pai_sys_id)` | **conta** |
| Indicadores, dashboard, histórico (API) | `tipo != 'task'` | **não conta** |

Enquanto não existir sc_task órfã, os dois dão o mesmo número e tudo parece certo. No dia
em que existir — task cujo pai saiu do filtro de grupo, ou que chegou antes do pai — a
fila mostra o card e nenhum indicador o conta. Nada avisa.

Há ainda o campo `total` da resposta de `/chamados`: ele é `len(chamados)`, ou seja, conta
as tasks com pai também. A tela não o exibe (usa só como `> 0`), mas qualquer outro
consumidor lê 113 onde a tela mostra ~60.

**Entrega:** trocar `tipo != 'task'` por `NOT (tipo='task' AND pai_sys_id IS NOT NULL)`
nas agregações, com `NOT EXISTS` — nunca `NOT IN`, que com um NULL na subconsulta devolve
conjunto vazio e zera a conta inteira sem erro nenhum. Mais o `total` coerente com o
recorte.

**Aceite:** teste de paridade que prova o mesmo número nos dois lados **com uma órfã
presente** no cenário — sem ela, o teste passa verde com o defeito intacto. Mais o
anti-drift que varre as queries sem o recorte (o das branches preservadas
`feat/chamados-card-por-trabalho` e `feat/chamados-indicadores-trabalho`, que não foram
apagadas).

### F6 — Fecho: manual, smoke e aceitação — ✅ **ENTREGUE**

* **Manual do usuário** — `docs/manual-chamados.md`.
* **Smoke** — `scripts/smoke_chamados.sh`: 11 verificações MEDIDAS, não uma
  lista para conferir a olho. Conferir "os Indicadores batem com a Fila" lendo
  dois números em telas diferentes é o próprio modo de falso verde que esta
  spec catalogou.
* **Revisão adversarial** — abaixo.

#### O que a revisão adversarial encontrou

**Confirmado em ordem:** as 19 rotas exigem autenticação e as 9 de `/admin`
exigem `acao_admin` (risco #2, fechado); nenhum `NOT IN` com subconsulta
(risco da F5); o proxy de anexo exige o par (anexo, chamado); os parâmetros
posicionais casam com os `?` em todas as consultas, inclusive com o filtro de
responsável de N nomes.

**Defeito 1 — `total` e `por_coluna` de `/chamados` contavam REGISTROS.**
Era uma entrega da F5 ("o `total` coerente com o recorte") que ficou por fazer.
Medido em dev: `total` 90 para 57 trabalhos, `novo` 34 onde a tela mostra 17 —
quase o dobro. A tela não exibe nenhum dos dois (usa `total` só como `> 0` e
conta as colunas por si), então nada aparecia errado; qualquer outro consumidor
lia o número duplicado. A contagem passou a vir do banco com `_so_trabalhos()`
— e **não** de um filtro em Python, que seria uma terceira cópia da regra.

**Defeito 2 — a idade do frescor misturava dois relógios.** ⚠️ **Achado pelo
SMOKE, não por teste** — nenhum teste pegava, porque todo dublê responde com o
mesmo relógio. `iniciado_em` é gravado pelo worker do Airflow; a conta usava
`DATEDIFF(…, GETDATE())`, o relógio do SQL Server. No dev os containers estão
em fusos diferentes (worker `-03`, banco `UTC`), e o carimbo dizia **180
minutos** para um ciclo de **1 minuto** — com o aviso âmbar de "integração
parada" disparando para sempre.

⚠️ A correção **não** foi gravar `iniciado_em` com `GETDATE()`, que seria o
caminho óbvio: `ultimo_delta_em()` usa esse mesmo `MAX(iniciado_em)` como
início da janela que pergunta ao ServiceNow o que mudou. Empurrada 3h para a
frente, ela pediria registros alterados depois de um instante **futuro** — e
não traria nada, com a DAG verde. A idade passou a ser calculada em Python.

#### Fio solto declarado (não corrigido, precisa de decisão)

`aberto_em` e `encerrado_em` vêm do **ServiceNow** e são comparados com
`GETDATE()` em `idade_dias`, no aging, no fluxo e no histórico. É a mesma
mistura de relógios do defeito 2, num terceiro fuso — o da instância. O impacto
é menor porque a granularidade ali é de **dias** (`DATEDIFF(DAY, …)`), então só
morde perto da virada do dia. Corrigir exige saber em que fuso a instância
devolve as datas — pergunta para quem administra o ServiceNow, não para o
código.

## 6. Riscos

| # | Risco | Mitigação |
|---|---|---|
| 1 | ~~DDL ausente~~ — resolvido pelo `000_schema_completo.sql` da 2ª foto | conferir cada tabela contra as migrations 094–098 antes de renumerar |
| 2 | Rotas admin sem permissão — **exposição viva hoje** | F3, com teste de 403 |
| 3 | Front da foto escrito contra base de junho | F4 adapta; `App.tsx`/`nav.ts` não são portados |
| 4 | Agrupamento RITM × SCTASK perdido ao fechar #327/#328 | F5 explícita, branches preservadas |
| 5 | Mudança em `dags/utils/` sem restart do worker | task verde com código antigo — o `deploy.sh` avisa desde a #313 |
| 6 | Testes homônimos sobrescritos na migração | mesclar, nunca substituir |
| 7 | Produção diverge de novo durante o porte | nenhum deploy até o porte fechar; `api/` é sincronizado **sem perguntar** |
| 8 | Números de migration colidindo (089, 093) entre as duas linhagens | renumerar a partir da 094; `etl_schema_version` rastreia por nome, então produção fica com as duas listas |
| 9 | Órfã visível na fila e ausente das contas — silencioso enquanto não houver órfã | F5, com teste que **inclui uma órfã no cenário** |

## 7. Operação

### 7.1 Medir a divergência da F5 no banco de produção

Responde, com dado, se a órfã é hipótese ou fato hoje. `NOT EXISTS`, nunca `NOT IN`.

```sql
-- 1) tasks ativas sem pai gravado
SELECT COUNT(*) AS orfas_sem_pai FROM dbo.etl_chamado
 WHERE ativo = 1 AND tipo = 'task' AND pai_sys_id IS NULL;

-- 2) tasks ativas cujo pai não está na fila ativa
SELECT COUNT(*) AS orfas_pai_fora FROM dbo.etl_chamado t
 WHERE t.ativo = 1 AND t.tipo = 'task' AND t.pai_sys_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM dbo.etl_chamado p
                    WHERE p.sys_id = t.pai_sys_id AND p.ativo = 1);

-- 3) os dois recortes lado a lado: se divergirem, a divergência JÁ existe
SELECT
  (SELECT COUNT(*) FROM dbo.etl_chamado
    WHERE ativo = 1 AND tipo != 'task')                                    AS conta_indicadores,
  (SELECT COUNT(*) FROM dbo.etl_chamado
    WHERE ativo = 1 AND NOT (tipo = 'task' AND pai_sys_id IS NOT NULL))    AS conta_fila,
  (SELECT COUNT(*) FROM dbo.etl_chamado WHERE ativo = 1)                   AS total_espelho;
```

### 7.2 Extrair o DDL — ✅ **não é mais necessário**

Resolvido pelo `000_schema_completo.sql` da segunda foto. Fica registrado para o caso de
precisar conferir o banco contra o schema:

```bash
cd /opt/airflow
docker compose exec -T orquestra-api python -c "
import os, pyodbc
T=('etl_chamado_anexo','etl_chamado_ciclo','etl_chamado_nota','etl_indicador_meta','etl_indicador_snapshot','etl_indicador_snapshot_analista','etl_indicador_snapshot_grupo','etl_servicenow_grupo','etl_sn_categoria')
cn=pyodbc.connect(os.environ['MSSQL_CONN_STR'],timeout=20); cur=cn.cursor()
cur.execute('SELECT TABLE_NAME,ORDINAL_POSITION,COLUMN_NAME,DATA_TYPE,CHARACTER_MAXIMUM_LENGTH,IS_NULLABLE,COLUMN_DEFAULT FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME IN {} ORDER BY TABLE_NAME,ORDINAL_POSITION'.format(T))
[print('\t'.join('' if v is None else str(v) for v in r)) for r in cur.fetchall()]
print('--- INDICES ---')
cur.execute('SELECT t.name,i.name,i.type_desc,i.is_unique,i.is_primary_key,c.name FROM sys.indexes i JOIN sys.tables t ON t.object_id=i.object_id JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id JOIN sys.columns c ON c.object_id=i.object_id AND c.column_id=ic.column_id WHERE t.name IN {} ORDER BY t.name,i.name,ic.key_ordinal'.format(T))
[print('\t'.join(str(v) for v in r)) for r in cur.fetchall()]
" > /tmp/ddl-chamados.txt 2>&1; cat /tmp/ddl-chamados.txt
```

### 7.3 Smoke pós-deploy

1. `/chamados` abre e a fila lista.
2. Um chamado abre o detalhe; um anexo baixa pelo proxy.
3. A aba Indicadores bate com a Fila no total.
4. O histórico responde nos três períodos.
5. Usuário **sem** `acao_admin` recebe 403 nas rotas admin (é o aceite da F3, verificado
   em produção).
6. `disparar-delta` roda e o ciclo aparece em `/admin/servicenow/ciclos`.

## 8. Decisões tomadas

1. **A versão de produção é a base** — as PRs #327/#328 foram fechadas (decisão do dono
   do produto, 2026-08-27). O que elas prendiam vira a F5.
2. **A branch pública saiu do GitHub** — o material está na tag local e no bundle.
3. **Nenhum deploy até o porte fechar** — `deploy.sh` sobrescreve `api/` sem perguntar.
4. **Validar no ambiente dev antes de produção** — o `000_schema_completo.sql` permite
   levantar um banco idêntico ao de produção, e o dev tem Airflow + SQL Server + API +
   front (runbook em `docs/ambiente-dev.md`).

## 9. Pendências

- [x] ~~DDL das 9 tabelas — bloqueava a F0~~. Resolvido pelo `000_schema_completo.sql`
      da segunda foto (`fe1376b`): 81 tabelas idempotentes, as 9 presentes. **Nenhuma
      pendência trava trabalho agora.**
- [x] ~~Rodar a §7.1 para saber se a divergência da F5 já é fato~~ — rodada em
      dev (2026-08-28): **zero órfãs** e os dois recortes dão 57. A divergência
      é hipótese, não fato. O passo [4] do `smoke_chamados.sh` mede isso a cada
      execução, então a resposta deixa de depender de alguém lembrar de rodar.
- [x] ~~Quem alimenta `etl_indicador_*`~~ — o próprio `servicenow_sync.py` grava os três
      snapshots (`etl_indicador_snapshot`, `_analista`, `_grupo`) no fim do ciclo. Isso
      **acopla F0 e F1**: o motor insere nas tabelas que a F0 cria, então a F1 não fecha
      antes da F0.
- [x] ~~Visões do dashboard~~ — são quatro: `geral`, `proprio`, `diaadia`, `iniciativa`.

O código de produção referencia a **migration 093** (`chamado_triagem`), que já está na
`main`. Ou seja: as duas linhas partiram da mesma base de banco até a 093 e divergiram
daí para frente — as 9 tabelas ausentes são o que foi criado depois, só no servidor.
