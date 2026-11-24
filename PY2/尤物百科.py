# -*- coding: utf-8 -*-
import json
import os
import re
import ssl
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    _BaseSpider = object

HOST = "https://big.zkdmig.com"
UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")
IMG_PROXY = "https://1.h8.ccwu.cc/"
CATS = [
    ("推特", "twitter"),
    ("onlyfans", "onlyfans"),
    ("糖心vlog", "tangxin"),
    ("麻豆传媒", "madou"),
    ("尤物短剧", "duanju"),
    ("吃瓜", "chigua"),
]
PAGE_SIZE = 20
TIMEOUT = 15
PROXY_PATH = "http://127.0.0.1:9978/proxy?do=py"
AUTHOR_PAGES = 19
AUTHOR_WORKERS = 16
_CTX = ssl._create_unverified_context()


def _clean(s):
    s = re.sub(r"<[^>]+>", "", str(s or ""))
    s = (s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"')
          .replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">"))
    return re.sub(r"\s+", " ", s).strip()


def _unpack(src):
    m = re.search(r"\}\('([\s\S]*)',(\d+),(\d+),'([\s\S]*)'\.split\('\|'\)", str(src or ""))
    if not m:
        return ""
    payload, a, c, kw = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4).split("|")

    def enc(n):
        if n < a:
            return str(n) if n < 10 else chr(n + 87)
        return enc(n // a) + enc(n % a)

    d = {}
    for i in range(c - 1, -1, -1):
        k = enc(i)
        d[k] = kw[i] if i < len(kw) and kw[i] else k
    payload = payload.replace("\\\\", "\\").replace('\\"', '"').replace("\\'", "'")
    return re.sub(r"\b\w+\b", lambda x: d.get(x.group(0), x.group(0)), payload)


def _nold(h):
    return re.sub(r"<script[^>]*ld\+json[^>]*>[\s\S]*?</script>", "", str(h or ""))


def _cards(html):
    out, seen = [], set()
    for blk in re.findall(r"<li[^>]*post-list-item[^>]*>([\s\S]*?)</li>", _nold(html)):
        m = re.search(r'href="/archives/(\d+)/"', blk)
        if not m:
            continue
        vid = m.group(1)
        if vid in seen:
            continue
        h = re.search(r"<h2[^>]*>([\s\S]{1,300}?)</h2>", blk)
        name = _clean(h.group(1)) if h else ""
        pic = ""
        for pat in (r'data-src="(https?://[^"]+)"', r'src="(https?://[^"]+)"'):
            p = re.search(pat, blk)
            if p:
                pic = p.group(1).replace("&amp;", "&")
                break
        if not name:
            a = re.search(r'alt="([^"]{1,300})"', blk)
            name = _clean(a.group(1)) if a else vid
        seen.add(vid)
        out.append({"vod_id": vid, "vod_name": name, "vod_pic": pic, "vod_remarks": ""})
    return out


def _authors(html):
    out, seen = [], set()
    for m in re.finditer(r'<li[^>]*data-id\s*=\s*"(\d+)"([\s\S]{0,3000}?)</li>', _nold(html)):
        aid, blk = m.group(1), m.group(2)
        if aid in seen:
            continue
        nm = re.search(r"<h2[^>]*>([\s\S]{1,100}?)</h2>", blk)
        if not nm:
            continue
        fans = ""
        f = re.search(r'<span class="text-primary[^"]*">([\d.]+[万wW]?)</span>', blk)
        if f:
            fans = f.group(1)
        seen.add(aid)
        out.append({"id": aid, "name": _clean(nm.group(1)), "fans": fans})
    return out


def _ep_titles(html):
    out = []
    for m in re.finditer(r'id="youwu-player-shell-([0-9a-z]+)"', str(html or "")):
        seg = html[max(0, m.start() - 4000):m.start()]
        hs = list(re.finditer(r"<h2[^>]*>([\s\S]{1,200}?)</h2>", seg))
        out.append(_clean(hs[-1].group(1)) if hs else "")
    return out


def _tokens(html):
    out = []
    for b in re.findall(r"<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)</script>", str(html or "")):
        if "eval(function(p,a,c,k,e,d)" not in b:
            continue
        o = _unpack(b)
        m = re.search(r"/api/player/([A-Za-z0-9_-]+)/", o)
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out


def _diag(name, msg):
    return {"vod_id": "0", "vod_name": "诊断｜%s" % name, "vod_pic": "",
            "vod_content": str(msg), "vod_remarks": "诊断",
            "vod_play_from": "诊断", "vod_play_url": "诊断$0"}


class Spider(_BaseSpider):
    host = HOST
    ua = UA
    imgproxy = IMG_PROXY
    proxy_base = PROXY_PATH
    cache = {}
    icache = {}
    acache = (0, [])
    cache_ttl = 600
    timeout = TIMEOUT
    ctx = _CTX

    def init(self, extend=""):
        cfg = {}
        try:
            e = str(extend or "").strip()
            if e.startswith("{"):
                cfg = json.loads(e)
        except Exception:
            cfg = {}
        self.host = str(cfg.get("host") or HOST).rstrip("/")
        self.ua = str(cfg.get("ua") or UA)
        self.imgproxy = str(cfg.get("imgproxy") if "imgproxy" in cfg else IMG_PROXY)
        self.proxy_base = str(cfg.get("proxy") or PROXY_PATH)
        self.timeout = int(cfg.get("timeout") or TIMEOUT)
        self.cache_ttl = int(cfg.get("ttl") or 600)
        self.cache = {}
        self.icache = {}
        self.acache = (0, [])
        return None

    def getDependence(self):
        return ""

    def getName(self):
        return "尤物百科"

    def isVideoFormat(self, url):
        u = str(url or "").lower()
        return ".m3u8" in u or ".mp4" in u

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self.cache = {}
        self.icache = {}
        self.acache = (0, [])
        return None

    def action(self, action):
        return ""

    def _proxy_url(self, typ, u):
        base = str(self.proxy_base or PROXY_PATH)
        sep = "&" if "?" in base else "?"
        return "%s%stype=%s&url=%s" % (base, sep, typ, urllib.parse.quote(u, safe=""))

    def _asset(self, u):
        u = str(u or "").strip()
        if not u.startswith("http"):
            return u
        pre = str(self.imgproxy or "").strip().rstrip("/")
        if pre:
            while u.startswith(pre + "/"):
                u = u[len(pre) + 1:]
            if self.host in u:
                return u
            return pre + "/" + u
        if self.host in u:
            return u
        return self._proxy_url("fetch", u)

    def _pic(self, u):
        u = str(u or "").strip()
        if not u.startswith("http"):
            return u
        q = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
        p = (q.get("p") or [""])[0]
        if "/og/img" in u and p:
            return "%s/og/img/?p=%s" % (self.host, urllib.parse.quote(p, safe=""))
        m = re.match(r"^https?://[^/]+(/upload_[^?#]+)", u)
        if m:
            return "%s/og/img/?p=%s" % (self.host, urllib.parse.quote(m.group(1), safe=""))
        return u

    def _rewrite(self, text):
        out = []
        for ln in str(text or "").splitlines():
            s = ln.strip()
            if not s:
                continue
            if s.startswith("#"):
                if 'URI="' in s:
                    s = re.sub(r'URI="([^"]+)"',
                               lambda mo: 'URI="%s"' % self._asset(mo.group(1)), s)
                out.append(s)
            else:
                out.append(self._asset(s))
        return "\n".join(out) + "\n"

    def _raw(self, u, limit=0):
        req = urllib.request.Request(u, headers={"User-Agent": self.ua,
                                                 "Accept": "*/*",
                                                 "Referer": self.host + "/"})
        with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as r:
            return (r.read(limit) if limit else r.read()), (r.headers.get("Content-Type") or "").lower()

    def _fetch_bytes(self, u, limit=0):
        try:
            return self._raw(u, limit)
        except Exception:
            pre = str(self.imgproxy or "").strip().rstrip("/")
            if pre and not u.startswith(pre):
                return self._raw(pre + "/" + u, limit)
            raise

    def localProxy(self, param):
        p = param if isinstance(param, dict) else {}
        typ = str(p.get("type") or p.get("t") or "img")
        u = urllib.parse.unquote(str(p.get("url") or p.get("u") or ""))
        if not u.startswith("http"):
            return [404, "text/plain", b"", {}]
        if typ == "img":
            hit = self.icache.get(u)
            if hit:
                return [200, hit[0], hit[1], {"User-Agent": self.ua}]
            try:
                body, ct = self._fetch_bytes(u)
            except Exception as e:
                return [502, "text/plain", str(e).encode(), {}]
            if not body:
                return [502, "text/plain", b"empty", {}]
            if not ct.startswith("image"):
                h = body[:12]
                if h[:8] == b"\x89PNG\r\n\x1a\n":
                    ct = "image/png"
                elif h[:2] == b"\xff\xd8":
                    ct = "image/jpeg"
                elif h[:4] == b"RIFF" and body[8:12] == b"WEBP":
                    ct = "image/webp"
                elif h[:3] == b"GIF":
                    ct = "image/gif"
                else:
                    ct = "image/jpeg"
            if len(self.icache) > 200:
                self.icache.clear()
            self.icache[u] = (ct, body)
            return [200, ct, body, {"User-Agent": self.ua}]
        try:
            body, ct = self._fetch_bytes(u)
        except Exception as e:
            return [502, "text/plain", str(e).encode(), {}]
        if not body:
            return [502, "text/plain", b"empty", {}]
        if typ == "m3u8":
            txt = body.decode("utf-8", "ignore")
            return [200, "application/vnd.apple.mpegurl",
                    self._rewrite(txt).encode("utf-8"), {"User-Agent": self.ua}]
        if not ct or "octet-stream" in ct:
            ct = "application/octet-stream"
        return [200, ct, body, {"User-Agent": self.ua}]

    def _get(self, url, ref=""):
        hd = {"User-Agent": self.ua, "Accept": "*/*", "Accept-Language": "zh-CN,zh;q=0.9"}
        if ref:
            hd["Referer"] = ref
        last = None
        for i in range(2):
            try:
                req = urllib.request.Request(url, headers=hd)
                with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as r:
                    raw = r.read()
                for enc in ("utf-8", "gbk"):
                    try:
                        return raw.decode(enc)
                    except UnicodeDecodeError:
                        continue
                return raw.decode("utf-8", "ignore")
            except Exception as e:
                last = e
                if i == 0:
                    time.sleep(0.3)
        raise last

    def _detail(self, vid):
        now = time.time()
        hit = self.cache.get(vid)
        if hit and now - hit[0] < self.cache_ttl:
            return hit[1]
        html = self._get("%s/archives/%s/" % (self.host, vid))
        self.cache[vid] = (now, html)
        if len(self.cache) > 40:
            for k in list(self.cache.keys())[:20]:
                self.cache.pop(k, None)
        return html

    def _wrap(self, items):
        for it in items:
            if it.get("vod_pic"):
                it["vod_pic"] = self._pic(it["vod_pic"])
        return items

    def _count_file(self):
        cands = []
        try:
            cands.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".youwu_works.json"))
        except Exception:
            pass
        try:
            import tempfile
            cands.append(os.path.join(tempfile.gettempdir(), "youwu_works.json"))
        except Exception:
            pass
        for c in cands:
            try:
                d = os.path.dirname(c)
                if not os.path.isdir(d):
                    continue
                t = os.path.join(d, ".yw_probe")
                with open(t, "w") as f:
                    f.write("1")
                os.remove(t)
                return c
            except Exception:
                continue
        return ""

    def _counts(self):
        path = self._count_file()
        val = {}
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    val = json.load(f)
                if not isinstance(val, dict):
                    val = {}
            except Exception:
                val = {}
        return val, path

    def _count_one(self, aid):
        url = "%s/author/%s/" % (self.host, aid)
        req = urllib.request.Request(url, headers={"User-Agent": self.ua, "Accept": "text/html,*/*"})
        with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as r:
            head = r.read(8192)
        m = re.search(rb'"numberOfItems":\s*(\d+)', head)
        return int(m.group(1)) if m else 0

    def _author_list(self):
        now = time.time()
        ts, lst = self.acache if isinstance(self.acache, tuple) else (0, [])
        if lst and now - ts < max(self.cache_ttl, 1800):
            return lst
        urls = ["%s/authors/" % self.host]
        urls += ["%s/authors/page/%d/" % (self.host, i) for i in range(2, AUTHOR_PAGES + 1)]

        def one(u):
            try:
                return _authors(self._get(u))
            except Exception:
                return []

        got = {}
        try:
            with ThreadPoolExecutor(max_workers=AUTHOR_WORKERS) as ex:
                for res in ex.map(one, urls):
                    for a in res:
                        if a["id"] not in got:
                            got[a["id"]] = a
        except Exception:
            pass
        lst = list(got.values())
        if not lst:
            return []
        cnt, path = self._counts()
        need = [a for a in lst if a["id"] not in cnt]

        def one_cnt(a):
            try:
                return self._count_one(a["id"])
            except Exception:
                return -1

        if need:
            try:
                with ThreadPoolExecutor(max_workers=AUTHOR_WORKERS) as ex:
                    for a, n in zip(need, ex.map(one_cnt, need)):
                        cnt[a["id"]] = n
            except Exception:
                pass
            bad = [a for a in need if int(cnt.get(a["id"], 0) or 0) < 0]
            if bad:
                try:
                    with ThreadPoolExecutor(max_workers=6) as ex:
                        for a, n in zip(bad, ex.map(one_cnt, bad)):
                            if n >= 0:
                                cnt[a["id"]] = n
                except Exception:
                    pass
            if path:
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(cnt, f)
                except Exception:
                    pass
        keep = []
        for a in lst:
            n = int(cnt.get(a["id"], 0) or 0)
            a["works"] = n
            if n != 0:
                keep.append(a)
        lst = keep
        lst.sort(key=lambda a: (a["works"] <= 0, -max(a["works"], 0), a["name"]))
        self.acache = (now, lst)
        return lst

    def homeContent(self, filter):
        cls = [{"type_id": "latest", "type_name": "最新推荐"}]
        cls += [{"type_id": s, "type_name": n} for n, s in CATS]
        ups = self._author_list()
        flt = {}
        if ups:
            cls.append({"type_id": "up", "type_name": "UP主"})
            flt["up"] = [{"key": "作者", "name": "作者",
                          "value": [{"n": "%s（%d）" % (a["name"], a["works"]) if a["works"] > 0
                                     else a["name"], "v": a["id"]} for a in ups]}]
        try:
            items = self._wrap(_cards(self._get(self.host + "/")))
        except Exception as e:
            return {"class": cls, "list": [_diag("首页", "请求失败 %s" % e)], "filters": flt}
        return {"class": cls, "list": items[:60], "filters": flt}

    def homeVideoContent(self):
        try:
            return {"list": self._wrap(_cards(self._get(self.host + "/")))[:30]}
        except Exception as e:
            return {"list": [_diag("首页", "请求失败 %s" % e)]}

    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid or "").strip()
        ext = extend if isinstance(extend, dict) else {}
        try:
            pg = int(pg or 1)
        except Exception:
            pg = 1
        aid = ""
        if tid == "up":
            aid = str(ext.get("作者") or "").strip()
        else:
            m = re.match(r"^u_?(\d+)$", tid)
            if m:
                aid = m.group(1)
        if tid == "up" or aid:
            if not re.match(r"^\d+$", aid):
                lst = self._author_list()
                aid = lst[0]["id"] if lst else ""
            if not aid:
                return {"list": [_diag("UP主", "作者列表为空")], "page": pg,
                        "pagecount": pg, "limit": PAGE_SIZE, "total": 0}
            if pg <= 1:
                url = "%s/author/%s/" % (self.host, aid)
            else:
                url = "%s/author/%s/page/%d/" % (self.host, aid, pg)
            try:
                items = self._wrap(_cards(self._get(url)))
            except Exception as e:
                return {"list": [_diag("UP主 %s" % aid, "第%d页请求失败 %s" % (pg, e))],
                        "page": pg, "pagecount": pg, "limit": PAGE_SIZE, "total": 0}
            return {"list": items, "page": pg,
                    "pagecount": pg + 1 if len(items) >= 10 else pg,
                    "limit": PAGE_SIZE, "total": 999999}
        slug = ""
        for name, s in CATS:
            if tid == s or tid == name:
                slug = s
                break
        if slug:
            if pg <= 1:
                url = "%s/category/%s/" % (self.host, slug)
            else:
                url = "%s/category/%s/page/%d/" % (self.host, slug, pg)
        else:
            url = self.host + "/" if pg <= 1 else "%s/page/%d/" % (self.host, pg)
        try:
            items = self._wrap(_cards(self._get(url)))
        except Exception as e:
            return {"list": [_diag("分类 %s" % (tid or "最新"), "第%d页请求失败 %s" % (pg, e))],
                    "page": pg, "pagecount": pg, "limit": PAGE_SIZE, "total": 0}
        return {"list": items, "page": pg,
                "pagecount": pg + 1 if len(items) >= 10 else pg,
                "limit": PAGE_SIZE, "total": 999999}

    def searchContent(self, key, quick, pg="1"):
        try:
            pg = int(pg or 1)
        except Exception:
            pg = 1
        kw = urllib.parse.quote(str(key or "").strip(), safe="")
        if not kw:
            return {"list": [], "page": 1, "pagecount": 1, "limit": PAGE_SIZE, "total": 0}
        if pg <= 1:
            url = "%s/posts/search/%s/" % (self.host, kw)
        else:
            url = "%s/posts/search/%s/page/%d/" % (self.host, kw, pg)
        try:
            items = self._wrap(_cards(self._get(url)))
        except Exception as e:
            return {"list": [_diag("搜索 %s" % key, "第%d页请求失败 %s" % (pg, e))],
                    "page": pg, "pagecount": pg, "limit": PAGE_SIZE, "total": 0}
        return {"list": items, "page": pg,
                "pagecount": pg + 1 if len(items) >= 10 else pg,
                "limit": PAGE_SIZE, "total": 999999}

    def detailContent(self, ids):
        vid = str(ids[0] if ids else "").split("|")[0].strip()
        if not vid:
            return {"list": [_diag("详情", "缺少 vod_id")]}
        try:
            html = self._detail(vid)
        except Exception as e:
            return {"list": [_diag("详情 %s" % vid, "请求失败 %s" % e)]}
        name = ""
        m = re.search(r"<h1[^>]*>([\s\S]{1,300}?)</h1>", html)
        if m:
            name = _clean(m.group(1))
        if not name:
            m = re.search(r"<title>([^<]+)</title>", html)
            name = _clean(m.group(1)) if m else vid
        pic = ""
        m = re.search(r'property="og:image"[^>]+content="([^"]+)"', html)
        if m:
            pic = m.group(1)
        if not pic:
            m = re.search(r'data-src="(https?://[^"]+)"', _nold(html))
            pic = m.group(1) if m else ""
        desc = ""
        m = re.search(r'name="description"[^>]+content="([^"]*)"', html)
        if m:
            desc = _clean(m.group(1))
        toks = _tokens(html)
        if not toks:
            return {"list": [_diag(name, "未解析到播放配置（页面 %d 字节）" % len(html))]}
        titles = _ep_titles(html)
        eps = []
        for i in range(len(toks)):
            t = titles[i] if i < len(titles) and titles[i] else "第%d集" % (i + 1)
            eps.append("%s$%s|%d" % (t.replace("$", " ").replace("#", " "), vid, i))
        vod = {"vod_id": vid, "vod_name": name, "vod_pic": self._pic(pic),
               "vod_content": desc, "vod_remarks": "%d集" % len(toks),
               "vod_play_from": "尤物", "vod_play_url": "#".join(eps)}
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        s = str(id or "").split("|")
        vid = s[0].strip()
        try:
            idx = int(s[1]) if len(s) > 1 else 0
        except Exception:
            idx = 0
        if not vid:
            return {"parse": 1, "url": "", "header": "", "msg": "缺少标识"}
        try:
            html = self._detail(vid)
        except Exception as e:
            return {"parse": 1, "url": "", "header": "", "msg": "详情页请求失败 %s" % e}
        toks = _tokens(html)
        if not toks:
            return {"parse": 1, "url": "", "header": "", "msg": "未解析到播放配置"}
        if idx < 0 or idx >= len(toks):
            idx = 0
        last = ""
        for n in range(3):
            if n:
                self.cache.pop(vid, None)
                try:
                    toks = _tokens(self._detail(vid))
                except Exception:
                    toks = []
                if not toks:
                    last = "详情页重取后仍无播放配置"
                    time.sleep(0.9)
                    continue
                if idx >= len(toks):
                    idx = 0
            api = "%s/api/player/%s/%d" % (self.host, toks[idx], int(time.time() / 2))
            try:
                js = self._get(api, "%s/archives/%s/" % (self.host, vid))
            except Exception as e:
                last = "播放配置请求失败 %s" % e
            else:
                o = _unpack(js)
                m = re.search(r'"video"\s*:\s*\{[\s\S]{0,400}?"url"\s*:\s*"([^"]+)"', o)
                if not m:
                    m = re.search(r'"(https?:[^"]*?\.m3u8[^"]*)"', o)
                if m:
                    url = re.sub(r"\\+/", "/", m.group(1)).replace("&amp;", "&")
                    return {"parse": 0, "url": self._proxy_url("m3u8", url),
                            "header": json.dumps({"User-Agent": self.ua}), "msg": ""}
                last = "配置未含 m3u8（第%d次 %d 字节）" % (n + 1, len(js))
            time.sleep(0.9)
        return {"parse": 1, "url": "", "header": "", "msg": last}


if __name__ == "__main__":
    import sys

    sp = Spider()
    sp.init("")
    print("=" * 60)
    t0 = time.time()
    r = sp.homeContent(False)
    cls = r.get("class") or []
    flt = r.get("filters") or {}
    ups = (flt.get("up") or [{}])[0].get("value") or []
    print("分类数:", len(cls), "| UP主作者数:", len(ups), "| 首页耗时 %.1fs" % (time.time() - t0))
    print("分类列表:", ", ".join(c["type_name"] for c in cls))
    print("UP主前5:", " | ".join(x["n"] for x in ups[:5]))
    items = r.get("list") or []
    print("首页条数:", len(items))
    first = items[0]["vod_id"] if items else ""
    if items:
        print("  封面:", items[0]["vod_pic"][:64])
        try:
            req = urllib.request.Request(items[0]["vod_pic"], headers={"User-Agent": sp.ua})
            with urllib.request.urlopen(req, timeout=20, context=_CTX) as rr:
                b = rr.read(32)
                ct = rr.headers.get("Content-Type")
            magic = b[:2] == b"\xff\xd8" or b[:8] == b"\x89PNG\r\n\x1a\n" or b[:4] == b"RIFF"
            print("  封面取图:", rr.status, ct, "magic", "OK" if magic else "坏图")
        except Exception as e:
            print("  封面取图异常:", e)
    uc = sp.categoryContent("up", 1, False, {"作者": ups[0]["v"] if ups else ""})
    print("UP主[%s] 条数:" % (ups[0]["n"] if ups else "-"), len(uc.get("list") or []),
          "pagecount:", uc.get("pagecount"))
    c = sp.categoryContent("twitter", 1, False, {})
    print("分类页条数:", len(c.get("list") or []), "pagecount:", c.get("pagecount"))
    s = sp.searchContent("推特", False, "1")
    print("搜索条数:", len(s.get("list") or []),
          "首条:", (s.get("list") or [{}])[0].get("vod_id", "-"))
    d = sp.detailContent([first])
    dl = d.get("list") or [{}]
    print("详情:", dl[0].get("vod_name", "-")[:24], "| 分集:", dl[0].get("vod_remarks"))
    p = sp.playerContent("尤物", "%s|0" % first, [])
    print("取流 parse:", p.get("parse"), "| msg:", p.get("msg") or "无")
    ok = 0
    if p.get("parse") == 0:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(p["url"]).query)
        per = sp.localProxy({"type": "m3u8", "url": (q.get("url") or [""])[0]})
        txt = per[2].decode("utf-8", "ignore")
        segs = [x for x in txt.splitlines() if x.strip() and not x.startswith("#")]
        keys = [x for x in txt.splitlines() if x.startswith("#EXT-X-KEY")]
        ok = 1 if segs and "#EXTM3U" in txt else 0
        print("m3u8 代理:", per[0], per[1], "| 分片", len(segs),
              "| 分片已改写:", bool(segs and "1.h8.ccwu.cc" in segs[0]))
        if keys:
            print("  密钥行已改写:", "1.h8.ccwu.cc" in keys[0])
        if segs:
            try:
                req = urllib.request.Request(segs[0], headers={"User-Agent": sp.ua})
                with urllib.request.urlopen(req, timeout=25, context=_CTX) as rr:
                    b = rr.read(4096)
                print("  分片首包:", rr.status, len(b), "字节")
            except Exception as e:
                ok = 0
                print("  分片异常:", e)
    print("=" * 60)
    sys.exit(0 if ok else 1)
