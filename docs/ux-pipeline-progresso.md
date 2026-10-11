# UX profissional do Pipeline — progresso das fases

Atualizado em 11/10/2026. Fonte dos critérios: [spec](spec-ux-pipeline-profissional.md), [contrato visual](design/pipeline-experiencia.md) e [matriz de preservação](matriz-paridade-pipeline.md).

| Fase | Estado | Registro |
|---|---|---|
| F1 — contrato e protótipo | Referência revisada pelo usuário (documentos `52c0c589`) | [protótipo](prototypes/pipeline-workspace/README.md), [verificação](prototypes/pipeline-workspace/VALIDACAO.md) |
| F3 inicial — cinco destinos e Configuração única | Concluída: 2.18.0, PR #499, `develop` `8a57ac6a` publicado no DEV | [2.18.0](release-notes/2.18.0-pipeline-ux-contexto.md) |
| F3 — aceite combinado | Pendente: percurso integrado salvar → publicar → executar → investigar com capacidades reais e comparação visual com mockups | spec §5 F3 |
| F4.1 — canvas amplo, painéis recolhíveis, barra e diagnóstico | Concluída: 2.19.0, PR #500, `develop` `3900e7c2` validado no DEV | [2.19.0](release-notes/2.19.0-pipeline-ux-montagem.md) |
| F4.2 — inspector em subseções, desfazer/refazer e modo focado | Candidato 2.20.0 na branch `feat/ux-pipeline-inspector-f4` (base `3900e7c2`); bancadas puras e do editor aprovadas; achados da revisão preliminar (guarda de saída com formulário do inspector pendente; histórico conferindo o estado anterior; foco após o último desfazer/refazer) corrigidos com regressões; navegador real aprovado em 13 verificações dos formulários, 6 de proteção do formulário pendente e 3 de foco/atalhos; diagnóstico no campo exato aprovado frio/quente; SQL responde à largura do painel; visual final SHIP; suíte 7365/8 preexistentes/51, tsc e lint sem regressão nova; QA adversarial final SHIP (18 verificações); build aprovado, entrada fria 246,3 KiB e SQL 284,9 KiB gzip; p95 local 300 etapas 116,9 ms (<200); publicação pendente; sem commit, PR nem DEV | [2.20.0](release-notes/2.20.0-pipeline-ux-inspector.md) |
| F5 — execução e investigação | Pendente | spec §5 F5 |
| F2 — descoberta e entrada única | Pendente | spec §5 F2 |
| F6 — aceite da jornada | Pendente; sem piloto com usuários até aqui | spec §5 F6 |

Fechamento da 2.18.0 (registro do Codex): DEV em `8a57ac6a`; smoke próprio PASS com duas sessões, incluindo a resposta 409 à sessão concorrente, e limpeza das fixtures; navegador PASS para saída pelo histórico e troca de Experiência com rascunho sujo. Nenhuma execução de motor ou DataStage real; nenhum piloto com usuários.

Malha versionada, monitores, IA e novos módulos estão fora desta spec.

F4.1: margens laterais de 12 px no celular e 16 px no desktop, sem limite externo de 1600 px no workspace. Painéis recolhíveis preservam edição ainda não aplicada, seleção e zoom. Sete cenários de painéis e três de publicação passaram em API sintética; suíte com 7346 aprovados, 8 falhas preexistentes e 51 ignorados, sem regressão nova. Esse resultado não encerra F4.2 nem o aceite integrado da F3. A cada nova implantação no DEV, avisar o usuário e seguir a próxima entrega conforme a autorização existente.

F4.2 (candidato): inspector com subseções Configuração, Etapa, Lineage e Avançado sobre os formulários reais dos 11 tipos, sem modal frequente; aplicar mescla só os campos alterados; desfazer/refazer local de 50 passos com patches diferenciais; modo focado na área do canvas; diagnóstico abre a subseção do campo; formulário não aplicado é estado separado do não salvo e sair da sessão com ele pede confirmação. Detalhes e limites nas release notes. Não encerra F5, F2, F6 nem o aceite integrado da F3.
