import React from 'react'

const TOP_K_OPTIONS = [5, 10, 20, 50]

export default function SearchControls({ topK, onTopKChange, onSearch, disabled, loading }) {
  return (
    <div className="search-controls">
      <div className="control-group">
        <label htmlFor="top-k-select" className="control-label">
          Top Results:
        </label>
        <select
          id="top-k-select"
          className="select-input"
          value={topK}
          onChange={(e) => onTopKChange(Number(e.target.value))}
          disabled={loading}
        >
          {TOP_K_OPTIONS.map((val) => (
            <option key={val} value={val}>
              {val} Results
            </option>
          ))}
        </select>
      </div>

      <button
        type="button"
        className="btn btn-search"
        onClick={onSearch}
        disabled={disabled || loading}
      >
        {loading ? 'Searching...' : 'Search Catalog'}
      </button>
    </div>
  )
}
