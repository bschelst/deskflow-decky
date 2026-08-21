# deskflow-decky

Use a Deskflow-connected computer's keyboard and mouse inside SteamOS **Gaming Mode** — the Steam UI, native Linux games, and Proton games running under Gamescope.

> **Status: specification only.** No product code exists yet. This repository currently contains the design and the instructions to build it.

---

## What this is

A [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin plus a purpose-built [Deskflow](https://github.com/deskflow/deskflow) helper, packaged as a user-scope Flatpak.

The Deck runs a Deskflow client that injects keyboard and mouse input directly into Gamescope through its libei (EIS) socket. The Decky plugin handles configuration, process lifecycle, diagnostics, and explicit input activation from the Quick Access Menu.

**v1 delivers** keyboard, mouse buttons, scroll wheel, and relative pointer motion.
**v1 does not deliver** clipboard sync, drag-and-drop, cursor-image sync, screen-edge switching, or a promise of universal game compatibility.

## Why it needs to exist

Deskflow works on the Steam Deck in Desktop Mode through the XDG RemoteDesktop portal. In Gaming Mode there is no portal behind Gamescope, so it does not work at all. Gamescope does, however, run an EIS server and accept local libei clients — so the input path exists, it just is not reachable from stock Deskflow, which hard-codes the portal backend.

This project bridges that gap with a small, upstreamable patch and a Decky front end.

## Documentation

| Document | Contents |
|---|---|
| [`PROJECT.md`](./PROJECT.md) | **Start here.** The implementation guide: scope, verified baseline, milestones, gates, and the plugin specification. |
| [`deskflow-gamescope-decky-implementation-plan.md`](./deskflow-gamescope-decky-implementation-plan.md) | The original architecture document. |
| [`docs/RESEARCH.md`](./docs/RESEARCH.md) | Verified upstream findings with citations, and a drift log. |
| [`docs/SECURITY.md`](./docs/SECURITY.md) | Threat model and the non-negotiable controls. |
| [`docs/UI-SPEC.md`](./docs/UI-SPEC.md) | Panel and page layout, alignment rules, fingerprint flow. |
| [`docs/TESTING.md`](./docs/TESTING.md) | Unit, fake-server, and hardware test plans. |
| [`docs/RELEASING.md`](./docs/RELEASING.md) | Tag-driven release and sideload installation. |

## Installation

Not yet available. When it is, distribution will be via this repository's GitHub Releases and a documented sideload — **not** the official Decky plugin store, which requires a public repository. See [`docs/RELEASING.md`](./docs/RELEASING.md).

## Requirements (planned)

- Steam Deck running SteamOS with Decky Loader 3.2.6 or newer
- Gamescope built with libeis support (stock SteamOS is expected to qualify — confirmed during M0)
- Flatpak available for the user-scope helper install
- A machine on the same network running a Deskflow server

## Licence

**GPL-2.0**, repository-wide — see [`LICENSE`](./LICENSE). The helper is derived from Deskflow, which is GPL-2.0-only, and the plugin ships under the same licence rather than splitting the repository across two.

Attribution to the Deskflow project appears in the plugin's About page as a licence obligation, not a courtesy.

## Acknowledgements

- [Deskflow](https://github.com/deskflow/deskflow) — the keyboard and mouse sharing engine this builds on
- [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) — the Steam Deck plugin platform
- [Gamescope](https://github.com/ValveSoftware/gamescope) — whose libeis server makes the Gaming Mode input path possible
