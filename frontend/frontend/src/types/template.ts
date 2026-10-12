export interface TextRange { start: number; end: number }
export interface Rect { x: number; y: number; w: number; h: number }
export interface BorderStyle { style?: string; widthPt?: number; color?: string }
export interface FieldStyle {
  fontFamily?: string
  fontSizePt?: number
  bold?: boolean
  italic?: boolean
  underline?: string
  color?: string
  paddingPt?: Partial<Record<'top' | 'right' | 'bottom' | 'left', number>>
  horizontalAlign?: string
  verticalAlign?: string
  wrapText?: boolean
  rotation?: number
  numberFormat?: string
  fillColor?: string
  borders?: Partial<Record<'top' | 'right' | 'bottom' | 'left', BorderStyle | null>>
}
export interface MappingRule {
  kind: 'semantic' | 'label' | 'anchor' | 'position'
  rowLabel?: string
  column?: 'measurement' | 'rate' | 'requirement'
  aliases?: string[]
  rowAliases?: string[]
  valueIndex?: number
  label?: string
  rect?: Rect
  tableRelative?: boolean
  cellCount?: number
  aspectRatio?: number
  signature?: {label:string;x:number;y:number}[]
}
export interface BusinessField extends FieldDefinition { businessFieldUuid: string; mappingRule?: MappingRule }
export interface FieldDefinition {
  name: string
  dataType: 'text' | 'number' | 'percent' | 'date'
  imageRecognition: boolean
}
export interface Field {
  fieldUuid: string
  businessFieldUuid?: string
  rect: Rect
  label?: string
  textOverride?: string
  underlineRanges?: TextRange[]
  inlineTemplate?: { prefix: string; suffix: string; placeholder: string; source: string; valueStyle: { underline: string; paddingEm: number }; inputRect?: Rect }
  regionVisible?: boolean
  definition?: FieldDefinition
  mapping?: SourceMapping
  style?: FieldStyle
  source?: { sheet?: string; range?: string; table?: number; row?: number; column?: number; columnSpan?: number }
}
export type SupplementaryRole = 'name' | 'requirement' | 'measurement' | 'rate'
export interface SupplementaryRegion { rows: Record<SupplementaryRole, string[]>[] }
export interface SupplementaryRecord {
  recordId: string; values: Record<SupplementaryRole,string>; rawValues: Record<SupplementaryRole,string>
  sourceRects: Record<SupplementaryRole,Rect>; targetRow: number | null; warning: string; corrected: boolean
}
export interface SupplementaryResult { values: Record<string,string>; records: SupplementaryRecord[]; warning: string }
export interface Page {
  supplementaryRegion?: SupplementaryRegion
  pageUuid: string
  pageNo: number
  width: number
  height: number
  background: string
  mergeMasks?: { maskUuid: string; rect: Rect; color: string }[]
  deletionMasks?: { maskUuid: string; rect: Rect; color: string }[]
  tables?: { tableUuid: string; name?: string; fields: Field[] }[]
  fields?: Field[]
}
export interface Template {
  templateUuid: string
  name: string
  version: number
  sourceFormat: string
  mappingScheme?: { sampleId: string; name: string }
  businessFields?: BusinessField[]
  mappingPreview?: {sampleId:string;results:Record<string,SourceMapping>}
  pages: Page[]
}
export interface TemplateSummary {
  templateUuid: string
  name: string
  sourceFormat: string
  pageCount: number
}

export interface SourceMapping { sampleId: string; sourceRect: Rect | null; textIds: string[]; text: string; warning: string; status: 'pending' | 'empty' | 'unmatched'; confirmed: boolean; method?: string; rawText?: string; basis?: string; corrected?: boolean; proposedRule?: MappingRule | null }
export interface SampleResult { supplementary?: SupplementaryResult | null; sampleId: string; name: string; width: number; height: number; image: string; tables?: { cells: { cellUuid: string; rect: Rect; text?: string }[] }[]; textItems?: { textUuid: string; text: string; rect: Rect; confidence?: number }[]; suggestions: Record<string, SourceMapping> }
