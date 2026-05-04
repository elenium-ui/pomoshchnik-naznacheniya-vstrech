import { createBrowserRouter } from "react-router-dom";

import { AppShellPage } from "../pages/AppShellPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShellPage />
  }
]);

