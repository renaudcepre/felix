export interface SSEEvent {
  event: string
  data: string
}

export async function* parseSSEStream(
  response: Response,
): AsyncGenerator<SSEEvent> {
  const reader = response.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let currentEvent = ''
  let currentData = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      for (const rawLine of lines) {
        const line = rawLine.replace(/\r$/, '')
        if (line.startsWith('event:')) {
          currentEvent = line.slice(6).trim()
        }
        else if (line.startsWith('data:')) {
          const value = line.startsWith('data: ') ? line.slice(6) : line.slice(5)
          // SSE spec: multiple data lines are concatenated with \n
          currentData = currentData ? `${currentData}\n${value}` : value
        }
        else if (line === '') {
          if (currentEvent || currentData) {
            yield { event: currentEvent || 'message', data: currentData }
            currentEvent = ''
            currentData = ''
          }
        }
      }
    }
    // Flush remaining
    if (currentEvent || currentData) {
      yield { event: currentEvent || 'message', data: currentData }
    }
  }
  finally {
    reader.releaseLock()
  }
}
