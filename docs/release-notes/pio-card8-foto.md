# Card 8 do PIO lê a foto diária — v2.6.9

Chamado **RITM0118664** (Card 08 — Sensibilizações = último movimento de propostas Vida; prazo 09/11/2026).

## O que muda
O Card 8 (**Sensibilizações**) lê as tabelas de consumo da foto do Fabric (`AGG`/`FAT`/`CTL_ORQ_CARD08_*`, schema `dbo`, DMDB41), uma linha por
**identificação** (`COD_EMPRESA_SIVPF` + `NUM_IDENTIFICACAO_SIVPF`). Os demais cards e a busca global seguem como estavam.

- **Card:** valor sensibilizado em destaque (`SUM(VLR_SENSIBILIZADO_TOTAL)`) e, abaixo em fonte menor, a quantidade de identificações
  (`SUM(QTD_CONTRATOS)`). ⚠️ O valor é o `VLR_PREMIO` do **último movimento** — não é prêmio pago, receita nem devolução efetivada. Sem valor
  informado mostra "—"; valor parcial avisa no tooltip.
- **Lista:** sem a contagem em dias; selo com o **status real do último movimento** ("Sem status" quando nulo e "Código não identificado" para os
  3 bytes NUL — ~225 mil na foto de 02/11 —, nunca rótulo vazio); número = proposta, e a identificação quando a proposta não existe (LEFT JOIN).
  O texto "as mais antigas primeiro" dá lugar a "por nº de identificação" neste card.
- **Botão "Sensibilizar":** habilita quando a **situação da proposta difere do último movimento encaminhado**. Movimento (`STATUS_ULTIMO_MOV`: EMT, ENV, CAN…)
  e proposta (`SIT_PROPOSTA_ATUAL`: R, S, N…) são domínios diferentes; a comparação usa a equivalência declarada pelo usuário em 02/11, num só lugar
  (`EQUIVALENTES` em `pio_card8.py`): **S Enviado = ENV Enviada; R Integrado = EMT Emitida ou PAI Pago/Aceito**. Fora disso — N, Pendente, código
  desconhecido, sem status — o botão fica habilitado. **O envio do movimento ainda não está integrado**: o clique avisa isso e que nenhum movimento
  foi enviado (sem "sucesso" simulado).
- **Resumo do Seguro:** "Dados da Sensibilização" com **valor do prêmio, movimento encaminhado, data de envio do movimento** (`DATA_GERACAO_LOTE`), data do
  movimento, situação atual da proposta, motivo, identificação, linha de negócio e produto. O **Workflow** mostra os dois estados reais
  (Movimento: X → Proposta: Y). O quadro "Dados do Segurado" some neste card: a foto não traz o segurado.
- **Fora do escopo desta entrega:** mapa do Brasil com filtros Região/Estado/Cidade (mesma decisão dos Cards 4–7), layout global, Workflow real nos demais
  cards, ação real de "Sensibilizar".

## Política de retenção (atualizada em 02/11 — Cards 5 a 8)
A **FAT guarda só hoje, D-1 e D-2** por `DTA_MOVIMENTO` (três datas de calendário, não as três últimas cargas); a **AGG, 36 meses**. Foto mais antiga que D-2
(ou lote sem linhas na FAT) = **detalhe expirado, não "zero propostas"**: `detalhe_disponivel=false`, a tela diz que o detalhe saiu da retenção e o **total
do card segue válido** (vem da AGG). Se a rotina parar por 3 dias, o último PUBLICADO pode ter só agregado.
⚠️ As release notes dos **Cards 5, 6 e 7** foram escritas antes desta política e dizem "fato 24 meses": vale a regra nova (a API deles já trata detalhe
ausente como indisponível, não como zero).

## Desempenho (6,5 milhões de linhas por foto; tabelas do Fabric, sem índice novo)
O **total da lista sai da AGG** (nenhum COUNT na FAT) e a lista ordena por (empresa, identificação), o índice único existente — nunca por data (ordenar 6,5
milhões de linhas a cada página). A consulta de exemplo da documentação ordena por `DATA_ULTIMO_MOVIMENTO DESC`: não foi adotada por isso. Medir no DEV
(foto real) a latência da 1ª página e de uma página profunda; páginas profundas leem `offset + limite` chaves.

**Medir no DEV antes de promover** (a revisão apontou que os testes não provam desempenho): com `SET STATISTICS IO, TIME ON`, o plano e a leitura de (a) a 1ª
página, (b) uma página funda (offset de milhares), (c) o `SELECT TOP 1 1 … WHERE DTA_MOVIMENTO=? AND LOTE_ID=?` de existência — `LOTE_ID` não está no índice único e
é predicado residual: fica barato se o lote publicado tem as linhas, mas varre a data inteira se elas forem de outro lote —, e (d) o `SUM(QTD_CONTRATOS)` da AGG (2,3 milhões
de grupos), que cada página repete para devolver o `total`. Se algum custar caro: `OPTION (FORCE ORDER)`/hint de índice, limitar a profundidade da navegação ou calcular o
total só na 1ª página. Confirmar também que FAT e AGG têm a mesma contagem por lote e se o pyodbc preserva os 3 bytes NUL (se truncar para vazio, o status vira "Sem status").

## Lacunas da fonte e premissas
- A foto **não traz o segurado** (nome, CPF, contato) nem `COD_USUARIO`; `COD_ERRO`, endereço e CEP da agência não são expostos.
- "Data de envio do movimento" = `DATA_GERACAO_LOTE` (premissa a **homologar**; há também `DATA_PROCESSAMENTO_LOTE` e `IND_ENVIO`).
- Geografia é da **agência de venda**; sem cidade do segurado.
- Valor e status representam só o último movimento da janela de 12 meses; limite superior = meia-noite de hoje (regra da origem, preservada).

## Deploy (produção — exige autorização própria; nada é executado por este documento)
1. **Preflight, só leitura**, no DMDB41: um lote `PUBLICADO` na data, conciliação AGG × FAT, `SELECT` do login da aplicação nas três tabelas, colunas
   `QTD_CONTRATOS`/`VLR_SENSIBILIZADO_TOTAL`/`QTD_VALORES_INFORMADOS`/`QTD_STATUS_INFORMADOS` na AGG e `DATA_GERACAO_LOTE`/`SIT_PROPOSTA_ATUAL` na FAT.
   Listar os códigos reais: `SELECT STATUS_ULTIMO_MOV, SIT_PROPOSTA_ATUAL, COUNT_BIG(*) … GROUP BY …` — confirma a equivalência do botão.
2. `scripts/deploy_prod.sh`: migrations pendentes (141–148 se ainda não aplicadas, e a 149) → **s**; `config/` → **n**.
3. Validar: valor e identificações do card × consulta de resumo da carga (02/11: 6.540.472 identificações, R$ 9.532.334.215,69); total da lista = identificações;
   Cards 1–7 inalterados.

## Smoke (a–i)
a) Preflight ok. b) Card = valor/identificações da foto. c) Lista: sem dias, selo com o status real, ordem por identificação, paginação sem repetir.
d) "Código não identificado" e "Sem status" aparecem legíveis. e) "Sensibilizar" habilita/desabilita pela regra; clique avisa, não envia. f) Resumo com valor,
movimento e data de envio; Workflow com os dois estados. g) Foto de D-3 ou mais: "detalhe expirado", total do card intacto. h) Cards 1–7 e busca global inalterados.
i) Sem permissão/tabela: "—".

## Rollback
Reverter o código (API + `dist/`). Tabelas e pipeline Fabric não são tocados.

## Pontos para o solicitante validar
- Equivalência do botão (S = ENV; R = EMT/PAI) e o que fazer quando o status do movimento é nulo ou ilegível.
- O que "Sensibilizar" deve enviar, para onde e com que permissão (hoje não há integração de escrita).
- "Data de envio do movimento" = `DATA_GERACAO_LOTE`? E se o "valor de prêmio" do chamado é mesmo o `VLR_PREMIO` do último movimento.
- `ROW_NUMBER` sem desempate adicional, `TOP 1` do produto sem `ORDER BY` e `NOLOCK` na origem (regras preservadas); a diferença de R$ 565,46 entre o
  diagnóstico e a carga de 02/11 (origem mutável) segue sem causa isolada.

## Pendências conhecidas
- Mapa do Brasil, layout global, Workflow real nos Cards 3, 4, 5, ação real de Sensibilizar; capacidade do SQL14 (projeção: FAT 6,84 GiB, AGG ~758 GiB em 36 meses —
  validar). Numeração 140+ a reconciliar com o `develop`; `pio_card8.py` é o 8º router do padrão (débito: fábrica comum).
