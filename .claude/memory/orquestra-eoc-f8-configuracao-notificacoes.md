---
name: EOC-F8 configuração das notificações
description: Formulário da política, legado preservado e compatibilidade de defaults/SQL; candidato2.26.0
---

Base DEV8f7b606a/2.25.0, branchfeat/eoc-f8-configuracao-notificacoes. Codex principal conclui diretamente, Claude parado. Supervisorexecutor interrompido para evitar dois coders; monitor5min/WhatsApp20min mantidos. Conferir prova pós-deploy e handoff, candidato não prova entrega.

Configuração→Notificações: events3, recipients compartilhados E-mail/Teams pessoal, groupId canal adicional, preview localoverride guarded revision/fence comtimeout20s. Ausência política→legado/optin explícito; futuro→consulta semoverwrite. Details preserva envia_msg_* e email_destinatarios própriosdoscomponentes; não confundir duaslistas. Consulta permite sóseleção deevento do resumo local, semwrite; servidorpreviewexigeedit/lease.

Root encontrou defeitoF7 initialWorkspace notify_on_*: camposSQL inexistentes. Defaults corrigidospara envia_msg_*FALSE. SQLDEV usa3nomesUPPER; projectionnormaliza só3aliases conhecidos, sync_rows escrevephysicalnames, snapshot preservado. UIedita chave original upper/lower. Aliases conflitantes rejeitados, desconhecidos continuam bloqueados. Não limpar/migrar drafts históricos automaticamente.

76 testes dirigidosPASS; browser4viewport/theme+editing/save/422/preview3e0/dialog0; catálogocanal sintético eadminexperiênciaConsulta, não piloto humano/RBACreal. NativeSQLdefaults RED/GREEN eINSERT/UPDATE/ROLLBACK PASS. Cold286688/304986gzip<307200; margemExec2214bytes, evitar crescimento carregado inicialmente semmedir. F6APIp95544.8ms/poll5s/humano/Caixa permanecemgates. Semprovidersends, run oupublicação emfixtures F8; defaultschema validação nãopublicação real. Migration178 idempotenteversão2.26.0/gateexterno. API3arquivos nestaF8; somenteAPIrestart. Auth/motor/.NET/DAG/deps/envpreservados. Security-reviewbuiltinindisponível; revisão manual+independente, não alegar scanner.
