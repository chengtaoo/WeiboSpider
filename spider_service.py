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
                    if tweet_ids:
                        logger.info(f"使用方法2（全HTML搜索）找到 {len(tweet_ids)} 个推文ID")
                
                # 方法3: 尝试匹配 mid 属性 (如 mid="4829255386537989") - 针对新版页面结构
                if not tweet_ids:
                    mid_matches = re.findall(r'mid="(\d+)"', html)
                    if mid_matches:
                        tweet_ids = list(set(mid_matches))
                        logger.info(f"使用方法3（mid属性）找到 {len(tweet_ids)} 个推文ID")
                
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
            
            # 调试：检查响应内容是否为JSON
            try:
                content = response.text
                if not content.strip().startswith('{'):
                    logger.warning(f"推文详情响应内容不是JSON格式，可能Cookie已失效或触发验证。内容摘要: {content[:200]}")
                    return None
                data = json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析失败: {e}, 内容摘要: {response.text[:200]}")
                return None
            
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

    def get_user_info(self, user_id):
        """
        获取用户信息
        
        Args:
            user_id: 用户ID
            
        Returns:
            dict: 用户信息字典
        """
        try:
            logger.info(f"开始获取用户信息: {user_id}")
            
            # 1. 获取基本信息
            url = f"https://weibo.com/ajax/profile/info?uid={user_id}"
            response = self.session.get(url, timeout=15)
            response.encoding = 'utf-8'
            
            if response.status_code != 200:
                logger.warning(f"获取用户信息失败，状态码: {response.status_code}, URL: {url}")
                return None
            
            # 调试：检查响应内容是否为JSON
            try:
                content = response.text
                if not content.strip().startswith('{'):
                    logger.warning(f"响应内容不是JSON格式，可能Cookie已失效或触发验证。内容摘要: {content[:200]}")
                    return None
                data = json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析失败: {e}, 内容摘要: {response.text[:200]}")
                return None

            if 'ok' in data and data['ok'] != 1:
                logger.warning(f"API返回错误: {data.get('msg', 'unknown error')}, URL: {url}")
                return None
                
            if 'data' not in data or 'user' not in data['data']:
                logger.warning(f"返回数据格式异常: {url}")
                return None
                
            from weibospider.spiders.common import parse_user_info
            item = parse_user_info(data['data']['user'])
            
            # 2. 获取详细信息
            detail_url = f"https://weibo.com/ajax/profile/detail?uid={user_id}"
            detail_response = self.session.get(detail_url, timeout=15)
            detail_response.encoding = 'utf-8'
            
            if detail_response.status_code == 200:
                try:
                    detail_data = json.loads(detail_response.text)
                    if 'data' in detail_data:
                        d_data = detail_data['data']
                        item['birthday'] = d_data.get('birthday', '')
                        if 'created_at' not in item:
                            item['created_at'] = d_data.get('created_at', '')
                        item['desc_text'] = d_data.get('desc_text', '')
                        item['ip_location'] = d_data.get('ip_location', '')
                        if 'sunshine_credit' in d_data:
                            item['sunshine_credit'] = d_data.get('sunshine_credit', {}).get('level', '')
                        item['label_desc'] = [label['name'] for label in d_data.get('label_desc', [])]
                        if 'company' in d_data:
                            item['company'] = d_data['company']
                        if 'education' in d_data:
                            item['education'] = d_data['education']
                except Exception as e:
                    logger.warning(f"解析用户详细信息失败: {e}")
            
            logger.info(f"获取用户信息成功: {item.get('nick_name', user_id)}")
            return item
            
        except Exception as e:
            logger.error(f"获取用户信息异常 {user_id}: {e}", exc_info=True)
            return None

