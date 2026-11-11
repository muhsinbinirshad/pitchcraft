# Installation

Pitchcraft needs Python 3.11+, Node.js 20+ (for the build), LibreOffice and Poppler. LibreOffice renders the page previews. Poppler (`pdftoppm`, `pdftotext`) turns PDFs into page images and reads PDF attachments.

## Docker (recommended)

```bash
docker compose up -d --build
```

The image includes everything, including fonts that match common Office fonts. Data is kept in the `pitchcraft-data` volume. The container runs as a non-root user with a read-only filesystem, and has a health check on `/api/health`.

Without Compose:

```bash
docker build -t pitchcraft .
docker run -d -p 127.0.0.1:8600:8600 --env-file .env -v pitchcraft-data:/data pitchcraft
```

## Installer (Linux and macOS)

```bash
./scripts/install.sh           # asks before installing system packages
./scripts/install.sh --yes     # no prompt
./scripts/install.sh --no-system   # skip system packages if you install them yourself
```

The installer runs these steps:
1. Installs LibreOffice, Poppler and fonts. It supports apt, dnf, pacman, zypper and Homebrew.
2. Creates the Python environment in `.venv`.
3. Builds the web UI. If your Node.js is older than 20, it downloads Node.js 22 into `.tools/` and verifies its checksum.
4. Creates a private `.env` file.
5. Runs `pitchcraft doctor`.

On Windows, use Docker or WSL.

## Manual setup

Install the system packages:

| System | Command |
|---|---|
| Debian / Ubuntu | `sudo apt install libreoffice-writer-nogui libreoffice-calc-nogui libreoffice-impress-nogui poppler-utils fonts-liberation fonts-crosextra-carlito` |
| Fedora / RHEL | `sudo dnf install libreoffice-writer libreoffice-calc libreoffice-impress poppler-utils liberation-fonts` |
| Arch | `sudo pacman -S libreoffice-fresh poppler ttf-liberation ttf-carlito` |
| macOS | `brew install --cask libreoffice && brew install poppler` |

Then:

```bash
make setup    # Python environment and npm packages
make build    # web UI
make api      # http://127.0.0.1:8600
```

For development with hot reload, run `make dev`. The API runs on `:8600` and Next.js on `:3600`.

## Check the install

```console
$ pitchcraft doctor
  ✓ Python                 3.12.8
  ✓ libreoffice            LibreOffice 25.2.3.2
  ✓ pdftoppm               /usr/bin/pdftoppm
  ✓ pdftotext              /usr/bin/pdftotext
  ✓ Preview render         1 page in 0.8s
  ✓ Web UI                 frontend/out
  ✓ Data folder            data (writable)
```

`doctor` renders a small test document. If a tool is missing, it names the tool and the command that installs it. The server also warns on start, and the app shows a banner.

## Troubleshooting

**Previews are blank or "Previews are off".**
LibreOffice or Poppler is missing. Run `pitchcraft doctor`. If LibreOffice is installed in an unusual place, set `PITCHCRAFT_SOFFICE=/path/to/soffice`.

**Fonts look different in the preview.**
Previews use the fonts embedded in the document first, then Google Fonts, then the fonts installed on the server. For licensed brand fonts, put the `.ttf` or `.otf` files in a folder and set `PITCHCRAFT_FONTS` to that folder.

**The web UI isn't built.**
You need Node.js 20 or newer. The installer adds it locally if yours is older.
