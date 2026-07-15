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
