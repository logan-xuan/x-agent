const fs = require('fs');
const path = require('path');
const html2pptx = require('html2pptx');
const PptxGenJS = require('pptxgenjs');

// Create a new PowerPoint presentation
const pptx = new PptxGenJS();

// Set slide size to 16:9 aspect ratio
pptx.layout = 'LAYOUT_16x9';

// Define the HTML file path
const htmlFilePath = path.join(__dirname, 'steel_how_to_make.html');

// Read the HTML content
const htmlContent = fs.readFileSync(htmlFilePath, 'utf8');

// Convert HTML to PowerPoint
html2pptx(htmlContent, pptx)
  .then((presentation) => {
    // Save the presentation to the workspace directory
    const outputPath = path.join(__dirname, 'steel_how_to_make.pptx');
    presentation.writeFile(outputPath)
      .then(() => {
        console.log(`PowerPoint presentation saved successfully to ${outputPath}`);
      })
      .catch((error) => {
        console.error('Error saving presentation:', error);
      });
  })
  .catch((error) => {
    console.error('Error converting HTML to PowerPoint:', error);
  });