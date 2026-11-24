# coding: utf-8
import re
import json
import sys
import base64
import ssl
import socket
import threading
import urllib.request
import urllib.parse
from html import unescape as html_unescape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.append('..')
from base.spider import Spider

SITE = "https://d39cgxtrya69tg.cloudfront.net"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
IMG_KEY = b"2019ysapp7527"
CATEGORIES = [
    {'type_id': '/category/jinri/', 'type_name': '今日吃瓜'},
    {'type_id': '/category/ai-egao/', 'type_name': 'AI成人短剧'},
    {'type_id': '/category/tuite/', 'type_name': '推特网黄'},
    {'type_id': '/category/xiaoyuan/', 'type_name': '校园黑料'},
    {'type_id': '/category/wanghong/', 'type_name': '网红黑料'},
    {'type_id': '/category/hot/', 'type_name': '热门大瓜'},
    {'type_id': '/category/toboo/', 'type_name': '海角乱伦'},
    {'type_id': '/category/mingxingheiliao/', 'type_name': '明星黑料'},
    {'type_id': '/category/wuye/', 'type_name': '午夜AV'},
    {'type_id': '/category/tanhua/', 'type_name': '91探花'},
    {'type_id': '/category/lieqi/', 'type_name': '猎奇重口'},
    {'type_id': '/category/dongman/', 'type_name': '成人动漫'},
    {'type_id': '/category/meiri/', 'type_name': '每日大赛'},
]

_proxy_port = 0
_proxy_started = False
_proxy_lock = threading.Lock()
_CUR_HOST = [SITE]
# 播放失败时返回的合法空清单（避免播放器报 Manifest Malformed）
ERR_M3U8 = ('#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:10\n'
            '#EXT-X-MEDIA-SEQUENCE:0\n#EXT-X-ENDLIST\n')
EMPTY_GIF = (b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00'
             b'\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,'
             b'\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;')


def _decode_img(data):
    key = IMG_KEY
    klen = len(key)
    raw = bytearray(data)
    for i in range(min(100, len(raw))):
        raw[i] ^= key[i % klen]
    return bytes(raw)


def _sniff_img_ct(data):
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if data[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    return ''


class _ProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/play/'):
            self._serve_play()
            return
        self._serve_img()

    def _serve_play(self):
        """m3u8 播放代理：实时取新鲜清单、校验、密钥地址绝对化"""
        try:
            ident = urllib.parse.unquote(self.path[len('/play/'):])
            if ident.endswith('.m3u8'):
                ident = ident[:-5]
            host = _CUR_HOST[0]
            slug = ''
            if ident.startswith('arch_'):
                try:
                    slug = base64.b64decode(ident[5:]).decode('utf-8')
                except Exception:
                    return self._write_m3u8(ERR_M3U8)
                real = _fresh_m3u8(host, slug)
            elif ident.startswith('raw_'):
                real = urllib.parse.unquote(ident[4:])
            else:
                real = ident if ident.startswith('http') else ''
            if not real:
                return self._write_m3u8(ERR_M3U8)
            body = _fetch_manifest(real)
            # 清单无效（JSON/广告/过期）且知道详情页时，重新签发 ticket 再取一次
            if not body or not _is_live_manifest(body):
                if slug:
                    real2 = _fresh_m3u8(host, slug)
                    if real2:
                        body = _fetch_manifest(real2) or body
                if not body or not _is_live_manifest(body):
                    return self._write_m3u8(ERR_M3U8)
            # 密钥 URI 是相对路径 /enkey?...，播放器经本地代理播放时会解析到 127.0.0.1，改写为绝对地址
            sp = urllib.parse.urlsplit(real)
            origin = sp.scheme + '://' + sp.netloc
            body = re.sub(r'URI="/enkey', 'URI="' + origin + '/enkey', body)
            self._write_m3u8(body)
        except Exception:
            self._write_m3u8(ERR_M3U8)

    def _write_m3u8(self, body):
        b = body.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/vnd.apple.mpegurl')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _serve_img(self):
        try:
            real = urllib.parse.unquote(self.path[1:])
            if not real or not real.startswith('http'):
                self.send_response(404); self.end_headers(); return
            r = urllib.request.urlopen(urllib.request.Request(
                real, headers={'User-Agent': UA, 'Referer': SITE + '/'}),
                timeout=20, context=ssl._create_unverified_context())
            data = _decode_img(r.read())
            # 源站常返回 octet-stream，按文件头嗅探真实图片类型
            ct = _sniff_img_ct(data)
            if not ct:
                src_ct = r.headers.get('Content-Type') or ''
                ct = src_ct if src_ct.startswith('image/') else 'image/jpeg'
            self.send_response(200)
            self.send_header('Content-Type', ct)
            self.send_header('Cache-Control', 'max-age=86400')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_response(200)
            self.send_header('Content-Type', 'image/gif')
            self.end_headers()
            self.wfile.write(EMPTY_GIF)

    def log_message(self, fmt, *args):
        pass


def _start_proxy():
    global _proxy_port, _proxy_started
    with _proxy_lock:
        if _proxy_started:
            return _proxy_port
        sk = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sk.bind(('127.0.0.1', 0))
        _proxy_port = sk.getsockname()[1]
        sk.close()
        server = ThreadingHTTPServer(('127.0.0.1', _proxy_port), _ProxyHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        _proxy_started = True
        return _proxy_port


def _ssl_ctx_insecure():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _http_get(url, referer=None, timeout=25):
    hdrs = {'User-Agent': UA}
    if referer:
        hdrs['Referer'] = referer
    req = urllib.request.Request(url, headers=hdrs)
    try:
        resp = urllib.request.urlopen(req, context=_ssl_ctx_insecure(), timeout=timeout)
    except Exception:
        resp = urllib.request.urlopen(req, timeout=timeout)
    return resp.read()


def _fresh_m3u8(host, slug):
    """访问详情页签发新 ticket，提取新鲜的 m3u8 地址"""
    try:
        h = _http_get(host + slug, referer=host + '/').decode('utf-8', 'replace')
        m = re.search(r'data-url="([^"]+?\.m3u8[^"]*)"', h)
        if not m:
            return ''
        rel = m.group(1).replace('&amp;', '&')
        if rel.startswith('http'):
            return rel
        if rel.startswith('/'):
            return host + rel
        return host + '/h5/m3u8/' + rel
    except Exception:
        return ''


def _fetch_manifest(url):
    """取 m3u8 清单；非 #EXTM3U（JSON/HTML）返回空"""
    try:
        data = _http_get(url, referer=_CUR_HOST[0] + '/', timeout=20).decode('utf-8', 'replace')
    except Exception:
        return ''
    if not data.lstrip().startswith('#EXTM3U'):
        return ''
    return data


def _is_live_manifest(body):
    """有效清单：EXT-X-KEY 的 URI 必须带 ticket 参数（广告/过期清单为 /enkey 无参）"""
    return bool(re.search(r'URI="/enkey\?[^"]*ticket=', body)) or bool(
        re.search(r'URI="[^"]*enkey\?[^"]*ticket=', body))


def _img_proxy_url(url):
    if not url:
        return ''
    return 'http://127.0.0.1:%d/%s' % (_start_proxy(), urllib.parse.quote(url, safe=''))


class Spider(Spider):
    def getName(self):
        return "69吃瓜网"

    def init(self, extend):
        self.host = SITE
        if isinstance(extend, dict) and extend.get('host'):
            self.host = extend.get('host')
        elif isinstance(extend, str) and extend.strip().startswith('http'):
            self.host = extend.strip().rstrip('/')
        self.headers = {'User-Agent': UA, 'Referer': self.host + '/'}
        self._ssl_ctx = ssl.create_default_context()
        self._ssl_ctx.check_hostname = False
        self._ssl_ctx.verify_mode = ssl.CERT_NONE
        _start_proxy()

    def _fetch(self, url, referer=None):
        hdrs = {'User-Agent': UA}
        if referer:
            hdrs['Referer'] = referer
        req = urllib.request.Request(url, headers=hdrs)
        try:
            resp = urllib.request.urlopen(req, context=self._ssl_ctx, timeout=25)
        except Exception:
            resp = urllib.request.urlopen(req, context=ssl._create_unverified_context(), timeout=25)
        return resp.read().decode('utf-8', errors='replace')

    def _fix(self, u):
        if not u:
            return ''
        if u.startswith('//'):
            return 'https:' + u
        if u.startswith('/'):
            return self.host + u
        if not u.startswith('http'):
            return self.host + '/' + u
        return u

    def _items(self, html):
        out = []
        seen = set()
        # 按 <article> 卡片块整体解析，slug/标题/封面同块提取，避免索引错位
        for blk in re.findall(r'<article\b[^>]*>.*?</article>', html, re.S):
            try:
                if '/archives/' not in blk:
                    continue
                ms = re.search(r'<a href="(/archives/[^"]+?/)"[^>]*'
                               r'class="(?:videoCardHitArea|searchListCard__link)"', blk)
                if not ms:
                    continue
                slug = ms.group(1)
                if slug in seen:
                    continue
                # 标题：优先卡片标题元素，其次 a 标签 aria-label
                title = ''
                mt = (re.search(r'videoTitle"[^>]*>(.*?)</h2>', blk, re.S) or
                      re.search(r'searchListCard__title[^>]*>(.*?)</div>', blk, re.S))
                if mt:
                    title = re.sub(r'<[^>]+>', '', mt.group(1)).strip()
                if not title:
                    ma = re.search(r'aria-label="(?:阅读文章：)?([^"]*)"', blk)
                    if ma:
                        title = ma.group(1).strip()
                if not title:
                    continue
                # 封面
                mp = re.search(r'(?:videoCover|searchListCard__image)[^>]*?data-src="([^"]+)"', blk)
                pic = mp.group(1) if mp else ''
                seen.add(slug)
                out.append({'vod_id': 'arch_' + base64.b64encode(slug.encode()).decode(),
                            'vod_name': html_unescape(title),
                            'vod_pic': _img_proxy_url(pic), 'vod_remarks': ''})
            except Exception:
                continue
        return out

    def _pagecount(self, h, pg):
        # 分页控件形如 “第 2/85 页”
        m = re.search(r'第\s*\d+\s*/\s*(\d+)\s*页', h)
        if m:
            try:
                return max(1, int(m.group(1)))
            except Exception:
                pass
        if 'nextBtn' in h or 'rel="next"' in h:
            return max(pg, 99)
        return pg

    def homeContent(self, filter):
        h = self._fetch(self.host + "/")
        return {'class': CATEGORIES, 'list': self._items(h)}

    def homeVideoContent(self):
        return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        if tid is None or tid == '':
            tid = '/category/jinri/'
        try:
            pg = int(pg) if pg else 1
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        if tid.startswith('/category/'):
            base = self.host + tid.rstrip('/')
        else:
            base = self.host + tid
        url = base if pg == 1 else base + '/' + str(pg)
        h = self._fetch(url)
        out = self._items(h)
        type_name = str(tid)
        for c in CATEGORIES:
            if c['type_id'] == tid:
                type_name = c['type_name']
                break
        pagecount = self._pagecount(h, pg)
        return {'list': out, 'page': pg, 'pagecount': pagecount, 'limit': 20,
                'total': pagecount * 20, 'type_name': type_name}

    def detailContent(self, array):
        if not array:
            return {'list': []}
        vid = str(array[0]) if isinstance(array, list) else str(array).strip()
        real_url = ''
        if vid.startswith('arch_'):
            try:
                real_url = base64.b64decode(vid[5:]).decode('utf-8')
            except Exception:
                return {'list': []}
        elif vid.startswith('/archives/') or vid.startswith('http'):
            real_url = vid
        if not real_url:
            return {'list': []}
        detail_url = real_url if real_url.startswith('http') else self._fix(real_url)
        try:
            h = self._fetch(detail_url)
        except Exception:
            return {'list': []}
        m = re.search(r'data-url="([^"]+?\.m3u8[^"]*)"', h)
        if not m:
            return {'list': []}
        rel = m.group(1).replace('&amp;', '&')
        if rel.startswith('http'):
            play_url = rel
        elif rel.startswith('/'):
            # data-url 已是 /h5/m3u8/... 绝对路径，直接拼 host，避免双重路径
            play_url = self.host + rel
        else:
            play_url = self.host + '/h5/m3u8/' + rel
        # 标题：优先播放器 data-video-title，其次 h1
        name = ''
        t = re.search(r'data-video-title="([^"]*)"', h) or re.search(r'<h1[^>]*>(.*?)</h1>', h, re.S)
        if t:
            name = html_unescape(re.sub(r'<[^>]+>', '', t.group(1))).strip()
        # 封面：播放器附近的详情主图
        pic = ''
        pos = h.find('data-url')
        if pos >= 0:
            ctx = h[max(0, pos - 2500):pos]
            mp = re.search(r'(?:data-src|src|poster)="(https://webimg[^"]+)"', ctx)
            if mp:
                pic = _img_proxy_url(mp.group(1))
        # 播放走本地代理：播放时实时签发新 ticket、校验清单、绝对化密钥地址
        if vid.startswith('arch_'):
            play_id = vid
        elif '/archives/' in real_url:
            path = urllib.parse.urlsplit(real_url).path
            play_id = 'arch_' + base64.b64encode(path.encode()).decode()
        else:
            play_id = 'raw_' + urllib.parse.quote(play_url, safe='')
        play_url = 'http://127.0.0.1:%d/play/%s.m3u8' % (_start_proxy(), play_id)
        return {'list': [{'vod_id': vid, 'vod_name': name, 'vod_pic': pic, 'type_name': '',
                          'vod_year': '', 'vod_area': '', 'vod_actor': '', 'vod_director': '',
                          'vod_content': '', 'vod_play_from': 'm3u8',
                          'vod_play_url': '正片$' + play_url, 'vod_remarks': ''}]}

    def searchContent(self, key, quick, pg='1'):
        try:
            pg = int(pg) if pg else 1
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        try:
            base = self.host + '/search/' + urllib.parse.quote(key)
            url = base if pg == 1 else base + '/' + str(pg)
            h = self._fetch(url)
            items = self._items(h)
            pagecount = self._pagecount(h, pg)
            return {'list': items, 'page': pg, 'pagecount': pagecount}
        except Exception:
            return {'list': [], 'page': pg, 'pagecount': 0}

    def playerContent(self, flag, id, vipFlags):
        # 未走代理的 id（原始 m3u8 链接或 arch_）统一包装成本地代理地址
        if id and not str(id).startswith('http://127.0.0.1:'):
            pid = str(id)
            if pid.startswith('http'):
                pid = 'raw_' + urllib.parse.quote(pid, safe='')
            id = 'http://127.0.0.1:%d/play/%s.m3u8' % (_start_proxy(), pid)
        return {'parse': 0, 'playUrl': '', 'url': id,
                'header': json.dumps({'User-Agent': UA, 'Referer': self.host + '/'})}

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return {}
