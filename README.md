# Freqtrade Vibe Strategies

개인 Freqtrade 전략을 독립적으로 관리하는 저장소입니다.

## 포함된 전략

- `VibeRsiStrategy`: 5분봉 RSI 과매도와 EMA 추세 필터를 사용하는 간단한 전략
- `KoreanStarterStrategy`: 15분봉 EMA·RSI·ADX·거래량 필터와 트레일링 스탑을 사용하는 보수적 시작 전략

두 전략 모두 학습·백테스트·모의투자용 출발점이며 수익성을 보장하지 않습니다.

## 사용법

원하는 전략 파일을 Freqtrade의 `user_data/strategies/` 폴더로 복사합니다.

```powershell
Copy-Item strategies/KoreanStarterStrategy.py ../freqtrade/user_data/strategies/
```

그다음 충분한 데이터를 받아 백테스트합니다.

```powershell
docker compose run --rm freqtrade backtesting `
  --config user_data/config.json `
  --strategy KoreanStarterStrategy
```

실거래 전에 장기간 백테스트와 dry-run을 수행하고 거래소 API에는 출금 권한을 부여하지 마세요.

## 재현 가능한 백테스트

검증 환경은 Freqtrade `2026.7` Docker 이미지에 고정되어 있습니다. 먼저 Docker Desktop을 설치한 뒤 예제 설정의 거래소와 페어를 검토하세요. 예제 설정은 현물·dry-run 전용이며 실제 API 키를 요구하지 않습니다.

시장 데이터를 내려받습니다.

```powershell
.\scripts\Get-MarketData.ps1 -Days 365
```

명시적인 기간으로 전략을 백테스트합니다.

```powershell
.\scripts\Invoke-Backtest.ps1 `
  -Strategy KoreanStarterStrategy `
  -Timerange 20250101-20260101
```

생성된 데이터와 결과는 `user_data/` 아래에 저장되며 Git에는 포함되지 않습니다. 서로 다른 결과를 비교할 때는 Freqtrade 이미지 버전, 설정, 페어, 기간과 전략 커밋을 동일하게 유지하세요.
