# Slack 백업

## 준비: 앱 생성 & 권한(스코프)

1. Slack 앱 생성 → OAuth & Permissions 설정에서 User Token Scopes에 아래 추가

    - `im:read`, `im:history` → 1:1 DM 목록/이력
    - `mpim:read`, `mpim:history` → 그룹 DM(MPIM) 목록/이력
    - `groups:read`, `groups:history` → 프라이빗 채널 목록/이력
    - `users:read` → 사용자 이름/프로필 매핑
    - `files:read` → 파일 내려받기까지 원하는 경우

1. 앱 설치(Install to Workspace) 후 User OAuth Token (보통 `xoxp-...`) 확보.

1. (선택) 워크스페이스가 Free라면 지난 90일만 API로 노출됩니다. 유료 플랜/보존정책에 따라 범위가 달라지니 참고하세요.

## 사용

- `uv add slack_sdk requests tqdm`
- `export SLACK_USER_TOKEN='xoxp-***'`
- `uv run main.py --output ./slack_backup`

## 출력 폴더 구조

```md
slack_backup/
  _index.json
  DM_상대이름__D12345/
    meta.json
    messages.jsonl
    files/
  GDM_A__B__C__G45678/
    ...
  PRV_secret-team__G99999/
    ...
```
