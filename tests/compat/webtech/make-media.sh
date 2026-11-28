#!/bin/bash
# the small test files of the playback checks (ffmpeg's own test sources)
set -e
d=${1:-media}; mkdir -p "$d"; cd "$d"
src="-f lavfi -i testsrc2=size=640x360:rate=30:duration=6 -f lavfi -i sine=frequency=440:duration=6"
ffmpeg -loglevel error -y $src -c:v libx264 -pix_fmt yuv420p -c:a aac h264_aac.mp4
ffmpeg -loglevel error -y $src -c:v libvpx-vp9 -b:v 500k -c:a libopus vp9_opus.webm
ffmpeg -loglevel error -y $src -c:v libsvtav1 -preset 10 -c:a libopus av1_opus.webm
ffmpeg -loglevel error -y -f lavfi -i testsrc2=size=640x360:rate=30:duration=6 -c:v libsvtav1 -preset 10 -movflags +faststart av1.mp4
ffmpeg -loglevel error -y -f lavfi -i sine=frequency=440:duration=6 -c:a libopus opus.ogg
ffmpeg -loglevel error -y -f lavfi -i testsrc2=size=320x240:duration=1 -frames:v 1 page.png
ls -la
