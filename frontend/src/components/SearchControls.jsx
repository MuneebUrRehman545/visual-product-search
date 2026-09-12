import React from 'react'

const TOP_K_OPTIONS = [5, 10, 20, 50]

const MODEL_OPTIONS = [
  {
    id: 'clip',
    name: 'OpenCLIP ViT-B/32',
    dim: '512-dim',
    desc: 'Multimodal Transformer',
    badge: 'Recommended',
  },
  {
    id: 'resnet',
    name: 'ResNet-50',
    dim: '2048-dim',
    desc: 'Deep CNN Features',
    badge: 'Baseline',
  },
]

export default function SearchControls({
  topK,
  onTopKChange,
  selectedModel,
  onModelChange,
  onSearch,
  disabled,
  loading,
}) {
  return (
    <div className="search-controls-card">
      <div className="search-controls-horizontal">
        {/* Model Selection */}
        <div className="control-section model-section">
          <div className="control-label-group">
            <span className="control-label">Embedding Model:</span>
          </div>
          <div className="model-pill-group">
            {MODEL_OPTIONS.map((m) => {
              const isActive = (selectedModel || 'clip') === m.id
              return (
                <button
                  key={m.id}
                  type="button"
                  className={`model-select-pill ${isActive ? 'active' : ''}`}
                  onClick={() => onModelChange && onModelChange(m.id)}
                  disabled={loading}
                >
                  <div className="model-pill-content">
                    <div className="model-title-row">
                      <span className="model-name">{m.name}</span>
                      <span className={`model-badge ${m.id === 'clip' ? 'badge-clip' : 'badge-resnet'}`}>
                        {m.badge}
                      </span>
                    </div>
                    <span className="model-dim-label">{m.dim} • {m.desc}</span>
                  </div>
                </button>
              )
            })}
          </div>
        </div>

        {/* Depth & Search Row */}
        <div className="control-bottom-row">
          <div className="control-left-section">
            <span className="control-label">Retrieval Depth:</span>
            <div className="top-k-pill-group">
              {TOP_K_OPTIONS.map((val) => (
                <button
                  key={val}
                  type="button"
                  className={`top-k-pill ${topK === val ? 'active' : ''}`}
                  onClick={() => onTopKChange(val)}
                  disabled={loading}
                >
                  Top {val}
                </button>
              ))}
            </div>
          </div>

          <div className="search-btn-wrapper">
            <button
              type="button"
              className={`btn btn-search ${loading ? 'btn-searching' : ''}`}
              onClick={onSearch}
              disabled={disabled || loading}
              title={
                disabled
                  ? 'Please select or upload an image above first'
                  : loading
                  ? 'Search is currently in progress...'
                  : 'Find visually similar products in catalog'
              }
            >
              {loading ? (
                <>
                  <span className="spinner-inline"></span>
                  <span>
                    Searching with {selectedModel === 'resnet' ? 'ResNet-50' : 'OpenCLIP'}...
                  </span>
                </>
              ) : (
                <>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25">
                    <circle cx="11" cy="11" r="8"></circle>
                    <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                  </svg>
                  <span>Find Similar Products</span>
                </>
              )}
            </button>
            {disabled && !loading && (
              <span className="search-hint-text">Select or drop a product photo above to search</span>
            )}
            {loading && (
              <span className="search-hint-text processing">
                Extracting deep visual embeddings & querying FAISS index…
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
