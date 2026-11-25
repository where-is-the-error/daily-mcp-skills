"""선택 결과 위에 얹는 규칙 — '이 변경은 테스트 하나로 못 덮는다'를 잡는다.

규칙은 두 종류다.
  · 범위 규칙  — 선택이 성립하지 않는 변경(테스트 설정·파싱 실패·동적 import·삭제된 모듈)
  · 신호 규칙  — 테스트가 통과해도 조용히 넘어갈 수 있는 변경(테스트 약화·예외 삼킴·난수/시각)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .select import ChangeSet
from .types import Risk

SEVERITIES = ["치명", "심각", "주의", "참고"]

CALL_RE = re.compile(r"\b([A-Za-z_][\w]*)\s*\(")
ASSERT_RE = re.compile(r"^\s*(assert\b|self\.assert|expect\(|assert_)")
SKIP_RE = re.compile(r"@pytest\.mark\.(skip|xfail)|\.skip\(|test\.todo|xit\(")
ENTRYPOINT_NAMES = {"__main__", "cli", "main", "app", "manage", "wsgi", "asgi", "run", "server"}
BROAD_EXC_RE = re.compile(r"^\s*except(\s+Exception)?\s*(as\s+\w+)?\s*:")
NONDET_RE = re.compile(r"\b(time\.sleep|datetime\.now\(|datetime\.utcnow\(|random\.|uuid4\(|time\.time\()")
ENVNET_RE = re.compile(r"\b(os\.environ|getenv\(|requests\.|httpx\.|urllib\.|socket\.)")
ALWAYS_TRUE_RE = re.compile(r"^\s*if\s+True\s*:|^\s*if\s+1\s*:")


@dataclass
class Context:
    change_set: ChangeSet
    added_by_file: dict[str, list[str]] = field(default_factory=dict)
    removed_by_file: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class Rule:
    rule: str
    severity: str
    title: str
    doc: str
    check: object                      # (Context) -> list[Risk]


def _risks(rule: Rule, items: list[tuple[str, str]]) -> list[Risk]:
    return [Risk(rule=rule.rule, severity=rule.severity, title=rule.title, detail=detail, where=where)
            for where, detail in items]


# ------------------------------------------------------------------ helpers
def _production_importers(change_set: ChangeSet, path: str) -> list[str]:
    repo = change_set.repo
    return sorted(p for p in repo.importers_of(path, include_tests=False) if not repo.is_test(p))


def _symbol_names_imported_by_others(change_set: ChangeSet, module_path: str, name: str) -> list[str]:
    repo = change_set.repo
    out: list[str] = []
    for other in repo.modules.values():
        if other.path == module_path:
            continue
        names = other.imported_symbols.get(module_path, set())
        if name in names or "*" in names:
            out.append(other.path)
    return out


def _added_lines(ctx: Context, path: str) -> list[str]:
    if path in ctx.added_by_file:
        return ctx.added_by_file[path]
    return []


# -------------------------------------------------------------------- rules
def _test_config(ctx: Context) -> list[Risk]:
    sets = ctx.change_set
    items = []
    for path in sets.test_config_touched():
        detail = {
            "conftest.py": "fixture·marker·hook 가 바뀌면 어느 테스트가 영향받는지 정적으로 알 수 없습니다",
            "pyproject.toml": "pytest 설정(경로·옵션·플러그인)이 바뀌었습니다",
        }.get(Path(path).name, "테스트 실행 방식이 바뀌었습니다")
        items.append((path, detail + " → 이번에는 전체 실행이 맞습니다"))
    return _risks(RULE_MAP["test-config-changed"], items)


def _unparseable(ctx: Context) -> list[Risk]:
    items = []
    for view in ctx.change_set.views:
        module = ctx.change_set.repo.module(view.module_path) if view.module_path else None
        if module is not None and module.parse_error:
            items.append((view.change.path, module.parse_error))
    return _risks(RULE_MAP["unparseable-change"], items)


def _dynamic(ctx: Context) -> list[Risk]:
    items = []
    for view in ctx.change_set.views:
        module = ctx.change_set.repo.module(view.module_path) if view.module_path else None
        if module is not None and module.dynamic_import:
            items.append((view.change.path, "importlib/__import__/변수 require — 정적 그래프가 이 간선을 못 봅니다"))
    return _risks(RULE_MAP["dynamic-import"], items)


def _unreached(ctx: Context) -> list[Risk]:
    sets = ctx.change_set
    items = []
    for view in sets.views:
        if not view.module_path or sets.repo.is_test(view.module_path):
            continue
        if view.change.path in sets.test_config_touched():
            continue
        reaching = sets.repo.tests_reaching(view.module_path)
        if any(sel.path in reaching for sel in sets.selections.values()):
            continue
        fan = sets.repo.fan_in(view.module_path)
        items.append((view.change.path,
                      f"이 파일에 도달하는 테스트 0 · 이 파일을 import 하는 프로덕션 모듈 {fan}개"))
    return _risks(RULE_MAP["no-test-reaches"], items)


def _deleted_module(ctx: Context) -> list[Risk]:
    from . import pyast
    sets = ctx.change_set
    items = []
    for view in sets.views:
        if view.change.status != "deleted":
            continue
        old = view.change.old_path or view.change.path
        name = pyast.module_name(old, sets.repo.root, old.endswith("__init__.py"))
        importers = _production_importers(sets, old) or sorted(
            sets.repo.importers_of_name(name, include_tests=False))
        if importers:
            items.append((old, "삭제된 모듈을 아직 import: " + ", ".join(importers[:5])))
    return _risks(RULE_MAP["deleted-module-still-imported"], items)


def _renamed_stale(ctx: Context) -> list[Risk]:
    from . import pyast
    sets = ctx.change_set
    items = []
    for view in sets.views:
        if view.change.status != "renamed" or not view.change.old_path:
            continue
        name = pyast.module_name(view.change.old_path, sets.repo.root,
                                 view.change.old_path.endswith("__init__.py"))
        importers = _production_importers(sets, view.change.old_path) or sorted(
            sets.repo.importers_of_name(name, include_tests=False))
        if importers:
            items.append((view.change.old_path,
                          f"이름이 바뀐 옛 경로를 아직 import: {', '.join(importers[:5])}"))
    return _risks(RULE_MAP["renamed-module-stale-import"], items)


def _public_removed(ctx: Context) -> list[Risk]:
    sets = ctx.change_set
    items = []
    for view in sets.views:
        module = sets.repo.module(view.module_path) if view.module_path else None
        if module is None:
            continue
        for name in view.removed_defs:
            if name.startswith("_"):
                continue
            if module.symbol(name) is not None:
                continue                       # 이름은 남아 있고 본문만 바뀐 경우
            users = _symbol_names_imported_by_others(sets, view.module_path, name)
            detail = f"공개 정의 `{name}` 가 사라졌습니다"
            if users:
                detail += " · 아직 import 하는 곳: " + ", ".join(users[:5])
            items.append((view.change.path, detail))
    return _risks(RULE_MAP["public-symbol-removed"], items)


def _signature(ctx: Context) -> list[Risk]:
    items = []
    for view in ctx.change_set.views:
        for name, old, new in view.signature_changes:
            items.append((view.change.path, f"`{name}` 인자 {old} → {new}"))
    return _risks(RULE_MAP["signature-changed"], items)


def _public_without_test(ctx: Context) -> list[Risk]:
    items = []
    for gap in ctx.change_set.gaps:
        if gap.get("kind") != "unreferenced-symbol":
            continue
        items.append((f"{gap['path']}:{gap.get('line', '')}", gap["detail"]))
    return _risks(RULE_MAP["public-symbol-no-test"], items)


def _high_fan_in(ctx: Context) -> list[Risk]:
    sets = ctx.change_set
    items = []
    for view in sets.views:
        if not view.module_path or sets.repo.is_test(view.module_path):
            continue
        fan = sets.repo.fan_in(view.module_path)
        if fan >= 5:
            items.append((view.change.path, f"프로덕션 모듈 {fan}개가 이 파일을 import — 변경 파급이 넓습니다"))
    return _risks(RULE_MAP["high-fan-in"], items)


def _test_weakened(ctx: Context) -> list[Risk]:
    sets = ctx.change_set
    items = []
    for view in sets.views:
        path = view.change.path
        if path not in sets.repo.tests:
            continue
        added = _added_lines(ctx, path)
        removed = ctx.removed_by_file.get(path, [])
        add_asserts = sum(1 for line in added if ASSERT_RE.match(line))
        del_asserts = sum(1 for line in removed if ASSERT_RE.match(line))
        added_skips = [line for line in added if SKIP_RE.search(line)]
        if del_asserts > add_asserts:
            items.append((path, f"assert 줄 {del_asserts}개 삭제 · {add_asserts}개 추가 — 검사가 약해졌습니다"))
        if added_skips:
            items.append((path, f"skip/xfail 추가: {added_skips[0].strip()[:60]}"))
    return _risks(RULE_MAP["test-weakened"], items)


def _test_deleted(ctx: Context) -> list[Risk]:
    sets = ctx.change_set
    items = []
    for view in sets.views:
        if view.change.status == "deleted" and (view.change.path in sets.repo.tests or Path(view.change.path).name.startswith("test_")):
            items.append((view.change.path, "테스트 파일이 삭제되었습니다 — 대체 테스트가 있는지 확인"))
    return _risks(RULE_MAP["test-deleted"], items)


def _fixture(ctx: Context) -> list[Risk]:
    items = []
    for path in ctx.change_set.test_config_touched():
        if Path(path).name == "conftest.py":
            items.append((path, "fixture 변경 — 영향 범위를 정적으로 확정할 수 없습니다"))
    return _risks(RULE_MAP["fixture-changed"], items)


def _new_file_no_test(ctx: Context) -> list[Risk]:
    items = []
    for gap in ctx.change_set.gaps:
        if gap.get("kind") in ("new-module", "no-test"):
            items.append((gap["path"], gap["detail"]))
    return _risks(RULE_MAP["new-file-no-test"], items)


def _module_level(ctx: Context) -> list[Risk]:
    sets = ctx.change_set
    items = []
    for view in sets.views:
        module = sets.repo.module(view.module_path) if view.module_path else None
        if module is None:
            continue
        numbers = {number for number, _ in view.change.added_lines()}
        hit = sorted(numbers & module.top_level_lines)
        if hit:
            items.append((view.change.path, f"import 하는 순간 실행되는 줄 {len(hit)}개 변경 (예: {hit[0]}행)"))
    return _risks(RULE_MAP["module-level-code"], items)


def _entrypoint(ctx: Context) -> list[Risk]:
    sets = ctx.change_set
    items = []
    for view in sets.views:
        module = sets.repo.module(view.module_path) if view.module_path else None
        if module is None:
            continue
        stem = Path(view.change.path).stem
        has_main = bool(re.search(r"if\s+__name__\s*==\s*['\"]__main__['\"]", module.source))
        if has_main or stem in ENTRYPOINT_NAMES:
            items.append((view.change.path, "진입점 변경 — 단위 테스트 말고 스모크 실행이 필요"))
    return _risks(RULE_MAP["entrypoint-changed"], items)


def _broad_except(ctx: Context) -> list[Risk]:
    items = []
    for view in ctx.change_set.views:
        path = view.change.path
        added = _added_lines(ctx, path)
        hits = [line for line in added if BROAD_EXC_RE.match(line)]
        if hits:
            swallow = any(re.match(r"^\s*(pass|return\s+None|continue)\s*$", line)
                          for line in added[added.index(hits[0]) + 1: added.index(hits[0]) + 3])
            note = " 뒤에서 예외를 삼킵니다" if swallow else ""
            items.append((path, f"`{hits[0].strip()[:50]}`{note} — 실패가 테스트에서 초록으로 보일 수 있습니다"))
    return _risks(RULE_MAP["broad-except"], items)


def _nondeterminism(ctx: Context) -> list[Risk]:
    items = []
    for view in ctx.change_set.views:
        added = _added_lines(ctx, view.change.path)
        hits = sorted({match.group(1) for line in added for match in [NONDET_RE.search(line)] if match})
        if hits:
            items.append((view.change.path, "시각·난수 사용 추가: " + ", ".join(hits[:4]) + " — flaky 후보"))
    return _risks(RULE_MAP["nondeterminism"], items)


def _env_or_network(ctx: Context) -> list[Risk]:
    items = []
    for view in ctx.change_set.views:
        added = _added_lines(ctx, view.change.path)
        hits = sorted({match.group(1) for line in added for match in [ENVNET_RE.search(line)] if match})
        if hits:
            items.append((view.change.path, "환경·네트워크 의존 추가: " + ", ".join(hits[:4])))
    return _risks(RULE_MAP["env-or-network"], items)


def _too_broad(ctx: Context) -> list[Risk]:
    sets = ctx.change_set
    total = sets.total_items()
    if total >= 10 and sets.selected_items() >= total * 0.6:
        return [Risk(rule="selection-too-broad", severity="참고", title="선택이 넓음",
                     detail=f"선택 {sets.selected_items()}/{total} ({sets.share():.0%}) — 전체 실행과 비슷합니다",
                     where="")]
    return []


def _no_tests(ctx: Context) -> list[Risk]:
    if ctx.change_set.repo.tests:
        return []
    return [Risk(rule="no-tests-in-repo", severity="치명", title="테스트 없음",
                 detail="이 저장소에서 테스트 파일을 찾지 못했습니다 — 선택할 대상이 없습니다", where="")]


def _broad_test(ctx: Context) -> list[Risk]:
    """선택된 테스트 중 저장소 모듈을 넓게 import 하는 파일 — 통합 성격이라 보통 느리다."""
    sets = ctx.change_set
    items = []
    for path in sets.selections:
        test = sets.repo.test(path)
        if test is None or test.is_conftest:
            continue
        modules = [target for target in test.resolved if not sets.repo.is_test(target)]
        if len(modules) >= 8:
            items.append((path, f"저장소 모듈 {len(modules)}개를 import — 통합 테스트, 시간이 안 줄 수 있습니다"))
    return _risks(RULE_MAP["broad-test"], items)


def _always_true(ctx: Context) -> list[Risk]:
    items = []
    for view in ctx.change_set.views:
        for line in _added_lines(ctx, view.change.path):
            if ALWAYS_TRUE_RE.match(line):
                items.append((view.change.path, f"`{line.strip()}` — 조건이 상수입니다"))
                break
    return _risks(RULE_MAP["constant-condition"], items)


RULES: list[Rule] = [
    Rule("test-config-changed", "치명", "테스트 설정 변경",
         "pytest.ini·conftest.py·pyproject 의 pytest 설정이 바뀌면 어느 테스트가 영향받는지 정적으로 알 수 없다. 전체 실행.", _test_config),
    Rule("unparseable-change", "치명", "바뀐 파일을 읽지 못함",
         "문법 오류·인코딩 문제로 파일을 파싱하지 못하면 import 그래프가 불완전하다.", _unparseable),
    Rule("dynamic-import", "심각", "동적 import",
         "importlib.import_module·__import__·변수 require 는 정적 그래프에 간선을 남기지 않는다.", _dynamic),
    Rule("no-test-reaches", "심각", "도달하는 테스트 없음",
         "바뀐 모듈을 직접·전이로 import 하는 테스트가 하나도 없다. 검증 없이 통과할 수 있다.", _unreached),
    Rule("deleted-module-still-imported", "치명", "삭제된 모듈을 아직 import",
         "파일을 지웠는데 다른 코드가 그 모듈을 import 하면 런타임/수집 단계에서 터진다.", _deleted_module),
    Rule("renamed-module-stale-import", "심각", "이름 바꾼 모듈의 옛 경로 import",
         "파일 이름을 바꾼 뒤 옛 경로를 import 하는 코드가 남아 있으면 ImportError.", _renamed_stale),
    Rule("public-symbol-removed", "심각", "공개 정의 삭제",
         "공개 함수·클래스가 사라졌다. 다른 모듈이 이름으로 import 하고 있으면 깨진다.", _public_removed),
    Rule("signature-changed", "주의", "인자 시그니처 변경",
         "def 인자가 바뀌면 호출부가 깨질 수 있다. 기본값 유무·키워드 여부를 확인.", _signature),
    Rule("public-symbol-no-test", "주의", "테스트가 이름을 대지 않는 공개 심볼",
         "바뀐 공개 심볼을 import 하거나 문자열로 참조하는 테스트가 없다.", _public_without_test),
    Rule("high-fan-in", "주의", "넓은 파급",
         "프로덕션 모듈 5개 이상이 import 하는 파일은 변경 영향이 넓다.", _high_fan_in),
    Rule("test-weakened", "심각", "테스트 약화",
         "assert 가 줄거나 skip/xfail 이 늘면 초록불이 의미를 잃는다.", _test_weakened),
    Rule("test-deleted", "심각", "테스트 삭제",
         "테스트 파일이 사라졌다. 대체 테스트 없이 지우면 회귀를 못 잡는다.", _test_deleted),
    Rule("fixture-changed", "주의", "fixture 변경",
         "conftest fixture 는 여러 테스트가 함께 쓴다. 영향 범위를 정적으로 확정할 수 없다.", _fixture),
    Rule("new-file-no-test", "주의", "테스트 없는 새 모듈",
         "새 파일을 참조하는 테스트가 없다.", _new_file_no_test),
    Rule("module-level-code", "참고", "모듈 최상위 실행 코드",
         "import 만으로 실행되는 줄이 바뀌면 테스트 수집 단계에서 부작용이 날 수 있다.", _module_level),
    Rule("entrypoint-changed", "주의", "진입점 변경",
         "CLI/main 진입점은 단위 테스트가 아니라 스모크 실행으로 확인해야 한다.", _entrypoint),
    Rule("broad-except", "참고", "넓은 예외 처리",
         "except: / except Exception: 로 삼키면 테스트가 실패를 못 본다.", _broad_except),
    Rule("nondeterminism", "참고", "비결정성 추가",
         "time.sleep·datetime.now·random 은 테스트를 flaky 하게 만든다.", _nondeterminism),
    Rule("env-or-network", "참고", "환경·네트워크 의존",
         "os.environ·requests 는 테스트 환경에 따라 결과가 달라진다.", _env_or_network),
    Rule("selection-too-broad", "참고", "선택이 넓음",
         "선택이 전체의 60% 를 넘으면 전체 실행이 낫다.", _too_broad),
    Rule("no-tests-in-repo", "치명", "테스트 없음",
         "저장소에 테스트 파일이 없다.", _no_tests),
    Rule("broad-test", "참고", "넓게 import 하는 테스트",
         "저장소 모듈 8개 이상을 import 하는 테스트는 통합 성격이다. 항목 수를 줄여도 이 파일 하나가 시간을 먹는다.",
         _broad_test),
    Rule("constant-condition", "참고", "상수 조건",
         "if True: 같은 조건은 분기를 죽인다.", _always_true),
]

RULE_MAP = {rule.rule: rule for rule in RULES}


def build_context(change_set: ChangeSet) -> Context:
    ctx = Context(change_set=change_set)
    for view in change_set.views:
        ctx.added_by_file[view.change.path] = [text for _, text in view.change.added_lines()]
        ctx.removed_by_file[view.change.path] = [text for _, text in view.change.removed_lines()]
    return ctx


def check(change_set: ChangeSet) -> list[Risk]:
    ctx = build_context(change_set)
    found: list[Risk] = []
    for rule in RULES:
        try:
            found.extend(rule.check(ctx))
        except Exception as exc:               # 규칙 하나가 죽어도 나머지는 돈다
            found.append(Risk(rule=rule.rule, severity="참고", title=rule.title,
                              detail=f"규칙 실행 실패: {exc.__class__.__name__}", where=""))
    order = {severity: index for index, severity in enumerate(SEVERITIES)}
    found.sort(key=lambda risk: (order.get(risk.severity, 9), risk.rule, risk.where))
    return found


def counts(risks: list[Risk]) -> dict[str, int]:
    out = {severity: 0 for severity in SEVERITIES}
    for risk in risks:
        out[risk.severity] = out.get(risk.severity, 0) + 1
    return out


def verdict(risks: list[Risk], fallback: list[str]) -> str:
    tally = counts(risks)
    if tally["치명"]:
        return "전체 실행"
    if fallback:
        return "전체 실행"
    if tally["심각"]:
        return "선택 실행 + 심각 항목 확인"
    return "선택 실행"


def catalog(rule_id: str = "") -> list[dict]:
    rows = []
    for rule in RULES:
        if rule_id and rule.rule != rule_id:
            continue
        rows.append({"rule": rule.rule, "severity": rule.severity, "title": rule.title, "doc": rule.doc})
    return rows
