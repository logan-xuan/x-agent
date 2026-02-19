const fs = require('fs');
const path = require('path');
const html2pptx = require('html2pptx');

async function createPresentation() {
  try {
    // Read the HTML file
    const htmlContent = fs.readFileSync('/Users/xuan.lx/Documents/x-agent/x-agent/workspace/steel_how_it_is_made.html', 'utf8');
    
    // Define the presentation configuration
    const options = {
      author: 'Assistant',
      creator: 'Assistant',
      description: '钢铁是怎么炼成的主题分析',
      orientation: 'landscape', // Use landscape orientation for 16:9 aspect ratio
      title: '钢铁是怎么炼成的 - 主题分析',
      subject: '文学分析',
      keywords: ['钢铁是怎样炼成的', '保尔·柯察金', '革命精神', '文学'],
      layout: 'screen16x9', // Use 16:9 layout
    };

    // Convert HTML to PowerPoint buffer
    const buffer = await html2pptx(htmlContent, options);

    // Write the PowerPoint file
    const outputPath = '/Users/xuan.lx/Documents/x-agent/x-agent/workspace/steel_how_it_is_made.pptx';
    fs.writeFileSync(outputPath, buffer);

    console.log(`PowerPoint presentation saved successfully to ${outputPath}`);
  } catch (error) {
    console.error('Error creating PowerPoint presentation:', error);
  }
}

createPresentation();