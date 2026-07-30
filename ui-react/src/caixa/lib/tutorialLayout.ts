// Geometria do tutorial: onde desenhar avatar e balão sem que um cubra o outro.
//
// Separado do componente porque é a parte que erra na prática — e, isolada,
// pode ser conferida sem navegador.
export interface PassoTutorialGeo {
  avatarPosition: { x: string; y: string };
  balloonPosition: "left" | "right" | "top" | "bottom";
}

export type Lado = "left" | "right" | "top" | "bottom";

export const AVATAR_PX = 128; // h-32 w-32
const FOLGA = 28; // respiro entre o avatar e o balão
const MARGEM = 16; // margem mínima da viewport
const OPOSTO: Record<Lado, Lado> = { top: "bottom", bottom: "top", left: "right", right: "left" };

export interface Caixa {
  left: number;
  top: number;
  width: number;
  height: number;
}

export function intersecta(a: Caixa, b: Caixa): boolean {
  return (
    a.left < b.left + b.width &&
    a.left + a.width > b.left &&
    a.top < b.top + b.height &&
    a.top + a.height > b.top
  );
}

export interface LayoutTutorial {
  lado: Lado | null;
  balao: Caixa;
  avatar: { x: number; y: number };
}

/**
 * Onde desenhar avatar e balão para que os dois apareçam inteiros e sem se
 * cobrir.
 *
 * Testa o lado preferido do passo, depois o oposto, depois os demais, e fica no
 * primeiro que couber na viewport sem encostar no avatar. Função pura: recebe
 * tamanho medido e viewport, devolve pixels.
 */
export function calcularLayout(
  passo: PassoTutorialGeo,
  tamanho: { width: number; height: number },
  viewport: { width: number; height: number },
): LayoutTutorial {
  const { width: VW, height: VH } = viewport;
  const { width: W, height: H } = tamanho;
  const ax = (parseFloat(passo.avatarPosition.x) / 100) * VW;
  const ay = (parseFloat(passo.avatarPosition.y) / 100) * VH;
  const avatar: Caixa = {
    left: ax - AVATAR_PX / 2,
    top: ay - AVATAR_PX / 2,
    width: AVATAR_PX,
    height: AVATAR_PX,
  };

  const pontoDe = (lado: Lado): Caixa => {
    if (lado === "right") return { left: avatar.left + avatar.width + FOLGA, top: ay - H / 2, width: W, height: H };
    if (lado === "left") return { left: avatar.left - FOLGA - W, top: ay - H / 2, width: W, height: H };
    if (lado === "top") return { left: ax - W / 2, top: avatar.top - FOLGA - H, width: W, height: H };
    return { left: ax - W / 2, top: avatar.top + avatar.height + FOLGA, width: W, height: H };
  };

  const cabe = (c: Caixa) =>
    c.left >= MARGEM &&
    c.left + c.width <= VW - MARGEM &&
    c.top >= MARGEM &&
    c.top + c.height <= VH - MARGEM;

  const preferido = passo.balloonPosition as Lado;
  const ordem: Lado[] = [
    preferido,
    OPOSTO[preferido],
    ...(["right", "left", "bottom", "top"] as Lado[]).filter(
      (l) => l !== preferido && l !== OPOSTO[preferido],
    ),
  ];

  for (const lado of ordem) {
    const c = pontoDe(lado);
    if (cabe(c) && !intersecta(c, avatar)) {
      return { lado, balao: c, avatar: { x: ax, y: ay } };
    }
  }

  // Nenhum lado serve (tela muito baixa/estreita): em vez de deixar o balão por
  // cima do avatar, empilha os dois — balão no topo, avatar abaixo dele. A seta
  // de direção some, porque não apontaria para nada.
  const balao: Caixa = {
    left: Math.max(MARGEM, Math.min(ax - W / 2, VW - MARGEM - W)),
    top: MARGEM,
    width: W,
    height: H,
  };
  return {
    lado: null,
    balao,
    avatar: {
      x: ax,
      y: Math.min(VH - MARGEM - AVATAR_PX / 2, Math.max(balao.top + H + FOLGA + AVATAR_PX / 2, ay)),
    },
  };
}

