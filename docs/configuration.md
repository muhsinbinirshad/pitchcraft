# Configuration

Settings come from environment variables or from a `.env` file in the working directory. Real environment variables take precedence over the file. To use a different file, run `pitchcraft serve --env-file path`. Start from [`.env.example`](../.env.example).

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | – | Server-wide Claude API key. Optional: users can add their own in Settings, where it's kept in their browser. |
| `PITCHCRAFT_DATA` | `data` | Folder for templates, proposals, versions and users. |
| `PITCHCRAFT_AUTH` | `on` | `off` disables sign-in. Use this only for single-user local setups. |
| `PITCHCRAFT_SECURE_COOKIE` | `0` | Set to `1` when serving over HTTPS. |
| `PITCHCRAFT_SOFFICE` | auto | Path to LibreOffice `soffice`, if it isn't found automatically. |
| `PITCHCRAFT_FONTS` | – | Folder of extra `.ttf` and `.otf` fonts used for previews. |
| `PITCHCRAFT_FETCH_FONTS` | `on` | Download missing template fonts from Google Fonts. |
| `PITCHCRAFT_FONT_CACHE` | `~/.cache/pitchcraft/fonts` | Cache folder for downloaded fonts. |
| `PITCHCRAFT_WEB` | `frontend/out` | Folder of the built web UI. |
| `PITCHCRAFT_PORT` | `8600` | Host port used by `docker-compose.yml`. |

## Sign-in

A fresh install has one account, `admin` / `admin`. That password must be changed at first sign-in; until then, every other request is refused. Admins add users under **Settings → Team**.

Passwords are stored as PBKDF2 hashes, and sessions use signed, HTTP-only cookies.

## Models

Claude Opus 5.5 is the default. Claude Sonnet 5.5 is faster and cheaper. Choose the model in **Settings → Claude & AI**.

## Command line

```bash
pitchcraft serve --port 8600 --data data              # run the web app
pitchcraft doctor                                     # check dependencies and previews
pitchcraft adduser alice --admin --data data          # create a login
pitchcraft import-templates a.docx b.docx --data data # load existing proposals as templates
pitchcraft outline proposal.docx                      # print the outline Claude reads
pitchcraft apply proposal.docx plan.json -o out.docx  # apply a saved plan offline
```

## Production

- Put Pitchcraft behind a reverse proxy with HTTPS, such as Caddy, nginx or Traefik, and set `PITCHCRAFT_SECURE_COOKIE=1`.
- Keep API keys in `.env` or your platform's secret store, never on the command line.
- Back up the data folder or volume.
