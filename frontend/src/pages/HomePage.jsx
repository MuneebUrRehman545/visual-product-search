import React from 'react'
import SampleQueries from '../components/SampleQueries'
import ImageUploader from '../components/ImageUploader'
import SearchControls from '../components/SearchControls'
import { useSearch } from '../context/SearchContext'
import { useNavigate } from '../context/RouterContext'

export default function HomePage() {
  const {
    selectedFile,
    setSelectedFile,
    topK,
    setTopK,
    selectedModel,
    setSelectedModel,
    loading,
    error,
    setError,
    executeSearch,
  } = useSearch()

  const navigate = useNavigate()

  const handleFileChange = (newFile) => {
    setSelectedFile(newFile)
    setError(null)
  }

  const handleSearch = async () => {
    if (!selectedFile || loading) return

    try {
      await executeSearch(selectedFile, topK, selectedModel)
      navigate('/results')
    } catch (err) {
      // Error is set in SearchContext, so error banner will show
      console.error('Search execution failed:', err)
    }
  }

  const handleSelectSample = async (sampleFilenameOrFile, previewUrl, categoryName) => {
    try {
      await executeSearch(sampleFilenameOrFile, topK, selectedModel, previewUrl, categoryName)
      navigate('/results')
    } catch (err) {
      console.error('Quick select search failed:', err)
    }
  }

  return (
    <div className="main-wrapper">
      <main className="search-workspace">
        {/* Quick Select Categories — Real Visual Search */}
        <SampleQueries
          onSelectSample={handleSelectSample}
          loading={loading}
        />

        {/* Upload Dropzone */}
        <ImageUploader
          file={selectedFile}
          onFileChange={handleFileChange}
          disabled={loading}
        />

        {/* Search Controls (Model Selection, Retrieval Depth, Search Button) */}
        <SearchControls
          topK={topK}
          onTopKChange={setTopK}
          selectedModel={selectedModel}
          onModelChange={setSelectedModel}
          onSearch={handleSearch}
          disabled={!selectedFile}
          loading={loading}
        />

        {/* Error Banner */}
        {error && (
          <div className="api-error-banner" role="alert">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
            <div className="error-text-group">
              <p className="error-title">Unable to search for similar products</p>
              <p className="error-message">{error}</p>
            </div>
            <button
              type="button"
              className="error-dismiss-btn"
              onClick={() => setError(null)}
              aria-label="Dismiss error"
            >
              &times;
            </button>
          </div>
        )}
      </main>
    </div>
  )
}
