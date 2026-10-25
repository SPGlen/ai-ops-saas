"""Real FFmpeg smoke test with synthetic narration/clips, never a live AI call."""
import io, json, wave, shutil, tempfile, subprocess
from pathlib import Path
from datetime import datetime, timezone
from app.matrix_rendering import story_video
from app.integrations.rendering import run
root=Path(__file__).resolve().parents[1]
folder=root/'.local'/'matrix-render';folder.mkdir(parents=True,exist_ok=True)
ffmpeg,ffprobe=shutil.which('ffmpeg'),shutil.which('ffprobe')
if not ffmpeg or not ffprobe:
    raise SystemExit('FFmpeg/FFprobe required for media acceptance')
voice=io.BytesIO()
with wave.open(voice,'wb') as w:
    w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\0\0'*16000*45)
run([ffmpeg,'-nostdin','-v','error','-y','-f','lavfi','-i','color=c=0x345d44:s=720x1280:r=24:d=1','-c:v','libx264','-threads','2','-pix_fmt','yuv420p','clip.mp4'],str(folder))
clip=(folder/'clip.mp4').read_bytes()
results=[]
for mode,kinds in [('program',['program']*3),('aigc',['aigc']*3),('mixed',['program','aigc','program'])]:
    scenes=[{'kind':k,'text':'观察、提问、比较与核对','purpose':'科普','narration':'和孩子一起观察生活中的问题，记录一个小发现。','seconds':15,**({'raw':clip,'mime':'video/mp4'} if k=='aigc' else {})} for k in kinds]
    video,cover,duration=story_video(scenes,'AI亲子练习','矩阵测试品牌',voice.getvalue())
    target=folder/(mode+'.mp4');target.write_bytes(video);(folder/(mode+'.png')).write_bytes(cover)
    probe=json.loads(run([ffprobe,'-v','error','-show_format','-show_streams','-of','json',target.name],str(folder),20))
    assert 45<=float(probe['format']['duration'])<=90
    assert any(s['codec_type']=='audio' for s in probe['streams'])
    assert any(s['codec_type']=='video' and s['width']==720 and s['height']==1280 for s in probe['streams'])
    results.append({'mode':mode,'status':'passed','duration_seconds':float(probe['format']['duration']),'bytes':len(video),'audio_and_video':True})
    print(mode,'passed',flush=True)
report={'generated_at':datetime.now(timezone.utc).isoformat(),'renderer':'real FFmpeg','inputs':'synthetic silent narration and generated color clip','real_provider_test':False,'cases':results}
(root/'docs/matrix-media-test.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
