# web-memo · 실제 실행 결과

명령과 출력을 그대로 옮겼습니다. 두 종류의 페이지를 씁니다.

- **로컬 픽스처** — 60개 버전 항목이 든 변경 이력 페이지(`http://127.0.0.1:8938/index.html`). 로컬 서버라 CLI의 `--allow-private`로 사설망 차단을 푼 상태입니다. "바뀐 뒤"는 파일에서 두 줄을 고치고 한 줄을 추가한 시점입니다.
- **실제 웹** — `docs.python.org` (robots.txt 허용, 6,000자 상한).

## 1. 처음 상태

```console
$ web-memo overview
# web-memo · overview
- 기억한 페이지 0개 · 스냅샷 0개 · 바뀐 적 있는 페이지 0개
- 스냅샷 본문 합계 추정 0 토큰
- 기억 그래프: 엔티티 0 · 관찰 0 · 관계 0

아직 기억한 페이지가 없습니다. `remember_page(url="...")`로 시작하세요.
```

## 2. 페이지를 처음 기억한다 — 1,867 토큰짜리 변경 이력

```console
$ web-memo remember http://127.0.0.1:8938/index.html
# web-memo · PayFlow API 변경 이력
> `http://127.0.0.1:8938/index.html`
- 상태: 새로 기억함 · 첫 스냅샷
- 본문 3,229자 · 추정 1,867 토큰 · 스냅샷 #1 (2026-11-18 11:41)
- robots: robots.txt 허용
- 이 페이지를 처음 기억했습니다. 다음에 다시 부르면 바뀐 줄만 돌려줍니다.

## 앞부분
> 변경 이력
> PayFlow API의 버전별 변경 사항입니다. 하위 호환되지 않는 변경은 굵게 표시합니다.
> v2.60.0 — 결제 API 응답 필드 정리, 재시도 정책 문서화, 오류 코드 460 정비
- 기억 중인 페이지 1개

## 다음
- 바뀐 기록을 다시 보려면 `page_changes(url="http://127.0.0.1:8938/index.html")`
- 이 페이지에 메모를 달려면 `annotate(target="http://127.0.0.1:8938/index.html", note="...")`
```

## 3. 같은 내용으로 다시 부르면 — 저장도, 긴 응답도 없다

```console
$ web-memo remember http://127.0.0.1:8938/index.html    # 한 번 더 (내용 동일)
# web-memo · PayFlow API 변경 이력
> `http://127.0.0.1:8938/index.html`
- 상태: 변경 없음 · 스냅샷을 늘리지 않았습니다
- 본문 3,229자 · 추정 1,867 토큰 · 스냅샷 #1 (2026-11-18 11:41)
- robots: robots.txt 허용
- 같은 내용이라 이번엔 아무것도 저장하지 않았습니다 (이 페이지 본문 1,867 토큰을 다시 넘기지 않아도 됩니다)
- 기억 중인 페이지 1개

## 다음
- 바뀐 기록을 다시 보려면 `page_changes(url="http://127.0.0.1:8938/index.html")`
- 이 페이지에 메모를 달려면 `annotate(target="http://127.0.0.1:8938/index.html", note="...")`
```

## 4. 두 줄이 바뀌고 한 줄이 늘어난 뒤

```console
$ web-memo remember http://127.0.0.1:8938/index.html    # 요금·버전이 바뀐 뒤
# web-memo · PayFlow API 변경 이력
> `http://127.0.0.1:8938/index.html`
- 상태: 변경됨 · +4줄 / -2줄
- 본문 3,287자 · 추정 1,903 토큰 · 스냅샷 #2 (2026-11-18 11:41)
- robots: robots.txt 허용
- 이번 응답은 바뀐 부분만: 약 298 토큰 (전체 1,903 토큰 대신 1,605 토큰 절약)

## 바뀐 부분
```diff
@@ -2,4 +2,6 @@
  
  PayFlow API의 버전별 변경 사항입니다. 하위 호환되지 않는 변경은 굵게 표시합니다.
+ 
+ v2.4.0 — 연간 결제 플랜 추가, 세금 계산 API 신설, 정산 리포트 필드 3종 추가
  
  v2.60.0 — 결제 API 응답 필드 정리, 재시도 정책 문서화, 오류 코드 460 정비
@@ -117,7 +119,7 @@
  v2.4.0 — 결제 API 응답 필드 정리, 재시도 정책 문서화, 오류 코드 404 정비
  
- v2.3.0 — 결제 API 응답 필드 정리, 재시도 정책 문서화, 오류 코드 403 정비
+ v2.3.1 — 결제 API 응답 필드 정리(핫픽스), 재시도 정책 문서화, 오류 코드 403 정비
  
  v2.2.0 — 결제 API 응답 필드 정리, 재시도 정책 문서화, 오류 코드 402 정비
  
- v2.1.0 — 결제 API 응답 필드 정리, 재시도 정책 문서화, 오류 코드 401 정비
+ v2.1.1 — 결제 API 응답 필드 정리, 재시도 정책 문서화, 오류 코드 401 정비
```
- 기억 중인 페이지 1개

## 다음
- 바뀐 기록을 다시 보려면 `page_changes(url="http://127.0.0.1:8938/index.html")`
- 이 페이지에 메모를 달려면 `annotate(target="http://127.0.0.1:8938/index.html", note="...")`
```

## 5. 나중에 다시 차이만 보고 싶을 때 (네트워크 0회)

```console
$ web-memo changes http://127.0.0.1:8938/index.html
# web-memo · page_changes
> `http://127.0.0.1:8938/index.html`
- 비교: 스냅샷 #1 (2026-11-18 11:41) → #2 (2026-11-18 11:41)
- +4줄 / -2줄 · 바뀐 부분만 211 토큰

## 차이
```diff
@@ -3,2 +3,4 @@
  PayFlow API의 버전별 변경 사항입니다. 하위 호환되지 않는 변경은 굵게 표시합니다.
+ 
+ v2.4.0 — 연간 결제 플랜 추가, 세금 계산 API 신설, 정산 리포트 필드 3종 추가
  
@@ -118,3 +120,3 @@
  
- v2.3.0 — 결제 API 응답 필드 정리, 재시도 정책 문서화, 오류 코드 403 정비
+ v2.3.1 — 결제 API 응답 필드 정리(핫픽스), 재시도 정책 문서화, 오류 코드 403 정비
  
@@ -122,2 +124,2 @@
  
- v2.1.0 — 결제 API 응답 필드 정리, 재시도 정책 문서화, 오류 코드 401 정비
+ v2.1.1 — 결제 API 응답 필드 정리, 재시도 정책 문서화, 오류 코드 401 정비
```
```

## 6. 메모·태그와 검색

```console
$ web-memo note http://127.0.0.1:8938/index.html "연간 결제 조항 신설 — 요금표 다시 봐야 함" --tags pricing,docs
# web-memo · annotate
> `http://127.0.0.1:8938/index.html`
- 기억에 새 엔티티를 만들었습니다.
- 메모를 한 줄 남겼습니다.
- 태그: #pricing, #docs

## 이 대상에 쌓인 메모
- 연간 결제 조항 신설 — 요금표 다시 봐야 함  (2026-11-18 11:41)
```

```console
$ web-memo recall 연간
# web-memo · recall
> `연간` · 기억 1개 중 1건

## 1. PayFlow API 변경 이력  ── 페이지 · 점수 6
- `http://127.0.0.1:8938/index.html`
- 걸린 곳: body, note
- 마지막 확인: 2026-11-18 11:41 · 1,903 토큰
- 메모: 연간 결제 조항 신설 — 요금표 다시 봐야 함
> 변경 이력  PayFlow API의 버전별 변경 사항입니다. 하위 호환되지 않는 변경은 굵게 표시합니다.  v2.4.0 — 연간 결제 플랜 추가, 세금 계산 API 신설, 정산 리포트 필드 3종 추가  v2.60.0 — 결제 API 응답 필드 정리, 재시도 정책…
```

## 7. 현황

```console
$ web-memo overview
# web-memo · overview
- 기억한 페이지 1개 · 스냅샷 2개 · 바뀐 적 있는 페이지 1개
- 스냅샷 본문 합계 추정 3,770 토큰
- 기억 그래프: 엔티티 3 · 관찰 1 · 관계 4

## 최근 확인한 페이지
- PayFlow API 변경 이력
  `http://127.0.0.1:8938/index.html` — 2026-11-18 11:41 · 확인 3회 · 바뀐 적 있음 · 스냅샷 2개
```

## 8. robots.txt가 막은 경로

```console
$ web-memo remember http://127.0.0.1:8938/admin/secret
⚠️ robots.txt 가 이 경로를 막습니다 — http://127.0.0.1:8938/admin/secret
```

## 9. 실제 웹 페이지 (docs.python.org)

```console
$ web-memo remember https://docs.python.org/3/library/asyncio-task.html --max-chars 6000
# web-memo · Coroutines and tasks — Python 3.15.2 documentation
> `https://docs.python.org/3/library/asyncio-task.html`
- 상태: 새로 기억함 · 첫 스냅샷
- 본문 6,013자 · 추정 1,525 토큰 · 스냅샷 #1 (2026-11-18 11:41)
- robots: robots.txt 허용
- 이 페이지를 처음 기억했습니다. 다음에 다시 부르면 바뀐 줄만 돌려줍니다.

## 앞부분
> Coroutines and tasks¶
> This section outlines high-level asyncio APIs to work with coroutines

$ web-memo remember https://docs.python.org/3/library/asyncio-task.html --max-chars 6000   # 두 번째
# web-memo · Coroutines and tasks — Python 3.15.2 documentation
> `https://docs.python.org/3/library/asyncio-task.html`
- 상태: 변경 없음 · 스냅샷을 늘리지 않았습니다
- 본문 6,013자 · 추정 1,525 토큰 · 스냅샷 #1 (2026-11-18 11:41)
- robots: robots.txt 허용
- 같은 내용이라 이번엔 아무것도 저장하지 않았습니다 (이 페이지 본문 1,525 토큰을 다시 넘기지 않아도 됩니다)
- 기억 중인 페이지 1개
```

> 토큰 수는 추정치입니다(ASCII 4자 ≈ 1토큰, 그 외 1자 ≈ 1토큰).
