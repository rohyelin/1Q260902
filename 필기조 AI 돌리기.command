#!/bin/bash
# 바탕화면에서 더블클릭하면 노션 동기화가 돌아갑니다.
# (Finder에서 이 파일을 더블클릭 → 터미널이 열리면서 자동 실행)

cd "$(dirname "$0")" 2>/dev/null || exit 1

# 이 파일을 바탕화면에 복사해 두고 실행하면 옆에 sync.sh 가 없다.
# 그럴 때를 대비해 흔한 위치에서 프로젝트 폴더를 찾아본다.
if [ ! -f sync.sh ]; then
  found=""
  for d in "$HOME"/Desktop/lecture-script-matcher* "$HOME"/lecture-script-matcher* \
           "$HOME"/Documents/lecture-script-matcher*; do
    if [ -f "$d/sync.sh" ]; then found="$d"; break; fi
  done
  if [ -z "$found" ]; then
    echo "프로젝트 폴더를 찾지 못했어요."
    echo "sync.sh 가 있는 폴더 안에 이 파일을 두고 실행하거나,"
    echo "폴더를 ~/Desktop 아래에 두세요."
    echo
    read -n 1 -s -r -p "아무 키나 누르면 닫힙니다..."
    exit 1
  fi
  cd "$found" || exit 1
fi

clear
echo "════════════════════════════════════════"
echo "  필기조 AI — 노션 동기화"
echo "════════════════════════════════════════"
echo

./sync.sh

echo
echo "════════════════════════════════════════"
read -n 1 -s -r -p "다 끝났어요! 아무 키나 누르면 창이 닫힙니다..."
echo
