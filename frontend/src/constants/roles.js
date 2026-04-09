export const ROLES = {
  SUPER_ADMIN: 'super_admin',
  ADMIN: 'admin',
  DIRECTOR: 'director',
  MANAGER: 'manager',
  ACCOUNTANT: 'accountant',
  WAREHOUSE: 'warehouse',
  CASHIER: 'cashier',
}

export const ROLE_GROUPS = {
  // Admin panelga kirish huquqi bor barcha rollar
  ALL_STAFF: [
    ROLES.SUPER_ADMIN, ROLES.ADMIN, ROLES.DIRECTOR,
    ROLES.MANAGER, ROLES.ACCOUNTANT, ROLES.WAREHOUSE, ROLES.CASHIER,
  ],
  // POS kassaga kirish
  POS_ACCESS: [ROLES.ADMIN, ROLES.DIRECTOR, ROLES.MANAGER, ROLES.CASHIER],
  // Faqat yuqori boshqaruv
  MANAGEMENT: [ROLES.ADMIN, ROLES.DIRECTOR],
  // Savdo va mijozlar
  SALES: [ROLES.ADMIN, ROLES.DIRECTOR, ROLES.MANAGER, ROLES.CASHIER],
  // Ombor boshqaruvi
  WAREHOUSE_ACCESS: [ROLES.ADMIN, ROLES.DIRECTOR, ROLES.MANAGER, ROLES.WAREHOUSE],
  // Moliya va buxgalteriya
  FINANCE_ACCESS: [ROLES.ADMIN, ROLES.DIRECTOR, ROLES.ACCOUNTANT],
  // Hisobotlar
  REPORTS_ACCESS: [ROLES.ADMIN, ROLES.DIRECTOR, ROLES.MANAGER, ROLES.ACCOUNTANT],
  // Omborxona + buxgalter
  OPS_ACCESS: [ROLES.ADMIN, ROLES.DIRECTOR, ROLES.MANAGER, ROLES.WAREHOUSE, ROLES.ACCOUNTANT],
}

export const ROLE_LABELS = {
  [ROLES.SUPER_ADMIN]: 'Super Admin',
  [ROLES.ADMIN]: 'Admin',
  [ROLES.DIRECTOR]: 'Direktor',
  [ROLES.MANAGER]: 'Menejer',
  [ROLES.ACCOUNTANT]: 'Buxgalter',
  [ROLES.WAREHOUSE]: 'Omborchi',
  [ROLES.CASHIER]: 'Kassir',
}

export const ROLE_GRADIENTS = {
  [ROLES.SUPER_ADMIN]: 'from-purple-500 to-purple-700',
  [ROLES.ADMIN]: 'from-red-500 to-red-700',
  [ROLES.DIRECTOR]: 'from-indigo-500 to-indigo-700',
  [ROLES.MANAGER]: 'from-blue-500 to-blue-700',
  [ROLES.ACCOUNTANT]: 'from-green-500 to-green-700',
  [ROLES.WAREHOUSE]: 'from-yellow-500 to-yellow-700',
  [ROLES.CASHIER]: 'from-cyan-500 to-cyan-700',
}
