export type InboxItem = { src: string; title: string; state: string; mt: number; last: string }

declare module 'claude-code' {
  interface PluginState {
    'chat-inbox': { items: Shaped<InboxItem[]> }
  }
}
