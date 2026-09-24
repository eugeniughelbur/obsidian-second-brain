#!/bin/bash
# Usage: transcribe.sh <video-file> <out-dir>
# Local Whisper transcript (mlx-whisper). Writes <out-dir>/transcript.md with [MM:SS] minute blocks.
set -e
V="$1"; OUT="$2"; mkdir -p "$OUT"
command -v ~/.local/bin/mlx_whisper >/dev/null || uv tool install mlx-whisper
ffmpeg -v error -y -i "$V" -vn -ac 1 -ar 16000 "$OUT/audio.wav"
# --condition-on-previous-text False prevents the repetition loops / "..." collapse on long silent stretches
~/.local/bin/mlx_whisper "$OUT/audio.wav" --model mlx-community/whisper-large-v3-turbo --language en \
  --condition-on-previous-text False --output-format json --output-dir "$OUT" --verbose False >/dev/null 2>&1
python3 - "$OUT" <<'PY'
import json,sys
out=sys.argv[1]; d=json.load(open(f"{out}/audio.json"))
cur=-1;buf=[];lines=[]
fmt=lambda m: f"{m//60}:{m%60:02d}:00" if m>=60 else f"{m:02d}:00"
for s in d["segments"]:
    m=int(s["start"]//60)
    if m!=cur:
        if buf: lines.append(f"**[{fmt(cur)}]** "+" ".join(buf))
        cur=m;buf=[]
    buf.append(s["text"].strip())
if buf: lines.append(f"**[{fmt(cur)}]** "+" ".join(buf))
open(f"{out}/transcript.md","w").write("\n\n".join(lines))
print(len(" ".join(lines).split()),"words")
PY
