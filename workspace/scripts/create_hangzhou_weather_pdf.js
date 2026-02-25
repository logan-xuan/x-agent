const PDFDocument = require('pdfkit');
const fs = require('fs');
const path = require('path');

// Create a document
const doc = new PDFDocument();
const outputFilename = '/Users/xuan.lx/Documents/x-agent/x-agent/workspace/pdfs/hangzhou_weather_report.pdf';
const stream = fs.createWriteStream(outputFilename);
doc.pipe(stream);

// Register Chinese font - Use system fonts
// macOS has built-in Chinese fonts
const chineseFontPath = '/System/Library/Fonts/PingFang.ttc';

// Check if font exists, otherwise use fallback
let fontRegistered = false;
try {
  if (fs.existsSync(chineseFontPath)) {
    doc.registerFont('Chinese', chineseFontPath);
    doc.font('Chinese');
    fontRegistered = true;
    console.log('Chinese font registered successfully');
  }
} catch (error) {
  console.warn('Failed to register Chinese font, will use default font:', error.message);
}

// If font registration failed, try alternative system fonts
if (!fontRegistered) {
  const alternatives = [
    '/System/Library/Fonts/STHeiti Light.ttc',
    '/System/Library/Fonts/STHeiti Medium.ttc',
    '/Library/Fonts/Arial Unicode.ttf',
  ];
  
  for (const fontPath of alternatives) {
    try {
      if (fs.existsSync(fontPath)) {
        doc.registerFont('Chinese', fontPath);
        doc.font('Chinese');
        fontRegistered = true;
        console.log(`Alternative font registered: ${fontPath}`);
        break;
      }
    } catch (error) {
      continue;
    }
  }
}

if (!fontRegistered) {
  console.warn('No Chinese font available - text may not display correctly');
}

// Add title
doc.fontSize(20).text('杭州明日天气旅游指南', 100, 100);

// Add weather info
doc.fontSize(14).text('日期: 2026年2月24日', 100, 150);
doc.fontSize(14).text('天气: 小雨转多云', 100, 170);
doc.fontSize(14).text('温度: 8°C ~ 13°C', 100, 190);
doc.fontSize(14).text('风力: 北风<3级', 100, 210);

// Add recommendations
doc.fontSize(16).text('推荐活动:', 100, 250);
doc.fontSize(12).text('1. 中国丝绸博物馆 - 室内景点，不受天气影响', 100, 280);
doc.fontSize(12).text('2. 浙江省博物馆 - 欣赏江南文化和艺术品', 100, 300);
doc.fontSize(12).text('3. 河坊街-南宋御街 - 古色古香的步行街，部分路段有遮蔽', 100, 320);
doc.fontSize(12).text('4. 中国茶叶博物馆 - 了解龙井茶文化，室内参观', 100, 340);
doc.fontSize(12).text('5. 京杭大运河游船 - 雨天乘船别有一番风味', 100, 360);

// Add travel plan
doc.fontSize(16).text('一日旅游计划:', 100, 400);
doc.fontSize(12).text('上午 (9:00-12:00): 中国丝绸博物馆 -> 浙江省博物馆', 100, 430);
doc.fontSize(12).text('下午 (13:30-17:00): 河坊街-南宋御街 -> 中国茶叶博物馆', 100, 450);
doc.fontSize(12).text('傍晚 (17:00-19:00): 京杭大运河游船', 100, 470);

// Add tips
doc.fontSize(16).text('出行提示:', 100, 510);
doc.fontSize(12).text('• 必备物品: 雨伞或雨衣、防滑鞋', 100, 540);
doc.fontSize(12).text('• 衣物建议: 保暖外套，温度较低', 100, 560);
doc.fontSize(12).text('• 预约提醒: 热门景点建议提前在官方公众号预约', 100, 580);
doc.fontSize(12).text('• 交通: 雨天路滑，请注意交通安全', 100, 600);

// Finalize PDF file
doc.end();

// Check when the PDF is finished writing
stream.on('finish', () => {
  console.log('PDF created successfully at:', outputFilename);
});