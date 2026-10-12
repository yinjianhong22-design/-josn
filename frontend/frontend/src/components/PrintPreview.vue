<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { RiPrinterLine, RiCloseLine, RiArrowLeftSLine, RiArrowRightSLine } from '@remixicon/vue'
import StyleSelect from './StyleSelect.vue'
import TemplatePage from './TemplatePage.vue'
import type { Page, Template } from '../types/template'

const props = defineProps<{ template: Template; currentPage: number; previewValues?: Record<string,string> }>()
const emit = defineEmits<{ close: [] }>()
const paper = ref('A4')
const orientation = ref(props.template.pages[props.currentPage]!.width > props.template.pages[props.currentPage]!.height ? 'landscape' : 'portrait')
const margin = ref(0)
const sizing = ref('fit')
const scale = ref(100)
const grayscale = ref(false)
const range = ref('all')
const customRange = ref('')
const previewIndex = ref(props.currentPage)
const previewZoom = ref(100)
const rangeOptions = computed(() => [
  { value: 'all', label: '全部页面' },
  { value: 'current', label: `当前编辑页（第 ${props.currentPage + 1} 页）` },
  { value: 'custom', label: '指定页码' },
])
const paperOptions = [{ value: 'A4', label: 'A4' }, { value: 'A3', label: 'A3' }, { value: 'Letter', label: 'Letter' }]
const orientationOptions = [{ value: 'portrait', label: '纵向' }, { value: 'landscape', label: '横向' }]
const sizingOptions = [{ value: 'fit', label: '适合纸张，不裁切' }, { value: 'original', label: '原始尺寸 / 自定义比例' }]
const previewZoomOptions = [{ value: 50, label: '50%' }, { value: 75, label: '75%' }, { value: 100, label: '100%' }, { value: 125, label: '125%' }]
const preparing = ref(false)
const printError = ref('')
const root = ref<HTMLElement>()
const printButton = ref<HTMLButtonElement>()
const dimensions = computed(() => {
  const sizes: Record<string, [number, number]> = { A4: [210, 297], A3: [297, 420], Letter: [215.9, 279.4] }
  const size = sizes[paper.value]!
  return orientation.value === 'landscape' ? [size[1], size[0]] : size
})
const selection = computed(() => {
  const count = props.template.pages.length
  if (range.value === 'all') return { indices: Array.from({ length: count }, (_, i) => i), error: '' }
  if (range.value === 'current') return { indices: [props.currentPage], error: '' }
  const indices = new Set<number>()
  const invalid = { indices: [] as number[], error: `请输入有效页码（1–${count}），例如 1,3-5` }
  for (const part of customRange.value.replaceAll('，', ',').split(',')) {
    const match = part.trim().match(/^(\d+)(?:\s*[-–]\s*(\d+))?$/)
    if (!match) return invalid
    const first = Number(match[1]), last = Number(match[2] || match[1])
    if (first < 1 || last > count || last < first) return invalid
    for (let number = first; number <= last; number++) indices.add(number - 1)
  }
  return { indices: [...indices].sort((a, b) => a - b), error: '' }
})
const selectedPages = computed(() => selection.value.indices.map(index => ({ page: props.template.pages[index]!, index })))
const settingsError = computed(() => !Number.isFinite(margin.value) || margin.value < 0 || margin.value > 30 ? '页边距应为 0–30 mm'
  : sizing.value === 'original' && (!Number.isFinite(scale.value) || scale.value < 10 || scale.value > 200) ? '内容缩放应为 10%–200%' : '')
const canPrint = computed(() => !selection.value.error && !settingsError.value && !preparing.value && selectedPages.value.length > 0)
watch(selection, () => { previewIndex.value = Math.min(previewIndex.value, Math.max(0, selectedPages.value.length - 1)) })
const sheetStyle = computed(() => ({ width: `${dimensions.value[0]}mm`, height: `${dimensions.value[1]}mm`, filter: grayscale.value ? 'grayscale(1)' : undefined }))
const stageStyle = computed(() => ({ width: `${dimensions.value[0]! * 96 / 25.4 * previewZoom.value / 100}px`, height: `${dimensions.value[1]! * 96 / 25.4 * previewZoom.value / 100}px` }))
function contentStyle(page: Page) {
  const availableWidth = dimensions.value[0]! - margin.value * 2
  const availableHeight = dimensions.value[1]! - margin.value * 2
  const fitWidth = Math.min(availableWidth, availableHeight * page.width / page.height)
  // Parser pages use two raster pixels per PDF point.
  const width = sizing.value === 'fit' ? fitWidth : page.width / 2 * 25.4 / 72 * scale.value / 100
  return { width: `${width}mm`, aspectRatio: `${page.width}/${page.height}`, left: `${(dimensions.value[0]! - width) / 2}mm`, top: `${margin.value}mm` }
}
const clipped = computed(() => sizing.value === 'original' && selectedPages.value.some(({ page }) => {
  const width = page.width / 2 * 25.4 / 72 * scale.value / 100
  return width > dimensions.value[0]! - margin.value * 2 + 0.1 || width * page.height / page.width > dimensions.value[1]! - margin.value * 2 + 0.1
}))
const pageRule = document.createElement('style')
watch(dimensions, () => { pageRule.textContent = `@media print { @page { size: ${dimensions.value[0]}mm ${dimensions.value[1]}mm; margin: 0; } }` }, { immediate: true })
async function print() {
  if (!canPrint.value) return
  preparing.value = true
  printError.value = ''
  try {
    await nextTick()
    await Promise.all(Array.from(root.value!.querySelectorAll('img')).map(image => image.decode()))
    await document.fonts.ready
    window.print()
  } catch {
    printError.value = '页面图像加载失败，请检查连接后重试'
  } finally { preparing.value = false }
}
function keydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && !preparing.value) { event.preventDefault(); emit('close') }
  if (event.key === 'Tab') {
    const items = Array.from(root.value!.querySelectorAll<HTMLElement>('button:not(:disabled), select, input'))
    const first = items[0], last = items[items.length - 1]
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
  }
}
const previousFocus = document.activeElement as HTMLElement | null
onMounted(() => { document.head.appendChild(pageRule); printButton.value?.focus() })
onUnmounted(() => { pageRule.remove(); previousFocus?.focus() })
</script>

<template>
  <Teleport to="body">
    <section ref="root" class="print-preview" role="dialog" aria-modal="true" aria-label="打印预览" @keydown="keydown">
      <header class="print-header"><div><strong>打印预览</strong><span>{{ template.name }}</span></div><button class="text-button" aria-label="退出打印预览" :disabled="preparing" @click="emit('close')"><RiCloseLine size="20px" />退出预览</button></header>
      <div class="print-body">
        <main class="print-stage">
          <div v-if="!selectedPages.length" class="print-empty">{{ selection.error }}</div>
          <div v-for="({ page, index }, position) in selectedPages" :key="page.pageUuid" class="print-page-stage" :class="{ 'preview-current': position === previewIndex }" :style="stageStyle">
            <article class="print-paper" :style="[sheetStyle, { transform: `scale(${previewZoom / 100})` }]" :aria-label="`打印第 ${index + 1} 页`">
              <div class="print-content" :style="contentStyle(page)"><TemplatePage :page="page" :preview-values="page === template.pages[currentPage] ? previewValues : undefined" :selected-ids="[]" :show-regions="false" :show-background="true" printable /></div>
            </article>
          </div>
        </main>
        <aside class="print-settings">
          <h2>打印设置</h2>
          <label>打印范围<StyleSelect :model-value="range" :options="rangeOptions" aria-label="打印范围" @update:model-value="range = String($event)" /></label>
          <label v-if="range === 'custom'">页码<input v-model="customRange" aria-label="指定页码" placeholder="例如：1,3-5" /></label>
          <p v-if="selection.error" class="print-error" role="alert">{{ selection.error }}</p>
          <div class="print-setting-row"><label>纸张<StyleSelect :model-value="paper" :options="paperOptions" aria-label="纸张" @update:model-value="paper = String($event)" /></label><label>方向<StyleSelect :model-value="orientation" :options="orientationOptions" aria-label="纸张方向" @update:model-value="orientation = String($event)" /></label></div>
          <label>页边距（mm）<input v-model.number="margin" aria-label="页边距" type="number" min="0" max="30" /></label>
          <p class="print-note">原件已包含页边距，通常保留 0 即可</p>
          <label>内容缩放<StyleSelect :model-value="sizing" :options="sizingOptions" aria-label="内容缩放" @update:model-value="sizing = String($event)" /></label>
          <label v-if="sizing === 'original'">比例（%）<input v-model.number="scale" aria-label="内容缩放比例" type="number" min="10" max="200" /></label>
          <label class="print-check"><input v-model="grayscale" type="checkbox" />灰度打印</label>
          <p v-if="settingsError" class="print-error" role="alert">{{ settingsError }}</p>
          <p v-if="clipped" class="print-error" role="status">内容超出可用纸张区域，打印会裁切，可改用“适合纸张”</p>
          <div class="print-summary">已选 {{ selectedPages.length }} / {{ template.pages.length }} 页</div>
          <p class="print-note">输出包含原始底图和最新修改，编辑边界和控制点不会打印；打印机、份数、双面及另存为 PDF，在系统打印窗口中选择</p>
          <p class="print-note">系统窗口中建议保留此纸张尺寸、100% 缩放，关闭页眉页脚，避免再次缩放</p>
          <p v-if="printError" class="print-error" role="alert">{{ printError }}</p>
          <button ref="printButton" class="primary print-submit" :disabled="!canPrint" @click="print"><RiPrinterLine size="18px" />{{ preparing ? '正在准备…' : '打印' }}</button>
        </aside>
      </div>
      <footer class="print-footer"><div><button class="tool-button" aria-label="预览上一页" :disabled="previewIndex <= 0" @click="previewIndex--"><RiArrowLeftSLine /></button><span>{{ selectedPages.length ? previewIndex + 1 : 0 }} / {{ selectedPages.length }} 页<span v-if="selectedPages[previewIndex]"> · 原件第 {{ selectedPages[previewIndex]!.index + 1 }} 页</span></span><button class="tool-button" aria-label="预览下一页" :disabled="previewIndex >= selectedPages.length - 1" @click="previewIndex++"><RiArrowRightSLine /></button></div><label>预览缩放 <StyleSelect :model-value="previewZoom" :options="previewZoomOptions" aria-label="预览缩放" @update:model-value="previewZoom = Number($event)" /></label></footer>
    </section>
  </Teleport>
</template>

<style>
.print-preview { position: fixed; inset: 0; z-index: 100; display: flex; flex-direction: column; background: #edeef1; }
.print-header { height: 58px; flex-shrink: 0; background: white; border-bottom: 1px solid #dedfe4; display: flex; align-items: center; justify-content: space-between; padding: 0 22px; }
.print-header > div { display: flex; align-items: center; gap: 18px; min-width: 0; }
.print-header strong { font-size: 15px; white-space: nowrap; }
.print-header span { color: #92969f; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.print-header button { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.print-body { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr) 300px; }
.print-stage { overflow: auto; padding: 32px; }
.print-page-stage { position: relative; margin: 0 auto; display: none; }
.print-page-stage.preview-current { display: block; }
.print-paper { position: relative; background: white; overflow: hidden; transform-origin: top left; box-shadow: 0 2px 16px #1f293720; }
.print-content { position: absolute; }
.print-content .document-page { box-shadow: none; }
.print-settings { overflow-y: auto; background: white; border-left: 1px solid #dedfe4; padding: 22px; }
.print-settings h2 { margin: 0 0 22px; font-size: 14px; }
.print-settings label { display: flex; flex-direction: column; gap: 8px; margin-bottom: 18px; color: #626873; }
.print-settings input:not([type=checkbox]) { width: 100%; border: 1px solid #dcdde2; border-radius: 5px; padding: 9px; background: white; font: inherit; color: #303238; min-width: 0; }
.print-settings .style-select, .print-footer .style-select { width: 100%; min-width: 0; }
.print-settings .style-select .style-select-value, .print-footer .style-select .style-select-value { width: 100%; border: 1px solid #dcdde2; border-radius: 5px; padding: 9px; background: white; font: inherit; color: #303238; min-width: 0; }
.print-settings .style-select .style-select-popup, .print-footer .style-select .style-select-popup { left: 0; width: 100%; }
.print-settings .style-select .style-select-popup { top: calc(100% + 6px); }
.print-setting-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.print-settings .print-check { flex-direction: row; align-items: center; }
.print-note { color: #969ba5; font-size: 11px; line-height: 1.7; margin: 0 0 18px; }
.print-error { color: #c25043; font-size: 11px; line-height: 1.6; }
.print-summary { border-top: 1px solid #e5e5e8; padding: 18px 0; font-weight: 600; }
.print-submit { width: 100%; display: flex; align-items: center; justify-content: center; gap: 8px; min-height: 38px; }
.print-footer { height: 52px; flex-shrink: 0; display: flex; align-items: center; justify-content: space-between; padding: 0 22px; border-top: 1px solid #dedfe4; background: white; }
.print-footer > div { display: flex; align-items: center; gap: 12px; }
.print-footer label { display: flex; align-items: center; gap: 10px; white-space: nowrap; }
.print-footer .style-select { width: 84px; flex-shrink: 0; }
.print-footer .style-select .style-select-value { padding: 5px 8px; }
.print-footer .style-select .style-select-popup { top: auto; bottom: calc(100% + 6px); }
.print-empty { text-align: center; padding: 100px 20px; color: #969ba5; }
@media (max-width: 740px) { .print-body { grid-template-columns: minmax(0, 1fr) 240px; } .print-settings { padding: 16px; } .print-stage { padding: 16px; } .print-header span { display: none; } }
@media print {
  html, body { margin: 0 !important; padding: 0 !important; height: auto !important; background: white !important; }
  body > *:not(.print-preview) { display: none !important; }
  .print-preview { position: static !important; display: block !important; background: white !important; }
  .print-header, .print-settings, .print-footer, .print-empty { display: none !important; }
  .print-body, .print-stage { display: block !important; padding: 0 !important; margin: 0 !important; overflow: visible !important; }
  .print-page-stage { display: block !important; width: auto !important; height: auto !important; margin: 0 !important; break-inside: avoid; break-after: page; }
  .print-page-stage:last-child { break-after: auto; }
  .print-paper { transform: none !important; box-shadow: none !important; print-color-adjust: exact; -webkit-print-color-adjust: exact; }
}
</style>
