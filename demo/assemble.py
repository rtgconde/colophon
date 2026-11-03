import json, os, subprocess
S = os.path.dirname(os.path.abspath(__file__)); os.chdir(S)
os.makedirs("seg", exist_ok=True)
D = json.load(open("tts/durations.json"))
def run(a): subprocess.run(a, check=True)
def dur(p): return float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",p],capture_output=True,text=True).stdout.strip())
def norm(src, dest, t=None, fade_out=0.0, ss=0.0):
    vf = "scale=1920:1080:flags=lanczos,fps=30,format=yuv420p"
    if t: vf += ",tpad=stop_mode=clone:stop_duration=10"      # hold the last frame, then -t cuts to the exact length
    if fade_out: vf += f",fade=t=out:st={t-fade_out:.2f}:d={fade_out}"
    a = ["ffmpeg","-y","-v","error"] + (["-ss", f"{ss:.2f}"] if ss else []) + ["-i",src]
    if t: a += ["-t", f"{t:.3f}"]
    a += ["-an","-vf",vf,"-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p","-r","30",dest]
    run(a)
# the segments: name -> list of (source, trim seconds or None)
plan = {
 "01_intro":      [("clips/slideshow.mp4", None), ("rec/card_open.webm", 6.5)],
 "02_sam":        [("rec/t02a.webm", 8.5), ("clips/kb_sam.mp4", None), ("rec/t02c.webm", 8.5)],
 "03_reader":     [("clips/kb_reader.mp4", None), ("rec/pageview.webm", 11.5)],
 "04_search":     [("rec/search.webm", 24.3)],
 "05_works":      [("rec/works.webm", 21.3)],
 "06_identifier": [("rec/t06.webm", 43.5)],
 "07_cost":       [("rec/t07.webm", 5.5), ("rec/readme.webm", 15.5, 2.5)],   # the GitHub page is blank for its first 2 s
 "08_close":      [("rec/card_close.webm", 5.5)],
}
LEAD = 0.4
vlist, alist, total = [], [], 0.0
for seg, parts in plan.items():
    seglen = 0.0
    for i, part in enumerate(parts):
        src, t = part[0], part[1]; ss = part[2] if len(part) > 2 else 0.0
        dest = f"seg/{seg}_{i}.mp4"
        last = (seg == "08_close") and i == len(parts) - 1
        norm(src, dest, t, fade_out=0.8 if last else 0.0, ss=ss)
        seglen += dur(dest); vlist.append(dest)
    nar = D[seg]
    assert seglen >= nar + LEAD - 0.05, (seg, seglen, nar)
    # audio: LEAD silence + narration + tail silence = seglen
    run(["ffmpeg","-y","-v","error","-i",f"tts/{seg}.wav","-af",f"adelay={int(LEAD*1000)}:all=1,apad=whole_dur={seglen:.3f}","-ar","48000","-ac","2","-t",f"{seglen:.3f}",f"seg/{seg}.wav"])
    alist.append(f"seg/{seg}.wav"); total += seglen
    print(f"{seg:14} video {seglen:5.1f}s  narration {nar:5.1f}s")
open("seg/v.txt","w").write("".join(f"file '{os.path.abspath(v)}'\n" for v in vlist))
open("seg/a.txt","w").write("".join(f"file '{os.path.abspath(a)}'\n" for a in alist))
run(["ffmpeg","-y","-v","error","-f","concat","-safe","0","-i","seg/v.txt","-c","copy","seg/video.mp4"])
run(["ffmpeg","-y","-v","error","-f","concat","-safe","0","-i","seg/a.txt","-af","loudnorm=I=-16:TP=-1.5:LRA=11","-ar","48000","-ac","2","seg/audio.wav"])
run(["ffmpeg","-y","-v","error","-i","seg/video.mp4","-i","seg/audio.wav","-c:v","copy","-c:a","aac","-b:a","192k","-shortest","-movflags","+faststart","colophon-demo.mp4"])
print(f"planned {total:.1f}s  video {dur('seg/video.mp4'):.1f}s  audio {dur('seg/audio.wav'):.1f}s  final {dur('colophon-demo.mp4'):.1f}s  size {os.path.getsize('colophon-demo.mp4')//1024//1024} MB")
