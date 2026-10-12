export const documentFonts = [
  { value: 'SimSun', label: '宋体' },
  { value: 'SimHei', label: '黑体' },
  { value: 'Microsoft YaHei', label: '微软雅黑' },
  { value: 'FangSong', label: '仿宋' },
  { value: 'KaiTi', label: '楷体' },
  { value: 'DengXian', label: '等线' },
  { value: 'Arial', label: 'Arial' },
  { value: 'Times New Roman', label: 'Times New Roman' },
  { value: 'Calibri', label: 'Calibri' },
]
const aliases: Record<string, string> = {
  宋体: 'SimSun', 黑体: 'SimHei', 微软雅黑: 'Microsoft YaHei', 仿宋: 'FangSong', 楷体: 'KaiTi', 等线: 'DengXian',
  ArialMT: 'Arial', TimesNewRomanPSMT: 'Times New Roman',
}
export function fontKey(name?: string) { return aliases[name || ''] || name || 'SimSun' }
export function fontStack(name?: string) {
  return `${JSON.stringify(fontKey(name))}, "SimSun", "宋体", serif`
}
export const namedFontSizes = [
  { label: '初号', value: 42 }, { label: '小初', value: 36 },
  { label: '一号', value: 26 }, { label: '小一', value: 24 },
  { label: '二号', value: 22 }, { label: '小二', value: 18 },
  { label: '三号', value: 16 }, { label: '小三', value: 15 },
  { label: '四号', value: 14 }, { label: '小四', value: 12 },
  { label: '五号', value: 10.5 }, { label: '小五', value: 9 },
  { label: '六号', value: 7.5 }, { label: '小六', value: 6.5 },
  { label: '七号', value: 5.5 }, { label: '八号', value: 5 },
]
export const pointFontSizes = [5, 5.5, 6.5, 7.5, 8, 9, 10, 10.5, 11, 12, 14, 16, 18, 20, 22, 24, 26, 28, 36, 48, 72]
