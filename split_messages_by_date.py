#!/usr/bin/env python3
import os
import json
import pathlib
from datetime import datetime, timezone
from collections import defaultdict
from typing import Dict, List
import argparse

def timestamp_to_date(ts: str) -> str:
    """타임스탬프를 UTC 날짜(YYYY-MM-DD)로 변환"""
    try:
        # Slack timestamp는 Unix timestamp (초 단위, 소수점 포함)
        timestamp = float(ts)
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return dt.strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        print(f"Warning: Invalid timestamp {ts}")
        return "unknown-date"

def split_messages_by_date(messages: List[dict]) -> Dict[str, List[dict]]:
    """메시지를 날짜별로 그룹화"""
    date_groups = defaultdict(list)

    for msg in messages:
        ts = msg.get("ts")
        if not ts:
            continue

        date_str = timestamp_to_date(ts)
        date_groups[date_str].append(msg)

    # 각 날짜 그룹 내에서 시간순 정렬
    for date_str in date_groups:
        date_groups[date_str].sort(key=lambda x: float(x.get("ts", "0")))

    return dict(date_groups)

def process_channel(channel_dir: pathlib.Path):
    """개별 채널 폴더의 messages.json을 날짜별로 분할"""
    messages_file = channel_dir / "messages.json"

    if not messages_file.exists():
        print(f"Warning: {messages_file} not found")
        return

    print(f"Processing {channel_dir.name}...")

    # messages.json 읽기
    try:
        with open(messages_file, 'r', encoding='utf-8') as f:
            messages = json.load(f)
    except Exception as e:
        print(f"Error reading {messages_file}: {e}")
        return

    if not messages:
        print(f"  No messages found in {channel_dir.name}")
        return

    # 날짜별로 분할
    date_groups = split_messages_by_date(messages)

    if not date_groups:
        print(f"  No valid messages with timestamps in {channel_dir.name}")
        return

    # 날짜별 폴더 생성 및 저장
    dates_dir = channel_dir / "dates"
    dates_dir.mkdir(exist_ok=True)

    for date_str, date_messages in date_groups.items():
        date_file = dates_dir / f"{date_str}.json"
        try:
            with open(date_file, 'w', encoding='utf-8') as f:
                json.dump(date_messages, f, ensure_ascii=False, indent=2)
            print(f"  Saved {len(date_messages)} messages to {date_file.name}")
        except Exception as e:
            print(f"Error writing {date_file}: {e}")

    print(f"  Split into {len(date_groups)} date files")

def find_channel_dirs(backup_root: pathlib.Path) -> List[pathlib.Path]:
    """백업 폴더에서 채널 디렉토리들을 찾기"""
    channel_dirs = []

    for item in backup_root.iterdir():
        if item.is_dir() and (item / "messages.json").exists():
            channel_dirs.append(item)

    return channel_dirs

def main():
    parser = argparse.ArgumentParser(description="Split Slack messages.json files by date")
    parser.add_argument("backup_dir", help="Backup directory containing channel folders")
    parser.add_argument("--channel", help="Specific channel directory name to process (optional)")

    args = parser.parse_args()

    backup_root = pathlib.Path(args.backup_dir)

    if not backup_root.exists():
        print(f"Error: Backup directory {backup_root} does not exist")
        return

    if args.channel:
        # 특정 채널만 처리
        channel_dir = backup_root / args.channel
        if not channel_dir.exists():
            print(f"Error: Channel directory {channel_dir} does not exist")
            return
        process_channel(channel_dir)
    else:
        # 모든 채널 처리
        channel_dirs = find_channel_dirs(backup_root)

        if not channel_dirs:
            print(f"No channel directories with messages.json found in {backup_root}")
            return

        print(f"Found {len(channel_dirs)} channel directories")

        for channel_dir in channel_dirs:
            process_channel(channel_dir)

    print("Date splitting completed!")

if __name__ == "__main__":
    main()
