<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import {
  RiFilePaper2Line, RiBrushAiLine,
  RiDraggable, RiSendPlaneLine, RiHand, RiSubtractLine, RiAddLine,
  RiCloseLine, RiFullscreenLine, RiLoader4Line, RiDeleteBinLine,
  RiAlignLeft, RiAlignCenter, RiAlignRight, RiAlignTop, RiAlignVertically, RiAlignBottom,
} from '@remixicon/vue'
import TemplatePage from '../components/TemplatePage.vue'
import SourceSample from '../components/SourceSample.vue'
import DataPanel from '../components/DataPanel.vue'
import SupplementaryPanel from '../components/SupplementaryPanel.vue'
import { appendSupplementaryRows, regionFieldIds } from '../utils/supplementary'
import PrintPreview from '../components/PrintPreview.vue'
import ColorPicker from '../components/ColorPicker.vue'
import StyleSelect from '../components/StyleSelect.vue'
import { allAnchors, syncBindings, migrateBindings, setPreview, templateForSave } from '../utils/businessFields'
import { displayFieldValue } from '../utils/fieldValue'
import { underlineRanges, rangeUnderlined, toggleRange, editedRanges } from '../utils/textUnderline'
import { mergeBounds, mergeMasks } from '../utils/merge'
import { documentFonts, fontKey, fontStack, namedFontSizes, pointFontSizes } from '../utils/fonts'
import { imageUrl, listTemplates, loadTemplate, saveTemplate, uploadTemplate, recognizeSample, getSample, selectSample, correctSample, matchSample, deleteTemplate } from '../api/template'
import type { SupplementaryRegion, SupplementaryResult, SupplementaryRole, SupplementaryRecord, MappingRule, Field, FieldDefinition, FieldStyle, SampleResult, SourceMapping, Page, Rect, Template, TemplateSummary } from '../types/template'

const template = ref<Template>()
const library = ref<TemplateSummary[]>([])
const pageIndex = ref(0)
const zoom = ref(100)
const selectedFields = ref<Field[]>([])
const selected = computed(() => selectedFields.value[0])
const selectedIds = computed(() => selectedFields.value.map(field => field.fieldUuid))
const rectKeys: (keyof Rect)[] = ['x', 'y', 'w', 'h']
const rectInputs = reactive<Record<keyof Rect, string>>({ x: '', y: '', w: '', h: '' })
type SplitDraft = { fieldUuid: string; axis: 'x' | 'y'; position: number }
const splitDraft = ref<SplitDraft>()
const labelDraft = ref('')
const labelInput = ref<HTMLTextAreaElement>()
const labelSelection = ref({start:0,end:0})
function rememberTextSelection() {
  labelSelection.value={start:labelInput.value?.selectionStart || 0,end:labelInput.value?.selectionEnd || 0}
}
const underlineActive = computed(() => {
  const field=selected.value
  if(!field)return false
  const text=field.textOverride ?? field.label ?? ''
  const {start,end}=labelSelection.value
  return rangeUnderlined(underlineRanges(field),end>start?start:0,end>start?end:text.length)
})
watch(() => {
  const field = selected.value
  return field ? [field.fieldUuid, field.rect.x, field.rect.y, field.rect.w, field.rect.h, field.label, field.textOverride] : []
}, () => {
  const field = selected.value
  for (const key of rectKeys) rectInputs[key] = field ? (field.rect[key] * 100).toFixed(2) : ''
  labelDraft.value = field?.textOverride ?? field?.label ?? ''
  labelSelection.value={start:0,end:0}
}, { immediate: true })
const showRegions = ref(true)
const showBackground = ref(true)
const busy = ref(false)
const saved = ref(false)
const error = ref('')
const notice = ref('')
const jsonOpen = ref(false)
const printOpen = ref(false)
const libraryTab = ref<'pages' | 'templates'>('pages')
const tool = ref<'select' | 'hand'>('select')
const canvas = ref<HTMLDivElement>()
const inspectorTab = ref<'properties' | 'data'>('properties')
const sampleInput = ref<HTMLInputElement>()
const sampleUrl = ref('')
const sampleName = ref('')
const sampleError = ref('')
const sampleFile = ref<File>()
const sampleResult = ref<SampleResult>()
const recognizing = ref(false)
const picking = ref(false)
const selectingSource = ref(false)
let sourceRequest = 0
const sourceTextIds = ref<string[]>([])
const trial = ref(false)
const trialMatching = ref(false)
let sampleGeneration = 0
const supplementaryResult=ref<SupplementaryResult>()
const supplementaryCorrections=ref<Record<string,Partial<Record<SupplementaryRole,string>>>>({})
const inspectedSupplementary=ref<SupplementaryRecord>()
const supplementaryIds=computed(()=>regionFieldIds(page.value?.supplementaryRegion))
const supplementarySelected=computed(()=>selectedFields.value.some(f=>supplementaryIds.value.has(f.fieldUuid)))
const currentMapping = computed(() => inspectedSupplementary.value ? {sampleId:sampleResult.value?.sampleId || '',sourceRect:inspectedSupplementary.value.sourceRects.name,textIds:[],text:'',warning:'',status:'pending' as const,confirmed:false} : selected.value?.mapping?.sampleId === sampleResult.value?.sampleId ? selected.value?.mapping : undefined)
function configureSupplementary(region:SupplementaryRegion) {
  if(!page.value)return
  const combined=appendSupplementaryRows(page.value,region)
  if(!combined.region){error.value=combined.error || '追加预留行失败';return}
  page.value.supplementaryRegion=combined.region;trial.value=false;supplementaryResult.value=undefined;inspectedSupplementary.value=undefined;saved.value=false;error.value=''
  selectedFields.value=fields.value.filter(f=>regionFieldIds(region).has(f.fieldUuid))
}
function removeSupplementary() {
  if(!page.value)return
  delete page.value.supplementaryRegion;supplementaryResult.value=undefined;supplementaryCorrections.value={};inspectedSupplementary.value=undefined;trial.value=false;saved.value=false
}
function removeSupplementaryRow(index:number) {
  const region=page.value?.supplementaryRegion
  if(!region)return
  region.rows.splice(index,1)
  if(!region.rows.length){removeSupplementary();return}
  const ids=regionFieldIds(region)
  selectedFields.value=selectedFields.value.filter(f=>ids.has(f.fieldUuid))
  supplementaryResult.value=undefined;inspectedSupplementary.value=undefined;trial.value=false;saved.value=false
}
function selectSupplementaryRow(index:number) {
  const row=page.value?.supplementaryRegion?.rows[index]
  if(row){const ids=new Set(Object.values(row).flat());selectedFields.value=fields.value.filter(f=>ids.has(f.fieldUuid))}
}
function inspectSupplementary(record:SupplementaryRecord) {
  inspectedSupplementary.value=record
  if(record.targetRow)selectSupplementaryRow(record.targetRow-1)
  else selectedFields.value=[]
}
async function correctSupplementary(recordId:string,values:Record<SupplementaryRole,string>) {
  supplementaryCorrections.value[recordId]=values;trial.value=false;await toggleTrialPreview()
  inspectedSupplementary.value=supplementaryResult.value?.records.find(r=>r.recordId===recordId)
}
function protectSupplementary(items:Field[]) {
  if(items.some(f=>supplementaryIds.value.has(f.fieldUuid))) {error.value='请先在数据面板取消补充区域设置，再调整区域结构';return true}
  return false
}
const businessFields = computed(() => template.value?.businessFields || [])
const mappingFields = computed(() => fields.value.filter((field,index,array) => field.definition?.name.trim() && field.definition.imageRecognition && array.findIndex(other=>other.businessFieldUuid===field.businessFieldUuid)===index))
const trialValues = computed(() => trial.value ? {...Object.fromEntries(fields.value.filter(field => field.definition?.imageRecognition && field.mapping?.sampleId === sampleResult.value?.sampleId && field.mapping?.confirmed && field.mapping.text && !field.mapping.warning).map(field => [field.fieldUuid, displayFieldValue(field.mapping!.text, field.definition?.dataType)])), ...supplementaryResult.value?.values} : undefined)
function applySuggestions(suggestions: Record<string,SourceMapping>) {
  for(const field of fields.value) {
    const mapping=suggestions[field.fieldUuid]
    if(!mapping)continue
    const business=businessFields.value.find(item=>item.businessFieldUuid===field.businessFieldUuid)
    if(business && business.mappingRule?.kind!=='semantic' && mapping.proposedRule?.kind==='semantic')business.mappingRule=JSON.parse(JSON.stringify(mapping.proposedRule))
    setPreview(template.value!,field,mapping)
  }
}
function configureRecognitionRule(rule: MappingRule) {
  const business=businessFields.value.find(item=>item.businessFieldUuid===selected.value?.businessFieldUuid)
  if(!business || !template.value)return
  business.mappingRule=rule
  if(template.value.mappingPreview)delete template.value.mappingPreview.results[business.businessFieldUuid]
  syncBindings(template.value);trial.value=false;saved.value=false
}
async function correctRecognition(text: string) {
  const anchor=selected.value, mapping=currentMapping.value,sample=sampleResult.value,currentTemplate=template.value
  if(!anchor?.definition || !mapping?.sourceRect || !sample || !currentTemplate || selectingSource.value)return
  const generation=sampleGeneration,requestId=++sourceRequest
  selectingSource.value=true;sampleError.value=''
  try {
    const corrected=await correctSample(sample.sampleId,anchor.definition,mapping,text)
    if(generation!==sampleGeneration || requestId!==sourceRequest || selected.value!==anchor)return
    setPreview(currentTemplate,anchor,corrected)
  } catch(e) { if(requestId===sourceRequest)sampleError.value=(e as Error).message }
  finally { if(requestId===sourceRequest)selectingSource.value=false }
}
async function recognizeUploadedSample() {
  if (!sampleFile.value || !page.value || recognizing.value || selectingSource.value || trialMatching.value) return
  sourceRequest++
  const generation = ++sampleGeneration
  recognizing.value = true; sampleError.value = ''; picking.value = false; trial.value = false
  const recognitionPage=page.value, configuration=JSON.stringify(recognitionPage)
  try {
    const job = await recognizeSample(sampleFile.value, recognitionPage)
    while (generation === sampleGeneration) {
      const state = await getSample(job.sampleId)
      if (generation !== sampleGeneration) return
      if (state.state === 'failed') throw new Error(state.error || '识别失败')
      if (state.state === 'done' && state.result) {
        const currentPage=page.value
        if(!currentPage)return
        const currentConfiguration=JSON.stringify(currentPage)
        let suggestions=state.result.suggestions
        if(currentPage!==recognitionPage || currentConfiguration!==configuration) {
          const matched=await matchSample(job.sampleId,currentPage)
          if(generation!==sampleGeneration)return
          state.result.supplementary=matched.supplementary
          suggestions=page.value===currentPage && JSON.stringify(currentPage)===currentConfiguration ? matched.suggestions : {}
        }
        sampleResult.value = state.result
        supplementaryResult.value=state.result.supplementary || undefined
        applySuggestions(suggestions)
        recognizing.value=false
        await toggleTrialPreview()
        saved.value = false
        return
      }
      await new Promise(resolve => setTimeout(resolve,1500))
    }
  } catch (e) { if (generation === sampleGeneration) sampleError.value = (e as Error).message }
  finally { if (generation === sampleGeneration) recognizing.value = false }
}
async function chooseSource(selection: {rect?:Rect; textIds?:string[]}) {
  const field = selected.value, sample = sampleResult.value
  if (!field?.definition || !sample || !picking.value || trialMatching.value) return
  const generation = sampleGeneration, requestId = ++sourceRequest
  selectingSource.value = true
  try {
    const mapping = await selectSample(sample.sampleId, field.definition, selection, template.value ? allAnchors(template.value).map(anchor=>anchor.label || '').filter(Boolean) : [])
    if (generation !== sampleGeneration || selected.value !== field || requestId !== sourceRequest) return
    setPreview(template.value!,field,mapping); saved.value = false; sampleError.value = ''
  } catch (e) { if (requestId === sourceRequest) sampleError.value = (e as Error).message }
  finally { if (requestId === sourceRequest) selectingSource.value = false }
}
function chooseSourceText(id: string, multiple: boolean) {
  sourceTextIds.value = multiple ? sourceTextIds.value.includes(id) ? sourceTextIds.value.filter(item=>item!==id) : [...sourceTextIds.value,id] : [id]
  if (sourceTextIds.value.length) void chooseSource({textIds:sourceTextIds.value})
}
async function confirmMapping() {
  let mapping=currentMapping.value
  const anchor=selected.value, sample=sampleResult.value, currentTemplate=template.value
  const business=businessFields.value.find(field=>field.businessFieldUuid===anchor?.businessFieldUuid)
  if(selectingSource.value || !mapping || mapping.warning || !business || !anchor || !sample || !currentTemplate)return
  if(!mapping.proposedRule && mapping.sourceRect) {
    const generation=sampleGeneration
    selectingSource.value=true
    try {
      mapping=await selectSample(sample.sampleId,business,{rect:mapping.sourceRect},allAnchors(currentTemplate).map(field=>field.label || '').filter(Boolean))
      if(generation!==sampleGeneration || selected.value!==anchor)return
      setPreview(currentTemplate,anchor,mapping)
    } catch(e) { sampleError.value=(e as Error).message;return }
    finally { selectingSource.value=false }
  }
  if(mapping.proposedRule?.kind==='semantic')business.mappingRule=JSON.parse(JSON.stringify(mapping.proposedRule))
  mapping.confirmed=true;picking.value=false;saved.value=false
}

async function toggleTrialPreview() {
  if(trialMatching.value || recognizing.value || selectingSource.value)return
  if(trial.value) { trial.value=false;return }
  const sample=sampleResult.value, currentPage=page.value, currentTemplate=template.value
  if(!sample || !currentPage || !currentTemplate)return
  const pending= mappingFields.value.find(field=>field.mapping?.sampleId===sample.sampleId && field.mapping.method==='人工选取' && !field.mapping.confirmed)
  if(pending) {
    selectedFields.value=[pending];picking.value=true
    sampleError.value='请先确认当前手动选取，再进行试填预览'
    return
  }
  const targets=mappingFields.value
  const generation=sampleGeneration, snapshot=JSON.stringify(currentPage)
  trialMatching.value=true;sampleError.value='';picking.value=false
  try {
    const result=await matchSample(sample.sampleId,currentPage,supplementaryCorrections.value)
    if(generation!==sampleGeneration || page.value!==currentPage || template.value!==currentTemplate)return
    if(JSON.stringify(currentPage)!==snapshot) { sampleError.value='字段配置已变化，请重新进行试填预览';return }
    let failed=0
    for(const field of targets) {
      const previous=field.mapping
      const preserve=previous?.sampleId===sample.sampleId && previous.confirmed && (previous.corrected || previous.method==='人工选取')
      const mapping=(preserve ? previous : result.suggestions[field.fieldUuid]) || {sampleId:sample.sampleId,sourceRect:null,textIds:[],text:'',warning:'未找到规则对应的来源',status:'unmatched' as const,confirmed:false}
      mapping.confirmed=!mapping.warning && mapping.status!=='unmatched' && !!mapping.sourceRect
      if(!mapping.confirmed)failed++
      const business=businessFields.value.find(item=>item.businessFieldUuid===field.businessFieldUuid)
      if(business && business.mappingRule?.kind!=='semantic' && mapping.proposedRule?.kind==='semantic')business.mappingRule=JSON.parse(JSON.stringify(mapping.proposedRule))
      setPreview(currentTemplate,field,mapping)
    }
    if(result.source && sampleResult.value)Object.assign(sampleResult.value,result.source)
    supplementaryResult.value=result.supplementary || undefined
    trial.value=true;saved.value=false
    if(failed)sampleError.value=`${failed} 个字段未通过规则定位或数据校验，请在字段列表中检查`
  } catch(e) { if(generation===sampleGeneration)sampleError.value=(e as Error).message }
  finally { if(generation===sampleGeneration)trialMatching.value=false }
}

function beginSourceSelection() { picking.value=true;sourceTextIds.value=[];trial.value=false }
let sampleHeightRatio = 1.414
function removeSample() {
  if(template.value) { delete template.value.mappingPreview;delete template.value.mappingScheme;syncBindings(template.value) }
  supplementaryResult.value=undefined;supplementaryCorrections.value={};inspectedSupplementary.value=undefined
  sourceRequest++;trialMatching.value=false;selectingSource.value=false
  sampleGeneration++; recognizing.value=false;sampleFile.value=undefined;sampleResult.value=undefined;picking.value=false;trial.value=false
  if (sampleUrl.value.startsWith('blob:')) URL.revokeObjectURL(sampleUrl.value)
  sampleUrl.value = ''
  sampleName.value = ''
  sampleError.value = ''
}
async function showSample(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = ''
  if (!file.type.startsWith('image/')) { sampleError.value = '请选择有效的图片文件'; return }
  const url = URL.createObjectURL(file)
  const image = new Image()
  image.src = url
  try {
    await image.decode()
    removeSample()
    sampleFile.value = file
    sampleUrl.value = url
    sampleName.value = file.name
    sampleHeightRatio = image.naturalHeight / image.naturalWidth
    await nextTick()
    fitPage()
    if (canvas.value) { canvas.value.scrollLeft = 0; canvas.value.scrollTop = 0 }
  } catch {
    URL.revokeObjectURL(url)
    sampleError.value = '无法读取这张图片，请更换 PNG、JPG 或 WebP 图片'
  }
}
onUnmounted(removeSample)
const panning = ref(false)
let dragStart = { x: 0, y: 0, left: 0, top: 0 }

function startPan(event: PointerEvent) {
  if (tool.value !== 'hand' || !canvas.value || event.button !== 0) return
  panning.value = true
  dragStart = { x: event.clientX, y: event.clientY, left: canvas.value.scrollLeft, top: canvas.value.scrollTop }
  canvas.value.setPointerCapture(event.pointerId)
}
function movePan(event: PointerEvent) {
  if (!panning.value || !canvas.value) return
  canvas.value.scrollLeft = dragStart.left - event.clientX + dragStart.x
  canvas.value.scrollTop = dragStart.top - event.clientY + dragStart.y
}
async function zoomWithWheel(event: WheelEvent) {
  if (!event.ctrlKey) return
  event.preventDefault()
  const element = canvas.value
  const artboard = element?.querySelector<HTMLElement>('.document-page')
  if (!element || !artboard || !event.deltaY) return
  const before = artboard.getBoundingClientRect()
  const x = (event.clientX - before.left) / before.width
  const y = (event.clientY - before.top) / before.height
  const direction = event.deltaY > 0 ? -1 : 1
  zoom.value = Math.max(25, Math.min(200, Math.round(zoom.value / 5) * 5 + direction * 5))
  await nextTick()
  const after = artboard.getBoundingClientRect()
  element.scrollLeft += after.left + x * after.width - event.clientX
  element.scrollTop += after.top + y * after.height - event.clientY
}
function setRegionVisibility(value: string) {
  const field = selected.value
  if (!field) return
  if (value === 'inherit') delete field.regionVisible
  else field.regionVisible = value === 'show'
  saved.value = false
}
function fitPage() {
  if (!canvas.value || !page.value) return
  zoom.value = Math.max(25, Math.min(200, Math.floor(Math.min(
    (canvas.value.clientWidth - 120 - (sampleUrl.value ? 48 : 0)) / (794 * (sampleUrl.value ? 2 : 1)),
    (canvas.value.clientHeight - 100) / (794 * Math.max(page.value.height / page.value.width, sampleUrl.value ? sampleHeightRatio : 0)),
  ) * 100)))
}
const input = ref<HTMLInputElement>()
const page = computed(() => template.value?.pages[pageIndex.value])
const fields = computed(() => page.value ? [...(page.value.fields || []), ...(page.value.tables || []).flatMap(table => table.fields)] : [])
const json = computed(() => JSON.stringify(template.value ? templateForSave(template.value) : undefined, null, 2))
const sourceText = computed(() => {
  const source = selected.value?.source
  if (!source) return '页面区域'
  if (source.sheet) return source.sheet + '!' + source.range
  return '表 ' + source.table + ' · 行 ' + source.row + ' · 列 ' + source.column
})
const alignmentGroups = [
  { key: 'horizontalAlign', label: '水平对齐', options: [
    { value: 'left', label: '左对齐', icon: RiAlignLeft },
    { value: 'center', label: '水平居中', icon: RiAlignCenter },
    { value: 'right', label: '右对齐', icon: RiAlignRight },
  ] },
  { key: 'verticalAlign', label: '垂直对齐', options: [
    { value: 'top', label: '顶部对齐', icon: RiAlignTop },
    { value: 'center', label: '垂直居中', icon: RiAlignVertically },
    { value: 'bottom', label: '底部对齐', icon: RiAlignBottom },
  ] },
] as const
function alignmentValue(axis: 'horizontalAlign' | 'verticalAlign') {
  const value = selected.value?.style?.[axis]?.toLowerCase()
  if (!value) return ''
  if (value === 'general') return axis === 'horizontalAlign' ? 'left' : 'bottom'
  return value === 'middle' || value === 'centercontinuous' ? 'center' : value
}
const fontOptions = computed(() => {
  const names = new Set(documentFonts.map(font => font.value))
  for (const page of template.value?.pages || []) {
    for (const field of [...(page.fields || []), ...(page.tables || []).flatMap(table => table.fields)]) {
      if (field.style?.fontFamily) names.add(fontKey(field.style.fontFamily))
    }
  }
  return [...names].map(value => ({ value, label: documentFonts.find(font => font.value === value)?.label || value }))
})
const currentFontSize = computed(() => selected.value?.style?.fontSizePt || 10)
const customFontSize = computed(() => !namedFontSizes.some(size => size.value === currentFontSize.value) && !pointFontSizes.includes(currentFontSize.value))
const fontSelectOptions = computed(() => fontOptions.value.map(font => ({ value: font.value, label: font.label, style: { fontFamily: fontStack(font.value) } })))
const fontSizeOptions = computed(() => {
  const options: { value: number; label: string }[] = []
  const seen = new Set<number>()
  const push = (value: number, label: string) => { if (!seen.has(value)) { seen.add(value); options.push({ value, label }) } }
  if (customFontSize.value) push(currentFontSize.value, String(currentFontSize.value))
  for (const size of namedFontSizes) push(size.value, size.label)
  for (const size of pointFontSizes) push(size, String(size))
  return options
})
const regionVisibilityOptions = [
  { value: 'inherit', label: '跟随全局' },
  { value: 'show', label: '始终显示' },
  { value: 'hide', label: '始终隐藏' },
]
function configureField(patch: Partial<FieldDefinition>) {
  const anchor=selected.value, currentTemplate=template.value
  if(!anchor || selectedFields.value.length!==1 || !currentTemplate || protectSupplementary([anchor]))return
  let business=currentTemplate.businessFields?.find(field=>field.businessFieldUuid===anchor.businessFieldUuid)
  if(!business) {
    const draft: FieldDefinition={name:'',dataType:'text',imageRecognition:true,...anchor.definition,...patch}
    anchor.definition=draft
    if(!draft.name.trim()) return
    business={...draft,businessFieldUuid:'biz_'+crypto.randomUUID().replaceAll('-','')}
    currentTemplate.businessFields ??= [];currentTemplate.businessFields.push(business);anchor.businessFieldUuid=business.businessFieldUuid
  } else {
    const renamed=patch.name!==undefined && patch.name.trim()!==business.name.trim()
    const changedType=patch.dataType!==undefined && patch.dataType!==business.dataType
    if(renamed)delete business.mappingRule
    if(renamed || changedType) {
      if(currentTemplate.mappingPreview)delete currentTemplate.mappingPreview.results[business.businessFieldUuid]
      sourceRequest++;selectingSource.value=false;picking.value=false;sampleError.value=''
    }
    Object.assign(business,patch)
  }
  syncBindings(currentTemplate);trial.value=false;saved.value=false;notice.value=''
}

function updateTextStyle(patch: Partial<FieldStyle>) {
  const field = selected.value
  if (!field) return
  field.style = { ...field.style, ...patch }
  field.textOverride ??= field.label ?? ''
  saved.value = false
  notice.value = ''
}
function setAlignment(axis: 'horizontalAlign' | 'verticalAlign', value: string) {
  updateTextStyle({ [axis]: value })
}
function toggleEmphasis(key: 'bold' | 'italic') {
  updateTextStyle({ [key]: !selected.value?.style?.[key] })
}
function toggleUnderline() {
  const field=selected.value
  if(!field)return
  const {start,end}=labelSelection.value
  applyLabelInput()
  const text=field.textOverride ?? field.label ?? ''
  if(!text.length) { updateTextStyle({underline:field.style?.underline ? undefined : 'single'});return }
  const from=end>start?start:0, to=end>start?end:text.length
  field.underlineRanges=toggleRange(underlineRanges(field),from,to,text.length)
  const inline=field.inlineTemplate
  if(inline && text.startsWith(inline.prefix) && text.endsWith(inline.suffix)
     && from===inline.prefix.length && to===text.length-inline.suffix.length) {
    inline.valueStyle.underline=rangeUnderlined(field.underlineRanges,from,to)?'single':'none'
  }
  field.textOverride ??= field.label ?? ''
  saved.value=false;notice.value=''
  nextTick(() => {labelInput.value?.focus();labelInput.value?.setSelectionRange(from,to);rememberTextSelection()})
}
function fieldListLabel(field: Field, index: number) {
  const text = field.textOverride ?? field.label
  return text?.trim() || (field.textOverride !== undefined ? '空白区域' : '单元格 ' + String(index + 1).padStart(3, '0'))
}

const canMerge = computed(() => !supplementarySelected.value && !!page.value && !!mergeBounds(selectedFields.value, page.value) && new Set(selectedFields.value.map(field=>field.businessFieldUuid).filter(Boolean)).size <= 1)

function display(value: Template, isSaved = false) {
  removeSample()
  deletions.length = 0
  const migrated=migrateBindings(value)
  template.value = value
  pageIndex.value = 0
  selectedFields.value = []
  splitDraft.value = undefined
  saved.value = isSaved && !migrated
  libraryTab.value = 'pages'
  error.value = ''
  notice.value = ''
}
async function refresh() { library.value = await listTemplates() }
const deleteTarget = ref<TemplateSummary>()
const deleteDialog = ref<HTMLDialogElement>()
const deleting = ref(false)
const deleteError = ref('')
async function requestDelete(item: TemplateSummary) {
  deleteTarget.value = item; deleteError.value = ''
  await nextTick(); deleteDialog.value?.showModal()
}
function cancelDelete() { if (!deleting.value) deleteDialog.value?.close() }
async function confirmDelete() {
  if (!deleteTarget.value || deleting.value) return
  const id = deleteTarget.value.templateUuid
  deleting.value = true; deleteError.value = ''
  try {
    await deleteTemplate(id)
    library.value = library.value.filter(item => item.templateUuid !== id)
    if (template.value?.templateUuid === id) {
      removeSample(); deletions.length=0; template.value=undefined; pageIndex.value=0
      selectedFields.value=[]; splitDraft.value=undefined; saved.value=false; notice.value=''; error.value=''
    }
    deleteDialog.value?.close()
  } catch (e) { deleteError.value=(e as Error).message }
  finally { deleting.value=false }
}
async function upload(file?: File) {
  if (!file || busy.value) return
  if (!/\.(pdf|xlsx?|docx?|png|jpe?g|bmp|tiff?|webp)$/i.test(file.name)) { error.value = '请选择 PDF、Excel、Word 或图片文件'; return }
  busy.value = true; error.value = ''; notice.value = ''
  try { display((await uploadTemplate(file)).template) }
  catch (e) { error.value = (e as Error).message }
  finally { busy.value = false; if (input.value) input.value.value = '' }
}
function onFile(event: Event) { void upload((event.target as HTMLInputElement).files?.[0]) }
function drop(event: DragEvent) { void upload(event.dataTransfer?.files[0]) }
async function open(id: string) {
  if (busy.value) return
  busy.value = true
  try { display((await loadTemplate(id)).template, true) }
  catch (e) { error.value = (e as Error).message }
  finally { busy.value = false }
}
async function save() {
  if (!template.value || busy.value) return
  for (const currentPage of template.value.pages) {
    const invalid = [...(currentPage.fields || []), ...(currentPage.tables || []).flatMap(table => table.fields)]
      .find(field => field.businessFieldUuid && field.definition?.imageRecognition && !field.definition.name.trim())
    if (invalid) {
      pageIndex.value = template.value.pages.indexOf(currentPage)
      selectedFields.value = [invalid]
      inspectorTab.value = 'data'
      error.value = '参与图片识别回填的区域需要填写字段名称'
      return
    }
  }
  busy.value = true; error.value = ''
  try { await saveTemplate(templateForSave(template.value)); saved.value = true; notice.value = '模板已保存'; await refresh() }
  catch (e) { error.value = (e as Error).message }
  finally { busy.value = false }
}
function selectField(field: Field, event?: MouseEvent) {
  inspectedSupplementary.value=undefined
  picking.value = false; sourceTextIds.value = []
  splitDraft.value = undefined
  tool.value = 'select'
  if (event?.shiftKey) {
    const exists = selectedFields.value.some(item => item.fieldUuid === field.fieldUuid)
    selectedFields.value = exists
      ? selectedFields.value.filter(item => item.fieldUuid !== field.fieldUuid)
      : [...selectedFields.value, field]
    return
  }
  selectedFields.value = [field]
}
function resizeField(fieldUuid: string, rect: Rect) {
  const field = fields.value.find(item => item.fieldUuid === fieldUuid)
  if (field && protectSupplementary([field]))return
  if (!field || (field.rect.x === rect.x && field.rect.y === rect.y && field.rect.w === rect.w && field.rect.h === rect.h)) return
  field.rect = rect
  saved.value = false
  notice.value = ''
}
function applyRectInput(key: keyof Rect) {
  const field = selected.value
  const value = Number(rectInputs[key])
  if (!field || !rectInputs[key].trim() || !Number.isFinite(value)) {
    error.value = '请输入有效的百分比数值'
    return
  }

  const rect: Rect = { ...field.rect, [key]: value / 100 }
  if (rect.x < 0 || rect.y < 0 || rect.w <= 0 || rect.h <= 0 ||
      rect.x + rect.w > 1 || rect.y + rect.h > 1) {
    error.value = '位置与尺寸需大于 0，且区域必须位于页面范围内'
    return
  }

  error.value = ''
  resizeField(field.fieldUuid, rect)
}
function applyLabelInput() {
  if(protectSupplementary(selectedFields.value))return
  const field = selected.value
  if (!field || (field.textOverride ?? field.label ?? '') === labelDraft.value) return
  if(field.underlineRanges!==undefined)field.underlineRanges=editedRanges(field.underlineRanges,field.textOverride ?? field.label ?? '',labelDraft.value)
  if (labelDraft.value === (field.label ?? '')) delete field.textOverride
  else field.textOverride = labelDraft.value
  saved.value = false
  error.value = ''
  notice.value = ''
}
function onLabelEnter(event: KeyboardEvent) {
  if (event.shiftKey) return
  event.preventDefault()
  applyLabelInput()
}
function startSplit() {
  const field = selected.value
  if (!field || selectedFields.value.length !== 1 || protectSupplementary([field])) return
  const currentPage = page.value
  if (!currentPage) return
  const axis = field.rect.w * currentPage.width >= field.rect.h * currentPage.height ? 'x' : 'y'
  splitDraft.value = {
    fieldUuid: field.fieldUuid,
    axis,
    position: axis === 'x' ? field.rect.x + field.rect.w / 2 : field.rect.y + field.rect.h / 2,
  }
  error.value = ''
  notice.value = ''
}
function setSplitAxis(axis: 'x' | 'y') {
  const field = selected.value
  if (!field) return
  splitDraft.value = {
    fieldUuid: field.fieldUuid,
    axis,
    position: axis === 'x' ? field.rect.x + field.rect.w / 2 : field.rect.y + field.rect.h / 2,
  }
}
function updateSplitPosition(axis: 'x' | 'y', position: number) {
  if (splitDraft.value?.axis === axis) splitDraft.value = { ...splitDraft.value, position }
}
function confirmSplit() {
  const currentPage = page.value
  const field = selected.value
  const draft = splitDraft.value
  if (!currentPage || !field || !draft || draft.fieldUuid !== field.fieldUuid) return

  const rect = field.rect
  const position = draft.position
  const second: Field = {
    fieldUuid: 'fld_' + crypto.randomUUID().replace(/-/g, ''),
    rect: draft.axis === 'x'
      ? { x: position, y: rect.y, w: rect.x + rect.w - position, h: rect.h }
      : { x: rect.x, y: position, w: rect.w, h: rect.y + rect.h - position },
    style: field.style ? { ...field.style, borders: field.style.borders ? { ...field.style.borders } : undefined } : undefined,
  }
  field.rect = draft.axis === 'x'
    ? { ...rect, w: position - rect.x }
    : { ...rect, h: position - rect.y }

  const containers: Field[][] = []
  if (currentPage.fields) containers.push(currentPage.fields)
  for (const table of currentPage.tables || []) containers.push(table.fields)
  const target = containers.find(container => container.includes(field))
  if (!target) return
  target.splice(target.indexOf(field) + 1, 0, second)
  selectedFields.value = [field]
  splitDraft.value = undefined
  saved.value = false
  error.value = ''
  notice.value = '区域已拆分，原文字保留在左侧或上侧；选择另一侧可单独编辑文字'
}
function sortInReadingOrder(items: Field[]) {
  const rows: Field[][] = []
  const centerY = (field: Field) => field.rect.y + field.rect.h / 2
  const sortedByY = [...items].sort((a, b) => centerY(a) - centerY(b) || a.rect.x - b.rect.x)

  for (const field of sortedByY) {
    const row = rows.find(cells => cells.some(cell => {
      const overlap = Math.max(0, Math.min(field.rect.y + field.rect.h, cell.rect.y + cell.rect.h) - Math.max(field.rect.y, cell.rect.y))
      const smallerHeight = Math.max(0.001, Math.min(field.rect.h, cell.rect.h))
      const overlapRatio = overlap / smallerHeight
      const centerDistance = Math.abs(centerY(field) - centerY(cell))
      return overlapRatio >= 0.35 || centerDistance <= smallerHeight * 0.45
    }))
    if (row) row.push(field)
    else rows.push([field])
  }

  return rows
    .sort((a, b) => centerY(a[0]!) - centerY(b[0]!))
    .flatMap(row => row.sort((a, b) => a.rect.x - b.rect.x || a.rect.y - b.rect.y))
}
function mergeSelected() {
  const currentPage = page.value
  const items = selectedFields.value
  if (!currentPage || items.length < 2 || protectSupplementary(items)) return
  if(new Set(items.map(field=>field.businessFieldUuid).filter(Boolean)).size>1) { error.value='不同业务字段不能直接合并，请先调整字段绑定'; return }
  const bounds = mergeBounds(items,currentPage)
  if (!bounds) { error.value='请选择至少两个区域'; return }

  const ordered = sortInReadingOrder(items)
  const primary = ordered[0]!
  const left = Math.min(...items.map(field => field.rect.x))
  const top = Math.min(...items.map(field => field.rect.y))
  const right = Math.max(...items.map(field => field.rect.x + field.rect.w))
  const bottom = Math.max(...items.map(field => field.rect.y + field.rect.h))
  const ids = new Set(items.map(field => field.fieldUuid))
  const hasOverride = ordered.some(field => field.textOverride !== undefined)
  const labels = ordered.map(field => field.label?.trim()).filter((label): label is string => Boolean(label))
  const displayLabels = ordered.map(field => (field.textOverride ?? field.label)?.trim()).filter((label): label is string => Boolean(label))
  const merged: Field = {
    fieldUuid: primary.fieldUuid,
    businessFieldUuid: primary.businessFieldUuid,
    rect: { x: left, y: top, w: right - left, h: bottom - top },
  }
  const definitions = ordered.filter(field => field.definition)
  if (definitions.length) merged.businessFieldUuid=primary.businessFieldUuid || definitions[0]!.businessFieldUuid
  if (primary.style) {
    merged.style = { ...primary.style, borders: primary.style.borders ? { ...primary.style.borders } : undefined }
  }
  if (labels.length) merged.label = labels.join(' ')
  if (hasOverride || displayLabels.length) merged.textOverride = displayLabels.join(' ')
  let textOffset=0
  merged.underlineRanges=ordered.flatMap(field=>{
    const full=field.textOverride ?? field.label ?? '', text=full.trim()
    if(!text)return []
    const leading=full.length-full.trimStart().length
    const ranges=underlineRanges(field).map(r=>({start:Math.max(0,r.start-leading),end:Math.min(text.length,r.end-leading)})).filter(r=>r.end>r.start)
    const shifted=ranges.map(r=>({start:r.start+textOffset,end:r.end+textOffset}))
    textOffset+=text.length+1
    return shifted
  })
  const sourceKey = JSON.stringify(primary.source || null)
  if (primary.source && ordered.every(field => JSON.stringify(field.source || null) === sourceKey)) {
    merged.source = { ...primary.source }
  }

  const containers: Field[][] = []
  if (currentPage.fields) containers.push(currentPage.fields)
  for (const table of currentPage.tables || []) containers.push(table.fields)
  const target = containers.find(container => container.some(field => field.fieldUuid === primary.fieldUuid))
  if (!target) return
  const targetIndex = target.findIndex(field => field.fieldUuid === primary.fieldUuid)
  const insertIndex = target.slice(0, targetIndex).filter(field => !ids.has(field.fieldUuid)).length
  const removed = containers.flatMap(container => container.flatMap((field,index) => ids.has(field.fieldUuid) ? [{container,index,field}] : []))
  const masks = mergeMasks(items,bounds,currentPage)
  currentPage.mergeMasks ??= []
  currentPage.mergeMasks.push(...masks)
  deletions.push({page:currentPage,removed,maskIds:[],created:[merged],mergeMaskIds:masks.map(mask=>mask.maskUuid)})
  for (const container of containers) {
    const retained = container.filter(field => !ids.has(field.fieldUuid))
    container.splice(0, container.length, ...retained)
  }
  target.splice(insertIndex, 0, merged)
  syncBindings(template.value!)
  selectedFields.value = [merged]
  splitDraft.value = undefined
  saved.value = false
  notice.value = ''
}
function clearSelection() { selectedFields.value = []; splitDraft.value = undefined }
function changePage(index: number) { removeSample();pageIndex.value = index; clearSelection() }
async function copyJson() {
  try {
    await navigator.clipboard.writeText(json.value)
    notice.value = 'JSON 已复制到剪贴板'
  } catch {
    error.value = '复制失败，请手动选择文本复制'
  }
}
type Deletion = {
  page: Page
  removed: { container: Field[]; index: number; field: Field }[]
  maskIds: string[]
  created?: Field[]
  mergeMaskIds?: string[]
}
const deletions: Deletion[] = []
function deleteSelectedRegions() {
  const currentPage = page.value
  if (!currentPage || !selectedFields.value.length || protectSupplementary(selectedFields.value)) return
  const ids = new Set(selectedIds.value)
  const containers = [currentPage.fields || [], ...(currentPage.tables || []).map(table => table.fields)]
  const removed = containers.flatMap(container => container.flatMap((field, index) => ids.has(field.fieldUuid) ? [{ container, index, field }] : []))
  if (!removed.length) return
  const masks = removed.map(({ container, field }) => {
    const inTable = currentPage.tables?.some(table => table.fields === container)
    // Keep the original table grid; exterior text masks extend slightly to cover edge pixels.
    const paddingX = (inTable ? -1 : 1) / currentPage.width
    const paddingY = (inTable ? -1 : 1) / currentPage.height
    return {
      maskUuid: 'mask_' + crypto.randomUUID(),
      rect: { x: field.rect.x - paddingX, y: field.rect.y - paddingY,
        w: Math.max(0, field.rect.w + paddingX * 2), h: Math.max(0, field.rect.h + paddingY * 2) },
      color: field.style?.fillColor?.slice(0, 7) || '#ffffff',
    }
  })
  for (const container of containers) {
    for (let index = container.length - 1; index >= 0; index--) {
      if (ids.has(container[index]!.fieldUuid)) container.splice(index, 1)
    }
  }
  currentPage.deletionMasks ??= []
  currentPage.deletionMasks.push(...masks)
  deletions.push({ page: currentPage, removed, maskIds: masks.map(mask => mask.maskUuid) })
  clearSelection()
  saved.value = false
  notice.value = ''
}
function undoRegionDeletion() {
  const deletion = deletions.pop()
  if (!deletion) return
  if (deletion.created) {
    for (const container of [deletion.page.fields || [], ...(deletion.page.tables || []).map(table=>table.fields)]) {
      for (let i=container.length-1;i>=0;i--) if (deletion.created.some(field=>field.fieldUuid===container[i]!.fieldUuid)) container.splice(i,1)
    }
  }
  deletion.page.mergeMasks=deletion.page.mergeMasks?.filter(mask=>!deletion.mergeMaskIds?.includes(mask.maskUuid))
  for (const { container, index, field } of deletion.removed) container.splice(index, 0, field)
  deletion.page.deletionMasks = deletion.page.deletionMasks?.filter(mask => !deletion.maskIds.includes(mask.maskUuid))
  pageIndex.value = template.value!.pages.indexOf(deletion.page)
  syncBindings(template.value!)
  selectedFields.value = deletion.removed.map(item => item.field)
  splitDraft.value = undefined
  saved.value = false
  notice.value = ''
}
function regionShortcut(event: KeyboardEvent) {
  if (event.defaultPrevented || event.isComposing || busy.value || printOpen.value || jsonOpen.value || picking.value || trial.value) return
  const target = event.target as HTMLElement | null
  if (target?.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="textbox"], [role="listbox"], [role="dialog"]')) return
  if ((event.ctrlKey || event.metaKey) && !event.shiftKey && !event.altKey && event.key.toLowerCase() === 'z' && deletions.length) {
    event.preventDefault()
    if (!event.repeat) undoRegionDeletion()
  } else if (event.key === 'Backspace' && !event.ctrlKey && !event.metaKey && !event.altKey && selectedFields.value.length) {
    event.preventDefault()
    if (!event.repeat) deleteSelectedRegions()
  }
}
onMounted(() => window.addEventListener('keydown', regionShortcut))
onUnmounted(() => window.removeEventListener('keydown', regionShortcut))
function printShortcut(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'p' && template.value) {
    event.preventDefault()
    printOpen.value = true
  }
}
onMounted(() => window.addEventListener('keydown', printShortcut))
onUnmounted(() => window.removeEventListener('keydown', printShortcut))
onMounted(() => refresh().catch(() => { error.value = '无法连接文档服务，请确认后端已启动' }))
</script>

<template>
  <PrintPreview v-if="printOpen && template" :template="template" :current-page="pageIndex" :preview-values="trialValues" @close="printOpen = false" />
  <div class="workspace" :inert="printOpen" @dragover.prevent @drop.prevent="drop">
    <input ref="sampleInput" class="file-input" type="file" accept="image/*" aria-label="上传样例图片文件" @change="showSample" />
    <input ref="input" class="file-input" type="file" accept=".pdf,.xlsx,.xls,.docx,.doc,.png,.jpg,.jpeg,.bmp,.tif,.tiff,.webp" @change="onFile" />
    <header class="appbar">
      <img class="app-logo" src="/logo.png" alt="SDIG" />
      <div class="app-actions">
        <button class="text-button" :disabled="busy" title="扫描件/图片由本地 OCR (RapidOCR) 逐格识别" @click="input?.click()">导入文档</button>
        <button class="text-button" :disabled="!template || busy" @click="printOpen = true">打印预览</button>
        <button class="text-button" :disabled="!template" @click="jsonOpen = true">JSON</button>
        <button class="primary" :disabled="!template || busy || saved" @click="save">{{ saved ? '已保存' : '保存模板' }}</button>
      </div>
    </header>
    <div v-if="error" class="message error" role="alert">{{ error.replace(/。/g, '') }}<button aria-label="关闭提示" @click="error = ''"><RiCloseLine size="16px" aria-hidden="true" /></button></div>
    <div v-if="notice" class="message success" role="status">{{ notice.replace(/。/g, '') }}<button aria-label="关闭提示" @click="notice = ''"><RiCloseLine size="16px" aria-hidden="true" /></button></div>
    <div class="editor-layout">
      <aside class="left-panel">
        <div class="panel-tabs" role="tablist" aria-label="文档导航">
          <button role="tab" :aria-selected="libraryTab === 'pages'" :class="{ active: libraryTab === 'pages' }" @click="libraryTab = 'pages'">页面</button>
          <button role="tab" :aria-selected="libraryTab === 'templates'" :class="{ active: libraryTab === 'templates' }" @click="libraryTab = 'templates'">模板</button>
        </div>
        <template v-if="libraryTab === 'pages'">
          <div class="page-panel-fixed">
            <div class="section-title">页面 <span>{{ template?.pages.length || 0 }}</span></div>
            <p v-if="!template" class="panel-empty">导入文档后显示页面</p>
            <button v-for="(p, index) in template?.pages || []" :key="p.pageUuid" class="page-item" :class="{ active: pageIndex === index }" @click="changePage(index)">
              <RiFilePaper2Line aria-hidden="true" />
              <span class="page-item-info">
                <span class="page-item-title"><span class="page-item-name">{{ template?.name }}</span><span class="page-item-format">{{ template?.sourceFormat.toUpperCase() }}</span></span>
                <span class="page-item-number">页面 {{ index + 1 }}</span>
              </span>
            </button>
            <template v-if="page">
              <div class="page-thumbnail"><img :src="imageUrl(page.background)" :alt="'第 ' + page.pageNo + ' 页缩略图'" /></div>
              <div class="section-title">区域 <span>{{ fields.length }}</span></div>
            </template>
          </div>
          <div v-if="page" class="layer-list">
            <button v-for="(field, index) in fields" :key="field.fieldUuid" class="layer-item" :class="{ active: selectedIds.includes(field.fieldUuid) }" @click="selectField(field, $event)">
              <RiDraggable class="layer-icon" size="16px" aria-hidden="true" /><span>{{ fieldListLabel(field, index) }}</span>
            </button>
          </div>
        </template>
        <template v-else>
          <div class="page-panel-fixed">
            <div class="section-title">已保存模板 <span>{{ library.length }}</span></div>
            <p v-if="!library.length" class="panel-empty">暂无模板</p>
          </div>
          <div v-if="library.length" class="layer-list">
            <div v-for="item in library" :key="item.templateUuid" class="library-row" :class="{ active: template?.templateUuid === item.templateUuid }">
            <button class="library-item" :class="{ active: template?.templateUuid === item.templateUuid }" :disabled="busy" @click="open(item.templateUuid)">
              <RiFilePaper2Line class="format-icon" size="20px" aria-hidden="true" />
              <span class="library-text"><strong>{{ item.name }}</strong><small>{{ item.sourceFormat.toUpperCase() }} · {{ item.pageCount }} 页</small></span>
            </button>
            <button class="library-delete" :disabled="busy" :aria-label="'删除模板：'+item.name" title="删除模板" @click.stop="requestDelete(item)"><RiDeleteBinLine size="17px" aria-hidden="true" /></button>
            </div>
          </div>
        </template>
      </aside>
      <main class="canvas-area">
        <div ref="canvas" class="canvas" :class="{ 'pan-mode': tool === 'hand', panning }" @wheel="zoomWithWheel" @pointerdown="startPan" @pointermove="movePan" @pointerup="panning = false" @pointercancel="panning = false" @click.self="clearSelection">
          <div v-if="page" class="canvas-documents" :class="{ 'has-sample': sampleUrl }" :style="{ width: ((sampleUrl ? 2 : 1) * 794 * zoom / 100 + (sampleUrl ? 48 : 0)) + 'px' }">
            <div v-if="sampleUrl" class="sample-artboard" :style="{ width: (794 * zoom / 100) + 'px' }"><div class="artboard-label sample-artboard-label"><span>样例图片</span><span :title="sampleName">{{ sampleName }}</span></div><SourceSample :url="sampleUrl" :sample="sampleResult" :mapping="currentMapping" :picking="picking" :selected-ids="sourceTextIds" @text="chooseSourceText" @area="chooseSource({rect:$event})" /></div>
            <div class="page-wrap" :style="{ width: (794 * zoom / 100) + 'px' }"><div class="artboard-label">{{ sampleUrl ? '目标模板 · ' : '' }}页面 {{ page.pageNo }}</div><div class="page-viewport" :style="{ height: (794 * zoom / 100 * page.height / page.width) + 'px' }"><TemplatePage :style="{ width: '794px', transform: `scale(${zoom / 100})`, transformOrigin: 'top left' }" :preview-values="trialValues" :page="page" :selected-ids="selectedIds" :show-regions="showRegions" :show-background="showBackground" :split-guide="splitDraft" @select="selectField" @resize="resizeField" @split-move="updateSplitPosition" /></div></div>
          </div>
          <div v-else class="empty-canvas"><RiBrushAiLine aria-hidden="true" /><p>拖入文件开始编辑</p><button class="secondary" :disabled="busy" @click="input?.click()">导入文档</button><p class="cloud-note">扫描件/图片由本地 OCR (RapidOCR) 识别</p></div>
        </div>
        <div class="canvas-tools" aria-label="画布工具">
          <button class="tool-button" :class="{ active: tool === 'select' }" aria-label="选择工具" :aria-pressed="tool === 'select'" title="选择" @click="tool = 'select'"><RiSendPlaneLine class="flip-x" aria-hidden="true" /></button>
          <button class="tool-button" :class="{ active: tool === 'hand' }" aria-label="移动画布" :aria-pressed="tool === 'hand'" title="移动画布" @click="tool = 'hand'"><RiHand aria-hidden="true" /></button>
          <span class="tool-divider"></span>
          <button class="tool-button" :disabled="!page || zoom <= 25" aria-label="缩小" @click="zoom = Math.max(25, zoom - 10)"><RiSubtractLine aria-hidden="true" /></button><span class="zoom-value">{{ zoom }}%</span><button class="tool-button" :disabled="!page || zoom >= 200" aria-label="放大" @click="zoom = Math.min(200, zoom + 10)"><RiAddLine aria-hidden="true" /></button>
          <span class="tool-divider"></span><button class="fit-button" :disabled="!page" @click="fitPage"><RiFullscreenLine size="16px" aria-hidden="true" />适应页面</button>
        </div>
      </main>
      <aside class="inspector">
        <div class="panel-tabs inspector-tabs" role="tablist" aria-label="区域配置"><button role="tab" :class="{ active: inspectorTab === 'properties' }" :aria-selected="inspectorTab === 'properties'" @click="inspectorTab = 'properties'">属性</button><button role="tab" :class="{ active: inspectorTab === 'data' }" :aria-selected="inspectorTab === 'data'" @click="inspectorTab = 'data'">数据</button></div>
        <SupplementaryPanel v-show="inspectorTab === 'data'" :page="page" :selected-fields="selectedFields" :result="supplementaryResult" :busy="recognizing || trialMatching || selectingSource" @configure="configureSupplementary" @remove-row="removeSupplementaryRow" @select-row="selectSupplementaryRow" @correct="correctSupplementary" @inspect="inspectSupplementary" />
        <DataPanel v-show="inspectorTab === 'data'" :key="template?.templateUuid || 'empty'" @configure-rule="configureRecognitionRule" @correct="correctRecognition" :selected="supplementarySelected ? undefined : selected" :selection-count="selectedFields.length" :supplementary-selected="supplementarySelected" :has-supplementary="!!page?.supplementaryRegion" :has-template="!!page" :sample-name="sampleName" :sample-error="sampleError" :selecting-source="selectingSource" :recognizing="recognizing" :recognized="!!sampleResult" :can-recognize="!!sampleFile" :mapping="currentMapping" :mapping-fields="mappingFields" :picking="picking" :trial="trial" :trial-matching="trialMatching" @recognize="recognizeUploadedSample" @pick="beginSourceSelection" @cancel-pick="picking=false" @confirm="confirmMapping" @trial="toggleTrialPreview" @select-field="selectField($event)" @upload="sampleInput?.click()" @remove="removeSample" @configure="configureField" />
        <div v-show="inspectorTab === 'properties'">
        <template v-if="selectedFields.length > 1">
          <section class="property-section">
            <div class="property-heading">多选区域</div>
            <h2>已选 {{ selectedFields.length }} 个格子</h2>
            <button class="primary merge-action" :disabled="!canMerge" @click="mergeSelected">合并为一个格子</button>
            <p class="property-hint">按住 Shift 点击可增减选中格子；合并范围按所选区域最外侧边界计算，包含中间空隙</p>
          </section>
        </template>
        <template v-else-if="selected">
          <section class="property-section"><div class="property-heading">{{ selected.source?.range ? '单元格' : '区域' }}</div><h2>{{ sourceText }}</h2><label class="detail-label" for="region-label">区域文字</label><textarea ref="labelInput" id="region-label" v-model="labelDraft" class="region-label-input" :placeholder="selected.textOverride !== undefined || selected.label ? '' : '空白区域'" @keydown.enter="onLabelEnter" @select="rememberTextSelection" @keyup="rememberTextSelection" @mouseup="rememberTextSelection"></textarea><p class="property-hint">按 Enter 确认；Shift+Enter 换行</p></section>
          <section class="property-section"><div class="property-heading">位置与尺寸 <span>%</span></div><div class="coordinates editable-coordinates"><label v-for="key in rectKeys" :key="key"><span>{{ key.toUpperCase() }}</span><input v-model="rectInputs[key]" type="number" step="0.01" :aria-label="key.toUpperCase() + ' 百分比'" @keydown.enter.prevent="applyRectInput(key)" /></label></div><p class="property-hint">输入数值后按 Enter 确认；拖动控制点时数值会同步更新</p></section>
          <section class="property-section">
            <div class="property-heading">文字与单元格样式</div>
            <div class="style-details">
              <div class="style-font-row">
                <label class="style-card"><small>字体</small><StyleSelect aria-label="字体" :model-value="fontKey(selected.style?.fontFamily)" :options="fontSelectOptions" @update:model-value="updateTextStyle({ fontFamily: String($event) })" /></label>
                <label class="style-card"><small>字号</small><StyleSelect aria-label="字号" :model-value="currentFontSize" :options="fontSizeOptions" @update:model-value="updateTextStyle({ fontSizePt: Number($event) })" /></label>
              </div>
              <div class="style-emphasis">
                <button type="button" class="style-tag" :class="{ active: selected.style?.bold }" :aria-pressed="!!selected.style?.bold" aria-label="加粗" title="加粗" @click="toggleEmphasis('bold')">B</button>
                <button type="button" class="style-tag italic" :class="{ active: selected.style?.italic }" :aria-pressed="!!selected.style?.italic" aria-label="斜体" title="斜体" @click="toggleEmphasis('italic')">I</button>
                <button type="button" class="style-tag underline" :class="{ active: underlineActive }" :aria-pressed="underlineActive" aria-label="下划线" title="下划线" @pointerdown.prevent @click="toggleUnderline">U</button>
              </div>
              <div class="style-color-editor"><div class="style-subheading">文字颜色</div><ColorPicker :key="selected.fieldUuid + '-text'" :model-value="selected.style?.color || '#000000'" @update:model-value="updateTextStyle({ color: $event })" /></div>
              <div v-if="selected.style?.fillColor" class="style-color-editor"><div class="style-subheading">单元格填充</div><ColorPicker :key="selected.fieldUuid + '-fill'" label="单元格填充" :model-value="selected.style?.fillColor" @update:model-value="updateTextStyle({ fillColor: $event })" /></div>
              <div class="alignment-controls">
                <div class="style-subheading">对齐</div>
                <div class="alignment-groups">
                  <div v-for="group in alignmentGroups" :key="group.key" class="alignment-group" role="group" :aria-label="group.label">
                    <button v-for="option in group.options" :key="option.value" type="button"
                      :class="{ active: alignmentValue(group.key) === option.value }"
                      :aria-pressed="alignmentValue(group.key) === option.value" :aria-label="option.label" :title="option.label"
                      @click="setAlignment(group.key, option.value)">
                      <component :is="option.icon" size="18px" aria-hidden="true" />
                    </button>
                  </div>
                </div>
              </div>
              <div v-if="selected.style?.wrapText !== undefined" class="style-value-row"><span>换行</span><strong>{{ selected.style?.wrapText ? '自动换行' : '关闭' }}</strong></div>
              <div v-if="selected.style?.rotation" class="style-value-row"><span>文字旋转</span><strong>{{ selected.style?.rotation }}°</strong></div>
              <div v-if="selected.style?.numberFormat" class="style-value-row"><span>数字格式</span><strong>{{ selected.style?.numberFormat }}</strong></div>

            </div>
          </section>
          <section v-if="!splitDraft" class="property-section"><div class="property-heading">区域调整</div><button class="secondary" @click="startSplit">拆分区域</button><p class="property-hint">把被误合并的区域拆成两个独立区域</p></section>
          <section v-else-if="splitDraft.fieldUuid === selected.fieldUuid" class="property-section"><div class="property-heading">拆分区域</div><p class="property-hint split-hint">拖动画布上的蓝色分割线调整位置</p><div class="split-axis-toggle"><button class="secondary" :class="{ active: splitDraft.axis === 'x' }" @click="setSplitAxis('x')">左右拆分</button><button class="secondary" :class="{ active: splitDraft.axis === 'y' }" @click="setSplitAxis('y')">上下拆分</button></div><div class="split-actions"><button class="secondary" @click="splitDraft = undefined">取消</button><button class="primary" @click="confirmSplit">确认拆分</button></div></section>
        </template>
        <template v-else>
          <section class="property-section"><div class="property-heading">{{ page ? '页面' : '画布' }}</div><div v-if="page" class="coordinates"><div><span>W</span><strong>{{ page.width }}</strong></div><div><span>H</span><strong>{{ page.height }}</strong></div></div><p class="property-hint">{{ page ? '选择格子查看属性；按住 Shift 可多选并合并' : '当前没有打开的文档' }}</p></section>
        </template>
        <section class="property-section"><div class="property-heading">显示</div>
          <label v-if="selectedFields.length === 1 && selected" class="style-card region-visibility"><small>当前单元格边界</small><StyleSelect aria-label="当前单元格边界" :model-value="selected.regionVisible === undefined ? 'inherit' : selected.regionVisible ? 'show' : 'hide'" :options="regionVisibilityOptions" @update:model-value="setRegionVisibility(String($event))" /></label>
          <p v-if="selectedFields.length === 1" class="property-hint region-visibility-hint">选中时仍显示蓝色操作框</p>
          <label class="region-toggle"><input v-model="showRegions" type="checkbox" />区域边界</label><label class="region-toggle"><input v-model="showBackground" type="checkbox" />页面背景</label></section>

        </div>
      </aside>
    </div>
    <div v-if="busy" class="loading" role="status"><RiLoader4Line class="spinner" size="16px" aria-hidden="true" />正在解析文档并识别文字与表格…</div>
    <dialog ref="deleteDialog" class="delete-template-dialog" aria-labelledby="delete-template-title" @cancel="deleting && $event.preventDefault()">
      <h2 id="delete-template-title">删除模板？</h2>
      <p>“{{ deleteTarget?.name }}”将从模板列表移除</p>
      <p v-if="template?.templateUuid === deleteTarget?.templateUuid && !saved" class="delete-note">当前未保存的修改也会丢弃</p>
      <p v-if="deleteError" class="delete-error" role="alert">{{ deleteError }}</p>
      <footer><button class="secondary" :disabled="deleting" @click="cancelDelete">取消</button><button class="delete-confirm" :disabled="deleting" @click="confirmDelete">{{ deleting ? '正在删除…' : '删除模板' }}</button></footer>
    </dialog>
    <div v-if="jsonOpen" class="modal-backdrop" @click.self="jsonOpen = false" @keydown.esc="jsonOpen = false">
      <section class="json-modal" role="dialog" aria-modal="true" aria-label="模板 JSON" tabindex="-1"><header><h2>模板 JSON</h2><button aria-label="关闭 JSON" @click="jsonOpen = false"><RiCloseLine size="16px" aria-hidden="true" /></button></header><pre>{{ json }}</pre><footer><button class="secondary" @click="jsonOpen = false">关闭</button><button class="primary" @click="copyJson">复制全部</button></footer></section>
    </div>
  </div>
</template>






<style scoped>
.library-row { display:flex; align-items:center; position:relative; }
.library-row:hover,.library-row.active { background:#e8f1ff; }
.library-row .library-item { flex:1; min-width:0; }
.library-row .library-item,.library-row .library-item:hover,.library-row .library-item.active { background:transparent; }
.library-delete { flex-shrink:0; display:flex; align-items:center; justify-content:center; width:30px; height:30px; margin-right:8px; padding:0; border:0; border-radius:5px; background:transparent; color:#8b929e; cursor:pointer; }
.library-delete:hover:not(:disabled),.library-delete:focus-visible { color:#d43d3d; background:transparent; }
.library-delete:focus-visible { outline:2px solid #0d75ed; outline-offset:2px; }
.delete-template-dialog { border:1px solid #e1e4ea; border-radius:12px; padding:24px; width:360px; max-width:calc(100vw - 40px); color:#303238; box-shadow:0 12px 50px #0003; }
.delete-template-dialog::backdrop { background:#11182755; backdrop-filter:blur(2px); -webkit-backdrop-filter:blur(2px); }
.delete-template-dialog h2 { margin:0 0 16px; font-size:16px; }
.delete-template-dialog p { line-height:1.7; overflow-wrap:anywhere; }
.delete-template-dialog footer { display:flex; justify-content:flex-end; gap:8px; margin-top:24px; }
.delete-note { color:#858b96; font-size:12px; }
.delete-error { color:#c43d3d; }
.delete-confirm { background:#dc3d3d; color:white; border:1px solid #dc3d3d; border-radius:5px; padding:8px 14px; }
</style>
