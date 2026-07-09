import * as React from "react";

import { cn } from "../../lib/utils";

// Placeholder pulsante para estados de carregamento. Default claro para os
// fundos escuros/gradiente da seção; passe className p/ ajustar por contexto.
function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("animate-pulse rounded-md bg-white/10", className)} {...props} />
  );
}

export { Skeleton };
