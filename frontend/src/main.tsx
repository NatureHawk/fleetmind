import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "@fontsource/jetbrains-mono/600.css";
import "./styles/global.css";
import { AppShell } from "./components/layout/AppShell";
import { OperationsPage } from "./pages/OperationsPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { ExperimentsPage } from "./pages/ExperimentsPage";
import { AlgorithmsPage } from "./pages/AlgorithmsPage";
import { ScenariosPage } from "./pages/ScenariosPage";
import { startStream } from "./lib/simulation/stream";

startStream();

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <OperationsPage /> },
      { path: "analytics", element: <AnalyticsPage /> },
      { path: "experiments", element: <ExperimentsPage /> },
      { path: "algorithms", element: <AlgorithmsPage /> },
      { path: "scenarios", element: <ScenariosPage /> },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RouterProvider router={router} future={{ v7_startTransition: true }} />
  </React.StrictMode>,
);
