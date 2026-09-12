import React, { useState } from 'react'
import { getCatalogImageUrl } from '../services/searchApi'

export default function ProductDetailModal({ product, onClose, onFindSimilar }) {
  const [imageError, setImageError] = useState(false)

  if (!product) return null

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
  } = product

  const fullImageUrl = getCatalogImageUrl(image_url || filename)
  const percentageScore = (Number(similarity_score != null ? similarity_score : 0) * 100).toFixed(2)
  const title = product_display_name || filename || `Product #${product_id}`

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="product-detail-card" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close-btn" onClick={onClose} aria-label="Close modal">
          &times;
        </button>

        <div className="product-detail-layout">
          {/* Left: High-Res Image View */}
          <div className="product-image-column">
            <div className="product-rank-badge">Rank #{rank}</div>
            {!imageError ? (
              <img
                src={fullImageUrl}
                alt={title}
                className="detail-large-image"
                onError={() => setImageError(true)}
              />
            ) : (
              <div className="detail-image-fallback">Image Unavailable</div>
            )}
            <div className="detail-image-caption">{filename}</div>
          </div>

          {/* Right: Product Metadata & Match Analytics */}
          <div className="product-info-column">
            <div className="detail-category-header">
              <span className="badge-master-cat">{category || 'Apparel'}</span>
              {article_type && <span className="badge-sub-cat">{article_type}</span>}
            </div>

            <h2 className="detail-title">{title}</h2>

            {/* Similarity Score Card */}
            <div className="detail-score-box">
              <div className="score-top">
                <span className="score-heading">Visual Similarity Match</span>
                <span className="score-pct">{percentageScore}%</span>
              </div>
              <div className="score-bar-bg">
                <div className="score-bar-prog" style={{ width: `${percentageScore}%` }}></div>
              </div>
              <p className="score-subtext">
                Computed via OpenCLIP ViT-B/32 cosine similarity over 512 dimensions.
              </p>
            </div>

            {/* Structured Specifications Table */}
            <div className="detail-spec-table">
              <div className="spec-row">
                <span className="spec-label">Database Item ID:</span>
                <span className="spec-value highlight">#{catalog_item_id}</span>
              </div>
              <div className="spec-row">
                <span className="spec-label">Product Group ID:</span>
                <span className="spec-value">#{product_id}</span>
              </div>
              {sub_category && (
                <div className="spec-row">
                  <span className="spec-label">Sub-Category:</span>
                  <span className="spec-value">{sub_category}</span>
                </div>
              )}
              {article_type && (
                <div className="spec-row">
                  <span className="spec-label">Article Type:</span>
                  <span className="spec-value">{article_type}</span>
                </div>
              )}
              {base_colour && (
                <div className="spec-row">
                  <span className="spec-label">Color:</span>
                  <span className="spec-value color-badge">{base_colour}</span>
                </div>
              )}
              {gender && (
                <div className="spec-row">
                  <span className="spec-label">Gender Target:</span>
                  <span className="spec-value">{gender}</span>
                </div>
              )}
              {season && (
                <div className="spec-row">
                  <span className="spec-label">Season:</span>
                  <span className="spec-value">{season}</span>
                </div>
              )}
              {usage && (
                <div className="spec-row">
                  <span className="spec-label">Usage / Style:</span>
                  <span className="spec-value">{usage}</span>
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="detail-actions">
              {onFindSimilar && (
                <button
                  type="button"
                  className="btn btn-primary btn-modal-find-similar"
                  onClick={() => {
                    onClose()
                    onFindSimilar(product)
                  }}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25">
                    <circle cx="11" cy="11" r="8" />
                    <line x1="21" y1="21" x2="16.65" y2="16.65" />
                  </svg>
                  <span>Find Similar Products</span>
                </button>
              )}
              <a
                href={fullImageUrl}
                target="_blank"
                rel="noreferrer"
                className="btn-view-raw"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                  <polyline points="15 3 21 3 21 9"></polyline>
                  <line x1="10" y1="14" x2="21" y2="3"></line>
                </svg>
                View Full-Resolution Image
              </a>
              <button className="btn-close-detail" onClick={onClose}>
                Back to Results
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
