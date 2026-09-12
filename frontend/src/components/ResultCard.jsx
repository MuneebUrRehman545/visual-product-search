import React, { useState } from 'react'
import { getCatalogImageUrl } from '../services/searchApi'

/**
 * Verify whether the result is genuinely the exact same catalog product/image as the query.
 *
 * Rules:
 *   - Must have matching reliable identifiers (filename, product_id, catalog_item_id, or external_id)
 *   - Excludes generic placeholder names (e.g. "query.jpg", "image.png")
 *   - Must have a genuine top similarity score (>= 99.9%)
 *   - NEVER marks an item as Exact Match solely based on score or rank
 */
function isExactImageMatch(result, queryFilename, rawScore) {
  if (!result || !queryFilename) return false

  const cleanQuery = String(queryFilename).trim().toLowerCase()
  const genericPlaceholders = ['query.jpg', 'query.png', 'query.jpeg', 'query image', 'uploaded image', 'image', 'search query']
  if (genericPlaceholders.includes(cleanQuery)) {
    return false
  }

  const cleanQueryStem = cleanQuery.replace(/\.[^/.]+$/, '')
  const cleanResultFn = String(result.filename || '').trim().toLowerCase()
  const cleanResultStem = cleanResultFn.replace(/\.[^/.]+$/, '')

  const idMatches =
    (cleanResultFn && cleanResultFn === cleanQuery) ||
    (cleanResultStem && cleanResultStem === cleanQueryStem) ||
    (result.product_id != null && String(result.product_id).trim() === cleanQueryStem) ||
    (result.catalog_item_id != null && String(result.catalog_item_id).trim() === cleanQueryStem) ||
    (result.external_id != null && String(result.external_id).trim().toLowerCase() === cleanQueryStem)

  return Boolean(idMatches && rawScore >= 0.999)
}

/**
 * Format similarity score and label cleanly without artificial roundups to 100%.
 */
function getSimilarityInfo(result, queryFilename, rawScore) {
  const percentageScore = Math.max(0, rawScore * 100)
  const isExact = isExactImageMatch(result, queryFilename, rawScore)

  if (isExact) {
    return {
      label: 'Match',
      displayValue: 'Exact Match',
      percentageScore,
      isExactMatch: true,
    }
  }

  // Display genuine measured similarity with 2 decimal places to avoid false 100% rounding
  return {
    label: 'Similarity',
    displayValue: `${percentageScore.toFixed(2)}%`,
    percentageScore,
    isExactMatch: false,
  }
}

export default function ResultCard({ result, queryFilename, onFindSimilar }) {
  const [imageError, setImageError] = useState(false)
  const [findingLoading, setFindingLoading] = useState(false)

  if (!result) return null

  const {
    rank,
    catalog_item_id,
    product_id,
    filename,
    product_display_name,
    category,
    sub_category,
    article_type,
    base_colour,
    gender,
    season,
    usage,
    image_url,
    similarity_score,
  } = result

  const fullImageUrl = getCatalogImageUrl(image_url || filename)

  // Use 0 as fallback so null scores don't appear as "100%"
  const rawScore = similarity_score != null ? Number(similarity_score) : 0
  const { label, displayValue, percentageScore, isExactMatch } = getSimilarityInfo(
    result,
    queryFilename,
    rawScore
  )

  const displayTitle = product_display_name || filename || `Product #${product_id || catalog_item_id}`

  const handleFindSimilar = async (e) => {
    e.stopPropagation() // prevent ProductDetailModal from opening
    if (!onFindSimilar || findingLoading) return
    setFindingLoading(true)
    try {
      await onFindSimilar(result)
    } finally {
      setFindingLoading(false)
    }
  }

  return (
    <div className="result-card">
      <div className="card-rank-badge">#{rank || 1}</div>

      <div className="card-image-container">
        {!imageError ? (
          <img
            src={fullImageUrl}
            alt={displayTitle}
            className="card-image"
            onError={() => setImageError(true)}
            loading="lazy"
          />
        ) : (
          <div className="image-fallback">
            <span>Product #{catalog_item_id || product_id}</span>
          </div>
        )}
      </div>

      <div className="card-body">
        <h3 className="card-title" title={displayTitle}>
          {displayTitle}
        </h3>

        <div className="score-container">
          <span className="score-label">
            {label}
          </span>
          <span className={`score-value ${isExactMatch ? 'score-exact-match' : ''}`}>
            {displayValue}
          </span>
        </div>
        <div className="score-bar-background">
          <div
            className="score-bar-fill"
            style={{ width: `${Math.min(Math.max(percentageScore, 0), 100)}%` }}
          />
        </div>

        <div className="card-details">
          <div className="tags-container">
            {category && <span className="meta-tag category-tag">{category}</span>}
            {sub_category && <span className="meta-tag category-tag">{sub_category}</span>}
            {article_type && <span className="meta-tag article-tag">{article_type}</span>}
            {base_colour && <span className="meta-tag colour-tag">{base_colour}</span>}
            {gender && <span className="meta-tag gender-tag">{gender}</span>}
          </div>

          <div className="id-meta-row">
            <span className="id-label">Item ID: #{catalog_item_id || product_id}</span>
            <span className="id-label">Prod: #{product_id}</span>
          </div>
        </div>

        {/* Find Similar action */}
        {onFindSimilar && (
          <button
            type="button"
            className={`btn-find-similar ${findingLoading ? 'btn-find-similar--loading' : ''}`}
            onClick={handleFindSimilar}
            disabled={findingLoading}
            title={`Find products visually similar to "${displayTitle}"`}
          >
            {findingLoading ? (
              <>
                <span className="spinner-inline" />
                <span>Searching…</span>
              </>
            ) : (
              <>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25">
                  <circle cx="11" cy="11" r="8" />
                  <line x1="21" y1="21" x2="16.65" y2="16.65" />
                </svg>
                <span>Find Similar</span>
              </>
            )}
          </button>
        )}
      </div>
    </div>
  )
}
