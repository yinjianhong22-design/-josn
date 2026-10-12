<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

type Option = { value: string | number; label: string; style?: Record<string, string>; group?: string }

const props = defineProps<{ modelValue: string | number; options: Option[] }>()
const emit = defineEmits<{ 'update:modelValue': [value: string | number] }>()
defineOptions({ inheritAttrs: false })

const open = ref(false)
const root = ref<HTMLDivElement>()

const current = computed(() => props.options.find(option => option.value === props.modelValue))
const groups = computed(() => {
  const result: { name: string; items: Option[] }[] = []
  for (const option of props.options) {
    const name = option.group || ''
    const existing = result.find(group => group.name === name)
    if (existing) existing.items.push(option)
    else result.push({ name, items: [option] })
  }
  return result
})

function choose(option: Option) {
  emit('update:modelValue', option.value)
  open.value = false
}
function onOutside(event: PointerEvent) {
  if (root.value && !root.value.contains(event.target as Node)) open.value = false
}
onMounted(() => document.addEventListener('pointerdown', onOutside, true))
onBeforeUnmount(() => document.removeEventListener('pointerdown', onOutside, true))
</script>

<template>
  <div ref="root" class="style-select" :class="{ open }">
    <button type="button" class="style-select-value" v-bind="$attrs" aria-haspopup="listbox" :aria-expanded="open" @click="open = !open" @keydown.esc="open = false">
      <span class="style-select-text" :style="current?.style">{{ current?.label ?? modelValue }}</span>
      <svg class="style-select-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
    </button>
    <div v-if="open" class="style-select-popup" role="listbox">
      <template v-for="group in groups" :key="group.name || 'default'">
        <div v-if="group.name" class="style-select-group">{{ group.name }}</div>
        <button v-for="option in group.items" :key="String(option.value)" type="button" class="style-select-option" :class="{ active: option.value === modelValue }" role="option" :aria-selected="option.value === modelValue" @click="choose(option)"><span :style="option.style">{{ option.label }}</span><svg v-if="option.value === modelValue" class="style-select-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5" /></svg></button>
      </template>
    </div>
  </div>
</template>

<style scoped>
.style-select { position: relative; }
.style-select-value { display: flex; align-items: center; justify-content: space-between; gap: 6px; width: 100%; margin: 0; padding: 0; border: 0; background: transparent; color: #343944; font: inherit; font-size: 11px; text-align: left; cursor: pointer; }
.style-select-text { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.style-select-arrow { width: 12px; height: 12px; flex-shrink: 0; color: #9397a1; transition: transform .15s ease; }
.open .style-select-arrow { transform: rotate(180deg); }
.style-select-popup { position: absolute; z-index: 30; top: calc(100% + 17px); left: -9px; width: calc(100% + 18px); max-height: 216px; overflow-y: auto; margin: 0; padding: 4px; border: 1px solid var(--line); border-radius: 8px; background: #fff; box-shadow: 0 6px 24px #1f29371f; }
.style-select-group { padding: 7px 4px 3px; color: #a1a4ad; font-size: 10px; }
.style-select-option { display: flex; align-items: center; justify-content: space-between; gap: 8px; width: 100%; margin: 0; padding: 7px 4px; border: 0; border-radius: 5px; background: transparent; color: #343944; font-size: 11px; text-align: left; cursor: pointer; }
.style-select-option span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.style-select-check { width: 13px; height: 13px; flex-shrink: 0; }
.style-select-option:hover { background: #f0f1f3; }
.style-select-option.active { color: var(--blue); }
</style>
