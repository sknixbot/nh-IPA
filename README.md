# nh-IPA

## 실시간 볼린저밴드 알림

`config/bollinger_watchlist.json`의 국내·미국 종목을 일봉 기준
`SMA(20) ± 2 × 모집단 표준편차`로 감시한다. 장중에는 직전 19개 확정 종가와
현재 체결가를 현재 일봉의 종가로 사용한다.

각 실행을 시작할 때 NH 잔고를 조회해 `holding` 그룹을 자동 갱신한다. 계좌 조회가
실패한 시장은 마지막 고정 목록을 유지하며, `swing`과 `value` 그룹은 잔고와 무관하게
계속 감시한다.

```bash
python main.py --bollinger --minutes 30 --markets KR
python main.py --bollinger --minutes 30 --markets US
python main.py --bollinger --minutes 0 --markets KR,US  # 상시 실행 환경 전용
```

알림은 기존과 동일하게 GitHub Issue로 발송된다. 서버·GitHub Actions에서는
`NH_APP_KEY`, `NH_APP_SECRET`, `GITHUB_TOKEN`, `GITHUB_REPOSITORY`가 필요하다.

### 신호

- 하단 터치
- 하단 이탈 후 밴드 안쪽 0.3% 회복
- 상단 터치
- 상단 돌파 후 밴드 안쪽 0.3% 재진입

동일 종목·동일 세션·동일 신호는 한 번만 전송한다. SK하이닉스와 SKHY,
삼성전자와 삼성전자우는 10분 이내 같은 신호가 발생하면 동일 기업으로 묶어
두 번째 알림을 억제한다.

### NH 시세 제약

- 국내 `mc`: NH 통합 실시간 체결가
- 미국 `rc`: 미국·중국 지연 체결가(기본값)
- 미국 `RC`: 유료 실시간 시세 약정 고객만 사용 가능. 약정 후
  `NH_OVERSEAS_REALTIME=true`로 전환한다.
- NH 제한은 앱키당 동시 WebSocket 2개, 세션당 등록 10개다. 미국 15종목은
  10종목씩 45초 간격으로 순환하므로 종목별 최대 약 45초의 비감시 구간이 있다.

`.github/workflows/bollinger-monitor.yml`은 휴일을 포함해 24시간, 매시 7분에
국내·미국 시장을 10분 동안 한 번씩 점검한다. 거래가 없는 시간에는 알림을 만들지
않는다. 한국 시장은 정규장 외에 NXT 프리마켓과 2026년 9월 14일 시작되는
KRX·NXT 애프터마켓(최대 20:00 KST)의 체결도 통합 채널로 받는다.

같은 종목이 같은 세션에서 같은 밴드에 여러 시간 연속 닿아 있으면 시간당 한 번만
알리고, GitHub Issue 제목과 본문에 `접촉 누적 N회`를 표시한다. 같은 시간에
워크플로가 재실행되어도 중복 Issue는 만들지 않는다. GitHub 예약 실행 자체는
수 분 지연될 수 있다.
