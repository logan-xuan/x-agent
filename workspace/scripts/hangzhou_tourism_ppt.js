const fs = require('fs');
const path = require('path');
const PptxGenJS = require('pptxgenjs');

// 创建PPT实例
const pptx = new PptxGenJS();

// 设置PPT标题页
let slide = pptx.addSlide();
slide.addText('杭州明日旅游攻略', {
  x: 0,
  y: 1,
  w: '100%',
  h: 2,
  align: 'center',
  fontSize: 32,
  bold: true,
  color: '363636'
});
slide.addText(`天气: 小雨转多云\n温度: 8°C ~ 13°C\n日期: 2026年2月24日`, {
  x: 0,
  y: 3.5,
  w: '100%',
  h: 2,
  align: 'center',
  fontSize: 18,
  color: '666666'
});

// 添加上午行程页
slide = pptx.addSlide();
slide.addText('上午行程 (9:00-12:00)', {
  x: 0,
  y: 0.2,
  w: '100%',
  h: 1,
  align: 'left',
  fontSize: 24,
  bold: true,
  color: '363636'
});
slide.addText([
  { text: '中国丝绸博物馆\n', options: { fontSize: 18, bold: true } },
  { text: '• 了解杭州丝绸文化历史\n', options: { fontSize: 14 } },
  { text: '• 室内景点，不受天气影响\n', options: { fontSize: 14 } },
  { text: '• 地址：杭州市西湖区玉皇山路73-1号\n\n', options: { fontSize: 14 } },
  
  { text: '浙江省博物馆\n', options: { fontSize: 18, bold: true } },
  { text: '• 欣赏江南文化和艺术品\n', options: { fontSize: 14 } },
  { text: '• 室内景点，适合雨天参观', options: { fontSize: 14 } }
], {
  x: 0.5,
  y: 1.2,
  w: 9,
  h: 6,
  fontSize: 14,
  color: '363636'
});

// 添加下午行程页
slide = pptx.addSlide();
slide.addText('下午行程 (13:30-17:00)', {
  x: 0,
  y: 0.2,
  w: '100%',
  h: 1,
  align: 'left',
  fontSize: 24,
  bold: true,
  color: '363636'
});
slide.addText([
  { text: '河坊街-南宋御街\n', options: { fontSize: 18, bold: true } },
  { text: '• 古色古香的步行街，部分路段有遮蔽设施\n', options: { fontSize: 14 } },
  { text: '• 适合品尝杭州小吃，购买特产\n', options: { fontSize: 14 } },
  { text: '• 可以逛胡庆余堂中药博物馆等室内景点\n\n', options: { fontSize: 14 } },
  
  { text: '中国茶叶博物馆\n', options: { fontSize: 18, bold: true } },
  { text: '• 了解龙井茶文化\n', options: { fontSize: 14 } },
  { text: '• 室内参观，还可以品茶暖身', options: { fontSize: 14 } }
], {
  x: 0.5,
  y: 1.2,
  w: 9,
  h: 6,
  fontSize: 14,
  color: '363636'
});

// 添加傍晚行程页
slide = pptx.addSlide();
slide.addText('傍晚行程 (17:00-19:00)', {
  x: 0,
  y: 0.2,
  w: '100%',
  h: 1,
  align: 'left',
  fontSize: 24,
  bold: true,
  color: '363636'
});
slide.addText([
  { text: '京杭大运河游船\n', options: { fontSize: 18, bold: true } },
  { text: '• 即使小雨也可乘船游览，别有一番风味\n', options: { fontSize: 14 } },
  { text: '• 运河夜景美丽，船上有遮蔽设施\n\n', options: { fontSize: 14 } },
  
  { text: '备选晴天方案\n', options: { fontSize: 18, bold: true } },
  { text: '• 西湖风景区：断桥残雪、平湖秋月等景点\n', options: { fontSize: 14 } },
  { text: '• 灵隐寺：著名的佛教寺庙\n', options: { fontSize: 14 } },
  { text: '• 西溪国家湿地公园', options: { fontSize: 14 } }
], {
  x: 0.5,
  y: 1.2,
  w: 9,
  h: 6,
  fontSize: 14,
  color: '363636'
});

// 添加出行提示页
slide = pptx.addSlide();
slide.addText('出行提示', {
  x: 0,
  y: 0.2,
  w: '100%',
  h: 1,
  align: 'left',
  fontSize: 24,
  bold: true,
  color: '363636'
});
slide.addText([
  { text: '必备物品\n', options: { fontSize: 18, bold: true } },
  { text: '• 雨伞或雨衣\n', options: { fontSize: 14 } },
  { text: '• 防滑鞋\n\n', options: { fontSize: 14 } },
  
  { text: '衣物建议\n', options: { fontSize: 18, bold: true } },
  { text: '• 保暖外套，温度较低\n\n', options: { fontSize: 14 } },
  
  { text: '其他提醒\n', options: { fontSize: 18, bold: true } },
  { text: '• 热门景点建议提前在官方公众号预约\n', options: { fontSize: 14 } },
  { text: '• 雨天路滑，请注意交通安全', options: { fontSize: 14 } }
], {
  x: 0.5,
  y: 1.2,
  w: 9,
  h: 6,
  fontSize: 14,
  color: '363636'
});

// 添加总结页
slide = pptx.addSlide();
slide.addText('祝您杭州之旅愉快！', {
  x: 0,
  y: 2,
  w: '100%',
  h: 2,
  align: 'center',
  fontSize: 32,
  bold: true,
  color: '363636'
});
slide.addText('杭州美景，值得细细品味', {
  x: 0,
  y: 4.5,
  w: '100%',
  h: 1,
  align: 'center',
  fontSize: 18,
  color: '666666'
});

// 保存PPT文件
const filePath = path.join(__dirname, '../presentations/hangzhou_tourism_plan.pptx');
pptx.writeFile({ fileName: filePath })
  .then(() => {
    console.log('PPT文件已成功创建:', filePath);
  })
  .catch(err => {
    console.error('创建PPT文件时发生错误:', err);
  });