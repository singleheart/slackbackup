#!/usr/bin/env python3
import os, json, time, argparse, re, pathlib, sys
from typing import List, Dict
from datetime import datetime, timezone
from collections import defaultdict
import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from tqdm import tqdm

# ---------- 설정 ----------
PAGE_LIMIT = 1000  # Slack 최대 1000

# ---------- 유틸 ----------
def sanitize(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9._-]+', '_', name)

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

def backoff_retry(func, *args, **kwargs):
    while True:
        try:
            return func(*args, **kwargs)
        except SlackApiError as e:
            if e.response is not None and e.response.status_code == 429:
                wait = int(e.response.headers.get("Retry-After", "5"))
                time.sleep(wait)
                continue
            raise

# ---------- 수집기 ----------
class SlackBackup:
    def __init__(self, token: str, outdir: str, types: List[str], conversation_id: str = None, oldest: float = None, latest: float = None):
        self.client = WebClient(token=token)
        self.token = token
        self.outdir = pathlib.Path(outdir)
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.types = types
        self.conversation_id = conversation_id
        self.oldest = oldest
        self.latest = latest
        self.user_map = {}  # user_id -> profile dict

    def load_users(self):
        cursor = None
        while True:
            resp = backoff_retry(self.client.users_list, limit=PAGE_LIMIT, cursor=cursor)
            for u in resp["members"]:
                self.user_map[u["id"]] = u
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

    def list_conversations(self):
        conversations = []
        cursor = None
        types_str = ",".join(self.types)
        while True:
            resp = backoff_retry(self.client.conversations_list, limit=PAGE_LIMIT, types=types_str, exclude_archived=True, cursor=cursor)
            conversations.extend(resp["channels"])
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
        return conversations

    def get_channel_info(self, channel_id: str):
        """특정 채널의 정보를 가져옵니다."""
        resp = backoff_retry(self.client.conversations_info, channel=channel_id)
        return resp["channel"]

    def load_existing_metadata(self, filename: str) -> List[dict]:
        """기존 메타데이터 파일을 읽어옵니다."""
        filepath = self.outdir / filename
        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, Exception) as e:
                print(f"[WARN] Failed to load existing {filename}: {e}", file=sys.stderr)
                return []
        return []

    def merge_metadata(self, existing_meta: List[dict], new_meta: List[dict]) -> List[dict]:
        """기존 메타데이터와 새로운 메타데이터를 병합합니다. ID 기준으로 중복을 제거합니다."""
        # 기존 메타데이터를 ID로 인덱싱
        existing_by_id = {item["id"]: item for item in existing_meta}

        # 새로운 메타데이터를 추가하거나 업데이트
        for item in new_meta:
            existing_by_id[item["id"]] = item

        # ID 순으로 정렬하여 반환
        return sorted(existing_by_id.values(), key=lambda x: x["id"])

    def conv_label(self, conv) -> str:
        """채널 타입에 따른 폴더명을 생성합니다.

        - DM/그룹DM: 채널 ID 사용
        - 일반 채널: 채널명 사용 (채널명이 없으면 ID 사용)
        """
        # DM이나 그룹DM인 경우 채널 ID 사용
        if conv.get("is_im"):
            return conv["id"]

        # 일반 채널인 경우 채널명 사용 (특수문자 제거)
        return sanitize(conv.get("name") or conv["id"])

    def get_members(self, channel_id: str) -> List[str]:
        out, cursor = [], None
        while True:
            resp = backoff_retry(self.client.conversations_members, channel=channel_id, limit=PAGE_LIMIT, cursor=cursor)
            out.extend(resp["members"])
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor: break
        return out

    def iter_history(self, channel_id: str):
        cursor = None
        while True:
            resp = backoff_retry(
                self.client.conversations_history,
                channel=channel_id,
                limit=PAGE_LIMIT,
                cursor=cursor,
                oldest=str(self.oldest) if self.oldest else None,
                latest=str(self.latest) if self.latest else None,
                inclusive=False
            )
            for m in resp.get("messages", []):
                yield m
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor: break

    def fetch_thread(self, channel_id: str, parent_ts: str):
        cursor = None
        msgs = []
        while True:
            resp = backoff_retry(
                self.client.conversations_replies,
                channel=channel_id, ts=parent_ts, limit=PAGE_LIMIT, cursor=cursor
            )
            msgs.extend(resp.get("messages", []))
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor: break
        return msgs

    def _collect_messages(self, channel_id: str) -> List[dict]:
        """채널의 모든 메시지를 수집하고 스레드를 확장합니다."""
        out_msgs = []
        for msg in self.iter_history(channel_id):
            out_msgs.append(msg)
            # 스레드가 있으면 풀체인 수집 (부모 ts 기준)
            if msg.get("thread_ts") == msg.get("ts") and msg.get("reply_count", 0) > 0:
                thread = self.fetch_thread(channel_id, msg["ts"])
                # replies 결과에는 부모가 포함되므로 중복 제거
                # (간단히 ts 기준으로 set 사용)
                by_ts = {m["ts"]: m for m in thread}
                out_msgs.extend([m for t,m in by_ts.items() if t != msg["ts"]])
        return out_msgs

    def _generate_metadata(self, conv: dict, label: str) -> dict:
        """대화 정보로부터 메타데이터를 생성합니다."""
        channel_id = conv["id"]
        meta = {"id": channel_id}

        # 생성 시간 추가
        if conv.get("created"):
            meta["created"] = conv["created"]

        # 멤버 리스트 가져오기 - 모든 타입에서 get_members 사용
        members = self.get_members(channel_id)
        meta["members"] = members

        # DM이 아닌 경우 추가 메타데이터
        if not conv.get("is_im"):
            meta["name"] = label
            if conv.get("creator"):
                meta["creator"] = conv["creator"]
            if "is_archived" in conv:
                meta["is_archived"] = conv["is_archived"]
            if "is_general" in conv:
                meta["is_general"] = conv["is_general"]
            if conv.get("topic"):
                meta["topic"] = conv["topic"]
            if conv.get("purpose"):
                meta["purpose"] = conv["purpose"]

        return meta

    def _classify_metadata(self, conv: dict, meta: dict, metadata_lists: dict):
        """메타데이터를 대화 타입에 따라 분류합니다."""
        if conv.get("is_im"):
            # DM - 기본 메타데이터만
            metadata_lists["dms"].append(meta)
        elif conv.get("is_mpim"):
            # 다중대화(그룹DM)
            metadata_lists["mpims"].append(meta)
        elif conv.get("is_private"):
            # 그룹 (프라이빗 채널)
            metadata_lists["groups"].append(meta)
        else:
            # 채널 (공개 채널)
            metadata_lists["channels"].append(meta)

    def _save_messages_by_date(self, messages: List[dict], conversation_dir: pathlib.Path):
        """메시지를 날짜별로 분할하여 저장합니다."""
        if not messages:
            return

        date_groups = split_messages_by_date(messages)
        for date_str, date_messages in date_groups.items():
            date_file = conversation_dir / f"{date_str}.json"
            try:
                with open(date_file, 'w', encoding='utf-8') as f:
                    json.dump(date_messages, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"[WARN] Failed to write {date_file}: {e}", file=sys.stderr)

    def _process_conversation(self, conv: dict, metadata_lists: dict):
        """하나의 대화를 처리합니다."""
        channel_id = conv["id"]
        label = self.conv_label(conv)
        conversation_dir = self.outdir / label
        conversation_dir.mkdir(parents=True, exist_ok=True)

        # 메시지 수집
        messages = self._collect_messages(channel_id)

        # 메타데이터 생성 및 분류
        metadata = self._generate_metadata(conv, label)
        self._classify_metadata(conv, metadata, metadata_lists)

        # 메시지를 날짜별로 저장
        self._save_messages_by_date(messages, conversation_dir)

    def _save_metadata(self, metadata_lists: dict):
        """메타데이터를 병합하여 파일로 저장합니다."""
        # 기존 메타데이터 로드
        existing_metadata = {
            "channels": self.load_existing_metadata("channels.json"),
            "groups": self.load_existing_metadata("groups.json"),
            "dms": self.load_existing_metadata("dms.json"),
            "mpims": self.load_existing_metadata("mpims.json")
        }

        # 새로운 데이터와 기존 데이터 병합
        merged_metadata = {}
        for metadata_type in ["channels", "groups", "dms", "mpims"]:
            merged_metadata[metadata_type] = self.merge_metadata(
                existing_metadata[metadata_type],
                metadata_lists[metadata_type]
            )

        # 병합된 메타데이터 파일 저장
        for metadata_type, data in merged_metadata.items():
            file_path = self.outdir / f"{metadata_type}.json"
            file_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

    def _get_conversations(self) -> List[dict]:
        """처리할 대화 목록을 가져옵니다."""
        if self.conversation_id:
            try:
                conv = self.get_channel_info(self.conversation_id)
                conv_name = conv.get('name', self.conversation_id)
                print(f"특정 대화 백업: {conv_name}")
                return [conv]
            except SlackApiError as e:
                print(f"ERROR: 대화 {self.conversation_id}를 찾을 수 없습니다: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            return self.list_conversations()

    def run(self):
        """슬랙 백업을 실행합니다."""
        # 사용자 정보 로드
        self.load_users()

        # 처리할 대화 목록 가져오기
        conversations = self._get_conversations()

        # 타입별 메타데이터 수집을 위한 딕셔너리
        metadata_lists = {
            "channels": [],  # 채널
            "groups": [],    # 그룹
            "dms": [],       # DM
            "mpims": []      # 다중대화(그룹DM)
        }

        # 각 대화 처리
        for conv in tqdm(conversations, desc="Conversations"):
            self._process_conversation(conv, metadata_lists)

        # 메타데이터 저장
        self._save_metadata(metadata_lists)

def parse_args():
    ap = argparse.ArgumentParser(description="Slack DM/Private backup via Web API")
    ap.add_argument("--out", required=True, help="Output directory")
    ap.add_argument("--types", default="im,mpim,private_channel", help="Comma sep: im,mpim,private_channel")
    ap.add_argument("--conversation-id", default=None, help="Specific conversation ID to backup (channel/DM/group - if provided, only this conversation will be backed up)")
    ap.add_argument("--oldest", type=float, default=None, help="Oldest ts (float seconds). Omit for all")
    ap.add_argument("--latest", type=float, default=None, help="Latest ts (float seconds). Omit for now")
    return ap.parse_args()

if __name__ == "__main__":
    token = os.getenv("SLACK_USER_TOKEN")
    if not token:
        print("ERROR: export SLACK_USER_TOKEN='xoxp-...'", file=sys.stderr)
        sys.exit(1)
    args = parse_args()
    backup = SlackBackup(
        token,
        args.out,
        [t.strip() for t in args.types.split(",") if t.strip()],
        conversation_id=getattr(args, 'conversation_id', None),
        oldest=args.oldest,
        latest=args.latest
    )
    backup.run()

