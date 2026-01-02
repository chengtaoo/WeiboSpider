#!/usr/bin/env python
# encoding: utf-8
"""
微博搜索Web系统 API
"""
import os
import json
import threading
import time
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, url_for
from spider_service import WeiboSpiderService

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'weibo_spider_secret_key_2024'  # 用于session

# 全局变量存储爬取结果
crawl_results = {}
crawl_status = {}
crawl_stop_flags = {}  # 存储停止标志

def get_cookie():
    """获取Cookie"""
    try:
        cookie_path = os.path.join('weibospider', 'cookie.txt')
        if os.path.exists(cookie_path):
            with open(cookie_path, 'rt', encoding='utf-8') as f:
                return f.read().strip()
    except Exception as e:
        logger.error(f"读取Cookie失败: {e}")
    return None

def run_spider(keyword, start_time_str, end_time_str, is_split_by_hour, task_id):
    """在后台线程中运行爬虫"""
    try:
        # 创建停止标志
        stop_flag = threading.Event()
        crawl_stop_flags[task_id] = stop_flag
        
        crawl_status[task_id] = {'status': 'running', 'count': 0, 'error': None, 'logs': []}
        crawl_results[task_id] = []
        
        logger.info(f"任务 {task_id} 开始: 关键词={keyword}, 时间={start_time_str} 到 {end_time_str}")
        
        # 解析时间
        start_time = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M')
        end_time = datetime.strptime(end_time_str, '%Y-%m-%d %H:%M')
        
        cookie = get_cookie()
        if not cookie:
            raise Exception("Cookie未配置，请在Cookie配置中填入有效的Cookie")
        
        # 创建爬虫服务（传入停止标志）
        spider = WeiboSpiderService(cookie=cookie, stop_flag=stop_flag)
        
        # 进度回调函数
        def progress_callback(count, items):
            crawl_status[task_id]['count'] = count
            crawl_results[task_id] = items.copy()
            log_msg = f"已找到 {count} 条结果"
            if task_id in crawl_status:
                if 'logs' not in crawl_status[task_id]:
                    crawl_status[task_id]['logs'] = []
                crawl_status[task_id]['logs'].append({
                    'time': datetime.now().strftime('%H:%M:%S'),
                    'message': log_msg
                })
                # 只保留最近50条日志
                if len(crawl_status[task_id]['logs']) > 50:
                    crawl_status[task_id]['logs'] = crawl_status[task_id]['logs'][-50:]
        
        # 执行搜索
        results = spider.search_by_keyword(
            keyword=keyword,
            start_time=start_time,
            end_time=end_time,
            is_split_by_hour=is_split_by_hour,
            progress_callback=progress_callback
        )
        
        if stop_flag.is_set():
            crawl_status[task_id]['status'] = 'stopped'
            logger.info(f"任务 {task_id} 已停止")
        else:
            crawl_status[task_id]['status'] = 'completed'
            logger.info(f"任务 {task_id} 完成，共 {len(results)} 条结果")
        
        crawl_results[task_id] = results
        
    except Exception as e:
        import traceback
        error_msg = str(e) + '\n' + traceback.format_exc()
        logger.error(f"任务 {task_id} 失败: {error_msg}")
        crawl_status[task_id] = {'status': 'error', 'error': error_msg}
    finally:
        # 清理停止标志
        if task_id in crawl_stop_flags:
            del crawl_stop_flags[task_id]

@app.route('/')
def index():
    """首页"""
    return render_template('index.html')

# ==================== API 接口 ====================

@app.route('/api/spider/search', methods=['POST'])
@app.route('/api/search', methods=['POST']) # 兼容旧接口
def search():
    """
    开始搜索任务
    ---
    parameters:
      - name: keyword
        type: string
        required: true
        description: 搜索关键词
      - name: start_time
        type: string
        required: true
        description: 开始时间 (YYYY-MM-DD HH:MM)
      - name: end_time
        type: string
        required: true
        description: 结束时间 (YYYY-MM-DD HH:MM)
      - name: is_split_by_hour
        type: boolean
        description: 是否按小时切分搜索
    """
    data = request.json
    keyword = data.get('keyword', '').strip()
    start_time = data.get('start_time', '')
    end_time = data.get('end_time', '')
    is_split_by_hour = data.get('is_split_by_hour', False)
    
    if not keyword:
        return jsonify({'success': False, 'error': '请输入关键词'})
    
    if not start_time or not end_time:
        return jsonify({'success': False, 'error': '请选择时间范围'})
    
    # 生成任务ID
    task_id = f"task_{int(time.time() * 1000)}"
    
    # 在后台线程中运行爬虫
    thread = threading.Thread(
        target=run_spider,
        args=(keyword, start_time, end_time, is_split_by_hour, task_id)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'task_id': task_id})

@app.route('/api/spider/tasks/<task_id>', methods=['GET'])
@app.route('/api/status/<task_id>', methods=['GET']) # 兼容旧接口
def get_task_status(task_id):
    """
    获取任务状态
    ---
    parameters:
      - name: task_id
        type: string
        required: true
        description: 任务ID
    """
    if task_id not in crawl_status:
        return jsonify({'status': 'not_found'})
    
    status = crawl_status[task_id].copy()
    if task_id in crawl_results:
        status['results'] = crawl_results[task_id]
    
    return jsonify(status)

@app.route('/api/spider/tasks/<task_id>/stop', methods=['POST'])
@app.route('/api/stop/<task_id>', methods=['POST']) # 兼容旧接口
def stop_task(task_id):
    """
    停止任务
    ---
    parameters:
      - name: task_id
        type: string
        required: true
        description: 任务ID
    """
    if task_id in crawl_stop_flags:
        crawl_stop_flags[task_id].set()
        logger.info(f"收到停止请求: {task_id}")
        if task_id in crawl_status:
            crawl_status[task_id]['status'] = 'stopping'
        return jsonify({'success': True, 'message': '停止请求已发送'})
    else:
        return jsonify({'success': False, 'error': '任务不存在或已完成'})

@app.route('/api/spider/user/<user_id>', methods=['GET'])
def get_user_info_api(user_id):
    """
    获取用户信息
    ---
    parameters:
      - name: user_id
        type: string
        required: true
        description: 用户ID
    """
    cookie = get_cookie()
    if not cookie:
         return jsonify({'success': False, 'error': 'Cookie未配置'})
    
    spider = WeiboSpiderService(cookie=cookie)
    user_info = spider.get_user_info(user_id)
    
    if user_info:
        return jsonify({'success': True, 'data': user_info})
    else:
        return jsonify({'success': False, 'error': '获取用户信息失败'})

@app.route('/api/config/cookie', methods=['GET', 'POST'])
@app.route('/api/cookie', methods=['GET', 'POST']) # 兼容旧接口
def manage_cookie():
    """
    管理Cookie
    ---
    GET: 获取当前Cookie
    POST: 设置新Cookie
    """
    cookie_path = os.path.join('weibospider', 'cookie.txt')
    
    if request.method == 'GET':
        cookie = get_cookie()
        return jsonify({'success': True, 'cookie': cookie or ''})
    
    elif request.method == 'POST':
        # 保存Cookie
        data = request.json
        cookie = data.get('cookie', '').strip()
        
        try:
            os.makedirs('weibospider', exist_ok=True)
            with open(cookie_path, 'wt', encoding='utf-8') as f:
                f.write(cookie)
            return jsonify({'success': True, 'message': 'Cookie保存成功'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

@app.route('/api/docs')
def api_docs():
    """API文档简述"""
    return jsonify({
        'endpoints': {
            'POST /api/spider/search': '创建关键词搜索任务',
            'GET /api/spider/tasks/<task_id>': '获取任务状态和结果',
            'POST /api/spider/tasks/<task_id>/stop': '停止任务',
            'GET /api/spider/user/<user_id>': '获取用户信息',
            'GET/POST /api/config/cookie': '管理微博Cookie'
        }
    })

if __name__ == '__main__':
    # 确保output目录存在
    os.makedirs('output', exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)
