# Validação — Valida Arquivo F3

27/09/2026. Base main 8cf356b, código sobre F2b cb6889d. F3 não ativa novo tipo na UI/fábrica.

- 202 testes direcionados e de migrations aprovados: políticas, literal, segredo, caixa/extensão, cabeçalho e última linha, grafo e seus dez tipos de destino, decisão binária/switch, convergência, erros da API, permissão e timeout cobrindo negociação exec/SFTP.
- Anti-drift por bytes entre contrato API e worker.
- SQL Server real isolado: migration131 aplicada duas vezes, duas edições concorrentes (uma aceita e outra em conflito), FK de destino e rollback integral, alteração de política e leitura. Banco temporário removido.
- QA adversarial e auditoria de segurança independentes: nenhum defeito confirmado restante após correções. Reproduções corrigidas: convergência no alvo, ramos da decisão omitidos, tipo malformado virando500 e negociação SSH sem prazo.
- Smoke SSH/SFTP real: worker Airflow conectado ao servidor de amostra, arquivos temporários vazio/cabeçalho/dados sem newline/ausente corretos; arquivos removidos ao final. Não é DataStage.
- Quatro testes antigos de frescor capturavam o relógio na coleta e falhavam se o runner demorasse mais de um minuto. Fixture local estabiliza somente o relógio do teste; nenhum código de Chamados alterado.
- Não há frontend alterado; validações de TypeScript/lint mantêm contrato existente. Suíte completa: **7024 aprovados, 51 pulados e as mesmas 8 falhas da main**; sem regressão nova. TypeScript, lint (178 mensagens vs180, nenhuma nova) e build aprovados, dist idêntico ao da F2b.

Evidências sanitizadas em `/root/orquestra-valida-f3-evidencias/`. DataStage real ainda não certificado; testes de parser são contratos, não evidência da versão instalada. Sem merge/deploy ou alteração de arquivo de cliente.

Confirmação do usuário: datasets DataStage só podem ser validados no ambiente Caixa. O smoke será assistido nesse ambiente; não bloqueia o restante da implementação/QA local e não foi marcado como concluído.
