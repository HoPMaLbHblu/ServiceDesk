import type { components } from './schema'

type S = components['schemas']

export type Session = S['Session']
export type User = S['User']
export type ActiveWorkspace = S['ActiveWorkspace']
export type MembershipSummary = S['MembershipSummary']
export type Business = S['Business']
export type BusinessHours = S['BusinessHours']
export type Member = S['Member']
export type StaffOption = S['StaffOption']
export type Invitation = S['Invitation']
export type Customer = S['Customer']
export type CustomerNote = S['CustomerNote']
export type Device = S['Device']
export type PortalAccess = S['PortalAccess']
export type OrderList = S['OrderList']
export type OrderDetail = S['OrderDetail']
export type OrderEvent = S['OrderEvent']
export type Attachment = S['Attachment']
export type Estimate = S['Estimate']
export type EstimateLine = S['EstimateLine']
export type LineInput = S['LineInputRequest']
export type PublicEstimate = S['PublicEstimate']
export type InvoiceList = S['InvoiceList']
export type InvoiceDetail = S['InvoiceDetail']
export type Payment = S['Payment']
export type Appointment = S['Appointment']
export type TechnicianAvailability = S['TechnicianAvailability']
export type TimeOff = S['TimeOff']
export type Part = S['Part']
export type StockMovement = S['StockMovement']
export type Reservation = S['Reservation']
export type Notification = S['Notification']
export type AuditLog = S['AuditLog']
export type SubscriptionState = S['SubscriptionState']
export type Plan = S['Plan']
export type PortalCustomer = S['PortalCustomer']
export type PortalOrder = S['PortalOrder']
export type PortalOrderDetail = S['PortalOrderDetail']
export type PortalAppointment = S['PortalAppointment']

export type OrderStatus = S['OrderStatusEnum']
export type Role = 'owner' | 'manager' | 'technician'

export interface Paginated<T> {
  count: number
  page: number
  page_size: number
  total_pages: number
  results: T[]
}

// Shapes the backend returns as free-form objects (documented in the API, not typed by the schema).
export interface PortalDevice {
  id: string
  label: string
}

export interface PortalEvent {
  kind: string
  message: string
  created_at: string
}

export interface PortalAttachment {
  id: string
  original_name: string
  content_type: string
  caption: string
  created_at: string
}

export interface PublicEstimateLine {
  kind: string
  description: string
  quantity: string
  unit_price: string
  line_total: string
  taxable: boolean
}

export interface PortalInvoice {
  id: string
  reference: string
  currency: string
  total: string
  amount_paid: string
  balance_due: string
  issued_at: string
  due_date: string | null
}

export interface DashboardReport {
  period: { start: string; end: string; timezone: string }
  currency: string
  collected: { gross: string; refunds: string; net: string; series: { date: string; amount: string }[] }
  outstanding: { balance: string; count: number; overdue_balance: string; overdue_count: number }
  orders_by_status: { status: string; label: string; count: number }[]
  turnaround: { count: number; average_hours: number | null; median_hours: number | null }
  technician_workload: {
    user_id: string
    name: string
    role: string
    open_orders: number
    completed_in_period: number
    booked_hours_next_7_days: number
  }[]
  top_parts: { part_id: string; sku: string; name: string; quantity_used: string; orders: number }[]
  low_stock: { part_id: string; sku: string; name: string; available: string; threshold: string }[]
  definitions: Record<string, string>
}
