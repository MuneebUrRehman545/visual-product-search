import React, { useState } from 'react'
import { usePipeline } from '../context/PipelineContext'
import { runAgentNow } from '../services/pipelineApi'

function ActionList({ actions }) {
  if (!Array.isArray(actions) || actions.length === 0) {
    return <p>No actions were returned.</p>
  }

  return (
    <ol>
      {actions.map((action, index) => (
        <li key={`${action?.action_type || 'action'}-${index}`}>
          <strong>{action?.action_type || 'Unknown action'}</strong>
          <pre>{JSON.stringify(action?.payload ?? {}, null, 2)}</pre>
        </li>
      ))}
    </ol>
  )
}

export default function AgentPage() {
  const { currentPipelineRunId, pipelineStatus, refreshPipelineStatus } = usePipeline()
  const [isRunning, setIsRunning] = useState(false)
  const [error, setError] = useState(null)

  if (!currentPipelineRunId) {
    return (
      <main className="main-wrapper">
        <section className="search-workspace">
          <h1>Agent</h1>
          <p>No active pipeline run.</p>
        </section>
      </main>
    )
  }

  const agentResult = pipelineStatus?.agent_result

  const handleRunAgent = async () => {
    setIsRunning(true)
    setError(null)

    try {
      await runAgentNow(currentPipelineRunId)
      await refreshPipelineStatus(currentPipelineRunId)
    } catch (err) {
      setError(err?.detail || err?.message || 'Unable to run the agent.')
    } finally {
      setIsRunning(false)
    }
  }

  return (
    <main className="main-wrapper">
      <section className="search-workspace">
        <h1>Agent</h1>
        <p>
          Pipeline run: <code>{currentPipelineRunId}</code>
        </p>

        {agentResult ? (
          <section aria-labelledby="agent-result-heading">
            <h2 id="agent-result-heading">Agent result</h2>
            <p>Decision: {agentResult.decision || 'Not provided'}</p>
            <p>Reason: {agentResult.reason || 'Not provided'}</p>
            <p>Agent run ID: {agentResult.agent_run_id || 'Not provided'}</p>
            <p>Status: {agentResult.status || 'Not provided'}</p>

            <h3>Actions</h3>
            <ActionList actions={agentResult.actions} />
          </section>
        ) : (
          <section aria-labelledby="agent-not-run-heading">
            <h2 id="agent-not-run-heading">Agent has not processed this run yet</h2>

            <button type="button" onClick={handleRunAgent} disabled={isRunning}>
              {isRunning ? 'Running Agent…' : 'Run Agent Now'}
            </button>

            {error && <p role="alert">{error}</p>}
          </section>
        )}
      </section>
    </main>
  )
}
