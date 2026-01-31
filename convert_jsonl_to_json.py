#!/usr/bin/env python3
"""
JSONL 파일을 JSON 파일로 변환하는 스크립트
slack_backup 디렉토리 아래의 모든 messages.jsonl 파일을 찾아서 messages.json으로 변환합니다.
"""

import os
import json
import sys
from pathlib import Path


def convert_jsonl_to_json(jsonl_file_path: Path) -> bool:
    """
    JSONL 파일을 JSON 파일로 변환

    Args:
        jsonl_file_path: 변환할 JSONL 파일 경로

    Returns:
        bool: 변환 성공 여부
    """
    try:
        messages = []

        # JSONL 파일 읽기
        with open(jsonl_file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line:  # 빈 줄 무시
                    try:
                        message = json.loads(line)
                        messages.append(message)
                    except json.JSONDecodeError as e:
                        print(f"Warning: JSON 파싱 에러 in {jsonl_file_path}:{line_num} - {e}")
                        continue

        # JSON 파일로 저장 (같은 디렉토리에 messages.json으로)
        json_file_path = jsonl_file_path.parent / "messages.json"

        with open(json_file_path, 'w', encoding='utf-8') as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)

        print(f"✓ 변환 완료: {jsonl_file_path} -> {json_file_path} ({len(messages)}개 메시지)")
        return True

    except Exception as e:
        print(f"✗ 변환 실패: {jsonl_file_path} - {e}")
        return False


def find_and_convert_messages_jsonl(root_dir: Path) -> None:
    """
    root_dir 아래의 모든 messages.jsonl 파일을 찾아서 변환

    Args:
        root_dir: 검색할 루트 디렉토리
    """
    converted_count = 0
    failed_count = 0

    print(f"slack_backup 디렉토리에서 messages.jsonl 파일들을 찾는 중: {root_dir}")

    # messages.jsonl 파일들을 재귀적으로 찾기
    jsonl_files = list(root_dir.rglob("messages.jsonl"))

    print(f"총 {len(jsonl_files)}개의 messages.jsonl 파일을 찾았습니다.")

    for jsonl_file in jsonl_files:
        if convert_jsonl_to_json(jsonl_file):
            converted_count += 1
        else:
            failed_count += 1

    print(f"\n변환 완료!")
    print(f"성공: {converted_count}개")
    print(f"실패: {failed_count}개")


def main():
    """메인 함수"""
    script_dir = Path(__file__).parent
    slack_backup_dir = script_dir / "slack_backup"

    if not slack_backup_dir.exists():
        print(f"에러: slack_backup 디렉토리를 찾을 수 없습니다: {slack_backup_dir}")
        sys.exit(1)

    find_and_convert_messages_jsonl(slack_backup_dir)


if __name__ == "__main__":
    main()
