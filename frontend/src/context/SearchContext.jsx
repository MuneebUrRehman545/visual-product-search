import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { searchProducts, getCatalogImageUrl } from '../services/searchApi'
import { createPipelineRun } from '../services/pipelineApi'
import { usePipeline } from './PipelineContext'

const SearchContext = createContext(null)
const SESSION_STORAGE_KEY = 'vps_last_search_state'

/**
 * Convert a File or Blob object into a base64 Data URL for persistent display and sessionStorage caching.
 */
function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    if (!file) {
      resolve('')
      return
    }
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = (err) => reject(err)
    reader.readAsDataURL(file)
  })
}

export function SearchProvider({ children }) {
  const { setCurrentPipelineRunId } = usePipeline()
  const [selectedFile, setSelectedFile] = useState(null)
  const [queryPreview, setQueryPreview] = useState(null)
  const [queryFilename, setQueryFilename] = useState(null)
  const [selectedModel, setSelectedModel] = useState('clip')
  const [topK, setTopK] = useState(10)
  const [searchResults, setSearchResults] = useState(null)
  const [loading, setLoading] = useState(false)
  // Separate loading flag for "Find Similar" — does NOT blank out the ResultsPage
  const [findSimilarLoading, setFindSimilarLoading] = useState(false)
  const [error, setError] = useState(null)

  // Initialize state from sessionStorage if available (supports page refresh on /results)
  useEffect(() => {
    try {
      const saved = sessionStorage.getItem(SESSION_STORAGE_KEY)
      if (saved) {
        const parsed = JSON.parse(saved)
        if (parsed && parsed.searchResults) {
          setSearchResults(parsed.searchResults)
          setQueryPreview(parsed.queryPreview || null)
          setQueryFilename(parsed.queryFilename || parsed.searchResults.query_filename || 'Query Image')
          setSelectedModel(parsed.selectedModel || 'clip')
          setTopK(parsed.topK || 10)
        }
      }
    } catch (e) {
      console.warn('Could not restore search state from sessionStorage:', e)
    }
  }, [])

  // Execute full multimodal visual product search (supports File, Blob, or catalog filename string)
  const executeSearch = useCallback(
    async (fileOrFilename, requestedTopK = 10, requestedModel = 'clip', customPreviewUrl = null, customTitle = null) => {
      if (!fileOrFilename) {
        throw new Error('An image file or catalog item must be selected for search.')
      }

      setLoading(true)
      setError(null)

      let previewDataUrl = customPreviewUrl || ''
      let filename = customTitle || 'query.jpg'

      if (typeof fileOrFilename === 'string') {
        const safeFn = fileOrFilename.trim()
        filename = customTitle || safeFn
        if (!previewDataUrl) {
          previewDataUrl = getCatalogImageUrl(safeFn)
        }
        setQueryPreview(previewDataUrl)
        setSelectedFile(null)
      } else {
        filename = customTitle || fileOrFilename.name || 'query.jpg'
        setSelectedFile(fileOrFilename)
        if (!previewDataUrl) {
          try {
            previewDataUrl = await fileToDataUrl(fileOrFilename)
          } catch {
            if (typeof URL !== 'undefined' && URL.createObjectURL) {
              previewDataUrl = URL.createObjectURL(fileOrFilename)
            }
          }
        }
        setQueryPreview(previewDataUrl)
      }

      const identifierName = typeof fileOrFilename === 'string' ? fileOrFilename.trim() : (fileOrFilename.name || filename)
      setQueryFilename(identifierName)
      setSelectedModel(requestedModel)
      setTopK(requestedTopK)

      try {
        const pipelineRun = await createPipelineRun()
        const pipelineRunId = pipelineRun?.pipeline_run_id
        if (!pipelineRunId) {
          throw new Error('Pipeline run was created without a pipeline_run_id.')
        }
        setCurrentPipelineRunId(pipelineRunId)

        const response = await searchProducts(fileOrFilename, requestedTopK, requestedModel)
        setSearchResults(response)

        // Persist snapshot to sessionStorage so refreshing /results works seamlessly
        try {
          sessionStorage.setItem(
            SESSION_STORAGE_KEY,
            JSON.stringify({
              searchResults: response,
              queryPreview: previewDataUrl,
              queryFilename: identifierName,
              selectedModel: requestedModel,
              topK: requestedTopK,
            })
          )
        } catch (storageErr) {
          console.warn('Session storage quota exceeded or unavailable:', storageErr)
        }

        return response
      } catch (err) {
        const detailMsg = err.detail || err.message || 'Unable to search for similar products. Please try again.'
        setError(detailMsg)
        throw err
      } finally {
        setLoading(false)
      }
    },
    [setCurrentPipelineRunId]
  )

  /**
   * Execute a "Find Similar" search starting from a catalog result item.
   *
   * @param {string} catalogFilename - Catalog image filename (e.g. "10003.jpg")
   * @param {string} imageUrl - Full HTTP URL of the catalog product image
   * @param {string} displayName - Product name used for labeling the new query
   * @param {number} currentTopK - Number of results to retrieve
   * @param {string} currentModel - Embedding model ('clip' or 'resnet')
   * @returns {Promise<Object>} - SearchResponse payload
   */
  const executeFindSimilar = useCallback(
    async (catalogFilename, imageUrl, displayName, currentTopK, currentModel) => {
      setError(null)
      setFindSimilarLoading(true)

      const displayTitle = displayName || catalogFilename || 'Similar Product'
      const previewSrc = imageUrl || (catalogFilename ? `/catalog-images/${catalogFilename}` : '')

      // 1. Immediately update sidebar query preview and title for instant feedback
      if (previewSrc) {
        setQueryPreview(previewSrc)
      }
      setQueryFilename(displayTitle)

      const requestedModel = currentModel || selectedModel || 'clip'
      const requestedTopK = currentTopK || topK || 10
      setSelectedModel(requestedModel)
      setTopK(requestedTopK)

      try {
        // 2. Perform direct catalog search using catalogFilename
        const queryInput = catalogFilename || (imageUrl ? imageUrl.split('/').pop() : 'query.jpg')
        const response = await searchProducts(queryInput, requestedTopK, requestedModel)
        setSearchResults(response)

        // 3. Persist new state to sessionStorage
        try {
          sessionStorage.setItem(
            SESSION_STORAGE_KEY,
            JSON.stringify({
              searchResults: response,
              queryPreview: previewSrc,
              queryFilename: displayTitle,
              selectedModel: requestedModel,
              topK: requestedTopK,
            })
          )
        } catch (storageErr) {
          console.warn('Session storage quota exceeded or unavailable:', storageErr)
        }

        return response
      } catch (err) {
        const detailMsg =
          err.detail || err.message || 'Unable to search for similar products. Please try again.'
        setError(detailMsg)
        throw err
      } finally {
        setFindSimilarLoading(false)
      }
    },
    [selectedModel, topK]
  )

  // Handle 1-Click Top Category Presets
  const executeCategoryPreset = useCallback((resultsData, previewUrl, categoryName) => {
    setError(null)
    setSearchResults(resultsData)
    setQueryPreview(previewUrl)
    const name = categoryName || resultsData.query_filename || 'Category Preset'
    setQueryFilename(name)
    setSelectedFile(null)
    const presetTopK = resultsData.top_k || 20
    setSelectedModel('clip')
    setTopK(presetTopK)

    try {
      sessionStorage.setItem(
        SESSION_STORAGE_KEY,
        JSON.stringify({
          searchResults: resultsData,
          queryPreview: previewUrl,
          queryFilename: name,
          selectedModel: 'clip',
          topK: presetTopK,
        })
      )
    } catch (e) {
      console.warn('Could not cache category search in sessionStorage:', e)
    }
  }, [])

  // Clear search and reset state
  const clearSearch = useCallback(() => {
    setSelectedFile(null)
    setQueryPreview(null)
    setQueryFilename(null)
    setSearchResults(null)
    setError(null)
    try {
      sessionStorage.removeItem(SESSION_STORAGE_KEY)
    } catch (e) {}
  }, [])

  const value = {
    selectedFile,
    setSelectedFile,
    queryPreview,
    setQueryPreview,
    queryFilename,
    selectedModel,
    setSelectedModel,
    topK,
    setTopK,
    searchResults,
    setSearchResults,
    loading,
    findSimilarLoading,
    error,
    setError,
    executeSearch,
    executeFindSimilar,
    executeCategoryPreset,
    clearSearch,
  }

  return <SearchContext.Provider value={value}>{children}</SearchContext.Provider>
}

export function useSearch() {
  const context = useContext(SearchContext)
  if (!context) {
    throw new Error('useSearch must be used within a SearchProvider')
  }
  return context
}
