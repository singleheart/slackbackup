# Slack 백업

## 준비: 앱 생성 & 권한(스코프)

### 1단계: Slack 앱 생성

1. [Slack API 사이트](https://api.slack.com/apps)에 접속
2. **"Create New App"** 버튼 클릭
3. **"From scratch"** 선택
4. 앱 이름 입력 (예: "Slack Backup Tool")
5. 백업할 워크스페이스 선택
6. **"Create App"** 클릭

### 2단계: OAuth 권한 설정

1. 왼쪽 메뉴에서 **"OAuth & Permissions"** 클릭
2. **"Scopes"** 섹션까지 스크롤
3. **"User Token Scopes"** 섹션에서 다음 권한들을 추가:

    - `channels:read` → 공개 채널 목록 조회
    - `channels:history` → 공개 채널 메시지 이력 조회
    - `im:read` → 1:1 DM 목록 조회
    - `im:history` → 1:1 DM 메시지 이력 조회
    - `mpim:read` → 그룹 DM 목록 조회
    - `mpim:history` → 그룹 DM 메시지 이력 조회
    - `groups:read` → 프라이빗 채널 목록 조회
    - `groups:history` → 프라이빗 채널 메시지 이력 조회
    - `users:read` → 사용자 이름/프로필 정보 조회
    - `files:read` → 파일 정보 조회 (파일 다운로드 시 필요)
    - `pins:read` → 핀된 메시지 정보 조회 (선택사항)

### 3단계: 앱 설치 및 토큰 획득

1. **"OAuth & Permissions"** 페이지 상단의 **"Install to Workspace"** 버튼 클릭
2. 권한 승인 화면에서 **"Allow"** 클릭
3. 설치 완료 후 **"User OAuth Token"** 복사
   - 토큰은 `xoxp-`로 시작합니다
   - 이 토큰을 안전한 곳에 보관하세요

### 4단계: 환경변수 설정

획득한 토큰을 환경변수로 설정:

```bash
export SLACK_USER_TOKEN='xoxp-여기에-복사한-토큰-입력'
```

### 주의사항

- **보안**: 토큰을 코드에 하드코딩하지 마세요. 반드시 환경변수를 사용하세요.
- **권한**: 백업하려는 채널/DM에 대한 접근 권한이 있어야 합니다.
- **제한사항**: 워크스페이스가 Free 플랜이라면 지난 90일 메시지만 API로 접근 가능합니다. 유료 플랜의 경우 보존 정책에 따라 범위가 달라집니다.

## 사용법

### 기본 설정

```bash
uv add slack_sdk requests tqdm
export SLACK_USER_TOKEN='xoxp-***'
```

### 전체 백업

```bash
# DM, 그룹DM, 프라이빗 채널 백업 (기본값)
uv run main.py --out ./slack_backup

# 모든 타입 백업 (공개 채널 포함)
uv run main.py --out ./slack_backup --types im,mpim,private_channel,public_channel
```

### 특정 대화 백업

```bash
# 채널 ID로 특정 채널만 백업
uv run main.py --out ./slack_backup --conversation-id C1234567890

# DM ID로 특정 DM만 백업
uv run main.py --out ./slack_backup --conversation-id D1234567890

# 그룹DM ID로 특정 그룹대화만 백업
uv run main.py --out ./slack_backup --conversation-id G1234567890
```

### 기간 제한 백업

```bash
# 특정 기간의 메시지만 백업 (Unix 타임스탬프)
uv run main.py --out ./slack_backup --oldest 1672531200 --latest 1704067200
```

## 출력 폴더 구조

```md
slack_backup/
├── channels.json     # 공개 채널 메타데이터 목록
├── groups.json       # 프라이빗 채널 메타데이터 목록
├── dms.json         # DM 메타데이터 목록
├── mpims.json       # 그룹DM 메타데이터 목록
├── general/         # 채널명 (채널/그룹)
│   ├── 2024-01-01.json
│   ├── 2024-01-02.json
│   └── ...
├── D1234567890/     # 채널 ID (DM)
│   ├── 2024-01-15.json
│   └── ...
└── C9876543210/     # 채널 ID (그룹DM)
    ├── 2024-02-01.json
    └── ...
```

### 메타데이터 파일

각 메타데이터 파일에는 해당 타입의 모든 채널/대화 정보가 포함됩니다:

- **channels.json**: 공개 채널들의 이름, 생성자, 토픽, 목적, 멤버 등
- **groups.json**: 프라이빗 채널들의 정보
- **dms.json**: DM들의 참여자 정보
- **mpims.json**: 그룹DM들의 정보 (채널과 같은 메타데이터 포함)

### 메시지 파일

메시지는 UTC 기준으로 날짜별로 분할되어 저장됩니다:

- 파일명: `YYYY-MM-DD.json` (예: `2024-01-15.json`)
- 각 파일에는 해당 날짜의 모든 메시지가 시간순으로 정렬되어 저장
- 스레드 메시지도 함께 포함

## 파일 URL 토큰 추가 도구

백업된 메시지의 파일 URL에 토큰이 누락되어 접근할 수 없는 경우, 사후에 토큰을 추가할 수 있습니다.

### 도구 사용법

```bash
# 환경변수 사용 (권장)
export SLACK_USER_TOKEN='xoxe-your-token-here'
python add_tokens_to_files.py backup_folder/

# 안전한 미리보기 모드
python add_tokens_to_files.py backup_folder/ --dry-run

# 토큰 직접 지정
python add_tokens_to_files.py backup_folder/ --token 'xoxe-your-token-here'

# 하위 폴더까지 재귀적 처리
python add_tokens_to_files.py backup_folder/ --recursive

# 자세한 사용법
python add_tokens_to_files.py --help
```

### 처리되는 URL

- `url_private`: 프라이빗 파일 URL
- `url_private_download`: 다운로드 URL
- `thumb_*`: 모든 썸네일 URL

### 파일 토큰 추가 주의사항

- 이미 토큰이 있는 URL은 수정하지 않음
- 원본 파일 직접 수정 (중요한 데이터는 사전 백업 권장)
- `--dry-run` 옵션으로 안전하게 미리보기 가능
