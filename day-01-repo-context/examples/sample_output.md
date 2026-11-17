# 샘플 출력 — 이 저장소에서 실제 실행한 결과

생성 시점: HEAD `611d149`, 커밋 6개, 2026-11-17.
이 파일 자신은 아직 커밋 전이라 `?? examples/`로 잡힙니다 — 툴이 실제로 도는 증거입니다.

## 1) `repo-context --root . overview`
```
# repo overview · `day-01-repo-context`
- 브랜치: `main`
- HEAD: `611d149` (2026-11-17) fix(day-01): TODO는 주석 안의 것만 수집, 핫 파일 섹션은 2회 이상 바뀐 파일만
- 커밋: 6개
- 커밋 안 된 변경: 1개
- 상태: `??` 1

## 상위 구조
- `README.md`
- `examples/` — 파일 1개
- `instagram-caption.md`
- `pyproject.toml`
- `reels/` — 파일 1개
- `reels-day01-poster.png`
- `reels-day01.mp4`
- `repo_context/` — 파일 8개
- `tests/` — 파일 6개

## 언어 비중 (추적 파일 기준)
- Python: 15개 (88%)
- Markdown: 2개 (12%)
```

## 2) `repo-context --root . recent --limit 5`
```
# recent changes · 최근 5개 커밋
- `611d149` 2026-11-17 · where-is-the-error — fix(day-01): TODO는 주석 안의 것만 수집, 핫 파일 섹션은 2회 이상 바뀐 파일만
  - repo_context/pack.py
- `57f3ea2` 2026-11-17 · where-is-the-error — content(day-01): 릴스 1080x1920 21.6초 + 커버 + 생성 스크립트(Pillow+ffmpeg)
  - reels-day01-poster.png
  - reels-day01.mp4
  - reels/build_reels.py
- `176a73b` 2026-11-17 · where-is-the-error — docs(day-01): README — 섞은 두 스킬 출처·라이선스·아키텍처·토큰 예산 동작·한계
  - README.md
  - instagram-caption.md
- `43a883a` 2026-11-17 · where-is-the-error — test(day-01): 40개 테스트 — 경로 탈출·비밀 파일·토큰 예산·MCP stdio 클라이언트
  - tests/conftest.py
  - tests/test_outline.py
  - tests/test_pack.py
  - tests/test_paths.py
  - tests/test_sandbox.py
  - tests/test_server.py
- `9af2adc` 2026-11-17 · where-is-the-error — feat(day-01): repo-context MCP — 샌드박스 파일 읽기 + 읽기 전용 git 이력
  - pyproject.toml
  - repo_context/__init__.py
  - repo_context/cli.py
  - repo_context/gitio.py
  - repo_context/outline.py
  - repo_context/pack.py
  - … 3개 더

## 아직 커밋되지 않은 변경
- `??` examples/
```

## 3) `repo-context --root . outline repo_context/pack.py`
```
# outline · `repo_context/pack.py` — 223줄
> 심볼 7개
- def `estimate_tokens` (L31) — Cheap, dependency-free estimate: ASCII ~4 chars/token, CJK ~1 ch
- def `_fit` (L38) — Hard guarantee: the returned text never exceeds ``max_tokens`` (
- class `HotFile` (L54)
- def `_hot_files` (L60)
- def `_todos` (L93)
- def `_header` (L118)
- def `context_pack` (L134) — A repository digest that fits a token budget, newest-and-hottest
```

## 4) `repo-context --root . pack repo_context --max-tokens 900`
```markdown
# repo-context · `day-01-repo-context` / `repo_context`
> branch `main` · HEAD `611d149` (2026-11-17) · 커밋 6개 · 변경 1개
> 마지막 커밋: fix(day-01): TODO는 주석 안의 것만 수집, 핫 파일 섹션은 2회 이상 바뀐 파일만

## 최근 커밋 (최근 6개)
- `611d149` 2026-11-17 fix(day-01): TODO는 주석 안의 것만 수집, 핫 파일 섹션은 2회 이상 바뀐 파일만  
  ↳ repo_context/pack.py
- `57f3ea2` 2026-11-17 content(day-01): 릴스 1080x1920 21.6초 + 커버 + 생성 스크립트(Pillow+ffmpeg)  
  ↳ reels-day01-poster.png, reels-day01.mp4, reels/build_reels.py
- `176a73b` 2026-11-17 docs(day-01): README — 섞은 두 스킬 출처·라이선스·아키텍처·토큰 예산 동작·한계  
  ↳ README.md, instagram-caption.md
- `43a883a` 2026-11-17 test(day-01): 40개 테스트 — 경로 탈출·비밀 파일·토큰 예산·MCP stdio 클라이언트  
  ↳ tests/conftest.py, tests/test_outline.py, tests/test_pack.py, tests/test_paths.py 외 2개
- `9af2adc` 2026-11-17 feat(day-01): repo-context MCP — 샌드박스 파일 읽기 + 읽기 전용 git 이력  
  ↳ pyproject.toml, repo_context/__init__.py, repo_context/cli.py, repo_context/gitio.py 외 5개
- `1e4c366` 2026-11-17 chore: 1일 1스킬 시리즈 저장소 시작 (README, LICENSE)

## 지금 바뀐 파일
- `??` examples/

## 핫 파일 (최근 20커밋에서 자주 바뀐 순)
### 1. `repo_context/pack.py` — 2회
- def `estimate_tokens` (L31) — Cheap, dependency-free estimate: ASCII ~4 chars/token, CJK ~1 ch
- def `_fit` (L38) — Hard guarantee: the returned text never exceeds ``max_tokens`` (
- class `HotFile` (L54)
- def `_hot_files` (L60)
- def `_todos` (L93)
- def `_header` (L118)
- def `context_pack` (L134) — A repository digest that fits a token budget, newest-and-hottest

## TODO / FIXME (소스 15개 스캔)
- `tests/conftest.py:38` TODO — 인자 파싱 추가\n    print(Greeter().hello('세상'))\n",
- `tests/test_paths.py:18` TODO — 테스트\n    pass\n", encoding="utf-8")

---
_repo-context · 추정 567 tokens / 예산 900 · 파일 20개 추적 중_
```

## 5) 같은 명령, `--max-tokens 200` (예산이 모자라면 섹션을 스스로 버립니다)
```markdown
# repo-context · `day-01-repo-context`
> branch `main` · HEAD `611d149` (2026-11-17) · 커밋 6개 · 변경 1개
> 마지막 커밋: fix(day-01): TODO는 주석 안의 것만 수집, 핫 파일 섹션은 2회 이상 바뀐 파일만

## 최근 커밋 (최근 2개)
- `611d149` 2026-11-17 fix(day-01): TODO는 주석 안의 것만 수집, 핫 파일 섹션은 2회 이상 바뀐 파일만  
  ↳ repo_context/pack.py
- `57f3ea2` 2026-11-17 content(day-01): 릴스 1080x1920 21.6초 + 커버 + 생성 스크립트(Pillow+ffmpeg)  
  ↳ reels-day01-poster.png, reels-day01.mp4, reels/build_reels.py

---
_repo-context · 추정 172 tokens / 예산 200 · 파일 20개 추적 중_
```
