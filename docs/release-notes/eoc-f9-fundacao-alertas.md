# EOC-F9A — Fundação persistente de alertas (2.27.0)

Evento e intenções são gravados numa transação, com deduplicação por evento, política original e referência do destino. Tentativas têm schema próprio, sem corpo da mensagem ou credenciais. O dispatcher será entregue na F9B; esta entrega parcial não habilita envio ou ingestão de resultados de clientes.

Deploy DEV autorizado: backup COPY_ONLY/CHECKSUM e RESTORE VERIFYONLY, migrations179 e180 nessa ordem, somente API se necessário. Sem alteração de UI/dist, DAG, .NET, dependência ou env. Não recriar DB/volumes. Schema ausente retorna503 nomeando179. Rollback de código preserva tabelas e fila; não apagar dados.

Smoke: saúde/login/versão2.27.0, SHA e assets iguais ao candidato, duas migrations aplicadas/idempotentes; fixture própria SQL comprova snapshot original, concorrência, dedup e rollback parcial; capacidades continuam indisponíveis e não existe rota de ingestão. Nenhum job deve rodar para provar entrega. F9B e gate de resultado/geração permanecem no Backlog. Main/produção não autorizadas.

Validação candidata: 7996PASS, exatas8FAIL pré-existentes e51SKIP (8055 testes,165.94s), comparados ao DEV1acf4919/F8; ESLint176=baseline, zero assinatura nova. UI/dist idênticos: tsc/build/visuais F8 reutilizados. Revisão independente ampla e confirmação dirigida após deadlock real corrigido; SQL com8writers mesma chave e8eventos distintos, rollback parcial, reconexão, constraints e migrations2x. ASGI/SQLreal valida prévia3/0 e auth negativa com limpeza. Nenhum scanner automatizado alegado.
