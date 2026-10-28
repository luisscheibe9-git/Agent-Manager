import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { InboxItem } from '../types'

const PANE = 'chat-inbox'
const PY = 'C:/Users/lscheibe/AppData/Local/Programs/Python/Python313/python.exe'
const SCRIPT = 'C:/Users/lscheibe/Desktop/Chat_Inbox/inbox.py'
const items = atom({ plugin: 'chat-inbox', key: 'items' } as const, [], {
  shape: 'items-1',
})

async function refresh($: any, markAll = false) {
  const args = [PY, SCRIPT, '--json', ...(markAll ? ['--mark-all'] : [])]
  const { exitCode, stdout } = await $.process.run(args, { timeoutMs: 60000 })
  if (exitCode === 0) {
    await update($, items, () => JSON.parse(stdout) as InboxItem[])
  }
}

const clean = (t: string) => t.replace(/[\x00-\x1f\x7f-\x9f]+/g, ' ')

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'inbox',
      description: 'Show finished, unread Claude and Codex chats',
    })
    await $.command.register({
      name: 'inbox-clear',
      description: 'Mark all chats in the inbox as read',
    })
    void $.ui.open({ id: PANE, title: 'Chat inbox' })
    void refresh($)
    $.clock.every(30000, () => refresh($))

    return next(e)
  })

  on('command.run', { command: 'inbox' }, async $ => {
    await $.ui.open({ id: PANE, title: 'Chat inbox' })
    await refresh($)

    return { text: 'Chat inbox opened.' }
  })

  on('command.run', { command: 'inbox-clear' }, async $ => {
    await refresh($, true)

    return { text: 'Inbox cleared.' }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const list = await read($, items)
    const unread = list.filter(i => i.state === 'unread')
    const working = list.filter(i => i.state === 'working')

    return (
      <Box flexDirection="column">
        <Text bold>{unread.length} unread, {working.length} working</Text>
        {list.length === 0 && <Text dimColor>All caught up. /inbox-clear marks read.</Text>}
        {list.slice(0, 15).map(i => (
          <Box flexDirection="column" marginTop={1}>
            <Text bold={i.state === 'unread'}>
              {i.state === 'unread' ? '● ' : '… '}[{i.src}] {clean(i.title)}
            </Text>
            <Text dimColor>{clean(i.last).replace(/\s+/g, ' ').slice(0, 160)}</Text>
          </Box>
        ))}
      </Box>
    )
  })
}
