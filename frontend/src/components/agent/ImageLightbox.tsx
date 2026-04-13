import { useEffect } from 'react'

interface ImageLightboxProps {
  imageUrl: string
  alt: string
  onClose: () => void
}

export function ImageLightbox({ imageUrl, alt, onClose }: ImageLightboxProps) {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [onClose])

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="图片预览"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
      onClick={onClose}
    >
      <div className="relative flex max-h-full max-w-full items-center justify-center" onClick={(event) => event.stopPropagation()}>
        <button
          type="button"
          aria-label="关闭图片预览"
          className="absolute right-3 top-3 z-10 rounded-full bg-black/60 px-3 py-2 text-sm text-white transition hover:bg-black/80"
          onClick={onClose}
        >
          关闭
        </button>
        <img
          src={imageUrl}
          alt={alt}
          className="max-h-[85vh] max-w-[90vw] rounded-2xl object-contain shadow-2xl"
        />
      </div>
    </div>
  )
}
