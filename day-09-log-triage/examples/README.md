# 예제 로그

여기 있는 `.log` 파일은 **합성**이다 — 도구가 무엇을 잡는지 보여 주려고
`build_examples.py` 가 만들었다. 실제 서비스 로그가 아니다.

| 파일 | 만든 방법 | 보여 주는 것 |
|---|---|---|
| `api-before.log` | 30분 · 분당 34~46요청 · 드문 오류 3건 | 정상 기준선, 서명 4종, 오류 0.2% |
| `api-after.log` | 같은 트래픽 · 14:10 이후 커넥션 풀 고갈 | 새 서명 1종 291건, 오류 폭주(2.2배), Python 스택 291개 |
| `formats.log` | 손으로 쓴 19줄 | ISO·syslog·Apache(2종)·HDFS·Spark·logcat·JSON·time-only, 오프셋 3종 |
| `korean-cp949.log` | CP949 로 저장 | 인코딩 판별(확신 1.00), 한국어 메시지 보존 |
| `messy-export.log` | 60줄 | 비밀 4종·개인정보 3종·긴 SQL·제어 문자·깨진 글자·빈 본문·재시도 6회 |
| `messy-export.masked.log` | `log-triage redact` 결과 | 지운 값 7, 남은 것 0, 줄 수 그대로 |

## 다시 만들기

```bash
python examples/build_examples.py
```

난수 시드는 고정이라 같은 파일이 나온다. 파일을 고치면 README 의 실측 수치도 같이
달라지므로, 수치를 인용하기 전에 다시 재세요.

## 실제 로그로 재기

```bash
python tools/corpus_probe.py            # 14개 코퍼스 표
python tools/corpus_probe.py --md       # README 에 붙일 표
python tools/corpus_probe.py --only HDFS,Apache
```

`tools/corpus_probe.py` 는 [logpai/loghub](https://github.com/logpai/loghub) 의 2,000줄
샘플을 **임시 폴더에만** 내려받아 분석한다. 그 파일들은 이 저장소에 들어오지 않는다.
