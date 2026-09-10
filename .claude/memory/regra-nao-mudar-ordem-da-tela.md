---
name: regra-nao-mudar-ordem-da-tela
description: "NÃO alterar a ordem/posição dos objetos numa tela sem pedido claro do usuário; na dúvida, perguntar ANTES de mexer"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 8a380743-1bf5-4253-ace6-207c3d764c4b
  modified: 2026-09-01T10:24:50.754Z
---

**Não mudar a ordem nem a posição dos elementos de uma tela sem solicitação
clara do usuário.** Se a mudança pedida esbarrar em layout — ou se houver
qualquer dúvida sobre o que se move e o que fica —, **perguntar ANTES de
alterar**, nunca decidir sozinho e mostrar o resultado depois.

**Why:** o usuário apresenta essas telas e conhece a ordem de cor; um bloco que
troca de lugar por iniciativa minha quebra a familiaridade de quem já usa e a
demo de quem apresenta, mesmo quando "fica melhor". Reordenar não é arrumação
de passagem — é mudança de produto. Dito em 2026-09-01, quando o ajuste do
buscador em `/caixa-seguro` levantou a pergunta de mover junto a tabela de
resultados (ver [[orquestra-caixa-seguro-poc]]).

**How to apply:**
- Vale para qualquer tela de qualquer projeto (Orquestra, LC Decorações,
  NexxaFarma, landing pages).
- Mexer em cor, espaçamento, texto ou comportamento **não** autoriza reordenar
  o que está em volta. Só move o que foi pedido.
- Quando a correção pedida implicar mover mais de um bloco, usar
  `AskUserQuestion` com as ordens desenhadas lado a lado (ASCII no `preview`) —
  foi assim que funcionou bem da primeira vez.
- Movimento aprovado vira **comentário no código, no ponto exato**, dizendo que
  foi decisão explícita e qual era a posição anterior — senão a próxima
  passagem "conserta" de volta achando que é engano.
