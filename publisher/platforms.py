"""Platform selectors adapted from pinned MIT/Apache upstreams; no upstream web panels."""

import re
from urllib.parse import urlparse

URLS = {
    "xiaohongshu": {
        "home": "https://creator.xiaohongshu.com",
        "upload": "https://creator.xiaohongshu.com/publish/publish",
        "manage": "https://creator.xiaohongshu.com/publish/manage",
        "public": "https://www.xiaohongshu.com/explore/",
    },
    "douyin": {
        "home": "https://creator.douyin.com",
        "upload": "https://creator.douyin.com/creator-micro/content/upload",
        "manage": "https://creator.douyin.com/creator-micro/content/manage",
        "public": "https://www.douyin.com/video/",
    },
    "channels": {
        "home": "https://channels.weixin.qq.com",
        "upload": "https://channels.weixin.qq.com/platform/post/create",
        "manage": "https://channels.weixin.qq.com/platform/post/list",
        "public": "https://channels.weixin.qq.com/platform/post/list?objectId=",
    },
}


async def visible(page, selectors):
    for selector in selectors:
        for locator in await page.locator(selector).all():
            if await locator.is_visible():
                return locator
    return None


async def logged_in(page, platform):
    if any(word in page.url for word in ("login.html", "/login", "passport")):
        return False
    text = (await page.locator("body").inner_text())[:12000]
    if any(
        x in text
        for x in (
            "扫码登录",
            "手机号登录",
            "微信扫码登录 视频号助手",
            "验证码",
            "账号异常",
            "滑块",
        )
    ):
        return False
    selectors = {
        "xiaohongshu": [
            ".user-info",
            '.creator-header [class*="avatar"]',
            'a[href*="/publish/manage"]',
        ],
        "douyin": ['[class*="avatar"]', 'a[href*="content/manage"]'],
        "channels": [
            '[class*="account-info"]',
            '[class*="finder-info"]',
            'button:has-text("发表")',
            'a[href*="/post/list"]',
        ],
    }
    return bool(await visible(page, selectors[platform]))


async def prepare(page, platform, title, body, files):
    await page.goto(
        URLS[platform]["upload"], wait_until="domcontentloaded", timeout=60000
    )
    await page.wait_for_timeout(1500)
    if not await logged_in(page, platform):
        raise ValueError("LOGIN_REQUIRED")
    videos = [x for x in files if x.suffix == ".mp4"]
    images = [x for x in files if x.suffix in (".png", ".jpg", ".webp")]
    if platform == "channels" and not videos:
        raise ValueError("CHANNELS_VIDEO_REQUIRED")
    if len(title) > 20 and platform in ("xiaohongshu", "douyin"):
        raise ValueError("TITLE_TOO_LONG")
    if platform == "xiaohongshu":
        tab = page.get_by_text("上传视频" if videos else "上传图文", exact=True).first
        if await tab.count():
            await tab.click()
    if platform == "douyin" and not videos:
        tab = page.get_by_text("发布图文", exact=False).first
        if await tab.count():
            await tab.click()
    selector = 'input[type="file"]'
    inputs = page.locator(selector)
    await inputs.first.wait_for(state="attached", timeout=30000)
    chosen = None
    for node in await inputs.all():
        accept = (await node.get_attribute("accept") or "").lower()
        if (videos and ("video" in accept or ".mp4" in accept)) or (
            not videos and ("image" in accept or ".jpg" in accept)
        ):
            chosen = node
            break
    chosen = chosen or inputs.first
    await chosen.set_input_files(
        [str(videos[0])] if videos else [str(x) for x in images]
    )
    title_selectors = {
        "xiaohongshu": ['input[placeholder*="填写标题"]', "input.d-text"],
        "douyin": ['input[placeholder*="作品标题"]'],
        "channels": ['input[placeholder*="填写短标题"]'],
    }
    body_selectors = {
        "xiaohongshu": [
            "div.tiptap.ProseMirror",
            'div.ProseMirror[contenteditable="true"]',
        ],
        "douyin": ['div.zone-container[contenteditable="true"]'],
        "channels": [
            'div[contenteditable="true"]',
            '.input-editor[contenteditable="true"]',
        ],
    }
    await page.wait_for_timeout(1500)
    # Locator waits handle upload duration; there is one final submission, never click retries.
    title_node = page.locator(",".join(title_selectors[platform])).first
    if platform != "channels" or await title_node.count():
        await title_node.wait_for(state="visible", timeout=90000)
        await title_node.fill(title)
    body_node = page.locator(",".join(body_selectors[platform])).first
    await body_node.wait_for(state="visible", timeout=90000)
    await body_node.fill(body)
    text = await page.locator("body").inner_text()
    if any(x in text for x in ("违规", "实名验证", "验证码", "账号异常", "滑块")):
        raise ValueError("ACCOUNT_REVIEW_REQUIRED")
    # Make the platform's AI disclosure explicit when it offers the control.
    ai = page.get_by_text("内容由AI生成", exact=True)
    if await ai.count() and await ai.first.is_visible():
        await ai.first.click()
    button = page.get_by_role(
        "button", name="发表" if platform == "channels" else "发布", exact=True
    ).first
    await button.wait_for(state="visible", timeout=90000)
    if not await button.is_enabled():
        raise ValueError("PUBLISH_FORM_INCOMPLETE")
    return button


def publication_response(platform, url, data):
    host = urlparse(url).hostname or ""
    domains = {
        "xiaohongshu": "xiaohongshu.com",
        "douyin": "douyin.com",
        "channels": "weixin.qq.com",
    }
    if not (host == domains[platform] or host.endswith("." + domains[platform])):
        return None
    patterns = {
        "xiaohongshu": r"/(?:web_api/)?sns/v\d+/note(?:/post|/publish)?(?:\?|$)",
        "douyin": r"(?:aweme/create|aweme/post|create_v2)",
        "channels": r"(?:post_create|publish_feed|create_feed)",
    }
    if not re.search(patterns[platform], url):
        return None
    ok = (
        data.get("success") is True
        or data.get("code") == 0
        or data.get("status_code") == 0
        or data.get("errcode") == 0
        or data.get("base_resp", {}).get("ret") == 0
    )
    if not ok:
        return None
    keys = {
        "xiaohongshu": ("note_id", "noteId"),
        "douyin": ("aweme_id", "item_id"),
        "channels": ("objectId", "object_id", "feed_id"),
    }[platform]

    def find(obj):
        if isinstance(obj, dict):
            for key in keys:
                if obj.get(key) and re.fullmatch(
                    r"[A-Za-z0-9_-]{8,100}", str(obj[key])
                ):
                    return str(obj[key])
            for value in obj.values():
                found = find(value)
                if found:
                    return found
        if isinstance(obj, list):
            for value in obj:
                found = find(value)
                if found:
                    return found
        return None

    found = find(data)
    return (
        {
            "status": "succeeded",
            "external_id": found,
            "external_url": URLS[platform]["public"] + found,
        }
        if found
        else None
    )
