---
type: source
date: {{session-date YYYY-MM-DD}}
tags: [source, {{topic}}, knowledge-sharing]
source_type: internal-talk
speaker: "[[{{Speaker Name}}]]"
event: "{{Session title}}"
status: finished
ai-first: true
created: {{today}}
---

## For future agent
Knowledge extracted from {{Speaker}}'s ({{role}}) ~{{N}}-minute {{live-coding session / workshop / recorded walkthrough}} "{{title}}" ({{date}}, {{audience}}). {{One or two sentences on what it covers and the demo context.}} {{Scope note, e.g. "Only the speaker's own content is captured."}} Built from {{Gemini notes / a local Whisper transcript ([[{{Title}} - Transcript]])}} plus frames from the recording{{, related tickets / slides}}. {{Staleness caveat, e.g. "Facts as stated in the session (as of YYYY-MM); verify against current docs."}} {{Paraphrase caveat if frames cut lines off.}}

**Sources**
- Recording: [{{title}} - Recording]({{recording-url}})
- Notes: [{{title}} - Notes]({{notes-url}})
- Slides / related pages / tickets: {{links}}
- Confluence: [{{page title}}]({{confluence-url}}) (added in phase 2)
- Transcript: [[{{Title}} - Transcript]]
- Related: [[{{related note}}]]

---

# {{Title}} ({{Speaker}})

**{{The idea / The flow / Core message}}**: {{one paragraph, or an arrow flow: step → step → step}}

## 1. {{Section}}
*Video MM:SS-MM:SS*

- {{What to do, exact commands and settings, the "most important thing" gotchas}}

```{{lang}}
{{exact code or config as shown}}
```

![[attachments/{{prefix}}-01a-{{short-name}}.png]]

## 2. {{Section}}
*Video MM:SS-MM:SS*

- {{...}}

![[attachments/{{prefix}}-02a-{{short-name}}.png]]

## {{N}}. Takeaways / Q&A
- {{Key lessons, when and where to apply them, answers from the Q&A}}

## Follow-ups
- [ ] {{Next steps named in the session (owner)}}
- [ ] {{Missing sources to chase, e.g. the part 1 recording}}
- Related: {{[[links]]}}
