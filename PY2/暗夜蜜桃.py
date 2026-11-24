#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import json
import time
import random
import hashlib
import hmac
import urllib.request
import urllib.parse
import ssl
import gzip
import zlib

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

class Spider(BaseSpider):
    def __init__(self):
        super(Spider, self).__init__()
        self.site_url = "https://mitaoline.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://honeypeach.cc/",
            "Connection": "close"
        }
        self.ssl_ctx = ssl.create_default_context()
        self.ssl_ctx.check_hostname = False
        self.ssl_ctx.verify_mode = ssl.CERT_NONE
        self.dev_id = "%x%x" % (random.randint(10000000, 99999999), int(time.time() * 1000))
        self.sid = ""
        self.skey = ""
        self.sk_exp = 0

    def _hp_hash(self, s):
        h = 0x811C9DC5
        for ch in s:
            h ^= ord(ch)
            h = (h * 0x01000193) & 0xFFFFFFFF
        return h

    def _hp_pow(self, chal, nonce):
        h = self._hp_hash("%s:%s" % (chal, nonce))
        for _ in range(4):
            hex_str = ("%08x" % h)[-8:]
            h = self._hp_hash(hex_str + chal)
        return ("%08x" % h)[-8:]

    def _hp_solve(self, chal, bits=16):
        want = "0" * (bits >> 2)
        n = 0
        while n < 20000000:
            nx = hex(n)[2:]
            hx = self._hp_pow(chal, nx)
            if hx.startswith(want):
                return "%s.%s" % (chal, nx)
            n += 1
        return ""

    def _raw_fetch(self, url, method="GET", headers=None, body_bytes=None, timeout=8):
        req_headers = dict(self.headers)
        if headers:
            req_headers.update(headers)
        req = urllib.request.Request(url, data=body_bytes, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=timeout) as resp:
                code = resp.getcode()
                raw_bytes = resp.read()
                encoding = resp.headers.get("Content-Encoding", "").lower()
                if "gzip" in encoding:
                    try:
                        raw_bytes = gzip.decompress(raw_bytes)
                    except Exception:
                        pass
                elif "deflate" in encoding:
                    try:
                        raw_bytes = zlib.decompress(raw_bytes)
                    except Exception:
                        pass
                text = raw_bytes.decode("utf-8", errors="ignore")
                return {"status": code, "content": text, "error": ""}
        except urllib.error.HTTPError as e:
            return {"status": e.code, "content": e.read().decode("utf-8", errors="ignore"), "error": str(e)}
        except Exception as e:
            return {"status": 0, "content": "", "error": str(e)}

    def _ensure_handshake(self):
        now = int(time.time())
        if self.sid and self.skey and now < (self.sk_exp - 60):
            return True

        hs_url = urllib.parse.urljoin(self.site_url, "/api/handshake?dev=" + urllib.parse.quote(self.dev_id))
        res = self._raw_fetch(hs_url, method="GET", timeout=6)
        if res["status"] != 200 or not res["content"]:
            return False

        try:
            d = json.loads(res["content"])
        except Exception:
            return False

        if d.get("need_chal"):
            chal = d["need_chal"]
            bits = int(d.get("bits", 16))
            tok = self._hp_solve(chal, bits)
            if not tok:
                return False
            chal_url = hs_url + "&c=" + urllib.parse.quote(tok)
            res = self._raw_fetch(chal_url, method="GET", timeout=6)
            if res["status"] != 200 or not res["content"]:
                return False
            try:
                d = json.loads(res["content"])
            except Exception:
                return False

        if d.get("sid") and d.get("skey"):
            self.sid = d["sid"]
            self.skey = d["skey"]
            self.sk_exp = int(d.get("exp", 0))
            return True
        return False

    def _signed_fetch(self, path, method="GET", params=None, body=None, timeout=8):
        if not self._ensure_handshake():
            url = urllib.parse.urljoin(self.site_url, path)
            if params:
                url += ("?" + urllib.parse.urlencode(params))
            return self._raw_fetch(url, method=method, timeout=timeout)

        query_str = urllib.parse.urlencode(params) if params else ""
        body_str = json.dumps(body) if body is not None else ""
        body_bytes = body_str.encode("utf-8") if body_str else None

        body_hash = hashlib.sha256(body_str.encode("utf-8") if body_str else b"").hexdigest()
        ts = "%d" % int(time.time())
        nonce = "%x%x" % (random.randint(100000, 999999), int(time.time() * 1000))

        canon = "%s\n%s\n%s\n%s\n%s\n%s\n%s" % (
            method.upper(),
            path,
            query_str,
            body_hash,
            ts,
            nonce,
            self.sid
        )

        try:
            key_bytes = bytes.fromhex(self.skey)
            sig = hmac.new(key_bytes, canon.encode("utf-8"), hashlib.sha256).hexdigest()
        except Exception:
            sig = ""

        req_headers = {
            "X-Hp-Sid": self.sid,
            "X-Hp-Ts": ts,
            "X-Hp-Nonce": nonce,
            "X-Hp-Sign": sig
        }
        if body_bytes:
            req_headers["Content-Type"] = "application/json"

        full_url = urllib.parse.urljoin(self.site_url, path)
        if query_str:
            full_url += ("?" + query_str)

        res = self._raw_fetch(full_url, method=method, headers=req_headers, body_bytes=body_bytes, timeout=timeout)
        if res["status"] == 401:
            self.sid = ""
            self.skey = ""
            if self._ensure_handshake():
                return self._signed_fetch(path, method=method, params=params, body=body, timeout=timeout)
        return res

    def _format_cover(self, mod, url):
        if not url:
            return ""
        if mod == "live" or url.startswith("/") or "://" not in url:
            if url.startswith("/"):
                return urllib.parse.urljoin(self.site_url, url)
            return url
        return urllib.parse.urljoin(self.site_url, "/cover/%s?u=%s" % (mod, urllib.parse.quote(url)))

    def init(self, extend=""):
        pass

    def homeContent(self, filter):
        classes = [
            {"type_id": "video", "type_name": "蜜桃视频"},
            {"type_id": "duanju", "type_name": "蜜桃短剧"},
            {"type_id": "hongtao", "type_name": "红桃短剧"},
            {"type_id": "caibian", "type_name": "擦边短剧"},
            {"type_id": "shortv", "type_name": "蜜桃动漫"},
            {"type_id": "guochan", "type_name": "国产精品"},
            {"type_id": "heiliao", "type_name": "黑料吃瓜"},
            {"type_id": "hbo", "type_name": "HBO精选"},
            {"type_id": "live", "type_name": "蜜桃直播"}
        ]

        filters = {
            "video": [
                {
                    "key": "cat",
                    "name": "分类",
                    "value": [
                        {"n": "最近更新", "v": "new"},
                        {"n": "新作上市", "v": "release"},
                        {"n": "中文字幕", "v": "chinese-subtitle"},
                        {"n": "麻豆传媒", "v": "madou"},
                        {"n": "无码流出", "v": "uncensored-leak"},
                        {"n": "FC2", "v": "fc2"},
                        {"n": "热门", "v": "monthly-hot"},
                        {"n": "VR", "v": "genres/VR"},
                        {"n": "HEYZO", "v": "heyzo"},
                        {"n": "东京热", "v": "tokyohot"},
                        {"n": "一本道", "v": "1pondo"},
                        {"n": "Caribbeancom", "v": "caribbeancom"},
                        {"n": "Caribbeancompr", "v": "caribbeancompr"},
                        {"n": "SIRO", "v": "siro"},
                        {"n": "LUXU", "v": "luxu"},
                        {"n": "TWAV", "v": "twav"},
                        {"n": "Furuke", "v": "furuke"},
                        {"n": "今日热门", "v": "today-hot"},
                        {"n": "本週热门", "v": "weekly-hot"}
                    ]
                }
            ],
            "duanju": [
                {
                    "key": "cat",
                    "name": "厂牌分类",
                    "value": [
                        {"n": "黄桃短剧", "v": "huangtao"},
                        {"n": "黄果短剧", "v": "huangguo"},
                        {"n": "野果短剧", "v": "yeguo"},
                        {"n": "橙果短剧", "v": "chengguo"},
                        {"n": "一直看短剧", "v": "yizk"},
                        {"n": "黄豆短剧", "v": "huangdou"},
                        {"n": "赤果短剧", "v": "chiguo"},
                        {"n": "怦然心动", "v": "pengran"},
                        {"n": "动漫", "v": "erciyuan"},
                        {"n": "金币专区", "v": "jinbi"},
                        {"n": "会员专区", "v": "huiyuan"}
                    ]
                },
                {
                    "key": "sub",
                    "name": "二级筛选",
                    "value": [
                        {"n": "全部/精选/推荐", "v": "0"},
                        {"n": "子类1(AI短剧/野果原创/黄豆原创/热门好剧/国漫)", "v": "1"},
                        {"n": "子类2(AI漫剧/真人短剧/UP原创/民国风月/日漫)", "v": "2"},
                        {"n": "子类3(魔改漫剧/大神精选/悬疑惊悚/动画同人)", "v": "3"},
                        {"n": "子类4(网红改编/单体作品/同人魔改/游戏同人)", "v": "4"},
                        {"n": "子类5(影视魔改/古典风月/排行榜)", "v": "5"},
                        {"n": "子类6(国漫AI/都市艳遇)", "v": "6"},
                        {"n": "子类7(魔改短剧/恋爱情感)", "v": "7"},
                        {"n": "子类8(爆爽逆袭)", "v": "8"},
                        {"n": "子类9(职场沉浮)", "v": "9"},
                        {"n": "子类10(家庭伦理)", "v": "10"},
                        {"n": "子类11(奇幻修仙)", "v": "11"}
                    ]
                }
            ],
            "hongtao": [
                {
                    "key": "cat",
                    "name": "频道",
                    "value": [
                        {"n": "红桃原创", "v": "zhenren"},
                        {"n": "甜宠言情", "v": "tc"},
                        {"n": "逆袭爽剧", "v": "nx"},
                        {"n": "古装传奇", "v": "gz"},
                        {"n": "都市生活", "v": "ds"},
                        {"n": "玄幻奇幻", "v": "xh"},
                        {"n": "悬疑热血", "v": "xy"},
                        {"n": "正经漫剧", "v": "manju"},
                        {"n": "未分类短剧", "v": "unclassified"}
                    ]
                },
                {
                    "key": "sub",
                    "name": "题材(原创专享)",
                    "value": [
                        {"n": "都市", "v": "0"},
                        {"n": "古装", "v": "1"},
                        {"n": "民国", "v": "2"},
                        {"n": "重生", "v": "3"},
                        {"n": "异能", "v": "4"}
                    ]
                }
            ],
            "caibian": [
                {
                    "key": "cat",
                    "name": "排序",
                    "value": [
                        {"n": "最新", "v": "0"},
                        {"n": "推荐", "v": "1"},
                        {"n": "全部", "v": "2"}
                    ]
                }
            ],
            "shortv": [
                {
                    "key": "cat",
                    "name": "源频道",
                    "value": [
                        {"n": "全部", "v": "all"},
                        {"n": "Hanime", "v": "Hanime"},
                        {"n": "NaughtyMachinima", "v": "NaughtyMachinima"},
                        {"n": "HS日本4K动漫", "v": "HS日本4K动漫"}
                    ]
                }
            ],
            "heiliao": [
                {
                    "key": "cat",
                    "name": "频道",
                    "value": [
                        {"n": "最新", "v": "0"},
                        {"n": "推荐", "v": "1"}
                    ]
                }
            ],
            "hbo": [
                {
                    "key": "cat",
                    "name": "剧集类型",
                    "value": [
                        {"n": "美剧", "v": "meiju"},
                        {"n": "韩剧", "v": "hanju"}
                    ]
                }
            ],
            "live": [
                {
                    "key": "cat",
                    "name": "分类与地区",
                    "value": [
                        {"n": "女主播", "v": "girls"},
                        {"n": "情侣", "v": "couples"},
                        {"n": "男主播", "v": "men"},
                        {"n": "跨性别", "v": "trans"},
                        {"n": "中国", "v": "cn"},
                        {"n": "日本", "v": "jp"},
                        {"n": "韩国", "v": "kr"},
                        {"n": "美国", "v": "us"},
                        {"n": "泰国", "v": "th"},
                        {"n": "越南", "v": "vn"},
                        {"n": "俄罗斯", "v": "ru"}
                    ]
                }
            ]
        }

        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        cat = extend.get("cat", "")
        sub = extend.get("sub", "")
        
        src_map = {
            "huangtao": "duoju86",
            "huangguo": "huangguo",
            "yeguo": "duoju86",
            "chengguo": "duoju86",
            "yizk": "duoju86",
            "huangdou": "huangdou",
            "chiguo": "chiguo",
            "pengran": "pengran",
            "erciyuan": "huangdou",
            "jinbi": "huangdou",
            "huiyuan": "huangdou",
            "zhenren": "huangdou",
            "tc": "duoju89",
            "nx": "duoju89",
            "gz": "duoju89",
            "ds": "duoju89",
            "xh": "duoju89",
            "xy": "duoju89",
            "manju": "huangdou",
            "unclassified": "duoju89",
            "meiju": "huangdou",
            "hanju": "huangdou"
        }

        params = {
            "key": tid,
            "page": page
        }

        src = "huangdou"
        if tid == "duanju":
            cat_val = cat if cat else "huangtao"
            src = src_map.get(cat_val, "duoju86")
            params["cat"] = cat_val
            params["src"] = src
            if sub:
                params["sub"] = int(sub) if str(sub).isdigit() else sub
            else:
                params["sub"] = 0
        elif tid == "hongtao":
            cat_val = cat if cat else "zhenren"
            src = src_map.get(cat_val, "huangdou")
            params["cat"] = cat_val
            params["src"] = src
            if cat_val == "zhenren":
                params["sub"] = int(sub) if str(sub).isdigit() else 0
            else:
                params["sub"] = 0
        elif tid == "hbo":
            cat_val = cat if cat else "meiju"
            src = "huangdou"
            params["cat"] = cat_val
            params["src"] = src
            params["sub"] = 0
        elif tid == "caibian":
            cat_val = cat if cat else "0"
            src = "huangdou"
            params["cat"] = cat_val
            params["src"] = src
            params["nav"] = "caibian"
            params["sub"] = int(cat_val) if str(cat_val).isdigit() else 0
        elif tid == "guochan":
            src = "guochan"
            params["src"] = src
        elif tid == "video":
            src = "missav"
            params["src"] = src
            if cat:
                params["cat"] = cat
        elif tid == "shortv":
            src = "dongman"
            params["src"] = src
            if cat:
                params["cat"] = cat
        else:
            if cat:
                params["cat"] = cat
            if extend.get("src"):
                src = extend.get("src")
                params["src"] = src

        res = self._signed_fetch("/api/module", params=params, timeout=10)
        
        cards = []
        has_more = False
        pagecount = page
        
        try:
            data = json.loads(res["content"])
            raw_list = data.get("list", [])
            has_more = bool(data.get("has_more", False))
            if has_more:
                pagecount = page + 1
            
            cover_mod = src if tid in ("duanju", "hongtao", "hbo") else tid
            for item in raw_list:
                item_id = str(item.get("id") or item.get("code") or "")
                if not item_id:
                    continue
                
                title = str(item.get("title") or item_id).strip()
                cover_url = item.get("cover_n") or item.get("cover") or ""
                pic = self._format_cover(cover_mod, cover_url)
                
                raw_remark = item.get("remark") or item.get("desc") or ""
                if raw_remark:
                    remarks = "🦋 蝴蝶影视 · %s" % raw_remark.strip()
                else:
                    remarks = "🦋 蝴蝶影视"
                
                card = {
                    "vod_id": "%s@@%s@@%s" % (tid, item_id, src),
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": remarks
                }
                cards.append(card)
        except Exception:
            pass

        return {
            "list": cards,
            "page": page,
            "pagecount": pagecount,
            "limit": len(cards),
            "total": 9999 if has_more else (page * len(cards))
        }

    def detailContent(self, ids):
        vod_id = ids[0] if isinstance(ids, list) else ids
        parts = vod_id.split("@@")
        
        mod = parts[0]
        real_id = parts[1] if len(parts) > 1 else vod_id
        src = parts[2] if len(parts) > 2 else ""

        detail_path = "/api/detail/%s/%s" % (mod, urllib.parse.quote(real_id))
        params = {}
        if src:
            params["src"] = src

        res = self._signed_fetch(detail_path, params=params, timeout=10)
        
        vod = {
            "vod_id": vod_id,
            "vod_name": real_id,
            "vod_pic": "",
            "vod_bg": "",
            "vod_background": "",
            "vod_banner": "",
            "vod_year": "",
            "vod_area": "蜜桃",
            "vod_remarks": "🦋 蝴蝶影视",
            "vod_actor": "🦋 TG群: @tvshare23",
            "vod_director": "🦋 蝴蝶影视",
            "vod_content": "🦋 蝴蝶影视提醒：本影片仅供测试交流，请勿用于非法用途！",
            "vod_play_from": "蜜桃专线",
            "vod_play_url": ""
        }

        play_urls = []
        try:
            data = json.loads(res["content"])
            det = data.get("detail", {})
            if det:
                title = det.get("title") or real_id
                vod["vod_name"] = str(title).strip()
                
                cover_mod = src if mod in ("duanju", "hongtao", "hbo") else mod
                cover_raw = det.get("cover") or ""
                pic_url = self._format_cover(cover_mod, cover_raw)
                vod["vod_pic"] = pic_url
                vod["vod_bg"] = pic_url
                vod["vod_background"] = pic_url
                vod["vod_banner"] = pic_url
                
                if det.get("date"):
                    vod["vod_year"] = str(det["date"])
                
                raw_desc = det.get("desc") or ""
                vod["vod_content"] = "🦋 蝴蝶影视官方交流群: @tvshare23\n\n%s" % raw_desc
                
                episodes = det.get("episodes", [])
                if episodes:
                    for ep_item in episodes:
                        ep_no = str(ep_item.get("ep", "1"))
                        raw_name = str(ep_item.get("name") or ("第%s集" % ep_no))
                        if raw_name.isdigit():
                            raw_name = "第%s集" % raw_name
                        
                        is_lock = ep_item.get("lock")
                        if is_lock:
                            ep_display = "%s[预告10s]" % raw_name
                        else:
                            ep_display = raw_name
                        
                        play_token = "%s@@%s@@%s@@%s" % (mod, real_id, ep_no, src)
                        play_urls.append("%s$%s" % (ep_display, play_token))
                else:
                    play_token = "%s@@%s@@1@@%s" % (mod, real_id, src)
                    play_urls.append("正片$%s" % play_token)
        except Exception:
            play_token = "%s@@%s@@1@@%s" % (mod, real_id, src)
            play_urls.append("正片$%s" % play_token)

        vod["vod_play_url"] = "#".join(play_urls)
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        parts = id.split("@@")
        mod = parts[0]
        real_id = parts[1] if len(parts) > 1 else id
        ep = parts[2] if len(parts) > 2 else "1"
        src = parts[3] if len(parts) > 3 else ""

        play_path = "/api/play/%s/%s/%s" % (mod, urllib.parse.quote(real_id), ep)
        params = {}
        if src:
            params["src"] = src

        res = self._signed_fetch(play_path, params=params, timeout=10)
        
        final_url = ""
        try:
            data = json.loads(res["content"])
            pl = data.get("play", {})
            raw_src = pl.get("src") or ""
            raw_proxy = pl.get("src_proxy") or ""
            
            if "preview-r10" in raw_src and raw_proxy:
                chosen = raw_proxy
            else:
                chosen = raw_src or raw_proxy
            
            if chosen:
                if chosen.startswith("/"):
                    final_url = urllib.parse.urljoin(self.site_url, chosen)
                else:
                    final_url = chosen
        except Exception:
            pass

        if final_url:
            lower_url = final_url.lower()
            if ".m3u8" not in lower_url and ".mp4" not in lower_url and ".mpd" not in lower_url:
                sep = "&" if "?" in final_url else "?"
                final_url = final_url + sep + "format=.m3u8"

        headers = {
            "User-Agent": self.headers["User-Agent"],
            "Referer": "https://honeypeach.cc/"
        }
        
        if "hembed.com" in final_url or "hanime" in final_url:
            headers["Referer"] = "https://hanime1.me/"

        return {
            "parse": 0,
            "url": final_url,
            "header": headers
        }

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        search_mods = ["video", "duanju", "hongtao", "hbo", "shortv", "guochan", "caibian"]
        
        cards = []
        for mod in search_mods:
            params = {
                "key": mod,
                "kw": key,
                "page": page
            }
            res = self._signed_fetch("/api/search", params=params, timeout=8)
            try:
                data = json.loads(res["content"])
                raw_list = data.get("list", [])
                for item in raw_list:
                    item_id = str(item.get("id") or item.get("code") or "")
                    if not item_id:
                        continue
                    
                    item_src = str(item.get("src") or mod)
                    title = str(item.get("title") or item_id).strip()
                    cover_url = item.get("cover_n") or item.get("cover") or ""
                    pic = self._format_cover(item_src if mod in ("duanju", "hongtao", "hbo") else mod, cover_url)
                    
                    raw_remark = item.get("remark") or item.get("desc") or ""
                    if raw_remark:
                        remarks = "🦋 蝴蝶影视 · %s" % raw_remark.strip()
                    else:
                        remarks = "🦋 蝴蝶影视"
                    
                    card = {
                        "vod_id": "%s@@%s@@%s" % (mod, item_id, item_src),
                        "vod_name": title,
                        "vod_pic": pic,
                        "vod_remarks": remarks
                    }
                    cards.append(card)
            except Exception:
                continue

        return {
            "list": cards,
            "page": page,
            "pagecount": page + 1 if len(cards) >= 10 else page,
            "limit": len(cards),
            "total": len(cards)
        }

    def action(self, action):
        return None

    def liveContent(self):
        return {}

    def localProxy(self, params):
        return [200, "text/plain", ""]

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return False

    def destroy(self):
        pass