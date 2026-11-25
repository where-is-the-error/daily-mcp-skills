# 인스타 캡션 — Day 07 · migrate-guard

## 본문 (복사용)

`ALTER TABLE` 한 줄이 **12분 동안** 서비스를 멈춥니다.

리뷰는 통과했습니다. 바꾸려는 것도 맞습니다 — `payload` 를 `text` 에서 `jsonb` 로.
문제는 그 표가 **4,200만 행**이고, 파일 전체가 `BEGIN … COMMIT` 하나로 묶여 있다는 것입니다.

`ACCESS EXCLUSIVE` 락은 그 표의 **SELECT 까지** 줄 세웁니다. 700초 동안.
뒤에 있는 "짧은" DDL 들도 앞 문장이 잡은 락이 풀리기 전까지 같이 기다립니다.

실제로 돌려 봤습니다 — **판정 보류 · 치명 3 · 심각 8 · 락 유지 합계 13분**

1. `ALTER TABLE events ALTER COLUMN payload TYPE jsonb USING payload::jsonb` — 42,000,000행 재작성 · 약 12분
2. `ALTER TABLE users ALTER COLUMN phone TYPE varchar(16)` — varchar(32) 에서 줄이기 · 140만 행 재작성 + 길이 초과 시 실패
3. `UPDATE users SET last_seen_at = now()` — WHERE 없음 · 140만 행 · 이전 값 없음
4. `DROP COLUMN sessions.legacy_token` — 값이 사라짐
5. `ADD COLUMN signup_source DEFAULT md5(random()::text)` — 매 행이 다른 기본값이라 전체 재작성
6. `CREATE INDEX` (CONCURRENTLY 아님) — 빌드가 끝날 때까지 쓰기 차단
7. `ADD CONSTRAINT … FOREIGN KEY` (NOT VALID 아님) — 두 표를 잠그고 820만 행 검증

같은 변경을 **3단계**로 다시 썼습니다 (도구가 만든 결과가 그대로 파일로 저장됩니다)
· 1단계 지금 — 기본값 없이 컬럼 추가, `CREATE INDEX CONCURRENTLY`, `NOT VALID` 로 제약만 걸기
· 2단계 백필 — 5,000행씩, 트랜잭션 밖에서
· 3단계 다음 배포 — `CHECK → VALIDATE → SET NOT NULL`, 이름 바꿔 둔 컬럼 정리

결과: **치명 3 → 0 · 심각 8 → 0 · 락 유지 13분 → 0.02초 · 판정 보류 → 통과**

오늘의 조합
· DBHub (MIT) — 툴 2개에 정의 261토큰, 읽기 전용·행 제한·타임아웃 가드레일. "작게, 그리고 막아라"
· Postgres MCP Pro (MIT) — 스키마를 먼저 읽고 묻기, explain, restricted/unrestricted 접근 모드
둘 다 DB에 붙어 쿼리를 실행하는 서버입니다. 이 도구는 반대로 **실행하지 않고 읽습니다** — 마이그레이션 파일과 기준 스키마만 있으면 됩니다. 코드는 한 줄도 복사하지 않았고, 툴 수는 14 → 9.

migrate-guard 가 하는 일
· 문장 나누기 — 주석·문자열·`$$ … $$` 안의 세미콜론은 문장을 끊지 않습니다
· 락 — 문장마다 PostgreSQL 락 모드, 무엇이 막히는지(읽기까지/쓰기만), 예상 유지 시간
· 재작성 — `varchar(32)→text` 는 메타데이터만, `varchar(32)→varchar(16)` 은 재작성 + 실패 위험
· 되돌리기 SQL — 역순으로, `DROP COLUMN` 은 "스키마만 복원, 값은 없음" 이라고 적습니다
· 3단계 다시 쓰기 · 스키마 변화 · CI 게이트(`--fail-on 치명` → exit 2)

검증한 것
· 테스트 **322개** (문장 나누기 31 · 타입/락 38 · 스키마 53 · 분류 51 · 규칙 51 · 단계 30 · 되돌리기 21 · 비교 8 · CLI 22 · MCP 17)
· 실제 공개 마이그레이션 **241개 파일 · 612문장** (mattermost) — 예외 0, 분류 밖 0
· 진짜 DB 카탈로그 대조 (SQLite `PRAGMA`) — 표 4 · 컬럼 20 · 인덱스 2, 불일치 0

정직하게: 실행 시간은 **실측이 아니라 모델**입니다(재작성 6만 행/초 가정). 지금 잡혀 있는 락, 복제 지연, 데이터 값의 분포는 판정하지 않습니다. 모르는 것은 결과에 그렇게 적습니다.
그리고 3단계로 나눠도 **값이 사라지는 변경은 그대로 사라집니다** — 백업 이야기를 숨기지 않습니다.

코드·README·릴스 전부 매일 올라갑니다.
github.com/where-is-the-error/daily-mcp-skills

#PostgreSQL #DB #마이그레이션 #DevOps #백엔드 #MCP #ModelContextProtocol #개발자 #사이드프로젝트 #1일1스킬 #SQL #성능 #무중단배포 #코딩공부 #삐에로개발자

---

## 짧은 버전 (스레드/릴스 첫 줄용)

`ALTER TABLE` 한 줄이 12분 동안 서비스를 멈춥니다.
4,200만 행 재작성 · ACCESS EXCLUSIVE · BEGIN 안이라 끝까지.
문장마다 락과 비용을 계산하고, 3단계(확장→백필→전환)로 다시 씁니다.
치명 3 → 0 · 심각 8 → 0 · 락 13분 → 0.02초.
오늘의 조합은 DBHub × Postgres MCP Pro.

## 해시태그만

#PostgreSQL #DB #마이그레이션 #DevOps #백엔드 #MCP #ModelContextProtocol #개발자 #사이드프로젝트 #1일1스킬 #SQL #성능 #무중단배포 #코딩공부 #삐에로개발자

## 업로드 체크리스트

- [ ] `reels-day07.mp4` — 1080×1920 · 21.5초 · H.264 High + AAC 48kHz 스테레오 · 1.85MB
- [ ] 커버: `reels-day07-poster.png` (첫 프레임 대신 커버로 지정)
- [ ] 문구가 모두 y 390~1220 안에 있는지 확인 (상단 20%·하단 35%·우측 버튼 영역 비움)
- [ ] 캡션 첫 두 줄이 훅 — 미리보기에서 잘리지 않는지 확인
- [ ] 링크는 프로필로 (본문 URL 은 눌리지 않음)
- [ ] 오디오 저작권: `reels/build_audio.py` 로 직접 합성한 트랙 (외부 음원 없음)
- [ ] 예제 값은 전부 예제입니다 — 실제 고객 데이터·회사 스키마를 쓰지 않았는지 확인
