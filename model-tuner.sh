#!/usr/bin/env bash
# Jev(~/jev)로 모델/effort를 판정한 뒤 이 프로젝트 디렉터리에서 실행한다.
# 사용법: ./model-tuner.sh "프롬프트" [--backend claude|codex]
exec ~/jev/router/agent-dispatch.sh "$@"
