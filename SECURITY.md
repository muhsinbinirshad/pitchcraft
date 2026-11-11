# Security policy

Please report vulnerabilities privately through [GitHub Security Advisories](https://github.com/muhsinbinirshad/pitchcraft/security/advisories/new), not in public issues.

Include the affected version, steps to reproduce and the impact. You can expect an initial reply within a few days.

## Deployment notes

- Change the default `admin` password at first sign-in. The app requires this.
- Serve over HTTPS behind a reverse proxy, and set `PITCHCRAFT_SECURE_COOKIE=1`.
- Keep `ANTHROPIC_API_KEY` in `.env` or a secret store, never in the repository.
