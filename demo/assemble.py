"""The re-cut: the search first, the identifier as a record card, Works with time, cost as unit numbers.
Narration: tts2/*.wav (Chatterbox), lengths in tts2/durations.json."""
import json, os, subprocess, sys
S = os.path.dirname(os.path.abspath(__file__)); os.chdir(S); os.makedirs("seg2", exist_ok=True)
D = json.load(open("tts2/durations.json"))
def run(a): subprocess.run(a, check=True)
def dur(p): return float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",p],capture_output=True,text=True).stdout.strip())
def norm(src, dest, t=None, fade_out=0.0, ss=0.0, fade_in=0.0):
    vf = "scale=1920:1080:flags=lanczos,fps=30,format=yuv420p"
    if t: vf += ",tpad=stop_mode=clone:stop_duration=12"
    if fade_in: vf += f",fade=t=in:st=0:d={fade_in}"
    if fade_out: vf += f",fade=t=out:st={t-fade_out:.2f}:d={fade_out}"
    a = ["ffmpeg","-y","-v","error"] + (["-ss", f"{ss:.2f}"] if ss else []) + ["-i", src]
    if t: a += ["-t", f"{t:.3f}"]
    run(a + ["-an","-vf",vf,"-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p","-r","30",dest])
LEAD = 0.4
def plan():
    i = D["06_identifier"] + 0.8
    return {
     "01_hook":       [("rec/card_open.webm", max(6.0, D["01_hook"] + 0.9), 0.0, 0.0)],
     "02_search":     [("rec/search1.webm", D["02_search"] + 0.7, 0.0, 0.0)],
     "03_sam":        [("rec/t02a.webm", 7.5, 0.0, 0.0), ("clips/kb_sam.mp4", None, 0.0, 0.0), ("rec/t02c.webm", max(8.0, D["03_sam"] + 0.6 - 13.0), 0.0, 0.0)],
     "04_reader":     [("clips/kb_reader.mp4", None, 0.0, 0.0), ("rec/pageview.webm", max(8.0, D["04_reader"] + 0.6 - 6.0), 0.0, 0.0)],
     "05_works":      [("rec/search2.webm", D["05_works"] + 0.7, 0.0, 0.0)],
     "06_identifier": [("rec/ident.webm", i, 0.0, 0.0)],
     "07_scale":      [("rec/stats.webm", 9.0, 0.0, 0.0), ("rec/readme.webm", max(12.0, D["07_scale"] + 0.6 - 9.0), 2.5, 0.0)],
     "08_close":      [("rec/card_close.webm", max(5.5, D["08_close"] + 2.0), 0.0, 0.8)],
    }
vlist, alist, total = [], [], 0.0
for seg, parts in plan().items():
    seglen = 0.0
    for k, (src, t, ss, fo) in enumerate(parts):
        dest = f"seg2/{seg}_{k}.mp4"; norm(src, dest, t, fade_out=fo, ss=ss); seglen += dur(dest); vlist.append(dest)
    nar = D[seg]; assert seglen >= nar + LEAD - 0.05, (seg, seglen, nar)
    run(["ffmpeg","-y","-v","error","-i",f"tts2/{seg}.wav","-af",f"adelay={int(LEAD*1000)}:all=1,apad=whole_dur={seglen:.3f}","-ar","48000","-ac","2","-t",f"{seglen:.3f}",f"seg2/{seg}.wav"])
    alist.append(f"seg2/{seg}.wav"); total += seglen
    print(f"{seg:14} video {seglen:5.1f}s  narration {nar:5.1f}s")
open("seg2/v.txt","w").write("".join(f"file '{os.path.abspath(v)}'\n" for v in vlist))
open("seg2/a.txt","w").write("".join(f"file '{os.path.abspath(a)}'\n" for a in alist))
run(["ffmpeg","-y","-v","error","-f","concat","-safe","0","-i","seg2/v.txt","-c","copy","seg2/video.mp4"])
run(["ffmpeg","-y","-v","error","-f","concat","-safe","0","-i","seg2/a.txt","-af","loudnorm=I=-16:TP=-1.5:LRA=11","-ar","48000","-ac","2","seg2/audio.wav"])
run(["ffmpeg","-y","-v","error","-i","seg2/video.mp4","-i","seg2/audio.wav","-c:v","copy","-c:a","aac","-b:a","192k","-shortest","-movflags","+faststart","colophon-demo-v2.mp4"])
print(f"planned {total:.1f}s  final {dur('colophon-demo-v2.mp4'):.1f}s  size {os.path.getsize('colophon-demo-v2.mp4')//1024//1024} MB")
