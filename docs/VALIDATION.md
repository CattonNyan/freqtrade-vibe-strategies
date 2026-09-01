# 전략 검증 절차

이 문서는 전략 수치를 변경하기 전에 반드시 수행할 검증 순서를 정의합니다. 예제 설정은 현물 dry-run 전용이며 실거래 설정으로 사용하면 안 됩니다.

## 현재 검증 상태

- Python AST 기반 소스 계약 검사: 통과
- 명시적인 음수 `shift` 및 `iloc` 참조 검사: 통과
- Freqtrade 런타임 전략 로딩: 미실행
- `recursive-analysis`: 2026-09-01 실행 완료
- `lookahead-analysis`: 미실행
- 백테스트 및 워크포워드 비교: 미실행

재귀 분석의 조건과 결과는 [`results/2026-09-01-recursive-analysis.md`](results/2026-09-01-recursive-analysis.md)에 기록되어 있습니다. 정적 검사와 재귀 분석 통과를 수익성 또는 전체 신호의 lookahead 검증으로 해석하지 마세요.

## 1. 데이터 준비

두 전략의 5분봉과 15분봉을 동일한 시장과 기간으로 내려받습니다.

```powershell
.\scripts\Get-MarketData.ps1 -Days 730
```

기본 페어는 `BTC/USDT`, `ETH/USDT`입니다. 실제 운용 대상이 다르면 예제 config의 whitelist와 스크립트의 `Pairs` 값을 함께 변경합니다.

## 2. 편향과 지표 안정성 검사

EMA 재귀 오차의 기준값을 만들 수 있도록 최소 5,000봉 이상이 포함된 기간을 지정합니다.

```powershell
.\scripts\Invoke-StrategyAnalysis.ps1 `
  -Timerange 20250101-20260101 `
  -Pair BTC/USDT
```

통과 조건은 다음과 같습니다.

1. lookahead 결과의 `has_bias`가 `No`여야 합니다.
2. 진입과 청산 신호가 각각 실제로 발생해 검사되어야 합니다.
3. 현재 `startup_candle_count`에서 진입 판단에 영향을 줄 정도의 EMA 편차가 없어야 합니다.
4. 편차가 크면 결과가 안정되는 후보 중 과도한 거래소 API 호출을 유발하지 않는 값을 선택합니다.

분석 결과 없이 `startup_candle_count`를 임의로 높이지 않습니다.

lookahead 분석은 지정가 전략을 시장가로 강제하는 Freqtrade의 기본 검사 방식과 호환되도록 `config/lookahead.json`을 두 번째 config로 적용합니다. 이 override는 분석 전용이며 일반 백테스트와 dry-run 가격 정책을 변경하지 않습니다.

## 3. 기간 외 검증

최적화 또는 아이디어 검토 기간과 최종 검증 기간을 분리합니다. 아래 날짜는 형식 예시이며 시장 국면이 여러 번 포함되도록 실제 기간을 정해야 합니다.

```powershell
# 아이디어 검토 기간
.\scripts\Invoke-Backtest.ps1 `
  -Strategy KoreanStarterStrategy `
  -Timerange 20240101-20250101

# 사용하지 않은 검증 기간
.\scripts\Invoke-Backtest.ps1 `
  -Strategy KoreanStarterStrategy `
  -Timerange 20250101-20260101
```

최소한 다음 값을 전략별·페어별·청산 태그별로 비교합니다.

- 거래 횟수와 시장 국면별 분포
- 순수익 및 수수료 포함 수익
- 최대 낙폭
- Profit Factor와 Expectancy
- 평균 및 최대 보유시간
- `stop_loss`, `rsi_overbought`, `ema_bearish_cross`, ROI 청산별 성과

거래량 기준 변경 전 비교 기준은 커밋 `0f18e4f`이고, 직전 20개 완료 봉을 사용하는 변경은 `2192db6`입니다. 동일 설정·데이터·기간에서 두 커밋을 비교해야 합니다.

## 4. 보류된 전략 변경

다음 항목은 데이터 검증 전에는 변경하지 않습니다.

- ROI 단계와 고정 손절 비율
- 트레일링 시작 오프셋과 간격
- RSI 과매수 진입 시 청산 또는 과매수 하향 이탈 시 청산 선택
- ATR 기반 동적 손절
- Cooldown, StoplossGuard 및 MaxDrawdown 보호 설정
- RSI·EMA·ADX 파라미터 범위 확장

실거래의 거래소 측 손절 주문은 전략 연구와 별개인 운영 안전 설정입니다. 거래소 지원 여부를 확인하고 dry-run 설정과 분리된 비공개 실거래 config에서 활성화하세요. API 키와 실거래 config는 이 저장소에 커밋하지 않습니다.
