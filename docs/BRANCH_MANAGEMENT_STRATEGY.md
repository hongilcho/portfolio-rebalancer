# 🌿 깃(Git) 브랜치 구조 정상화 및 최적화 전략 제안서
**Portfolio Rebalancer Git Branch Management Strategy**

---

## 📌 1. 현재 상황 및 문제점 분석

현재 저장소에는 다음 브랜치들이 존재하며, 임시 배포 동기화 과정에서 중복이 발생해 있습니다:

1. **`main`**: 현재 최신 React 19 + FastAPI 완성본 코드가 머지되어 배포를 담당하고 있음.
2. **`feat/react-fastapi-migration`**: 마이그레이션 작업용 브랜치였으나, `main`과 100% 동일한 커밋 상태로 남아있음.
3. **`legacy/streamlit`**: 기존 Streamlit 원본 코드가 영구 보존되어 있는 백업 브랜치.

> **문제점**: 피처 브랜치(`feat/...`)의 변경사항이 이미 `main`에 완전히 통합되었음에도 불구하고, 동일한 내용의 두 브랜치가 병렬로 유지되어 개념적 혼란과 관리 포인트 중복을 유발합니다.

---

## 💡 2. 해결 방안 (3가지 전략)

### ✅ 전략 A (강력 권장 ⭐): 표준 GitHub Flow로 브랜치 정리

이미 `main`에 마이그레이션이 성공적으로 머지되었고 기존 코드는 `legacy/streamlit`에 보관되어 있으므로, **개발 완료된 피처 브랜치를 깔끔하게 삭제하고 단일 브랜치(`main`) 체제로 정리**하는 표준 방식입니다.

* **구체적 실행 절차 (3분 소요)**:
  1. Render 대시보드 $\rightarrow$ `portfolio-rebalancer-api` $\rightarrow$ `Settings` $\rightarrow$ **Branch를 `main`으로 변경** (Vercel은 이미 `main`을 바라보고 있음).
  2. 역할이 끝난 `feat/react-fastapi-migration` 브랜치를 Git과 GitHub에서 완전히 삭제.
* **최종 브랜치 구조**:
  * `main` : 프로덕션(React + FastAPI) 단일 진실 공급원(SSOT) $\rightarrow$ Render & Vercel 자동 배포.
  * `legacy/streamlit` : 과거 Streamlit 레거시 코드 영구 보존용 아카이브.
* **장점**:
  * 중복 브랜치가 사라지고 Git 히스토리가 업계 표준에 맞춰 가장 깔끔해짐.
  * 앞으로 Antigravity에서 작업하고 푸시할 때 브랜치 고민 없이 `main` 하나만 다루면 됨.

---

### 전략 B: 별도 독립 GitHub 저장소(Repository)로 분리

Streamlit 프로젝트와 React+FastAPI 프로젝트의 깃 히스토리나 저장소 자체를 완전히 섞이지 않게 떼어놓는 방식입니다.

* **구체적 실행 절차**:
  1. GitHub에 새 저장소 `portfolio-rebalancer-web` 생성.
  2. 현재의 React+FastAPI 코드를 새 저장소의 `main`에 푸시.
  3. 기존 저장소 `portfolio-rebalancer`는 Streamlit 전용 레포로 원상복구.
* **장점**: 두 프로젝트의 코드가 1%도 섞이지 않고 완전 격리됨.
* **단점**: 저장소가 2개로 나뉘어 관리해야 함.

---

### 전략 C: `develop` & `main` 2중 브랜치 체제 (Git Flow)

* `main` : 상용 서비스(Production) 배포 브랜치 (Vercel & Render 연결)
* `develop` : 일상적인 개발 및 기능 추가 작업 브랜치
* **장점**: 개발 중인 불안정한 코드가 라이브 서버에 바로 배포되는 것을 방지.
* **단점**: 1인 프로젝트에는 다소 무겁고 매번 머지 작업이 필요함.

---

## 🎯 3. 최종 권장 조치 (Next Steps)

다음 작업 시점에 **[전략 A]**를 적용하여:
1. Render의 배포 브랜치를 `main`으로 클릭 한 번으로 변경
2. `feat/react-fastapi-migration` 브랜치를 안전하게 삭제(Prune)

위 2단계만 진행하시면 가장 이상적이고 표준적인 Git 브랜치 아키텍처가 완성됩니다.
