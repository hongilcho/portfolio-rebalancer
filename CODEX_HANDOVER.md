# 📘 Portfolio Rebalancer — Codex 인수인계 및 개발 가이드 (Handover Guide)

> **문서 목적**: 본 문서는 OpenAI Codex 또는 새로운 AI/개발자 환경에서 이 프로젝트의 개발을 즉시 이어서 진행할 수 있도록 **환경 구성, 시스템 아키텍처, 데이터 모델, 핵심 금융 공학 로직(수식 포함), 설계 원칙 및 주의사항**을 완벽하게 정리한 인수인계 문서입니다.

---

## 1. 프로젝트 요약 (Executive Summary)

* **프로젝트명**: Portfolio Rebalancer (자산 배분 포트폴리오 리밸런서)
* **목적**:
  * 복수 계좌(일반 위탁, ISA, 연금저축, IRP, CMA, 금현물 등)에 분산된 자산과 가상자산(업비트)을 다중 포트폴리오로 통합 관리
  * 거래소 실시간 시세 연동(네이버 금융 JSON API 1순위, NH투자증권 나무 API 2순위, yfinance 3순위, 업비트)
  * 증권사 MTS 원본 매입단가(평단가)를 100% 보존하면서 실제 세후 배당금을 시계열로 정밀 추적하는 **Total Return 손익 체계** 제공
  * IRP 위험자산 70% 규제 검증, 계좌별 우선순위/납입한도, 최소 이체(Transfer) 최적화 기반 **스마트 리밸런싱 플랜** 자동 산출
* **핵심 설계 철학**:
  1. **증권사 MTS 일치성**: 인위적으로 평단가를 깎아 손익을 맞추지 않음. 적립식 매수 및 증권사 잔고와 1원 단위까지 1:1 대조 가능.
  2. **데이터 조회 및 캐시**: 주요 테이블 배치 조회와 메모리·PostgreSQL 캐시(`market_cache`). 시작 시 예열하며 일반 시세 만료 시에는 캐시를 반환하고 백그라운드 갱신합니다. 강제 새로고침·리밸런싱은 수집을 기다립니다. 응답 시간 보장은 없습니다.
  3. **클린 아키텍처**: 데이터베이스(영속성), 비즈니스 로직(도메인/금융공학), API 계층(FastAPI), UI(React 19)의 철저한 관심사 분리.

---

## 2. 개발 및 런타임 환경 (Environment & Setup)

### 2.1 기술 스택
* **Language & Backend**:
  * Python `3.12.x` (루트의 `.python-version` 및 `runtime.txt` 참조)
  * FastAPI, Uvicorn, Pydantic, python-dotenv
  * `psycopg2-binary` (PostgreSQL 스레드세이프 커넥션 풀링)
  * `pandas==2.2.3`, `python-dateutil`
  * 시세 수집: `requests`, `yfinance`, `lxml`, `urllib3`
* **Frontend**:
  * Node.js `v18+` or `v20+`
  * React `19.2.x`, Vite `8.2.x`, Lucide React
  * CSS Variables 기반 모던 테마 시스템 (다크/라이트/세피아, Tailwind 미사용)
  * Oxlint (`npm run lint`)
* **Database**:
  * Supabase PostgreSQL (AWS 기반, Connection Pooling 지원)
  * 영구 시세 캐시 테이블: `market_cache` (JSONB)
* **운영 체제 환경**:
  * Windows (개발 머신 기준, PowerShell / CMD)
  * Git 실행 경로: `C:\Program Files\Git\cmd\git.exe`
  * Python 인코딩: `$env:PYTHONIOENCODING='utf-8'` (PowerShell 한글 출력 필수)

---

### 2.2 환경 변수 (`.env`) 설정
프로젝트 루트 디렉토리에 `.env` 파일이 필요합니다 (`.env.example` 참조):

```env
# 1. Supabase PostgreSQL 접속 URL (필수)
# 트랜잭션 풀러(포트 6543) 또는 세션 풀러(포트 5432)
SUPABASE_URL=postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres

# 2. 애플리케이션 진입 비밀번호 (기본값: 1234)
APP_PASSWORD=1234

# 3. NH투자증권 나무(Namuh) PLUG 오픈 API (선택사항 - 잔고 동기화 및 금현물 1순위)
NAMUH_APP_KEY=your_namuh_app_key
NAMUH_APP_SECRET=your_namuh_app_secret

# 4. 환율 고정 Fallback (기본값: 1380.0)
DEFAULT_USD_KRW=1380.0
```

---

### 2.3 실행 및 검증 명령어

#### 1) 개발 서버 기동 (원클릭)
Windows 환경에서는 루트의 배치 파일을 실행합니다:
```cmd
start_dev.bat
```
* **Backend API (Swagger Docs)**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **Frontend Web UI**: [http://localhost:5173](http://localhost:5173)

수동 기동 시:
```bash
# 백엔드 기동 (Port 8000)
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# 프론트엔드 기동 (Port 5173)
cd frontend
npm run dev
```

#### 2) 테스트 실행 (격리 회귀 테스트; DB 의존 테스트는 별도 검증)
```bash
# 루트 디렉토리에서 실행
python -m pytest -q -p no:cacheprovider
```

#### 3) 프론트엔드 린트 및 프로덕션 빌드 검증
```bash
cd frontend
npm run lint      # oxlint 기반 (0 warning, 0 error)
npm run build     # Vite 프로덕션 빌드 (1초대 번들링 완료)
```

---

## 3. 디렉토리 구조 및 역할

```
portfolio-rebalancer/
├── backend/
│   ├── config.py           # .env 로딩, DB URL, 보안 암호, 상속 상수
│   ├── main.py             # FastAPI 앱 생성, CORS 허용, 라이프사이클 이벤트
│   ├── services.py         # MarketStateService (시세 캐시 싱글톤, 인메모리 + DB 캐시)
│   └── routers/
│       ├── dashboard.py    # /api/dashboard/bundle (대시보드 원샷 초고속 번들), Total Return 메트릭 계산
│       ├── holdings.py     # 계좌별 보유종목 조회/수정/배당정보 연동
│       ├── accounts.py     # 계좌 CRUD, 납입한도/세액공제한도 관리
│       ├── assets.py       # 자산 종목 CRUD, 목표비중, 정기예금 메타데이터
│       ├── trades.py       # 매매기록 CRUD, INIT/BUY/SELL 로깅
│       ├── rebalance.py    # 리밸런싱 실행 및 계좌 간 자금 이체 플랜 도출
│       ├── sync.py         # NH투자증권 나무 잔고 자동 동기화
│       ├── portfolios.py   # 다중 포트폴리오 관리 (생성, 전환, 복제)
│       ├── crypto.py       # 업비트 가상자산 시세, 소유자별 지분 배분
│       └── system.py       # 외부 API 핑 지연시간 및 시스템 상태 진단
│
├── data/
│   ├── data_manager.py     # PostgreSQL 스레드세이프 커넥션 풀, get_overview_batch_data (단일 배치 쿼리)
│   ├── enums.py            # AccountType, AssetClass 등 표준 Enum 정의
│   └── nh_api.py           # NH투자증권 Namuh PLUG API 클라이언트 (OAuth 2.0)
│
├── logic/
│   ├── dividend_fetcher.py # 거래소 공식 배당금 수집(yfinance) + trade_history 시계열 수량 추적 알고리즘
│   ├── price_fetcher.py    # 3단계 시세 수집기 (네이버 JSON 1순위, NH 2순위, yfinance 3순위), 예금 일할 단리 이자
│   └── rebalance_calculator.py # 목표 비중 괴리율 분석, 매매 수량 산출, IRP 70% 규제 검증
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Tab1Dashboard/ # 대시보드 탭 (KPI 카드, 통화 토글, 예금 토글, 자산목록, 계좌별 카드, 배당모달)
│   │   │   ├── Tab2Assets/    # 자산 및 목표비중 관리 탭
│   │   │   ├── Tab3Rebalance/ # 리밸런싱 시뮬레이션 및 매매/이체 실행 탭
│   │   │   ├── Tab4Trades/    # 전체 매매 이력(trade_history) 조회 탭
│   │   │   ├── Tab5Crypto/    # 업비트 가상자산 소유자별 현황 탭
│   │   │   └── Tab6Settings/  # 다중 포트폴리오 관리, 나무 API 설정, 시스템 진단
│   │   └── utils/
│   │       ├── api.js         # fetch 기반 고속 번들 API 클라이언트
│   │       └── formatters.js  # 통화(KRW/USD), 백분율, 날짜 포맷 함수
│   └── package.json
│
├── docs/
│   ├── DEPLOYMENT_GUIDE.md # Render, Vercel, NH API 배포 및 접속 조건 가이드
│   └── BRANCH_MANAGEMENT_STRATEGY.md # 깃 브랜치 전략
│
├── scripts/
│   ├── seed_dev_db.sql     # 최신 DDL 스키마 및 가짜(Mock) 샘플 데이터 SQL
│   └── seed_dev_db.py      # 파이썬 DB 시딩 러너
│
├── tests/                  # Pytest 기반 격리 회귀 테스트 스위트
├── start_dev.bat           # 윈도우 원클릭 서버 실행 스크립트
├── .env.example            # 환경 변수 템플릿 (필수/선택 명시)
├── PROJECT_STRUCTURE.md    # 아키텍처 상세 명세서
└── CODEX_HANDOVER.md       # (본 문서) 인수인계 가이드
```

---

## 4. 데이터베이스 스키마 및 핵심 모델

계좌·자산의 `portfolio_id`를 통해 금융 포트폴리오를 구분합니다. 보유·거래는 계좌·자산을 통해 연결하며 가상자산은 소유자별 별도 관리입니다 (`default` 포트폴리오가 기본값).

### 4.1 테이블 구조
1. **`portfolios`**: 포트폴리오 엔티티
   * `id` (VARCHAR PK), `name`, `description`, `is_default`, `created_at`
2. **`accounts`**: 증권/은행 계좌
   * `id` (VARCHAR PK), `account_no` (계좌번호), `account_alias` (별칭), `account_type` (`일반`, `ISA`, `연금`, `IRP`, `CMA`, `금현물`, `정기예금`)
   * `deposit_krw` (원화 예수금), `deposit_usd` (달러 예수금)
   * `annual_limit` (연간 납입한도), `tax_limit` (세액공제 한도)
   * `priority` (리밸런싱 매수 우선순위 1~99), `limit_preference` (`ANNUAL` / `TAX`)
   * `portfolio_id` (FK)
3. **`assets`**: 투자 자산 마스터
   * `id` (VARCHAR PK), `name`, `ticker`, `market` (`KR`, `US`)
   * `is_risk_asset` (위험자산 여부 - IRP 70% 룰 적용 대상)
   * `target_weight` (목표 비중 %), `include_in_rebalance` (리밸런싱 대상 포함 여부)
   * `is_deposit` (정기예금 여부), `deposit_principal` (원금), `interest_rate` (연이율), `start_date`, `maturity_date`, `tax_rate` (세율)
   * `portfolio_id` (FK)
4. **`holdings`**: 계좌별 보유 종목 상태
   * `id` (VARCHAR PK), `account_id` (FK), `asset_id` (FK)
   * `quantity` (현재 보유 수량)
   * `avg_price` (증권사 원본 매입단가 KRW), `avg_price_usd` (미국주식 매입단가 USD), `buy_fx_rate` (매입환율)
   * `original_avg_price`, `first_buy_date` (최초 매수일), `manual_dividend_override` (수동 배당 보정값)
5. **`trade_history`**: 매매 거래 내역 (영구 보존)
   * `id` (VARCHAR PK), `trade_date` (YYYY-MM-DD), `account_id` (FK), `asset_id` (FK)
   * `trade_type` (`INIT` - 초기잔고/스냅샷, `BUY` - 매수, `SELL` - 매도)
   * `quantity`, `price`, `currency` (`KRW`/`USD`), `exchange_rate`, `notes`
6. **`crypto_holdings`**: 가상자산 보유 상태
   * `id`, `owner` (소유자명), `symbol` (BTC, ETH 등), `name`, `quantity`, `avg_buy_price`, `portfolio_id`
7. **`market_cache`**: 영구 시세/배당 캐시
   * `key` (TEXT PK, e.g. `div_KR_379810`), `data` (JSONB), `updated_at` (TIMESTAMP)

---

## 5. 핵심 비즈니스 로직 및 계산 공식

### 5.1 Total Return 배당금 추적 시스템 (`logic/dividend_fetcher.py`)

#### ① 평단가 비차감 및 MTS 일치 원칙
* 과거 단기채(SGOV 등)에서 사용하던 "배당금으로 평단가를 인위적으로 깎는 방식(Adjusted Cost Basis)"은 적립식 매수를 반복하는 일반 ETF에서는 증권사 MTS와 대조가 불가능해지는 치명적 결함이 있었습니다.
* 본 시스템은 **증권사 MTS 매입단가(`avg_price`)를 100% 원본 그대로 보존**하고, 배당금을 별도의 독립 수익(Dividend Income)으로 집계하여 Total Return에 합산합니다.

#### ② 매매기록(`trade_history`) 시계열 수량 역추적 알고리즘
* 단순 곱셈(`현재 수량 × 누적 배당금`)의 과대계상 문제를 해결하기 위해, 각 배당락일(Ex-Dividend Date) 당시의 실제 보유 수량을 역추적합니다:
  ```python
  # 1. 배당락일 ex_date 직전 거래일까지 발생한 거래 필터링
  prior_trades = [t for t in trades if t['trade_date'] < ex_date]

  # 2. 가장 최근 INIT(스냅샷) 기준으로 잔고 복원 후 BUY(+) / SELL(-) 반영
  init_trades = [t for t in prior_trades if t['trade_type'] == 'INIT']
  if init_trades:
      latest_init = init_trades[-1]
      qty_at_ex = latest_init['quantity']
      for t in prior_trades:
          if t['trade_date'] > latest_init['trade_date']:
              if t['trade_type'] == 'BUY': qty_at_ex += t['quantity']
              elif t['trade_type'] == 'SELL': qty_at_ex -= t['quantity']
  else:
      qty_at_ex = sum(BUY) - sum(SELL)
  ```
* **계좌별 원천징수 세율 적용**:
  * 비과세/절세 계좌 (`ISA`, `IRP`, `연금저축`): **0.0%** (과세이연/비과세)
  * 일반 계좌 국내자산: **15.4%** (소득세 14% + 지방세 1.4%)
  * 일반 계좌 미국자산: **15.0%** (한미 조세협약 세율)
* **손익 공식**:
  $$\text{평가손익(KRW)} = \text{현재 평가금액} - \text{매수원금}$$
  $$\text{총 배당금(KRW)} = \sum (\text{배당락일 당시 수량} \times \text{세후 주당배당금})$$
  $$\mathbf{Total\ Return\ 총손익(KRW)} = \text{평가손익} + \text{총 배당금}$$
  $$\mathbf{Total\ Return\ 총수익률(\%)} = \frac{\text{Total Return 총손익}}{\text{매수원금}} \times 100$$

---

### 5.2 이중 통화 및 환차익/환차손 분해 (`backend/routers/dashboard.py`)
미국 주식(US Market) 자산의 경우, 원화 손익을 **순수 주가 수익(Pure Stock Return)**과 **환차익/환차손(FX Gain/Loss)**으로 수학적으로 분해하여 제공합니다:

$$\text{Pure Stock Profit (KRW)} = \text{Eval Profit (USD)} \times \text{현재 환율}$$
$$\text{FX Profit (KRW)} = \text{매수금액 (USD)} \times (\text{현재 환율} - \text{매입 환율})$$
$$\text{Eval Profit (KRW)} = \text{Pure Stock Profit (KRW)} + \text{FX Profit (KRW)}$$

* **가중평균 매입환율 (`weighted_buy_fx_rate`)**:
  $$\text{가중평균 매입환율} = \frac{\sum (\text{종목별 원화 매수금액})}{\sum (\text{종목별 달러 매수금액})}$$
* **대시보드 통화 토글 (KRW / USD)**:
  * 프론트엔드 헤더의 통화 스위치를 통해 원화 기준 포트폴리오와 달러 기준 포트폴리오 뷰를 실시간 전환 가능.

---

### 5.3 3단계 시세 수집 엔진 (`logic/price_fetcher.py`)
1. **1순위 (초고속 ~500ms, 호출 제한 없음)**:
   * **네이버 금융 공식 JSON API**:
     * 실시간 환율: `https://m.stock.naver.com/front-api/marketIndex/prices?category=exchange&reutersCode=FX_USDKRW`
     * 국내 주식: `https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{ticker}`
     * 미국 주식: `https://api.stock.naver.com/stock/{ticker}/basic`
2. **2순위 (국내 장외 특화)**:
   * **NH투자증권 Namuh PLUG API**:
     * KRX 금현물(1g 단위, `M04020000` 1순위 수집)
     * 네이버 API 장애 시 국내/해외 주식 2순위 폴백
3. **3순위 (글로벌 표준)**:
   * **Yahoo Finance (`yfinance`)**:
     * 해외 자산 및 배당 이력 최종 폴백

---

### 5.4 스마트 리밸런싱 최적화 엔진 (`logic/rebalance_calculator.py`)
* **목표 비중 괴리율 분석**:
  $$\text{Drift (\%)} = \text{현재 비중 (\%)} - \text{목표 비중 (\%)} = \left(\frac{\text{자산 평가액}}{\text{리밸런싱 총 주식 평가액}} \times 100\right) - \text{Target Weight}$$
* **IRP 70% 위험자산 한도 규제 강제 검증**:
  * IRP 계좌의 위험자산(`is_risk_asset = True`) 비중이 70%를 초과할 경우 경고 및 매수 제한.
* **계좌별 우선순위 기반 자금 배분**:
  * 계좌 우선순위(`priority`: ISA > 연금저축 > IRP > 일반)에 따라 신규 매수 자금을 우선 배정하고, 절세 계좌의 연간 납입한도/세액공제 한도 소진 여부 검증.
* **계좌 간 최소 이체 플랜 (Transfer Plan)**:
  * 예수금이 부족한 계좌로 잉여 예수금을 최소 거래 횟수로 이체하는 최적화 경로 도출.

---

### 5.5 특수 자산 및 계좌 처리 규칙
1. **정기예금 (Pure Asset 모델)**:
   * 정기예금은 계좌가 아니라 자산(`is_deposit = True`)으로 모델링.
   * 일할 단리로 세전이자를 계산하고, 이자에만 세금을 부과하여 평가액에 가산:
     `세전이자 = 원금 × (연이율 / 100) × 경과일수 / 365`
     `이자세금 = floor(세전이자 × 세율 / 100)`
     `평가액 = 원금 + 세전이자 − 이자세금`
   * 대시보드 탭 상단의 **'예금 포함/제외' 토글**로 순수 투자자산 뷰와 종합 자산 뷰 원터치 전환.
2. **CMA 계좌 20:00 컷오프 특성**:
   * 증권사 CMA 계좌는 매일 오후 8시 이후 잔고가 예수금에서 'CMA 발행어음'으로 자동 매수되어 다음 날 오전까지 예수금이 0원으로 잡힙니다.
   * 나무 API 동기화 시 오후 늦게 0원이 들어와 실제 현금을 덮어쓰지 않도록 안전 로직이 적용되어 있습니다.
3. **KRX 금시장 현물 (`M04020000`)**:
   * 1주가 아닌 **1g 단위**로 거래되며, 부가가치세 및 양도소득세 비과세 자산입니다.

---

## 6. 개발 시 주의사항 및 알려진 엣지케이스 (Pitfalls & Rules)

1. **`trade_history` 누적과 배당 계산의 관계**:
   * `data/data_manager.py`의 `get_overview_batch_data()` 및 `holdings` 쿼리에서 `trade_date <= '2000-01-01'`인 초기 레코드는 인셉션 일자(`'2026-07-01'`)로 안전하게 매핑됩니다.
   * **하드코딩 금지**: 특정 종목의 배당금을 하드코딩 테이블로 때려 맞추지 마십시오. 과거 보유 종목과 현재 종목의 티커(예: 환헤지 H형 `453850` vs 환노출형 `476760`)를 명확히 구분하고, `trade_history`의 수량을 올바르게 유지하면 yfinance 공식 배당금과 1원 단위까지 자동으로 일치합니다.
2. **전량 매도 종목 처리 철학 (관점 A 유지 중)**:
   * 현재 대시보드 메인 표는 **현재 보유 중인 포지션(Open Positions, `quantity > 0`)**만 표시합니다.
   * 전량 매도된 종목의 매도 대금과 과거 수령 배당금은 이미 계좌의 **예수금(`deposit_krw`)**으로 입금되어 총 자산 평가액에 100% 녹아 있습니다.
   * 추후 확장이 필요할 경우, 메인 표를 건드리지 말고 **"청산 포지션 (Closed Positions)"** 전용 리포트나 배당 캘린더 탭을 신설하십시오.
3. **N+1 쿼리 절대 금지 (단일 배치 쿼리 유지)**:
   * 백엔드는 대시보드 로딩 시 `data_manager.get_overview_batch_data()`의 단 1회 PostgreSQL `json_build_object` 쿼리로 포트폴리오, 계좌, 자산, 보유종목, 거래내역 150여 건을 0.02초 만에 한 번에 수취합니다.
   * 루프 안에서 개별 DB 쿼리를 날리는 N+1 패턴을 절대 작성하지 마십시오.

---

## 7. 향후 추천 로드맵 (Next Steps for Codex)

1. **과거 청산 종목(Closed Positions) 전용 리포트**:
   * 전량 매도되어 현재 보유 수량이 0인 종목들의 누적 매도 실현손익 및 보유 기간 배당금 집계 화면 추가.
2. **월별/연도별 배당금 캘린더 (Dividend Calendar)**:
   * `trade_history`와 배당 공시일을 매핑하여 이번 달 / 다음 달 예상 배당금 캘린더 위젯 개발.
3. **나무(Namuh) API 자동 주문 연동 검토**:
   * 리밸런싱 탭에서 도출된 매수/매도 주문을 원클릭으로 증권사 모의/실전 계좌로 전송하는 확장.

---

> 💡 **Codex 작업 팁**: 작업을 시작할 때는 항상 `git status`로 브랜치를 확인하고, 코드 변경 후에는 반드시 `python -m pytest -q -p no:cacheprovider`와 `cd frontend && npm run build`를 실행하여 정합성을 검증하십시오!


## 최신 보완 사항

개별·전체 화면은 배당 포함 보유자산 수익률을 사용하며 예수금을 분모에서 제외합니다. 거래 취소의 현금 복원, 기존 거래 삭제 제한, 테스트 격리와 배포 전 검증은 [ACCOUNTING_CHANGES.md](docs/ACCOUNTING_CHANGES.md)를 우선 참조하세요. 문서의 성능 수치와 운영 설정은 실제 측정·대시보드 확인 없이 보장하지 않습니다.
