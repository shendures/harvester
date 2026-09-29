#!/usr/bin/env bash
# Jev(~/jev)로 모델/effort를 판정한 뒤 Claude Code 백엔드로 실행한다.
# 사용법: ./model-tuner-claude.sh "프롬프트" [--mode edit|plan]
for a in "$@"; do
  if [[ "$a" == "--backend" ]]; then
    echo "model-tuner-claude.sh는 claude 전용입니다. --backend 인자는 사용할 수 없습니다." >&2
    exit 1
  fi
done
exec ~/jev/router/agent-dispatch.sh "$@" --backend claude
