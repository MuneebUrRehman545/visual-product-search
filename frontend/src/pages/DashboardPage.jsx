import React from 'react'
import { usePipeline } from '../context/PipelineContext'

const STAGES = [
  { key: 'vision', label: 'Vision' },
  { key: 'rag', label: 'RAG' },
  { key: 'agent', label: 'Agent' },
]

function normalizeStatus(value) {
  if (!value) return null

  const status = String(value).trim().toLowerCase()
  if (/(fail|error|cancel)/.test(status)) return 'failed'
  if (/(complete|success|finish|done)/.test(status)) return 'complete'
  if (/(process|running|started|in.progress)/.test(status)) return 'processing'
  if (/(pending|queued|waiting)/.test(status)) return 'pending'
  return status
}

function getStageStatus(pipelineStatus, stageKey, events) {
  const stageData = pipelineStatus?.stages?.[stageKey] || pipelineStatus?.[stageKey]
  const explicitStatus =
    stageData?.status ||
    pipelineStatus?.[`${stageKey}_status`] ||
    pipelineStatus?.[`${stageKey}Status`]

  const normalizedExplicitStatus = normalizeStatus(explicitStatus)
  if (normalizedExplicitStatus) return normalizedExplicitStatus

  const stageEvents = events.filter(
    (item) => String(item?.module || '').trim().toLowerCase() === stageKey
  )
  const latestEvent = stageEvents[stageEvents.length - 1]
  const eventStatus = normalizeStatus(
    latestEvent?.status || latestEvent?.state || latestEvent?.event || latestEvent?.type
  )
  if (eventStatus) return eventStatus

  // A result is concrete gateway data, so it is evidence of a completed stage.
  if (pipelineStatus?.[`${stageKey}_result`] != null) return 'complete'

  return 'not started'
}

function getVisionSummary(visionResult) {
  if (!visionResult) return null

  const product = visionResult.primary_match || visionResult.product || visionResult
  return {
    productName: product?.product_name || product?.name || product?.title || 'Unknown product',
    confidence: visionResult.confidence ?? product?.confidence ?? product?.score ?? null,
  }
}

function getRagSummary(ragResult) {
  if (!ragResult) return null
  return ragResult.content || ragResult.summary || ragResult.text || ragResult.answer || null
}

export default function DashboardPage() {
  const { currentPipelineRunId, pipelineStatus } = usePipeline()

  if (!currentPipelineRunId) {
    return (
      <main className="main-wrapper">
        <section className="search-workspace">
          <h1>Pipeline Dashboard</h1>
          <p>No active pipeline run — start a search to begin.</p>
        </section>
      </main>
    )
  }

  const events = Array.isArray(pipelineStatus?.events) ? pipelineStatus.events : []
  const visionSummary = getVisionSummary(pipelineStatus?.vision_result)
  const ragSummary = getRagSummary(pipelineStatus?.rag_result)
  const agentResult = pipelineStatus?.agent_result

  return (
    <main className="main-wrapper">
      <section className="search-workspace">
        <h1>Pipeline Dashboard</h1>
        <p>
          Pipeline run: <code>{currentPipelineRunId}</code>
        </p>

        <section aria-labelledby="pipeline-stages-heading">
          <h2 id="pipeline-stages-heading">Stage progress</h2>
          <ol>
            {STAGES.map((stage) => (
              <li key={stage.key}>
                <strong>{stage.label}</strong>: {getStageStatus(pipelineStatus, stage.key, events)}
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="pipeline-results-heading">
          <h2 id="pipeline-results-heading">Available results</h2>

          {visionSummary && (
            <article>
              <h3>Vision</h3>
              <p>Product: {visionSummary.productName}</p>
              <p>
                Confidence:{' '}
                {visionSummary.confidence === null ? 'Not provided' : visionSummary.confidence}
              </p>
            </article>
          )}

          {ragSummary && (
            <article>
              <h3>RAG</h3>
              <p>{ragSummary}</p>
            </article>
          )}

          {agentResult && (
            <article>
              <h3>Agent</h3>
              <p>Decision: {agentResult.decision || 'Not provided'}</p>
              <p>Reason: {agentResult.reason || 'Not provided'}</p>
            </article>
          )}

          {!visionSummary && !ragSummary && !agentResult && (
            <p>No module result summaries are available yet.</p>
          )}
        </section>

        <section aria-labelledby="pipeline-events-heading">
          <h2 id="pipeline-events-heading">Pipeline events</h2>

          {events.length === 0 ? (
            <p>No events have been received for this run yet.</p>
          ) : (
            <ol>
              {events.map((item, index) => (
                <li key={`${item?.timestamp || item?.created_at || index}-${item?.module || 'event'}`}>
                  <strong>{item?.module || 'unknown module'}</strong> — {item?.event || 'event'}
                  {item?.message ? `: ${item.message}` : ''}
                  <br />
                  <small>{item?.timestamp || item?.created_at || 'timestamp unavailable'}</small>
                </li>
              ))}
            </ol>
          )}
        </section>
      </section>
    </main>
  )
}
