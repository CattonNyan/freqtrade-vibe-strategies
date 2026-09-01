# Dry-run 보호장치 검증

## 적용 내용

세 전략 모두 다음 시간 기반 보호장치를 선언합니다.

- `CooldownPeriod`: 거래 종료 후 해당 페어 60분 잠금
- `StoplossGuard`: 30일 내 손실 stoploss 2회 시 전체 페어 7일 잠금
- `MaxDrawdown`: 60일 내 최소 8건의 계좌 낙폭이 5% 초과 시 전체 페어 14일 잠금

Freqtrade 2026.7은 config의 `protections` 항목을 거부하므로 전략의 `protections` 속성을 사용했습니다. MaxDrawdown은 신규 구성에 권장되는 `calculation_mode="equity"`를 사용합니다.

## 검증

1. Docker `show-config`로 기본 config와 dry-run overlay의 병합 및 스키마 검증 통과
2. 병합 결과에서 `dry_run=true`, `initial_state=running`, 전용 SQLite 경로 확인
3. KoreanStarterStrategy 2년 백테스트에 `--enable-protections`를 적용
4. `CooldownPeriod`, `StoplossGuard`, `MaxDrawdown` 플러그인 로드 확인
5. 소스 계약 테스트로 모든 전략의 세 보호장치와 dry-run API 키 공란을 고정

보호장치 활성 백테스트 결과는 88건, `-11.400 USDT`, 최대 낙폭 `18.056 USDT`로 비활성 기준과 동일했습니다. 이 구간에서는 손실 stoploss 연속 발생과 60분 내 동일 페어 재진입이 없어 잠금 조건이 발동하지 않았습니다.

## 판단

보호장치는 유효하게 로드되지만 현재 백테스트의 음수 성과를 개선하지 않습니다. 예기치 않은 연속 손실과 재진입을 제한하는 운영 안전망으로만 취급하며, dry-run 관찰을 거치지 않은 실거래 전환은 보류합니다.
