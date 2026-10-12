import type { Field, TextRange } from '../types/template'

export function normalizeRanges(ranges: TextRange[], length: number): TextRange[] {
  const result: TextRange[] = []
  for (const range of ranges.map(r => ({ start: Math.max(0, r.start), end: Math.min(length, r.end) })).filter(r => r.end > r.start).sort((a,b) => a.start-b.start)) {
    const last=result.at(-1)
    if(last && range.start<=last.end)last.end=Math.max(last.end,range.end)
    else result.push({...range})
  }
  return result
}
export function underlineRanges(field: Field, text=field.textOverride ?? field.label ?? ''): TextRange[] {
  return normalizeRanges(field.underlineRanges ?? (field.style?.underline && !['none','nil'].includes(field.style.underline) ? [{start:0,end:text.length}] : []),text.length)
}
export function rangeUnderlined(ranges: TextRange[], start: number, end: number) {
  return end>start && ranges.some(r => r.start<=start && r.end>=end)
}
export function toggleRange(ranges: TextRange[], start: number, end: number, length: number) {
  if(!rangeUnderlined(ranges,start,end))return normalizeRanges([...ranges,{start,end}],length)
  return normalizeRanges(ranges.flatMap(r => r.end<=start || r.start>=end ? [r] : [{start:r.start,end:start},{start:end,end:r.end}]),length)
}
export function editedRanges(ranges: TextRange[], before: string, after: string) {
  let start=0, oldEnd=before.length, newEnd=after.length
  while(start<oldEnd && start<newEnd && before[start]===after[start])start++
  while(oldEnd>start && newEnd>start && before[oldEnd-1]===after[newEnd-1]){oldEnd--;newEnd--}
  if(start===oldEnd && start===newEnd)return normalizeRanges(ranges,after.length)
  const delta=newEnd-oldEnd
  const inherited=oldEnd>start ? rangeUnderlined(ranges,start,oldEnd) : ranges.some(r=>r.start<start && r.end>=start)
  return normalizeRanges([
    ...ranges.flatMap(r=>[{start:r.start,end:Math.min(r.end,start)}, {start:Math.max(r.start,oldEnd)+delta,end:r.end+delta}]),
    ...(inherited && newEnd>start ? [{start,end:newEnd}] : []),
  ],after.length)
}
export function textSegments(field: Field, text: string, preview=false) {
  if(preview && field.inlineTemplate) {
    const rule=field.inlineTemplate
    let value=text.normalize('NFKC').trim()
    const prefix=rule.prefix.normalize('NFKC').trim(), suffix=rule.suffix.normalize('NFKC').trim()
    if(prefix && value.startsWith(prefix))value=value.slice(prefix.length).trim()
    if(suffix && value.endsWith(suffix))value=value.slice(0,-suffix.length).trim()
    value=value.replace(/^[_＿ ]+|[_＿ ]+$/g,'')
    return [{text:rule.prefix,underline:false}, {text:value,underline:rule.valueStyle.underline!=='none'}, {text:rule.suffix,underline:false}]
  }
  const ranges=preview ? editedRanges(underlineRanges(field),field.textOverride ?? field.label ?? '',text) : underlineRanges(field,text)
  const parts: {text:string;underline:boolean}[]=[]
  let cursor=0
  for(const range of ranges) {
    if(range.start>cursor)parts.push({text:text.slice(cursor,range.start),underline:false})
    parts.push({text:text.slice(range.start,range.end),underline:true});cursor=range.end
  }
  if(cursor<text.length)parts.push({text:text.slice(cursor),underline:false})
  return parts
}
