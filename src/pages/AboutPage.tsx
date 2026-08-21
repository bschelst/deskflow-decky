import { ButtonItem, Field, Navigation, PanelSection, PanelSectionRow } from "@decky/ui";
import { useEffect, useState, type FC } from "react";

import { getHelperInfo } from "../api/backend";
import type { HelperInfo } from "../api/types";
import { DESKFLOW_URL, ISSUES_URL, REPOSITORY_URL } from "../routes";

/** Injected by @decky/rollup from plugin.json / package.json at build time. */
declare const DECKY_PLUGIN_VERSION: string | undefined;
declare const DECKY_PLUGIN_AUTHOR: string | undefined;

const version = typeof DECKY_PLUGIN_VERSION === "string" ? DECKY_PLUGIN_VERSION : "unknown";
const author =
  typeof DECKY_PLUGIN_AUTHOR === "string" ? DECKY_PLUGIN_AUTHOR : "Bart Schelstraete";

export const AboutPage: FC = () => {
  const [helper, setHelper] = useState<HelperInfo | null>(null);

  useEffect(() => {
    void (async () => {
      const result = await getHelperInfo();
      if (result.ok) setHelper(result.data);
    })();
  }, []);

  return (
    <>
      <PanelSection title="Deskflow Decky">
        <PanelSectionRow>
          <Field label="Version" bottomSeparator="none">
            {version}
          </Field>
        </PanelSectionRow>
        <PanelSectionRow>
          <Field label="Helper" bottomSeparator="none">
            {helper === null ? "Checking…" : helper.installed ? helper.appId : "Not installed"}
          </Field>
        </PanelSectionRow>
        {helper?.installed && helper.version ? (
          <PanelSectionRow>
            <Field label="Helper version" bottomSeparator="none">
              {helper.version}
            </Field>
          </PanelSectionRow>
        ) : null}
        {helper?.installed && helper.permissions.length > 0 ? (
          <PanelSectionRow>
            <Field
              label="Helper permissions"
              bottomSeparator="none"
              description="Access to Gamescope's input socket is granted per launch, scoped to one socket."
            >
              {helper.permissions.join(", ")}
            </Field>
          </PanelSectionRow>
        ) : null}
        <PanelSectionRow>
          <Field label="Author">{author}</Field>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Licence">
        <PanelSectionRow>
          <Field label="Licence" bottomSeparator="none">
            GPL-2.0
          </Field>
        </PanelSectionRow>
        <PanelSectionRow>
          <Field
            label="Built on Deskflow"
            description={
              "The input helper is derived from Deskflow, licensed GPL-2.0-only with an " +
              "OpenSSL exception. This plugin ships under the same licence."
            }
          >
            deskflow/deskflow
          </Field>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Links">
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            onClick={() => Navigation.NavigateToExternalWeb(REPOSITORY_URL)}
          >
            View on GitHub
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            onClick={() => Navigation.NavigateToExternalWeb(ISSUES_URL)}
          >
            Report an issue
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            onClick={() => Navigation.NavigateToExternalWeb(DESKFLOW_URL)}
          >
            The Deskflow project
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    </>
  );
};
