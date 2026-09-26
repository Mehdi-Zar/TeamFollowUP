/**
 * Application entry point.
 *
 * Mounts the React tree into #root and wires up the global providers in the
 * order they depend on each other. Provider nesting is deliberate:
 * Router (URL) -> I18n (language) -> Config (server settings, which may set the
 * default language) -> Auth (session + permissions, needed by every screen) ->
 * App (routes). StrictMode is enabled for extra dev-time checks.
 */
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./auth";
import { I18nProvider } from "./i18n";
import { ConfigProvider } from "./config";
import "./theme.css";

// Non-null assertion: index.html always ships the #root element.
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <I18nProvider>
        <ConfigProvider>
          <AuthProvider>
            <App />
          </AuthProvider>
        </ConfigProvider>
      </I18nProvider>
    </BrowserRouter>
  </React.StrictMode>
);
