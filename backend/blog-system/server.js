const express = require('express');
const bodyParser = require('body-parser');
const cors = require('cors');
const multer = require('multer');
const sqlite3 = require('sqlite3').verbose();
const moment = require('moment');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

// 中间件配置
app.use(cors());
app.use(bodyParser.json());
app.use(bodyParser.urlencoded({ extended: true }));
app.use('/uploads', express.static(path.join(__dirname, 'uploads')));

// 文件上传配置
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    cb(null, 'uploads/');
  },
  filename: (req, file, cb) => {
    const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1E9);
    cb(null, file.fieldname + '-' + uniqueSuffix + path.extname(file.originalname));
  }
});
const upload = multer({ storage: storage });

// 数据库初始化
const db = new sqlite3.Database('./blog.db', (err) => {
  if (err) {
    console.error(err.message);
  } else {
    console.log('Connected to the blog database.');
  }
});

// 创建文章表
db.run(`CREATE TABLE IF NOT EXISTS posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  author TEXT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  image_url TEXT
)`);

// API 路由

// 获取所有文章
app.get('/api/posts', (req, res) => {
  const { page = 1, limit = 10 } = req.query;
  const offset = (page - 1) * limit;
  
  db.all(
    `SELECT * FROM posts ORDER BY created_at DESC LIMIT ? OFFSET ?`,
    [limit, offset],
    (err, rows) => {
      if (err) {
        res.status(500).json({ error: err.message });
        return;
      }
      // 获取总数用于分页
      db.get('SELECT COUNT(*) as count FROM posts', (err, countRow) => {
        if (err) {
          res.status(500).json({ error: err.message });
          return;
        }
        res.json({
          posts: rows,
          pagination: {
            currentPage: parseInt(page),
            totalPages: Math.ceil(countRow.count / limit),
            totalPosts: countRow.count,
            hasNext: page * limit < countRow.count,
            hasPrev: page > 1
          }
        });
      });
    }
  );
});

// 根据ID获取单篇文章
app.get('/api/posts/:id', (req, res) => {
  const { id } = req.params;
  
  db.get(
    'SELECT * FROM posts WHERE id = ?',
    [id],
    (err, row) => {
      if (err) {
        res.status(500).json({ error: err.message });
        return;
      }
      if (!row) {
        res.status(404).json({ message: 'Post not found' });
        return;
      }
      res.json(row);
    }
  );
});

// 创建新文章
app.post('/api/posts', upload.single('image'), (req, res) => {
  const { title, content, author } = req.body;
  const imageUrl = req.file ? `/uploads/${req.file.filename}` : null;
  
  if (!title || !content || !author) {
    return res.status(400).json({ error: 'Title, content, and author are required' });
  }
  
  const stmt = db.prepare(
    'INSERT INTO posts (title, content, author, image_url) VALUES (?, ?, ?, ?)'
  );
  
  stmt.run([title, content, author, imageUrl], function(err) {
    if (err) {
      res.status(500).json({ error: err.message });
      return;
    }
    res.status(201).json({
      id: this.lastID,
      title,
      content,
      author,
      image_url: imageUrl,
      created_at: moment().format('YYYY-MM-DD HH:mm:ss')
    });
  });
  
  stmt.finalize();
});

// 更新文章
app.put('/api/posts/:id', upload.single('image'), (req, res) => {
  const { id } = req.params;
  const { title, content, author } = req.body;
  let imageUrl = req.body.existing_image_url; // 如果没有上传新图片，保留现有图片URL
  
  if (req.file) {
    imageUrl = `/uploads/${req.file.filename}`;
  }
  
  if (!title || !content || !author) {
    return res.status(400).json({ error: 'Title, content, and author are required' });
  }
  
  const stmt = db.prepare(
    'UPDATE posts SET title = ?, content = ?, author = ?, image_url = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?'
  );
  
  stmt.run([title, content, author, imageUrl, id], function(err) {
    if (err) {
      res.status(500).json({ error: err.message });
      return;
    }
    
    if (this.changes === 0) {
      res.status(404).json({ message: 'Post not found' });
      return;
    }
    
    res.json({
      id: parseInt(id),
      title,
      content,
      author,
      image_url: imageUrl,
      updated_at: moment().format('YYYY-MM-DD HH:mm:ss')
    });
  });
  
  stmt.finalize();
});

// 删除文章
app.delete('/api/posts/:id', (req, res) => {
  const { id } = req.params;
  
  const stmt = db.prepare('DELETE FROM posts WHERE id = ?');
  
  stmt.run([id], function(err) {
    if (err) {
      res.status(500).json({ error: err.message });
      return;
    }
    
    if (this.changes === 0) {
      res.status(404).json({ message: 'Post not found' });
      return;
    }
    
    res.json({ message: 'Post deleted successfully' });
  });
  
  stmt.finalize();
});

// 搜索文章
app.get('/api/search', (req, res) => {
  const { q } = req.query;
  
  if (!q) {
    return res.status(400).json({ error: 'Query parameter "q" is required' });
  }
  
  const searchTerm = `%${q}%`;
  
  db.all(
    `SELECT * FROM posts 
     WHERE title LIKE ? OR content LIKE ? 
     ORDER BY created_at DESC`,
    [searchTerm, searchTerm],
    (err, rows) => {
      if (err) {
        res.status(500).json({ error: err.message });
        return;
      }
      res.json(rows);
    }
  );
});

// 启动服务器
app.listen(PORT, () => {
  console.log(`Blog server is running on port ${PORT}`);
  console.log(`Access the API at http://localhost:${PORT}/api`);
});