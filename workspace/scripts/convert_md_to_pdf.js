const fs = require('fs');
const path = require('path');

// Read the markdown content
const markdownContent = fs.readFileSync('/Users/xuan.lx/Documents/x-agent/x-agent/workspace/documents/2026_ai_trends_research.md', 'utf8');

// Simple markdown to PDF conversion using basic formatting
const PDFDocument = require('pdfkit');

// Create a new PDF document
const doc = new PDFDocument();
const outputPath = '/Users/xuan.lx/Documents/x-agent/x-agent/workspace/pdfs/2026_ai_trends_research.pdf';
const writeStream = fs.createWriteStream(outputPath);
doc.pipe(writeStream);

// Add title
doc.fontSize(20).text('2026年AI发展趋势深度研究报告', { align: 'center' });
doc.moveDown();

// Add some space
doc.moveDown();

// Process markdown content and add to PDF
let lines = markdownContent.split('\n');
for (let line of lines) {
  if (line.startsWith('# ')) {
    // Main heading
    doc.fontSize(16).font('Helvetica-Bold').text(line.replace('# ', ''), { underline: true });
    doc.moveDown(0.5);
  } else if (line.startsWith('## ')) {
    // Sub heading
    doc.fontSize(14).font('Helvetica-Bold').text(line.replace('## ', ''));
    doc.moveDown(0.3);
  } else if (line.startsWith('### ')) {
    // Sub-sub heading
    doc.fontSize(12).font('Helvetica-Bold').text(line.replace('### ', ''));
    doc.moveDown(0.2);
  } else if (line.trim() === '') {
    // Empty line
    doc.moveDown(0.3);
  } else {
    // Regular paragraph
    doc.fontSize(10).font('Helvetica').text(line.trim());
  }
}

// End the PDF
doc.end();

// Wait for the stream to finish
writeStream.on('finish', () => {
  console.log('PDF created successfully:', outputPath);
});

writeStream.on('error', (err) => {
  console.error('Error creating PDF:', err);
});