export interface Notification {
  id: string
  user_id: string
  channel: string
  title: string
  content: string
  is_read: boolean
  created_at: string
}
