<script setup lang="ts">
import { computed, ref } from 'vue'
import { RiCloseLine, RiArrowDownSLine } from '@remixicon/vue'
import type { Field, Page, SupplementaryRegion, SupplementaryResult, SupplementaryRole, SupplementaryRecord } from '../types/template'
import { appendSupplementaryRows, buildSupplementaryRegion, regionFieldIds } from '../utils/supplementary'
const props=defineProps<{page?:Page; selectedFields:Field[]; result?:SupplementaryResult; busy:boolean}>()
const emit=defineEmits<{configure:[region:SupplementaryRegion];removeRow:[index:number];selectRow:[index:number];correct:[recordId:string,values:Record<SupplementaryRole,string>];inspect:[record:SupplementaryRecord]}>()
const existingIds=computed(()=>regionFieldIds(props.page?.supplementaryRegion))
const onlyExisting=computed(()=>props.selectedFields.length>0 && props.selectedFields.every(f=>existingIds.value.has(f.fieldUuid)))
const draft=computed(()=> {
  if(!props.page)return {}
  const selection=buildSupplementaryRegion(props.page,props.selectedFields)
  if(!selection.region || !props.page.supplementaryRegion)return selection
  const combined=appendSupplementaryRows(props.page,selection.region)
  if(!combined.region)return {error:combined.error}
  return {region:{rows:selection.region.rows.filter(row=>!Object.values(row).flat().every(id=>existingIds.value.has(id)))}}
})
const showDraft=computed(()=>!props.page?.supplementaryRegion || (props.selectedFields.length>1 && !onlyExisting.value))
function rowSelected(index:number){const row=props.page?.supplementaryRegion?.rows[index];return !!row && props.selectedFields.some(f=>Object.values(row).flat().includes(f.fieldUuid))}
const expanded=ref<number|null>(null)
const overflowRecords=computed(()=>props.result?.records.filter(record=>!record.targetRow) || [])
function recordsFor(index:number){return props.result?.records.filter(record=>record.targetRow===index+1) || []}
function toggleRow(index:number){expanded.value=recordsFor(index).length && expanded.value!==index?index:null;editing.value='';emit('selectRow',index);const record=recordsFor(index)[0];if(expanded.value!==null && record)emit('inspect',record)}
const columns=[{key:'name',label:'项目名称及单位'},{key:'requirement',label:'规定值或允许偏差'},{key:'measurement',label:'实测值'},{key:'rate',label:'合格率'}] as const
const editing=ref(''),correction=ref<Record<SupplementaryRole,string>>({name:'',requirement:'',measurement:'',rate:''})
function edit(record:SupplementaryRecord){editing.value=record.recordId;correction.value={...record.values};emit('inspect',record)}
function apply(){emit('correct',editing.value,{...correction.value});editing.value=''}
</script>
<template>
<section v-if="page?.supplementaryRegion || selectedFields.length>1" class="property-section supplementary-panel">
  <div class="property-heading">补充检测项目</div>
  <template v-if="page?.supplementaryRegion">
    <div class="region-summary">已设置 {{ page.supplementaryRegion.rows.length }} 个预留行</div>
    <p class="region-description">固定项目匹配后，其余检测项目按来源顺序填入</p>
    <div class="reserved-rows" aria-label="已设置的预留行">
      <div v-for="(_,index) in page.supplementaryRegion.rows" :key="index" class="reserved-item" :class="{active:rowSelected(index),open:expanded===index}">
      <div class="reserved-row">
        <button class="row-select" :aria-expanded="expanded===index" @click="toggleRow(index)"><span>预留行 {{ index+1 }}<small v-if="recordsFor(index)[0]">{{ recordsFor(index)[0]?.warning ? '待处理' : recordsFor(index)[0]?.values.name }}</small></span><RiArrowDownSLine v-if="recordsFor(index).length" :class="{rotated:expanded===index}" size="16px" aria-hidden="true" /></button>
        <button class="row-remove" :disabled="busy" :aria-label="'移除预留行 '+(index+1)" title="移除预留行" @click="emit('removeRow',index)"><RiCloseLine size="16px" aria-hidden="true" /></button>
      </div>
      <div v-if="expanded===index && recordsFor(index).length" class="row-drawer">
    <div v-for="record in recordsFor(index)" :key="record.recordId" class="supplementary-record">
      <template v-if="editing===record.recordId">
        <label v-for="column in columns" :key="column.key">{{ column.label }}<textarea :aria-label="'补充项目'+column.label" v-model="correction[column.key]" rows="2" /></label>
        <div class="mapping-actions"><button class="primary" :disabled="busy" @click="apply">应用修正</button><button class="secondary" @click="editing=''">取消</button></div>
      </template>
      <template v-else>
        <div v-for="column in columns.slice(1)" :key="column.key" class="record-value"><span>{{ column.label }}</span><div>{{ record.values[column.key] || '空' }}</div></div>
        <p v-if="record.warning" class="data-error">{{ record.warning }}</p>
        <small v-if="record.corrected" class="property-hint corrected-note">已修正本次识别结果</small>
        <div class="record-actions"><button class="secondary" :disabled="busy" @click="edit(record)">修正结果</button></div>
      </template>
    </div>
      </div>
      </div>
    </div>
    <p class="append-hint">选中其他完整空白行，可继续追加</p>
  </template>
  <div v-if="showDraft" class="region-draft" :class="{appending:page?.supplementaryRegion}">
    <div v-if="page?.supplementaryRegion" class="draft-heading">追加预留行</div>
    <div v-if="draft.region" class="draft-summary">已识别 {{ draft.region.rows.length }} 个完整预留行</div>
    <p class="draft-hint">{{ draft.error || '包含项目名称、规定值、实测值和合格率四列' }}</p>
    <div class="draft-actions"><button class="primary" :disabled="!draft.region || busy" @click="draft.region && emit('configure',draft.region)">{{ page?.supplementaryRegion ? '追加到补充区域' : '设为补充项目区域' }}</button></div>
  </div>
  <template v-if="result">
    <div v-if="result.warning || overflowRecords.length" class="results-heading">待处理问题</div>
    <p v-if="result.warning" class="data-error" role="alert">{{ result.warning }}</p>
    <p v-if="!result.records.length && !result.warning" class="property-hint">当前来源没有补充检测项目</p>
    <details v-for="record in overflowRecords" :key="record.recordId" class="supplementary-record overflow-record">
      <summary class="record-heading" @click="emit('inspect',record)"><strong>{{ record.values.name || '未识别项目名称' }}</strong><small>未填入</small></summary>
      <template v-if="editing===record.recordId">
        <label v-for="column in columns" :key="column.key">{{ column.label }}<textarea :aria-label="'补充项目'+column.label" v-model="correction[column.key]" rows="2" /></label>
        <div class="mapping-actions"><button class="primary" :disabled="busy" @click="apply">应用修正</button><button class="secondary" @click="editing=''">取消</button></div>
      </template>
      <template v-else>
        <div v-for="column in columns.slice(1)" :key="column.key" class="record-value"><span>{{ column.label }}</span><div>{{ record.values[column.key] || '空' }}</div></div>
        <p v-if="record.warning" class="data-error">{{ record.warning }}</p>
        <small v-if="record.corrected" class="property-hint corrected-note">已修正本次识别结果</small>
        <div class="record-actions"><button class="secondary" :disabled="busy" @click="edit(record)">修正结果</button></div>
      </template>
    </details>
  </template>
</section>
</template>
<style scoped>
.supplementary-panel p {font-size:11px;line-height:1.7;margin:0}
.supplementary-panel button {font-size:11px}
.region-summary,.draft-summary {font-size:11px;color:#303238;line-height:1.6}
.region-description {color:#9299a4;margin-top:10px!important}
.reserved-rows {display:flex;flex-direction:column;gap:6px;margin-top:16px}
.reserved-item {border:1px solid #e8eaf0;border-radius:6px;overflow:hidden;background:#fff}
.reserved-item.open {background:#f6f7f9;border-color:transparent}
.reserved-item.active {background:#e8f1ff;border-color:transparent}
.reserved-row {display:flex;align-items:center}
.row-select {display:flex;align-items:center;justify-content:space-between;gap:10px;flex:1;min-width:0;border:0;background:transparent;padding:11px 10px;text-align:left;color:#454c57}
.row-select svg {color:#9ba3af;transition:transform .15s}
.row-select svg.rotated {transform:rotate(180deg)}
.row-select small {display:block;color:#9299a4;font-size:10px;margin-top:4px}
.row-drawer {padding:0 10px 12px}
.row-drawer .supplementary-record {margin-top:0;border-top:0;padding-top:12px}
.row-remove {display:flex;align-items:center;justify-content:center;width:34px;align-self:stretch;border:0;background:transparent;color:#9ba3af}
.row-remove:hover:not(:disabled) {background:#feecec;color:#cf4545}
.append-hint {color:#9299a4;margin-top:12px!important}
.region-draft {margin-top:2px}
.region-draft.appending {border-top:1px solid #e8eaf0;padding-top:16px;margin-top:16px}
.draft-heading {font-size:11px;font-weight:500;margin-bottom:10px}
.draft-hint {color:#9299a4;margin-top:10px!important}
.draft-actions {margin-top:18px}
.draft-actions .primary {padding:10px 12px}
.results-heading {font-size:11px;font-weight:500;border-top:1px solid #e8eaf0;margin-top:16px;padding-top:16px}
.supplementary-record {border-top:1px solid #e8eaf0;margin-top:16px;padding-top:12px}
.record-heading {display:flex;align-items:center;justify-content:space-between;gap:8px;border:0;background:transparent;width:100%;text-align:left;padding-left:0!important}
.record-heading strong {font-weight:500;overflow-wrap:anywhere}
.record-heading small,.record-value>span {color:#9097a1;font-size:10px}
.record-value {margin:8px 0;font-size:11px}
.record-value>div {white-space:pre-wrap;overflow-wrap:anywhere;margin-top:4px}
.supplementary-record label {display:block;color:#9097a1;font-size:11px;margin:10px 0}
.supplementary-record textarea {display:block;width:100%;margin-top:6px;border:1px solid #dfe2e8;border-radius:5px;padding:8px;font:inherit;color:#303238;resize:vertical}
.supplementary-record textarea:focus {outline:none;border-color:#0d75ed}
.data-error {color:#c25043;font-size:11px;line-height:1.7}
.mapping-actions {display:flex;gap:8px}
.record-actions {margin-top:12px}
.corrected-note {display:block;margin-top:10px}
.overflow-record summary {cursor:pointer;padding:8px 0}
.overflow-record:not([open]) {padding-top:4px;margin-top:8px}
</style>
