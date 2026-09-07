/**
 * Pipeline Gateway API client.
 *
 * `VITE_PIPELINE_API_BASE_URL` may point at a dedicated gateway. When it is
 * not supplied, the existing Vite API base URL convention is used.
 */
export function getPipelineApiBaseUrl() {
  let configuredUrl = null

  try {
    configuredUrl = import.meta.env.VITE_PIPELINE_API_BASE_URL || import.meta.env.VITE_API_BASE_URL
  } catch (e) {}

  if (configuredUrl && typeof configuredUrl === 'string' && configuredUrl.trim()) {
    return configuredUrl.trim().replace(/\/+$/, '')
  }

  if (typeof window !== 'undefined' && window.location?.hostname) {
    return `http://${window.location.hostname}:8000`
  }

  return 'http://127.0.0.1:8000'
}

async function readResponse(response) {
  let data = null

  try {
    data = await response.json()
  } catch (e) {}

  if (!response.ok) {
    const detail = data?.detail || data?.message || `Pipeline request failed (HTTP ${response.status})`
    const error = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
    error.status = response.status
    error.detail = detail
    throw error
  }

  return data
}

/**
 * Start a new pipeline run.
 *
 * @param {object} [payload] Optional run configuration accepted by the gateway.
 * @returns {Promise<object>} The created pipeline-run payload.
 */
export async function createPipelineRun(payload) {
  const options = { method: 'POST' }

  if (payload !== undefined) {
    options.headers = { 'Content-Type': 'application/json' }
    options.body = JSON.stringify(payload)
  }

  const response = await fetch(`${getPipelineApiBaseUrl()}/api/v1/pipeline/run`, options)
  return readResponse(response)
}

/**
 * Retrieve the latest status for one pipeline run.
 *
 * @param {string} runId
 * @returns {Promise<object>} The pipeline status payload.
 */
export async function getPipelineStatus(runId) {
  if (!runId) {
    throw new Error('A pipeline run ID is required.')
  }

  const response = await fetch(
    `${getPipelineApiBaseUrl()}/api/v1/pipeline/run/${encodeURIComponent(runId)}`
  )
  return readResponse(response)
}

/**
 * Manually trigger the Agent module for an existing pipeline run.
 *
 * @param {string} pipelineRunId
 * @returns {Promise<object>} The Agent-run response payload.
 */
export async function runAgentNow(pipelineRunId) {
  if (!pipelineRunId) {
    throw new Error('A pipeline run ID is required to run the agent.')
  }

  const response = await fetch(`${getPipelineApiBaseUrl()}/api/v1/agent/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pipeline_run_id: pipelineRunId }),
  })

  return readResponse(response)
}
