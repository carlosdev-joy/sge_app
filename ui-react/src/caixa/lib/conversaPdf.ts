// A conversa do assistente desenhada num documento jsPDF.
//
// Mora fora do componente por dois motivos: o ChatAssistant não precisa saber
// de milímetros e larguras de coluna, e assim a exportação pode ser PROVADA —
// um script gera o PDF com este mesmo código e o resultado se abre e se lê.
// Quando a lógica vivia dentro do onClick, o único jeito de conferir era
// clicar no botão e abrir o arquivo.
//
// O que este módulo desenha são os BLOCOS de markdown.ts — os mesmos que a
// bolha desenha em JSX. Antes daqui o PDF recebia o texto cru e saía com
// `## Status`, `**Emitida**` e as tabelas em canos.
import type jsPDF from "jspdf";
import { parseMarkdown, textoDe, textoParaPdf,
         type BlocoMd, type PedacoInline } from "./markdown";

export interface MensagemPdf {
  text: string;
  sender: "user" | "assistant";
}

// Negrito parcial no meio de uma linha exigiria desenhar pedaço a pedaço e
// recalcular a quebra a cada um. A regra aqui é de MAIORIA: se mais da metade
// dos caracteres da linha está em negrito, a linha inteira sai em negrito.
//
// "Todas as partes em negrito" seria mais simples e erraria o caso real: a
// célula "| ✅ **Emitida** |" tem o emoji FORA do negrito, então o rótulo —
// justamente o que a tabela do modelo quer destacar — sairia em redondo. Uma
// palavra grifada no meio de um parágrafo continua não pesando o suficiente.
function estiloDe(partes: PedacoInline[]): "bold" | "normal" {
  let negrito = 0, total = 0;
  for (const p of partes) {
    const n = p.texto.trim().length;
    total += n;
    if (p.negrito) negrito += n;
  }
  return total > 0 && negrito * 2 > total ? "bold" : "normal";
}

export function montarConversaPdf(
  doc: jsPDF,
  opcoes: { nome: string; mensagens: MensagemPdf[]; exportadoEm?: string },
): void {
  const { nome, mensagens } = opcoes;
  const larguraPagina = doc.internal.pageSize.getWidth();
  const alturaPagina = doc.internal.pageSize.getHeight();
  const m = 20;
  const util = larguraPagina - 2 * m;
  let y = m;

  const cabe = (altura: number) => {
    if (y + altura > alturaPagina - m) { doc.addPage(); y = m; }
  };

  const escrever = (texto: string, op: {
    tamanho?: number; estilo?: "normal" | "bold" | "italic";
    recuo?: number; cor?: [number, number, number]; fonte?: string;
    preservarEspacos?: boolean;
  } = {}) => {
    const tamanho = op.tamanho ?? 11;
    const recuo = op.recuo ?? 0;
    const alturaLinha = tamanho * 0.52;
    doc.setFont(op.fonte ?? "helvetica", op.estilo ?? "normal");
    doc.setFontSize(tamanho);
    const [r, g, b] = op.cor ?? [50, 50, 50];
    doc.setTextColor(r, g, b);
    const limpo = textoParaPdf(texto, op.preservarEspacos);
    if (!limpo) return;
    for (const linha of doc.splitTextToSize(limpo, util - recuo)) {
      cabe(alturaLinha);
      doc.text(linha, m + recuo, y);
      y += alturaLinha;
    }
  };

  const desenharTabela = (b: Extract<BlocoMd, { tipo: "tabela" }>) => {
    const colunas = b.cabecalho.length;
    if (!colunas) return;
    doc.setFontSize(9); doc.setFont("helvetica", "normal");
    // Largura proporcional ao conteúdo mais longo de cada coluna: divisão
    // igual espremeria "Descrição" ao lado de "Status" e deixaria papel em
    // branco na coluna curta.
    //
    // ⚠️ O peso é TETADO. Sem o teto, uma célula de descrição com 400
    // caracteres levava quase toda a largura e sobrava ~1,8mm para "Status":
    // `larguras[j] - 3` ficava NEGATIVO, e `splitTextToSize` com largura
    // negativa devolve uma letra por linha — o cabeçalho virava uma coluna
    // vertical de letras por cima da vizinha. O teto e o piso abaixo garantem
    // que toda coluna caiba entre MIN_COLUNA e o resto da página.
    const MIN_COLUNA = 16;
    const teto = Math.max(util - MIN_COLUNA * (colunas - 1), MIN_COLUNA);
    const pesos = b.cabecalho.map((c, j) => {
      const textos = [textoDe(c), ...b.linhas.map(l => textoDe(l[j] ?? []))];
      const bruto = Math.max(
        ...textos.map(t => doc.getTextWidth(textoParaPdf(t)) + 4), MIN_COLUNA);
      return Math.min(bruto, teto);
    });
    const soma = pesos.reduce((s, p) => s + p, 0) || 1;
    // Reparte o disponível pelos pesos e depois empurra cada coluna para o
    // piso: a soma pode passar de `util` por poucos milímetros, e isso é
    // preferível a uma coluna ilegível (a tabela encosta na margem).
    const larguras = pesos.map(p => Math.max((p / soma) * util, MIN_COLUNA));

    const linha = (celulas: PedacoInline[][], cabecalho: boolean) => {
      // O estilo entra ANTES de medir: o jsPDF quebra o texto com a fonte
      // ATIVA, e medir em redondo para desenhar em negrito (~5-8% mais largo)
      // estoura a coluna. Sem isto, o cabeçalho era medido em redondo e cada
      // linha herdava o estilo da última célula da linha anterior.
      const porCelula = celulas.map((c, j) => {
        doc.setFontSize(9);
        doc.setFont("helvetica", cabecalho ? "bold" : estiloDe(c));
        return doc.splitTextToSize(textoParaPdf(textoDe(c)),
                                   Math.max(larguras[j] - 3, 4));
      });
      const altura = Math.max(...porCelula.map(l => l.length)) * 4.6 + 2;
      cabe(altura + 2);
      let x = m;
      porCelula.forEach((linhas, j) => {
        doc.setFontSize(9);
        doc.setFont("helvetica", cabecalho ? "bold" : estiloDe(celulas[j]));
        if (cabecalho) doc.setTextColor(26, 95, 168);
        else doc.setTextColor(50, 50, 50);
        doc.text(linhas, x + 1.5, y + 3.4);
        x += larguras[j];
      });
      y += altura;
      if (cabecalho) doc.setDrawColor(26, 95, 168);
      else doc.setDrawColor(215, 215, 215);
      doc.line(m, y, m + util, y);
      y += 1.5;
    };

    linha(b.cabecalho, true);
    b.linhas.forEach(l => linha(l, false));
    y += 2;
  };

  doc.setFontSize(16); doc.setTextColor(26, 95, 168);
  doc.text(textoParaPdf(`Conversa com ${nome}`), m, y); y += 8;
  doc.setFontSize(10); doc.setTextColor(100, 100, 100);
  doc.text(`Exportado em: ${opcoes.exportadoEm ?? new Date().toLocaleString("pt-BR")}`,
           m, y);
  y += 12;

  for (const mm of mensagens) {
    cabe(16);
    doc.setFont("helvetica", "bold"); doc.setFontSize(11);
    if (mm.sender === "user") doc.setTextColor(50, 50, 50);
    else doc.setTextColor(26, 95, 168);
    doc.text(mm.sender === "user" ? "Você:" : `${nome}:`, m, y);
    y += 6;

    // A pergunta é o que a pessoa digitou — vai literal, como na bolha.
    if (mm.sender === "user") {
      escrever(mm.text);
      y += 6;
      continue;
    }

    for (const b of parseMarkdown(mm.text)) {
      switch (b.tipo) {
        case "titulo":
          y += 2;
          escrever(textoDe(b.partes), {
            tamanho: b.nivel === 1 ? 13 : 12, estilo: "bold", cor: [26, 95, 168],
          });
          y += 1.5;
          break;
        case "separador":
          cabe(5);
          doc.setDrawColor(215, 215, 215);
          doc.line(m, y, m + util, y);
          y += 4;
          break;
        case "codigo":
          // `preservarEspacos`: sem isso a faxina de espaços comeria a
          // indentação, e código desalinhado é código errado.
          escrever(b.texto, {
            tamanho: 9, fonte: "courier", recuo: 4, preservarEspacos: true,
          });
          y += 2;
          break;
        case "lista":
          b.itens.forEach((item, i) => {
            escrever((b.ordenada ? `${i + 1}. ` : "- ") + textoDe(item), {
              recuo: 4, estilo: estiloDe(item), tamanho: 10.5,
            });
          });
          y += 2;
          break;
        case "tabela":
          desenharTabela(b);
          break;
        default:
          escrever(textoDe(b.partes), { estilo: estiloDe(b.partes) });
          y += 2;
      }
    }
    y += 6;
  }
}
