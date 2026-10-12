<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { RiCloseLine, RiSipLine } from '@remixicon/vue'

const props = withDefaults(defineProps<{ modelValue: string; label?: string }>(), { label: '文字颜色' })
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const trigger = ref<HTMLButtonElement>()
const panel = ref<HTMLDivElement>()
const isOpen = ref(false)
const position = ref({ left: '0px', top: '0px' })
const hsv = reactive({ h: 0, s: 0, v: 0, alpha: 1 })
const hexDraft = ref('000000')
let dragging = false

function readHex(value: string) {
  const hex = value.replace('#', '')
  const r = parseInt(hex.slice(0, 2), 16) / 255
  const g = parseInt(hex.slice(2, 4), 16) / 255
  const b = parseInt(hex.slice(4, 6), 16) / 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b), delta = max - min
  if (delta) hsv.h = ((max === r ? (g - b) / delta : max === g ? (b - r) / delta + 2 : (r - g) / delta + 4) * 60 + 360) % 360
  hsv.s = max ? delta / max : 0
  hsv.v = max
  hsv.alpha = hex.length === 8 ? parseInt(hex.slice(6), 16) / 255 : 1
  hexDraft.value = hex.slice(0, 6).toUpperCase()
}
watch(() => props.modelValue, readHex, { immediate: true })
const hexColor = computed(() => {
  const chroma = hsv.v * hsv.s
  const x = chroma * (1 - Math.abs((hsv.h / 60) % 2 - 1))
  const m = hsv.v - chroma
  const sector = Math.min(5, Math.floor(hsv.h / 60))
  const rgb = [[chroma, x, 0], [x, chroma, 0], [0, chroma, x], [0, x, chroma], [x, 0, chroma], [chroma, 0, x]][sector]!
  return '#' + rgb.map(channel => Math.round((channel + m) * 255).toString(16).padStart(2, '0')).join('').toUpperCase()
})
const opacityPercent = computed(() => Math.round(hsv.alpha * 100))
function commit() {
  const alpha = hsv.alpha < 1 ? Math.round(hsv.alpha * 255).toString(16).padStart(2, '0').toUpperCase() : ''
  emit('update:modelValue', hexColor.value + alpha)
}
function choosePoint(event: PointerEvent) {
  const box = (event.currentTarget as HTMLElement).getBoundingClientRect()
  hsv.s = Math.max(0, Math.min(1, (event.clientX - box.left) / box.width))
  hsv.v = 1 - Math.max(0, Math.min(1, (event.clientY - box.top) / box.height))
  commit()
}
function startDrag(event: PointerEvent) {
  if (event.button !== 0) return
  dragging = true
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  choosePoint(event)
}
function moveDrag(event: PointerEvent) { if (dragging) choosePoint(event) }
function keyboardColor(event: KeyboardEvent) {
  const delta = event.shiftKey ? 0.1 : 0.01
  if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return
  event.preventDefault()
  if (event.key === 'ArrowLeft') hsv.s = Math.max(0, hsv.s - delta)
  if (event.key === 'ArrowRight') hsv.s = Math.min(1, hsv.s + delta)
  if (event.key === 'ArrowUp') hsv.v = Math.min(1, hsv.v + delta)
  if (event.key === 'ArrowDown') hsv.v = Math.max(0, hsv.v - delta)
  commit()
}
function applyHex(event: Event) {
  const input = event.target as HTMLInputElement
  const hex = hexDraft.value.trim().replace(/^#/, '')
  if (!/^[0-9a-f]{6}$/i.test(hex)) {
    input.setCustomValidity('请输入 6 位 HEX 颜色，如 C43B3B')
    input.reportValidity()
    return
  }
  input.setCustomValidity('')
  const alpha = hsv.alpha
  readHex(hex)
  hsv.alpha = alpha
  commit()
}
function applyOpacity(event: Event) {
  const input = event.target as HTMLInputElement
  if (input.value === '' || !input.checkValidity()) return
  hsv.alpha = Number(input.value) / 100
  commit()
}
function togglePicker() {
  if (!panel.value || !trigger.value) return
  const box = trigger.value.getBoundingClientRect()
  position.value = {
    left: `${Math.max(8, Math.min(window.innerWidth - 296, box.left >= 300 ? box.left - 300 : box.left))}px`,
    top: `${Math.max(8, Math.min(window.innerHeight - 350, box.top - 80))}px`,
  }
  panel.value.togglePopover()
}
function onToggle(event: Event) { isOpen.value = (event as ToggleEvent).newState === 'open' }
type Dropper = { open(): Promise<{ sRGBHex: string }> }
const EyeDropperClass = (window as unknown as { EyeDropper?: new () => Dropper }).EyeDropper
async function pickScreenColor() {
  if (!EyeDropperClass) return
  try {
    const value = await new EyeDropperClass().open()
    const alpha = hsv.alpha
    readHex(value.sRGBHex)
    hsv.alpha = alpha
    commit()
  } catch (error) {
    if ((error as Error).name !== 'AbortError') console.error(error)
  }
}
</script>

<template>
  <div class="color-picker-control">
    <button ref="trigger" type="button" class="color-trigger" :aria-label="label" :aria-expanded="isOpen" @click="togglePicker">
      <span class="color-checker color-trigger-swatch"><i :style="{ backgroundColor: modelValue }"></i></span>
      <span class="color-trigger-hex">{{ modelValue.slice(0, 7).toUpperCase() }}</span><span class="color-trigger-alpha">{{ opacityPercent }} %</span>
    </button>
    <div ref="panel" popover="auto" class="color-popover" :style="position" role="dialog" :aria-label="label + '选择器'" @toggle="onToggle">
      <header><span>{{ label }}</span><button type="button" aria-label="关闭颜色面板" @click="panel?.hidePopover()"><RiCloseLine size="16px" /></button></header>
      <div class="color-board" :style="{ backgroundColor: `hsl(${hsv.h}, 100%, 50%)` }" role="slider" tabindex="0"
        aria-label="颜色区域" :aria-valuetext="hexColor" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="Math.round(hsv.s * 100)"
        @pointerdown="startDrag" @pointermove="moveDrag" @pointerup="dragging = false" @pointercancel="dragging = false" @keydown="keyboardColor">
        <i :style="{ left: hsv.s * 100 + '%', top: (1 - hsv.v) * 100 + '%', backgroundColor: hexColor }"></i>
      </div>
      <div class="color-slider-row">
        <button type="button" class="color-eyedropper" aria-label="屏幕取色" :disabled="!EyeDropperClass" :title="EyeDropperClass ? '屏幕取色' : '当前浏览器不支持屏幕取色'" @click="pickScreenColor"><RiSipLine size="19px" /></button>
        <div class="color-sliders">
          <input v-model.number="hsv.h" class="color-range color-hue" type="range" min="0" max="359" step="1" aria-label="色相" @input="commit" />
          <div class="color-checker color-alpha-track"><input v-model.number="hsv.alpha" class="color-range" type="range" min="0" max="1" step="0.01" aria-label="颜色透明度" :style="{ background: `linear-gradient(to right, ${hexColor}00, ${hexColor})` }" @input="commit" /></div>
        </div>
      </div>
      <div class="color-inputs"><span>HEX</span><label class="color-hex-input"><span>#</span><input v-model="hexDraft" maxlength="7" aria-label="HEX 颜色" spellcheck="false" @input="($event.target as HTMLInputElement).setCustomValidity('')" @change="applyHex" @keydown.enter.prevent="applyHex" /></label><label class="color-opacity-input"><input type="number" min="0" max="100" step="1" :value="opacityPercent" aria-label="颜色不透明度百分比" @input="applyOpacity" /><span>%</span></label></div>
    </div>
  </div>
</template>

<style scoped>
.color-trigger { width: 100%; display: flex; align-items: center; gap: 9px; height: 36px; padding: 7px 9px; border: 0; border-radius: 6px; background: #f3f3f4; font-size: 11px; text-align: left; }
.color-checker { background-color: #fff; background-image: conic-gradient(#d9dbe0 25%, transparent 0 50%, #d9dbe0 0 75%, transparent 0); background-size: 8px 8px; }
.color-trigger-swatch { width: 18px; height: 18px; overflow: hidden; border: 1px solid #d5d8de; border-radius: 4px; }
.color-trigger-swatch i { display: block; width: 100%; height: 100%; }
.color-trigger-hex { flex: 1; color: #343944; }
.color-trigger-alpha { color: #777e89; }
.color-popover { position: fixed; inset: auto; width: 288px; margin: 0; padding: 14px; border: 1px solid #e1e3e8; border-radius: 9px; box-shadow: 0 7px 28px #1d293322; background: #fff; color: #303238; font: 12px/1.4 system-ui, sans-serif; }
.color-popover header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; font-weight: 500; }
.color-popover header button { display: grid; place-items: center; width: 24px; height: 24px; padding: 0; border: 0; background: transparent; border-radius: 4px; color: #7f8793; }
.color-board { position: relative; height: 180px; border-radius: 5px; background-image: linear-gradient(to top, #000, transparent), linear-gradient(to right, #fff, transparent); cursor: crosshair; touch-action: none; }
.color-board i { position: absolute; width: 13px; height: 13px; border: 2px solid white; border-radius: 50%; box-shadow: 0 0 2px 1px #0005; transform: translate(-50%, -50%); pointer-events: none; }
.color-slider-row { display: flex; align-items: center; gap: 12px; margin: 15px 0; }
.color-eyedropper { display: grid; place-items: center; width: 34px; height: 38px; padding: 0; border: 1px solid #dfe2e7; border-radius: 6px; background: white; color: #838b98; }
.color-sliders { display: grid; gap: 10px; flex: 1; min-width: 0; }
.color-range { appearance: none; display: block; width: 100%; height: 11px; margin: 0; border: 0; border-radius: 10px; cursor: pointer; }
.color-hue { background: linear-gradient(to right, red, #ff0, #0f0, #0ff, #00f, #f0f, red); }
.color-range::-webkit-slider-thumb { appearance: none; width: 17px; height: 17px; border: 1px solid #b8bec9; border-radius: 50%; background: white; box-shadow: 0 1px 3px #0002; }
.color-range::-moz-range-thumb { width: 15px; height: 15px; border: 1px solid #b8bec9; border-radius: 50%; background: white; }
.color-alpha-track { border-radius: 10px; }
.color-inputs { display: grid; grid-template-columns: 43px minmax(0, 1fr) 64px; align-items: center; min-height: 34px; border: 1px solid #e1e3e8; border-radius: 6px; overflow: hidden; }
.color-inputs > span { text-align: center; color: #6f7784; font-size: 10px; }
.color-inputs label { display: flex; align-items: center; gap: 3px; padding: 7px; background: #f5f5f6; }
.color-inputs input { width: 100%; min-width: 0; padding: 0; border: 0; background: transparent; outline: 0; color: #343944; font: inherit; }
.color-hex-input > span, .color-opacity-input > span { color: #8c929d; }
.color-opacity-input { border-left: 1px solid #e1e3e8; }
.color-opacity-input input { appearance: textfield; text-align: right; }
.color-opacity-input input::-webkit-inner-spin-button { appearance: none; }
.color-board:focus-visible, .color-range:focus-visible, .color-inputs:focus-within { outline: 2px solid #75adff; outline-offset: 2px; }
</style>
