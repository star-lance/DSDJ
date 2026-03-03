import { useState, useEffect, useRef } from 'react'

const DEFAULT_STATE = {
  deck_a: { playing: false, bpm: 0, volume: 0, filter_value: 0.5,
            eq_low: 0.5, eq_mid: 0.5, eq_high: 0.5, sync_enabled: false,
            loop_active: false, hot_cues: [false,false,false,false],
            track_title: '', track_artist: '' },
  deck_b: { playing: false, bpm: 0, volume: 0, filter_value: 0.5,
            eq_low: 0.5, eq_mid: 0.5, eq_high: 0.5, sync_enabled: false,
            loop_active: false, hot_cues: [false,false,false,false],
            track_title: '', track_artist: '' },
  crossfader: 0.5,
  gyro_enabled: false,
  eq_mode: false,
  effect_wet_dry: 0.0,
  effect_parameter: 0.5,
  gyro_roll_binding: { unit: 0, target: 'mix' },
  gyro_pitch_binding: { unit: 1, target: 'parameter1' },
  ui_view: 'decks',
  connected: false,
}

export function useWebSocket(url) {
  const [state, setState] = useState(DEFAULT_STATE)
  const [connected, setConnected] = useState(false)
  const wsRef = useRef(null)

  useEffect(() => {
    let retryTimer = null

    function connect() {
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => setConnected(true)

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          if (msg.type === 'state_update') setState(msg.data)
        } catch {}
      }

      ws.onclose = () => {
        setConnected(false)
        retryTimer = setTimeout(connect, 2000)
      }

      ws.onerror = () => ws.close()
    }

    connect()
    return () => {
      clearTimeout(retryTimer)
      wsRef.current?.close()
    }
  }, [url])

  return { state, connected }
}
