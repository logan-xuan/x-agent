const PDFDocument = require('pdfkit');
const fs = require('fs');

// 创建PDF文档实例
const doc = new PDFDocument();
const filename = 'hangzhou_tomorrow_travel_plan.pdf';

// 将PDF写入文件
doc.pipe(fs.createWriteStream(`${__dirname}/../pdfs/` + filename));

// 设置标题
doc.fontSize(24).text('杭州明日旅游计划', 50, 50);
doc.moveDown();

// 添加天气信息
doc.fontSize(16).text('天气预报：', 50, 120);
doc.fontSize(12).text('日期：2026年2月24日', 50, 150);
doc.text('天气状况：小雨转多云', 50, 170);
doc.text('温度范围：8°C ~ 13°C', 50, 190);
doc.text('风力：北风<3级', 50, 210);
doc.text('降雨概率：74%', 50, 230);

doc.moveDown(2);

// 添加旅游建议
doc.fontSize(16).text('旅游建议：', 50, 280);
doc.fontSize(12).text('由于明天可能下雨，建议准备雨具并考虑以下室内或半室内景点：', 50, 310);

doc.moveDown();

// 上午行程
doc.fontSize(14).text('上午行程 (9:00-12:00)', 50, 350);
doc.fontSize(12).text('1. 中国丝绸博物馆', 50, 380);
doc.text('   - 可以了解杭州丝绸文化历史', 50, 400);
doc.text('   - 室内景点，不受天气影响', 50, 420);
doc.text('   - 地址：杭州市西湖区玉皇山路73-1号', 50, 440);

doc.text('2. 浙江省博物馆', 50, 470);
doc.text('   - 欣赏江南文化和艺术品', 50, 490);
doc.text('   - 室内景点，适合雨天参观', 50, 510);

// 下午行程
doc.fontSize(14).text('下午行程 (13:30-17:00)', 50, 540);
doc.fontSize(12).text('1. 河坊街-南宋御街', 50, 570);
doc.text('   - 古色古香的步行街，部分路段有遮蔽设施', 50, 590);
doc.text('   - 适合品尝杭州小吃，购买特产', 50, 610);
doc.text('   - 可以逛胡庆余堂中药博物馆等室内景点', 50, 630);

doc.text('2. 中国茶叶博物馆', 50, 660);
doc.text('   - 了解龙井茶文化', 50, 680);
doc.text('   - 室内参观，还可以品茶暖身', 50, 700);

// 结束文档
doc.end();

console.log('PDF created successfully!');