# 투자 실행 운영 반영 안내

2026년 10월 10일. 개발 기준 main 1b5aeea, 작업 브랜치 codex/investment-execution.
이 문서는 준비된 절차다. 운영 점검·백업·DB 변경·병합/push·배포는 아직 실행하지 않았다.

## 변경과 유지 사항

- 새 화면: 8. 투자 실행. 4번 저장 계획에서 시작하고 5번과 공통 장부 입력을 사용한다.
- 추가 DB: 비공개 portfolio_execution 스키마의 cycles, steps, attempts, results, record_links 5개 테이블과 인덱스.
- 초기화: 기존 init_db의 같은 트랜잭션에서 추가 구조와 RLS/권한 차단을 반복 적용한다. 직접 실행할 중복 DDL 파일은 만들지 않았다. 기준 소스는 data/investment_schema.py다.
- 기존 public 20개 장부, portfolio_security.migrations의 보안 스냅샷/버전, 로그인·세션·외부 시세·종가 작업은 유지한다.
- 실제 증권사 주문·이체·환전은 하지 않는다. 새 증권사 키나 예약 실행 서버를 추가하지 않는다.
- Python 3.12.8, Node 24, 기존 빌드/시작 명령과 런타임 의존성은 바꾸지 않는다. 새 필수 환경변수는 없다.

## 적용 전에 확인

1. 사용자 최종 검토와 main 병합·origin push 승인을 확인한다. Vercel은 push로 자동 배포되고 Render는 수동 배포한다.
2. 이전 정상 배포 SHA를 Render·Vercel 양쪽에서 기록한다. 현재 실제 배포 SHA를 로컬 main의 SHA로 추정하지 않는다.
3. 운영 기록 입력을 잠시 중단하고 저장 확인 중인 요청을 먼저 확정한다. 이후 최신 백업과 배포 사이에 기록이 추가됐다면 그 기록도 따로 보호한다.
4. 운영 관리용 세션 연결로 scripts/sql/investment_execution_preflight.sql을 읽기 전용으로 실행한다. 연결값을 출력하거나 채팅에 붙이지 않는다. 자산 행을 읽는 SQL이 아니다.
5. Supabase Data API 꺼짐, Render의 APP_PASSWORD·APP_SESSION_SECRET 및 PORTFOLIO_DB_SECURITY_ENABLED=1을 유지한다. 값은 다시 요청하거나 변경할 필요가 없다.
6. 기존 scripts/backup_database.py로 새 백업을 만든다. PostgreSQL 17 pg_dump와 승인된 비공개 설정을 사용하며 로그에는 연결 문자열을 출력하지 않는다.

백업 실행 예시는 다음과 같다. 운영 접근 승인 뒤 실행하며 이번 로컬 개발에서는 실행하지 않았다.

    python scripts/backup_database.py --pg-bin .\backups\local_validation\pgsql\bin

완료된 archive의 크기·SHA-256과 생성 시각, pg_dump 정상 종료를 확인한다. Supabase Free Plan의 자동 백업을 전제하지 않는다. 백업은 ignored backups 아래에 두고 git에 추가하거나 공개하지 않는다. 전체 논리 백업에는 추가 스키마도 포함된다. 실제 운영 백업을 따로 복원 시험하지 않은 경우 이를 명확하게 기록한다. 이번 검증의 복원 성공은 합성 데이터에 한정한다.

## 사전 메타데이터의 성공 조건

| 항목 | 기대 상태 |
| --- | --- |
| 앱 역할 | 기존 확인된 postgres 연결 역할. 풀러의 postgres.프로젝트ID 사용자명과 실제 current_user를 구분 |
| public 장부 | 기존 20개, 기존 소유권·RLS/권한 차단 유지 |
| 기존 보안 스냅샷 | portfolio_security.migrations 존재, 기존 변경 버전 유지 |
| 최초 추가 스키마 | 아직 없어도 정상. 없으면 실제 앱 역할에 현재 DB의 CREATE 권한 필요 |
| 이미 존재하는 추가 스키마 | 소유자가 실제 앱 역할과 같아야 함 |
| 추가 테이블 | 적용 후 5개 모두 RLS 활성, FORCE RLS 없음, 허용 정책 없음 |
| 공개 접근 | PUBLIC·anon·authenticated·service_role의 schema USAGE/CREATE 및 테이블·컬럼 접근 없음 |
| 다른 역할 | 소유자 이외의 예상하지 않은 권한이 있으면 별도 조사 |

권한이 없으면 런타임 역할의 권한을 자동 확대하지 않는다. 사용자 승인된 관리 역할로 추가 스키마를 생성하고 앱 역할에 소유권을 맞추는 방안을 먼저 확인한다. 그 승인/준비가 끝나기 전에는 새 백엔드를 배포하지 않는다. 새 스키마의 임의 GRANT나 전체 허용 RLS 정책으로 오류를 해결하지 않는다.

이번 로컬 검증에서는 비슈퍼유저 소유자/BYPASSRLS 역할의 정상 입력·취소·초기화를 확인했다. 소유자 또는 BYPASSRLS 역할의 접근 특성과 API 역할의 권한 차단은 [Supabase RLS 안내](https://supabase.com/docs/guides/database/postgres/row-level-security)에 근거한다.


## 실제 적용 순서

1. 최신 백업과 사전 메타데이터 확인을 완료한다.
2. 승인된 개발 브랜치를 main에 병합하고 origin에 push한다. 최종 커밋 SHA를 사용자에게 전달한다.
3. Vercel 자동 Production 배포가 해당 SHA로 Ready인지 확인한다. Render가 아직 이전 코드이면 8번만 준비 안내가 나오며 기존 5번 독립 입력을 사용할 수 있다. 투자에 연결된 미확정 요청을 임의로 연결 해제하거나 새 요청으로 바꾸지 않는다.
4. 사용자가 Render에서 Manual Deploy → Deploy latest commit을 실행한다. 시작 시 추가 스키마·RLS·권한 차단을 같은 DB 트랜잭션에 적용한다.
5. Render가 Live가 되고 정상 시작 로그가 확인되면 사전 SQL을 다시 실행해 적용 후 5개 테이블·소유권·RLS·권한을 확인한다. Data API는 계속 꺼둔다.
6. 로그인·1번 자산 조회·기존 5번 기록 조회·4번 계획 조회·7번 성과/종가 기능·8번 지원 버전을 확인한다.
7. 운영에서 주문·이체·환전을 시험 목적으로 만들지 않는다. 장부 변경 없이 8번 준비 안내를 확인하고, 첫 실제 투자 때 이미 실행한 금융 기록만 입력해 기존 현황과 함께 확인한다.

다음 설정은 유지한다.

- Render: 기존 SUPABASE_URL, APP_PASSWORD, APP_SESSION_SECRET, PORTFOLIO_DB_SECURITY_ENABLED=1, 기존 종가 스케줄러 설정.
- Vercel: 기존 VITE_API_BASE_URL, frontend 루트, npm run build, dist 출력.
- Supabase: Data API 꺼짐. 공개 정책이나 광범위한 역할 권한을 추가하지 않는다.

## 성공 기준과 확인 한계

| 확인 | 기준 |
| --- | --- |
| 비인가 HTTP | 투자 생성/조회/변경/연결 등 모든 경로에 인증 없이 접근하면 401 |
| 공개 DB 역할 | 추가 스키마·테이블 읽기/쓰기가 권한 오류로 차단됨 |
| 정상 기능 | 기존 로그인·자산·장부·성과 조회와 입력 경로 유지 |
| 준비/목표/종료 | 그 자체로 잔고·수량·원가·성과를 변경하지 않음 |
| 실제 기록 | 5번·8번 같은 공통 경로로 저장되고 다른 화면에 반영 |
| 재시도 | 저장 여부가 불명확하면 같은 요청을 보존하고 중복 금융 반영 없음 |
| 취소 | 원본 기록 취소 후 8번 진행도 재계산, 자동 재주문 없음 |

운영 경로의 비인가 접근 점검은 별도 승인된 무인증 요청으로 할 수 있으며 실제 자산을 조회하지 않아야 한다. SQL 점검은 메타데이터에 한정한다. 정상 금융 입력은 첫 실제 거래 시 사용자가 확인하며, 운영 시험 데이터를 만들거나 무단으로 실제 기록을 취소하지 않는다.

실제 휴대폰과 운영 Supabase/Render/Vercel은 로컬 테스트와 같다고 단정할 수 없다. 운영 적용 완료는 위 확인이 끝난 뒤에만 보고한다.

## 장애 대응과 롤백

- 시작 권한/소유권 오류: 권한을 넓히거나 RLS를 끄지 말고 이전 정상 Render 배포를 유지/복원한다. 실패한 초기화 트랜잭션이 부분 반영되지 않았는지 메타데이터로 확인한다.
- 백엔드 문제: 이전 정상 Render 커밋으로 Rollback한다. 새 프런트엔드를 유지하면 새 투자 API 지원 여부를 보고 8번과 연결된 요청만 차단하고 5번 독립 입력은 유지한다.
- 프런트엔드 문제: 필요할 때 이전 정상 Vercel 배포를 Promote to Production한다. 확인 중인 금융 요청이 있다면 내용과 식별자를 보존하고 구버전 폼에서 새 요청으로 다시 입력하지 않는다. 새 버전에서 동일 요청 결과를 먼저 확인한다.
- 추가 테이블·투자 결과·실제 장부·보안 스냅샷은 삭제하지 않는다. 코드 롤백은 실제 거래를 취소하지 않는다.
- 구버전으로 돌아간 동안 신규 투자에 사용한 원본 계획의 링크를 임의로 편집/해제하지 않는다. 구버전은 새 투자 연결 구조를 알지 못한다. 새 버전 복구 후 연결 상태를 다시 검증한다.
- 거래가 잘못 기록됐다면 기존 5번의 취소·정정을 사용한다. 투자 연결 해제나 과정 종료로 잔고를 되돌리지 않는다.

DB 전체 복원은 코드 롤백과 다르다. 백업 이후의 정상 금융 기록까지 덮어쓸 수 있으므로 일반적인 앱 오류에서는 전체 복원을 먼저 선택하지 않는다. 복원이 필요한 손상이 확인되면 서버 쓰기를 중단하고 최근 기록을 보존한 뒤, 승인된 별도 환경에 archive를 먼저 복원·검증한다. 실제 운영 복원에는 별도의 최종 승인이 필요하다.

합성 검증은 변경 전/후 custom-format archive를 새 DB에 pg_restore로 복원해 모든 장부·투자 테이블의 행 해시, 연결, 종료 보고서, 접근 차단을 비교했다. 실제 운영 archive와 소유권/역할은 별도로 확인해야 한다. [PostgreSQL 17 pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html)와 [Supabase DB 접속 안내](https://supabase.com/docs/guides/database/connecting-to-postgres)를 참고한다.
