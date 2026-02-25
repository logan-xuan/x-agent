const PDFDocument = require('pdfkit');
const fs = require('fs');

// 创建PDF文档实例
const doc = new PDFDocument();
const filename = '/Users/xuan.lx/Documents/x-agent/x-agent/workspace/pdfs/hangzhou_tourism_plan.pdf';

// 将PDF写入文件
doc.pipe(fs.createWriteStream(filename));

// 设置标题
doc.fontSize(24).text('杭州明日旅游计划', 100, 50);
doc.moveDown();

// 添加日期和天气信息
doc.fontSize(14).text(`日期: 2026年2月24日`, 100, 120);
doc.text(`天气: 小雨转多云`, 100, 140);
doc.text(`温度: 8°C ~ 13°C`, 100, 160);
doc.text(`风力: 北风<3级`, 100, 180);
doc.moveDown();

// 添加上午行程
doc.fontSize(18).text('上午行程 (9:00-12:00)', 100, 240);
doc.fontSize(12).text('1. 中国丝绸博物馆', 100, 270);
doc.text('  - 可以了解杭州丝绸文化历史', 120, 290);
doc.text('  - 室内景点，不受天气影响', 120, 310);
doc.text('  - 地址：杭州市西湖区玉皇山路73-1号', 120, 330);

doc.text('2. 浙江省博物馆', 100, 360);
doc.text('  - 欣赏江南文化和艺术品', 120, 380);
doc.text('  - 室内景点，适合雨天参观', 120, 400);
doc.moveDown();

// 添加下午行程
doc.fontSize(18).text('下午行程 (13:30-17:00)', 100, 440);
doc.fontSize(12).text('1. 河坊街-南宋御街', 100, 470);
doc.text('  - 古色古香的步行街，部分路段有遮蔽设施', 120, 490);
doc.text('  - 适合品尝杭州小吃，购买特产', 120, 510);
doc.text('  - 可以逛胡庆余堂中药博物馆等室内景点', 120, 530);

doc.text('2. 中国茶叶博物馆', 100, 560);
doc.text('  - 了解龙井茶文化', 120, 580);
doc.text('  - 室内参观，还可以品茶暖身', 120, 600);

// 新页面
doc.addPage();

// 添加傍晚行程
doc.fontSize(18).text('傍晚行程 (17:00-19:00)', 100, 50);
doc.fontSize(12).text('1. 京杭大运河游船', 100, 80);
doc.text('  - 即使小雨也可乘船游览，别有一番风味', 120, 100);
doc.text('  - 运河夜景美丽，船上有遮蔽设施', 120, 120);

// 添加备选晴天方案
doc.fontSize(18).text('备选晴天方案', 100, 170);
doc.fontSize(12).text('如果天气好转，可以考虑：', 100, 200);
doc.text('- 西湖风景区：断桥残雪、平湖秋月等景点', 120, 220);
doc.text('- 灵隐寺：著名的佛教寺庙', 120, 240);
doc.text('- 西溪国家湿地公园', 120, 260);

// 添加出行提示
doc.fontSize(18).text('出行提示', 100, 310);
doc.fontSize(12).text('1. 必备物品：雨伞或雨衣、防滑鞋', 100, 340);
doc.text('2. 衣物建议：保暖外套，温度较低', 100, 360);
doc.text('3. 预约提醒：热门景点建议提前在官方公众号预约', 100, 380);
doc.text('4. 交通：雨天路滑，请注意交通安全', 100, 400);

// 添加结束语
doc.fontSize(14).text('祝您在杭州度过愉快的一天！', 100, 480);

// 结束文档
doc.end();

console.log('PDF文件已生成:', filename);