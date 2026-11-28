import type { Identity } from './contracts'

const owner = '[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*'
const repositoryPattern = new RegExp('^' + owner + '/[a-zA-Z0-9_.-]{1,100}$')
export const uuidPattern = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i
export function validRepository(name: string) {
  return repositoryPattern.test(name) && name.indexOf('/') <= 39 && !name.endsWith('/.') && !name.endsWith('/..')
}
const encodeSegment = (segment: string) => encodeURIComponent(segment).replace(/[!'()*]/g, (char) => '%' + char.charCodeAt(0).toString(16).toUpperCase())

export function pinnedLink(identity: Identity, path: string, start: number | null, end: number | null, link: string) {
  if (!validRepository(identity.repository) || !/^[0-9a-f]{40}$/.test(identity.commit_sha)) return null
  const segments = path.split('/')
  if (segments.some((part) => !part || part === '.' || part === '..' || part.includes('\\') ||
    Array.from(part).some((char) => char.charCodeAt(0) < 32 || char.charCodeAt(0) === 127))) return null
  if (start !== null && (!Number.isSafeInteger(start) || start < 1 || end === null || !Number.isSafeInteger(end) || end < start)) return null
  if (start === null && end !== null) return null
  try {
    const fragment = start === null ? '' : '#L' + start + (end === start ? '' : '-L' + end)
    const expected = 'https://github.com/' + identity.repository + '/blob/' + identity.commit_sha + '/' + segments.map(encodeSegment).join('/') + fragment
    return link === expected ? expected : null
  } catch {
    return null
  }
}
export function sourceLines(text: string) {
  return (text.match(/[^\r\n]*(?:\r\n|\r|\n|$)/g) ?? [])
    .filter(Boolean).map((line) => line.replace(/(?:\r\n|\r|\n)$/, ''))
}
