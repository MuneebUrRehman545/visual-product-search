import React, { useState } from 'react'
import ImageUploader from './components/ImageUploader'
import SearchControls from './components/SearchControls'
import SearchResults from './components/SearchResults'
import { searchProducts } from './services/searchApi'

function App() {
  const [selectedFile, setSelectedFile] = useState(null)
  const [topK, setTopK] = useState(10)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [searchResults, setSearchResults] = useState(null)

  const handleFileChange = (newFile) => {
    setSelectedFile(newFile)
    setSearchResults(null)
    setError(null)
  }

  const handleSearch = async () => {
    if (!selectedFile || loading) return

    setError(null)
    setLoading(true)

    try {
      const response = await searchProducts(selectedFile, topK)
      setSearchResults(response)
    } catch (err) {
      setError(err.detail || err.message || 'Visual search failed.')
      setSearchResults(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container">
      <header className="header">
        <h1>Visual Product Search</h1>
        <p className="subtitle">
          Upload an image to find visually similar catalog products.
        </p>
      </header>

      <main className="main-content">
        <ImageUploader file={selectedFile} onFileChange={handleFileChange} />

        {selectedFile && (
          <SearchControls
            topK={topK}
            onTopKChange={setTopK}
            onSearch={handleSearch}
            disabled={!selectedFile}
            loading={loading}
          />
        )}

        {error && (
          <div className="api-error-banner" role="alert">
            <p className="error-title">Search Error</p>
            <p className="error-message">{error}</p>
          </div>
        )}

        {searchResults && (
          <SearchResults
            queryFilename={searchResults.query_filename}
            totalResults={searchResults.total_results}
            results={searchResults.results}
          />
        )}
      </main>
    </div>
  )
}

export default App
