import React, { useState, useRef, useEffect } from 'react'

const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp']

export default function ImageUploader({ file, onFileChange }) {
  const [previewUrl, setPreviewUrl] = useState(null)
  const [errorMessage, setErrorMessage] = useState('')
  const fileInputRef = useRef(null)

  // Sync previewUrl with prop 'file' and clean up object URLs
  useEffect(() => {
    if (!file) {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl)
      }
      setPreviewUrl(null)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
      return
    }

    const objectUrl = URL.createObjectURL(file)
    setPreviewUrl((oldUrl) => {
      if (oldUrl) {
        URL.revokeObjectURL(oldUrl)
      }
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

  const handleFileChange = (e) => {
    const selected = e.target.files && e.target.files[0]
    if (!selected) return

    if (!isValidImageFile(selected)) {
      setErrorMessage('Unsupported file type. Please select a valid JPG, PNG, or WebP image.')
      if (onFileChange) {
        onFileChange(null)
      }
      return
    }

    setErrorMessage('')
    if (onFileChange) {
      onFileChange(selected)
    }
  }

  const handleReset = () => {
    setErrorMessage('')
    if (onFileChange) {
      onFileChange(null)
    }
  }

  return (
    <div className="upload-container">
      <input
        type="file"
        ref={fileInputRef}
        accept="image/jpeg,image/png,image/webp"
        capture="environment"
        onChange={handleFileChange}
        style={{ display: 'none' }}
        id="image-file-input"
      />

      {errorMessage && (
        <div className="error-banner" role="alert">
          {errorMessage}
        </div>
      )}

      {!file ? (
        <div className="upload-box">
          <p className="upload-prompt">Select an image to search the catalog</p>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => fileInputRef.current?.click()}
          >
            Choose Image
          </button>
          <p className="supported-formats">Supported formats: JPG, PNG, WebP</p>
        </div>
      ) : (
        <div className="preview-container">
          <div className="preview-card">
            {previewUrl && (
              <img src={previewUrl} alt="Query Image Preview" className="preview-image" />
            )}
            <div className="preview-info">
              <span className="file-name" title={file.name}>
                {file.name}
              </span>
              <span className="file-size">
                {(file.size / 1024).toFixed(1)} KB
              </span>
            </div>
          </div>
          <div className="preview-actions">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => fileInputRef.current?.click()}
            >
              Change Image
            </button>
            <button type="button" className="btn btn-danger" onClick={handleReset}>
              Remove Image
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
