# PIO — Cards 1 a 6 no novo contrato de leitura — v2.6.14

Origem: "PIO - contrato de leitura das tabelas finais para desenvolvimento" (19/11/2026, SQL14 / DMDB41 / dbo).
Os nomes das tabelas e a conexão não mudam; mudam as colunas lidas e o que a tela diz.

## O que muda
- **Cards 1, 2 e 3 — endereço é o da AGÊNCIA.** A API deixa de ler `NOM_CIDADE`/`NOM_UF` (endereço do segurado, que a
  nova extração não preenche) e passa a ler `NOM_AGENCIA`, `DES_ENDERECO_AGENCIA`, `NOM_CIDADE_AGENCIA`,
  `SIG_UF_AGENCIA` e `CEP_AGENCIA`. Não há COALESCE entre endereço de pessoa e de agência.
  - Lista: "Região" vira **"Região da agência"** (derivada de `SIG_UF_AGENCIA`).
  - Resumo do seguro › Dados da Venda: **"Agência"** mostra número e nome; novo campo **"Endereço da Agência"**
    (endereço · cidade/UF · CEP). `CEP_AGENCIA` é `int` na origem e é formatado com oito posições só na apresentação.
- **Card 4 — situação.** `DES_COD_SIT_CONTRATO` é exposto (`cod_situacao`) e aparece ao lado da descrição recebida em
  `NOM_SUB_SITUACAO` ("Pendente (cód. 0)"). Nenhuma situação é filtrada ou traduzida: 0, 1, 9 e E aparecem como vierem.
  Lista segue agrupada por certificado; prêmio e contratos seguem vindo da AGG.
- **Card 6 — data.** Rótulo **"Data de Venda (quitação)"**: `DTH_VENDA` agora deriva de `DATA_QUITACAO` na origem.
- **Cards 4, 5 e 6:** passam a ler também `NOM_AGENCIA`, `DES_ENDERECO_AGENCIA` e `CEP_AGENCIA` (mesma apresentação).
- **Card 5:** sem mudança de código (layout mantido; o contato unificado já prioriza o celular via `TIP_CONTATO`).
- **Cards 7 e 8 e a busca em todos os cards:** não mudam.
- `AREA_PRODUTO` (agora `varchar(20)`): a API e a tela não têm limite de tamanho; coberto por teste.

## Atenção
- **Fotos antigas** (anteriores à nova extração) têm os campos novos `NULL`: a tela mostra "Região da agência: Não
  informada", a agência só com o número e omite o endereço. Isso não é defeito. **Não validar a entrega com foto antiga.**
- **As colunas novas precisam existir** nas FAT dos Cards 1 a 6 em produção (o contrato diz que já existem). Se faltar
  uma, a lista do card fica "indisponível" (nunca zero); o número do card (AGG) não é afetado.
- As queries de carga dos Cards 4 a 6 têm o ano **2026 fixo**: revisar antes da virada para 2027 (carga, não aplicação).

## Deploy (produção — exige autorização própria)
`scripts/deploy_prod.sh`: migration 155 → **s**; `config/` → **n**. Atualiza `api/` (reiniciar `orquestra-api`) e
`dist/`. Sem tabela nova, sem `dags/`, sem variável de ambiente.

## Smoke (após uma carga diária bem-sucedida posterior à mudança da extração)
1. `CTL_ORQ_CARD0N_LOTE` com lote `PUBLICADO` da data nova (Cards 1 a 6).
2. Cards 1 a 3: abrir a lista → "Região da agência" preenchida; Resumo do seguro → Agência com nome e "Endereço da
   Agência" com CEP de oito posições.
3. Card 4: situações além de "1" e "9" aparecem com descrição e código; Resumo lista as críticas por certificado;
   o número do card bate com `SUM(QTD_CONTRATOS)`/`SUM(VLR_PREMIO_TOTAL)` da AGG da mesma foto.
4. Card 6: Resumo mostra "Data de Venda (quitação)".
5. Abrir uma foto antiga (se a tela permitir escolher data): abre sem erro, com os campos novos não informados.

## Rollback
Reverter o código (`api/` + `dist/`). A versão anterior lê `NOM_CIDADE`/`NOM_UF`, que continuam existindo na FAT.
