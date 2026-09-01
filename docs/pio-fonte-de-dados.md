# PIO — a fonte de dados dos cards do Workflow

Os cards do Workflow em **Busca & Vendas** (`/caixa-seguro`) leem a carga do
PIO: propostas comerciais de seguros, agregadas **por card**.

Este documento existe porque a infra descrita aqui foi criada **direto no
servidor**, fora deste repositório — sem ele, a origem dos números da tela não
está escrita em lugar nenhum que acompanhe o código.

> **Modelo vigente desde 2026-09-01** (guia de referência do PIO). Ele substitui
> o primeiro desenho, em que havia uma `_AGG` única agregada por
> `STA_CATEGORIA`. O que mudou: o agregado passou a ser **por card**
> (`COD_CARD`), ganhou histórico, e **cada card tem a sua própria tabela de
> detalhe**.

## O caminho do dado

```
TDDB48 (sql18,1450\staging4)          ← fonte, sistema de propostas
   │  OPENQUERY no linked server SQL18\STAGING4
   │  PRC_PIO_CARGA_DIARIA — diária, 07:30
   ▼
DMDB41 (sql14,1480)                   ← o PRÓPRIO banco do Orquestra
   ├── PIO_AGG                        1 linha por card, snapshot do dia (TRUNCATE)
   ├── PIO_AGG_HIST                   mesma estrutura, INSERT-only (tendência)
   ├── PIO_PROPOSTA_PENDENTE_DET      detalhe do card PEND_ASSIN  (TRUNCATE)
   ├── PIO_PROPOSTA_PEND_PGTO_DET     detalhe do card PEND_PGTO   (TRUNCATE)
   └── PIO_PROPOSTA_ASSINA_PAGA_DET   detalhe do card ASSINA_PAGA (TRUNCATE)
   │  SELECT direto, via MSSQL_CONN_STR
   ▼
api/routers/pio.py → /pio/contagens e /pio/propostas
   ▼
ui-react/src/caixa/lib/pio.ts → os cards e a lista
```

⚠️ **A API nunca fala com o TDDB48 em runtime.** Ela lê as tabelas do banco em
que já está conectada — o `SQL14_DMDB41` de `dags/utils/conn_resolver.py` é o
mesmo banco do `MSSQL_CONN_STR` da API. Linked server é assunto da carga, uma
vez por dia.

A ordem da carga importa: as três DET primeiro, depois a `PIO_AGG` como
`UNION ALL` **delas** (não da fonte), e por fim a `PIO_AGG_HIST`, que só insere
se a `DTH_REFERENCIA` ainda não existir — proteção contra dupla execução.

## Os cards

| `COD_CARD` | Card do Workflow | Filtro na origem | Tabela de detalhe | Volume |
|---|---|---|---|---|
| `PEND_ASSIN` | Pendentes de Assinatura | `STA_ASSINATURA='PE'` | `PIO_PROPOSTA_PENDENTE_DET` | ~8.700 |
| `PEND_PGTO` | Pendentes de Pagamento | `STA_ASSINATURA='CO' AND STA_PAGO='N'` | `PIO_PROPOSTA_PEND_PGTO_DET` | ~22.500 |
| `ASSINA_PAGA` | Assinadas e Pagas | `STA_ASSINATURA='CO' AND STA_PAGO='S'` | `PIO_PROPOSTA_ASSINA_PAGA_DET` | — |

Os três recortam ainda `STA_SITUACAO NOT IN ('CA','EXP')` e `DTH_VENDA` nos
**últimos 30 dias**.

⚠️ **Os cards 2 e 3 saem do mesmo `STA_ASSINATURA='CO'` — quem os separa é o
`STA_PAGO`.** Se a carga do card 2 deixar de filtrar `STA_PAGO='N'`, as duas
tabelas passam a conter as mesmas propostas pagas: os dois cards contam a mesma
venda, o total do Workflow infla, e nada acusa. (O passo 02 do fluxo de carga
no guia descreve o filtro como só `'CO'`; o catálogo e o mapeamento do mesmo
guia dizem `'CO' AND STA_PAGO='N'`. Vale conferir o texto da proc em produção —
a consulta de conferência está no fim deste documento.)

⚠️ **`COD_CARD` precisa de pelo menos `VARCHAR(11)`.** O guia especifica
`VARCHAR(10)`, mas **`'ASSINA_PAGA'` tem 11 caracteres**. Com a coluna em 10, a
carga ou morre (Msg 2628, `ANSI_WARNINGS ON`) ou grava `'ASSINA_PAG'` em
silêncio — e aí o front pede `'ASSINA_PAGA'`, não casa, e o card mostra **zero
para sempre**, sem erro em lugar nenhum. A migration 103 alarga para
`VARCHAR(20)` na `PIO_AGG` e na `PIO_AGG_HIST`.

⚠️ **A API não refiltra por status.** Cada DET já contém apenas as propostas do
seu card — o filtro foi aplicado na carga. Repetir `STA_ASSINATURA` na consulta
é a forma silenciosa de zerar um card no dia em que a carga mudar de critério:
tabela cheia, tela mostrando 0.

Os demais cards da sequência (*Em Análise*, *Emitidas*, *Rejeitadas*,
*Devoluções de Prêmio*, *Sensibilizações*) **ainda não têm carga** e seguem no
dado de exemplo.

Códigos de `STA_ASSINATURA` na fonte, para referência: `PE` pendente de
assinatura · `CO` assinada · `AP` assinada e paga · `AN` em análise · `EM`
emitida · `RE` rejeitada.

## Como ligar o próximo card

Dois lugares, e os dois têm teste que reprova a divergência:

1. `ORIGEM_PIO`, em `ui-react/src/caixa/lib/pio.ts` — card do Workflow → `COD_CARD`.
2. `CARDS`, em `api/routers/pio.py` — `COD_CARD` → (rótulo, **tabela de detalhe**).

```ts
export const ORIGEM_PIO: Partial<Record<StatusWorkflow, string>> = {
  pending_signature: "PEND_ASSIN",
  awaiting_payment: "PEND_PGTO",
  paid: "ASSINA_PAGA",
};
```

Acrescentar a linha faz três coisas sozinho: o card passa a contar da carga, as
propostas de exemplo daquele status somem da tela, e a lista do card passa a vir
paginada do servidor.

⚠️ **Card que lê a carga não mostra sub-filtro.** O Select de sub-status filtra o
array local de exemplo e não se aplica à lista paginada do servidor. Quem lê o
PIO tem o Select escondido (`subFiltroAtivo`, no `InlineWorkflow`) — sem isso o
usuário escolheria "Cartão de crédito", a lista continuaria idêntica e nada
explicaria por quê. Para oferecer o recorte de verdade, o sub-status precisa ir
para dentro de `/pio/propostas`.

E, claro: a carga precisa **trazer** o card. Card ligado a um `COD_CARD` que a
proc não popula mostra zero — verdadeiro, mas inútil.

## Por que `MAX(DTH_REFERENCIA)` e não `= hoje`

O guia do PIO filtra o agregado por `DTH_REFERENCIA = CAST(GETDATE() AS DATE)`,
o que está certo **enquanto a carga roda**. A API usa o último snapshot porque o
SQL Agent Job ainda depende do DBA: no dia em que a carga não rodar, `= hoje`
não devolve linha nenhuma e os cards mostram **zero**, que é falso. Com o último
snapshot o número continua verdadeiro, e a tela exibe a data dele — que é
justamente o que denuncia a carga parada. Como a `PIO_AGG` é TRUNCATE + INSERT,
nos dias normais as duas leituras devolvem a mesma linha.

## Estado da infra

| Item | Onde | Situação |
|---|---|---|
| `PIO_AGG`, `PIO_AGG_HIST`, as duas primeiras `_DET` | DMDB41 | `sql/migrations/102_pio_agg_e_card_pagamento.sql` as cria em ambiente novo (a 101 criou as da primeira versão) |
| `PIO_PROPOSTA_ASSINA_PAGA_DET` e o alargamento de `COD_CARD` | DMDB41 | `sql/migrations/103_pio_card_assinadas_pagas.sql` |
| `PRC_PIO_CARGA_DIARIA` | DMDB41 | **fora do repo** — ver pendência abaixo |
| SQL Agent Job da carga | msdb do sql14,1480 | **aguarda o DBA aplicar** — `usr_dstage_prev` não tem permissão no SQL Agent |
| `PIO_PROPOSTA_PENDENTE_AGG` | DMDB41 | **órfã** desde este modelo: ninguém lê. Não foi dropada — a carga nasceu fora do repo e derrubar tabela que talvez ainda seja escrita lá troca um problema de tela por um de dado |

⚠️ **A procedure não está versionada.** As migrations criam só as tabelas: o
texto que roda em produção é a fonte da verdade, e reconstituí-lo a partir da
documentação significaria sobrescrever o original por uma cópia aproximada. Para
versionar, extrair do servidor:

```sql
SELECT OBJECT_DEFINITION(OBJECT_ID('dbo.PRC_PIO_CARGA_DIARIA'));
```

Enquanto isso, um ambiente novo tem as tabelas **vazias** — e a tela sabe
distinguir isso de "não consegui ler".

## Dicionário de dados

### `dbo.PIO_AGG` e `dbo.PIO_AGG_HIST` (mesma estrutura)

| Coluna | Tipo | Descrição |
|---|---|---|
| `ID` | int IDENTITY | PK |
| `COD_CARD` | varchar(20) | `PEND_ASSIN` \| `PEND_PGTO` \| `ASSINA_PAGA` — **o que escolhe a tabela de detalhe**. O guia diz varchar(10) e `'ASSINA_PAGA'` tem 11 caracteres: a migration 103 alarga |
| `DES_CARD` | varchar(100) | Rótulo legível do card |
| `STA_CATEGORIA` | varchar(50) | Código do status na fonte (PE, CO, …) |
| `DES_CATEGORIA` | varchar(100) | Rótulo do status |
| `QTD_PROPOSTAS` | int | Quantidade na data de referência |
| `DTH_REFERENCIA` | date | Data de corte da extração |
| `DTH_CARGA` | datetime | Quando a linha foi inserida |

Índices: `PK_PIO_AGG (ID)` / `PK_PIO_AGG_HIST (ID)`,
`IX_PIO_AGG_CARD_REF` e `IX_PIO_AGG_HIST_CARD_REF`, ambos `(COD_CARD, DTH_REFERENCIA)`.

⚠️ Consulta ao histórico **sempre** com `COD_CARD` no filtro: sem ele, os três
cards voltam misturados e o gráfico de tendência soma valores de datas iguais.

### As três `_DET` (`PENDENTE`, `PEND_PGTO`, `ASSINA_PAGA`)

Estrutura **idêntica** nas três — 31 colunas, na mesma ordem. Só o nome da
tabela muda, e é por isso que a API escolhe o `FROM` por um dicionário fechado:
trocar uma pela outra devolveria uma lista plausível de propostas erradas, sem
erro nenhum. Entre a `PEND_PGTO` e a `ASSINA_PAGA` isso é ainda mais traiçoeiro:
as duas têm `STA_ASSINATURA='CO'`, e só o `STA_PAGO` distingue uma da outra.

| Coluna | Tipo | Descrição |
|---|---|---|
| `ID` | bigint IDENTITY | PK |
| `COD_PROPOSTA` | varchar(50) | Código único da proposta |
| `NUM_AGENCIA` | varchar(20) | Agência da venda |
| `NUM_MATRICULA` | varchar(30) | Matrícula do responsável — formato CEF `0000161406-9` |
| `DTH_VENDA` | date | Data da proposta |
| `STA_SITUACAO` | varchar(10) | Situação (AT=Ativa; CA e EXP ficam fora da carga) |
| `DES_JUST_CANC` | varchar(500) | Justificativa de cancelamento |
| `STA_ASSINATURA` | varchar(10) | Status na fonte — **já filtrado pela carga** |
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

Índices de cada uma: PK por `ID`, `(COD_PROPOSTA)`, `(DTH_REFERENCIA)`,
`(STA_ASSINATURA, STA_SITUACAO)` e `(DTH_VENDA, COD_PROPOSTA)` — este último
cobre a ordenação da lista, que é sempre pela venda mais antiga.

Tabelas de origem no TDDB48: `PV_040_PROPOSTA`, `PV_044_PROPOSTA_PESSOA`,
`PV_036_PESSOA_FISICA`, `PV_020_ENDERECO`, `PV_038_PRODUTO`, `PV_017_CONTATO`,
`PV_052_PREMIO_PRODUTO`.

## Que coluna preenche cada campo da tela

Levantado em 2026-09-01 para explicar as diferenças entre a tela e a fonte.
**Só as propostas vindas da carga** seguem esta tabela; as de exemplo (cards
ainda não ligados) continuam saindo de `caixa/lib/workflow.ts`.

O caminho é sempre o mesmo: coluna → `api/routers/pio.py` (campo do JSON) →
`propostaDoPio()` em `caixa/lib/pio.ts` (campo do componente) → tela.

### Card da lista (`InlineWorkflow` e o painel `ProposalWorkflowSheet`)

| Na tela | Campo interno | Coluna da carga |
|---|---|---|
| Número da proposta | `number` | `COD_PROPOSTA` |
| Etiqueta de status | `status` | **nenhuma** — é o card selecionado, não o dado |
| "N dias pendente" | `daysInPending` | `DATEDIFF(day, DTH_VENDA, hoje)` |
| Nome | `insuredName` | `NOM_PESSOA` |
| Produto | `product` | `NOM_PRODUTO` |
| Valor (ao lado do produto) | `value` | **`VLR_PREMIO`** — é o prêmio, não a renda |
| Região | `region` | `NOM_UF` → região do IBGE (`caixa/lib/regiao.ts`) |
| Faixa | `ageRange` | `DATEDIFF(year, DTA_NASCIMENTO, hoje)` + " anos" |

⚠️ **"Faixa" mostra a idade exata, não uma faixa.** As propostas de exemplo
traziam `"45-60"`; a carga tem a data de nascimento, então o valor real é
`"45 anos"`. Os dois convivem na mesma linha da tela.

### Modal "Resumo do seguro" (`ProposalDetailDialog`)

| Na tela | Campo interno | Coluna da carga |
|---|---|---|
| Linha do tempo | `status` | **nenhuma** — o card selecionado |
| Data de Venda | `date` | `DTH_VENDA` |
| Matrícula do Indicador | `indicatorId` | `NUM_MATRICULA` |
| Agência | `agency` | `NUM_AGENCIA` |
| **Usuário** | derivado | **nenhuma** — é `"c"` + os 6 primeiros dígitos da matrícula, montado na tela |
| Nome civil | `insuredName` | `NOM_PESSOA` |
| CPF | `cpf` | `COD_CPF` |
| Produto | `product` | `NOM_PRODUTO` |
| Telefone | `phone` | `NUM_DDD_TEL_CEL` + `NUM_TEL_CEL`; sem celular, cai no `..._RES` |
| E-mail | `email` | `DES_EMAIL` |
| Renda Individual | `individualIncome` | **`VLR_RENDA_FORMAL`** |
| Rodapé (faixa cinza) | vários | repete proposta, CPF, nome, produto, **prêmio**, data, agência e matrícula |
| Bolinha verde do rodapé | — | **nenhuma** — decorativa, sempre verde |

### O que saiu da tela em 2026-09-01

Todos eram **literais escritos no código**, iguais em toda proposta — a carga
não traz nenhum deles:

| Campo | O que exibia |
|---|---|
| Sexo | `"Masculino"`, em toda proposta |
| Profissão | `"SUPERV, INSPETOR E AGENTE DE COMPRAS/VENDAS"` |
| Estado Civil | `"Solteiro"` |
| Seção **Dados do Beneficiário** inteira | `"Herdeiros Legais"` / `"Herdeiros Legais"` / `"100%"` |

E um que **ficou, mas trocou de fonte**: *Renda Individual* exibia `value`, ou
seja o **`VLR_PREMIO`** — o rótulo de um dado com o número de outro. Agora lê
`VLR_RENDA_FORMAL`. Onde a carga não trouxer a renda, o campo some da tela em
vez de mostrar outro número no lugar.

`tests/test_pio_regiao.py` reprova a volta de qualquer um desses literais e o
reencontro entre renda e prêmio.

### Colunas da carga que a tela ainda NÃO usa

`AREA_PRODUTO`, `VLR_IMP_SEGURADA` (capital segurado), `COD_PLANO`,
`NOM_LOGRADOURO`, `NOM_BAIRRO`, `NOM_CIDADE`, `NUM_CEP`, `STA_SITUACAO`,
`STA_PAGO`, `DTH_ALTERACAO`, `DES_JUST_CANC`.

As quatro primeiras da lista (`area_produto`, `imp_segurada`, `cidade`, `uf`) e
mais `situacao`/`pago` **já vêm no JSON** de `/pio/propostas` — colocá-las na
tela é trabalho só de front. As demais exigem mexer no `SELECT` do router.

⚠️ `NOM_CIDADE` deixou de aparecer quando o campo Região passou a mostrar a
região do IBGE (decisão do usuário em 2026-09-01). O dado continua vindo na API.

## Conferência da carga (rodar no DMDB41 depois de cada mudança na proc)

Três perguntas que a tela não faz e ninguém percebe se a resposta mudar:

```sql
-- 1. Os cards 2 e 3 se sobrepõem? (as três linhas devem dar ZERO)
SELECT 'card2 com proposta paga'      AS conferencia, COUNT(*) AS qtd
  FROM dbo.PIO_PROPOSTA_PEND_PGTO_DET   WHERE STA_PAGO = 'S'
UNION ALL
SELECT 'card3 com proposta nao paga',  COUNT(*)
  FROM dbo.PIO_PROPOSTA_ASSINA_PAGA_DET WHERE STA_PAGO <> 'S'
UNION ALL
SELECT 'mesma proposta nos dois',      COUNT(*)
  FROM dbo.PIO_PROPOSTA_PEND_PGTO_DET p
  JOIN dbo.PIO_PROPOSTA_ASSINA_PAGA_DET a ON a.COD_PROPOSTA = p.COD_PROPOSTA;

-- 2. O COD_CARD coube inteiro? (nenhuma linha deve voltar)
SELECT DISTINCT COD_CARD FROM dbo.PIO_AGG
 WHERE COD_CARD NOT IN ('PEND_ASSIN','PEND_PGTO','ASSINA_PAGA');

-- 3. A AGG bate com as DET? (as diferenças devem ser 0)
SELECT a.COD_CARD, a.QTD_PROPOSTAS,
       (SELECT COUNT(*) FROM dbo.PIO_PROPOSTA_PENDENTE_DET)    AS det_pend_assin,
       (SELECT COUNT(*) FROM dbo.PIO_PROPOSTA_PEND_PGTO_DET)   AS det_pend_pgto,
       (SELECT COUNT(*) FROM dbo.PIO_PROPOSTA_ASSINA_PAGA_DET) AS det_assina_paga
  FROM dbo.PIO_AGG a
 WHERE a.DTH_REFERENCIA = (SELECT MAX(DTH_REFERENCIA) FROM dbo.PIO_AGG);
```

## Backlog

- **Nome do vendedor** (fase 2): `NUM_MATRICULA` vem no formato CEF
  `0000161406-9`; para exibir o nome é preciso normalizar e cruzar com
  `WORK_GEPLAC.dbo.TB_VENDA_MATRICULA_VIDA`. Normalização:
  `CAST(CAST(LEFT(NUM_MATRICULA, CHARINDEX('-', NUM_MATRICULA)-1) AS BIGINT) AS VARCHAR)`.
- **Gráfico de tendência** a partir da `PIO_AGG_HIST` — a tabela já é carregada,
  mas nenhuma tela a lê ainda.
- **Sub-status na consulta**, para o card Pendentes de Pagamento voltar a
  oferecer o recorte por forma de pagamento.
