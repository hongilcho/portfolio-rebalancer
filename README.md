# 📈 자산 배분 포트폴리오 리밸런서 (Portfolio Rebalancer)

다계좌(일반, ISA, 연금저축, IRP, 정기예금 등) 및 다중 포트폴리오 기반의 자산 배분 관리 및 스마트 리밸런싱 계산 시스템입니다.  
초고속 실시간 시세 연동(네이버 금융 JSON API 1순위, NH투자증권 Namuh PLUG API, 업비트) 및 목표 비중 기반의 최적 매수/매도/이체 플랜을 자동으로 도출합니다.

> 📖 **자세한 시스템 구조 및 모듈별 명세**: [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)를 참고해 주세요.

---

## 🏛️ 시스템 아키텍처 요약

```
portfolio-rebalancer/
├── backend/            # FastAPI 고성능 백엔드 API (단일 번들 통신, SWR 영구 캐시)
│   ├── routers/        # 도메인별 라우터 (대시보드 번들, 계좌, 자산, 거래, 리밸런싱, 가상화폐, 시스템 진단 등)
│   ├── config.py       # 중앙 환경변수 및 보안 설정 (.env & 하위호환 지원)
│   ├── main.py         # FastAPI 애플리케이션 진입점 및 CORS 설정
│   └── services.py     # MarketStateService 싱글톤 (SWR 백그라운드 갱신 및 Zero Cold-Start)
├── frontend/           # React 19 + Vite 모던 웹 프론트엔드 (Dark/Light/Sepia 테마)
│   ├── src/components/ # 탭별 컴포넌트 (포트폴리오 현황, 예금 토글, 목표비중, 리밸런싱, 거래내역, 가상자산, 설정)
│   └── src/utils/      # 고속 번들 API 클라이언트 및 통화/비율 포맷터
├── data/               # 데이터베이스 매니저 (Supabase PostgreSQL 스레드세이프 커넥션 풀 & NH API)
├── logic/              # 3단계 시세 수집기 (네이버 1순위, NH 2순위, yf 3순위), 리밸런싱 최적화 엔진
├── docs/               # 브랜치 전략, 시스템 명세 및 아카이브 문서
├── tests/              # pytest 기반 백엔드 통합 및 단위 테스트 (27개 테스트 전체 통과)
└── PROJECT_STRUCTURE.md # 전체 소프트웨어 구조 및 아키텍처 상세 명세서
```

### 기술 스택
- **Frontend**: React 19, Vite, Lucide React, CSS Variables (다크/라이트/세피아 모드 지원)
- **Backend**: FastAPI, Uvicorn, Pydantic, Python 3.12
- **Database**: Supabase PostgreSQL (ThreadedConnectionPool 기반 고성능 연결 풀 & `market_cache` 영구 캐시)
- **External APIs**: 네이버 금융 공식 JSON API (환율/국내/미국 1순위), NH투자증권 Namuh PLUG API (금현물 1순위 & 계좌 동기화), Upbit Open API

---

## 🚀 시작하기

### 1. 환경 변수 설정
루트 디렉토리에 `.env` 파일을 생성하거나 `.streamlit/secrets.toml`을 설정합니다:
```bash
cp .env.example .env
```

`.env` 설정 예시:
```env
# Supabase PostgreSQL 접속 URL
SUPABASE_URL=postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres

# 애플리케이션 접속 암호 (기본값: 1234)
APP_PASSWORD=1234

# NH투자증권 Namuh PLUG 오픈 API (선택사항 - 시세 및 계좌 잔고 자동 연동)
NAMUH_APP_KEY=
NAMUH_APP_SECRET=
```

### 2. 가동 (원클릭 개발 서버)
Windows 환경에서는 `start_dev.bat`을 실행하면 백엔드와 프론트엔드가 동시에 실행됩니다:
```cmd
start_dev.bat
```
- **Backend API (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Frontend Web UI**: [http://localhost:5173](http://localhost:5173)

---

## 🧪 테스트 및 품질 검증

### 백엔드 테스트 실행
```bash
python -m pytest
```

### 프론트엔드 린터 및 빌드
```bash
cd frontend
npm run lint      # oxlint 기반 정적 분석 (0 warning, 0 error)
npm run build     # Vite 프로덕션 번들 빌드
```

---

## 🌿 깃 브랜치 전략
- **`main`**: 프로덕션 배포 브랜치 (Render 백엔드 & Vercel 프론트엔드 연동)
- **`legacy/streamlit`**: 기존 Streamlit 원본 소스코드 영구 보존용 아카이브 브랜치
