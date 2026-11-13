#!/usr/bin/env bash
# Qdrant del servicio de IA (plan 01, S5). Un contenedor cada vez, con límites
# para no saturar el portátil, solo en 127.0.0.1 y de la imagen ya descargada.
#
#   qdrant.sh up      Qdrant de desarrollo con volumen (127.0.0.1:56333)
#   qdrant.sh down    lo para (los datos siguen en el volumen)
#   qdrant.sh test    Qdrant temporal sin volumen (127.0.0.1:56334), ejecuta las
#                     pruebas marcadas `qdrant` y lo para siempre al terminar
set -euo pipefail

readonly IMAGE="qdrant/qdrant:v1.19.1"
readonly LIMITS=(--cpus 2 --memory 1g)

readonly DEV_NAME="estadistica-forms-qdrant"
readonly DEV_VOLUME="estadistica-forms-qdrant-data"
readonly DEV_PORT=56333

readonly TEST_NAME="estadistica-forms-qdrant-test"
readonly TEST_PORT=56334
readonly READY_TIMEOUT_SECONDS=30

start_dev() {
  if docker ps --format '{{.Names}}' | grep -qx "$DEV_NAME"; then
    echo "Qdrant de desarrollo ya está en marcha en 127.0.0.1:$DEV_PORT"
    return
  fi
  # `--rm`: el contenedor no queda parado ocupando sitio; los datos viven en el volumen.
  docker run --detach --rm --name "$DEV_NAME" "${LIMITS[@]}" \
    --volume "$DEV_VOLUME:/qdrant/storage" \
    --publish "127.0.0.1:$DEV_PORT:6333" \
    "$IMAGE" >/dev/null
  wait_until_ready "$DEV_PORT"
  echo "Qdrant de desarrollo listo en http://127.0.0.1:$DEV_PORT (consola: /dashboard)"
}

stop_dev() {
  docker stop "$DEV_NAME" >/dev/null 2>&1 || true
  echo "Qdrant de desarrollo parado"
}

run_tests() {
  docker run --detach --rm --name "$TEST_NAME" "${LIMITS[@]}" \
    --publish "127.0.0.1:$TEST_PORT:6333" \
    "$IMAGE" >/dev/null
  trap 'docker stop "$TEST_NAME" >/dev/null 2>&1 || true' EXIT
  wait_until_ready "$TEST_PORT"
  TEST_QDRANT_URL="http://127.0.0.1:$TEST_PORT" uv run pytest -m qdrant "$@"
}

wait_until_ready() {
  local port=$1
  local deadline=$((SECONDS + READY_TIMEOUT_SECONDS))
  until curl --silent --fail "http://127.0.0.1:$port/readyz" >/dev/null; do
    if ((SECONDS > deadline)); then
      echo "Qdrant no respondió en $READY_TIMEOUT_SECONDS s" >&2
      return 1
    fi
    sleep 0.5
  done
}

case "${1:-}" in
  up) start_dev ;;
  down) stop_dev ;;
  test) shift; run_tests "$@" ;;
  *) echo "Uso: $0 up|down|test" >&2; exit 2 ;;
esac
