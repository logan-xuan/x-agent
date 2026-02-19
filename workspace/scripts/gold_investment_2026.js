const fs = require('fs');
const path = require('path');

// Check if pptxgenjs is available
let pptx;
try {
  pptx = require('pptxgenjs');
} catch (error) {
  console.error('Error loading pptxgenjs:', error.message);
  process.exit(1);
}

console.log('Creating presentation...');

// Create new PptxGenJS object
let pres = new pptx();

// Set presentation properties
pres.title = '2026年黄金投资价值分析';
pres.author = 'Investment Analysis Team';
pres.company = 'Financial Consulting Group';

// Slide 1: Title slide
let titleSlide = pres.addSlide();
titleSlide.addText('2026年黄金还值得投资吗？', { 
  x: 0.5, 
  y: 1.5, 
  w: 9, 
  h: 1.5, 
  fontSize: 32, 
  bold: true, 
  color: '00008B',
  align: 'center'
});
titleSlide.addText('黄金投资价值分析报告', { 
  x: 0.5, 
  y: 3, 
  w: 9, 
  h: 0.8, 
  fontSize: 20, 
  italic: true,
  color: '4B0082',
  align: 'center'
});
titleSlide.addText('2026年度投资策略专题', { 
  x: 0.5, 
  y: 4, 
  w: 9, 
  h: 0.8, 
  fontSize: 16, 
  color: '333333',
  align: 'center'
});

// Slide 2: Table of Contents
let tocSlide = pres.addSlide();
tocSlide.addText('目录', { 
  x: 0.5, 
  y: 0.3, 
  w: 9, 
  h: 0.6, 
  fontSize: 28, 
  bold: true, 
  color: '00008B' 
});
const tocItems = [
  '1. 黄金投资概述',
  '2. 2026年经济环境分析',
  '3. 影响黄金价格的因素',
  '4. 黄金与其他资产对比',
  '5. 投资策略建议',
  '6. 风险提示',
  '7. 总结与展望'
];
tocItems.forEach((item, index) => {
  tocSlide.addText(item, { 
    x: 1, 
    y: 1 + (index * 0.5), 
    w: 8, 
    h: 0.4, 
    fontSize: 16, 
    bullet: true 
  });
});

// Slide 3: Gold Investment Overview
let overviewSlide = pres.addSlide();
overviewSlide.addText('黄金投资概述', { 
  x: 0.5, 
  y: 0.3, 
  w: 9, 
  h: 0.6, 
  fontSize: 28, 
  bold: true, 
  color: '00008B' 
});
const overviewPoints = [
  '避险资产：在不确定时期保值增值',
  '通胀对冲：抵御货币贬值风险',
  '分散化投资：降低投资组合波动',
  '流动性强：全球市场交易活跃',
  '历史表现：长期保值功能显著'
];
overviewPoints.forEach((point, index) => {
  overviewSlide.addText(point, { 
    x: 1, 
    y: 1.2 + (index * 0.6), 
    w: 8, 
    h: 0.5, 
    fontSize: 16, 
    bullet: true 
  });
});

// Slide 4: 2026 Economic Environment Analysis
let economySlide = pres.addSlide();
economySlide.addText('2026年经济环境分析', { 
  x: 0.5, 
  y: 0.3, 
  w: 9, 
  h: 0.6, 
  fontSize: 28, 
  bold: true, 
  color: '00008B' 
});
const economyPoints = [
  '全球经济增长预期：温和复苏或面临挑战',
  '通胀水平：各国央行政策分化',
  '地缘政治风险：不确定性因素增加',
  '货币政策：利率走势影响投资偏好',
  '美元走势：对金价形成直接影响'
];
economyPoints.forEach((point, index) => {
  economySlide.addText(point, { 
    x: 1, 
    y: 1.2 + (index * 0.6), 
    w: 8, 
    h: 0.5, 
    fontSize: 16, 
    bullet: true 
  });
});

// Slide 5: Factors Affecting Gold Prices
let factorsSlide = pres.addSlide();
factorsSlide.addText('影响黄金价格的主要因素', { 
  x: 0.5, 
  y: 0.3, 
  w: 9, 
  h: 0.6, 
  fontSize: 28, 
  bold: true, 
  color: '00008B' 
});
const factorPoints = [
  '供需关系：开采量vs消费需求',
  '央行储备：各国央行购金政策',
  '投机需求：ETF持仓变化',
  '美元指数：负相关关系',
  '通胀预期：实际利率影响',
  '避险情绪：市场恐慌指数'
];
factorPoints.forEach((point, index) => {
  factorsSlide.addText(point, { 
    x: 1, 
    y: 1.2 + (index * 0.5), 
    w: 8, 
    h: 0.4, 
    fontSize: 16, 
    bullet: true 
  });
});

// Slide 6: Gold vs Other Assets
let comparisonSlide = pres.addSlide();
comparisonSlide.addText('黄金与其他资产对比', { 
  x: 0.5, 
  y: 0.3, 
  w: 9, 
  h: 0.6, 
  fontSize: 28, 
  bold: true, 
  color: '00008B' 
});
const comparisonHeaders = ['资产类别', '收益率', '波动性', '流动性', '避险属性'];
const comparisonRows = [
  ['黄金', '中等', '中高', '高', '强'],
  ['股票', '高', '高', '高', '弱'],
  ['债券', '低中', '低', '中高', '中'],
  ['房地产', '中', '中', '低', '中'],
  ['加密货币', '极高', '极高', '中', '弱']
];
comparisonSlide.addTable([
  comparisonHeaders,
  ...comparisonRows
], {
  x: 0.5,
  y: 1.2,
  w: 9,
  h: 4,
  fontSize: 14,
  align: 'center',
  border: { pt: 1, color: '363636' },
  fill: 'F5F5F5'
});

// Slide 7: Investment Strategy Recommendations
let strategySlide = pres.addSlide();
strategySlide.addText('投资策略建议', { 
  x: 0.5, 
  y: 0.3, 
  w: 9, 
  h: 0.6, 
  fontSize: 28, 
  bold: true, 
  color: '00008B' 
});
const strategyPoints = [
  '配置比例：投资组合中占比5%-15%',
  '分批建仓：避免一次性投入风险',
  '长期持有：发挥保值增值功能',
  '关注时机：结合技术面和基本面',
  '多样化投资：实物金、纸黄金、黄金股'
];
strategyPoints.forEach((point, index) => {
  strategySlide.addText(point, { 
    x: 1, 
    y: 1.2 + (index * 0.6), 
    w: 8, 
    h: 0.5, 
    fontSize: 16, 
    bullet: true 
  });
});

// Slide 8: Risk Warnings
let riskSlide = pres.addSlide();
riskSlide.addText('风险提示', { 
  x: 0.5, 
  y: 0.3, 
  w: 9, 
  h: 0.6, 
  fontSize: 28, 
  bold: true, 
  color: '00008B' 
});
const riskPoints = [
  '价格波动：短期可能面临较大波动',
  '机会成本：无利息收入',
  '存储成本：实物黄金保管费用',
  '流动性风险：特定情况下的变现难度',
  '汇率风险：国际金价受美元影响'
];
riskPoints.forEach((point, index) => {
  riskSlide.addText(point, { 
    x: 1, 
    y: 1.2 + (index * 0.6), 
    w: 8, 
    h: 0.5, 
    fontSize: 16, 
    bullet: true 
  });
});

// Slide 9: Summary and Outlook
let summarySlide = pres.addSlide();
summarySlide.addText('总结与展望', { 
  x: 0.5, 
  y: 0.3, 
  w: 9, 
  h: 0.6, 
  fontSize: 28, 
  bold: true, 
  color: '00008B' 
});
const summaryPoints = [
  '黄金作为避险资产地位稳固',
  '2026年不确定性增加，利好黄金',
  '建议适度配置，分散投资风险',
  '关注美联储政策和地缘政治',
  '长期看好黄金保值功能'
];
summaryPoints.forEach((point, index) => {
  summarySlide.addText(point, { 
    x: 1, 
    y: 1.2 + (index * 0.6), 
    w: 8, 
    h: 0.5, 
    fontSize: 16, 
    bullet: true 
  });
});

// Save the presentation
const outputPath = path.join(__dirname, '2026黄金投资价值分析.pptx');
pres.writeFile(outputPath).then(() => {
  console.log(`Presentation saved successfully at ${outputPath}`);
}).catch(error => {
  console.error('Error saving presentation:', error);
});