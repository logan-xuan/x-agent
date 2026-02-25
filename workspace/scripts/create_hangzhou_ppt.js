const fs = require('fs');
const path = require('path');
const pptx = require('pptxgenjs');

// 创建PPT对象
const pptxFile = new pptx();

// 设置PPT主题
pptxFile.author = '虾铁蛋AI助手';
pptxFile.company = 'Personal AI Agent';
pptxFile.revision = '1.0';

// 第一页：封面
const slide1 = pptxFile.addSlide();
slide1.addText('杭州三日游\n精彩行程推荐', {
  x: 0.5,
  y: 1.0,
  w: 9,
  h: 3,
  align: 'center',
  fontSize: 32,
  bold: true,
  color: '363636'
});
slide1.addText('根据天气精心规划的杭州之旅', {
  x: 0.5,
  y: 4.0,
  w: 9,
  h: 1,
  align: 'center',
  fontSize: 18,
  color: '696969'
});
slide1.addText('2026年2月24日', {
  x: 0.5,
  y: 5.5,
  w: 9,
  h: 1,
  align: 'center',
  fontSize: 16,
  color: '696969'
});

// 第二页：天气预报
const slide2 = pptxFile.addSlide();
slide2.addText('明日杭州天气预报', {
  x: 0.5,
  y: 0.5,
  w: 9,
  h: 1,
  align: 'left',
  fontSize: 24,
  bold: true,
  color: '363636'
});
slide2.addText([
  { text: '日期: 2026年2月24日\n' },
  { text: '天气状况: 小雨转多云\n' },
  { text: '温度范围: 8°C ~ 13°C\n' },
  { text: '风力: 北风<3级\n' },
  { text: '降雨概率: 74%\n' }
], {
  x: 0.5,
  y: 1.5,
  w: 9,
  h: 4,
  fontSize: 18,
  color: '000000'
});
slide2.addText('温馨提示: 请携带雨具及保暖衣物', {
  x: 0.5,
  y: 5.5,
  w: 9,
  h: 1,
  italic: true,
  fontSize: 16,
  color: 'FF6347'
});

// 第三页：上午行程安排
const slide3 = pptxFile.addSlide();
slide3.addText('上午行程安排 (9:00-12:00)', {
  x: 0.5,
  y: 0.5,
  w: 9,
  h: 1,
  align: 'left',
  fontSize: 24,
  bold: true,
  color: '363636'
});
slide3.addText([
  { text: '中国丝绸博物馆\n', options: { bold: true } },
  { text: '• 了解杭州丝绸文化历史\n' },
  { text: '• 室内景点，不受天气影响\n' },
  { text: '• 地址：杭州市西湖区玉皇山路73-1号\n' },
  { text: '\n' },
  { text: '浙江省博物馆\n', options: { bold: true } },
  { text: '• 欣赏江南文化和艺术品\n' },
  { text: '• 室内景点，适合雨天参观\n' }
], {
  x: 0.5,
  y: 1.5,
  w: 9,
  h: 5,
  fontSize: 16,
  color: '000000'
});

// 第四页：下午行程安排
const slide4 = pptxFile.addSlide();
slide4.addText('下午行程安排 (13:30-17:00)', {
  x: 0.5,
  y: 0.5,
  w: 9,
  h: 1,
  align: 'left',
  fontSize: 24,
  bold: true,
  color: '363636'
});
slide4.addText([
  { text: '河坊街-南宋御街\n', options: { bold: true } },
  { text: '• 古色古香的步行街，部分路段有遮蔽设施\n' },
  { text: '• 适合品尝杭州小吃，购买特产\n' },
  { text: '• 可以逛胡庆余堂中药博物馆等室内景点\n' },
  { text: '\n' },
  { text: '中国茶叶博物馆\n', options: { bold: true } },
  { text: '• 了解龙井茶文化\n' },
  { text: '• 室内参观，还可以品茶暖身\n' }
], {
  x: 0.5,
  y: 1.5,
  w: 9,
  h: 5,
  fontSize: 16,
  color: '000000'
});

// 第五页：傍晚行程及备选方案
const slide5 = pptxFile.addSlide();
slide5.addText('傍晚行程及备选方案', {
  x: 0.5,
  y: 0.5,
  w: 9,
  h: 1,
  align: 'left',
  fontSize: 24,
  bold: true,
  color: '363636'
});
slide5.addText([
  { text: '京杭大运河游船\n', options: { bold: true } },
  { text: '• 即使小雨也可乘船游览，别有一番风味\n' },
  { text: '• 运河夜景美丽，船上有遮蔽设施\n' },
  { text: '\n' },
  { text: '备选晴天方案:\n', options: { bold: true } },
  { text: '• 西湖风景区：断桥残雪、平湖秋月等景点\n' },
  { text: '• 灵隐寺：著名的佛教寺庙\n' },
  { text: '• 西溪国家湿地公园\n' }
], {
  x: 0.5,
  y: 1.5,
  w: 9,
  h: 5,
  fontSize: 16,
  color: '000000'
});

// 第六页：出行提示
const slide6 = pptxFile.addSlide();
slide6.addText('出行提示', {
  x: 0.5,
  y: 0.5,
  w: 9,
  h: 1,
  align: 'left',
  fontSize: 24,
  bold: true,
  color: '363636'
});
slide6.addText([
  { text: '必备物品:\n', options: { bold: true } },
  { text: '• 雨伞或雨衣\n' },
  { text: '• 防滑鞋\n' },
  { text: '\n' },
  { text: '衣物建议:\n', options: { bold: true } },
  { text: '• 保暖外套，温度较低\n' },
  { text: '\n' },
  { text: '其他提醒:\n', options: { bold: true } },
  { text: '• 热门景点建议提前在官方公众号预约\n' },
  { text: '• 雨天路滑，请注意交通安全\n' }
], {
  x: 0.5,
  y: 1.5,
  w: 9,
  h: 5,
  fontSize: 16,
  color: '000000'
});

// 保存PPT文件
const filePath = path.join(__dirname, '../presentations/hangzhou_travel_plan.pptx');
pptxFile.writeFile(filePath)
  .then(() => {
    console.log(`PPT文件已成功创建: ${filePath}`);
  })
  .catch(error => {
    console.error('创建PPT文件时发生错误:', error);
  });