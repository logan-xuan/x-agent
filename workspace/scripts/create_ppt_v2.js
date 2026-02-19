const PptxGenJS = require('pptxgenjs');
const fs = require('fs');

// Create a new PowerPoint presentation
const pptx = new PptxGenJS();

// Define slide layout
pptx.layout = 'LAYOUT_WIDE'; // 13.33" x 7.5" (1600 x 900 pixels)

// Slide 1: Title
let slide = pptx.addSlide();
slide.addText('人工智能 (AI)', { 
  x: 0.5, 
  y: 1.5, 
  w: 12, 
  h: 1.5, 
  fontSize: 40, 
  bold: true, 
  color: 'FFFFFF',
  fill: { color: '2a5298' },
  align: 'center',
  valign: 'middle'
});
slide.addText('探索智能科技的未来', { 
  x: 0.5, 
  y: 3.0, 
  w: 12, 
  h: 1, 
  fontSize: 24, 
  color: 'FFFFFF',
  fill: { color: '2a5298' },
  align: 'center',
  valign: 'middle'
});

// Slide 2: What is AI
slide = pptx.addSlide();
slide.addText('什么是人工智能？', {
  x: 0.5,
  y: 0.5,
  w: 12,
  h: 1,
  fontSize: 28,
  bold: true,
  color: '2a5298',
  align: 'center'
});
slide.addText([
  { text: '人工智能(AI)是指由人类创造的机器所表现出来的智能行为。\n\n它是研究、开发用于模拟、延伸和扩展人的智能的理论、方法、技术及应用系统的一门新的技术科学。', options: { breakLine: true } }
], {
  x: 0.5,
  y: 1.5,
  w: 12,
  h: 5,
  fontSize: 16,
  align: 'left',
  margin: 10
});

// Slide 3: AI History
slide = pptx.addSlide();
slide.addText('AI发展历程', {
  x: 0.5,
  y: 0.5,
  w: 12,
  h: 1,
  fontSize: 28,
  bold: true,
  color: '2a5298',
  align: 'center'
});
slide.addText([
  { text: '• 1956年：达特茅斯会议标志着AI领域的诞生\n', options: { breakLine: true } },
  { text: '• 1960-70年代：早期AI研究与期望过高导致第一次AI寒冬\n', options: { breakLine: true } },
  { text: '• 1980年代：专家系统的兴起\n', options: { breakLine: true } },
  { text: '• 1990年代-2000年代：机器学习开始发展\n', options: { breakLine: true } },
  { text: '• 2010年代至今：深度学习革命与AI的大规模应用', options: { breakLine: true } }
], {
  x: 0.5,
  y: 1.5,
  w: 12,
  h: 5,
  fontSize: 16,
  align: 'left',
  margin: 10
});

// Slide 4: Core Technologies
slide = pptx.addSlide();
slide.addText('核心技术', {
  x: 0.5,
  y: 0.5,
  w: 12,
  h: 1,
  fontSize: 28,
  bold: true,
  color: '2a5298',
  align: 'center'
});
slide.addText([
  { text: '• 机器学习\n', options: { breakLine: true } },
  { text: '• 深度学习\n', options: { breakLine: true } },
  { text: '• 自然语言处理', options: { breakLine: true } }
], {
  x: 0.5,
  y: 2,
  w: 5.5,
  h: 4,
  fontSize: 16,
  align: 'left',
  margin: 10
});
slide.addText([
  { text: '• 计算机视觉\n', options: { breakLine: true } },
  { text: '• 强化学习\n', options: { breakLine: true } },
  { text: '• 知识图谱', options: { breakLine: true } }
], {
  x: 6.5,
  y: 2,
  w: 5.5,
  h: 4,
  fontSize: 16,
  align: 'left',
  margin: 10
});

// Slide 5: Applications
slide = pptx.addSlide();
slide.addText('应用场景', {
  x: 0.5,
  y: 0.5,
  w: 12,
  h: 1,
  fontSize: 28,
  bold: true,
  color: '2a5298',
  align: 'center'
});
slide.addText([
  { text: '• 医疗健康\n', options: { breakLine: true } },
  { text: '• 金融服务\n', options: { breakLine: true } },
  { text: '• 智能制造\n', options: { breakLine: true } },
  { text: '• 自动驾驶', options: { breakLine: true } }
], {
  x: 0.5,
  y: 2,
  w: 5.5,
  h: 4,
  fontSize: 16,
  align: 'left',
  margin: 10
});
slide.addText([
  { text: '• 教育培训\n', options: { breakLine: true } },
  { text: '• 零售电商\n', options: { breakLine: true } },
  { text: '• 智能客服\n', options: { breakLine: true } },
  { text: '• 游戏娱乐', options: { breakLine: true } }
], {
  x: 6.5,
  y: 2,
  w: 5.5,
  h: 4,
  fontSize: 16,
  align: 'left',
  margin: 10
});

// Slide 6: Benefits
slide = pptx.addSlide();
slide.addText('AI的优势', {
  x: 0.5,
  y: 0.5,
  w: 12,
  h: 1,
  fontSize: 28,
  bold: true,
  color: '2a5298',
  align: 'center'
});
slide.addText([
  { text: '• 提高效率\n', options: { breakLine: true } },
  { text: '• 减少错误\n', options: { breakLine: true } },
  { text: '• 24小时服务', options: { breakLine: true } }
], {
  x: 0.5,
  y: 2,
  w: 5.5,
  h: 4,
  fontSize: 16,
  align: 'left',
  margin: 10
});
slide.addText([
  { text: '• 数据分析能力\n', options: { breakLine: true } },
  { text: '• 个性化体验\n', options: { breakLine: true } },
  { text: '• 创新可能性', options: { breakLine: true } }
], {
  x: 6.5,
  y: 2,
  w: 5.5,
  h: 4,
  fontSize: 16,
  align: 'left',
  margin: 10
});

// Slide 7: Challenges
slide = pptx.addSlide();
slide.addText('面临的挑战', {
  x: 0.5,
  y: 0.5,
  w: 12,
  h: 1,
  fontSize: 28,
  bold: true,
  color: '2a5298',
  align: 'center'
});
slide.addText([
  { text: '• 数据隐私与安全\n', options: { breakLine: true } },
  { text: '• 算法偏见与公平性\n', options: { breakLine: true } },
  { text: '• 就业影响与社会伦理\n', options: { breakLine: true } },
  { text: '• 技术透明度与可解释性\n', options: { breakLine: true } },
  { text: '• 对齐问题与控制风险', options: { breakLine: true } }
], {
  x: 0.5,
  y: 1.5,
  w: 12,
  h: 5,
  fontSize: 16,
  align: 'left',
  margin: 10
});

// Slide 8: Future Outlook
slide = pptx.addSlide();
slide.addText('未来展望', {
  x: 0.5,
  y: 1,
  w: 12,
  h: 1,
  fontSize: 36,
  bold: true,
  color: 'FFFFFF',
  fill: { color: '4a6fc5' },
  align: 'center',
  valign: 'middle'
});
slide.addText('AGI(通用人工智能)的发展方向', {
  x: 0.5,
  y: 2.5,
  w: 12,
  h: 1,
  fontSize: 20,
  color: 'FFFFFF',
  fill: { color: '4a6fc5' },
  align: 'center'
});
slide.addText('AI与其他前沿技术的融合', {
  x: 0.5,
  y: 3.5,
  w: 12,
  h: 1,
  fontSize: 20,
  color: 'FFFFFF',
  fill: { color: '4a6fc5' },
  align: 'center'
});
slide.addText('负责任AI的发展路径', {
  x: 0.5,
  y: 4.5,
  w: 12,
  h: 1,
  fontSize: 20,
  color: 'FFFFFF',
  fill: { color: '4a6fc5' },
  align: 'center'
});

// Slide 9: Conclusion
slide = pptx.addSlide();
slide.addText('总结', {
  x: 0.5,
  y: 0.5,
  w: 12,
  h: 1,
  fontSize: 28,
  bold: true,
  color: '2a5298',
  align: 'center'
});
slide.addText([
  { text: '人工智能正在深刻改变我们的世界，为各行各业带来前所未有的机遇。\n\n我们需要以负责任的态度推动AI技术的发展，确保其造福全人类。', options: { breakLine: true } }
], {
  x: 0.5,
  y: 1.5,
  w: 12,
  h: 5,
  fontSize: 16,
  align: 'left',
  margin: 10
});

// Slide 10: Thank You
slide = pptx.addSlide();
slide.addText('谢谢观看！', { 
  x: 0.5, 
  y: 2, 
  w: 12, 
  h: 2, 
  fontSize: 48, 
  bold: true, 
  color: 'FFFFFF',
  fill: { color: '2a5298' },
  align: 'center',
  valign: 'middle'
});
slide.addText('让我们共同迎接AI时代的到来', { 
  x: 0.5, 
  y: 4.5, 
  w: 12, 
  h: 1, 
  fontSize: 24, 
  color: 'FFFFFF',
  fill: { color: '2a5298' },
  align: 'center',
  valign: 'middle'
});

// Save the presentation
pptx.writeFile({ fileName: '/Users/xuan.lx/Documents/x-agent/x-agent/workspace/ai_presentation.pptx' })
  .then(() => {
    console.log('PowerPoint presentation created successfully!');
  })
  .catch(err => {
    console.error('Error creating PowerPoint:', err);
  });