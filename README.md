# Pi 설정 백업 / 복원

macOS, Ubuntu, Windows에서 Pi의 **전역 사용자 설정**을 옮기는 도구입니다. Makefile은 명령 실행을 맡고, 파일 처리는 OS에 종속되지 않는 Python 표준 라이브러리로 구현했습니다.

## 준비

- Python **3.9 이상**
- GNU Make (Windows에서는 `make`가 없다면 아래 Python 직접 실행 사용)
- 복원할 컴퓨터에 Pi 별도 설치: Node.js 22.19 이상에서
  ```sh
  npm install -g --ignore-scripts @earendil-works/pi-coding-agent
  ```
- 가능하면 두 컴퓨터의 Pi 버전을 맞추고, 백업·복원 시 Pi를 종료하세요.

macOS: `xcode-select --install`로 Make 설치 가능. Ubuntu: `sudo apt install make python3`.
Windows에서는 Python을 설치하고 Git Bash + GNU Make 또는 WSL을 사용할 수 있습니다. **WSL의 홈과 Windows의 홈은 별개**입니다. Windows 네이티브 Pi 설정은 Windows Python으로, WSL Pi 설정은 WSL Python으로 작업하세요.

## 사용

이 저장소 디렉터리에서 실행합니다.

### 1. 기존 컴퓨터에서 백업

```sh
make backup
# 또는 파일 이름 지정
make backup OUTPUT=backups/my-pi.zip
```

기본 출력은 `backups/pi-config-<UTC시각>.zip`입니다. 기존 ZIP은 덮어쓰지 않습니다.

### 2. ZIP을 새 컴퓨터로 복사

USB, 개인 클라우드, SSH 등으로 ZIP을 전달하세요. 스크립트/Makefile은 Git으로 관리할 수 있지만 **백업 ZIP은 기본 .gitignore로 제외**합니다. 비공개 저장소라도 ZIP에 비밀 값이 들어갈 수 있다는 점은 같습니다.

### 3. 미리 확인하고 복원

```sh
make restore-preview ARCHIVE=backups/my-pi.zip
make restore ARCHIVE=backups/my-pi.zip
# 확인 질문 없이 실행
make restore ARCHIVE=backups/my-pi.zip FLAGS=--yes
```

복원은 **파일 단위 병합**입니다. ZIP에 있는 파일은 덮어쓰고, 없는 파일은 그대로 둡니다. `settings.json`도 키 단위 병합이 아니라 파일 전체 교체입니다. 완전한 동기화/삭제는 하지 않습니다.

덮어쓸 기존 파일은 먼저 `backups/rollback/before-restore-<시각>.zip`에 보관합니다. 파일 쓰기 실패 시 이미 변경한 파일을 원래 상태로 되돌리려고 시도합니다. 프로세스 강제 종료/전원 장애까지 포함하는 트랜잭션은 아닙니다. 기존 파일을 수동으로 되돌릴 때도 같은 명령을 사용합니다:

```sh
make restore ARCHIVE=backups/rollback/before-restore-실제시각.zip
```

이 ZIP에는 **원래 존재하던 파일만** 들어 있습니다. 복원 시 새로 생성한 파일은 위 명령으로 제거되지 않습니다.

복원 후 새 컴퓨터에서:

```sh
pi
# Pi 안에서 /login 으로 인증 후 종료
pi update --extensions
```

`settings.json`의 npm/git 패키지 선언은 옮기되 설치 캐시는 옮기지 않습니다. `pi update --extensions`는 네트워크와 패키지 도구가 필요합니다. 로컬 확장의 `package.json` 의존성은 해당 디렉터리에서 별도로 설치하세요. 신뢰하는 확장만 설치/실행하세요.

## Windows: Make 없이 실행

PowerShell에서도 동일하게 동작합니다.

```powershell
python scripts/pi_config.py backup --output backups/my-pi.zip
python scripts/pi_config.py restore --archive backups/my-pi.zip --dry-run
python scripts/pi_config.py restore --archive backups/my-pi.zip
```

`python` 대신 `py -3`를 써도 됩니다. Make 사용 시에는 `make backup PYTHON="py -3"`로 지정할 수 있습니다.

## 백업 범위

기본 설정 경로는 `~/.pi/agent`, 환경 변수 `PI_CODING_AGENT_DIR`가 있으면 해당 경로입니다.

| 포함 | 제외 |
|---|---|
| `settings.json`, `keybindings.json` | `auth.json` (로그인/API 키) |
| `models.json`, `mcp.json` | `sessions/` (대화 기록) |
| `AGENTS.override.md`, `AGENTS.md`, `AGENTS.MD`, `CLAUDE.md`, `CLAUDE.MD` | 설치 파일, `bin/`, npm/git 캐시, `models-store.json` |
| `SYSTEM.md`, `APPEND_SYSTEM.md` | `node_modules/`, `.git/`, `__pycache__/` |
| `extensions/`, `skills/`, `prompts/`, `themes/` | 프로젝트별 `.pi/`, 외부 경로의 리소스, 환경 변수 |

**중요: `auth.json`을 제외해도 비밀 값이 완전히 제거되는 것은 아닙니다.** `models.json`에 API 키, `mcp.json`에 토큰/환경 변수, 커스텀 코드나 설정에 비밀 값이 있을 수 있습니다. ZIP은 **암호화되지 않습니다**. 공유 전에 검토하고, 가능하면 비밀 값을 환경 변수 참조로 관리하세요. Unix에서는 ZIP 권한을 `600`으로 설정하지만 Windows ACL은 자동 구성하지 않습니다.

### OS별 설정 및 외부 경로

기본 백업에서는 다른 OS에 잘 맞지 않는 다음 `settings.json` 키를 제외합니다:

- `shellPath`, `shellCommandPrefix`, `externalEditor`
- `sessionDir`, `npmCommand`, `httpProxy`

원본 설정은 변경하지 않습니다. 같은 OS에 그대로 복구하려면:

```sh
make backup FLAGS=--keep-machine-settings
```

복원 시 기존 `settings.json`이 교체되므로 제외된 키도 기존 값이 보존되지는 않습니다. 필요한 기기별 값은 복원 후 다시 설정하세요.

그 외 경로(`extensions`, `skills`, 로컬 `packages`, MCP 명령 등)는 자동 변환하지 않습니다. 가능한 리소스를 `~/.pi/agent` 내부 표준 디렉터리에 두고 상대 경로를 사용하세요. 외부 리소스는 따로 옮겨야 합니다. 심볼릭 링크는 OS 간 호환성과 경로 이탈 방지를 위해 거부합니다. 실제 파일을 복사하거나 npm/git 패키지로 관리하세요. 대소문자만 다른 파일 이름도 백업 시 거부합니다.

## 다른 설정 경로 / 테스트

```sh
make backup AGENT_DIR="/path/to/agent"
make restore ARCHIVE=backups/my-pi.zip AGENT_DIR="/path/to/agent"
make test
```

Python 직접 실행에서는 `--agent-dir`를 서브명령 **앞에** 지정합니다:

```sh
python3 scripts/pi_config.py --agent-dir /path/to/agent backup
```

복원 시 ZIP 구조, 허용 경로, 파일별 SHA-256을 확인합니다. 체크섬은 손상 감지용이지 발신자 인증용 서명이 아닙니다. 신뢰할 수 있는 백업만 복원하세요. 빈 디렉터리는 저장하지 않으며 백업 크기는 256 MiB로 제한합니다.
