#!/usr/bin/env bash
# Stop 훅: Claude Code가 방금 만든 변경사항(git diff)에 명백한 버그나 미완성 코드가
# 없는지 별도의 저비용 Claude 호출(--restricted, 프로젝트 훅 미로딩)로 검증한다.
# 문제를 발견하면 decision:block을 반환해 Claude가 계속 작업하게 만든다.

set -euo pipefail

INPUT=$(cat)

STOP_HOOK_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')
if [[ "$STOP_HOOK_ACTIVE" == "true" ]]; then
  exit 0
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  exit 0
fi

DIFF=$(git diff HEAD 2>/dev/null; git diff --cached 2>/dev/null)
if [[ -z "$DIFF" ]]; then
  exit 0
fi

SCHEMA='{"type":"object","properties":{"ok":{"type":"boolean"},"reason":{"type":"string"}},"required":["ok","reason"]}'

RAW=$(claude -p --restricted --model haiku --output-format json --json-schema "$SCHEMA" \
  "다음은 방금 작업으로 생긴 git diff다. 문법 오류, 명백한 버그, 미완성 코드(TODO만 남기고
끝낸 부분 등)가 있는지만 검토해. 문제 없으면 ok=true, 있으면 ok=false와 구체적 이유.

$DIFF" 2>/dev/null) || exit 0

OK=$(echo "$RAW" | jq -r 'if .structured_output.ok == false then "false" else "true" end' 2>/dev/null) || exit 0
REASON=$(echo "$RAW" | jq -r '.structured_output.reason // ""' 2>/dev/null)

if [[ "$OK" == "false" ]]; then
  jq -n --arg reason "$REASON" '{decision: "block", reason: ("검증 훅이 문제를 발견했습니다: " + $reason)}'
fi
