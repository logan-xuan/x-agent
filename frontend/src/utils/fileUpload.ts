/**
 * File upload utility for x-agent2 AI assistant system
 * Handles file uploads with progress tracking and validation
 */

interface UploadOptions {
  maxSize?: number; // in bytes (default: 10MB)
  allowedTypes?: string[]; // MIME types
  onProgress?: (progress: number) => void; // Progress callback
  onValidate?: (file: File) => boolean; // Custom validation function
}

interface UploadResult {
  success: boolean;
  filePath?: string;
  filename?: string;
  error?: string;
}

class FileUploadUtil {
  static readonly DEFAULT_MAX_SIZE = 10 * 1024 * 1024; // 10MB
  static readonly DEFAULT_ALLOWED_TYPES = [
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp',
    'text/plain',
    'text/csv',
    'application/pdf',
    'application/json',
    'application/zip',
    'application/x-zip-compressed',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  ];

  /**
   * Upload a file to the backend
   */
  static async uploadFile(
    file: File,
    sessionId: string,
    options: UploadOptions = {}
  ): Promise<UploadResult> {
    // Apply defaults to options
    const maxSize = options.maxSize || FileUploadUtil.DEFAULT_MAX_SIZE;
    const allowedTypes = options.allowedTypes || FileUploadUtil.DEFAULT_ALLOWED_TYPES;

    // Validate file
    const validationResult = this.validateFile(file, maxSize, allowedTypes, options.onValidate);
    if (!validationResult.valid) {
      return {
        success: false,
        error: validationResult.errorMessage
      };
    }

    // Create form data
    const formData = new FormData();
    formData.append('file', file, file.name);
    formData.append('session_id', sessionId);

    try {
      // Create XMLHttpRequest for progress tracking
      return new Promise<UploadResult>((resolve) => {
        const xhr = new XMLHttpRequest();

        // Track upload progress
        xhr.upload.addEventListener('progress', (event) => {
          if (event.lengthComputable && options.onProgress) {
            const progress = Math.round((event.loaded / event.total) * 100);
            options.onProgress(progress);
          }
        });

        // Handle completion
        xhr.addEventListener('load', () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              const response = JSON.parse(xhr.responseText);
              resolve({
                success: true,
                filePath: response.file_path,
                filename: response.filename
              });
            } catch (parseError) {
              resolve({
                success: false,
                error: 'Invalid response from server'
              });
            }
          } else {
            resolve({
              success: false,
              error: `Upload failed with status: ${xhr.status}`
            });
          }
        });

        // Handle errors
        xhr.addEventListener('error', () => {
          resolve({
            success: false,
            error: 'Network error occurred during upload'
          });
        });

        // Handle abort
        xhr.addEventListener('abort', () => {
          resolve({
            success: false,
            error: 'Upload was aborted'
          });
        });

        // Open request and send
        xhr.open('POST', `/api/v1/files/upload`);
        xhr.send(formData);
      });
    } catch (error) {
      return {
        success: false,
        error: `Upload failed: ${(error as Error).message}`
      };
    }
  }

  /**
   * Validate file based on size, type, and custom validation
   */
  private static validateFile(
    file: File,
    maxSize: number,
    allowedTypes: string[],
    customValidator?: (file: File) => boolean
  ): { valid: boolean; errorMessage?: string } {
    // Check file size
    if (file.size > maxSize) {
      const maxSizeMB = (maxSize / (1024 * 1024)).toFixed(2);
      return {
        valid: false,
        errorMessage: `File size (${(file.size / (1024 * 1024)).toFixed(2)} MB) exceeds maximum allowed size (${maxSizeMB} MB)`
      };
    }

    // Check file type
    if (allowedTypes.length > 0 && !allowedTypes.includes(file.type)) {
      return {
        valid: false,
        errorMessage: `File type '${file.type}' is not allowed. Allowed types: ${allowedTypes.join(', ')}`
      };
    }

    // Run custom validation if provided
    if (customValidator && !customValidator(file)) {
      return {
        valid: false,
        errorMessage: 'File failed custom validation'
      };
    }

    return { valid: true };
  }

  /**
   * Format file size for display
   */
  static formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 Bytes';

    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  /**
   * Extract file extension from name
   */
  static getFileExtension(fileName: string): string {
    return fileName.slice(((fileName.lastIndexOf(".") - 1) >>> 0) + 2);
  }

  /**
   * Get human-readable file type description
   */
  static getFileTypeDescription(fileType: string): string {
    const typeMap: Record<string, string> = {
      'image/jpeg': 'JPEG Image',
      'image/png': 'PNG Image',
      'image/gif': 'GIF Image',
      'image/webp': 'WebP Image',
      'text/plain': 'Plain Text',
      'text/csv': 'CSV File',
      'application/pdf': 'PDF Document',
      'application/json': 'JSON File',
      'application/zip': 'ZIP Archive',
      'application/x-zip-compressed': 'ZIP Archive',
      'application/msword': 'Word Document',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'Word Document',
      'application/vnd.ms-excel': 'Excel Spreadsheet',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'Excel Spreadsheet'
    };

    return typeMap[fileType] || fileType || 'Unknown File Type';
  }

  /**
   * Pre-process file before upload (resize images, etc.)
   */
  static async preprocessFile(file: File, maxSize?: number): Promise<File> {
    // If it's an image and we need to resize
    if (file.type.startsWith('image/') && maxSize && file.size > maxSize) {
      return this.compressImage(file, maxSize);
    }

    return file;
  }

  /**
   * Compress image file
   */
  private static async compressImage(file: File, maxSize: number): Promise<File> {
    return new Promise<File>((resolve) => {
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      const img = new Image();

      img.onload = () => {
        // Start with original dimensions
        let width = img.width;
        let height = img.height;

        // Reduce dimensions until size is acceptable
        const qualitySteps = 0.1; // Reduce by 10% quality each step
        let quality = 0.9; // Start with 90% quality

        // Try to reduce dimensions first
        const maxDimension = 1920; // Max dimension for images
        if (width > maxDimension || height > maxDimension) {
          const ratio = Math.min(maxDimension / width, maxDimension / height);
          width *= ratio;
          height *= ratio;
        }

        canvas.width = width;
        canvas.height = height;

        ctx?.drawImage(img, 0, 0, width, height);

        // Keep reducing quality until file size is acceptable
        let dataUrl;
        while (quality > 0.1) {
          dataUrl = canvas.toDataURL(file.type, quality);

          // Convert to blob to check size
          const byteString = atob(dataUrl.split(',')[1]);
          const mimeString = dataUrl.split(',')[0].split(':')[1].split(';')[0];
          const ab = new ArrayBuffer(byteString.length);
          const ia = new Uint8Array(ab);
          for (let i = 0; i < byteString.length; i++) {
            ia[i] = byteString.charCodeAt(i);
          }
          const blob = new Blob([ab], { type: mimeString });

          if (blob.size <= maxSize) {
            resolve(new File([blob], file.name, { type: file.type }));
            return;
          }

          quality -= qualitySteps;
        }

        // If we couldn't reduce enough, use the smallest we could create
        if (dataUrl) {
          const byteString = atob(dataUrl.split(',')[1]);
          const mimeString = dataUrl.split(',')[0].split(':')[1].split(';')[0];
          const ab = new ArrayBuffer(byteString.length);
          const ia = new Uint8Array(ab);
          for (let i = 0; i < byteString.length; i++) {
            ia[i] = byteString.charCodeAt(i);
          }
          const blob = new Blob([ab], { type: mimeString });
          resolve(new File([blob], file.name, { type: file.type }));
        } else {
          // If compression failed, return original file
          resolve(file);
        }
      };

      img.src = URL.createObjectURL(file);
    });
  }
}

export default FileUploadUtil;