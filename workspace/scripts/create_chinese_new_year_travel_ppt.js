import { html2pptx } from './html2pptx.js';

// Create a new PowerPoint presentation
const pptx = new html2pptx();

// Add slides for Chinese New Year Travel presentation
// Slide 1: Title slide
pptx.addSlide({
  title: '春节旅游',
  subtitle: '欢度佳节，畅游天下',
  layout: 'TITLE',
  theme: {
    backgroundColor: '#C72C48',
    titleColor: '#FFFFFF',
    subtitleColor: '#FCD5CE',
    font: 'Arial'
  }
});

// Slide 2: Introduction
pptx.addSlide({
  title: '春节旅游概述',
  content: [
    { type: 'text', text: '春节是中国最重要的传统节日', style: { fontSize: 18 } },
    { type: 'text', text: '越来越多的人选择在春节期间出游', style: { fontSize: 18 } },
    { type: 'text', text: '体验不同地方的年味和文化', style: { fontSize: 18 } }
  ],
  layout: 'SECTION_HEADER',
  theme: {
    backgroundColor: '#FCD5CE',
    titleColor: '#7C1C2D',
    contentColor: '#333333',
    font: 'Arial'
  }
});

// Slide 3: Popular Destinations
pptx.addSlide({
  title: '热门国内旅游目的地',
  content: [
    { type: 'list', items: ['哈尔滨 - 冰雪大世界', '三亚 - 温暖海滩', '北京 - 历史古迹', '西安 - 文化之旅'] },
  ],
  layout: 'TWO_COLUMN',
  theme: {
    backgroundColor: '#FFFFFF',
    titleColor: '#C72C48',
    contentColor: '#333333',
    font: 'Arial'
  }
});

// Slide 4: Overseas Travel
pptx.addSlide({
  title: '海外旅游推荐',
  content: [
    { type: 'list', items: ['新加坡 - 华人社区庆祝', '泰国 - 佛教文化体验', '日本 - 传统文化', '马来西亚 - 多元文化'] },
  ],
  layout: 'TWO_COLUMN',
  theme: {
    backgroundColor: '#FFF0F3',
    titleColor: '#7C1C2D',
    contentColor: '#333333',
    font: 'Arial'
  }
});

// Slide 5: Tips
pptx.addSlide({
  title: '春节旅游注意事项',
  content: [
    { type: 'list', items: ['提前预订机票和酒店', '关注天气变化', '安排充足的行程时间', '备好常用药品'] },
  ],
  layout: 'TWO_COLUMN',
  theme: {
    backgroundColor: '#FFFFFF',
    titleColor: '#C72C48',
    contentColor: '#333333',
    font: 'Arial'
  }
});

// Slide 6: Budget Planning
pptx.addSlide({
  title: '预算规划与省钱技巧',
  content: [
    { type: 'list', items: ['制定详细预算清单', '比较不同平台价格', '考虑淡季时段出行', '选择经济型住宿'] },
  ],
  layout: 'TWO_COLUMN',
  theme: {
    backgroundColor: '#FCD5CE',
    titleColor: '#7C1C2D',
    contentColor: '#333333',
    font: 'Arial'
  }
});

// Slide 7: Special Experiences
pptx.addSlide({
  title: '春节特色体验活动',
  content: [
    { type: 'list', items: ['观看舞龙舞狮表演', '参加庙会活动', '品尝各地年味美食', '欣赏花灯展览'] },
  ],
  layout: 'TWO_COLUMN',
  theme: {
    backgroundColor: '#FFFFFF',
    titleColor: '#C72C48',
    contentColor: '#333333',
    font: 'Arial'
  }
});

// Slide 8: Safety Tips
pptx.addSlide({
  title: '安全与健康提示',
  content: [
    { type: 'list', items: ['保管好个人财物', '注意饮食卫生', '遵守当地法律法规', '购买旅游保险'] },
  ],
  layout: 'TWO_COLUMN',
  theme: {
    backgroundColor: '#FFF0F3',
    titleColor: '#7C1C2D',
    contentColor: '#333333',
    font: 'Arial'
  }
});

// Slide 9: Checklist
pptx.addSlide({
  title: '旅行准备清单',
  content: [
    { type: 'list', items: ['身份证件及复印件', '现金和银行卡', '充电器及转换插头', '换洗衣物及洗漱用品'] },
  ],
  layout: 'TWO_COLUMN',
  theme: {
    backgroundColor: '#FFFFFF',
    titleColor: '#C72C48',
    contentColor: '#333333',
    font: 'Arial'
  }
});

// Slide 10: Conclusion
pptx.addSlide({
  title: '结语与祝福',
  content: [
    { type: 'text', text: '春节旅游是体验不同文化的好机会', style: { fontSize: 18 } },
    { type: 'text', text: '祝大家旅途愉快，新年快乐！', style: { fontSize: 18, bold: true } }
  ],
  layout: 'SECTION_HEADER',
  theme: {
    backgroundColor: '#C72C48',
    titleColor: '#FFFFFF',
    contentColor: '#FCD5CE',
    font: 'Arial'
  }
});

// Save the presentation
await pptx.writeFile('/Users/xuan.lx/Documents/x-agent/x-agent/workspace/chinese_new_year_travel.pptx');