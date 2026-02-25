const fs = require('fs');
const PptxGenJS = require('pptxgenjs');

// Read the input JSON file
const inputPath = process.argv[2];
const outputPath = process.argv[3];

if (!inputPath || !outputPath) {
  console.error('Usage: node create_presentation.js <input.json> <output.pptx>');
  process.exit(1);
}

const jsonData = JSON.parse(fs.readFileSync(inputPath, 'utf8'));

// Create a new PowerPoint presentation
const pptx = new PptxGenJS();

// Process each slide based on its type
jsonData.slides.forEach(slideData => {
  const slide = pptx.addSlide();

  switch (slideData.type) {
    case 'title':
      // Title slide
      slide.addText(slideData.title, {
        x: 0.5,
        y: 1,
        w: 9,
        h: 1.5,
        fontSize: 36,
        bold: true,
        color: '363636'
      });
      
      if (slideData.subtitle) {
        slide.addText(slideData.subtitle, {
          x: 0.5,
          y: 2.5,
          w: 9,
          h: 1,
          fontSize: 20,
          color: '666666'
        });
      }
      break;

    case 'section':
      // Section slide with title and content
      slide.addText(slideData.title, {
        x: 0.5,
        y: 0.2,
        w: 9,
        h: 0.8,
        fontSize: 28,
        bold: true,
        color: '363636'
      });
      
      slide.addText(slideData.content, {
        x: 0.5,
        y: 1.2,
        w: 9,
        h: 3.5,
        fontSize: 16,
        color: '444444'
      });
      break;

    case 'bullet_points':
      // Slide with bullet points
      slide.addText(slideData.title, {
        x: 0.5,
        y: 0.2,
        w: 9,
        h: 0.8,
        fontSize: 28,
        bold: true,
        color: '363636'
      });
      
      let yPos = 1.2;
      slideData.items.forEach((item, index) => {
        slide.addText('• ' + item, {
          x: 0.7,
          y: yPos,
          w: 8.5,
          h: 0.6,
          fontSize: 16,
          color: '444444'
        });
        yPos += 0.6;
      });
      break;

    case 'two_column':
      // Two-column layout slide
      slide.addText(slideData.title, {
        x: 0.5,
        y: 0.2,
        w: 9,
        h: 0.8,
        fontSize: 28,
        bold: true,
        color: '363636'
      });
      
      // Left column title
      slide.addText(slideData.left_title, {
        x: 0.5,
        y: 1.2,
        w: 4,
        h: 0.5,
        fontSize: 18,
        bold: true,
        color: '363636'
      });
      
      // Left column content
      let leftYPos = 1.7;
      slideData.left_content.forEach(item => {
        slide.addText('• ' + item, {
          x: 0.6,
          y: leftYPos,
          w: 3.8,
          h: 0.5,
          fontSize: 14,
          color: '444444'
        });
        leftYPos += 0.5;
      });
      
      // Right column title
      slide.addText(slideData.right_title, {
        x: 5.0,
        y: 1.2,
        w: 4,
        h: 0.5,
        fontSize: 18,
        bold: true,
        color: '363636'
      });
      
      // Right column content
      let rightYPos = 1.7;
      slideData.right_content.forEach(item => {
        slide.addText('• ' + item, {
          x: 5.1,
          y: rightYPos,
          w: 3.8,
          h: 0.5,
          fontSize: 14,
          color: '444444'
        });
        rightYPos += 0.5;
      });
      break;

    case 'summary':
      // Summary slide
      slide.addText(slideData.title, {
        x: 0.5,
        y: 0.2,
        w: 9,
        h: 0.8,
        fontSize: 28,
        bold: true,
        color: '363636'
      });
      
      slide.addText(slideData.content, {
        x: 0.5,
        y: 1.2,
        w: 9,
        h: 3.5,
        fontSize: 16,
        color: '444444'
      });
      break;

    default:
      // Default slide type - just add the title
      slide.addText(slideData.title, {
        x: 0.5,
        y: 0.2,
        w: 9,
        h: 0.8,
        fontSize: 28,
        bold: true,
        color: '363636'
      });
      break;
  }
});

// Save the presentation
pptx.writeFile({ fileName: outputPath }).then(() => {
  console.log(`PPT presentation created successfully: ${outputPath}`);
});