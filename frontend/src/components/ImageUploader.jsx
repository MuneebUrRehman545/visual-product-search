import React, { useState, useRef, useEffect } from 'react'

const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp']
const MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024 // 25 MB

export default function ImageUploader({ file, onFileChange, disabled = false }) {
  const [previewUrl, setPreviewUrl] = useState(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef(null)

  useEffect(() => {
    if (!file) {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
      setPreviewUrl(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
      return
    }

    const objectUrl = URL.createObjectURL(file)
    setPreviewUrl((oldUrl) => {
      if (oldUrl) URL.revokeObjectURL(oldUrl)
      return objectUrl
    })

    return () => {
      URL.revokeObjectURL(objectUrl)
    }
  }, [file])

  const isValidImageFile = (candidateFile) => {
    if (!candidateFile) return false
    if (ALLOWED_TYPES.includes(candidateFile.type)) return true
    const fileName = candidateFile.name.toLowerCase()
    return ALLOWED_EXTENSIONS.some((ext) => fileName.endsWith(ext))
  }

  const processSelectedFile = (selected) => {
    if (disabled) return
    if (!selected) return

    if (selected.size === 0) {
      setErrorMessage('Selected file is empty (0 bytes). Please upload a valid image.')
      if (onFileChange) onFileChange(null)
      return
    }

    if (selected.size > MAX_FILE_SIZE_BYTES) {
      setErrorMessage('File size exceeds the 25 MB limit. Please select a smaller image.')
      if (onFileChange) onFileChange(null)
      return
    }

    if (!isValidImageFile(selected)) {
      setErrorMessage('Unsupported format. Please upload a JPG, PNG, or WebP image.')
      if (onFileChange) onFileChange(null)
      return
    }

    setErrorMessage('')
    if (onFileChange) onFileChange(selected)
  }

  const handleFileInputChange = (e) => {
    if (disabled) return
    const selected = e.target.files && e.target.files[0]
    processSelectedFile(selected)
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    e.stopPropagation()
    if (disabled) return
    setIsDragging(true)
  }

  const handleDragLeave = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
    if (disabled) return

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const droppedFile = e.dataTransfer.files[0]
      processSelectedFile(droppedFile)
    }
  }

  const handleReset = (e) => {
    e.stopPropagation()
    if (disabled) return
    setErrorMessage('')
    if (onFileChange) onFileChange(null)
  }

  return (
    <div className="upload-container">
      <input
        type="file"
        ref={fileInputRef}
        accept="image/jpeg,image/png,image/webp"
        capture="environment"
        onChange={handleFileInputChange}
        style={{ display: 'none' }}
        id="image-file-input"
        disabled={disabled}
      />

      {errorMessage && (
        <div className="error-banner compact-error" role="alert">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="8" x2="12" y2="12"></line>
            <line x1="12" y1="16" x2="12.01" y2="16"></line>
          </svg>
          <span>{errorMessage}</span>
        </div>
      )}

      {!file ? (
        <div
          className={`upload-box-compact ${isDragging ? 'drag-over' : ''} ${disabled ? 'disabled' : ''}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => {
            if (!disabled) fileInputRef.current?.click()
          }}
        >
          <div className="compact-upload-left">
            <div className="compact-upload-icon-wrapper">
              <svg
                className="compact-cloud-icon"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="17 8 12 3 7 8"></polyline>
                <line x1="12" y1="3" x2="12" y2="15"></line>
              </svg>
            </div>
            <div className="compact-text-group">
              <span className="compact-upload-prompt">
                {isDragging ? 'Drop your image now!' : 'Upload or drag & drop any product photo'}
              </span>
              <span className="compact-upload-subtext">JPG, PNG, WebP up to 25 MB</span>
            </div>
          </div>

          <button
            type="button"
            className="btn-compact-browse"
            disabled={disabled}
            onClick={(e) => {
              e.stopPropagation()
              if (!disabled) fileInputRef.current?.click()
            }}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path>
            </svg>
            Browse Image
          </button>
        </div>
      ) : (
        <div className="compact-preview-card">
          <div className="compact-preview-left">
            <div className="compact-preview-thumb">
              {previewUrl && (
                <img src={previewUrl} alt="Query Image Preview" />
              )}
            </div>
            <div className="compact-preview-info">
              <span className="compact-file-name" title={file.name}>
                {file.name}
              </span>
              <span className="compact-file-meta">
                {(file.size / 1024).toFixed(1)} KB • Image Loaded
              </span>
            </div>
          </div>

          <div className="compact-preview-actions">
            <button
              type="button"
              className="btn-compact-change"
              disabled={disabled}
              onClick={() => {
                if (!disabled) fileInputRef.current?.click()
              }}
            >
              Change
            </button>
            <button
              type="button"
              className="btn-compact-remove"
              disabled={disabled}
              onClick={handleReset}
            >
              Remove
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
