#!/usr/bin/env bash
# 노션 ↔ 필기조 AI 하루 한 번 동기화.
# 백엔드가 꺼져 있으면 알아서 띄우고, 내가 띄운 경우에만 끝나고 정리한다.
#
#   ./sync.sh              평소 실행
#   ./sync.sh --dry-run    뭘 처리할지 보기만 하기

set -uo pipefail
cd "$(dirname "$0")"

BACKEND_URL="http://localhost:8000"
STARTED_BACKEND=0
BACKEND_PID=""
CAFFEINE_PID=""

# 처리가 오래 걸리므로 도중에 맥이 잠들지 않게 막는다.
# -i 유휴 잠자기 방지 / -m 디스크 잠자기 방지 / -s 전원 연결 시 시스템 잠자기 방지
# -w $$ 이 스크립트가 끝나면 자동 해제 (화면은 평소대로 꺼짐)
if command -v caffeinate >/dev/null 2>&1; then
  caffeinate -ims -w $$ &
  CAFFEINE_PID=$!
  echo "처리하는 동안 맥이 잠들지 않게 해둘게요."
fi

cleanup() {
  if [ "$STARTED_BACKEND" = "1" ] && [ -n "$BACKEND_PID" ]; then
    echo "백엔드 정리 중..."
    kill "$BACKEND_PID" 2>/dev/null
    wait "$BACKEND_PID" 2>/dev/null
  fi
  if [ -n "$CAFFEINE_PID" ]; then
    kill "$CAFFEINE_PID" 2>/dev/null
  fi
}
trap cleanup EXIT INT TERM

if [ ! -d backend/.venv ]; then
  echo "backend/.venv 가 없어요. 먼저 가상환경을 만들어 주세요."
  exit 1
fi

source backend/.venv/bin/activate

if curl -s -o /dev/null -m 3 "$BACKEND_URL/"; then
  echo "백엔드가 이미 떠 있어요 — 그대로 씁니다."
else
  echo "백엔드를 띄우는 중..."
  ( cd backend && exec uvicorn app.main:app --host 127.0.0.1 --port 8000 ) \
    > .sync_backend.log 2>&1 &
  BACKEND_PID=$!
  STARTED_BACKEND=1

  for i in $(seq 1 60); do
    if curl -s -o /dev/null -m 2 "$BACKEND_URL/"; then
      echo "백엔드 준비 완료."
      break
    fi
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
      echo "백엔드가 시작하다 죽었어요. .sync_backend.log 를 확인해 주세요:"
      tail -20 .sync_backend.log
      exit 1
    fi
    sleep 2
    if [ "$i" = "60" ]; then
      echo "백엔드가 2분 안에 안 떴어요. .sync_backend.log 를 확인해 주세요."
      exit 1
    fi
  done
fi

echo
python notion_sync.py "$@"
