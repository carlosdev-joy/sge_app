# Subsistema A — Inteligência Operacional ServiceNow: Sync Híbrido, Notas, Anexos, Indicadores e Admin

**Data:** 2026-08-22  
**Status:** Aprovado — aguardando plano de implementação  
**Subsistemas dependentes:** B (modal + kanban), C (análise de tabelas), D (IA de atribuição)

---

## 1. Objetivo

Transformar o sync do ServiceNow de um espelho passivo (full a cada 15 min) em uma base de inteligência operacional: dados frescos a cada 5 min via delta incremental, histórico estruturado de notas e anexos por chamado, snapshots históricos de indicadores por analista/grupo, e uma tela de Admin centralizada para configuração. O Subsistema B consome as notas e anexos para o modal de detalhes; os Subsistemas C e D consomem o histórico para análise de padrões e sugestões de IA.

---

## 2. Escopo

### Incluído nesta spec

- Migrations 094–098 (5 novas tabelas / alterações)
- DAG `etl_servicenow_delta` (a cada 5 min)
- DAG `etl_servicenow_full` (a cada 12h — 02h e 14h)
- Refatoração de `servicenow_sync.py` para suportar modo delta e busca de notas/anexos
- Endpoints API: detalhe do chamado, proxy de anexos, admin ServiceNow, indicadores históricos
- Tela Admin ServiceNow (conexão, grupos, sync, perfis)
- Tela de indicadores históricos (tendência, analistas, grupos)
- Modal de detalhes do chamado (descrição, notas, anexos)
- Regra visual de destaque para INC não-encerrado em todas as telas
- Estrutura preparada para gatilhos Teams e metas de indicadores (sem lógica de disparo)

### Fora do escopo (subsistemas futuros)

- **Subsistema B:** kanban com modal integrado (consome endpoints desta spec)
- **Subsistema C:** análise de tabelas com erros recorrentes
- **Subsistema D:** IA para aceleração de atribuição e sugestão de correção
- **Subsistema E:** sistema de perfis granular e controle de acesso por tela/submenu
- Lógica de disparo dos gatilhos Teams (estrutura criada aqui, disparo no E)

---

## 3. Arquitetura de Dados

### 3.1 Alterações em `dbo.etl_chamado` (migration 094)

Adicionar coluna `tem_anexo TINYINT NULL DEFAULT 0` — atualizada pelo sync de anexos.

### 3.2 `dbo.etl_chamado_nota` (migration 094)

Uma linha por nota do `sys_journal_field`. Notas são imutáveis no ServiceNow — o sync só insere, nunca atualiza.

```sql
CREATE TABLE dbo.etl_chamado_nota (
    sys_id_nota      NVARCHAR(32)   NOT NULL,
    sys_id_chamado   NVARCHAR(32)   NOT NULL,
    autor            NVARCHAR(120)  NULL,
    autor_email      NVARCHAR(200)  NULL,
    criado_em        DATETIME2      NULL,
    texto            NVARCHAR(4000) NULL,
    tipo             NVARCHAR(20)   NOT NULL,  -- 'work_notes' | 'comments'
    sync_em          DATETIME2      NOT NULL DEFAULT GETDATE(),
    CONSTRAINT PK_etl_chamado_nota PRIMARY KEY (sys_id_nota),
    CONSTRAINT FK_nota_chamado FOREIGN KEY (sys_id_chamado)
        REFERENCES dbo.etl_chamado(sys_id)
);
CREATE INDEX IX_nota_chamado ON dbo.etl_chamado_nota (sys_id_chamado);
```

### 3.3 `dbo.etl_chamado_anexo` (migration 095)

Uma linha por anexo. O proxy usa `url_download` para buscar o arquivo via credencial do ServiceNow.

```sql
CREATE TABLE dbo.etl_chamado_anexo (
    sys_id_anexo     NVARCHAR(32)   NOT NULL,
    sys_id_chamado   NVARCHAR(32)   NOT NULL,
    nome_arquivo     NVARCHAR(255)  NULL,
    mime_type        NVARCHAR(100)  NULL,
    tamanho_bytes    INT            NULL,
    url_download     NVARCHAR(500)  NULL,  -- /api/now/attachment/{sys_id}/file
    criado_em        DATETIME2      NULL,
    sync_em          DATETIME2      NOT NULL DEFAULT GETDATE(),
    CONSTRAINT PK_etl_chamado_anexo PRIMARY KEY (sys_id_anexo),
    CONSTRAINT FK_anexo_chamado FOREIGN KEY (sys_id_chamado)
        REFERENCES dbo.etl_chamado(sys_id)
);
CREATE INDEX IX_anexo_chamado ON dbo.etl_chamado_anexo (sys_id_chamado);
```

### 3.4 `dbo.etl_chamado_ciclo` (migration 096)

Substitui `dbo.etl_chamado_sync`. Registra cada ciclo delta ou full com contagens e modo. A DAG delta lê o último ciclo bem-sucedido para calcular o ponto de corte incremental.

```sql
CREATE TABLE dbo.etl_chamado_ciclo (
    id               INT IDENTITY(1,1) NOT NULL,
    modo             NVARCHAR(10)   NOT NULL,  -- 'delta' | 'full'
    iniciado_em      DATETIME2      NOT NULL,
    terminado_em     DATETIME2      NULL,
    status           NVARCHAR(10)   NOT NULL DEFAULT 'ERRO',  -- 'OK'|'PARCIAL'|'ERRO'
    qtd_chamados     INT            NULL,
    qtd_notas        INT            NULL,
    qtd_anexos       INT            NULL,
    qtd_desativados  INT            NULL,      -- preenchido só no full
    disparado_por    NVARCHAR(50)   NULL,
    erro             NVARCHAR(1000) NULL,
    CONSTRAINT PK_etl_chamado_ciclo PRIMARY KEY (id)
);
CREATE INDEX IX_ciclo_modo_status ON dbo.etl_chamado_ciclo (modo, status, iniciado_em DESC);
```

A DAG full migra os dados históricos de `etl_chamado_sync` na primeira execução (INSERT INTO ciclo SELECT ... FROM sync).

### 3.5 `dbo.etl_indicador_snapshot` + filhas (migration 097)

Cabeçalho de snapshot — uma linha por ciclo delta (e por full).

```sql
CREATE TABLE dbo.etl_indicador_snapshot (
    id                          INT IDENTITY(1,1) NOT NULL,
    capturado_em                DATETIME2      NOT NULL DEFAULT GETDATE(),
    total_ativos                INT            NOT NULL DEFAULT 0,
    novo                        INT            NOT NULL DEFAULT 0,
    andamento                   INT            NOT NULL DEFAULT 0,
    aguardando                  INT            NOT NULL DEFAULT 0,
    resolvido                   INT            NOT NULL DEFAULT 0,
    outros                      INT            NOT NULL DEFAULT 0,
    sla_vencidos                INT            NOT NULL DEFAULT 0,
    idade_media_dias            DECIMAL(6,1)   NULL,
    tempo_medio_resolucao_horas DECIMAL(8,1)   NULL,  -- média dos encerrados nos últimos 30 dias
    qtd_encerrados_7d           INT            NOT NULL DEFAULT 0,
    qtd_abertos_7d              INT            NOT NULL DEFAULT 0,
    qtd_iniciativas_abertas     INT            NOT NULL DEFAULT 0,  -- tipo_demanda='iniciativa'
    CONSTRAINT PK_snapshot PRIMARY KEY (id)
);
CREATE INDEX IX_snapshot_capturado ON dbo.etl_indicador_snapshot (capturado_em DESC);

CREATE TABLE dbo.etl_indicador_snapshot_analista (
    id_snapshot      INT            NOT NULL,
    atribuido_a      NVARCHAR(120)  NOT NULL,
    atribuido_a_email NVARCHAR(200) NOT NULL DEFAULT '',
    total_ativos     INT            NOT NULL DEFAULT 0,
    sla_vencidos     INT            NOT NULL DEFAULT 0,
    idade_media_dias DECIMAL(6,1)   NULL,
    CONSTRAINT PK_snapshot_analista PRIMARY KEY (id_snapshot, atribuido_a_email),
    CONSTRAINT FK_snapshot_analista FOREIGN KEY (id_snapshot)
        REFERENCES dbo.etl_indicador_snapshot(id)
);

CREATE TABLE dbo.etl_indicador_snapshot_grupo (
    id_snapshot      INT            NOT NULL,
    grupo            NVARCHAR(120)  NOT NULL,
    total_ativos     INT            NOT NULL DEFAULT 0,
    sla_vencidos     INT            NOT NULL DEFAULT 0,
    idade_media_dias DECIMAL(6,1)   NULL,
    CONSTRAINT PK_snapshot_grupo PRIMARY KEY (id_snapshot, grupo),
    CONSTRAINT FK_snapshot_grupo FOREIGN KEY (id_snapshot)
        REFERENCES dbo.etl_indicador_snapshot(id)
);
```

### 3.6 `dbo.etl_indicador_meta` (migration 097 — estrutura para metas futuras)

```sql
CREATE TABLE dbo.etl_indicador_meta (
    id              INT IDENTITY(1,1) NOT NULL,
    metrica         NVARCHAR(60)   NOT NULL,   -- 'tempo_medio_resolucao_horas', 'sla_vencidos', etc.
    valor_meta      DECIMAL(8,1)   NOT NULL,
    periodo_inicio  DATE           NOT NULL,
    periodo_fim     DATE           NULL,        -- NULL = meta contínua
    grupo           NVARCHAR(120)  NULL,        -- NULL = meta global
    criado_por      NVARCHAR(120)  NULL,
    criado_em       DATETIME2      NOT NULL DEFAULT GETDATE(),
    CONSTRAINT PK_meta PRIMARY KEY (id)
);
```

A tela de indicadores renderiza a linha horizontal de meta nos gráficos quando existe uma meta ativa — sem CRUD de metas nesta spec.

### 3.7 `dbo.etl_servicenow_grupo` (migration 098)

Substitui o campo CSV `servicenow_grupos` de `etl_app_config`. Cada grupo tem seu próprio registro, com histórico de quando foi adicionado.

```sql
CREATE TABLE dbo.etl_servicenow_grupo (
    id           INT IDENTITY(1,1) NOT NULL,
    nome         NVARCHAR(200)  NOT NULL,   -- nome exato do grupo no ServiceNow
    ativo        TINYINT        NOT NULL DEFAULT 1,
    criado_em    DATETIME2      NOT NULL DEFAULT GETDATE(),
    alterado_em  DATETIME2      NOT NULL DEFAULT GETDATE(),
    CONSTRAINT PK_sn_grupo PRIMARY KEY (id),
    CONSTRAINT UQ_sn_grupo_nome UNIQUE (nome)
);
```

### 3.8 `dbo.etl_servicenow_gatilho` (migration 098 — estrutura preparada)

```sql
CREATE TABLE dbo.etl_servicenow_gatilho (
    id            INT IDENTITY(1,1) NOT NULL,
    tipo          NVARCHAR(60)   NOT NULL,   -- 'inc_novo', 'sla_proximo', 'aguardando_Xd'
    condicao_json NVARCHAR(500)  NULL,       -- ex: {"horas_antes": 2}
    webhook_url   NVARCHAR(500)  NULL,
    ativo         TINYINT        NOT NULL DEFAULT 0,  -- desligado até o Subsistema E
    grupo         NVARCHAR(120)  NULL,       -- NULL = todos os grupos
    criado_em     DATETIME2      NOT NULL DEFAULT GETDATE(),
    CONSTRAINT PK_sn_gatilho PRIMARY KEY (id)
);
```

---

## 4. DAGs

### 4.1 `etl_servicenow_delta` (schedule: `*/5 * * * *`)

```
[espelho_delta] → [notas_e_anexos] → [snapshot] → [triagem]
```

**Configuração:**
- `max_active_runs=1` — descarta o próximo disparo se o anterior ainda estiver rodando
- `dagrun_timeout=8min` — folga para 3 tasks + triagem

**Task `espelho_delta`:**
1. Lê grupos de `etl_servicenow_grupo WHERE ativo=1`
2. Calcula ponto de corte: `SELECT MAX(iniciado_em) FROM etl_chamado_ciclo WHERE modo='delta' AND status IN ('OK','PARCIAL')`. Se NULL (primeiro run), usa `NOW() - 30min` como fallback seguro
3. Insere linha em `etl_chamado_ciclo` com `modo='delta'` e `status='ERRO'` (padrão — fechado no finally)
4. Chama Table API com filtro `sysparm_query=assignment_group.nameIN{grupos}^sys_updated_on>={ponto_corte}`
5. Upsert normal via `servicenow_sync.upsert_sql()` — sem step de desativação
6. Fecha ciclo com status e contagens

**Task `notas_e_anexos`:**
1. Recebe lista de `sys_id` tocados no espelho_delta
2. Para cada chamado, chama `GET /api/now/table/sys_journal_field?sysparm_query=element_id={sys_id}^element=work_notes^ORDERBYcreated_on`
3. MERGE por `sys_id_nota` — insere apenas notas novas (imutáveis)
4. Chama `GET /api/now/attachment?sysparm_query=table_sys_id={sys_id}` para anexos
5. MERGE por `sys_id_anexo` — insere apenas anexos novos
6. UPDATE `etl_chamado SET tem_anexo=1 WHERE sys_id=? AND tem_anexo=0` para chamados com anexos
7. Atualiza `qtd_notas` e `qtd_anexos` no registro de ciclo

**Task `snapshot`:**
1. SELECT agregado sobre `etl_chamado WHERE ativo=1` — contagens por `estado_kanban`, SLA, idade, iniciativas
2. SELECT por analista (GROUP BY `atribuido_a_email`)
3. SELECT por grupo (GROUP BY `grupo`)
4. INSERT em `etl_indicador_snapshot` + filhas
5. Leve — sem chamada ao ServiceNow

**Task `triagem`:** comportamento atual sem mudança.

### 4.2 `etl_servicenow_full` (schedule: `0 2,14 * * *`)

```
[espelho_full] → [notas_e_anexos_full] → [snapshot]
```

**Configuração:**
- `max_active_runs=1`
- `dagrun_timeout=25min` — o full pode ter centenas de chamados + notas

**Task `espelho_full`:**
- Comportamento atual da DAG `etl_servicenow_sync` — busca todas as páginas, faz desativação por `sync_em < inicio`
- Grava com `modo='full'`
- Na primeira execução: migra histórico de `etl_chamado_sync` para `etl_chamado_ciclo`

**Task `notas_e_anexos_full`:**
- Igual à task delta, mas varre TODOS os chamados ativos — não só os tocados no ciclo
- Garante cobertura de chamados antigos que nunca passaram pelo delta

**Task `snapshot`:** mesmo código da DAG delta — função compartilhada em `servicenow_sync.py`.

### 4.3 DAG `etl_servicenow_sync` (existente)

Desativada após o full rodar uma vez com sucesso. O interruptor `servicenow_habilitado=0` serve de killswitch durante a transição.

---

## 5. Refatoração de `servicenow_sync.py`

Novas funções públicas (usadas pelas DAGs):

```python
def ultimo_delta_em(hook) -> datetime:
    """Ponto de corte para o próximo delta. Fallback: NOW() - 30min."""

def query_delta(grupos: list[str], desde: datetime) -> str:
    """sysparm_query com filtro de grupo + sys_updated_on >= desde."""

def buscar_notas(cliente, url: str, sys_id: str) -> list[dict]:
    """sys_journal_field para um chamado. Retorna lista de notas estruturadas."""

def buscar_anexos(cliente, url: str, sys_id: str) -> list[dict]:
    """attachment API para um chamado. Retorna lista de metadados de anexos."""

def upsert_nota_sql() -> str:
    """MERGE por sys_id_nota — placeholder %s."""

def upsert_anexo_sql() -> str:
    """MERGE por sys_id_anexo — placeholder %s."""

def capturar_snapshot(hook) -> int:
    """Grava snapshot + filhas. Retorna id do snapshot gravado."""
```

---

## 6. Endpoints API

### 6.1 `GET /chamados/{sys_id}/detalhe`

Retorna o chamado completo com notas e anexos. Requer autenticação.

**Response:**
```json
{
  "chamado": {
    "sys_id": "...", "numero": "INC0012345", "tipo": "incident",
    "titulo": "...", "descricao": "...", "estado_kanban": "andamento",
    "atribuido_a": "João Silva", "atribuido_a_email": "...",
    "grupo": "Eng. Dados", "aberto_em": "2026-08-15T10:00:00",
    "url": "https://...", "tem_anexo": true,
    "sla_vencido": false, "prazo": null
  },
  "notas": [
    {
      "sys_id_nota": "...", "autor": "João Silva",
      "autor_email": "joao@empresa.com", "criado_em": "2026-08-20T10:32:15",
      "texto": "Verificado o job...", "tipo": "work_notes"
    }
  ],
  "anexos": [
    {
      "sys_id_anexo": "...", "nome_arquivo": "screenshot.png",
      "mime_type": "image/png", "tamanho_bytes": 420000,
      "url_proxy": "/chamados/{sys_id}/anexos/{sys_id_anexo}",
      "criado_em": "2026-08-19T14:05:00"
    }
  ]
}
```

### 6.2 `GET /chamados/{sys_id}/anexos/{sys_id_anexo}`

Proxy autenticado. Busca o arquivo via credencial do ServiceNow (`servicenow_usuario` + `servicenow_senha_enc` de `etl_app_config`) e faz streaming ao cliente.

- Imagens (`image/*`): `Content-Type: image/png` (ou mime real), sem `Content-Disposition` — renderiza inline
- Outros tipos: `Content-Disposition: attachment; filename="{nome_arquivo}"` — dispara download

### 6.3 `GET /chamados/indicadores/historico`

Parâmetros: `periodo` (`hoje` | `30d` | `historico`), `grupo` (opcional).

**Response:**
```json
{
  "snapshots": [
    {
      "capturado_em": "2026-08-22T10:00:00",
      "total_ativos": 42, "novo": 5, "andamento": 18,
      "aguardando": 12, "resolvido": 7, "outros": 0,
      "sla_vencidos": 3, "idade_media_dias": 4.2,
      "tempo_medio_resolucao_horas": 18.5,
      "qtd_encerrados_7d": 22, "qtd_abertos_7d": 19,
      "qtd_iniciativas_abertas": 8
    }
  ],
  "por_analista": [
    {
      "atribuido_a": "João Silva", "atribuido_a_email": "...",
      "total_ativos": 8, "sla_vencidos": 1, "idade_media_dias": 4.2
    }
  ],
  "por_grupo": [
    {
      "grupo": "Eng. Dados", "total_ativos": 42,
      "sla_vencidos": 3, "idade_media_dias": 4.2
    }
  ],
  "metas": [
    {
      "metrica": "tempo_medio_resolucao_horas",
      "valor_meta": 24.0, "grupo": null
    }
  ]
}
```

A agregação por período é feita no SQL:
- `hoje`: SELECT bruto das últimas 24h, agrupado por hora (`DATEPART(hour, capturado_em)`)
- `30d`: AVG por dia (`CAST(capturado_em AS DATE)`)
- `historico`: AVG por semana (`DATEPART(week, capturado_em)`)

### 6.4 Endpoints Admin ServiceNow

```
GET  /admin/servicenow/config          — lê config global (URL, usuário, habilitado)
PUT  /admin/servicenow/config          — salva config global
POST /admin/servicenow/testar          — testa credencial contra Table API
GET  /admin/servicenow/grupos          — lista etl_servicenow_grupo
POST /admin/servicenow/grupos          — cria grupo
PUT  /admin/servicenow/grupos/{id}     — edita nome ou ativo
POST /admin/servicenow/grupos/verificar — verifica se grupo existe no ServiceNow
GET  /admin/servicenow/ciclos          — últimos 20 ciclos de etl_chamado_ciclo
POST /admin/servicenow/disparar-delta  — dispara DAG delta via Airflow REST API
GET  /admin/servicenow/perfis-acesso   — lista perfis com acesso à tela
PUT  /admin/servicenow/perfis-acesso   — salva lista de perfis (grava em etl_app_config['servicenow_admin_perfis'])
```

Acesso: perfil `admin` sempre liberado. Outros perfis: verificar `servicenow_admin_perfis` em `etl_app_config`.

---

## 7. Interface (Frontend)

### 7.1 Modal de Detalhes do Chamado

Abre ao clicar em qualquer card do kanban. Consome `GET /chamados/{sys_id}/detalhe`.

**Layout:**
```
┌─────────────────────────────────────────────────────┐
│  INC0012345 · Erro na carga ETL_VENDAS        [✕]  │
│  Analista: João Silva  │  Grupo: Eng. Dados          │
│  Estado: Em andamento  │  Aberto: 15/08/2026         │
├─────────────────────────────────────────────────────┤
│  DESCRIÇÃO                                          │
│  Falha na execução do job ETL_VENDAS_DIARIO...      │
├─────────────────────────────────────────────────────┤
│  HISTÓRICO DE NOTAS                    [3 notas]    │
│  ┌──────────────────────────────────────────────┐   │
│  │ João Silva · 20/08 10:32  [work_notes]       │   │
│  │ Verificado o job, coluna ausente na tabela.. │   │
│  └──────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────┤
│  ANEXOS  [📎 2]                                     │
│  🖼 screenshot_erro.png  420 KB        [ver]        │
│  📄 log_datastage.txt    12 KB         [baixar]     │
│  ┌──────────────────────────────────────────────┐   │
│  │  [imagem renderizada inline via url_proxy]   │   │
│  └──────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────┤
│  [🔗 Abrir no ServiceNow]                           │
└─────────────────────────────────────────────────────┘
```

### 7.2 Regra Visual — INC não-encerrado

Em **todas** as telas (kanban, dashboard, modal, indicadores): chamados com `tipo='incident'` e `estado_kanban NOT IN ('resolvido', 'encerrado')` recebem:
- Card: borda esquerda vermelha (`border-l-4 border-red-500`) + badge `INC` em vermelho
- Modal: header com fundo `bg-red-50 dark:bg-red-900/20`
- Tabelas de indicadores: linha com `text-red-600 dark:text-red-400`

### 7.3 Tela Admin ServiceNow (`/admin/servicenow`)

Quatro seções em abas:

**Aba "Conexão":**
- Campos: URL, Usuário, Senha (mascarada), toggle Habilitado
- Botão "Salvar" → `PUT /admin/servicenow/config`
- Botão "Testar conexão" → `POST /admin/servicenow/testar` — exibe latência e status

**Aba "Grupos":**
- Tabela: Nome | Ativo | Criado em | Ações
- Botão "+ Adicionar" — input inline com "Verificar" antes de salvar
- Toggle ativo/inativo por linha (sem delete)

**Aba "Sincronização":**
- Tabela dos últimos 20 ciclos: Modo | Status | Início | Duração | Chamados | Notas | Anexos | Erro
- Botão "Forçar delta agora"

**Aba "Acesso":**
- Multiselect de perfis existentes em `etl_usuario.perfil`
- Salva em `etl_app_config['servicenow_admin_perfis']`

### 7.4 Tela de Indicadores Históricos (`/chamados/indicadores/historico`)

Seletor de período: Hoje | 30 dias | Histórico

**Gráficos (biblioteca existente no bundle):**
- Linha: total de ativos ao longo do tempo
- Barras empilhadas: distribuição por coluna kanban
- Linha: tempo médio de resolução (+ linha horizontal de meta quando existir)
- Barras: encerrados × abertos por semana

**Tabela de analistas:** Analista | Ativos | SLA vencidos | Idade média

**Tabela de grupos:** Grupo | Ativos | SLA vencidos | Idade média

---

## 8. Regras de Negócio

### 8.1 Ponto de corte do delta

- Fonte: `MAX(iniciado_em) WHERE modo='delta' AND status IN ('OK','PARCIAL')`
- Fallback se NULL: `NOW() - 30min` — garante que o primeiro delta cobre a janela de transição
- Ciclos com `status='ERRO'` não avançam o ponto de corte — o próximo delta re-processa o mesmo intervalo

### 8.2 Desativação de chamados reatribuídos

- **Somente o full** executa `UPDATE etl_chamado SET ativo=0 WHERE sync_em < inicio`
- O delta não desativa — um chamado que não aparece no delta pode simplesmente não ter mudado
- Janela máxima de "fantasma": 12h (tempo entre fulls)

### 8.3 Chamados encerrados com risco de reabertura

Estado `encerrado` (`estado_kanban='encerrado'` ou `ativo=0`) dentro de 5 dias do `encerrado_em`: o delta continua incluindo esses chamados na busca via filtro `sys_updated_on`. Após 5 dias, saem naturalmente do delta porque não são mais atualizados no ServiceNow.

### 8.4 Notas e anexos — idempotência

- Notas: MERGE por `sys_id_nota` — sem risco de duplicata mesmo se o mesmo chamado aparecer em delta e full simultâneos
- Anexos: MERGE por `sys_id_anexo` — mesma garantia
- `tem_anexo`: UPDATE condicional (`WHERE tem_anexo=0`) — evita escrita desnecessária

### 8.5 Proxy de anexos

- Credencial lida de `etl_app_config` a cada request (não em cache) — troca de senha no Admin tem efeito imediato
- Timeout: 30s para a chamada ao ServiceNow
- Tamanho máximo: sem limite explícito (streaming passa os bytes conforme chegam)
- Sem cache local — cada request vai ao ServiceNow

### 8.6 FRESCOR_ALERTA_MINUTOS

O campo `FRESCOR_ALERTA_MINUTOS` em `api/routers/chamados.py` deve ser atualizado de `15` para `8` quando a DAG delta entrar em produção (cadência de 5 min + margem).

---

## 9. Compatibilidade e Transição

### 9.1 `etl_chamado_sync` → `etl_chamado_ciclo`

- A tabela antiga continua existindo durante a transição
- O primeiro full migra o histórico: `INSERT INTO etl_chamado_ciclo (modo, iniciado_em, terminado_em, status, qtd_chamados, disparado_por, erro) SELECT 'full', iniciado_em, terminado_em, status, (qtd_incident+qtd_ritm+qtd_task+qtd_change), disparado_por, erro FROM etl_chamado_sync`
- Após migração confirmada, `etl_chamado_sync` pode ser arquivada (fora do escopo desta spec)

### 9.2 `servicenow_grupos` em `etl_app_config`

- Continua existindo como fallback durante a transição
- As DAGs novas leem de `etl_servicenow_grupo`
- A tela de Admin mostra aviso se `servicenow_grupos` ainda tiver valor diferente dos grupos cadastrados

### 9.3 DAG `etl_servicenow_sync` (existente)

- Não é deletada — apenas pausada via Airflow UI após o full rodar uma vez com sucesso
- O interruptor `servicenow_habilitado=0` serve de killswitch de emergência para todas as DAGs

---

## 10. Testes

### 10.1 Testes unitários (dags/tests/)

- `test_servicenow_delta.py`: ponto de corte correto, query delta com filtro `sys_updated_on`, fallback de 30 min, sem desativação no delta
- `test_servicenow_notas.py`: MERGE por sys_id_nota, notas imutáveis (sem UPDATE), mapeamento autor/email/tipo
- `test_servicenow_snapshot.py`: contagens corretas por coluna kanban, por analista, por grupo, qtd_iniciativas_abertas
- `test_servicenow_cadencia.py` (existente): atualizar para aceitar `FRESCOR_ALERTA_MINUTOS=8` com delta de 5 min

### 10.2 Testes de integração (api/)

- `test_chamados_detalhe.py`: endpoint detalhe retorna chamado + notas + anexos, 404 para sys_id inexistente
- `test_chamados_anexo_proxy.py`: proxy retorna Content-Type correto, Content-Disposition para não-imagens
- `test_admin_servicenow.py`: CRUD de grupos, teste de conexão, lista de ciclos
- `test_indicadores_historico.py`: agregação por período (hoje/30d/histórico), filtro por grupo

---

## 11. Ordem de Implementação

As tasks devem ser executadas nesta ordem — cada uma entrega valor independente:

1. **Migrations 094–098** — base para tudo
2. **`servicenow_sync.py`** — novas funções: `ultimo_delta_em`, `query_delta`, `buscar_notas`, `buscar_anexos`, `upsert_nota_sql`, `upsert_anexo_sql`, `capturar_snapshot`
3. **DAG `etl_servicenow_delta`** — sync incremental + notas + anexos + snapshot
4. **DAG `etl_servicenow_full`** — refatoração do full com migração de histórico
5. **Endpoints API** — detalhe, proxy de anexos, indicadores históricos, admin
6. **Tela Admin ServiceNow** — config, grupos, ciclos, perfis
7. **Modal de detalhes** — integrado ao kanban existente
8. **Tela de indicadores históricos** — gráficos + tabelas
9. **Regra visual INC** — borda vermelha em todas as telas
10. **QA completo** — suite de testes atualizada, smoke em produção

---

## 12. Subsistemas Dependentes

| Subsistema | Depende de | O que consome |
|---|---|---|
| B — Modal + Kanban | A | `GET /chamados/{sys_id}/detalhe`, regra visual INC |
| C — Análise de tabelas | A | `etl_chamado_nota`, `etl_chamado.objetos` |
| D — IA de atribuição | A + C | Notas + histórico de analistas + padrões de tabelas |
| E — Perfis e acesso | A | `etl_servicenow_gatilho`, estrutura de perfis de acesso |
