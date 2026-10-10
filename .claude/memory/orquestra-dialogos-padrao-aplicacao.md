# Diálogos no padrão da aplicação — candidato2.12.5

Pedido de 10/10/2026: auditar mensagens nativas Chrome e seguir design system existente. Branch fix/dialogos-padrao-aplicacao, baseada na develop após PR488/DEV2.12.4.

13 chamadas confirm/prompt e um alert substituídos por Modal/Input/Button e Toast compartilhados. Fila global cancela por rota/token; guardas de draft/revision/fence impedem intenção atrasada. O beforeunload obrigatório do navegador é a exceção ao fechar/recarregar aba com alterações.

QA e segurança manual aprovados. Pytest7225PASS, mesmas8falhas/51skips; build/tsc-b PASS. Evidências privadas /root/orquestra-dialogos-evidencias. Lint comparado por assinatura, revisão visual, backup, entrega e smoke final devem constar no registro compartilhado final, que substitui este snapshot de candidato. Não autoriza main/produção. Paridade/performance F6 permanece fora desta correção.
