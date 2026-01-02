# 微博搜索系统 API 文档

本文档详细描述了微博搜索系统的 API 接口用法，包括接口地址、请求方式、请求参数及返回示例。

## 服务信息

- **默认基础 URL**: `http://localhost:5000`
- **数据格式**: JSON

---

## 1. 配置 Cookie (必须)

在使用爬虫功能前，必须先配置有效的微博 Cookie。

- **接口地址**: `/api/config/cookie`
- **请求方式**: `POST`
- **功能**: 设置或更新爬虫使用的微博 Cookie。
- **请求头**: `Content-Type: application/json`

### 请求参数

| 参数名 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `cookie` | string | 是 | 微博网页版的完整 Cookie 字符串 |

### 请求示例

```json
{
    "cookie": "SINAGLOBAL=123456...; SUB=_2A25...;"
}
```

### 响应示例

```json
{
    "success": true,
    "message": "Cookie保存成功"
}
```

---

## 2. 获取当前 Cookie

- **接口地址**: `/api/config/cookie`
- **请求方式**: `GET`
- **功能**: 查看当前系统配置的 Cookie。

### 响应示例

```json
{
    "success": true,
    "cookie": "SINAGLOBAL=123456...; SUB=_2A25...;"
}
```

---

## 3. 创建搜索任务

- **接口地址**: `/api/spider/search`
- **请求方式**: `POST`
- **功能**: 创建一个后台异步任务，根据关键词和时间范围搜索微博。

### 请求参数

| 参数名 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `keyword` | string | 是 | 搜索关键词，例如 "网络强国" |
| `start_time` | string | 是 | 开始时间，格式 `YYYY-MM-DD HH:MM` |
| `end_time` | string | 是 | 结束时间，格式 `YYYY-MM-DD HH:MM` |
| `is_split_by_hour` | boolean | 否 | 是否按小时切分任务（默认 false）。对于热门话题建议开启，可获取更多数据，但速度较慢。 |

### 请求示例

```json
{
    "keyword": "网络强国",
    "start_time": "2023-10-01 00:00",
    "end_time": "2023-10-02 00:00",
    "is_split_by_hour": false
}
```

### 响应示例

```json
{
    "success": true,
    "task_id": "task_1672531200000"
}
```

> **注意**: 请保存返回的 `task_id`，用于后续查询任务状态和获取结果。

---

## 4. 查询任务状态与结果

- **接口地址**: `/api/spider/tasks/<task_id>`
- **请求方式**: `GET`
- **功能**: 获取指定任务的运行状态、日志及抓取到的数据。

### url 参数

| 参数名 | 说明 |
| :--- | :--- |
| `task_id` | 任务 ID (创建任务时返回) |

### 响应示例 (运行中)

```json
{
    "status": "running",
    "count": 5,
    "logs": [
        {
            "time": "10:00:01",
            "message": "已找到 5 条结果"
        }
    ],
    "results": [...]
}
```

### 响应示例 (已完成)

```json
{
    "status": "completed",
    "count": 100,
    "logs": [...],
    "results": [
        {
            "_id": "4826312651310475",
            "content": "微博正文内容...",
            "user": {
                "nick_name": "用户昵称",
                ...
            },
            "created_at": "2023-10-01 12:30:00",
            ...
        },
        ...
    ]
}
```

### 状态码说明 (`status` 字段)

- `running`: 正在运行
- `completed`: 已完成
- `stopped`: 已手动停止
- `error`: 发生错误（此时会有 `error` 字段说明原因）
- `not_found`: 任务 ID 不存在

---

## 5. 停止任务

- **接口地址**: `/api/spider/tasks/<task_id>/stop`
- **请求方式**: `POST`
- **功能**: 停止正在运行的任务。

### 响应示例

```json
{
    "success": true,
    "message": "停止请求已发送"
}
```

---

## 6. 获取用户信息

- **接口地址**: `/api/spider/user/<user_id>`
- **请求方式**: `GET`
- **功能**: 直接获取指定用户的详细公开信息。

### url 参数

| 参数名 | 说明 |
| :--- | :--- |
| `user_id` | 微博用户 ID (数字 ID) |

### 响应示例

```json
{
    "success": true,
    "data": {
        "_id": "1749127163",
        "nick_name": "雷军",
        "followers_count": 22756103,
        "description": "小米董事长...",
        "verified": true,
        "gender": "m",
        ...
    }
}
```

### 错误响应

如果 Cookie 失效或用户不存在：

```json
{
    "success": false,
    "error": "获取用户信息失败"
}
```

---

## 常见问题

1. **API 返回 "Cookie未配置"**
   - 请先调用 `/api/config/cookie` 接口设置有效的微博 Cookie。

2. **搜索结果为空**
   - 检查时间范围设置是否正确。
   - 检查 Cookie 是否过期（微博 Cookie 有效期较短，建议定期更新）。
   - 检查关键词是否能搜索到内容。

3. **如何获取 task_id？**
   - `task_id` 在调用 `/api/spider/search` 接口成功创建任务后，会在响应 JSON 中返回。

