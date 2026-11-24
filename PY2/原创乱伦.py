# -*- coding: utf-8 -*-
import base64
import json
import re
import ssl
import time
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

RECT_178_STYLE = {"type": "rect", "ratio": 1.78}

CLASSES_CACHE = [
    {"type_id": "2510", "type_name": "日韩精品"},
    {"type_id": "2509", "type_name": "日韩无码"},
    {"type_id": "2508", "type_name": "女优明星"},
    {"type_id": "2507", "type_name": "日韩超清"},
    {"type_id": "2506", "type_name": "异族风情"},
    {"type_id": "2505", "type_name": "国产超清"},
    {"type_id": "2504", "type_name": "国产自拍"},
    {"type_id": "2503", "type_name": "主播诱惑"},
    {"type_id": "2502", "type_name": "探花约炮"},
    {"type_id": "2501", "type_name": "偷拍偷窥"},
    {"type_id": "2500", "type_name": "网曝吃瓜"},
    {"type_id": "2499", "type_name": "抖阴短片"},
    {"type_id": "2498", "type_name": "传媒剧情"},
    {"type_id": "2497", "type_name": "自拍偷拍"},
    {"type_id": "2496", "type_name": "国内换脸"},
    {"type_id": "2495", "type_name": "吃瓜黑料"},
    {"type_id": "2494", "type_name": "直播裸聊"},
    {"type_id": "2493", "type_name": "反差母狗"},
    {"type_id": "2492", "type_name": "野战车震"},
    {"type_id": "2491", "type_name": "野外露出"},
    {"type_id": "2490", "type_name": "原创乱伦"},
    {"type_id": "2489", "type_name": "粉穴学妹"},
    {"type_id": "2488", "type_name": "撸管必看"},
    {"type_id": "2487", "type_name": "偷情少妇"},
    {"type_id": "2486", "type_name": "乱伦毁三观"},
    {"type_id": "2485", "type_name": "国产精品"},
    {"type_id": "2484", "type_name": "华语AV"},
    {"type_id": "2483", "type_name": "黑料吃瓜"},
    {"type_id": "2482", "type_name": "国产裸聊"},
    {"type_id": "2481", "type_name": "国产盗摄"},
    {"type_id": "2480", "type_name": "强奸迷奸"},
    {"type_id": "2479", "type_name": "网曝黑料"},
    {"type_id": "2478", "type_name": "国产厂牌"},
    {"type_id": "2477", "type_name": "丝袜制服"},
    {"type_id": "2476", "type_name": "主播网红"},
    {"type_id": "2475", "type_name": "群交多P"},
    {"type_id": "2474", "type_name": "学生萝莉"},
    {"type_id": "2473", "type_name": "口交自慰"},
    {"type_id": "2472", "type_name": "国产三级"},
    {"type_id": "2471", "type_name": "精品推荐"},
    {"type_id": "2470", "type_name": "国产色情"},
    {"type_id": "2469", "type_name": "网曝门"},
    {"type_id": "2468", "type_name": "SM调教"},
    {"type_id": "2467", "type_name": "中文字幕"},
    {"type_id": "2466", "type_name": "麻豆视频"},
    {"type_id": "2465", "type_name": "91制片厂"},
    {"type_id": "2464", "type_name": "天美传媒"},
    {"type_id": "2463", "type_name": "蜜桃传媒"},
    {"type_id": "2462", "type_name": "皇家华人"},
    {"type_id": "2461", "type_name": "星空传媒"},
    {"type_id": "2460", "type_name": "焦点影业"},
    {"type_id": "2459", "type_name": "海角社区"},
    {"type_id": "2458", "type_name": "成人头条"},
    {"type_id": "2457", "type_name": "乌鸦传媒"},
    {"type_id": "2456", "type_name": "兔子先生"},
    {"type_id": "2455", "type_name": "杏吧原创"},
    {"type_id": "2454", "type_name": "玩偶姐姐"},
    {"type_id": "2453", "type_name": "MINI传媒"},
    {"type_id": "2452", "type_name": "大象传媒"},
    {"type_id": "2451", "type_name": "开心鬼传媒"},
    {"type_id": "2450", "type_name": "萝莉社"},
    {"type_id": "2449", "type_name": "性视界"},
    {"type_id": "2448", "type_name": "psycho"},
    {"type_id": "2447", "type_name": "糖心vlog"}
]

_AES_SBOX = (
    0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
    0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
    0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
    0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
    0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
    0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
    0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
    0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
    0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
    0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
    0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
    0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
    0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
    0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
    0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16
)
_AES_INV_SBOX = [0] * 256
for _i, _v in enumerate(_AES_SBOX):
    _AES_INV_SBOX[_v] = _i
_AES_INV_SBOX = tuple(_AES_INV_SBOX)
_AES_RCON = (0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1b,0x36)

def _aes_xtime(a):
    return (((a << 1) ^ 0x1b) & 0xff) if (a & 0x80) else ((a << 1) & 0xff)

def _aes_gmul(a, b):
    p = 0
    while b:
        if b & 1:
            p ^= a
        a = _aes_xtime(a)
        b >>= 1
    return p

_AES_M09 = tuple(_aes_gmul(i, 0x09) for i in range(256))
_AES_M0B = tuple(_aes_gmul(i, 0x0b) for i in range(256))
_AES_M0D = tuple(_aes_gmul(i, 0x0d) for i in range(256))
_AES_M0E = tuple(_aes_gmul(i, 0x0e) for i in range(256))

def _aes_expand_key(key):
    ek = list(key)
    for i in range(10):
        t = ek[-4:]
        t = t[1:] + t[:1]
        t = [_AES_SBOX[b] for b in t]
        t[0] ^= _AES_RCON[i]
        for _j in range(4):
            t = [t[k] ^ ek[-16+k] for k in range(4)]
            ek += t
    return [ek[i:i+16] for i in range(0, 176, 16)]

def _aes_decrypt_block(blk, rk):
    s = [a ^ b for a, b in zip(blk, rk[10])]
    for r in range(9, 0, -1):
        s = [s[0],s[13],s[10],s[7],s[4],s[1],s[14],s[11],s[8],s[5],s[2],s[15],s[12],s[9],s[6],s[3]]
        s = [_AES_INV_SBOX[b] for b in s]
        s = [a ^ b for a, b in zip(s, rk[r])]
        o = [0] * 16
        for c in range(4):
            a0, a1, a2, a3 = s[c*4], s[c*4+1], s[c*4+2], s[c*4+3]
            o[c*4]   = _AES_M0E[a0] ^ _AES_M0B[a1] ^ _AES_M0D[a2] ^ _AES_M09[a3]
            o[c*4+1] = _AES_M09[a0] ^ _AES_M0E[a1] ^ _AES_M0B[a2] ^ _AES_M0D[a3]
            o[c*4+2] = _AES_M0D[a0] ^ _AES_M09[a1] ^ _AES_M0E[a2] ^ _AES_M0B[a3]
            o[c*4+3] = _AES_M0B[a0] ^ _AES_M0D[a1] ^ _AES_M09[a2] ^ _AES_M0E[a3]
        s = o
    s = [s[0],s[13],s[10],s[7],s[4],s[1],s[14],s[11],s[8],s[5],s[2],s[15],s[12],s[9],s[6],s[3]]
    s = [_AES_INV_SBOX[b] for b in s]
    return bytes(a ^ b for a, b in zip(s, rk[0]))

class FastAesCbc(object):
    def __init__(self, key, iv):
        self.rk = _aes_expand_key(key)
        self.iv = bytes(iv)

    def decrypt(self, data):
        out = bytearray()
        prev = self.iv
        for i in range(0, len(data) - 15, 16):
            blk = _aes_decrypt_block(data[i:i+16], self.rk)
            out += bytes(a ^ b for a, b in zip(blk, prev))
            prev = data[i:i+16]
        if not out:
            return b""
        pad = out[-1]
        if 1 <= pad <= 16 and bytes(out[-pad:]) == bytes([pad]) * pad:
            del out[-pad:]
        return bytes(out)

class Spider(BaseSpider):
    def __init__(self):
        super(Spider, self).__init__()
        self.base_url = "https://cu8qt2.yclla.top"
        self.key = b"a9yX32LpQvUt7wBc"
        self.iv = b"N7cPk2Bv38hWqFzM"
        self.cipher_engine = FastAesCbc(self.key, self.iv)

    def init(self, extend=""):
        pass

    def homeContent(self, filter):
        return {
            "class": CLASSES_CACHE,
            "filters": {},
            "style": RECT_178_STYLE
        }

    def homeVideoContent(self):
        return self.categoryContent("2510", "1", {}, {})

    def _fetch_url(self, url, headers=None, timeout=8):
        req_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Referer": "%s/" % self.base_url,
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Connection": "close"
        }
        if headers:
            req_headers.update(headers)

        ctx = ssl._create_unverified_context()
        req = urllib.request.Request(url, headers=req_headers)
        start_t = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                elapsed_ms = int((time.time() - start_t) * 1000)
                code = resp.getcode()
                raw = resp.read()
                charset = resp.headers.get_content_charset() or "utf-8"
                text = raw.decode(charset, errors="ignore")
                return {
                    "status_code": code,
                    "elapsed_ms": elapsed_ms,
                    "body": text,
                    "error": ""
                }
        except urllib.error.HTTPError as he:
            err_body = ""
            try:
                err_body = he.read().decode("utf-8", errors="ignore")
            except Exception:
                pass
            return {
                "status_code": he.code,
                "elapsed_ms": int((time.time() - start_t) * 1000),
                "body": err_body,
                "error": "HTTP %s: %s" % (he.code, str(he.reason))
            }
        except Exception as e:
            return {
                "status_code": 0,
                "elapsed_ms": int((time.time() - start_t) * 1000),
                "body": "",
                "error": str(e)
            }

    def _decrypt_cipher(self, cipher_b64):
        try:
            raw_cipher = base64.b64decode(cipher_b64)
            decrypted = self.cipher_engine.decrypt(raw_cipher)
            return json.loads(decrypted.decode("utf-8", errors="ignore"))
        except Exception:
            return {}

    def categoryContent(self, tid, pg, filter, extend):
        page_num = str(pg or "1")
        target_tid = str(tid or "2510")

        url = "%s/api/videos?category_id=%s&page=%s&limit=20" % (self.base_url, target_tid, page_num)
        res = self._fetch_url(url, timeout=8)

        cards = []
        pagecount = 1
        total = 0

        if res["status_code"] == 200 and res["body"]:
            try:
                js = json.loads(res["body"])
                cipher_str = js.get("cipher", "")
                if cipher_str:
                    plain_obj = self._decrypt_cipher(cipher_str)
                    data_block = plain_obj.get("data", {})
                    raw_list = data_block.get("list", [])
                    total = data_block.get("total", len(raw_list))
                    pagecount = data_block.get("pages", 1)

                    for item in raw_list:
                        pic_raw = str(item.get("cover_url", "")).strip()
                        if not pic_raw or not pic_raw.startswith("http"):
                            continue

                        title = str(item.get("title", "")).strip()
                        if not title or any(k in title for k in ["澳门", "博彩", "注册送", "加微", "客服", "下载APP"]):
                            continue

                        vid = str(item.get("id", ""))
                        if not vid:
                            continue

                        hits = item.get("hits", 0)
                        likes = item.get("likes", 0)
                        
                        if hits:
                            if hits >= 10000:
                                remarks = "原创乱伦 · 🔥 %.1f万" % (hits / 10000.0)
                            else:
                                remarks = "原创乱伦 · 🔥 %s" % hits
                        elif likes:
                            remarks = "原创乱伦 · 👍 %s" % likes
                        else:
                            remarks = "原创乱伦 · HD超清"

                        pic = "%s@Referer=https://cu8qt2.yclla.top/" % pic_raw

                        cards.append({
                            "vod_id": vid,
                            "vod_name": title,
                            "vod_pic": pic,
                            "vod_remarks": remarks,
                            "style": RECT_178_STYLE
                        })
            except Exception:
                pass

        return {
            "page": int(page_num),
            "pagecount": pagecount,
            "limit": len(cards),
            "total": total,
            "list": cards,
            "style": RECT_178_STYLE
        }

    def _clean_m3u8_url(self, raw_str):
        if not raw_str:
            return ""
        m = re.search(r'(https?://(?!localhost)[^\s"\'\$<>]+?\.m3u8[^\s"\'\$<>]*)', raw_str)
        if m:
            return m.group(1).replace("\\u002F", "/").replace("\\/", "")
        return ""

    def detailContent(self, ids):
        vid = str(ids[0] if isinstance(ids, list) and ids else ids)

        vod_detail = {
            "vod_id": vid,
            "vod_name": "视频 %s" % vid,
            "vod_pic": "",
            "vod_director": "原创乱伦",
            "vod_actor": "原创乱伦",
            "vod_play_from": "原创乱伦",
            "vod_play_url": "",
            "vod_content": "原创乱伦专线加速播放"
        }

        api_url = "%s/api/movie?id=%s" % (self.base_url, vid)
        res = self._fetch_url(api_url, timeout=8)

        if res["status_code"] == 200 and res["body"]:
            try:
                js = json.loads(res["body"])
                cipher_str = js.get("cipher", "")
                plain = self._decrypt_cipher(cipher_str) if cipher_str else js
                data_obj = plain.get("data", plain)
                
                info = data_obj.get("info", data_obj) if isinstance(data_obj, dict) else {}
                if isinstance(info, dict):
                    title = info.get("title")
                    if title:
                        vod_detail["vod_name"] = str(title)

                    cover = info.get("cover_url")
                    if cover:
                        vod_detail["vod_pic"] = "%s@Referer=https://cu8qt2.yclla.top/" % cover

                    desc = info.get("description") or info.get("intro") or ""
                    if desc:
                        vod_detail["vod_content"] = "原创乱伦专线直连" % desc

                    clean_url = self._clean_m3u8_url(info.get("play_url", ""))
                    if clean_url:
                        vod_detail["vod_play_url"] = "全集$%s" % clean_url
            except Exception:
                pass

        return {"list": [vod_detail]}

    def playerContent(self, flag, id, vipFlags):
        play_url = str(id or "").strip()
        clean_url = self._clean_m3u8_url(play_url) or play_url

        return {
            "parse": 0,
            "playUrl": "",
            "url": clean_url,
            "header": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                "Referer": "https://cu8qt2.yclla.top/",
                "Origin": "https://cu8qt2.yclla.top"
            }
        }

    def searchContent(self, key, quick, pg="1"):
        return {"list": [], "style": RECT_178_STYLE}

    def action(self, action):
        return ""

    def liveContent(self):
        return ""

    def localProxy(self, params):
        return [200, "text/plain", "OK"]

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return False

    def destroy(self):
        pass