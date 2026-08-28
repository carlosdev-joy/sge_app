// Regra de envio da senha do ServiceNow no formulário do Admin.
//
// Existe como função pura, e não inline no JSX, porque o caso que ela protege
// é invisível na tela: o formulário parece igual nos dois estados e a diferença
// só aparece no que sai no corpo do POST.
//
// O backend (`servicenow_set`) trata string vazia como "mantenha a senha
// atual" — o que é o comportamento certo: evita que salvar o grupo ou o proxy
// apague a credencial sem querer. Só que a tela renderiza o botão "Trocar
// senha" APENAS quando já existe senha gravada (`tem_senha`). Num ambiente
// recém-configurado esse botão nunca aparece, `trocando` fica false para
// sempre, e a primeira senha nunca chega ao banco: o campo aceita a digitação,
// a tela responde "Configuração salva" e nada é gravado. Verde em tudo.
export function senhaParaEnviar(
  digitada: string,
  trocando: boolean,
  temSenhaGravada: boolean,
): string {
  return (trocando || !temSenhaGravada) ? digitada : ''
}
