---
name: obsidian-find
description: "Search the user's Obsidian vault and answer from it with citations. Use when the user asks what they wrote, decided, or know about something, asks where a note is, or asks a question their own notes should answer; also use before giving advice that past decisions in the vault may affect. Korean triggers: 볼트에서 찾아, 내 노트에서, 전에 뭐라고 정리했지, 기록 있어?, 옵시디언에서 검색."
---

# obsidian-find

볼트를 검색하고, 찾은 노트를 근거로 답합니다. Karpathy LLM Wiki의 **Query** 연산입니다. 파일 이름만 나열하지 않고, 사용자가 바로 판단할 수 있을 만큼의 맥락과 인용을 줍니다.

## 0. 시작 절차

1. 설정을 읽습니다:
   ```bash
   python3 "{{OSB_ROOT}}/scripts/osb_env.py"
   ```
   종료 코드가 0이 아니면 오류를 전하고 멈춥니다.
2. `<vault_path>/AGENTS.md`(없으면 `CLAUDE.md`)를 읽습니다. 민감 정보 규칙이 있으면 따릅니다.

## 1. 검색

1. `<vault_path>/index.md`를 먼저 읽고 질문과 관련된 페이지를 고릅니다.
2. 순위 검색을 실행합니다(한글은 2글자 단위로 비교하므로 조사가 붙어도 찾습니다):
   ```bash
   "<python>" "<skill_root>/scripts/vault_search.py" "<질문 또는 핵심어>" --json --limit 15
   ```
3. 결과가 적으면 동의어, 영어/한국어 표기, 상위 개념으로 한두 번 더 검색합니다. `aliases:`에 다른 표기가 있을 수 있습니다. 필요하면 `grep -ril`로 보완합니다.
4. 상위 결과와 index에서 고른 페이지를 실제로 읽습니다. 링크된 페이지(`[[...]]`)가 답에 필요하면 한 단계 더 따라갑니다.
5. "없다"고 말하기 전에 위 방법을 모두 써 봅니다. 없다는 결론은 검색한 표현과 함께 밝힙니다.

## 2. 답변

- 질문에 먼저 답하고, 근거 노트를 `[[노트 제목]]`과 볼트 상대 경로로 인용합니다. 중요한 문장은 짧게 그대로 인용합니다.
- 노트들끼리 내용이 다르면 감추지 말고 양쪽을 보여 줍니다(날짜 포함). 정리가 필요하면 `obsidian-health`를 제안합니다.
- 노트에 `(as of ...)` 같은 날짜가 오래된 주장이 있으면 그 날짜를 함께 알립니다.
- 결과가 여러 종류면 유형별(인물, 프로젝트, 개념, 결정, 소스)로 묶습니다.
- 볼트에 없는 내용을 일반 지식으로 보충할 때는 볼트 근거와 구분해서 표시합니다.

## 3. 답변 저장 제안

여러 노트를 엮어서 만든 비교, 분석, 새로 발견한 연결처럼 다시 쓸 만한 답이 나왔다면, `wiki/synthesis/`에 저장할지 한 줄로 묻습니다. 사용자가 원하면 `obsidian-save` 절차로 저장합니다. 이 스킬 자체는 볼트에 쓰지 않습니다.

<!-- author-credit -->

---

Based on [obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain) by Eugeniu Ghelbur. MIT license.
