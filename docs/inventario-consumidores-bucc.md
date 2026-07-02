# Inventário de Consumidores (endpoints → views/procs do BUCC)

Tela **Governança & Dados → Inventário de Consumidores** (`/inventario`).

## Propósito

Cadastro **documental** de quais endpoints/serviços consomem quais views/procs/
tabelas de um banco (caso motivador: **BUCC**). A regra operacional que a tela
sustenta é:

> **Em alterações de schema, os consumidores são ajustados PRIMEIRO e o banco
> por último.**

Antes de alterar uma view/proc do banco, consulte a tela (ou filtre pelo nome
do objeto na busca) para saber **quem** consome aquele objeto, avise/ajuste os
consumidores e só então aplique a mudança no banco. Cada objeto tem um
**status de validação** (`pendente` / `validado` / `com_erro`) para acompanhar
o ciclo de conferência após um incidente ou uma mudança.

## Contexto — incidente BUCC de 2026-07-02

O que motivou a tela:

- Foi conduzida com o DBA a **restauração do backup do BUCC de sexta-feira**.
- Durante a restauração, o endpoint do GI
  **`GBE_ConsultaContratosCelularEmailIREndereco_SF`** (consumido pelo
  Salesforce) **reportou erro**.
- O campo **`NUM_CPF_CNPJ`** hoje é **VARCHAR**, preservando zeros à esquerda —
  PF com **11** dígitos, PJ com **14**.
- O **GI retorna os dados conforme a TIPAGEM do SELECT** da view: se a view
  retorna VARCHAR `'07011460950'`, o GI devolve exatamente isso; se a coluna
  sai numérica, devolve `7011460950` **sem o zero à esquerda**. Logo, **as
  views devem manter o campo como VARCHAR**.
- **Pendência registrada no seed**: validar se as **6 views** do endpoint
  `GBE_ConsultaContratosCelularEmailIREndereco_SF` têm o campo de CNPJ e se
  **já foram recompiladas** (`sp_refreshview`) após a restauração:
  `VW_PESSOAS_VINCULADAS_GENESYS`, `VW_CONTRATO_IMPOSTO_RENDA`,
  `VW_CELULAR_CONTRATOS_CVP_GENESYS`, `VW_FIXA_CONTRATOS_CVP_GENESYS`,
  `VW_ENDERECO_CONTRATOS_CVP_GENESYS`, `VW_EMAIL_CONTRATOS_CVP_GENESYS`.

Outros consumidores levantados no mesmo dia (também no seed da migration 055):

- `GBE_ConsultaContratos` (GI, consumido pelo Salesforce) — objetos ainda não
  mapeados.
- Processo **Genesys** de contatos de clientes (equipe Jordan) — consome
  `VW_CLIENTES_EMAIL_TELEFONE_CVP`.

## Modelo de dados (migration `sql/migrations/055_inventario_consumidores.sql`)

### `dbo.etl_inventario_endpoint`

| Coluna | Tipo | Descrição |
| --- | --- | --- |
| `id` | INT IDENTITY PK | |
| `endpoint` | NVARCHAR(200) NOT NULL | nome do serviço/endpoint (ex.: `GBE_ConsultaContratos`) |
| `plataforma` | NVARCHAR(100) NULL | ex.: `GI`, `Salesforce`, `Genesys` |
| `consumidor` | NVARCHAR(200) NULL | quem chama o endpoint |
| `banco` | NVARCHAR(128) NOT NULL DEFAULT `'BUCC'` | banco cujos objetos são consumidos |
| `descricao` | NVARCHAR(1000) NULL | contexto/incidentes/pendências |
| `responsavel` | NVARCHAR(200) NULL | quem responde pelo consumidor |
| `ativo` | BIT NOT NULL DEFAULT 1 | soft delete |
| `criado_por/criado_em/atualizado_por/atualizado_em` | auditoria | matrícula autenticada |

Índice único filtrado `UX_inventario_endpoint_nome (endpoint) WHERE ativo = 1`
(padrão da migration 052): o soft delete libera o nome para novo cadastro.

### `dbo.etl_inventario_objeto`

| Coluna | Tipo | Descrição |
| --- | --- | --- |
| `id` | INT IDENTITY PK | |
| `endpoint_id` | INT NOT NULL | FK lógica p/ `etl_inventario_endpoint` |
| `objeto` | NVARCHAR(300) NOT NULL | nome da view/proc/tabela |
| `tipo` | VARCHAR(10) NOT NULL DEFAULT `'view'` | `view` \| `proc` \| `tabela` |
| `status_validacao` | VARCHAR(20) NOT NULL DEFAULT `'pendente'` | `pendente` \| `validado` \| `com_erro` |
| `observacao` | NVARCHAR(1000) NULL | |
| `criado_por/criado_em` | auditoria | |

Índice `IX_inventario_objeto_endpoint (endpoint_id)`.

### RBAC

Recurso **`tela_inventario`** concedido aos perfis **admin** e
**desenvolvedor** (MERGE idempotente, padrão da 052). O recurso controla a
visibilidade do menu **e** a escrita na API; a leitura exige apenas usuário
autenticado e **degrada para lista vazia** se a migration ainda não rodou.

## API (`api/routers/inventario.py`)

| Método | Rota | Permissão | Descrição |
| --- | --- | --- | --- |
| GET | `/inventario/endpoints?q=&banco=` | autenticado | lista endpoints ativos + objetos agregados; `q` faz LIKE em endpoint/consumidor/objeto |
| POST | `/inventario/endpoints` | `tela_inventario` | cria (sem `id`) ou atualiza (com `id`) |
| DELETE | `/inventario/endpoints/{id}` | `tela_inventario` | soft delete (`ativo=0`) |
| POST | `/inventario/endpoints/{id}/objetos` | `tela_inventario` | adiciona objeto (`objeto`, `tipo`) |
| PATCH | `/inventario/objetos/{id}` | `tela_inventario` | atualiza `status_validacao`/`observacao` |
| DELETE | `/inventario/objetos/{id}` | `tela_inventario` | remove objeto |

Auditoria: `criado_por`/`atualizado_por` recebem a matrícula autenticada.

## Como usar

1. **Documentar um consumidor**: “Novo endpoint” → preencha nome, plataforma,
   consumidor, banco (default BUCC), responsável e descrição → “Criar
   endpoint” → o modal permanece aberto para mapear os objetos (nome + tipo).
2. **Antes de alterar o schema**: busque pelo nome da view/proc no campo de
   busca — todos os endpoints que a consomem aparecem. Ajuste/avise os
   consumidores primeiro; o banco muda por último.
3. **Após um incidente/mudança**: use o status de cada objeto
   (âmbar = pendente, verde = validado, vermelho = com erro) e a observação
   para acompanhar a conferência, endpoint a endpoint.
4. **Excluir**: soft delete — o registro sai da tela, mas fica no banco para
   histórico (e o nome fica livre para recadastro).
