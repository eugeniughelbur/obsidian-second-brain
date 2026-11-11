# Contributing

이 저장소는 Claude Code와 Codex 전용으로 줄인 포크입니다. 스킬은 5개(`skills/`)만 유지합니다.

## 규칙

- 스킬 본문(`skills/<name>/SKILL.md`)은 두 호스트 공용입니다. 특정 호스트에만 있는 도구 이름(`AskUserQuestion`, `Task tool` 등)이나 환경 변수(`CLAUDE_PLUGIN_ROOT`)에 기대지 않습니다. 하위 에이전트는 "지원하면 병렬, 아니면 순차"로 씁니다.
- 경로는 `{{OSB_ROOT}}` 자리표시자를 씁니다. 설치 스크립트가 절대 경로로 바꿉니다.
- 볼트 경로는 항상 `scripts/osb_env.py`로 얻습니다. 현재 작업 디렉터리를 볼트로 간주하지 않습니다.
- 볼트에 쓰는 모든 스킬은 `references/ai-first-rules.md`를 따르고, 마지막에 `scripts/check_notes.py`로 검증합니다.
- 외부 LLM API에 의존하는 기능은 추가하지 않습니다. 요약과 판단은 호출한 에이전트가 합니다.
- 소스 파일에 em-dash, 둥근 따옴표, 유니코드 수학 기호를 쓰지 않습니다(`python scripts/sweep_non_ascii.py --check`).

## 검사

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
python scripts/sweep_non_ascii.py --check
```

Codex 호환성에 영향을 주는 변경은 Codex로 리뷰합니다.
