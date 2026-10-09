# F3 — fronteiras e ameaças

F3 autorizada pelo usuário até concluir DEV. Uma interface nova acessa exclusivamente endpoints workspace para mutações; nunca montar o FluxoEditor legado editável no rascunho. Leituras de execução/logs passam pelas permissões existentes; experiência escolhe contexto, sem alterar capacidades. Rotas de compatibilidade e menu permanecem nesta fase.

Edição só após lease explícita; salvar exige revision e fence recebidos do servidor. Consulta/executação não alteram configuração nem layout. Renew falho congela edição e preserva conteúdo local na aba. Revisão concorrente não substitui conteúdo sujo silenciosamente. Segredos mascarados/referências permanecem inalterados; UI não grava payloads em localStorage e não expõe parâmetros encrypted editáveis. API continua autoridade de RBAC/segredos; query cache é separado por sessão.

Corpos de configuração preservam extensions, omissão/null e identidade exata. Falta .NET/flags/schema mantém lista/rotas antigas disponíveis; novas ações só aparecem com capabilities confirmadas. Não habilitar validar/publicar/executar antes das fases correspondentes. Testes funcionais e rede devem comprovar ausência de mutações legado em criação, edição e consulta, além de concorrência e retenção após desconexão.
