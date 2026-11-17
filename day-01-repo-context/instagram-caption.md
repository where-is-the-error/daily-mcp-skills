# 인스타 릴스 캡션 — Day 01

- 영상: `reels-day01.mp4` (1080×1920 · 21.6초 · 무음 → 인스타에서 음원 추가)
- 커버: `reels-day01-poster.png`

---

## 본문 (복사해서 붙여넣기)

Filesystem MCP + Git MCP 섞었더니? 🔀

공개 MCP 두 개를 그대로 쓰면 툴이 29개가 됩니다.
에이전트는 툴 목록만 읽다가 지치고, 파일은 최근에 뭐가 바뀐 건지 모르고,
git은 그 파일 안에 뭐가 들었는지 모릅니다.

그래서 둘을 **파일 경로** 하나로 붙였습니다.

· git 이력이 → 지금 중요한 파일을 정하고
· 샌드박스가 → 그 파일 안을 읽어 심볼·TODO로 요약하고
· 토큰 예산이 → 얼마나 넘길지 정합니다

결과는 4개 툴짜리 MCP 하나 👇
1️⃣ repo_overview — 브랜치·커밋·구조 한눈에
2️⃣ recent_changes — 최근 커밋 + 안 커밋된 변경
3️⃣ file_outline — 클래스·함수 + 줄 번호 (Python은 AST)
4️⃣ context_pack — 1,200토큰 예산 맥락 팩

보안은 원본 filesystem MCP의 규칙을 그대로 가져왔습니다.
`..`·심링크·절대경로는 거부, git은 commit/add/reset 같은 쓰기 툴 자체를 뺐고,
`.env` · `*.pem`은 목록에도 내용도 올리지 않습니다.

버린 것: write/edit/commit/reset 툴 25개
가져온 것: 경로 샌드박스 + 이력 읽기

💡 활용 팁
코딩 시작 전에 context_pack 한 번 → 파일은 file_outline으로 좁히면 토큰이 남습니다.

코드·README·테스트 40개·영상 생성 스크립트까지 저장소에 있어요.
👉 github.com/where-is-the-error/daily-mcp-skills

매일 공개 MCP 2개를 섞어 1개씩 올립니다. Day 02는 뭘 섞을까요?

---

## 해시태그

#1일1스킬 #MCP #ModelContextProtocol #AI에이전트 #ClaudeCode #Cursor #오픈소스 #파이썬 #개발자 #개발자브랜딩 #사이드프로젝트 #깃허브 #GitHub #코딩스타그램 #개발공부

---

## 대체 텍스트(alt text, 선택)

Filesystem MCP와 Git MCP를 섞어 만든 repo-context MCP 소개 릴스. 29개 툴이 4개로 줄고,
토큰 예산 1,200 안에서 저장소 맥락 팩을 만드는 과정을 보여 줍니다.

## 첫 댓글(선택)

명령어 한 줄로 바로 써볼 수 있어요 👇
`pip install -e ".[dev]" && repo-context --root . pack . --max-tokens 900`

## 업로드 체크리스트

- [ ] 오디오: 인스타 인기 음원 추가(무음 mp4이므로 필수)
- [ ] 커버: `reels-day01-poster.png` 선택
- [ ] 위치·태그: 선택
- [ ] 저장소 링크는 프로필 링크 또는 첫 댓글에 (본문 링크는 클릭 불가)
