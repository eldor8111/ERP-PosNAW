// T1.1: Global joriy filial konteksti.
// Login'dan keyin GET /branches/my-context chaqiriladi; tanlangan filial
// localStorage['current_branch_id'] da saqlanadi va axios X-Branch-Id header'ini boshqaradi.
import { createContext, useContext, useState, useEffect, useMemo, useCallback } from 'react'
import api, { clearCache, getCurrentBranchId, setCurrentBranchId as setAxiosBranchId } from '../api/axios'
import { useAuth } from './AuthContext'

const BranchContext = createContext(null)

const EMPTY = {
  currentBranchId: null,   // null = barcha filiallar
  assignedBranchId: null,
  branches: [],
  canSwitch: false,
  canSelectAll: false,
  needsAssignment: false,
  defaultWarehouseId: null,   // T1.5: joriy (yoki biriktirilgan) filialning asosiy savdo ombori
  loaded: false,
  version: 0,
  setBranch: () => {},
}

export function BranchProvider({ children }) {
  const { user } = useAuth()
  const [state, setState] = useState(() => ({ ...EMPTY, currentBranchId: getCurrentBranchId() }))

  // Foydalanuvchi (yoki korxona) o'zgarganda kontekstni serverdan yuklaymiz
  useEffect(() => {
    if (!user) {
      setAxiosBranchId(null)
      setState(s => ({ ...EMPTY, version: s.version }))
      return
    }
    let alive = true
    // Header'siz so'raymiz: eski (boshqa korxona) saqlangan filial 404 bermasin
    api.get('/branches/my-context', { _noCache: true, _noBranch: true })
      .then(r => {
        if (!alive) return
        const d = r.data || {}
        const branches = d.branches || []
        const stored = getCurrentBranchId()
        let current = d.current_branch_id ?? null
        if (d.can_switch && stored && branches.some(b => b.id === stored)) {
          current = stored   // oldin tanlangan filial hali ham mavjud
        }
        setAxiosBranchId(current)
        setState(s => ({
          ...s,
          currentBranchId: current,
          assignedBranchId: d.assigned_branch_id ?? null,
          branches,
          canSwitch: !!d.can_switch,
          canSelectAll: !!d.can_select_all,
          needsAssignment: !!d.needs_branch_assignment,
          loaded: true,
        }))
      })
      .catch(() => {
        if (!alive) return
        setState(s => ({ ...s, loaded: true }))
      })
    return () => { alive = false }
  }, [user?.id, user?.company_id])

  const setBranch = useCallback((id) => {
    const next = id ? Number(id) || null : null
    setAxiosBranchId(next)   // header + localStorage
    clearCache()             // eski filial keshi ko'rinmasin
    setState(s => ({ ...s, currentBranchId: next, version: s.version + 1 }))
  }, [])

  // T1.5: joriy filialning default ombori (`/branches/my-context` -> branches[].default_warehouse_id);
  // "barcha filiallar" rejimida biriktirilgan filial ombori. Server bermasa — null (backend o'zi tanlaydi).
  const defaultWarehouseId = useMemo(() => {
    const bid = state.currentBranchId ?? state.assignedBranchId
    const b = state.branches.find(x => x.id === bid)
    return b?.default_warehouse_id ?? null
  }, [state.currentBranchId, state.assignedBranchId, state.branches])

  const value = useMemo(() => ({ ...state, defaultWarehouseId, setBranch }), [state, defaultWarehouseId, setBranch])

  return (
    <BranchContext.Provider value={value}>
      {children}
    </BranchContext.Provider>
  )
}

// Provider'siz (masalan, alohida sahifalar) xavfsiz standart qiymat qaytaradi
// eslint-disable-next-line react-refresh/only-export-components
export const useBranch = () => useContext(BranchContext) || EMPTY
