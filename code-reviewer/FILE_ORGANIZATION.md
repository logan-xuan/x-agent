# Skill File Organization Standards

## Mandatory Directory Structure

All skills that create files MUST save them to designated subdirectories within the workspace.

### Standard Directories

| Skill Type | Output Files | Directory |
|------------|-------------|-----------|
| pptx | .pptx presentations | `presentations/` |
| xlsx | .xlsx spreadsheets | `spreadsheets/` |
| pdf | .pdf documents | `pdfs/` |
| docx | .docx documents | `documents/` |
| images | .png, .jpg, .svg | `images/` |
| code | .py, .js, .ts | `code/` |

## Rationale

1. **Organization**: Files are automatically categorized by type
2. **Discoverability**: Easy to find specific file types
3. **Clean Workspace**: Root directory remains uncluttered
4. **Automation**: Scripts can process files by directory

## Usage Pattern

### For Skills

When a skill creates a file, it MUST:

1. Check if user specified a custom path
   - If yes → use custom path
   - If no → use default directory

2. Use the default directory pattern:
   ```javascript
   // GOOD ✅
   const outputPath = 'presentations/my-presentation.pptx';
   
   // BAD ❌
   const outputPath = 'my-presentation.pptx';  // Wrong location
   const outputPath = 'temp/file.pptx';        // Wrong location
   ```

3. Create subdirectories as needed:
   ```javascript
   // Project-specific organization
   const outputPath = 'presentations/project-alpha/review.pptx';
   ```

### Example Implementation

```javascript
// PPTX Skill Example
async function createPresentation(userRequest) {
  // Determine output path
  let outputPath;
  if (userRequest.customPath) {
    outputPath = userRequest.customPath;
  } else {
    // Default to presentations/ directory
    const fileName = generateFileName(userRequest.topic);
    outputPath = `presentations/${fileName}.pptx`;
  }
  
  // Create and save presentation
  const pptx = new pptxgen();
  // ... build slides ...
  await pptx.writeFile(outputPath);
  
  console.log(`Presentation saved to: ${outputPath}`);
}
```

## User Communication

When creating a file, always inform the user:

```
✅ Created presentation: presentations/chinese_new_year_food.pptx

The file has been saved in the presentations/ directory.
You can find it at: /workspace/presentations/chinese_new_year_food.pptx
```

## Exception Handling

If a user explicitly requests a different location:

```
User: "Save it to /projects/client-x/deck.pptx"
Assistant: "Saving to /projects/client-x/deck.pptx"
```

But gently remind them of the standard:

```
Note: I typically save presentations to the presentations/ directory 
for better organization. Would you like me to move it there after creation?
```

## Migration Guide

For existing files in the wrong location:

```bash
# Move all PPTX files to correct directory
mv *.pptx presentations/ 2>/dev/null || true

# Move all XLSX files
mv *.xlsx spreadsheets/ 2>/dev/null || true

# Similar for other types
```
