"""Deterministic local storyboard composition. Only local bytes reach FFmpeg."""
import io, json, shutil, tempfile
from pathlib import Path
from PIL import Image, ImageDraw
from .integrations.rendering import font, lines, run
from .security import fail


def frame(title, text, brand, raw=None):
    canvas = Image.new('RGB', (720,1280), '#e8eddb')
    if raw:
        from PIL import ImageOps
        img = Image.open(io.BytesIO(raw)).convert('RGB')
        if img.width*img.height > 40000000:
            fail('IMAGE_TOO_LARGE','素材像素过大')
        canvas.paste(ImageOps.fit(img,(720,1280)))
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((28,50,692,230), 22, fill='#244b35')
    for i,line in enumerate(lines(title,600,d,font(36))[:3]):
        d.text((55,70+i*45),line,font=font(36),fill='white')
    d.rounded_rectangle((28,690,692,1170),22,fill='#f7f8f1')
    for i,line in enumerate(lines(text,580,d,font(32))[:10]):
        d.text((65,735+i*39),line,font=font(32),fill='#244b35')
    d.text((35,1220),brand[:23]+' · AI辅助创作',font=font(22),fill='#244b35')
    out=io.BytesIO();canvas.save(out,format='PNG')
    return out.getvalue()


def story_video(scenes, title, brand, audio, minimum=45, maximum=90):
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        fail('FFMPEG_UNAVAILABLE','部署节点需要安装FFmpeg',503)
    if not scenes or not audio:
        fail('STORYBOARD_INVALID','分镜或配音缺失')
    with tempfile.TemporaryDirectory(prefix='matrix-render-') as temp:
        folder=Path(temp)
        (folder/'voice.wav').write_bytes(audio)
        probe=json.loads(run([ffprobe,'-v','error','-show_format','-of','json','voice.wav'],temp,20))
        voice_seconds=float(probe['format']['duration'])
        total=voice_seconds+2
        if total < minimum or total > maximum:
            fail('NARRATION_DURATION_INVALID',f'实际配音加片尾为{total:.1f}秒，须在{minimum}至{maximum}秒；请调整分镜后新建运行')
        weights=[max(1,len(scene['narration'])) for scene in scenes]
        lengths=[voice_seconds*w/sum(weights) for w in weights]
        for i,(scene,seconds) in enumerate(zip(scenes,lengths)):
            command=[ffmpeg,'-nostdin','-v','error','-y','-threads','2','-filter_threads','1','-filter_complex_threads','1']
            video_source=scene.get('raw') and scene.get('mime')=='video/mp4'
            if scene['kind']=='aigc' and not video_source:
                fail('STORYBOARD_INVALID','AIGC场景缺少已完成的视频片段')
            filters=[]
            input_count=1
            if video_source:
                (folder/f'source{i}.mp4').write_bytes(scene['raw'])
                command+=['-stream_loop','-1','-protocol_whitelist','file,pipe,crypto','-i',f'source{i}.mp4']
                overlay=Image.new('RGBA',(720,1280))
                d=ImageDraw.Draw(overlay)
                d.rounded_rectangle((28,110,692,330),18,fill=(25,50,35,225))
                for j,line in enumerate(lines(scene['text'],590,d,font(32))[:4]):
                    d.text((55,135+j*39),line,font=font(32),fill='white')
                d.text((35,40),brand[:23],font=font(23),fill='white')
                overlay.save(folder/f'overlay{i}.png')
                command+=['-loop','1','-i',f'overlay{i}.png']
                input_count=2
                filters=['[0:v]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1,fps=24[base]','[base][1:v]overlay=0:0[v0]']
            else:
                raw=scene.get('raw') if str(scene.get('mime','')).startswith('image/') else None
                (folder/f'frame{i}.png').write_bytes(frame(title,scene['text'],brand,raw))
                command+=['-loop','1','-i',f'frame{i}.png']
                filters=['[0:v]scale=720:1280,setsar=1,fps=24[v0]']
            # Caption timings are proportional to narration characters within this scene's actual audio duration.
            measure=ImageDraw.Draw(Image.new('RGB',(720,1280)))
            wrapped=lines(scene['narration'],600,measure,font(29))
            captions=['\n'.join(wrapped[j:j+2]) for j in range(0,len(wrapped),2)]
            caption_weight=sum(len(c) for c in captions)
            elapsed=0.0
            for j,caption in enumerate(captions):
                layer=Image.new('RGBA',(720,1280));d=ImageDraw.Draw(layer)
                d.rounded_rectangle((28,1060,692,1200),18,fill=(20,42,31,235))
                for line_index,line in enumerate(caption.split('\n')):
                    d.text((55,1080+line_index*43),line,font=font(29),fill='white')
                layer.save(folder/f'sub{i}-{j}.png')
                command+=['-loop','1','-i',f'sub{i}-{j}.png']
                end=elapsed+seconds*len(caption)/caption_weight
                filters.append(f"[v{j}][{input_count+j}:v]overlay=0:0:enable='between(t,{elapsed:.4f},{end:.4f})'[v{j+1}]")
                elapsed=end
            command+=['-filter_complex',';'.join(filters),'-map',f'[v{len(captions)}]','-an','-t',f'{seconds:.4f}','-c:v','libx264','-threads','2','-preset','veryfast','-pix_fmt','yuv420p',f'part{i}.mp4']
            run(command,temp,180)
        ending=frame(brand,'一起探索，保持好奇',brand)
        (folder/'ending.png').write_bytes(ending)
        run([ffmpeg,'-nostdin','-v','error','-y','-loop','1','-i','ending.png','-vf','fps=24,setsar=1','-t','2','-an','-c:v','libx264','-threads','2','-preset','veryfast','-pix_fmt','yuv420p','ending.mp4'],temp)
        (folder/'concat.txt').write_text(''.join(f"file 'part{i}.mp4'\n" for i in range(len(scenes)))+"file 'ending.mp4'\n",encoding='utf8')
        run([ffmpeg,'-nostdin','-v','error','-y','-f','concat','-safe','1','-i','concat.txt','-i','voice.wav','-map','0:v','-map','1:a','-c:v','copy','-c:a','aac','-af','apad','-t',str(total),'-movflags','+faststart','output.mp4'],temp)
        return (folder/'output.mp4').read_bytes(),frame(title,scenes[0]['text'],brand),total
