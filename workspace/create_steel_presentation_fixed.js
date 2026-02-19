const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer');

async function createSteelPresentation() {
    try {
        // Read the HTML content
        const htmlPath = './steel_html.txt';
        const htmlContent = fs.readFileSync(htmlPath, 'utf8');
        
        // Define the output file path
        const outputPath = './presentations/steel_how_is_made.pptx';
        
        // Ensure the presentations directory exists
        const dir = path.dirname(outputPath);
        if (!fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
        }
        
        // Launch Puppeteer browser
        const browser = await puppeteer.launch();
        const page = await browser.newPage();
        
        // Set the HTML content to the page
        await page.setContent(htmlContent, { waitUntil: 'networkidle0' });
        
        // Generate PDF first (as an intermediate step)
        const pdfPath = './temp/steel_presentation.pdf';
        if (!fs.existsSync('./temp')) {
            fs.mkdirSync('./temp', { recursive: true });
        }
        
        await page.pdf({
            path: pdfPath,
            format: 'A4',
            printBackground: true
        });
        
        // Close the browser
        await browser.close();
        
        console.log(`PDF generated successfully: ${pdfPath}`);
        console.log(`Next step would be to convert PDF to PPTX if needed`);
    } catch (error) {
        console.error('Error creating presentation:', error);
    }
}

createSteelPresentation();