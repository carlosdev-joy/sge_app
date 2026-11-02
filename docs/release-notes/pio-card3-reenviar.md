# Botão "Reenviar Proposta" no Card 3 — v2.6.11

Pedido do Carlos em 03/11/2026.

## O que muda
Na lista de propostas do **Card 3 (Assinadas e Pagas)**, cada registro ganha o botão **"Reenviar Proposta"**, ao lado direito, no mesmo lugar dos botões dos outros cards.
- **Por enquanto o botão é sem ação**: **nada é enviado**. O clique só mostra o alerta **"Proposta reenviada."** (pedido explícito do solicitante, como etapa inicial).
- ⚠️ Como o alerta diz "reenviada" sem que exista envio, **quem opera pode achar que a proposta foi reenviada**. Comunicar aos usuários que o botão ainda é um marcador, ou trocar o texto
  do alerta, até haver integração real.
- Os demais cards, a busca e o Resumo do Seguro não mudam.

## Para ligar o envio de verdade (futuro)
Definir: para onde o reenvio vai (e-mail, WhatsApp, sistema), com que permissão, se registra auditoria e se o alerta passa a refletir o resultado (sucesso ou falha). O ponto de entrada é o
`onClick` do botão em `InlineWorkflow.tsx` (`data-testid="reenviar-proposta"`).

## Deploy (produção — exige autorização própria)
`scripts/deploy_prod.sh`: migration 151 → **s**; `config/` → **n**; só `dist/` e migration de versão. Sem mudança de API, tabela ou carga.

## Smoke
Card 3 → lista: cada registro mostra "Reenviar Proposta"; clicar mostra o alerta "Proposta reenviada." e **não** abre o Resumo do Seguro; os Cards 1, 2 e 4–8 sem o botão.

## Rollback
Reverter o código (`dist/`).
