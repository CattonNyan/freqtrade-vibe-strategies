# Freqtrade Vibe Strategies

개인 Freqtrade 전략을 독립적으로 관리하는 저장소입니다.

## 포함된 전략

- `VibeRsiStrategy`: 5분봉 RSI 과매도와 EMA 추세 필터를 사용하는 간단한 전략
- `KoreanStarterStrategy`: 15분봉 EMA·RSI·ADX·거래량 필터와 트레일링 스탑을 사용하는 보수적 시작 전략
- `MultiTimeframeAtrStrategy`: 5분봉 진입 + 1시간봉 상위 추세(EMA 50/200) 및 동적 Break-even 커스텀 스탑로스를 적용한 다중 타임프레임 전략

세 전략 모두 학습·백테스트·모의투자용 출발점이며 수익성을 보장하지 않습니다.
`MultiTimeframeAtrStrategy` 이름은 기존 설정 호환성을 위해 유지하지만, 현재 손절 로직은 ATR이 아닌 수익률 임계값을 사용합니다.

## 사용법

원하는 전략 파일을 Freqtrade의 `user_data/strategies/` 폴더로 복사합니다.

```powershell
Copy-Item strategies/KoreanStarterStrategy.py ../freqtrade/user_data/strategies/
```

그다음 충분한 데이터를 받아 백테스트합니다.

```powershell
docker compose run --rm freqtrade backtesting `
  --config /freqtrade/user_data/config/backtest.example.json `
  --strategy-path /freqtrade/user_data/strategies `
  --strategy KoreanStarterStrategy
```

실거래 전에 장기간 백테스트와 dry-run을 수행하고 거래소 API에는 출금 권한을 부여하지 마세요.

## 재현 가능한 백테스트

검증 환경은 Freqtrade `2026.7` Docker 이미지에 고정되어 있습니다. 먼저 Docker Desktop을 설치한 뒤 예제 설정의 거래소와 페어를 검토하세요. 예제 설정은 현물·dry-run 전용이며 실제 API 키를 요구하지 않습니다.

Docker를 사용할 수 없으면 저장소 내부 가상환경을 사용할 수 있습니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt
```

검증 스크립트는 Docker 엔진에 연결할 수 있으면 Docker를 우선 사용하고, 그렇지 않으면 `.venv`의 Freqtrade를 자동으로 사용합니다.
Windows의 `.venv/Scripts/freqtrade.exe`와 Linux/macOS의 `.venv/bin/freqtrade` 경로를 모두 인식합니다.

Windows 실행 정책이 스크립트를 차단하면 현재 프로세스에만 적용되는 Bypass 옵션으로 실행합니다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\Get-MarketData.ps1 -Days 365
```

시장 데이터를 내려받습니다.

```powershell
.\scripts\Get-MarketData.ps1 -Days 365
```

명시적인 기간으로 전략을 백테스트합니다.

```powershell
.\scripts\Invoke-Backtest.ps1 `
  -Strategy KoreanStarterStrategy `
  -Timerange 20250101-20260101 `
  -Pairs BTC/USDT,ETH/USDT
```

백테스트와 분석 스크립트는 요청한 페어의 전략별 필수 타임프레임 데이터가 없으면 다운로드 명령을 안내하고 실행을 중단합니다.

같은 이름의 결과 파일이 있으면 스크립트가 중단됩니다. 기존 결과를 의도적으로 교체할 때만 `-Force`를 추가하세요.

생성된 데이터와 결과는 `user_data/` 아래에 저장되며 Git에는 포함되지 않습니다. 서로 다른 결과를 비교할 때는 Freqtrade 이미지 버전, 설정, 페어, 기간과 전략 커밋을 동일하게 유지하세요.

개인 API 키가 포함된 설정은 `config/*.private.json` 또는 `config/*.local.json` 이름으로 저장하세요. 해당 파일과 `config/live.json`, `config/live-*.json`, 환경별 `.env.*` 파일은 Git에서 제외됩니다.

전략 소스의 기본 계약과 명시적인 미래 봉 참조를 의존성 없이 검사할 수 있습니다.

```powershell
python -B -m unittest discover -s tests -v
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  .\tests\Test-PowerShellScripts.ps1
```

충분한 데이터가 준비되면 재귀 지표 안정성과 lookahead bias를 함께 검사합니다. 최소 5,000봉 이상이 포함되는 기간을 사용하세요.

```powershell
.\scripts\Invoke-StrategyAnalysis.ps1 -Timerange 20250101-20260101
```

분석 CSV와 recursive/lookahead 실행 로그는 `user_data/backtest_results/`에 전략·페어·기간별로 저장됩니다.

`recursive-analysis` 결과를 검토한 뒤에만 각 전략의 `startup_candle_count`를 확정합니다. 신호가 적어 lookahead 검사가 중단되면 기간을 넓히거나 `MinimumTradeAmount`를 조정하되, 검사하지 못한 신호를 편향 없음으로 간주하지 마세요.

세부 통과 조건과 기간 외 검증 절차는 [`docs/VALIDATION.md`](docs/VALIDATION.md)를 따릅니다. 전략 수치 변경은 이 절차의 결과를 남긴 뒤 별도 커밋으로 진행합니다.

모의투자를 시작하기 전에는 [`docs/DRY_RUN.md`](docs/DRY_RUN.md)의 안전 절차를 따릅니다. 기본 명령은 설정만 검증하며 `-Start`를 명시해야 dry-run 프로세스가 시작됩니다.
