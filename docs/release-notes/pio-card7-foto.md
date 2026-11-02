# Card 7 do PIO lê a foto diária — v2.6.8

Chamado **RITM0118567** (Card 07 — Devolução de Prêmio, rejeitadas VG + AP; prazo 06/11/2026).

## O que muda
O Card 7 (**Devolução de Prêmio**) lê as tabelas de consumo da foto do Fabric (`AGG`/`FAT`/`CTL_ORQ_CARD07_*`, schema `dbo`,
DMDB41), uma linha por contrato (VG = certificado, AP = bilhete, sempre com o segmento). Os demais cards e a busca global seguem como estavam.

- **Card principal:** valor devolvido em destaque (`SUM(VLR_DEVOLUCAO_TOTAL)`, **todos os status**, inclusive pendentes e cancelados) e,
  abaixo em fonte menor, a quantidade de contratos. ⚠️ É valor de **devolução**, não prêmio.
- **Clicar no card não lista nada.** Aparecem 3 sub-cards — **Devolução Realizada**, **em Andamento** e **Pendente** — cada um com valor e
  contratos; a lista só abre ao clicar em um deles (clicar de novo desmarca). Sem sub-card, nenhuma lista. Os 3 somam o card.
- **Classificação** (regra única no backend, `_bucket`; decisão do usuário em 02/11):
  | Sub-card | VG (`COD_SIT_MOVIMENTO`) | AP |
  |---|---|---|
  | Realizada | `1` Devolvido (crédito efetivado), `F` Finalizado | `2` |
  | Em Andamento | `3` Enviado/aguarda retorno, `7` Reprogramado, `8` Processando | — |
  | Pendente | sem movimento (nulo), `0`, `2` Retornado com pendência, `8` **Cancelado** (restrição na conta), qualquer código desconhecido | sem movimento (nulo) e qualquer outro |
  `8` Processando × Cancelado vem de `DES_SIT_MOVIMENTO` (a origem usa `CODRET`, que não é guardado).
- **Lista de cada sub-card:** selo com o **status real** do último movimento, na cor do sub-card (verde, âmbar, vermelho); sem "dias".
- **Resumo do Seguro (devolução):** linha do tempo na **etapa real** (pendente → valor disponível; em andamento → devolução programada;
  realizada → pagamento efetivado); **Dados da Devolução** com valor devolvido, status, data do crédito (**data prevista** em andamento),
  instituição (código do banco), agência, operação, conta e dígito da conta. Os dados bancários só saem em `GET /pio/card7/devolucao`,
  aberto no Resumo de um contrato — **nunca na lista**.
- **Fora do escopo desta entrega (decisão do usuário):** dados bancários **editáveis** + Salvar, botão **Gerar Nova Venda** (Portal de Vendas),
  layout global (área dos cards fixa, sem a barra Workflow), mapa do Brasil e o Workflow real nos demais cards.

## Lacunas da fonte (a foto do Card 7 NÃO traz)
- **E-mail, telefone e celular do cliente**: a tela diz "Não disponível nesta foto". Pedir à frente de dados incluir os contatos.
- **Nome do banco** (só `COD_BANCO`) e **dígito da agência**; **operação** só existe em VG.
- **Motivos de declínio** (pedido: última informação de Dados da Venda, como no Card 6): a foto do Card 7 não tem `COD_MSG_CRITICA` etc.
  Avaliar ler da foto do Card 6 por certificado (só cobre VG com declínio no ano corrente) ou incluir na carga.
- "Data do crédito" = `DTH_VENCIMENTO_MOV` (em AP vem de `DATA_QUITACAO`, conforme a fonte): **homologar** que é a data do crédito.

## Deploy (produção — exige autorização própria; nada é executado por este documento)
1. **Preflight, só leitura**, no DMDB41: um lote `PUBLICADO` na data, conciliação AGG × FAT, `SELECT` do login da aplicação nas três tabelas,
   colunas `QTD_CONTRATOS`/`VLR_DEVOLUCAO_TOTAL`/`QTD_VALORES_INFORMADOS` na AGG e `COD_SIT_MOVIMENTO`/`DES_SIT_MOVIMENTO`/`NUM_CONTA_DEBITO` na FAT.
   Conferir os códigos reais: `SELECT SEGMENTO, COD_SIT_MOVIMENTO, DES_SIT_MOVIMENTO, COUNT_BIG(*) FROM FAT … GROUP BY …` — todo código fora do mapa cai em Pendente.
2. `scripts/deploy_prod.sh`: migrations pendentes (141–147 se ainda não aplicadas, e a 148) → **s**; `config/` → **n**.
3. Validar: valor e contratos do card × consulta de resumo da carga (02/11: 6.023 contratos, R$ 1.059.627,20); os 3 sub-cards somam o card; total da lista =
   contratos do sub-card; Cards 1–6 e 8 inalterados.

## Smoke (a–i)
a) Preflight ok. b) Card = valor/contratos da foto. c) Clicar no card: só os 3 sub-cards, nenhuma lista. d) Cada sub-card: total da lista = contratos dele.
e) Selo com o status real. f) Resumo: dados bancários e linha do tempo na etapa certa. g) Contrato AP (bilhete) abre sem erro. h) Cards 1–6, 8 e busca global
inalterados. i) Sem permissão/tabela: "—".

## Rollback
Reverter o código (API + `dist/`). Tabelas e pipeline Fabric não são tocados.

## Pontos para o solicitante validar
- Mapa de status dos sub-cards (tabela acima), em especial `F` Finalizado em Realizada e `7` Reprogramado em Andamento.
- Valor do card = total de todos os status (não só o creditado: o creditado é o sub-card Realizada; na foto de 02/11, 4.198 contratos / R$ 913.997,41).
- `TOP 1` da forma de pagamento sem `ORDER BY`, `NOLOCK` e só o **último** movimento por contrato (não é o histórico de parcelas): regras da origem preservadas.
- Dados pessoais e bancários no analítico: acesso pela mesma permissão `tela_caixa_seguro`; revisar se o perfil operacional deve ver conta bancária.

## Pendências conhecidas
- Itens "Fora do escopo" acima; contatos e motivos de declínio fora da foto; numeração 140+ a reconciliar com o `develop`; `pio_card7.py` é o 7º router do padrão (débito: fábrica comum).
