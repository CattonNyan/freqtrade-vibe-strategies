# 전략 분석 및 검증 결과 기록 (Results Archive)

이 디렉터리는 전략 소스 수치 변경, 최적화 또는 검증을 수행했을 때 그 근거가 되는 백테스트 및 분석 결과를 보관하는 저장소입니다.

---

## 보관된 검증 보고서 목록

- [`2026-09-01-recursive-analysis.md`](2026-09-01-recursive-analysis.md): 지표 재귀 안정성(`startup_candle_count`) 검증 결과
- [`2026-09-01-lookahead-analysis.md`](2026-09-01-lookahead-analysis.md): 미래 봉 데이터 참조(Lookahead bias) 검사 결과
- [`2026-09-01-exit-rule-comparison.md`](2026-09-01-exit-rule-comparison.md): 청산 규칙(RSI, EMA 크로스, Stoploss) 성과 비교
- [`2026-09-01-out-of-sample-validation.md`](2026-09-01-out-of-sample-validation.md): 기간 외(Out-of-sample) 시장 국면별 성과 비교
- [`2026-09-01-protection-validation.md`](2026-09-01-protection-validation.md): Cooldown 및 Drawdown 보호장치 유효성 검증
- [`2026-09-01-volume-baseline-comparison.md`](2026-09-01-volume-baseline-comparison.md): 직전 20개 완료 봉 거래량 필터 비교
- [`2026-09-01-hyperopt-training.md`](2026-09-01-hyperopt-training.md): 하이퍼옵트 파라미터 튜닝 기록

---

## 새 검증 결과 작성 표준 템플릿

새로운 검증 보고서를 작성할 때는 `YYYY-MM-DD-<주제>.md` 형식의 파일명으로 아래 양식을 따릅니다:

```markdown
# YYYY-MM-DD: <검증 주제 제목>

## 1. 검증 목적
- 변경하려는 전략 속성 또는 검증 가설

## 2. 테스트 환경 및 파라미터
- 실행 일자: YYYY-MM-DD
- 커밋 해시: <commit-hash>
- Freqtrade 버전: 2026.7
- 대상 전략: KoreanStarterStrategy / VibeRsiStrategy / MultiTimeframeAtrStrategy
- 검증 기간: YYYYMMDD-YYYYMMDD
- 거래 페어: BTC/USDT, ETH/USDT

## 3. 실행 명령어
\`\`\`powershell
.\\scripts\\Invoke-Backtest.ps1 -Strategy KoreanStarterStrategy -Timerange 20250101-20260101
\`\`\`

## 4. 검증 결과 요약
| 항목 | 기존 수치 | 신규 수치 | 증감 |
| :--- | :---: | :---: | :---: |
| 총 거래 수 | - | - | - |
| 승률 | -% | -% | -%p |
| 수익률 (Total Return) | -% | -% | -%p |
| 최대 낙폭 (MDD) | -% | -% | -%p |
| Profit Factor | - | - | - |

## 5. 결론 및 다음 단계
- 전략 채택 여부 및 근거
```
