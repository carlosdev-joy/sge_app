# UX profissional do Pipeline — progresso das fases

Atualizado em 11/10/2026. Fonte dos critérios: [spec](spec-ux-pipeline-profissional.md), [contrato visual](design/pipeline-experiencia.md) e [matriz de preservação](matriz-paridade-pipeline.md).

| Fase | Estado | Registro |
|---|---|---|
| F1 — contrato e protótipo | Referência revisada pelo usuário (documentos `52c0c589`) | [protótipo](prototypes/pipeline-workspace/README.md), [verificação](prototypes/pipeline-workspace/VALIDACAO.md) |
| F3 inicial — cinco destinos e Configuração única | Concluída: 2.18.0, PR #499, `develop` `8a57ac6a` publicado no DEV | [2.18.0](release-notes/2.18.0-pipeline-ux-contexto.md) |
| F3 — aceite combinado | Pendente: percurso integrado salvar → publicar → executar → investigar com capacidades reais e comparação visual com mockups | spec §5 F3 |
| F4.1 — canvas amplo, painéis recolhíveis, barra e diagnóstico | Candidato 2.19.0 na branch `feat/ux-pipeline-montagem-f4`; QA independente e bancadas de navegador aprovadas para o recorte; revisão visual final aprovada após 16 capturas; aguarda commit, PR, DEV e smoke autenticado | [2.19.0](release-notes/2.19.0-pipeline-ux-montagem.md) |
| F4.2 — desfazer/refazer e inspector em subseções | Pendente | spec §Montagem |
| F5 — execução e investigação | Pendente | spec §5 F5 |
| F2 — descoberta e entrada única | Pendente | spec §5 F2 |
| F6 — aceite da jornada | Pendente; sem piloto com usuários até aqui | spec §5 F6 |

Fechamento da 2.18.0 (registro do Codex): DEV em `8a57ac6a`; smoke próprio PASS com duas sessões, incluindo a resposta 409 à sessão concorrente, e limpeza das fixtures; navegador PASS para saída pelo histórico e troca de Experiência com rascunho sujo. Nenhuma execução de motor ou DataStage real; nenhum piloto com usuários.

Malha versionada, monitores, IA e novos módulos estão fora desta spec.

F4.1: margens laterais de 12 px no celular e 16 px no desktop, sem limite externo de 1600 px no workspace. Painéis recolhíveis preservam edição ainda não aplicada, seleção e zoom. Sete cenários de painéis e três de publicação passaram em API sintética; suíte com 7346 aprovados, 8 falhas preexistentes e 51 ignorados, sem regressão nova. Esse resultado não encerra F4.2 nem o aceite integrado da F3. A cada nova implantação no DEV, avisar o usuário e seguir a próxima entrega conforme a autorização existente.
