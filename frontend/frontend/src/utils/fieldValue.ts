import type { FieldDefinition } from '../types/template'
export function displayFieldValue(text: string, dataType?: FieldDefinition['dataType']) {
  const date = dataType === 'date' && /^(\d{4})-(\d{2})-(\d{2})$/.exec(text)
  return date ? `${date[1]}年${Number(date[2])}月${Number(date[3])}日` : text
}
