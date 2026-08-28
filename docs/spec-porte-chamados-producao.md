# Spec — Porte do módulo ServiceNow desenvolvido em produção

> **Status:** RASCUNHO, aguardando aprovação.
> **Origem:** foto de produção `18046a8`, preservada na tag local `foto-producao-20260827`
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

## 4. O que o banco precisa — e ainda não sabemos

O código usa **9 tabelas que não têm migration em lugar nenhum**:

`etl_chamado_anexo` · `etl_chamado_ciclo` · `etl_chamado_nota` · `etl_indicador_meta` ·
`etl_indicador_snapshot` · `etl_indicador_snapshot_analista` ·
`etl_indicador_snapshot_grupo` · `etl_servicenow_grupo` · `etl_sn_categoria`

Foram criadas direto no banco de produção. Nenhuma migration nova veio na foto, e o
`prod_info` que veio junto é um snapshot antigo (33 tabelas, nenhuma delas). **Sem o DDL
real, o módulo não sobe em ambiente nenhum** — e escrever a migration "deduzindo" tipo,
nulidade e índice a partir das queries produz um schema parecido, que aceita os `SELECT`
de hoje e quebra no primeiro dado fora do formato imaginado.

O DDL sai do próprio banco (comando em §7.1). É o **único bloqueio real** desta spec.

## 5. Fases

### F0 — As 9 tabelas viram migrations `094`+

Do DDL extraído do banco, uma migration idempotente por assunto, rastreada em
`dbo.etl_schema_version`.

- **Aceite:** `migrate.py --dry-run` num banco limpo aplica tudo sem erro; reaplicar não
  altera nada; `sql/tests` cobre a criação.
- **Atenção:** índice filtrado (`CREATE INDEX ... WHERE`) falha no `sqlcmd` por
  `QUOTED_IDENTIFIER` e, se criado assim, quebra todo DML da tabela pelo `sqlcmd`
  enquanto o `pymssql` da DAG segue verde.
- **Bloqueada por:** DDL de produção (§7.1).

### F1 — O motor de sincronização

`servicenow_sync.py`, `chamado_derivacoes.py`, `etl_servicenow_full.py`,
`etl_servicenow_delta.py`, `etl_log_cleanup.py`, `.airflowignore`.

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
- ⚠️ Enquanto a F3 não subir, a exposição continua **viva em produção**.

### F4 — O front

`Chamados.tsx`, `ChamadoDetalheModal.tsx`, `lib/chamado.ts`, adaptados aos componentes
atuais (a tela da foto foi escrita contra a base de junho).

- `RBAC_RECURSOS` é uma segunda lista à mão: tela que entra só no NAV vira permissão
  **sem interruptor** no cadastro de perfis (aconteceu com `tela_chamados`).
- Permissão nova **exige relogin** — as permissões vivem no `localStorage` e só atualizam
  no login.
- `dist/` rebuildada e commitada.
- **Aceite:** `tsc` 0 erros, `eslint` idêntico ao baseline, build ok.

### F5 — Reconquistar o card por trabalho

As PRs #327/#328 foram fechadas por decisão do dono do produto (a base do porte é a
versão de produção). O que elas prendiam **não existe na versão de produção** e volta a
ser defeito se ninguém reaplicar:

- **um card por trabalho** (RITM × SCTASK): a fila mostra 113 registros para ~60
  trabalhos;
- **paridade Fila × Indicadores**: sem o mesmo recorte nas agregações, a aba Indicadores
  diz 113 onde a Fila diz 60 — e as duas parecem certas;
- os testes de agrupamento (órfã, auto-referência, ciclo `A↔B`, cadeia `A←B←C`) e o
  anti-drift que varre por AST as queries sem o recorte.

O código está preservado nas branches `feat/chamados-card-por-trabalho` e
`feat/chamados-indicadores-trabalho`, que **não foram apagadas**.

### F6 — Fecho: manual, smoke e aceitação

Manual do usuário, roteiro de smoke (§7.2) e a revisão adversarial única de fim de spec.

## 6. Riscos

| # | Risco | Mitigação |
|---|---|---|
| 1 | DDL deduzido do código gera schema parecido que quebra no primeiro dado real | F0 bloqueada até o DDL sair do banco |
| 2 | Rotas admin sem permissão — **exposição viva hoje** | F3, com teste de 403 |
| 3 | Front da foto escrito contra base de junho | F4 adapta; `App.tsx`/`nav.ts` não são portados |
| 4 | Agrupamento RITM × SCTASK perdido ao fechar #327/#328 | F5 explícita, branches preservadas |
| 5 | Mudança em `dags/utils/` sem restart do worker | task verde com código antigo — o `deploy.sh` avisa desde a #313 |
| 6 | Testes homônimos sobrescritos na migração | mesclar, nunca substituir |
| 7 | Produção diverge de novo durante o porte | nenhum deploy até o porte fechar; `api/` é sincronizado **sem perguntar** |

## 7. Operação

### 7.1 Extrair o DDL (bloqueia a F0)

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

### 7.2 Smoke pós-deploy

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

## 9. Pendências

- [ ] **DDL das 9 tabelas (§7.1) — bloqueia a F0.** É a única pendência que trava
      trabalho.
- [x] ~~Quem alimenta `etl_indicador_*`~~ — o próprio `servicenow_sync.py` grava os três
      snapshots (`etl_indicador_snapshot`, `_analista`, `_grupo`) no fim do ciclo. Isso
      **acopla F0 e F1**: o motor insere nas tabelas que a F0 cria, então a F1 não fecha
      antes da F0.
- [x] ~~Visões do dashboard~~ — são quatro: `geral`, `proprio`, `diaadia`, `iniciativa`.

O código de produção referencia a **migration 093** (`chamado_triagem`), que já está na
`main`. Ou seja: as duas linhas partiram da mesma base de banco até a 093 e divergiram
daí para frente — as 9 tabelas ausentes são o que foi criado depois, só no servidor.
