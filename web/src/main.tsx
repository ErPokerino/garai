import "@fontsource-variable/funnel-sans";
import "@fontsource-variable/work-sans";
import "./index.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "sonner";
import App from "./App";
import { ConfirmProvider } from "./components/Confirm";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1, staleTime: 5_000 } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ConfirmProvider>
          <App />
        </ConfirmProvider>
        <Toaster position="bottom-right" closeButton toastOptions={{ className: "font-sans! rounded-xl!" }} />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
