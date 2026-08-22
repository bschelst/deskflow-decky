<p align="center">
  <img src="images/deskflowdecky-128.png" alt="Deskflow Decky" width="128" height="128">
</p>

<h1 align="center">Deskflow Decky</h1>

<p align="center">
  Use your desktop's / laptop's keyboard and mouse on the Steam Deck or Steam Machine — in Gaming Mode.
</p>

<p align="center">
  <a href="https://github.com/bschelst/deskflow-decky/releases"><img src="https://img.shields.io/github/v/release/bschelst/deskflow-decky?label=release&color=blue" alt="Latest release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--2.0-green" alt="License GPL-2.0"></a>
  <a href="https://deskflow.schelstraete.org"><img src="https://img.shields.io/badge/project-site-blueviolet" alt="Project site"></a>
</p>

---

## ✨ Features

| | Feature | Details |
|---|---|---|
| ⌨️ | **Keyboard input** | Full keyboard forwarding with layout-independent key mapping |
| 🖱️ | **Mouse input** | Buttons, scroll wheel, and relative pointer motion |
| 🎮 | **Gaming Mode native** | Injects input directly into Gamescope via libei (EIS) |
| 🔐 | **TLS + fingerprint trust** | Encrypted connection with interactive fingerprint verification |
| 🔄 | **Auto-reconnect** | Automatic retry with exponential backoff on disconnect |
| 🩺 | **Built-in diagnostics** | Self-test, log viewer, and exportable diagnostic reports |
| ⚙️ | **Configurable** | Input backend, activation mode, log level, and more |
| 🔔 | **Steam notifications** | Connection state changes surfaced as native Steam toasts |

## 🤔 Why this exists

[Deskflow](https://github.com/deskflow/deskflow) works on the Steam Deck/Steam Machine in Desktop Mode. In Gaming Mode it does not work at all.

**Deskflow Decky** tries to make this possible by creating purpose-built Deskflow helper and a Decky front end that handles configuration, process lifecycle, diagnostics, and input activation from the Quick Access Menu.

NOTE: The logo was made with AI. I can't make images, so feel free to send a pull request with new logo if you really want to change that.

## 📦 Installation

Distribution is via GitHub Releases as a sideload.

### Requirements

- 🎮 Steam Deck running SteamOS with [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) 3.2.6+
- 🖥️ Gamescope with libeis support (stock SteamOS qualifies)
- 📦 Flatpak available for the user-scope helper
- 🌐 A machine on the same network running a Deskflow server. TIP: You can use tailscale & the Decky tailscale plugin.

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────┐
│  Steam Deck (Gaming Mode)                        │
│                                                  │
│  ┌────────────┐     ┌──────────────────────────┐ │
│  │ Decky      │◄───►│ Python backend            │ │
│  │ Plugin UI  │     │ (config, lifecycle, diag) │ │
│  │ (React/TS) │     └──────────┬───────────────┘ │
│  └────────────┘                │                 │
│                     ┌──────────▼───────────────┐ │
│                     │ Deskflow helper           │ │
│                     │ (Flatpak, libei client)   │ │
│                     └──────────┬───────────────┘ │
│                                │ EIS socket      │
│                     ┌──────────▼───────────────┐ │
│                     │ Gamescope                 │ │
│                     └──────────────────────────┘ │
└──────────────────────────────────────────────────┘
                         │ TLS
              ┌──────────▼───────────────┐
              │ Desktop / Laptop         │
              │ (Deskflow server)        │
              └──────────────────────────┘
```

**Frontend** — React/TypeScript plugin with Quick Access panel, settings page, and fingerprint trust flow.

**Backend** — Python modules handling Deskflow config generation, helper process management, TLS identity, EIS socket discovery, and diagnostics.

**Helper** — A patched Deskflow client packaged as a user-scope Flatpak, connecting directly to Gamescope's libei socket.

## 🛠️ Development

```bash
# Install dependencies
pnpm install

# Build for production
pnpm build

# Development with hot reload
pnpm watch

# Type checking
pnpm typecheck

# Lint
pnpm lint

# Run tests
pnpm test

# Full check (typecheck + lint + test + build)
pnpm check
```

## 📁 Project Structure

```
├── src/
│   ├── components/     # QuickAccessPanel, StatusRows, FingerprintModal, etc.
│   ├── pages/          # DeskflowPage, SettingsPage, AboutPage, DocumentationPage
│   ├── hooks/          # useDeskflowStatus — reactive connection state
│   ├── api/            # Typed backend calls with Result<T> envelope
│   ├── lib/            # Validation, formatting, Steam integration
│   └── assets/         # Embedded logo
├── py_modules/         # Python backend
│   ├── helper_process.py   # Flatpak helper lifecycle + backoff
│   ├── discovery.py        # EIS socket discovery
│   ├── deskflow_config.py  # Config file generation
│   ├── tls.py              # TLS certificate + fingerprint management
│   ├── identity.py         # Client naming
│   ├── diagnostics.py      # Self-test + export
│   ├── state.py            # Persistent state
│   ├── validation.py       # Input validation
│   └── envelope.py         # Uniform ok/err response wrapper
├── main.py             # Decky backend entry point
└── images/             # Project logos and icons
```

## ⚖️ Licence

**GPL-2.0** — see [LICENSE](./LICENSE). The helper is derived from Deskflow (GPL-2.0-only), and the plugin ships under the same licence. Attribution to the Deskflow project appears in the plugin's About page.

## 🙏 Acknowledgements

- [Deskflow](https://github.com/deskflow/deskflow) — the keyboard and mouse sharing engine this builds on
- [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) — the Steam Deck plugin platform
- [Gamescope](https://github.com/ValveSoftware/gamescope) — whose libeis server makes the Gaming Mode input path possible
