#!/usr/bin/env python
# encoding: utf-8
"""
启动Web服务器
"""
import os
import sys

# 确保在正确的目录
if __name__ == '__main__':
    # 检查必要的目录
    os.makedirs('templates', exist_ok=True)
    os.makedirs('output', exist_ok=True)
    os.makedirs('weibospider', exist_ok=True)
    
    # 确保日志文件可写
    log_file = 'spider.log'
    if os.path.exists(log_file):
        # 如果日志文件太大（>10MB），清空它
        if os.path.getsize(log_file) > 10 * 1024 * 1024:
            open(log_file, 'w').close()
    
    # 导入并运行Flask应用
    from app import app
    
    print("=" * 50)
    print("微博搜索Web系统")
    print("=" * 50)
    print("服务器启动中...")
    print("访问地址: http://localhost:5000")
    print("按 Ctrl+C 停止服务器")
    print("=" * 50)
    
    app.run(debug=True, host='0.0.0.0', port=5000)

