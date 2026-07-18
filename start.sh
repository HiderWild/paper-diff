#!/usr/bin/env bash

# Launch the API and web development servers without holding this terminal.
# Existing listeners on the default development ports are stopped first.

set -euo pipefail

readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly RUN_DIR="$ROOT_DIR/.run"
readonly API_PORT=8000
readonly WEB_PORT=5173

listener_pids() {
  local port="$1"

  if [[ "$(uname -s)" == "Darwin" ]]; then
    netstat -anv -p tcp | awk -v port="$port" '
      $0 ~ ("\\." port "[[:space:]]") && /LISTEN/ {
        for (i = 1; i <= NF; i++) {
          if ($i ~ /:[0-9]+$/) {
            count = split($i, parts, ":")
            print parts[count]
          }
        }
      }
    ' | sort -u
  else
    lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
  fi
}

stop_port_listener() {
  local port="$1"
  local pids
  local -a pid_list

  pids="$(listener_pids "$port")"
  if [[ -z "$pids" ]]; then
    return
  fi
  read -r -a pid_list <<< "$pids"

  echo "Stopping listener(s) on port $port: $pids"
  kill "${pid_list[@]}" 2>/dev/null || true

  local pid attempt
  for attempt in {1..20}; do
    local still_running=false
    for pid in "${pid_list[@]}"; do
      if kill -0 "$pid" 2>/dev/null; then
        still_running=true
        break
      fi
    done
    if [[ "$still_running" == false ]]; then
      return
    fi
    sleep 0.25
  done

  echo "Force-stopping listener(s) on port $port: $pids"
  kill -KILL "${pid_list[@]}" 2>/dev/null || true
}

wait_for_port() {
  local port="$1"
  local name="$2"
  local pid="$3"
  local attempt

  for attempt in {1..40}; do
    if [[ -n "$(listener_pids "$port")" ]]; then
      return
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "Error: $name exited before listening on port $port." >&2
      return 1
    fi
    sleep 0.25
  done

  echo "Error: $name did not listen on port $port within 10 seconds." >&2
  return 1
}

if [[ "$(uname -s)" == "Darwin" ]]; then
  command -v netstat >/dev/null || {
    echo "Error: netstat is required to clear existing port listeners." >&2
    exit 1
  }
else
  command -v lsof >/dev/null || {
    echo "Error: lsof is required to clear existing port listeners." >&2
    exit 1
  }
fi

mkdir -p "$RUN_DIR"
stop_port_listener "$API_PORT"
stop_port_listener "$WEB_PORT"

API_UVICORN="$ROOT_DIR/apps/api/.venv/bin/uvicorn"
if [[ ! -x "$API_UVICORN" ]]; then
  API_UVICORN="$(command -v uvicorn || true)"
fi
if [[ -z "$API_UVICORN" ]]; then
  echo "Error: uvicorn not found. Install the API dependencies first." >&2
  exit 1
fi

if [[ ! -d "$ROOT_DIR/apps/web/node_modules" ]]; then
  echo "Error: web dependencies are missing. Run 'cd apps/web && npm install' first." >&2
  exit 1
fi

(
  cd "$ROOT_DIR/apps/api"
  exec nohup "$API_UVICORN" app.main:app --host 127.0.0.1 --port "$API_PORT" --reload --log-level debug
) >"$RUN_DIR/api.log" 2>&1 &
echo $! >"$RUN_DIR/api.pid"

(
  cd "$ROOT_DIR/apps/web"
  exec nohup npm run dev -- --host 127.0.0.1 --port "$WEB_PORT" --debug
) >"$RUN_DIR/web.log" 2>&1 &
echo $! >"$RUN_DIR/web.pid"

wait_for_port "$API_PORT" "API" "$(<"$RUN_DIR/api.pid")"
wait_for_port "$WEB_PORT" "web server" "$(<"$RUN_DIR/web.pid")"

echo "Started Paper Diff in the background."
echo "  API: http://127.0.0.1:$API_PORT (log: $RUN_DIR/api.log)"
echo "  Web: http://127.0.0.1:$WEB_PORT (log: $RUN_DIR/web.log)"
