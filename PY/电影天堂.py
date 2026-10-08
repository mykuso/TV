# coding=utf-8
"""
目标站: 电影天堂 (JSON API)
接口: http://caiji.dyttzyapi.com/api.php/provide/vod/from/dyttm3u8/at/json
说明: 标准 MacCMS JSON 接口解析
"""
import sys
import json
import urllib.parse
import re

sys.path.append('..')
from base.spider import Spider

class Spider(Spider):

    def init(self, extend=""):
        self.site_url = "http://caiji.dyttzyapi.com/api.php/provide/vod/from/dyttm3u8/at/json"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }

    # 格式化列表影片数据
    def _format_vod(self, vod):
        return {
            "vod_id": str(vod.get("vod_id", "")),
            "vod_name": vod.get("vod_name", ""),
            "vod_pic": vod.get("vod_pic", ""),
            "vod_remarks": vod.get("vod_remarks", "") or vod.get("vod_pubdate", "")
        }

    # ==================== 首页分类接口 ====================
    def homeContent(self, filter):
        url = f"{self.site_url}?ac=list"
        resp = self.fetch(url, headers=self.headers)
        
        classes = []
        if resp:
            try:
                data = json.loads(resp.text)
                for c in data.get('class', []):
                    classes.append({
                        "type_id": str(c.get('type_id')),
                        "type_name": c.get('type_name')
                    })
            except Exception:
                pass
                
        # 生成对应的空 filters 结构以避免某些客户端报错
        filters = {item["type_id"]: [] for item in classes}
        
        return {"class": classes, "filters": filters}

    # ==================== 首页视频列表接口 ====================
    def homeVideoContent(self):
        url = f"{self.site_url}?ac=videolist"
        resp = self.fetch(url, headers=self.headers)
        video_list = []
        if resp:
            try:
                data = json.loads(resp.text)
                video_list = [self._format_vod(v) for v in data.get('list', [])]
            except Exception:
                pass
        return {"list": video_list}

    # ==================== 分类列表 ====================
    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        url = f"{self.site_url}?ac=videolist&t={tid}&pg={page}"
        
        resp = self.fetch(url, headers=self.headers)
        if not resp:
            return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}
            
        try:
            data = json.loads(resp.text)
            video_list = [self._format_vod(v) for v in data.get('list', [])]
            return {
                "list": video_list,
                "page": data.get("page", page),
                "pagecount": data.get("pagecount", 1),
                "limit": data.get("limit", 20),
                "total": data.get("total", 0)
            }
        except Exception:
            return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}

    # ==================== 详情 ====================
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
            
        vod_id = ids[0]
        # 【核心修正】這裡必須用 ac=detail，否則官方接口不會返回 vod_play_url (播放連結)
        url = f"{self.site_url}?ac=detail&ids={vod_id}"
        
        resp = self.fetch(url, headers=self.headers)
        if not resp:
            return {"list": []}
            
        try:
            data = json.loads(resp.text)
            vod_list = data.get('list', [])
            if not vod_list:
                return {"list": []}
                
            vod = vod_list[0]
            
            # 防呆機制：如果來源方忘記給 play_from，設定一個預設值，否則播放器無法切換線路
            vod_play_from = vod.get("vod_play_from", "")
            if not vod_play_from:
                vod_play_from = "电影天堂"
                
            detail = {
                "vod_id": str(vod.get("vod_id", "")),
                "vod_name": vod.get("vod_name", ""),
                "vod_pic": vod.get("vod_pic", ""),
                "vod_remarks": vod.get("vod_remarks", ""),
                "vod_content": re.sub(r'<[^>]*>', '', vod.get("vod_blurb", "") or vod.get("vod_content", "")).strip(),
                "vod_director": vod.get("vod_director", ""),
                "vod_actor": vod.get("vod_actor", ""),
                "vod_year": vod.get("vod_year", ""),
                "vod_area": vod.get("vod_area", ""),
                "vod_play_from": vod_play_from,
                "vod_play_url": vod.get("vod_play_url", "")
            }
            return {"list": [detail]}
        except Exception:
            return {"list": []}

    # ==================== 搜索 ====================
    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        url = f"{self.site_url}?ac=videolist&wd={urllib.parse.quote(key)}&pg={page}"
        
        resp = self.fetch(url, headers=self.headers)
        if not resp:
            return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}
            
        try:
            data = json.loads(resp.text)
            video_list = [self._format_vod(v) for v in data.get('list', [])]
            return {
                "list": video_list,
                "page": data.get("page", page),
                "pagecount": data.get("pagecount", 1),
                "limit": data.get("limit", 20),
                "total": data.get("total", 0)
            }
        except Exception:
            return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}

    # ==================== 播放解析 ====================
    def playerContent(self, flag, id, vipFlags):
        # API 返回的通常是直鏈，直接傳給播放器即可
        return {
            "parse": 0,
            "playUrl": "",
            "url": id,
            "header": self.headers
        }