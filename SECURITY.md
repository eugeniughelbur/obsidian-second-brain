# Security policy

Thanks for helping keep obsidian-second-brain and its users safe.

## Reporting a vulnerability

If you find a security issue in this skill, **do not open a public GitHub issue.** Email it directly to:

**e.ghelbur@gmail.com**

Please include:

- A description of the issue
- Steps to reproduce
- Affected version (run `git rev-parse --short HEAD` inside your clone, or note the release tag)
- Any impact assessment you've done

If you'd like to encrypt the email, mention it in the first message and we'll set up a channel.

## What you can expect

This is a solo-maintained project, so response times are honest:

- **Acknowledgement** within 7 days
- **Triage and severity assessment** within 14 days
- **Fix or mitigation** within 30 days for confirmed issues
- **Public disclosure** only after a fix ships, coordinated with you

If a fix takes longer than 30 days (complex vulnerabilities sometimes do), we'll keep you updated and agree on a disclosure timeline together.

## In scope

- Slash command files in `commands/`
- Python research toolkit in `scripts/`
- Hooks in `hooks/`
- Install script (`install.sh`) and setup tooling
- Anything that handles user vault paths, API keys, or external API calls

Examples of what we care about: path traversal vulnerabilities in scripts, API key leakage in logs or saved notes, prompt injection vectors that exfiltrate vault content, supply-chain risks in the install flow.

## Out of scope

- Bugs in upstream Claude Code, the Anthropic API, Obsidian itself, xAI's API, Perplexity's API, or the YouTube Data API. Report those to the respective vendor.
- Vulnerabilities that require an attacker to already have full access to the user's machine.
- Issues in user-supplied vault content (the skill writes notes, but what you put in your vault is your responsibility).

## Recognition

If your report leads to a fix, you'll be credited in the release notes for the version that ships the fix, unless you'd prefer to stay anonymous. Just let us know in your initial email.

## Summary

- **Email:** e.ghelbur@gmail.com
- **Do not** open a public issue for a vulnerability
- **Do** include reproduction steps and version info
- **Coordinated disclosure** - we'll work with you on the timeline
