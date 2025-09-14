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

    def run(self):
        self.load_users()

        # 특정 대화 ID가 주어진 경우 해당 대화만 처리
        if self.conversation_id:
            try:
                conv = self.get_channel_info(self.conversation_id)
                conversations = [conv]
                conv_name = conv.get('name', self.conversation_id)
                print(f"특정 대화 백업: {conv_name}")
            except SlackApiError as e:
                print(f"ERROR: 대화 {self.conversation_id}를 찾을 수 없습니다: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            conversations = self.list_conversations()

        # 타입별 메타데이터 수집을 위한 리스트
        channels_meta = []  # 채널
        groups_meta = []    # 그룹
        dms_meta = []       # DM
        mpims_meta = []     # 다중대화(그룹DM)

        for conv in tqdm(conversations, desc="Conversations"):
            cid = conv["id"]
            label = self.conv_label(conv)
            cdir = self.outdir / label
            cdir.mkdir(parents=True, exist_ok=True)

            # 메시지 수집 + 스레드 확장
            out_msgs = []
            for msg in self.iter_history(cid):
                out_msgs.append(msg)
                # 스레드가 있으면 풀체인 수집 (부모 ts 기준)
                if msg.get("thread_ts") == msg.get("ts") and msg.get("reply_count", 0) > 0:
                    thread = self.fetch_thread(cid, msg["ts"])
                    # replies 결과에는 부모가 포함되므로 중복 제거
                    # (간단히 ts 기준으로 set 사용)
                    by_ts = {m["ts"]: m for m in thread}
                    out_msgs.extend([m for t,m in by_ts.items() if t != msg["ts"]])

            # 메타데이터 생성
            meta = {"id": cid}

            # 생성 시간 추가
            if conv.get("created"):
                meta["created"] = conv["created"]

            # 멤버 리스트 가져오기 - 모든 타입에서 get_members 사용
            members = self.get_members(cid)
            meta["members"] = members

            # 타입에 따라 메타데이터 구성 및 분류
            if conv.get("is_im"):
                # DM - 기본 메타데이터만
                dms_meta.append(meta)
            else:
                # 채널/그룹/다중대화 - 공통 메타데이터 추가
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

                # 타입별 분류
                if conv.get("is_mpim"):
                    # 다중대화(그룹DM)
                    mpims_meta.append(meta)
                elif conv.get("is_private"):
                    # 그룹 (프라이빗 채널)
                    groups_meta.append(meta)
                else:
                    # 채널 (공개 채널)
                    channels_meta.append(meta)

            # 메시지를 날짜별로 분할하여 저장
            if out_msgs:
                date_groups = split_messages_by_date(out_msgs)
                for date_str, date_messages in date_groups.items():
                    date_file = cdir / f"{date_str}.json"
                    try:
                        with open(date_file, 'w', encoding='utf-8') as f:
                            json.dump(date_messages, f, ensure_ascii=False, indent=2)
                    except Exception as e:
                        print(f"[WARN] Failed to write {date_file}: {e}", file=sys.stderr)

        # 타입별 메타데이터 파일 저장 (빈 배열이라도 항상 생성)
        (self.outdir / "channels.json").write_text(json.dumps(channels_meta, ensure_ascii=False, indent=2), encoding="utf-8")
        (self.outdir / "groups.json").write_text(json.dumps(groups_meta, ensure_ascii=False, indent=2), encoding="utf-8")
        (self.outdir / "dms.json").write_text(json.dumps(dms_meta, ensure_ascii=False, indent=2), encoding="utf-8")
        (self.outdir / "mpims.json").write_text(json.dumps(mpims_meta, ensure_ascii=False, indent=2), encoding="utf-8")

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

