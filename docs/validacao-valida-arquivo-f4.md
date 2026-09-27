# Validação — F4: configuração original e diagnóstico durável

Base comparada: main 8cf356b; fase empilhada sobre F3 #458. Sem merge ou deploy.

- Suíte completa: **7042 passed, 51 skipped, mesmas 8 falhas da main** (API v2.4 ×4, rodapé Kanban ×3, smoke de autenticação ×1). Nenhuma falha nova.
- SQL Server real em banco temporário: migrations 130–132 reaplicadas; retomada preservou diretório e política originais; nova corrida recebeu edição; diagnóstico de erro persistiu; duas escritas simultâneas da mesma tentativa produziram um registro; falha injetada na inserção de entrada desfez a tentativa inteira. Banco removido ao final.
- TypeScript, build e comparação ESLint aprovados: 71 achados distintos herdados, nenhum novo. Dist inalterado; fontes sem NUL.
- Revisão adversarial funcional e auditoria de segurança independentes: nenhum defeito confirmado restante. Histórico API não retorna catálogo, ciphertext ou código Python; decisões/motivos são reconstruídos a partir do snapshot, sem confiar no resultado recebido.

Artefatos locais: `/root/orquestra-valida-f4-evidencias/` (full-pytest.log, sql-smoke.json, lint-comparison.json, tsc.log, build.log). Testes permanentes em `tests/test_valida_arquivo_registro.py`.

## Limites

Runtime ainda não ativado: executar a avaliação, persistir antes de lançar falha e liberar destinos será integrado na F5. F6 entrega a interface. SQL real comprova persistência, não certifica DataStage. Usuário confirmou que arquivo/dataset DataStage real só está disponível no ambiente Caixa; roteiro assistido permanece obrigatório.
