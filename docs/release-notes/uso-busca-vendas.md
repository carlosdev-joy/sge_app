# Uso do módulo Busca & Vendas — v2.6.2

Spec: `docs/spec-uso-busca-vendas.md`. Origem: pedido do solicitante do RITM0117336
("a partir deste primeiro CARD construiremos monitoramento de usabilidade").

## O que muda
- Tela nova **Uso do módulo** (`/caixa-seguro/uso`), item no fim do menu do módulo: usuários
  online agora, acessos e usuários distintos por dia, mês e ano, acessos por tela e ranking
  de usuários.
- **Acesso** = abertura de uma tela de `/caixa-seguro/*`; o mesmo usuário na mesma tela conta
  uma vez a cada 30 minutos. Não mede cliques dentro da tela. **Online agora** = tela aberta
  nos últimos 10 minutos.
- A tela só aparece para quem tem a permissão **Caixa Seguro — Uso do módulo**
  (`caixa_seguro_uso`). Ela nasce só no perfil `admin`; o Admin concede aos demais em
  Perfis e Permissões ou por usuário.
- Sem IP, sem user-agent: só matrícula, tela e instante.

## Deploy (produção — exige autorização própria; nada é executado por este documento)
1. `scripts/deploy_prod.sh` (`config/` → responder **n**). **Responder `s` à pergunta de
   migrations (etapa 6c):** a 141 cria `etl_uso_evento` e `etl_uso_presenca` e semeia o recurso
   no perfil admin; a 142 registra a versão 2.6.2. Sem `dags/`, sem restart de worker, sem
   dependência Python nova.
2. Quem receber a permissão precisa **sair e entrar de novo** (a permissão vem na sessão).

## Smoke
a) Conferir as duas tabelas e `caixa_seguro_uso` no perfil admin.
b) Em Admin, conceder `caixa_seguro_uso` a um perfil de teste; o usuário faz logout/login.
c) Esse usuário vê "Uso do módulo" no menu do módulo; quem não tem a permissão não vê, e a URL
   direta redireciona.
d) Abrir Consulta de Propostas, Monitoramento e Portabilidades; a tela de Uso mostra as
   aberturas, e recarregar a mesma tela em seguida não duplica.
e) "Online agora" mostra o usuário e deixa de mostrá-lo cerca de 10 minutos depois de fechar a aba.
f) Alternar Dia / Mês / Ano. No primeiro dia, mês e ano mostram só hoje e a data de início do registro.
g) Tema escuro e celular: sem rolagem horizontal da página.

## Rollback
Reverter o código (API + `dist/`). As tabelas ficam (só crescem com a medição) e podem ser
removidas à mão se for preciso; a versão registrada é só rótulo. Sem a API nova, o front antigo
não chama nenhum endpoint de uso.

## Pendências conhecidas
- **Retenção:** sem expurgo automático dos eventos (proposta: 24 meses, com job). Decisão do
  solicitante; fora desta entrega.
- A medição **começa na publicação**; não existe histórico anterior.
- Medição de ações dentro da tela (cliques, buscas) fica para um próximo ciclo.
- Numeração 141/142 e versão 2.6.2 a reconciliar com o `develop` (mesma nota da 140): o
  `migrate.py` controla por NOME, e o `develop` usa 2.7.0+.
