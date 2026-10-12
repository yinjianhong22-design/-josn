import type { Template, TemplateSummary, Page, SampleResult, SourceMapping, FieldDefinition, Rect, SupplementaryResult, SupplementaryRole } from '../types/template'

const base = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
export const imageUrl = (path: string) => new URL(path, base).href

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, options)
  const data = await response.json()
  if (!response.ok) throw new Error(data.detail || '请求失败，请稍后重试')
  return data
}

export const listTemplates = () => request<TemplateSummary[]>('/templates')
export const loadTemplate = (id: string) => request<{ template: Template }>(`/templates/${id}`)
export const saveTemplate = (template: Template) => request(`/templates/${template.templateUuid}/save`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(template),
})
export function uploadTemplate(file: File) {
  const body = new FormData()
  body.append('file', file)
  return request<{ template: Template }>('/upload', { method: 'POST', body })
}

export function recognizeSample(file: File, page: Page) {
  const body = new FormData(); body.append('file', file); body.append('page', JSON.stringify(page))
  return request<{sampleId:string}>('/samples/recognize', {method:'POST',body})
}
export const getSample = (id: string) => request<{state:string; result?:SampleResult; error?:string}>(`/samples/${id}`)
export const selectSample = (id: string, definition: FieldDefinition, selection: {rect?:Rect; textIds?:string[]}, knownLabels: string[] = []) => request<SourceMapping>(`/samples/${id}/select`, {method:'POST', headers:{'Content-Type':'application/json'},body:JSON.stringify({definition,...selection,knownLabels})})

export const matchSample = (id: string, page: Page, corrections?:Record<string,Partial<Record<SupplementaryRole,string>>>) => request<{suggestions:Record<string,SourceMapping>;supplementary?:SupplementaryResult | null;source?:Pick<SampleResult,'tables' | 'textItems'>}>(`/samples/${id}/match`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...page,supplementaryCorrections:corrections})})

export const deleteTemplate = (id: string) => request(`/templates/${id}`, {method:'DELETE'})

export const correctSample = (id: string, definition: FieldDefinition, mapping: SourceMapping, text: string) => request<SourceMapping>(`/samples/${id}/correct`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({definition,rect:mapping.sourceRect,textIds:mapping.textIds.length ? mapping.textIds : undefined,text})})
