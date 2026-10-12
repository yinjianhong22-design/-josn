<script setup lang="ts">
import { computed, onUnmounted, ref, type CSSProperties } from 'vue'
import type { Field, Page, Rect } from '../types/template'
import { imageUrl } from '../api/template'
import { textSegments } from '../utils/textUnderline'
import { fontStack } from '../utils/fonts'

type Handle = 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w' | 'nw'
type SnapGuide = { axis: 'x' | 'y'; value: number }
type SplitGuide = { fieldUuid: string; axis: 'x' | 'y'; position: number }
type SplitDragState = { axis: 'x' | 'y'; start: number; position: number; bounds: DOMRect }
type ResizeState = {
  fieldUuid: string
  handle: Handle
  startX: number
  startY: number
  pageBounds: DOMRect
  initial: Rect
}

const props = defineProps<{ page: Page; selectedIds: string[]; showRegions: boolean; showBackground: boolean; splitGuide?: SplitGuide; printable?: boolean; previewValues?: Record<string, string> }>()
const emit = defineEmits<{
  select: [field: Field, event: MouseEvent]
  resize: [fieldUuid: string, rect: Rect]
  splitMove: [axis: 'x' | 'y', position: number]
}>()

const fields = computed(() => [...(props.page.fields || []), ...(props.page.tables || []).flatMap(table => table.fields)])
const textOverrides = computed(() => fields.value.filter(field => field.textOverride !== undefined || props.previewValues?.[field.fieldUuid] !== undefined))
const splitField = computed(() => props.splitGuide ? fields.value.find(field => field.fieldUuid === props.splitGuide?.fieldUuid) : undefined)
const handles: Handle[] = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w']
const guides = ref<SnapGuide[]>([])
let resizeState: ResizeState | undefined
let splitDragState: SplitDragState | undefined

function overlayStyle(field: Field): CSSProperties {
  const style = field.style
  const horizontal = style?.horizontalAlign?.toLowerCase()
  const vertical = style?.verticalAlign?.toLowerCase()
  const justifyContent: CSSProperties['justifyContent'] = horizontal === 'right' ? 'flex-end'
    : horizontal === 'center' || horizontal === 'centercontinuous' ? 'center'
      : horizontal === 'distributed' || horizontal === 'justify' ? 'space-between' : 'flex-start'
  const alignItems: CSSProperties['alignItems'] = vertical === 'top' ? 'flex-start'
    : vertical === 'bottom' ? 'flex-end' : 'center'
  const textAlign: CSSProperties['textAlign'] = horizontal === 'right' ? 'right' : horizontal === 'center' || horizontal === 'centercontinuous' ? 'center' : horizontal === 'justify' || horizontal === 'distributed' ? 'justify' : 'left'
  const whiteSpace: CSSProperties['whiteSpace'] = style?.wrapText === false ? 'pre' : 'pre-wrap'
  const fontSizePt = style?.fontSizePt || 10

  return {
    left: `calc(${field.rect.x * 100}% + 1px)`,
    top: `calc(${field.rect.y * 100}% + 1px)`,
    width: `calc(${field.rect.w * 100}% - 2px)`,
    height: `calc(${field.rect.h * 100}% - 2px)`,
    backgroundColor: style?.fillColor || '#fff',
    color: style?.color || '#202124',
    fontFamily: fontStack(style?.fontFamily),
    // All document backgrounds are rasterized at two pixels per PDF point.
    fontSize: `${fontSizePt * 2 / props.page.width * 100}cqw`,
    fontWeight: style?.bold ? '700' : '400',
    fontStyle: style?.italic ? 'italic' : 'normal',
    textDecoration: 'none',
    textAlign,
    textAlignLast: horizontal === 'distributed' ? 'justify' : undefined,
    ...(style?.paddingPt ? Object.fromEntries(['top','right','bottom','left'].map(side=>['padding'+side[0]!.toUpperCase()+side.slice(1),`${(style.paddingPt![side as keyof typeof style.paddingPt] || 0)*2/props.page.width*100}cqw`])) : {}),
    justifyContent,
    alignItems,
    whiteSpace,
  }
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.max(minimum, Math.min(maximum, value))
}

function snap(value: number, candidates: number[], tolerance: number): number | undefined {
  let closest: number | undefined
  let distance = tolerance
  for (const candidate of candidates) {
    const delta = Math.abs(candidate - value)
    if (delta < distance) {
      closest = candidate
      distance = delta
    }
  }
  return closest
}

function startResize(event: PointerEvent, field: Field, handle: Handle) {
  event.preventDefault()
  event.stopPropagation()
  const pageElement = (event.currentTarget as HTMLElement).closest('.document-page')
  if (!pageElement) return

  resizeState = {
    fieldUuid: field.fieldUuid,
    handle,
    startX: event.clientX,
    startY: event.clientY,
    pageBounds: pageElement.getBoundingClientRect(),
    initial: { ...field.rect },
  }
  window.addEventListener('pointermove', moveResize)
  window.addEventListener('pointerup', finishResize)
  window.addEventListener('pointercancel', finishResize)
}

function moveResize(event: PointerEvent) {
  const state = resizeState
  if (!state) return

  const dx = (event.clientX - state.startX) / state.pageBounds.width
  const dy = (event.clientY - state.startY) / state.pageBounds.height
  const minimumWidth = Math.min(1, 8 / state.pageBounds.width)
  const minimumHeight = Math.min(1, 8 / state.pageBounds.height)
  let left = state.initial.x
  let right = state.initial.x + state.initial.w
  let top = state.initial.y
  let bottom = state.initial.y + state.initial.h
  const movedX = state.handle.includes('w') || state.handle.includes('e')
  const movedY = state.handle.includes('n') || state.handle.includes('s')

  if (state.handle.includes('w')) left = clamp(left + dx, 0, right - minimumWidth)
  if (state.handle.includes('e')) right = clamp(right + dx, left + minimumWidth, 1)
  if (state.handle.includes('n')) top = clamp(top + dy, 0, bottom - minimumHeight)
  if (state.handle.includes('s')) bottom = clamp(bottom + dy, top + minimumHeight, 1)

  const xLines = fields.value.filter(item => item.fieldUuid !== state.fieldUuid)
    .flatMap(item => [item.rect.x, item.rect.x + item.rect.w]).concat([0, 1])
  const yLines = fields.value.filter(item => item.fieldUuid !== state.fieldUuid)
    .flatMap(item => [item.rect.y, item.rect.y + item.rect.h]).concat([0, 1])
  const snapX = state.handle.includes('w') ? 'left' : 'right'
  const snapY = state.handle.includes('n') ? 'top' : 'bottom'
  const nextGuides: SnapGuide[] = []

  if (movedX) {
    const edge = snapX === 'left' ? left : right
    const matched = snap(edge, xLines, 6 / state.pageBounds.width)
    if (matched !== undefined) {
      if (snapX === 'left') left = clamp(matched, 0, right - minimumWidth)
      else right = clamp(matched, left + minimumWidth, 1)
      nextGuides.push({ axis: 'x', value: matched })
    }
  }
  if (movedY) {
    const edge = snapY === 'top' ? top : bottom
    const matched = snap(edge, yLines, 6 / state.pageBounds.height)
    if (matched !== undefined) {
      if (snapY === 'top') top = clamp(matched, 0, bottom - minimumHeight)
      else bottom = clamp(matched, top + minimumHeight, 1)
      nextGuides.push({ axis: 'y', value: matched })
    }
  }

  guides.value = nextGuides
  emit('resize', state.fieldUuid, {
    x: Number(left.toFixed(6)),
    y: Number(top.toFixed(6)),
    w: Number((right - left).toFixed(6)),
    h: Number((bottom - top).toFixed(6)),
  })
}

function startSplitDrag(event: PointerEvent) {
  const guide = props.splitGuide
  const pageElement = (event.currentTarget as HTMLElement).closest('.document-page')
  if (!guide || !pageElement) return
  event.preventDefault()
  event.stopPropagation()
  splitDragState = {
    axis: guide.axis,
    start: guide.axis === 'x' ? event.clientX : event.clientY,
    position: guide.position,
    bounds: pageElement.getBoundingClientRect(),
  }
  window.addEventListener('pointermove', moveSplitDrag)
  window.addEventListener('pointerup', finishSplitDrag)
  window.addEventListener('pointercancel', finishSplitDrag)
}

function moveSplitDrag(event: PointerEvent) {
  const state = splitDragState
  const guide = props.splitGuide
  const field = splitField.value
  if (!state || !guide || !field) return
  const horizontal = state.axis === 'x'
  const current = horizontal ? event.clientX : event.clientY
  const dimension = horizontal ? state.bounds.width : state.bounds.height
  const delta = (current - state.start) / dimension
  const start = horizontal ? field.rect.x : field.rect.y
  const end = start + (horizontal ? field.rect.w : field.rect.h)
  const minimum = Math.min((horizontal ? field.rect.w : field.rect.h) / 2, 8 / dimension)
  const position = clamp(state.position + delta, start + minimum, end - minimum)
  emit('splitMove', state.axis, Number(position.toFixed(6)))
}

function finishSplitDrag() {
  window.removeEventListener('pointermove', moveSplitDrag)
  window.removeEventListener('pointerup', finishSplitDrag)
  window.removeEventListener('pointercancel', finishSplitDrag)
  splitDragState = undefined
}

function finishResize() {
  window.removeEventListener('pointermove', moveResize)
  window.removeEventListener('pointerup', finishResize)
  window.removeEventListener('pointercancel', finishResize)
  resizeState = undefined
  guides.value = []
}

onUnmounted(() => { finishResize(); finishSplitDrag() })
</script>

<template>
  <div class="document-page" :style="{ aspectRatio: page.width + '/' + page.height }">
    <img v-if="showBackground" :src="imageUrl(page.background)" :alt="'文档第 ' + page.pageNo + ' 页'" draggable="false" />
    <div class="text-overlay-layer" aria-hidden="true">
      <div v-for="mask in page.mergeMasks || []" :key="mask.maskUuid" class="merge-mask"
        :style="{ left: mask.rect.x * 100 + '%', top: mask.rect.y * 100 + '%', width: mask.rect.w * 100 + '%', height: mask.rect.h * 100 + '%', backgroundColor: mask.color }" />
      <div v-for="field in textOverrides" :key="field.fieldUuid" class="text-overlay"
        :style="overlayStyle(field)"><span class="formatted-text" :style="{width: ['justify','distributed'].includes(field.style?.horizontalAlign || '') ? '100%' : undefined}"><span v-for="(part,index) in textSegments(field, previewValues?.[field.fieldUuid] ?? field.textOverride ?? '', previewValues?.[field.fieldUuid] !== undefined)" :key="index" :style="{textDecoration:part.underline?'underline':'none',textUnderlineOffset:'0.12em'}">{{ part.text }}</span></span></div>
      <div v-for="mask in page.deletionMasks || []" :key="mask.maskUuid" class="deletion-mask"
        :style="{ left: mask.rect.x * 100 + '%', top: mask.rect.y * 100 + '%', width: mask.rect.w * 100 + '%', height: mask.rect.h * 100 + '%', backgroundColor: mask.color }" />
    </div>
    <div v-if="!printable" class="region-layer">
      <button v-for="(field, index) in fields" :key="field.fieldUuid" class="region"
        :class="{ selected: selectedIds.includes(field.fieldUuid), 'boundary-visible': field.regionVisible ?? showRegions }"
        :style="{ left: (field.rect.x * 100) + '%', top: (field.rect.y * 100) + '%', width: (field.rect.w * 100) + '%', height: (field.rect.h * 100) + '%' }"
        :aria-label="'区域 ' + (index + 1) + ((field.textOverride ?? field.label) ? '：' + (field.textOverride ?? field.label) : '：空白单元格')"
        @click.stop="emit('select', field, $event)">
        <span class="region-number">{{ String(index + 1).padStart(3, '0') }}</span>
        <span v-if="!splitGuide && selectedIds.length === 1 && selectedIds[0] === field.fieldUuid"
          v-for="handle in handles" :key="handle" class="resize-handle" :class="handle"
          :aria-label="'调整区域 ' + handle" @pointerdown="startResize($event, field, handle)" />
      </button>
      <div v-if="splitGuide && splitField" class="split-divider"
        :class="splitGuide.axis === 'x' ? 'vertical' : 'horizontal'"
        :style="splitGuide.axis === 'x'
          ? { left: (splitGuide.position * 100) + '%', top: (splitField.rect.y * 100) + '%', height: (splitField.rect.h * 100) + '%' }
          : { top: (splitGuide.position * 100) + '%', left: (splitField.rect.x * 100) + '%', width: (splitField.rect.w * 100) + '%' }"
        role="separator" :aria-orientation="splitGuide.axis === 'x' ? 'vertical' : 'horizontal'"
        aria-label="拖动调整分割位置" @pointerdown="startSplitDrag">
        <span class="split-grip"></span>
      </div>
      <div v-for="guide in guides" :key="guide.axis + guide.value"
        class="snap-guide" :class="guide.axis === 'x' ? 'vertical' : 'horizontal'"
        :style="guide.axis === 'x' ? { left: (guide.value * 100) + '%' } : { top: (guide.value * 100) + '%' }"></div>
    </div>
  </div>
</template>

<style scoped>
.document-page { position: relative; width: 100%; container-type: inline-size; background: white; box-shadow: 0 2px 16px #1f293714; }
img { display: block; width: 100%; height: 100%; user-select: none; }
.text-overlay-layer { position: absolute; z-index: 1; inset: 0; overflow: hidden; pointer-events: none; }
.text-overlay { font-synthesis: weight style; position: absolute; display: flex; overflow: hidden; padding: 0 0.4cqw; line-height: 1.2; overflow-wrap: anywhere; }
.merge-mask,.deletion-mask { position: absolute; pointer-events: none; }
.region-layer { position: absolute; z-index: 2; inset: 0; }
.region { position: absolute; overflow: visible; margin: 0; padding: 0; border: 1px solid transparent; border-radius: 0; background: transparent; cursor: pointer; touch-action: none; }
.region.boundary-visible { border-color: #9eacbd66; }
.region:hover, .region:focus-visible { border-color: #0067e9; background: #0067e908; outline: none; z-index: 2; }
.region.selected { border: 2px solid #0067e9; background: #0067e90c; z-index: 3; }
.region-number { display: none; position: absolute; left: -1px; top: -19px; padding: 2px 5px; border-radius: 3px 3px 0 0; font: 11px/14px system-ui; color: white; background: #0067e9; white-space: nowrap; pointer-events: none; }
.region:hover .region-number, .region:focus-visible .region-number, .selected .region-number { display: block; }
.resize-handle { position: absolute; z-index: 6; box-sizing: border-box; width: 8px; height: 8px; border: 1.5px solid #0067e9; border-radius: 50%; background: white; touch-action: none; }
.nw { left: 0; top: 0; transform: translate(-50%, -50%); cursor: nwse-resize; }
.n { left: 50%; top: 0; transform: translate(-50%, -50%); cursor: ns-resize; }
.ne { right: 0; top: 0; transform: translate(50%, -50%); cursor: nesw-resize; }
.e { right: 0; top: 50%; transform: translate(50%, -50%); cursor: ew-resize; }
.se { right: 0; bottom: 0; transform: translate(50%, 50%); cursor: nwse-resize; }
.s { left: 50%; bottom: 0; transform: translate(-50%, 50%); cursor: ns-resize; }
.sw { left: 0; bottom: 0; transform: translate(-50%, 50%); cursor: nesw-resize; }
.w { left: 0; top: 50%; transform: translate(-50%, -50%); cursor: ew-resize; }
.split-divider { position: absolute; z-index: 7; background: #0067e9; touch-action: none; }
.split-divider.vertical { width: 2px; cursor: col-resize; }
.split-divider.horizontal { height: 2px; cursor: row-resize; }
.split-grip { position: absolute; left: 50%; top: 50%; width: 14px; height: 36px; border: 1px solid #0067e9; border-radius: 8px; background: white; box-shadow: 0 1px 5px #1f293733; transform: translate(-50%, -50%); }
.split-divider.horizontal .split-grip { width: 36px; height: 14px; }
.snap-guide { position: absolute; z-index: 5; background: #0067e9; pointer-events: none; }
.snap-guide.vertical { top: 0; bottom: 0; width: 1px; }
.snap-guide.horizontal { left: 0; right: 0; height: 1px; }
</style>
