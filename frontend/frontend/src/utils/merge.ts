import type { Field, Page, Rect } from '../types/template'

export function mergeBounds(items: Field[], _page: Page): Rect | undefined {
  if (items.length < 2) return
  const x = Math.min(...items.map(f => f.rect.x)), y = Math.min(...items.map(f => f.rect.y))
  const w = Math.max(...items.map(f => f.rect.x + f.rect.w)) - x
  const h = Math.max(...items.map(f => f.rect.y + f.rect.h)) - y
  return { x, y, w, h }
}

export function mergeMasks(items: Field[], bounds: Rect, page: Page) {
  const masks: NonNullable<Page['mergeMasks']> = []
  const add = (rect: Rect, color: string) => {
    if (rect.w > 0 && rect.h > 0) masks.push({ maskUuid: 'mask_' + crypto.randomUUID(), rect, color })
  }
  const edgeWidth = (axis: 'x' | 'y') => Math.max(1, ...items.flatMap(field => {
    const start = axis === 'x' ? 'left' : 'top', end = axis === 'x' ? 'right' : 'bottom'
    const size = axis === 'x' ? 'w' : 'h'
    return [Math.abs(field.rect[axis]-bounds[axis]) < .001 ? field.style?.borders?.[start]?.widthPt || 0 : 0,
      Math.abs(field.rect[axis]+field.rect[size]-bounds[axis]-bounds[size]) < .001 ? field.style?.borders?.[end]?.widthPt || 0 : 0]
  }))
  const insetX = edgeWidth('x') / page.width, insetY = edgeWidth('y') / page.height
  for (let i = 0; i < items.length; i++) for (const b of items.slice(i+1)) {
    const a = items[i]!
    const color = a.style?.fillColor || b.style?.fillColor || '#ffffff'
    for (const [left, right] of [[a,b],[b,a]] as const) {
      if (Math.abs(left.rect.x+left.rect.w-right.rect.x) <= insetX) {
        const y = Math.max(left.rect.y,right.rect.y,bounds.y+insetY)
        const end = Math.min(left.rect.y+left.rect.h,right.rect.y+right.rect.h,bounds.y+bounds.h-insetY)
        const width = Math.max(3, (Math.max(left.style?.borders?.right?.widthPt || 0,right.style?.borders?.left?.widthPt || 0)*2)+2) / page.width
        const edge = (left.rect.x+left.rect.w+right.rect.x)/2
        add({x:edge-width/2,y,w:width,h:end-y},color)
      }
      if (Math.abs(left.rect.y+left.rect.h-right.rect.y) <= insetY) {
        const x = Math.max(left.rect.x,right.rect.x,bounds.x+insetX)
        const end = Math.min(left.rect.x+left.rect.w,right.rect.x+right.rect.w,bounds.x+bounds.w-insetX)
        const height = Math.max(3, (Math.max(left.style?.borders?.bottom?.widthPt || 0,right.style?.borders?.top?.widthPt || 0)*2)+2) / page.height
        const edge = (left.rect.y+left.rect.h+right.rect.y)/2
        add({x,y:edge-height/2,w:end-x,h:height},color)
      }
    }
  }
  // Remove original raster text before rendering the combined editable content.
  for (const field of items) if ((field.textOverride ?? field.label)?.trim()) {
    add({x:field.rect.x+insetX,y:field.rect.y+insetY,w:field.rect.w-2*insetX,h:field.rect.h-2*insetY},field.style?.fillColor || '#ffffff')
  }
  return masks
}
