# 🚀 Portfolio Rebalancer — 실제 배포 설정 및 환경 가이드 (Deployment Guide)

> 본 문서는 **Render (백엔드)** 및 **Vercel (프론트엔드)**의 실제 프로덕션 배포 설정값, 시작 명령어, 필수 환경 변수, CORS 및 **NH투자증권 Open API 접속 조건(IP 허용 정책)**을 명시한 배포 가이드입니다.

> 아래 배포값은 구성 참고용입니다. 실제 배포 SHA, 연결 브랜치와 Auto-Deploy 상태는 운영 대시보드에서 확인해야 합니다. 이번 보완에서는 운영 배포·DB 변경을 수행하지 않았습니다. 배포 전 [거래 취소 스키마 및 검증 사항](ACCOUNTING_CHANGES.md)을 확인하세요.

---

## 1. 백엔드 배포: Render (Cloud Web Service)

Render는 FastAPI 백엔드를 구동하는 PaaS 플랫폼입니다.

* **GitHub 연결 레포지토리**: `https://github.com/hongilcho/portfolio-rebalancer`
* **배포 연결 브랜치**: **`main`**
* **Auto-Deploy**: 실제 Render 대시보드에서 확인 (문서만으로 활성 여부를 판단하지 않음)
* **런타임 환경 (Runtime)**: `Python 3` (루트의 `runtime.txt`에 `python-3.12.10` 지정됨)
* **Root Directory**: `.` (프로젝트 루트 디렉토리)
* **Build Command**:
  ```bash
  pip install -r requirements.txt
  ```
* **Start Command**:
  ```bash
  uvicorn backend.main:app --host 0.0.0.0 --port $PORT
  ```
  *(Render가 주입하는 동적 환경변수 `$PORT`에 바인딩)*
* **Health Check Path**: `/api/health` (현재 코드의 상태 확인 경로)

### Render 필수 환경 변수 (Environment Variables)
Render 대시보드 > Web Service > `Environment` 탭에 다음 변수들을 등록합니다:

| 변수명 | 필수 여부 | 예시 / 기본값 | 설명 |
| :--- | :---: | :--- | :--- |
| `SUPABASE_URL` | **필수** | `postgresql://postgres.[ref]:[pw]@[host]:6543/postgres` | Supabase 트랜잭션 풀러(6543) 연결 문자열 |
| `APP_PASSWORD` | 선택 | `1234` | 대시보드 로그인 비밀번호 (미설정 시 1234) |
| `NAMUH_APP_KEY` | 선택 | `(나무증권 App Key)` | NH투자증권 오픈 API 키 |
| `NAMUH_APP_SECRET`| 선택 | `(나무증권 App Secret)` | NH투자증권 오픈 API 시크릿 |
| `DEFAULT_USD_KRW`| 선택 | `1380.0` | 환율 외부 API 장애 시 기준 폴백값 |
| `PYTHON_VERSION` | 선택 | `3.12.10` | 파이썬 버전 명시 |

---

## 2. 프론트엔드 배포: Vercel (Edge SPA)

Vercel은 React 19 + Vite SPA를 호스팅하는 CDN 플랫폼입니다.

* **GitHub 연결 레포지토리**: `https://github.com/hongilcho/portfolio-rebalancer`
* **배포 연결 브랜치**: **`main`**
* **Root Directory**: **`frontend`** *(반드시 frontend 디렉토리로 지정해야 함)*
* **Framework Preset**: `Vite`
* **Build Command**: `npm run build`
* **Output Directory**: `dist`
* **SPA Routing 설정 (`frontend/vercel.json`)**:
  새로고침 시 404가 발생하지 않도록 모든 경로를 `/index.html`로 리라이트합니다:
  ```json
  {
    "rewrites": [
      {
        "source": "/(.*)",
        "destination": "/index.html"
      }
    ]
  }
  ```

### Vercel 필수 환경 변수 (Environment Variables)
Vercel 대시보드 > Project Settings > `Environment Variables` 탭에 다음 변수를 등록합니다:

| 변수명 | 필수 여부 | 예시 값 | 설명 |
| :--- | :---: | :--- | :--- |
| `VITE_API_BASE_URL` | **필수** | `https://portfolio-rebalancer-api.onrender.com` | 위 Render 백엔드의 프로덕션 도메인 (끝에 슬래시 `/` 제외) |

---

## 3. CORS 및 네트워크 통신 정책

* **백엔드 CORS 허용 (`backend/main.py`)**:
  ```python
  app.add_middleware(
      CORSMiddleware,
      allow_origins=["*"],  # Vercel 배포 도메인, localhost 모두 허용
      allow_credentials=True,
      allow_methods=["*"],
      allow_headers=["*"],
  )
  ```
  Vercel 프론트엔드 도메인이 바뀌더라도 별도의 CORS 화이트리스트 수정 없이 즉시 통신이 가능합니다.

---

## 4. NH투자증권 Namuh PLUG Open API 접속 조건 및 허용 IP 정책

### 4.1 접속 조건
* **API Base URL**: `https://api.nhplug.com:8443`
* **인증 프로토콜**: OAuth 2.0 Client Credentials Grant (`/oauth2/tokenP`)

### 4.2 공인 IP (IP Whitelist) 제한 및 클라우드 환경 특성
* **NH API IP 제한 정책**:
  * NH투자증권 오픈 API 개발자 센터에서는 보안 규정에 따라 키 발급 시 **사전에 등록된 공인 IP (Static Public IP)** 에서의 접속만 허용합니다.
* **클라우드(Render, Vercel, Codex Cloud 등) 환경 이슈**:
  * Render나 Vercel 같은 서버리스/PaaS 환경은 요청 시마다 아웃바운드 공인 IP가 동적으로 변경되므로, NH API 토큰 발급 호출 시 `IP 미등록 오류(403/500)`가 발생할 수 있습니다.
* **시스템의 내결함성(Fault-Tolerance) 아키텍처**:
  1. **자동 폴백 설계**: 백엔드는 NH API 인증이나 호출이 실패하더라도 시스템이 블로킹되지 않고, **1순위 네이버 금융 JSON API** 및 **3순위 Yahoo Finance(yfinance)** 로 0.1초 만에 자동 전환됩니다.
  2. **시세 및 배당 정상 보장**: 따라서 NH API가 연결되지 않는 클라우드 환경에서도 **실시간 환율, 국내주식 시세, 미국주식 시세 및 Total Return 배당금 계산은 100% 정상 작동**합니다.
  3. **나무증권 계좌 잔고 동기화(Sync)**: 나무 계좌 잔고를 실시간 스크래핑해오는 기능만 NH API가 필요하므로, 이 작업은 공인 IP가 등록된 **로컬 PC 환경**에서 수행하거나 클라우드에 고정 IP Egress 프록시(Fixie 등)를 연결하여 사용할 수 있습니다.
