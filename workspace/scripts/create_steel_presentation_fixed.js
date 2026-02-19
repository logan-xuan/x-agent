const fs = require('fs');
const path = require('path');

// 引入pptxgenjs库
const pptx = require('pptxgenjs');

// 创建一个新的PowerPoint演示文稿
const pres = new pptx();

// 幻灯片1: 封面页
let slide = pres.addSlide();
slide.background = { fill: 'E8F4FD' };
slide.addText('钢铁是怎样炼成的', {
  x: 0.5,
  y: 1,
  w: 9,
  h: 1.5,
  font_size: 36,
  bold: true,
  color: '2C3E50',
  align: 'center'
});
slide.addText('经典文学作品介绍', {
  x: 0.5,
  y: 2.2,
  w: 9,
  h: 0.8,
  font_size: 24,
  color: '34495E',
  align: 'center'
});
slide.addImage({ path: 'https://via.placeholder.com/600x400/E8F4FD/2C3E50?text=Book+Cover', x: 2, y: 3.5, w: 6, h: 4 });

// 幻灯片2: 作者介绍
slide = pres.addSlide();
slide.background = { fill: 'FFFFFF' };
slide.addText('作者介绍', { x: 0.5, y: 0.3, w: 9, h: 0.8, font_size: 28, bold: true, color: '2C3E50' });
slide.addText([
  { text: '尼古拉·奥斯特洛夫斯基\n', options: { bold: true, font_size: 20 } },
  { text: '\n生平简介：\n', options: { bold: true } },
  { text: '• 苏联作家，1904年出生于乌克兰\n' },
  { text: '• 参加过国内战争，在战斗中受伤\n' },
  { text: '• 后因伤病全身瘫痪，双目失明\n' },
  { text: '• 凭借坚强意志完成这部作品\n\n' },
  { text: '创作背景：\n', options: { bold: true } },
  { text: '• 1930年开始创作，历时三年\n' },
  { text: '• 以自身经历为基础\n' },
  { text: '• 展现革命者的成长历程' }
], {
  x: 0.5,
  y: 1.2,
  w: 9,
  h: 6,
  font_size: 16,
  color: '34495E',
  lineSpacing: 15
});

// 幻灯片3: 故事梗概
slide = pres.addSlide();
slide.background = { fill: 'FFFFFF' };
slide.addText('故事梗概', { x: 0.5, y: 0.3, w: 9, h: 0.8, font_size: 28, bold: true, color: '2C3E50' });
slide.addText([
  { text: '主人公保尔·柯察金的成长历程：\n\n', options: { bold: true, font_size: 18 } },
  { text: '童年时期：\n', options: { bold: true } },
  { text: '• 出身贫寒，在车站食堂当童工\n' },
  { text: '• 受到革命思想启蒙\n\n' },
  { text: '青年时期：\n', options: { bold: true } },
  { text: '• 参加红军，投身革命斗争\n' },
  { text: '• 在战斗中英勇负伤\n\n' },
  { text: '建设时期：\n', options: { bold: true } },
  { text: '• 参与铁路建设等艰苦工作\n' },
  { text: '• 即使身体残疾仍坚持写作\n\n' },
  { text: '主要情节：\n', options: { bold: true } },
  { text: '• 与冬妮娅、丽达的情感经历\n' },
  { text: '• 坚定的革命信念与奋斗精神' }
], {
  x: 0.5,
  y: 1.2,
  w: 9,
  h: 6,
  font_size: 16,
  color: '34495E',
  lineSpacing: 15
});

// 幻灯片4: 主要人物分析
slide = pres.addSlide();
slide.background = { fill: 'FFFFFF' };
slide.addText('主要人物分析', { x: 0.5, y: 0.3, w: 9, h: 0.8, font_size: 28, bold: true, color: '2C3E50' });
slide.addText([
  { text: '保尔·柯察金：\n', options: { bold: true, font_size: 18 } },
  { text: '• 坚强勇敢，具有钢铁般的意志\n' },
  { text: '• 为理想而献身的精神\n' },
  { text: '• 顽强奋斗，乐观豁达\n' },
  { text: '• 自我牺牲精神\n\n' },
  { text: '其他重要角色：\n', options: { bold: true, font_size: 18 } },
  { text: '• 朱赫来：革命引路人\n' },
  { text: '• 冬妮娅：初恋情人\n' },
  { text: '• 丽达：志同道合的战友\n' },
  { text: '• 达雅：妻子，精神支持者' }
], {
  x: 0.5,
  y: 1.2,
  w: 9,
  h: 6,
  font_size: 16,
  color: '34495E',
  lineSpacing: 15
});

// 幻灯片5: 主题思想
slide = pres.addSlide();
slide.background = { fill: 'FFFFFF' };
slide.addText('主题思想', { x: 0.5, y: 0.3, w: 9, h: 0.8, font_size: 28, bold: true, color: '2C3E50' });
slide.addText([
  { text: '革命理想主义：\n', options: { bold: true } },
  { text: '• 为共产主义事业奋斗终生\n' },
  { text: '• 将个人命运与国家前途结合\n\n' },
  { text: '顽强拼搏精神：\n', options: { bold: true } },
  { text: '• 面对困难永不退缩\n' },
  { text: '• 在逆境中磨练意志\n\n' },
  { text: '人生意义探讨：\n', options: { bold: true } },
  { text: '• 生命的价值在于奉献\n' },
  { text: '• 为人民利益而活\n' },
  { text: '• 让生命更有意义' }
], {
  x: 0.5,
  y: 1.2,
  w: 9,
  h: 6,
  font_size: 16,
  color: '34495E',
  lineSpacing: 15
});

// 幻灯片6: 经典语录
slide = pres.addSlide();
slide.background = { fill: 'FFFFFF' };
slide.addText('经典语录', { x: 0.5, y: 0.3, w: 9, h: 0.8, font_size: 28, bold: true, color: '2C3E50' });
slide.addText([
  { text: '书中著名段落摘选：\n\n', options: { bold: true, font_size: 18 } },
  { text: '"人最宝贵的是生命，生命属于人只有一次..."', options: { bold: true, color: 'E74C3C' } },
  { text: '\n\n"钢是在烈火里燃烧、高度冷却中炼成的..."', options: { bold: true, color: 'E74C3C' } },
  { text: '\n\n"即使生活到了难以忍受的地步，也要善于生活，并使生活有益而充实"', options: { bold: true, color: 'E74C3C' } },
  { text: '\n\n"对我来说，活着的每一天都意味着要和巨大的痛苦作斗争，但你们看到的是我脸上的微笑"', options: { bold: true, color: 'E74C3C' } }
], {
  x: 0.5,
  y: 1.2,
  w: 9,
  h: 6,
  font_size: 16,
  color: '34495E',
  lineSpacing: 20
});

// 幻灯片7: 文学价值
slide = pres.addSlide();
slide.background = { fill: 'FFFFFF' };
slide.addText('文学价值', { x: 0.5, y: 0.3, w: 9, h: 0.8, font_size: 28, bold: true, color: '2C3E50' });
slide.addText([
  { text: '在世界文学史上的地位：\n', options: { bold: true } },
  { text: '• 社会主义现实主义文学经典\n' },
  { text: '• 影响了几代人的励志小说\n' },
  { text: '• 被翻译成多种语言传播\n\n' },
  { text: '对后世的影响：\n', options: { bold: true } },
  { text: '• 激发无数读者的奋斗精神\n' },
  { text: '• 成为教育青少年的重要读物\n' },
  { text: '• 在多个国家被改编为影视作品' }
], {
  x: 0.5,
  y: 1.2,
  w: 9,
  h: 6,
  font_size: 16,
  color: '34495E',
  lineSpacing: 15
});

// 幻灯片8: 现实意义
slide = pres.addSlide();
slide.background = { fill: 'FFFFFF' };
slide.addText('现实意义', { x: 0.5, y: 0.3, w: 9, h: 0.8, font_size: 28, bold: true, color: '2C3E50' });
slide.addText([
  { text: '对当代人的启示：\n', options: { bold: true } },
  { text: '• 面对挫折要有坚韧不拔的精神\n' },
  { text: '• 树立正确的人生观和价值观\n' },
  { text: '• 为理想而不懈努力\n\n' },
  { text: '激励作用：\n', options: { bold: true } },
  { text: '• 鼓舞人们克服困难\n' },
  { text: '• 培养积极向上的生活态度\n' },
  { text: '• 塑造坚强的意志品质' }
], {
  x: 0.5,
  y: 1.2,
  w: 9,
  h: 6,
  font_size: 16,
  color: '34495E',
  lineSpacing: 15
});

// 幻灯片9: 读后感想
slide = pres.addSlide();
slide.background = { fill: 'FFFFFF' };
slide.addText('读后感想', { x: 0.5, y: 0.3, w: 9, h: 0.8, font_size: 28, bold: true, color: '2C3E50' });
slide.addText([
  { text: '读者评价：\n', options: { bold: true } },
  { text: '• 一部激励人心的英雄史诗\n' },
  { text: '• 人生教科书式的经典作品\n' },
  { text: '• 告诉我们如何让生命更有意义\n\n' },
  { text: '个人感悟：\n', options: { bold: true } },
  { text: '• 意志力的重要性\n' },
  { text: '• 理想信念的力量\n' },
  { text: '• 为他人和社会奉献的精神' }
], {
  x: 0.5,
  y: 1.2,
  w: 9,
  h: 6,
  font_size: 16,
  color: '34495E',
  lineSpacing: 15
});

// 幻灯片10: 结语
slide = pres.addSlide();
slide.background = { fill: 'E8F4FD' };
slide.addText('结语', { x: 0.5, y: 0.3, w: 9, h: 0.8, font_size: 28, bold: true, color: '2C3E50' });
slide.addText([
  { text: '《钢铁是怎样炼成的》不仅是一部文学作品，更是一部人生教科书。\n\n', options: { font_size: 18 } },
  { text: '保尔·柯察金的坚强意志和革命精神，至今仍然激励着无数读者。\n\n' },
  { text: '让我们从这本书中汲取力量，以钢铁般的意志面对生活中的各种挑战。\n\n' },
  { text: '推荐大家阅读原著，深入体会其中的精神内涵。' }
], {
  x: 0.5,
  y: 2,
  w: 9,
  h: 5,
  font_size: 16,
  color: '34495E',
  align: 'center',
  lineSpacing: 20
});

// 保存PowerPoint文件
pres.writeFile('steel_how_it_is_made_presentation.pptx').then(() => {
  console.log('PPT文件创建成功！');
});