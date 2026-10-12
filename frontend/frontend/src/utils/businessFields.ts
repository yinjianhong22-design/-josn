import type { BusinessField, Field, Template, SourceMapping } from '../types/template'
export const allAnchors = (template: Template) => template.pages.flatMap(page => [...(page.fields || []), ...(page.tables || []).flatMap(table => table.fields)])
export function syncBindings(template: Template) {
  for (const anchor of allAnchors(template)) {
    anchor.definition=template.businessFields?.find(field=>field.businessFieldUuid===anchor.businessFieldUuid)
    anchor.mapping=anchor.businessFieldUuid ? template.mappingPreview?.results[anchor.businessFieldUuid] : undefined
  }
}
export function migrateBindings(template: Template) {
  let changed=false
  template.businessFields ??= []
  const emptyIds=new Set(template.businessFields.filter(field=>!field.name.trim() && !field.mappingRule).map(field=>field.businessFieldUuid))
  if(emptyIds.size) {
    template.businessFields=template.businessFields.filter(field=>!emptyIds.has(field.businessFieldUuid))
    for(const anchor of allAnchors(template)) if(anchor.businessFieldUuid && emptyIds.has(anchor.businessFieldUuid)) { delete anchor.businessFieldUuid;delete anchor.definition }
    for(const id of emptyIds) if(template.mappingPreview) delete template.mappingPreview.results[id]
    changed=true
  }
  for (const anchor of allAnchors(template)) if (!anchor.businessFieldUuid && anchor.definition?.name.trim()) {
    const field: BusinessField={...anchor.definition,businessFieldUuid:'biz_'+crypto.randomUUID().replaceAll('-','')}
    anchor.businessFieldUuid=field.businessFieldUuid;template.businessFields.push(field);changed=true
    if(anchor.mapping) {
      template.mappingPreview ??= {sampleId:anchor.mapping.sampleId,results:{}}
      template.mappingPreview.results[field.businessFieldUuid]=anchor.mapping
    }
  }
  for(const field of template.businessFields) {
    const preview=template.mappingPreview?.results[field.businessFieldUuid]
    if(!field.mappingRule && preview?.confirmed && preview.proposedRule) { field.mappingRule=JSON.parse(JSON.stringify(preview.proposedRule));changed=true }
  }
  if(template.mappingScheme || template.mappingPreview)changed=true
  delete template.mappingScheme;delete template.mappingPreview
  syncBindings(template)
  return changed
}
export function setPreview(template: Template, anchor: Field, mapping: SourceMapping) {
  if (!anchor.businessFieldUuid) return
  if (template.mappingPreview?.sampleId !== mapping.sampleId) template.mappingPreview={sampleId:mapping.sampleId,results:{}}
  template.mappingPreview!.results[anchor.businessFieldUuid]=mapping
  syncBindings(template)
}
export function templateForSave(template: Template): Template {
  const copy=JSON.parse(JSON.stringify(template)) as Template
  delete copy.mappingScheme;delete copy.mappingPreview
  for(const anchor of allAnchors(copy)) {
    delete anchor.definition;delete anchor.mapping
    const borders=anchor.style?.borders
    if(borders) {
      const presets: Record<string,number>={hair:.25,thin:.75,medium:1.5,thick:2.25,double:2.25,single:.75,solid:.75,dashed:.75,dotted:.75}
      const widths=Object.fromEntries(Object.entries(borders).flatMap(([side,border])=>{
        const width=border?.widthPt ?? presets[border?.style || '']
        return width!=null && width>0 ? [[side,{widthPt:width}]] : []
      }))
      if(Object.keys(widths).length)anchor.style!.borders=widths
      else delete anchor.style!.borders
    }
  }
  return copy
}
