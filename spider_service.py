#!/usr/bin/env python
# encoding: utf-8
"""
微博爬虫服务模块（使用requests，不依赖Scrapy）
"""
import os
import json
import re
import time
import logging
import urllib.parse
import requests
from datetime import datetime, timedelta
from weibospider.spiders.common import parse_tweet_info, parse_long_tweet

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('spider.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class WeiboSpiderService:
    """微博爬虫服务类"""
    
    def __init__(self, cookie=None, stop_flag=None):
        self.cookie = cookie
        self.stop_flag = stop_flag  # 停止标志
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.13; rv:61.0) Gecko/20100101 Firefox/61.0',
            'Cookie': cookie or '',
            'Referer': 'https://s.weibo.com/'
        })
    
    def search_by_keyword(self, keyword, start_time, end_time, is_split_by_hour=False, 
                         progress_callback=None):
        """
        根据关键词搜索微博
        
        Args:
            keyword: 搜索关键词
            start_time: 开始时间 (datetime对象)
            end_time: 结束时间 (datetime对象)
            is_split_by_hour: 是否按小时切分
            progress_callback: 进度回调函数 callback(count, items)
        
        Returns:
            list: 搜索结果列表
        """
        results = []
        
        try:
            logger.info(f"开始搜索关键词: {keyword}, 时间范围: {start_time} 到 {end_time}")
            
            if not is_split_by_hour:
                # 不按小时切分
                _start_time = start_time.strftime("%Y-%m-%d-%H")
                _end_time = end_time.strftime("%Y-%m-%d-%H")
                # URL编码关键词
                encoded_keyword = urllib.parse.quote(keyword)
                url = f"https://s.weibo.com/weibo?q={encoded_keyword}&timescope=custom%3A{_start_time}%3A{_end_time}&page=1"
                logger.info(f"搜索URL: {url}")
                results.extend(self._crawl_search_page(url, keyword, progress_callback))
            else:
                # 按小时切分
                time_cur = start_time
                while time_cur < end_time:
                    if self.stop_flag and self.stop_flag.is_set():
                        logger.info("收到停止信号，停止搜索")
                        break
                    
                    _start_time = time_cur.strftime("%Y-%m-%d-%H")
                    _end_time = (time_cur + timedelta(hours=1)).strftime("%Y-%m-%d-%H")
                    encoded_keyword = urllib.parse.quote(keyword)
                    url = f"https://s.weibo.com/weibo?q={encoded_keyword}&timescope=custom%3A{_start_time}%3A{_end_time}&page=1"
                    results.extend(self._crawl_search_page(url, keyword, progress_callback))
                    time_cur = time_cur + timedelta(hours=1)
                    time.sleep(1)  # 避免请求过快
            
            logger.info(f"搜索完成，共找到 {len(results)} 条结果")
        
        except Exception as e:
            logger.error(f"搜索失败: {str(e)}", exc_info=True)
            raise Exception(f"搜索失败: {str(e)}")
        
        return results
    
    def _crawl_search_page(self, url, keyword, progress_callback=None):
        """爬取搜索页面"""
        results = []
        page = 1
        max_pages = 100  # 限制最大页数，避免无限循环
        
        while page <= max_pages:
            # 检查停止标志
            if self.stop_flag and self.stop_flag.is_set():
                logger.info("收到停止信号，停止爬取")
                break
            
            try:
                logger.info(f"正在爬取第 {page} 页: {url}")
                
                # 请求搜索页面
                response = self.session.get(url, timeout=15)
                response.encoding = 'utf-8'
                
                if response.status_code != 200:
                    logger.warning(f"请求失败，状态码: {response.status_code}")
                    break
                
                html = response.text
                
                # 检查是否有结果
                if '<p>抱歉，未找到相关结果。</p>' in html or '抱歉，未找到相关结果' in html:
                    logger.info("未找到相关结果")
                    break
                
                # 提取推文ID - 使用多种正则表达式模式
                tweets_infos = re.findall('<div class="from"\s+>(.*?)</div>', html, re.DOTALL)
                tweet_ids = []
                
                # 方法1: 在from div中查找（原始Scrapy方法，但去掉末尾空格要求）
                for tweets_info in tweets_infos:
                    # 尝试多种变体
                    ids = re.findall(r'weibo\.com/\d+/(.+?)\?refer_flag=1001030103_"', tweets_info)
                    if not ids:
                        # 尝试协议相对URL
                        ids = re.findall(r'//weibo\.com/\d+/(.+?)\?refer_flag=1001030103_"', tweets_info)
                    tweet_ids.extend(ids)
                
                # 方法2: 如果方法1没找到，直接在整个HTML中查找（更可靠）
                if not tweet_ids:
                    # 匹配所有包含refer_flag=1001030103_的推文链接
                    all_matches = re.findall(r'(?:https?://|//)?weibo\.com/(\d+)/([A-Za-z0-9]{6,})\?refer_flag=1001030103_', html)
                    tweet_ids = [tid[1] for tid in all_matches]  # 提取推文ID（第二个捕获组）
                    # 去重
                    tweet_ids = list(set(tweet_ids))
                    logger.info(f"使用方法2（全HTML搜索）找到 {len(tweet_ids)} 个推文ID")
                
                # 如果还是没找到，记录警告
                if not tweet_ids:
                    logger.warning("未找到任何推文ID，HTML可能已变化")
                    # 尝试最简单的模式作为最后手段
                    simple_matches = re.findall(r'weibo\.com/\d+/([A-Za-z0-9]{6,})\?', html)
                    tweet_ids = list(set(simple_matches))
                    if tweet_ids:
                        logger.info(f"使用简单模式找到 {len(tweet_ids)} 个推文ID")
                
                logger.info(f"第 {page} 页找到 {len(tweet_ids)} 条推文ID")
                
                # 获取每条推文详情
                for idx, tweet_id in enumerate(tweet_ids):
                    if self.stop_flag and self.stop_flag.is_set():
                        logger.info("收到停止信号，停止获取推文详情")
                        break
                    
                    try:
                        logger.debug(f"正在获取推文详情 {idx+1}/{len(tweet_ids)}: {tweet_id}")
                        tweet = self._get_tweet_detail(tweet_id, keyword)
                        if tweet:
                            results.append(tweet)
                            logger.info(f"成功获取推文: {tweet.get('_id', 'unknown')}")
                            if progress_callback:
                                progress_callback(len(results), results)
                        time.sleep(0.5)  # 避免请求过快
                    except Exception as e:
                        logger.warning(f"获取推文详情失败 {tweet_id}: {e}")
                        continue
                
                # 查找下一页
                next_page = re.search('<a href="(.*?)" class="next">下一页</a>', html)
                if next_page:
                    url = "https://s.weibo.com" + next_page.group(1)
                    page += 1
                    time.sleep(1)  # 页面间延迟
                else:
                    logger.info("没有更多页面")
                    break
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"网络请求失败 {url}: {e}")
                break
            except Exception as e:
                logger.error(f"爬取页面失败 {url}: {e}", exc_info=True)
                break
        
        logger.info(f"本批次爬取完成，共获取 {len(results)} 条结果")
        return results
    
    def _get_tweet_detail(self, tweet_id, keyword):
        """获取推文详情"""
        try:
            url = f"https://weibo.com/ajax/statuses/show?id={tweet_id}"
            response = self.session.get(url, timeout=15)
            response.encoding = 'utf-8'
            
            if response.status_code != 200:
                logger.warning(f"获取推文详情失败，状态码: {response.status_code}, URL: {url}")
                return None
            
            data = json.loads(response.text)
            
            # 检查返回数据 - API返回的数据直接在顶层，没有嵌套的data字段
            if 'ok' in data and data['ok'] != 1:
                logger.warning(f"API返回错误: {data.get('msg', 'unknown error')}, URL: {url}")
                return None
            
            # API返回的数据结构直接在顶层，包含mid, mblogid, user等字段
            # 如果没有mid字段，说明返回格式不对
            if 'mid' not in data:
                logger.warning(f"返回数据格式异常，缺少mid字段: {url}")
                logger.debug(f"返回数据的键: {list(data.keys())[:10]}")
                return None
            
            # 直接使用顶层数据，不需要data['data']
            item = parse_tweet_info(data)
            item['keyword'] = keyword
            
            # 如果是长微博，获取全文
            if item.get('isLongText'):
                try:
                    long_url = f"https://weibo.com/ajax/statuses/longtext?id={item['mblogid']}"
                    long_response = self.session.get(long_url, timeout=15)
                    long_response.encoding = 'utf-8'
                    if long_response.status_code == 200:
                        long_data = json.loads(long_response.text)
                        if 'data' in long_data:
                            item['content'] = long_data['data'].get('longTextContent', item.get('content', ''))
                            logger.debug(f"成功获取长微博全文: {item['mblogid']}")
                except Exception as e:
                    logger.warning(f"获取长微博失败 {item['mblogid']}: {e}")
            
            return item
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败 {tweet_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"获取推文详情异常 {tweet_id}: {e}", exc_info=True)
            return None

