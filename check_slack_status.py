#!/usr/bin/env python3
"""Slack API 상태 체크 유틸리티

API 연결 상태, rate limit, timeout 등을 확인합니다.
"""
import argparse
import os
import sys
import time
from datetime import datetime

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


class SlackStatusChecker:
    """Slack API 상태를 체크하는 클래스"""
    
    def __init__(self, token: str, timeout: int = 30):
        self.token = token
        self.timeout = timeout
        self.client = WebClient(token=token, timeout=timeout)
    
    def check_auth(self) -> dict:
        """인증 상태를 확인합니다."""
        result = {
            "test": "auth.test",
            "success": False,
            "user": None,
            "team": None,
            "error": None,
            "response_time_ms": None
        }
        
        start_time = time.time()
        try:
            response = self.client.auth_test()
            elapsed = (time.time() - start_time) * 1000
            
            result["success"] = response["ok"]
            result["user"] = response.get("user")
            result["team"] = response.get("team")
            result["user_id"] = response.get("user_id")
            result["team_id"] = response.get("team_id")
            result["response_time_ms"] = round(elapsed, 2)
            
        except SlackApiError as e:
            elapsed = (time.time() - start_time) * 1000
            result["error"] = str(e)
            result["response_time_ms"] = round(elapsed, 2)
            if e.response:
                result["status_code"] = e.response.status_code
                result["error_code"] = e.response.get("error")
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            result["error"] = f"Connection error: {str(e)}"
            result["response_time_ms"] = round(elapsed, 2)
            # Timeout 감지
            if "timed out" in str(e).lower() or "timeout" in str(e).lower():
                result["timeout"] = True
        
        return result
    
    def check_rate_limit(self) -> dict:
        """Rate limit 상태를 확인합니다 (api.test 호출)."""
        result = {
            "test": "api.test",
            "success": False,
            "rate_limited": False,
            "retry_after": None,
            "error": None,
            "response_time_ms": None
        }
        
        start_time = time.time()
        try:
            response = self.client.api_test()
            elapsed = (time.time() - start_time) * 1000
            
            result["success"] = response["ok"]
            result["response_time_ms"] = round(elapsed, 2)
            
        except SlackApiError as e:
            elapsed = (time.time() - start_time) * 1000
            result["response_time_ms"] = round(elapsed, 2)
            
            if e.response and e.response.status_code == 429:
                result["rate_limited"] = True
                result["retry_after"] = int(e.response.headers.get("Retry-After", 0))
                result["error"] = f"Rate limited. Retry after {result['retry_after']} seconds"
            else:
                result["error"] = str(e)
                if e.response:
                    result["status_code"] = e.response.status_code
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            result["error"] = f"Connection error: {str(e)}"
            result["response_time_ms"] = round(elapsed, 2)
            if "timed out" in str(e).lower() or "timeout" in str(e).lower():
                result["timeout"] = True
        
        return result
    
    def check_users_list(self, limit: int = 1) -> dict:
        """users.list API 상태를 확인합니다."""
        result = {
            "test": "users.list",
            "success": False,
            "user_count": None,
            "rate_limited": False,
            "retry_after": None,
            "error": None,
            "response_time_ms": None
        }
        
        start_time = time.time()
        try:
            response = self.client.users_list(limit=limit)
            elapsed = (time.time() - start_time) * 1000
            
            result["success"] = response["ok"]
            result["user_count"] = len(response.get("members", []))
            result["response_time_ms"] = round(elapsed, 2)
            
        except SlackApiError as e:
            elapsed = (time.time() - start_time) * 1000
            result["response_time_ms"] = round(elapsed, 2)
            
            if e.response and e.response.status_code == 429:
                result["rate_limited"] = True
                result["retry_after"] = int(e.response.headers.get("Retry-After", 0))
                result["error"] = f"Rate limited. Retry after {result['retry_after']} seconds"
            else:
                result["error"] = str(e)
                if e.response:
                    result["status_code"] = e.response.status_code
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            result["error"] = f"Connection error: {str(e)}"
            result["response_time_ms"] = round(elapsed, 2)
            if "timed out" in str(e).lower() or "timeout" in str(e).lower():
                result["timeout"] = True
        
        return result
    
    def check_conversations_list(self, limit: int = 1) -> dict:
        """conversations.list API 상태를 확인합니다."""
        result = {
            "test": "conversations.list",
            "success": False,
            "channel_count": None,
            "rate_limited": False,
            "retry_after": None,
            "error": None,
            "response_time_ms": None
        }
        
        start_time = time.time()
        try:
            response = self.client.conversations_list(limit=limit, types="im,mpim,private_channel")
            elapsed = (time.time() - start_time) * 1000
            
            result["success"] = response["ok"]
            result["channel_count"] = len(response.get("channels", []))
            result["response_time_ms"] = round(elapsed, 2)
            
        except SlackApiError as e:
            elapsed = (time.time() - start_time) * 1000
            result["response_time_ms"] = round(elapsed, 2)
            
            if e.response and e.response.status_code == 429:
                result["rate_limited"] = True
                result["retry_after"] = int(e.response.headers.get("Retry-After", 0))
                result["error"] = f"Rate limited. Retry after {result['retry_after']} seconds"
            else:
                result["error"] = str(e)
                if e.response:
                    result["status_code"] = e.response.status_code
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            result["error"] = f"Connection error: {str(e)}"
            result["response_time_ms"] = round(elapsed, 2)
            if "timed out" in str(e).lower() or "timeout" in str(e).lower():
                result["timeout"] = True
        
        return result
    
    def run_all_checks(self, verbose: bool = True) -> dict:
        """모든 상태 체크를 실행합니다."""
        results = {
            "timestamp": datetime.now().isoformat(),
            "timeout_setting": self.timeout,
            "checks": {}
        }
        
        # 1. 인증 체크
        if verbose:
            print("🔍 인증 상태 확인 중 (auth.test)...")
        auth_result = self.check_auth()
        results["checks"]["auth"] = auth_result
        
        if auth_result["success"]:
            if verbose:
                print(f"   ✅ 인증 성공: {auth_result['user']}@{auth_result['team']}")
                print(f"   ⏱️  응답 시간: {auth_result['response_time_ms']}ms")
        else:
            if verbose:
                print(f"   ❌ 인증 실패: {auth_result.get('error', 'Unknown error')}")
                if auth_result.get("timeout"):
                    print("   ⚠️  TIMEOUT 발생!")
            return results  # 인증 실패시 중단
        
        # 2. API 테스트 (rate limit 확인)
        if verbose:
            print("\n🔍 API 상태 확인 중 (api.test)...")
        api_result = self.check_rate_limit()
        results["checks"]["api_test"] = api_result
        
        if api_result["success"]:
            if verbose:
                print(f"   ✅ API 정상")
                print(f"   ⏱️  응답 시간: {api_result['response_time_ms']}ms")
        elif api_result["rate_limited"]:
            if verbose:
                print(f"   ⚠️  Rate Limited! {api_result['retry_after']}초 후 재시도 필요")
        else:
            if verbose:
                print(f"   ❌ API 오류: {api_result.get('error', 'Unknown error')}")
                if api_result.get("timeout"):
                    print("   ⚠️  TIMEOUT 발생!")
        
        # 3. Users List 테스트
        if verbose:
            print("\n🔍 사용자 목록 API 확인 중 (users.list)...")
        users_result = self.check_users_list()
        results["checks"]["users_list"] = users_result
        
        if users_result["success"]:
            if verbose:
                print(f"   ✅ users.list 정상")
                print(f"   ⏱️  응답 시간: {users_result['response_time_ms']}ms")
        elif users_result["rate_limited"]:
            if verbose:
                print(f"   ⚠️  Rate Limited! {users_result['retry_after']}초 후 재시도 필요")
        else:
            if verbose:
                print(f"   ❌ users.list 오류: {users_result.get('error', 'Unknown error')}")
                if users_result.get("timeout"):
                    print("   ⚠️  TIMEOUT 발생!")
        
        # 4. Conversations List 테스트
        if verbose:
            print("\n🔍 대화 목록 API 확인 중 (conversations.list)...")
        conv_result = self.check_conversations_list()
        results["checks"]["conversations_list"] = conv_result
        
        if conv_result["success"]:
            if verbose:
                print(f"   ✅ conversations.list 정상")
                print(f"   ⏱️  응답 시간: {conv_result['response_time_ms']}ms")
        elif conv_result["rate_limited"]:
            if verbose:
                print(f"   ⚠️  Rate Limited! {conv_result['retry_after']}초 후 재시도 필요")
        else:
            if verbose:
                print(f"   ❌ conversations.list 오류: {conv_result.get('error', 'Unknown error')}")
                if conv_result.get("timeout"):
                    print("   ⚠️  TIMEOUT 발생!")
        
        # 결과 요약
        results["summary"] = self._generate_summary(results["checks"])
        
        if verbose:
            self._print_summary(results["summary"])
        
        return results
    
    def _generate_summary(self, checks: dict) -> dict:
        """결과 요약을 생성합니다."""
        summary = {
            "overall_status": "OK",
            "total_checks": len(checks),
            "successful": 0,
            "failed": 0,
            "rate_limited": 0,
            "timed_out": 0,
            "avg_response_time_ms": 0
        }
        
        total_response_time = 0
        response_count = 0
        
        for name, result in checks.items():
            if result.get("success"):
                summary["successful"] += 1
            else:
                summary["failed"] += 1
            
            if result.get("rate_limited"):
                summary["rate_limited"] += 1
                summary["overall_status"] = "RATE_LIMITED"
            
            if result.get("timeout"):
                summary["timed_out"] += 1
                summary["overall_status"] = "TIMEOUT"
            
            if result.get("response_time_ms"):
                total_response_time += result["response_time_ms"]
                response_count += 1
        
        if response_count > 0:
            summary["avg_response_time_ms"] = round(total_response_time / response_count, 2)
        
        if summary["failed"] > 0 and summary["overall_status"] == "OK":
            summary["overall_status"] = "ERROR"
        
        return summary
    
    def _print_summary(self, summary: dict):
        """결과 요약을 출력합니다."""
        print("\n" + "=" * 50)
        print("📊 상태 요약")
        print("=" * 50)
        
        status_emoji = {
            "OK": "✅",
            "RATE_LIMITED": "⚠️",
            "TIMEOUT": "🚨",
            "ERROR": "❌"
        }
        
        emoji = status_emoji.get(summary["overall_status"], "❓")
        print(f"전체 상태: {emoji} {summary['overall_status']}")
        print(f"성공: {summary['successful']}/{summary['total_checks']}")
        print(f"평균 응답 시간: {summary['avg_response_time_ms']}ms")
        
        if summary["rate_limited"] > 0:
            print(f"⚠️  Rate Limited 발생: {summary['rate_limited']}건")
        
        if summary["timed_out"] > 0:
            print(f"🚨 Timeout 발생: {summary['timed_out']}건")
        
        # 응답 시간 경고
        if summary["avg_response_time_ms"] > 5000:
            print("\n⚠️  경고: 평균 응답 시간이 5초를 초과합니다. 네트워크 상태를 확인하세요.")
        elif summary["avg_response_time_ms"] > 2000:
            print("\n📝 참고: 응답 시간이 다소 느립니다 (2초 이상).")


def main():
    parser = argparse.ArgumentParser(
        description="Slack API 상태 체크 유틸리티",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  python check_slack_status.py                    # 기본 상태 체크 (30초 timeout)
  python check_slack_status.py --timeout 10       # 10초 timeout으로 체크
  python check_slack_status.py --quick            # 빠른 체크 (인증만)
  python check_slack_status.py --json             # JSON 형식으로 출력
        """
    )
    parser.add_argument(
        "--timeout", 
        type=int, 
        default=30, 
        help="API 호출 timeout (초, 기본값: 30)"
    )
    parser.add_argument(
        "--quick", 
        action="store_true", 
        help="빠른 체크 (인증만 확인)"
    )
    parser.add_argument(
        "--json", 
        action="store_true", 
        help="JSON 형식으로 결과 출력"
    )
    
    args = parser.parse_args()
    
    token = os.getenv("SLACK_USER_TOKEN")
    if not token:
        print("ERROR: export SLACK_USER_TOKEN='xoxp-...'", file=sys.stderr)
        sys.exit(1)
    
    checker = SlackStatusChecker(token, timeout=args.timeout)
    
    if args.quick:
        # 빠른 체크 - 인증만
        if not args.json:
            print(f"🔍 Slack API 빠른 상태 체크 (timeout: {args.timeout}초)\n")
        result = checker.check_auth()
        
        if args.json:
            import json
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            if result["success"]:
                print(f"✅ 인증 성공: {result['user']}@{result['team']}")
                print(f"⏱️  응답 시간: {result['response_time_ms']}ms")
            else:
                print(f"❌ 인증 실패: {result.get('error', 'Unknown error')}")
                if result.get("timeout"):
                    print("🚨 TIMEOUT 발생!")
                sys.exit(1)
    else:
        # 전체 체크
        if not args.json:
            print(f"🔍 Slack API 전체 상태 체크 (timeout: {args.timeout}초)")
            print("=" * 50 + "\n")
        
        results = checker.run_all_checks(verbose=not args.json)
        
        if args.json:
            import json
            print(json.dumps(results, ensure_ascii=False, indent=2))
        
        # 종료 코드 설정
        if results["summary"]["overall_status"] != "OK":
            sys.exit(1)


if __name__ == "__main__":
    main()
