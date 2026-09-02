# Dry-run 운영 절차

현재 전략 결과는 실거래 투입 기준을 충족하지 않습니다. 이 절차는 주문 없이 동작과 운영 안정성을 관찰하기 위한 모의투자 전용입니다.

## 1. 설정 검증

기본 실행은 봇을 시작하지 않고 병합된 설정만 검사합니다.

```powershell
.\scripts\Invoke-DryRun.ps1 -Strategy KoreanStarterStrategy
```

다음을 출력에서 확인합니다.

- `dry_run: true`
- `initial_state: running`
- 대상 페어와 주문 금액이 의도한 값인지
- API 키가 예제 설정이나 Git 추적 파일에 없는지
- Telegram 등 외부 알림이 비활성 상태인지
- SQLite DB가 `user_data/db/tradesv3.dryrun.sqlite`를 사용하는지

## 2. 모의투자 시작

```powershell
.\scripts\Invoke-DryRun.ps1 `
  -Strategy KoreanStarterStrategy `
  -Start
```

`-Start`를 명시해야만 장기 실행 프로세스가 시작됩니다. Docker에서는 `user_data/db`가 마운트되므로 dry-run DB가 컨테이너 종료 후에도 남습니다. 이 폴더는 Git에서 제외됩니다.

## 3. 기본 보호장치

각 전략의 `protections` 속성은 다음 보호장치를 설정합니다. Freqtrade 2026.7은 config 파일의 보호장치 정의를 거부하므로 전략에 선언합니다.

- 거래 종료 후 같은 페어에 60분간 재진입 금지
- 30일 내 손실 stoploss가 2회 발생하면 전체 페어를 7일간 잠금
- 60일 내 최소 8건에서 계좌 기준 낙폭이 5%를 넘으면 전체 페어를 14일간 잠금

보호장치는 새 진입을 잠그지만 이미 열린 포지션의 손실을 대신 제한하지 않습니다. 전략 stoploss와 별도로 동작합니다.

## 4. 실거래 전 금지 사항

- 검증 결과가 음수인 현재 상태에서 `dry_run`을 끄지 않습니다.
- API 키, 비공개 실거래 config, Telegram 토큰을 저장소에 커밋하지 않습니다.
- 추후 실거래 API 키를 만들더라도 출금 권한을 부여하지 않습니다.
- 최소 한 달의 dry-run 기록과 주문 거절·타임아웃·DB 복구 절차를 확인하기 전 실거래로 전환하지 않습니다.
