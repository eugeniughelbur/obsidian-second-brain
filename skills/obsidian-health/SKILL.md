---
name: obsidian-health
description: "Check and repair the user's Obsidian vault interactively: find contradictions between notes, near-duplicate notes, broken links, missing frontmatter, stale or undated claims, and orphans, then fix them one by one with the user's approval (rewrite, merge into one note with a redirect, or record an open conflict). Use when the user asks to check, lint, clean up, or fix the vault, or after a large save. Korean triggers: 볼트 점검, 볼트 정리, 모순 찾아, 중복 합쳐, 깨진 링크, 노트 상태 확인."
---

# obsidian-health

볼트를 점검하고, 문제 있는 노트를 사용자와 한 건씩 확인하며 고칩니다. Karpathy LLM Wiki의 **Lint** 연산이며, 기존의 health(점검), reconcile(모순 해소), merge(중복 병합)를 하나로 합친 스킬입니다.

원칙: 점검은 자동, **수정은 승인 후**. 노트는 지우지 않습니다. 인용할 수 없는 모순은 모순이 아닙니다.

## 0. 시작 절차

1. 설정을 읽습니다:
   ```bash
   python3 "{{OSB_ROOT}}/scripts/osb_env.py"
   ```
   종료 코드가 0이 아니면 오류를 전하고 멈춥니다.
2. `<vault_path>/AGENTS.md`(없으면 `CLAUDE.md`), `<skill_root>/references/ai-first-rules.md`, `<skill_root>/references/write-rules.md`를 읽습니다.
3. 인자로 주제나 노트가 주어지면 그 범위만 점검합니다. 없으면 볼트 전체를 점검합니다.

## 1. 점검 (읽기 전용)

다음을 실행하고 결과를 모읍니다. 호스트가 하위 에이전트를 지원하면 2~4단계를 나눠 돌려도 됩니다.

1. 구조 점검:
   ```bash
   "<python>" "<skill_root>/scripts/vault_health.py" --path "<vault_path>" --json
   ```
   중복 후보, 깨진 링크(`wanted_note`), frontmatter 누락, 고아 노트, 템플릿 잔재, 잘못된 태그, 소스 품질 문제를 줍니다.
2. 링크 관계 점검:
   ```bash
   "<python>" "<skill_root>/scripts/link_graph.py" --path "<vault_path>" --lint
   ```
3. 낡은 주장 점검(`<skill_root>/references/freshness-policy.md` 기준, 날짜 없는 현재형 사실과 오래된 `as of`):
   ```bash
   "<python>" "<skill_root>/scripts/freshness_lint.py" --path "<vault_path>" --json
   ```
4. 모순 찾기(에이전트 판단): `index.md`를 읽고 `wiki/concepts/`, `wiki/entities/`, `wiki/projects/`, `wiki/decisions/`에서 서로 충돌하는 주장, 나중에 뒤집혔는데 갱신되지 않은 결정, 더 새로운 소스가 있는데 옛 소스만 인용하는 페이지를 찾습니다. 각 모순은 양쪽 주장마다 `path`, `line`, `quote`(그 노트에서 한 줄을 글자 그대로, 12자 이상)를 갖춰야 합니다.
5. 모순 증명: 모든 모순 후보를 검사기로 확인합니다.
   ```bash
   "<python>" "<skill_root>/scripts/verify_quotes.py" --path "<vault_path>" <<'EOF'
   [{"path": "<노트>", "line": 12, "quote": "<그 노트의 한 줄>"},
    {"path": "<다른 노트>", "line": 40, "quote": "<그 노트의 한 줄>"}]
   EOF
   ```
   양쪽 모두 `"ok": true`인 것만 모순으로 인정하고, 줄 번호는 출력의 `found_line`을 씁니다. 실패한 후보는 "증명 안 됨" 목록으로 빼고 고치지 않습니다.
6. 한 사람이 생각을 바꾼 것(시간에 따른 변화)은 모순이 아니라 변화입니다. 구분해서 분류합니다.

## 2. 요약 보고

심각도별로 묶어 먼저 전체를 보여 줍니다:
- **심각**: 증명된 모순, 템플릿 잔재, frontmatter가 코드 블록에 갇힌 노트, 링크 관계 모순
- **경고**: 중복 후보, frontmatter 누락, 낡은/날짜 없는 주장, 잘못된 태그, 깨진 관계
- **정보**: 아직 없는 링크 대상(앞으로 쓸 페이지 목록, 오류 아님), 고아 노트, 빈 폴더

그리고 처리 방식을 묻습니다: "심각부터 하나씩 / 특정 유형만 / 보고만 하고 끝".

## 3. 한 건씩 수정 (사용자 피드백 루프)

선택된 항목을 심각도 순으로 하나씩 처리합니다. 매 건마다:

1. 문제를 보여 줍니다: 해당 노트 경로, 문제 줄 인용, 왜 문제인지.
2. 수정안을 구체적으로 제시합니다(바뀔 문장 전/후, 또는 병합 미리보기).
3. 선택지를 줍니다: **적용 / 수정해서 적용(사용자가 고칠 점을 말함) / 건너뛰기 / 중단**.
4. 승인된 것만 씁니다. "수정해서 적용"이면 피드백을 반영한 새 수정안을 다시 보여 주고 승인을 받습니다.
5. 비대화형 실행(예: `codex exec`, `claude -p`)처럼 사용자에게 물을 수 없으면 아무것도 고치지 않고 2단계 보고서와 각 항목의 수정안만 출력합니다. 사용자가 대화형 세션에서 다시 실행하면 그때 한 건씩 진행합니다.
6. 같은 종류의 단순 수정(예: 날짜 없는 사실 20개에 `as of` 추가)은 묶어서 한 번에 물어도 됩니다. 사용자가 "나머지는 알아서"라고 하면 그 유형에 한해서만 일괄 적용하고 목록을 보고합니다.

### 유형별 수정 방법

- **모순 (명확한 승자)**: 낡은 쪽 페이지를 최신 내용으로 고치고 `## History`에 "이전: X (출처, 날짜) -> 변경: Y (출처, 날짜)"와 증명된 인용을 남깁니다.
- **모순 (판단 불가)**: `wiki/decisions/Conflict - <주제>.md`(`type: conflict`, `status: open`)에 양쪽 인용과 `path:line`, 근거를 기록하고 두 노트에서 링크합니다. 사용자가 결론을 주면 그에 맞게 고치고 `status: resolved`로 바꿉니다.
- **변화**: 현재 상태로 갱신하고 이전 상태는 `## History`에 남깁니다.
- **중복 병합**:
  1. 두 노트를 모두 읽고, 남길 노트(canonical)를 제안하고 이유를 말합니다(더 풍부하거나 더 많이 링크된 쪽). 사용자가 확정합니다. 3개 이상 묶음은 사용자가 고르게 합니다.
  2. 병합 본문을 작성합니다: 병합 사실을 밝힌 `## For future agent` 서문, 양쪽의 출처와 날짜, 양쪽 `[[링크]]` 전부, 실제로 다른 내용은 고르지 말고 나열. 임시 파일에 저장합니다.
  3. 미리보기(쓰지 않음):
     ```bash
     "<python>" "<skill_root>/scripts/merge_notes.py" --path "<vault_path>" --canonical "<남길 노트>" --retire "<없앨 노트>" --merged-body-file "<임시 파일>"
     ```
     출력(frontmatter 충돌, 별칭, 두 결과 파일 전문)을 요약하지 말고 보여 줍니다.
  4. 승인되면 같은 명령에 `--apply`를 붙여 실행합니다. 없앨 노트는 삭제되지 않고 `type: redirect`로 바뀝니다. 적용 후 손으로 다시 고치지 않습니다.
  5. 스크립트가 거부하면(형식이 깨진 frontmatter 등) 메시지를 그대로 전하고 추측으로 진행하지 않습니다.
- **frontmatter 누락**: 노트 유형에 맞는 필드를 채운 수정안. 코드 블록에 갇힌 frontmatter는 새로 추가하지 말고 코드 블록을 벗겨 냅니다.
- **깨진 링크**: 오타면 링크를 고치고, 여러 곳에서 언급되는 대상이면 새 페이지를 만들지 묻고, 의도적인 예정 링크면 그대로 둡니다.
- **낡은/날짜 없는 주장**: 날짜를 붙이거나(`as of`), 진실이 있는 곳을 가리키는 포인터로 바꾸거나, 기록으로 옮깁니다. 지우지 않습니다.
- **고아 노트**: 관련 페이지나 `index.md`에서 링크할 곳을 제안합니다.

## 4. 마무리

1. 바뀐 페이지의 `index.md` 항목을 갱신합니다.
2. `Logs/YYYY-MM-DD.md`에 추가: `**HH:MM** - health | 심각 X, 경고 Y, 정보 Z / 수정 A, 병합 B, 충돌기록 C, 건너뜀 D`
3. 모든 쓰기를 마친 뒤 마지막으로, 이번에 쓰거나 고친 노트를 검증합니다:
   ```bash
   "<python>" "<skill_root>/scripts/check_notes.py" --path "<vault_path>" <쓴 파일들>
   ```
   실패가 있으면 고치고 다시 검증합니다.
4. 보고: 고친 것, 병합된 노트(남은 쪽과 리다이렉트된 쪽), 열린 충돌 노트, 건너뛴 것, 증명 안 된 모순 후보.

<!-- author-credit -->

---

Based on [obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain) by Eugeniu Ghelbur. MIT license.
