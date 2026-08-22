// Schelstraete Bart - bart@schelstraete.org - https://github.com/bschelst/deskflow-decky

import { ErrorBoundary, SidebarNavigation } from "@decky/ui";
import type { FC } from "react";

import { AboutPage } from "./AboutPage";
import { DocumentationPage } from "./DocumentationPage";
import { SettingsPage } from "./SettingsPage";

/**
 * The full-page surface. Long-form content lives here rather than in the Quick Access
 * panel, which stays glanceable.
 */
export const DeskflowPage: FC = () => (
  <ErrorBoundary>
    <SidebarNavigation
      title="Deskflow"
      showTitle
      pages={[
        { title: "Settings", content: <SettingsPage />, route: "/deskflow-decky/settings" },
        {
          title: "Documentation",
          content: <DocumentationPage />,
          route: "/deskflow-decky/documentation",
        },
        { title: "About", content: <AboutPage />, route: "/deskflow-decky/about" },
      ]}
    />
  </ErrorBoundary>
);
