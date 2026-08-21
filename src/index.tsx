import { definePlugin, routerHook } from "@decky/api";
import { ErrorBoundary, staticClasses } from "@decky/ui";
import { FaKeyboard } from "react-icons/fa";

import { QuickAccessPanel } from "./components/QuickAccessPanel";
import { DeskflowPage } from "./pages/DeskflowPage";
import { PLUGIN_ROUTE } from "./routes";

export default definePlugin(() => {
  routerHook.addRoute(PLUGIN_ROUTE, DeskflowPage, { exact: false });

  return {
    // staticClasses.Title keeps the header consistent with every other Decky plugin.
    name: "Deskflow Decky",
    titleView: <div className={staticClasses.Title}>Deskflow</div>,
    // A render fault inside the panel would otherwise unmount the Quick Access Menu,
    // which in Gaming Mode is genuinely hard to recover from.
    content: (
      <ErrorBoundary>
        <QuickAccessPanel />
      </ErrorBoundary>
    ),
    icon: <FaKeyboard />,
    onDismount() {
      routerHook.removeRoute(PLUGIN_ROUTE);
    },
  };
});
