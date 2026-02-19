const fs = require('fs');
const path = require('path');
const html2pptx = require('html2pptx');

// Read the HTML file
const htmlContent = fs.readFileSync('/Users/xuan.lx/Documents/x-agent/x-agent/workspace/presentations/chinese_new_year_food.html', 'utf8');

// Convert HTML to PowerPoint
html2pptx(htmlContent, { author: 'Claude', company: 'Anthropic', subject: '春节美食介绍' })
    .then((buffer) => {
        // Write the PowerPoint file
        const outputPath = '/Users/xuan.lx/Documents/x-agent/x-agent/workspace/presentations/chinese_new_year_food.pptx';
        fs.writeFileSync(outputPath, buffer);
        console.log(`PowerPoint presentation saved to ${outputPath}`);
    })
    .catch((error) => {
        console.error('Error creating PowerPoint:', error);
    });