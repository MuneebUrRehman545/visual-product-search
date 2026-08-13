import React, { useState } from 'react'
import { getCatalogImageUrl } from '../services/searchApi'

export default function ResultCard({ result }) {
  const [imageError, setImageError] = useState(false)

  if (!result) return null

  const { rank, product_id, external_id, filename, category, image_url, similarity_score } = result

  const fullImageUrl = getCatalogImageUrl(image_url)
  const percentageScore = (similarity_score * 100).toFixed(2)

  return (
    <div className="result-card">
      <div className="card-rank-badge">#{rank}</div>

      <div className="card-image-container">
        {!imageError ? (
          <img
            src={fullImageUrl}
            alt={filename ? `Product ${filename}` : `Catalog Product #${rank}`}
            className="card-image"
            onError={() => setImageError(true)}
            loading="lazy"
          />
        ) : (
          <div className="image-fallback">
            <span>Image Unavailable</span>
          </div>
        )}
      </div>

      <div className="card-body">
        <div className="score-container">
          <span className="score-label">Similarity</span>
          <span className="score-value">{percentageScore}%</span>
        </div>
        <div className="score-bar-background">
          <div
            className="score-bar-fill"
            style={{ width: `${Math.min(Math.max(Number(percentageScore), 0), 100)}%` }}
          />
        </div>

        <div className="card-details">
          <p className="detail-row">
            <span className="detail-label">Product ID:</span>
            <span className="detail-value">{product_id}</span>
          </p>
          <p className="detail-row">
            <span className="detail-label">External ID:</span>
            <span className="detail-value">{external_id || 'N/A'}</span>
          </p>
          {category && (
            <p className="detail-row">
              <span className="detail-label">Category:</span>
              <span className="detail-value category-tag">{category}</span>
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
