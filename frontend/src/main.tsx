import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { ConnectionGate, ErrorBoundary } from "./Connection";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <ConnectionGate>
        <App />
      </ConnectionGate>
    </ErrorBoundary>
  </StrictMode>,
);
