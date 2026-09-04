import React, { useState, useMemo, useEffect } from 'react'
import ResultCard from './ResultCard'
import { getCatalogImageUrl } from '../services/searchApi'

export default function ResultsWindowModal({
  isOpen,
  searchResults,
  queryImagePreview,
  onClose,
  onInspectProduct,
  onSearchAnother,
}) {
  const [activeCategoryFilter, setActiveCategoryFilter] = useState('ALL')
  const [minSimilarityFilter, setMinSimilarityFilter] = useState(0)

  // Reset filters whenever a new search result is received
  useEffect(() => {
    if (searchResults) {
      setActiveCategoryFilter('ALL')
      setMinSimilarityFilter(0)
    }
  }, [searchResults])

  if (!isOpen || !searchResults) return null

  const queryFilename = searchResults.query_filename || 'Query Image'
  const rawResults = Array.isArray(searchResults.results) ? searchResults.results : []
  const totalResults = searchResults.total_results || rawResults.length

  // Extract available unique master categories
  const categories = useMemo(() => {
    const cats = new Set()
    rawResults.forEach((r) => {
      if (r.category) cats.add(r.category)
      else if (r.article_type) cats.add(r.article_type)
    })
    return ['ALL', ...Array.from(cats)]
  }, [rawResults])

  // Filtered results with safe defaults
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

  // Open results in a new dedicated detached browser window
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
        <title>Visual Search Results — ${queryFilename}</title>
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
          .img-box {
            width: 100%;
            height: 180px;
            background: #000;
            overflow: hidden;
          }
          .img-box img {
            width: 100%;
            height: 100%;
            object-fit: cover;
          }
          .card-info {
            padding: 0.85rem;
            display: flex;
            flex-direction: column;
            gap: 0.45rem;
          }
          .score-row { display: flex; flex-direction: column; gap: 0.2rem; }
          .score-num { font-size: 0.9rem; font-weight: 700; color: #38bdf8; }
          .score-bar { width: 100%; height: 4px; background: rgba(255,255,255,0.1); border-radius: 2px; overflow: hidden; }
          .score-fill { height: 100%; background: linear-gradient(90deg, #38bdf8, #818cf8); }
          .prod-title {
            font-size: 0.875rem;
            font-weight: 600;
            color: #f8fafc;
            line-height: 1.3;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }
          .tags { display: flex; flex-wrap: wrap; gap: 0.25rem; }
          .tag { font-size: 0.68rem; padding: 0.15rem 0.4rem; border-radius: 0.25rem; font-weight: 600; }
          .tag.cat { background: rgba(56,189,248,0.15); color: #38bdf8; }
          .tag.article { background: rgba(168,85,247,0.15); color: #c084fc; }
          .tag.color { background: rgba(234,179,8,0.15); color: #facc15; }
          .tag.gender { background: rgba(34,197,94,0.15); color: #4ade80; }
          .id-row {
            display: flex;
            justify-content: space-between;
            font-size: 0.72rem;
            color: #94a3b8;
            border-top: 1px solid rgba(255,255,255,0.05);
            padding-top: 0.35rem;
            margin-top: 0.2rem;
          }
        </style>
      </head>
      <body>
        <div class="header">
          <div>
            <h1>Visual Search Results</h1>
            <p>Query: ${queryFilename} • (${rawResults.length} catalog matches)</p>
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

  return (
    <div className="modal-overlay results-modal-overlay" onClick={onClose}>
      <div
        className="results-window-card"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        {/* Top Floating Control Bar */}
        <div className="results-window-header">
          <div className="results-header-left">
            <div className="pulse-indicator">
              <span className="dot"></span>
              <span className="label">LIVE SEARCH MATCHES</span>
            </div>
            <h2 className="results-window-title">
              Visual Search Results
              <span className="results-count-pill">{filteredResults.length} / {totalResults} Found</span>
            </h2>
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
                onClose()
                if (onSearchAnother) onSearchAnother()
              }}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="17 8 12 3 7 8"></polyline>
                <line x1="12" y1="3" x2="12" y2="15"></line>
              </svg>
              <span>New Search</span>
            </button>

            <button className="results-close-btn" onClick={onClose} aria-label="Close window">
              &times;
            </button>
          </div>
        </div>

        {/* Main Content: Split Workspace */}
        <div className="results-window-body">
          {/* Left Column: Query Inspection */}
          <aside className="query-sidebar-panel">
            <div className="panel-section-title">Query Image</div>
            <div className="query-image-wrapper">
              {queryImagePreview ? (
                <img
                  src={queryImagePreview}
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
                <span className="label">Source:</span>
                <span className="value" title={queryFilename}>
                  {queryFilename}
                </span>
              </div>
              <div className="query-meta-row">
                <span className="label">Retrieval Engine:</span>
                <span className="value model-tag">
                  {searchResults.model_used === 'ResNet_50'
                    ? 'ResNet-50 (2048-dim)'
                    : searchResults.model_used === 'Database_Catalog_Browse'
                    ? 'Database Catalog'
                    : 'OpenCLIP ViT-B/32 (512-dim)'}
                </span>
              </div>
              <div className="query-meta-row">
                <span className="label">Catalog Size:</span>
                <span className="value">44,119 Products</span>
              </div>
              <div className="query-meta-row">
                <span className="label">Top Match:</span>
                <span className="value highlight-score">
                  {rawResults[0]
                    ? `${(Number(rawResults[0].similarity_score || 1.0) * 100).toFixed(1)}%`
                    : 'N/A'}
                </span>
              </div>
            </div>

            <div className="sidebar-tip-box">
              <span className="tip-title">⚡ Zero Scroll Experience</span>
              <p>
                Matches open automatically in this overlay window for instant side-by-side comparison.
              </p>
            </div>
          </aside>

          {/* Right Column: Results Grid & Filters */}
          <main className="results-grid-panel">
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
                    onClick={() => onInspectProduct && onInspectProduct(item)}
                    className="clickable-card-wrapper"
                  >
                    <ResultCard result={item} />
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
          </main>
        </div>
      </div>
    </div>
  )
}
