# Card 6 do PIO lê a foto diária — v2.6.7

Chamado **RITM0118511** (Card 06 — Propostas Rejeitadas, Vida em Grupo; prazo 06/11/2026).

## O que muda
O Card 6 (**Rejeitadas**, `SIT_REGISTRO='2'`) lê as tabelas de consumo da foto do Fabric
(`AGG`/`FAT`/`CTL_ORQ_CARD06_*`, schema `dbo`, DMDB41). Número do card, lista, Resumo, Histórico e Enviar usam a
mesma foto (data + lote). Os demais cards e a busca global seguem como estavam.

**Granularidade = certificado (`NUM_SIVPF` = `NUM_CERTIFICADO`).** A FAT tem uma linha por motivo; o certificado repete.
- **Card:** prêmio em destaque (`SUM(VLR_PREMIO_TOTAL)` da AGG, uma vez por certificado) e, abaixo em fonte menor, a
  quantidade de contratos (`SUM(QTD_CONTRATOS)`). Sem prêmio informado mostra "—"; prêmio parcial avisa no tooltip.
- **Lista:** uma linha por certificado (`GROUP BY NUM_SIVPF`); total = contratos do card. **A contagem em dias ao lado de
  "Rejeitada" e o botão "Gerenciar Devolução" saem deste card** (pedido do chamado).
- **Resumo do Seguro:** "Proposta/Certificado"; sem "Usuário" e rodapé; **motivos da rejeição como última informação de
  Dados da Venda** (`DES_MSG_CRITICA` + `DES_COMPLEMENTAR`, rota nova `GET /pio/card6/motivos?certificado=`, só leitura).
- **Workflow da proposta:** a linha do tempo da rejeitada termina em **"Proposta Rejeitada"** (vermelho), não em "Proposta Emitida".
- **Histórico:** Situação, Motivos, Declínio e Quitação.
- **Fora do escopo:** mapa do Brasil (mesma decisão dos Cards 4 e 5); o mesmo ajuste de Workflow nos demais cards.
- "Região" fica vazia: UF/cidade são da **agência de cobrança**, não do segurado.

⚠️ A foto é um **estoque do ano corrente**; fotos de dias diferentes nunca se somam como "novas rejeições".
`QTD_MOTIVOS` conta linhas da query, não eventos históricos distintos. A origem não filtra `STA_CRITICA` e usa
`>= início do ano` sem limite superior: regra da CARGA, não reaplicada pela API.

## Deploy (produção — exige autorização própria; nada é executado por este documento)
1. **Preflight, só leitura**, no DMDB41: um lote `PUBLICADO` na data, conciliação AGG × FAT, `SELECT` do login da aplicação
   nas três tabelas, colunas `QTD_CONTRATOS`/`QTD_MOTIVOS`/`QTD_PREMIOS_INFORMADOS`/`VLR_PREMIO_TOTAL` na AGG e
   `DTH_DECLINIO`/`DIAS_VENDA_DECLINIO`/`COD_MSG_CRITICA` na FAT.
2. `scripts/deploy_prod.sh`: migrations pendentes (141–146 se ainda não aplicadas, e a 147) → **s**; `config/` → **n**.
3. Validar: contratos e prêmio do card × consulta 1 da carga; total da lista = contratos; Cards 1–5 e 7–8 inalterados.

## Smoke (a–h)
a) Preflight ok. b) Card "Rejeitadas" = prêmio/contratos da foto (02/11: 2.087 contratos, R$ 940.842,79). c) Lista: uma linha por
certificado, total = contratos, paginação sem repetir; sem dias e sem "Gerenciar Devolução". d) Resumo: motivos por último em
Dados da Venda. e) Workflow termina em "Proposta Rejeitada". f) Histórico e Enviar com o contato da foto. g) Cards 1–5, 7–8 e
busca global inalterados. h) Sem permissão/tabela: "—".

## Rollback
Reverter o código (API + `dist/`). Tabelas e pipeline Fabric não são tocados.

## Pontos para o solicitante validar
- O Workflow da rejeitada assume assinatura e pagamento concluídos antes da rejeição (todas as linhas da foto têm quitação);
  o chamado pede "status real, padronizado para todos os cards" sem desenhar o fluxo — homologar.
- `VLR_IS_VENDA` vem da linha do motivo (`CRI.VLR_IS`); a carga validou prêmio e contexto únicos por certificado, mas não a IS:
  a lista usa `MIN()` por certificado.
- `TOP 1`/`NOLOCK` nos contatos da origem, e datas futuras possíveis (sem limite superior): regra preservada.
- O botão de devolução desta tela sai; o fluxo de devolução existente segue no Card 7.

## Pendências conhecidas
- Mapa do Brasil e geografia comum (agência × segurado); Workflow real nos Cards 3, 4 e 5 (cancelada); alertas/identidade de serviço e CU(s) do pipeline.
- Numeração 140+ a reconciliar com o `develop`. `pio_card6.py` é o 6º router do padrão (débito: fábrica comum).
