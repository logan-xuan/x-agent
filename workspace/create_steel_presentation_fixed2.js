const fs = require('fs');
const path = require('path');
const pptxgen = require('pptxgenjs');

// Create a new presentation
const pres = new pptxgen();

// Read the HTML file to extract content
const htmlContent = fs.readFileSync('/Users/xuan.lx/Documents/x-agent/x-agent/workspace/steel_workshop.html', 'utf8');

// Add slides based on the HTML content
// Slide 1: Title
pres.addSlide().addText([
    { text: '钢铁是怎样炼成的\n', options: { fontSize: 32, bold: true, color: 'FFFFFF' } },
    { text: 'How Steel Was Tempered', options: { fontSize: 24, bold: true, color: 'FFFFFF' } }
], { 
    x: 0.5, y: 1, w: 9, h: 2, 
    align: 'center', 
    fill: { color: '2C3E50' },
    margin: 20
});
pres.addSlide().addText('经典苏联文学作品 | Classic Soviet Literature\n尼古拉·奥斯特洛夫斯基 | Nikolai Ostrovsky', { 
    x: 0.5, y: 3, w: 9, h: 1, 
    align: 'center', 
    fontSize: 14, 
    color: 'FFFFFF', 
    fill: { color: '34495E' },
    margin: 15
});

// Slide 2: Introduction
const slide2 = pres.addSlide();
slide2.addText('作品简介', { x: 0.5, y: 0.2, w: 9, h: 0.8, fontSize: 28, bold: true, align: 'center', color: 'E74C3C' });
slide2.addText('《钢铁是怎样炼成的》是苏联作家尼古拉·奥斯特洛夫斯基于1932年发表的长篇小说。\n\n这是一部自传体小说，讲述了主人公保尔·柯察金的成长历程。\n\n作品展现了革命精神和坚韧不拔的意志力。', { x: 0.5, y: 1.2, w: 9, h: 3.5, fontSize: 16, align: 'left', margin: 10 });

// Slide 3: Author Background
const slide3 = pres.addSlide();
slide3.addText('作者背景', { x: 0.5, y: 0.2, w: 9, h: 0.8, fontSize: 28, bold: true, align: 'center', color: 'FFFFFF', fill: { color: '3498DB' } });
slide3.addText('尼古拉·奥斯特洛夫斯基 (Nikolai Ostrovsky)\n\n1904年出生于乌克兰的一个工人家庭\n\n15岁参加革命，经历了国内战争的洗礼\n\n25岁时双目失明，全身瘫痪，仍坚持创作\n\n1936年病逝，年仅32岁\n\n小说基于他个人的真实经历创作', { x: 0.5, y: 1.2, w: 9, h: 3.5, fontSize: 16, align: 'left', margin: 10 });

// Slide 4: Plot Summary
const slide4 = pres.addSlide();
slide4.addText('情节概要', { x: 0.5, y: 0.2, w: 9, h: 0.8, fontSize: 28, bold: true, align: 'center', color: 'FFFFFF', fill: { color: 'F39C12' } });
slide4.addText('童年时期 - 在贫困环境中成长，反抗压迫\n\n革命岁月 - 参加红军，在战斗中英勇作战\n\n建设时期 - 投入国家重建，参与铁路修建\n\n疾病斗争 - 面对伤病，以顽强意志继续生活\n\n文学创作 - 在失明瘫痪中完成这部著作', { x: 0.5, y: 1.2, w: 9, h: 3.5, fontSize: 14, align: 'left', margin: 8 });

// Slide 5: Main Character
const slide5 = pres.addSlide();
slide5.addText('主人公：保尔·柯察金', { x: 0.5, y: 0.2, w: 9, h: 0.8, fontSize: 28, bold: true, align: 'center', color: 'FFFFFF', fill: { color: '8E44AD' } });
slide5.addText('保尔·柯察金是小说的主人公，也是作者的化身。他是一个具有钢铁般意志的革命战士。\n\n保尔经历了从无知少年到坚定革命者的转变，即使在身体残疾的情况下，依然坚持为理想奋斗。\n\n他的名言："人最宝贵的是生命……当他回首往事的时候，不会因为碌碌无为、虚度年华而悔恨。"', { x: 0.5, y: 1.2, w: 9, h: 3.5, fontSize: 16, align: 'left', margin: 10 });

// Slide 6: Themes
const slide6 = pres.addSlide();
slide6.addText('主要主题', { x: 0.5, y: 0.2, w: 9, h: 0.8, fontSize: 28, bold: true, align: 'center', color: 'FFFFFF', fill: { color: '16A085' } });
slide6.addText('革命精神 - 为理想而奋斗的革命热情\n\n坚韧不拔 - 面对困难永不放弃的精神\n\n自我牺牲 - 为集体利益奉献个人幸福\n\n理想主义 - 对美好未来的坚定信念\n\n人生意义 - 探讨生命的价值和意义', { x: 0.5, y: 1.2, w: 9, h: 3.5, fontSize: 16, align: 'left', margin: 10 });

// Slide 7: Historical Context
const slide7 = pres.addSlide();
slide7.addText('历史背景', { x: 0.5, y: 0.2, w: 9, h: 0.8, fontSize: 28, bold: true, align: 'center', color: 'FFFFFF', fill: { color: 'E67E22' } });
slide7.addText('时代背景：小说描绘了从第一次世界大战、十月革命、国内战争到经济恢复时期的苏联社会变迁。\n\n社会意义：反映了那个时代的青年如何在革命斗争中锻炼自己，成长为坚强的共产主义战士。\n\n国际影响：作品被翻译成多种语言，在全世界产生了深远的影响，尤其在中国影响了几代人。', { x: 0.5, y: 1.2, w: 9, h: 3.5, fontSize: 14, align: 'left', margin: 10 });

// Slide 8: Literary Significance
const slide8 = pres.addSlide();
slide8.addText('文学价值', { x: 0.5, y: 0.2, w: 9, h: 0.8, fontSize: 28, bold: true, align: 'center', color: 'FFFFFF', fill: { color: '2C3E50' } });
slide8.addText('被誉为共产主义思想教育的教科书\n\n展现了个人命运与时代洪流的结合\n\n塑造了经典的无产阶级英雄形象\n\n激励了无数青年投身革命事业\n\n在中国被列为青少年必读书目之一', { x: 0.5, y: 1.2, w: 9, h: 3.5, fontSize: 14, align: 'left', margin: 8 });

// Slide 9: Adaptations
const slide9 = pres.addSlide();
slide9.addText('改编作品', { x: 0.5, y: 0.2, w: 9, h: 0.8, fontSize: 28, bold: true, align: 'center', color: 'FFFFFF', fill: { color: 'E74C3C' } });
slide9.addText('电影 - 多次被改编为电影，包括中国版\n\n电视剧 - 电视连续剧版本在全球播出\n\n戏剧 - 被改编为话剧、歌剧等多种艺术形式\n\n连环画 - 中国出版了多版本的连环画\n\n动画 - 也有动画片版本面世', { x: 0.5, y: 1.2, w: 9, h: 3.5, fontSize: 16, align: 'left', margin: 10 });

// Slide 10: Conclusion
const slide10 = pres.addSlide();
slide10.addText('结语', { x: 0.5, y: 0.2, w: 9, h: 0.8, fontSize: 28, bold: true, align: 'center', color: '2C3E50', fill: { color: 'F1C40F' } });
slide10.addText('《钢铁是怎样炼成的》不仅是一部文学作品，更是一部人生教科书。\n\n它教会我们如何在逆境中成长，如何以坚韧的意志面对生活的挑战。\n\n"钢是在烈火里燃烧、高度冷却中炼成的，因此它很坚固。"', { x: 0.5, y: 1.2, w: 9, h: 3.5, fontSize: 16, align: 'center', margin: 10 });

// Save the presentation
pres.writeFile('/Users/xuan.lx/Documents/x-agent/x-agent/workspace/steel_how_was_tempered.pptx')
    .then(() => {
        console.log('Presentation saved successfully!');
    })
    .catch(error => {
        console.error('Error creating PowerPoint:', error);
    });