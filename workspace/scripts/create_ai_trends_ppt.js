const fs = require('fs');
const PptxGenJS = require('pptxgenjs');

// Create a new presentation
const pptx = new PptxGenJS();

// Set theme colors
const themeColors = {
  primary: '2E5090',
  secondary: 'F58534',
  accent: '6EB5E0',
  text: '2C2C2C',
  background: 'FFFFFF'
};

// Slide 1: Title slide
let slide = pptx.addSlide();
slide.addText('2026年AI发展趋势', {
  x: 0.5,
  y: 2,
  w: 9,
  h: 1.5,
  fontSize: 36,
  bold: true,
  color: themeColors.primary,
  align: 'center'
});
slide.addText('深度研究报告', {
  x: 0.5,
  y: 3.5,
  w: 9,
  h: 1,
  fontSize: 24,
  color: themeColors.secondary,
  align: 'center'
});
slide.addText('AI Trends 2026', {
  x: 0.5,
  y: 5,
  w: 9,
  h: 0.8,
  fontSize: 18,
  italic: true,
  color: themeColors.text,
  align: 'center'
});
slide.addText('虾铁蛋 制作', {
  x: 0.5,
  y: 8,
  w: 9,
  h: 0.5,
  fontSize: 14,
  color: themeColors.text,
  align: 'center'
});

// Slide 2: Table of Contents
slide = pptx.addSlide();
slide.addText('目录', {
  x: 0.5,
  y: 0.5,
  w: 9,
  h: 0.8,
  fontSize: 28,
  bold: true,
  color: themeColors.primary
});
const tocItems = [
  '引言与背景',
  '八大主要趋势',
  '技术预测',
  '应用领域展望',
  '挑战与机遇',
  '结论与展望'
];
tocItems.forEach((item, index) => {
  slide.addText(`${index + 1}. ${item}`, {
    x: 1,
    y: 1.5 + index * 0.6,
    w: 8,
    h: 0.5,
    fontSize: 18,
    bullet: true,
    color: themeColors.text
  });
});

// Slide 3: Introduction
slide = pptx.addSlide();
slide.addText('引言与背景', {
  x: 0.5,
  y: 0.5,
  w: 9,
  h: 0.8,
  fontSize: 28,
  bold: true,
  color: themeColors.primary
});
slide.addText([
  { text: '• 2025年是AI应用加速落地的一年', options: { breakLine: true } },
  { text: '• 2026年人工智能发展将继续深化', options: { breakLine: true } },
  { text: '• 从技术创新到应用场景都将迎来新变革', options: { breakLine: true } },
  { text: '• 预计2026年国内AI核心产业规模突破1.2万亿元', options: { breakLine: true } }
], {
  x: 1,
  y: 1.8,
  w: 8,
  h: 5,
  fontSize: 16,
  color: themeColors.text
});

// Slide 4: Eight Major Trends
slide = pptx.addSlide();
slide.addText('2026年八大主要趋势', {
  x: 0.5,
  y: 0.5,
  w: 9,
  h: 0.8,
  fontSize: 28,
  bold: true,
  color: themeColors.primary
});
const trends = [
  'AI治理全球化',
  '智能算力规模化',
  '应用主流化',
  '多模态实用化',
  '原生AI终端硬件普及化',
  'AI Agent技术成熟',
  '世界模型成为AGI共识方向',
  '云3.0时代到来'
];
trends.forEach((trend, index) => {
  const row = Math.floor(index / 2);
  const col = index % 2;
  slide.addText(`${index + 1}. ${trend}`, {
    x: 1 + col * 4,
    y: 1.5 + row * 0.8,
    w: 3.5,
    h: 0.6,
    fontSize: 14,
    bullet: true,
    color: themeColors.text
  });
});

// Slide 5: Trend Details - Part 1
slide = pptx.addSlide();
slide.addText('八大趋势详解 (一)', {
  x: 0.5,
  y: 0.5,
  w: 9,
  h: 0.8,
  fontSize: 28,
  bold: true,
  color: themeColors.primary
});
slide.addText([
  { text: 'AI治理全球化:', options: { breakLine: true, bold: true } },
  { text: '全球统一AI伦理标准和监管框架建设', options: { breakLine: true } },
  { text: '', options: { breakLine: true } },
  { text: '智能算力规模化:', options: { breakLine: true, bold: true } },
  { text: '国产AI芯片规模化应用，全国一体化算力网建设', options: { breakLine: true } },
  { text: '', options: { breakLine: true } },
  { text: '应用主流化:', options: { breakLine: true, bold: true } },
  { text: '从通用能力转向解决垂直领域行业痛点', options: { breakLine: true } },
  { text: '', options: { breakLine: true } },
  { text: '多模态实用化:', options: { breakLine: true, bold: true } },
  { text: '"世界模型"技术，从感知智能向决策智能演进', options: { breakLine: true } }
], {
  x: 0.8,
  y: 1.5,
  w: 8.5,
  h: 6.5,
  fontSize: 14,
  color: themeColors.text
});

// Slide 6: Trend Details - Part 2
slide = pptx.addSlide();
slide.addText('八大趋势详解 (二)', {
  x: 0.5,
  y: 0.5,
  w: 9,
  h: 0.8,
  fontSize: 28,
  bold: true,
  color: themeColors.primary
});
slide.addText([
  { text: '原生AI终端硬件普及化:', options: { breakLine: true, bold: true } },
  { text: '终端硬件从"工具适配"转向"原生AI设计"', options: { breakLine: true } },
  { text: '', options: { breakLine: true } },
  { text: 'AI Agent技术成熟:', options: { breakLine: true, bold: true } },
  { text: '具备自主性、能举一反三和长期记忆特征', options: { breakLine: true } },
  { text: '', options: { breakLine: true } },
  { text: '世界模型成为AGI共识方向:', options: { breakLine: true, bold: true } },
  { text: 'Next-State Prediction新技术范式', options: { breakLine: true } },
  { text: '', options: { breakLine: true } },
  { text: '云3.0时代到来:', options: { breakLine: true, bold: true } },
  { text: '以混合云、边缘计算和分布式架构为核心', options: { breakLine: true } }
], {
  x: 0.8,
  y: 1.5,
  w: 8.5,
  h: 6.5,
  fontSize: 14,
  color: themeColors.text
});

// Slide 7: Technology Predictions
slide = pptx.addSlide();
slide.addText('技术预测', {
  x: 0.5,
  y: 0.5,
  w: 9,
  h: 0.8,
  fontSize: 28,
  bold: true,
  color: themeColors.primary
});
slide.addText([
  { text: '智能体AI的崛起:', options: { breakLine: true, bold: true } },
  { text: '具备更强自主性和适应性，能在复杂环境中独立完成任务', options: { breakLine: true } },
  { text: '', options: { breakLine: true } },
  { text: '专业能力转型:', options: { breakLine: true, bold: true } },
  { text: '转向系统思维、AI与智能体编排、复杂流程管理', options: { breakLine: true } },
  { text: '', options: { breakLine: true } },
  { text: '算力与应用平衡:', options: { breakLine: true, bold: true } },
  { text: 'AI应用市场增长率48.3% > 算力市场22.5%', options: { breakLine: true } }
], {
  x: 0.8,
  y: 1.5,
  w: 8.5,
  h: 6.5,
  fontSize: 16,
  color: themeColors.text
});

// Slide 8: Application Areas
slide = pptx.addSlide();
slide.addText('应用领域展望', {
  x: 0.5,
  y: 0.5,
  w: 9,
  h: 0.8,
  fontSize: 28,
  bold: true,
  color: themeColors.primary
});
const appAreas = [
  { title: '企业服务', desc: 'AI智能客服，已服务超过40万家企业' },
  { title: '消费级应用', desc: '原生AI终端硬件普及，融入日常生活' },
  { title: '行业解决方案', desc: '金融、医疗、制造、教育等领域深度应用' }
];
appAreas.forEach((area, index) => {
  const y = 1.5 + index * 2.2;
  slide.addShape(pptx.ShapeType.rect, {
    x: 0.8,
    y: y - 0.2,
    w: 8.5,
    h: 1.8,
    fill: { color: themeColors.accent, transparency: 20 },
    line: { color: themeColors.accent }
  });
  slide.addText(area.title, {
    x: 1,
    y: y,
    w: 8,
    h: 0.5,
    fontSize: 18,
    bold: true,
    color: themeColors.primary
  });
  slide.addText(area.desc, {
    x: 1.2,
    y: y + 0.7,
    w: 7.8,
    h: 0.8,
    fontSize: 14,
    color: themeColors.text
  });
});

// Slide 9: Challenges and Opportunities
slide = pptx.addSlide();
slide.addText('挑战与机遇', {
  x: 0.5,
  y: 0.5,
  w: 9,
  h: 0.8,
  fontSize: 28,
  bold: true,
  color: themeColors.primary
});

// Challenges column
slide.addText('挑战', {
  x: 1,
  y: 1.5,
  w: 3,
  h: 0.5,
  fontSize: 18,
  bold: true,
  color: 'FF0000'
});
const challenges = [
  'AI治理和监管框架建立',
  '数据隐私和安全问题',
  '技术标准化和互操作性',
  '人才培养和技能转型'
];
challenges.forEach((challenge, index) => {
  slide.addText(`• ${challenge}`, {
    x: 1,
    y: 2.2 + index * 0.5,
    w: 3,
    h: 0.4,
    fontSize: 14,
    color: themeColors.text
  });
});

// Opportunities column
slide.addText('机遇', {
  x: 5.5,
  y: 1.5,
  w: 3,
  h: 0.5,
  fontSize: 18,
  bold: true,
  color: '00AA00'
});
const opportunities = [
  '全球AI市场规模扩大',
  '新兴技术融合创新',
  '垂直行业转型需求',
  '国产AI生态完善'
];
opportunities.forEach((opportunity, index) => {
  slide.addText(`• ${opportunity}`, {
    x: 5.5,
    y: 2.2 + index * 0.5,
    w: 3,
    h: 0.4,
    fontSize: 14,
    color: themeColors.text
  });
});

// Slide 10: Conclusion
slide = pptx.addSlide();
slide.addText('结论与展望', {
  x: 0.5,
  y: 0.5,
  w: 9,
  h: 0.8,
  fontSize: 28,
  bold: true,
  color: themeColors.primary
});
slide.addText([
  { text: '2026年将是AI发展的重要转折点', options: { breakLine: true } },
  { text: '从技术探索到应用落地的转变加速', options: { breakLine: true } },
  { text: '', options: { breakLine: true } },
  { text: '主要趋势:', options: { breakLine: true, bold: true } },
  { text: '• AI治理全球化', options: { breakLine: true } },
  { text: '• 智能算力规模化', options: { breakLine: true } },
  { text: '• 应用主流化', options: { breakLine: true } },
  { text: '', options: { breakLine: true } },
  { text: '前沿技术推动突破性进展', options: { breakLine: true } },
  { text: '合规、安全基础上释放AI价值', options: { breakLine: true } }
], {
  x: 0.8,
  y: 1.5,
  w: 8.5,
  h: 6.5,
  fontSize: 16,
  color: themeColors.text
});

// Save the presentation
pptx.writeFile({ fileName: '/Users/xuan.lx/Documents/x-agent/x-agent/workspace/presentations/ai_trends_2026_presentation.pptx' });