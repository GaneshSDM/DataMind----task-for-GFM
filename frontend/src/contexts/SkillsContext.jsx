import { createContext, useContext, useState } from 'react'

// ── Seed data ──────────────────────────────────────────────────────────────────
const SEED_SKILLS = [
  {
    id: 1,
    name: 'commission_calculator',
    type: 'template',
    description: 'Calculate sales representative commission based on region and quarter',
    domain: 'Sales',
    sql: `SELECT
  sp.rep_name,
  SUM(fo.revenue_usd)                          AS total_revenue,
  SUM(fo.revenue_usd) * {{commission_rate}}    AS commission_amount
FROM sales.fact_orders fo
JOIN sales.dim_salesperson sp ON fo.salesperson_id = sp.salesperson_id
WHERE fo.region   = '{{region}}'
  AND fo.quarter  = '{{quarter}}'
GROUP BY sp.rep_name
ORDER BY commission_amount DESC`,
    parameters: [
      { id: 'p1', name: 'region',          label: 'Region',          type: 'text',    required: true,  example: 'India'   },
      { id: 'p2', name: 'quarter',         label: 'Quarter',         type: 'text',    required: true,  example: 'Q1-2025' },
      { id: 'p3', name: 'commission_rate', label: 'Commission Rate', type: 'numeric', required: false, example: '0.05'    },
    ],
    is_active: true,
    created_by: 'admin@slm.local',
  },
  {
    id: 2,
    name: 'monthly_revenue_view',
    type: 'view',
    description: 'Aggregated monthly revenue by product category and geography — pre-computed DB view',
    domain: 'Sales',
    sql: `CREATE OR REPLACE VIEW sales.v_monthly_revenue AS
SELECT
  DATE_TRUNC('month', order_date)  AS month,
  product_category,
  country,
  SUM(revenue_usd)                 AS total_revenue,
  COUNT(DISTINCT order_id)         AS order_count
FROM sales.fact_orders
GROUP BY 1, 2, 3`,
    parameters: [],
    is_active: true,
    created_by: 'admin@slm.local',
  },
  {
    id: 3,
    name: 'forecast_gap',
    type: 'template',
    description: 'Compare actual vs forecast sales for a date range and show gap analysis by product category',
    domain: 'Sales',
    sql: `SELECT
  fo.product_category,
  SUM(fo.revenue_usd)                                                         AS actual_revenue,
  SUM(ff.forecast_amount)                                                     AS forecasted_revenue,
  SUM(fo.revenue_usd) - SUM(ff.forecast_amount)                              AS gap,
  ROUND(
    (SUM(fo.revenue_usd) / NULLIF(SUM(ff.forecast_amount), 0) - 1) * 100, 2
  )                                                                           AS gap_pct
FROM sales.fact_orders fo
LEFT JOIN sales.fact_forecast ff
  ON fo.product_category = ff.product_category
 AND DATE_TRUNC('month', fo.order_date) = ff.forecast_month
WHERE DATE_TRUNC('month', fo.order_date)
      BETWEEN '{{start_date}}' AND '{{end_date}}'
GROUP BY fo.product_category
ORDER BY gap ASC`,
    parameters: [
      { id: 'p1', name: 'start_date', label: 'Start Date', type: 'date', required: true, example: '2025-01-01' },
      { id: 'p2', name: 'end_date',   label: 'End Date',   type: 'date', required: true, example: '2025-03-31' },
    ],
    is_active: false,
    created_by: 'admin@slm.local',
  },
]

// ── Context ────────────────────────────────────────────────────────────────────
const SkillsContext = createContext(null)

export function SkillsProvider({ children }) {
  const [skills, setSkills] = useState(SEED_SKILLS)

  const addSkill = skill => {
    const id = Date.now()
    setSkills(prev => [...prev, { ...skill, id, created_by: 'admin@slm.local' }])
    return id
  }

  const updateSkill = (id, updates) =>
    setSkills(prev => prev.map(s => s.id === id ? { ...s, ...updates } : s))

  const deleteSkill = id =>
    setSkills(prev => prev.filter(s => s.id !== id))

  const toggleSkill = id =>
    setSkills(prev => prev.map(s => s.id === id ? { ...s, is_active: !s.is_active } : s))

  return (
    <SkillsContext.Provider value={{ skills, addSkill, updateSkill, deleteSkill, toggleSkill }}>
      {children}
    </SkillsContext.Provider>
  )
}

export function useSkills() {
  const ctx = useContext(SkillsContext)
  if (!ctx) throw new Error('useSkills must be used within SkillsProvider')
  return ctx
}
