# Windows(PowerShell) 환경 git 초기 설정 스크립트
# 사용법: PowerShell에서 .\git-setup-windows.ps1 실행

Write-Host "=== Windows git 환경 설정 시작 ==="

# 줄바꿈 자동 변환: 체크아웃 시 LF->CRLF, 커밋 시 CRLF->LF
git config --global core.autocrlf true

# 파일 모드(권한) 변경 무시
git config --global core.fileMode false

# 기본 브랜치명 통일
git config --global init.defaultBranch main

$gitName  = Read-Host "git user.name 입력"
$gitEmail = Read-Host "git user.email 입력"
if ($gitName)  { git config --global user.name  "$gitName" }
if ($gitEmail) { git config --global user.email "$gitEmail" }

# Git for Windows 기본 포함된 Credential Manager 사용 (매번 로그인 방지)
git config --global credential.helper manager

# 자주 쓰는 alias
git config --global alias.st status
git config --global alias.co checkout
git config --global alias.br branch
git config --global alias.cm "commit -m"
git config --global alias.lg "log --oneline --graph --all --decorate"

Write-Host ""
Write-Host "=== 설정 완료. 현재 설정 확인 ==="
git config --global --list | Select-String "core.autocrlf|core.fileMode|credential.helper|init.defaultBranch|user.name|user.email"

Write-Host ""
Write-Host "저장소 clone 예시:"
Write-Host "  cd C:\Users\<사용자명>\projects"
Write-Host "  git clone <원격저장소_URL>"
