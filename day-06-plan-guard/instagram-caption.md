# 인스타 캡션 — Day 06 · plan-guard

## 본문 (복사용)

`terraform plan` 이 "2 to add, 3 to change, **2 to destroy**" 라고 말합니다.
그 두 개가 뭔지는 말해 주지 않습니다.

일부러 위험한 plan 을 하나 만들었습니다. AWS provider 로 실제 `terraform plan` 을 돌려서요.
(예제 비밀번호 하나가 plan 파일 안에서 평문으로 **5곳**에 나왔습니다.)

돌려 보니 — **판정 보류 · 치명 4 · 심각 2**

1. `22/tcp 0.0.0.0/0` — SSH 를 인터넷에 열었습니다 (출처: 10.0.0.0/8 → 0.0.0.0/0)
2. `storage_encrypted: false → true` — **DB 가 재생성됩니다.** 암호화 켜려다 데이터를 잃는 자리
3. `acl: private → public-read` — 버킷이 공개로
4. IAM 정책에 `Action: "*"` 가 새로 들어감
5. `aws_instance.worker` 삭제 + `skip_final_snapshot = true` — 스냅샷 없이 사라짐

같은 state 로 "고친 plan" 을 다시 만들었습니다 → **치명 4 → 0, 사라지는 리소스 2 → 0, 판정 통과**

오늘의 조합
· HashiCorp 공식 `terraform-mcp-server` (MPL-2.0) — 문서를 통째로 주지 않고 **주소 하나로 좁혀** 보여 주는 방식
· AWS Labs `aws-iac-mcp-server` (Apache-2.0) — 배포 실패를 **30여 가지 패턴으로 분류**하듯 사유를 라벨로, best practice 를 "고치기" 문장으로
코드는 한 줄도 복사하지 않고 설계와 태도만 가져와 9개 툴로 다시 만들었습니다.

plan-guard 가 하는 일
· 목록 안쪽까지 diff — `ingress[tcp/22-22].cidr_blocks[0]: 10.0.0.0/8 → 0.0.0.0/0` (순서가 바뀌어도 22번만)
· 순서 — 지우려는 걸 아직 참조하는 리소스가 있으면 apply 가 막힙니다
· 되돌리기 — apply 전 state 백업, DB 스냅샷 명령, 되돌릴 값
· `redact` — 공유 전에 비밀번호를 «민감» 으로 (terraform 은 표시만 하고 지우지 않습니다)
· CI 게이트 — `--fail-on 치명` 이면 **exit 2**

정직하게: 비용·apply 결과·drift·처음 보는 리소스 타입은 **판정하지 않습니다**고 결과에 적습니다.

terraform 은 원본 도구의 몫으로 두고, **만들어진 plan 을 사람이 읽는 자리**만 맡았습니다.
테스트 242개. 코드·README·릴스 전부 매일 올라갑니다.
github.com/where-is-the-error/daily-mcp-skills

#Terraform #IaC #DevOps #인프라 #MCP #ModelContextProtocol #개발자 #사이드프로젝트 #1일1스킬 #AWS #보안 #클라우드 #코딩공부 #동양미래대학교 #삐에로개발자

---

## 짧은 버전 (스레드/릴스 첫 줄용)

`2 to destroy` 가 뭔지는 plan 이 말해 주지 않습니다.
plan.json 하나로 — 사라지는 리소스 · 열린 포트 · 되돌리기까지.
오늘의 조합은 Terraform MCP × AWS IaC MCP. 치명 4 → 0, 고친 plan 은 통과.

## 해시태그만

#Terraform #IaC #DevOps #인프라 #MCP #ModelContextProtocol #개발자 #사이드프로젝트 #1일1스킬 #AWS #보안 #클라우드 #코딩공부 #동양미래대학교 #삐에로개발자

## 업로드 체크리스트

- [ ] `reels-day06.mp4` — 1080×1920 · 21.5초 · H.264 High + AAC 48kHz 스테레오 · 1.93MB
- [ ] 커버: `reels-day06-poster.png` (첫 프레임 대신 커버로 지정)
- [ ] 문구가 모두 y 390~1220 안에 있는지 확인 (상단 20%·하단 35%·우측 버튼 영역 비움)
- [ ] 캡션 첫 두 줄이 훅 — 미리보기에서 잘리지 않는지 확인
- [ ] 링크는 프로필로 (본문 URL 은 눌리지 않음)
- [ ] 오디오 저작권: `reels/build_audio.py` 로 직접 합성한 트랙 (외부 음원 없음)
- [ ] 캡션에 실제 비밀번호 예제 값을 쓰지 않았는지 확인 (`correcthorsebatterystaple` 은 plan 파일 안에만)
