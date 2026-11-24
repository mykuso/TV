# -*- coding: utf-8 -*-
import base64
import gzip
import hashlib
import html
import http.client
import http.cookiejar
import json
import re
import ssl
import threading
import time
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        def getCache(self, key):
            return None

        def setCache(self, key, value):
            return "fail"

        def delCache(self, key):
            return "fail"


DEFAULT_HOST = "https://www.hsck01.net"
NAV_URLS = [
    "https://x99dh.cc",
    "https://x99dh.one",
    "https://x99dh.net",
    "https://x99dh.lat",
]
MIRROR_POOL = [
    "https://www.hsck01.net",
    "https://hsck01.net",
]
SITE_TITLE_KEY = "黄色仓库"
SITE_DESC_KEY = "最新麻豆视频"
HOST_CACHE_KEY = "hsck01_dynamic_site_url_v1"
HOST_CACHE_TTL = 86400 * 3

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
BRAND = "蝴蝶影视"
TG = "🦋 TG群: @tvshare23"
DIRECTOR = "🦋 蝴蝶影视"
PLAY_FROM = "蝴蝶专线"
TG_URL = "https://t.me/tvshare23"
GATE_COOKIE = "x-index-auth=authed"
PLAYER_REFERER = "https://player.centercdn.top/"
PLAYER_ORIGIN = "https://player.centercdn.top"
CARD_STYLE = {"type": "rect", "ratio": 1.78}

CLASSES = [
    ("0", "最新推荐"),
    ("1", "麻豆"),
    ("2", "中字"),
    ("3", "国产"),
    ("4", "欧美"),
    ("5", "日韩"),
]
LABELS = [
    ("麻豆", "麻豆传媒"), ("91制片厂", "91制片厂"), ("蜜桃影像", "蜜桃影像"),
    ("果冻传媒", "果冻传媒"), ("星空无限", "星空无限"), ("天美传媒", "天美传媒"),
    ("精东影业", "精东影业"), ("皇家华人", "皇家华人"), ("糖心Vlog", "糖心Vlog"),
    ("萝莉社", "萝莉社"), ("性视界", "性视界传媒"), ("草霉视频", "草霉视频"),
    ("玩偶姐姐", "玩偶姐姐"), ("爱豆传媒", "爱豆传媒"), ("91茄子", "91茄子"),
    ("扣扣传媒", "扣扣传媒"), ("SA国际传媒", "SA国际传媒"), ("杏吧", "杏吧原创"),
    ("大象传媒", "大象传媒"), ("乌托邦", "乌托邦"), ("69传媒", "69传媒"),
    ("成人头条", "成人头条"), ("乌鸦传媒", "乌鸦传媒"), ("香蕉视频", "香蕉视频"),
]
LABEL_KWS = set(kw for kw, _ in LABELS)
CLASSES = CLASSES + [(kw, name) for kw, name in LABELS]
CAT_NAMES = dict(CLASSES)

CARD_RE = re.compile(
    r'class="stui-vodlist__thumb lazyload" href="/index\.php/vod/play/id/(\d+)/sid/1/nid/1\.html" title="([^"]*)" data-original="([^"]*)"',
    re.S)
DUR_RE = re.compile(r'<span class="pic-text text-right">([^<]*)</span>')
SUB_RE = re.compile(r'<p class="sub"><span class="pull-right">[^<]*</span>([^<]*)</p>')
TITLE_RE = re.compile(r"<title>([^<]*)</title>", re.I)
H1_RE = re.compile(r"<h1[^>]*>([\s\S]*?)</h1>", re.I)
DETAIL_PIC_RE = re.compile(r'<div class="detail-pic[^"]*"><img src="([^"]+)"', re.I)
POSTER_RE = re.compile(r'(?:data-original|data-src|src)=["\']([^"\']+\.(?:png|jpg|webp)[^"\']*)["\']', re.I)
PLAY_LINK_RE = re.compile(r'<a[^>]+href=["\']([^"\']*(?:/vod/play/[^"\']+))["\'][^>]*>([\s\S]*?)</a>', re.I)
IFRAME_RE = re.compile(r'<iframe[^>]+src=["\']([^"\']+)["\']', re.I)
PLAYER_AAAA_RE = re.compile(r"var\s+player_aaaa\s*=\s*(\{[\s\S]*?\});", re.I)
M3U8_URL_RE = re.compile(r"https?://[^\s\"'<>]+(?:\.m3u8|/index\.m3u8)[^\s\"'<>]*", re.I)
REL_BLOCK_RE = re.compile(r'<ul class="img-list dis">(.*?)</ul>', re.S)
REL_ITEM_RE = re.compile(r'<li><a href="/index\.php/vod/detail/id/(\d+)\.html" title="([^"]*)"><img src="[^"]+"', re.S)
TYPE_RE = re.compile(r"<dt>类型：</dt><dd>(.*?)</dd>", re.S)


def format_remarks(brand="蝴蝶影视", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = re.sub(r"[\r\n\t]+", " ", clean_meta).strip()
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand


def clean_ep_name(name):
    return re.sub(r"[\$#]", "", str(name or "").strip())


def normalize_origin(url):
    raw = str(url or "").strip()
    if not raw:
        return ""
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    m = re.match(r"^(https?://[^/?#]+)", raw, re.I)
    return m.group(1).rstrip("/") if m else ""


def unpack_vod_id(vod_id):
    s = str(vod_id or "")
    for _ in range(3):
        d = urllib.parse.unquote(s)
        if d == s:
            break
        s = d
    if "@@" in s:
        base, packed = s.split("@@", 1)
        return base, urllib.parse.unquote(packed)
    return s, ""


def extract_vid(vod_id):
    base, poster = unpack_vod_id(vod_id)
    vid = base[4:] if base.startswith("vod/") else base
    if vid.isdigit():
        return vid, poster
    runs = re.findall(r"\d+", base)
    if runs:
        return max(runs, key=len), poster
    return "", poster


class Spider(BaseSpider):

    def __init__(self):
        self._ctx = ssl.create_default_context()
        self._ctx.check_hostname = False
        self._ctx.verify_mode = ssl.CERT_NONE
        self._jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._jar),
            urllib.request.HTTPSHandler(context=self._ctx))
        self._host_lock = threading.Lock()
        self._active_host = ""
        self._custom_host = ""

    def init(self, extend=""):
        ext = extend
        if isinstance(ext, str) and ext.strip():
            try:
                ext = json.loads(ext)
            except Exception:
                ext = {"host": ext.strip()} if ext.strip().startswith("http") else {}
        if isinstance(ext, dict):
            custom = normalize_origin(ext.get("host") or ext.get("site") or "")
            if custom:
                self._custom_host = custom
                self._active_host = custom

    def getName(self):
        return BRAND

    def _headers(self, referer=None, host=None):
        base_host = host or self._active_host or DEFAULT_HOST
        h = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "close",
            "Cookie": GATE_COOKIE,
            "Referer": referer or (base_host + "/enter"),
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Upgrade-Insecure-Requests": "1",
        }
        return h

    def _decode(self, raw):
        if raw[:2] == b"\x1f\x8b":
            try:
                return gzip.decompress(raw).decode("utf-8", "ignore")
            except Exception:
                return raw.decode("utf-8", "ignore")
        return raw.decode("utf-8", "ignore")

    def _read_once(self, req, timeout):
        try:
            with self._opener.open(req, timeout=timeout) as resp:
                return resp.status, self._decode(resp.read()), resp.geturl()
        except http.client.IncompleteRead as e:
            return 200, self._decode(e.partial), req.full_url
        return 0, "", req.full_url

    def _load_cached_host(self):
        try:
            raw = self.getCache(HOST_CACHE_KEY)
            if not raw:
                return ""
            if isinstance(raw, dict):
                host = normalize_origin(raw.get("host", ""))
                exp = float(raw.get("exp", 0) or 0)
                if host and (not exp or time.time() < exp):
                    return host
                return ""
            if isinstance(raw, str):
                s = raw.strip()
                if s.startswith("{"):
                    obj = json.loads(s)
                    host = normalize_origin(obj.get("host", ""))
                    exp = float(obj.get("exp", 0) or 0)
                    if host and (not exp or time.time() < exp):
                        return host
                    return ""
                return normalize_origin(s)
        except Exception:
            pass
        return ""

    def _save_cached_host(self, host):
        clean = normalize_origin(host)
        if not clean:
            return
        try:
            payload = json.dumps({"host": clean, "exp": int(time.time()) + HOST_CACHE_TTL})
            self.setCache(HOST_CACHE_KEY, payload)
        except Exception:
            pass

    def _clear_cached_host(self):
        try:
            self.delCache(HOST_CACHE_KEY)
        except Exception:
            try:
                self.setCache(HOST_CACHE_KEY, "")
            except Exception:
                pass

    def _check_host_alive(self, base_url):
        clean_base = normalize_origin(base_url)
        if not clean_base:
            return ""
        target = clean_base + "/enter"
        req = urllib.request.Request(target, headers=self._headers(referer=clean_base + "/enter", host=clean_base))
        try:
            status, text, final_url = self._read_once(req, timeout=6)
            if (status == 0 or (200 <= status < 400)) and "stui-vodlist__thumb" in text:
                final_origin = normalize_origin(final_url)
                return final_origin or clean_base
        except Exception:
            pass
        return ""

    def _collect_item_urls(self, item):
        urls = []
        if not isinstance(item, dict):
            return urls
        raw_list = []
        for k in ("url", "link", "href", "directUrl", "bestUrl"):
            if item.get(k):
                raw_list.append(str(item.get(k)))
        if isinstance(item.get("urls"), list):
            for u_obj in item.get("urls"):
                if isinstance(u_obj, str):
                    raw_list.append(u_obj)
                elif isinstance(u_obj, dict):
                    for uk in ("url", "href"):
                        if u_obj.get(uk):
                            raw_list.append(str(u_obj.get(uk)))
        for raw in raw_list:
            origin = normalize_origin(raw)
            if origin and origin not in urls:
                urls.append(origin)
        return urls

    def _fetch_nav_page(self, nav_url):
        headers = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "close",
        }
        req = urllib.request.Request(nav_url, headers=headers)
        try:
            status, text, _ = self._read_once(req, timeout=6)
            if status == 0 or (200 <= status < 400):
                return text
        except Exception:
            pass
        return ""

    def _refresh_site_url(self):
        for nav in NAV_URLS:
            text = self._fetch_nav_page(nav)
            if not text:
                continue

            for m in re.finditer(r'["\']([A-Za-z0-9+/=]{100,})["\']', text):
                b64_str = m.group(1)
                try:
                    raw_bytes = base64.b64decode(b64_str + "===")
                    decoded = raw_bytes.decode("utf-8", "ignore")
                    if "%5B" in decoded or "%7B" in decoded:
                        decoded = urllib.parse.unquote(decoded)
                    if "[" not in decoded or (SITE_TITLE_KEY not in decoded and "麻豆视频" not in decoded):
                        continue
                    site_list = json.loads(decoded)
                    if not isinstance(site_list, list):
                        continue
                    for item in site_list:
                        if not isinstance(item, dict):
                            continue
                        name = str(item.get("name") or item.get("title") or "").strip()
                        desc = str(item.get("desc") or item.get("description") or "").strip()
                        if SITE_TITLE_KEY in name or SITE_DESC_KEY in desc:
                            for cand in self._collect_item_urls(item):
                                alive = self._check_host_alive(cand)
                                if alive:
                                    self._save_cached_host(alive)
                                    return alive
                except Exception:
                    continue

            idx = text.find(SITE_TITLE_KEY)
            if idx != -1:
                snippet = text[max(0, idx - 120):min(len(text), idx + 600)]
                for hm in re.finditer(r'href=["\'](https?://[^"\'/?#]+)[^"\']*["\']', snippet, re.I):
                    cand = normalize_origin(hm.group(1))
                    if cand and "x99dh" not in cand:
                        alive = self._check_host_alive(cand)
                        if alive:
                            self._save_cached_host(alive)
                            return alive

        for mirror in MIRROR_POOL:
            alive = self._check_host_alive(mirror)
            if alive:
                self._save_cached_host(alive)
                return alive

        default_alive = self._check_host_alive(DEFAULT_HOST)
        if default_alive:
            self._save_cached_host(default_alive)
            return default_alive

        return DEFAULT_HOST

    def _get_host(self):
        if self._custom_host:
            return self._custom_host
        with self._host_lock:
            if self._active_host:
                return self._active_host
            cached = self._load_cached_host()
            if cached:
                self._active_host = cached
                return cached
            probed = self._refresh_site_url()
            self._active_host = probed or DEFAULT_HOST
            return self._active_host

    def _heal_host(self, failed_host):
        if self._custom_host:
            return self._custom_host
        with self._host_lock:
            if self._active_host and self._active_host != failed_host:
                return self._active_host
            self._clear_cached_host()
            new_host = self._refresh_site_url()
            self._active_host = new_host or DEFAULT_HOST
            return self._active_host

    def _get_path(self, path, timeout=8, attempts=2, referer_path=None):
        host = self._get_host()
        rel = path if path.startswith("/") else ("/" + path)
        url = host + rel
        ref = (host + referer_path) if referer_path else (host + "/enter")
        text = self._get_raw(url, timeout=timeout, attempts=attempts, referer=ref, host=host)
        if not text and not self._custom_host:
            new_host = self._heal_host(host)
            if new_host and new_host != host:
                url2 = new_host + rel
                ref2 = (new_host + referer_path) if referer_path else (new_host + "/enter")
                text = self._get_raw(url2, timeout=timeout, attempts=attempts, referer=ref2, host=new_host)
        return text

    def _get_raw(self, url, timeout=8, attempts=2, referer=None, host=None):
        req = urllib.request.Request(url, headers=self._headers(referer=referer, host=host))
        best = ""
        for _ in range(attempts):
            try:
                status, text, final_url = self._read_once(req, timeout)
                if status == 200 and len(text) > len(best):
                    best = text
                if status == 200 and len(text) >= 1000 and "</html>" in text:
                    eff = normalize_origin(final_url)
                    if eff and not self._custom_host and eff != self._active_host and "stui-vodlist__thumb" in text:
                        self._active_host = eff
                        self._save_cached_host(eff)
                    return text
            except Exception:
                time.sleep(1)
        return best

    def _post_form_path(self, path, data, referer_path=None, timeout=8, attempts=2):
        host = self._get_host()
        rel = path if path.startswith("/") else ("/" + path)
        url = host + rel
        ref = (host + referer_path) if referer_path else (host + "/enter")
        text = self._post_form_raw(url, data, referer=ref, timeout=timeout, attempts=attempts, host=host)
        if not text and not self._custom_host:
            new_host = self._heal_host(host)
            if new_host and new_host != host:
                url2 = new_host + rel
                ref2 = (new_host + referer_path) if referer_path else (new_host + "/enter")
                text = self._post_form_raw(url2, data, referer=ref2, timeout=timeout, attempts=attempts, host=new_host)
        return text

    def _post_form_raw(self, url, data, referer=None, timeout=8, attempts=2, host=None):
        body = urllib.parse.urlencode(data).encode("utf-8")
        h = self._headers(referer=referer, host=host)
        h["X-Requested-With"] = "XMLHttpRequest"
        h["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        req = urllib.request.Request(url, data=body, headers=h)
        best = ""
        for _ in range(attempts):
            try:
                status, text, _ = self._read_once(req, timeout)
                if status == 200 and len(text) > len(best):
                    best = text
                if status == 200 and len(text) >= 1000 and "</html>" in text:
                    return text
            except Exception:
                time.sleep(1)
        return best

    def _parse_cards(self, text, cat_name=""):
        host = self._get_host()
        items = []
        seen = set()
        parts = text.split('class="stui-vodlist__thumb lazyload"')
        for part in parts[1:]:
            m = re.search(
                r'href="/index\.php/vod/play/id/(\d+)/sid/1/nid/1\.html" title="([^"]*)" data-original="([^"]*)"',
                part)
            if not m:
                continue
            vid, title, pic = m.group(1), m.group(2), m.group(3)
            if vid in seen:
                continue
            seen.add(vid)
            title = html.unescape(title).strip()
            if pic and not pic.startswith("http"):
                pic = urllib.parse.urljoin(host, pic)
            dur_m = DUR_RE.search(part)
            dur = dur_m.group(1).strip() if dur_m else ""
            sub_m = SUB_RE.search(part)
            date = sub_m.group(1).strip() if sub_m else ""
            items.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_actor": TG,
                "vod_remarks": format_remarks(BRAND, date or dur),
                "vod_year": date.split("-")[0] if date else "",
                "style": dict(CARD_STYLE),
            })
        return items

    def _parse_related(self, text, current_vid):
        related = []
        seen = set()
        if not text:
            return related
        for block in REL_BLOCK_RE.findall(text):
            for vid, title in REL_ITEM_RE.findall(block):
                if vid == current_vid or vid in seen:
                    continue
                seen.add(vid)
                title = html.unescape(title or "").strip()
                if not title:
                    continue
                related.append((vid, title))
        return related

    def _page_result(self, items, page):
        page = int(page)
        if items:
            total = page * len(items) + 100
            return {"list": items, "page": page, "pagecount": page + 1,
                    "limit": 20, "total": total}
        return {"list": [], "page": page, "pagecount": 1,
                "limit": 20, "total": 0}

    def _fetch_search(self, kw, page):
        q = urllib.parse.quote(kw)
        if page == 1:
            path = "/index.php/vod/search.html?wd=" + q
        else:
            path = "/index.php/vod/search/wd/%s/page/%d.html" % (q, page)
        text = self._get_path(path)
        return self._parse_cards(text) if text else []

    def homeContent(self, filter):
        return {"class": [{"type_id": tid, "type_name": name} for tid, name in CLASSES]}

    def homeVideoContent(self):
        text = self._get_path("/enter")
        items = self._parse_cards(text) if text else []
        return {"list": items}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg)
        except Exception:
            page = 1
        if page < 1:
            page = 1
        tid = urllib.parse.unquote(str(tid))
        if tid == "0":
            if page > 1:
                return {"list": [], "page": page, "pagecount": 1,
                        "limit": 20, "total": 0}
            text = self._get_path("/enter")
            return self._page_result(self._parse_cards(text) if text else [], page)
        if tid in LABEL_KWS:
            items = self._fetch_search(tid, page)
            return self._page_result(items, page)
        if page == 1:
            path = "/index.php/vod/type/id/%s.html" % tid
        else:
            path = "/index.php/vod/type/id/%s/page/%d.html" % (tid, page)
        text = self._get_path(path)
        items = self._parse_cards(text, CAT_NAMES.get(tid, "")) if text else []
        return self._page_result(items, page)

    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg)
        except Exception:
            page = 1
        if page < 1:
            page = 1
        items = self._fetch_search(key, page)
        return self._page_result(items, page)

    def _resolve_play(self, vid, sid, nid):
        play_path = "/index.php/vod/play/id/%s/sid/%s/nid/%s.html" % (vid, sid, nid)
        ref_path = "/index.php/vod/detail/id/%s.html" % vid
        text = self._post_form_path(play_path, {"id": vid, "sid": sid, "nid": nid}, referer_path=ref_path)
        if not text:
            return ""
        m = IFRAME_RE.search(text)
        if m:
            vm = re.search(r"[?&]video_url=([^&\"'<>]+)", m.group(1))
            if vm:
                return urllib.parse.unquote(vm.group(1))
        pm = PLAYER_AAAA_RE.search(text)
        if pm:
            try:
                pd = json.loads(pm.group(1))
                raw_u = pd.get("url", "")
                enc = str(pd.get("encrypt", "0"))
                if enc == "1":
                    return urllib.parse.unquote(raw_u)
                if enc == "2":
                    return base64.b64decode(raw_u).decode("utf-8")
                return raw_u
            except Exception:
                pass
        mall = M3U8_URL_RE.findall(text)
        if mall:
            return mall[0]
        return ""

    def _structured_content(self, title, category, vid, related_titles, host):
        lines = []
        lines.append("标题：" + (title or ""))
        if category:
            lines.append("分类：" + category)
        lines.append("片源：" + PLAY_FROM)
        lines.append("编号：" + vid)
        if related_titles:
            lines.append("相关推荐：" + " / ".join(related_titles[:6]))
        if host:
            lines.append("当前主站：" + host)
        lines.append("🦋 蝴蝶影视专线直连 | 官方交流群: @tvshare23 | " + TG_URL)
        return "\n".join(lines)

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vid, _ = extract_vid(str(ids[0]))
        if not vid:
            return {"list": []}
        detail_path = "/index.php/vod/detail/id/%s.html" % vid
        text = self._get_path(detail_path)
        if not text:
            text = self._get_path(detail_path)
        host = self._get_host()
        title = ""
        if text:
            h1_m = H1_RE.search(text)
            if h1_m:
                t = html.unescape(re.sub(r"<[^>]*>", "", h1_m.group(1))).strip()
                if t and t not in ("目录", "首页", "播放"):
                    title = t
            if not title:
                tm = TITLE_RE.search(text)
                if tm:
                    raw_t = html.unescape(tm.group(1)).strip()
                    title = re.split(r"详情介绍|在线观看|迅雷下载|-", raw_t)[0].strip()
        if not title:
            title = "视频 " + vid
        poster = ""
        if text:
            pm = DETAIL_PIC_RE.search(text)
            if pm:
                poster = pm.group(1).strip()
            if not poster:
                im = POSTER_RE.search(text)
                if im:
                    poster = im.group(1).strip()
            if poster and not poster.startswith("http"):
                poster = urllib.parse.urljoin(host, poster)
        category = ""
        if text:
            tm2 = TYPE_RE.search(text)
            if tm2:
                category = html.unescape(re.sub(r"<[^>]*>", "", tm2.group(1))).strip()
        routes = []
        if text:
            for href, label in PLAY_LINK_RE.findall(text):
                vm = re.search(r"/id/(\d+)", href)
                if vm and vm.group(1) != vid:
                    continue
                name = clean_ep_name(re.sub(r"<[^>]*>", "", label or "").strip()) or "正片"
                rel_href = href
                if rel_href.startswith("http"):
                    m_rel = re.match(r"^https?://[^/]+(/.*)$", rel_href)
                    if m_rel:
                        rel_href = m_rel.group(1)
                routes.append("%s$%s" % (name, rel_href))
        if not routes:
            routes.append("正片$/index.php/vod/play/id/%s/sid/1/nid/1.html" % vid)
        ep_meta = "正片" if len(routes) == 1 else "%d集全" % len(routes)
        related = self._parse_related(text, vid)
        for rvid, rtitle in related:
            play = "/index.php/vod/play/id/%s/sid/1/nid/1.html" % rvid
            label = clean_ep_name(rtitle) or ("推荐" + rvid)
            routes.append("%s$%s@@@%s" % (label, play, rtitle))
        detail = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": poster,
            "vod_bg": poster,
            "vod_background": poster,
            "vod_banner": poster,
            "vod_actor": TG,
            "vod_director": DIRECTOR,
            "vod_play_from": PLAY_FROM,
            "vod_content": self._structured_content(title, category, vid, [t for _, t in related], host),
            "vod_remarks": format_remarks(BRAND, ep_meta),
            "vod_year": "",
            "vod_play_url": "#".join(routes),
        }
        return {"list": [detail]}

    def playerContent(self, flag, id, vipFlags):
        if not id:
            return {"parse": 0, "playUrl": "", "url": "", "header": {"User-Agent": UA, "Referer": PLAYER_REFERER}}
        play_headers = {"User-Agent": UA, "Referer": PLAYER_REFERER,
                        "Origin": PLAYER_ORIGIN}
        id = urllib.parse.unquote(str(id))
        if "@@@" in id:
            id = id.split("@@@", 1)[0]
        if id.startswith("http") and ".m3u8" in id.lower():
            return {"parse": 0, "playUrl": "", "url": id, "header": play_headers}
        vid = ""
        sid = "1"
        nid = "1"
        vm = re.search(r"/id/(\d+)", id)
        if vm:
            vid = vm.group(1)
        sm = re.search(r"/sid/(\d+)", id)
        if sm:
            sid = sm.group(1)
        nm = re.search(r"/nid/(\d+)", id)
        if nm:
            nid = nm.group(1)
        if not vid:
            vid, _ = extract_vid(id)
        if vid:
            host = self._get_host()
            play_url = host + "/index.php/vod/play/id/%s/sid/%s/nid/%s.html" % (vid, sid, nid)
            m3u8 = self._resolve_play(vid, sid, nid)
            if m3u8:
                return {"parse": 0, "playUrl": "", "url": m3u8,
                        "header": play_headers}
            return {"parse": 0, "playUrl": "", "url": play_url, "header": play_headers}
        return {"parse": 0, "playUrl": "", "url": id, "header": play_headers}

    def isVideoFormat(self, url):
        if not url:
            return False
        low = url.lower()
        for ext in (".m3u8", ".mp4", ".m4a", ".mp3", ".flac", ".aac", ".wav", ".ogg"):
            if ext in low:
                return True
        return False

    def manualVideoCheck(self):
        return False

    def localProxy(self, params):
        return [200, "text/plain", b""]

    def destroy(self):
        return None