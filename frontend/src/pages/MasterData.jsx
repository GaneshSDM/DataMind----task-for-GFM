import { useState, useEffect } from 'react'
import CRUDPage from '../components/common/CRUDPage'
import {
  getGeographies, createGeography, updateGeography, deleteGeography,
  getDomains, createDomain, updateDomain, deleteDomain,
  getSubDomains, createSubDomain, updateSubDomain, deleteSubDomain,
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
        { key: 'IsActive', label: 'Status', render: v => (
          <span className={`badge badge-${v ? 'success' : 'neutral'}`}>{v ? 'Active' : 'Inactive'}</span>
        )},
        { key: 'CreatedDate', label: 'Created', render: v => v ? new Date(v).toLocaleDateString() : '—' },
      ]}
      formFields={[
        { key: 'DomainName', label: 'Domain Name', required: true, placeholder: 'e.g. Sales' },
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
