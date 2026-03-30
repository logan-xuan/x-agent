const PptxGenJS = require('pptxgenjs');
const path = require('path');

// Create presentation instance with dark theme
const pptx = new PptxGenJS();
pptx.layout = 'LAYOUT_16x9';

// Define dark theme colors
const bgColor = '2C2C2C'; // Dark gray background
const accentColor = '4A90E2'; // Blue accent
const textColor = 'FFFFFF'; // White text
const secondaryTextColor = 'CCCCCC'; // Light gray text

// Slide 1: Title Slide
let slide1 = pptx.addSlide();
// Background
slide1.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: '100%', h: '100%', fill: bgColor });
// Title
slide1.addText('西安古都探秘之旅', { 
  x: 1, y: 2, w: 8, h: 1.5, 
  fontSize: 44, bold: true, 
  color: textColor,
  shadow: { type: 'outer', opacity: 0.5 }
});
slide1.addText('杭州-西安五日游详细攻略', { 
  x: 1, y: 3.5, w: 8, h: 0.8, 
  fontSize: 24, 
  color: secondaryTextColor
});
slide1.addText('Travel Guide | 西安旅游', { 
  x: 1, y: 8, w: 8, h: 0.5, 
  fontSize: 16, 
  color: secondaryTextColor,
  align: 'center'
});

// Slide 2: 行程概览
let slide2 = pptx.addSlide();
slide2.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: '100%', h: '100%', fill: bgColor });
slide2.addText('行程概览', { 
  x: 0.5, y: 0.5, w: 9, h: 0.8, 
  fontSize: 36, bold: true, 
  color: textColor 
});
slide2.addText([
  { text: '第一天: 抵达西安，市区游览 - 钟鼓楼、回民街\n', options: { breakLine: true } },
  { text: '第二天: 兵马俑 + 华清宫 - 世界文化遗产体验\n', options: { breakLine: true } },
  { text: '第三天: 西安城墙 + 陕西历史博物馆 - 古都风貌\n', options: { breakLine: true } },
  { text: '第四天: 大雁塔 + 大兴善寺 - 盛唐文化\n', options: { breakLine: true } },
  { text: '第五天: 自由活动，返程回家', options: { breakLine: true } }
], { 
  x: 0.5, y: 1.5, w: 9, h: 6, 
  fontSize: 18, 
  color: secondaryTextColor,
  lineSpacing: 20
});
slide2.addText('Day 1-5 Overview', { 
  x: 0.5, y: 8, w: 9, h: 0.5, 
  fontSize: 14, 
  color: secondaryTextColor,
  italic: true
});

// Slide 3: 第一天 - 市区游览
let slide3 = pptx.addSlide();
slide3.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: '100%', h: '100%', fill: bgColor });
slide3.addText('第一天：抵达西安', { 
  x: 0.5, y: 0.5, w: 9, h: 0.8, 
  fontSize: 32, bold: true, 
  color: textColor 
});
slide3.addText('上午', { 
  x: 0.5, y: 1.5, w: 2, h: 0.5, 
  fontSize: 20, bold: true, 
  color: accentColor 
});
slide3.addText('从杭州出发，乘机抵达西安', { 
  x: 2.7, y: 1.5, w: 6, h: 0.5, 
  fontSize: 16, 
  color: secondaryTextColor 
});
slide3.addText('下午', { 
  x: 0.5, y: 2.2, w: 2, h: 0.5, 
  fontSize: 20, bold: true, 
  color: accentColor 
});
slide3.addText('入住酒店，稍作休息', { 
  x: 2.7, y: 2.2, w: 6, h: 0.5, 
  fontSize: 16, 
  color: secondaryTextColor 
});
slide3.addText('傍晚', { 
  x: 0.5, y: 2.9, w: 2, h: 0.5, 
  fontSize: 20, bold: true, 
  color: accentColor 
});
slide3.addText('游览钟鼓楼广场，品尝回民街小吃', { 
  x: 2.7, y: 2.9, w: 6, h: 0.5, 
  fontSize: 16, 
  color: secondaryTextColor 
});

// Slide 4: 第二天 - 兵马俑和华清宫
let slide4 = pptx.addSlide();
slide4.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: '100%', h: '100%', fill: bgColor });
slide4.addText('第二天：世界文化遗产', { 
  x: 0.5, y: 0.5, w: 9, h: 0.8, 
  fontSize: 32, bold: true, 
  color: textColor 
});
slide4.addText('上午', { 
  x: 0.5, y: 1.5, w: 2, h: 0.5, 
  fontSize: 20, bold: true, 
  color: accentColor 
});
slide4.addText('参观秦始皇兵马俑博物馆 (游览约3小时)', { 
  x: 2.7, y: 1.5, w: 6, h: 0.5, 
  fontSize: 16, 
  color: secondaryTextColor 
});
slide4.addText('下午', { 
  x: 0.5, y: 2.2, w: 2, h: 0.5, 
  fontSize: 20, bold: true, 
  color: accentColor 
});
slide4.addText('游览华清宫，感受唐玄宗与杨贵妃的爱情故事', { 
  x: 2.7, y: 2.2, w: 6, h: 0.5, 
  fontSize: 16, 
  color: secondaryTextColor 
});
slide4.addText('晚上 (可选)', { 
  x: 0.5, y: 2.9, w: 2.5, h: 0.5, 
  fontSize: 20, bold: true, 
  color: accentColor 
});
slide4.addText('观看《长恨歌》实景演出 (298元起)', { 
  x: 2.7, y: 2.9, w: 6, h: 0.5, 
  fontSize: 16, 
  color: secondaryTextColor 
});

// Slide 5: 第三天 - 城墙和博物馆
let slide5 = pptx.addSlide();
slide5.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: '100%', h: '100%', fill: bgColor });
slide5.addText('第三天：古都风貌', { 
  x: 0.5, y: 0.5, w: 9, h: 0.8, 
  fontSize: 32, bold: true, 
  color: textColor 
});
slide5.addText('上午', { 
  x: 0.5, y: 1.5, w: 2, h: 0.5, 
  fontSize: 20, bold: true, 
  color: accentColor 
});
slide5.addText('参观西安城墙，骑行或步行体验明代城垣', { 
  x: 2.7, y: 1.5, w: 6, h: 0.5, 
  fontSize: 16, 
  color: secondaryTextColor 
});
slide5.addText('下午', { 
  x: 0.5, y: 2.2, w: 2, h: 0.5, 
  fontSize: 20, bold: true, 
  color: accentColor 
});
slide5.addText('游览陕西历史博物馆 (免费，需预约)', { 
  x: 2.7, y: 2.2, w: 6, h: 0.5, 
  fontSize: 16, 
  color: secondaryTextColor 
});
slide5.addText('晚上', { 
  x: 0.5, y: 2.9, w: 2, h: 0.5, 
  fontSize: 20, bold: true, 
  color: accentColor 
});
slide5.addText('游览大唐不夜城，感受盛唐文化氛围', { 
  x: 2.7, y: 2.9, w: 6, h: 0.5, 
  fontSize: 16, 
  color: secondaryTextColor 
});

// Slide 6: 第四天 - 大雁塔和寺庙
let slide6 = pptx.addSlide();
slide6.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: '100%', h: '100%', fill: bgColor });
slide6.addText('第四天：盛唐文化', { 
  x: 0.5, y: 0.5, w: 9, h: 0.8, 
  fontSize: 32, bold: true, 
  color: textColor 
});
slide6.addText('上午', { 
  x: 0.5, y: 1.5, w: 2, h: 0.5, 
  fontSize: 20, bold: true, 
  color: accentColor 
});
slide6.addText('参观大雁塔及北广场音乐喷泉', { 
  x: 2.7, y: 1.5, w: 6, h: 0.5, 
  fontSize: 16, 
  color: secondaryTextColor 
});
slide6.addText('下午', { 
  x: 0.5, y: 2.2, w: 2, h: 0.5, 
  fontSize: 20, bold: true, 
  color: accentColor 
});
slide6.addText('游览大兴善寺，体验佛教文化', { 
  x: 2.7, y: 2.2, w: 6, h: 0.5, 
  fontSize: 16, 
  color: secondaryTextColor 
});
slide6.addText('傍晚', { 
  x: 0.5, y: 2.9, w: 2, h: 0.5, 
  fontSize: 20, bold: true, 
  color: accentColor 
});
slide6.addText('参观大唐芙蓉园，欣赏园林景观', { 
  x: 2.7, y: 2.9, w: 6, h: 0.5, 
  fontSize: 16, 
  color: secondaryTextColor 
});

// Slide 7: 第五天和旅行贴士
let slide7 = pptx.addSlide();
slide7.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: '100%', h: '100%', fill: bgColor });
slide7.addText('第五天：返程 & 旅行贴士', { 
  x: 0.5, y: 0.5, w: 9, h: 0.8, 
  fontSize: 32, bold: true, 
  color: textColor 
});
slide7.addText('上午', { 
  x: 0.5, y: 1.5, w: 2, h: 0.5, 
  fontSize: 20, bold: true, 
  color: accentColor 
});
slide7.addText('自由活动，购买特产', { 
  x: 2.7, y: 1.5, w: 6, h: 0.5, 
  fontSize: 16, 
  color: secondaryTextColor 
});
slide7.addText('下午', { 
  x: 0.5, y: 2.2, w: 2, h: 0.5, 
  fontSize: 20, bold: true, 
  color: accentColor 
});
slide7.addText('前往机场，返回杭州', { 
  x: 2.7, y: 2.2, w: 6, h: 0.5, 
  fontSize: 16, 
  color: secondaryTextColor 
});
slide7.addText('旅行贴士', { 
  x: 0.5, y: 3.2, w: 9, h: 0.6, 
  fontSize: 20, bold: true, 
  color: accentColor 
});
slide7.addText([
  { text: '• 交通: 市内建议使用地铁和出租车，去临潼可乘坐旅游专线\n', options: { bullet: true } },
  { text: '• 美食: 肉夹馍、凉皮、羊肉泡馍、biáng biáng面、葫芦头等\n', options: { bullet: true } },
  { text: '• 住宿: 建议选择钟楼、大雁塔附近，交通便利\n', options: { bullet: true } },
  { text: '• 门票: 兵马俑120元，华清宫120元，西安城墙54元，陕历博免费(需预约)', options: { bullet: true } }
], { 
  x: 0.5, y: 4, w: 9, h: 4, 
  fontSize: 16, 
  color: secondaryTextColor,
  lineSpacing: 18
});

// Slide 8: 西安景点概览图
let slide8 = pptx.addSlide();
slide8.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: '100%', h: '100%', fill: bgColor });
slide8.addText('西安主要景点分布', { 
  x: 0.5, y: 0.5, w: 9, h: 0.8, 
  fontSize: 32, bold: true, 
  color: textColor 
});
slide8.addText([
  { text: '市中心区域:\n', options: { bold: true } },
  { text: '• 钟鼓楼广场 - 古都地标，夜景迷人\n', options: { bullet: true } },
  { text: '• 回民街 - 美食天堂，体验当地小吃\n', options: { bullet: true } },
  { text: '• 西安城墙 - 保存最完整的古代城垣\n', options: { bullet: true } },
  { text: '\n东部临潼区:\n', options: { bold: true, breakLine: true } },
  { text: '• 兵马俑 - 世界第八大奇迹\n', options: { bullet: true } },
  { text: '• 华清宫 - 唐玄宗与杨贵妃的爱情地\n', options: { bullet: true } },
  { text: '\n南部文化区:\n', options: { bold: true, breakLine: true } },
  { text: '• 陕西历史博物馆 - 陕西历史文化宝库\n', options: { bullet: true } },
  { text: '• 大雁塔 - 唐代著名佛塔\n', options: { bullet: true } },
  { text: '• 大唐不夜城 - 盛唐文化体验区', options: { bullet: true } }
], { 
  x: 0.5, y: 1.5, w: 9, h: 6.5, 
  fontSize: 16, 
  color: secondaryTextColor,
  lineSpacing: 16
});

// Save the presentation
const outputPath = path.join(__dirname, '..', 'presentations', 'hangzhou_to_xian_travel_guide.pptx');
pptx.writeFile({ fileName: outputPath })
  .then(() => console.log(`✅ PPT saved: ${outputPath}`))
  .catch(err => console.error('Error:', err));