#!/usr/bin/env python3
"""The ffmpeg-made clips: the opening page-turn (eight plates of the 1929 catalogue in pages/, crossfaded) and two
slow zooms on docs/img/reader-input.jpg. Writes clips/slideshow3.mp4, clips/kb_sam.mp4, clips/kb_reader.mp4."""
import os, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); os.makedirs("clips", exist_ok=True)
def run(a): subprocess.run(a, check=True)
pages = ["0070", "0080", "0086", "0099", "0104", "0125", "0136", "0150"]   # pages/<nnnn>.jpg, copied from the hub's pages/13269/
D, X = 3.0, 0.5
args = ["ffmpeg", "-y", "-v", "error"]
for p in pages: args += ["-loop", "1", "-t", str(D), "-i", f"pages/{p}.jpg"]
fc = [f"[{i}:v]scale=-2:1040:flags=lanczos,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x0b0d10,setsar=1,fps=30,format=yuv420p[v{i}]" for i in range(len(pages))]
prev, off = "v0", D - X
for i in range(1, len(pages)):
    fc.append(f"[{prev}][v{i}]xfade=transition=fade:duration={X}:offset={off:.2f}[x{i}]"); prev = f"x{i}"; off += D - X
fc.append(f"[{prev}]fade=t=in:st=0:d=0.6[vout]")
run(args + ["-filter_complex", ";".join(fc), "-map", "[vout]", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "clips/slideshow3.mp4"])
IMG = os.path.join(HERE, "..", "docs", "img", "reader-input.jpg")
def kb(dest, secs, z0, z1, cx, cy):
    n = int(secs * 30)
    vf = (f"scale=-2:1080:flags=lanczos,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x0b0d10,"
          f"zoompan=z='{z0}+({z1}-{z0})*on/{n}':x='iw*{cx}-(iw/zoom)*{cx}':y='ih*{cy}-(ih/zoom)*{cy}':d={n}:s=1920x1080:fps=30,format=yuv420p")
    run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-t", str(secs), "-i", IMG, "-vf", vf, "-t", str(secs), "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", dest])
kb("clips/kb_sam.mp4", 5.5, 1.0, 1.18, 0.5, 0.45)
kb("clips/kb_reader.mp4", 6.0, 1.05, 1.45, 0.42, 0.33)
print("clips written")
