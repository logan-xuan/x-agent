const fs = require('fs');
const path = require('path');
const { html2pptx } = require('html2pptx');

// Read the HTML file
const htmlContent = fs.readFileSync('/Users/xuan.lx/Documents/x-agent/x-agent/workspace/product_intro.html', 'utf8');

// Define slide dimensions (16:9 aspect ratio)
const slideWidth = 720; // Points
const slideHeight = 405; // Points

// Configuration for the presentation
const config = {
  width: slideWidth,
  height: slideHeight,
  exportOptions: {
    format: 'pptx',
    transitionEffect: 'push',
  }
};

// Create the PowerPoint presentation from HTML
html2pptx(htmlContent, config)
  .then((buffer) => {
    // Write the generated PowerPoint file to disk
    const outputPath = '/Users/xuan.lx/Documents/x-agent/x-agent/workspace/product_introduction.pptx';
    fs.writeFileSync(outputPath, buffer);
    console.log(`PowerPoint presentation saved to ${outputPath}`);
  })
  .catch((error) => {
    console.error('Error generating PowerPoint:', error);
  });