#!/bin/bash
# Usage:
#   frames.sh sheets <video> <out-dir> [seconds-per-cell]   -> 4x4 contact sheets (default 30s per cell; 20s for <20 min videos)
#   frames.sh grab   <video> <out-dir> <sec> [<sec> ...]     -> full-res frames c<SSSS>.png cropped to the screen-share area + 2x2 previews p<NN>.png
set -e
MODE="$1"; V="$2"; OUT="$3"; shift 3; mkdir -p "$OUT"
if [ "$MODE" = sheets ]; then
  N="${1:-30}"
  ffprobe -v error -show_entries format=duration -of default=nw=1 "$V"
  ffmpeg -v error -y -i "$V" -vf "fps=1/$N,scale=480:-1,tile=4x4" "$OUT/sheet_%02d.png"
  echo "cell k (0-based, row-major) on sheet s (1-based) = second ((s-1)*16 + k) * $N"; ls "$OUT"
  exit 0
fi
# Meet recordings: screen share is the left 1440x934 below the top bar; speaker tiles on the right.
CROP="${CROP:-crop=1440:934:0:73}"
for t in "$@"; do ffmpeg -v error -y -ss "$t" -i "$V" -frames:v 1 -vf "$CROP" "$OUT/$(printf 'c%04d.png' "$t")"; done
files=( $(printf "c%04d.png " "$@") ); n=1; cd "$OUT"
for ((i=0;i<${#files[@]};i+=4)); do
  a=${files[i]}; b=${files[i+1]:-$a}; c=${files[i+2]:-$a}; d=${files[i+3]:-$a}
  ffmpeg -v error -y -i $a -i $b -i $c -i $d -filter_complex "[0]scale=960:-1[a];[1]scale=960:-1[b];[2]scale=960:-1[c];[3]scale=960:-1[d];[a][b]hstack[t];[c][d]hstack[u];[t][u]vstack" $(printf "p%02d.png" $n)
  echo "p$n: $a $b $c $d"; n=$((n+1))
done
