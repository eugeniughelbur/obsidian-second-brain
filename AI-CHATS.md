# Bring your chats from 5 AI websites into the vault

The skill saves your Claude Code sessions. It does not see chats you have on ChatGPT, Claude.ai, Gemini, Grok or Perplexity. This page shows how to get those chats into the vault with two steps: an exporter saves each chat as a Markdown file, then `/obsidian-ingest` turns the useful ones into notes.

## What you need

- An exporter that writes one Markdown file per chat into a folder on your disk.
- A folder for those files that sits **outside** your vault.
- The skill, installed as usual.

Any exporter works if it writes plain Markdown. This page uses [Chat to Markdown](https://chattomarkdown.com) as the example, a Chrome and Edge extension. Each service's own data export works too, once you turn it into Markdown files.

## Step 1: save your chats to a folder

1. Make a folder outside the vault, for example `~/ai-chats/`.
2. Install the exporter and point it at that folder.
3. Turn on only the chat sites you want in your notes.

Chat to Markdown writes one file per chat, in one folder per service (as of 2026-11, version 1.0.5, https://chattomarkdown.com/docs/file-format/). Each file starts with a header that holds `title`, `source`, `url`, `id`, `model`, `created` and `updated`. When a chat continues, the same file is updated in place.

Three settings are worth changing before the first save:

- **Save images and files: off.** `/obsidian-ingest` treats every picture in the folder as its own source.
- **Hide secrets: on.** It swaps API keys and passwords for a label before the file is written.
- **Skip these projects.** Add any project whose chats do not belong on this disk, such as work chats on a personal machine.

The free plan saves 10 chats (as of 2026-11, https://chattomarkdown.com/pricing/).

## Step 2: ingest the chats you want

Look before you ingest. This lists what the folder holds and writes nothing:

```
/obsidian-ingest ~/ai-chats/ --preview
```

Then ingest one chat that matters:

```
/obsidian-ingest "~/ai-chats/ChatGPT/2026-10-02 Pricing page ideas.md"
```

Or work through the folder in small batches. Run the same command again for the next batch:

```
/obsidian-ingest ~/ai-chats/ --batch-size 5
```

For each chat, the command saves a copy under `raw/`, then proposes changes to your notes. The original file in `~/ai-chats/` is never edited.

## What to expect

**An AI chat is the lowest trust grade.** The skill grades every source by where it came from. A chat export is graded `speculation`, because an AI answer is a summary with no chain back to its sources. So a chat can add new notes, but it cannot change a note you already have without your yes. Each claim taken from a chat is marked `(confidence: speculation)`. The rule is in [`references/source-quality-check.md`](references/source-quality-check.md).

**Your own words count for more than the AI's.** When you wrote "I signed the contract on Monday" in a chat, that is your statement. When the AI wrote "I made two files for you", that is its own report and nobody checked it. Ask the agent to keep the two apart in the note.

**Most chats are not worth ingesting.** A recipe question or a quick translation adds nothing to a vault. Pick by topic. Ingest the chats about a project, a decision or a plan, and leave the rest in the folder. They stay searchable there with any text search.

## Limits today

- **Keep the folder outside the vault.** Chat files have no AI-first header, so `/obsidian-health` would flag them. The folder ingest also skips any folder named `raw`, `wiki`, `logs`, `research`, `bases` or `boards`, at any depth. A chat project named "Research" is skipped for that reason. Rename the project folder or ingest those files one by one.
- **A chat that keeps growing is saved again.** Raw copies never change. When the chat file changes, the next ingest saves a new copy that points to the old one with `supersedes`. Ingest a chat when it is finished, not while it is still going.
- **Pictures are separate sources.** Turn off picture saving in the exporter, or the batch fills with image files.
- **One folder ingest per vault at a time.** The batch helper has no lock.

## Privacy

- An exporter extension reads every chat site you turn on. Read its privacy policy before you install it. Chat to Markdown states that chats are written straight to your folder and are not sent to its server (as of 2026-11-13, https://chattomarkdown.com/privacy/). Its source code is not public, so that statement is the developer's own.
- Your vault may sync or back up to another place. A chat you ingest goes there too.
- Temporary chats are marked `private: true` in the file header by Chat to Markdown. Leave those out.

## Disclosure

The maintainer received a free license for Chat to Markdown from its developer. This page was not paid for, and the steps work with any exporter that writes Markdown files.
