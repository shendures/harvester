#!/usr/bin/env bash
# Jev로 모델/effort를 판정한 뒤 Claude Code 백엔드로 실행한다.
# 사용법: ./scripts/model-tuner-claude.sh "프롬프트" [--mode edit|plan]
for a in "$@"; do
  if [[ "$a" == "--backend" ]]; then
    echo "model-tuner-claude.sh는 claude 전용입니다. --backend 인자는 사용할 수 없습니다." >&2
    exit 1
  fi
done
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
JEV_HOME="${JEV_HOME:-$PROJECT_DIR/../../jev}"
cd "$PROJECT_DIR"   # .jev-session/ 이 호출 위치와 무관하게 프로젝트 루트에 생기도록 한다.
exec "$JEV_HOME/router/agent-dispatch.sh" "$@" --backend claude
