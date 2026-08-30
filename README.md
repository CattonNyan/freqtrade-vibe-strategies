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
