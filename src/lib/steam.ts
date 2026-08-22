/**
 * The one Steam client call this plugin uses. RestartPC is the same path as the
 * power menu's Restart entry, which makes it the reboot that needs no
 * privileges — the plugin backend runs unprivileged and logind refuses it.
 */
export const restartDevice = (): void => {
  SteamClient.System.RestartPC();
};
