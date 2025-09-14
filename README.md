# Slack 백업

## 준비: 앱 생성 & 권한(스코프)

1. Slack 앱 생성 → OAuth & Permissions 설정에서 User Token Scopes에 아래 추가

    - `channels:read`, `channels:history` → 공개 채널 목록/이력
    - `im:read`, `im:history` → 1:1 DM 목록/이력
    - `mpim:read`, `mpim:history` → 그룹 DM(MPIM) 목록/이력
    - `groups:read`, `groups:history` → 프라이빗 채널 목록/이력
    - `users:read` → 사용자 이름/프로필 매핑
    - `files:read` → 파일 내려받기까지 원하는 경우
    - `pins:read` → 핀된 메시지 정보 (선택)

2. 앱 설치(Install to Workspace) 후 User OAuth Token (보통 `xoxp-...`) 확보.

3. (선택) 워크스페이스가 Free라면 지난 90일만 API로 노출됩니다. 유료 플랜/보존정책에 따라 범위가 달라지니 참고하세요.

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

### 특정 채널 백업
```bash
# 채널 ID로 특정 채널만 백업
uv run main.py --out ./slack_backup --channel-id C1234567890

# DM ID로 특정 DM만 백업
uv run main.py --out ./slack_backup --channel-id D1234567890
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
