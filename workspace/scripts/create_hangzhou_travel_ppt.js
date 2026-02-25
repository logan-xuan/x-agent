const PptxGenJS = require('pptxgenjs');

// Create a new PowerPoint presentation
const pptx = new PptxGenJS();

// Slide 1: Title Slide
const titleSlide = pptx.addSlide();
titleSlide.addText('杭州明日旅游攻略', {
  x: 0.5,
  y: 1,
  w: 9,
  h: 1.5,
  fontSize: 36,
  bold: true,
  color: '363636'
});
titleSlide.addText(`天气预报：小雨转多云\n温度：8°C ~ 13°C`, {
  x: 0.5,
  y: 2.5,
  w: 9,
  h: 1,
  fontSize: 20,
  color: '666666'
});

// Slide 2: Weather Information
const weatherSlide = pptx.addSlide();
weatherSlide.addText('明日天气详情', {
  x: 0.5,
  y: 0.2,
  w: 9,
  h: 0.8,
  fontSize: 28,
  bold: true,
  color: '363636'
});
weatherSlide.addText([
  { text: '天气状况：', options: { bold: true } },
  { text: '小雨转多云\n' },
  { text: '温度范围：', options: { bold: true } },
  { text: '8°C ~ 13°C\n' },
  { text: '风力：', options: { bold: true } },
  { text: '北风<3级\n' },
  { text: '降雨概率：', options: { bold: true } },
  { text: '74%' }
], {
  x: 0.5,
  y: 1.2,
  w: 9,
  h: 3,
  fontSize: 18,
  color: '444444'
});
weatherSlide.addText('出行提示：请携带雨具，注意保暖', {
  x: 0.5,
  y: 4.5,
  w: 9,
  h: 0.5,
  fontSize: 16,
  color: 'FF0000',
  bold: true
});

// Slide 3: Morning Plan
const morningSlide = pptx.addSlide();
morningSlide.addText('上午行程 (9:00-12:00)', {
  x: 0.5,
  y: 0.2,
  w: 9,
  h: 0.8,
  fontSize: 28,
  bold: true,
  color: '363636'
});
morningSlide.addText([
  { text: '中国丝绸博物馆\n', options: { bold: true, fontSize: 20 } },
  { text: '• 了解杭州丝绸文化历史\n• 室内景点，不受天气影响\n• 地址：杭州市西湖区玉皇山路73-1号\n\n' },
  { text: '浙江省博物馆\n', options: { bold: true, fontSize: 20 } },
  { text: '• 欣赏江南文化和艺术品\n• 室内景点，适合雨天参观' }
], {
  x: 0.5,
  y: 1.2,
  w: 9,
  h: 3.5,
  fontSize: 16,
  color: '444444'
});

// Slide 4: Afternoon Plan
const afternoonSlide = pptx.addSlide();
afternoonSlide.addText('下午行程 (13:30-17:00)', {
  x: 0.5,
  y: 0.2,
  w: 9,
  h: 0.8,
  fontSize: 28,
  bold: true,
  color: '363636'
});
afternoonSlide.addText([
  { text: '河坊街-南宋御街\n', options: { bold: true, fontSize: 20 } },
  { text: '• 古色古香的步行街，部分路段有遮蔽设施\n• 适合品尝杭州小吃，购买特产\n• 可以逛胡庆余堂中药博物馆等室内景点\n\n' },
  { text: '中国茶叶博物馆\n', options: { bold: true, fontSize: 20 } },
  { text: '• 了解龙井茶文化\n• 室内参观，还可以品茶暖身' }
], {
  x: 0.5,
  y: 1.2,
  w: 9,
  h: 3.5,
  fontSize: 16,
  color: '444444'
});

// Slide 5: Evening Plan
const eveningSlide = pptx.addSlide();
eveningSlide.addText('傍晚行程 (17:00-19:00)', {
  x: 0.5,
  y: 0.2,
  w: 9,
  h: 0.8,
  fontSize: 28,
  bold: true,
  color: '363636'
});
eveningSlide.addText([
  { text: '京杭大运河游船\n', options: { bold: true, fontSize: 20 } },
  { text: '• 即使小雨也可乘船游览，别有一番风味\n• 运河夜景美丽，船上有遮蔽设施' }
], {
  x: 0.5,
  y: 1.2,
  w: 9,
  h: 3.5,
  fontSize: 16,
  color: '444444'
});

// Slide 6: Alternative Sunny Plan
const sunnySlide = pptx.addSlide();
sunnySlide.addText('备选晴天方案', {
  x: 0.5,
  y: 0.2,
  w: 9,
  h: 0.8,
  fontSize: 28,
  bold: true,
  color: '363636'
});
sunnySlide.addText([
  { text: '如果天气好转，可以考虑：\n\n', options: { fontSize: 18 } },
  { text: '西湖风景区\n', options: { bold: true, fontSize: 20 } },
  { text: '• 断桥残雪、平湖秋月等景点\n\n' },
  { text: '灵隐寺\n', options: { bold: true, fontSize: 20 } },
  { text: '• 著名的佛教寺庙\n\n' },
  { text: '西溪国家湿地公园\n', options: { bold: true, fontSize: 20 } },
  { text: '• 自然风光优美' }
], {
  x: 0.5,
  y: 1.2,
  w: 9,
  h: 3.5,
  fontSize: 16,
  color: '444444'
});

// Slide 7: Travel Tips
const tipsSlide = pptx.addSlide();
tipsSlide.addText('出行提示', {
  x: 0.5,
  y: 0.2,
  w: 9,
  h: 0.8,
  fontSize: 28,
  bold: true,
  color: '363636'
});
tipsSlide.addText([
  { text: '必备物品：', options: { bold: true } },
  { text: '雨伞或雨衣、防滑鞋\n\n' },
  { text: '衣物建议：', options: { bold: true } },
  { text: '保暖外套，温度较低\n\n' },
  { text: '预约提醒：', options: { bold: true } },
  { text: '热门景点建议提前在官方公众号预约\n\n' },
  { text: '交通：', options: { bold: true } },
  { text: '雨天路滑，请注意交通安全' }
], {
  x: 0.5,
  y: 1.2,
  w: 9,
  h: 3.5,
  fontSize: 18,
  color: '444444'
});

// Slide 8: Closing
const closingSlide = pptx.addSlide();
closingSlide.addText('祝您旅途愉快！', {
  x: 0.5,
  y: 2,
  w: 9,
  h: 1.5,
  fontSize: 36,
  bold: true,
  color: '363636'
});
closingSlide.addText('根据天气情况灵活调整行程', {
  x: 0.5,
  y: 3.5,
  w: 9,
  h: 1,
  fontSize: 20,
  color: '666666'
});

// Save the presentation
pptx.writeFile({ fileName: 'presentations/Hangzhou_Tourism_Plan.pptx' }).then(() => {
  console.log('杭州旅游计划PPT已创建完成');
});