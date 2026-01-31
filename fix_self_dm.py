#!/usr/bin/env python3
"""
자신과의 대화(self-DM) members 수정 도구

기존에 백업된 dms.json에서 members가 1명인 DM을 찾아서
2명으로 복제합니다 (자신과의 대화 처리).
"""

import json
import argparse
import pathlib
import sys

def fix_self_dm_members(backup_dir: str, dry_run: bool = False):
    """자신과의 대화의 members를 수정합니다."""
    backup_path = pathlib.Path(backup_dir)
    dms_file = backup_path / "dms.json"

    if not dms_file.exists():
        print(f"Error: {dms_file} 파일을 찾을 수 없습니다.", file=sys.stderr)
        return False

    try:
        # 기존 파일 읽기
        with open(dms_file, 'r', encoding='utf-8') as f:
            dms_data = json.load(f)

        print(f"총 {len(dms_data)}개의 DM 확인 중...")

        modified_count = 0
        for dm in dms_data:
            members = dm.get("members", [])

            # DM에서 멤버가 1명이면 자신과의 대화
            if len(members) == 1:
                user_id = members[0]
                print(f"자신과의 대화 발견: {dm['id']} - 사용자 {user_id}")

                if not dry_run:
                    dm["members"] = [user_id, user_id]
                    print(f"  → 수정: members를 [{user_id}, {user_id}]로 변경")
                else:
                    print(f"  → [미리보기] members를 [{user_id}, {user_id}]로 변경 예정")

                modified_count += 1

        if modified_count == 0:
            print("수정할 자신과의 대화가 없습니다.")
            return True

        print(f"\n총 {modified_count}개의 자신과의 대화를 찾았습니다.")

        # 실제 수정 모드인 경우 파일 저장
        if not dry_run:
            # 백업 생성
            backup_file = backup_path / "dms.json.backup"
            if not backup_file.exists():
                import shutil
                shutil.copy2(dms_file, backup_file)
                print(f"원본 파일 백업: {backup_file}")

            # 수정된 데이터 저장
            with open(dms_file, 'w', encoding='utf-8') as f:
                json.dump(dms_data, f, ensure_ascii=False, indent=2)
            print(f"수정 완료: {dms_file}")
        else:
            print("\n미리보기 모드입니다. 실제 적용하려면 --dry-run 옵션을 제거하세요.")

        return True

    except Exception as e:
        print(f"Error: 처리 중 오류 발생: {e}", file=sys.stderr)
        return False

def main():
    parser = argparse.ArgumentParser(
        description="자신과의 대화(self-DM) members 수정 도구",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  python fix_self_dm.py ./backup          # 수정 실행
  python fix_self_dm.py ./backup --dry-run # 미리보기 모드
        """
    )

    parser.add_argument(
        "backup_dir",
        help="백업 디렉토리 경로 (dms.json이 있는 폴더)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 수정하지 않고 미리보기만 출력"
    )

    args = parser.parse_args()

    print("=== 자신과의 대화 Members 수정 도구 ===")
    print(f"백업 디렉토리: {args.backup_dir}")
    print(f"모드: {'미리보기' if args.dry_run else '실제 수정'}")
    print()

    success = fix_self_dm_members(args.backup_dir, args.dry_run)

    if success:
        print("\n작업이 성공적으로 완료되었습니다.")
    else:
        print("\n작업 중 오류가 발생했습니다.")
        sys.exit(1)

if __name__ == "__main__":
    main()

