#!/usr/bin/env python3
"""
Slack 백업 파일의 URL에 토큰 추가 도구

이 스크립트는 Slack 백업된 JSON 파일들에서 파일 URL에 토큰이 누락된 경우
사후에 토큰을 추가하여 파일 접근을 가능하게 합니다.

사용법:
    # 환경변수 사용 (권장)
    export SLACK_USER_TOKEN='xoxe-your-token-here'
    python add_tokens_to_files.py backup_folder/

    # 토큰 직접 지정
    python add_tokens_to_files.py file.json --token "xoxe-your-token-here"

    # 디렉토리 전체 처리
    python add_tokens_to_files.py backup_folder/ --token "xoxe-your-token-here"

    # 하위 폴더 포함 재귀적 처리
    python add_tokens_to_files.py backup_folder/ --token "xoxe-your-token-here" --recursive

    # 실제 수정 없이 미리보기 (안전)
    python add_tokens_to_files.py backup_folder/ --dry-run

처리되는 URL 필드:
    - url_private: 프라이빗 파일 URL
    - url_private_download: 다운로드 URL
    - thumb_*: 모든 썸네일 URL (thumb_64, thumb_80, ..., thumb_1024)

예시:
    변환 전: https://files.slack.com/files-pri/T-123/F-456/image.png
    변환 후: https://files.slack.com/files-pri/T-123/F-456/image.png?token=xoxe-your-token-here

주의사항:
    - 이미 토큰이 있는 URL은 수정하지 않습니다
    - 원본 파일을 직접 수정하므로 중요한 데이터는 사전에 백업하세요
    - Slack 파일 URL만 처리하고 다른 URL은 건드리지 않습니다
"""

import json
import argparse
import pathlib
import sys
import os
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

def add_token_to_url(url: str, token: str) -> str:
    """URL에 토큰 파라미터를 추가합니다."""
    if not url or 'files.slack.com' not in url:
        return url

    # 이미 토큰이 있는 경우 스킵
    if 'token=' in url:
        return url

    # URL을 파싱
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)

    # 토큰 추가
    query_params['token'] = [token]

    # URL 재구성
    new_query = urlencode(query_params, doseq=True)
    new_parsed = parsed._replace(query=new_query)

    return urlunparse(new_parsed)

def process_message(message: dict, token: str) -> bool:
    """메시지 객체의 파일 URL들에 토큰을 추가합니다. 수정되었으면 True 반환."""
    modified = False

    if 'files' in message and isinstance(message['files'], list):
        for file_obj in message['files']:
            if isinstance(file_obj, dict):
                # url_private 처리
                if 'url_private' in file_obj:
                    original_url = file_obj['url_private']
                    new_url = add_token_to_url(original_url, token)
                    if new_url != original_url:
                        file_obj['url_private'] = new_url
                        modified = True

                # url_private_download 처리
                if 'url_private_download' in file_obj:
                    original_url = file_obj['url_private_download']
                    new_url = add_token_to_url(original_url, token)
                    if new_url != original_url:
                        file_obj['url_private_download'] = new_url
                        modified = True

                # 썸네일 URL들 처리
                thumbnail_keys = ['thumb_64', 'thumb_80', 'thumb_160', 'thumb_360',
                                'thumb_480', 'thumb_720', 'thumb_800', 'thumb_960', 'thumb_1024']

                for thumb_key in thumbnail_keys:
                    if thumb_key in file_obj:
                        original_url = file_obj[thumb_key]
                        new_url = add_token_to_url(original_url, token)
                        if new_url != original_url:
                            file_obj[thumb_key] = new_url
                            modified = True

    return modified

def process_json_file(file_path: pathlib.Path, token: str, dry_run: bool = False) -> int:
    """JSON 파일을 처리하여 토큰을 추가합니다. 수정된 메시지 수를 반환."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)
        return 0

    if not isinstance(data, list):
        print(f"Warning: {file_path} does not contain a list of messages")
        return 0

    modified_count = 0

    for message in data:
        if isinstance(message, dict):
            if process_message(message, token):
                modified_count += 1

    if modified_count > 0 and not dry_run:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"Updated {file_path}: {modified_count} messages modified")
        except Exception as e:
            print(f"Error writing {file_path}: {e}", file=sys.stderr)
            return 0
    elif modified_count > 0:
        print(f"Would update {file_path}: {modified_count} messages (dry run)")

    return modified_count

def main():
    parser = argparse.ArgumentParser(
        description="Slack 백업 파일의 URL에 토큰 추가 도구",
        epilog="""
사용 예시:
  %(prog)s backup_folder/ --dry-run                    # 미리보기 (안전)
  %(prog)s file.json --token xoxe-123...              # 단일 파일 처리
  %(prog)s backup_folder/ --token xoxe-123...         # 디렉토리 처리
  %(prog)s backup_folder/ --recursive                 # 하위 폴더 포함

환경변수:
  SLACK_USER_TOKEN    Slack 사용자 토큰 (xoxe-... 형태)
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("path",
                       help="처리할 JSON 파일 또는 디렉토리 경로")

    parser.add_argument("--token",
                       help="URL에 추가할 토큰 (미지정시 SLACK_USER_TOKEN 환경변수 사용)")

    parser.add_argument("--dry-run",
                       action="store_true",
                       help="실제 파일 수정 없이 변경사항만 미리보기 (안전 모드)")

    parser.add_argument("--recursive", "-r",
                       action="store_true",
                       help="디렉토리의 모든 하위 폴더까지 재귀적으로 JSON 파일 처리")

    args = parser.parse_args()

    # 토큰 가져오기
    token = args.token or os.getenv("SLACK_USER_TOKEN")
    if not token:
        print("Error: No token provided.", file=sys.stderr)
        print("", file=sys.stderr)
        print("사용법:", file=sys.stderr)
        print("  1. 환경변수 설정: export SLACK_USER_TOKEN='xoxe-your-token-here'", file=sys.stderr)
        print("  2. 또는 직접 지정: --token 'xoxe-your-token-here'", file=sys.stderr)
        print("", file=sys.stderr)
        print("자세한 사용법은 --help 옵션을 참조하세요.", file=sys.stderr)
        sys.exit(1)

    # 토큰에서 xoxp- 부분만 추출 (Bearer 제거)
    if token.startswith('Bearer '):
        token = token[7:]

    path = pathlib.Path(args.path)

    if not path.exists():
        print(f"Error: Path {path} does not exist", file=sys.stderr)
        sys.exit(1)

    total_modified = 0

    if path.is_file():
        if path.suffix == '.json':
            total_modified = process_json_file(path, token, args.dry_run)
        else:
            print(f"Error: {path} is not a JSON file", file=sys.stderr)
            sys.exit(1)
    elif path.is_dir():
        if args.recursive:
            json_files = list(path.rglob("*.json"))
        else:
            json_files = list(path.glob("*.json"))

        if not json_files:
            print(f"No JSON files found in {path}")
            return

        print(f"Found {len(json_files)} JSON files to process")

        for json_file in json_files:
            modified = process_json_file(json_file, token, args.dry_run)
            total_modified += modified

    action = "Would modify" if args.dry_run else "Modified"
    print(f"\n{action} {total_modified} messages total")

if __name__ == "__main__":
    main()
