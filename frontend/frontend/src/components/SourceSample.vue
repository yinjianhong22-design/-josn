<script setup lang="ts">
import { ref } from 'vue'
import type { Rect, SampleResult, SourceMapping } from '../types/template'
const props = defineProps<{ url: string; sample?: SampleResult; mapping?: SourceMapping; picking: boolean; selectedIds: string[] }>()
const emit = defineEmits<{ text: [id: string, multiple: boolean]; area: [rect: Rect] }>()
const root = ref<HTMLElement>()
const drag = ref<Rect>()
let start: { x: number; y: number } | undefined
function point(event: PointerEvent) { const box = root.value!.getBoundingClientRect(); return { x: Math.max(0, Math.min(1,(event.clientX-box.left)/box.width)), y: Math.max(0,Math.min(1,(event.clientY-box.top)/box.height)) } }
function down(event: PointerEvent) { if (!props.picking || event.button !== 0) return; event.preventDefault(); event.stopPropagation(); start=point(event); root.value!.setPointerCapture(event.pointerId) }
function move(event: PointerEvent) { if (!start) return; const p=point(event); drag.value={x:Math.min(start.x,p.x),y:Math.min(start.y,p.y),w:Math.abs(start.x-p.x),h:Math.abs(start.y-p.y)} }
function up(event: PointerEvent) { if (!start) return; move(event); if (drag.value && drag.value.w>.003 && drag.value.h>.003) emit('area',drag.value); else { const p=point(event); const cell=props.sample?.tables?.flatMap(table=>table.cells).filter(cell=>p.x>=cell.rect.x && p.x<=cell.rect.x+cell.rect.w && p.y>=cell.rect.y && p.y<=cell.rect.y+cell.rect.h).sort((a,b)=>a.rect.w*a.rect.h-b.rect.w*b.rect.h)[0]; if(cell) emit('area',cell.rect) } start=undefined;drag.value=undefined }
function style(rect: Rect) { return {left:rect.x*100+'%',top:rect.y*100+'%',width:rect.w*100+'%',height:rect.h*100+'%'} }
</script>
<template>
 <div ref="root" class="source-sample" :class="{ picking }" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="start=undefined;drag=undefined">
  <img :src="url" alt="样例图片" draggable="false" />
  <template v-if="picking"><button v-for="cell in sample?.tables?.flatMap(table => table.cells) || []" :key="cell.cellUuid" class="source-cell" :style="style(cell.rect)" :aria-label="'选取来源单元格：'+(cell.text || '空白格')"></button><button v-for="item in sample?.textItems || []" :key="item.textUuid" class="source-text" :class="{ chosen: selectedIds.includes(item.textUuid) }" :style="style(item.rect)" :aria-label="'选取来源：'+item.text" @pointerdown.stop @click.stop="emit('text',item.textUuid,$event.shiftKey || $event.ctrlKey)"></button></template>
  <div v-if="mapping?.sourceRect" class="source-highlight" :style="style(mapping.sourceRect)"></div>
  <div v-if="drag" class="source-highlight drawing" :style="style(drag)"></div>
 </div>
</template>
<style scoped>
.source-sample { position:relative; width:100%; }
img { display:block; width:100%; user-select:none; }
.picking { cursor:crosshair; touch-action:none; }
.source-cell { position:absolute; border:1px solid transparent; background:transparent; padding:0; border-radius:0; cursor:pointer; }
.source-cell:hover { border-color:#0d75ed; background:#0d75ed12; }
.source-text { position:absolute; border:1px solid #658ec280; background:#0d75ed05; padding:0; border-radius:0; cursor:pointer; }
.source-text:hover,.source-text.chosen { border-color:#0d75ed; background:#0d75ed22; }
.source-highlight { position:absolute; border:2px solid #0d75ed; background:#0d75ed12; pointer-events:none; }
.drawing { border-style:dashed; }
</style>
