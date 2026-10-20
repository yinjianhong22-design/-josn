<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RiImageCircleLine, RiCursorHand } from '@remixicon/vue'
import StyleSelect from './StyleSelect.vue'
import { displayFieldValue } from '../utils/fieldValue'
import type { Field, FieldDefinition, SourceMapping, BusinessField, MappingRule } from '../types/template'
const props = defineProps<{ selected?: Field; supplementarySelected?:boolean; hasSupplementary?:boolean; selectionCount: number; hasTemplate: boolean; sampleName: string; sampleError: string; selectingSource: boolean; recognizing: boolean; recognized: boolean; canRecognize: boolean; mapping?: SourceMapping; mappingFields: Field[]; picking: boolean; trial: boolean; trialMatching: boolean; sheetName: string; sheetError: string; sheetMatching: boolean; sheetResult?: { title: string | null; fields: Record<string, unknown>[]; values: Record<string, string>; unmatched: string[] } }>()
const emit = defineEmits<{ upload: []; remove: []; configure: [patch: Partial<FieldDefinition>]; configureRule:[rule:MappingRule]; correct:[text:string]; recognize: []; pick: []; cancelPick: []; confirm: []; trial: []; selectField: [field:Field]; 'upload-sheet': []; 'match-sheet': [] }>()
const draft = computed<FieldDefinition | undefined>(() => props.selected && props.selectionCount === 1 ? props.selected.definition || {name:'',dataType:'text',imageRecognition:true} : undefined)
const showRule=ref(false),editing=ref(false),correction=ref('')
watch(()=>props.selected?.fieldUuid,()=>{showRule.value=false;editing.value=false})
watch(()=>props.mapping,()=>{editing.value=false})
const problemCount=computed(()=>props.mappingFields.filter(field=>field.mapping?.warning || field.mapping?.status==='unmatched').length)
const rule = computed(() => (props.selected?.definition as BusinessField | undefined)?.mappingRule || props.mapping?.proposedRule)
const columns=[{value:'measurement',label:'实测值'},{value:'rate',label:'合格率'},{value:'requirement',label:'规定值或允许偏差'}]
const types=[{value:'text',label:'文本'},{value:'number',label:'数字'},{value:'percent',label:'百分比'},{value:'date',label:'日期'}]
function editRule(patch:Partial<MappingRule>){if(rule.value)emit('configureRule',{...rule.value,kind:'semantic',...patch})}
function editResult(){correction.value=props.mapping?.text ? displayFieldValue(props.mapping.text,draft.value?.dataType) : '';editing.value=true}
function state(mapping?:SourceMapping){return !mapping ? '未识别' : mapping.status==='unmatched' ? '未找到' : mapping.warning ? '待修正' : mapping.status==='empty' ? '来源为空' : mapping.corrected ? '已修正' : mapping.confirmed ? mapping.method==='业务含义匹配' ? '已匹配' : '已核对' : '待核对'}
</script>
<template>
<div class="data-panel">
  <section v-if="selectionCount <= 1 && !supplementarySelected && (!hasSupplementary || selected)" class="property-section">
    <div class="property-heading">字段定义<span v-if="draft">当前选中区域</span></div>
    <template v-if="draft">
      <div class="data-form-label"><span>字段名称</span><input :value="draft.name" @input="emit('configure',{name:($event.target as HTMLInputElement).value})" @blur="emit('configure',{name:draft.name.trim()})" aria-label="字段名称" placeholder="例如：施工单位" /></div>
      <div class="data-form-label"><span>数据类型</span><StyleSelect aria-label="字段数据类型" :model-value="draft.dataType" :options="types" @update:model-value="emit('configure',{dataType:$event as FieldDefinition['dataType']})" /></div>
      <label class="data-checkbox"><input type="checkbox" :checked="draft.imageRecognition" @change="emit('configure',{imageRecognition:($event.target as HTMLInputElement).checked})" />参与图片识别回填</label>
      <template v-if="rule?.kind==='semantic'">
        <button class="text-button rule-toggle" @click="showRule=!showRule">{{ showRule ? '收起识别依据' : '调整识别依据' }}</button>
        <div v-if="showRule" class="rule-editor">
          <template v-if="rule.rowLabel">
            <div class="data-form-label"><span>检测项目</span><input aria-label="检测项目" :value="rule.rowLabel" @change="editRule({rowLabel:($event.target as HTMLInputElement).value.trim()})" /></div>
            <div class="data-form-label"><span>数据列</span><StyleSelect aria-label="数据列" :model-value="rule.column || 'measurement'" :options="columns" @update:model-value="editRule({column:$event as MappingRule['column']})" /></div>
          </template>
          <div v-else class="data-form-label"><span>来源标签</span><input aria-label="来源标签" :value="rule.label" @change="editRule({label:($event.target as HTMLInputElement).value.trim()})" /></div>
          <div class="data-form-label"><span>其他叫法</span><input aria-label="其他叫法" :value="(rule.rowLabel ? rule.rowAliases : rule.aliases)?.join('、') || ''" placeholder="多个名称用顿号分隔" @change="editRule(rule.rowLabel ? {rowAliases:($event.target as HTMLInputElement).value.split(/[、,，]/).map(x=>x.trim()).filter(Boolean)} : {aliases:($event.target as HTMLInputElement).value.split(/[、,，]/).map(x=>x.trim()).filter(Boolean)})" /></div>
        </div>
      </template>
    </template>
    <div v-else class="data-selection-empty"><RiCursorHand size="24px" aria-hidden="true" /><strong>{{ selectionCount>1 ? '请单独选择一个填写区域' : '选择模板中的填写区域' }}</strong><p>点击一个空白格，在这里设置字段名称和数据类型</p></div>
  </section>
  <section v-if="recognized" class="property-section">
    <div class="property-heading">识别结果<span v-if="draft">{{ state(mapping) }}</span></div>
    <template v-if="draft?.name.trim() && draft.imageRecognition">
      <template v-if="editing">
        <textarea class="correction-input" aria-label="修正本次结果" v-model="correction" rows="3" />
        <div class="mapping-actions"><button class="primary" :disabled="selectingSource || trialMatching" @click="emit('correct',correction)">应用修正</button><button class="secondary" @click="editing=false">取消</button></div>
      </template>
      <template v-else>
        <div class="mapping-value">{{ mapping?.text ? displayFieldValue(mapping.text,draft.dataType) : mapping?.status==='unmatched' ? '未找到对应内容' : '未读取到填写内容' }}</div>
        <small v-if="mapping?.corrected" class="original-value">OCR 原文：{{ mapping.rawText || '空' }}</small>
        <p v-if="mapping?.warning" class="data-error">{{ mapping.warning.replace(/。/g, '') }}</p>
        <div class="mapping-actions"><button class="secondary" :disabled="trialMatching || selectingSource || !mapping?.sourceRect" @click="editResult">修正结果</button><button class="secondary" :disabled="trialMatching" @click="emit('pick')">重新选取</button></div>
      </template>
      <div v-if="picking" class="source-pick-controls"><p class="property-hint">点击左侧来源格或识别文字；按住 Shift 多选，或拖动框选</p><div class="mapping-actions"><button v-if="mapping?.method==='人工选取' && !mapping.confirmed" class="primary" :disabled="selectingSource || !!mapping.warning" @click="emit('confirm')">确认选取</button><button class="secondary" @click="emit('cancelPick')">结束选取</button></div></div>
    </template>
    <p v-else class="property-hint">选择需要检查的目标字段</p>
    <details class="field-results"><summary>字段结果 <small>{{ mappingFields.length }} 项<span v-if="problemCount"> · {{ problemCount }} 项待检查</span></small></summary><div class="mapping-list"><button v-for="field in mappingFields" :key="field.fieldUuid" :class="{active:selected?.businessFieldUuid===field.businessFieldUuid}" @click="emit('selectField',field)"><span>{{ field.definition?.name }}</span><small>{{ state(field.mapping) }}</small></button></div></details>
    <div class="mapping-actions"><button class="secondary" :disabled="trialMatching || recognizing || selectingSource || (!trial && !mappingFields.length && !hasSupplementary)" @click="emit('trial')">{{ trialMatching ? '正在试填…' : trial ? '退出试填' : '试填预览' }}</button></div>
    <p v-if="trial" class="property-hint">正在试填预览，退出后恢复模板内容</p>
  </section>
  <section class="property-section">
    <div class="property-heading">数据简表</div>
    <template v-if="sheetName"><div class="data-sample-file"><RiImageCircleLine size="20px" aria-hidden="true" /><span :title="sheetName">{{ sheetName }}</span></div><div class="data-sample-actions"><button class="secondary" @click="emit('upload-sheet')">更换简表</button></div></template>
    <button v-else class="data-upload" @click="emit('upload-sheet')"><RiImageCircleLine size="28px" aria-hidden="true" /><strong>上传数据简表</strong><span>按表名 / 编号自动匹配模板 (.xlsx / 已填表照片)</span></button>
    <button v-if="sheetName" class="primary recognize-action" :disabled="sheetMatching" @click="emit('match-sheet')">{{ sheetMatching ? '正在匹配…' : '重新匹配填值' }}</button>
    <details v-if="sheetResult" class="field-results"><summary>匹配结果 <small>{{ Object.keys(sheetResult.values).length }} 个值<span v-if="sheetResult.unmatched.length"> · {{ sheetResult.unmatched.length }} 项未匹配</span></small></summary>
      <div class="mapping-list sheet-result"><p class="property-hint">标题:{{ sheetResult.title || '未识别' }} · 字段 {{ sheetResult.fields.length }} 个</p><p v-if="sheetResult.unmatched.length" class="data-error">未匹配: {{ sheetResult.unmatched.join('、') }}</p></div>
    </details>
    <p v-if="sheetError" class="data-error" role="alert">{{ sheetError.replace(/。/g, '') }}</p>
  </section>
</div>
</template>
<style scoped>
.data-form-label { display: flex; flex-direction: column; gap: 9px; margin-bottom: 18px; color: #898f99; font-size: 11px; }
.data-form-label > input { width: 100%; border: 1px solid transparent; border-radius: 5px; padding: 10px; background: #f5f5f6; font: inherit; color: #303238; }
.data-form-label > input:focus { outline: none; border-color: #0d75ed; }
.data-form-label > input::placeholder { color: #a0a4ad; }
.data-form-label :deep(.style-select-value) { background: #f5f5f6; padding: 10px; border-radius: 5px; }
.data-form-label :deep(.style-select-popup) { top: calc(100% + 5px); left: 0; width: 100%; }
.data-form-label :deep(.style-select-option) { padding-left: 5px; padding-right: 5px; }
.data-checkbox { display: flex; align-items: center; gap: 6px; font-size: 11px; margin: 4px 0 18px; }
.data-target { display: flex; flex-direction: column; gap: 8px; border-top: 1px solid #ededf0; padding-top: 15px; font-size: 11px; }
.data-target span { color: #969ba5; }
.data-target strong { font-weight: 400; overflow-wrap: anywhere; }
.data-selection-empty { display: flex; align-items: center; flex-direction: column; text-align: center; padding: 18px 8px 10px; color: #9a9faa; gap: 10px; }
.data-selection-empty strong { color: #727985; font-weight: 400; }
.data-selection-empty p { margin: 0; font-size: 11px; line-height: 1.8; }
.data-upload { width: 100%; display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 26px 10px; border: 1px dashed #ccd5e0; border-radius: 7px; background: #fafbfd; color: #6983a1; }
.data-upload:hover:not(:disabled) { border-color: #0d75ed; background: #f3f7ff; }
.data-upload strong { font-size: 12px; font-weight: 500; color: #4c6482; }
.data-upload span { font-size: 10px; color: #9a9faa; }
.data-sample-file { display: flex; align-items: center; gap: 8px; background: #f5f5f6; padding: 12px 10px; border-radius: 5px; }
.data-sample-file svg { flex-shrink: 0; color: #8b99ab; }
.data-sample-file span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; }
.data-sample-actions { display: flex; gap: 8px; margin-top: 12px; }
.property-hint { line-height: 1.7; }
.data-error { color: #c25043; font-size: 11px; }
.mapping-value { padding:12px; border-radius:5px; background:#f5f5f6; white-space:pre-wrap; overflow-wrap:anywhere; min-height:42px; }
.mapping-actions { display:flex; gap:8px; margin-top:12px; }
.mapping-actions button { font-size:11px; padding:8px; }
.field-results {margin-top:16px;border:1px solid #e8eaf0;border-radius:6px;padding:8px}
.field-results summary {cursor:pointer;font-size:11px;padding:4px}
.field-results summary small {color:#9198a4;font-size:10px}
.field-results .mapping-list {max-height:240px;overflow-y:auto;margin-top:8px}
.mapping-list { margin-top:16px; display:flex; flex-direction:column; gap:3px; }
.mapping-list button { display:flex; align-items:center; justify-content:space-between; gap:8px; background:transparent; border:0; padding:9px 6px; text-align:left; border-radius:4px; font-size:11px; }
.mapping-list button.active { background:#e8f1ff; }
.mapping-list button span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.mapping-list small { color:#9198a4; flex-shrink:0; }
.recognize-action { margin-top:14px; width:100%; }
</style>

<style scoped>
.source-pick-controls { margin:16px 0; }
.source-pick-controls .property-hint { margin:0 0 10px; }
.source-pick-controls button { display:block; margin:0; font-size:11px; padding:8px; }
</style>

<style scoped>
.mapping-rule { display:flex; flex-direction:column; gap:6px; margin-bottom:12px; font-size:11px; }
.mapping-rule span,.mapping-rule small { color:#9299a4; }
.mapping-rule strong { font-weight:400; }
</style>

<style scoped>
.rule-toggle { display:block; padding:0; font-size:11px; color:#7b8492; margin:12px 0; }
.rule-editor { margin-top:14px; }
.correction-input { width:100%; resize:vertical; padding:10px; font:inherit; font-size:11px; border:1px solid #dfe2e8; border-radius:5px; }
.correction-input:focus { outline:none; border-color:#0d75ed; }
.original-value { display:block; font-size:10px; color:#9198a4; margin:8px 0; white-space:pre-wrap; }
</style>
