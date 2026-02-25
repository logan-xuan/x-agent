const PptxGenJS = require('pptxgenjs');
const fs = require('fs');

// 读取配置文件
const configPath = './presentations/ai_trends_2026_config.json';
const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));

// Create a new PowerPoint presentation
const pptx = new PptxGenJS();

// Set presentation properties
pptx.author = '虾铁蛋AI助手';
pptx.company = 'Personal AI Agent';
pptx.revision = '1.0';

// Process each slide based on the configuration
config.slides.forEach((slideData, index) => {
  const slide = pptx.addSlide();
  
  switch(slideData.layout) {
    case 'titleSlide':
      // Title slide with large title and subtitle
      slide.addText(slideData.title, {
        x: 0.5,
        y: 1.5,
        w: 9,
        h: 2,
        fontSize: 40,
        bold: true,
        color: '363636',
        align: 'center'
      });
      
      if (slideData.subtitle) {
        slide.addText(slideData.subtitle, {
          x: 0.5,
          y: 3.5,
          w: 9,
          h: 1,
          fontSize: 24,
          color: '666666',
          align: 'center'
        });
      }
      
      if (slideData.author || slideData.date) {
        let footerText = '';
        if (slideData.author) footerText += `作者: ${slideData.author}`;
        if (slideData.author && slideData.date) footerText += ' | ';
        if (slideData.date) footerText += slideData.date;
        
        slide.addText(footerText, {
          x: 0.5,
          y: 6.5,
          w: 9,
          h: 0.5,
          fontSize: 14,
          color: '666666',
          align: 'center'
        });
      }
      break;

    case 'sectionHeader':
      // Section header with title and content
      slide.addText(slideData.title, {
        x: 0.5,
        y: 0.5,
        w: 9,
        h: 0.8,
        fontSize: 32,
        bold: true,
        color: '363636'
      });
      
      slide.addText(slideData.content, {
        x: 0.5,
        y: 1.5,
        w: 9,
        h: 2,
        fontSize: 18,
        color: '444444',
        align: 'center'
      });
      break;

    case 'twoColumn':
      // Two-column layout
      slide.addText(slideData.title, {
        x: 0.5,
        y: 0.2,
        w: 9,
        h: 0.6,
        fontSize: 28,
        bold: true,
        color: '363636'
      });
      
      slide.addText(slideData.leftContent, {
        x: 0.5,
        y: 1,
        w: 4,
        h: 5,
        fontSize: 16,
        color: '444444',
        bullet: true
      });
      
      slide.addText(slideData.rightContent, {
        x: 5.0,
        y: 1,
        w: 4,
        h: 5,
        fontSize: 16,
        color: '444444',
        bullet: true
      });
      
      break;

    case 'contentWithBulletPoints':
      // Content with bullet points
      slide.addText(slideData.title, {
        x: 0.5,
        y: 0.2,
        w: 9,
        h: 0.6,
        fontSize: 28,
        bold: true,
        color: '363636'
      });
      
      slide.addText(slideData.content, {
        x: 0.5,
        y: 1,
        w: 9,
        h: 1.2,
        fontSize: 18,
        color: '444444'
      });
      
      slide.addText(slideData.bulletPoints, {
        x: 0.5,
        y: 2.4,
        w: 9,
        h: 3.5,
        fontSize: 16,
        color: '444444',
        bullet: true
      });
      break;

    case 'contentWithImage':
      // Content with potential image placeholder
      slide.addText(slideData.title, {
        x: 0.5,
        y: 0.2,
        w: 9,
        h: 0.6,
        fontSize: 28,
        bold: true,
        color: '363636'
      });
      
      if (Array.isArray(slideData.content)) {
        slide.addText(slideData.content, {
          x: 0.5,
          y: 1,
          w: 9,
          h: 5,
          fontSize: 16,
          color: '444444',
          bullet: true
        });
      } else {
        slide.addText(slideData.content, {
          x: 0.5,
          y: 1,
          w: 9,
          h: 5,
          fontSize: 16,
          color: '444444'
        });
      }
      break;

    case 'thankYou':
      // Thank you slide
      slide.addText(slideData.title, {
        x: 0.5,
        y: 2,
        w: 9,
        h: 1.5,
        fontSize: 40,
        bold: true,
        color: '363636',
        align: 'center'
      });
      
      if (slideData.subtitle) {
        slide.addText(slideData.subtitle, {
          x: 0.5,
          y: 3.5,
          w: 9,
          h: 0.8,
          fontSize: 24,
          color: '666666',
          align: 'center'
        });
      }
      
      if (slideData.content) {
        slide.addText(slideData.content, {
          x: 0.5,
          y: 4.5,
          w: 9,
          h: 1,
          fontSize: 18,
          color: '666666',
          align: 'center'
        });
      }
      break;

    default:
      // Default slide layout with just title and content
      slide.addText(slideData.title, {
        x: 0.5,
        y: 0.5,
        w: 9,
        h: 0.8,
        fontSize: 32,
        bold: true,
        color: '363636'
      });
      
      if (slideData.content) {
        slide.addText(slideData.content, {
          x: 0.5,
          y: 1.5,
          w: 9,
          h: 5,
          fontSize: 16,
          color: '444444'
        });
      }
  }
});

// Save the presentation
pptx.writeFile({ 
  fileName: './presentations/ai_trends_2026_presentation.pptx' 
}).then(() => {
  console.log('2026年AI发展趋势PPT已创建完成');
});