# Header ORQ no Outlook escuro

O print do usuário confirmou inversão parcial: o Outlook clareou o fundo Navy em
CSS, mas preservou o PNG do logo. O header fica incoerente mesmo com `bgcolor` e
metadados `color-scheme: light only`. A inversão de cores do Outlook Windows é
registrada nos testes da [Litmus](https://www.litmus.com/blog/the-ultimate-guide-to-dark-mode-for-email-marketers).

A correção incorpora o header inteiro (fundo, logo e assinatura) em um PNG local
via `cid:orq-header@orquestra`. Fonte editável: `docs/branding/orq-email-header.html`;
exportação: `python3 scripts/export_orq_email_header.py`. PNG 1200×416, 57 KB,
exibição fluida até 600×208. Assinatura de 20 px no original resulta em 12 px na
largura de 360. Alt preserva a descrição institucional e a alternativa text/plain.
Dados da execução, marcadores, anexos e filete permanecem como antes.

API e worker continuam aceitando o CID anterior, mantendo modelos existentes.
Migration 115 altera somente o corpo original da 114, com SHA256 repetido no
EXISTS e UPDATE. Modelos personalizados devem ser adaptados explicitamente.
Não editar a 114 já aplicada. Nenhuma dependência ou configuração nova.

Deploy: atualizar API e assets, dags/utils e assets, dist; reiniciar worker e
scheduler antes de aplicar 115. A etapa 6c do deploy padrão deve respeitar essa
ordem para que modelos novos não sejam enviados por módulos antigos.

Validação: MIME e anexos, texto simples, compatibilidade dos dois CIDs, prévia
sandbox em 800/360 px, build/TypeScript, ESLint sem novos achados; pytest 5427
aprovados, 8 falhas conhecidas, 50 ignorados. Revisões adversarial e segurança
aprovadas. Nenhum envio real foi executado. Chromium não simula o motor do Word;
confirmar cores no próximo recebimento em Outlook escuro e claro. Mensagens já
recebidas não são alteradas por esta correção. Com imagens bloqueadas, o cliente
poderá mostrar apenas o texto alternativo até liberá-las.
