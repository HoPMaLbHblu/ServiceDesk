import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import type { Role } from '@/api/types'
import { useSessionStore } from '@/stores/session'

declare module 'vue-router' {
  interface RouteMeta {
    /** Reachable without signing in (auth pages, public approval links). */
    public?: boolean
    /** Only for signed-out visitors; signed-in users are sent home. */
    guestOnly?: boolean
    /** Needs an active workspace membership. */
    workspace?: boolean
    /** Roles allowed in the active workspace. Omitted means every staff role. */
    roles?: Role[]
    /** Customer portal pages. */
    portal?: boolean
    title?: string
  }
}

const MANAGERS: Role[] = ['owner', 'manager']
const OWNER: Role[] = ['owner']

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: () => import('@/layouts/AuthLayout.vue'),
    children: [
      { path: 'login', name: 'login', component: () => import('@/views/auth/LoginView.vue'), meta: { public: true, guestOnly: true, title: 'Sign in' } },
      { path: 'register', name: 'register', component: () => import('@/views/auth/RegisterView.vue'), meta: { public: true, guestOnly: true, title: 'Create account' } },
      { path: 'forgot-password', name: 'forgot-password', component: () => import('@/views/auth/ForgotPasswordView.vue'), meta: { public: true, title: 'Reset password' } },
      { path: 'reset-password', name: 'reset-password', component: () => import('@/views/auth/ResetPasswordView.vue'), meta: { public: true, title: 'Choose a new password' } },
      { path: 'verify-email', name: 'verify-email', component: () => import('@/views/auth/VerifyEmailView.vue'), meta: { public: true, title: 'Verify email' } },
      { path: 'invitations/accept', name: 'accept-invitation', component: () => import('@/views/auth/AcceptInvitationView.vue'), meta: { public: true, title: 'Join workspace' } },
      { path: 'portal/accept', name: 'portal-accept', component: () => import('@/views/portal/PortalAcceptView.vue'), meta: { public: true, title: 'Customer portal access' } },
      { path: 'approve/:token', name: 'public-approval', component: () => import('@/views/public/ApprovalView.vue'), meta: { public: true, title: 'Review estimate' }, props: true },
      { path: 'welcome', name: 'welcome', component: () => import('@/views/onboarding/WelcomeView.vue'), meta: { title: 'Get started' } },
    ],
  },
  {
    path: '/portal',
    component: () => import('@/layouts/PortalLayout.vue'),
    meta: { portal: true },
    children: [
      { path: '', name: 'portal', component: () => import('@/views/portal/PortalHomeView.vue'), meta: { portal: true, title: 'My repairs' } },
      { path: 'orders/:id', name: 'portal-order', component: () => import('@/views/portal/PortalOrderView.vue'), meta: { portal: true, title: 'Repair' }, props: true },
    ],
  },
  {
    path: '/',
    component: () => import('@/layouts/AppLayout.vue'),
    meta: { workspace: true },
    children: [
      { path: '', name: 'dashboard', component: () => import('@/views/DashboardView.vue'), meta: { workspace: true, title: 'Today' } },
      { path: 'orders', name: 'orders', component: () => import('@/views/orders/OrdersListView.vue'), meta: { workspace: true, title: 'Repair orders' } },
      { path: 'orders/new', name: 'order-new', component: () => import('@/views/orders/OrderCreateView.vue'), meta: { workspace: true, roles: MANAGERS, title: 'New repair order' } },
      { path: 'orders/:id', name: 'order', component: () => import('@/views/orders/OrderDetailView.vue'), meta: { workspace: true, title: 'Repair order' }, props: true },
      { path: 'customers', name: 'customers', component: () => import('@/views/customers/CustomersListView.vue'), meta: { workspace: true, title: 'Customers' } },
      { path: 'customers/:id', name: 'customer', component: () => import('@/views/customers/CustomerDetailView.vue'), meta: { workspace: true, title: 'Customer' }, props: true },
      { path: 'appointments', name: 'appointments', component: () => import('@/views/appointments/AppointmentsView.vue'), meta: { workspace: true, title: 'Appointments' } },
      { path: 'inventory', name: 'inventory', component: () => import('@/views/inventory/PartsListView.vue'), meta: { workspace: true, title: 'Inventory' } },
      { path: 'inventory/:id', name: 'part', component: () => import('@/views/inventory/PartDetailView.vue'), meta: { workspace: true, title: 'Part' }, props: true },
      { path: 'invoices', name: 'invoices', component: () => import('@/views/invoices/InvoicesListView.vue'), meta: { workspace: true, roles: MANAGERS, title: 'Invoices' } },
      { path: 'invoices/:id', name: 'invoice', component: () => import('@/views/invoices/InvoiceDetailView.vue'), meta: { workspace: true, roles: MANAGERS, title: 'Invoice' }, props: true },
      { path: 'reports', name: 'reports', component: () => import('@/views/reports/ReportsView.vue'), meta: { workspace: true, roles: OWNER, title: 'Reports' } },
      {
        path: 'settings',
        component: () => import('@/views/settings/SettingsLayout.vue'),
        meta: { workspace: true },
        children: [
          { path: '', name: 'settings', redirect: { name: 'settings-account' } },
          { path: 'account', name: 'settings-account', component: () => import('@/views/settings/AccountSettings.vue'), meta: { workspace: true, title: 'Account' } },
          { path: 'business', name: 'settings-business', component: () => import('@/views/settings/BusinessSettings.vue'), meta: { workspace: true, roles: OWNER, title: 'Business' } },
          { path: 'team', name: 'settings-team', component: () => import('@/views/settings/TeamSettings.vue'), meta: { workspace: true, roles: OWNER, title: 'Team' } },
          { path: 'schedule', name: 'settings-schedule', component: () => import('@/views/settings/ScheduleSettings.vue'), meta: { workspace: true, roles: MANAGERS, title: 'Working hours' } },
          { path: 'billing', name: 'settings-billing', component: () => import('@/views/settings/BillingSettings.vue'), meta: { workspace: true, title: 'Billing' } },
          { path: 'billing/dev-checkout', name: 'dev-checkout', component: () => import('@/views/settings/DevCheckoutView.vue'), meta: { workspace: true, roles: OWNER, title: 'Development checkout' } },
          { path: 'notifications', name: 'settings-notifications', component: () => import('@/views/settings/NotificationsView.vue'), meta: { workspace: true, roles: MANAGERS, title: 'Email outbox' } },
          { path: 'audit', name: 'settings-audit', component: () => import('@/views/settings/AuditLogView.vue'), meta: { workspace: true, roles: OWNER, title: 'Audit log' } },
        ],
      },
      { path: 'forbidden', name: 'forbidden', component: () => import('@/views/ForbiddenView.vue'), meta: { workspace: true, title: 'No access' } },
    ],
  },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('@/views/NotFoundView.vue'), meta: { public: true, title: 'Not found' } },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: (_to, _from, saved) => saved ?? { top: 0 },
})

/** Where a signed-in user belongs when no specific page was requested. */
export function homeFor(session: ReturnType<typeof useSessionStore>) {
  if (session.workspace) return { name: 'dashboard' }
  if (session.hasPortal && !session.memberships.length) return { name: 'portal' }
  return { name: 'welcome' }
}

router.beforeEach(async (to) => {
  const session = useSessionStore()
  if (!session.restored) {
    try {
      await session.restore()
    } catch {
      // The API is unreachable; public pages still render and protected ones go to login.
    }
  }

  if (to.meta.public) {
    if (to.meta.guestOnly && session.isAuthenticated) {
      const next = typeof to.query.next === 'string' && to.query.next.startsWith('/') ? to.query.next : null
      return next ?? homeFor(session)
    }
    return true
  }
  if (!session.isAuthenticated) {
    return { name: 'login', query: to.fullPath === '/' ? {} : { next: to.fullPath } }
  }
  if (to.meta.portal) {
    return session.hasPortal ? true : homeFor(session)
  }
  if (to.meta.workspace) {
    if (!session.workspace) return session.hasPortal && !session.memberships.length ? { name: 'portal' } : { name: 'welcome' }
    const roles = to.meta.roles
    if (roles && !roles.includes(session.role as Role)) return { name: 'forbidden' }
  }
  return true
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · ServiceDesk` : 'ServiceDesk'
})
