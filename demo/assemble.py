"""The story cut (2026-11-03, the third and final cut). Each segment = clips + one or more narration files (joined with a 0.5 s gap), video held to fit."""
import json, os, subprocess
S = os.path.dirname(os.path.abspath(__file__)); os.chdir(S); os.makedirs("seg", exist_ok=True)
D = json.load(open("tts/durations.json"))
def run(a): subprocess.run(a, check=True)
def dur(p): return float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",p],capture_output=True,text=True).stdout.strip())
def norm(src, dest, t=None, fade_out=0.0, ss=0.0):
    vf = "scale=1920:1080:flags=lanczos,fps=30,format=yuv420p"
    if t: vf += ",tpad=stop_mode=clone:stop_duration=15"
    if fade_out: vf += f",fade=t=out:st={t-fade_out:.2f}:d={fade_out}"
    a = ["ffmpeg","-y","-v","error"] + (["-ss", f"{ss:.2f}"] if ss else []) + ["-i", src]
    if t: a += ["-t", f"{t:.3f}"]
    run(a + ["-an","-vf",vf,"-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p","-r","30",dest])
LEAD, GAP = 0.4, 0.5
def nar_len(names): return sum(D[n] for n in names) + GAP * (len(names) - 1)
# (segment, narration files, clips[(src, length or None, start offset)]) — a clip length of "fit" = narration + 0.7 s
PLAN = [
 ("01_library",  ["01_library"],              [("rec/wall.webm", 8.0, 0)]),
 ("02_moma",     ["02_moma", "03_problem"],   [("clips/slideshow3.mp4", "fit", 0)]),
 ("04_goal",     ["04_goal"],                 [("rec/card_open.webm", 5.5, 0), ("rec/jobs.webm", "rest", 0)]),
 ("05_sam",      ["05_sam"],                  [("rec/t02a.webm", 7.0, 0), ("clips/kb_sam.mp4", None, 0), ("clips/kb_reader.mp4", "rest", 0)]),
 ("06_read",     ["06_read"],                 [("rec/pageview.webm", 8.0, 0), ("rec/flow.webm", "rest", 0)]),
 ("07_search",   ["07_search"],               [("rec/search1.webm", 9.5, 0), ("rec/search2.webm", "rest", 0.8)]),
 ("08_identifier", ["08_identifier"],         [("rec/ident.webm", "fit", 0)]),
 ("09_scale",    ["09_scale"],                [("rec/stats.webm", 8.5, 0), ("rec/readme.webm", "rest", 2.5)]),
 ("10_close",    ["10_close"],                [("rec/card_close.webm", 5.5, 0)]),
]
vlist, alist, total = [], [], 0.0
for seg, nars, clips in PLAN:
    need = nar_len(nars) + LEAD + 0.3
    fixed = sum(c[1] for c in clips if isinstance(c[1], float)) + sum(dur(c[0]) for c in clips if c[1] is None)
    seglen = 0.0
    for k, (src, t, ss) in enumerate(clips):
        if t == "fit": t = need
        elif t == "rest": t = max(6.0, need - fixed)
        dest = f"seg/{seg}_{k}.mp4"; last = seg == "10_close"
        norm(src, dest, t, fade_out=0.8 if last else 0.0, ss=ss); seglen += dur(dest); vlist.append(dest)
    assert seglen >= nar_len(nars) + LEAD - 0.05, (seg, seglen, nar_len(nars))
    # the narration track for the segment: files joined with GAP, LEAD in front, padded to the video length
    inputs = []; filt = ""
    for i, n in enumerate(nars): inputs += ["-i", f"tts/{n}.wav"]; filt += f"[{i}:a]apad=pad_dur={GAP if i < len(nars)-1 else 0}[a{i}];"
    filt += "".join(f"[a{i}]" for i in range(len(nars))) + f"concat=n={len(nars)}:v=0:a=1,adelay={int(LEAD*1000)}:all=1,apad=whole_dur={seglen:.3f}[out]"
    run(["ffmpeg","-y","-v","error"] + inputs + ["-filter_complex", filt, "-map", "[out]", "-ar","48000","-ac","2","-t",f"{seglen:.3f}",f"seg/{seg}.wav"])
    alist.append(f"seg/{seg}.wav"); total += seglen
    print(f"{seg:14} video {seglen:5.1f}s  narration {nar_len(nars):5.1f}s")
open("seg/v.txt","w").write("".join(f"file '{os.path.abspath(v)}'\n" for v in vlist))
open("seg/a.txt","w").write("".join(f"file '{os.path.abspath(a)}'\n" for a in alist))
run(["ffmpeg","-y","-v","error","-f","concat","-safe","0","-i","seg/v.txt","-c","copy","seg/video.mp4"])
run(["ffmpeg","-y","-v","error","-f","concat","-safe","0","-i","seg/a.txt","-af","loudnorm=I=-16:TP=-1.5:LRA=11","-ar","48000","-ac","2","seg/audio.wav"])
run(["ffmpeg","-y","-v","error","-i","seg/video.mp4","-i","seg/audio.wav","-c:v","copy","-c:a","aac","-b:a","192k","-shortest","-movflags","+faststart","colophon-demo.mp4"])
print(f"planned {total:.1f}s = {int(total//60)}:{int(total%60):02d}  final {dur('colophon-demo.mp4'):.1f}s  size {os.path.getsize('colophon-demo.mp4')//1024//1024} MB")
