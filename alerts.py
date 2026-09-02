import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List


@dataclass
class AlertState:
    foreign_net_buy_active: bool = False
    last_foreign_net: int = 0


def process_foreign_net_buy_alert(
    state: AlertState,
    foreign_net: int,
    previous_foreign_net: int,
    threshold: int = 500,
    ratio_threshold: float = 1.5,
) -> bool:
    """외국계 순매수 급증이 실질적으로 돌파/유지되기 시작했을 때만 1회 알림한다."""
    if state.foreign_net_buy_active:
        if foreign_net <= 0 or foreign_net < threshold:
            state.foreign_net_buy_active = False
        state.last_foreign_net = foreign_net
        return False

    if foreign_net <= 0:
        state.last_foreign_net = foreign_net
        return False

    significant_by_threshold = foreign_net >= threshold
    significant_by_ratio = previous_foreign_net > 0 and (
        foreign_net - previous_foreign_net
    ) >= previous_foreign_net * ratio_threshold

    if significant_by_threshold or significant_by_ratio:
        state.foreign_net_buy_active = True
        state.last_foreign_net = foreign_net
        return True

    state.last_foreign_net = foreign_net
    return False


def issue_title(prefix: str) -> str:
    return f"[{prefix}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"


def create_github_issue(title: str, body: str, assignee: str = "sknixbot") -> bool:
    """GitHub Issue 생성. 실제 주문 기능은 포함하지 않는다."""
    try:
        subprocess.run(
            [
                "gh",
                "issue",
                "create",
                "--title",
                title,
                "--body",
                body,
                "--assignee",
                assignee,
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "GH_TOKEN": os.environ.get("GH_TOKEN", os.environ.get("GITHUB_TOKEN", ""))},
        )
        return True
    except Exception as exc:  # pragma: no cover - CLI 환경 의존적
        print(f"GitHub Issue 생성 실패: {exc}", file=sys.stderr)
        return False


def emit_alert(alert_type: str, message: str) -> bool:
    title = issue_title(alert_type)
    body = (
        "자동 감지 알림\n\n"
        f"유형: {alert_type}\n"
        f"시각: {datetime.now().isoformat(timespec='seconds')}\n\n"
        f"내용:\n{message}\n\n"
        "주의: 실제 주문 기능은 이 시스템에서 수행하지 않습니다."
    )
    return create_github_issue(title, body)


ALERT_STATUS: Dict[str, str] = {
    "국내 보유종목 전일대비 +3%/-3%": "작동",
    "평단 이탈/회복": "작동",
    "프로그램 순매수 급증": "작동",
    "08:10 장전 수급 브리핑": "작동",
    "09:00 수급 브리핑": "작동",
    "외국인+기관 쌍끌이 매수/매도": "API자료필요",
    "미국 보유주식 30분 브리핑": "미연결",
}


ALERT_TYPES = [
    "국내 보유종목 전일대비 +3%/-3%",
    "평단 이탈/회복",
    "프로그램 순매수 급증",
    "08:10 장전 수급 브리핑",
    "09:00 수급 브리핑",
    "외국인+기관 쌍끌이 매수/매도",
    "미국 보유주식 30분 브리핑",
]


def alert_status_rows() -> List[Dict[str, str]]:
    rows = [
        {
            "유형": "국내 보유종목 전일대비 +3%/-3%",
            "상태": ALERT_STATUS["국내 보유종목 전일대비 +3%/-3%"],
            "설명": "국내 종목의 전일 대비 변동률 감시 로직이 연결되어 있음",
        },
        {
            "유형": "평단 이탈/회복",
            "상태": ALERT_STATUS["평단 이탈/회복"],
            "설명": "평단 대비 이탈과 복귀를 감지하는 로직이 연결되어 있음",
        },
        {
            "유형": "프로그램 순매수 급증",
            "상태": ALERT_STATUS["프로그램 순매수 급증"],
            "설명": "프로그램 매매 흐름 급변을 감지하는 실시간 지표를 처리하고 있음",
        },
        {
            "유형": "08:10 장전 수급 브리핑",
            "상태": ALERT_STATUS["08:10 장전 수급 브리핑"],
            "설명": "장전 브리핑 생성 로직은 연결되어 있으나 공식 수급 API 규격과 연동이 추가로 필요함",
        },
        {
            "유형": "09:00 수급 브리핑",
            "상태": ALERT_STATUS["09:00 수급 브리핑"],
            "설명": "장중 브리핑 생성 로직은 연결되어 있으나 공식 수급 API 규격과 연동이 추가로 필요함",
        },
        {
            "유형": "외국인+기관 쌍끌이 매수/매도",
            "상태": ALERT_STATUS["외국인+기관 쌍끌이 매수/매도"],
            "설명": "기관 데이터가 연결된 경우에만 계산 가능하며, 현재 기관 공식 스키마가 확인되지 않아 API자료필요 상태",
        },
        {
            "유형": "미국 보유주식 30분 브리핑",
            "상태": ALERT_STATUS["미국 보유주식 30분 브리핑"],
            "설명": "공식 API 규격이 없어 미연결 상태이며, 실제 주문은 수행하지 않음",
        },
    ]
    return rows
