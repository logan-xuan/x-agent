# PPTX Generation Quick Reference

## Common Mistakes to Avoid

### ❌ WRONG - defineTheme doesn't exist
```javascript
const pptxgenjs = require('pptxgenjs');
const pres = new pptxgenjs();
pres.defineTheme({...});  // ERROR: This method doesn't exist!
```

**This will cause:** `TypeError: pres.defineTheme is not a function`

---

## ✅ CORRECT - Use the Proper API

### Basic Example
```javascript
const pptxgenjs = require('pptxgenjs');

async function createPresentation() {
  const pptx = new pptxgenjs();
  
  // Set layout (16:9 widescreen)
  pptx.layout = 'LAYOUT_16x9';
  
  // Add a slide
  const slide = pptx.addSlide();
  
  // Add title
  slide.addText('Steel: How It's Made', {
    x: 0.5, y: 0.5, w: '90%', h: 0.75,
    fontSize: 32,
    bold: true,
    color: '363636',
    align: 'center'
  });
  
  // Add bullet points
  slide.addText([
    { text: 'Iron ore mining and processing', options: { fontSize: 18 } },
    { text: 'Steelmaking methods (BOF vs EAF)', options: { fontSize: 18 } },
    { text: 'Continuous casting and rolling', options: { fontSize: 18 } },
    { text: 'Quality control and finishing', options: { fontSize: 18 } }
  ], {
    x: 0.5, y: 1.5, w: '90%', h: 4,
    bullet: true,
    lineSpacing: 36,
    color: '666666'
  });
  
  // Save file
  await pptx.writeFile({ fileName: 'steel_presentation.pptx' });
}

createPresentation().catch(console.error);
```

---

## Key API Methods

### Presentation Setup
```javascript
const pptx = new pptxgenjs();
pptx.layout = 'LAYOUT_16x9';  // or LAYOUT_4x3
```

### Adding Slides
```javascript
const slide = pptx.addSlide();  // uses default layout
// or
const slide = pptx.addSlide('LAYOUT_WIDE');
```

### Adding Content

#### Text
```javascript
slide.addText('Simple text', { x: 1, y: 1, w: 5, h: 0.5 });

// Multiple runs with different formatting
slide.addText([
  { text: 'Bold ', options: { bold: true } },
  { text: 'and ', options: {} },
  { text: 'italic', options: { italic: true } }
], { x: 1, y: 2, w: 5, h: 0.5 });
```

#### Images
```javascript
slide.addImage({
  path: 'path/to/image.png',
  x: 1, y: 1, w: 5, h: 3
});
```

#### Shapes
```javascript
slide.addShape(pptx.ShapeType.rect, {
  x: 1, y: 1, w: 5, h: 3,
  fill: '366099',
  radius: 0.1  // rounded corners (0-1)
});
```

### Saving
```javascript
await pptx.writeFile({ fileName: 'presentation.pptx' });
```

---

## Complete Working Example

```javascript
const pptxgenjs = require('pptxgenjs');

async function createSteelPresentation() {
  const pptx = new pptxgenjs();
  pptx.layout = 'LAYOUT_16x9';
  
  // Slide 1: Title
  const slide1 = pptx.addSlide();
  slide1.addText('Steel: The Backbone of Modern Industry', {
    x: 0.5, y: 1, w: '90%', h: 1,
    fontSize: 36,
    bold: true,
    color: 'E76F51',
    align: 'center'
  });
  slide1.addText('From Iron Ore to Finished Products', {
    x: 0.5, y: 2.2, w: '90%', h: 0.5,
    fontSize: 20,
    color: '666666',
    align: 'center'
  });
  
  // Slide 2: Process Overview
  const slide2 = pptx.addSlide();
  slide2.addText('Steel Manufacturing Process', {
    x: 0.5, y: 0.3, w: '90%', h: 0.5,
    fontSize: 28,
    bold: true,
    color: '363636'
  });
  
  const steps = [
    'Mining: Extract iron ore from the earth',
    'Processing: Crush and refine the ore',
    'Smelting: Heat in blast furnace with coke',
    'Refining: Remove impurities and add alloys',
    'Casting: Form into shapes (billets, blooms, slabs)',
    'Rolling: Shape into final products'
  ];
  
  slide2.addText(steps.map(s => ({ text: s, options: { fontSize: 16 } })), {
    x: 0.5, y: 1, w: '90%', h: 4,
    bullet: true,
    lineSpacing: 32,
    color: '555555'
  });
  
  // Save
  await pptx.writeFile({ fileName: 'steel_process.pptx' });
  console.log('✅ Presentation created successfully!');
}

createSteelPresentation().catch(console.error);
```

---

## Resources

- **Official Docs**: https://gitbrent.github.io/PptxGenJS/docs/usage.html
- **GitHub**: https://github.com/gitbrent/PptxGenJS
- **Examples**: https://gitbrent.github.io/PptxGenJS/demos/
