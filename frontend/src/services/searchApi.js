/**
 * Visual Product Search API Client Service
 */

/**
 * Dynamically resolve the backend API Base URL based on current environment or browser hostname.
 * Respects VITE_API_BASE_URL when set, otherwise falls back to window.location.hostname.
 */
export const getApiBaseUrl = () => {
  let envUrl = null
  try {
    if (typeof import.meta !== 'undefined' && import.meta && import.meta.env) {
      envUrl = import.meta.env.VITE_API_BASE_URL
    }
  } catch (e) {}
  if (!envUrl && typeof process !== 'undefined' && process.env) {
    envUrl = process.env.VITE_API_BASE_URL
  }
  if (envUrl && typeof envUrl === 'string' && envUrl.trim() !== '') {
    return envUrl.trim().replace(/\/+$/, '')
  }
  if (typeof window !== 'undefined' && window.location && window.location.hostname) {
    const hostname = window.location.hostname
    return `http://${hostname}:8000`
  }
  return 'http://127.0.0.1:8000'
}

export const API_BASE_URL = getApiBaseUrl()

/**
 * Convert a relative catalog image path or filename into a full HTTP browser URL.
 * Supports: "/catalog-images/15025.jpg", "15025.jpg", "/15025.jpg", or full URLs.
 *
 * @param {string} imagePathOrUrl
 * @returns {string} - Full HTTP/HTTPS browser URL
 */
export function getCatalogImageUrl(imagePathOrUrl) {
  if (!imagePathOrUrl) return ''
  const str = String(imagePathOrUrl).trim()
  if (str.startsWith('http://') || str.startsWith('https://') || str.startsWith('data:')) {
    return str
  }
  const baseUrl = getApiBaseUrl()
  let path = str
  if (!path.startsWith('/')) {
    path = `/${path}`
  }
  if (!path.startsWith('/catalog-images/')) {
    path = `/catalog-images${path}`
  }
  return `${baseUrl}${path}`
}

/**
 * Execute visual product search query against backend API.
 * Supports passing either an uploaded File object OR a catalog filename string (e.g. "10003.jpg").
 *
 * @param {File|Blob|string} imageFileOrFilename - Uploaded image File or catalog image filename string.
 * @param {number} topK - Number of top results to return (1-50, default 10).
 * @param {string} model - Embedding model choice ('clip' or 'resnet').
 * @returns {Promise<Object>} - SearchResponse payload.
 */
export async function searchProducts(imageFileOrFilename, topK = 10, model = 'clip') {
  if (!imageFileOrFilename) {
    throw new Error('An image file or catalog filename must be provided for visual search.')
  }

  const topKNum = Number(topK)
  if (!Number.isInteger(topKNum) || topKNum < 1 || topKNum > 50) {
    throw new Error('top_k must be an integer between 1 and 50.')
  }

  const formData = new FormData()
  if (typeof imageFileOrFilename === 'string') {
    // Direct server-side catalog item search (fast, 0-network download)
    formData.append('catalog_filename', imageFileOrFilename.trim())
  } else {
    // Uploaded user image search
    formData.append('file', imageFileOrFilename)
  }
  formData.append('top_k', topKNum.toString())
  formData.append('model', model || 'clip')

  const baseUrl = getApiBaseUrl()
  const searchUrl = `${baseUrl}/search`

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
      let detailMsg = `Search request failed (HTTP ${response.status})`
      if (response.status >= 500) {
        detailMsg = 'The visual search server encountered an error processing your request. Please try again.'
      } else if (data && data.detail) {
        if (typeof data.detail === 'string') {
          detailMsg = data.detail
        } else if (Array.isArray(data.detail)) {
          detailMsg = data.detail.map((d) => d.msg || 'Invalid input parameter').join('; ')
        } else {
          detailMsg = 'The search request contained invalid parameters.'
        }
      }

      const error = new Error(detailMsg)
      error.status = response.status
      error.detail = detailMsg
      throw error
    }

    if (!data || !Array.isArray(data.results)) {
      throw new Error('Invalid or malformed response format received from visual search API.')
    }

    return data
  } catch (err) {
    if (err.status) {
      throw err
    }
    const networkError = new Error('Unable to connect to visual search service. Please ensure the backend gateway is running.')
    networkError.status = 0
    throw networkError
  }
}

/**
 * Fetch top categories with item counts and sample images.
 */
export async function fetchTopCategories(limit = 8) {
  const baseUrl = getApiBaseUrl()
  const res = await fetch(`${baseUrl}/api/catalog/categories?limit=${limit}`)
  if (!res.ok) {
    throw new Error('Failed to fetch catalog categories.')
  }
  return await res.json()
}

/**
 * Fetch catalog products for a specific category or article type.
 */
export async function fetchCategoryProducts(categoryName, limit = 20) {
  const baseUrl = getApiBaseUrl()
  const cleanName = encodeURIComponent(categoryName)
  const res = await fetch(`${baseUrl}/api/catalog/category/${cleanName}?limit=${limit}`)
  if (!res.ok) {
    throw new Error(`Failed to fetch items for category '${categoryName}'.`)
  }
  return await res.json()
}
