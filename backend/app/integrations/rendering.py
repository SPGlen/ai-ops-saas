"""Deterministic CJK cards and local-only video finishing. No shell evaluation of copy."""

import io, os, re, shutil, subprocess, tempfile, json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
from ..security import fail


def font(size):
    choices = [
        os.environ.get("OPS_FONT_FILE", ""),
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "C:/Windows/Fonts/msyh.ttc",
    ]
    for path in choices:
        if path and Path(path).is_file():
            return ImageFont.truetype(path, size=size)
    fail("FONT_UNAVAILABLE", "未安装中文字体，请配置 OPS_FONT_FILE", 503)


def lines(text, width, draw, f):
    result = []
    current = ""
    for char in text:
        if char == "\n" or (
            current and draw.textlength(current + char, font=f) > width
        ):
            result.append(current)
            current = "" if char == "\n" else char
        else:
            current += char
    if current:
        result.append(current)
    return result


def cards(raw, title, body, brand):
    image = Image.open(io.BytesIO(raw))
    image.verify()
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    background = ImageOps.fit(image, (1080, 650))
    probe = ImageDraw.Draw(Image.new("RGB", (1080, 1440)))
    copy = lines(body[:6000], 920, probe, font(31))
    if len(copy) > 133:
        fail("CARD_COPY_TOO_LONG", "图文超过8张容量，请缩短文案")
    pages = [copy[:7]] + [copy[i : i + 18] for i in range(7, len(copy), 18)]
    result = []
    for i, copy_page in enumerate(pages):
        page = Image.new("RGB", (1080, 1440), "#f6f6ed")
        d = ImageDraw.Draw(page)
        if i == 0:
            page.paste(background, (0, 0))
            d.rectangle((0, 570, 1080, 720), fill="#f6f6ed")
            y = 610
        else:
            y = 95
        for text in lines(title, 920, d, font(48))[:3]:
            d.text((80, y), text, font=font(48), fill="#244b35")
            y += 68
        y += 35
        for text in copy_page:
            d.text((80, y), text, font=font(31), fill="#455c43")
            y += 47
        d.line((80, 1300, 1000, 1300), fill="#d3dac7", width=2)
        d.text((80, 1335), brand[:24] + " · AI辅助创作", font=font(24), fill="#79916c")
        d.text(
            (935, 1335),
            str(i + 1) + "/" + str(len(pages)),
            font=font(23),
            fill="#79916c",
        )
        out = io.BytesIO()
        page.save(out, format="PNG")
        result.append(out.getvalue())
    return result


def run(args, cwd, timeout=180):
    result = subprocess.run(
        args, cwd=cwd, capture_output=True, timeout=timeout, shell=False
    )
    if result.returncode:
        fail("MEDIA_RENDER_FAILED", "媒体合成失败，请查看运行环境与原始素材", 503)
    return result.stdout


def video(raw, title, narration, brand, audio=None):
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        fail("FFMPEG_UNAVAILABLE", "部署节点需要安装FFmpeg", 503)
    with tempfile.TemporaryDirectory(prefix="ops-media-") as temp:
        folder = Path(temp)
        (folder / "input.mp4").write_bytes(raw)
        probe = json.loads(
            run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-f",
                    "mov",
                    "-show_format",
                    "-show_streams",
                    "-of",
                    "json",
                    "input.mp4",
                ],
                temp,
                20,
            )
        )
        duration = min(120, float(probe["format"]["duration"]))
        # A timed transparent overlay is rendered from text, never interpolated into ffmpeg expressions.
        phrases = re.findall(r"[^。！？\n]{1,16}[。！？]?", narration) or [title[:16]]
        phrases = phrases[:30]
        for i, text in enumerate(phrases):
            layer = Image.new("RGBA", (720, 1280))
            d = ImageDraw.Draw(layer)
            d.rounded_rectangle(
                (30, 1020, 690, 1190), radius=18, fill=(20, 42, 31, 210)
            )
            for j, line in enumerate(lines(text, 600, d, font(34))[:3]):
                d.text((60, 1040 + 45 * j), line, font=font(34), fill="white")
            d.text((35, 40), brand[:20], font=font(23), fill="white")
            layer.save(folder / f"sub{i}.png")
        cover = Image.new("RGB", (720, 1280), "#e8eddb")
        d = ImageDraw.Draw(cover)
        for i, line in enumerate(lines(title, 610, d, font(46))[:5]):
            d.text((55, 340 + 70 * i), line, font=font(46), fill="#244b35")
        d.text((55, 1130), brand[:22] + " · AI辅助创作", font=font(23), fill="#5d7950")
        cover.save(folder / "cover.png")
        ending = Image.new("RGB", (720, 1280), "#244b35")
        d = ImageDraw.Draw(ending)
        d.text((55, 530), brand[:20], font=font(34), fill="white")
        d.text((55, 600), "一起探索，保持好奇", font=font(28), fill="#c9dda9")
        ending.save(folder / "ending.png")
        command = [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-protocol_whitelist",
            "file,pipe,crypto",
            "-f",
            "mov",
            "-i",
            "input.mp4",
        ]
        for i in range(len(phrases)):
            command += ["-loop", "1", "-i", f"sub{i}.png"]
        command += ["-loop", "1", "-t", "2", "-i", "ending.png"]
        audio_index = len(phrases) + 2
        if audio:
            (folder / "voice.wav").write_bytes(audio)
            command += ["-i", "voice.wav"]
        filters = [
            "[0:v]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1,fps=24[v0]"
        ]
        for i in range(len(phrases)):
            start = duration * i / len(phrases)
            end = duration * (i + 1) / len(phrases)
            filters.append(
                f"[v{i}][{i + 1}:v]overlay=0:0:enable='between(t,{start:.3f},{end:.3f})'[v{i + 1}]"
            )
        filters.append(
            f"[{len(phrases) + 1}:v]scale=720:1280,setsar=1,fps=24,trim=duration=2,setpts=PTS-STARTPTS[end]"
        )
        filters.append(
            f"[v{len(phrases)}]trim=duration={duration},setpts=PTS-STARTPTS[main]"
        )
        filters.append("[main][end]concat=n=2:v=1:a=0[out]")
        command += ["-filter_complex", ";".join(filters), "-map", "[out]"]
        if audio:
            command += ["-map", str(audio_index) + ":a", "-af", "apad", "-c:a", "aac"]
        elif any(x.get("codec_type") == "audio" for x in probe["streams"]):
            command += ["-map", "0:a", "-af", "apad", "-c:a", "aac"]
        command += [
            "-t",
            str(duration + 2),
            "-c:v",
            "libx264",
            "-threads",
            "2",
            "-preset",
            "fast",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "output.mp4",
        ]
        run(command, temp)
        return (folder / "output.mp4").read_bytes(), (folder / "cover.png").read_bytes()
