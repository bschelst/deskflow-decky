import { addEventListener, definePlugin, removeEventListener, routerHook, toaster } from "@decky/api";
import { ErrorBoundary, Navigation, staticClasses } from "@decky/ui";
import { FaKeyboard } from "react-icons/fa";

import { QuickAccessPanel } from "./components/QuickAccessPanel";
import { DeskflowPage } from "./pages/DeskflowPage";
import { PLUGIN_ROUTE } from "./routes";
import LOGO_DATA_URL from "./assets/logo";

interface Notification {
  title: string;
  body: string;
}

const isNotification = (value: unknown): value is Notification =>
  typeof value === "object" &&
  value !== null &&
  typeof (value as Notification).title === "string" &&
  typeof (value as Notification).body === "string";

const notificationLogo = (
  <img
    src={LOGO_DATA_URL}
    alt=""
    style={{
      width: "44px",
      height: "44px",
      flex: "0 0 44px",
      objectFit: "contain",
      display: "block",
      marginRight: "8px",
    }}
  />
);

export default definePlugin(() => {
  routerHook.addRoute(PLUGIN_ROUTE, DeskflowPage, { exact: false });

  toaster.toast({
    title: "Deskflow Decky started",
    body: "The plugin was loaded by Decky.",
    logo: notificationLogo,
    onClick: () => Navigation.Navigate(PLUGIN_ROUTE),
  });

  const onNotify = (payload: unknown) => {
    if (!isNotification(payload)) return;
    toaster.toast({
      title: payload.title,
      body: payload.body,
      logo: notificationLogo,
      onClick: () => Navigation.Navigate(PLUGIN_ROUTE),
    });
  };
  addEventListener<[unknown]>("deskflow_notify", onNotify);

  return {
    // staticClasses.Title keeps the header consistent with every other Decky plugin.
    // Matches plugin.json's name so the panel header and Decky's plugin list agree.
    name: "Deskflow Decky",
    titleView: <div className={staticClasses.Title}>Deskflow Decky</div>,
    // A render fault inside the panel would otherwise unmount the Quick Access Menu,
    // which in Gaming Mode is genuinely hard to recover from.
    content: (
      <ErrorBoundary>
        <QuickAccessPanel />
      </ErrorBoundary>
    ),
    icon: <FaKeyboard />,
    onDismount() {
      removeEventListener<[unknown]>("deskflow_notify", onNotify);
      routerHook.removeRoute(PLUGIN_ROUTE);
    },
  };
});
