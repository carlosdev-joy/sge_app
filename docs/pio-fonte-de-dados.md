# PIO — a fonte de dados dos cards do Workflow

Os cards do Workflow em **Busca & Vendas** (`/caixa-seguro`) leem a carga do
PIO: propostas comerciais de seguros, agregadas por status de assinatura.

Este documento existe porque a infra descrita aqui foi criada **direto no
servidor**, fora deste repositório — sem ele, a origem dos números da tela não
está escrita em lugar nenhum que acompanhe o código.

## O caminho do dado

```
TDDB48 (sql18,1450\staging4)          ← fonte, sistema de propostas
   │  OPENQUERY no linked server SQL18\STAGING4
   │  PRC_PIO_CARGA_PROPOSTA_PENDENTE — TRUNCATE + INSERT, diário 07:30
   ▼
DMDB41 (sql14,1480)                   ← o PRÓPRIO banco do Orquestra
   ├── PIO_PROPOSTA_PENDENTE_DET      uma linha por proposta
   └── PIO_PROPOSTA_PENDENTE_AGG      uma linha por categoria (o número do card)
   │  SELECT direto, via MSSQL_CONN_STR
   ▼
api/routers/pio.py → /pio/contagens e /pio/propostas
   ▼
ui-react/src/caixa/lib/pio.ts → os cards e a lista
```

⚠️ **A API nunca fala com o TDDB48 em runtime.** Ela lê as duas tabelas do
banco em que já está conectada — o `SQL14_DMDB41` de
`dags/utils/conn_resolver.py` é o mesmo banco do `MSSQL_CONN_STR` da API.
Linked server é assunto da carga, uma vez por dia.

## As categorias

`STA_ASSINATURA` é o que separa um card do outro:

| Código | Card do Workflow |
|---|---|
| `PE` | Pendentes de Assinatura |
| `PP` | Pendentes de Pagamento |
| `AP` | Assinadas e Pagas |
| `AN` | Em Análise |
| `EM` | Emitidas |
| `RE` | Rejeitadas |

Os dois últimos cards da sequência — *Devoluções de Prêmio* e *Sensibilizações*
— **não têm categoria correspondente** nesta carga.

O filtro da carga hoje é `STA_ASSINATURA = 'PE'`, `STA_PAGO = 'N'`,
`STA_SITUACAO NOT IN ('CA','EXP')` e `DTH_VENDA` nos últimos 30 dias — ou seja,
**só `PE` é carregada**. Primeira carga: 8.706 propostas.

## Como ligar o próximo card

Um lugar só: `ORIGEM_PIO`, em `ui-react/src/caixa/lib/pio.ts`.

```ts
export const ORIGEM_PIO: Partial<Record<StatusWorkflow, string>> = {
  pending_signature: "PE",
  // awaiting_payment: "PP",  ← descomentar quando a carga trouxer PP
};
```

Acrescentar a linha faz três coisas sozinho: o card passa a contar da carga, as
propostas de exemplo daquele status somem da tela, e a lista do card passa a vir
paginada do servidor.

**Antes de ligar um card que tem sub-filtro** (`awaiting_payment`,
`in_analysis`, `refund_scheduled`), o sub-status precisa ir para a consulta em
`/pio/propostas` — o filtro da tela roda sobre o array local e não se aplica à
lista paginada. `tests/test_pio_api.py` reprova essa combinação, com o motivo.

E, claro: a carga precisa **trazer** a categoria. Card ligado a uma categoria
que a proc não popula mostra zero — verdadeiro, mas inútil.

## Estado da infra

| Item | Onde | Situação |
|---|---|---|
| Tabelas `_AGG` e `_DET` | DMDB41 | em produção; `sql/migrations/101_pio_proposta_pendente.sql` as cria em ambiente novo |
| `PRC_PIO_CARGA_PROPOSTA_PENDENTE` | DMDB41 | em produção, **fora do repo** — ver pendência abaixo |
| SQL Agent Job "PIO - Carga Proposta Pendente" | msdb do sql14,1480 | script pronto (`089b`, linhagem de produção); **aguarda o DBA aplicar** — `usr_dstage_prev` não tem permissão no SQL Agent |

⚠️ **A procedure não está versionada.** A migration 101 cria só as tabelas: o
texto que roda em produção é a fonte da verdade, e reconstituí-lo a partir da
documentação significaria sobrescrever o original por uma cópia aproximada. Para
versionar, extrair do servidor:

```sql
SELECT OBJECT_DEFINITION(OBJECT_ID('dbo.PRC_PIO_CARGA_PROPOSTA_PENDENTE'));
```

Enquanto isso, um ambiente novo tem as tabelas **vazias** — e a tela sabe
distinguir isso de "não consegui ler".

## Dicionário de dados

### `dbo.PIO_PROPOSTA_PENDENTE_AGG`

| Coluna | Tipo | Descrição |
|---|---|---|
| `ID` | int IDENTITY | PK |
| `STA_CATEGORIA` | varchar(50) | Código da categoria (PE, PP, AP, AN, EM, RE) |
| `DES_CATEGORIA` | varchar(100) | Rótulo legível |
| `QTD_PROPOSTAS` | int | Quantidade na data de referência |
| `DTH_REFERENCIA` | date | Data de corte da extração |
| `DTH_CARGA` | datetime | Quando a linha foi inserida |

Índices: `PK_PIO_PROPOSTA_PENDENTE_AGG (ID)`, `IX_PIO_AGG_REF (DTH_REFERENCIA, STA_CATEGORIA)`.

### `dbo.PIO_PROPOSTA_PENDENTE_DET`

| Coluna | Tipo | Descrição |
|---|---|---|
| `ID` | bigint IDENTITY | PK |
| `COD_PROPOSTA` | varchar(50) | Código único da proposta |
| `NUM_AGENCIA` | varchar(20) | Agência da venda |
| `NUM_MATRICULA` | varchar(30) | Matrícula do responsável |
| `DTH_VENDA` | date | Data da proposta |
| `STA_SITUACAO` | varchar(10) | Situação (AT=Ativa; CA e EXP ficam fora da carga) |
| `DES_JUST_CANC` | varchar(500) | Justificativa de cancelamento |
| `STA_ASSINATURA` | varchar(10) | Categoria do card (ver tabela acima) |
| `STA_PAGO` | varchar(5) | Flag de pagamento (N=não pago) |
| `DTH_ALTERACAO` | datetime | Última atualização na fonte |
| `NOM_PESSOA` | varchar(200) | Nome do proponente |
| `COD_CPF` | varchar(20) | CPF |
| `DTA_NASCIMENTO` | date | Nascimento |
| `VLR_RENDA_FORMAL` | decimal(18,2) | Renda formal declarada |
| `NOM_LOGRADOURO` · `NOM_BAIRRO` · `NOM_CIDADE` · `NOM_UF` · `NUM_CEP` | varchar | Endereço |
| `NOM_PRODUTO` | varchar(200) | Produto contratado |
| `AREA_PRODUTO` | varchar(100) | Área/segmento |
| `VLR_IMP_SEGURADA` | decimal(18,2) | Capital segurado |
| `VLR_PREMIO` | decimal(18,2) | Prêmio (mensalidade) |
| `COD_PLANO` | varchar(20) | Plano |
| `NUM_DDD_TEL_RES` · `NUM_TEL_RES` · `NUM_DDD_TEL_CEL` · `NUM_TEL_CEL` | varchar | Telefones |
| `DES_EMAIL` | varchar(200) | E-mail |
| `DTH_REFERENCIA` | date | Data de corte |
| `DTH_CARGA` | datetime | Quando a linha foi inserida |

Índices: `PK_..._DET (ID)`, `IX_PIO_DET_REF (DTH_REFERENCIA)`,
`IX_PIO_DET_STA (STA_ASSINATURA, STA_SITUACAO)`, `IX_PIO_DET_PROPOSTA (COD_PROPOSTA)`.

Tabelas de origem no TDDB48: `PV_040_PROPOSTA`, `PV_044_PROPOSTA_PESSOA`,
`PV_036_PESSOA_FISICA`, `PV_020_ENDERECO`, `PV_038_PRODUTO`, `PV_017_CONTATO`,
`PV_052_PREMIO_PRODUTO`.
