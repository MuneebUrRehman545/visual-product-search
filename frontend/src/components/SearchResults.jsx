import React from 'react'
import ResultCard from './ResultCard'

export default function SearchResults({ queryFilename, totalResults, results }) {
  if (!results) return null

  if (results.length === 0) {
    return (
      <div className="results-container empty-results">
        <p className="no-results-message">No visually similar products found in the catalog.</p>
      </div>
    )
  }

  return (
    <div className="results-section">
      <div className="results-header">
        <h2>Search Results</h2>
        <p className="results-summary">
          Found <strong>{totalResults}</strong> visually similar product{totalResults === 1 ? '' : 's'} for query image <em>"{queryFilename}"</em>
        </p>
      </div>

      <div className="results-grid">
        {results.map((result) => (
          <ResultCard key={`${result.product_id}-${result.rank}`} result={result} />
        ))}
      </div>
    </div>
  )
}
