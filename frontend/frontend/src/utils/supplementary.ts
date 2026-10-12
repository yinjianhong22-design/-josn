import type { Field, Page, SupplementaryRegion, SupplementaryRole } from '../types/template'
const roles: SupplementaryRole[] = ['name','requirement','measurement','rate']
const key = (text: string) => text.normalize('NFKC').replace(/[\s:：△Δ□_]/g,'').replace(/\([^)]*\)/g,'')
function role(text: string): SupplementaryRole | undefined {
  const name=key(text)
  if(['抽检项目','检验项目','检测项目','检查项目'].includes(name))return 'name'
  if(['规定值或允许偏差','规定值','允许偏差','标准值'].includes(name))return 'requirement'
  if(['实测值','实测值或实测偏差值','实测值或实测偏差','实测偏差值','实测结果','测量值'].includes(name))return 'measurement'
  if(['合格率','合格率百分比'].includes(name))return 'rate'
}
export function regionFieldIds(region?: SupplementaryRegion) { return new Set(region?.rows.flatMap(row=>Object.values(row).flat()) || []) }
export function buildSupplementaryRegion(page: Page, selected: Field[]): { region?: SupplementaryRegion; error?: string } {
  if(selected.length<2)return {error:'按住 Shift 选择补充区域左上角和右下角的格子'}
  const all=[...(page.fields || []),...(page.tables || []).flatMap(t=>t.fields)]
  const x=Math.min(...selected.map(f=>f.rect.x)), y=Math.min(...selected.map(f=>f.rect.y))
  const right=Math.max(...selected.map(f=>f.rect.x+f.rect.w)),bottom=Math.max(...selected.map(f=>f.rect.y+f.rect.h))
  const inside=all.filter(f=>f.rect.x>=x-.002 && f.rect.y>=y-.002 && f.rect.x+f.rect.w<=right+.002 && f.rect.y+f.rect.h<=bottom+.002)
  if(inside.some(f=>f.businessFieldUuid || (f.textOverride ?? f.label ?? '').trim()))return {error:'请选择未绑定字段的完整空白行'}
  const headers=all.filter(f=>f.rect.y+f.rect.h<=y+.002 && f.rect.x>=x-.002 && f.rect.x+f.rect.w<=right+.002 && role(f.label || '')==='name').sort((a,b)=>b.rect.y-a.rect.y)
  const header=headers[0]
  if(!header)return {error:'选区需要包含完整四列，并位于检测项目表头下方'}
  const columns: Partial<Record<SupplementaryRole,Field>>={}
  for(const f of all) {
    const r=role(f.label || '')
    if(r && Math.abs(f.rect.y-header.rect.y)<.003 && f.rect.x>=x-.002 && f.rect.x+f.rect.w<=right+.002)columns[r]=f
  }
  if(!roles.every(r=>columns[r]))return {error:'未识别出完整四列表头，请检查选区和表头文字'}
  const names=inside.filter(f=>Math.abs(f.rect.x-columns.name!.rect.x)<.003 && Math.abs(f.rect.w-columns.name!.rect.w)<.003).sort((a,b)=>a.rect.y-b.rect.y)
  if(!names.length)return {error:'未找到完整预留行'}
  const rows: SupplementaryRegion['rows']=[]
  for(const name of names) {
    const row={} as Record<SupplementaryRole,string[]>
    for(const r of roles) {
      const c=columns[r]!.rect
      const cells=inside.filter(f=>f.rect.x>=c.x-.002 && f.rect.x+f.rect.w<=c.x+c.w+.002 && f.rect.y>=name.rect.y-.002 && f.rect.y+f.rect.h<=name.rect.y+name.rect.h+.002).sort((a,b)=>Math.abs(a.rect.y-b.rect.y)<.002 ? a.rect.x-b.rect.x : a.rect.y-b.rect.y)
      if(!cells.length)return {error:'选区缺少完整列，请选择每行的全部格子'}
      const area=cells.reduce((sum,f)=>sum+f.rect.w*f.rect.h,0)
      if(Math.abs(area-c.w*name.rect.h)>c.w*name.rect.h*.04)return {error:'选区有缺格或重复区域，请先修正区域结构'}
      row[r]=cells.map(f=>f.fieldUuid)
    }
    rows.push(row)
  }
  if(Math.abs(names[0]!.rect.y-y)>.003 || Math.abs(names.at(-1)!.rect.y+names.at(-1)!.rect.h-bottom)>.003 || names.some((f,i)=>i>0 && Math.abs(f.rect.y-names[i-1]!.rect.y-names[i-1]!.rect.h)>.003))return {error:'请选择连续的完整空白行'}
  return {region:{rows}}
}

export function appendSupplementaryRows(page: Page, incoming: SupplementaryRegion): {region?: SupplementaryRegion; error?: string} {
  const existing=page.supplementaryRegion
  if(!existing)return {region:incoming}
  const all=[...(page.fields || []),...(page.tables || []).flatMap(t=>t.fields)]
  const anchors=new Map(all.map(f=>[f.fieldUuid,f]))
  const used=regionFieldIds(existing)
  const newRows=incoming.rows.filter(row=>!Object.values(row).flat().every(id=>used.has(id)))
  if(!newRows.length)return {error:'所选预留行已设置'}
  if(newRows.some(row=>Object.values(row).flat().some(id=>used.has(id))))return {error:'选区与已有预留行重叠，请选择完整空白行'}
  const bounds=(row: SupplementaryRegion['rows'][number],role: SupplementaryRole) => {
    const cells=row[role].map(id=>anchors.get(id)!).filter(Boolean)
    return {left:Math.min(...cells.map(f=>f.rect.x)),right:Math.max(...cells.map(f=>f.rect.x+f.rect.w))}
  }
  const first=existing.rows[0]!
  if(newRows.some(row=>roles.some(role=>{
    const a=bounds(first,role),b=bounds(row,role)
    return Math.abs(a.left-b.left)>.003 || Math.abs(a.right-b.right)>.003
  })))return {error:'追加的预留行需要使用同一检测表的四列'}
  const rows=[...existing.rows,...newRows].sort((a,b)=>anchors.get(a.name[0]!)!.rect.y-anchors.get(b.name[0]!)!.rect.y)
  if(rows.length>100)return {error:'预留行数量不能超过 100'}
  return {region:{rows}}
}
