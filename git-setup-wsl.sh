#!/usr/bin/env bash
# WSL(리눅스) 환경 git 초기 설정 스크립트
# 사용법: bash git-setup-wsl.sh
set -e

echo "=== WSL git 환경 설정 시작 ==="

# 줄바꿈 자동 변환: 커밋 시 CRLF->LF 로 변환, 체크아웃 시에는 변환하지 않음
git config --global core.autocrlf input

# pull 시 병합(merge) 방식 사용 (원치 않으면 true로 바꿔 rebase 사용)
git config --global pull.rebase false

# 파일 실행권한(mode) 비트 변경 무시 (Windows<->WSL 간 마운트 시 흔들리는 문제 방지)
git config --global core.fileMode false

# 기본 브랜치명 통일
git config --global init.defaultBranch main

# 사용자 정보 설정 (이미 설정되어 있으면 엔터로 건너뛰기 가능)
read -p "git user.name 입력: " GIT_NAME
read -p "git user.email 입력: " GIT_EMAIL
[ -n "$GIT_NAME" ] && git config --global user.name "$GIT_NAME"
[ -n "$GIT_EMAIL" ] && git config --global user.email "$GIT_EMAIL"

# 자주 쓰는 alias
git config --global alias.st status
git config --global alias.co checkout
git config --global alias.br branch
git config --global alias.cm "commit -m"
git config --global alias.lg "log --oneline --graph --all --decorate"

echo ""
echo "=== 설정 완료. 현재 설정 확인 ==="
git config --global --list | grep -E "core.autocrlf|core.fileMode|pull.rebase|init.defaultBranch|user.name|user.email"

echo ""
echo "저장소는 WSL 네이티브 경로(/home/...)에 clone 하는 것을 권장합니다:"
echo "  mkdir -p ~/projects && cd ~/projects"
echo "  git clone <원격저장소_URL>"
