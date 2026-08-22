# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.3.x   | Yes       |
| < 0.3   | No        |

## Reporting a Vulnerability

If you discover a security vulnerability in RDM, please report it responsibly.

**Do not open a public issue.**

Send an email to **bart@schelstraete.org** with:

- A description of the vulnerability
- Steps to reproduce
- Affected version(s)
- Impact assessment (if known)

You will receive an acknowledgement within 48 hours. A fix will be prioritized based on severity:

| Severity | Response target |
|----------|----------------|
| Critical (RCE, auth bypass, data exposure) | Patch within 72 hours |
| High (privilege escalation, injection)     | Patch within 1 week   |
| Medium (information disclosure, CSRF)      | Next scheduled release |
| Low (minor, defense-in-depth)              | Backlog               |

## Security Architecture

### Authentication
- Passwords hashed with bcrypt (cost factor 12)
- Account lockout after configurable failed attempts
- Session idle timeout (default 30 minutes)
- Admin actions require re-authentication
- LDAP/Active Directory integration (optional)

### Encryption
- All credentials (RDP, SSH, database) encrypted at rest with AES-256-GCM
- Master encryption key stored in `.env` (mode 600, not in version control)
- TLS/HTTPS support with configurable certificates

### Container Isolation
- Each service runs under a dedicated non-root system user
- Rootless Podman with separate UID namespaces per service
- SELinux enforcing with `:Z` volume labels
- Application container runs with `--read-only` filesystem
- Memory limits enforced per container

### Network
- All internal services bind to `127.0.0.1` by default
- No direct external network exposure without explicit configuration
- WebSocket connections (SSH/RDP) authenticated via session token
- Rate limiting on authentication endpoints

### Supply Chain
- Container images built in GitHub Actions (reproducible)
- Private container registry (ghcr.io) with token-based access
- Python dependencies pinned in `requirements.txt`
- No runtime package installation on production servers

## Security Checklist for Deployments

- [ ] Default admin password changed
- [ ] `.env` file permissions set to 600
- [ ] HTTPS enabled with valid certificate
- [ ] Firewall configured (see `deploy/firewall.md`)
- [ ] LDAP connection uses LDAPS (port 636)
- [ ] Database backups encrypted or stored securely
- [ ] Registry access token has minimal scope (read:packages only)
- [ ] System users have no login shell (`/usr/sbin/nologin`)
