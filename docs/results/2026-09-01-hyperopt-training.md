# KoreanStarterStrategy 학습 구간 최적화

## 방법

- 학습 구간: 2024-09-01 ~ 2025-09-01 (startup 제외 후 356일)
- 페어/타임프레임: BTC/USDT, ETH/USDT / 15분
- 수수료: 진입/청산 각각 0.1%
- 탐색 공간: `buy_rsi`, `buy_adx`, `sell_rsi`, EMA20/50 청산 사용 여부
- 목적 함수: `MultiMetricHyperOptLoss`
- 시행 횟수: 200 epochs
- 재현 seed: 42
- 최소 거래 수: 20
- 병렬 worker: 4
- ROI, stoploss, trailing 설정은 고정

## 선택 결과

```python
buy_adx = 19
buy_rsi = 47
sell_rsi = 77
sell_use_ema_exit = False
```

| 학습 구간 지표 | 기본값 | 선택값 |
|---|---:|---:|
| 거래 수 | 46 | 89 |
| 총손익 | -2.135 USDT | +27.730 USDT |
| 승률 | 58.7% | 77.5% |
| Profit Factor | 0.89 | 2.67 |
| Expectancy | -0.05 USDT | +0.31 USDT |
| 평균 보유시간 | 3시간 15분 | 10시간 5분 |
| 최대 낙폭(종료 거래) | 8.655 USDT | 8.185 USDT |

Hyperopt가 보고한 선택 epoch는 168/200이며, 선택값을 고정한 별도 backtesting 명령에서도 결과가 동일하게 재현됐습니다.

## 주의와 결정

학습 성과는 파라미터 선택에 사용된 동일 데이터의 결과이므로 미래 성과의 증거가 아닙니다. 특히 선택값은 EMA 청산을 끄고 보유시간을 크게 늘리며, 학습 구간에 한 건의 `-8.18%` stoploss가 발생했습니다. 운영 전략의 기본값은 아직 변경하지 않고 다음 독립 검증 구간에 그대로 적용합니다.

Freqtrade 2026.7 Hyperopt는 `joblib.externals.cloudpickle`을 사용하지만 joblib 1.6.0에서는 해당 경로가 제거됐습니다. 재현 가능한 설치를 위해 런타임 요구사항에 Hyperopt extra와 `joblib>=1.2,<1.6` 호환 범위를 명시했습니다.
