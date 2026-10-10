---
name: Ajustes de cadastro e ligações do workspace
description: Correção após F6 de nomes, seleção/exclusão e catálogos/agendas; candidato 2.12.2
type: project
---

09/10/2026. Pedido do usuário: nome ultrapassa cartão, ligação não destaca seleção, exclusão usa confirmação do navegador, criação não recupera projeto/domínio anteriores e agenda só sob demanda.

Branch fix/workspace-cadastro-conexoes, baseada em develop5b60379. Correção preserva o sistema visual: títulos contidos em duas linhas; seleção de ligação por identidade estável, botão de remoção e Modal compartilhado para ligações/etapas; catálogos legados; oito agendas e calendário; validação quinzenal no adaptador Python. Valores nulos de dia mantêm a compatibilidade anterior. Não muda snapshots publicados, lease, autorização nem motor.

Validação pré-integração: 7220 pytest PASS, oito falhas preexistentes e 51 skips; módulo de publicação49 PASS; build/tsc-b PASS; lint75 assinaturas sem novas; navegador12 PASS com fixtures sintéticas. QA adversarial e segurança APROVADO. Relatórios privados /root/orquestra-ajustes-evidencias. Migration150 registra2.12.2; deploy exige backup e restartorquestra-api. Integração por uma PR para develop e DEV autorizada; produção/main não autorizada.

Estado deste snapshot: candidato antes de merge/deploy. A confirmação final de SHA, versão, backup e smoke real será registrada em /srv/segundo-cerebro/registros/orquestra/ e na memória viva após entrega. Outros itens da paridade F6 não são cobertos por este ajuste.

Why: recuperar comportamento solicitado do cadastro antigo mantendo o fluxo novo.
How to apply: conferir estado no DEV/GitHub e registro final antes de inferir que o candidato foi entregue.
