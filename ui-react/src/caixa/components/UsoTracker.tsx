// Sem interface: registra o acesso à tela e mantém a presença enquanto a aba está
// visível. Montado dentro de cada rota de /caixa-seguro/* (App.tsx). Spec
// docs/spec-uso-busca-vendas.md.
import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { INTERVALO_PRESENCA_MS, registrarAcesso, registrarPresenca } from "../lib/usoRastreio";

export default function UsoTracker() {
  const { pathname } = useLocation();

  useEffect(() => {
    registrarAcesso(pathname);
  }, [pathname]);

  useEffect(() => {
    const bater = () => {
      if (document.visibilityState === "visible") registrarPresenca(pathname);
    };
    bater();
    const timer = window.setInterval(bater, INTERVALO_PRESENCA_MS);
    document.addEventListener("visibilitychange", bater);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", bater);
    };
  }, [pathname]);

  return null;
}
