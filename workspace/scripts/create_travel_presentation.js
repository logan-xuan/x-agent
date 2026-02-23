const PptxGenJS = require('pptxgenjs');

// Create a new presentation
const pptx = new PptxGenJS();

// Slide 1: Title slide
const titleSlide = pptx.addSlide();
titleSlide.addText('春运返程高峰', { 
  x: 0.5, 
  y: 1.5, 
  w: 9, 
  h: 1, 
  fontSize: 36, 
  bold: true, 
  color: 'FFFFFF',
  fill: { color: '2A5CAA' },
  align: 'center'
});
titleSlide.addText('这份出行攻略请查收', { 
  x: 0.5, 
  y: 2.8, 
  w: 9, 
  h: 1, 
  fontSize: 28, 
  color: 'FFFFFF',
  fill: { color: '2A5CAA' },
  align: 'center'
});

// Slide 2: Overview
const overviewSlide = pptx.addSlide();
overviewSlide.addText('返程客流概况', { x: 0.5, y: 0.3, w: 9, h: 0.8, fontSize: 24, bold: true });
overviewSlide.addText([
  '• 返程客流逐渐攀升，正月初六至初八为高峰期',
  '• 高速公路单日最高流量预计达140万辆次',
  '• 铁路首个返程高峰日为正月初七',
  '• 民航高位客流将持续一周，正月初七达峰值',
  '• 杭州交通运输部门已做好充分准备'
].join('\n'), {
  x: 0.5,
  y: 1.2,
  w: 9,
  h: 4.5,
  fontSize: 16,
  bullet: true
});

// Slide 3: Weather Warning
const weatherSlide = pptx.addSlide();
weatherSlide.addText('天气预警与出行建议', { x: 0.5, y: 0.3, w: 9, h: 0.8, fontSize: 24, bold: true });
weatherSlide.addText([
  '• 今天杭州天气晴好',
  '• 明天白天天气转差，傍晚开始至正月初八阴有雨',
  '• 气温随之下降',
  '• 正月初九至十一还有一次降水过程',
  '• 请做好应对降水、大风、低能见度等措施'
].join('\n'), {
  x: 0.5,
  y: 1.2,
  w: 9,
  h: 4.5,
  fontSize: 16,
  bullet: true
});

// Slide 4: Highway Information
const highwaySlide = pptx.addSlide();
highwaySlide.addText('高速公路出行指南', { x: 0.5, y: 0.3, w: 9, h: 0.8, fontSize: 24, bold: true });
highwaySlide.addText([
  '• 免费通行于2月23日24时（正月初七）截止',
  '• 高峰期拥堵路段：G56杭徽高速、G25杭新景高速等',
  '• 推荐服务区：临安、龙岗、建德、桐庐等',
  '• 新能源车主需提前规划补能路线',
  '• 避免长时间排队，可就近驶离高速改走国省道'
].join('\n'), {
  x: 0.5,
  y: 1.2,
  w: 9,
  h: 4.5,
  fontSize: 16,
  bullet: true
});

// Slide 5: Railway Information
const railwaySlide = pptx.addSlide();
railwaySlide.addText('铁路出行信息', { x: 0.5, y: 0.3, w: 9, h: 0.8, fontSize: 24, bold: true });
railwaySlide.addText([
  '• 铁路杭州站昨日发送旅客30.5万人次',
  '• 杭州东站发送旅客约20.2万人次',
  '• 节后预计发送旅客603万人次',
  '• 首个返程高峰日：2月23日，预计发送27.3万人次',
  '• 第二个返程高峰日：3月7日（正月十九），预计发送30.5万人次'
].join('\n'), {
  x: 0.5,
  y: 1.2,
  w: 9,
  h: 4.5,
  fontSize: 16,
  bullet: true
});

// Slide 6: Safety Tips
const safetySlide = pptx.addSlide();
safetySlide.addText('安全出行温馨提示', { x: 0.5, y: 0.3, w: 9, h: 0.8, fontSize: 24, bold: true });
safetySlide.addText([
  '• 谨慎驾驶，平安出行',
  '• 关注实时路况，错峰出行',
  '• 新能源车提前检查车况和电量',
  '• 智驾是辅助，驾驶要自控',
  '• 随身携带应急工具：安全锤、破窗器等'
].join('\n'), {
  x: 0.5,
  y: 1.2,
  w: 9,
  h: 4.5,
  fontSize: 16,
  bullet: true
});

// Save the presentation to the presentations folder
pptx.writeFile({ fileName: 'presentations/travel_guide_presentation.pptx' }).then(() => {
  console.log('PPTX file created successfully!');
});