# F2 — ameaças e fronteiras

Escopo autorizado: persistência e consulta de rascunhos em DEV; publicação, execução e UI ficam nas fases seguintes. Sessão Bearer e RBAC atuais são obrigatórios para mutações; Basic permanece para consulta. Não há bypass por nome de perfil.

A conta SQL concede leitura somente às fontes explícitas de configuração, sem credenciais de conexão, snapshots cifrados ou escritas nas tabelas ativas. Escritas ficam em quatro tabelas workspace. Importação remove valores encrypted e credenciais identificadas; configurações que demandem redação além de parâmetros tornam-se somente leitura. Campos desconhecidos são preservados.

Concorrência: transação bloqueia rascunho antes da lease; revisão impede aba antiga e fence crescente impede posse antiga. Liberação nunca apaga fence. Hora SQL UTC determina validade. Auditoria integra a mesma transação, sem conteúdo, token ou hash de sessão. Versões importadas são imutáveis e identificadas como bases importadas, sem associação com execuções históricas.

Limites: corpo 1 MiB, nomes 200 unidades UTF-16, 1.000 nós, timeout SQL, concorrência HTTP limitada. Ausência de schema desabilita capacidade e escrita retorna migration necessária; requests não executam DDL. Falhas retornam códigos e mensagens em português, sem detalhes SQL/credenciais. Dados salvos persistem independentemente da sessão/lease e eventos ficam associados à vida do rascunho; eventual expurgo exige política específica posterior.

Validação exigida: SQL real isolado, migration repetida, corrida entre sessões, revisão/fence obsoletos, expiração, transferência, rollback de auditoria, parâmetros cifrados, tipos/campos desconhecidos, ausência de schema, permissões negativas, integridade das tabelas ativas e pacote offline. Revisões independentes adversarial e de segurança antes da PR.
