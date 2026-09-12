import { useState } from 'react'
import { usePipeline } from '../../context/PipelineContext'
import { getPipelineApiBaseUrl } from '../../services/pipelineApi'
import './RagSection.css'

/**
 * RAG section for the shared frontend shell.
 *
 * Consumes the active pipeline_run_id from PipelineContext and displays
 * the RAG stage's result (summary, citations, grounded status) once the
 * gateway reports it. No manual re-upload or copy/paste is needed — this
 * section just reacts to pipelineStatus as it updates over the shared
 * WebSocket connection.
 *
 * ASSUMPTION (not yet confirmed against the gateway's real schema):
 * pipelineStatus.rag_result is expected to mirror the shape returned by
 * POST /api/v1/rag/process — { summary, citations, grounded,
 * groundedness_score, status }. Adjust the field reads below once this
 * is confirmed against a live gateway response.
 */
export default function RagSection() {
  const { currentPipelineRunId, pipelineStatus, connectionStatus } = usePipeline()

  const ragResult = pipelineStatus?.rag_result || null

  return (
    <div className="rag-section">
      <div className="rag-section__header">
        <h2>RAG — Grounded Answer</h2>
        <ConnectionBadge status={connectionStatus} />
      </div>

      {!currentPipelineRunId && (
        <EmptyState message="No active pipeline run. Upload an image to start one." />
      )}

      {currentPipelineRunId && !ragResult && (
        <EmptyState
          message="Waiting for the RAG stage to complete for this run."
          subtle
        />
      )}

      {ragResult && <RagResult result={ragResult} />}

      <StandaloneChat />
    </div>
  )
}

function ConnectionBadge({ status }) {
  const label = {
    connected: 'Live',
    connecting: 'Connecting…',
    disconnected: 'Offline',
    error: 'Connection error',
  }[status] || 'Idle'

  return <span className={`rag-badge rag-badge--${status || 'idle'}`}>{label}</span>
}

function EmptyState({ message, subtle }) {
  return (
    <div className={`rag-empty ${subtle ? 'rag-empty--subtle' : ''}`}>
      <p>{message}</p>
    </div>
  )
}

function RagResult({ result }) {
  const { summary, citations = [], grounded, groundedness_score, status } = result

  return (
    <div className="rag-result">
      <div className="rag-result__meta">
        <StatusPill status={status} />
        <GroundedPill grounded={grounded} score={groundedness_score} />
      </div>

      <p className="rag-result__summary">
        {summary && summary.trim() ? summary : 'No answer was generated for this run.'}
      </p>

      {citations.length > 0 && (
        <div className="rag-citations">
          <h3>Citations</h3>
          <ul>
            {citations.map((c, i) => (
              <li key={i} className="rag-citation">
                {c.image_url && (
                  <img src={c.image_url} alt={c.source || 'source'} className="rag-citation__thumb" />
                )}
                <div>
                  <div className="rag-citation__source">{c.source || 'Unknown source'}</div>
                  <div className="rag-citation__type">
                    {c.source_type === 'catalog_item' ? 'Catalog item' : 'Document'}
                    {c.page_number != null && ` · Page ${c.page_number}`}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function StatusPill({ status }) {
  const known = ['completed', 'insufficient_data', 'llm_unavailable', 'failed']
  const cls = known.includes(status) ? status : 'unknown'
  return <span className={`rag-pill rag-pill--${cls}`}>{status || 'unknown'}</span>
}

function GroundedPill({ grounded, score }) {
  if (grounded === null || grounded === undefined) {
    return <span className="rag-pill rag-pill--neutral">Not checked</span>
  }
  const label = grounded
    ? `Grounded${score != null ? ` (${score.toFixed(2)})` : ''}`
    : 'Not grounded'
  return <span className={`rag-pill rag-pill--${grounded ? 'grounded' : 'ungrounded'}`}>{label}</span>
}

/**
 * Keeps the original standalone RAG capability (ask a question directly
 * against the knowledge base) accessible inside the unified app, alongside
 * the merged-pipeline result above — per the team's agreement that each
 * module's standalone endpoint stays reachable, not replaced.
 */
function StandaloneChat() {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const ask = async () => {
    if (!question.trim()) return
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(`${getPipelineApiBaseUrl()}/api/v1/rag/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, history: [] }),
      })
      if (!response.ok) throw new Error(`Request failed (HTTP ${response.status})`)
      const data = await response.json()
      setAnswer(data)
    } catch (e) {
      setError(e.message || 'Something went wrong.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rag-standalone">
      <h3>Ask the knowledge base directly</h3>
      <div className="rag-standalone__input">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && ask()}
          placeholder="Ask a question about your documents…"
        />
        <button onClick={ask} disabled={loading || !question.trim()}>
          {loading ? 'Asking…' : 'Ask'}
        </button>
      </div>
      {error && <p className="rag-standalone__error">{error}</p>}
      {answer && (
        <div className="rag-standalone__answer">
          <p>{answer.answer}</p>
          {answer.sources?.length > 0 && (
            <ul className="rag-standalone__sources">
              {answer.sources.map((s, i) => (
                <li key={i}>{s.source}{s.page_number != null ? ` · Page ${s.page_number}` : ''}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}