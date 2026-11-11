---
name: obsidian-review
description: "Create or update a daily, weekly, or monthly review note from what was saved in the user's Obsidian vault during that period: what happened, decisions, what was learned, what is being missed or left open, and what matters most right now. Use when the user asks for a review, recap, retrospective, or summary of today/this week/this month. Korean triggers: 오늘 리뷰, 주간 리뷰, 월간 리뷰, 이번 주 정리, 회고, 뭐 했는지 정리, 놓친 거 있어?"
---

# obsidian-review

기간(오늘/이번 주/이번 달) 동안 볼트에 저장된 마크다운 노트만을 재료로 리뷰 노트를 만들거나 갱신합니다. 기존의 recap(요약)과 review(리뷰 노트)를 합친 스킬입니다. 칸반이나 데일리 노트에 의존하지 않습니다.

## 0. 시작 절차

1. 설정을 읽습니다:
   ```bash
   python3 "{{OSB_ROOT}}/scripts/osb_env.py"
   ```
   종료 코드가 0이 아니면 오류를 전하고 멈춥니다.
2. `<vault_path>/AGENTS.md`(없으면 `CLAUDE.md`)와 `<skill_root>/references/ai-first-rules.md`를 읽습니다.

## 1. 기간 결정

- 인자/요청에서 `daily`(오늘), `weekly`(이번 주, 월요일~오늘), `monthly`(이번 달 1일~오늘)를 정합니다. "지난주"처럼 지난 기간이면 그 기간 전체입니다. 불분명하면 `weekly`.
- 노트 이름: `wiki/reviews/YYYY-MM-DD - Daily Review.md`, `wiki/reviews/YYYY-Www - Weekly Review.md`(ISO 주차), `wiki/reviews/YYYY-MM - Monthly Review.md`.

## 2. 재료 수집 (볼트의 마크다운만)

1. `Logs/` 아래 기간 내 날짜 파일을 모두 읽습니다. 무엇이 언제 저장/수정/점검되었는지의 기본 타임라인입니다.
2. 기간 내 생성되거나 수정된 노트를 찾습니다. frontmatter의 `date`/`updated`가 기간 안에 있거나, 파일 수정 시각이 기간 안인 노트(`raw/` 제외):
   ```bash
   find "<vault_path>/wiki" -name "*.md" -newermt "<시작일>" ! -newermt "<종료일 다음날>"
   ```
   frontmatter 날짜도 grep으로 함께 확인합니다(수정 시각은 동기화로 바뀔 수 있으므로 둘 다 봅니다).
3. 유형별로 읽습니다: `wiki/sessions/`(무엇을 했나), `wiki/decisions/`와 프로젝트의 `## Key Decisions`(무엇을 정했나), `wiki/sources/`(무엇을 읽고 봤나), `wiki/concepts/`와 `wiki/synthesis/`(무엇을 배웠나), `type: conflict`의 `status: open`(무엇이 미해결인가).
4. 주간 리뷰는 그 주의 일간 리뷰가, 월간 리뷰는 그 달의 주간 리뷰가 있으면 함께 읽습니다.
5. 기간보다 이전 노트 중, 이번 기간 노트가 링크한 프로젝트와 결정도 읽어 맥락을 잡습니다.
6. 노트가 많으면 호스트가 지원할 때 유형별 하위 에이전트로 나눠 읽어도 됩니다.

## 3. 리뷰 작성

노트 언어는 설정의 `language`. 구조:

```markdown
---
type: review
period: daily | weekly | monthly
date: YYYY-MM-DD            # 작성/갱신일
period-start: YYYY-MM-DD
period-end: YYYY-MM-DD
tags: [review, <period>]
ai-first: true
---

## For future agent
<이 기간의 핵심 2~3문장: 무엇에 집중했고, 무엇이 결정되었고, 무엇이 열려 있는지>

## 한 일
## 결정한 것        (결정과 이유, 결정 노트 링크)
## 배운 것          (새 개념, 바뀐 생각, 근거 노트 링크)
## 놓치고 있는 것   (아래 기준)
## 특히 중요한 것   (아래 기준, 최대 3개)
## 다음에 볼 것     (다음 기간에 이어서 할 일, 열린 질문)
## 이 기간의 노트   (근거로 쓴 노트 링크 전체)
```

### "놓치고 있는 것" 기준

근거 노트를 반드시 링크하고, 근거가 없으면 쓰지 않습니다.
- 결정했지만 후속 기록이 없는 것(결정 후 관련 세션/프로젝트 갱신이 없음)
- `status: open`인 충돌 노트, 답하지 않은 열린 질문
- 세션 기록에 "다음에 할 것"으로 남았는데 이후 다시 언급되지 않은 것
- 여러 노트에서 언급되지만 아직 자기 페이지가 없는 개념이나 사람
- 저장된 소스 중 요약만 하고 어떤 프로젝트/개념과도 연결되지 않은 것
- 이전 리뷰의 "다음에 볼 것" 중 이번 기간에 다루지 않은 것

### "특히 중요한 것" 기준

최대 3개. 다시 알려 줄 가치가 있는 것만 고릅니다: 되돌리기 어려운 결정, 여러 프로젝트에 영향을 주는 배움, 마감이나 약속이 걸린 것, 이전 생각을 뒤집은 발견. 각 항목에 왜 중요한지 한 줄과 근거 링크를 붙입니다.

## 4. 생성 또는 갱신

- 같은 기간의 리뷰 노트가 없으면 새로 만듭니다.
- 이미 있으면(예: 하루에 두 번 실행) 새로 쓰지 말고 갱신합니다: 기존 내용을 읽고, 새로 생긴 항목을 추가하고, 해결된 "놓치고 있는 것"은 `(해결: [[노트]])`로 표시합니다. 사용자가 직접 쓴 문단은 그대로 둡니다. `date`를 오늘로 바꿉니다.
- 기존 리뷰 노트를 고칠 때는 크기와 관계없이 쓰기 전에 변경 요약을 보여 주고 승인받습니다. `<vault_path>/.vault-config.json`의 `rewrite_policy`가 `unattended`이면 묻지 않고 쓰되 보고에 변경 내용을 나열합니다.
- 비대화형 실행(예: `codex exec`, `claude -p`)처럼 물을 수 없으면 새 리뷰 노트만 만들고, 기존 노트 변경은 보고서에 "승인 대기"로 남깁니다.
- 리뷰 외의 다른 노트(프로젝트, 결정 등)는 이 스킬에서 고치지 않습니다. 고칠 것이 보이면 "놓치고 있는 것"에 적고 `obsidian-save`나 `obsidian-health`를 제안합니다.

## 5. 마무리

1. `index.md`의 리뷰 섹션에 항목을 추가/갱신합니다.
2. `Logs/YYYY-MM-DD.md`에 추가: `**HH:MM** - review | <period> <기간> 생성|갱신`
3. 모든 쓰기를 마친 뒤 마지막으로 검증합니다:
   ```bash
   "<python>" "<skill_root>/scripts/check_notes.py" --path "<vault_path>" "<리뷰 노트 상대 경로>"
   ```
   실패가 있으면 고치고 다시 검증합니다.
4. 사용자에게는 노트 전문 대신 "특히 중요한 것"과 "놓치고 있는 것"을 먼저 짧게 보여 주고, 노트 경로를 알려 줍니다.

<!-- author-credit -->

---

Based on [obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain) by Eugeniu Ghelbur. MIT license.
