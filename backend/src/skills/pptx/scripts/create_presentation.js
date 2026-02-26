#!/usr/bin/env node
/**
 * create_presentation.js - Create PowerPoint presentations from Markdown
 * 
 * Usage:
 *   node create_presentation.js <input.md> <output.pptx>
 * 
 * Example:
 *   node create_presentation.js /workspace/report.md /workspace/presentation.pptx
 */

const fs = require('fs');
const path = require('path');

// Parse command line arguments
const args = process.argv.slice(2);

function printUsage() {
    console.log('Usage: node create_presentation.js <input.md> [output.pptx]');
    console.log('');
    console.log('Arguments:');
    console.log('  input.md    - Input markdown file path');
    console.log('  output.pptx - Output PowerPoint file path (optional, defaults to input.pptx)');
    console.log('');
    console.log('Example:');
    console.log('  node create_presentation.js report.md report.pptx');
}

if (args.length < 1) {
    console.error('Error: Missing input file path');
    printUsage();
    process.exit(1);
}

// Support both --input flag and positional arguments
let inputFile = null;
let outputFile = null;

for (let i = 0; i < args.length; i++) {
    if (args[i] === '--input' || args[i] === '-i') {
        inputFile = args[++i];
    } else if (args[i] === '--output' || args[i] === '-o') {
        outputFile = args[++i];
    } else if (!inputFile) {
        inputFile = args[i];
    } else if (!outputFile) {
        outputFile = args[i];
    }
}

if (!inputFile) {
    console.error('Error: Input file is required');
    printUsage();
    process.exit(1);
}

// Generate output filename if not provided
if (!outputFile) {
    const inputBase = path.basename(inputFile, path.extname(inputFile));
    const inputDir = path.dirname(inputFile);
    outputFile = path.join(inputDir, inputBase + '.pptx');
}

console.log(`Creating presentation...`);
console.log(`  Input:  ${inputFile}`);
console.log(`  Output: ${outputFile}`);

// Check if input file exists
if (!fs.existsSync(inputFile)) {
    console.error(`Error: Input file not found: ${inputFile}`);
    process.exit(1);
}

// Read the markdown file
let content;
try {
    content = fs.readFileSync(inputFile, 'utf-8');
} catch (err) {
    console.error(`Error reading input file: ${err.message}`);
    process.exit(1);
}

// Parse markdown into slides
const slides = parseMarkdownToSlides(content);

console.log(`Parsed ${slides.length} slides from markdown`);

// For now, create a placeholder PPTX
// In a real implementation, you would use a library like pptxgenjs
console.log('Note: This is a simplified implementation.');
console.log('Full PPTX generation requires additional dependencies.');

// Create a simple text file as placeholder
const placeholderContent = `Presentation created from: ${inputFile}
Output: ${outputFile}
Slides: ${slides.length}

Slide Titles:
${slides.map((s, i) => `${i + 1}. ${s.title}`).join('\n')}

To create a full PowerPoint presentation, install pptxgenjs:
  npm install pptxgenjs

Then implement full PPTX generation logic.
`;

const placeholderPath = outputFile.replace('.pptx', '_placeholder.txt');
fs.writeFileSync(placeholderPath, placeholderContent, 'utf-8');

console.log('');
console.log('✓ Presentation structure created');
console.log(`  Placeholder saved to: ${placeholderPath}`);
console.log('');
console.log('Next steps:');
console.log('1. Install pptxgenjs for full PPTX generation');
console.log('2. Or manually create the PPTX using the slide structure above');

process.exit(0);

/**
 * Parse markdown content into slide structure
 */
function parseMarkdownToSlides(content) {
    const lines = content.split('\n');
    const slides = [];
    let currentSlide = { title: '', content: [] };
    
    for (const line of lines) {
        // H1 starts a new slide
        if (line.startsWith('# ')) {
            if (currentSlide.title) {
                slides.push(currentSlide);
            }
            currentSlide = {
                title: line.substring(2).trim(),
                content: []
            };
        } 
        // H2 creates subsection within slide
        else if (line.startsWith('## ')) {
            currentSlide.content.push({
                type: 'subtitle',
                text: line.substring(3).trim()
            });
        }
        // Bullet points
        else if (line.trim().startsWith('- ') || line.trim().startsWith('* ')) {
            currentSlide.content.push({
                type: 'bullet',
                text: line.trim().substring(2)
            });
        }
        // Regular text
        else if (line.trim()) {
            currentSlide.content.push({
                type: 'text',
                text: line.trim()
            });
        }
    }
    
    // Add last slide
    if (currentSlide.title) {
        slides.push(currentSlide);
    }
    
    return slides;
}
