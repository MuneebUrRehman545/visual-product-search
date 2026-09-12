import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { getPipelineApiBaseUrl, getPipelineStatus } from '../services/pipelineApi'

const PipelineContext = createContext(null)
const SESSION_STORAGE_KEY = 'vps_current_pipeline_run_id'

function getPipelineWebSocketUrl(runId) {
  const gatewayUrl = new URL(getPipelineApiBaseUrl())
  gatewayUrl.protocol = gatewayUrl.protocol === 'https:' ? 'wss:' : 'ws:'
  gatewayUrl.pathname = `/ws/pipeline/${encodeURIComponent(runId)}`
  gatewayUrl.search = ''
  gatewayUrl.hash = ''
  return gatewayUrl.toString()
}

export function PipelineProvider({ children }) {
  const [currentPipelineRunId, setCurrentPipelineRunIdState] = useState(null)
  const [pipelineStatus, setPipelineStatus] = useState(null)
  const [socket, setSocket] = useState(null)
  const [connectionStatus, setConnectionStatus] = useState('disconnected')
  const socketRef = useRef(null)

  useEffect(() => {
    try {
      const savedRunId = sessionStorage.getItem(SESSION_STORAGE_KEY)
      if (savedRunId) {
        setCurrentPipelineRunIdState(savedRunId)
      }
    } catch (error) {
      console.warn('Could not restore the active pipeline run:', error)
    }
  }, [])

  const setCurrentPipelineRunId = useCallback((nextRunId) => {
    setCurrentPipelineRunIdState((previousRunId) => {
      const resolvedRunId = typeof nextRunId === 'function' ? nextRunId(previousRunId) : nextRunId

      try {
        if (resolvedRunId) {
          sessionStorage.setItem(SESSION_STORAGE_KEY, resolvedRunId)
        } else {
          sessionStorage.removeItem(SESSION_STORAGE_KEY)
        }
      } catch (error) {
        console.warn('Could not persist the active pipeline run:', error)
      }

      return resolvedRunId || null
    })
  }, [])

  const refreshPipelineStatus = useCallback(async (runId = currentPipelineRunId) => {
    if (!runId) return null

    const latestStatus = await getPipelineStatus(runId)
    setPipelineStatus(latestStatus)
    return latestStatus
  }, [currentPipelineRunId])

  useEffect(() => {
    if (!currentPipelineRunId) {
      setPipelineStatus(null)
      setConnectionStatus('disconnected')
      setSocket(null)
      return undefined
    }

    let active = true
    let pipelineSocket = null

    refreshPipelineStatus(currentPipelineRunId).catch((error) => {
      if (active) console.error('Could not load pipeline status:', error)
    })

    if (typeof WebSocket === 'undefined') {
      return () => {
        active = false
      }
    }

    try {
      setConnectionStatus('connecting')
      pipelineSocket = new WebSocket(getPipelineWebSocketUrl(currentPipelineRunId))
      socketRef.current = pipelineSocket
      setSocket(pipelineSocket)

      pipelineSocket.onopen = () => {
        if (active) setConnectionStatus('connected')
      }

      pipelineSocket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          if (active) setPipelineStatus(message.status || message)
        } catch (error) {
          console.warn('Ignoring non-JSON pipeline WebSocket message:', error)
        }
      }

      pipelineSocket.onerror = () => {
        if (active) setConnectionStatus('error')
      }

      pipelineSocket.onclose = () => {
        if (active) {
          setConnectionStatus('disconnected')
          setSocket(null)
        }
      }
    } catch (error) {
      console.error('Could not connect to pipeline WebSocket:', error)
      setConnectionStatus('error')
    }

    return () => {
      active = false
      if (pipelineSocket) {
        pipelineSocket.close()
      }
      if (socketRef.current === pipelineSocket) {
        socketRef.current = null
      }
    }
  }, [currentPipelineRunId, refreshPipelineStatus])

  const value = useMemo(
    () => ({
      currentPipelineRunId,
      setCurrentPipelineRunId,
      pipelineStatus,
      setPipelineStatus,
      socket,
      connectionStatus,
      refreshPipelineStatus,
    }),
    [connectionStatus, currentPipelineRunId, pipelineStatus, refreshPipelineStatus, socket]
  )

  return <PipelineContext.Provider value={value}>{children}</PipelineContext.Provider>
}

export function usePipeline() {
  const context = useContext(PipelineContext)
  if (!context) {
    throw new Error('usePipeline must be used within a PipelineProvider')
  }
  return context
}
