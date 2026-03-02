// api-test.js - API 测试示例

// 以下是使用 curl 命令测试 API 的示例：

/*
1. 获取所有文章:
curl -X GET http://localhost:3000/api/posts

2. 获取特定文章:
curl -X GET http://localhost:3000/api/posts/1

3. 创建新文章:
curl -X POST http://localhost:3000/api/posts \
  -F "title=我的第一篇博客" \
  -F "content=这是我的第一篇博客内容" \
  -F "author=张三" \
  -F "image=@./path/to/image.jpg"

4. 更新文章:
curl -X PUT http://localhost:3000/api/posts/1 \
  -F "title=更新后的标题" \
  -F "content=更新后的内容" \
  -F "author=李四" \
  -F "existing_image_url=/uploads/image.jpg"

5. 删除文章:
curl -X DELETE http://localhost:3000/api/posts/1

6. 搜索文章:
curl -X GET "http://localhost:3000/api/search?q=关键词"
*/

// 也可以使用 JavaScript 进行测试
const testPosts = async () => {
  try {
    // 获取所有文章
    const response = await fetch('http://localhost:3000/api/posts');
    const data = await response.json();
    console.log('所有文章:', data);

    // 创建新文章
    const newPostResponse = await fetch('http://localhost:3000/api/posts', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        title: '通过API创建的文章',
        content: '这是一篇通过API创建的文章内容',
        author: 'API测试者'
      })
    });
    const newPost = await newPostResponse.json();
    console.log('新创建的文章:', newPost);
  } catch (error) {
    console.error('API测试出错:', error);
  }
};

console.log('博客系统API测试示例');
console.log('启动服务后，可以通过以上方式测试API');