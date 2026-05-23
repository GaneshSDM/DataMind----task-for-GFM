import { useState, useEffect } from 'react'
import CRUDPage from '../components/common/CRUDPage'
import {
  getGeographies, createGeography, updateGeography, deleteGeography,
  getDomains, createDomain, updateDomain, deleteDomain,
  getSubDomains, createSubDomain, updateSubDomain, deleteSubDomain,
  getRagCategories, createRagCategory, updateRagCategory,
  getRagSubCategories, createRagSubCategory, updateRagSubCategory,
  getPgSchemas,
} from '../api/client'

export function GeographyPage() {
  return (
    <CRUDPage
      title="Geographies"
      subtitle="Manage geographic regions"
      fetchFn={getGeographies}
      createFn={createGeography}
      updateFn={updateGeography}
      deleteFn={deleteGeography}
      noDelete={true}
      getItemId={i => i.GeoID}
      getItemLabel={i => i.GeoName}
      columns={[
        { key: 'GeoID', label: '#' },
        { key: 'GeoName', label: 'Name' },
        { key: 'IsActive', label: 'Status', render: v => (
          <span className={`badge badge-${v ? 'success' : 'neutral'}`}>{v ? 'Active' : 'Inactive'}</span>
        )},
        { key: 'CreatedDate', label: 'Created', render: v => v ? new Date(v).toLocaleDateString() : '—' },
      ]}
      formFields={[
        { key: 'GeoName', label: 'Geography Name', required: true, placeholder: 'e.g. APAC' },
        { key: 'IsActive', label: 'Active', type: 'checkbox', editOnly: true },
      ]}
    />
  )
}

export function DomainPage() {
  const [schemaOptions, setSchemaOptions] = useState([])

  useEffect(() => {
    getPgSchemas()
      .then(rows => setSchemaOptions(rows))
      .catch(() => setSchemaOptions([]))
  }, [])

  return (
    <CRUDPage
      title="Domains"
      subtitle="Manage data domains"
      fetchFn={getDomains}
      createFn={createDomain}
      updateFn={updateDomain}
      deleteFn={deleteDomain}
      noDelete={true}
      getItemId={i => i.DomainID}
      getItemLabel={i => i.DomainName}
      columns={[
        { key: 'DomainID', label: '#' },
        { key: 'DomainName', label: 'Name' },
        { key: 'DbSchema', label: 'DB Schema', render: v => v
            ? <code style={{ fontSize: 11, background: 'var(--bg-subtle)', padding: '1px 5px', borderRadius: 4 }}>{v}</code>
            : <span style={{ color: 'var(--text-tertiary)', fontSize: 11 }}>—</span>
        },
        { key: 'IsActive', label: 'Status', render: v => (
          <span className={`badge badge-${v ? 'success' : 'neutral'}`}>{v ? 'Active' : 'Inactive'}</span>
        )},
        { key: 'CreatedDate', label: 'Created', render: v => v ? new Date(v).toLocaleDateString() : '—' },
      ]}
      formFields={[
        { key: 'DomainName', label: 'Domain Name', required: true, placeholder: 'e.g. Sales' },
        { key: 'DbSchema', label: 'DB Schema', type: 'select', options: schemaOptions },
        { key: 'IsActive', label: 'Active', type: 'checkbox', editOnly: true },
      ]}
    />
  )
}

export function SubDomainPage() {
  const [domainOptions, setDomainOptions] = useState([])

  useEffect(() => {
    getDomains().then(ds => setDomainOptions(ds.map(d => ({ value: d.DomainID, label: d.DomainName }))))
  }, [])

  return (
    <CRUDPage
      title="Sub-Domains"
      subtitle="Manage sub-domains and map them to domains"
      fetchFn={getSubDomains}
      createFn={createSubDomain}
      updateFn={updateSubDomain}
      deleteFn={deleteSubDomain}
      noDelete={true}
      getItemId={i => i.SubDomainID}
      getItemLabel={i => i.SubDomainName}
      columns={[
        { key: 'SubDomainID', label: '#' },
        { key: 'SubDomainName', label: 'Sub-Domain' },
        { key: 'domain_name', label: 'Domain', render: v => v || '—' },
        { key: 'IsActive', label: 'Status', render: v => (
          <span className={`badge badge-${v ? 'success' : 'neutral'}`}>{v ? 'Active' : 'Inactive'}</span>
        )},
      ]}
      formFields={[
        { key: 'DomainID', label: 'Domain', required: true, type: 'select', options: domainOptions },
        { key: 'SubDomainName', label: 'Sub-Domain Name', required: true, placeholder: 'e.g. Revenue Analytics' },
        { key: 'IsActive', label: 'Active', type: 'checkbox', editOnly: true },
      ]}
    />
  )
}


// ── RAG Category ──────────────────────────────────────────────────────────────
export function RagCategoryPage() {
  return (
    <CRUDPage
      title="RAG Categories"
      subtitle="Manage document categories for RAG pipeline"
      fetchFn={getRagCategories}
      createFn={createRagCategory}
      updateFn={updateRagCategory}
      deleteFn={null}
      noDelete={true}
      getItemId={i => i.category_id}
      getItemLabel={i => i.category_name}
      columns={[
        { key: 'category_id',   label: '#' },
        { key: 'category_name', label: 'Category' },
        { key: 'description',   label: 'Description', render: v => v || '—' },
        { key: 'is_active',     label: 'Status', render: v => (
          <span className={`badge badge-${v ? 'success' : 'neutral'}`}>{v ? 'Active' : 'Inactive'}</span>
        )},
        { key: 'created_date',  label: 'Created', render: v => v ? new Date(v).toLocaleDateString() : '—' },
      ]}
      formFields={[
        { key: 'category_name', label: 'Category Name', required: true, placeholder: 'e.g. SOPs' },
        { key: 'description',   label: 'Description', type: 'textarea', placeholder: 'Optional description' },
        { key: 'is_active',     label: 'Active', type: 'checkbox', editOnly: true },
      ]}
    />
  )
}


// ── RAG Sub-Category ──────────────────────────────────────────────────────────
export function RagSubCategoryPage() {
  return (
    <CRUDPage
      title="RAG Sub-Categories"
      subtitle="Manage document sub-categories for RAG pipeline"
      fetchFn={getRagSubCategories}
      createFn={createRagSubCategory}
      updateFn={updateRagSubCategory}
      deleteFn={null}
      noDelete={true}
      getItemId={i => i.sub_category_id}
      getItemLabel={i => i.sub_category_name}
      columns={[
        { key: 'sub_category_id',   label: '#' },
        { key: 'sub_category_name', label: 'Sub-Category' },
        { key: 'description',       label: 'Description', render: v => v || '—' },
        { key: 'is_active',         label: 'Status', render: v => (
          <span className={`badge badge-${v ? 'success' : 'neutral'}`}>{v ? 'Active' : 'Inactive'}</span>
        )},
        { key: 'created_date', label: 'Created', render: v => v ? new Date(v).toLocaleDateString() : '—' },
      ]}
      formFields={[
        { key: 'sub_category_name', label: 'Sub-Category Name', required: true, placeholder: 'e.g. Domestic_Orders' },
        { key: 'description',       label: 'Description', type: 'textarea', placeholder: 'Optional description' },
        { key: 'is_active',         label: 'Active', type: 'checkbox', editOnly: true },
      ]}
    />
  )
}
