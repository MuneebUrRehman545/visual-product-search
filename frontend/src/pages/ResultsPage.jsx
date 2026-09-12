import React, { useState, useMemo, useRef } from 'react'
import ResultCard from '../components/ResultCard'
import ProductDetailModal from '../components/ProductDetailModal'
import { useSearch } from '../context/SearchContext'
import { useNavigate } from '../context/RouterContext'
import { getCatalogImageUrl } from '../services/searchApi'

/**
 * Derive "You May Also Like" recommendations from existing results.
 *
 * Strategy (no extra API calls):
 *  1. Reference item = rawResults[0] (top match)
 *  2. Find items that share the same category AND base_colour as the reference
 *     but are NOT already in the top-3 visible results
 *  3. Fallback: if < 2 found, also include items sharing article_type
 *  4. Cap at 4 recommendations; minimum 2 required to show the section
 */
function deriveRecommendations(rawResults) {
  if (!rawResults || rawResults.length < 4) return []

  const ref = rawResults[0]
  const pool = rawResults.slice(3) // exclude top-3 from recommendations

  // Primary match: same category + same base_colour
  const primary = pool.filter(
    (r) =>
      r.category &&
      ref.category &&
      r.category.toLowerCase() === ref.category.toLowerCase() &&
      r.base_colour &&
      ref.base_colour &&
      r.base_colour.toLowerCase() === ref.base_colour.toLowerCase()
  )

  // Fallback: same article_type
  const fallback = pool.filter(
    (r) =>
      !primary.includes(r) &&
      r.article_type &&
      ref.article_type &&
      r.article_type.toLowerCase() === ref.article_type.toLowerCase()
  )

  const combined = [...primary, ...fallback].slice(0, 4)
  return combined.length >= 2 ? combined : []
}

export default function ResultsPage() {
  const {
    searchResults,
    queryPreview,
    queryFilename,
    selectedModel,
    topK,
    loading,
    findSimilarLoading,
    error,
    clearSearch,
    executeFindSimilar,
  } = useSearch()

  const navigate = useNavigate()
  const [selectedProductDetail, setSelectedProductDetail] = useState(null)
  const [activeCategoryFilter, setActiveCategoryFilter] = useState('ALL')
  const [minSimilarityFilter, setMinSimilarityFilter] = useState(0)

  // Keep track of which card triggered "Find Similar" so we don't blank the page
  const findSimilarTargetRef = useRef(null)

  // Handle case: Search is currently in progress (only for fresh searches from Home)
  if (loading && !findSimilarLoading) {
    return (
      <div className="main-wrapper">
        <div className="results-loading-container">
          <div className="spinner-large"></div>
          <h2 className="results-loading-title">Searching for visually similar products...</h2>
          <p className="results-loading-sub">
            Extracting deep visual features using{' '}
            <strong>{selectedModel === 'resnet' ? 'ResNet-50' : 'OpenCLIP ViT-B/32'}</strong> and querying FAISS vector index.
          </p>
        </div>
      </div>
    )
  }

  // Handle case: API error occurred and no cached results
  if (error && !searchResults) {
    return (
      <div className="main-wrapper">
        <div className="results-fallback-card">
          <div className="fallback-icon-error">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
          </div>
          <h2 className="fallback-title">Unable to search for similar products.</h2>
          <p className="fallback-desc">{error || 'Please try again with another query image.'}</p>
          <div className="fallback-actions">
            <button
              className="btn btn-primary"
              onClick={() => {
                clearSearch()
                navigate('/')
              }}
            >
              Back to Search
            </button>
          </div>
        </div>
      </div>
    )
  }

  // Handle case: Direct access to /results without any search performed
  if (!searchResults) {
    return (
      <div className="main-wrapper">
        <div className="results-fallback-card">
          <div className="fallback-icon-empty">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
              <line x1="11" y1="8" x2="11" y2="14"></line>
              <line x1="8" y1="11" x2="14" y2="11"></line>
            </svg>
          </div>
          <h2 className="fallback-title">No search has been performed yet.</h2>
          <p className="fallback-desc">
            Upload or drop a product photo to find visually and semantically similar items across 44,000+ catalog products.
          </p>
          <div className="fallback-actions">
            <button className="btn btn-primary" onClick={() => navigate('/')}>
              Search for a Product
            </button>
          </div>
        </div>
      </div>
    )
  }

  const rawResults = Array.isArray(searchResults.results) ? searchResults.results : []
  const totalResults = searchResults.total_results || rawResults.length
  const displayFilename = queryFilename || searchResults.query_filename || 'Query Image'
  const modelUsedName =
    searchResults.model_used === 'ResNet_50'
      ? 'ResNet-50 (2048-dim)'
      : searchResults.model_used === 'Database_Catalog_Browse'
      ? 'Database Catalog'
      : 'OpenCLIP ViT-B/32 (512-dim)'

  // Extract available unique categories
  const categories = useMemo(() => {
    const cats = new Set()
    rawResults.forEach((r) => {
      if (r.category) cats.add(r.category)
      else if (r.article_type) cats.add(r.article_type)
    })
    return ['ALL', ...Array.from(cats)]
  }, [rawResults])

  // Filtered results
  const filteredResults = useMemo(() => {
    if (!rawResults || rawResults.length === 0) return []
    if (activeCategoryFilter === 'ALL' && minSimilarityFilter === 0) {
      return rawResults
    }
    return rawResults.filter((r) => {
      const matchCat =
        activeCategoryFilter === 'ALL' ||
        (r.category && r.category.toLowerCase() === activeCategoryFilter.toLowerCase()) ||
        (r.article_type && r.article_type.toLowerCase() === activeCategoryFilter.toLowerCase())
      const score = Number(r.similarity_score != null ? r.similarity_score : 0) * 100
      const matchScore = score >= minSimilarityFilter
      return matchCat && matchScore
    })
  }, [rawResults, activeCategoryFilter, minSimilarityFilter])

  // Derive "You May Also Like" recommendations
  const recommendedItems = useMemo(() => deriveRecommendations(rawResults), [rawResults])

  // Handle case: Zero results returned from backend
  if (rawResults.length === 0) {
    return (
      <div className="main-wrapper">
        <div className="results-fallback-card">
          <div className="fallback-icon-empty">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="8" y1="12" x2="16" y2="12"></line>
            </svg>
          </div>
          <h2 className="fallback-title">No matching products found.</h2>
          <p className="fallback-desc">
            The visual search service did not find any catalog items matching this image. Try uploading a different product photo or exploring our category presets.
          </p>
          <div className="fallback-actions">
            <button
              className="btn btn-primary"
              onClick={() => {
                clearSearch()
                navigate('/')
              }}
            >
              Upload Another Image
            </button>
          </div>
        </div>
      </div>
    )
  }

  // Detached browser window popup
  const handleOpenInNewWindow = () => {
    const newWin = window.open('', '_blank', 'width=1280,height=850')
    if (!newWin) {
      alert('Popup blocker prevented opening the new window. Please allow popups for this site.')
      return
    }

    const cardsHtml = rawResults
      .map((r) => {
        const fullImg = getCatalogImageUrl(r.image_url || r.filename)
        const title = r.product_display_name || r.filename || `Item #${r.catalog_item_id}`
        const score = (Number(r.similarity_score != null ? r.similarity_score : 0) * 100).toFixed(2)
        const category = r.category || 'Apparel'
        const article = r.article_type || ''
        const color = r.base_colour ? `<span class="tag color">${r.base_colour}</span>` : ''
        const gender = r.gender ? `<span class="tag gender">${r.gender}</span>` : ''

        return `
        <div class="product-card">
          <div class="rank-badge">#${r.rank || 1}</div>
          <div class="img-box">
            <img src="${fullImg}" alt="${title}" onerror="this.src='https://via.placeholder.com/200?text=Product+Image'"/>
          </div>
          <div class="card-info">
            <div class="score-row">
              <span class="score-num">${score}% Similarity</span>
              <div class="score-bar"><div class="score-fill" style="width:${score}%"></div></div>
            </div>
            <h3 class="prod-title" title="${title}">${title}</h3>
            <div class="tags">
              <span class="tag cat">${category}</span>
              ${article ? `<span class="tag article">${article}</span>` : ''}
              ${color}
              ${gender}
            </div>
            <div class="id-row">
              <span>Item ID: #${r.catalog_item_id || r.product_id}</span>
              <span>Prod: #${r.product_id}</span>
            </div>
          </div>
        </div>`
      })
      .join('')

    const htmlContent = `
      <!DOCTYPE html>
      <html lang="en">
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Visual Search Results — ${displayFilename}</title>
        <style>
          * { box-sizing: border-box; margin: 0; padding: 0; }
          body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Inter, sans-serif;
            background: #080c17;
            color: #f8fafc;
            padding: 2rem;
            min-height: 100vh;
          }
          .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            padding-bottom: 1.25rem;
            margin-bottom: 2rem;
          }
          .header h1 { font-size: 1.5rem; color: #fff; font-weight: 700; }
          .header p { color: #94a3b8; font-size: 0.9rem; margin-top: 0.25rem; }
          .model-badge {
            background: #0284c7;
            color: #fff;
            padding: 0.35rem 0.85rem;
            border-radius: 9999px;
            font-size: 0.85rem;
            font-weight: 600;
          }
          .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
            gap: 1.25rem;
          }
          .product-card {
            background: #11192e;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 0.75rem;
            overflow: hidden;
            position: relative;
            display: flex;
            flex-direction: column;
            box-shadow: 0 4px 15px rgba(0,0,0,0.4);
          }
          .rank-badge {
            position: absolute;
            top: 0.5rem;
            left: 0.5rem;
            background: rgba(2,132,199,0.9);
            color: #fff;
            font-size: 0.75rem;
            font-weight: 700;
            padding: 0.2rem 0.5rem;
            border-radius: 0.35rem;
            z-index: 10;
          }
          .img-box { width: 100%; height: 180px; background: #000; overflow: hidden; }
          .img-box img { width: 100%; height: 100%; object-fit: cover; }
          .card-info { padding: 0.85rem; display: flex; flex-direction: column; gap: 0.45rem; }
          .score-row { display: flex; flex-direction: column; gap: 0.2rem; }
          .score-num { font-size: 0.9rem; font-weight: 700; color: #38bdf8; }
          .score-bar { width: 100%; height: 4px; background: rgba(255,255,255,0.1); border-radius: 2px; overflow: hidden; }
          .score-fill { height: 100%; background: linear-gradient(90deg, #38bdf8, #818cf8); }
          .prod-title { font-size: 0.875rem; font-weight: 600; color: #f8fafc; line-height: 1.3; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
          .tags { display: flex; flex-wrap: wrap; gap: 0.25rem; }
          .tag { font-size: 0.68rem; padding: 0.15rem 0.4rem; border-radius: 0.25rem; font-weight: 600; }
          .tag.cat { background: rgba(56,189,248,0.15); color: #38bdf8; }
          .tag.article { background: rgba(168,85,247,0.15); color: #c084fc; }
          .tag.color { background: rgba(234,179,8,0.15); color: #facc15; }
          .tag.gender { background: rgba(34,197,94,0.15); color: #4ade80; }
          .id-row { display: flex; justify-content: space-between; font-size: 0.72rem; color: #94a3b8; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 0.35rem; margin-top: 0.2rem; }
        </style>
      </head>
      <body>
        <div class="header">
          <div>
            <h1>Visual Search Results</h1>
            <p>Query: ${displayFilename} • (${rawResults.length} catalog matches)</p>
          </div>
          <span class="model-badge">${searchResults.model_used || 'OpenCLIP ViT-B/32'}</span>
        </div>
        <div class="grid">
          ${cardsHtml}
        </div>
      </body>
      </html>
    `
    newWin.document.write(htmlContent)
    newWin.document.close()
  }

  /**
   * Handle "Find Similar" from a result card.
   * Uses executeFindSimilar (does NOT set loading=true, results update in-place).
   */
  const handleFindSimilar = async (result) => {
    if (!result) return
    const catalogFilename = result.filename || (result.image_url ? result.image_url.split('/').pop() : '')
    const imageUrl = getCatalogImageUrl(result.image_url || result.filename)
    const displayName = result.product_display_name || result.filename || `Product #${result.product_id}`
    findSimilarTargetRef.current = result.catalog_item_id || result.product_id

    // Reset filters so the new product matches are fully displayed
    setActiveCategoryFilter('ALL')
    setMinSimilarityFilter(0)
    setSelectedProductDetail(null)

    try {
      await executeFindSimilar(catalogFilename, imageUrl, displayName, topK, selectedModel)
      // Smooth scroll back to top of results
      if (typeof window !== 'undefined') {
        window.scrollTo({ top: 0, behavior: 'smooth' })
      }
    } finally {
      findSimilarTargetRef.current = null
    }
  }

  return (
    <div className="results-page-layout">
      {/* Top Header / Action Bar */}
      <div className="results-top-header">
        <div className="results-top-left">
          <div className="pulse-indicator">
            <span className="dot"></span>
            <span className="label">LIVE SEARCH MATCHES</span>
          </div>
          <h1 className="results-main-title">
            Search Results
            <span className="results-count-pill">
              {filteredResults.length} / {totalResults} Found
            </span>
          </h1>
        </div>

        <div className="results-header-actions">
          <button
            className="btn-header-action"
            onClick={handleOpenInNewWindow}
            title="Open search in a separate detached browser window"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
              <polyline points="15 3 21 3 21 9"></polyline>
              <line x1="10" y1="14" x2="21" y2="3"></line>
            </svg>
            <span>Open in New Window</span>
          </button>

          <button
            className="btn-header-action btn-search-again"
            onClick={() => {
              clearSearch()
              navigate('/')
            }}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
              <polyline points="17 8 12 3 7 8"></polyline>
              <line x1="12" y1="3" x2="12" y2="15"></line>
            </svg>
            <span>New Search</span>
          </button>
        </div>
      </div>

      {/* Find Similar in-page loading banner */}
      {findSimilarLoading && (
        <div className="find-similar-loading-banner">
          <span className="spinner-inline" />
          <span>Loading visually similar products for selected item…</span>
        </div>
      )}

      {/* Error banner (inline, does not replace the page) */}
      {error && searchResults && (
        <div className="api-error-banner" role="alert">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="8" x2="12" y2="12"></line>
            <line x1="12" y1="16" x2="12.01" y2="16"></line>
          </svg>
          <div className="error-text-group">
            <p className="error-title">Search error</p>
            <p className="error-message">{error}</p>
          </div>
        </div>
      )}

      {/* Main Results Body: Two-Column Workspace */}
      <div className="results-page-body">
        {/* Left Column: Searched / Query Image */}
        <aside className="query-sidebar-panel">
          <div className="panel-section-title">Searched Image</div>
          <div className="query-image-wrapper">
            {queryPreview ? (
              <img
                src={queryPreview}
                alt="Query preview"
                className="query-hero-image"
                onError={(e) => {
                  if (rawResults[0]) {
                    e.target.src = getCatalogImageUrl(rawResults[0].image_url || rawResults[0].filename)
                  }
                }}
              />
            ) : rawResults[0] ? (
              <img
                src={getCatalogImageUrl(rawResults[0].image_url || rawResults[0].filename)}
                alt="Query match"
                className="query-hero-image"
              />
            ) : (
              <div className="query-image-placeholder">No Preview</div>
            )}
          </div>

          <div className="query-meta-card">
            <div className="query-meta-row">
              <span className="label">Query Filename:</span>
              <span className="value" title={displayFilename}>
                {displayFilename}
              </span>
            </div>
            <div className="query-meta-row">
              <span className="label">Retrieval Engine:</span>
              <span className="value model-tag">{modelUsedName}</span>
            </div>
            <div className="query-meta-row">
              <span className="label">Catalog Size:</span>
              <span className="value">44,119 Products</span>
            </div>
            <div className="query-meta-row">
              <span className="label">Top Match:</span>
              <span className="value highlight-score">
                {rawResults[0]
                  ? `${(Number(rawResults[0].similarity_score != null ? rawResults[0].similarity_score : 0) * 100).toFixed(1)}%`
                  : 'N/A'}
              </span>
            </div>
          </div>

          <div className="sidebar-tip-box">
            <span className="tip-title">⚡ Multi-Modal Search</span>
            <p>
              Ranked items reflect cosine similarity calculated across deep visual embeddings and color features.
            </p>
          </div>
        </aside>

        {/* Right Column: Similar Products Grid & Controls */}
        <main className="results-grid-panel">
          <div className="panel-section-title">Similar Products</div>

          {/* Filter Bar */}
          <div className="filter-controls-bar">
            <div className="category-filter-pills">
              {categories.map((cat) => (
                <button
                  key={cat}
                  className={`filter-pill ${activeCategoryFilter === cat ? 'active' : ''}`}
                  onClick={() => setActiveCategoryFilter(cat)}
                >
                  {cat}
                </button>
              ))}
            </div>

            <div className="similarity-slider-group">
              <label htmlFor="sim-filter">
                Min Similarity: <strong>{minSimilarityFilter}%</strong>
              </label>
              <input
                id="sim-filter"
                type="range"
                min="0"
                max="90"
                step="5"
                value={minSimilarityFilter}
                onChange={(e) => setMinSimilarityFilter(Number(e.target.value))}
              />
            </div>
          </div>

          {/* Results Grid */}
          {filteredResults.length > 0 ? (
            <div className="results-cards-grid">
              {filteredResults.map((item) => (
                <div
                  key={item.catalog_item_id || item.id || item.rank}
                  onClick={() => setSelectedProductDetail(item)}
                  className="clickable-card-wrapper"
                >
                  <ResultCard
                    result={item}
                    queryFilename={displayFilename}
                    onFindSimilar={handleFindSimilar}
                  />
                </div>
              ))}
            </div>
          ) : (
            <div className="no-matches-notice">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="8" y1="12" x2="16" y2="12"></line>
              </svg>
              <h3>No results match this filter</h3>
              <p>Try selecting "ALL" or lowering the minimum similarity threshold.</p>
            </div>
          )}

          {/* ================================================================
              You May Also Like — Metadata-based recommendations
              Derived client-side: same category + color as top result
              ================================================================ */}
          {recommendedItems.length >= 2 && (
            <div className="recommendations-section">
              <div className="recommendations-divider">
                <span className="recommendations-divider-line" />
                <span className="recommendations-divider-label">✨ You May Also Like</span>
                <span className="recommendations-divider-line" />
              </div>
              <p className="recommendations-caption">
                Based on category &amp; color similarity to your top match — curated from your current result set.
              </p>
              <div className="recommendations-grid">
                {recommendedItems.map((item) => (
                  <div
                    key={`rec-${item.catalog_item_id || item.id || item.rank}`}
                    onClick={() => setSelectedProductDetail(item)}
                    className="clickable-card-wrapper"
                  >
                    <ResultCard
                      result={item}
                      queryFilename={displayFilename}
                      onFindSimilar={handleFindSimilar}
                    />
                  </div>
                ))}
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Product Detail Modal */}
      <ProductDetailModal
        product={selectedProductDetail}
        onClose={() => setSelectedProductDetail(null)}
        onFindSimilar={handleFindSimilar}
      />
    </div>
  )
}
