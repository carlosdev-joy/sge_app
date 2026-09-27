# Validação — F2b

Data: 27/09/2026. Base main 8cf356b; implementação sobre F2a 681a724. Sem alteração do banco do produto nem deploy.

- Pytest completo comparado à main: mesmas oito falhas preexistentes (test_api_v2_4 ×4, test_kanban_rodape_card ×3, test_smoke ×1); nenhum defeito novo nessa comparação. Resultado final: **6957 aprovados, 51 pulados, 8 falhas preexistentes**. Main: 6861 aprovados, 79 pulados e as mesmas oito falhas.
- 54 testes direcionados aprovados após as correções de payload parcial, identidade de reexecução, servidor efetivo, rollback e proteção de retomada.
- Build final aprovado, dist recompilado após a última alteração de UI. TypeScript `tsc -b` aprovado. ESLint sem achados novos por arquivo/regra/severidade/mensagem; normalizados apenas números de linha embutidos nas duas mensagens preexistentes de hooks.
- SQL Server real em banco temporário removido ao terminar: migration 130 aplicada duas vezes, duas capturas concorrentes geram um snapshot, conteúdo cifrado, retry preserva original, novo run recebe novo valor, publicação incompatível bloqueada, retry sem original recusado.
- Navegador com componentes reais e API simulada: selecionar/remover vínculo Python, caminho direto, destinos DS/ORQ, segredo protegido e retomada readonly. Desktop/celular (1280, 390 e 320 px), claro/escuro, sem overflow nem erro JS. Não equivale a execução Airflow/DataStage.
- Detector Impeccable nos componentes novos/alterados desta fase: nenhum achado.
- Revisão adversarial independente concluída sem defeito confirmado restante, com ressalva de smoke operacional real. Achados corrigidos: configuração parcial Python, override ignorado, retomada por execution_id, retomada após mudança estrutural e SSH efetivo DS.
- Auditoria de segurança estática independente: nenhum defeito confirmado; conferiu Fernet, máscara, SQL parametrizado, permissões e quoting dos caminhos Python.

Evidências locais sanitizadas: `/root/orquestra-parametros-f2b-evidencias/` (logs de testes, resultados JSON, capturas e scripts). Não contêm credenciais.

Limite: DataStage instalado não foi exercitado. As etapas seguintes da spec incluirão o smoke Airflow para os novos controles de grafo; operação em ambiente final exige validação conforme release note.
