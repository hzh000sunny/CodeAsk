import { QueryClientProvider } from "@tanstack/react-query";

import { AppShell } from "./components/layout/AppShell";
import { queryClient } from "./lib/query-client";
import "./styles/globals.css";

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppShell />
    </QueryClientProvider>
  );
}
