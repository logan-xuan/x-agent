# 博客系统

这是一个基于 Node.js + Express + SQLite 的简单博客系统后端。

## 功能特性

- 创建、读取、更新、删除文章（CRUD）
- 分页显示文章列表
- 文章搜索功能
- 图片上传支持
- RESTful API 接口

## 技术栈

- Node.js
- Express.js
- SQLite3
- Body-parser
- Multer (文件上传)
- Cors
- Moment.js

## 安装步骤

1. 确保已安装 Node.js 和 npm

2. 克隆或下载此项目到本地

3. 进入项目目录并安装依赖：
   ```bash
   cd blog-system
   npm install
   ```

4. 启动服务：
   ```bash
   # 开发模式
   npm run dev
   
   # 生产模式
   npm start
   ```

## API 接口

### 获取所有文章
```
GET /api/posts?page=1&limit=10
```

### 获取单篇文章
```
GET /api/posts/:id
```

### 创建文章
```
POST /api/posts
Content-Type: multipart/form-data
Form Data: title, content, author, image (可选)
```

### 更新文章
```
PUT /api/posts/:id
Content-Type: multipart/form-data
Form Data: title, content, author, image (可选)
```

### 删除文章
```
DELETE /api/posts/:id
```

### 搜索文章
```
GET /api/search?q=search_term
```

## 响应格式

成功响应通常如下：
```json
{
  "posts": [...],
  "pagination": {
    "currentPage": 1,
    "totalPages": 1,
    "totalPosts": 5,
    "hasNext": false,
    "hasPrev": false
  }
}
```

错误响应：
```json
{
  "error": "Error message"
}
```

## 文件结构

- `server.js`: 主服务文件
- `package.json`: 项目配置文件
- `uploads/`: 存放上传的图片文件
- `blog.db`: SQLite 数据库文件

## 注意事项

- 图片上传目录 `uploads` 会自动创建
- 数据库存储在 `blog.db` 文件中
- 默认端口为 3000，可通过环境变量修改