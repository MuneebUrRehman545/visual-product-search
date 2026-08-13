/**
 * Visual Product Search API Client Service
 */

/**
 * Dynamically resolve the backend API Base URL based on current environment or browser hostname.
 * Supports Localhost and LAN IP access (e.g. http://192.168.100.63:8000).
 */
export const getApiBaseUrl = () => {
  const envUrl = import.meta.env.VITE_API_BASE_URL
  if (envUrl && envUrl.trim() !== '' && !envUrl.includes('127.0.0.1') && !envUrl.includes('localhost')) {
    return envUrl.replace(/\/+$/, '')
  }
  if (typeof window !== 'undefined' && window.location && window.location.hostname) {
    const hostname = window.location.hostname
    return `http://${hostname}:8000`
  }
  return 'http://127.0.0.1:8000'
}

export const API_BASE_URL = getApiBaseUrl()

/**
 * Convert a relative catalog image path into a full HTTP browser URL.
 *
 * @param {string} imagePathOrUrl - e.g. "/catalog-images/15025.jpg"
 * @returns {string} - e.g. "http://192.168.100.63:8000/catalog-images/15025.jpg"
 */
export function getCatalogImageUrl(imagePathOrUrl) {
  if (!imagePathOrUrl) return ''
  if (imagePathOrUrl.startsWith('http://') || imagePathOrUrl.startsWith('https://')) {
    return imagePathOrUrl
  }
  const baseUrl = getApiBaseUrl()
  const cleanPath = imagePathOrUrl.startsWith('/') ? imagePathOrUrl : `/${imagePathOrUrl}`
  return `${baseUrl}${cleanPath}`
}

/**
 * Execute visual product search query against backend API.
 *
 * @param {File} imageFile - Uploaded image File object.
 * @param {number} topK - Number of top results to return (1-50, default 10).
 * @returns {Promise<Object>} - SearchResponse payload.
 */
export async function searchProducts(imageFile, topK = 10) {
  if (!imageFile) {
    throw new Error('An image file must be provided for visual search.')
  }

  const topKNum = Number(topK)
  if (!Number.isInteger(topKNum) || topKNum < 1 || topKNum > 50) {
    throw new Error('top_k must be an integer between 1 and 50.')
  }

  const formData = new FormData()
  formData.append('file', imageFile)
  formData.append('top_k', topKNum.toString())

  const baseUrl = getApiBaseUrl()
  const searchUrl = `${baseUrl}/api/v1/search`

  try {
    const response = await fetch(searchUrl, {
      method: 'POST',
      body: formData,
    })

    let data
    try {
      data = await response.json()
    } catch {
      data = null
    }

    if (!response.ok) {
      const detailMsg =
        data && data.detail
          ? typeof data.detail === 'string'
            ? data.detail
            : JSON.stringify(data.detail)
          : `Search API request failed (HTTP ${response.status})`

      const error = new Error(detailMsg)
      error.status = response.status
      error.detail = detailMsg
      throw error
    }

    if (!data || !Array.isArray(data.results)) {
      throw new Error('Invalid or malformed response format received from search API.')
    }

    return data
  } catch (err) {
    if (err.status) {
      throw err
    }
    const networkError = new Error(`Unable to connect to search service (${err.message})`)
    networkError.status = 0
    throw networkError
  }
}
