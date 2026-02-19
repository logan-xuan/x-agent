const fs = require('fs');
const path = require('path');
const html2pptx = require('html2pptx');

// Read the HTML file
const htmlContent = fs.readFileSync('/Users/xuan.lx/Documents/x-agent/x-agent/workspace/ai_presentation.html', 'utf8');

// Define output path
const outputPath = '/Users/xuan.lx/Documents/x-agent/x-agent/workspace/ai_presentation.pptx';

// Convert HTML to PowerPoint
html2pptx(htmlContent, { width: 720, height: 405 })
  .then((buffer) => {
    fs.writeFileSync(outputPath, buffer);
    console.log(`PowerPoint presentation saved to ${outputPath}`);
  })
  .catch((error) => {
    console.error('Error creating PowerPoint:', error);
  });