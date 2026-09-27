# F7 — Fechamento documental e aceite assistido

A implementação local F1–F6 e a documentação F7 estão preparadas. **O aceite operacional F7 não está concluído**: depende de aplicação autorizada e da matriz de ensaio no ambiente Caixa, único local autorizado para testar DataStage real. Nenhuma evidência local substitui essa etapa.

## Documentos entregues

- `manual-parametros-valida-arquivo.md`: cadastro, importação, referências, canvas, políticas, acompanhamento e retomada.
- `release-notes/parametros-valida-arquivo-caixa.md`: cadeia de implantação, configuração administrativa, certificação de parsers, caso real a preencher, matriz A–L/extra, rollback e registro de aceite.
- `MANUAL_USUARIO.md`: entrada para os guias da funcionalidade.
- `spec-parametros-globais-valida-arquivo.md`: estado atualizado sem marcar certificação externa como concluída.

## Cobertura e limites

| Camada | Evidência local | Limite |
|---|---|---|
| Contrato e parâmetros | Testes unitários/anti-drift, APIs, SQL real F1–F4 | Saída real dsjob ainda não certificada |
| Texto e diagnóstico | SSH/SFTP real de amostra; contagem/header/timeout/erros; SQL por tentativa | Não valida arquivos de negócio Caixa |
| Grafo e publicação | F5: nove cenários Airflow 2.11.2 + SQL/SFTP, com replay parcial | Execução real exercitada com Shell/Aguarde/Decisão de ensaio; não certifica efeitos reais dos dez tipos |
| Dez tipos controlados | Contrato/fábrica/guardas e seletor genérico em testes | Matriz operacional dos dez tipos continua no roteiro Caixa |
| UI e transação | F6: SQL real atômico/CAS/FKs/rollback; navegador/teclado/claro/escuro e editor completo | API do navegador usa fixture; SQL e runtime reais exercitados em bancadas separadas |
| Retomada | Snapshot original, identidade execution_id, tentativas/provas antigas e replay testados | Replicar cenário com pipeline e arquivos reais na Caixa |
| Frescor e limpeza | Item preparado na migration 128 | Funcionalidade fora do escopo; limpeza diária é premissa informada |

Revisão adversarial documental: aprovada com ressalva operacional; nenhum defeito confirmado. Não há código de produto novo na F7. Regressão, tipos, lint e build devem manter os resultados da F6; o registro final da PR informa as verificações efetivamente concluídas.

## Próximo passo externo

Após integrar e implantar o conjunto autorizado, preencher a configuração real de ensaio, certificar formatos dsjob/orchadmin e executar a matriz na Caixa. Somente o aceite registrado permite declarar integração DataStage validada. Não houve merge, deploy ou alteração de pipeline real nesta entrega.

## Verificação final do checkout F7

Pytest: **7094 passed, 51 skipped, mesmas 8 falhas preexistentes** (4 test_api_v2_4, 3 test_kanban_rodape_card, 1 test_smoke). Zero falha nova. `tsc -b` aprovado; ESLint71achados distintos idênticos à base normalizada; build aprovado, dist idêntica à F6. Cinco links locais verificados, nenhum ausente; documentos novos sem NUL; diff sem erro de whitespace. Evidências locais em `/root/orquestra-valida-f7-evidencias/`.
