# Sourced by the scripts in bin/

bipolar_refuse_when_delegated() {
  # A CLI launched by the broker (or by bipolar-rescue) inherits BIPOLAR_DELEGATION_DEPTH=1
  [ "${BIPOLAR_DELEGATION_DEPTH:-0}" = 0 ] && return 0
  echo "bipolar recursion guard: this session already runs inside a delegated job (BIPOLAR_DELEGATION_DEPTH=$BIPOLAR_DELEGATION_DEPTH); not delegating again"
  exit 77
}

bipolar_load_config() {
  # Environment variables win; the file written by /bipolar:setup is the fallback
  [ -z "$BIPOLAR_URL" ] && [ -f "$HOME/.config/bipolar-cc/env" ] && . "$HOME/.config/bipolar-cc/env"
  [ -n "$BIPOLAR_URL" ] && [ -n "$BIPOLAR_API_KEY" ] && return 0
  echo "bipolar-cc not configured: run /bipolar:setup"
  exit 78
}

bipolar_resolve_claude() {
  # Git Bash's PATH can list the native installer's folder as /Users/<you>/.local/bin, which does not resolve
  command -v claude || command -v claude.exe || { [ -x "$HOME/.local/bin/claude.exe" ] && echo "$HOME/.local/bin/claude.exe"; }
}

bipolar_split_response() {
  HTTP_CODE=${1##*$'\n'} HTTP_BODY=${1%$'\n'*}
}

bipolar_require_job_id() {
  [[ ${1-} =~ ^[A-Za-z0-9_-]+$ ]] && return 0
  echo "usage: ${0##*/} <job id> (the id from bipolar-delegate-submit's reply)"
  exit 64
}

bipolar_unreachable() {
  echo "bipolar-code unreachable at $BIPOLAR_URL: backend off, wrong URL or off-LAN"
  exit 82
}
