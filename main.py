#!/usr/bin/env python3
import os, json, time, argparse, re, pathlib, sys, math
from typing import Dict, List
import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from tqdm import tqdm

# ---------- 설정 ----------
DEFAULT_TYPES = ["im", "mpim", "private_channel"]  # DM/그룹DM/프채
PAGE_LIMIT = 1000  # Slack 최대 1000
OUTSTRUCT = "jsonl"  # jsonl | json
DOWNLOAD_FILES = True

# ---------- 유틸 ----------
def sanitize(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9._-]+', '_', name)

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
    def __init__(self, token: str, outdir: str, types: List[str], oldest: float = None, latest: float = None):
        self.client = WebClient(token=token)
        self.token = token
        self.outdir = pathlib.Path(outdir)
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.types = types
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

    def conv_label(self, conv) -> str:
        # DM: 상대 유저명, MPIM: 멤버명 조합, 프채: 채널명
        if conv.get("is_im"):
            # im 객체는 상대 user id가 conv['user']로 올 수 있음 (토큰 사용자와의 1:1)
            uid = conv.get("user")
            if uid and uid in self.user_map:
                name = self.user_map[uid]["profile"].get("display_name") or self.user_map[uid]["profile"].get("real_name") or self.user_map[uid].get("name") or uid
            else:
                name = "dm_" + conv["id"]
            return f"DM_{sanitize(name)}"
        elif conv.get("is_mpim"):
            # 멤버 리스트로 라벨 구성
            members = self.get_members(conv["id"])
            names = []
            for uid in members:
                if uid in self.user_map:
                    prof = self.user_map[uid]["profile"]
                    names.append(prof.get("display_name") or prof.get("real_name") or self.user_map[uid].get("name") or uid)
                else:
                    names.append(uid)
            return "GDM_" + sanitize("__".join(sorted(names))[:80])
        else:
            # private channel
            return "PRV_" + sanitize(conv.get("name") or conv["id"])

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

    def download_file(self, fobj: dict, dest_dir: pathlib.Path):
        url = fobj.get("url_private")
        if not url: return
        fname = sanitize(fobj.get("name") or fobj.get("id") or "file")
        dest = dest_dir / fname
        # 헤더에 Bearer 토큰 필요
        with requests.get(url, headers={"Authorization": f"Bearer {self.token}"}, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(dest, "wb") as fp:
                for chunk in r.iter_content(chunk_size=1<<20):
                    if chunk: fp.write(chunk)

    def run(self):
        self.load_users()
        conversations = self.list_conversations()
        index = []
        for conv in tqdm(conversations, desc="Conversations"):
            cid = conv["id"]
            label = self.conv_label(conv)
            cdir = self.outdir / f"{label}__{cid}"
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

            # 파일 다운로드
            if DOWNLOAD_FILES:
                fdir = cdir / "files"
                fdir.mkdir(exist_ok=True)
                for m in out_msgs:
                    for f in m.get("files", []) or []:
                        try:
                            self.download_file(f, fdir)
                        except Exception as e:
                            print(f"[WARN] file download failed: {e}", file=sys.stderr)

            # 저장
            meta = {
                "id": cid,
                "label": label,
                "type_flags": {
                    "is_im": conv.get("is_im", False),
                    "is_mpim": conv.get("is_mpim", False),
                    "is_private": conv.get("is_private", False),
                },
                "member_ids": self.get_members(cid) if not conv.get("is_im") else [conv.get("user")],
            }
            (cdir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

            if OUTSTRUCT == "jsonl":
                with open(cdir / "messages.jsonl", "w", encoding="utf-8") as fp:
                    for m in sorted(out_msgs, key=lambda x: float(x["ts"])):
                        fp.write(json.dumps(m, ensure_ascii=False) + "\n")
            else:
                (cdir / "messages.json").write_text(json.dumps(sorted(out_msgs, key=lambda x: float(x["ts"])), ensure_ascii=False, indent=2), encoding="utf-8")

            index.append({"id": cid, "label": label, "dir": str(cdir)})

        (self.outdir / "_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

def parse_args():
    ap = argparse.ArgumentParser(description="Slack DM/Private backup via Web API")
    ap.add_argument("--out", required=True, help="Output directory")
    ap.add_argument("--types", default="im,mpim,private_channel", help="Comma sep: im,mpim,private_channel")
    ap.add_argument("--oldest", type=float, default=None, help="Oldest ts (float seconds). Omit for all")
    ap.add_argument("--latest", type=float, default=None, help="Latest ts (float seconds). Omit for now")
    return ap.parse_args()

if __name__ == "__main__":
    token = os.getenv("SLACK_USER_TOKEN")
    if not token:
        print("ERROR: export SLACK_USER_TOKEN='xoxp-...'", file=sys.stderr)
        sys.exit(1)
    args = parse_args()
    backup = SlackBackup(token, args.out, [t.strip() for t in args.types.split(",") if t.strip()], oldest=args.oldest, latest=args.latest)
    backup.run()

