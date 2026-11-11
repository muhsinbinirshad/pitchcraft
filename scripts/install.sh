#!/usr/bin/env bash
# Pitchcraft installer: system packages (LibreOffice, Poppler, fonts), Python env, web UI, then a self-check.
#
#   ./scripts/install.sh              # everything
#   ./scripts/install.sh --no-system  # skip OS packages (no sudo); only Python + web UI
#   ./scripts/install.sh --yes        # don't ask before installing OS packages
#
# Supports Debian/Ubuntu (apt), Fedora/RHEL (dnf), Arch (pacman), openSUSE (zypper) and macOS (Homebrew).
# On Windows, use Docker or WSL.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SYSTEM=1
ASSUME_YES=0
for arg in "$@"; do
  case "$arg" in
    --no-system) SYSTEM=0 ;;
    --yes|-y) ASSUME_YES=1 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

bold() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33mwarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

SUDO=""
if [ "$(id -u)" -ne 0 ] && have sudo; then SUDO="sudo"; fi

confirm() {
  [ "$ASSUME_YES" = 1 ] && return 0
  read -r -p "$1 [Y/n] " reply
  case "${reply:-y}" in [Yy]*) return 0 ;; *) return 1 ;; esac
}

# ---------- 1. system packages ----------
install_system() {
  local os; os="$(uname -s)"
  if [ "$os" = "Darwin" ]; then
    have brew || die "Homebrew is required on macOS: https://brew.sh"
    bold "Installing LibreOffice, Poppler, Python and Node with Homebrew"
    brew list --cask libreoffice >/dev/null 2>&1 || brew install --cask libreoffice
    brew install poppler python@3.12 node
    return
  fi

  if have apt-get; then
    bold "Installing LibreOffice, Poppler and fonts with apt"
    $SUDO apt-get update
    # -nogui variants are smaller; older releases only have the full packages
    local lo="libreoffice-writer-nogui libreoffice-calc-nogui libreoffice-impress-nogui"
    apt-cache show libreoffice-writer-nogui >/dev/null 2>&1 || lo="libreoffice-writer libreoffice-calc libreoffice-impress"
    # shellcheck disable=SC2086
    $SUDO apt-get install -y --no-install-recommends $lo poppler-utils python3 python3-venv python3-pip \
      fonts-dejavu fonts-liberation fonts-crosextra-carlito fonts-crosextra-caladea
    $SUDO apt-get install -y --no-install-recommends fonts-noto-core 2>/dev/null || true
    $SUDO apt-get install -y --no-install-recommends curl ca-certificates xz-utils
  elif have dnf; then
    bold "Installing LibreOffice, Poppler and fonts with dnf"
    $SUDO dnf install -y libreoffice-writer libreoffice-calc libreoffice-impress poppler-utils python3 python3-pip nodejs npm
    $SUDO dnf install -y dejavu-sans-fonts liberation-fonts google-carlito-fonts google-noto-sans-fonts 2>/dev/null || true
  elif have pacman; then
    bold "Installing LibreOffice, Poppler and fonts with pacman"
    $SUDO pacman -Sy --needed --noconfirm libreoffice-fresh poppler python python-pip nodejs npm \
      ttf-dejavu ttf-liberation ttf-carlito ttf-caladea noto-fonts
  elif have zypper; then
    bold "Installing LibreOffice, Poppler and fonts with zypper"
    $SUDO zypper --non-interactive install libreoffice-writer libreoffice-calc libreoffice-impress poppler-tools python3 python3-pip nodejs npm
    $SUDO zypper --non-interactive install dejavu-fonts liberation-fonts google-carlito-fonts 2>/dev/null || true
  else
    warn "Unknown package manager. Install LibreOffice (Writer, Calc, Impress), Poppler (pdftoppm, pdftotext), Python 3.11+ and Node.js 20+ yourself."
  fi
}

if [ "$SYSTEM" = 1 ]; then
  if confirm "Install LibreOffice, Poppler, fonts, Python and Node.js with your system package manager?"; then
    install_system
  else
    warn "Skipping system packages. Previews need LibreOffice and Poppler."
  fi
fi

# ---------- 2. Python ----------
bold "Setting up Python environment (.venv)"
PY=""
for c in python3.13 python3.12 python3.11 python3 python; do
  if have "$c" && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then PY="$c"; break; fi
done
[ -n "$PY" ] || die "Python 3.11 or newer is required."

if have uv; then
  [ -d .venv ] || uv venv -q --python "$PY" .venv
  uv pip install -q --python .venv/bin/python -e ".[dev]"
else
  [ -d .venv ] || "$PY" -m venv .venv
  .venv/bin/python -m pip install -q --upgrade pip
  .venv/bin/python -m pip install -q -e ".[dev]"
fi

# ---------- 3. web UI ----------
node_ok() { have node && [ "$(node -p 'process.versions.node.split(".")[0]')" -ge 20 ]; }

# Many distros ship Node 18. If so, fetch the official Node 22 build into .tools/ (checksum-verified, no sudo).
ensure_node() {
  [ -x .tools/node/bin/node ] && export PATH="$ROOT/.tools/node/bin:$PATH"
  node_ok && return 0
  local os arch base file
  case "$(uname -s)" in Linux) os=linux ;; Darwin) os=darwin ;; *) die "Install Node.js 20+ from https://nodejs.org" ;; esac
  case "$(uname -m)" in x86_64|amd64) arch=x64 ;; aarch64|arm64) arch=arm64 ;; *) die "Install Node.js 20+ from https://nodejs.org" ;; esac
  have curl || die "curl is needed to download Node.js (or install Node.js 20+ yourself)."
  base="https://nodejs.org/dist/latest-v22.x"
  bold "Downloading Node.js 22 ($os-$arch) into .tools/node"
  local tmp; tmp="$(mktemp -d)"
  curl -fsSL "$base/SHASUMS256.txt" -o "$tmp/SHASUMS256.txt"
  file="$(grep -oE "node-v22\.[0-9]+\.[0-9]+-$os-$arch\.tar\.gz" "$tmp/SHASUMS256.txt" | head -1)"
  [ -n "$file" ] || die "Could not find a Node.js build for $os-$arch."
  curl -fsSL "$base/$file" -o "$tmp/$file"
  ( cd "$tmp" && grep " $file\$" SHASUMS256.txt | { have sha256sum && sha256sum -c - || shasum -a 256 -c -; } ) >/dev/null \
    || die "Node.js download failed its checksum."
  rm -rf .tools/node && mkdir -p .tools/node
  tar -xzf "$tmp/$file" -C .tools/node --strip-components=1
  rm -rf "$tmp"
  export PATH="$ROOT/.tools/node/bin:$PATH"
  node_ok || die "Node.js install failed."
}

bold "Building the web UI"
ensure_node
echo "Node.js $(node --version)"
( cd frontend && npm ci --no-audit --no-fund && NEXT_TELEMETRY_DISABLED=1 npm run build )

# ---------- 4. settings ----------
if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  echo "Created .env (private). Add ANTHROPIC_API_KEY there, or let each user add a key in Settings."
fi

# ---------- 5. self-check ----------
bold "Checking the install"
.venv/bin/pitchcraft doctor || die "Some checks failed (see above)."

cat <<'EOF'

Pitchcraft is ready. Start it with:

  .venv/bin/pitchcraft serve --data data

Then open http://127.0.0.1:8600. The first visit creates the admin account.
EOF
